"""Eigentümer-Achse für das Objekt-Matching.

Die Adress-Achse in `matcher.py` scheitert genau dann, wenn eine Nachricht den
Eigentümer nennt und keine Adresse — und das ist der Normalfall bei
Flächenupdates ("Flächenupdate Mileway 07/26") und bei Marktmeldungen
("Vermieter: Aconlog"). `search_units("Mileway")` findet nichts, weil "Mileway"
in keinem Objekttitel steht; die Zugehörigkeit steht ausschließlich in den
Eigentümer-Verknüpfungen.

Belegt am 31.07.2026 an zwei liegengebliebenen Aufgaben:

  - Aufgabe 143382495 (Aconlog Viersen) hatte "Vermieter: Aconlog" extrahiert
    und dann über den Ortsnamen gematcht — Ergebnis war Unit 2778052
    ("Mackenstein 48"), ein Datensatz ohne Flächen, ohne Status und ohne jede
    Eigentümer-Verknüpfung. Über den Eigentümer wäre es Kontakt 17220059
    -> Projekt 499759 -> Units 5050165/5050187 gewesen, in zwei Requests.
  - Aufgabe 142592761 (Flächenupdate Mileway) endete mit "23 Kandidaten, keine
    eindeutige Zuordnung". Über den Eigentümer sind es 26 Einheiten in 3
    Projekten — und das ist bei einem Flächenupdate die vollständige, richtige
    Antwort, kein Mehrdeutigkeitsfehler.

Wichtig: `GET /relationships` ignoriert seine Filterparameter. Die Liste muss
paginiert geholt und clientseitig gefiltert werden. Geschrieben wird
`related_client_id`, gelesen `client_id` — beide Felder werden hier geprüft.
"""

from __future__ import annotations

import logging
import re

from .propstack import all_relationships, search_contacts

logger = logging.getLogger(__name__)

# Rechtsformen und Füllwörter, die beim Namensvergleich nichts unterscheiden.
_NOISE = {
    "gmbh", "mbh", "ag", "kg", "co", "ohg", "se", "ug", "ltd", "llc", "bv", "nv",
    "sarl", "plc", "inc", "und", "and", "germany", "deutschland", "holding",
    "projektentwicklung", "development", "developments", "real", "estate",
    "immobilien", "logistics", "logistik", "properties", "property", "group",
    "gruppe", "invest", "investment", "management", "verwaltung",
}

OWNER_ROLE = "owner"


def normalize_company(name: str) -> str:
    """Firmenname auf die unterscheidenden Tokens reduzieren.

    "Mileway Germany GmbH" -> "mileway", "Aconlog Projektentwicklung GmbH" ->
    "aconlog". Ohne das matcht "Mileway Germany GmbH" nicht gegen "Mileway",
    und "X Immobilien GmbH" würde gegen jedes andere "* Immobilien GmbH"
    matchen.
    """
    tokens = re.split(r"[^0-9a-zäöüß]+", name.strip().lower())
    kern = [t for t in tokens if t and t not in _NOISE]
    # Fällt alles der Rauschliste zum Opfer, ist der Rohname besser als nichts.
    return " ".join(kern) if kern else " ".join(t for t in tokens if t)


def find_owner_contacts(name: str) -> list[dict]:
    """Kontakte zu einem Eigentümernamen suchen.

    Zurück kommen Firmen- UND Personenkontakte der Firma: Verknüpfungen hängen
    in der Praxis an beiden (bei Aconlog war die Firma Eigentümer und die Person
    Partner am selben Objekt). Wer nur `is_company` nimmt, verliert Objekte.
    """
    if not name or not name.strip():
        return []

    wanted = normalize_company(name)
    if not wanted:
        return []
    wanted_tokens = set(wanted.split())

    kandidaten = search_contacts(name)
    treffer = []
    for contact in kandidaten:
        haystack = normalize_company(
            f"{contact.get('company') or ''} {contact.get('name') or ''}"
        )
        # Jedes unterscheidende Token des gesuchten Namens muss vorkommen,
        # sonst liefert q= auch thematisch verwandte Fremdfirmen mit.
        if wanted_tokens and wanted_tokens.issubset(set(haystack.split())):
            treffer.append(contact)

    logger.info(
        "Eigentümer-Suche '%s' (normalisiert '%s'): %d von %d Kontakten passen",
        name, wanted, len(treffer), len(kandidaten),
    )
    return treffer


def owned_objects(contact_ids: list[int]) -> tuple[list[int], list[int]]:
    """Einheiten- und Projekt-IDs, die diesen Kontakten als Eigentümer gehören.

    Rolle `owner` — `partner` und `associate` sind ausdrücklich nicht gemeint,
    sonst zieht man Fremdmandate ins Portfolio.
    """
    if not contact_ids:
        return [], []

    gesucht = set(contact_ids)
    units: set[int] = set()
    projects: set[int] = set()

    for rel in all_relationships():
        if rel.get("internal_name") != OWNER_ROLE:
            continue
        # Geschrieben wird related_client_id, gelesen client_id - beides prüfen.
        if not ({rel.get("related_client_id"), rel.get("client_id")} & gesucht):
            continue
        if rel.get("property_id"):
            units.add(rel["property_id"])
        if rel.get("project_id"):
            projects.add(rel["project_id"])

    logger.info(
        "Eigentümer %s: %d Einheiten, %d Projekte",
        sorted(gesucht), len(units), len(projects),
    )
    return sorted(units), sorted(projects)


def resolve_owner(name: str) -> tuple[list[int], list[int], list[int]]:
    """Eigentümername -> (Kontakt-IDs, Einheiten-IDs, Projekt-IDs).

    Leere Listen, wenn der Name nicht auflösbar ist — dann bleibt es bei der
    Adress-Achse.
    """
    contacts = find_owner_contacts(name)
    contact_ids = [c["id"] for c in contacts if c.get("id")]
    if not contact_ids:
        logger.info("Eigentümer '%s' nicht in Propstack auflösbar", name)
        return [], [], []

    units, projects = owned_objects(contact_ids)
    return contact_ids, units, projects
