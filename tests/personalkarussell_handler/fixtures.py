"""Suchtreffer nach den realen Fällen aus #personalkarussel-logistik (Stand 10/2026)."""

# Zwei aurelis-Gesellschaften – "zu Aurelis gewechselt" ist damit nicht eindeutig
AURELIS = [
    {"id": 17221995, "is_company": True, "name": "Aurelis Real Estate GmbH", "company": "Aurelis Real Estate GmbH"},
    {"id": 23378833, "is_company": True, "name": "Aurelis Real Estate Service GmbH",
     "company": "Aurelis Real Estate Service GmbH"},
    # Person, die fälschlich als Firma markiert ist – darf nie als Zielfirma gelten
    {"id": 22802061, "is_company": True, "first_name": "Marcus", "last_name": "Behnke",
     "name": "Marcus Behnke (Aurelis Real Estate Service GmbH)", "company": "Aurelis Real Estate Service GmbH"},
]

SWISS_LIFE = [
    {"id": 25289935, "is_company": True, "name": "Swiss Life Asset Manager Deutschland",
     "company": "Swiss Life Asset Manager Deutschland"},
    {"id": 35208875, "is_company": True, "name": "Swiss Life Asset Managers Logistics GmbH",
     "company": "Swiss Life Asset Managers Logistics GmbH"},
]

CENTRALIS = [
    {"id": 23052700, "is_company": True, "name": "Centralis Immobilien Management GmbH",
     "company": "Centralis Immobilien Management GmbH"},
    {"id": 23052759, "is_company": False, "first_name": "Felix", "last_name": "Lorenz",
     "name": "Felix Lorenz", "company": "Centralis Immobilien Management GmbH"},
]

MARQ = [
    {"id": 18300001, "is_company": True, "name": "Marq Logistics", "company": "Marq Logistics"},
]

# Tim Hamacher lag vor der Bereinigung doppelt im System
TIM_HAMACHER_DOPPELT = [
    {"id": 23669297, "first_name": "Tim", "last_name": "Hamacher", "company": "Swiss Life Asset Manager Deutschland"},
    {"id": 32056894, "first_name": "Tim", "last_name": "Hamacher", "company": "Swiss Life Asset Managers Logistics GmbH"},
]

FELIX_LORENZ_ALT = [
    {"id": 23052759, "first_name": "Felix", "last_name": "Lorenz", "company": "Aquila Capital",
     "email": "felix.lorenz@aquila-capital.de"},
    {"id": 40000001, "first_name": "Felix", "last_name": "Lorenzen", "company": "Irgendwo GmbH"},
]
