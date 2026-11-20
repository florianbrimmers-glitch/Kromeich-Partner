"""Telefonnummern einheitlich und wählbar schreiben.

Gleiche Regel wie im Propstack-Connector (propstack-mcp/src/propstack/dedupe.ts,
formatPhone; Entscheidungen Florian, 13.11.2026):

1. Nach einer Ländervorwahl steht keine 0 der Ortsvorwahl. Aus Signaturen kommt
   oft "+49 (0) 151 …" oder "+49 0151 …" – so lässt sich die Nummer nicht anwählen.
   - "(0)" nach der Ländervorwahl: immer weg – außer in Ländern, in denen die 0
     zur Nummer gehört (dort ohne Klammern).
   - eine 0 ohne Klammern bzw. "(0171)": nur bei Ländern, in denen nach der
     Vorwahl nie eine 0 folgt.
2. Einheitlich mit Ländervorwahl: "00" wird zu "+", und eine Nummer ohne
   Ländervorwahl ("0171 …") bekommt die des Landes. Ohne Landesangabe gilt sie
   als deutsch (+49). Bei einem unbekannten Land bleibt die Nummer unverändert.

Die übrige Schreibweise (Leerzeichen, Bindestriche) bleibt. Was nicht wie eine
Nummer mit 0 oder + beginnt, bleibt ganz.
"""
from __future__ import annotations

import re

# Länder, in denen nach der Ländervorwahl nie eine 0 folgt
NO_ZERO_AFTER = ["49", "43", "41", "31", "32", "33", "44", "352", "45", "46", "47", "48", "34", "351",
                 "353", "420", "421", "385", "386", "40", "359", "358", "30", "90", "423"]
# Länder, in denen die 0 zur Rufnummer gehört (Italien, San Marino, Elfenbeinküste, Gabun, Kongo)
ZERO_BELONGS = ["39", "378", "225", "241", "242"]

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

_UNSET = object()


def country_calling_code(country: str | None):
    """Ländervorwahl zum Land ("49" usw.). _UNSET = kein Land angegeben,
    None = Land angegeben, aber nicht bekannt."""
    text = country.strip().lower() if isinstance(country, str) else ""
    if not text:
        return _UNSET
    for pattern, code in _COUNTRY_CODES:
        if re.fullmatch(pattern, text):
            return code
    return None


def _national(text: str, original: str, country: str | None) -> str:
    """Nummer ohne Ländervorwahl ("0171 …", "(0221) 47…") mit der Vorwahl des Landes schreiben."""
    known = country_calling_code(country)
    if known is None:
        return original
    code = "49" if known is _UNSET else known
    keep_zero = code in ZERO_BELONGS
    bracket = re.match(r"\(\s*0\s*(\d[\d\s]*?)\s*\)\s*", text)
    if bracket:
        return f"+{code} {'0' if keep_zero else ''}{bracket.group(1)} {text[bracket.end():]}".strip()
    return f"+{code} {text if keep_zero else re.sub(r'^0\s*', '', text)}"


def format_phone(phone: str | None, country: str | None = None) -> str | None:
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


def is_german_mobile_national(phone: str | None) -> bool:
    """Sieht die Nummer wie eine deutsche Mobilnummer ohne Ländervorwahl aus?
    (015x/016x/017x, 11–12 Ziffern einschließlich der führenden 0 – gleich
    beginnendes Festnetz in Delft, Paris oder Wien ist kürzer.)"""
    if not isinstance(phone, str):
        return False
    text = phone.strip()
    return bool(re.match(r"\(?\s*0(?!0)\s*\d", text)) and bool(re.fullmatch(r"01[567]\d{8,9}", re.sub(r"\D", "", text)))


def format_phone_for_contact(phone: str | None, country: str | None = None) -> str | None:
    """Wie format_phone, rät aber nicht: Eine deutsche Mobilnummer ohne
    Ländervorwahl an einem Kontakt im Ausland bleibt unverändert – das Land der
    Adresse sagt nichts Sicheres über die Handynummer ("0171 …" an einem Kontakt
    in Österreich würde sonst zu "+43 171 …")."""
    code = country_calling_code(country)
    if is_german_mobile_national(phone) and code is not _UNSET and code != "49":
        return phone
    return format_phone(phone, country)
