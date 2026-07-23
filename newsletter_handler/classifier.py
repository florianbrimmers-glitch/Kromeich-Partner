from __future__ import annotations

import json
import logging

import anthropic
from pydantic import ValidationError

from . import config
from .models import NewsletterExtraction

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Du analysierst eine Nachricht aus dem Slack-Kanal #newsletter eines Gewerbeimmobilien-Maklers (Kromeich & Partner). Dort postet ein Bot täglich den "Logistik-Deal Radar" – eine Zusammenfassung von Logistikimmobilien-Marktnews aus Deutschland (Neubauten, Transaktionen, Vermietungen), je mit Ort, Größe, Akteuren und Link.

Zerlege die Nachricht in ALLE einzelnen Deal-Items und gib sie als JSON-Liste zurück. Ordne jedem Item genau einen deal_typ zu:

- "vermietung": eine (Anschluss-)Vermietung, ein abgeschlossener Mietvertrag, eine verfügbare oder gesuchte Fläche. Beispiele:
  "REALOGIS sichert Anschlussvermietung für CityLink-Logistikimmobilie mit rund 6.000 m² – Nutzer LAMPAG GmbH"
  "TCC und CBRE IM vermieten 10.000 m² Logistikfläche in Schönefeld an die GVS Group"
- "transaktion": An-/Verkauf, Investment, Erwerb einer Immobilie. Beispiel:
  "Realterm erwirbt 25.620 m² große Logistikimmobilie bei Hamburg"
- "neubau": Neubau-Ankündigung, Baustart, Fertigstellung, Richtfest. Beispiel:
  "Verdion errichtet 24.000 m² Logistik- und Gewerbezentrum bei Köln"
- "sonstiges": Marktnews ohne konkreten Flächen-Deal, Personalien, Smalltalk, Emojis.

Setze ist_vermietung=true GENAU DANN, wenn deal_typ == "vermietung". Reine An-/Verkaufstransaktionen und Neubauten sind KEINE Vermietung.

Extrahiere pro Deal zusätzlich (null wenn nicht vorhanden):
- strasse: NUR der Straßenname, OHNE Hausnummer (meist nicht vorhanden – dann null)
- hausnummer
- stadt: Ort/Stadt der Immobilie
- objekt_name: Projektname, Immobilienname oder die zentrale Firma (Eigentümer/Entwickler/Projekt), z.B. "CityLink Dortmund", "Logicor-Park Langenfeld"
- groessen_hinweis: Quadratmeterzahl als String oder null (z.B. "6000")
- mieter: der Mieter/Nutzer, falls genannt
- vermieter: der Vermieter/Eigentümer, falls genannt
- confidence: 0.0-1.0 – wie sicher bist du bei deal_typ UND den extrahierten Daten
- begruendung: 1 kurzer Satz

Antworte ausschließlich mit einem JSON-Objekt dieser Form:
{{
  "deals": [
    {{
      "deal_typ": "vermietung" | "transaktion" | "neubau" | "sonstiges",
      "ist_vermietung": true | false,
      "strasse": "..." | null,
      "hausnummer": "..." | null,
      "stadt": "..." | null,
      "objekt_name": "..." | null,
      "groessen_hinweis": "..." | null,
      "mieter": "..." | null,
      "vermieter": "..." | null,
      "confidence": 0.0,
      "begruendung": "..."
    }}
  ]
}}

Wenn die Nachricht keine Deal-Items enthält, gib {{"deals": []}} zurück.

Nachricht:
{text}
"""

MAX_TEXT_CHARS = 12000


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.anthropic_api_key())


def extract_deals(text: str) -> NewsletterExtraction | None:
    """Extrahiert alle Deal-Items eines Digests. None bei API-/Parse-Fehler (Retry im nächsten Lauf)."""
    prompt = config.DOMAIN_CONTEXT + "\n\n" + EXTRACTION_PROMPT.format(text=text[:MAX_TEXT_CHARS])

    try:
        response = _get_client().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _parse_extraction_json(response.content[0].text)
        return NewsletterExtraction.model_validate(raw)
    except anthropic.APIError as e:
        logger.error("Claude API error bei Extraktion: %s", e)
        return None
    except (json.JSONDecodeError, ValidationError, KeyError, IndexError) as e:
        logger.error("Extraktions-Antwort nicht parsebar: %s", e)
        return None


def _parse_extraction_json(text: str) -> dict:
    """```-Fences strippen, erste {...}-Klammer bis zur letzten extrahieren, json.loads."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    return json.loads(text)
