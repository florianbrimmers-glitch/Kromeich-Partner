from comparables_handler import normalize
from comparables_handler.models import AngebotsOption, Mietangebot

from .fixtures import doc, mileway_bergkamen, westcore_bitterfeld


# --- Ausschluss auf Dateinamen-Ebene (spart LLM-Calls) ---------------------
def test_kromeich_bueromiete_wird_ausgeschlossen():
    """Reale Datei: die eigene Büromiete liegt als 'Mietangebot' im Drive."""
    grund = normalize.datei_ausschluss("Mietangebot-Kromeich GmbH-2025-06_V1.pdf")
    assert grund is not None
    assert "Eigenmiete" in grund


def test_vorlagen_werden_ausgeschlossen():
    assert normalize.datei_ausschluss("Mietangebot Vorlage FvW.xlsx") is not None
    assert normalize.datei_ausschluss("Mietangebot Vorlage NEU.pdf") is not None


def test_anlagen_werden_ausgeschlossen():
    grund = normalize.datei_ausschluss("Anlagen Indikatives Mietangebot2_Patac.pdf")
    assert grund is not None
    assert "Anlage" in grund


def test_echtes_angebot_wird_nicht_ausgeschlossen():
    assert normalize.datei_ausschluss("260610_Sun Park_Brüninghoff_Mietangebot.pdf") is None
    assert normalize.datei_ausschluss("26-04-30 VIR21 Indikatives Mietangebot IMC Pro Logistics.pdf") is None


def test_vorlage_marker_nur_als_wortanfang():
    """'Musterhausen' o.Ä. darf kein Angebot aussortieren."""
    assert normalize.datei_ausschluss("Mietangebot Musterhausener Weg 4.pdf") is None


# --- Straßen-/Textnormalisierung -------------------------------------------
def test_strassenschreibweisen_sind_gleich():
    assert normalize.normalisiere_strasse("Hamborner Str. 12") == \
        normalize.normalisiere_strasse("Hamborner Straße 12")
    assert normalize.normalisiere_strasse("Zörbiger Strasse 8") == \
        normalize.normalisiere_strasse("Zörbiger Straße 8")


def test_hausnummer_bleibt_unterscheidend():
    assert normalize.normalisiere_strasse("Musterweg 7") != normalize.normalisiere_strasse("Musterweg 9")


# --- Effektivmiete ---------------------------------------------------------
def test_effektivmiete_glaettet_mietfreie_zeit():
    # 3 mietfreie Monate auf 60 Monate Laufzeit bei 4,58 €/m²
    assert normalize.effektivmiete(4.58, 60, 3) == 4.35


def test_effektivmiete_ohne_mietfreie_zeit_ist_kaltmiete():
    assert normalize.effektivmiete(4.58, 60, None) == 4.58
    assert normalize.effektivmiete(4.58, 60, 0) == 4.58


def test_effektivmiete_ohne_laufzeit_nicht_berechenbar():
    assert normalize.effektivmiete(4.58, None, 3) is None


def test_effektivmiete_mietfrei_laenger_als_laufzeit():
    """Unsinnige Kombination -> None statt negativer Miete."""
    assert normalize.effektivmiete(4.58, 12, 24) is None


# --- Normalisierung auf Zeilen --------------------------------------------
def test_referenzfall_mileway():
    zeilen = normalize.zu_zeilen(doc(), mileway_bergkamen())
    assert len(zeilen) == 1
    zeile = zeilen[0]
    assert zeile.kaltmiete_eur_qm == 4.58
    assert zeile.nebenkosten_eur_qm == 2.15
    assert zeile.region_key == "59"
    assert "Bergkamen" in zeile.region_label
    assert zeile.zone_key == "5"
    assert zeile.verwertbar


def test_laufzeitstaffel_ergibt_eine_zeile_je_option():
    """Task-Vorgabe: eine Zeile pro Laufzeit-Option."""
    zeilen = normalize.zu_zeilen(doc(name="Sun Park.pdf"), westcore_bitterfeld())
    assert len(zeilen) == 3
    assert [z.kaltmiete_eur_qm for z in zeilen] == [4.50, 4.30, 4.05]
    assert [z.laufzeit_monate for z in zeilen] == [60, 84, 120]
    assert all(z.region_key == "06" for z in zeilen)
    assert all(z.verwertbar for z in zeilen)


def test_absolute_miete_wird_auf_qm_umgerechnet():
    """Task-Regel: absolute Mieten auf €/m² umrechnen."""
    angebot = mileway_bergkamen()
    angebot.flaeche_qm = 2500.0
    angebot.optionen = [AngebotsOption(laufzeit_monate=60, kaltmiete_absolut_eur=12500.0)]
    zeile = normalize.zu_zeilen(doc(), angebot)[0]
    assert zeile.kaltmiete_eur_qm == 5.0
    assert zeile.normalisiert_aus_absolut is True
    assert zeile.verwertbar


def test_absolute_miete_ohne_flaeche_bleibt_unverwertbar():
    angebot = mileway_bergkamen()
    angebot.flaeche_qm = None
    angebot.optionen = [AngebotsOption(laufzeit_monate=60, kaltmiete_absolut_eur=12500.0)]
    zeile = normalize.zu_zeilen(doc(), angebot)[0]
    assert zeile.kaltmiete_eur_qm is None
    assert not zeile.verwertbar


def test_unplausible_kaltmiete_wird_ausgeschlossen():
    """4,58 €/m² vs. 458 €/m² – ein Komma-Fehler darf den Median nicht kippen."""
    angebot = mileway_bergkamen()
    angebot.optionen = [AngebotsOption(laufzeit_monate=60, kaltmiete_eur_qm=458.0)]
    zeile = normalize.zu_zeilen(doc(), angebot)[0]
    assert not zeile.verwertbar
    assert "außerhalb" in zeile.ausschluss_grund


def test_unplausible_nebenkosten_verwerfen_nur_das_feld():
    """Die Kaltmiete bleibt verwertbar, wenn nur die NK unsinnig sind."""
    angebot = mileway_bergkamen()
    angebot.optionen = [AngebotsOption(
        laufzeit_monate=60, kaltmiete_eur_qm=4.58, nebenkosten_eur_qm=215.0,
    )]
    zeile = normalize.zu_zeilen(doc(), angebot)[0]
    assert zeile.nebenkosten_eur_qm is None
    assert zeile.kaltmiete_eur_qm == 4.58
    assert zeile.verwertbar


def test_ohne_plz_keine_region():
    angebot = mileway_bergkamen()
    angebot.plz = None
    zeile = normalize.zu_zeilen(doc(), angebot)[0]
    assert not zeile.verwertbar
    assert "PLZ" in zeile.ausschluss_grund


def test_plz_wird_aus_freitext_gezogen():
    angebot = mileway_bergkamen()
    angebot.plz = "D-59192 Bergkamen"
    zeile = normalize.zu_zeilen(doc(), angebot)[0]
    assert zeile.plz == "59192"
    assert zeile.region_key == "59"


def test_angebot_ohne_optionen_ergibt_eine_unverwertbare_zeile():
    """Kein stiller Verlust: das Dokument bleibt mit Grund im Datensatz."""
    angebot = mileway_bergkamen()
    angebot.optionen = []
    zeilen = normalize.zu_zeilen(doc(), angebot)
    assert len(zeilen) == 1
    assert not zeilen[0].verwertbar


# --- eigenes vs. erhaltenes Angebot ---------------------------------------
def test_eigenes_angebot_wird_am_anbieter_erkannt():
    angebot = mileway_bergkamen()
    angebot.eigenes_angebot = None
    angebot.anbieter = "Kromeich & Partner GmbH"
    assert normalize.ist_eigenes_angebot(angebot) is True


def test_fremdes_angebot_bleibt_unmarkiert_wenn_unklar():
    angebot = mileway_bergkamen()
    angebot.eigenes_angebot = None
    angebot.anbieter = "Mileway"
    assert normalize.ist_eigenes_angebot(angebot) is None


# --- Ausschluss aus der Extraktion ----------------------------------------
def test_niedrige_confidence_wird_ausgeschlossen():
    angebot = mileway_bergkamen()
    angebot.confidence = 0.2
    grund = normalize.angebot_ausschluss(angebot)
    assert grund is not None
    assert "Confidence" in grund


def test_kein_mietangebot_wird_ausgeschlossen():
    assert normalize.angebot_ausschluss(Mietangebot(ist_mietangebot=False, confidence=0.9)) == "kein Mietangebot"


def test_vom_llm_erkannte_eigenmiete_wird_ausgeschlossen():
    angebot = mileway_bergkamen()
    angebot.ist_eigenmiete = True
    assert "Eigenmiete" in normalize.angebot_ausschluss(angebot)
