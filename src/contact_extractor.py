from __future__ import annotations

import base64
import json
import logging
import os

import anthropic

from .models import ContactData, EmailData, GroupCategory, GROUP_ID_MAP

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
Analysiere die folgende Email und extrahiere Kontaktdaten aus der Email-Signatur des Absenders.

Regeln:
- Extrahiere NUR Daten aus der Signatur (am Ende der Email), NICHT aus dem Email-Text selbst.
- Trenne Straße und Hausnummer immer in zwei separate Felder.
- Trenne Festnetz und Mobilnummer immer in zwei separate Felder (siehe unten).
- Wenn ein Feld nicht in der Signatur vorhanden ist, setze es auf null.
- Die Email-Adresse ist ein PFLICHTFELD – wenn keine Email erkennbar ist, verwende die Absender-Email.

Antworte ausschließlich mit einem JSON-Objekt in diesem Format:
{{
  "first_name": "string oder null",
  "last_name": "string oder null",
  "email": "string (Pflichtfeld)",
  "phone": "string oder null (NUR Festnetz: Tel/Telefon/Fon/T/Phone/Office/Durchwahl)",
  "mobile": "string oder null (NUR Mobil: Mobil/Handy/Mob/M/Cell/Mobile oder deutsche Vorwahl 015x/016x/017x)",
  "company": "string oder null",
  "position": "string oder null",
  "street": "string oder null (NUR Straßenname, OHNE Hausnummer)",
  "house_number": "string oder null (NUR die Hausnummer)",
  "zip_code": "string oder null",
  "city": "string oder null",
  "salutation": "mr wenn männliche Anrede/Person klar erkennbar (z.B. Herr), ms wenn weiblich (z.B. Frau), sonst null"
}}

Absender: {sender}
Absender-Email: {sender_email}
Betreff: {subject}

Email-Inhalt:
{body}
"""

CATEGORIZATION_PROMPT = """\
Du bist ein Experte für die Immobilien- und Logistikbranche in Deutschland.

Bestimme für den folgenden Kontakt die passende(n) Kategorie(n). Es gibt sechs Kategorien:

1. **Eigentümer** – Immobilieneigentümer, Asset Manager, Property Manager, Vermieter von Gewerbe-/Logistikflächen, Bestandshalter. Beispiele: Logicor, CTP, Prologis, Segro, VGP, Goodman, Mileway, etc.

2. **Investor** – Investmentgesellschaften, Private-Equity-Firmen, Family Offices, Fondsmanager, die in Immobilien investieren. Beispiele: Blackstone, Brookfield, CBRE Investment Management, AEW, etc.

3. **Logistiker** – Logistikunternehmen, Speditionen, Fulfillment-Dienstleister, Intralogistik-Hersteller, Supply-Chain-Unternehmen. Beispiele: Logwin, DHL, Jungheinrich, AutoStore, KNAPP, Amazon Logistics, Kühne+Nagel, etc.

4. **Makler** – Immobilienmakler, Gewerbemakler, Industriemakler, Beratungsunternehmen für Gewerbeimmobilien. Beispiele: CBRE, JLL, Cushman & Wakefield, Colliers, BNP Paribas Real Estate, Realogis, Logivest, etc.

5. **Entwickler** – Projektentwickler, die Immobilien entwickeln und bauen. Beispiele: Panattoni, Goodman Development, Aurelis, Dietz AG, Four Parx, Verdion, etc.

6. **Sonstiges** – Alle Kontakte, die NICHT eindeutig in eine der fünf obigen Kategorien passen. Dies ist der Fallback.

Regeln:
- Ein Kontakt kann MEHRERE Kategorien haben (z.B. ein Logistik-Investor oder ein Eigentümer der auch Projektentwickler ist).
- Wenn der Kontakt eindeutig in eine oder mehrere der Kategorien 1-5 passt: weise diese zu.
- Wenn der Kontakt in KEINE der Kategorien 1-5 passt: weise "Sonstiges" zu.
- Jeder Kontakt MUSS mindestens eine Kategorie erhalten.
- Nutze den Firmennamen, die Position, und den Email-Kontext für deine Entscheidung.

WICHTIG – Web-Recherche:
- Wenn dir das Unternehmen nicht eindeutig bekannt ist oder du unsicher bist, in welche Kategorie es gehört, nutze ZUERST die Websuche (web_search), um herauszufinden, was das Unternehmen macht.
- Suche z.B. nach dem Firmennamen + "Logistik" oder dem Firmennamen + "Unternehmen" um die Branche zu klären.
- Stütze deine Kategorisierung auf die Rechercheergebnisse.

Kontaktdaten:
- Name: {name}
- Firma: {company}
- Position: {position}
- Email: {email}

Email-Kontext (Betreff + Auszug):
{email_context}

Gib am Ende deiner Antwort ausschließlich ein JSON-Objekt aus (nach eventueller Web-Recherche):
{{
  "categories": ["Eigentümer" und/oder "Investor" und/oder "Logistiker" und/oder "Makler" und/oder "Entwickler" und/oder "Sonstiges"],
  "reasoning": "Kurze Begründung (inkl. Rechercheergebnis falls gesucht)"
}}
"""


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def extract_contact(email_data: EmailData) -> ContactData | None:
    client = _get_client()

    body_truncated = email_data.body[:8000] if len(email_data.body) > 8000 else email_data.body

    prompt = EXTRACTION_PROMPT.format(
        sender=email_data.sender,
        sender_email=email_data.sender_email,
        subject=email_data.subject,
        body=body_truncated,
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(text)

        contact_email = data.get("email") or email_data.sender_email
        if not contact_email:
            logger.warning("No email found for sender %s", email_data.sender)
            return None

        return ContactData(
            first_name=data.get("first_name") or None,
            last_name=data.get("last_name") or None,
            email=contact_email.lower().strip(),
            phone=data.get("phone") or None,
            mobile=data.get("mobile") or None,
            company=data.get("company") or None,
            position=data.get("position") or None,
            street=data.get("street") or None,
            house_number=data.get("house_number") or None,
            zip_code=data.get("zip_code") or None,
            city=data.get("city") or None,
            salutation=(data.get("salutation") if data.get("salutation") in ("mr", "ms") else None),
        )
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Failed to parse extraction response for %s: %s", email_data.sender_email, e)
        return None
    except anthropic.APIError as e:
        logger.error("Claude API error during extraction: %s", e)
        return None


def _extract_json_from_blocks(response) -> str:
    """Bei Web-Search liefert die API mehrere Content-Blöcke. Wir sammeln
    alle Text-Blöcke und nehmen den letzten, der ein JSON-Objekt enthält."""
    text_parts = [block.text for block in response.content if block.type == "text"]
    full_text = "\n".join(text_parts).strip()

    # JSON-Objekt aus dem Text extrahieren (letzte {...}-Klammer)
    start = full_text.rfind("{")
    end = full_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return full_text[start : end + 1]
    return full_text


def categorize_contact(
    contact: ContactData,
    email_subject: str,
    email_body_excerpt: str,
) -> list[str]:
    client = _get_client()

    name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
    email_context = f"Betreff: {email_subject}\n\n{email_body_excerpt[:2000]}"

    prompt = CATEGORIZATION_PROMPT.format(
        name=name,
        company=contact.company or "Unbekannt",
        position=contact.position or "Unbekannt",
        email=contact.email,
        email_context=email_context,
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=[
                {
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "max_uses": 1,
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )

        text = _extract_json_from_blocks(response)
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(text)
        categories = data.get("categories", [])
        reasoning = data.get("reasoning", "")

        group_ids: list[str] = []
        for cat_name in categories:
            for group_cat in GroupCategory:
                if group_cat.value.lower() == cat_name.lower():
                    group_ids.append(GROUP_ID_MAP[group_cat])
                    break

        if not group_ids:
            group_ids = [GROUP_ID_MAP[GroupCategory.SONSTIGES]]
            logger.info("Fallback 'Sonstiges' für %s – %s", contact.email, reasoning)
        else:
            logger.info("Categorized %s as %s: %s", contact.email, categories, reasoning)

        return group_ids
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Failed to parse categorization response for %s: %s", contact.email, e)
        return [GROUP_ID_MAP[GroupCategory.SONSTIGES]]
    except anthropic.APIError as e:
        logger.error("Claude API error during categorization: %s", e)
        return [GROUP_ID_MAP[GroupCategory.SONSTIGES]]


BUSINESSCARD_PROMPT = """\
Analysiere das Foto dieser Visitenkarte und extrahiere alle Kontaktdaten.

Regeln:
- Trenne Straße und Hausnummer immer in zwei separate Felder.
- Trenne Festnetz und Mobilnummer immer in zwei separate Felder (siehe unten).
- Wenn ein Feld nicht auf der Visitenkarte vorhanden ist, setze es auf null.
- Bei mehreren Personen auf einer Karte: extrahiere nur die Hauptperson.

Antworte ausschließlich mit einem JSON-Objekt in diesem Format:
{{
  "first_name": "string oder null",
  "last_name": "string oder null",
  "email": "string oder null",
  "phone": "string oder null (NUR Festnetz: Tel/Telefon/Fon/T/Phone/Office/Durchwahl)",
  "mobile": "string oder null (NUR Mobil: Mobil/Handy/Mob/M/Cell/Mobile oder deutsche Vorwahl 015x/016x/017x)",
  "company": "string oder null",
  "position": "string oder null",
  "street": "string oder null (NUR Straßenname, OHNE Hausnummer)",
  "house_number": "string oder null (NUR die Hausnummer)",
  "zip_code": "string oder null",
  "city": "string oder null",
  "salutation": "mr wenn männliche Anrede/Person klar erkennbar (z.B. Herr), ms wenn weiblich (z.B. Frau), sonst null"
}}
"""

SLACK_TEXT_PROMPT = """\
Analysiere den folgenden Text aus einer Slack-Nachricht und extrahiere Kontaktdaten.
Der Text kann eine formlose Notiz sein, eine kopierte Visitenkarte, oder eine Kontaktbeschreibung.

Regeln:
- Trenne Straße und Hausnummer immer in zwei separate Felder.
- Trenne Festnetz und Mobilnummer immer in zwei separate Felder (siehe unten).
- Wenn ein Feld nicht vorhanden ist, setze es auf null.

Antworte ausschließlich mit einem JSON-Objekt in diesem Format:
{{
  "first_name": "string oder null",
  "last_name": "string oder null",
  "email": "string oder null",
  "phone": "string oder null (NUR Festnetz: Tel/Telefon/Fon/T/Phone/Office/Durchwahl)",
  "mobile": "string oder null (NUR Mobil: Mobil/Handy/Mob/M/Cell/Mobile oder deutsche Vorwahl 015x/016x/017x)",
  "company": "string oder null",
  "position": "string oder null",
  "street": "string oder null (NUR Straßenname, OHNE Hausnummer)",
  "house_number": "string oder null (NUR die Hausnummer)",
  "zip_code": "string oder null",
  "city": "string oder null",
  "salutation": "mr wenn männliche Anrede/Person klar erkennbar (z.B. Herr), ms wenn weiblich (z.B. Frau), sonst null"
}}

Slack-Nachricht:
{text}
"""


def _parse_contact_json(text: str, source: str) -> ContactData | None:
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    start = text.rfind("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    data = json.loads(text)

    first_name = data.get("first_name") or None
    last_name = data.get("last_name") or None

    if not first_name and not last_name:
        logger.info("No name found in %s", source)
        return None

    contact_email = data.get("email") or None

    return ContactData(
        first_name=first_name,
        last_name=last_name,
        email=contact_email.lower().strip() if contact_email else "",
        phone=data.get("phone") or None,
        mobile=data.get("mobile") or None,
        company=data.get("company") or None,
        position=data.get("position") or None,
        street=data.get("street") or None,
        house_number=data.get("house_number") or None,
        zip_code=data.get("zip_code") or None,
        city=data.get("city") or None,
        salutation=(data.get("salutation") if data.get("salutation") in ("mr", "ms") else None),
    )


def extract_contact_from_image(image_data: bytes) -> ContactData | None:
    client = _get_client()
    b64 = base64.standard_b64encode(image_data).decode("utf-8")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                    },
                    {"type": "text", "text": BUSINESSCARD_PROMPT},
                ],
            }],
        )
        text = response.content[0].text.strip()
        return _parse_contact_json(text, "business card image")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Failed to parse business card extraction: %s", e)
        return None
    except anthropic.APIError as e:
        logger.error("Claude API error during business card extraction: %s", e)
        return None


def extract_contact_from_text(slack_text: str) -> ContactData | None:
    client = _get_client()
    prompt = SLACK_TEXT_PROMPT.format(text=slack_text[:4000])

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        resp_text = response.content[0].text.strip()
        return _parse_contact_json(resp_text, "slack text")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Failed to parse slack text extraction: %s", e)
        return None
    except anthropic.APIError as e:
        logger.error("Claude API error during slack text extraction: %s", e)
        return None
