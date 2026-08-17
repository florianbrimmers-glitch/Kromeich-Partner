from __future__ import annotations

import logging
import time

import httpx

from . import config
from .models import Event

logger = logging.getLogger(__name__)

ASANA_BASE_URL = "https://app.asana.com/api/1.0"
MAX_ATTEMPTS = 4


def build_task(event: Event, quelle_link: str) -> tuple[str, str]:
    """Baut (Aufgaben-Name, Beschreibung) für ein Event.

    Name: '<Datum kompakt> <Event-Name>', z.B. '08./09.09.2026 Zukunftskongress
    Logistik'. Bevorzugt wird das einheitliche deutsche Kurzformat; nur falls es
    fehlt, wird auf die Originalschreibweise zurückgefallen. Die Wertungen
    'Funktion KP'/'Spannend für' kommen NICHT in die Beschreibung – die füllt ein Mensch."""
    datum = (event.datum_kompakt or event.datum or "").strip()
    name = " ".join(p for p in (datum, (event.event_name or "").strip()) if p)
    name = name or "Event (ohne Namen)"

    zeilen: list[str] = []
    if event.branche:
        zeilen.append(f"Branche: {event.branche}")
    if event.ort:
        zeilen.append(f"Ort: {event.ort}")
    if event.kosten:
        zeilen.append(f"Kosten (nur Ticket): {event.kosten}")
    if event.anmeldelink:
        zeilen.append(f"Anmeldung/Info: {event.anmeldelink}")
    if quelle_link:
        zeilen.append(f"Quelle (Slack #events): {quelle_link}")
    zeilen.append("")
    zeilen.append("(automatisch aus #events übernommen – 'Funktion KP' und 'Spannend für' bitte manuell ergänzen)")
    return name, "\n".join(zeilen)


def _request(method: str, path: str, *, json: dict | None = None, params: dict | None = None) -> httpx.Response:
    """Asana-Request mit Retry (Backoff 2**attempt) bei 429/5xx/Netzfehlern."""
    headers = {
        "Authorization": f"Bearer {config.asana_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    last_error: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            time.sleep(2**attempt)
        try:
            response = httpx.request(
                method, f"{ASANA_BASE_URL}{path}",
                headers=headers, json=json, params=params, timeout=30.0,
            )
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning("Asana %s %s: HTTP %s (Versuch %d/%d)",
                               method, path, response.status_code, attempt + 1, MAX_ATTEMPTS)
                last_error = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response)
                continue
            if response.status_code >= 400:
                logger.error("Asana %s %s fehlgeschlagen: HTTP %s – %s",
                             method, path, response.status_code, response.text)
                response.raise_for_status()
            return response
        except httpx.HTTPStatusError:
            raise
        except httpx.HTTPError as e:
            logger.warning("Asana %s %s: %s (Versuch %d/%d)", method, path, e, attempt + 1, MAX_ATTEMPTS)
            last_error = e

    raise last_error if last_error else RuntimeError(f"Asana {method} {path} fehlgeschlagen")


def list_section_tasks() -> list[dict]:
    """Namen der Aufgaben im Ziel-Abschnitt – Grundlage für den Dublettencheck.

    Gelesen wird über das PROJEKT und anschließend nach Abschnitts-Zugehörigkeit
    gefiltert: der Abschnitts-Endpunkt (/sections/:id/tasks) lieferte in der
    Praxis unvollständige Listen (einzelne Aufgaben fehlten, obwohl ihre
    memberships den Abschnitt nennen). Ein unvollständiger Bestand würde still
    zu Doppeleinträgen führen.

    Reiner GET, läuft auch unter NO_WRITE/DRY_RUN. Bei fehlendem Token/Fehler
    entscheidet der Aufrufer, wie er damit umgeht."""
    section = config.section_id()
    tasks: list[dict] = []
    gesamt = 0
    offset: str | None = None
    while True:
        params: dict = {
            "project": config.project_id(),
            "opt_fields": "name,memberships.section.gid",
            "limit": 100,
        }
        if offset:
            params["offset"] = offset
        data = _request("GET", "/tasks", params=params).json()
        for t in data.get("data", []):
            if not isinstance(t, dict) or not t.get("gid"):
                continue
            gesamt += 1
            in_section = any(
                ((m or {}).get("section") or {}).get("gid") == section
                for m in (t.get("memberships") or [])
            )
            if in_section:
                tasks.append({"gid": t["gid"], "name": t.get("name") or ""})
        next_page = data.get("next_page") or {}
        if not next_page.get("offset"):
            break
        offset = next_page["offset"]
    logger.info("%d bestehende Aufgabe(n) im Abschnitt %s (von %d im Projekt)",
                len(tasks), section, gesamt)
    return tasks


def create_event_task(name: str, notes: str, due_on: str | None = None) -> str | None:
    """Legt eine Aufgabe im Marketing-Projekt an und schiebt sie in den 'Events'-Abschnitt.

    due_on = Starttag des Events (YYYY-MM-DD); macht den Abschnitt chronologisch
    sortierbar. Gibt die Permalink-URL der Aufgabe zurück (None im NO_WRITE-Lauf)."""
    if config.no_write():
        logger.info("[NO_WRITE] Würde Asana-Aufgabe anlegen: %r (due %s) im Abschnitt %s",
                    name, due_on or "-", config.section_id())
        return None

    payload: dict = {"name": name, "notes": notes, "projects": [config.project_id()]}
    if due_on:
        payload["due_on"] = due_on

    # 1. Aufgabe im Projekt anlegen
    created = _request(
        "POST", "/tasks",
        params={"opt_fields": "permalink_url"},
        json={"data": payload},
    ).json()["data"]
    task_gid = created["gid"]

    # 2. In den Ziel-Abschnitt 'Events' einsortieren
    _request(
        "POST", f"/sections/{config.section_id()}/addTask",
        json={"data": {"task": task_gid}},
    )

    url = created.get("permalink_url") or f"https://app.asana.com/0/{config.project_id()}/{task_gid}"
    logger.info("Asana-Aufgabe angelegt: %r (%s)", name, url)
    return url
