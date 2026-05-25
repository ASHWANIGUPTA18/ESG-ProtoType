"""Ingestion: a batch is one uploaded file; raw rows preserve the source verbatim.

Raw rows are immutable once stored. They are the source of truth for re-parsing
if a parser is fixed. ActivityRecord is the canonical derivative — see
normalization/models.py.
"""
from django.db import models


class IngestionBatch(models.Model):
    class SourceType(models.TextChoices):
        SAP_FUEL = "sap_fuel", "SAP fuel & procurement"
        UTILITY_ELECTRICITY = "utility_electricity", "Utility electricity"
        TRAVEL_CONCUR = "travel_concur", "Corporate travel (Concur-shape)"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARSING = "parsing", "Parsing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="batches"
    )
    source_type = models.CharField(max_length=32, choices=SourceType.choices, db_index=True)
    original_filename = models.CharField(max_length=300)
    file_blob = models.FileField(upload_to="uploads/%Y/%m/")
    parser_version = models.CharField(max_length=24, default="v1")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    row_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        "tenants.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    parse_summary = models.JSONField(
        default=dict, blank=True, help_text="parser-emitted summary: detected encoding, locale, schema match score"
    )

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["tenant", "source_type", "-uploaded_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.source_type}] {self.original_filename} @ {self.uploaded_at:%Y-%m-%d}"


class RawRow(models.Model):
    """Verbatim source row as JSON. Immutable. Indexed by (batch, line_no)."""

    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="raw_rows")
    line_no = models.PositiveIntegerField()
    raw_json = models.JSONField()
    parse_errors = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["batch_id", "line_no"]
        indexes = [models.Index(fields=["batch", "line_no"])]
        constraints = [
            models.UniqueConstraint(fields=["batch", "line_no"], name="uniq_rawrow_per_batch_line")
        ]

    def __str__(self) -> str:
        return f"row {self.line_no} of batch {self.batch_id}"
