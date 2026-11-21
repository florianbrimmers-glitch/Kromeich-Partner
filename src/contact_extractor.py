from __future__ import annotations

import base64
import json
import logging
import os

import anthropic

from . import problems
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
    # Das SDK wartet sonst bis zu 10 Minuten je Versuch – bei 90 Minuten Job-Timeout
    # reichen wenige hängende Aufrufe, um den Lauf ohne Zusammenfassung abzubrechen.
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=120.0, max_retries=2)


class KeinJson(ValueError):
    """Die Antwort enthält gar kein JSON-Objekt (z. B. „Die Mail hat keine Signatur.“).
    Das ist kein Fehler des Laufs, sondern „kein Kontakt“."""


def _json_object(text: str) -> dict:
    """Das JSON-Objekt aus einer Modellantwort lesen – auch wenn Text davor oder danach
    steht oder ein Zeilenumbruch in einem Wert (strict=False). Am 19.11.2026 scheiterten
    zwei von 21 Extraktionen an „Expecting value: line 1 column 1“; die Mails fielen als
    „kein Kontakt“ weg."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip() if "\n" in text else text.strip("`")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise KeinJson(text[:80])
    data = json.loads(text[start : end + 1], strict=False)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("Antwort ist kein JSON-Objekt", text, 0)
    return data


def _text_or_none(value) -> str | None:
    """Feldwert als Text. Das Modell liefert gelegentlich eine Zahl (PLZ, Hausnummer);
    ohne Umwandlung verwirft pydantic den ganzen Kontakt."""
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    text = str(value).strip()
    return text or None


def extract_contact(email_data: EmailData) -> ContactData | None:
    """Kontakt aus der Signatur. None = die Mail enthält keinen verwertbaren Kontakt.
    Fehler der Claude-API werden NICHT geschluckt (früher: „kein Kontakt“, Lauf grün) –
    der Aufrufer zählt sie als Fehler."""
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

        data = _json_object(response.content[0].text)

        contact_email = _text_or_none(data.get("email")) or email_data.sender_email
        if not contact_email:
            logger.warning("No email found for sender %s", email_data.sender)
            return None

        return ContactData(
            first_name=_text_or_none(data.get("first_name")),
            last_name=_text_or_none(data.get("last_name")),
            email=contact_email.lower().strip(),
            phone=_text_or_none(data.get("phone")),
            mobile=_text_or_none(data.get("mobile")),
            company=_text_or_none(data.get("company")),
            position=_text_or_none(data.get("position")),
            street=_text_or_none(data.get("street")),
            house_number=_text_or_none(data.get("house_number")),
            zip_code=_text_or_none(data.get("zip_code")),
            city=_text_or_none(data.get("city")),
            salutation=(data.get("salutation") if data.get("salutation") in ("mr", "ms") else None),
        )
    except KeinJson as e:
        logger.warning("Kein JSON in der Antwort für %s – als „kein Kontakt“ gewertet: %s", email_data.sender_email, e)
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        problems.melde("Antwort der KI nicht lesbar (Signatur)", str(e)[:80])
        return None


def _extract_json_from_blocks(response) -> str:
    """Bei Web-Search liefert die API mehrere Content-Blöcke. Wir sammeln
    alle Text-Blöcke und nehmen den letzten, der ein JSON-Objekt enthält."""
    text_parts = [block.text for block in response.content if block.type == "text"]
    # Ohne Trenner zusammensetzen: Mit Websuche teilt die API den Text an Zitatgrenzen
    # in mehrere Blöcke. Ein eingefügter Zeilenumbruch mitten in einem JSON-Wert machte
    # die Antwort unlesbar – die Kategorie fiel dann still auf „Sonstiges“.
    full_text = "".join(text_parts).strip()

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

        data = _json_object(_extract_json_from_blocks(response))
        categories = data.get("categories") or []
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
    except (KeinJson, json.JSONDecodeError, KeyError, IndexError) as e:
        # Der Kontakt wird trotzdem angelegt (Merkmal „Sonstiges“) – aber nicht unbemerkt.
        problems.melde("Kategorie nicht bestimmbar – „Sonstiges“ gesetzt", f"Antwort nicht lesbar: {str(e)[:60]}")
        return [GROUP_ID_MAP[GroupCategory.SONSTIGES]]
    except anthropic.APIError as e:
        problems.melde("Kategorie nicht bestimmbar – „Sonstiges“ gesetzt", f"Claude-API: {type(e).__name__}")
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
Stehen mehrere Personen in der Nachricht, antworte mit einer JSON-Liste aus solchen Objekten, eines je Person.

Slack-Nachricht:
{text}
"""


def _json_objekte(text: str) -> list[dict]:
    """Alle Kontakt-Objekte aus einer Modellantwort: ein Objekt, eine Liste von Objekten
    oder mehrere Objekte hintereinander. Text davor oder danach stört nicht.

    Am 21.11.2026 stand eine Slack-Nachricht mit zwei Personen im Kanal; die KI antwortete
    mit zwei Objekten nacheinander, _json_object scheiterte an „Extra data“ und der Lauf
    wurde rot – beide Kontakte wären verloren gewesen."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip() if "\n" in text else text.strip("`")
    anfaenge = [p for p in (text.find("{"), text.find("[")) if p != -1]
    if not anfaenge:
        raise KeinJson(text[:80])
    leser = json.JSONDecoder(strict=False)
    objekte: list[dict] = []
    stelle = min(anfaenge)
    while stelle < len(text) and text[stelle] in "{[":
        wert, stelle = leser.raw_decode(text, stelle)
        werte = wert if isinstance(wert, list) else [wert]
        objekte.extend(w for w in werte if isinstance(w, dict))
        while stelle < len(text) and text[stelle] in " \t\r\n,":
            stelle += 1
    if not objekte:
        raise json.JSONDecodeError("Antwort enthält kein JSON-Objekt", text, 0)
    return objekte


def _parse_contact_json(text: str, source: str) -> ContactData | None:
    return _kontakt_aus(_json_object(text), source)


def _kontakt_aus(data: dict, source: str) -> ContactData | None:
    first_name = _text_or_none(data.get("first_name"))
    last_name = _text_or_none(data.get("last_name"))

    if not first_name and not last_name:
        logger.info("No name found in %s", source)
        return None

    contact_email = _text_or_none(data.get("email"))

    return ContactData(
        first_name=first_name,
        last_name=last_name,
        email=contact_email.lower().strip() if contact_email else "",
        phone=_text_or_none(data.get("phone")),
        mobile=_text_or_none(data.get("mobile")),
        company=_text_or_none(data.get("company")),
        position=_text_or_none(data.get("position")),
        street=_text_or_none(data.get("street")),
        house_number=_text_or_none(data.get("house_number")),
        zip_code=_text_or_none(data.get("zip_code")),
        city=_text_or_none(data.get("city")),
        salutation=(data.get("salutation") if data.get("salutation") in ("mr", "ms") else None),
    )


# Bildformate, die die Claude-API annimmt. Slack liefert auch HEIC (iPhone) u. a.
SUPPORTED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")


def extract_contact_from_image(image_data: bytes, media_type: str = "image/jpeg") -> ContactData | None:
    """Kontakt von einem Visitenkartenfoto. None = kein Name erkennbar.
    Fehler der Claude-API werden nicht geschluckt – der Aufrufer zählt sie als Fehler."""
    if media_type == "image/jpg":
        media_type = "image/jpeg"
    if media_type not in SUPPORTED_IMAGE_TYPES:
        # Früher ging jedes Bild als image/jpeg an die API; ein PNG oder HEIC wurde
        # abgelehnt und die Karte zählte still als „kein Kontakt“.
        problems.melde("Visitenkarte nicht lesbar", f"Bildformat {media_type} wird nicht unterstützt – bitte als JPG oder PNG posten")
        return None

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
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": BUSINESSCARD_PROMPT},
                ],
            }],
        )
        return _parse_contact_json(response.content[0].text, "business card image")
    except KeinJson as e:
        logger.warning("Kein JSON in der Antwort (Visitenkarte) – als „kein Kontakt“ gewertet: %s", e)
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        problems.melde("Antwort der KI nicht lesbar (Visitenkarte)", str(e)[:80])
        return None


def extract_contacts_from_text(slack_text: str) -> list[ContactData]:
    """Kontakte aus einer Slack-Nachricht – eine Nachricht kann mehrere Personen nennen.
    Leere Liste = kein Kontakt erkennbar."""
    client = _get_client()
    prompt = SLACK_TEXT_PROMPT.format(text=slack_text[:4000])

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        kontakte = [_kontakt_aus(daten, "slack text") for daten in _json_objekte(response.content[0].text)]
        return [k for k in kontakte if k]
    except KeinJson as e:
        logger.warning("Kein JSON in der Antwort (Slack-Text) – als „kein Kontakt“ gewertet: %s", e)
        return []
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        problems.melde("Antwort der KI nicht lesbar (Slack-Text)", str(e)[:80])
        return []
