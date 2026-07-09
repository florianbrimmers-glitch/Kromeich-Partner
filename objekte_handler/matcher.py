from __future__ import annotations

import logging
import re

from .models import Classification, MatchResult, MatchStatus, Unit
from .propstack import search_units

logger = logging.getLogger(__name__)

SEARCH_LIMIT = 100


def normalize_street(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"str\.$|str\.(?=\s)|strasse\b", "straße", s)
    s = re.sub(r"str\b", "straße", s)
    s = re.sub(r"[\s\-]+", " ", s)
    return s.strip()


def _norm_house_number(s: str) -> str:
    return re.sub(r"\s+", "", s.strip().lower())


def filter_by_address(units: list[Unit], cls: Classification) -> list[Unit]:
    """q= ist eine Volltextsuche ("Hamburgring" -> 5 Treffer inkl. Nr. 3/30) –
    deshalb lokal auf Straße + exakte Hausnummer + Stadt nachfiltern."""
    result = units

    if cls.strasse:
        wanted = normalize_street(cls.strasse)
        result = [
            u for u in result
            if u.street and (normalize_street(u.street) == wanted or normalize_street(u.street).startswith(wanted))
        ]

    if cls.hausnummer:
        wanted_nr = _norm_house_number(cls.hausnummer)
        # Hausnummer extrahiert, aber im Datensatz leer => kein Match für den Kandidaten
        result = [u for u in result if u.house_number and _norm_house_number(u.house_number) == wanted_nr]

    if cls.stadt:
        wanted_city = cls.stadt.strip().lower()
        result = [u for u in result if not u.city or u.city.strip().lower() == wanted_city]

    if cls.objekt_name and not cls.strasse:
        wanted_name = cls.objekt_name.strip().lower()
        tokens = [t for t in wanted_name.split() if len(t) > 2]
        if tokens:
            def name_matches(u: Unit) -> bool:
                haystack = f"{u.name or ''} {u.title or ''}".lower()
                return any(t in haystack for t in tokens)
            named = [u for u in result if name_matches(u)]
            if named:
                result = named

    return result


def pick_by_size_hint(units: list[Unit], hint: str) -> Unit | None:
    """"die kleine Einheit" -> kleinste property_space_value; Zahl -> nächstliegende."""
    sized = [u for u in units if u.property_space_value is not None]
    if len(sized) != len(units) or not sized:
        return None  # fehlende Flächenwerte -> nicht ableitbar -> Stufe B

    hint = hint.strip().lower()
    if hint in ("kleinste", "klein", "kleiner"):
        return min(sized, key=lambda u: u.property_space_value)
    if hint in ("groesste", "größte", "gross", "groß", "groesser", "größer"):
        return max(sized, key=lambda u: u.property_space_value)

    match = re.search(r"[\d.,]+", hint)
    if match:
        try:
            wanted = float(match.group().replace(".", "").replace(",", "."))
        except ValueError:
            return None
        return min(sized, key=lambda u: abs(u.property_space_value - wanted))
    return None


def _same_address(units: list[Unit]) -> bool:
    keys = {
        (normalize_street(u.street) if u.street else "", _norm_house_number(u.house_number) if u.house_number else "")
        for u in units
    }
    # Ohne Straßendaten keine Aussage möglich -> nicht als "gleiche Adresse" werten
    return len(keys) == 1 and next(iter(keys)) != ("", "")


def _build_queries(cls: Classification) -> list[str]:
    queries: list[str] = []
    if cls.objekt_name:
        queries.append(cls.objekt_name)
    adresse = " ".join(t for t in (cls.strasse, cls.hausnummer, cls.stadt) if t)
    if adresse:
        queries.append(adresse)
    if cls.strasse and adresse != cls.strasse:
        queries.append(cls.strasse)
    return queries


def find_unit(cls: Classification) -> MatchResult:
    """Sucht die Unit zur Nachricht. Nur bei eindeutigem Treffer UNIQUE."""
    queries = _build_queries(cls)
    if not queries:
        return MatchResult(status=MatchStatus.NONE, grund="Keine Adresse/Objektname extrahiert")

    units: list[Unit] = []
    used_query = ""
    for q in queries:
        units = search_units(q)
        used_query = q
        if units:
            break

    if not units:
        return MatchResult(status=MatchStatus.NONE, grund=f"Keine Treffer für '{', '.join(queries)}'")

    if len(units) >= SEARCH_LIMIT:
        return MatchResult(
            status=MatchStatus.AMBIGUOUS,
            kandidaten=units[:10],
            grund=f"Suche '{used_query}' zu unspezifisch ({len(units)}+ Treffer)",
        )

    kandidaten = filter_by_address(units, cls)

    if not kandidaten:
        return MatchResult(
            status=MatchStatus.NONE,
            kandidaten=units[:10],
            grund=f"{len(units)} Treffer für '{used_query}', aber keiner passt zu Adresse/Hausnummer",
        )

    if len(kandidaten) == 1:
        return MatchResult(status=MatchStatus.UNIQUE, units=kandidaten, kandidaten=kandidaten)

    # Mehrere Einheiten am selben Objekt
    if _same_address(kandidaten):
        if cls.groessen_hinweis:
            unit = pick_by_size_hint(kandidaten, cls.groessen_hinweis)
            if unit:
                return MatchResult(
                    status=MatchStatus.UNIQUE,
                    units=[unit],
                    kandidaten=kandidaten,
                    grund=f"Aus {len(kandidaten)} Einheiten über Größen-Hinweis '{cls.groessen_hinweis}' gewählt",
                )
            return MatchResult(
                status=MatchStatus.AMBIGUOUS,
                kandidaten=kandidaten,
                grund=f"Größen-Hinweis '{cls.groessen_hinweis}' nicht auflösbar (fehlende Flächenwerte)",
            )
        # Kein Größen-Hinweis: Nachricht betrifft das ganze Objekt -> alle Einheiten
        # (Hamburgring-48-Fall: getrennte Alt-Datensätze an derselben Adresse)
        return MatchResult(
            status=MatchStatus.UNIQUE,
            units=kandidaten,
            kandidaten=kandidaten,
            grund=f"Ganzes Objekt: {len(kandidaten)} Einheiten an derselben Adresse",
        )

    return MatchResult(
        status=MatchStatus.AMBIGUOUS,
        kandidaten=kandidaten,
        grund=f"{len(kandidaten)} Kandidaten für '{used_query}', keine eindeutige Zuordnung",
    )
