from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DriveDoc(BaseModel):
    """Eine Drive-Datei, die ein Mietangebot enthalten kann."""

    model_config = ConfigDict(extra="ignore")

    file_id: str
    name: str
    mime_type: str
    size: int | None = None
    md5: str | None = None
    modified_time: str | None = None
    created_time: str | None = None
    web_link: str | None = None
    owner: str | None = None
    gefunden_via: str = ""       # "titel" | "ordner:<id>"
    pfad_hinweis: str | None = None   # Ordnername, in dem die Datei liegt
    fundstellen: int = 1         # wie oft dieselbe Datei im Drive liegt

    def dedup_key(self) -> str:
        """Datei-Identität: md5 wenn vorhanden, sonst Größe+MIME.

        Im Drive liegt dasselbe Angebot oft 3-5x in verschiedenen Ordnern
        (gemessen 12.08.2026: ~70 Treffer, ~22 verschiedene Dokumente). Ohne
        diesen Schritt würde jede Kopie einzeln an Claude geschickt.
        """
        if self.md5:
            return f"md5:{self.md5}"
        if self.size:
            return f"size:{self.size}:{self.mime_type}"
        return f"id:{self.file_id}"


class AngebotsOption(BaseModel):
    """Eine Laufzeit-/Konditions-Option eines Angebots -> eine Report-Zeile."""

    model_config = ConfigDict(extra="ignore")

    laufzeit_monate: int | None = None
    kaltmiete_eur_qm: float | None = None      # €/m²/Monat, wie im Dokument
    kaltmiete_absolut_eur: float | None = None  # Monatsmiete absolut, falls so genannt
    nebenkosten_eur_qm: float | None = None
    mietfreie_monate: float | None = None
    flaeche_qm: float | None = None             # falls die Option eigene Fläche hat
    hinweis: str | None = None                  # z.B. "Staffel Jahr 1-3"


class Mietangebot(BaseModel):
    """Das aus einem Dokument extrahierte Angebot."""

    model_config = ConfigDict(extra="ignore")

    ist_mietangebot: bool = False
    objekt: str | None = None
    adresse: str | None = None
    plz: str | None = None
    ort: str | None = None
    anbieter: str | None = None       # Vermieter/Eigentümer bzw. dessen Makler
    empfaenger: str | None = None     # Mietinteressent
    datum: str | None = None          # ISO (JJJJ-MM-TT), wenn erkennbar
    flaeche_qm: float | None = None
    nutzungsart: str | None = None    # Logistik/Halle/Produktion/Büro/Freifläche
    optionen: list[AngebotsOption] = Field(default_factory=list)
    sicherheit: str | None = None
    indexierung: str | None = None
    eigenes_angebot: bool | None = None   # von K&P/Kromeich versandt?
    ist_vorlage: bool = False
    ist_eigenmiete: bool = False          # Kromeich-Büromiete
    ist_anlage: bool = False              # Anlagen-/Beiblatt ohne Konditionen
    confidence: float = 0.0
    begruendung: str = ""


class ComparableZeile(BaseModel):
    """Flache Report-Zeile: ein Angebot x eine Laufzeit-Option."""

    model_config = ConfigDict(extra="ignore")

    # Herkunft
    quelle: str = "drive"             # "propstack" | "drive"
    file_id: str                      # Drive-fileId bzw. Propstack-Unit-ID
    datei: str                        # Dateiname bzw. Objektbezeichnung
    quelle_link: str | None = None
    fundstellen: int = 1
    miete_feld: str | None = None     # Propstack: Feld, aus dem die Miete kam
    vermietet: bool | None = None     # Propstack: rented-Flag

    # Objekt
    objekt: str | None = None
    adresse: str | None = None
    plz: str | None = None
    ort: str | None = None
    region_key: str | None = None     # 2-stellige PLZ
    region_label: str | None = None
    zone_key: str | None = None       # 1-stellige PLZ
    zone_label: str | None = None

    # Parteien / Zeit
    anbieter: str | None = None
    empfaenger: str | None = None
    datum: str | None = None
    eigenes_angebot: bool | None = None

    # Konditionen (normalisiert)
    flaeche_qm: float | None = None
    nutzungsart: str | None = None
    laufzeit_monate: int | None = None
    kaltmiete_eur_qm: float | None = None
    nebenkosten_eur_qm: float | None = None
    mietfreie_monate: float | None = None
    effektivmiete_eur_qm: float | None = None
    sicherheit: str | None = None
    indexierung: str | None = None
    option_hinweis: str | None = None

    # Qualität
    normalisiert_aus_absolut: bool = False
    confidence: float = 0.0
    ausschluss_grund: str | None = None   # gesetzt = fließt nicht in die Statistik

    @property
    def verwertbar(self) -> bool:
        return self.ausschluss_grund is None and self.kaltmiete_eur_qm is not None


class RegionStats(BaseModel):
    """Vergleichsmieten einer Region: Median + Spanne + n (Task-Vorgabe)."""

    ebene: str                 # "leitregion" | "leitregion_einzel" | "zone" | "gesamt"
    key: str
    label: str
    # Flächenart (Halle/Lager, Büro, Mezzanine …). Hallen- und Büromieten
    # liegen in ganz verschiedenen Größenordnungen und dürfen nie in denselben
    # Median fallen – die Flächenart ist deshalb Teil des Gruppenschlüssels.
    nutzungsart: str = ""
    n: int = 0
    n_objekte: int = 0
    n_eigene: int = 0
    n_erhalten: int = 0
    n_propstack: int = 0
    n_drive: int = 0
    median_kaltmiete: float | None = None
    min_kaltmiete: float | None = None
    max_kaltmiete: float | None = None
    median_nebenkosten: float | None = None
    median_effektivmiete: float | None = None
    median_flaeche: float | None = None
    jüngstes_datum: str | None = None
    objekte: list[str] = Field(default_factory=list)


class KennzahlenZeile(BaseModel):
    """Eine Zeile der Kennzahlen-Tabelle (Marktbericht-Layout)."""

    label: str
    gruppe: str = ""
    # "position" | "zwischensumme" | "gesamtsumme" | "anteil"
    ebene: str = "position"
    n: int = 0
    n_standorte: int = 0
    median_jetzt: float | None = None
    median_vorher: float | None = None
    veraenderung_prozent: float | None = None   # bei Anteilen: Prozentpunkte
    min_kaltmiete: float | None = None
    max_kaltmiete: float | None = None
    median_nebenkosten: float | None = None
    ist_summe: bool = False
    ist_prozentwert: bool = False


class KennzahlenTabelle(BaseModel):
    """Kennzahlen einer Flächenart: Marktzeilen, Zwischensummen, Anteile."""

    flaechenart: str
    zeilen: list[KennzahlenZeile] = Field(default_factory=list)
    gesamt: KennzahlenZeile | None = None
    anteile: list[KennzahlenZeile] = Field(default_factory=list)


class DecisionRecord(BaseModel):
    """Eine JSONL-Zeile pro Dokument."""

    run_id: str
    verarbeitet_am: str
    file_id: str
    datei: str
    mime_type: str = ""
    quelle_link: str | None = None
    gefunden_via: str = ""
    fundstellen: int = 1
    aus_cache: bool = False
    uebersprungen: str | None = None   # Grund, wenn nicht extrahiert
    angebot: Mietangebot | None = None
    zeilen: int = 0
    fehler: str | None = None


class PropstackReport(BaseModel):
    """Zähler des Propstack-Zweigs – auch die Grundlage der Datenqualitäts-Aussage."""

    units_geladen: int = 0
    keine_mietobjekte: int = 0
    mit_miete: int = 0
    ohne_miete: int = 0
    preis_auf_anfrage: int = 0
    ohne_flaeche: int = 0
    flaeche_unplausibel: int = 0
    flaechenart_uebersprungen: int = 0   # Miete vorhanden, Flächenart nicht im Report
    aus_absolut_normalisiert: int = 0
    vermietet: int = 0
    miete_felder: dict[str, int] = Field(default_factory=dict)


class RunReport(BaseModel):
    quelle: str = ""
    propstack: PropstackReport = Field(default_factory=PropstackReport)
    dateien_gefunden: int = 0
    dateien_eindeutig: int = 0
    dateien_kopien_uebersprungen: int = 0
    format_uebersprungen: int = 0
    regel_uebersprungen: int = 0      # Vorlage/Eigenmiete/Anlage
    aus_cache: int = 0
    extrahiert: int = 0
    keine_mietangebote: int = 0
    versionen_uebersprungen: int = 0
    zeilen_gesamt: int = 0
    zeilen_verwertbar: int = 0
    zeilen_ausgeschlossen: int = 0
    regionen: int = 0
    slack_gepostet: bool = False
    pdf_erstellt: str | None = None
    fehler: list[str] = Field(default_factory=list)
