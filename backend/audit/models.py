"""Audit trail. One row per state-changing action on any auditable model.

We use a generic relation (content_type + object_id) so the same table covers
ActivityRecord, ClassificationRule, IngestionBatch, etc. The before/after JSON
captures the row diff for analyst review.
"""
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        EDIT = "edit", "Edit (analyst field change)"
        APPROVE = "approve", "Approve"
        REJECT = "reject", "Reject"
        FLAG = "flag", "Flag"
        BULK_APPROVE = "bulk_approve", "Bulk approve"
        RULE_APPLY = "rule_apply", "Classification rule applied"
        PARSER_EMIT = "parser_emit", "Parser created record"

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="audit_events"
    )
    actor = models.ForeignKey(
        "tenants.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        help_text="null = system action (parser, scheduled job)",
    )
    action = models.CharField(max_length=24, choices=Action.choices, db_index=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    notes = models.CharField(max_length=300, blank=True)
    ts = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ts"]
        indexes = [
            models.Index(fields=["tenant", "-ts"]),
            models.Index(fields=["content_type", "object_id", "-ts"]),
            models.Index(fields=["action", "-ts"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.content_type.model}#{self.object_id} by {self.actor or 'system'} at {self.ts:%Y-%m-%d %H:%M}"
