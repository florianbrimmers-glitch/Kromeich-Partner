from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DealTyp(str, Enum):
    VERMIETUNG = "vermietung"      # (Anschluss-)Vermietung / verfügbare bzw. gesuchte Fläche
    TRANSAKTION = "transaktion"    # An-/Verkauf, Investment
    NEUBAU = "neubau"             # Neubau-Ankündigung / Fertigstellung / Richtfest
    SONSTIGES = "sonstiges"        # Marktnews ohne konkreten Flächen-Deal


class Deal(BaseModel):
    """Ein einzelnes Deal-Item aus einem Logistik-Deal-Radar-Digest.

    Die Adress-/Größenfelder heißen bewusst wie in objekte_handler.Classification,
    damit matcher.find_unit ein Deal-Objekt unverändert konsumieren kann.
    """

    model_config = ConfigDict(extra="ignore")

    deal_typ: DealTyp
    ist_vermietung: bool = False
    strasse: str | None = None
    hausnummer: str | None = None
    stadt: str | None = None
    objekt_name: str | None = None      # Projekt-/Eigentümer-/Mieter-Firma, z.B. "CityLink Dortmund"
    groessen_hinweis: str | None = None  # "kleinste" | "groesste" | qm-Zahl als String
    mieter: str | None = None
    vermieter: str | None = None
    # Ein bestehender Mieter verlängert seinen Vertrag: Es wird nichts frei und nichts
    # neu vergeben – keine Aufgabe. (Eine Erweiterung um neue Fläche ist eine Vermietung.)
    ist_verlaengerung: bool = False
    confidence: float = 0.0
    begruendung: str = ""


class NewsletterExtraction(BaseModel):
    """Ergebnis eines Digests: Liste aller extrahierten Deal-Items."""

    deals: list[Deal] = Field(default_factory=list)


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
    status_id: int | None = None
    archived: bool | None = None
    einheit: str | None = None        # unit_id, z. B. „Unit 2“ oder „Halle B (3)“
    eigentuemer: str | None = None    # Custom-Feld „eigentumer“; im Altbestand oft leer

    def ist_abgeschlossen(self, status_abgeschlossen: int) -> bool:
        """Nicht mehr in der Vermarktung: als vermietet geführt, Status „Abgeschlossen“
        oder archiviert. Fehlt eine Angabe, gilt die Einheit als offen."""
        return self.rented is True or self.archived is True or (
            self.status_id is not None and self.status_id == status_abgeschlossen
        )

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


class MatchResult(BaseModel):
    status: MatchStatus
    # Bei UNIQUE die Ziel-Units: meist genau eine; mehrere, wenn die Meldung das
    # ganze Objekt betrifft und es aus mehreren Einheiten besteht.
    units: list[Unit] = Field(default_factory=list)
    kandidaten: list[Unit] = Field(default_factory=list)
    grund: str = ""
    # NONE, weil die gewählte Einheit erkennbar einem anderen gehört als dem Vermieter der
    # Meldung und nichts sonst für sie spricht (match_ai.select_match_geprueft).
    anderer_eigentuemer: bool = False


class Tier(str, Enum):
    A = "A"
    B = "B"
    NONE = "none"  # ignorieren


class Decision(BaseModel):
    tier: Tier
    grund: str
    geplante_aktionen: list[str] = Field(default_factory=list)


class DecisionRecord(BaseModel):
    """Eine JSONL-Zeile pro extrahiertem Deal."""

    run_id: str
    verarbeitet_am: str
    message_ts: str
    deal_index: int = 0
    permalink: str | None = None
    text_auszug: str = ""
    deal: Deal | None = None
    match: MatchResult | None = None
    decision: Decision | None = None
    ausgefuehrte_aktionen: list[str] = Field(default_factory=list)
    fehler: str | None = None


class RunReport(BaseModel):
    nachrichten_gesehen: int = 0
    bereits_verarbeitet: int = 0
    deals_gesamt: int = 0
    vermietungen: int = 0
    ignoriert: int = 0
    stufe_a: int = 0
    stufe_b: int = 0
    # Vermietungen ohne neue Aufgabe: Einheit schon vermietet/abgeschlossen bzw. zur
    # Einheit liegt schon eine offene Review-Aufgabe.
    bereits_abgeschlossen: int = 0
    bereits_offen: int = 0
    # Vermietungen ohne Aufgabe: Objekt gehört einem anderen Eigentümer bzw. bloße Verlängerung.
    anderer_eigentuemer: int = 0
    verlaengerungen: int = 0
    fehler: list[str] = Field(default_factory=list)
