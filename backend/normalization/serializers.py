from rest_framework import serializers

from emissions.models import EmissionResult
from normalization.models import ActivityRecord, ClassificationRule


class EmissionResultInlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionResult
        fields = ["kgco2e", "computed_at"]
        read_only_fields = fields


class ActivityRecordSerializer(serializers.ModelSerializer):
    emission_result = EmissionResultInlineSerializer(read_only=True)
    source_type = serializers.CharField(source="source_batch.source_type", read_only=True)
    source_filename = serializers.CharField(source="source_batch.original_filename", read_only=True)
    source_row_line_no = serializers.IntegerField(source="source_row.line_no", read_only=True, default=None)
    source_row_raw = serializers.JSONField(source="source_row.raw_json", read_only=True, default=None)

    class Meta:
        model = ActivityRecord
        fields = [
            "id", "scope", "ghg_category", "activity_type",
            "quantity", "unit_canonical",
            "period_start", "period_end",
            "location_country", "location_region",
            "cost", "currency",
            "details", "status", "confidence_flags", "notes",
            "created_at", "last_edited_at", "approved_at",
            "emission_result",
            "source_batch_id", "source_type", "source_filename",
            "source_row_line_no", "source_row_raw",
        ]
        read_only_fields = [
            "id", "scope", "ghg_category", "created_at",
            "emission_result", "source_batch_id",
            "source_type", "source_filename",
            "source_row_line_no", "source_row_raw",
        ]


class ActivityRecordEditSerializer(serializers.ModelSerializer):
    """For PATCH — only the fields an analyst should be able to change."""

    class Meta:
        model = ActivityRecord
        fields = [
            "activity_type", "quantity", "unit_canonical",
            "period_start", "period_end",
            "location_country", "location_region",
            "notes",
        ]


class BulkApproveSerializer(serializers.Serializer):
    record_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, max_length=500)


class ClassificationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassificationRule
        fields = [
            "id", "source_type", "match_field", "match_pattern",
            "mapped_activity_type", "notes", "active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
