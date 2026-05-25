"""Utility electricity parser.

We accept ConEd-style monthly billing CSV with columns like:
  Account Number, Service Address, Meter Number, Rate Class, Read Date From,
  Read Date To, Days, Read Type, Billed kWh, Demand kW, Total Charges, ...

Key behaviors:
- Pro-rata allocation of billing-period kWh into calendar months when a billing
  period straddles a month boundary (common: 28-34 day cycles starting mid-month).
- Estimated (E) vs Actual (A) read-type flagging.
- Multi-meter accounts.
- MWh/therms detection and rejection (flag, not silent conversion).
"""
from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal
from typing import Any

from normalization.models import FlagCode
from tenants.models import Tenant

from .base import (
    ActivityDraft,
    ParseResult,
    build_alias_map,
    flag,
    iter_csv_dicts,
    normalize_header,
    parse_date,
    parse_decimal,
    read_text,
)


SOURCE_TYPE = "utility_electricity"
PARSER_VERSION = "v1"


HEADER_ALIASES: dict[str, list[str]] = {
    "account_number": ["Account Number", "Account", "Account_No", "Acct #", "Kundennummer"],
    "service_address": ["Service Address", "Address", "Location", "Standort"],
    "meter_number": ["Meter Number", "Meter", "Meter_No", "MPAN", "Zählpunkt"],
    "rate_class": ["Rate Class", "Rate", "Tariff", "Rate Code", "Tarif"],
    "read_date_from": ["Read Date From", "Period Start", "Start Date", "Service Start Date", "Service Start", "Von"],
    "read_date_to": ["Read Date To", "Period End", "End Date", "Service End Date", "Service End", "Bis"],
    "days": ["Days", "Service Days", "Billing Days", "Tage"],
    "read_type": ["Read Type", "ReadType", "Type", "Ablesung"],
    "billed_kwh": ["Billed kWh", "kWh", "Usage kWh", "Consumption kWh", "Usage", "Consumption", "Verbrauch kWh"],
    "on_peak_kwh": ["On-Peak kWh", "On Peak kWh", "Peak kWh", "HT kWh"],
    "off_peak_kwh": ["Off-Peak kWh", "Off Peak kWh", "Shoulder kWh", "NT kWh"],
    "demand_kw": ["Demand kW", "Demand", "Peak Demand kW", "Max Demand", "Leistung kW"],
    "total_charges": ["Total Charges", "Total $", "Total Amount", "Amount", "Gesamtbetrag"],
    "currency": ["Currency", "Währung"],
    "supply_charge": ["Supply Charge", "Supply", "Lieferkosten"],
    "delivery_charge": ["Delivery Charge", "Delivery", "Netzentgelt"],
}
ALIAS_LOOKUP = build_alias_map(HEADER_ALIASES)

# US ZIP -> eGRID subregion (simplified — real mapping uses EPA's Power Profiler)
ZIP_REGION_PREFIX = {
    "100": "US-NYCW", "101": "US-NYCW", "104": "US-NYLI",
    "941": "US-CAMX", "940": "US-CAMX", "945": "US-CAMX",
    "606": "US-RFCW", "600": "US-RFCW",
    "303": "US-SRMV", "300": "US-SRMV",
    "021": "US-NEWE", "020": "US-NEWE",
}


def _zip_to_region(address: str) -> str:
    """Extract ZIP prefix from address and map to eGRID subregion. Very approximate."""
    m = re.search(r"\b(\d{5})(?:-\d{4})?\b", address)
    if m:
        z = m.group(1)
        for prefix, region in ZIP_REGION_PREFIX.items():
            if z.startswith(prefix):
                return region
    return ""


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


def _prorate_months(start, end, total_kwh: Decimal) -> list[tuple]:
    """Split a billing period into calendar months with pro-rata kWh.

    Returns [(month_start, month_end, allocated_kwh), ...]
    Each sub-period covers the overlap between the billing window and one
    calendar month. This is how ESG platforms handle non-aligned billing periods.
    """
    from calendar import monthrange
    from datetime import date

    chunks: list[tuple] = []
    cursor = start
    total_days = (end - start).days or 1
    while cursor <= end:
        mo_end = date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
        chunk_end = min(mo_end, end)
        chunk_days = (chunk_end - cursor).days + 1
        ratio = Decimal(str(chunk_days)) / Decimal(str(total_days))
        chunks.append((cursor, chunk_end, (total_kwh * ratio).quantize(Decimal("0.0001"))))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def parse(path: str, tenant: Tenant) -> ParseResult:
    text, encoding = read_text(path)
    iter_rows, delimiter = iter_csv_dicts(text)

    result = ParseResult()
    result.summary["encoding"] = encoding
    result.summary["delimiter"] = delimiter
    detected_locale: str | None = None

    line_no = 1
    meters_seen: set[str] = set()

    for row in iter_rows:
        line_no += 1
        canonical = _row_key(row)
        row_flags: list[dict[str, Any]] = []
        parse_errors: list[dict[str, Any]] = []

        # --- Period dates ---
        start_raw = canonical.get("read_date_from", "")
        end_raw = canonical.get("read_date_to", "")
        start_date, sflags = parse_date(start_raw)
        end_date, eflags = parse_date(end_raw)
        row_flags.extend(flag(f, f"Period start '{start_raw}' ambiguous") for f in sflags)
        row_flags.extend(flag(f, f"Period end '{end_raw}' ambiguous") for f in eflags)

        if start_date is None:
            parse_errors.append(flag("invalid_start_date", f"Could not parse period start '{start_raw}'"))
        if end_date is None:
            if start_date:
                row_flags.append(flag(FlagCode.PERIOD_MISSING_END, "No period end date; using start+30"))
                end_date = start_date + timedelta(days=30)
            else:
                parse_errors.append(flag("invalid_end_date", f"Could not parse period end '{end_raw}'"))

        # --- kWh ---
        kwh_raw = canonical.get("billed_kwh", "")
        kwh, loc = parse_decimal(kwh_raw)
        if loc and loc != "plain":
            detected_locale = loc

        # Sanity: reject if unit is MWh, therms, ccf
        if kwh is not None and any(k in kwh_raw.lower() for k in ("mwh", "therm", "ccf")):
            row_flags.append(flag(FlagCode.UNIT_UNCONVERTIBLE, f"Value '{kwh_raw}' looks like non-kWh unit"))

        if kwh is None and kwh_raw:
            parse_errors.append(flag("invalid_kwh", f"Could not parse kWh '{kwh_raw}'"))

        # Demand (captured for reference, not for emission calc)
        demand_raw = canonical.get("demand_kw", "")
        demand, _ = parse_decimal(demand_raw)

        # Cost
        charges_raw = canonical.get("total_charges", "")
        charges, _ = parse_decimal(charges_raw)
        currency = canonical.get("currency", "USD") or "USD"

        # Read type
        read_type = canonical.get("read_type", "").upper().strip()
        if read_type == "E":
            row_flags.append(flag(FlagCode.ESTIMATED_READ, "Read type is Estimated (E), not Actual"))

        # Location
        address = canonical.get("service_address", "")
        region = _zip_to_region(address)
        meter = canonical.get("meter_number", "")
        if meter:
            meters_seen.add(meter)

        result.raw_rows.append((line_no, canonical, parse_errors))

        if start_date is None or kwh is None:
            continue

        # Period straddle detection
        if start_date.month != end_date.month or start_date.year != end_date.year:
            row_flags.append(flag(FlagCode.PERIOD_STRADDLES_MONTHS,
                                  f"Billing period {start_date}-{end_date} crosses month boundary; pro-rating kWh"))
            chunks = _prorate_months(start_date, end_date, kwh)
        else:
            chunks = [(start_date, end_date, kwh)]

        cost_per_kwh = charges / kwh if charges and kwh else None
        for (cstart, cend, ckwh) in chunks:
            ccost = (cost_per_kwh * ckwh).quantize(Decimal("0.01")) if cost_per_kwh else None
            result.activities.append(ActivityDraft(
                scope=2,
                ghg_category="Purchased Electricity",
                activity_type="electricity_grid",
                quantity=ckwh,
                unit_canonical="kWh",
                period_start=cstart,
                period_end=cend,
                location_country="US",
                location_region=region,
                cost=ccost,
                currency=currency,
                details={
                    "account_number": canonical.get("account_number"),
                    "meter_number": meter,
                    "service_address": address,
                    "rate_class": canonical.get("rate_class"),
                    "read_type": read_type,
                    "on_peak_kwh": canonical.get("on_peak_kwh"),
                    "off_peak_kwh": canonical.get("off_peak_kwh"),
                    "demand_kw": str(demand) if demand else "",
                    "billing_period_start": str(start_date),
                    "billing_period_end": str(end_date),
                },
                confidence_flags=row_flags,
                source_line_no=line_no,
            ))

    result.summary.update({
        "rows_read": line_no - 1,
        "activities_created": len(result.activities),
        "unique_meters": len(meters_seen),
        "detected_locale": detected_locale or "plain",
    })
    return result
