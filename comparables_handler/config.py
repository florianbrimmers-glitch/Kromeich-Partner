from __future__ import annotations

import os

CLAUDE_MODEL = "claude-opus-4-8"

# --- Datenquelle ------------------------------------------------------------
# Propstack ist die primäre Quelle: dort werden die Mieten gepflegt, die Daten
# sind strukturiert und brauchen keine LLM-Extraktion. Der Drive-Pfad liefert
# ergänzend die ERHALTENEN Fremdangebote (Mileway, HIH, Westcore …), die in
# Propstack nicht stehen, weil sie keine eigenen Mandate sind.
QUELLE_PROPSTACK = "propstack"
QUELLE_DRIVE = "drive"
QUELLE_BEIDE = "beide"


def quelle() -> str:
    wert = os.environ.get("QUELLE", QUELLE_PROPSTACK).strip().lower()
    if wert not in (QUELLE_PROPSTACK, QUELLE_DRIVE, QUELLE_BEIDE):
        raise RuntimeError(
            f"QUELLE={wert!r} unbekannt – erlaubt: "
            f"{QUELLE_PROPSTACK}, {QUELLE_DRIVE}, {QUELLE_BEIDE}"
        )
    return wert


def nutzt_propstack() -> bool:
    return quelle() in (QUELLE_PROPSTACK, QUELLE_BEIDE)


def nutzt_drive() -> bool:
    return quelle() in (QUELLE_DRIVE, QUELLE_BEIDE)

# --- Google-Drive-Datenbasis -------------------------------------------------
# Gefunden am 12.08.2026 per Drive-Suche. Zwei "03. Leasing"-Ordner (eigenes
# Shared Drive + ein von felix.kern geteilter) und zwei "Mietangebote"-Ordner.
# Die Ordner-IDs sind nur SAATGUT für die Rekursion – der Titel-Scan
# ("Mietangebot" im Dateinamen) findet zusätzlich alles, was woanders liegt.
SEED_FOLDER_IDS = (
    "1oHcqgQVhMu2_54p8PxH2vEWfWHgXbwD2",  # 03. Leasing (Shared Drive)
    "13fQQg1EbnE58iHREJKgIK_esIT7HFVdh",  # 03. Leasing (geteilt, felix.kern)
    "15BorjO7bV8DLOC_lQkL57LelcYvGBYV6",  # Mietangebote
    "1ykTBz0p_EhVSND2apNhp8BPvrfvgFRgP",  # Mietangebote
)

# Titel-Suchbegriffe (Drive-Suche ist case-insensitive)
TITLE_TERMS = ("Mietangebot",)

# Wie tief die Ordner-Rekursion läuft (Schutz gegen Endlos-Bäume)
MAX_FOLDER_DEPTH = 6

# Drive-MIME-Typen, aus denen wir Konditionen lesen können
MIME_PDF = "application/pdf"
MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_SHORTCUT = "application/vnd.google-apps.shortcut"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_GDOC = "application/vnd.google-apps.document"
MIME_GSLIDES = "application/vnd.google-apps.presentation"
MIME_GSHEET = "application/vnd.google-apps.spreadsheet"

SUPPORTED_MIMETYPES = (
    MIME_PDF, MIME_DOCX, MIME_PPTX, MIME_XLSX,
    MIME_GDOC, MIME_GSLIDES, MIME_GSHEET,
)

# Claude nimmt PDFs direkt als Dokument-Block (auch Scans). Limit der API: 32 MB.
MAX_PDF_BYTES = 30_000_000
MAX_TEXT_CHARS = 60_000

# --- Ausschlussregeln (Task-Vorgabe) ---------------------------------------
# Eigene Vorlagen: Dateiname enthält einen dieser Begriffe.
VORLAGE_MARKER = ("vorlage", "muster", "template", "blanko", "entwurf leer")
# Kromeich-Büromiete: die eigene Büromiete ist kein Marktangebot.
# Trifft z.B. "Mietangebot-Kromeich GmbH-2025-06_V1.pdf" (monatliche Rechnung).
EIGENMIETE_MARKER = ("kromeich gmbh",)
# Anlagen-/Beiblatt-Dateien tragen keine eigenen Konditionen.
ANLAGEN_MARKER = ("anlage", "anlagen", "beiblatt")

# Anbieter-Namen, die ein EIGENES (von K&P versandtes) Angebot markieren
EIGENE_ANBIETER_MARKER = ("kromeich", "k&p", "kromeich & partner")

# --- Plausibilität (Ausreißer fliegen mit Grund raus) ----------------------
# Untergrenze für Halle/Lager. Bei 1,00 rutschten Platzhalter-Werte durch:
# "Stettiner Straße 2, Neuss" trug 1,00 €/m², während dieselbe Adresse andere
# Einheiten mit 3,00 führt. Unter 2,50 €/m² gibt es für Hallen-/Lagerflächen
# keinen echten Markt – solche Werte sind Platzhalter oder Tippfehler.
KALTMIETE_MIN_EUR_QM = 2.5
KALTMIETE_MAX_EUR_QM = 25.0
NEBENKOSTEN_MIN_EUR_QM = 0.1
NEBENKOSTEN_MAX_EUR_QM = 6.0
FLAECHE_MIN_QM = 100.0
FLAECHE_MAX_QM = 500_000.0
LAUFZEIT_MIN_MONATE = 6
LAUFZEIT_MAX_MONATE = 360

CONFIDENCE_THRESHOLD = 0.5

# Ab wie vielen Datenpunkten ein Median als belastbar ausgewiesen wird.
# Regionen darunter werden NICHT unterdrückt, sondern als Einzelwerte
# ausgewiesen: bekannte Mieten sind rar (Vermieter veröffentlichen sie nicht),
# und ein einzelner belegter Wert ist im Kundengespräch wertvoll – er darf nur
# nicht als "Median" auftreten.
MIN_N_LEITREGION = 3

# --- Marktgebiete für die Kennzahlen-Tabelle --------------------------------
# Gliederung wie in den Marktberichten der großen Häuser: die bedeutenden
# Logistikmärkte einzeln, das Ruhrgebiet als eigene Gruppe, alles Übrige
# gebündelt – je mit Zwischensumme.
#
# ACHTUNG: Marktgrenzen sind eine fachliche Festlegung, keine Naturkonstante.
# Die Zuordnung unten folgt den PLZ-Leitregionen und ist bewusst hier
# zentralisiert, damit K&P sie anpassen kann (z.B. ob Krefeld (47) zum
# Ruhrgebiet oder zu Düsseldorf zählt, oder Aachen (52) zu Köln).
MARKTGEBIETE_TOP = (
    ("Berlin", ("10", "12", "13", "14")),
    ("Düsseldorf", ("40", "41")),
    ("Frankfurt/Rhein-Main", ("60", "61", "63", "64", "65")),
    ("Hamburg", ("20", "21", "22", "25")),
    ("Köln", ("50", "51")),
    ("Leipzig/Halle", ("04", "06")),
    ("München", ("80", "81", "82", "85")),
)
MARKTGEBIET_RUHR = ("Ruhrgebiet", ("44", "45", "46", "47", "58", "59"))

# Gruppenbezeichnungen der Tabelle
GRUPPE_TOP = "Bedeutende Logistikmärkte"
GRUPPE_SONSTIGE = "Sonstige Standorte"
LABEL_UEBRIGE = "Übrige Logistikregionen"

# --- Aggregationsbasis ------------------------------------------------------
# "standort": je Adresse EIN Wert (Median ihrer Einheiten) – so zählt ein
#   Multi-Unit-Objekt einmal und nicht 14-mal. Gemessen am 13.08.2026: die 10
#   größten Standorte stellten 21 % aller Datenpunkte; in Berlin verschob das
#   den Median um 1,67 €/m². Für eine Marktaussage ist der Standort die
#   richtige Einheit.
# "einheit": jede vermietbare Einheit zählt einzeln – relevant, wenn die Frage
#   lautet "was zahlt ein Mieter für eine Einheit", nicht "wie hoch ist das
#   Marktniveau".
AGGREGATION_STANDORT = "standort"
AGGREGATION_EINHEIT = "einheit"
AGGREGATION_STANDARD = AGGREGATION_STANDORT


def aggregation() -> str:
    wert = os.environ.get("AGGREGATION", AGGREGATION_STANDARD).strip().lower()
    if wert not in (AGGREGATION_STANDORT, AGGREGATION_EINHEIT):
        raise RuntimeError(
            f"AGGREGATION={wert!r} unbekannt – erlaubt: "
            f"{AGGREGATION_STANDORT}, {AGGREGATION_EINHEIT}"
        )
    return wert


# Spitzenmiete: oberes Perzentil statt des Maximums. Ein einzelner Ausreißer
# soll das Spitzenniveau nicht bestimmen – und das Maximum ist über die
# Spanne-Spalte ohnehin sichtbar. 1.0 ergibt das echte Maximum.
SPITZENMIETE_PERZENTIL = 0.95

# Wie viele Monate zurück der Vergleichswert der Veränderungsspalte liegt.
# 12 = Vorjahresvergleich; der nächstgelegene vorhandene Snapshot gewinnt.
VERGLEICH_MONATE = 12
# Toleranz bei der Snapshot-Suche (Monate)
VERGLEICH_TOLERANZ_MONATE = 3


# --- Slack ------------------------------------------------------------------
# Kein eigener Leasing-/Comparables-Kanal vorhanden (Stand 12.08.2026), daher
# #objekte als Ziel – dort läuft die operative Objekt-Kommunikation und der
# Bot ist bereits Mitglied. Per COMPARABLES_CHANNEL umstellbar.
DEFAULT_CHANNEL = "C07GH7AN80J"  # #objekte


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("true", "1", "yes")


def dry_run() -> bool:
    """Default true (sicher): Report wird gebaut und geloggt, aber nicht gepostet."""
    return _env_bool("DRY_RUN", "true")


def no_write() -> bool:
    """Reiner Lese-/Loglauf: kein Slack-Post, keine Dateien nach außen."""
    return _env_bool("NO_WRITE", "false")


def slack_channel() -> str:
    return os.environ.get("COMPARABLES_CHANNEL") or DEFAULT_CHANNEL


def slack_bot_token() -> str:
    return os.environ["SLACK_BOT_TOKEN"]


def anthropic_api_key() -> str:
    return os.environ["ANTHROPIC_API_KEY"]


def decision_log_path() -> str:
    return os.environ.get("DECISION_LOG_PATH", "comparables_decisions.jsonl")


def dataset_path() -> str:
    """Flache Comparables-Tabelle des Laufs (CSV, als Actions-Artefakt)."""
    return os.environ.get("DATASET_PATH", "comparables_dataset.csv")


def cache_path() -> str:
    """Extraktions-Cache: fileId+modifiedTime -> Extraktion.

    Spart LLM-Calls über Monate hinweg; unveränderte Dokumente werden nicht
    erneut an Claude geschickt. Leerer Wert schaltet den Cache ab.
    """
    return os.environ.get("EXTRACTION_CACHE_PATH", "comparables_cache.jsonl")


def pdf_path() -> str:
    return os.environ.get("PDF_PATH", "comparables_report.pdf")


def snapshot_path() -> str:
    """Zeitreihe der Monats-Mediane – Basis der Veränderungsspalte.

    Muss die Läufe ÜBERDAUERN, sonst gibt es nie einen Periodenvergleich
    (siehe README, Abschnitt "Zeitreihe").
    """
    return os.environ.get("SNAPSHOT_PATH", "comparables_snapshots.json")


def make_pdf() -> bool:
    """K&P-PDF erzeugen (Task: 'auf Abruf für Kundengespräche')."""
    return _env_bool("MAKE_PDF", "false")


def max_documents() -> int:
    """Obergrenze extrahierter Dokumente pro Lauf (0 = unbegrenzt).

    Nur als Kostenbremse/Testhilfe – im Normalbetrieb 0, damit nie still
    ein Teil der Datenbasis wegfällt.
    """
    return int(os.environ.get("MAX_DOCUMENTS", "0"))


def kp_design_dir() -> str:
    """Verzeichnis des kp-design-Skills (Schriften für das PDF).

    Fehlt es, fällt das PDF auf reportlab-Standardschriften zurück.
    """
    return os.environ.get(
        "KP_DESIGN_DIR",
        os.path.expanduser("~/.claude/skills/synced/kp-design"),
    )


# --- Propstack --------------------------------------------------------------
PROPSTACK_BASE_URL = "https://api.propstack.de/v1"
PROPSTACK_MAX_ATTEMPTS = 4

# Seitengröße. Am 12.08.2026 gegen die echte API gemessen
# (scripts/propstack_miet_audit.py):
#     per=100        -> 100 Einheiten   ✅
#     per_page=100   ->  20 Einheiten   ❌ (wird ignoriert)
#     ohne Parameter ->  20 Einheiten
# Der Listen-Endpoint respektiert also `per`, NICHT `per_page`. Der bestehende
# objekte_handler liegt damit richtig. Der Nebenbefund "/units liefert nur 20"
# aus der Asana-Aufgabe entstand durch einen Aufruf ohne Seitengröße.
# Wir schicken beide Namen; `per` gewinnt.
PROPSTACK_PER_PAGE = 100
PROPSTACK_MAX_PAGES = 200          # Schutz gegen Endlos-Paginierung

# Mietobjekte erkennen
MARKETING_TYPES_MIETE = ("RENT", "RENT_AND_BUY", "MIETE")


# --- Mieten je Flächenart ---------------------------------------------------
# K&P pflegt die Mieten NICHT in den Propstack-Standardfeldern, sondern in
# Custom Fields – und zwar GETRENNT JE FLÄCHENART, bereits als €/m²/Monat
# (gemessen 12.08.2026 über 1.978 Mietobjekte).
#
# Das ist fachlich entscheidend: Hallenflächen liegen bei 4-8 €/m², Büro bei
# 12-14 €/m². Beides in einen Median zu werfen ergäbe eine Zahl, die keinen
# Markt beschreibt. Deshalb ist die Flächenart Teil des Aggregations-
# schlüssels und jede Fläche eine eigene Report-Zeile.
#
# Reihenfolge je Art: interner Wert zuerst (aus Mandaten/Beratung, also die
# tatsächlich bekannte Kondition), dann der ausgeschriebene Mietpreis, dann
# die "ab"-Angabe der Flächenaufstellung.
class Flaechenart:
    """Eine Flächenart mit ihren Miet-, NK- und Flächenfeldern."""

    def __init__(self, name, miete_felder, miete_bis_felder=(), nk_felder=(), flaeche_felder=()):
        self.name = name
        self.miete_felder = miete_felder
        self.miete_bis_felder = miete_bis_felder
        self.nk_felder = nk_felder
        self.flaeche_felder = flaeche_felder


FLAECHENARTEN = (
    Flaechenart(
        "Halle/Lager",
        miete_felder=("intern_mietpreis_hallenflache", "mietpreis_hallenflache",
                      "lagerflache_miete_m_von"),
        miete_bis_felder=("lagerflache_miete_m_bis",),
        nk_felder=("lagerflache_nebenkosten_m_von", "lagerflache_nebenkosten_m_bis"),
        flaeche_felder=("lagerflache", "lagerflache_gesamt"),
    ),
    Flaechenart(
        "Büro",
        miete_felder=("intern_mietpreis_buro", "mietpreis_buroflache", "buroflache_miete_m_von"),
        miete_bis_felder=("buroflache_miete_m_bis",),
        nk_felder=("buroflache_nebenkosten_m_von", "buroflache_nebenkosten_m_bis"),
        flaeche_felder=("buroflache", "buroflache_gesamt"),
    ),
    Flaechenart(
        "Mezzanine",
        miete_felder=("intern_mietpreis_mezzanine", "mietpreis_mezzanine",
                      "mezzanineflache_miete_m_von"),
        miete_bis_felder=("mezzanineflache_miete_m_bis",),
        flaeche_felder=("mezzanineflache", "mezzanineflache_gesamt"),
    ),
    Flaechenart(
        "Servicefläche",
        miete_felder=("serviceflache_miete_m_von",),
        miete_bis_felder=("serviceflache_miete_m_bis",),
        flaeche_felder=("serviceflache_gesamt",),
    ),
    Flaechenart(
        "Freifläche",
        miete_felder=("freiflache_miete_m_von",),
        miete_bis_felder=("freiflache_miete_m_bis",),
        flaeche_felder=("freiflache_gesamt",),
    ),
    Flaechenart(
        "Keller/Archiv",
        miete_felder=("keller_archivflache_miete_m_von",),
        flaeche_felder=(),
    ),
)

# Welche Flächenarten in den Report gehen. Standard: nur Halle/Lager – das ist
# der Markt, um den es geht. Büro, Mezzanine, Service- und Keller/Archivfläche
# werden nicht ausgewertet (auf Wunsch 13.08.2026). Sie bleiben in
# FLAECHENARTEN definiert und lassen sich per FLAECHENARTEN-Env oder durch
# Ergänzen dieser Liste jederzeit wieder aufnehmen.
FLAECHENARTEN_STANDARD = ("Halle/Lager",)

# Freitext-Nutzungsarten aus den Drive-Angeboten auf die Flächenarten mappen,
# damit Drive- und Propstack-Zeilen im selben Abschnitt landen (das LLM
# schreibt "Logistik", Propstack "Halle/Lager").
NUTZUNGSART_SYNONYME = {
    "logistik": "Halle/Lager",
    "logistikhalle": "Halle/Lager",
    "halle": "Halle/Lager",
    "hallenflaeche": "Halle/Lager",
    "hallenfläche": "Halle/Lager",
    "lager": "Halle/Lager",
    "lagerflaeche": "Halle/Lager",
    "lagerfläche": "Halle/Lager",
    "lagerhalle": "Halle/Lager",
    "buero": "Büro",
    "büro": "Büro",
    "bueroflaeche": "Büro",
    "bürofläche": "Büro",
    "mezzanine": "Mezzanine",
}


def ausgewertete_flaechenarten() -> tuple[str, ...]:
    """Flächenarten des Reports; per FLAECHENARTEN überschreibbar.

    Beispiel: FLAECHENARTEN="Halle/Lager,Büro"
    """
    roh = os.environ.get("FLAECHENARTEN", "").strip()
    if not roh:
        return FLAECHENARTEN_STANDARD
    return tuple(teil.strip() for teil in roh.split(",") if teil.strip())


# BEWUSST NICHT ausgewertet – das sind Preise pro Stellplatz, nicht pro m².
# Sie würden mit Werten von 20-70 € jeden €/m²-Median zerstören.
STELLPLATZ_FELDER_IGNORIERT = (
    "stellplatzmiete", "lkw_stellplatzmiete", "preis_aussen_stellpl",
    "preis_innen_stellpl", "parking_space_price",
)

# BEWUSST NICHT ausgewertet – die Standardfelder sind bei K&P kaum gepflegt
# (base_rent: 6 von 1.978) und inkonsistent: sie enthalten teils €/m² (6,00),
# teils absolute Monatsmieten (19.848). Ohne Unterscheidungsmerkmal ist das
# nicht sicher normalisierbar, für 6 Datenpunkte nicht das Risiko wert.
STANDARDFELDER_IGNORIERT = ("base_rent", "price", "price_per_sqm", "rent_price")

# Fallback-Flächen, wenn die Flächenart keine eigene Fläche trägt. Reihenfolge
# nach gemessener Belegung: property_space_value 63 %, total_floor_space 63 %,
# industrial_area 34 %, usable_floor_space 12 %.
# plot_area ist BEWUSST NICHT dabei – das Grundstück ist keine Mietfläche.
FLAECHE_FELDER = (
    "property_space_value", "total_floor_space", "industrial_area", "usable_floor_space",
)

PROPSTACK_KEY_ENV_NAMES = ("PROPSTACK_KEY_OBJEKTE", "PROPSTACK_API_KEY")


def propstack_key_env_name() -> str | None:
    for name in PROPSTACK_KEY_ENV_NAMES:
        if os.environ.get(name, "").strip():
            return name
    return None


def propstack_key() -> str:
    name = propstack_key_env_name()
    if not name:
        raise RuntimeError(
            "Kein Propstack-Key gefunden. Eines dieser Secrets füllen "
            f"({', '.join(PROPSTACK_KEY_ENV_NAMES)})."
        )
    return os.environ[name].strip()


# --- Google-Drive-Zugang ----------------------------------------------------
# Muster wie src/gmail_client.py: Client-ID/Secret + Refresh-Token.
# ACHTUNG: Die bestehenden GOOGLE_REFRESH_TOKEN* sind auf gmail.readonly
# ausgestellt und reichen für Drive NICHT. Deshalb zuerst ein eigenes
# Drive-Token, dann Fallback (funktioniert nur, wenn dieses Token den
# drive.readonly-Scope mitträgt).
DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)

DRIVE_REFRESH_TOKEN_ENV_NAMES = (
    "GOOGLE_REFRESH_TOKEN_DRIVE",
    "GOOGLE_DRIVE_REFRESH_TOKEN",
    "GOOGLE_REFRESH_TOKEN",
)


def drive_refresh_token_env_name() -> str | None:
    for name in DRIVE_REFRESH_TOKEN_ENV_NAMES:
        if os.environ.get(name, "").strip():
            return name
    return None


def drive_refresh_token() -> str:
    name = drive_refresh_token_env_name()
    if not name:
        raise RuntimeError(
            "Kein Google-Refresh-Token für Drive gefunden. Eines dieser Secrets "
            f"füllen ({', '.join(DRIVE_REFRESH_TOKEN_ENV_NAMES)}) – das Token muss "
            "den Scope drive.readonly tragen (siehe comparables_handler/README.md)."
        )
    return os.environ[name].strip()


def google_client_id() -> str:
    return os.environ["GOOGLE_CLIENT_ID"]


def google_client_secret() -> str:
    return os.environ["GOOGLE_CLIENT_SECRET"]
