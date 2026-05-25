"""Corporate travel (Concur-shape) parser.

We accept CSV in the shape Concur Standard Reporting produces: one row per
segment (air/hotel/car), keyed by TripId or PNR, with IATA codes for air,
check-in/out for hotel, SIPP class for car.

Key behaviors:
- Distance computed from airport IATA lat/lon using great-circle + 9% uplift.
- Multi-leg trips share one TripId; each leg is a separate ActivityRecord.
- Cancelled bookings filtered by BookingStatus.
- Hotel: nights computed from check-in/out dates, not a "Nights" column.
- Car: SIPP first-char → size class for factor selection.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from normalization.models import FlagCode
from reference.models import Airport
from tenants.models import Tenant

from .base import (
    ActivityDraft,
    ParseResult,
    build_alias_map,
    flag,
    haversine_km,
    iter_csv_dicts,
    normalize_header,
    parse_date,
    parse_decimal,
    read_text,
)


SOURCE_TYPE = "travel_concur"
PARSER_VERSION = "v1"


HEADER_ALIASES: dict[str, list[str]] = {
    "trip_id": ["TripId", "Trip ID", "Trip_ID", "PNR", "Record Locator", "RecordLocator", "Booking ID"],
    "segment_type": ["Segment Type", "SegmentType", "Travel Type", "Type", "Category"],
    "traveler_id": ["Traveler ID", "TravelerId", "Employee ID", "EmployeeId"],
    "traveler_name": ["Traveler Name", "Name", "Employee Name"],
    "origin": ["Origin", "StartCityCode", "DepartureCode", "From", "Departure Airport"],
    "destination": ["Destination", "EndCityCode", "ArrivalCode", "To", "Arrival Airport"],
    "departure_date": ["Departure Date", "StartDateLocal", "Start Date", "Travel Date", "Date"],
    "return_date": ["Return Date", "EndDateLocal", "End Date"],
    "carrier": ["Carrier", "MarketingCarrier", "Airline"],
    "flight_number": ["Flight Number", "FlightNumber", "Flight#"],
    "cabin_class": ["Cabin Class", "ClassOfService", "Class", "Service Class"],
    "ticket_number": ["Ticket Number", "TicketNumber"],
    "fare_amount": ["Fare Amount", "FareTotal", "Total Fare", "Amount", "Cost"],
    "currency": ["Currency", "CurrencyCode", "Curr"],
    "booking_status": ["Booking Status", "BookingStatus", "Status"],
    # Hotel
    "property_name": ["Property Name", "Hotel Name", "Hotel", "PropertyName"],
    "check_in": ["Check-In Date", "CheckInDate", "Check In", "Arrival"],
    "check_out": ["Check-Out Date", "CheckOutDate", "Check Out", "Departure"],
    "room_rate": ["Room Rate", "RoomRate", "Nightly Rate", "Rate"],
    "city": ["City", "CityCode", "Location"],
    "country": ["Country", "CountryCode"],
    # Car
    "car_type": ["Car Type", "CarTypeCode", "Vehicle Class", "SIPP", "SIPP Code"],
    "pickup_date": ["Pick-Up Date", "PickUpDate", "Pickup"],
    "dropoff_date": ["Drop-Off Date", "DropOffDate", "Dropoff", "Return Date"],
    "vendor": ["Vendor", "VendorCode", "Rental Company"],
}
ALIAS_LOOKUP = build_alias_map(HEADER_ALIASES)

# SIPP first character -> our canonical size class
SIPP_SIZE = {
    "M": "small", "N": "small", "E": "small",
    "H": "small", "C": "medium", "D": "medium",
    "I": "medium", "S": "medium", "R": "medium",
    "F": "large", "G": "large", "P": "large",
    "U": "large", "L": "large", "W": "large",
    "O": "large", "X": "large",
}

GCD_UPLIFT = Decimal("1.09")


def _row_key(row: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in row.items():
        if k is None:
            continue
        canon = ALIAS_LOOKUP.get(normalize_header(k))
        if canon:
            out[canon] = (v or "").strip()
        else:
            out[f"_extra__{normalize_header(k)}"] = (v or "").strip()
    return out


def _detect_segment_type(canonical: dict[str, str]) -> str:
    """Infer segment type from row contents if not explicitly provided."""
    explicit = canonical.get("segment_type", "").lower()
    if explicit:
        for word in ("air", "flight", "fly"):
            if word in explicit:
                return "air"
        for word in ("hotel", "lodging", "accommodation"):
            if word in explicit:
                return "hotel"
        for word in ("car", "rental", "vehicle"):
            if word in explicit:
                return "car"
        if "rail" in explicit:
            return "rail"
        return explicit
    if canonical.get("origin") and canonical.get("destination"):
        return "air"
    if canonical.get("property_name") or canonical.get("check_in"):
        return "hotel"
    if canonical.get("car_type") or canonical.get("vendor"):
        return "car"
    return "unknown"


def parse(path: str, tenant: Tenant) -> ParseResult:
    text, encoding = read_text(path)
    iter_rows, delimiter = iter_csv_dicts(text)

    result = ParseResult()
    result.summary["encoding"] = encoding
    result.summary["delimiter"] = delimiter

    # Load airport lookup
    airports = {a.iata: a for a in Airport.objects.all()}

    line_no = 1
    trips_seen: set[str] = set()
    cancelled = 0

    for row in iter_rows:
        line_no += 1
        canonical = _row_key(row)
        row_flags: list[dict[str, Any]] = []
        parse_errors: list[dict[str, Any]] = []

        # Skip cancelled bookings
        status = canonical.get("booking_status", "").upper()
        if status in ("CANCELLED", "CANCELED", "VOIDED", "REFUNDED"):
            row_flags.append(flag(FlagCode.CANCELLED_BOOKING, f"Booking status={status}, skipping"))
            result.raw_rows.append((line_no, canonical, parse_errors + row_flags))
            cancelled += 1
            continue

        trip_id = canonical.get("trip_id", "")
        if trip_id:
            trips_seen.add(trip_id)

        seg_type = _detect_segment_type(canonical)

        # Cost
        fare_raw = canonical.get("fare_amount", "") or canonical.get("room_rate", "")
        fare, _ = parse_decimal(fare_raw)
        currency = canonical.get("currency", "USD") or "USD"

        result.raw_rows.append((line_no, canonical, parse_errors))

        # ---------- AIR ----------
        if seg_type == "air":
            origin_code = (canonical.get("origin", "") or "").upper().strip()
            dest_code = (canonical.get("destination", "") or "").upper().strip()
            dep_raw = canonical.get("departure_date", "")
            dep_date, dflags = parse_date(dep_raw)
            row_flags.extend(flag(f, f"Departure date '{dep_raw}' ambiguous") for f in dflags)

            if not dep_date:
                parse_errors.append(flag("invalid_date", f"Could not parse departure date '{dep_raw}'"))
                continue

            origin = airports.get(origin_code)
            dest = airports.get(dest_code)
            if not origin:
                row_flags.append(flag(FlagCode.UNKNOWN_AIRPORT, f"Unknown origin airport: {origin_code}"))
            if not dest:
                row_flags.append(flag(FlagCode.UNKNOWN_AIRPORT, f"Unknown destination airport: {dest_code}"))

            if origin and dest:
                dist_km = Decimal(str(round(haversine_km(origin.lat, origin.lon, dest.lat, dest.lon), 1)))
                dist_km_uplifted = dist_km * GCD_UPLIFT
                row_flags.append(flag(FlagCode.DISTANCE_INFERRED, f"GCD {origin_code}-{dest_code} = {dist_km}km + 9% uplift", severity="info"))
            else:
                dist_km_uplifted = Decimal("0")
                row_flags.append(flag("distance_unknown", "Cannot compute distance without airport coords"))

            cabin = (canonical.get("cabin_class", "") or "Y").upper().strip()
            if len(cabin) > 1:
                cabin = cabin[0]

            haul = "air_travel_economy_long" if dist_km_uplifted > 3700 else ("air_travel_economy_short" if dist_km_uplifted > 500 else "air_travel_economy_domestic")
            activity_type = haul

            result.activities.append(ActivityDraft(
                scope=3,
                ghg_category="Business Travel - Air",
                activity_type=activity_type,
                quantity=dist_km_uplifted,
                unit_canonical="km",
                period_start=dep_date,
                period_end=dep_date,
                location_country="",
                location_region="",
                cost=fare,
                currency=currency,
                details={
                    "trip_id": trip_id,
                    "origin": origin_code,
                    "destination": dest_code,
                    "carrier": canonical.get("carrier"),
                    "flight_number": canonical.get("flight_number"),
                    "cabin_class": cabin,
                    "ticket_number": canonical.get("ticket_number"),
                    "gcd_km": str(dist_km) if origin and dest else "",
                    "distance_includes_uplift": True,
                },
                confidence_flags=row_flags,
                source_line_no=line_no,
            ))

        # ---------- HOTEL ----------
        elif seg_type == "hotel":
            ci_raw = canonical.get("check_in", "")
            co_raw = canonical.get("check_out", "")
            ci_date, ciflags = parse_date(ci_raw)
            co_date, coflags = parse_date(co_raw)
            row_flags.extend(flag(f, f"Check-in date '{ci_raw}' ambiguous") for f in ciflags)
            row_flags.extend(flag(f, f"Check-out date '{co_raw}' ambiguous") for f in coflags)

            if not ci_date:
                parse_errors.append(flag("invalid_date", f"Could not parse check-in '{ci_raw}'"))
                continue

            if co_date:
                nights = max((co_date - ci_date).days, 1)
            else:
                row_flags.append(flag(FlagCode.PERIOD_MISSING_END, "No check-out date; assuming 1 night"))
                nights = 1
                co_date = ci_date + timedelta(days=1)

            country = (canonical.get("country", "") or "").upper().strip()

            result.activities.append(ActivityDraft(
                scope=3,
                ghg_category="Business Travel - Hotel",
                activity_type="hotel_night",
                quantity=Decimal(nights),
                unit_canonical="room-night",
                period_start=ci_date,
                period_end=co_date,
                location_country=country,
                location_region="",
                cost=fare * nights if fare else None,
                currency=currency,
                details={
                    "trip_id": trip_id,
                    "property_name": canonical.get("property_name"),
                    "city": canonical.get("city"),
                    "country": country,
                    "room_rate_per_night": str(fare) if fare else "",
                },
                confidence_flags=row_flags,
                source_line_no=line_no,
            ))

        # ---------- CAR ----------
        elif seg_type == "car":
            pu_raw = canonical.get("pickup_date", "")
            do_raw = canonical.get("dropoff_date", "")
            pu_date, puflags = parse_date(pu_raw)
            do_date, doflags = parse_date(do_raw)
            row_flags.extend(flag(f, "Pickup date ambiguous") for f in puflags)
            row_flags.extend(flag(f, "Dropoff date ambiguous") for f in doflags)

            if not pu_date:
                parse_errors.append(flag("invalid_date", f"Could not parse pickup date '{pu_raw}'"))
                continue
            if not do_date:
                do_date = pu_date + timedelta(days=1)
                row_flags.append(flag(FlagCode.PERIOD_MISSING_END, "No drop-off date; assuming 1 day"))

            sipp = (canonical.get("car_type", "") or "").upper().strip()
            size = SIPP_SIZE.get(sipp[0], "medium") if sipp else "medium"
            activity_type = f"rental_car_{size}"

            # Rental cars: no odometer data in Concur. Assume 150km/day.
            days = max((do_date - pu_date).days, 1)
            est_km = Decimal(str(days * 150))
            row_flags.append(flag(FlagCode.DISTANCE_INFERRED, f"Estimated {est_km}km from {days} rental days x 150km/day", severity="info"))

            result.activities.append(ActivityDraft(
                scope=3,
                ghg_category="Business Travel - Ground",
                activity_type=activity_type,
                quantity=est_km,
                unit_canonical="km",
                period_start=pu_date,
                period_end=do_date,
                location_country="",
                location_region="",
                cost=fare,
                currency=currency,
                details={
                    "trip_id": trip_id,
                    "sipp_code": sipp,
                    "size_class": size,
                    "vendor": canonical.get("vendor"),
                    "rental_days": days,
                    "assumed_km_per_day": 150,
                },
                confidence_flags=row_flags,
                source_line_no=line_no,
            ))

        # ---------- UNKNOWN ----------
        else:
            row_flags.append(flag(FlagCode.UNMAPPED_ACTIVITY_TYPE, f"Unknown segment type: {seg_type}"))
            result.activities.append(ActivityDraft(
                scope=3,
                ghg_category="Business Travel - Other",
                activity_type=f"travel_{seg_type}",
                quantity=Decimal("0"),
                unit_canonical="?",
                period_start=parse_date(canonical.get("departure_date", ""))[0] or parse_date(canonical.get("pickup_date", ""))[0] or parse_date("20240101")[0],
                period_end=parse_date(canonical.get("return_date", ""))[0] or parse_date(canonical.get("dropoff_date", ""))[0] or parse_date("20240101")[0],
                location_country="",
                location_region="",
                cost=fare,
                currency=currency,
                details={"trip_id": trip_id, "raw_type": seg_type},
                confidence_flags=row_flags,
                source_line_no=line_no,
            ))

    result.summary.update({
        "rows_read": line_no - 1,
        "activities_created": len(result.activities),
        "unique_trips": len(trips_seen),
        "cancelled_skipped": cancelled,
    })
    return result
