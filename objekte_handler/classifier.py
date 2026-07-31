from __future__ import annotations

import json
import logging

import anthropic
from pydantic import ValidationError

from . import config
from .models import Classification

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """Du analysierst Nachrichten aus dem internen Slack-Kanal #objekte eines Gewerbeimmobilien-Maklers (Kromeich & Partner). Dort posten Kollegen Status-Meldungen zu Objekten, die ins CRM Propstack nachgezogen werden sollen.

Klassifiziere die NACHRICHT (nicht den Kontext) in genau einen Typ:

- "status_anweisung": konkrete Anweisung zu einem bestehenden Objekt (vermietet melden, Deals absagen, Objekt aktualisieren, Bilder ablegen). Beispiele:
  "Hamburgring 48, Mönchengladbach ist vermietet – bitte Objekt inaktiv setzen, Deals absagen"
  "Viersen Aconlog – die kleine Einheit ist vermietet"
  "Update prodac Castrop – bitte Bilder ablegen und PS aktualisieren"
- "fehlt_in_ps": Hinweis, dass ein Objekt in Propstack (PS) fehlt bzw. angelegt werden muss. Beispiel:
  "Das Objekt Landau von Nvelop fehlt in Propstack"
- "flaechenupdate": Flächenupdate-/Bestandslisten-Hinweis eines Eigentümers. Beispiele:
  "Flächenupdate Hillwood 06/26", "Newsletter Panattoni 06/26"
- "ignorieren": LinkedIn-Links, Marktnews, Diskussionen, Emojis, Smalltalk

Extrahiere zusätzlich (null wenn nicht vorhanden):
- strasse: NUR der Straßenname, OHNE Hausnummer
- hausnummer
- stadt
- objekt_name: Projekt-/Eigentümername wie "Viersen Aconlog", "prodac Castrop", "Landau von Nvelop"
- eigentuemer: NUR die Firma, die das Objekt besitzt/entwickelt/vermietet – ohne Ortszusatz
  und ohne Rechtsform-Ballast. Das ist der wichtigste Schlüssel überhaupt, weil die
  Zugehörigkeit im CRM über die Eigentümer-Verknüpfung läuft und nie im Objekttitel steht.
  "Flächenupdate Mileway 07/26" -> "Mileway"
  "Viersen Aconlog – die kleine Einheit ist vermietet" -> "Aconlog"
  "Das Objekt Landau von Nvelop fehlt in Propstack" -> "Nvelop"
  "Newsletter Panattoni 06/26" -> "Panattoni"
  Nenne die Firma auch dann, wenn sie zusätzlich im objekt_name steht. null, wenn die
  Nachricht keine Eigentümerfirma nennt – rate nicht aus dem Ortsnamen.
- aktion: "vermietet" | "update" | "sonstiges" (nur bei status_anweisung)
- groessen_hinweis: "kleinste" | "groesste" | Quadratmeterzahl als String | null
  (z.B. "die kleine Einheit" -> "kleinste")
- confidence: 0.0-1.0 – wie sicher bist du bei Typ UND extrahierten Daten
- begruendung: 1 Satz

Antworte ausschließlich mit einem JSON-Objekt:
{{
  "typ": "status_anweisung" | "fehlt_in_ps" | "flaechenupdate" | "ignorieren",
  "aktion": "vermietet" | "update" | "sonstiges" | null,
  "strasse": "..." | null,
  "hausnummer": "..." | null,
  "stadt": "..." | null,
  "objekt_name": "..." | null,
  "eigentuemer": "..." | null,
  "groessen_hinweis": "..." | null,
  "confidence": 0.0,
  "begruendung": "..."
}}
{context_block}
Nachricht:
{text}
"""

CONTEXT_BLOCK = """
Thread-Kontext (nur zum Verständnis, z.B. um Adresse/Objekt zuzuordnen – klassifiziert wird ausschließlich die Nachricht unten):
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
    """```-Fences strippen, letzte {...}-Klammer extrahieren, json.loads."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    return json.loads(text)
