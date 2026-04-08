from __future__ import annotations

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
- Wenn ein Feld nicht in der Signatur vorhanden ist, setze es auf null.
- Die Email-Adresse ist ein PFLICHTFELD – wenn keine Email erkennbar ist, verwende die Absender-Email.

Antworte ausschließlich mit einem JSON-Objekt in diesem Format:
{
  "first_name": "string oder null",
  "last_name": "string oder null",
  "email": "string (Pflichtfeld)",
  "phone": "string oder null",
  "company": "string oder null",
  "position": "string oder null",
  "street": "string oder null (NUR Straßenname, OHNE Hausnummer)",
  "house_number": "string oder null (NUR die Hausnummer)",
  "zip_code": "string oder null",
  "city": "string oder null"
}

Absender: {sender}
Absender-Email: {sender_email}
Betreff: {subject}

Email-Inhalt:
{body}
"""

CATEGORIZATION_PROMPT = """\
Du bist ein Experte für die Immobilien- und Logistikbranche in Deutschland.

Bestimme für den folgenden Kontakt die passende(n) Kategorie(n). Es gibt sechs Kategorien:

1. **Eigentümer** (ID: 507350) – Immobilieneigentümer, Asset Manager, Property Manager, Vermieter von Gewerbe-/Logistikflächen, Bestandshalter. Beispiele: Logicor, CTP, Prologis, Segro, VGP, Goodman, P3 Logistic Parks, Panattoni, etc.

2. **Investor** (ID: 507349) – Investmentgesellschaften, Private-Equity-Firmen, Family Offices, Fondsmanager, die in Immobilien investieren. Beispiele: Blackstone, Brookfield, CBRE Investment Management, AEW, etc.

3. **Logistiker** (ID: 636740) – Logistikunternehmen, Speditionen, Fulfillment-Dienstleister, Intralogistik-Hersteller, Supply-Chain-Unternehmen. Beispiele: Logwin, DHL, Jungheinrich, AutoStore, KNAPP, Amazon Logistics, Kühne+Nagel, etc.

4. **Makler** (ID: 409483) – Immobilienmakler, Gewerbemakler, Industriemakler, Beratungsunternehmen für Gewerbeimmobilien. Beispiele: CBRE, JLL, Cushman & Wakefield, Colliers, BNP Paribas Real Estate, Realogis, Logivest, etc.

5. **Produzent** (ID: 641030) – Produzierende Unternehmen, Hersteller, Industrieunternehmen, die Gewerbe-/Logistikflächen als Mieter oder Nutzer benötigen. Beispiele: Automobilhersteller, Maschinenbauer, Konsumgüterhersteller, Lebensmittelproduzenten, etc.

6. **Handel** (ID: 641031) – Handelsunternehmen, Einzelhändler, Großhändler, E-Commerce-Unternehmen, die Lager- und Logistikflächen nutzen. Beispiele: Amazon, Zalando, REWE, ALDI, Lidl, Otto, MediaMarkt, etc.

Regeln:
- Ein Kontakt kann MEHRERE Kategorien haben (z.B. ein Logistik-Investor oder ein Handelsunternehmen mit eigenen Logistikflächen).
- Wenn der Kontakt NICHT eindeutig in eine der sechs Kategorien passt: gib ein leeres Array zurück.
- Nutze den Firmennamen, die Position, und den Email-Kontext für deine Entscheidung.

Kontaktdaten:
- Name: {name}
- Firma: {company}
- Position: {position}
- Email: {email}

Email-Kontext (Betreff + Auszug):
{email_context}

Antworte ausschließlich mit einem JSON-Objekt:
{{
  "categories": ["Eigentümer" und/oder "Investor" und/oder "Logistiker" und/oder "Makler" und/oder "Produzent" und/oder "Handel"],
  "reasoning": "Kurze Begründung"
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
            model="claude-sonnet-4-20250514",
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
            company=data.get("company") or None,
            position=data.get("position") or None,
            street=data.get("street") or None,
            house_number=data.get("house_number") or None,
            zip_code=data.get("zip_code") or None,
            city=data.get("city") or None,
        )
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Failed to parse extraction response for %s: %s", email_data.sender_email, e)
        return None
    except anthropic.APIError as e:
        logger.error("Claude API error during extraction: %s", e)
        return None


def categorize_contact(
    contact: ContactData,
    email_subject: str,
    email_body_excerpt: str,
) -> list[int]:
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
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(text)
        categories = data.get("categories", [])
        reasoning = data.get("reasoning", "")

        group_ids: list[int] = []
        for cat_name in categories:
            for group_cat in GroupCategory:
                if group_cat.value.lower() == cat_name.lower():
                    group_ids.append(GROUP_ID_MAP[group_cat])
                    break

        if group_ids:
            logger.info("Categorized %s as %s: %s", contact.email, categories, reasoning)
        else:
            logger.info(
                "Kein Merkmal zugewiesen für %s – %s",
                contact.email,
                reasoning or "Unternehmen passt nicht eindeutig in eine der Kategorien",
            )

        return group_ids
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Failed to parse categorization response for %s: %s", contact.email, e)
        return []
    except anthropic.APIError as e:
        logger.error("Claude API error during categorization: %s", e)
        return []
