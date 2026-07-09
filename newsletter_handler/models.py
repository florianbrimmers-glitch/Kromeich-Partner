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
    fehler: list[str] = Field(default_factory=list)
