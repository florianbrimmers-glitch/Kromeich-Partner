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
            # Passt der Name auf keine Einheit, ist das kein Treffer. Früher blieb die
            # Liste dann ungefiltert – ein einzelner, völlig fremder Suchtreffer galt
            # als „eindeutig“ und wäre in Stufe A auf vermietet gesetzt worden.
            result = [u for u in result if name_matches(u)]

    return result


# Wie weit die Fläche der Einheit von der genannten Zahl abweichen darf
SIZE_TOLERANCE = 0.15


def parse_qm(text: str) -> float | None:
    """Quadratmeterzahl aus einem Hinweis lesen: "7.666 qm", "7666.0", "9,024", "12.500,5".

    Punkt und Komma sind Tausendertrenner, wenn danach genau drei Ziffern stehen –
    bei Hallenflächen ist "9,024" nie neun Komma null zwei vier. Früher wurde jeder
    Punkt entfernt: "7666.0" ergab 76.660 und traf die falsche Einheit."""
    m = re.search(r"\d[\d.,]*", text or "")
    if not m:
        return None
    raw = m.group().rstrip(".,")
    try:
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", raw):
            return float(re.sub(r"[.,]", "", raw))
        if re.fullmatch(r"\d{1,3}(\.\d{3})+,\d+", raw):
            return float(raw.replace(".", "").replace(",", "."))
        if re.fullmatch(r"\d{1,3}(,\d{3})+\.\d+", raw):
            return float(raw.replace(",", ""))
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def pick_by_size_hint(units: list[Unit], hint: str) -> Unit | None:
    """"die kleine Einheit" -> kleinste Fläche; Zahl -> die Einheit mit dieser Fläche.

    Schon vermietete Einheiten zählen nicht mit: „die kleine ist vermietet“ meint die
    kleinste, die noch frei ist. Eine Zahl muss auf ±15 % passen, und keine zweite
    Einheit darf fast genauso gut passen – sonst None (-> Stufe B). Früher gewann
    immer die „nächstliegende“: „3.000 m² vermietet“ traf eine Einheit mit 7.666 m²."""
    offen = [u for u in units if u.rented is not True]
    sized = [u for u in offen if u.property_space_value is not None]
    if len(sized) != len(offen) or not sized:
        return None  # fehlende Flächenwerte -> nicht ableitbar -> Stufe B

    hint = hint.strip().lower()
    if hint in ("kleinste", "klein", "kleiner"):
        return min(sized, key=lambda u: u.property_space_value)
    if hint in ("groesste", "größte", "gross", "groß", "groesser", "größer"):
        return max(sized, key=lambda u: u.property_space_value)

    wanted = parse_qm(hint)
    if not wanted or wanted <= 0:
        return None
    nach_abstand = sorted(sized, key=lambda u: abs(u.property_space_value - wanted))
    bester = abs(nach_abstand[0].property_space_value - wanted)
    if bester > SIZE_TOLERANCE * wanted:
        return None
    if len(nach_abstand) > 1:
        zweiter = abs(nach_abstand[1].property_space_value - wanted)
        # Die zweite Einheit darf nicht fast genauso gut passen: außerhalb der Toleranz
        # oder mindestens dreimal so weit weg (gemessen an mindestens 1 % der Zahl).
        if zweiter <= SIZE_TOLERANCE * wanted and zweiter < 3 * max(bester, 0.01 * wanted):
            return None
    return nach_abstand[0]


# Die Nachricht nennt eine bestimmte Einheit oder nur einen Teil – dann ist nicht das
# ganze Objekt gemeint ("Halle 2 ist vermietet", "Unit 1 und 2", "Teilfläche").
_BEZEICHNER = r"(?:halle|unit|einheit|geb(?:ä|ae)ude|bauabschnitt|modul|abschnitt|block|haus)"
_EINZELNE_EINHEIT = re.compile(
    rf"\b{_BEZEICHNER}\s*[-.:#]?\s*\d+[a-z]?\b"         # "Halle 2", "Unit 1.2", "Gebäude 17"
    rf"|\b{_BEZEICHNER}\s+(?:[a-h]|[ivx]{{1,4}})\b"      # "Halle B", "Unit E", "Block II" – nur nach Leerzeichen
    r"|\b(?:ba|bt|dc)\s*\d+\b"                          # "BA 2", "DC3"
    r"|\bteil(?:fl(?:ä|ae)che|vermiet\w*|weise)\b|\bzum\s+teil\b"
    r"|\beine\s+(?:der\s+)?(?:einheit|halle|unit)\w*",
    re.IGNORECASE,
)


def nennt_einzelne_einheit(text: str | None) -> str | None:
    """Der Wortlaut, mit dem die Nachricht eine einzelne Einheit/Teilfläche nennt – sonst None."""
    m = _EINZELNE_EINHEIT.search(text or "")
    return m.group(0).strip() if m else None


def _same_address(units: list[Unit]) -> bool:
    keys = {
        (normalize_street(u.street) if u.street else "", _norm_house_number(u.house_number) if u.house_number else "")
        for u in units
    }
    # Ohne Straßendaten keine Aussage möglich -> nicht als "gleiche Adresse" werten
    if len(keys) != 1 or next(iter(keys)) == ("", ""):
        return False
    # "Industriestraße 12" gibt es in vielen Orten: Liegen die Einheiten erkennbar in
    # verschiedenen Orten oder PLZ, ist es nicht dasselbe Objekt.
    orte = {u.city.strip().lower() for u in units if u.city and u.city.strip()}
    plz = {u.zip_code.strip() for u in units if u.zip_code and u.zip_code.strip()}
    return len(orte) <= 1 and len(plz) <= 1


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


def find_unit(cls: Classification, text: str | None = None) -> MatchResult:
    """Sucht die Unit zur Nachricht. Nur bei eindeutigem Treffer UNIQUE.

    text: Wortlaut der Nachricht – nur um zu erkennen, ob sie eine einzelne Einheit
    nennt, wenn an der Adresse mehrere liegen."""
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
        if not cls.strasse and not cls.objekt_name:
            # Nur ein Ort: Dass dort genau eine Einheit geführt wird, belegt nicht,
            # dass sie gemeint ist.
            return MatchResult(
                status=MatchStatus.AMBIGUOUS,
                kandidaten=kandidaten,
                grund="Nur der Ort ist genannt – ein einzelner Treffer dort ist kein eindeutiger Beleg",
            )
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
        # Kein Größen-Hinweis, aber die Nachricht nennt eine bestimmte Einheit oder nur
        # einen Teil ("Halle 2 ist vermietet"): Dann nicht alle Einheiten schließen.
        # Einheiten eines Projekts erben dessen Adresse – das trifft jedes Projekt
        # mit mehreren Einheiten.
        genannt = nennt_einzelne_einheit(text)
        if genannt:
            return MatchResult(
                status=MatchStatus.AMBIGUOUS,
                kandidaten=kandidaten,
                grund=(
                    f"Nachricht nennt „{genannt}“, an der Adresse liegen {len(kandidaten)} Einheiten – "
                    "welche gemeint ist, entscheidet ein Mensch"
                ),
            )
        # Sonst betrifft die Nachricht das ganze Objekt -> alle Einheiten
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
