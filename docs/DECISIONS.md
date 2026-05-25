# DECISIONS.md — Every ambiguity resolved

## Ingestion mode: CSV file upload for all three sources

**Decision:** All three sources (SAP, utility, travel) are ingested via CSV file upload, not live API integration.

**Why:** Research showed this is the realistic ingestion mode for a mid-market enterprise client:
- SAP: clients on ECC 6.0 won't open OData to a third-party vendor (security review blocks it). Their BI analyst already runs SE16N/SQVI extracts and drops CSV/XLSX monthly.
- Utility: facilities managers pull billing CSVs from ConEd/PG&E portals. Green Button (ESPI XML) has uneven adoption. PDF OCR is a separate engineering problem. Real multi-site buyers use aggregators like Urjanet, but those are paid SaaS products.
- Concur: clients almost never grant live API access in a pilot engagement. The "Standard Reporting" tab exports CSV with the same field names as the API JSON — building to this shape means a live integration is a mechanical swap later.

**What I'd ask the PM:** "Is the client actually willing to grant API credentials, or will we get file drops for the first quarter while they evaluate?"

---

## SAP export shape: flat-file SE16N extract, not IDoc or OData

**Decision:** Parser expects a flat CSV with EKKO+EKPO+MKPF+MSEG semantics (PO line-level or material document line-level), not hierarchical IDoc segments or OData JSON.

**Why:** A flat file is what a sustainability lead actually has. IDocs require middleware (SAP PI/PO, Boomi). OData requires S/4HANA or explicit service exposure from Basis. A BI analyst can produce a flat extract in 20 minutes from SE16N or SQ01.

**What I'd ask the PM:** "Which SAP modules does this client actually use? Do they have MM Procurement, or do they use PM (Plant Maintenance) for fleet fuel tracking? That changes which tables are in the extract."

---

## SAP header aliasing: German and English

**Decision:** The parser detects both German (Belegnummer, Menge, Mengeneinheit, Buchungsdatum) and English (PO Number, Quantity, UoM, Posting Date) column headers via an alias map.

**Why:** SAP exports use whichever language the user's logon is configured for. A German SAP system with a German user exports German headers. The same system with an English user exports English headers. Some exports mix both. Not handling this means the parser breaks on first real deployment.

---

## Decimal locale detection: DE comma vs EN period

**Decision:** Parser auto-detects `1.234,56` (German) vs `1,234.56` (English) and trailing-minus credits (`1234,56-` = -1234.56).

**Why:** SAP exports in DE locale use decimal comma. When the same data is opened in Excel on an EN-locale machine and re-saved, some cells get re-formatted. Real SAP exports have mixed locales in the same file.

---

## Fuel classification fallback chain

**Decision:** ClassificationRule (tenant DB) → MATKL whitelist → SAKTO whitelist → TXZ01 keyword regex → unmapped.

**Why:** Real SAP data has rows where:
1. MATNR is generic ("Misc Consumables") but SAKTO=400100 = diesel cost center
2. MATKL is a customer-invented grouping (ZFUEL01) not in any standard
3. TXZ01 (short text) says "Diesel EN590" but MATKL is "MISC"
The chain tries the most structured field first, falls through to keyword matching, and gives up cleanly with a flag so the analyst can create a ClassificationRule.

**What I'd ask the PM:** "Can we get the client's MATKL-to-fuel mapping table? Otherwise we'll spend the first week classifying by hand."

---

## Utility billing periods: pro-rata calendar month allocation

**Decision:** When a billing period straddles a month boundary (e.g., Oct 15–Nov 14), the parser splits the kWh pro-rata by calendar days into each month.

**Why:** ESG reporting is by calendar month/quarter/year. A 31-day billing period starting Oct 15 has 17 days in October and 14 days in November. Without pro-rating, the analyst has to do this manually in Excel — which is what happens at most companies today. Automating it is a clear value-add.

**What I'd ask the PM:** "Does the client report monthly or quarterly? If quarterly, we might not need month-level granularity and can skip the split."

---

## Utility read type: estimated vs actual flagging

**Decision:** The parser flags estimated reads (ReadType=E) with `estimated_read`. It does NOT reject or correct them.

**Why:** Estimated reads are common and expected. Utilities issue them when they can't access the meter. The next actual read (A) often includes a true-up (sometimes negative kWh). The analyst should see the flag and know to look for the correction in the next billing period.

---

## Air travel distance: computed from IATA airport codes

**Decision:** The parser computes great-circle distance from airport lat/lon (haversine formula) and adds 9% uplift for non-direct routing, per DEFRA guidance.

**Why:** Concur exports typically don't include distance. They give origin/destination IATA codes (LHR, JFK). The GHG Protocol Scope 3 Category 6 methodology requires passenger-km. DEFRA's published guidance recommends 8–9% uplift over great-circle distance to account for routing, stacking, and taxiing. We seed 48 airports covering most global business travel routes.

**What I'd ask the PM:** "Does the client use Navan? Navan includes CO2 estimates inline via Thrust Carbon. If so, we could use their number instead of computing our own."

---

## Hotel emissions: nights from check-in/check-out, not a "Nights" column

**Decision:** The parser computes nights as `(check_out_date - check_in_date).days`, ignoring any "Nights" column if present.

**Why:** "Nights" columns in travel platform exports are unreliable. Early check-outs, late check-ins, and booking modifications create discrepancies. Dates are more trustworthy.

---

## Rental car emissions: estimated km from days

**Decision:** No odometer data exists in Concur. We estimate km = days × 150km/day and flag `distance_inferred`.

**Why:** Concur doesn't capture mileage. Expense reports don't either. The 150km/day assumption is a reasonable business-travel estimate (DEFRA methodology suggests spend-based EEIO as an alternative, which we don't implement). The flag ensures the analyst knows this is an estimate.

---

## Approval granularity: per-row with bulk approve

**Decision:** Each ActivityRecord has its own status (pending/flagged/edited/approved/rejected). The UI supports bulk-approve via checkbox selection.

**Why:** Real audit workflows require per-record sign-off. A "batch approve" (approve all 50 rows from one upload at once) is too coarse — what if 3 of those rows have unit issues? Per-row approval lets the analyst fix 3 and approve 47. Bulk approve is the convenience layer for the "everything looks fine" case.

---

## Status machine: pending → flagged → edited → approved | rejected

**Decision:** Parser sets records to `pending` if no severe flags, `flagged` if any concerning flag (unmapped type, unit issue, unresolved plant, date ambiguity). Analyst can edit (→ edited), then approve or reject.

**Why:** The analyst's job is to look at flagged rows first. The status ordering puts the most urgent work on top.

---

## Scope 2: location-based only

**Decision:** We compute location-based Scope 2 emissions using eGRID/DEFRA/IEA grid factors. Market-based Scope 2 is modeled in the schema (EmissionFactor supports `method="market"`) but not implemented in ingestion or UI.

**Why:** See TRADEOFFS.md for the full rationale.

---

## Default tenant: "demo" hardcoded

**Decision:** The prototype seeds one tenant ("Demo Industries Ltd.") and all API operations use it. No login required.

**Why:** Multi-tenant auth adds ~2 days of work (user registration, login UI, JWT or session flow, tenant-scoped queries). The schema already has `tenant_id` everywhere; skipping the auth flow is the right scope cut for a 4-day prototype. See TRADEOFFS.md.

---

## Tech stack choices

- **Django 5.2 LTS + DRF**: most productive stack for data-heavy APIs with an admin interface. LTS means no surprise deprecations.
- **SQLite (dev) / Postgres (prod)**: SQLite for zero-config local development. Postgres on Render for JSONB and concurrent writes.
- **React + Vite + Tailwind**: fast iteration, no build complexity. TanStack Query for data fetching with cache invalidation.
- **No Celery**: file parsing is synchronous and fast enough at prototype scale (<1 second per file). Documented as a known scaling limitation.
