from rest_framework import serializers

from ingestion.models import IngestionBatch, RawRow


class IngestionBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionBatch
        fields = [
            "id", "source_type", "original_filename", "parser_version",
            "status", "row_count", "error_count", "parse_summary",
            "uploaded_at", "completed_at",
        ]
        read_only_fields = fields


class IngestionBatchUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    source_type = serializers.ChoiceField(choices=IngestionBatch.SourceType.choices)


class RawRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRow
        fields = ["id", "line_no", "raw_json", "parse_errors"]
        read_only_fields = fields
