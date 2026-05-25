"""Shared parser scaffolding.

Each source has its own parser module that returns a ParseResult. The
orchestrator in ingestion/services.py persists raw rows + activity records and
runs emission compute. Parsers don't touch the database directly.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from math import asin, cos, radians, sin, sqrt
from typing import Any, Iterable

import chardet


# ---------- ParseResult ----------

@dataclass
class ActivityDraft:
    """A normalized record the parser wants to create. The orchestrator turns
    this into an ActivityRecord row + an EmissionResult."""
    scope: int
    ghg_category: str
    activity_type: str
    quantity: Decimal
    unit_canonical: str
    period_start: date
    period_end: date
    location_country: str = ""
    location_region: str = ""
    cost: Decimal | None = None
    currency: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    confidence_flags: list[dict[str, Any]] = field(default_factory=list)
    source_line_no: int | None = None


@dataclass
class ParseResult:
    raw_rows: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = field(default_factory=list)
    activities: list[ActivityDraft] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    batch_errors: list[str] = field(default_factory=list)


# ---------- Encoding + CSV helpers ----------

def detect_encoding(raw: bytes) -> str:
    """Pick a sensible encoding. Tries chardet, falls back to utf-8-sig."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    guess = chardet.detect(raw[:200_000])
    encoding = (guess.get("encoding") or "utf-8").lower()
    if encoding in ("ascii", "iso-8859-1"):
        encoding = "cp1252"  # SAP DE often misreports
    return encoding


def read_text(path_or_bytes) -> tuple[str, str]:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        raw = bytes(path_or_bytes)
    else:
        with open(path_or_bytes, "rb") as f:
            raw = f.read()
    encoding = detect_encoding(raw)
    return raw.decode(encoding, errors="replace"), encoding


def sniff_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        class _D(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        return _D()


def iter_csv_dicts(text: str) -> tuple[Iterable[dict[str, str]], str]:
    """Iterate rows as dicts. Returns (iterator, delimiter)."""
    sample = text[:8192]
    dialect = sniff_dialect(sample)
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return reader, dialect.delimiter


# ---------- Decimal locale ----------

_DECIMAL_DE = re.compile(r"^-?\d{1,3}(\.\d{3})*,\d+$")
_DECIMAL_DE_TRAILING_NEG = re.compile(r"^\d{1,3}(\.\d{3})*,\d+-$")
_DECIMAL_EN = re.compile(r"^-?\d{1,3}(,\d{3})*\.\d+$")


def parse_decimal(value: str | None) -> tuple[Decimal | None, str | None]:
    """Parse a decimal string, detecting locale + trailing-minus credits.

    Returns (value, detected_locale). Locale is one of 'de', 'en', 'plain', None.
    """
    if value is None:
        return None, None
    s = value.strip()
    if not s:
        return None, None
    if _DECIMAL_DE_TRAILING_NEG.match(s):
        s_clean = "-" + s[:-1].replace(".", "").replace(",", ".")
        try:
            return Decimal(s_clean), "de"
        except InvalidOperation:
            return None, None
    if _DECIMAL_DE.match(s):
        s_clean = s.replace(".", "").replace(",", ".")
        try:
            return Decimal(s_clean), "de"
        except InvalidOperation:
            return None, None
    if _DECIMAL_EN.match(s):
        s_clean = s.replace(",", "")
        try:
            return Decimal(s_clean), "en"
        except InvalidOperation:
            return None, None
    # plain integer or float
    if s.endswith("-") and s[:-1].replace(".", "").replace(",", "").isdigit():
        s = "-" + s[:-1]
    try:
        return Decimal(s.replace(",", ".") if "," in s and "." not in s else s), "plain"
    except InvalidOperation:
        return None, None


# ---------- Date parsing ----------

_SAP_INTERNAL = re.compile(r"^\d{8}$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
_DOTS = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_SLASHES = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DASH_DMY = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")


def parse_date(value: str | None, *, prefer_locale: str | None = None) -> tuple[date | None, list[str]]:
    """Parse a date string from any of the SAP/Excel/ISO shapes.

    Returns (date, flags). Flags include 'date_format_ambiguous' when DD/MM vs
    MM/DD couldn't be disambiguated from the value alone.
    """
    if not value:
        return None, []
    s = value.strip()
    if not s:
        return None, []
    flags: list[str] = []

    if _SAP_INTERNAL.match(s):
        try:
            return date(int(s[0:4]), int(s[4:6]), int(s[6:8])), flags
        except ValueError:
            return None, flags

    if _ISO.match(s):
        try:
            return date(int(s[0:4]), int(s[5:7]), int(s[8:10])), flags
        except ValueError:
            return None, flags

    m = _DOTS.match(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d), flags
        except ValueError:
            return None, flags

    m = _SLASHES.match(s) or _DASH_DMY.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # MM/DD when a<=12 and b>12, DD/MM when a>12, otherwise ambiguous.
        if a > 12:
            mo, d = b, a
        elif b > 12:
            mo, d = a, b
        else:
            if prefer_locale == "de":
                mo, d = b, a
            elif prefer_locale == "en":
                mo, d = a, b
            else:
                mo, d = a, b
                flags.append("date_format_ambiguous")
        try:
            return date(y, mo, d), flags
        except ValueError:
            return None, flags

    return None, flags


# ---------- Header aliasing ----------

def normalize_header(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.strip().lower()).strip("_")


def build_alias_map(aliases: dict[str, list[str]]) -> dict[str, str]:
    """canonical -> raw header. Returns reverse lookup: normalized -> canonical."""
    out: dict[str, str] = {}
    for canon, variants in aliases.items():
        for v in variants:
            out[normalize_header(v)] = canon
        out[normalize_header(canon)] = canon
    return out


# ---------- Geo: great-circle distance ----------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlmb / 2) ** 2
    return 2 * R * asin(sqrt(a))


# ---------- Flag helper ----------

def flag(code: str, message: str, *, severity: str = "warn", field: str | None = None) -> dict[str, Any]:
    f = {"code": code, "severity": severity, "message": message}
    if field:
        f["field"] = field
    return f
