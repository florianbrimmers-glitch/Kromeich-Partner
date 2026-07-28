from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Event(BaseModel):
    """Ein aus einer #events-Einladung extrahiertes Event."""

    model_config = ConfigDict(extra="ignore")

    ist_event: bool = False        # False = Werbung/Newsletter ohne konkreten Termin
    datum: str | None = None        # wie im Original, z.B. "04.10.2026" oder "16./17.06"
    event_name: str | None = None
    branche: str | None = None
    ort: str | None = None
    kosten: str | None = None       # z.B. "kostenlos", "260 Eur", "tba"
    anmeldelink: str | None = None  # Registrierungs-/Info-Link aus der Einladung
    confidence: float = 0.0
    begruendung: str = ""


class EventExtraction(BaseModel):
    """Ergebnis eines #events-Posts: alle darin gefundenen Events."""

    events: list[Event] = Field(default_factory=list)


class DecisionRecord(BaseModel):
    """Eine JSONL-Zeile pro extrahiertem Event."""

    run_id: str
    verarbeitet_am: str
    message_ts: str
    event_index: int = 0
    permalink: str | None = None
    text_auszug: str = ""
    event: Event | None = None
    aufgabe_name: str | None = None   # der (im Dry-Run vorbereitete) Asana-Aufgaben-Name
    aufgabe_notes: str | None = None  # die vorbereitete Aufgaben-Beschreibung
    in_asana: bool = False            # tatsächlich als Asana-Aufgabe angelegt?
    asana_task_url: str | None = None
    duplikat_von: str | None = None   # gid der bestehenden Aufgabe, wenn als Dublette erkannt
    fehler: str | None = None


class RunReport(BaseModel):
    nachrichten_gesehen: int = 0
    bereits_verarbeitet: int = 0
    events_erkannt: int = 0
    nicht_events: int = 0
    aufgaben_erstellt: int = 0
    duplikate: int = 0
    fehler: list[str] = Field(default_factory=list)
