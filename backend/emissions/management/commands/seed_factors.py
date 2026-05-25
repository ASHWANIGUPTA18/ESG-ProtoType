"""Seed emission factors.

Values are illustrative, sourced from publicly available DEFRA 2024, eGRID 2022,
and CHSB 2023 tables. Numbers used here are *approximate* and rounded for the
prototype; a production system would ingest the source spreadsheets directly.
We document this honestly in SOURCES.md.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from emissions.models import EmissionFactor as EF


# (activity_type, region, year, scope, method, factor, unit, source, notes)
FACTORS: list[tuple] = [
    # Scope 1 fuels - DEFRA UK 2024, kgCO2e per litre/m3
    ("diesel", "GB", 2024, 1, "direct", "2.5121", "L", "defra", "Diesel (avg biofuel blend)"),
    ("petrol", "GB", 2024, 1, "direct", "2.1675", "L", "defra", "Petrol (avg biofuel blend)"),
    ("lpg", "GB", 2024, 1, "direct", "1.5570", "L", "defra", "LPG"),
    ("heating_oil", "GB", 2024, 1, "direct", "2.5180", "L", "defra", "Kerosene/heating oil"),
    ("natural_gas_m3", "GB", 2024, 1, "direct", "2.0383", "m3", "defra", "Natural gas, gross CV"),
    # Scope 1 fuels - generic (used when country unknown)
    ("diesel", "XX", 2024, 1, "direct", "2.6800", "L", "other", "Global avg fallback (no country lookup)"),
    ("petrol", "XX", 2024, 1, "direct", "2.3100", "L", "other", "Global avg fallback"),
    ("lpg", "XX", 2024, 1, "direct", "1.5570", "L", "other", "Global avg fallback"),
    ("heating_oil", "XX", 2024, 1, "direct", "2.5180", "L", "other", "Global avg fallback"),
    ("natural_gas_m3", "XX", 2024, 1, "direct", "2.0383", "m3", "other", "Global avg fallback"),
    # Scope 2 electricity - location-based grid factors (kgCO2e/kWh)
    ("electricity_grid", "US-CAMX", 2022, 2, "location", "0.2497", "kWh", "egrid", "eGRID 2022, California subregion"),
    ("electricity_grid", "US-RFCW", 2022, 2, "location", "0.3957", "kWh", "egrid", "eGRID 2022, RFC West"),
    ("electricity_grid", "US-NEWE", 2022, 2, "location", "0.2273", "kWh", "egrid", "eGRID 2022, New England"),
    ("electricity_grid", "US-SRMV", 2022, 2, "location", "0.4300", "kWh", "egrid", "eGRID 2022, SERC Mississippi"),
    ("electricity_grid", "GB", 2024, 2, "location", "0.2072", "kWh", "defra", "DEFRA 2024 UK grid"),
    ("electricity_grid", "DE", 2023, 2, "location", "0.3801", "kWh", "iea", "IEA 2023 Germany"),
    ("electricity_grid", "FR", 2023, 2, "location", "0.0560", "kWh", "iea", "IEA 2023 France (nuclear-heavy)"),
    ("electricity_grid", "IN", 2023, 2, "location", "0.7080", "kWh", "iea", "IEA 2023 India"),
    ("electricity_grid", "XX", 2023, 2, "location", "0.4750", "kWh", "iea", "Global avg fallback"),
    # Scope 3 Cat 6 - Air travel (DEFRA passenger-km, economy class baseline)
    ("air_travel_economy_domestic", "XX", 2024, 3, "direct", "0.2464", "passenger-km", "defra", "Domestic flight (<500km)"),
    ("air_travel_economy_short", "XX", 2024, 3, "direct", "0.1546", "passenger-km", "defra", "Short-haul <3700km"),
    ("air_travel_economy_long", "XX", 2024, 3, "direct", "0.1957", "passenger-km", "defra", "Long-haul >3700km"),
    # Cabin multipliers are applied in code, not stored as separate factors. See compute_emissions.py.
    # Scope 3 Cat 6 - Hotels (CHSB kgCO2e per room-night)
    ("hotel_night", "GB", 2023, 3, "direct", "10.40", "room-night", "chsb", "CHSB 2023 UK"),
    ("hotel_night", "US", 2023, 3, "direct", "16.20", "room-night", "chsb", "CHSB 2023 US (avg)"),
    ("hotel_night", "DE", 2023, 3, "direct", "11.30", "room-night", "chsb", "CHSB 2023 Germany"),
    ("hotel_night", "FR", 2023, 3, "direct", "7.80", "room-night", "chsb", "CHSB 2023 France"),
    ("hotel_night", "IN", 2023, 3, "direct", "26.00", "room-night", "chsb", "CHSB 2023 India"),
    ("hotel_night", "AE", 2023, 3, "direct", "39.00", "room-night", "chsb", "CHSB 2023 UAE"),
    ("hotel_night", "XX", 2023, 3, "direct", "15.00", "room-night", "chsb", "Global avg fallback"),
    # Scope 3 Cat 6 - Rental cars (DEFRA kgCO2e per km)
    ("rental_car_small", "XX", 2024, 3, "direct", "0.1422", "km", "defra", "Small car, avg"),
    ("rental_car_medium", "XX", 2024, 3, "direct", "0.1760", "km", "defra", "Medium car, avg"),
    ("rental_car_large", "XX", 2024, 3, "direct", "0.2229", "km", "defra", "Large car, avg"),
    # Rail passenger (Cat 6)
    ("rail_national", "GB", 2024, 3, "direct", "0.0354", "passenger-km", "defra", "National rail UK"),
    ("rail_national", "XX", 2024, 3, "direct", "0.0410", "passenger-km", "other", "Generic rail fallback"),
]


class Command(BaseCommand):
    help = "Seed emission factors. Idempotent."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        with transaction.atomic():
            for row in FACTORS:
                (activity_type, region, year, scope, method, factor, unit, source, notes) = row
                _, was_created = EF.objects.update_or_create(
                    activity_type=activity_type,
                    region_code=region,
                    year=year,
                    method=method,
                    defaults=dict(
                        scope=scope,
                        factor_kgco2e=Decimal(factor),
                        unit=unit,
                        source=source,
                        notes=notes,
                    ),
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
        self.stdout.write(self.style.SUCCESS(f"Factors: {created} created, {updated} updated."))
