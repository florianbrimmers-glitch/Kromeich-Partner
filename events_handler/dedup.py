from __future__ import annotations

import json
import logging

import anthropic

from . import config
from .classifier import _get_client, _parse_extraction_json
from .models import Event

logger = logging.getLogger(__name__)

DEDUP_PROMPT = """Du prüfst, ob eine Veranstaltung in einer Event-Liste BEREITS ENTHALTEN ist.

NEUES EVENT:
- Datum: {datum}
- Name: {event_name}
- Ort: {ort}

BESTEHENDE EINTRÄGE der Liste (gid + Name):
{existing}

Ein Eintrag ist dieselbe Veranstaltung, wenn es sich inhaltlich um denselben Termin handelt – auch bei ABWEICHENDER SCHREIBWEISE. Achte darauf:
- Datumsformate variieren: „8. und 9. September 2026", „08. und 09. September", „08.-09.09", „8./9.9.2026" sind identisch.
- Namen variieren: Zusätze, Untertitel, Jahreszahlen, Bindestrich vs. Slash, Abkürzungen (z.B. „Zukunftskongress Logistik – 44. Dortmunder Gespräche" = „Zukunftskongress Logistik / 44. Dortmunder Gespräche").
- Gleiche Veranstaltungsreihe in einem ANDEREN Jahr oder an einem anderen Termin ist NICHT dieselbe Veranstaltung.
- Ein bloß ähnliches Thema genügt nicht – Termin und Veranstaltung müssen übereinstimmen.

Antworte ausschließlich mit JSON:
{{
  "duplikat_gid": "<gid des bestehenden Eintrags>" | null,
  "begruendung": "1 kurzer Satz"
}}
"""


def find_duplicate(event: Event, existing: list[dict]) -> tuple[str | None, str]:
    """Sucht per KI einen bestehenden Eintrag, der dieselbe Veranstaltung ist.

    Rückgabe: (gid des Duplikats oder None, Begründung).
    Bei fehlenden Einträgen kein API-Call. Bei API-/Parsefehler bewusst None –
    ein möglicher Doppeleintrag ist weniger schädlich als ein verlorenes Event."""
    if not existing:
        return None, "keine bestehenden Einträge"

    prompt = DEDUP_PROMPT.format(
        datum=event.datum or "-",
        event_name=event.event_name or "-",
        ort=event.ort or "-",
        existing=json.dumps(
            [{"gid": e.get("gid"), "name": e.get("name")} for e in existing],
            ensure_ascii=False, indent=1,
        ),
    )
    try:
        response = _get_client().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _parse_extraction_json(response.content[0].text)
    except anthropic.APIError as e:
        logger.error("Claude API error beim Dublettencheck: %s", e)
        return None, "Dublettencheck fehlgeschlagen (API)"
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Dublettencheck-Antwort nicht parsebar: %s", e)
        return None, "Dublettencheck nicht parsebar"

    gid = raw.get("duplikat_gid")
    begruendung = raw.get("begruendung") or ""
    if gid is None or str(gid).strip() in ("", "null", "None"):
        return None, begruendung

    gid = str(gid).strip()
    known = {str(e.get("gid")) for e in existing}
    if gid not in known:
        logger.warning("Dublettencheck nannte unbekannte gid %r – wird als kein Duplikat behandelt", gid)
        return None, f"unbekannte gid {gid} – kein Duplikat angenommen"
    return gid, begruendung
