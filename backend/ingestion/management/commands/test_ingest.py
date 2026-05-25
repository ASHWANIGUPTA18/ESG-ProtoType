"""Quick harness: ingest a file and print the result summary."""
import shutil
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from ingestion.models import IngestionBatch
from ingestion.services import run_ingestion
from normalization.models import ActivityRecord
from tenants.models import Tenant


class Command(BaseCommand):
    help = "Ingest a file for testing. Usage: test_ingest <path> <source_type>"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("source_type", choices=["sap_fuel", "utility_electricity", "travel_concur"])

    def handle(self, *args, **options):
        tenant = Tenant.objects.get(slug="demo")
        src = Path(options["path"])

        batch = IngestionBatch(
            tenant=tenant,
            source_type=options["source_type"],
            original_filename=src.name,
        )
        with open(src, "rb") as f:
            batch.file_blob.save(src.name, File(f), save=True)

        summary = run_ingestion(batch)
        self.stdout.write(self.style.SUCCESS(f"Batch #{batch.id} {batch.status}"))
        for k, v in summary.items():
            self.stdout.write(f"  {k}: {v}")

        records = ActivityRecord.objects.filter(source_batch=batch)
        self.stdout.write(f"\n  Records: {records.count()}")
        for r in records[:10]:
            result_val = getattr(r, 'emission_result', None)
            kg = result_val.kgco2e if result_val else "?"
            flags = [f["code"] for f in r.confidence_flags]
            self.stdout.write(f"    [{r.status:8s}] {r.activity_type:25s} {r.quantity:>12} {r.unit_canonical:6s} => {kg:>12} kgCO2e  flags={flags}")
