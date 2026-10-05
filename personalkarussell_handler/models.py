from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    WECHSEL = "wechsel"            # Person(en) wechseln, neue Firma ist genannt
    ABGANG = "abgang"              # Person hat die Firma verlassen, Ziel unbekannt
    UMFIRMIERUNG = "umfirmierung"  # Firma heißt jetzt anders (betrifft viele Kontakte)
    LINKEDIN = "linkedin"          # nur ein Link – Inhalt nicht maschinell lesbar
    IGNORIEREN = "ignorieren"


class Wechsel(BaseModel):
    vorname: str | None = None
    nachname: str | None = None
    alte_firma: str | None = None
    neue_firma: str | None = None
    neue_position: str | None = None
    ab_datum: str | None = None  # so wie in der Nachricht ("zum 01.05.")

    def name(self) -> str:
        return " ".join(t for t in (self.vorname, self.nachname) if t) or "unbekannt"


class Classification(BaseModel):
    typ: MessageType
    wechsel: list[Wechsel] = Field(default_factory=list)
    confidence: float = 0.0
    begruendung: str = ""


class Person(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    email: str | None = None
    description: str | None = None

    def name(self) -> str:
        return " ".join(t for t in (self.first_name, self.last_name) if t) or f"Kontakt {self.id}"


class Company(BaseModel):
    id: int
    name: str


class Link(BaseModel):
    """Eine Firmen-Verknüpfung (V2 /relationships) einer Person."""

    relationship_id: int
    company_id: int
    company_name: str = ""


class MatchStatus(str, Enum):
    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


class PersonMatch(BaseModel):
    status: MatchStatus
    person: Person | None = None
    kandidaten: list[Person] = Field(default_factory=list)
    grund: str = ""


class CompanyMatch(BaseModel):
    status: MatchStatus
    company: Company | None = None
    kandidaten: list[Company] = Field(default_factory=list)
    grund: str = ""


class Tier(str, Enum):
    A = "A"        # automatisch ausführen
    B = "B"        # Review-Aufgabe
    NONE = "none"  # ignorieren


class Decision(BaseModel):
    tier: Tier
    grund: str
    geplante_aktionen: list[str] = Field(default_factory=list)
    bereits_aktuell: bool = False


class WechselPlan(BaseModel):
    """Alles, was zur Ausführung eines einzelnen Wechsels nötig ist."""

    wechsel: Wechsel
    person: PersonMatch | None = None
    firma: CompanyMatch | None = None
    alte_links: list[Link] = Field(default_factory=list)
    decision: Decision | None = None


class DecisionRecord(BaseModel):
    """Eine JSONL-Zeile pro verarbeiteter Nachricht."""

    run_id: str
    verarbeitet_am: str
    message_ts: str
    thread_ts: str | None = None
    permalink: str | None = None
    text_auszug: str = ""
    classification: Classification | None = None
    plaene: list[WechselPlan] = Field(default_factory=list)
    ausgefuehrte_aktionen: list[str] = Field(default_factory=list)
    fehler: str | None = None


class RunReport(BaseModel):
    nachrichten_gesehen: int = 0
    bereits_verarbeitet: int = 0
    ignoriert: int = 0
    stufe_a: int = 0
    stufe_b: int = 0
    fehler: list[str] = Field(default_factory=list)
