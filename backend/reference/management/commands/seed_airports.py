"""Seed a small airport reference set.

A real deployment would load OurAirports' full ~80k-row CSV. For the prototype
we load ~40 of the most-trafficked codes globally so the sample-data travel
parser can compute distances for every realistic route.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from reference.models import Airport


# iata, icao, name, city, country, lat, lon
AIRPORTS = [
    # North America
    ("JFK", "KJFK", "John F Kennedy International", "New York", "US", 40.6413, -73.7781),
    ("LGA", "KLGA", "LaGuardia", "New York", "US", 40.7769, -73.8740),
    ("EWR", "KEWR", "Newark Liberty International", "Newark", "US", 40.6895, -74.1745),
    ("LAX", "KLAX", "Los Angeles International", "Los Angeles", "US", 33.9416, -118.4085),
    ("SFO", "KSFO", "San Francisco International", "San Francisco", "US", 37.6213, -122.3790),
    ("ORD", "KORD", "Chicago OHare", "Chicago", "US", 41.9742, -87.9073),
    ("ATL", "KATL", "Hartsfield-Jackson Atlanta", "Atlanta", "US", 33.6407, -84.4277),
    ("DFW", "KDFW", "Dallas/Fort Worth", "Dallas", "US", 32.8998, -97.0403),
    ("SEA", "KSEA", "Seattle-Tacoma", "Seattle", "US", 47.4502, -122.3088),
    ("BOS", "KBOS", "Boston Logan", "Boston", "US", 42.3656, -71.0096),
    ("IAD", "KIAD", "Washington Dulles", "Washington", "US", 38.9531, -77.4565),
    ("YYZ", "CYYZ", "Toronto Pearson", "Toronto", "CA", 43.6777, -79.6248),
    ("YVR", "CYVR", "Vancouver International", "Vancouver", "CA", 49.1939, -123.1844),
    ("MEX", "MMMX", "Mexico City International", "Mexico City", "MX", 19.4361, -99.0719),
    # Europe
    ("LHR", "EGLL", "London Heathrow", "London", "GB", 51.4700, -0.4543),
    ("LGW", "EGKK", "London Gatwick", "London", "GB", 51.1537, -0.1821),
    ("LCY", "EGLC", "London City", "London", "GB", 51.5053, 0.0553),
    ("CDG", "LFPG", "Paris Charles de Gaulle", "Paris", "FR", 49.0097, 2.5479),
    ("ORY", "LFPO", "Paris Orly", "Paris", "FR", 48.7233, 2.3795),
    ("AMS", "EHAM", "Amsterdam Schiphol", "Amsterdam", "NL", 52.3105, 4.7683),
    ("FRA", "EDDF", "Frankfurt am Main", "Frankfurt", "DE", 50.0379, 8.5622),
    ("MUC", "EDDM", "Munich", "Munich", "DE", 48.3538, 11.7861),
    ("BER", "EDDB", "Berlin Brandenburg", "Berlin", "DE", 52.3667, 13.5033),
    ("MAD", "LEMD", "Madrid Barajas", "Madrid", "ES", 40.4983, -3.5676),
    ("BCN", "LEBL", "Barcelona El Prat", "Barcelona", "ES", 41.2974, 2.0833),
    ("FCO", "LIRF", "Rome Fiumicino", "Rome", "IT", 41.8003, 12.2389),
    ("MXP", "LIMC", "Milan Malpensa", "Milan", "IT", 45.6306, 8.7281),
    ("ZRH", "LSZH", "Zurich", "Zurich", "CH", 47.4582, 8.5555),
    ("CPH", "EKCH", "Copenhagen", "Copenhagen", "DK", 55.6180, 12.6508),
    ("DUB", "EIDW", "Dublin", "Dublin", "IE", 53.4213, -6.2701),
    # Asia-Pacific
    ("NRT", "RJAA", "Tokyo Narita", "Tokyo", "JP", 35.7720, 140.3929),
    ("HND", "RJTT", "Tokyo Haneda", "Tokyo", "JP", 35.5494, 139.7798),
    ("ICN", "RKSI", "Seoul Incheon", "Seoul", "KR", 37.4602, 126.4407),
    ("HKG", "VHHH", "Hong Kong", "Hong Kong", "HK", 22.3080, 113.9185),
    ("SIN", "WSSS", "Singapore Changi", "Singapore", "SG", 1.3644, 103.9915),
    ("BKK", "VTBS", "Bangkok Suvarnabhumi", "Bangkok", "TH", 13.6900, 100.7501),
    ("KUL", "WMKK", "Kuala Lumpur International", "Kuala Lumpur", "MY", 2.7456, 101.7099),
    ("PVG", "ZSPD", "Shanghai Pudong", "Shanghai", "CN", 31.1443, 121.8083),
    ("PEK", "ZBAA", "Beijing Capital", "Beijing", "CN", 40.0801, 116.5846),
    ("SYD", "YSSY", "Sydney Kingsford Smith", "Sydney", "AU", -33.9461, 151.1772),
    ("DEL", "VIDP", "Delhi Indira Gandhi", "Delhi", "IN", 28.5562, 77.1000),
    ("BOM", "VABB", "Mumbai", "Mumbai", "IN", 19.0896, 72.8656),
    ("BLR", "VOBL", "Bengaluru Kempegowda", "Bengaluru", "IN", 13.1986, 77.7066),
    # Middle East / Africa
    ("DXB", "OMDB", "Dubai International", "Dubai", "AE", 25.2532, 55.3657),
    ("DOH", "OTHH", "Doha Hamad", "Doha", "QA", 25.2731, 51.6080),
    ("JNB", "FAOR", "Johannesburg OR Tambo", "Johannesburg", "ZA", -26.1392, 28.2460),
    # Latin America
    ("GRU", "SBGR", "Sao Paulo Guarulhos", "Sao Paulo", "BR", -23.4356, -46.4731),
    ("EZE", "SAEZ", "Buenos Aires Ezeiza", "Buenos Aires", "AR", -34.8222, -58.5358),
]


class Command(BaseCommand):
    help = "Seed airport reference data. Idempotent."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        with transaction.atomic():
            for (iata, icao, name, city, country, lat, lon) in AIRPORTS:
                _, was_created = Airport.objects.update_or_create(
                    iata=iata,
                    defaults=dict(icao=icao, name=name, city=city, country=country, lat=lat, lon=lon),
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
        self.stdout.write(self.style.SUCCESS(f"Airports: {created} created, {updated} updated."))
