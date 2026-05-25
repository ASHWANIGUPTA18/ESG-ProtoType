"""Normalized activity records + analyst-authored classification rules.

ActivityRecord is the canonical, auditable representation of one emissions-
generating event. It is derived from a RawRow but lives independently so that
analyst edits and approvals attach to it without mutating raw data.

ConfidenceFlag is a JSON shape, not a separate table: each flag is
{code, severity, message, field?}. Parsers emit flags during normalization;
re-parses can regenerate them. The analyst's job is to clear or accept them.
"""
from django.db import models


# Vocabulary kept in code, not the DB, so parsers and the UI share one list.
class FlagCode:
    UNIT_INFERRED = "unit_inferred"
    UNIT_MISSING = "unit_missing"
    UNIT_UNCONVERTIBLE = "unit_unconvertible"
    NEGATIVE_QUANTITY = "negative_quantity"
    PERIOD_STRADDLES_MONTHS = "period_straddles_months"
    PERIOD_MISSING_END = "period_missing_end"
    ESTIMATED_READ = "estimated_read"
    DATE_FORMAT_AMBIGUOUS = "date_format_ambiguous"
    UNMAPPED_ACTIVITY_TYPE = "unmapped_activity_type"
    UNRESOLVED_PLANT = "unresolved_plant"
    CANCELLED_BOOKING = "cancelled_booking"
    MULTI_LEG_PNR = "multi_leg_pnr"
    DISTANCE_INFERRED = "distance_inferred"
    UNKNOWN_AIRPORT = "unknown_airport"
    MATERIALLY_LARGE = "materially_large"
    FACTOR_NOT_FOUND = "factor_not_found"


class ActivityRecord(models.Model):
    class Scope(models.IntegerChoices):
        SCOPE_1 = 1, "Scope 1"
        SCOPE_2 = 2, "Scope 2"
        SCOPE_3 = 3, "Scope 3"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        FLAGGED = "flagged", "Flagged (needs attention)"
        EDITED = "edited", "Edited by analyst"
        APPROVED = "approved", "Approved (locked for audit)"
        REJECTED = "rejected", "Rejected"

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="activity_records"
    )
    source_batch = models.ForeignKey(
        "ingestion.IngestionBatch",
        on_delete=models.PROTECT,
        related_name="activity_records",
    )
    source_row = models.ForeignKey(
        "ingestion.RawRow",
        on_delete=models.PROTECT,
        related_name="activity_records",
        null=True,
        blank=True,
        help_text="Multiple records per raw row possible (period-split utility, multi-segment travel).",
    )

    scope = models.PositiveSmallIntegerField(choices=Scope.choices)
    ghg_category = models.CharField(
        max_length=64,
        db_index=True,
        help_text="e.g. Stationary Combustion, Purchased Electricity, Business Travel - Air",
    )
    activity_type = models.CharField(max_length=64, db_index=True)

    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_canonical = models.CharField(max_length=24, help_text="L, kWh, km, room-night, ...")

    period_start = models.DateField()
    period_end = models.DateField()

    location_country = models.CharField(max_length=2, blank=True, help_text="ISO-3166-1 alpha-2")
    location_region = models.CharField(
        max_length=32, blank=True, help_text="eGRID subregion / DEFRA region / state"
    )

    cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)

    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="source-specific attributes: plant_code, cabin_class, supplier, meter_id, ...",
    )

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    confidence_flags = models.JSONField(
        default=list,
        blank=True,
        help_text="list of {code, severity, message, field?}",
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_edited_by = models.ForeignKey(
        "tenants.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edited_records",
    )
    last_edited_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "tenants.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_records",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "scope", "period_start"]),
            models.Index(fields=["source_batch", "status"]),
            models.Index(fields=["activity_type"]),
        ]

    def __str__(self) -> str:
        return f"[{self.status}] {self.activity_type} {self.quantity} {self.unit_canonical}"


class ClassificationRule(models.Model):
    """Analyst-authored mapping. When the parser sees `match_field == match_pattern`
    for a given source_type, it assigns mapped_activity_type. Rules persist;
    parsers consult them before the built-in fallback chain.
    """

    class SourceType(models.TextChoices):
        SAP_FUEL = "sap_fuel", "SAP fuel & procurement"
        UTILITY_ELECTRICITY = "utility_electricity", "Utility electricity"
        TRAVEL_CONCUR = "travel_concur", "Corporate travel"

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="classification_rules"
    )
    source_type = models.CharField(max_length=32, choices=SourceType.choices, db_index=True)
    match_field = models.CharField(
        max_length=64, help_text="raw column name, e.g. MATNR, MATKL, SAKTO, RATE_CLASS, EXPENSE_TYPE"
    )
    match_pattern = models.CharField(max_length=200, help_text="exact match (case-insensitive)")
    mapped_activity_type = models.CharField(max_length=64)
    notes = models.CharField(max_length=300, blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "tenants.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tenant", "source_type", "match_field"]
        indexes = [
            models.Index(fields=["tenant", "source_type", "match_field", "active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "source_type", "match_field", "match_pattern"],
                name="uniq_rule_per_tenant_source_field_pattern",
            )
        ]

    def __str__(self) -> str:
        return f"{self.source_type}: {self.match_field}={self.match_pattern} -> {self.mapped_activity_type}"
