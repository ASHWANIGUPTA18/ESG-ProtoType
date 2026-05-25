from rest_framework import serializers

from audit.models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True, default="system")
    target_type = serializers.CharField(source="content_type.model", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id", "action", "actor_name", "target_type", "object_id",
            "before", "after", "notes", "ts",
        ]
        read_only_fields = fields
