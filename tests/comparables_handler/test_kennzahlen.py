"""Kennzahlen-Tabelle im Marktbericht-Layout + Periodenvergleich."""

from comparables_handler import config, kennzahlen, marktgebiete, snapshots
from comparables_handler.models import ComparableZeile


def _zeile(plz: str, miete: float, art="Halle/Lager", adresse=None, **kw) -> ComparableZeile:
    from comparables_handler import regions
    leit = regions.leitregion(plz)
    zon = regions.zone(plz)
    return ComparableZeile(
        quelle="propstack", file_id=f"{plz}-{miete}", datei="Testobjekt",
        objekt="Testobjekt", adresse=adresse or f"Musterweg {miete}",
        plz=plz, region_key=leit[0], region_label=leit[1],
        zone_key=zon[0], zone_label=zon[1],
        nutzungsart=art, kaltmiete_eur_qm=miete, **kw,
    )


# --- Marktgebiets-Zuordnung ------------------------------------------------
def test_top_maerkte_werden_erkannt():
    assert marktgebiete.markt("40") == "Düsseldorf"
    assert marktgebiete.markt("60") == "Frankfurt/Rhein-Main"
    assert marktgebiete.markt("04") == "Leipzig/Halle"
    assert marktgebiete.markt("80") == "München"


def test_ruhrgebiet_ist_eigene_gruppe():
    """Wie in den Marktberichten: das Ruhrgebiet steht unter 'sonstige'."""
    assert marktgebiete.markt("44") == "Ruhrgebiet"
    assert marktgebiete.gruppe("44") == config.GRUPPE_SONSTIGE
    assert marktgebiete.gruppe("40") == config.GRUPPE_TOP


def test_unbekannte_region_wird_gesammelt():
    assert marktgebiete.markt("99") is None
    assert marktgebiete.zeilen_label("99") == config.LABEL_UEBRIGE
    assert marktgebiete.gruppe("99") == config.GRUPPE_SONSTIGE


def test_keine_region_faellt_in_die_sammelzeile():
    assert marktgebiete.zeilen_label(None) == config.LABEL_UEBRIGE


# --- Tabellenaufbau --------------------------------------------------------
def test_gruppen_zwischensummen_und_gesamt():
    zeilen = [
        _zeile("40213", 6.00), _zeile("40468", 6.50),      # Düsseldorf
        _zeile("60313", 7.00),                              # Frankfurt
        _zeile("44145", 5.00), _zeile("45143", 5.50),      # Ruhrgebiet
        _zeile("99084", 4.00),                              # übrige
    ]
    t = kennzahlen.baue_tabelle(zeilen, "Halle/Lager")

    labels = [z.label for z in t.zeilen]
    assert "Düsseldorf" in labels
    assert "Frankfurt/Rhein-Main" in labels
    assert "Ruhrgebiet" in labels
    assert config.LABEL_UEBRIGE in labels
    assert f"{config.GRUPPE_TOP} gesamt" in labels
    assert f"{config.GRUPPE_SONSTIGE} gesamt" in labels

    top = next(z for z in t.zeilen if z.label == f"{config.GRUPPE_TOP} gesamt")
    assert top.n == 3                     # Düsseldorf 2 + Frankfurt 1
    assert top.median_jetzt == 6.50       # Median aus 6,00 / 6,50 / 7,00

    sonstige = next(z for z in t.zeilen if z.label == f"{config.GRUPPE_SONSTIGE} gesamt")
    assert sonstige.n == 3
    assert t.gesamt.n == 6


def test_median_summiert_sich_nicht():
    """n addiert sich über die Gruppen, der Median wird neu berechnet."""
    zeilen = [_zeile("40213", 4.00), _zeile("40468", 10.00)]
    t = kennzahlen.baue_tabelle(zeilen, "Halle/Lager")
    assert t.gesamt.n == 2
    assert t.gesamt.median_jetzt == 7.00        # nicht 14,00


def test_reihenfolge_der_top_maerkte_ist_fest():
    """Die Tabelle soll monatlich gleich aussehen, nicht nach Datenmenge springen."""
    zeilen = [_zeile("80331", 9.0), _zeile("10115", 7.0), _zeile("20095", 8.0)]
    t = kennzahlen.baue_tabelle(zeilen, "Halle/Lager")
    positionen = [z.label for z in t.zeilen if z.ebene == "position"]
    assert positionen == ["Berlin", "Hamburg", "München"]


def test_markt_ohne_daten_erscheint_nicht_als_leerzeile():
    t = kennzahlen.baue_tabelle([_zeile("40213", 6.0)], "Halle/Lager")
    assert [z.label for z in t.zeilen if z.ebene == "position"] == ["Düsseldorf"]


def test_nur_die_gewaehlte_flaechenart_zaehlt():
    zeilen = [_zeile("40213", 6.00), _zeile("40213", 12.00, art="Büro")]
    halle = kennzahlen.baue_tabelle(zeilen, "Halle/Lager")
    buero = kennzahlen.baue_tabelle(zeilen, "Büro")
    assert halle.gesamt.n == 1 and halle.gesamt.median_jetzt == 6.00
    assert buero.gesamt.n == 1 and buero.gesamt.median_jetzt == 12.00


def test_ausgeschlossene_zeilen_gehen_nicht_ein():
    schlecht = _zeile("40213", 6.0)
    schlecht.ausschluss_grund = "Testgrund"
    t = kennzahlen.baue_tabelle([_zeile("40468", 5.0), schlecht], "Halle/Lager")
    assert t.gesamt.n == 1


def test_standorte_werden_getrennt_gezaehlt():
    zeilen = [
        _zeile("40213", 6.0, adresse="Hauptstraße 1"),
        _zeile("40213", 6.5, adresse="Hauptstraße 1"),   # gleiche Adresse
        _zeile("40213", 7.0, adresse="Nebenweg 2"),
    ]
    t = kennzahlen.baue_tabelle(zeilen, "Halle/Lager")
    duesseldorf = next(z for z in t.zeilen if z.label == "Düsseldorf")
    assert duesseldorf.n == 3
    assert duesseldorf.n_standorte == 2


# --- Periodenvergleich -----------------------------------------------------
def test_veraenderung_gegen_vergleichs_snapshot():
    vergleich = {"stand": "2025-08", "werte": {
        snapshots.schluessel("Halle/Lager", "Düsseldorf"): 5.00,
    }}
    t = kennzahlen.baue_tabelle([_zeile("40213", 6.00)], "Halle/Lager", vergleich)
    d = next(z for z in t.zeilen if z.label == "Düsseldorf")
    assert d.median_vorher == 5.00
    assert d.veraenderung_prozent == 20.0      # 5,00 -> 6,00


def test_ohne_vergleichswert_bleibt_die_spalte_leer():
    """Keine erfundene Basis: lieber '–' als eine Zahl ohne Grundlage."""
    t = kennzahlen.baue_tabelle([_zeile("40213", 6.00)], "Halle/Lager", None)
    d = next(z for z in t.zeilen if z.label == "Düsseldorf")
    assert d.median_vorher is None
    assert d.veraenderung_prozent is None


def test_negative_veraenderung():
    vergleich = {"stand": "2025-08", "werte": {
        snapshots.schluessel("Halle/Lager", "Düsseldorf"): 8.00,
    }}
    t = kennzahlen.baue_tabelle([_zeile("40213", 6.00)], "Halle/Lager", vergleich)
    assert next(z for z in t.zeilen if z.label == "Düsseldorf").veraenderung_prozent == -25.0


# --- Abgeleitete Anteile ---------------------------------------------------
def test_anteile_werden_berechnet():
    zeilen = [
        _zeile("40213", 6.0, miete_feld="custom_fields.intern_mietpreis_hallenflache",
               vermietet=True, nebenkosten_eur_qm=1.0),
        _zeile("40468", 6.5, miete_feld="custom_fields.mietpreis_hallenflache",
               vermietet=False),
        _zeile("40474", 7.0, miete_feld="custom_fields.lagerflache_miete_m_von",
               vermietet=False, nebenkosten_eur_qm=1.2),
        _zeile("40476", 7.5, miete_feld="custom_fields.intern_mietpreis_hallenflache",
               vermietet=False),
    ]
    t = kennzahlen.baue_tabelle(zeilen, "Halle/Lager")
    nach_label = {a.label: a for a in t.anteile}
    assert nach_label[kennzahlen.ANTEIL_INTERN].median_jetzt == 50.0
    assert nach_label[kennzahlen.ANTEIL_VERMIETET].median_jetzt == 25.0
    assert nach_label[kennzahlen.ANTEIL_MIT_NK].median_jetzt == 50.0
    assert all(a.ist_prozentwert for a in t.anteile)


def test_anteile_veraendern_sich_in_prozentpunkten():
    """Wie im Marktbericht: '-2,7 %-Pkte.', nicht relativ."""
    vergleich = {"stand": "2025-08", "werte": {
        snapshots.schluessel("Halle/Lager", kennzahlen.ANTEIL_VERMIETET): 30.0,
    }}
    zeilen = [_zeile("40213", 6.0, vermietet=True), _zeile("40468", 6.5, vermietet=False),
              _zeile("40474", 7.0, vermietet=False), _zeile("40476", 7.5, vermietet=False)]
    t = kennzahlen.baue_tabelle(zeilen, "Halle/Lager", vergleich)
    anteil = next(a for a in t.anteile if a.label == kennzahlen.ANTEIL_VERMIETET)
    assert anteil.median_jetzt == 25.0
    assert anteil.veraenderung_prozent == -5.0     # Prozentpunkte


# --- Snapshot-Werte --------------------------------------------------------
def test_snapshot_werte_enthalten_zeilen_summen_und_anteile():
    t = kennzahlen.baue_tabelle([_zeile("40213", 6.0), _zeile("44145", 5.0)], "Halle/Lager")
    werte = kennzahlen.snapshot_werte([t])
    assert werte[snapshots.schluessel("Halle/Lager", "Düsseldorf")] == 6.0
    assert werte[snapshots.schluessel("Halle/Lager", "Ruhrgebiet")] == 5.0
    assert werte[snapshots.schluessel("Halle/Lager", "Gesamt")] == 5.5
    assert snapshots.schluessel("Halle/Lager", kennzahlen.ANTEIL_INTERN) in werte


def test_leere_tabelle_liefert_keine_werte():
    t = kennzahlen.baue_tabelle([], "Halle/Lager")
    assert t.zeilen == []
    assert t.gesamt is None
    assert kennzahlen.snapshot_werte([t]) == {}


# --- Durchschnitts- und Spitzenmiete --------------------------------------
def test_durchschnitt_ist_das_arithmetische_mittel():
    """Bewusst nicht flächengewichtet – die Propstack-Flächen sind unzuverlässig."""
    zeilen = [_zeile("40213", 4.00), _zeile("40468", 6.00), _zeile("40474", 11.00)]
    t = kennzahlen.baue_tabelle(zeilen, "Halle/Lager")
    assert t.gesamt.median_jetzt == 6.00        # Median
    assert t.gesamt.durchschnittsmiete == 7.00  # Mittel (21/3)


def test_spitzenmiete_ist_nicht_das_maximum():
    """Ein einzelner Ausreißer soll das Spitzenniveau nicht bestimmen."""
    mieten = [4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 20.0]
    zeilen = [_zeile(f"402{i:02d}", m) for i, m in enumerate(mieten)]
    t = kennzahlen.baue_tabelle(zeilen, "Halle/Lager")
    assert t.gesamt.max_kaltmiete == 20.0        # Maximum bleibt sichtbar
    assert t.gesamt.spitzenmiete < 20.0          # Spitze nicht
    assert t.gesamt.spitzenmiete > t.gesamt.median_jetzt


def test_spitzenmiete_bei_einem_wert_ist_der_wert():
    t = kennzahlen.baue_tabelle([_zeile("40213", 6.50)], "Halle/Lager")
    assert t.gesamt.spitzenmiete == 6.50
    assert t.gesamt.durchschnittsmiete == 6.50


def test_perzentil_1_ergibt_das_maximum(monkeypatch):
    """Über die Konfiguration ist die echte Spitze einstellbar."""
    monkeypatch.setattr(kennzahlen.config, "SPITZENMIETE_PERZENTIL", 1.0)
    zeilen = [_zeile("40213", 4.0), _zeile("40468", 6.0), _zeile("40474", 20.0)]
    t = kennzahlen.baue_tabelle(zeilen, "Halle/Lager")
    assert t.gesamt.spitzenmiete == 20.0


def test_spitze_liegt_nie_unter_dem_median():
    for mieten in ([5.0], [5.0, 5.0], [4.0, 5.0, 6.0], [1.0, 2.0, 3.0, 10.0]):
        zeilen = [_zeile(f"402{i:02d}", m) for i, m in enumerate(mieten)]
        t = kennzahlen.baue_tabelle(zeilen, "Halle/Lager")
        assert t.gesamt.spitzenmiete >= t.gesamt.median_jetzt


def test_kennwerte_stehen_auch_je_gruppe():
    zeilen = [_zeile("40213", 6.0), _zeile("44145", 4.0), _zeile("44139", 8.0)]
    t = kennzahlen.baue_tabelle(zeilen, "Halle/Lager")
    ruhr = next(z for z in t.zeilen if z.label == "Ruhrgebiet")
    assert ruhr.durchschnittsmiete == 6.00
    assert ruhr.spitzenmiete is not None


def test_snapshot_enthaelt_durchschnitt_und_spitze():
    """Damit die Zeitreihe später auch diese Werte vergleichen kann."""
    t = kennzahlen.baue_tabelle([_zeile("40213", 6.0), _zeile("40468", 8.0)], "Halle/Lager")
    werte = kennzahlen.snapshot_werte([t])
    assert werte["Halle/Lager|Düsseldorf|durchschnitt"] == 7.0
    assert "Halle/Lager|Düsseldorf|spitze" in werte
    assert "Halle/Lager|Gesamt|durchschnitt" in werte
