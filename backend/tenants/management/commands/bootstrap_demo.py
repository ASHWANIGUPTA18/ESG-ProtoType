"""Bootstrap one demo tenant with two users + a few SAP plant lookups.

Calls seed_factors and seed_airports as well, so a fresh database is one
command away from a working demo.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from tenants.models import Tenant, User
from reference.models import PlantLookup


PLANTS = [
    # WERKS, site name, country, grid region
    ("1010", "Manchester Distribution Centre", "GB", "GB"),
    ("1020", "Birmingham Plant", "GB", "GB"),
    ("2010", "Hamburg Hauptwerk", "DE", "DE"),
    ("2020", "Munich Logistik", "DE", "DE"),
    ("3010", "Chicago Plant", "US", "US-RFCW"),
    ("3020", "Atlanta Distribution", "US", "US-SRMV"),
    # Note: WERKS 4010 is deliberately NOT seeded so the parser surfaces
    # an "unresolved_plant" flag on rows that reference it - showing the
    # real-world reality of clients shipping the lookup table separately.
]


class Command(BaseCommand):
    help = "Create demo tenant + users, seed plant lookups, factors, airports."

    def handle(self, *args, **options):
        with transaction.atomic():
            tenant, t_created = Tenant.objects.update_or_create(
                slug="demo",
                defaults=dict(name="Demo Industries Ltd."),
            )

            admin, _ = User.objects.update_or_create(
                username="admin",
                defaults=dict(
                    email="admin@demo.example",
                    first_name="Ada",
                    last_name="Admin",
                    is_staff=True,
                    is_superuser=True,
                    tenant=tenant,
                    role=User.Role.ADMIN,
                ),
            )
            if not admin.has_usable_password():
                admin.set_password("admin12345")
                admin.save()

            analyst, _ = User.objects.update_or_create(
                username="analyst",
                defaults=dict(
                    email="analyst@demo.example",
                    first_name="Ana",
                    last_name="Lyst",
                    tenant=tenant,
                    role=User.Role.ANALYST,
                ),
            )
            if not analyst.has_usable_password():
                analyst.set_password("analyst12345")
                analyst.save()

            for werks, name, country, grid_region in PLANTS:
                PlantLookup.objects.update_or_create(
                    tenant=tenant,
                    werks_code=werks,
                    defaults=dict(site_name=name, country=country, grid_region=grid_region),
                )

        call_command("seed_factors")
        call_command("seed_airports")

        self.stdout.write(self.style.SUCCESS(
            f"Demo bootstrapped. tenant={tenant.slug} "
            f"admin=admin/admin12345 analyst=analyst/analyst12345"
        ))
