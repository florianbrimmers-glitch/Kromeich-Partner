"""Passt der Vermieter einer Marktmeldung zum Eigentümer einer Einheit?

Anlass (Stand 20.11.2026, 129 einzeln geprüfte Review-Aufgaben): Stimmte der Eigentümer der
gewählten Einheit mit dem Vermieter der Meldung überein (43 Aufgaben), ging es in 40 Fällen
um ein eigenes Objekt. Widersprach er (22 Aufgaben), war die gewählte Einheit in 20 Fällen
nicht gemeint – eine Ixocon-Meldung hing an einer BEOS-Halle, eine VGP-Meldung an einer
CTP-Einheit. Bei 48 Aufgaben stand am Objekt kein Eigentümer; dann ist nichts zu sagen.

Verglichen werden die Namenswörter, nicht die ganze Zeichenkette: „Garbe“ und „GARBE
Industrial GmbH & Co. KG“ sind derselbe, „Panattoni“ und „evolutiq GmbH“ nicht. Im
Altbestand steht im Feld oft Nummer und Ansprechpartner davor („65110 Jochen Boudon ADOLF
WEBER INVESTMENT GMBH“) – das stört nicht.
"""
from __future__ import annotations

import re

# Rechtsformen, Gattungswörter und Beschreibungen ohne Namen („ein britischer Investor“).
# Bleibt nach dem Abzug nichts übrig, gilt der Name als unbekannt – dann wird nichts verworfen.
_ALLGEMEIN = {
    "gmbh", "co", "kg", "ag", "se", "mbh", "ug", "sa", "sarl", "bv", "lp", "ltd", "inc", "kgaa",
    "und", "and", "der", "die", "das", "des", "von", "mit", "für", "the", "of", "im", "in", "am",
    "ein", "eine", "einen", "einem", "einer",
    "germany", "deutschland", "europe", "european", "international", "internationaler", "internationale",
    "real", "estate", "property", "properties", "industrial", "logistic", "logistics", "logistik",
    "park", "parks", "group", "gruppe", "holding", "invest", "investment", "investments", "management",
    "immobilien", "immobilie", "grundstücksgesellschaft", "gesellschaft", "facilities", "industriebau",
    "capital", "partners", "partner", "asset", "assets", "advisors", "development", "developments",
    "projektentwicklung", "company", "fonds", "fund", "jv", "joint", "venture",
    "investor", "investoren", "entwickler", "projektentwickler", "eigentümer", "eigentuemer", "vermieter",
    "bestandshalter", "unternehmen", "konzern", "privater", "private", "privat", "institutioneller",
    "britischer", "deutscher", "family", "office", "manager", "immobilienunternehmen", "immobilieninvestor",
    "lokaler", "regionaler", "nicht", "genannt", "unbekannt", "west", "ost", "nord", "süd",
}


def namen(text: str | None) -> set[str]:
    """Die Namenswörter eines Firmennamens, klein geschrieben."""
    woerter = re.findall(r"[a-zäöüß0-9]+", (text or "").lower())
    return {
        w for w in woerter
        if w not in _ALLGEMEIN and not w.isdigit() and (len(w) >= 3 or any(c.isdigit() for c in w))
    }


def passt(vermieter: str | None, eigentuemer: str | None) -> bool | None:
    """True = derselbe, False = erkennbar ein anderer, None = nicht zu sagen
    (eine Seite fehlt oder besteht nur aus Gattungswörtern)."""
    v, e = namen(vermieter), namen(eigentuemer)
    if not v or not e:
        return None
    return bool(v & e)
