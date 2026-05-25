"""Orchestrator: file -> IngestionBatch -> parser -> persist -> compute emissions.

This is the only place that writes ActivityRecord/RawRow rows. Parsers are
pure: they read text, return ParseResult. Persistence + audit live here.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from importlib import import_module
from typing import Any

from django.db import transaction
from django.utils import timezone

from audit.models import AuditEvent
from emissions.compute import upsert_result
from ingestion.models import IngestionBatch, RawRow
from normalization.models import ActivityRecord, FlagCode
from tenants.models import Tenant, User


PARSER_MODULES = {
    IngestionBatch.SourceType.SAP_FUEL: "ingestion.parsers.sap_fuel",
    IngestionBatch.SourceType.UTILITY_ELECTRICITY: "ingestion.parsers.utility_electricity",
    IngestionBatch.SourceType.TRAVEL_CONCUR: "ingestion.parsers.travel_concur",
}


def _initial_status(flags: list[dict[str, Any]]) -> str:
    """Status after parse: flagged if any severe flag, else pending."""
    if any(f.get("severity") in ("error",) for f in flags):
        return ActivityRecord.Status.FLAGGED
    if any(f.get("code") in {
        FlagCode.UNMAPPED_ACTIVITY_TYPE,
        FlagCode.UNIT_UNCONVERTIBLE,
        FlagCode.UNRESOLVED_PLANT,
        FlagCode.PERIOD_MISSING_END,
        FlagCode.UNKNOWN_AIRPORT,
        FlagCode.DATE_FORMAT_AMBIGUOUS,
    } for f in flags):
        return ActivityRecord.Status.FLAGGED
    return ActivityRecord.Status.PENDING


@transaction.atomic
def run_ingestion(batch: IngestionBatch) -> dict:
    """Run the parser for `batch` and persist results. Returns a summary dict."""
    module_path = PARSER_MODULES.get(batch.source_type)
    if not module_path:
        batch.status = IngestionBatch.Status.FAILED
        batch.parse_summary = {"error": f"No parser for source_type {batch.source_type}"}
        batch.save(update_fields=["status", "parse_summary"])
        return batch.parse_summary

    parser_mod = import_module(module_path)
    batch.status = IngestionBatch.Status.PARSING
    batch.parser_version = getattr(parser_mod, "PARSER_VERSION", "v1")
    batch.save(update_fields=["status", "parser_version"])

    file_path = batch.file_blob.path
    try:
        result = parser_mod.parse(file_path, batch.tenant)
    except Exception as e:
        batch.status = IngestionBatch.Status.FAILED
        batch.parse_summary = {"error": f"{type(e).__name__}: {e}"}
        batch.save(update_fields=["status", "parse_summary"])
        raise

    # Persist raw rows
    raw_objs: list[RawRow] = []
    line_to_raw: dict[int, RawRow] = {}
    for (line_no, raw_json, parse_errors) in result.raw_rows:
        rr = RawRow(batch=batch, line_no=line_no, raw_json=raw_json, parse_errors=parse_errors)
        raw_objs.append(rr)
    RawRow.objects.bulk_create(raw_objs, batch_size=500)
    for rr in RawRow.objects.filter(batch=batch):
        line_to_raw[rr.line_no] = rr

    # Persist activities
    activities_created = 0
    factor_not_found = 0
    for draft in result.activities:
        raw_row = line_to_raw.get(draft.source_line_no) if draft.source_line_no else None
        status = _initial_status(draft.confidence_flags)
        ar = ActivityRecord.objects.create(
            tenant=batch.tenant,
            source_batch=batch,
            source_row=raw_row,
            scope=draft.scope,
            ghg_category=draft.ghg_category,
            activity_type=draft.activity_type,
            quantity=draft.quantity,
            unit_canonical=draft.unit_canonical,
            period_start=draft.period_start,
            period_end=draft.period_end,
            location_country=draft.location_country,
            location_region=draft.location_region,
            cost=draft.cost,
            currency=draft.currency,
            details=draft.details,
            status=status,
            confidence_flags=draft.confidence_flags,
        )
        activities_created += 1

        # Compute emissions; flag if no factor matched
        result_obj = upsert_result(ar)
        if result_obj is None:
            ar.confidence_flags = ar.confidence_flags + [
                {"code": FlagCode.FACTOR_NOT_FOUND, "severity": "warn",
                 "message": f"No emission factor for activity_type={ar.activity_type} region={ar.location_region or ar.location_country}"}
            ]
            ar.status = ActivityRecord.Status.FLAGGED
            ar.save(update_fields=["confidence_flags", "status"])
            factor_not_found += 1

        # Audit event for the parser-generated record
        AuditEvent.objects.create(
            tenant=batch.tenant,
            actor=None,
            action=AuditEvent.Action.PARSER_EMIT,
            content_type_id=_content_type_id(ActivityRecord),
            object_id=ar.id,
            before={},
            after={"status": ar.status, "scope": ar.scope, "activity_type": ar.activity_type},
            notes=f"parser={batch.source_type} v{batch.parser_version}",
        )

    batch.row_count = len(result.raw_rows)
    batch.error_count = sum(1 for (_l, _r, errs) in result.raw_rows if errs)
    batch.status = IngestionBatch.Status.COMPLETED
    batch.parse_summary = result.summary | {
        "activities_created": activities_created,
        "factor_not_found": factor_not_found,
    }
    batch.completed_at = timezone.now()
    batch.save(update_fields=["row_count", "error_count", "status", "parse_summary", "completed_at"])

    return batch.parse_summary


_ct_cache: dict[type, int] = {}


def _content_type_id(model: type) -> int:
    if model not in _ct_cache:
        from django.contrib.contenttypes.models import ContentType
        _ct_cache[model] = ContentType.objects.get_for_model(model).id
    return _ct_cache[model]
