from __future__ import annotations

import json
import logging
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .models import Einreichung, Kontakt, Nachweisart, Objektdaten, Rolle, Status

logger = logging.getLogger(__name__)

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS einreichungen (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nummer          TEXT    NOT NULL UNIQUE,
    token           TEXT    NOT NULL UNIQUE,
    status          TEXT    NOT NULL,
    eingegangen_am  TEXT    NOT NULL,
    daten           TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_status ON einreichungen(status);
"""


def _jetzt() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _verbindung() -> sqlite3.Connection:
    verbindung = sqlite3.connect(config.datenbank())
    verbindung.row_factory = sqlite3.Row
    return verbindung


def init() -> None:
    with _verbindung() as verbindung:
        verbindung.executescript(SCHEMA)


def _ordner(einreichung_id: int) -> Path:
    pfad = config.daten_verzeichnis() / "vorgaenge" / str(einreichung_id)
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def _naechste_nummer(verbindung: sqlite3.Connection) -> str:
    jahr = datetime.now(timezone.utc).year
    praefix = f"{config.NUMMER_PRAEFIX}-{jahr}-"
    zeile = verbindung.execute(
        "SELECT nummer FROM einreichungen WHERE nummer LIKE ? ORDER BY id DESC LIMIT 1",
        (praefix + "%",),
    ).fetchone()
    laufend = int(zeile["nummer"].rsplit("-", 1)[1]) + 1 if zeile else 1
    return f"{praefix}{laufend:04d}"


def _lesen(zeile: sqlite3.Row) -> Einreichung:
    daten = json.loads(zeile["daten"])
    daten.update(id=zeile["id"], nummer=zeile["nummer"], token=zeile["token"],
                 status=zeile["status"], eingegangen_am=zeile["eingegangen_am"])
    return Einreichung.model_validate(daten)


def _schreiben(verbindung: sqlite3.Connection, einreichung: Einreichung) -> None:
    daten = einreichung.model_dump(mode="json")
    for feld in ("id", "nummer", "token", "status", "eingegangen_am"):
        daten.pop(feld)
    verbindung.execute(
        "UPDATE einreichungen SET status = ?, daten = ? WHERE id = ?",
        (einreichung.status.value, json.dumps(daten, ensure_ascii=False), einreichung.id),
    )


def anlegen(
    rolle: Rolle,
    kontakt: Kontakt,
    objekt: Objektdaten,
    nachweis: tuple[str, bytes],
    bilder: list[tuple[str, bytes]],
) -> Einreichung:
    """Vorgang speichern. Der Nachweis landet außerhalb jedes statischen Pfads."""
    nachweis_name, nachweis_inhalt = nachweis
    with _lock, _verbindung() as verbindung:
        nummer = _naechste_nummer(verbindung)
        token = secrets.token_urlsafe(16)
        zeiger = verbindung.execute(
            "INSERT INTO einreichungen (nummer, token, status, eingegangen_am, daten)"
            " VALUES (?, ?, ?, ?, ?)",
            (nummer, token, Status.IN_PRUEFUNG.value, _jetzt(), "{}"),
        )
        einreichung_id = int(zeiger.lastrowid)

        ordner = _ordner(einreichung_id)
        (ordner / nachweis_name).write_bytes(nachweis_inhalt)
        bildnamen: list[str] = []
        for index, (name, inhalt) in enumerate(bilder, start=1):
            endung = Path(name).suffix or ".jpg"
            bildname = f"bild_{index}{endung}"
            (ordner / bildname).write_bytes(inhalt)
            bildnamen.append(bildname)

        einreichung = Einreichung(
            id=einreichung_id, nummer=nummer, token=token, rolle=rolle,
            kontakt=kontakt, objekt=objekt, status=Status.IN_PRUEFUNG,
            eingegangen_am=_jetzt(), bilder=bildnamen,
            nachweis_art=Nachweisart.fuer(rolle), nachweis_dateiname=nachweis_name,
        )
        _schreiben(verbindung, einreichung)

    logger.info("Vorgang %s angelegt (%s, %s)", nummer, rolle.value, objekt.adresse())
    return einreichung


def holen(einreichung_id: int) -> Einreichung | None:
    with _verbindung() as verbindung:
        zeile = verbindung.execute(
            "SELECT * FROM einreichungen WHERE id = ?", (einreichung_id,)
        ).fetchone()
    return _lesen(zeile) if zeile else None


def holen_per_token(token: str) -> Einreichung | None:
    with _verbindung() as verbindung:
        zeile = verbindung.execute(
            "SELECT * FROM einreichungen WHERE token = ?", (token,)
        ).fetchone()
    return _lesen(zeile) if zeile else None


def liste(status: Status | None = None) -> list[Einreichung]:
    sql = "SELECT * FROM einreichungen"
    werte: tuple = ()
    if status:
        sql += " WHERE status = ?"
        werte = (status.value,)
    sql += " ORDER BY id DESC"
    with _verbindung() as verbindung:
        return [_lesen(z) for z in verbindung.execute(sql, werte).fetchall()]


def nachweis_pfad(einreichung: Einreichung) -> Path | None:
    if not einreichung.nachweis_dateiname:
        return None
    pfad = _ordner(einreichung.id) / einreichung.nachweis_dateiname
    return pfad if pfad.exists() else None


def bild_pfad(einreichung: Einreichung, bildname: str) -> Path | None:
    """Nur Bilder aus der gespeicherten Liste – der Name kommt aus der URL."""
    if bildname not in einreichung.bilder:
        return None
    pfad = _ordner(einreichung.id) / bildname
    return pfad if pfad.exists() else None


def entscheiden(einreichung_id: int, freigeben: bool, pruefer: str, grund: str = "") -> Einreichung | None:
    """Vorgang abschließen und den Nachweis löschen.

    Ein Grundbuchauszug enthält Eigentümer und Belastungen. Für den Betrieb
    der Plattform wird er nach der Prüfung nicht mehr gebraucht – was bleibt,
    ist das Protokoll: wer hat wann welche Art von Nachweis gesehen."""
    with _lock, _verbindung() as verbindung:
        zeile = verbindung.execute(
            "SELECT * FROM einreichungen WHERE id = ?", (einreichung_id,)
        ).fetchone()
        if zeile is None:
            return None
        einreichung = _lesen(zeile)

        if einreichung.nachweis_dateiname:
            pfad = _ordner(einreichung.id) / einreichung.nachweis_dateiname
            pfad.unlink(missing_ok=True)
            einreichung.nachweis_dateiname = None

        einreichung.status = Status.FREIGEGEBEN if freigeben else Status.ABGELEHNT
        einreichung.geprueft_am = _jetzt()
        einreichung.geprueft_von = pruefer.strip()
        einreichung.ablehnungsgrund = grund.strip() or None
        _schreiben(verbindung, einreichung)

    logger.info(
        "Vorgang %s %s durch %s – Nachweis gelöscht",
        einreichung.nummer, einreichung.status.value, pruefer,
    )
    return einreichung
