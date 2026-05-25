# TRADEOFFS.md — What we deliberately did not build

## 1. Market-based Scope 2 emissions

**What it is:** The GHG Protocol requires dual reporting for Scope 2 — location-based (grid average) and market-based (contractual instruments: RECs, GOs, supplier-specific factors). Market-based tracks whether the company *purchased* renewable energy, not just whether it consumed electricity in a clean-grid region.

**Why we skipped it:** Market-based Scope 2 requires:
- Ingestion of Renewable Energy Certificate (REC) / Guarantee of Origin (GO) data from registries (M-RETS, APX, Powernext) — each with different schemas and access models.
- Supplier disclosure letters with per-supplier emission factors.
- A hierarchy: contractual instruments → supplier-specific → residual mix → grid fallback.
- Matching certificates to billing periods and meters by serial number, vintage, and MWh quantity.

This is a separate engineering project, not a side feature. Building it poorly would be worse than not building it — incorrect market-based numbers create audit risk.

**What we did instead:** The `EmissionFactor` schema already supports `method="market"`. Adding market-based factors and a certificate table later doesn't require schema changes — the seam is designed in.

---

## 2. Live API integrations (SAP OData, Concur OAuth, utility APIs)

**What it is:** Direct polling of data from source systems instead of file upload.

**Why we skipped it:** Research showed that mid-market clients do not grant live API access during onboarding or pilot phases. The security review process alone (OAuth credential issuance, IP allowlisting, data classification) takes weeks. File upload is what actually happens in practice, and it's not a temporary hack — it's the realistic first integration mode.

**What we did instead:** Parsers are designed around field names from the live APIs (Concur Itinerary v1.1 JSON, SAP OData MM_PUR_PO_MAINTAIN_SRV). The CSV shape mirrors the API shape. Replacing the file parser with an API poll is a mechanical swap — parse the JSON response instead of CSV rows, same ActivityDraft output, same persistence. This is documented and testable.

---

## 3. Background processing (Celery / task queue)

**What it is:** Asynchronous file parsing via a message broker (Redis/RabbitMQ) and worker process.

**Why we skipped it:** Our largest sample file (20 travel rows) parses in ~200ms. Even a real enterprise file (5,000 rows) would take ~5 seconds synchronously. Django's request timeout (30s on Gunicorn) won't fire. Adding Celery would require: a broker service (Redis), a worker process, a result backend, task status polling in the UI, error handling for failed workers, and deployment of 3 services instead of 1.

**What we did instead:** Synchronous parse with immediate response. The upload endpoint returns the full parse summary in the HTTP response body. The UI shows the result immediately.

**When this breaks:** A file with 50,000+ rows or a parser that calls external APIs (geocoding, airport lookup from a remote service). At that point, Celery + a progress websocket is the right investment.

---

## 4. PDF utility bill ingestion

**What it is:** OCR/template parsing of scanned or digital PDF utility bills.

**Why we skipped it:** PDF bill parsing is brittle, template-specific engineering. ConEd bills look nothing like PG&E bills look nothing like British Gas bills. A single rate change by the utility can break the template. Real ESG products use dedicated OCR services (AWS Textract, Google Document AI) or aggregators (Urjanet, Arcadia) rather than building in-house parsers. Building a toy version would demonstrate nothing and mislead about capability.

**What we did instead:** CSV upload of the billing data that a facilities manager copies out of the portal. This is what they actually have.

---

## 5. Multi-user authentication and roles

**What it is:** Login, registration, JWT/session management, role-based access control, team invites.

**Why we skipped it:** The schema models it (User has role: analyst|admin, every table has tenant_id), but the runtime doesn't enforce it. No login screen, no token flow. The DRF endpoints use `AllowAny` permissions.

**Why this was the right cut:** Authentication is infrastructure, not domain logic. It adds no insight into whether we understand ESG data quality, emission factor lookup, or analyst review workflows. A production deployment would use django-allauth or a hosted auth provider (Auth0, Clerk) — building a custom login form is wasted effort.

---

## 6. Interval / half-hourly meter data

**What it is:** 15-minute or 30-minute granularity energy consumption data (as opposed to monthly billing totals). UK suppliers provide HH data with 48 period columns per day; US smart meters export Green Button ESPI XML at 15-min intervals.

**Why we skipped it:** Interval data is used for load profiling and demand response, not for Scope 2 emissions reporting (which uses total kWh per period). Ingesting it would require: a separate table schema (time-series, not flat records), aggregation to billing periods, handling of missing intervals, and storage for ~35,000 readings per meter per year. This is a v2 concern for energy management, not a v1 concern for carbon accounting.

---

## What we'd build next (if this were week 2)

1. **Market-based Scope 2** — REC/GO upload + supplier factor management
2. **Celery** — for files > 10K rows and for scheduled re-parsing when factors change
3. **Login + role enforcement** — via django-allauth + react-router auth guards
4. **Dashboard charts** — time series of emissions by scope, trend lines, YoY comparison
5. **Export to audit pack** — PDF/Excel report with approved records, factors used, audit trail
6. **CI/CD** — GitHub Actions for test + lint + deploy on push
