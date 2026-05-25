# MODEL.md — Data Model and Why

## Design principles

1. **Raw is sacred.** Every uploaded row is stored verbatim as JSON on `RawRow`, immutable after ingestion. `ActivityRecord` is the canonical derivative — recomputable from raw data + parser version if the parser is fixed.

2. **Emissions are derived.** `EmissionResult` is a recomputable join of `ActivityRecord × EmissionFactor`. Approving an ActivityRecord freezes the inputs (quantity, unit, period, location), not the kgCO2e output. If a factor is corrected upstream, results rebuild without re-approving.

3. **Multi-tenancy is modeled, not enforced.** Every table that holds client data carries `tenant_id` as a foreign key to `Tenant`, with appropriate indexes. The prototype seeds one tenant ("demo") and does not enforce tenant isolation via middleware or scoped managers. The seam is explicit: adding a `TenantScopedManager` and request middleware would complete it. This was a deliberate choice for a 4-day prototype — schema points > runtime enforcement when there's one tenant.

4. **Audit trail is complete.** Every state-changing operation (parser create, analyst edit, approve, reject, bulk approve, rule apply) writes an `AuditEvent` with before/after JSON snapshots, actor, timestamp, and a generic relation to the target row. An auditor can reconstruct the full lifecycle of any activity record.

---

## Entity-Relationship Diagram (text)

```
Tenant ─┬─ User (role: analyst | admin)
        │
        ├─ IngestionBatch
        │    ├─ source_type (sap_fuel | utility_electricity | travel_concur)
        │    ├─ file_blob, parser_version, status, parse_summary
        │    └──< RawRow (line_no, raw_json, parse_errors)
        │              │
        │              └──< ActivityRecord (can be many per raw row)
        │                     ├─ scope (1 | 2 | 3), ghg_category, activity_type
        │                     ├─ quantity, unit_canonical
        │                     ├─ period_start, period_end
        │                     ├─ location_country, location_region
        │                     ├─ cost, currency
        │                     ├─ details (JSONField — source-specific flex)
        │                     ├─ status (pending | flagged | edited | approved | rejected)
        │                     ├─ confidence_flags (JSONField list)
        │                     └── EmissionResult (1:1, derived)
        │                           ├─ factor_id → EmissionFactor
        │                           └─ kgco2e, computed_at
        │
        ├─ ClassificationRule
        │    ├─ source_type, match_field, match_pattern
        │    └─ mapped_activity_type
        │
        ├─ PlantLookup (SAP WERKS → site metadata)
        │
        └─ AuditEvent (generic relation to any model above)

EmissionFactor (standalone reference — not tenant-scoped)
  ├─ activity_type, region_code, year, scope, method
  ├─ factor_kgco2e, unit, source (DEFRA | eGRID | CHSB | IEA)
  └─ unique on (activity_type, region, year, method)

Airport (standalone reference)
  └─ IATA code, lat, lon, country
```

---

## Key model decisions

### ActivityRecord: why a single table, not polymorphic

Fuel, electricity, and travel rows all share the same lifecycle (ingest → review → approve → audit → report). Splitting into `FuelRecord`, `ElectricityRecord`, `TravelRecord` would triple the approval logic, triple the audit surface, and force the review dashboard into a union query. A single `ActivityRecord` with `scope` + `ghg_category` + `activity_type` + a `details` JSONField for source-specific metadata keeps the schema flat and the review workflow uniform. Django's JSONField is query-supportable on Postgres but we primarily filter on the indexed top-level fields (status, scope, period, activity_type), not into the JSON.

### RawRow → ActivityRecord: ForeignKey, not OneToOne

The initial design used a OneToOneField. This broke immediately when the utility parser pro-rated a single billing-period row into multiple calendar-month ActivityRecords. Real ESG ingestion creates many-from-one regularly (period splits, multi-fuel line items, scope 1+3 splits of the same purchase). ForeignKey with `related_name="activity_records"` allows this cleanly.

### EmissionFactor: region + year + method as the lookup key

A single factor table serves Scope 1 (DEFRA fuel factors by country), Scope 2 (eGRID subregion grid factors, location-based), and Scope 3 (DEFRA air travel by haul class, CHSB hotel by country). The lookup path is:

1. Exact match on `(activity_type, region_code, year, method)`
2. Same region+method, closest year
3. Country fallback (e.g., US-CAMX → US → XX)
4. Global fallback (XX)

This avoids separate factor tables per scope while preserving the precision hierarchy. The unique constraint on `(activity_type, region_code, year, method)` prevents duplicates.

### Confidence flags: JSON list, not a separate table

Each flag is `{code, severity, message, field?}`. A separate `Flag` table would cost N writes per row (a row can have 3-4 flags easily) and would need a join on every list query. A JSON list on ActivityRecord is denormalized but keeps the review query to one table. Tradeoff: you can't query "show me all rows with flag X" via a simple `WHERE`; we iterate in Python. This is acceptable at prototype scale. A production system might add a GIN index on the JSON array.

### Multi-tenancy: shared DB with tenant_id

Schema-per-tenant (via `django-tenants`) provides stronger isolation but adds: a separate migration chain per tenant, cross-tenant reporting complexity, and a library dependency that constrains Django version upgrades. At prototype scale with one tenant, the cost far exceeds the benefit. The `tenant_id` FK + composite indexes (e.g., `(tenant_id, status)`, `(tenant_id, scope, period_start)`) are in place; a future `TenantScopedManager` is ~5 lines of code.

### Audit: generic relation via ContentType

`AuditEvent` uses Django's `ContentType` framework so the same table can track changes to `ActivityRecord`, `ClassificationRule`, `IngestionBatch`, etc. The alternative — a dedicated audit table per model — scatters the audit trail and makes "show me everything that happened today" harder. The `before` and `after` JSON fields capture the diff; we don't store the full row snapshot to keep storage bounded.

---

## Scope 1/2/3 categorization

- **Scope 1**: SAP fuel purchases where the activity_type maps to a combustion fuel (diesel, petrol, LPG, natural gas, heating oil). Classified by the fallback chain: ClassificationRule → MATKL → SAKTO → TXZ01 keyword.
- **Scope 2**: Utility electricity. Always `activity_type="electricity_grid"`, method="location". Market-based is modeled (the EmissionFactor table supports `method="market"`) but not implemented in the UI. See TRADEOFFS.md.
- **Scope 3 Category 6**: Business travel (air, hotel, ground transport). Air distance computed from IATA pair via haversine + 9% GCD uplift. Hotel nights computed from check-in/check-out dates. Car rental km estimated from rental days × 150km/day.

---

## Unit normalization

Every ActivityRecord stores `quantity` in a canonical unit for its activity type:

| Activity domain | Canonical unit | Conversion examples |
|---|---|---|
| Liquid fuels | L (liters) | GAL × 3.785, USG × 3.785, UK_GAL × 4.546 |
| Natural gas | m3 | - |
| Electricity | kWh | MWh rejected with flag (not silently converted) |
| Air travel | km (passenger-km after GCD uplift) | IATA pair → haversine → × 1.09 |
| Hotel | room-night | check-out − check-in, min 1 |
| Car rental | km | days × 150 (estimated, flagged) |

KG (mass) for fuel is flagged as `unit_unconvertible` because density depends on the specific fuel and temperature — the analyst must fill this in.

---

## Source-of-truth tracking

Every ActivityRecord links back to:
- `source_batch` → the IngestionBatch that produced it (file, parser version, upload timestamp)
- `source_row` → the specific RawRow (line number, verbatim JSON, parser errors)
- `last_edited_by`, `last_edited_at` → who touched it last
- `approved_by`, `approved_at` → who locked it for audit
- AuditEvent chain → full history of every mutation

This means an auditor can answer: "This 12,500L diesel record — which file did it come from, who uploaded it, what did the raw data look like, who approved it, and when?"
