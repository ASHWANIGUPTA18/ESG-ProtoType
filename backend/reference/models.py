"""Reference data: airports for travel-distance lookup, SAP plant lookups."""
from django.db import models


class Airport(models.Model):
    """OurAirports subset, IATA-keyed. Used to compute great-circle distance for
    air travel rows that don't carry distance (Concur typical)."""

    iata = models.CharField(max_length=3, primary_key=True)
    icao = models.CharField(max_length=4, blank=True)
    name = models.CharField(max_length=200)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=2, db_index=True, help_text="ISO-3166-1 alpha-2")
    lat = models.FloatField()
    lon = models.FloatField()

    class Meta:
        ordering = ["iata"]

    def __str__(self) -> str:
        return f"{self.iata} - {self.name}"


class PlantLookup(models.Model):
    """SAP WERKS code -> physical site. Clients ship this as a side CSV
    weeks after the procurement extract; we model it explicitly so rows show
    'unresolved plant' when the lookup is missing."""

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="plants")
    werks_code = models.CharField(max_length=8)
    site_name = models.CharField(max_length=200)
    country = models.CharField(max_length=2, help_text="ISO-3166-1 alpha-2")
    grid_region = models.CharField(
        max_length=32, blank=True, help_text="eGRID subregion / DEFRA region for Scope 2 join"
    )

    class Meta:
        unique_together = [("tenant", "werks_code")]
        indexes = [models.Index(fields=["tenant", "werks_code"])]

    def __str__(self) -> str:
        return f"{self.werks_code} - {self.site_name}"
