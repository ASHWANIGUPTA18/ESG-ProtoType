"""Emission factors + computed results.

Two principles:
1. EmissionFactor is reference data, versioned by year and region. The same
   activity_type ("diesel") has different factors for different countries and
   different vintages; we store all of them and pick at compute time.
2. EmissionResult is a derived join. It is recomputable from ActivityRecord x
   EmissionFactor. Approving an ActivityRecord freezes the inputs, not the
   kgCO2e output. If a factor is corrected upstream, results rebuild.
"""
from django.db import models


class EmissionFactor(models.Model):
    class Scope(models.IntegerChoices):
        SCOPE_1 = 1, "Scope 1"
        SCOPE_2 = 2, "Scope 2"
        SCOPE_3 = 3, "Scope 3"

    class Method(models.TextChoices):
        LOCATION = "location", "Location-based"
        MARKET = "market", "Market-based"
        DIRECT = "direct", "Direct (Scope 1 or 3 fuel-based)"

    class Source(models.TextChoices):
        DEFRA = "defra", "DEFRA / BEIS (UK)"
        EGRID = "egrid", "EPA eGRID (US)"
        CHSB = "chsb", "Cornell CHSB (hotels)"
        IEA = "iea", "IEA grid factors"
        OTHER = "other", "Other"

    activity_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text="e.g. diesel, petrol, lpg, electricity_grid, air_travel_economy, hotel_night, rental_car_small",
    )
    region_code = models.CharField(
        max_length=16,
        db_index=True,
        help_text="ISO-2 country, or grid subregion (e.g. US-CAMX, GB, DE)",
    )
    year = models.PositiveSmallIntegerField()
    scope = models.PositiveSmallIntegerField(choices=Scope.choices)
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.DIRECT)
    factor_kgco2e = models.DecimalField(
        max_digits=14, decimal_places=6, help_text="kg CO2e per unit"
    )
    unit = models.CharField(
        max_length=24, help_text="canonical unit, e.g. L, kWh, passenger-km, room-night"
    )
    source = models.CharField(max_length=16, choices=Source.choices)
    notes = models.CharField(max_length=300, blank=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["activity_type", "region_code", "year"]),
            models.Index(fields=["scope", "method"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["activity_type", "region_code", "year", "method"],
                name="uniq_factor_per_activity_region_year_method",
            )
        ]

    def __str__(self) -> str:
        return f"{self.activity_type} {self.region_code} {self.year} = {self.factor_kgco2e} {self.unit}"


class EmissionResult(models.Model):
    """Derived. Recomputable from activity + factor."""

    activity_record = models.OneToOneField(
        "normalization.ActivityRecord",
        on_delete=models.CASCADE,
        related_name="emission_result",
    )
    factor = models.ForeignKey(EmissionFactor, on_delete=models.PROTECT, related_name="+")
    kgco2e = models.DecimalField(max_digits=18, decimal_places=4)
    computed_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.kgco2e} kgCO2e (record {self.activity_record_id})"
