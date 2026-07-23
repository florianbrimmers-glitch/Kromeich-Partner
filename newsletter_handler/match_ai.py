from __future__ import annotations

import json
import logging

import anthropic

from . import config
from .classifier import _get_client, _parse_extraction_json
from .models import Deal, MatchResult, MatchStatus, Unit

logger = logging.getLogger(__name__)

SELECT_PROMPT = """Du gleichst eine Immobilien-Marktmeldung gegen den Objektbestand eines Gewerbeimmobilien-Maklers (Kromeich & Partner) in Propstack ab.

DEAL (aus einem Logistik-Newsletter):
- Objekt/Projekt: {objekt_name}
- Ort laut Meldung: {ort}
- Vermieter/Entwickler: {vermieter}
- Mieter: {mieter}
- Größe: {groesse}

WICHTIG: Der Ort aus der Meldung ist oft ungenau (z.B. "Berlin" für ein Objekt im Umland wie Ludwigsfelde). Verlasse dich stärker auf Projektname, Entwickler und Adresse als auf die Stadt.

KANDIDATEN aus Propstack (mögliche Objekte):
{candidates}

Welcher Kandidat bezeichnet DASSELBE Objekt wie der Deal? Wenn kein Kandidat sicher passt, gib null zurück (lieber vorsichtig).

Antworte ausschließlich mit JSON:
{{
  "unit_id": <id des passenden Kandidaten> | null,
  "confidence": 0.0-1.0,
  "begruendung": "1 kurzer Satz"
}}
"""


def _candidate_line(u: Unit) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "title": u.title,
        "street": u.street,
        "house_number": u.house_number,
        "zip_code": u.zip_code,
        "city": u.city,
        "flaeche_qm": u.property_space_value,
        "makler": u.broker_name,
    }


def select_match(deal: Deal, candidates: list[Unit]) -> MatchResult:
    """Lässt Claude aus den Kandidaten das passende Objekt wählen.

    - kein Kandidat -> NONE (kein API-Call)
    - Claude wählt null -> NONE
    - Treffer, confidence >= Schwelle -> UNIQUE
    - Treffer, confidence < Schwelle -> AMBIGUOUS (wird zu Stufe-B-Review)
    - API-/Parsefehler -> AMBIGUOUS mit Kandidaten (kein stiller Verlust)
    """
    if not candidates:
        return MatchResult(status=MatchStatus.NONE, grund="Keine Kandidaten gefunden")

    by_id = {u.id: u for u in candidates}
    prompt = SELECT_PROMPT.format(
        objekt_name=deal.objekt_name or "-",
        ort=deal.stadt or "-",
        vermieter=deal.vermieter or "-",
        mieter=deal.mieter or "-",
        groesse=deal.groessen_hinweis or "-",
        candidates=json.dumps([_candidate_line(u) for u in candidates], ensure_ascii=False, indent=1),
    )

    try:
        response = _get_client().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _parse_extraction_json(response.content[0].text)
    except anthropic.APIError as e:
        logger.error("Claude API error bei Match-Auswahl: %s", e)
        return MatchResult(status=MatchStatus.AMBIGUOUS, kandidaten=candidates[:10],
                           grund="KI-Auswahl fehlgeschlagen (API) – manuelle Prüfung")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Match-Auswahl-Antwort nicht parsebar: %s", e)
        return MatchResult(status=MatchStatus.AMBIGUOUS, kandidaten=candidates[:10],
                           grund="KI-Auswahl nicht parsebar – manuelle Prüfung")

    unit_id = raw.get("unit_id")
    confidence = raw.get("confidence") or 0.0
    begruendung = raw.get("begruendung") or ""

    if unit_id is None:
        return MatchResult(status=MatchStatus.NONE,
                           kandidaten=candidates[:10],
                           grund=f"KI: kein passendes Objekt ({begruendung})")

    try:
        chosen = by_id.get(int(unit_id))
    except (TypeError, ValueError):
        chosen = None
    if chosen is None:
        return MatchResult(status=MatchStatus.AMBIGUOUS, kandidaten=candidates[:10],
                           grund=f"KI wählte unbekannte id {unit_id!r} – manuelle Prüfung")

    andere = [u for u in candidates if u.id != chosen.id][:9]
    if confidence < config.CONFIDENCE_THRESHOLD:
        return MatchResult(
            status=MatchStatus.AMBIGUOUS,
            units=[chosen],
            kandidaten=[chosen] + andere,
            grund=f"KI-Treffer unsicher (conf {confidence:.2f}): {chosen.adresse()} – {begruendung}",
        )
    return MatchResult(
        status=MatchStatus.UNIQUE,
        units=[chosen],
        kandidaten=[chosen] + andere,
        grund=f"KI-Zuordnung (conf {confidence:.2f}): {chosen.adresse()} – {begruendung}",
    )
