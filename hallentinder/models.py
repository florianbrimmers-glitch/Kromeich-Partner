from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Nutzung(str, Enum):
    LAGER = "lager"
    PRODUKTION = "produktion"
    UMSCHLAG = "umschlag"
    EGAL = "egal"


class Zeithorizont(str, Enum):
    SOFORT = "sofort"
    DREI_MONATE = "3_monate"
    SECHS_MONATE = "6_monate"
    FLEXIBEL = "flexibel"


class SearchProfile(BaseModel):
    """Antworten aus dem Onboarding – die Grundlage für Filter und Reihenfolge."""

    model_config = ConfigDict(extra="ignore")

    ort: str = Field(min_length=1, max_length=120)
    flaeche_min: int = Field(ge=0, le=1_000_000)
    flaeche_max: int = Field(ge=0, le=1_000_000)
    nutzung: Nutzung = Nutzung.EGAL
    zeithorizont: Zeithorizont = Zeithorizont.FLEXIBEL
    radius_km: int | None = Field(default=None, ge=5, le=400)

    def spanne(self) -> tuple[int, int]:
        """Min/Max robust gegen vertauschte Eingaben; 0 heißt 'offen'."""
        werte = [w for w in (self.flaeche_min, self.flaeche_max) if w > 0]
        if not werte:
            return (0, 0)
        return (min(werte), max(werte))


class HallCard(BaseModel):
    """Was eine Karte im Frontend zeigt – bewusst nur freigegebene Felder.

    Propstack-Rohobjekte enthalten Eigentümer-, Makler- und interne Felder;
    die App ist öffentlich, deshalb ist diese Klasse die Whitelist."""

    model_config = ConfigDict(extra="forbid")

    id: int
    titel: str
    einheit: str | None = None      # z.B. "Einheit 3" – aus dem Objektnamen gelöst
    stadt: str | None = None
    plz: str | None = None
    strasse: str | None = None
    lat: float | None = None
    lng: float | None = None
    flaeche: float | None = None
    hallenhoehe: float | None = None
    # Propstack liefert diese beiden als Boolean, nicht als Text
    rampe: bool = False
    kranbahn: bool = False
    baujahr: int | None = None
    expose_url: str | None = None
    bilder: list[str] = Field(default_factory=list)
    entfernung_km: float | None = None

    def adresse(self) -> str:
        teile = [t for t in (self.plz, self.stadt) if t]
        ort = " ".join(teile)
        if self.strasse and ort:
            return f"{self.strasse}, {ort}"
        return self.strasse or ort or self.titel


class SwipeRichtung(str, Enum):
    LIKE = "like"
    DISLIKE = "dislike"


class SwipeEvent(BaseModel):
    token: str = Field(min_length=8, max_length=64)
    unit_id: int
    richtung: SwipeRichtung


class LeadPayload(BaseModel):
    """Kontaktformular am Ende des Decks."""

    model_config = ConfigDict(extra="ignore")

    token: str = Field(min_length=8, max_length=64)
    vorname: str = Field(default="", max_length=100)
    nachname: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=5, max_length=200)
    telefon: str = Field(default="", max_length=50)
    firma: str = Field(default="", max_length=200)
    nachricht: str = Field(default="", max_length=2000)
    einwilligung: bool = False
    # Honeypot: von Menschen nie ausgefüllt, von einfachen Bots schon
    website: str = Field(default="", max_length=200)


class LeadResult(BaseModel):
    kontakt_id: int | None = None
    kontakt_neu: bool = False
    deals_angelegt: int = 0
    deals_geplant: int = 0
    deals_fehlgeschlagen: int = 0
    no_write: bool = False
