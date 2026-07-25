from __future__ import annotations

import json
import logging
import re

import anthropic
from pydantic import ValidationError

from . import config
from .models import EventExtraction

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Du wertest einen Beitrag aus dem internen Slack-Kanal #events eines Gewerbeimmobilien-Maklers (Kromeich & Partner) aus. Dort werden weitergeleitete Veranstaltungs-Einladungen, Messe-Hinweise und Newsletter gepostet – meist als E-Mail-Inhalt.

Extrahiere ALLE konkreten Veranstaltungen (Messen, Kongresse, Netzwerk-Events, Webinare, Kundenevents) mit einem erkennbaren Termin. Gib sie als JSON-Liste zurück.

Setze ist_event=false, wenn es sich um reine Werbung, einen allgemeinen Newsletter ohne konkreten Termin, eine Grußnachricht o.Ä. handelt (dann trotzdem ein Listeneintrag mit ist_event=false).

Extrahiere je Event (null wenn nicht vorhanden):
- datum: exakt wie im Text, z.B. "04.10.2026", "14. Juli", "16./17.06" (keine Umformatierung)
- event_name: Name der Veranstaltung
- branche: thematische Einordnung, z.B. "Logistik", "Immobilien", "Einkauf", "Fashion" (kurz)
- ort: Stadt/Ort bzw. "virtuell"/"digital"
- kosten: z.B. "kostenlos", "260 Eur", "tba" – null wenn nicht genannt
- anmeldelink: Registrierungs-/Info-Link aus der Einladung, falls vorhanden
- confidence: 0.0-1.0
- begruendung: 1 kurzer Satz

Antworte ausschließlich mit einem JSON-Objekt:
{{
  "events": [
    {{
      "ist_event": true,
      "datum": "..." | null,
      "event_name": "..." | null,
      "branche": "..." | null,
      "ort": "..." | null,
      "kosten": "..." | null,
      "anmeldelink": "..." | null,
      "confidence": 0.0,
      "begruendung": "..."
    }}
  ]
}}

Wenn nichts Verwertbares enthalten ist, gib {{"events": []}} zurück.

Titel des Slack-Anhangs / der Nachricht:
{title}

Inhalt:
{content}
"""

MAX_CONTENT_CHARS = 16000


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.anthropic_api_key())


def html_to_text(raw: str) -> str:
    """Grobes HTML→Text: Skripte/Styles raus, Tags strippen, Whitespace kollabieren."""
    if not raw:
        return ""
    text = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def extract_events(title: str, content: str) -> EventExtraction | None:
    """Extrahiert alle Events aus Titel + (bereits zu Text reduziertem) Inhalt.

    None bei API-/Parse-Fehler (Retry im nächsten Lauf)."""
    prompt = EXTRACTION_PROMPT.format(
        title=(title or "")[:500],
        content=(content or "")[:MAX_CONTENT_CHARS],
    )
    try:
        response = _get_client().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _parse_extraction_json(response.content[0].text)
        return EventExtraction.model_validate(raw)
    except anthropic.APIError as e:
        logger.error("Claude API error bei Event-Extraktion: %s", e)
        return None
    except (json.JSONDecodeError, ValidationError, KeyError, IndexError) as e:
        logger.error("Extraktions-Antwort nicht parsebar: %s", e)
        return None


def _parse_extraction_json(text: str) -> dict:
    """```-Fences strippen, erste {...} bis letzte } extrahieren, json.loads."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return json.loads(text)
