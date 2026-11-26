"""Suchprofile lesen (angebots_radar/gesuch.py, felder.py), ohne Netz.

Die Texte sind die der echten Suchprofile vom 26.11.2026 (ohne Namen). Jeder Fall hier ist beim
Gegenlesen aller 127 Miet-Suchprofile aufgefallen – als richtig gelesen oder als Fehler, der
behoben wurde.
"""
from __future__ import annotations

from datetime import date

import pytest

from angebots_radar.felder import SOFORT, bundesland, im_polygon, ort_schluessel, quartal
from angebots_radar.gesuch import (
    aus_suchprofil, besonderheiten_aus_text, flaeche_aus_text, hoehe_aus_text, ist_hallengesuch, rampen_aus_text,
)

from .zeilen import WERMELSKIRCHEN, suchprofil


def test_vorlage_des_teams_wird_vollstaendig_gelesen():
    g = aus_suchprofil(WERMELSKIRCHEN)
    assert (g.flaeche_von, g.flaeche_bis, g.flaeche_quelle) == (8000, 12000, "Text")
    assert g.untergrenze == 8000
    assert (g.hoehe_min, g.rampen_min, g.ab_wann) == (9.0, 4.0, (2027, 3))
    assert g.gebiet == "Umkreis" and round(g.umkreis_km) == 25
    assert g.besonderheiten == []            # „kein 24/7“ ist keine Anforderung
    assert g.aktiv and ist_hallengesuch(g)


@pytest.mark.parametrize("text, erwartet", [
    ("▪️ ~8.000 - 12.000 m² Hallenfläche", (8000, 12000)),
    ("▪️ 4000 - 5000m² Hallenfläche / ▪️100 - 200 qm Bürofläche", (4000, 5000)),
    ("▪️ ~10.000 m² Hallenfläche  / ▪️ ~1.000 m² Bürofläche", (10000, 10000)),
    ("▪️ ~3.500m² - 4.000m²m² Hallenfläche", (3500, 4000)),                      # Tippfehler in der Vorlage
    ("− Grundstück ab 2.500 m2 / − Hallenfläche: 800-2.500 m2 / − Büro & Sozialräume: 120-150 m2", (800, 2500)),
    ("Ca. 3-5.000 qm / Ebenerdig ausreichend", (3000, 5000)),                    # „3-5.000“ meint 3.000–5.000
    ("Die suchen nochmal 10-15.000 krefeld in MG oder Düsseldorf aber batterielager", (10000, 15000)),
    ("20K / wenig Büro nur Logistik / 12 M hoch", (20000, 20000)),
    ("haben aktuell 1.500 in Dortmund / suchen 5.000 Halle + 2.000 Produktion", (5000, 5000)),
    ("▪️ mind. 7000m² Hallenfläche mit Kranbahn, 1 magazinhalle", (7000, None)),
    ("Lagermöglichkeit für bis zu 20.000m², kleinere Flächen kommen ggf. auch in Frage", (None, 20000)),
    ("östliches Ruhrgebiet / 30.000m² / Ab Mitte 2027", (30000, 30000)),
    ("Kurzfassung: ca. 10.000-12.000 m² Gebäude / 40.000 m² Grundstück, A1/A43", (10000, 12000)),
    ("Gesuch 15.000-18.000 m2, Umkreis max 30 km. Tippgeber X. UKB min 10 m und Autobahnnaehe haben kein Feld", (15000, 18000)),
    ("Raum Bönen,Unna,Hamm / Mind. 1000m², gewünscht: 5.000m² - 10.000m² / Umschlaglager", (5000, 10000)),
    # Keine Hallenfläche: Rampen-Regel, Büro, Grundstück
    ("▪️ mind. 1 Rampe je 1.000 m² / ▪️ 250 m² Bürofläche", None),
    ("ab ca. 8.000 m² Grundstücksfläche, Ballungszentren", None),
    ("Nähe ist unabdingbar / ab 01.11 / 01.12 / Ebenerdige Andienung zwingend", None),
])
def test_flaeche_aus_text(text, erwartet):
    assert flaeche_aus_text(text) == erwartet


def test_nur_untergrenze_gilt_bis_zum_doppelten():
    """Das Custom-Feld lagerflache ist die Untergrenze für Propstacks Matching, nicht der Wunsch."""
    g = aus_suchprofil(suchprofil(text="", lagerflache=2500.0, lat=51.6, lng=12.3, radius=30000))
    assert (g.flaeche_von, g.flaeche_bis, g.flaeche_quelle) == (2500, 5000, "Untergrenze")


def test_einzelwert_und_mindestwert_bekommen_einen_korridor():
    assert aus_suchprofil(suchprofil(text="▪️ ~10.000 m² Hallenfläche", lagerflache=8000.0)).flaeche_bis == 12500
    g = aus_suchprofil(suchprofil(text="mind. 5000 qm ab sofort für 1-2 Jahre", lagerflache=4000.0))
    assert (g.flaeche_von, g.flaeche_bis) == (5000, 7500)
    g = aus_suchprofil(suchprofil(text="Lagermöglichkeit für bis zu 20.000m²", lagerflache=15000.0))
    assert (g.flaeche_von, g.flaeche_bis) == (15000, 20000)


@pytest.mark.parametrize("text, hoehe", [
    ("▪️ mind. 9m Deckenhöhe", 9.0),
    ("▪️ 10-12m Deckenhöhe", 10.0),
    ("▪️10,5m UKB", 10.5),
    ("Deckenhöhe > 7,5m / Temperatur: 4-6 Grad", 7.5),
    ("12 M hoch - im Idealfall schon regaliert", 12.0),
    ("Mind 11 M UKB + Spinkler", 11.0),
    ("▪️ keine Anforderungen an die Deckenhöhe", None),
    ("Keine Anforderungen an Deckenhöhe (min. 4m / max. 18 m)", None),
    ("▪️ Deckenhöhe k.A.", None),
])
def test_hoehe_aus_text(text, hoehe):
    assert hoehe_aus_text(text) == hoehe


@pytest.mark.parametrize("text, flaeche, rampen", [
    ("▪️ mind. 4 Rampen", 8000, 4),
    ("▪️ 20 - 30 Rampen", 8000, 20),
    ("▪️ 3-4 Rampen + 1-2 Tore Höhe 4,5m", 1000, 3),
    ("▪️ 1 Rampe pro 1.000 qm", 8000, 8),
    ("▪️mind. 1 Rampe je 1.000 m²", 30000, 30),
    ("▪️ Mind. 20 Docks, Cross-Dock", 10000, 20),
    ("viele Rampen", 20000, None),
    ("▪️ Rampen keine Angaben", 15000, None),
])
def test_rampen_aus_text(text, flaeche, rampen):
    assert rampen_aus_text(text, flaeche) == rampen


@pytest.mark.parametrize("text, erwartet", [
    ("▪️E-Commerce und Batterie / WGK und Sprinklerung erforderlich", ["Gefahrgut/WGK/Batterie", "Sprinkler"]),
    ("▪️E-Commerce (ohne Gefahrgut)", []),
    ("Lagerung von Konsumgütern (keine Gefahrgüter)", []),
    ("▪️Was wird gelagert? (Gefahrgut etc.)", []),                               # unausgefüllte Vorlage
    ("▪️ Art und Anzahl der Andienungen (Rampen, ebenerdiges Tor)", []),         # unausgefüllte Vorlage
    ("▪️B2B Sendungen für Konsumgüter mit und ohne Batterien", ["Gefahrgut/WGK/Batterie"]),
    ("▪️ 24/7 – Notwendig nein", []),
    ("▪️ 24/7 – Notwendig ja", ["24/7"]),
    ("▪️ 24/7 nicht zwingend erforderlich", []),
    ("Kühlfläche bei Berlin / Temperatur: 4-6 Grad", ["Kühlung"]),
    ("▪️ Gerne 2mal 10t Kräne, im Zweifel rüsten sie selber nach", ["Kran (Wunsch)"]),
    ("mind. 7000m² Hallenfläche mit Kranbahn", ["Kran"]),
    ("▪️Ebenerdige Tore erforderlich", ["ebenerdige Andienung"]),
])
def test_besonderheiten(text, erwartet):
    assert besonderheiten_aus_text(text) == erwartet


def test_ergebnisse_in_der_notiz_sind_kein_wunsch():
    """Suchprofil 12698289: Eine Sitzung hat am 11.08.2026 passende Flächen in die Notiz geschrieben –
    „5 Rampen“ dort ist eine Eigenschaft des Treffers, keine Anforderung."""
    g = aus_suchprofil(suchprofil(
        notiz="Kriterien woertlich: Logistikhalle ca. 2.500-5.000 m2, moeglichst mehrere Laderampen. "
              "PASSENDE FLAECHEN IM BESTAND (Abgleich vom 11.08.2026): Einheit 5674869 Log Plaza Unit 3 mit 3.916 m2 Halle, "
              "12,00 m, 5 Rampen plus 1 ebenerdige Zufahrt"))
    assert (g.flaeche_von, g.flaeche_bis) == (2500, 5000)
    assert g.rampen_min is None and g.hoehe_min is None
    assert g.genannte_einheiten == [5674869]


def test_zustand_aus_der_notiz():
    erledigt = aus_suchprofil(suchprofil(text="▪️ ~4.000–5.000 m² Hallenfläche", notiz="03.08 Tender wurde verloren"))
    assert erledigt.erledigt_hinweis == "Tender wurde verloren"
    assert aus_suchprofil(suchprofil(notiz="Info 31.07 - Die haben Herne von Prologis angemietet")).erledigt_hinweis
    assert aus_suchprofil(suchprofil(text="haben aktuell 1.500 in Dortmund / suchen 5.000 Halle")).erledigt_hinweis is None
    intern = aus_suchprofil(suchprofil(text="Bitte noch nicht an den kunden senden wir fahren gemeinsam hin aber gerne Vorauswahl treffen"))
    assert intern.noch_nicht_senden
    angeboten = aus_suchprofil(suchprofil(notiz="Herkunft: LinkedIn\n\nAngeboten: \nTeilungsweg 30, Essen\nHerne Prologis"))
    assert "Teilungsweg 30" in angeboten.angeboten_text


@pytest.mark.parametrize("profil, grund", [
    (suchprofil(vermarktung="BUY", text="Ankaufsprofil: ab 5.000 qm Hallenfläche"), "Ankaufsprofil"),
    (suchprofil(typen=("STORE",), vermarktung=None, lagerflache=400.0), "andere Objektart (STORE)"),
    (suchprofil(text="Test", lagerflache=5000.0), "Testprofil"),
    (suchprofil(text="Kundengesuch: Freifläche 25.000 qm / ▪️ ~25.000 m² befestigte Fläche / Errichten Zelthallen",
                lagerflache=23000.0, typen=()), "Freifläche gesucht, keine Halle"),
    (suchprofil(text="Neubau- und Bestands-Logistikimmobilien ab 5.000 m², deutschlandweit. Vermietungsgrad mind. 80%",
                vermarktung=None, lagerflache=5000.0), "Ankauf oder Grundstück laut Text"),
])
def test_kein_hallengesuch(profil, grund):
    g = aus_suchprofil(profil)
    assert g.kein_hallengesuch == grund and not ist_hallengesuch(g)


def test_inaktiv_ueber_das_custom_feld():
    """Aktiv heißt: Propstack-Schalter an UND das Custom-Feld „aktiv“ nicht auf Inaktiv (182818)."""
    assert aus_suchprofil(suchprofil(aktiv_feld=(182818,))).aktiv is False
    assert aus_suchprofil(suchprofil(aktiv_feld=None)).aktiv is True
    assert aus_suchprofil(suchprofil(aktiv=False)).aktiv is False


HEUTE = date(2026, 11, 26)


@pytest.mark.parametrize("text, spaetestes, erwartet", [
    ("Ab sofort", False, SOFORT),
    ("Ab sofort spätestens Sommer 2026", False, SOFORT),
    ("Ab sofort(Q2/2026)", False, SOFORT),
    ("Ab Q3 2026", False, (2026, 3)),
    ("Ab in ca. 1,5 Jahren (ca.Q3/2027)", False, (2027, 3)),      # nicht „3/2027“ = März
    ("ab Sommer 2027", False, (2027, 3)),
    ("Ab April/Mai 2027", False, (2027, 2)),
    ("Ab spätestens 01.12.2026", False, (2026, 4)),
    ("Ab Ende 2028", False, (2028, 4)),
    # Bezug an der Einheit: das späteste genannte Quartal
    ("Q2/Q3 2027", True, (2027, 3)),
    ("Bauzeit Feb 2027 bis Jan 2028 (Phase III)", True, (2028, 1)),
    ("ca. 15 Monate nach Mietvertragsabschluss", True, (2028, 1)),
    ("laut Flaechenupdate August 2026 verfuegbar", True, (2026, 3)),
    ("sofort, in Abhängigkeit von Ausstattung und Flächenaufteilung", True, SOFORT),
    ("auf Anfrage", True, None),
    ("Quartal", True, None),                                       # nicht ausgefüllter Platzhalter im Feld
])
def test_quartal(text, spaetestes, erwartet):
    assert quartal(text, HEUTE, spaetestes) == erwartet


def test_gebiete():
    viereck = [[6.0, 51.0], [7.0, 51.0], [7.0, 52.0], [6.0, 52.0]]            # Ecken als [lng, lat]
    assert im_polygon(51.5, 6.5, viereck) and not im_polygon(50.9, 6.5, viereck)
    assert ort_schluessel("Köln-Ossendorf") == ort_schluessel("Köln") == "köln"
    assert ort_schluessel("Mülheim an der Ruhr") == "mülheim"
    assert bundesland("Nordrhein-Westfalen", None) == "Nordrhein-Westfalen"
    assert bundesland(None, "42897") == "Nordrhein-Westfalen" and bundesland(None, "Deutschland") is None
