from __future__ import annotations

import json
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import config, mail, speicher
from .models import Einreichung, Entscheidung, Kontakt, Objektdaten, Rolle, Status

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
# Der Realm landet in einem HTTP-Header und muss latin-1-kodierbar sein,
# deshalb bewusst ohne Umlaute und Gedankenstriche.
REALM = "Hallenboerse intern"
sicherheit = HTTPBasic(realm=REALM)


@asynccontextmanager
async def lifespan(app: FastAPI):
    speicher.init()
    yield


app = FastAPI(title="Hallenbörse", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)


def pruefer(zugang: HTTPBasicCredentials = Depends(sicherheit)) -> str:
    """Zugang zur Prüfansicht. compare_digest, damit die Laufzeit nichts verrät."""
    passt = secrets.compare_digest(zugang.password, config.pruef_passwort())
    if not passt or not zugang.username.strip():
        raise HTTPException(
            status_code=401, detail="Kein Zugang",
            headers={"WWW-Authenticate": f'Basic realm="{REALM}"'},
        )
    return zugang.username.strip()


def _datei_lesen(
    datei: UploadFile, erlaubt: dict[str, str], grenze: int, label: str, zielname: str
) -> tuple[str, bytes]:
    """Hochgeladene Datei prüfen und einlesen.

    Der Dateiname wird aus dem erlaubten Inhaltstyp gebildet, nicht vom Client
    übernommen – ein hochgeladener Name darf nie in einen Pfad geraten."""
    typ = (datei.content_type or "").split(";")[0].strip().lower()
    if typ not in erlaubt:
        raise HTTPException(
            status_code=400,
            detail=f"{label}: nur {', '.join(sorted(erlaubt))} – empfangen wurde {typ or 'unbekannt'}.",
        )
    inhalt = datei.file.read(grenze + 1)
    if len(inhalt) > grenze:
        raise HTTPException(status_code=413, detail=f"{label} ist größer als {grenze // 1024 // 1024} MB.")
    if not inhalt:
        raise HTTPException(status_code=400, detail=f"{label} ist leer.")
    return f"{zielname}{erlaubt[typ]}", inhalt


@app.post("/api/einreichung")
async def einreichen(
    rolle: str = Form(...),
    kontakt: str = Form(...),
    objekt: str = Form(...),
    einwilligung: bool = Form(False),
    nachweis: UploadFile = File(...),
    bilder: list[UploadFile] = File(default=[]),
):
    if not einwilligung:
        raise HTTPException(status_code=400, detail="Ohne Einwilligung können wir den Vorgang nicht bearbeiten.")
    try:
        rolle_wert = Rolle(rolle)
        kontakt_wert = Kontakt.model_validate(json.loads(kontakt))
        objekt_wert = Objektdaten.model_validate(json.loads(objekt))
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=_fehlertext(e)) from e

    nachweis_name, nachweis_inhalt = _datei_lesen(
        nachweis, config.NACHWEIS_TYPEN, config.MAX_NACHWEIS_BYTES, "Nachweis", "nachweis",
    )

    echte_bilder = [b for b in bilder if b and b.filename]
    if len(echte_bilder) > config.MAX_BILDER:
        raise HTTPException(status_code=400, detail=f"Höchstens {config.MAX_BILDER} Bilder.")
    gelesen = [
        _datei_lesen(b, config.BILD_TYPEN, config.MAX_BILD_BYTES, "Bild", "bild")
        for b in echte_bilder
    ]

    einreichung = speicher.anlegen(
        rolle_wert, kontakt_wert, objekt_wert, (nachweis_name, nachweis_inhalt), gelesen,
    )
    mail.eingang_bestaetigen(einreichung)
    mail.intern_melden(einreichung, "Neue Einreichung")
    return {
        "nummer": einreichung.nummer,
        "token": einreichung.token,
        "status_url": f"/status.html?t={einreichung.token}",
        "nachweis_art": einreichung.nachweis_art.value,
    }


def _fehlertext(fehler: Exception) -> str:
    if isinstance(fehler, ValidationError):
        erste = fehler.errors()[0]
        feld = ".".join(str(t) for t in erste.get("loc", ()) if t != "body")
        return f"{feld}: {erste.get('msg', 'ungültig')}" if feld else str(erste.get("msg"))
    return "Die Angaben konnten nicht gelesen werden."


@app.get("/api/status/{token}")
def status(token: str):
    einreichung = speicher.holen_per_token(token)
    if einreichung is None:
        raise HTTPException(status_code=404, detail="Zu diesem Link gibt es keinen Vorgang.")
    return {
        "nummer": einreichung.nummer,
        "status": einreichung.status.value,
        "eingegangen_am": einreichung.eingegangen_am,
        "geprueft_am": einreichung.geprueft_am,
        "ablehnungsgrund": einreichung.ablehnungsgrund,
        "adresse": einreichung.objekt.adresse(),
        "nachweis_art": einreichung.nachweis_art.value,
        "nachweis_geloescht": not einreichung.nachweis_vorhanden(),
        "objekt": einreichung.objekt.model_dump(),
        "bilder": einreichung.bilder,
        "verlauf": [e.model_dump() for e in einreichung.verlauf],
    }


@app.get("/api/objekte")
def objekte():
    """Freigegebene Objekte – ohne jede Angabe zum Einsender."""
    return {"objekte": [e.oeffentlich() for e in speicher.liste(Status.FREIGEGEBEN)]}


@app.get("/api/bild/{nummer}/{bildname}")
def bild(nummer: str, bildname: str):
    treffer = next((e for e in speicher.liste(Status.FREIGEGEBEN) if e.nummer == nummer), None)
    if treffer is None:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    pfad = speicher.bild_pfad(treffer, bildname)
    if pfad is None:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return FileResponse(pfad)


# --- Bearbeiten durch den Einsender ------------------------------------------
#
# Der Statuslink ist der Zugang: Wer ihn hat, hat das Objekt eingereicht.
# Für einen Prototyp ist das angemessen; für den Echtbetrieb gehört an diese
# Stelle ein Bestätigungscode per Mail bei jeder Änderung.

def _per_token(token: str):
    einreichung = speicher.holen_per_token(token)
    if einreichung is None:
        raise HTTPException(status_code=404, detail="Zu diesem Link gibt es keinen Vorgang.")
    return einreichung


@app.put("/api/vorgang/{token}")
async def objekt_aendern(
    token: str,
    objekt: str = Form(...),
    nachweis: UploadFile | None = File(default=None),
):
    einreichung = _per_token(token)
    try:
        objekt_wert = Objektdaten.model_validate(json.loads(objekt))
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=_fehlertext(e)) from e

    neuer_nachweis = None
    if nachweis is not None and nachweis.filename:
        neuer_nachweis = _datei_lesen(
            nachweis, config.NACHWEIS_TYPEN, config.MAX_NACHWEIS_BYTES, "Nachweis", "nachweis",
        )

    try:
        geaendert = speicher.aktualisieren(einreichung.id, objekt_wert, neuer_nachweis)
    except speicher.NeuerNachweisNoetig:
        raise HTTPException(
            status_code=400,
            detail="Bei einer neuen Adresse ist ein neuer Nachweis nötig – der geprüfte galt für die bisherige.",
        ) from None

    if geaendert.status is Status.IN_PRUEFUNG and einreichung.status is not Status.IN_PRUEFUNG:
        mail.intern_melden(geaendert, "Adresse geändert, erneute Prüfung nötig")

    return {"status": geaendert.status.value, "verlauf": [e.model_dump() for e in geaendert.verlauf]}


@app.post("/api/vorgang/{token}/bilder")
async def bilder_ergaenzen(token: str, bilder: list[UploadFile] = File(default=[])):
    einreichung = _per_token(token)
    echte = [b for b in bilder if b and b.filename]
    if not echte:
        raise HTTPException(status_code=400, detail="Keine Datei empfangen.")
    if len(einreichung.bilder) + len(echte) > config.MAX_BILDER:
        raise HTTPException(status_code=400, detail=f"Höchstens {config.MAX_BILDER} Fotos je Objekt.")

    gelesen = [
        _datei_lesen(b, config.BILD_TYPEN, config.MAX_BILD_BYTES, "Bild", "bild")
        for b in echte
    ]
    geaendert = speicher.bilder_ergaenzen(einreichung.id, gelesen)
    return {"bilder": geaendert.bilder}


@app.delete("/api/vorgang/{token}/bilder/{bildname}")
def bild_entfernen(token: str, bildname: str):
    einreichung = _per_token(token)
    if bildname not in einreichung.bilder:
        raise HTTPException(status_code=404, detail="Dieses Foto gehört nicht zum Vorgang.")
    geaendert = speicher.bild_entfernen(einreichung.id, bildname)
    return {"bilder": geaendert.bilder}


@app.post("/api/vorgang/{token}/sichtbarkeit")
def sichtbarkeit(token: str, sichtbar: bool = Form(...)):
    einreichung = _per_token(token)
    if sichtbar and einreichung.status is not Status.ZURUECKGEZOGEN:
        raise HTTPException(status_code=409, detail="Nur zurückgezogene Objekte lassen sich wieder online stellen.")
    if not sichtbar and einreichung.status is not Status.FREIGEGEBEN:
        raise HTTPException(status_code=409, detail="Nur freigegebene Objekte lassen sich zurückziehen.")
    geaendert = speicher.sichtbarkeit_setzen(einreichung.id, sichtbar)
    return {"status": geaendert.status.value}


@app.get("/api/vorgang/{token}/bild/{bildname}")
def eigenes_bild(token: str, bildname: str):
    """Eigene Fotos sieht der Einsender auch vor der Freigabe."""
    einreichung = _per_token(token)
    pfad = speicher.bild_pfad(einreichung, bildname)
    if pfad is None:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return FileResponse(pfad)


# --- interne Prüfung ---------------------------------------------------------

def _vorgang(einreichung: Einreichung, mit_kontakt: bool) -> dict:
    daten = {
        "id": einreichung.id,
        "nummer": einreichung.nummer,
        "rolle": einreichung.rolle.value,
        "status": einreichung.status.value,
        "eingegangen_am": einreichung.eingegangen_am,
        "adresse": einreichung.objekt.adresse(),
        "flaeche_qm": einreichung.objekt.flaeche_qm,
        "nachweis_art": einreichung.nachweis_art.value,
        "nachweis_vorhanden": einreichung.nachweis_vorhanden(),
        "geprueft_am": einreichung.geprueft_am,
        "geprueft_von": einreichung.geprueft_von,
        "ablehnungsgrund": einreichung.ablehnungsgrund,
        "bilder": einreichung.bilder,
        "verlauf": [e.model_dump() for e in einreichung.verlauf],
    }
    if mit_kontakt:
        daten["kontakt"] = einreichung.kontakt.model_dump()
        daten["objekt"] = einreichung.objekt.model_dump()
    return daten


@app.get("/api/pruefung")
def pruefliste(name: str = Depends(pruefer), status: str | None = None):
    gewaehlt = Status(status) if status in {s.value for s in Status} else None
    return {"vorgaenge": [_vorgang(e, mit_kontakt=False) for e in speicher.liste(gewaehlt)]}


@app.get("/api/pruefung/{einreichung_id}")
def pruefdetail(einreichung_id: int, name: str = Depends(pruefer)):
    einreichung = speicher.holen(einreichung_id)
    if einreichung is None:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return _vorgang(einreichung, mit_kontakt=True)


@app.get("/api/pruefung/{einreichung_id}/nachweis")
def nachweis_ansehen(einreichung_id: int, name: str = Depends(pruefer)):
    einreichung = speicher.holen(einreichung_id)
    if einreichung is None:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    pfad = speicher.nachweis_pfad(einreichung)
    if pfad is None:
        raise HTTPException(
            status_code=410,
            detail="Der Nachweis wurde nach der Prüfung gelöscht – im Protokoll steht, wer ihn gesehen hat.",
        )
    logger.info("Nachweis zu %s von %s eingesehen", einreichung.nummer, name)
    return FileResponse(pfad, filename=f"{einreichung.nummer}-{einreichung.nachweis_art.value}{pfad.suffix}")


@app.post("/api/pruefung/{einreichung_id}/entscheidung")
def entscheiden(einreichung_id: int, entscheidung: Entscheidung, name: str = Depends(pruefer)):
    vorhanden = speicher.holen(einreichung_id)
    if vorhanden is None:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    if vorhanden.status is not Status.IN_PRUEFUNG:
        raise HTTPException(status_code=409, detail=f"Vorgang ist bereits {vorhanden.status.value}.")
    if not entscheidung.freigeben and not entscheidung.grund.strip():
        raise HTTPException(status_code=400, detail="Eine Ablehnung braucht einen Grund – der Einsender sieht ihn.")

    einreichung = speicher.entscheiden(
        einreichung_id, entscheidung.freigeben, entscheidung.pruefer, entscheidung.grund,
    )
    mail.entscheidung_melden(einreichung)
    return _vorgang(einreichung, mit_kontakt=True)


@app.get("/healthz")
def healthz():
    offen = len(speicher.liste(Status.IN_PRUEFUNG))
    return {"status": "ok", "offene_vorgaenge": offen}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
