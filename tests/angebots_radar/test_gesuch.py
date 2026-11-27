"""Suchprofile lesen (angebots_radar/gesuch.py, felder.py), ohne Netz.

Die Texte sind die der echten Suchprofile vom 26.11.2026 (ohne Namen). Jeder Fall hier ist beim
Gegenlesen aller 127 Miet-Suchprofile aufgefallen – als richtig gelesen oder als Fehler, der
behoben wurde.
"""
from __future__ import annotations

from datetime import date

import pytest

from angebots_radar.felder import SOFORT, bundesland, gleicher_ort, im_polygon, ort_schluessel, plz5, quartal, zahl
from angebots_radar.gesuch import (
    ab_wann_aus_text, aus_suchprofil, besonderheiten_aus_text, erledigt_aus_text, flaeche_aus_text, hoehe_aus_text,
    ist_hallengesuch, rampen_aus_text,
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
    assert ort_schluessel("Mülheim an der Ruhr") == "mülheim ruhr" and gleicher_ort("Mülheim", "Mülheim an der Ruhr")
    assert bundesland("Nordrhein-Westfalen", None) == "Nordrhein-Westfalen"
    assert bundesland(None, "42897") == "Nordrhein-Westfalen" and bundesland(None, "Deutschland") is None


# --- Befunde des unabhängigen Prüflaufs vom 26.11.2026 -----------------------------------------
# Ein zweiter Durchgang hat die Lesefunktionen mit rund 600 erdachten und echten Eingaben
# beschossen. Was dabei falsch herauskam, steht hier – jeweils mit dem Ergebnis von vorher.

@pytest.mark.parametrize("text, erwartet", [
    ("Büro 300 m², Halle 5.000 m²", (5000, 5000)),                               # vorher 300: die erste Zahl der Zeile
    ("500 m² Büro und 3.000 m² Lager", (3000, 3000)),
    ("Grundstück 20.000 m² mit Halle 8.000 m²", (8000, 8000)),                   # vorher 20.000
    ("Erweiterung von 2.000 m² auf 6.000 m² Hallenfläche", (6000, 6000)),
    ("aktuell 1.500 m² Halle in Dortmund, sucht 3.000 m²", (3000, 3000)),        # vorher 1.500: der heutige Bestand
    ("Halle 3.000 m² (aktuell 1.500 m² in Dortmund)", (3000, 3000)),
    ("Lager ab 01.07.2026 – 5.000 m²", (5000, 5000)),                            # vorher 2026–5.000
    ("Kundengesuch: Halle ab 2027 - 10.000 m² in Köln", (10000, 10000)),
    ("Sucht 2027 Halle in Köln", None),                                          # vorher 2.027 m²
    ("PLZ 40764 Lager gesucht", None),                                           # vorher 40.764 m²
    ("Halle für 5.000 Paletten", None),
    ("ca. 5.000 Palettenstellplätze, Halle ca. 6.000 m²", (6000, 6000)),
    ("Sucht Lager in Köln, Budget ca. 30k im Monat", None),                      # vorher 30.000 m²
    ("Lager für 20k Artikel (SKU)", None),
    ("Halle 20k qm", (20000, 20000)),
    ("5-7k Halle", (5000, 7000)),
    ("Miete max. 6,50 €/m² für 4.000 m²", (4000, 4000)),
    ("Lagerfläche: 12.500,00 m²", (12500, 12500)),                               # vorher nicht lesbar
    ("mind. 2.500 m² bis max. 5.000 m² Halle", (2500, 5000)),
    ("Halle zwischen 2.500 und 5.000 m²", (2500, 5000)),
    ("Mindestfläche von 1750 m² für die Einrichtung", (1750, None)),             # vorher 1.750 als fester Wert
    ("Hallenfläche > 3.000 m²", (3000, None)),
    ("Lager unter 3.000 m²", (None, 3000)),
    ("Lager nicht größer als 3.000 m²", (None, 3000)),
    ("Mind. 1.000 m², gewünscht 5.000 - 10.000 m² Lager", (5000, 10000)),        # die Spanne schlägt den Einzelwert
])
def test_flaeche_befunde_des_prueflaufs(text, erwartet):
    assert flaeche_aus_text(text) == erwartet


def test_bis_zu_mit_hoeherer_untergrenze_ergibt_keinen_verdrehten_korridor():
    """Vorher: „bis zu 20.000 m²“ mit Untergrenze 25.000 ergab 25.000–20.000 und damit nie einen Treffer."""
    g = aus_suchprofil(suchprofil(text="Lagermöglichkeit für bis zu 20.000m²", lagerflache=25000.0))
    assert (g.flaeche_von, g.flaeche_bis) == (10000, 20000)
    vertauscht = aus_suchprofil(suchprofil(text="", industrial_area=9000, industrial_area_to=6000))
    assert (vertauscht.flaeche_von, vertauscht.flaeche_bis) == (6000, 9000)


@pytest.mark.parametrize("text, hoehe", [
    ("Höhe mind. 12,20m", 12.2),                       # vorher 20: die zwei Ziffern hinter dem Komma
    ("UKB: 10,00 m", 10.0),
    ("Tore Höhe 4,5m", None),                          # vorher 4,5 als Hallenhöhe
    ("Torhöhe 4,5 m\nHallenhöhe 10 m", 10.0),
    ("Rampenhöhe 1,20 m, Hallenhöhe 10 m", 10.0),
    ("Bürohöhe 3 m\nHalle 10 m UKB", 10.0),
    ("Raumhöhe Büro 3 m", None),
    ("Deckenhöhe max. 6 m", None),                     # eine Obergrenze ist kein Mindestmaß
    ("Höhe: zwischen 8 und 10 m", 8.0),
    ("lichte Höhe 6 Metern", 6.0),
])
def test_hoehe_befunde_des_prueflaufs(text, hoehe):
    assert hoehe_aus_text(text) == hoehe


@pytest.mark.parametrize("text, ziel, rampen", [
    ("1 Rampe je 800 m²", 8000, 10),                   # vorher 1
    ("1,5 Rampen je 1.000 m²", 8000, 12),              # vorher 40
    ("mind. 1 Rampe / 1.000 m²", 5000, 5),             # „ / “ ist hier kein Zeilentrenner
    ("1 Rampentor je 1.000 m²", 5000, 5),
    ("Rampen: 4", None, 4),
    ("Anzahl Rampentore: 6", None, 6),
    ("2026 Rampen erneuert", None, None),              # vorher 26
    ("Rampe 1,20 m hoch", None, None),
    ("0 Rampen", None, None),
    ("keine Rampen nötig", None, None),
])
def test_rampen_befunde_des_prueflaufs(text, ziel, rampen):
    assert rampen_aus_text(text, ziel) == rampen


def test_rampen_je_1000_rechnen_mit_dem_wunsch_nicht_mit_der_untergrenze():
    """Vorher: „~10.000 m², 1 Rampe je 1.000 m²“ ergab 8 Rampen, weil mit 80 % des Wunsches gerechnet wurde."""
    g = aus_suchprofil(suchprofil(text="▪️ ~10.000 m² Hallenfläche\n▪️ 1 Rampe je 1.000 m²", lagerflache=8000.0))
    assert (g.flaeche_von, g.flaeche_ziel, g.rampen_min) == (8000, 10000, 10)


@pytest.mark.parametrize("text, erwartet", [
    ("Kühlung ja, Gefahrgut nein", ["Kühlung"]),                                 # vorher beides verworfen
    ("Kühlung erforderlich, Sprinkler nicht erforderlich", ["Kühlung"]),
    ("Kran zwingend, Gleisanschluss nicht nötig", ["Kran"]),
    ("Kein Kran, aber Gleisanschluss zwingend", ["Gleisanschluss"]),
    ("Kühlung zwingend, gerne mit Rampe", ["Kühlung"]),                          # vorher nur „Wunsch“
    ("WGK 3 erforderlich, Kühlung nicht", ["Gefahrgut/WGK/Batterie"]),
    ("Gefahrgut (nein)", []),
    ("weder Kühlung noch Kran", []),
    ("Kühlung wird nicht gebraucht", []),
    ("Lebensmittel (ungekühlt)", []),                                            # vorher Kühlung als Bedingung
    ("Ungekühltes Lager", []),
    ("Lagerung von Kühlschränken", []),
    ("Herr Kühl sucht Halle", []),
    ("Lagerung von Krankenhausbetten", []),                                      # vorher Kran
    ("Am Gleis 5", []),
    ("Tel. TK-Anlage", []),
    ("Heizung: mind. 12 Grad Temperatur", []),
    ("Kranbahn wäre schön", ["Kran (Wunsch)"]),
    ("24 / 7 Betrieb", ["24/7"]),                                                # vorher an „ / “ zerschnitten
    ("24/7 k. A.", []),
])
def test_besonderheiten_befunde_des_prueflaufs(text, erwartet):
    assert besonderheiten_aus_text(text) == erwartet


@pytest.mark.parametrize("text, erledigt", [
    ("Kunde hat noch nichts angemietet", False),                                 # vorher „erledigt“ – das Gegenteil
    ("Hat bereits 3.000 m² angemietet und sucht eine Erweiterung", False),
    ("Besichtigung abgesagt, neuer Termin folgt", False),
    ("Kein Bedarf an Büroflächen", False),
    ("Exposé nicht mehr aktuell, neues angefordert", False),
    ("Die haben Herne von Prologis angemietet", True),
    ("Kunde hat abgesagt", True),
    ("Gesuch ist nicht mehr aktuell", True),
    ("Kein Bedarf mehr", True),
    ("Hat sich erledigt", True),
])
def test_erledigt_liest_nicht_das_gegenteil(text, erledigt):
    assert bool(erledigt_aus_text(text)) is erledigt


def test_bezugstermin_nur_aus_zeilen_die_danach_klingen():
    assert ab_wann_aus_text("Start der Suche: 01.09.2026\nMietbeginn 01.04.2027") == (2027, 2)     # vorher Q3 2026
    assert ab_wann_aus_text("Profil angelegt am 01.03.2026") is None
    assert ab_wann_aus_text("Halle in Köln, ab sofort") == SOFORT


def test_ids_und_ueberschrift_in_der_notiz():
    """„(ID 4807608)“ zählt wie „Einheit 4807608“. Und nur die Überschrift schneidet die Notiz ab –
    „Kunde sucht passende Flächen in Köln“ ist der Wunsch selbst (vorher fehlte danach die Fläche)."""
    g = aus_suchprofil(suchprofil(notiz="Schon gezeigt: Log Plaza (ID 4807608) und https://crm.propstack.de/app/portfolio/properties/5674869"))
    assert g.genannte_einheiten == [4807608, 5674869]
    g = aus_suchprofil(suchprofil(text="Kunde sucht passende Flächen in Köln, Halle 5.000 m²"))
    assert (g.flaeche_von, g.flaeche_bis) == (4000, 6250)


def test_angeboten_liste_endet_an_der_leerzeile():
    g = aus_suchprofil(suchprofil(notiz="Angeboten: Teilungsweg 30\n\nKunde sitzt heute in der Industriestraße in Neuss"))
    assert g.angeboten_text == "Teilungsweg 30"


@pytest.mark.parametrize("text, spaetestes, erwartet", [
    ("nicht verfügbar", True, None),                                 # vorher „sofort“
    ("nicht sofort verfügbar", True, None),
    ("derzeit vermietet, kurzfristig nicht verfügbar", True, None),
    ("Bauabschnitt II, Baubeginn ab Q2 2026", True, None),           # Baubeginn ist kein Bezug
    ("Baubeginn Q1 2027, Fertigstellung Q4 2027", True, (2027, 4)),
    ("Halle 12 Monate nach Mietvertragsunterzeichnung, Bueros sofort", True, (2027, 4)),    # vorher „sofort“
    ("Laufzeit 36 Monate, ab sofort", True, SOFORT),
    ("erbaut 2020", True, None),
    ("2. Halbjahr 2027", True, (2027, 3)),
    ("2. Quartal 2027", True, (2027, 2)),
    ("KW 10/2027", True, (2027, 1)),                                 # vorher Oktober
    ("2026-10-01T00:00:00+02:00", True, (2026, 4)),
    ("1/1/2027", True, (2027, 1)),
    ("07.2026", True, (2026, 3)),
])
def test_quartal_befunde_des_prueflaufs(text, spaetestes, erwartet):
    assert quartal(text, HEUTE, spaetestes) == erwartet


def test_zahl_plz_und_orte():
    assert zahl("6.858,32 m²") == 6858.32 and zahl("7.575 m²") == 7575 and zahl("9,5") == 9.5      # vorher None
    assert plz5("4451") == "04451" and plz5("Deutschland") == ""
    assert bundesland(None, "4451") == "Sachsen" and bundesland(None, "76137") == "Baden-Württemberg"
    assert not gleicher_ort("Frankfurt (Oder)", "Frankfurt am Main") and gleicher_ort("Frankfurt", "Frankfurt am Main")
    assert not gleicher_ort("Neu-Ulm", "Neu-Isenburg") and gleicher_ort("Köln-Ossendorf", "Köln")
