from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_MUSTER = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


class Rolle(str, Enum):
    EIGENTUEMER = "eigentuemer"
    MAKLER = "makler"


class Nachweisart(str, Enum):
    """Was eingereicht wurde, um die Verfügungsbefugnis zu belegen."""

    GRUNDBUCHAUSZUG = "grundbuchauszug"
    ALLEINVERMARKTUNGSAUFTRAG = "alleinvermarktungsauftrag"

    @classmethod
    def fuer(cls, rolle: Rolle) -> "Nachweisart":
        return cls.GRUNDBUCHAUSZUG if rolle is Rolle.EIGENTUEMER else cls.ALLEINVERMARKTUNGSAUFTRAG


class Status(str, Enum):
    IN_PRUEFUNG = "in_pruefung"
    FREIGEGEBEN = "freigegeben"
    ABGELEHNT = "abgelehnt"
    ZURUECKGEZOGEN = "zurueckgezogen"   # vom Einsender offline genommen


class Nutzung(str, Enum):
    LAGER = "lager"
    PRODUKTION = "produktion"
    UMSCHLAG = "umschlag"
    GEMISCHT = "gemischt"


class Kontakt(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vorname: str = Field(default="", max_length=100)
    nachname: str = Field(min_length=1, max_length=100)
    firma: str = Field(default="", max_length=200)
    email: str = Field(min_length=5, max_length=200)
    telefon: str = Field(default="", max_length=50)

    @field_validator("email")
    @classmethod
    def email_pruefen(cls, wert: str) -> str:
        wert = wert.strip()
        if not EMAIL_MUSTER.match(wert):
            raise ValueError("Bitte eine gültige E-Mail-Adresse angeben.")
        return wert

    def name(self) -> str:
        return " ".join(t for t in (self.vorname.strip(), self.nachname.strip()) if t)


class Objektdaten(BaseModel):
    model_config = ConfigDict(extra="ignore")

    strasse: str = Field(min_length=1, max_length=200)
    hausnummer: str = Field(default="", max_length=20)
    plz: str = Field(min_length=5, max_length=5)
    stadt: str = Field(min_length=1, max_length=120)
    flaeche_qm: float = Field(gt=0, le=1_000_000)
    hallenhoehe_m: float | None = Field(default=None, gt=0, le=100)
    rampe: bool = False
    nutzung: Nutzung = Nutzung.GEMISCHT
    verfuegbar_ab: str = Field(default="", max_length=40)
    miete_eur_qm: float | None = Field(default=None, ge=0, le=1000)
    beschreibung: str = Field(default="", max_length=4000)

    @field_validator("plz")
    @classmethod
    def plz_pruefen(cls, wert: str) -> str:
        wert = wert.strip()
        if not wert.isdigit():
            raise ValueError("Die Postleitzahl besteht aus fünf Ziffern.")
        return wert

    def adresse(self) -> str:
        strasse = " ".join(t for t in (self.strasse.strip(), self.hausnummer.strip()) if t)
        return f"{strasse}, {self.plz} {self.stadt}".strip(", ")


class Verlaufseintrag(BaseModel):
    """Was wann mit dem Vorgang passiert ist – für Einsender und Prüfung."""

    zeitpunkt: str
    text: str


class Einreichung(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    nummer: str                     # KP-2026-0001, für Rückfragen am Telefon
    token: str                      # Statuslink für den Einsender
    rolle: Rolle
    kontakt: Kontakt
    objekt: Objektdaten
    status: Status = Status.IN_PRUEFUNG
    eingegangen_am: str
    bilder: list[str] = Field(default_factory=list)
    verlauf: list[Verlaufseintrag] = Field(default_factory=list)

    # Prüfprotokoll – bleibt erhalten, auch wenn der Nachweis gelöscht ist
    nachweis_art: Nachweisart
    nachweis_dateiname: str | None = None   # None = nach der Prüfung gelöscht
    geprueft_am: str | None = None
    geprueft_von: str | None = None
    ablehnungsgrund: str | None = None

    def nachweis_vorhanden(self) -> bool:
        return self.nachweis_dateiname is not None

    def oeffentlich_sichtbar(self) -> bool:
        return self.status is Status.FREIGEGEBEN

    def oeffentlich(self) -> dict:
        """Was ein Suchender sehen darf: das Objekt, nie der Einsender."""
        return {
            "nummer": self.nummer,
            "adresse": self.objekt.adresse(),
            "stadt": self.objekt.stadt,
            "plz": self.objekt.plz,
            "flaeche_qm": self.objekt.flaeche_qm,
            "hallenhoehe_m": self.objekt.hallenhoehe_m,
            "rampe": self.objekt.rampe,
            "nutzung": self.objekt.nutzung.value,
            "verfuegbar_ab": self.objekt.verfuegbar_ab,
            "miete_eur_qm": self.objekt.miete_eur_qm,
            "beschreibung": self.objekt.beschreibung,
            "bilder": self.bilder,
            "herkunft": "Direkt vom Eigentümer" if self.rolle is Rolle.EIGENTUEMER
                        else "Über Vermarktungsmandat",
        }


def adress_schluessel(objekt: "Objektdaten") -> str:
    """Vergleichbare Form der Adresse.

    Ändert sich die Adresse, ist es ein anderes Objekt – der geprüfte Nachweis
    galt für die alte. Groß-/Kleinschreibung und Leerzeichen sollen dafür aber
    keinen Unterschied machen."""
    teile = (objekt.strasse, objekt.hausnummer, objekt.plz, objekt.stadt)
    return "|".join(" ".join(t.split()).casefold() for t in teile)


class Entscheidung(BaseModel):
    freigeben: bool
    pruefer: str = Field(min_length=1, max_length=100)
    grund: str = Field(default="", max_length=1000)
