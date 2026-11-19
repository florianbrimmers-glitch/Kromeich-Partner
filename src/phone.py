"""Telefonnummern einheitlich und wählbar schreiben.

Dieselbe Regel wie im Propstack-Connector (propstack-mcp/src/propstack/dedupe.ts,
formatPhone) – Entscheidungen Florian vom 13.11.2026. Die Tests in tests/test_phone.py
sind die des Connectors (propstack-mcp/test/phone.test.ts); wer hier etwas ändert,
ändert es an beiden Stellen.

1. Nach einer Ländervorwahl steht keine 0 der Ortsvorwahl. Aus Signaturen kommt oft
   „+49 (0) 151 …“ oder „+49 0151 …“ – so gespeichert lässt sich die Nummer nicht
   anwählen (am 13.11.2026 bei 8 der 600 neuesten Kontakte aus diesem Import).
   - „(0)“ nach der Ländervorwahl: immer weg – außer in Ländern, in denen die 0 zur
     Nummer gehört (dort ohne Klammern).
   - eine 0 ohne Klammern bzw. „(0171)“: nur bei Ländern, in denen nach der Vorwahl
     nie eine 0 folgt.
2. Einheitlich mit Ländervorwahl: „00“ wird zu „+“, eine Nummer ohne Ländervorwahl
   („0171 …“) bekommt die des Landes. Ohne Landesangabe gilt sie als deutsch (+49).
   Ist ein Land angegeben, das hier nicht bekannt ist, bleibt die Nummer unverändert,
   statt eine falsche Vorwahl zu erfinden.

Die übrige Schreibweise (Leerzeichen, Bindestriche) bleibt. Was nicht wie eine Nummer
mit 0 oder + beginnt, bleibt ganz.
"""
from __future__ import annotations

import re

# Länder, in denen nach der Ländervorwahl nie eine 0 folgt.
NO_ZERO_AFTER = [
    "49", "43", "41", "31", "32", "33", "44", "352", "45", "46", "47", "48", "34", "351",
    "353", "420", "421", "385", "386", "40", "359", "358", "30", "90", "423",
]
# Länder, in denen die 0 zur Rufnummer gehört und mitgewählt wird
# (Italien, San Marino, Elfenbeinküste, Gabun, Kongo).
ZERO_BELONGS = ["39", "378", "225", "241", "242"]

# Ländervorwahl zum Land des Kontakts – für Nummern ohne Ländervorwahl. Bewusst nur die
# Länder, mit denen Kromeich zu tun hat; ein Land, das hier fehlt, gilt als unbekannt.
_COUNTRY_CODES: list[tuple[str, str]] = [
    (r"de|deu|deutschland|germany|brd|bundesrepublik deutschland", "49"),
    (r"at|aut|österreich|oesterreich|austria", "43"),
    (r"ch|che|schweiz|switzerland|suisse", "41"),
    (r"nl|nld|niederlande|netherlands|nederland|holland", "31"),
    (r"be|bel|belgien|belgium|belgique|belgië", "32"),
    (r"fr|fra|frankreich|france", "33"),
    (r"lu|lux|luxemburg|luxembourg", "352"),
    (r"gb|gbr|uk|großbritannien|grossbritannien|vereinigtes königreich|united kingdom|england", "44"),
    (r"it|ita|italien|italy|italia", "39"),
    (r"pl|pol|polen|poland|polska", "48"),
    (r"cz|cze|tschechien|tschechische republik|czechia|czech republic", "420"),
    (r"dk|dnk|dänemark|daenemark|denmark", "45"),
    (r"es|esp|spanien|spain|españa", "34"),
    (r"se|swe|schweden|sweden", "46"),
    (r"li|lie|liechtenstein", "423"),
]

UNBEKANNT = object()  # Land angegeben, aber nicht in der Liste


def country_calling_code(country: object):
    """Ländervorwahl zum Land: "49" usw.; None = kein Land angegeben,
    UNBEKANNT = Land angegeben, aber nicht bekannt."""
    text = country.strip().lower() if isinstance(country, str) else ""
    if not text:
        return None
    for pattern, code in _COUNTRY_CODES:
        if re.fullmatch(pattern, text):
            return code
    return UNBEKANNT


def _national(text: str, original: str, country: object) -> str:
    """Nummer ohne Ländervorwahl („0171 …“, „(0221) 47…“) mit der Vorwahl des Landes schreiben."""
    known = country_calling_code(country)
    if known is UNBEKANNT:
        return original
    code = known or "49"
    keep_zero = code in ZERO_BELONGS
    # „(0221) 4710199“: Klammer um die Ortsvorwahl auflösen
    bracket = re.match(r"\(\s*0\s*(\d[\d\s]*?)\s*\)\s*", text)
    if bracket:
        return f"+{code} {'0' if keep_zero else ''}{bracket.group(1)} {text[bracket.end():]}".strip()
    rest = text if keep_zero else re.sub(r"^0\s*", "", text)
    return f"+{code} {rest}"


def format_phone(phone: str | None, country: object = None) -> str | None:
    """Telefonnummer einheitlich schreiben (siehe Modulbeschreibung)."""
    if not isinstance(phone, str):
        return phone
    text = phone.strip()
    if re.match(r"\(?\s*0(?!0)\s*\d", text):
        return _national(text, phone, country)
    prefix = re.match(r"(\+|00)\s*", text)
    if not prefix:
        return phone
    rest = text[prefix.end():]
    lead_match = re.match(r"\d+", rest)
    lead = lead_match.group(0) if lead_match else ""
    # Ländervorwahl: die bekannte am Anfang (auch bei zusammengeschriebenen Nummern),
    # sonst die Ziffern bis zum ersten Trenner
    code = next((c for c in NO_ZERO_AFTER + ZERO_BELONGS if lead.startswith(c)), None)
    if code is None and 1 <= len(lead) <= 3:
        code = lead
    if not code:
        return f"+{rest}" if prefix.group(1) == "00" and lead else phone
    tail = rest[len(code):]
    separator = re.match(r"[\s\-/.]*", tail).group(0)
    body = tail[len(separator):]
    keep_zero = code in ZERO_BELONGS
    bracketed = re.match(r"\(\s*0\s*\)\s*", body)
    if bracketed:
        return f"+{code} {'0' if keep_zero else ''}{body[bracketed.end():]}"
    if code in NO_ZERO_AFTER:
        in_bracket = re.match(r"\(\s*0(?=\d)", body)
        if in_bracket:
            return f"+{code}{separator}({body[in_bracket.end():]}"
        if re.match(r"0\d", body):
            return f"+{code}{separator}{body[1:]}"
    return f"+{code}{tail}" if prefix.group(1) == "00" else phone
