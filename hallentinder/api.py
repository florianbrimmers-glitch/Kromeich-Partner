from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import catalog, config, leads, ranking
from .models import LeadPayload, SearchProfile, SwipeEvent
from .ratelimit import limiter
from .session import store

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bestand beim Boot laden, damit der erste Besucher nicht auf die
    ~2 Minuten des vollen Propstack-Abrufs wartet."""
    catalog.vorwaermen()
    yield


app = FastAPI(title="Hallentinder", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)

if config.allowed_origins():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unbekannt"


def _drossel(request: Request) -> None:
    if not limiter.erlaubt(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen. Bitte später erneut versuchen.")


def _bestand():
    try:
        return catalog.cards()
    except Exception as e:
        logger.error("Bestand nicht verfügbar: %s", e)
        raise HTTPException(status_code=503, detail="Der Objektbestand ist gerade nicht erreichbar.") from e


def _seite(karten, offset: int):
    ausschnitt = karten[offset : offset + config.CARD_PAGE_SIZE]
    return {
        "karten": [k.model_dump() for k in ausschnitt],
        "offset": offset + len(ausschnitt),
        "weitere": offset + len(ausschnitt) < len(karten),
    }


@app.post("/api/session")
def session_anlegen(profil: SearchProfile, request: Request):
    _drossel(request)
    karten, zentrum, radius = ranking.rangliste(_bestand(), profil)
    session = store.anlegen(profil, karten, radius)
    logger.info(
        "Neue Session: Ort '%s', %d Treffer, Radius %d km (Zentrum: %s)",
        profil.ort, len(karten), radius, zentrum.quelle,
    )
    return {
        "token": session.token,
        "treffer": len(karten),
        "radius_km": radius,
        "region_erkannt": zentrum.bekannt(),
        **_seite(karten, 0),
    }


@app.get("/api/cards")
def karten_abrufen(token: str, offset: int = 0):
    session = store.holen(token)
    if session is None:
        raise HTTPException(status_code=404, detail="Sitzung abgelaufen. Bitte Suche neu starten.")
    return _seite(session.karten, max(offset, 0))


@app.post("/api/swipe")
def swipe(event: SwipeEvent):
    session = store.swipe(event.token, event.unit_id, event.richtung)
    if session is None:
        raise HTTPException(status_code=404, detail="Sitzung abgelaufen. Bitte Suche neu starten.")
    return {"likes": len(session.likes), "dislikes": len(session.dislikes)}


@app.post("/api/lead")
def lead_senden(lead: LeadPayload, request: Request):
    _drossel(request)
    session = store.holen(lead.token)
    if session is None:
        raise HTTPException(status_code=404, detail="Sitzung abgelaufen. Bitte Suche neu starten.")
    try:
        ergebnis = leads.verarbeite(session, lead)
    except leads.LeadFehler as e:
        if str(e) == "honeypot":
            logger.warning("Honeypot ausgelöst von %s – kein Write", _client_ip(request))
            return {"kontakt_id": None, "deals_angelegt": 0, "deals_geplant": 0,
                    "deals_fehlgeschlagen": 0, "kontakt_neu": False, "no_write": True}
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Lead-Verarbeitung fehlgeschlagen: %s", e)
        raise HTTPException(status_code=502, detail="Anfrage konnte nicht übermittelt werden.") from e
    return ergebnis.model_dump()


@app.get("/api/likes")
def likes(token: str):
    session = store.holen(token)
    if session is None:
        raise HTTPException(status_code=404, detail="Sitzung abgelaufen. Bitte Suche neu starten.")
    return {"karten": [k.model_dump() for k in session.gelikte_karten()]}


@app.get("/healthz")
def healthz():
    anzahl, geladen_um = catalog.stand()
    return {
        "status": "ok",
        "objekte_im_cache": anzahl,
        "cache_alter_sekunden": round(time.time() - geladen_um) if geladen_um else None,
        "sessions": store.anzahl(),
        "no_write": config.no_write(),
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
