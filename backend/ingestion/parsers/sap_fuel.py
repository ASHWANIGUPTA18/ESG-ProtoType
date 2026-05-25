"""SAP fuel & procurement parser.

We accept flat-file extracts in the shape an SAP BI analyst would produce from
SE16N / SQVI / a custom ABAP report over EKKO+EKPO+MKPF+MSEG. Columns are
aliased English<->German<->long-form so we can handle the realistic header
variations clients ship.

Classification fallback chain (first hit wins):
1. ClassificationRule (tenant-authored, from the DB) on any of MATNR, MATKL, SAKTO
2. Built-in MATKL whitelist for canonical fuel groupings
3. Built-in SAKTO GL-account whitelist
4. TXZ01 short-text keyword regex
5. None -> flag UNMAPPED_ACTIVITY_TYPE, status stays pending for analyst review.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from normalization.models import FlagCode, ClassificationRule
from reference.models import PlantLookup
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


SOURCE_TYPE = "sap_fuel"
PARSER_VERSION = "v1"


# --- Header aliases ---
HEADER_ALIASES: dict[str, list[str]] = {
    "ebeln": ["EBELN", "Belegnummer", "Bestellnummer", "PO Number", "PO_Number", "Purchase Order"],
    "ebelp": ["EBELP", "Position", "POS", "PO Item", "Item"],
    "budat": ["BUDAT", "Buchungsdatum", "Posting Date", "Posting_Date", "Buchungstag"],
    "werks": ["WERKS", "Werk", "Plant", "Plant Code"],
    "matnr": ["MATNR", "Material", "Materialnummer", "Material Number", "Material_No"],
    "txz01": ["TXZ01", "Materialkurztext", "Description", "Short_Text", "Mat. Description", "Kurztext"],
    "matkl": ["MATKL", "Materialgruppe", "Material Group", "Warengruppe"],
    "sakto": ["SAKTO", "Sachkonto", "GL Account", "GL_Account", "G/L Account"],
    "menge": ["MENGE", "Menge", "Quantity", "Qty", "Bestellmenge"],
    "meins": ["MEINS", "Mengeneinheit", "UoM", "Unit", "Unit of Measure", "BME"],
    "netwr": ["NETWR", "Wert", "Nettowert", "Net Value", "Net_Amount", "Net Worth"],
    "waers": ["WAERS", "Währung", "Waehrung", "Currency", "Curr"],
    "lifnr": ["LIFNR", "Lieferant", "Vendor", "Supplier", "Kreditor"],
    "bukrs": ["BUKRS", "Buchungskreis", "Company Code", "Co_Code"],
    "knttp": ["KNTTP", "Kontierungstyp", "Account Assignment Cat", "Acct Asgmt Cat"],
}
ALIAS_LOOKUP = build_alias_map(HEADER_ALIASES)


# --- Built-in classification (fallback after analyst rules) ---
# MATKL groups: many SAP installs use ZFUEL01/02/03 or FUEL01/PETR/DIES etc.
MATKL_TO_TYPE = {
    "fuel01": "diesel", "fuel-d": "diesel", "zfueld": "diesel", "diesel": "diesel",
    "fuel02": "petrol", "fuel-p": "petrol", "zfuelp": "petrol", "petrol": "petrol",
    "fuel03": "lpg", "lpg": "lpg",
    "ng01": "natural_gas_m3", "natgas": "natural_gas_m3",
    "ho01": "heating_oil", "heatoil": "heating_oil",
}
# GL account ranges seen in real SAP fuel-cost mappings (illustrative).
SAKTO_TO_TYPE = {
    "400100": "diesel",
    "400110": "petrol",
    "400120": "lpg",
    "400130": "heating_oil",
    "400140": "natural_gas_m3",
}
# Keyword regex over TXZ01 short text. Order matters; first match wins.
KEYWORD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(diesel|gas[öo]il|gazole|en590)\b", re.I), "diesel"),
    (re.compile(r"\b(petrol|gasoline|benzin|unleaded|premium|95|98)\b", re.I), "petrol"),
    (re.compile(r"\b(lpg|propane|fl[üu]ssiggas|autogas)\b", re.I), "lpg"),
    (re.compile(r"\b(natural\s*gas|erdgas|methane|cng)\b", re.I), "natural_gas_m3"),
    (re.compile(r"\b(heating\s*oil|heiz[öo]l|kerosene)\b", re.I), "heating_oil"),
]


# --- Unit normalization ---
# canonical units per activity type: all fuels -> "L" except natural gas -> "m3"
CANONICAL_UNIT = {
    "diesel": "L", "petrol": "L", "lpg": "L", "heating_oil": "L",
    "natural_gas_m3": "m3",
}
UNIT_TO_LITRES = {
    "l": Decimal("1"), "ltr": Decimal("1"), "liter": Decimal("1"), "litre": Decimal("1"),
    "gal": Decimal("3.78541"), "usg": Decimal("3.78541"),
    "gal_uk": Decimal("4.54609"), "uk_gal": Decimal("4.54609"),
}
UNIT_TO_M3 = {
    "m3": Decimal("1"), "cbm": Decimal("1"), "nm3": Decimal("1"),
}
COUNT_UNITS = {"ea", "pc", "st", "stk"}


def _row_key(row: dict[str, str]) -> dict[str, str]:
    """Map raw row dict (any header variant) to canonical keys."""
    out: dict[str, str] = {}
    for k, v in row.items():
        if k is None:
            continue
        canon = ALIAS_LOOKUP.get(normalize_header(k))
        if canon:
            out[canon] = (v or "").strip()
        else:
            # preserve unmapped columns under their normalized name so they
            # land in raw_json and can be inspected by the analyst.
            out[f"_extra__{normalize_header(k)}"] = (v or "").strip()
    return out


def _classify(canonical: dict[str, str], rules_by_key: dict[tuple[str, str], str]) -> tuple[str | None, str]:
    """Return (activity_type or None, reason). reason describes which rule fired."""
    # 1) tenant rules (most specific to least specific match field)
    for field_name in ("matnr", "matkl", "sakto"):
        value = canonical.get(field_name, "")
        if not value:
            continue
        if (field_name.upper(), value.upper()) in rules_by_key:
            return rules_by_key[(field_name.upper(), value.upper())], f"rule({field_name})"
    # 2) MATKL whitelist
    matkl = canonical.get("matkl", "").lower()
    if matkl in MATKL_TO_TYPE:
        return MATKL_TO_TYPE[matkl], "matkl"
    # 3) SAKTO whitelist
    sakto = canonical.get("sakto", "")
    if sakto in SAKTO_TO_TYPE:
        return SAKTO_TO_TYPE[sakto], "sakto"
    # 4) Keyword regex on TXZ01
    text = canonical.get("txz01", "")
    for pat, atype in KEYWORD_PATTERNS:
        if pat.search(text):
            return atype, "txz01_keyword"
    return None, "no_match"


def _convert_quantity(qty: Decimal, meins: str, activity_type: str | None) -> tuple[Decimal, str, list[dict[str, Any]]]:
    """Convert (qty, meins) to canonical unit per activity_type.
    Returns (qty_canonical, unit_canonical, flags)."""
    flags: list[dict[str, Any]] = []
    if not activity_type:
        unit = (meins or "").strip()
        if not unit:
            flags.append(flag(FlagCode.UNIT_MISSING, "No unit on row"))
        return qty, unit or "?", flags

    target = CANONICAL_UNIT.get(activity_type)
    m = (meins or "").strip().lower()
    if not m:
        flags.append(flag(FlagCode.UNIT_MISSING, "No MEINS on row; assuming canonical unit"))
        return qty, target or "?", flags

    if target == "L":
        if m in UNIT_TO_LITRES:
            mult = UNIT_TO_LITRES[m]
            if mult != 1:
                flags.append(flag(FlagCode.UNIT_INFERRED, f"Converted {meins} to L (x{mult})"))
            return qty * mult, "L", flags
        if m in COUNT_UNITS:
            flags.append(flag(FlagCode.UNIT_UNCONVERTIBLE, f"Unit {meins} is a count, not a volume"))
            return qty, meins, flags
        flags.append(flag(FlagCode.UNIT_UNCONVERTIBLE, f"Unknown unit {meins} for liquid fuel"))
        return qty, meins, flags

    if target == "m3":
        if m in UNIT_TO_M3:
            return qty, "m3", flags
        flags.append(flag(FlagCode.UNIT_UNCONVERTIBLE, f"Unknown unit {meins} for gas"))
        return qty, meins, flags

    return qty, target or meins, flags


def parse(path: str, tenant: Tenant) -> ParseResult:
    text, encoding = read_text(path)
    iter_rows, delimiter = iter_csv_dicts(text)

    result = ParseResult()
    result.summary["encoding"] = encoding
    result.summary["delimiter"] = delimiter
    detected_locale: str | None = None

    # Load tenant's classification rules for SAP, keyed by (field, value)
    rules_by_key: dict[tuple[str, str], str] = {}
    for r in ClassificationRule.objects.filter(
        tenant=tenant, source_type=SOURCE_TYPE, active=True
    ):
        rules_by_key[(r.match_field.upper(), r.match_pattern.upper())] = r.mapped_activity_type

    # Plant lookup for tenant
    plants = {p.werks_code: p for p in PlantLookup.objects.filter(tenant=tenant)}

    line_no = 1  # header
    matched_rows = 0
    unmapped_rows = 0

    for row in iter_rows:
        line_no += 1
        canonical = _row_key(row)
        row_flags: list[dict[str, Any]] = []
        parse_errors: list[dict[str, Any]] = []

        # Quantity
        qty_raw = canonical.get("menge", "")
        qty, loc = parse_decimal(qty_raw)
        if loc and loc != "plain":
            detected_locale = loc
        if qty is None and qty_raw:
            parse_errors.append(flag("invalid_quantity", f"Could not parse MENGE='{qty_raw}'"))

        # Date
        date_raw = canonical.get("budat", "")
        d, date_flags = parse_date(date_raw, prefer_locale=detected_locale)
        row_flags.extend(flag(f, f"BUDAT '{date_raw}' format ambiguous") for f in date_flags)
        if d is None and date_raw:
            parse_errors.append(flag("invalid_date", f"Could not parse BUDAT='{date_raw}'"))

        # Cost
        cost_raw = canonical.get("netwr", "")
        cost, _ = parse_decimal(cost_raw)
        currency = canonical.get("waers", "") or ""

        # Skip rows with no quantity AND no cost (service header rows, etc.)
        if (qty is None or qty == 0) and (cost is None or cost == 0):
            result.raw_rows.append((line_no, canonical, parse_errors + [flag("skipped_empty_row", "No quantity or cost on row", severity="info")]))
            continue

        # Classify
        activity_type, reason = _classify(canonical, rules_by_key)
        if not activity_type:
            row_flags.append(flag(FlagCode.UNMAPPED_ACTIVITY_TYPE,
                                  f"No fuel-type match on MATNR/MATKL/SAKTO/TXZ01 (reason={reason})"))
            unmapped_rows += 1
        else:
            matched_rows += 1

        # Unit conversion
        meins = canonical.get("meins", "")
        if qty is not None:
            qty_canon, unit_canon, uflags = _convert_quantity(qty, meins, activity_type)
        else:
            qty_canon, unit_canon, uflags = Decimal("0"), CANONICAL_UNIT.get(activity_type or "", "?"), []
        row_flags.extend(uflags)

        # Negative quantity (returns / credits)
        if qty_canon is not None and qty_canon < 0:
            row_flags.append(flag(FlagCode.NEGATIVE_QUANTITY,
                                  "Negative quantity - likely a goods return (BWART 102/122)"))

        # Location
        werks = canonical.get("werks", "")
        plant = plants.get(werks)
        if werks and not plant:
            row_flags.append(flag(FlagCode.UNRESOLVED_PLANT, f"No plant lookup for WERKS={werks}"))
        location_country = plant.country if plant else ""
        location_region = plant.grid_region if plant else ""

        # Persist raw row regardless
        result.raw_rows.append((line_no, canonical, parse_errors))

        # If we couldn't parse date or quantity, still create the activity but mark pending/flagged
        if d is None or qty_canon is None:
            # Without date or quantity we can't produce a meaningful activity; skip
            continue

        # Activity draft
        ghg_category = "Stationary Combustion (Fuel)" if activity_type else "Procurement (Unclassified)"
        result.activities.append(ActivityDraft(
            scope=1 if activity_type else 1,  # default fuel = Scope 1; analyst can recategorize
            ghg_category=ghg_category,
            activity_type=activity_type or "unclassified_fuel",
            quantity=qty_canon,
            unit_canonical=unit_canon,
            period_start=d,
            period_end=d,
            location_country=location_country,
            location_region=location_region,
            cost=cost,
            currency=currency,
            details={
                "po": canonical.get("ebeln"),
                "po_item": canonical.get("ebelp"),
                "material": canonical.get("matnr"),
                "description": canonical.get("txz01"),
                "matkl": canonical.get("matkl"),
                "sakto": canonical.get("sakto"),
                "plant_code": werks,
                "plant_name": plant.site_name if plant else "",
                "vendor": canonical.get("lifnr"),
                "company_code": canonical.get("bukrs"),
                "classification_reason": reason,
                "raw_unit": meins,
                "raw_quantity": qty_raw,
            },
            confidence_flags=row_flags,
            source_line_no=line_no,
        ))

    result.summary.update({
        "rows_read": line_no - 1,
        "matched_rows": matched_rows,
        "unmapped_rows": unmapped_rows,
        "detected_locale": detected_locale or "plain",
    })
    return result
