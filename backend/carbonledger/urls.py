from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from rest_framework.routers import DefaultRouter

from audit.views import AuditEventViewSet
from ingestion.views import IngestionBatchViewSet
from normalization.views import ActivityRecordViewSet, ClassificationRuleViewSet

router = DefaultRouter()
router.register("batches", IngestionBatchViewSet, basename="batch")
router.register("records", ActivityRecordViewSet, basename="record")
router.register("rules", ClassificationRuleViewSet, basename="rule")
router.register("audit", AuditEventViewSet, basename="audit")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/auth/", include("rest_framework.urls")),
]

if not settings.DEBUG:
    urlpatterns += [
        re_path(r"^(?!api/|admin/|static/|media/).*$", TemplateView.as_view(template_name="index.html")),
    ]
