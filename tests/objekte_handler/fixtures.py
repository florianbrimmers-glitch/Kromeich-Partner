"""Fixture-Units nach den realen Stolpersteinen aus dem Briefing (08.07.2026)."""
from objekte_handler.models import Unit

# "Hamburgring" liefert 5 Treffer: Nr. 3, 30 und 48 als getrennte Alt-Datensätze,
# Nr. 48 besteht aus zwei Einheiten (5263216 + 5263218).
HAMBURGRING_UNITS = [
    Unit(id=5263216, name="Hamburgring 48", street="Hamburgring", house_number="48",
         city="Mönchengladbach", property_space_value=4200.0, broker_id=387451, broker_name="Marek"),
    Unit(id=5263218, name="Hamburgring 48 Halle 2", street="Hamburgring", house_number="48",
         city="Mönchengladbach", property_space_value=2800.0, broker_id=387451, broker_name="Marek"),
    Unit(id=4000001, name="Hamburgring 3", street="Hamburgring", house_number="3",
         city="Mönchengladbach", property_space_value=1500.0),
    Unit(id=4000002, name="Hamburgring 30", street="Hamburgring", house_number="30",
         city="Mönchengladbach", property_space_value=3100.0),
    Unit(id=4000003, name="Hamburgring 30 Büro", street="Hamburgring", house_number="30",
         city="Mönchengladbach", property_space_value=800.0),
]

# Viersen Aconlog: 2 Einheiten am Industriering 21, 7.666 m² vs. 9.024 m²
VIERSEN_UNITS = [
    Unit(id=5050165, name="Aconlog Viersen kleine Einheit", street="Industriering", house_number="21",
         city="Viersen", property_space_value=7666.0, broker_id=254958, broker_name="Lena Klinnert"),
    Unit(id=5050166, name="Aconlog Viersen große Einheit", street="Industriering", house_number="21",
         city="Viersen", property_space_value=9024.0, broker_id=254958, broker_name="Lena Klinnert"),
]
