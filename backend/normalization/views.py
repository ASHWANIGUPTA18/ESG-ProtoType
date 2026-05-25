import csv
import io

from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from audit.models import AuditEvent
from emissions.compute import upsert_result
from normalization.models import ActivityRecord, ClassificationRule
from normalization.serializers import (
    ActivityRecordSerializer,
    ActivityRecordEditSerializer,
    BulkApproveSerializer,
    ClassificationRuleSerializer,
)


def _audit(record, actor, action_code, before, after, notes=""):
    AuditEvent.objects.create(
        tenant=record.tenant,
        actor=actor if actor and actor.is_authenticated else None,
        action=action_code,
        content_type=ContentType.objects.get_for_model(ActivityRecord),
        object_id=record.id,
        before=before,
        after=after,
        notes=notes,
    )


class ActivityRecordViewSet(viewsets.ModelViewSet):
    serializer_class = ActivityRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "status": ["exact", "in"],
        "scope": ["exact"],
        "activity_type": ["exact"],
        "source_batch_id": ["exact"],
        "source_batch__source_type": ["exact"],
        "period_start": ["gte", "lte"],
        "period_end": ["gte", "lte"],
    }
    search_fields = ["activity_type", "ghg_category", "notes", "details"]
    ordering_fields = ["created_at", "period_start", "quantity", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = ActivityRecord.objects.select_related(
            "source_batch", "source_row",
        ).all()
        try:
            qs = qs.select_related("emission_result")
        except Exception:
            pass
        return qs

    def get_serializer_class(self):
        if self.action in ("partial_update", "update"):
            return ActivityRecordEditSerializer
        return ActivityRecordSerializer

    def perform_update(self, serializer):
        record = self.get_object()
        before = {f: str(getattr(record, f)) for f in serializer.validated_data}
        record = serializer.save(
            status=ActivityRecord.Status.EDITED,
            last_edited_at=timezone.now(),
        )
        after = {f: str(getattr(record, f)) for f in serializer.validated_data}
        _audit(record, self.request.user, AuditEvent.Action.EDIT, before, after)
        upsert_result(record)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        record = self.get_object()
        if record.status == ActivityRecord.Status.APPROVED:
            return Response({"detail": "Already approved"}, status=status.HTTP_400_BAD_REQUEST)
        before = {"status": record.status}
        record.status = ActivityRecord.Status.APPROVED
        record.approved_at = timezone.now()
        record.save(update_fields=["status", "approved_at"])
        _audit(record, request.user, AuditEvent.Action.APPROVE, before, {"status": "approved"})
        return Response(ActivityRecordSerializer(record).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        record = self.get_object()
        before = {"status": record.status}
        record.status = ActivityRecord.Status.REJECTED
        record.save(update_fields=["status"])
        _audit(record, request.user, AuditEvent.Action.REJECT, before, {"status": "rejected"}, notes=request.data.get("notes", ""))
        return Response(ActivityRecordSerializer(record).data)

    @action(detail=False, methods=["post"], url_path="bulk-approve")
    def bulk_approve(self, request):
        ser = BulkApproveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = ser.validated_data["record_ids"]
        records = ActivityRecord.objects.filter(id__in=ids).exclude(status=ActivityRecord.Status.APPROVED)
        count = 0
        for record in records:
            before = {"status": record.status}
            record.status = ActivityRecord.Status.APPROVED
            record.approved_at = timezone.now()
            record.save(update_fields=["status", "approved_at"])
            _audit(record, request.user, AuditEvent.Action.BULK_APPROVE, before, {"status": "approved"})
            count += 1
        return Response({"approved": count})

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        qs = self.get_queryset()
        from django.db.models import Count, Sum, Q
        from emissions.models import EmissionResult

        by_status = dict(qs.values_list("status").annotate(c=Count("id")).values_list("status", "c"))
        by_scope = dict(qs.values_list("scope").annotate(c=Count("id")).values_list("scope", "c"))
        total_kgco2e = EmissionResult.objects.aggregate(total=Sum("kgco2e"))["total"] or 0

        scope_emissions = {}
        for row in (
            EmissionResult.objects
            .values("activity_record__scope")
            .annotate(total=Sum("kgco2e"))
        ):
            scope_emissions[row["activity_record__scope"]] = str(row["total"] or 0)

        source_emissions = {}
        for row in (
            EmissionResult.objects
            .values("activity_record__source_batch__source_type")
            .annotate(total=Sum("kgco2e"), count=Count("id"))
        ):
            src = row["activity_record__source_batch__source_type"]
            source_emissions[src] = {"kgco2e": str(row["total"] or 0), "count": row["count"]}

        flagged_codes = {}
        for r in qs.filter(status__in=["flagged", "pending"]):
            for f in r.confidence_flags:
                code = f.get("code", "unknown")
                flagged_codes[code] = flagged_codes.get(code, 0) + 1

        return Response({
            "total_records": qs.count(),
            "by_status": by_status,
            "by_scope": by_scope,
            "total_kgco2e": str(total_kgco2e),
            "scope_emissions": scope_emissions,
            "source_emissions": source_emissions,
            "flag_breakdown": flagged_codes,
        })


    @action(detail=False, methods=["get"], url_path="export")
    def export_csv(self, request):
        qs = self.filter_queryset(self.get_queryset())
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "scope", "ghg_category", "activity_type",
            "quantity", "unit", "period_start", "period_end",
            "location_country", "location_region",
            "cost", "currency", "kgco2e",
            "status", "source_type", "source_file",
            "flags", "approved_at",
        ])
        for r in qs.iterator():
            kg = ""
            try:
                kg = str(r.emission_result.kgco2e)
            except Exception:
                pass
            flag_codes = ", ".join(f.get("code", "") for f in (r.confidence_flags or []))
            writer.writerow([
                r.id, r.scope, r.ghg_category, r.activity_type,
                r.quantity, r.unit_canonical, r.period_start, r.period_end,
                r.location_country, r.location_region,
                r.cost or "", r.currency, kg,
                r.status, r.source_batch.source_type, r.source_batch.original_filename,
                flag_codes, r.approved_at or "",
            ])
        response = HttpResponse(buf.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="activity_records_export.csv"'
        return response


class ClassificationRuleViewSet(viewsets.ModelViewSet):
    serializer_class = ClassificationRuleSerializer

    def get_queryset(self):
        return ClassificationRule.objects.all()

    def perform_create(self, serializer):
        from tenants.models import Tenant
        tenant = Tenant.objects.get(slug="demo")
        serializer.save(
            tenant=tenant,
            created_by=self.request.user if self.request.user.is_authenticated else None,
        )
