from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend

from audit.models import AuditEvent
from audit.serializers import AuditEventSerializer


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditEventSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {
        "action": ["exact", "in"],
        "object_id": ["exact"],
        "content_type__model": ["exact"],
    }

    def get_queryset(self):
        return AuditEvent.objects.select_related("actor", "content_type").all()
