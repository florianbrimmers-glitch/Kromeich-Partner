from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import httpx

from . import config
from .models import NewUnit, ProjectInfo, PruefTask

logger = logging.getLogger(__name__)

PROPSTACK_BASE_URL = "https://api.propstack.de/v1"

MAX_ATTEMPTS = 4
PAGE_SIZE = 200
PAGE_PAUSE_SECONDS = 0.3
# Reißleine gegen Endlosschleifen, falls der Server Paginierung ignoriert.
MAX_PAGES = 40


def _request(method: str, path: str, *, key: str, params: dict | None = None) -> httpx.Response:
    """Read-only-Request mit Retry (Backoff 2**attempt) bei 429/5xx/Netzfehlern.

    Andere 4xx werden sofort mit Status+Body geloggt und geraist."""
    headers = {"X-API-KEY": key, "Accept": "application/json"}
    last_error: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            time.sleep(2**attempt)
        try:
            response = httpx.request(
                method,
                f"{PROPSTACK_BASE_URL}{path}",
                headers=headers,
                params=params,
                timeout=60.0,
            )
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "Propstack %s %s: HTTP %s (Versuch %d/%d)",
                    method, path, response.status_code, attempt + 1, MAX_ATTEMPTS,
                )
                last_error = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response
                )
                continue
            if response.status_code >= 400:
                logger.error(
                    "Propstack %s %s fehlgeschlagen: HTTP %s – %s",
                    method, path, response.status_code, response.text,
                )
                response.raise_for_status()
            return response
        except httpx.HTTPStatusError:
            raise
        except httpx.HTTPError as e:
            logger.warning("Propstack %s %s: %s (Versuch %d/%d)", method, path, e, attempt + 1, MAX_ATTEMPTS)
            last_error = e

    raise last_error if last_error else RuntimeError(f"Propstack {method} {path} fehlgeschlagen")


def _scalar(value):
    """Propstack liefert manche Felder als Custom-Field-Objekt {"label":..., "value":...}.
    Diese auf den reinen Wert reduzieren; Skalare unverändert durchreichen."""
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _rows(payload) -> list[dict]:
    """Antwort ist je nach Endpunkt eine nackte Liste oder {"data": [...]}."""
    raw = payload if isinstance(payload, list) else payload.get("data", [])
    return [r for r in raw if isinstance(r, dict) and r.get("id")]


def _float(value) -> float | None:
    value = _scalar(value)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_unit(raw: dict) -> NewUnit:
    return NewUnit(
        id=raw["id"],
        title=_scalar(raw.get("title")),
        name=_scalar(raw.get("name")),
        address=_scalar(raw.get("address")),
        city=_scalar(raw.get("city")),
        property_space_value=_float(raw.get("property_space_value")),
        marketing_type=_scalar(raw.get("marketing_type")),
        project_id=_scalar(raw.get("project_id")),
        created_at=_scalar(raw.get("created_at")),
    )


def _to_project(raw: dict) -> ProjectInfo:
    return ProjectInfo(
        id=raw["id"],
        title=_scalar(raw.get("title")),
        name=_scalar(raw.get("name")),
        address=_scalar(raw.get("address")),
    )


def _to_task(raw: dict) -> PruefTask:
    def names(key: str) -> list[str]:
        value = raw.get(key) or []
        return [str(v) for v in value if v] if isinstance(value, list) else []

    return PruefTask(
        id=raw["id"],
        title=_scalar(raw.get("title")),
        done=_scalar(raw.get("done")),
        broker_id=_scalar(raw.get("broker_id")),
        original_created_at=_scalar(raw.get("original_created_at")),
        updated_at=_scalar(raw.get("updated_at")),
        property_names=names("property_names"),
        project_names=names("project_names"),
    )


def _paginate(path: str, *, key: str, params: dict):
    """Seitenweise lesen, bis eine Seite leer oder kürzer als PAGE_SIZE ist."""
    for page in range(1, MAX_PAGES + 1):
        response = _request("GET", path, key=key, params={**params, "per": PAGE_SIZE, "page": page})
        rows = _rows(response.json())
        if not rows:
            return
        yield from rows
        if len(rows) < PAGE_SIZE:
            return
        time.sleep(PAGE_PAUSE_SECONDS)
    logger.warning("Propstack %s: Seitenlimit %d erreicht – Ergebnis evtl. unvollständig", path, MAX_PAGES)


def fetch_new_units(since: datetime, until: datetime) -> list[NewUnit]:
    """GET /units – im Fenster angelegte Einheiten.

    created_at_from/created_at_to wirken serverseitig (verifiziert: 2201 -> 31 -> 21),
    aber nur tagesgenau und mit undokumentiertem Zeitzonenverhalten. Deshalb wird das
    Serverfenster um je einen Tag geweitet und der exakte Schnitt clientseitig gezogen.
    expand=1 ist zwingend, sonst ist created_at im Payload null."""
    params = {
        "expand": 1,
        "created_at_from": (since - timedelta(days=1)).strftime("%Y-%m-%d"),
        "created_at_to": (until + timedelta(days=1)).strftime("%Y-%m-%d"),
    }
    units = [_to_unit(r) for r in _paginate("/units", key=config.propstack_key_objekte(), params=params)]
    im_fenster = [u for u in units if u.created_at and since <= _parse(u.created_at) < until]
    logger.info(
        "Propstack: %d Einheiten im geweiteten Serverfenster, %d davon im Berichtsfenster",
        len(units), len(im_fenster),
    )
    return sorted(im_fenster, key=lambda u: u.created_at or "", reverse=True)


def fetch_projects_index() -> dict[int, ProjectInfo]:
    """GET /projects – alle Projekte einmal als Index.

    Nötig, weil der Unit-Payload das Feld `project` selbst mit expand=1 nicht füllt.
    Ein Komplettabruf (rund 350 Projekte = 2 Seiten) ist billiger als ein Einzel-GET
    pro Projekt."""
    projects = {
        p.id: p
        for p in (_to_project(r) for r in _paginate("/projects", key=config.propstack_key_objekte(), params={}))
    }
    logger.info("Propstack: %d Projekte indiziert", len(projects))
    return projects


def earliest_unit_created_at(project_id: int) -> datetime | None:
    """Frühestes created_at aller Einheiten eines Projekts – datiert das Projekt.

    Propstack liefert für Projekte selbst keinerlei Zeitstempel (verifiziert für die
    Liste und für GET /projects/:id), sort_by=created_at auf /units funktioniert aber."""
    response = _request(
        "GET", "/units",
        key=config.propstack_key_objekte(),
        params={"project_id": project_id, "expand": 1, "sort_by": "created_at", "order": "asc", "per": 1},
    )
    rows = _rows(response.json())
    if not rows:
        return None
    created_at = _scalar(rows[0].get("created_at"))
    return _parse(created_at) if created_at else None


def fetch_pruef_tasks(since: datetime, until: datetime, broker_ids: list[int]) -> list[PruefTask]:
    """GET /activities – Prüfaufgaben, deren updated_at im Fenster liegt.

    updated_at_from/to werden vom Server ignoriert (verifiziert: Filter ändert die
    total_count nicht), sort_by=updated_at&order=desc funktioniert dagegen. Also
    absteigend lesen und abbrechen, sobald wir aus dem Fenster laufen."""
    tasks: list[PruefTask] = []
    for broker_id in broker_ids:
        for row in _paginate(
            "/activities",
            key=config.propstack_key_tasks(),
            params={
                "item_type": "reminder",
                "broker_id": broker_id,
                "sort_by": "updated_at",
                "order": "desc",
            },
        ):
            task = _to_task(row)
            if not task.updated_at:
                continue
            updated = _parse(task.updated_at)
            if updated < since:
                break  # ab hier ist alles Weitere älter – Rest der Seiten sparen
            if updated < until:
                tasks.append(task)
    logger.info("Propstack: %d Prüfaufgaben mit updated_at im Fenster (Broker %s)", len(tasks), broker_ids)
    return sorted(tasks, key=lambda t: t.updated_at or "", reverse=True)


def _parse(value: str) -> datetime:
    """ISO-8601 aus Propstack ("2026-08-19T11:29:56.983+02:00") in ein aware datetime."""
    return datetime.fromisoformat(value)
