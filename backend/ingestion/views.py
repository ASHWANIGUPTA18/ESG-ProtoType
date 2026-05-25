from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from ingestion.models import IngestionBatch
from ingestion.serializers import (
    IngestionBatchSerializer,
    IngestionBatchUploadSerializer,
    RawRowSerializer,
)
from ingestion.services import run_ingestion
from tenants.models import Tenant


class IngestionBatchViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IngestionBatchSerializer

    def get_queryset(self):
        return IngestionBatch.objects.all().order_by("-uploaded_at")

    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        ser = IngestionBatchUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tenant = Tenant.objects.get(slug="demo")
        f = ser.validated_data["file"]
        batch = IngestionBatch(
            tenant=tenant,
            source_type=ser.validated_data["source_type"],
            original_filename=f.name,
        )
        batch.file_blob.save(f.name, f, save=True)
        try:
            run_ingestion(batch)
        except Exception as e:
            return Response(
                {"error": str(e), "batch_id": batch.id},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        batch.refresh_from_db()
        return Response(IngestionBatchSerializer(batch).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="raw-rows")
    def raw_rows(self, request, pk=None):
        batch = self.get_object()
        rows = batch.raw_rows.all()
        page = self.paginate_queryset(rows)
        if page is not None:
            ser = RawRowSerializer(page, many=True)
            return self.get_paginated_response(ser.data)
        return Response(RawRowSerializer(rows, many=True).data)
