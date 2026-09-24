"""Fixture-Units für die Newsletter-Handler-Tests (eigener Propstack-Bestand)."""
from newsletter_handler.models import Unit

# Fiktiver eigener Bestand, der zufällig zu einer Radar-Vermietung passen könnte.
CITYLINK_UNITS = [
    Unit(id=6100001, name="CityLink Dortmund", title="CityLink Dortmund", street="Wieckesweg",
         house_number="12", city="Dortmund", property_space_value=6000.0,
         broker_id=254958, broker_name="Lena Klinnert"),
]

# Zwei Einheiten an derselben Adresse (Größen-Hinweis nötig für Eindeutigkeit).
INDUSTRIERING_UNITS = [
    Unit(id=6200001, name="Industriering klein", street="Industriering", house_number="21",
         city="Viersen", property_space_value=7666.0, broker_id=254958, broker_name="Lena Klinnert"),
    Unit(id=6200002, name="Industriering groß", street="Industriering", house_number="21",
         city="Viersen", property_space_value=9024.0, broker_id=254958, broker_name="Lena Klinnert"),
]
