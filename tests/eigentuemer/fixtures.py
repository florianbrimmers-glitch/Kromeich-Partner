"""Bausteine für die Tests des Eigentümer-Portals."""
from __future__ import annotations

from eigentuemer.models import Kontakt, Objektdaten

NACHWEIS = ("nachweis.pdf", b"%PDF-1.4 Grundbuchauszug Testinhalt")


def kontakt(**overrides) -> Kontakt:
    basis = {"vorname": "Erika", "nachname": "Musterfrau", "firma": "Muster Logistik GmbH",
             "email": "erika@example.invalid", "telefon": "0151 0000000"}
    basis.update(overrides)
    return Kontakt(**basis)


def objekt(**overrides) -> Objektdaten:
    basis = {"strasse": "Mellinghofer Straße", "hausnummer": "40", "plz": "45473",
             "stadt": "Mülheim an der Ruhr", "flaeche_qm": 5400.0, "hallenhoehe_m": 10.5,
             "rampe": True, "verfuegbar_ab": "sofort", "miete_eur_qm": 5.2,
             "beschreibung": "Beispielhalle für den Test."}
    basis.update(overrides)
    return Objektdaten(**basis)


def formular(**overrides) -> dict:
    """Felder für POST /api/einreichung."""
    import json

    basis = {
        "rolle": "eigentuemer",
        "kontakt": json.dumps(kontakt().model_dump()),
        "objekt": json.dumps(objekt().model_dump()),
        "einwilligung": "true",
    }
    basis.update(overrides)
    return basis
