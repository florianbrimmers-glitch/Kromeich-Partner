from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MessageType(str, Enum):
    STATUS_ANWEISUNG = "status_anweisung"
    FEHLT_IN_PS = "fehlt_in_ps"
    FLAECHENUPDATE = "flaechenupdate"
    IGNORIEREN = "ignorieren"


class AktionsTyp(str, Enum):
    VERMIETET = "vermietet"
    UPDATE = "update"  # "Bilder ablegen", "PS aktualisieren" etc.
    SONSTIGES = "sonstiges"


class Classification(BaseModel):
    typ: MessageType
    aktion: AktionsTyp | None = None
    strasse: str | None = None
    hausnummer: str | None = None
    stadt: str | None = None
    objekt_name: str | None = None  # z.B. "Viersen Aconlog", "prodac Castrop"
    # Eigentümer/Vermieter/Entwickler als eigenes Feld. Steckt er nur im
    # objekt_name, ist er für das Matching verloren: "Flächenupdate Mileway
    # 07/26" hat keine Adresse, und die Zugehörigkeit steht ausschließlich in
    # den Eigentümer-Verknüpfungen, nie im Objekttitel.
    eigentuemer: str | None = None
    groessen_hinweis: str | None = None  # "kleinste" | "groesste" | qm-Zahl
    confidence: float = 0.0
    begruendung: str = ""


class Unit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str | None = None
    title: str | None = None
    street: str | None = None
    house_number: str | None = None
    zip_code: str | None = None
    city: str | None = None
    property_space_value: float | None = None
    broker_id: int | None = None
    broker_name: str | None = None
    rented: bool | None = None
    project_id: int | None = None
    # Entscheidungsrelevante Felder. Ein Kandidat, der nur aus Straße und Stadt
    # besteht, lässt sich nicht bewerten - genau daran ist der Aconlog-Match
    # gescheitert: der Sieger hatte keine Fläche, keinen Status und war als
    # APARTMENT typisiert.
    status_id: int | None = None
    status_name: str | None = None
    free_from: str | None = None
    hall_area: float | None = None
    rs_type: str | None = None

    def ist_huelle(self) -> bool:
        """Datensatz ohne belastbaren Inhalt.

        Keine Fläche und kein Status heißt: als Ziel eines Flächen- oder
        Statusupdates unbrauchbar, egal wie gut die Adresse passt."""
        return not self.hall_area and not self.property_space_value and self.status_id is None

    def kurzform(self) -> str:
        """Eine Zeile für Kandidatenlisten in Aufgaben – mit den Feldern, die
        eine Entscheidung tragen, nicht nur der Adresse."""
        teile = [self.adresse(), f"Unit {self.id}"]
        if self.hall_area:
            teile.append(f"{self.hall_area:,.0f} m² Halle".replace(",", "."))
        if self.status_name:
            teile.append(self.status_name)
        if self.rented is not None:
            teile.append("vermietet" if self.rented else "nicht vermietet")
        if self.free_from:
            teile.append(f"frei ab {self.free_from}")
        return " · ".join(teile)

    def adresse(self) -> str:
        teile = [t for t in (self.street, self.house_number) if t]
        zeile = " ".join(teile)
        if self.city:
            zeile = f"{zeile}, {self.city}" if zeile else self.city
        return zeile or (self.name or self.title or f"Unit {self.id}")


class MatchStatus(str, Enum):
    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"
    NONE = "none"
    # Der Bestand eines Eigentümers. Bei einem Flächenupdate ist "26 Einheiten"
    # der Treffer und nicht die Mehrdeutigkeit: die Meldung betrifft das ganze
    # Portfolio, die zeilenweise Zuordnung passiert danach innerhalb dieser Menge.
    PORTFOLIO = "portfolio"


class MatchResult(BaseModel):
    status: MatchStatus
    # Bei UNIQUE die Ziel-Units: meist genau eine; mehrere, wenn die Nachricht das
    # ganze Objekt betrifft und es aus mehreren Einheiten besteht (Hamburgring-Fall).
    # Bei PORTFOLIO der vollständige Eigentümerbestand.
    units: list[Unit] = Field(default_factory=list)
    kandidaten: list[Unit] = Field(default_factory=list)
    grund: str = ""
    # Woher der Treffer kommt - für die Auswertung der Trefferquote je Achse.
    achse: str = "adresse"  # "adresse" | "eigentuemer" | "eigentuemer+flaeche"
    eigentuemer_contact_ids: list[int] = Field(default_factory=list)
    eigentuemer_project_ids: list[int] = Field(default_factory=list)


class Tier(str, Enum):
    A = "A"
    B = "B"
    NONE = "none"  # ignorieren


class Decision(BaseModel):
    tier: Tier
    grund: str
    geplante_aktionen: list[str] = Field(default_factory=list)


class DecisionRecord(BaseModel):
    """Eine JSONL-Zeile pro verarbeiteter Nachricht (Woche-1-Auswertung)."""

    run_id: str
    verarbeitet_am: str
    message_ts: str
    thread_ts: str | None = None
    permalink: str | None = None
    text_auszug: str = ""
    classification: Classification | None = None
    match: MatchResult | None = None
    decision: Decision | None = None
    ausgefuehrte_aktionen: list[str] = Field(default_factory=list)
    fehler: str | None = None


class RunReport(BaseModel):
    nachrichten_gesehen: int = 0
    bereits_verarbeitet: int = 0
    ignoriert: int = 0
    stufe_a: int = 0
    stufe_b: int = 0
    fehler: list[str] = Field(default_factory=list)
