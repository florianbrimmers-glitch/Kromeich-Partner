from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import date

import httpx

from .models import ContactData

logger = logging.getLogger(__name__)

PROPSTACK_BASE_URL = "https://api.propstack.de/v1"
PROPSTACK_BASE_URL_V2 = "https://api.propstack.de/v2"

try:
    import gender_guesser.detector as _gender
    _gender_detector = _gender.Detector(case_sensitive=False)
except Exception:  # Bibliothek fehlt -> Anrede-Fallback wird einfach übersprungen
    _gender_detector = None


def _derive_salutation(first_name: str | None) -> str | None:
    """Leitet 'mr'/'ms' aus dem Vornamen ab – nur bei EINDEUTIGEM Geschlecht.
    Unklare/uni-sex/internationale Namen -> None (Anrede bleibt leer, kein Raten)."""
    if not first_name or _gender_detector is None:
        return None
    token = re.split(r"[ \-]", first_name.strip())[0]
    if not token:
        return None
    guess = _gender_detector.get_gender(token)
    return {"male": "mr", "female": "ms"}.get(guess)


def _norm_name(name: str | None) -> str:
    """Vergleichsform für Firmennamen: nur Buchstaben und Ziffern zählen
    ("L.I.T. AG" == "LIT AG", "GmbH & Co.KG" == "GmbH & Co. KG")."""
    return re.sub(r"[^0-9a-zäöüß]", "", (name or "").lower())


def _company_display_names(record: dict) -> set[str]:
    """Alle Namensformen, unter denen ein Firmen-Datensatz auftauchen kann.
    Altlasten mit last_name == company werden als "X (X)" angezeigt."""
    names = {_norm_name(record.get("name")), _norm_name(record.get("company"))}
    m = re.fullmatch(r"(.+) \((\1)\)", (record.get("name") or "").strip())
    if m:
        names.add(_norm_name(m.group(1)))
    names.discard("")
    return names


_LEGAL_FORMS = re.compile(
    r"\b(gmbh|co|kg|ag|se|mbh|ug|haftungsbeschrankt|ohg|gbr|e ?k|kgaa|inc|ltd|llc|bv|b v|nv|sa|sarl|plc)\b"
)


def _loose_words(name: str | None) -> str:
    """Firmenname ohne Rechtsform, Akzente und Satzzeichen, Wörter durch Leerzeichen
    getrennt ("Goodman Germany GmbH & Co. KG" -> "goodman germany").
    Gleiche Regel wie im Propstack-Connector (propstack-mcp, normalizeCompany)."""
    text = unicodedata.normalize("NFKD", (name or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).replace("ß", "ss")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"\s+", " ", _LEGAL_FORMS.sub(" ", text)).strip()


def _company_search_terms(name: str) -> list[str]:
    """Suchbegriffe für die Firmensuche. Die Propstack-Suche verlangt jedes Wort der
    Eingabe: "Goodman Germany AG" findet "Goodman Germany GmbH" nicht. Deshalb
    zusätzlich ohne Rechtsform und – damit auch ein kürzer benannter Datensatz
    ("Goodman") auffällt – mit dem ersten Wort allein."""
    full = re.sub(r"\s+", " ", name.strip())
    core = " ".join(w for w in full.split(" ") if _loose_words(w))
    first = core.split(" ")[0] if core else ""
    terms: list[str] = []
    for term in (full, core, first if " " in core and len(_loose_words(first)) >= 4 else ""):
        if term and term.lower() not in (t.lower() for t in terms):
            terms.append(term)
    return terms


def _is_company_row(record: dict) -> bool:
    """Echter Firmen-Datensatz? Personen, die fälschlich als Firma markiert sind,
    haben einen Vornamen."""
    return bool(record.get("is_company")) and not record.get("first_name")


def _match_companies(company_name: str, records: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Teilt Suchtreffer ein in (exakt, gleich bis auf Rechtsform, nur ähnlich).

    exakt:    gleicher Name, nur Satz-/Leerzeichen weichen ab ("L.I.T. AG" = "LIT AG")
    gleich:   gleicher Name ohne Rechtsform ("Goodman Germany AG" = "Goodman Germany GmbH")
    ähnlich:  Name ist nur länger oder kürzer ("Goodman" / "Goodman Germany GmbH")
    """
    strict = _norm_name(company_name)
    loose = _loose_words(company_name)
    exact, same, similar = [], [], []
    seen: set = set()
    for rec in records:
        if not _is_company_row(rec) or rec.get("id") is None or rec.get("id") in seen:
            continue
        seen.add(rec.get("id"))
        raw_names = [rec.get("company"), rec.get("name")]
        m = re.fullmatch(r"(.+) \((\1)\)", (rec.get("name") or "").strip())
        if m:
            raw_names.append(m.group(1))
        looses = {_loose_words(n) for n in raw_names} - {""}
        if strict in _company_display_names(rec):
            exact.append(rec)
        elif loose and any(o.replace(" ", "") == loose.replace(" ", "") for o in looses):
            same.append(rec)
        elif loose and any(o.startswith(loose + " ") or loose.startswith(o + " ") for o in looses):
            similar.append(rec)
    return exact, same, similar


def _api_key() -> str:
    return os.environ["PROPSTACK_API_KEY"]


def _api_key_v2() -> str | None:
    return os.environ.get("PROPSTACK_API_V2_CONTACTS")


def check_duplicate(email: str) -> bool | None:
    """Prüft, ob ein Kontakt mit dieser Email bereits existiert.
    Gibt None zurück, wenn die Prüfung fehlschlägt (damit kein Duplikat angelegt wird)."""
    try:
        response = httpx.get(
            f"{PROPSTACK_BASE_URL}/contacts",
            params={"api_key": _api_key(), "email": email},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        exists = isinstance(data, list) and len(data) > 0
        if exists:
            logger.info("Propstack duplicate found for %s", email)
        return exists
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Propstack duplicate check failed for %s: %s", email, e)
        return None


def check_duplicate_by_name(first_name: str, last_name: str) -> bool | None:
    """Duplikat-Prüfung über Vor- und Nachname (für Kontakte ohne Email, z.B. Visitenkarten).
    Gibt None zurück, wenn die Prüfung fehlschlägt."""
    try:
        response = httpx.get(
            f"{PROPSTACK_BASE_URL}/contacts",
            params={"api_key": _api_key(), "q": f"{first_name} {last_name}", "per": 25},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            return False
        target_first = first_name.strip().lower()
        target_last = last_name.strip().lower()
        # Kein is_company-Filter: es gibt Personen, die fälschlich als Firma
        # markiert sind ("Max Muster (Firma GmbH)"). Echte Firmen-Datensätze
        # haben keinen Vornamen und matchen hier ohnehin nicht.
        for c in data:
            if (
                (c.get("first_name") or "").strip().lower() == target_first
                and (c.get("last_name") or "").strip().lower() == target_last
            ):
                logger.info("Propstack duplicate (name match) found for %s %s", first_name, last_name)
                return True
        return False
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Propstack name duplicate check failed for %s %s: %s", first_name, last_name, e)
        return None


def _has_legal_form(name: str | None) -> bool:
    text = re.sub(r"[^a-z0-9]+", " ", (name or "").lower())
    return bool(_LEGAL_FORMS.search(text))


def _is_short_form_of(company_name: str, record: dict) -> bool:
    """Ist der kürzere der beiden Namen eine Kurzform ohne Rechtsform?
    ("Goodman" zu "Goodman Germany GmbH": ja; "L.I.T. AG" zu "L.I.T. Speditions GmbH": nein)"""
    other = record.get("company") or record.get("name")
    shorter = company_name if len(_loose_words(company_name)) < len(_loose_words(other)) else other
    return not _has_legal_form(shorter)


def find_company(company_name: str) -> int | None:
    """Sucht einen bestehenden Firmen-Datensatz (is_company=true) anhand des Namens.

    Dieselbe Firma wird auch mit anderer Rechtsform oder Schreibweise wiedererkannt
    und verwendet.

    Nur ähnlich benannte Firma ("Goodman" / "Goodman Germany GmbH"), Entscheidung
    vom 12.11.2026: Sie wird verwendet, wenn es genau eine gibt und der kürzere
    der beiden Namen eine Kurzform ohne Rechtsform ist. Trägt der kürzere Name
    eine Rechtsform ("L.I.T. AG" / "L.I.T. Speditions GmbH"), sind es zwei
    Firmen – dann wird wie bisher neu angelegt."""
    records: list[dict] = []
    try:
        for term in _company_search_terms(company_name):
            response = httpx.get(
                f"{PROPSTACK_BASE_URL}/contacts",
                params={"api_key": _api_key(), "q": term, "per": 50},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                records.extend(data)
    except (httpx.HTTPError, ValueError) as e:
        # Unverändert zu vorher: Bei einem Suchfehler gilt die Firma als nicht gefunden.
        logger.error("Propstack company search failed for '%s': %s", company_name, e)
        return None

    exact, same, similar = _match_companies(company_name, records)
    for label, hits in (("gleicher Name", exact), ("gleicher Name, andere Rechtsform/Schreibweise", same)):
        if hits:
            # Bei mehreren Treffern den ältesten Datensatz nehmen (kleinste ID)
            hit = min(hits, key=lambda c: c.get("id"))
            if len(hits) > 1:
                logger.warning("Firma '%s' mehrfach vorhanden (%s): ids=%s – verwende %s",
                               company_name, label, sorted(c.get("id") for c in hits), hit.get("id"))
            logger.info("Firma gefunden (%s): %s -> %s (id=%s)", label, company_name, hit.get("name"), hit.get("id"))
            return hit.get("id")
    if similar:
        listing = ", ".join(f"{c.get('name')} ({c.get('id')})" for c in similar[:5])
        if len(similar) == 1 and _is_short_form_of(company_name, similar[0]):
            logger.warning("Firma '%s' einer ähnlich benannten Firma zugeordnet: %s", company_name, listing)
            return similar[0].get("id")
        logger.warning("Ähnlich benannte Firma vorhanden für '%s': %s – wird nicht verwendet",
                       company_name, listing)
    logger.info("Keine bestehende Firma gefunden für: %s", company_name)
    return None


def create_company(contact: ContactData) -> int | None:
    """Legt eine Firma an (V1 POST + V2 PUT commercial:true). Gibt die ID zurück."""
    client_data: dict = {"last_name": contact.company}
    if contact.street:
        client_data["office_street"] = contact.street
    if contact.house_number:
        client_data["office_house_number"] = contact.house_number
    if contact.zip_code:
        client_data["office_zip_code"] = contact.zip_code
    if contact.city:
        client_data["office_city"] = contact.city
    if contact.country:
        client_data["office_country"] = contact.country
    client_data["description"] = f"KI-Scan (GitHub Actions) vom {date.today().isoformat()} – Firma automatisch angelegt"

    try:
        response = httpx.post(
            f"{PROPSTACK_BASE_URL}/contacts",
            params={"api_key": _api_key()},
            json={"client": client_data},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=30.0,
        )
        response.raise_for_status()
        company_id = response.json().get("id")
        if not company_id:
            return None

        v2_key = _api_key_v2()
        if v2_key:
            # last_name wieder leeren: bleibt er stehen, zeigt Propstack die Firma
            # als "X (X)" an und find_company() findet sie nicht mehr -> Dubletten.
            v2_resp = httpx.put(
                f"{PROPSTACK_BASE_URL_V2}/clients/{company_id}",
                headers={"X-Api-Key": v2_key, "Content-Type": "application/json"},
                json={"commercial": True, "company": contact.company, "last_name": None},
                timeout=30.0,
            )
            if v2_resp.status_code == 200:
                logger.info("Firma angelegt: %s (id=%s, commercial=true)", contact.company, company_id)
            else:
                logger.warning("Firma angelegt aber commercial nicht gesetzt: %s (%s)", contact.company, v2_resp.status_code)
        else:
            logger.warning("Firma angelegt ohne commercial (V2-Key fehlt): %s", contact.company)

        return company_id
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Propstack create company failed for '%s': %s", contact.company, e)
        return None


def find_or_create_company(contact: ContactData) -> int | None:
    """Sucht die Firma oder legt sie neu an. Gibt die Firmen-ID zurück."""
    if not contact.company:
        return None
    company_id = find_company(contact.company)
    if company_id:
        return company_id
    return create_company(contact)


def link_contact_to_company(person_id: int, company_id: int) -> bool:
    """Verknüpft eine Person mit ihrer Firma (associate) über die V2-API.

    `name` beschreibt client_id und wird am ANDEREN Kontakt angezeigt: Die Zeile
    der Person heißt "Mitarbeiter" und erscheint an der Firma. Die Gegenzeile
    ("Firma", erscheint an der Person) ergänzt Propstack selbst.

    Am 12.11.2026 wurde das irrtümlich auf "Firma" umgestellt; danach stand am
    Kontakt die Firma als "Mitarbeiter" (in der Propstack-Oberfläche geprüft am
    13.11.2026). Nicht wieder umdrehen, ohne in der Oberfläche nachzusehen."""
    v2_key = _api_key_v2()
    if not v2_key:
        logger.warning("PROPSTACK_API_V2_CONTACTS not set, skipping company linking")
        return False
    try:
        response = httpx.post(
            f"{PROPSTACK_BASE_URL_V2}/relationships",
            headers={"X-Api-Key": v2_key, "Content-Type": "application/json"},
            json={
                "internal_name": "associate",
                "name": "Mitarbeiter",
                "client_id": person_id,
                "related_client_id": company_id,
            },
            timeout=30.0,
        )
        if response.status_code in (200, 201, 204):
            logger.info("Person %s mit Firma %s verknüpft (Mitarbeiter)", person_id, company_id)
            return True
        if response.status_code == 422:
            logger.info("Person %s bereits mit Firma %s verknüpft", person_id, company_id)
            return True
        logger.error(
            "Verknüpfung fehlgeschlagen (%s): %s", response.status_code, response.text
        )
        return False
    except httpx.HTTPError as e:
        logger.error("Verknüpfung Person %s -> Firma %s fehlgeschlagen: %s", person_id, company_id, e)
        return False


def create_contact(
    contact: ContactData,
    group_ids: list[str] | None = None,
) -> dict | None:
    client_data: dict = {}

    if contact.first_name:
        client_data["first_name"] = contact.first_name
    if contact.last_name:
        client_data["last_name"] = contact.last_name

    if contact.email:
        client_data["email"] = contact.email

    if contact.phone:
        client_data["office_phone"] = contact.phone
    # Mobilnummern gehören in office_cell – ein Feld "mobile" kennt die
    # Propstack-API nicht, sie verwirft es ohne Fehlermeldung (HTTP 200).
    if contact.mobile:
        client_data["office_cell"] = contact.mobile
    if contact.company:
        client_data["company"] = contact.company
    if contact.position:
        client_data["position"] = contact.position
    if contact.street:
        client_data["office_street"] = contact.street
    if contact.house_number:
        client_data["office_house_number"] = contact.house_number
    if contact.zip_code:
        client_data["office_zip_code"] = contact.zip_code
    if contact.city:
        client_data["office_city"] = contact.city
    if contact.country:
        client_data["office_country"] = contact.country

    # Anrede: explizit aus der Signatur/Karte, sonst eindeutiger Namens-Fallback
    salutation = contact.salutation or _derive_salutation(contact.first_name)
    if salutation:
        client_data["salutation"] = salutation

    if group_ids:
        client_data["mailchimp_interest_ids"] = group_ids

    client_data["description"] = f"KI-Scan (GitHub Actions) vom {date.today().isoformat()} aus Email-Signatur"

    payload = {"client": client_data}

    try:
        response = httpx.post(
            f"{PROPSTACK_BASE_URL}/contacts",
            params={"api_key": _api_key()},
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
        name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
        logger.info("Created contact in Propstack: %s (%s)", name, contact.email)
        return result
    except httpx.HTTPStatusError as e:
        logger.error(
            "Propstack create contact failed for %s: %s - %s",
            contact.email,
            e.response.status_code,
            e.response.text,
        )
        return None
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Propstack create contact failed for %s: %s", contact.email, e)
        return None
