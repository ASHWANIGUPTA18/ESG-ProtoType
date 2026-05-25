"""Compute emissions for an ActivityRecord.

Pick the best EmissionFactor by (activity_type, region, year, method) and
return a Decimal kgCO2e value. Records that have no factor get a
FACTOR_NOT_FOUND flag added by the caller; we don't raise.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from emissions.models import EmissionFactor, EmissionResult
from normalization.models import ActivityRecord


# Air-travel cabin multipliers - applied on top of the economy factor.
CABIN_MULTIPLIER = {
    "Y": Decimal("1.0"), "ECONOMY": Decimal("1.0"), "M": Decimal("1.0"),
    "W": Decimal("1.5"), "PREMIUM_ECONOMY": Decimal("1.5"), "PREMIUM": Decimal("1.5"),
    "C": Decimal("2.9"), "J": Decimal("2.9"), "BUSINESS": Decimal("2.9"),
    "F": Decimal("4.0"), "FIRST": Decimal("4.0"),
}

# Great-circle distance uplift for non-direct routing (DEFRA guidance: 8-9%).
GCD_UPLIFT = Decimal("1.09")


def _resolve_air_activity_type(distance_km: Decimal) -> str:
    """Pick short/long classification from distance for DEFRA factor selection."""
    if distance_km < 500:
        return "air_travel_economy_domestic"
    if distance_km < 3700:
        return "air_travel_economy_short"
    return "air_travel_economy_long"


def _factor_for(activity_type: str, region: str, year: int, method: str = "direct") -> EmissionFactor | None:
    """Try (activity, region, year, method) then progressively widen."""
    q = EmissionFactor.objects.filter(activity_type=activity_type)
    # Exact match
    exact = q.filter(region_code=region, year=year, method=method).first()
    if exact:
        return exact
    # Same region+method, different year (closest)
    same_region = q.filter(region_code=region, method=method).order_by("-year").first()
    if same_region:
        return same_region
    # Country fallback
    if "-" in region:  # e.g. US-CAMX -> US -> XX
        country = region.split("-")[0]
        country_factor = q.filter(region_code=country, method=method).order_by("-year").first()
        if country_factor:
            return country_factor
    # Global fallback
    return q.filter(region_code="XX", method=method).order_by("-year").first()


def compute_for_record(record: ActivityRecord) -> tuple[Optional[Decimal], Optional[EmissionFactor], list[str]]:
    """Return (kgCO2e, factor, debug_steps). None values mean no factor matched."""
    steps: list[str] = []
    atype = record.activity_type
    qty = record.quantity
    region = record.location_region or record.location_country or "XX"

    # Special case: air travel - resolve haul class from distance, apply cabin multiplier
    if atype.startswith("air_travel"):
        distance_km = qty  # parser already stores distance in km
        haul_type = _resolve_air_activity_type(distance_km)
        steps.append(f"air haul={haul_type} dist={distance_km}km")
        factor = _factor_for(haul_type, "XX", record.period_start.year, method="direct")
        if not factor:
            return None, None, steps
        cabin = (record.details.get("cabin_class") or "Y").upper()
        mult = CABIN_MULTIPLIER.get(cabin, Decimal("1.0"))
        steps.append(f"cabin_mult={mult}")
        # distance already includes uplift if parser applied it; if not, apply here
        if record.details.get("distance_includes_uplift") != True:
            distance_km = distance_km * GCD_UPLIFT
            steps.append(f"applied_uplift x{GCD_UPLIFT}")
        kg = Decimal(factor.factor_kgco2e) * distance_km * mult
        return kg.quantize(Decimal("0.0001")), factor, steps

    # Generic path: find factor and multiply
    method = "location" if atype == "electricity_grid" else "direct"
    factor = _factor_for(atype, region, record.period_start.year, method=method)
    if not factor:
        steps.append(f"no factor for {atype} {region} {record.period_start.year}")
        return None, None, steps
    steps.append(f"factor={factor.id} ({factor.activity_type} {factor.region_code} {factor.year})")
    kg = Decimal(factor.factor_kgco2e) * qty
    return kg.quantize(Decimal("0.0001")), factor, steps


def upsert_result(record: ActivityRecord) -> EmissionResult | None:
    """Compute and persist an EmissionResult. Returns the result or None."""
    kg, factor, _steps = compute_for_record(record)
    if kg is None or factor is None:
        # Drop any stale result
        EmissionResult.objects.filter(activity_record=record).delete()
        return None
    result, _ = EmissionResult.objects.update_or_create(
        activity_record=record,
        defaults=dict(factor=factor, kgco2e=kg),
    )
    return result
