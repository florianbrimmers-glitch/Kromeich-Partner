from __future__ import annotations

import json
import logging

import anthropic
from pydantic import ValidationError

from . import config
from .models import Classification

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """Du analysierst Nachrichten aus dem internen Slack-Kanal #personalkarussel-logistik eines Gewerbeimmobilien-Maklers (Kromeich & Partner). Dort melden Kollegen, wenn Ansprechpartner aus der Logistik-/Immobilienbranche den Arbeitgeber wechseln, damit das CRM Propstack nachgezogen wird.

Klassifiziere die NACHRICHT (nicht den Kontext) in genau einen Typ:

- "wechsel": eine oder mehrere Personen sind zu einer NEUEN, genannten Firma gewechselt. Beispiele:
  "Julia Schander von Goodman zu Aurelis gewechselt"
  "Felix Lorenz nicht mehr bei Aquila, sondern bei Centralis"
  "Tim Hamacher ist von arrow weg zu Swiss life"
  "Sarah berndt von mileway geht zum 01.05 zu citylink"
  "Moritz Kalisch und Patrick Frank sind jetzt beide Marq logistik" (zwei Wechsel)
- "abgang": eine Person hat eine Firma verlassen, das Ziel ist NICHT bekannt. Beispiele:
  "Marco Vajas ist nicht bei CTXL, aber ich weiß noch nicht, wo der hin ist"
  "Nachfolgerin von Valerie Setz, die da wohl weg geht (keine Ahnung wohin)"
- "umfirmierung": eine Firma heißt jetzt anders. Beispiel:
  "Das Unternehmen hieß erst GLP, dann Ares, jetzt Marq"
- "linkedin": die Nachricht besteht im Kern nur aus einem LinkedIn-Link (lnkd.in, linkedin.com) ohne erklärenden Text
- "ignorieren": Beitritte, Emojis, Smalltalk, reine Arbeitsanweisungen ohne neuen Wechsel ("bitte in PS aktualisieren"), Gesprächsnotizen

Bei "wechsel" und "abgang" für JEDE genannte Person einen Eintrag in "wechsel":
- vorname, nachname: wie geschrieben, Groß-/Kleinschreibung korrigieren ("sarah berndt" -> "Sarah", "Berndt")
- alte_firma: bisheriger Arbeitgeber (null wenn nicht genannt)
- neue_firma: neuer Arbeitgeber (null bei "abgang")
- neue_position: nur wenn ausdrücklich genannt
- ab_datum: nur wenn genannt, so wie geschrieben
Erfinde keine Firmen und keine Namen. Slack-Erwähnungen wie <@U123|Oguzhan Sahin> sind Kollegen, KEINE wechselnden Personen.

confidence: 0.0-1.0 – wie sicher bist du bei Typ UND Personen/Firmen
begruendung: 1 Satz

Antworte ausschließlich mit einem JSON-Objekt:
{{
  "typ": "wechsel" | "abgang" | "umfirmierung" | "linkedin" | "ignorieren",
  "wechsel": [
    {{"vorname": "...", "nachname": "...", "alte_firma": "..." | null, "neue_firma": "..." | null,
      "neue_position": "..." | null, "ab_datum": "..." | null}}
  ],
  "confidence": 0.0,
  "begruendung": "..."
}}
{context_block}
Nachricht:
{text}
"""

CONTEXT_BLOCK = """
Thread-Kontext (nur zum Verständnis, z.B. auf welche Person sich eine Antwort bezieht – klassifiziert wird ausschließlich die Nachricht unten):
{context}
"""

MAX_TEXT_CHARS = 4000
MAX_CONTEXT_CHARS = 500


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.anthropic_api_key())


def build_thread_context(parent_text: str, prior_replies: list[str]) -> str:
    """Parent + max. 5 vorangehende Replies, je auf 500 Zeichen gekürzt."""
    parts = [f"Ursprungsnachricht: {parent_text[:MAX_CONTEXT_CHARS]}"]
    for reply in prior_replies[-5:]:
        parts.append(f"Antwort: {reply[:MAX_CONTEXT_CHARS]}")
    return "\n".join(parts)


def classify_message(text: str, thread_context: str | None = None) -> Classification | None:
    """Klassifiziert eine Nachricht. None bei API-/Parse-Fehler (Retry im nächsten Lauf)."""
    context_block = CONTEXT_BLOCK.format(context=thread_context) if thread_context else ""
    prompt = CLASSIFICATION_PROMPT.format(context_block=context_block, text=text[:MAX_TEXT_CHARS])

    try:
        response = _get_client().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _parse_classification_json(response.content[0].text)
        return Classification.model_validate(raw)
    except anthropic.APIError as e:
        logger.error("Claude API error bei Klassifikation: %s", e)
        return None
    except (json.JSONDecodeError, ValidationError, KeyError, IndexError) as e:
        logger.error("Klassifikations-Antwort nicht parsebar: %s", e)
        return None


def _parse_classification_json(text: str) -> dict:
    """```-Fences strippen, erste { bis letzte } extrahieren, json.loads."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    return json.loads(text)
