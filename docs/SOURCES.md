# SOURCES.md — Real-world source research

## 1. SAP Fuel & Procurement

### What we researched

SAP's ecosystem offers multiple export mechanisms: IDoc (hierarchical EDI segments via middleware like SAP PI/PO), flat-file extracts (SE16N, SQVI/SQ01 queries, scheduled SM37 jobs writing to AL11), OData services (`/sap/opu/odata/sap/MM_PUR_PO_MAINTAIN_SRV`, `API_PURCHASEORDER_PROCESS_SRV` on S/4HANA), and BAPI/RFC calls (via `pyrfc` Python SDK). We also examined the relevant SAP modules (MM for procurement, FI for invoice/GL) and their core tables: EKKO/EKPO (purchase order header+line), MKPF/MSEG (material document header+line), MAKT (material text), T001W (plants), LFA1 (vendors), BKPF/BSEG (FI documents).

### Why we chose flat-file CSV

Mid-market clients (ECC 6.0, not S/4HANA Cloud) do not expose OData to third-party vendors — the security review alone takes months. Their BI analyst or FICO consultant already runs SE16N extracts or SQ01 custom queries monthly. The output lands on an AL11 filesystem share or gets emailed as an Excel attachment. This is the realistic shape.

### What our sample data looks like

The sample CSV (`samples/sap/sap_procurement_2024_q4.csv`) is a semicolon-delimited file with German column headers (Belegnummer, Materialgruppe, Buchungsdatum, etc.), simulating an extract from a DE-locale SAP system. Key design choices:

- **12 rows** spanning 3 company codes (UK, DE, US plants) to exercise cross-plant, cross-currency, cross-unit scenarios.
- **German decimal locale**: `18750,00` (decimal comma, period for thousands separator).
- **SAP-internal dates**: `20241015` (YYYYMMDD as a string, not a date).
- **Trailing-minus credits**: `500,00-` representing a goods return (BWART 102/122 in real SAP).
- **WERKS=4010**: deliberately NOT in the plant lookup table, to trigger the `unresolved_plant` flag and demonstrate the real-world problem of clients shipping the T001W lookup weeks after the extract.
- **Fuel-by-GL-only row**: `MAT-MISC` / "Misc Consumables" / SAKTO=400100. The material code is generic but the GL account betrays it as diesel. This tests the SAKTO fallback in the classification chain.
- **KG unit row**: 1800 KG of "Betriebsstoff allgemein" (general operating materials). KG can't be converted to L without density, so the parser flags `unit_unconvertible`.
- **Service PO row**: MENGE=0, EA unit, cost only. Represents a fuel pump maintenance charge that has no quantity — tests the skip-empty-row logic and the `unmapped_activity_type` flag.
- **USG unit (US gallons)**: 15000 USG diesel, converted to 56,781 L by the parser with `unit_inferred` flag.

### What would break in a real deployment

- **Custom Z-fields**: many SAP clients add ZZ_FUEL_TYPE, ZZ_EMISSION_CAT, or similar custom fields. Our parser would silently drop them into `_extra__` columns. Not a crash, but lost classification data.
- **Service entry sheets (ML81N)**: some companies procure fuel via service POs (KNTTP=K) that have cost but no MENGE/MEINS. Our parser creates a record with qty=0 and flags it; a real system would need a separate spend-based EEIO flow.
- **Material master lookup (MARA/MAKT/MARM)**: we don't receive or join against the material master. A real deployment would want MARM (unit conversion table) and MAKT (material descriptions in multiple languages) as separate lookup uploads.
- **Multiple UoMs per material (MARM)**: SAP materials can be ordered in KG but stored in L. The conversion factor lives in MARM table which is not exported. We assume MEINS is the delivery unit.
- **BAPI vs SE16N field names**: BAPI returns structured types with slightly different field names than SE16N dump columns. Our alias map would need extension.

---

## 2. Utility Electricity

### What we researched

Facilities teams obtain electricity data via: utility portal CSV/Excel exports (ConEd "My Account", PG&E SmartMeter, Duke Energy XLSX), PDF bills (universal but brittle to parse), Green Button ESPI XML (standardized `IntervalReading` with `timePeriod` and `value`, adopted unevenly in US), direct utility APIs (rare, per-utility OAuth onboarding takes months), and third-party aggregators (Urjanet, Arcadia — enterprise pricing, normalized JSON across thousands of utilities). UK suppliers provide half-hourly data with MPAN identifiers and 48 period columns (P1–P48).

### Why we chose portal CSV upload

This is what a facilities manager actually has in hand within a week. Green Button requires per-utility registration. PDF parsing requires OCR templates per utility format. Aggregators are a paid SaaS product. A monthly billing-period CSV from the portal is the lowest-friction realistic starting point. The ConEd export shape (Account Number, Service Address, Meter Number, Rate Class, Read Date From/To, kWh, Demand kW, Total Charges) is representative of US commercial utility exports generally.

### What our sample data looks like

The sample CSV (`samples/utility/coned_billing_2024.csv`) has 10 rows across 4 accounts, 6 meters, 2 billing cycles:

- **Multi-meter accounts**: ACCT-001 has two meters (MTR-A001, MTR-A002) at the same address. Tests that the dashboard doesn't double-count at the account level.
- **Non-aligned billing periods**: Oct 15–Nov 14 (31 days) and Nov 14–Dec 15 (32 days). Neither aligns with calendar months. The parser pro-rates kWh into Oct/Nov and Nov/Dec respectively, creating 2 ActivityRecords per raw row, flagged `period_straddles_months`.
- **Estimated read**: ACCT-002, MTR-B002 has ReadType=E, flagged `estimated_read`. The next period would typically have an actual read with a true-up correction.
- **Multiple US regions**: addresses in NYC (10118 → US-NYCW), Atlanta (30303 → US-SRMV), San Francisco (94105 → US-CAMX), and Boston (02109 → US-NEWE). Each maps to a different eGRID subregion with a different grid emission factor, ranging from 0.227 kgCO2e/kWh (New England) to 0.430 (SERC Mississippi).
- **On-peak/off-peak split**: some rows include peak/shoulder breakdown for tariff analysis, stored in details JSON.

### What would break in a real deployment

- **ZIP-to-eGRID mapping**: our simplified prefix mapping covers ~6 metros. A real system needs EPA's Power Profiler ZIP-to-subregion lookup table (~40k rows).
- **MWh/therms/ccf in the same export**: some utility portals mix electric and gas billing in one CSV. A row with "therms" instead of "kWh" would be flagged but not correctly handled.
- **Demand charges (kW) vs energy (kWh)**: we capture demand but don't use it for emissions. Some commercial tariffs have complex demand ratchets that affect cost allocation.
- **Rate changes mid-period**: a rate increase mid-billing-period splits one bill into two tariff blocks. Our parser treats it as one period.
- **International utilities**: different column names, different formats, different units (EU uses kWh universally, but some Asian utilities report in kVA). Our parser assumes US ConEd shape.

---

## 3. Corporate Travel (Concur)

### What we researched

SAP Concur is the dominant corporate travel platform. Relevant APIs: Travel v4 `/travel/v4/bookings` and Itinerary v1.1 `/api/travel/trip/v1.1` for bookings, Expense v4 `/expensereports/v4/users/{userID}/reports` for out-of-pocket spend that bypasses the booking flow. Auth: OAuth2 with company-level JWT tokens (`company_request_token` → `company_access_token`). Navan has a partner REST API (`/api/v1/bookings`, `/api/v1/travel-emissions`) that includes inline CO2 estimates via Thrust Carbon, but requires a partner agreement. Egencia/Amex GBT provides SFTP data feeds (daily CSV/XML).

### Why we chose Concur Standard Reporting CSV

Same reasoning as SAP/utility: clients don't grant live API credentials during pilot. The "Standard Reporting" tab in Concur exports CSV with one row per segment, field names mirroring the API response. Building to this shape means a live API swap is mechanical (parse JSON instead of CSV, same output). Every travel platform offers some form of CSV/Excel export from its admin reporting interface.

### What our sample data looks like

The sample CSV (`samples/travel/concur_trips_2024_q4.csv`) has 20 rows spanning 8 trips, 5 travelers, 3 segment types:

- **Air segments with IATA codes**: LHR→JFK (5,555km, business class J), SFO→NRT (8,271km, economy Y), FRA→LHR (635km, short-haul economy), DEL→BOM (1,140km, domestic economy), MUC→DXB (4,560km, first class F), GRU→EZE (1,693km, economy). Tests haul classification (domestic/short/long) and cabin multipliers (Y=1.0, J=2.9, F=4.0).
- **Hotel segments**: computed nights from check-in/check-out. Countries include US (16.2 kgCO2e/night), GB (10.4), JP (no seeded factor — would use XX fallback), AE/Dubai (39.0 — testing high-factor region), AR (XX fallback).
- **Car rental**: SIPP code CCAR (Compact, maps to "medium" via first-character lookup). 4-day rental → 600km estimated. Flagged `distance_inferred`.
- **Cancelled trip**: TRP-005 (LHR→CDG + hotel in Paris) with BookingStatus=Cancelled. Parser skips, counts in summary.
- **Multi-leg trip**: TRP-001 has outbound (LHR→JFK) and return (JFK→LHR), sharing the same TripId. Each is a separate ActivityRecord but they're groupable by trip_id in the details JSON.

### What would break in a real deployment

- **Exchange/reissue tickets**: when a traveler changes a flight, Concur creates a new record with a new ticket number. Naive ingestion double-counts. Need to detect reissues via original ticket reference fields not in Standard Reporting export.
- **Expense-only travel**: out-of-pocket Uber, hotel paid on personal card then expensed. Only in Expense API, not Travel. Must union and dedupe against Travel by traveler+date.
- **Airport code ambiguities**: NYC metro = JFK, LGA, EWR. Some systems report "NYC" metro code instead of specific airport. Our parser would flag `unknown_airport` for "NYC" since it's not a valid IATA code.
- **Multi-city itineraries**: LHR→FRA→MUC booked as one PNR shows as 2 segments. Each segment gets its own distance calculation, which is correct for emissions but the UI shows them as separate rows. Grouping by TripId for display purposes would improve UX.
- **Personal vs business split**: some travelers have personal legs mixed in. The `IsPersonal` field exists in Expense API but may not be in Standard Reporting.
- **Codeshare flights**: a BA-marketed flight operated by AA. The carrier in the export might not match the actual aircraft type, which affects per-passenger-km factors for newer aircraft models.

---

## Emission factor sources

| Source | Used for | Reference | Notes |
|---|---|---|---|
| DEFRA 2024 | Scope 1 fuels, air travel, rail, rental cars | UK BEIS/Defra annual conversion factors | Values are approximate, rounded for prototype |
| EPA eGRID 2022 | Scope 2 US grid factors (by subregion) | eGRID summary tables | Subregion factors, not plant-level |
| IEA 2023 | Scope 2 non-US grid factors | IEA country-level CO2/kWh | Approximations for DE, FR, IN |
| Cornell CHSB 2023 | Scope 3 hotel room-nights | Hotel Carbon Measurement Initiative | kgCO2e per room-night by country |

All values are illustrative. A production system would ingest the full source spreadsheets (DEFRA publishes ~3,000 rows across 15 tabs) and match by specific fuel/vehicle/accommodation subcategory rather than broad averages.
