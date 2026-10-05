"""Reine Abgleichslogik (ohne Netz) – Personen, Firmen und alte Verknüpfungen.

Bewusst konservativ: bei jedem Zweifel lieber Stufe B als ein falscher Auto-Write."""
from __future__ import annotations

import re

from .models import Company, CompanyMatch, Link, MatchStatus, Person, PersonMatch

_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})

# Wörter, die bei Firmennamen nichts unterscheiden ("Marq logistik" == "Marq Logistics")
_FIRMEN_FUELLWOERTER = {
    "gmbh", "mbh", "ag", "se", "kg", "co", "kgaa", "ohg", "ltd", "limited", "inc", "bv", "nv",
    "plc", "sa", "sarl", "llc", "und", "the", "group", "gruppe", "holding",
    "deutschland", "germany", "europe", "logistik", "logistics",
}


def norm_name(s: str | None) -> str:
    """Personennamen vergleichbar machen: "Fröhlich" == "Froehlich", Groß/Klein egal."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().translate(_UMLAUTE))


def firmen_suchbegriff(gemeldet: str) -> str:
    """Suchbegriff für die Propstack-Volltextsuche: nur die markanten Wörter.

    Die Suche verlangt alle Wörter – "Marq logistik" fände "Marq Logistics" sonst nicht."""
    return " ".join(firmen_tokens(gemeldet)) or gemeldet


def firmen_tokens(s: str | None) -> list[str]:
    """Signifikante Wörter eines Firmennamens (ohne Rechtsform-/Füllwörter)."""
    worte = re.findall(r"[a-z0-9]+", (s or "").lower().translate(_UMLAUTE))
    return [w for w in worte if w not in _FIRMEN_FUELLWOERTER]


def firma_passt(gemeldet: str | None, propstack_name: str | None) -> bool:
    """Jedes signifikante Wort der Meldung muss ein Wort im Propstack-Namen anfangen.

    "arrow" passt auf "Arrow Capital Deutschland GmbH", "Swiss life" auf beide
    Swiss-Life-Gesellschaften, "Goodman" nicht auf "Goodcang". Kurze Wörter (bis
    3 Zeichen, z.B. "ID" in "ID Logistics") müssen exakt passen, sonst träfe "id"
    auch "idealo"."""
    gesucht = firmen_tokens(gemeldet)
    vorhanden = firmen_tokens(propstack_name)
    if not gesucht or not vorhanden:
        return False

    def wort_passt(g: str, v: str) -> bool:
        return v == g if len(g) <= 3 else v.startswith(g)

    return all(any(wort_passt(g, v) for v in vorhanden) for g in gesucht)


def match_person(records: list[dict], vorname: str | None, nachname: str | None) -> PersonMatch:
    """Exakter Vor- + Nachnamen-Abgleich auf den Suchtreffern.

    Firmen-Datensätze ohne Vornamen fallen raus; Personen, die fälschlich als Firma
    markiert sind, haben einen Vornamen und zählen mit."""
    if not nachname:
        return PersonMatch(status=MatchStatus.NONE, grund="Kein Nachname erkannt")

    treffer: dict[int, Person] = {}
    for r in records:
        if not r.get("id") or not r.get("first_name"):
            continue
        if norm_name(r.get("last_name")) != norm_name(nachname):
            continue
        if vorname and norm_name(r.get("first_name")) != norm_name(vorname):
            continue
        treffer[r["id"]] = Person(
            id=r["id"], first_name=r.get("first_name"), last_name=r.get("last_name"),
            company=r.get("company"), email=r.get("email"), description=r.get("description"),
        )

    personen = list(treffer.values())
    name = " ".join(t for t in (vorname, nachname) if t)
    if not personen:
        return PersonMatch(status=MatchStatus.NONE, grund=f"{name} nicht in Propstack gefunden")
    if len(personen) > 1:
        return PersonMatch(
            status=MatchStatus.AMBIGUOUS, kandidaten=personen,
            grund=f"{len(personen)} Datensätze für {name} (Dublette?)",
        )
    return PersonMatch(status=MatchStatus.UNIQUE, person=personen[0], kandidaten=personen)


def match_company(records: list[dict], gemeldet: str | None) -> CompanyMatch:
    """Zielfirma unter den Suchtreffern bestimmen.

    Eindeutig nur, wenn genau eine Firma passt oder genau eine exakt so heißt."""
    if not gemeldet:
        return CompanyMatch(status=MatchStatus.NONE, grund="Keine neue Firma genannt")

    firmen: dict[int, Company] = {}
    for r in records:
        if not r.get("id") or not r.get("is_company") or r.get("first_name"):
            continue
        name = r.get("company") or r.get("name") or ""
        if firma_passt(gemeldet, name) or firma_passt(gemeldet, r.get("name")):
            firmen[r["id"]] = Company(id=r["id"], name=name)

    kandidaten = list(firmen.values())
    if not kandidaten:
        return CompanyMatch(status=MatchStatus.NONE, grund=f"Firma '{gemeldet}' nicht in Propstack")
    if len(kandidaten) == 1:
        return CompanyMatch(status=MatchStatus.UNIQUE, company=kandidaten[0], kandidaten=kandidaten)

    exakt = [c for c in kandidaten if firmen_tokens(c.name) == firmen_tokens(gemeldet)]
    if len(exakt) == 1:
        return CompanyMatch(status=MatchStatus.UNIQUE, company=exakt[0], kandidaten=kandidaten)
    return CompanyMatch(
        status=MatchStatus.AMBIGUOUS, kandidaten=kandidaten,
        grund=f"{len(kandidaten)} Firmen passen auf '{gemeldet}'",
    )


def alte_links(links: list[Link], person: Person, alte_firma: str | None, neue_firma_id: int | None) -> list[Link]:
    """Verknüpfungen, die zum bisherigen Arbeitgeber gehören und entfernt werden.

    Ist die alte Firma genannt, zählt sie; sonst die Firma im Kontakt-Feld 'company'."""
    bezug = alte_firma or person.company
    if not bezug:
        return []
    return [
        link for link in links
        if link.company_id != neue_firma_id and firma_passt(bezug, link.company_name)
    ]


def ist_bereits_aktuell(person: Person, links: list[Link], neue_firma: Company) -> bool:
    """Steht die Person schon bei der neuen Firma (Feld + Verknüpfung)?"""
    verknuepft = any(link.company_id == neue_firma.id for link in links)
    feld = firmen_tokens(person.company) == firmen_tokens(neue_firma.name)
    return verknuepft and feld


def alte_firma_plausibel(person: Person, links: list[Link], alte_firma: str | None) -> bool:
    """Passt die gemeldete alte Firma zu dem, was Propstack über die Person weiß?

    Ohne Angabe der alten Firma gibt es nichts zu widersprechen."""
    if not alte_firma:
        return True
    if firma_passt(alte_firma, person.company):
        return True
    return any(firma_passt(alte_firma, link.company_name) for link in links)


def eindeutig_ueber_verknuepfung(
    firma: CompanyMatch, links: list[Link], firmenfeld: str | None = None
) -> CompanyMatch:
    """Mehrere passende Firmen, aber die Person ist schon mit genau einer verknüpft
    ("zu Aurelis gewechselt" bei zwei Aurelis-Gesellschaften) -> diese ist gemeint.
    Bei mehreren Verknüpfungen entscheidet das Firmenfeld des Kontakts."""
    if firma.status != MatchStatus.AMBIGUOUS:
        return firma
    verknuepft = [c for c in firma.kandidaten if any(link.company_id == c.id for link in links)]
    if len(verknuepft) > 1 and firmenfeld:
        verknuepft = [c for c in verknuepft if firmen_tokens(c.name) == firmen_tokens(firmenfeld)]
    if len(verknuepft) != 1:
        return firma
    return CompanyMatch(
        status=MatchStatus.UNIQUE, company=verknuepft[0], kandidaten=firma.kandidaten,
        grund=f"{firma.grund}; Person ist bereits mit {verknuepft[0].name} verknüpft",
    )
