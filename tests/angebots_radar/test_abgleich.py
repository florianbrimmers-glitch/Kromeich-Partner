"""Bestand und Abgleich (angebots_radar/bestand.py, abgleich.py, bericht.py), ohne Netz.

Die Fälle sind die, an denen die Regeln am 26.11.2026 ausgerichtet wurden: die echten Angebote
des Teams aus der Pipeline „300 Mieter“ und die Eigenheiten der Einheiten in Propstack.
"""
from __future__ import annotations

from datetime import date

import pytest

from angebots_radar.abgleich import GROESSER, KOMBINATION, PASST, TEILBAR, Abgleich, Angebote
from angebots_radar.bericht import als_daten, als_nachricht, als_text, fuer_seite, fuer_vergleich, vergleich
from angebots_radar.bestand import ALTBESTAND, VERMARKTUNG, hallenflaeche, lade_bestand, verfuegbar_als
from angebots_radar.gesuch import aus_suchprofil
from angebots_radar.main import Quelle

from .zeilen import REMSCHEID, WERMELSKIRCHEN, einheit, suchprofil

HEUTE = date(2026, 11, 26)


def abgleich(einheiten: list[dict], deals: list[dict] | None = None, **kw) -> Abgleich:
    flaechen, _ = lade_bestand(einheiten, HEUTE)
    return Abgleich(flaechen, Angebote.aus_deals(deals or []), HEUTE, **kw)


# --- Bestand ---------------------------------------------------------------------------------

def test_verfuegbar_ist_vermarktung_oder_aktiver_altbestand():
    assert verfuegbar_als(REMSCHEID) == VERMARKTUNG
    assert verfuegbar_als(einheit(vermietet=True)) is None
    assert verfuegbar_als(einheit(status=163673)) is None                       # Vorbereitung
    assert verfuegbar_als(einheit(status=None, status_logistik="Aktiv")) == ALTBESTAND
    assert verfuegbar_als(einheit(status=None)) is None                          # weder Status noch „Aktiv“
    assert verfuegbar_als(einheit(status_logistik="Inaktiv")) is None


def test_hallenflaeche_nicht_irgendeine_flaeche():
    """26.11.2026: Der Altbestand steht als „APARTMENT“ in Propstack und ist trotzdem Halle; ein
    Büro-Datensatz trägt die Bürofläche als Gesamtfläche und ist keine."""
    altbestand = einheit(typ="APARTMENT", kategorie=None, lagerflache=None, lagerflache_verfugbar="13.100 m²")
    assert hallenflaeche(altbestand) == 13100
    buero = einheit(typ="OFFICE", kategorie="OFFICE", lagerflache=None, gesamt=5283.02, titel="Büroflächen in (40) Ratingen")
    assert hallenflaeche(buero) is None
    halle_ohne_feld = einheit(lagerflache=None, gesamt=4200.0)
    assert hallenflaeche(halle_ohne_feld) == 4200


def test_teilbar_ab_steht_teils_um_faktor_1000_zu_klein_im_feld():
    """152 Einheiten am 26.11.2026: 4.585 m² als 4.585 gespeichert. Und „teilbar ab“ = ganze Fläche
    heißt: nicht teilbar."""
    flaechen, _ = lade_bestand([
        einheit(id=1, lagerflache=10762.0, lagerflache_teilbar_ab=4.585),
        einheit(id=2, lagerflache=10385.0, lagerflache_teilbar_ab=10.385),
        einheit(id=3, lagerflache=9481.75, lagerflache_teilbar_ab=3818.94),
    ], HEUTE)
    assert [f.teilbar_ab for f in flaechen] == [4585, None, 3818.94]


def test_einheit_ohne_koordinaten_bekommt_geschaetzte_lage():
    """245 Einheiten in Vermarktung ohne Koordinaten – eine Umkreissuche sähe sie nicht."""
    nachbar = einheit(id=1, projekt_id=567212, plz="71706", ort="Markgröningen", lat=48.90, lng=9.08)
    ohne = einheit(id=2, projekt_id=567212, plz="71706", ort="Markgröningen", lat=None, lng=None)
    gleiche_plz = einheit(id=3, plz="71706", ort="Markgröningen", lat=None, lng=None)
    fremd = einheit(id=4, plz="99999", ort="Nirgendwo", lat=None, lng=None)
    vermietet_mit_lage = einheit(id=5, plz="04158", ort="Leipzig", lat=51.39, lng=12.29, vermietet=True)
    leipzig = einheit(id=6, plz="04158", ort="Leipzig", lat=None, lng=None)
    flaechen, ohne_lage = lade_bestand([nachbar, ohne, gleiche_plz, fremd, vermietet_mit_lage, leipzig], HEUTE)
    je_id = {f.id: f for f in flaechen}
    assert (je_id[2].lage_geschaetzt, je_id[2].lat) == ("Projekt", 48.90)
    assert je_id[3].lage_geschaetzt == "PLZ"
    assert je_id[4].lat is None and ohne_lage == 1
    assert je_id[6].lage_geschaetzt == "PLZ"          # die Adresse einer vermieteten Einheit stimmt ja


def test_altbestand_mit_ort_in_der_strasse():
    """Import 01/2025: „40764 Langenfeld (Rheinland)“ steht in der Straße, im PLZ-Feld „Deutschland“."""
    flaechen, _ = lade_bestand([einheit(status=None, status_logistik="Aktiv", strasse="40764 Langenfeld (Rheinland)",
                                        plz="Deutschland", ort="", lat=None, lng=None, typ="APARTMENT")], HEUTE)
    assert (flaechen[0].plz, flaechen[0].ort, flaechen[0].land) == ("40764", "Langenfeld (Rheinland)", "Nordrhein-Westfalen")


# --- Abgleich --------------------------------------------------------------------------------

def test_remscheid_passt_auf_das_gesuch_wermelskirchen():
    """Die Halle, für die der Handler am 25.11. noch eine Aufgabe „Objekt fehlt“ schrieb, ist der beste
    Treffer für ein Gesuch vom März: 4 km, 8.875 m², 4 Rampen – Höhe 8,58 m knapp unter 9 m."""
    e = abgleich([REMSCHEID]).pruefe(aus_suchprofil(WERMELSKIRCHEN))
    v = e.vorschlaege[0]
    assert (v.art, round(v.entfernung_km), v.summe) == (PASST, 4, 8875)
    assert "4 Rampen" in v.gruende and "frei ab Q1 2027" in v.gruende
    assert any("knapp unter den gewünschten 9 m" in p for p in v.pruefen)


def test_gepflegte_hoehe_zu_niedrig_faellt_raus_fehlende_bleibt():
    g = aus_suchprofil(WERMELSKIRCHEN)
    assert abgleich([einheit(hallenhohe=6.0)]).pruefe(g).vorschlaege == []
    v = abgleich([einheit(hallenhohe=None)]).pruefe(g).vorschlaege[0]
    assert "Hallenhöhe nicht gepflegt (gewünscht ab 9 m)" in v.pruefen


def test_arten_passt_teilbar_groesser():
    g = aus_suchprofil(suchprofil(text="▪️ ~4.000 - 5.000 m² Hallenfläche", lat=51.15, lng=7.27, radius=20000))
    a = abgleich([
        einheit(id=1, lagerflache=4600.0),
        einheit(id=2, lagerflache=12000.0, lagerflache_teilbar_ab=3000.0),
        einheit(id=3, lagerflache=9000.0),                       # größer, Teilbarkeit unbekannt
        einheit(id=4, lagerflache=30000.0),                      # viel zu groß
        einheit(id=5, lagerflache=1500.0),                       # zu klein, kein Projekt
    ])
    arten = {v.erste.id: v.art for v in a.pruefe(g).vorschlaege}
    assert arten == {1: PASST, 2: TEILBAR, 3: GROESSER}
    assert [v.erste.id for v in a.pruefe(g).vorschlaege] == [1, 2, 3]            # in dieser Rangfolge


def test_kombination_im_selben_projekt():
    """20.04.2026: Für „~10.000 m²“ gingen vier Einheiten zu je rund 5.000 m² aus Düsseldorf-Flingern
    raus. Vorgeschlagen werden möglichst wenige Einheiten, deren Summe passt."""
    g = aus_suchprofil(suchprofil(text="▪️ ~10.000 m² Hallenfläche", lat=51.22, lng=6.78, radius=25000))
    flingern = [einheit(id=5301725 + i, name=f"Phase 2 – Unit {i + 1}", projekt_id=518706, projekt_titel="Flingern",
                        lat=51.23, lng=6.82, lagerflache=fl) for i, fl in enumerate((5098.0, 5071.0, 5059.0, 5100.0))]
    e = abgleich(flingern).pruefe(g)
    assert len(e.vorschlaege) == 1
    v = e.vorschlaege[0]
    assert v.art == KOMBINATION and len(v.flaechen) == 2 and 10000 <= v.summe <= 10300
    assert "2 Einheiten im selben Projekt" in v.gruende[0]


def test_je_projekt_ein_vorschlag_die_uebrigen_werden_genannt():
    g = aus_suchprofil(suchprofil(text="▪️ ~5.000 m² Hallenfläche", lat=51.22, lng=6.78, radius=25000))
    park = [einheit(id=10 + i, projekt_id=518706, lat=51.23, lng=6.82, lagerflache=fl) for i, fl in enumerate((5098.0, 5071.0, 5059.0))]
    e = abgleich(park).pruefe(g)
    assert len(e.vorschlaege) == 1 and len(e.vorschlaege[0].weitere_im_projekt) == 2


def test_dieselbe_halle_zweimal_in_propstack_zaehlt_einmal():
    """24.11.2026: sieben Hillwood-Einheiten wurden ein zweites Mal angelegt (Kirchlengern 3158471/6572519).
    Der zwei Tage alte Zwilling macht die Halle nicht „neu“ (Prüflauf 26.11.2026: elf solche „Neuheiten“)."""
    g = aus_suchprofil(suchprofil(text="▪️ ~10.000 m² Hallenfläche", polygon=[[8.0, 52.0], [9.0, 52.0], [9.0, 52.5], [8.0, 52.5]]))
    alt = einheit(id=3158471, projekt_id=411492, strasse="Hamerstraße", ort="Kirchlengern", lat=52.2, lng=8.63, lagerflache=9824.0)
    neu = einheit(id=6572519, projekt_id=623999, strasse="Hamerstraße", ort="Kirchlengern", lat=52.2, lng=8.63, lagerflache=9824.0,
                  angelegt="2026-11-24")
    e = abgleich([alt, neu]).pruefe(g)
    assert len(e.vorschlaege) == 1 and e.vorschlaege[0].dubletten == [6572519]
    assert e.vorschlaege[0].erste.id == 3158471 and not e.vorschlaege[0].neu


def test_knapp_ausserhalb_des_umkreises():
    """24.11.2026: Gesuch mit 17 km Umkreis, angeboten wurde bei 17 und 20 km. Bis 25 % (mindestens 5 km)
    darüber: Vorschlag mit Hinweis. Weiter weg: keiner."""
    g = aus_suchprofil(suchprofil(text="▪️ ~9.000 m² Hallenfläche", lat=51.54, lng=7.70, radius=17000))
    knapp = einheit(id=1, lat=51.54, lng=7.99)       # rund 20 km östlich
    weit = einheit(id=2, lat=51.54, lng=8.20)        # rund 35 km
    e = abgleich([knapp, weit]).pruefe(g)
    assert [v.erste.id for v in e.vorschlaege] == [1]
    assert any("knapp außerhalb des Umkreises (17 km)" in p for p in e.vorschlaege[0].pruefen)


def test_erst_spaeter_frei_ist_kein_vorschlag():
    g = aus_suchprofil(suchprofil(text="▪️ ~9.000 m² Hallenfläche\n▪️Ab sofort", lat=51.15, lng=7.27, radius=20000))
    e = abgleich([einheit(id=1, strasse="Erste Straße", bezug="Q4 2028"), einheit(id=2, strasse="Zweite Straße", bezug="sofort"),
                  einheit(id=3, strasse="Dritte Straße", bezug="auf Anfrage")]).pruefe(g)
    assert sorted(v.erste.id for v in e.vorschlaege) == [2, 3] and e.spaeter_frei == 1
    offen = next(v for v in e.vorschlaege if v.erste.id == 3)
    assert "Bezug: „auf Anfrage“" in offen.pruefen


def test_kuehlung_als_bedingung_nur_mit_nachweis():
    """Kühlung ist an einer Handvoll Einheiten gepflegt. Ein Kühlgesuch bekommt keine ungekühlten
    Hallen vorgeschlagen – der Bericht sagt, dass von Hand gesucht werden muss."""
    g = aus_suchprofil(suchprofil(text="Kühlfläche bei Berlin / 2.000 m² Hallenfläche / Temperatur: 4-6 Grad", lat=52.5, lng=13.4, radius=27000))
    e = abgleich([einheit(lat=52.5, lng=13.4, lagerflache=2000.0)]).pruefe(g)
    assert e.vorschlaege == [] and "Kühlung (1 passende Flächen ohne Nachweis)" in e.grund_ohne_vorschlag
    gekuehlt = einheit(lat=52.5, lng=13.4, lagerflache=2000.0, titel="Kühllager in (13) Berlin")
    assert len(abgleich([gekuehlt]).pruefe(g).vorschlaege) == 1


def test_ein_wunsch_schliesst_nicht_aus():
    g = aus_suchprofil(suchprofil(text="▪️ ~2.500m² Hallenfläche \n▪️ Gerne 2mal 10t Kräne, im Zweifel rüsten sie selber nach",
                                  lat=51.63, lng=12.33, radius=50000))
    assert len(abgleich([einheit(lat=51.63, lng=12.33, lagerflache=2600.0)]).pruefe(g).vorschlaege) == 1


def test_schon_angeboten_ueber_deal_projekt_und_notiz():
    g = aus_suchprofil(suchprofil(kontakt=77, text="▪️ ~9.000 m² Hallenfläche", lat=51.15, lng=7.27, radius=20000,
                                  notiz="Angeboten:\nTeilungsweg 30, Essen\nHerne Prologis\nEinheit 4444444 war zu teuer"))
    einheiten = [
        einheit(id=1),                                                    # Deal zur Einheit
        einheit(id=2, projekt_id=560425, strasse="Projektweg"),           # Deal zum Projekt (property_id leer)
        einheit(id=3, strasse="Teilungsweg"),                             # Straße steht hinter „Angeboten:“
        einheit(id=5, strasse="Am Hafen", ort="Herne", eigentumer="Prologis Germany Management GmbH"),
        einheit(id=4444444, strasse="Andere Straße"),                     # mit ID in der Notiz genannt
        einheit(id=6, strasse="Neue Straße"),                             # noch nicht angeboten
    ]
    deals = [{"client_id": 77, "property_id": 1, "project_id": None, "deal_pipeline_id": 156095},
             {"client_id": 77, "property_id": None, "project_id": 560425, "deal_pipeline_id": 156095},
             {"client_id": 99, "property_id": 6, "project_id": None, "deal_pipeline_id": 156095}]      # anderer Kontakt
    e = abgleich(einheiten, deals).pruefe(g)
    assert [v.erste.id for v in e.vorschlaege] == [6] and e.schon_angeboten == 5


def test_eigentuemer_bekommt_nicht_die_eigene_halle():
    g = aus_suchprofil(suchprofil(kontakt=25289197, text="▪️ ~9.000 m² Hallenfläche", lat=51.15, lng=7.27, radius=20000))
    assert abgleich([einheit(eigentuemer_kontakt=25289197)]).pruefe(g).vorschlaege == []


def test_gebiet_ueber_orte_bundesland_und_ohne():
    koeln = einheit(id=1, ort="Köln-Ossendorf", plz="50829", lat=50.97, lng=6.90, region=None)
    nahe = einheit(id=2, ort="Hürth", plz="50354", lat=50.99, lng=6.93, region=None)          # 3 km von der Kölner Einheit
    bayern = einheit(id=3, ort="München", plz="80939", lat=48.2, lng=11.6, region=None)
    a = abgleich([koeln, nahe, bayern])
    ids = lambda profil: sorted(v.erste.id for v in a.pruefe(aus_suchprofil(profil)).vorschlaege)   # noqa: E731
    assert ids(suchprofil(text="~9.000 m² Hallenfläche", orte=["Köln"])) == [1, 2]
    assert ids(suchprofil(text="~9.000 m² Hallenfläche", laender=["Nordrhein-Westfalen"])) == [1, 2]
    # Ohne Gebiet wird gezählt, aber nichts gezeigt – fünf aus Hunderten wären Zufall
    ohne = a.pruefe(aus_suchprofil(suchprofil(text="~9.000 m² Hallenfläche")))
    assert ohne.vorschlaege == [] and ohne.grund_ohne_vorschlag.startswith("kein Gebiet im Suchprofil – 3 passende Objekte bundesweit")
    alle_laender = ["Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen", "Nordrhein-Westfalen"]
    assert a.pruefe(aus_suchprofil(suchprofil(text="~9.000 m² Hallenfläche", laender=alle_laender))).vorschlaege == []


def test_widerspruch_und_alter_stehen_als_hinweis_am_vorschlag():
    """Stichprobe 26.11.2026: Eine Halle am Flughafen Mönchengladbach gilt als frei, trägt aber
    „Vermietungsstand 100%“. Nicht nach Regel auflösen – nennen und nach hinten stellen."""
    g = aus_suchprofil(suchprofil(text="▪️ ~9.000 m² Hallenfläche", lat=51.15, lng=7.27, radius=20000))
    widerspruch = einheit(id=1, strasse="Flughafenstraße", vermietungsstand_einheiten="100%")
    frisch = einheit(id=2, strasse="Neue Straße")
    alt = einheit(id=3, strasse="Alte Straße")
    alt["updated_at"] = "2025-04-22T10:00:00+02:00"
    frisch["updated_at"] = widerspruch["updated_at"] = "2026-10-01T10:00:00+02:00"
    e = abgleich([widerspruch, frisch, alt]).pruefe(g)
    assert [v.erste.id for v in e.vorschlaege] == [2, 3, 1]
    assert any("Vermietungsstand“ sagt 100 %" in p for p in e.vorschlaege[2].pruefen)
    assert "Datensatz seit 04/2025 nicht geändert" in e.vorschlaege[1].pruefen


def test_altbestand_steht_hinten_und_traegt_den_hinweis():
    g = aus_suchprofil(suchprofil(text="▪️ ~9.000 m² Hallenfläche", lat=51.15, lng=7.27, radius=20000))
    e = abgleich([einheit(id=1, strasse="Alte Straße", status=None, status_logistik="Aktiv"), einheit(id=2)]).pruefe(g)
    assert [v.erste.id for v in e.vorschlaege] == [2, 1]
    assert any("Altbestand ohne Propstack-Status" in p for p in e.vorschlaege[1].pruefen)


def test_gesuch_ohne_lesbare_flaeche_bekommt_keinen_vorschlag():
    e = abgleich([REMSCHEID]).pruefe(aus_suchprofil(suchprofil(text="Interesse an Flächen im Raum Köln", lat=51.15, lng=7.27, radius=20000)))
    assert e.vorschlaege == [] and e.grund_ohne_vorschlag == "Fläche im Suchprofil nicht lesbar"


# --- Bericht und Vergleich -------------------------------------------------------------------

def _daten(deals=None):
    g = aus_suchprofil(WERMELSKIRCHEN)
    e = abgleich([REMSCHEID], deals).pruefe(g)
    kopf = {"gesuche_geprueft": 1, "flaechen": 1, "flaechen_geschaetzt": 0, "flaechen_ohne_lage": 0, "gesuche_mit_vorschlag": 1,
            "vorschlaege_gezeigt": 1, "je_gesuch": 5, "vorschlaege_gesamt": 1}
    return als_daten([e], [], {28988960: {"name": "Erika Beispiel (Beispiel Logistik GmbH)", "firma": "Beispiel Logistik GmbH"}},
                     {387451: "Marek Zimmermann"}, HEUTE, kopf)


def test_bericht_nennt_kontakt_wunsch_und_vorschlag():
    daten = _daten()
    text = als_text(daten)
    assert "▶ Erika Beispiel (Beispiel Logistik GmbH) – Suchprofil 11072931 vom 06.03.2026" in text      # Firma nicht doppelt
    assert "Gesucht: 8.000–12.000 m² · Umkreis 25 km · Höhe ab 9 m · ab 4 Rampen · ab Q3 2027" in text
    assert "1. Logistikhalle in (42) Remscheid – Am Weidenbroich 20-22 - Remscheid – Remscheid, 4 km – 8.875 m² [passt]" in text
    assert "https://crm.propstack.de/app/portfolio/properties/5159361" in text
    assert daten["gesuche"][0]["alt"] is True            # seit dem 06.03. nicht bearbeitet: über 180 Tage


def test_vergleich_zaehlt_nur_deals_nach_dem_lauf():
    """Wirkung statt Aktivität: Was wurde aus den Vorschlägen? Ein Deal von vor dem Lauf zählt nicht."""
    alt = _daten()
    davor = {"client_id": 28988960, "property_id": 5159361, "project_id": None, "created_at": "2026-11-20T10:00:00+01:00"}
    danach = {"client_id": 28988960, "property_id": 5159361, "project_id": None, "created_at": "2026-12-03T10:00:00+01:00"}
    fremd = {"client_id": 1, "property_id": 5159361, "project_id": None, "created_at": "2026-12-03T10:00:00+01:00"}
    assert vergleich(alt, [davor, fremd])["angeboten"] == 0
    ergebnis = vergleich(alt, [davor, danach])
    assert (ergebnis["vorschlaege"], ergebnis["angeboten"]) == (1, 1)


def test_wochenmeldung_ist_kurz_und_nennt_nur_frische_gesuche():
    daten = _daten()
    assert als_nachricht(daten, "Marek Zimmermann") == ""          # das Gesuch ist seit März unberührt: erst nachfragen
    daten["gesuche"][0]["alt"] = False
    text = als_nachricht(daten, "Marek Zimmermann")
    assert text.startswith("Angebots-Radar, Stand 26.11.2026: 1 Vorschlag für 1 Gesuch – Vorauswahl, noch nicht angeboten.")
    assert "– Logistikhalle in (42) Remscheid – Am Weidenbroich 20-22 - Remscheid (Remscheid, 4 km, 8.875 m²) – prüfen: Höhe 8,6 m" in text
    assert als_nachricht(daten, "Lena Klinnert") == ""


def test_daten_fuer_seite_und_vergleich_tragen_nur_das_noetige():
    daten = _daten()
    seite = fuer_seite(daten)
    v = seite["gesuche"][0]["vorschlaege"][0]
    assert v["weitere"] == 0 and "punkte" not in v and v["url"].endswith("/5159361")
    ohne_namen = fuer_vergleich(daten)
    assert "Erika" not in str(ohne_namen) and ohne_namen["gesuche"][0]["kontakt"] == "Kontakt 28988960"


# --- Befunde des unabhängigen Prüflaufs vom 26.11.2026 -----------------------------------------

KIRCHLENGERN = dict(strasse="Hamerkampstraße", ort="Kirchlengern", plz="32278", lat=52.2, lng=8.63, lagerflache=9824.0)
OWL = [[8.0, 52.0], [9.0, 52.0], [9.0, 52.5], [8.0, 52.5]]


def test_angebot_zum_zwilling_gilt_fuer_die_halle():
    """Vorher: Der Kontakt hatte einen Deal zum alten Datensatz – der neu angelegte Zwilling kam als
    frischer Vorschlag wieder. Ein Angebot zu einem der beiden Datensätze gilt für beide."""
    g = aus_suchprofil(suchprofil(kontakt=77, text="▪️ ~10.000 m² Hallenfläche", polygon=OWL))
    alt = einheit(id=3158471, name="Hamerkampstraße  – 002", **KIRCHLENGERN)
    neu = einheit(id=6572519, name="002", projekt_id=371785, angelegt="2026-11-24", **KIRCHLENGERN)
    for deal in ({"client_id": 77, "property_id": 6572519, "project_id": None},
                 {"client_id": 77, "property_id": 3158471, "project_id": None},
                 {"client_id": 77, "property_id": None, "project_id": 371785}):
        e = abgleich([alt, neu], [deal]).pruefe(g)
        assert e.vorschlaege == [] and e.schon_angeboten == 1


def test_gleich_grosse_einheiten_sind_keine_dubletten():
    """Im Gewerbepark stehen sechs Einheiten zu je 388 m² – „Unit 2“ und „Unit 2.02“ sind zwei Einheiten,
    und zwei Einheiten desselben Projekts sind nie eine Dublette."""
    park = dict(strasse="Höherweg", ort="Düsseldorf", lagerflache=388.0)
    flaechen, _ = lade_bestand([
        einheit(id=1, name="Höherweg  – Phase 1.1 – Unit 2", **park),
        einheit(id=2, name="Unit 2.02", projekt_id=375481, **park),
        einheit(id=3, name="Unit 2.03", projekt_id=375481, **park),
        einheit(id=4, name="Unit 2.03", projekt_id=375481, **park),
    ], HEUTE)
    assert [f.id for f in flaechen] == [1, 2, 3, 4] and not any(f.zwillinge for f in flaechen)


@pytest.mark.parametrize("notiz, strasse, hausnummer, ort, eigentuemer, kennung, angeboten", [
    ("Teilungsweg 30, Essen", "Teilungsweg", "30", "Essen", "", "", True),
    ("Teilungsweg 30, Essen", "Teilungsweg", "12", "Essen", "", "", False),                 # andere Hausnummer
    ("Im Freihafen 4", "Im Freihafen", "4", "Duisburg", "", "", True),                      # vorher: erstes Wort „Im“ zu kurz
    ("Zum Eisenhammer 52", "Zum Eisenhammer", "52", "Oberhausen", "", "", True),
    ("Carl-Benz-Str. 4, Unna", "Carl-Benz-Straße", "4", "Unna", "", "", True),
    ("Industriestraße 5, Essen", "Industriestraße", "40", "Kerpen", "", "", False),         # vorher Treffer: gleicher Straßenname
    ("Märkische Straße Bochum", "Märkische Straße", None, "Essen", "", "", False),          # andere Stadt
    ("Heisenbergstraße 3, Essen", "Bergstraße", "10", "Unna", "", "", False),               # vorher Treffer als Teilwort
    ("Klöcknerstraße 55", "Straße der Einheit", "5", "Falkensee", "", "", False),           # vorher Treffer über „straße“
    ("Herne Prologis", "Hafenstraße", "1", "Herne", "Prologis Germany Management GmbH", "", True),
    ("Herne Prologis", "Hafenstraße", "1", "Herne", "Garbe Industrial", "", False),
    ("Herten Unit 2.1 und 2.2", "Zum Bahnhof", "1", "Herten", "", "Unit 2.2", True),
    ("Herten Unit 2.1 und 2.2", "Zum Bahnhof", "1", "Herten", "", "Unit 1.1", False),
    ("Industriering 21 Unit 2", "Industriering", "21", "Lünen", "", "Unit 1", False),
    ("Dorfen", "Alte Ziegelei", "3", "Dorfen", "", "", True),                               # ein Ort allein: nur wenn eindeutig
    ("nichts bisher", "Nichtsstraße", "1", "Essen", "", "", False),
])
def test_schon_angeboten_laut_notiz(notiz, strasse, hausnummer, ort, eigentuemer, kennung, angeboten):
    """Suchprofil 11656279 (gelesen 26.11.2026) zeigt, wie das Team es schreibt."""
    g = aus_suchprofil(suchprofil(text="▪️ ~9.000 m² Hallenfläche", notiz=f"Herkunft: LinkedIn\n\nAngeboten:\n{notiz}",
                                  lat=51.15, lng=7.27, radius=20000))
    # Essen und Bochum sind Orte des Bestands – nur so ist „… Bochum“ als andere Stadt erkennbar
    andere = [einheit(id=8 + i, strasse="Ganz Woanders", hausnummer="1", ort=o, lagerflache=100000.0) for i, o in enumerate(("Essen", "Bochum"))]
    e = abgleich([einheit(id=1, strasse=strasse, hausnummer=hausnummer, ort=ort, eigentumer=eigentuemer,
                          name=f"{strasse} – {kennung}" if kennung else strasse), *andere]).pruefe(g)
    assert (e.schon_angeboten == 1) is angeboten and (e.vorschlaege == []) is angeboten


def test_frei_ist_nur_ein_teil_der_halle():
    """31 Einheiten am 26.11.2026: „Lagerfläche“ 14.086 m², „Lagerfläche verfügbar“ 3.919 m². Vorher ging
    die Halle an ein Gesuch über 12.000 m². Abgeglichen wird, was frei ist."""
    teil = einheit(id=1, lagerflache=14086.0, lagerflache_verfugbar="3.919 m²")
    assert abgleich([teil]).pruefe(aus_suchprofil(suchprofil(text="▪️ ~13.000 m² Hallenfläche"))).vorschlaege == []
    e = abgleich([teil]).pruefe(aus_suchprofil(suchprofil(text="▪️ ~4.000 m² Hallenfläche", lat=51.15, lng=7.27, radius=20000)))
    assert e.vorschlaege[0].summe == 3919 and "frei sind 3.919 m² von 14.086 m² (Feld „Lagerfläche verfügbar“)" in e.vorschlaege[0].pruefen
    spanne, _ = lade_bestand([einheit(id=2, lagerflache=109813.0, lagerflache_verfugbar="7.218 bis 93.655 m² BGF laut Eigentuemer")], HEUTE)
    assert (spanne[0].flaeche, spanne[0].teilbar_ab) == (93655, 7218)
    mehr, _ = lade_bestand([einheit(id=3, lagerflache=5430.0, lagerflache_verfugbar="15.280 m²")], HEUTE)     # Widerspruch: nicht entscheidbar
    assert mehr[0].flaeche == 5430 and "15.280 m²" in mehr[0].flaeche_hinweis


def test_bezug_der_text_gilt_vor_dem_alten_datum():
    """Vorher: „frei ab sofort“ für 14 Einheiten, bei denen „auf Anfrage“ steht und nur das Datumsfeld
    einen alten Tag trägt. Das Feld „Bezug“ enthält teils nur die Art („Quartal“, „Datum“)."""
    flaechen, _ = lade_bestand([
        einheit(id=1, frei_ab="auf Anfrage", bezug="Datum", bezug_datum="2024-08-01"),
        einheit(id=2, frei_ab="ab Q3 2025", bezug="Quartal", bezug_datum="2025-07-01"),
        einheit(id=3, frei_ab="Q1 2026 (Early Access)", bezug="Quartal", bezug_datum="2025-04-01"),
        einheit(id=4, frei_ab=None, bezug=None, bezug_datum="2027-04-01"),
        einheit(id=5, frei_ab="kurzfristig", bezug="kurzfristig", bezug_datum="1970-01-01"),
        einheit(id=6, frei_ab="sofort", bezug="Q2 2027"),
    ], HEUTE)
    assert [(f.bezug_text, f.bezug) for f in flaechen] == [
        ("auf Anfrage", None), ("ab Q3 2025", (2025, 3)), ("Q1 2026 (Early Access)", (2026, 1)),
        ("2027-04-01", (2027, 2)), ("kurzfristig", (0, 0)), ("sofort", (2027, 2))]


def test_rampen_stehen_nur_im_feld_rampentore():
    """`anzahl_rampentore_2` heißt in Propstack „Ebenerdige Tore“ (propstack-mcp/src/propstack/howto.ts).
    Vorher wurde es als Rampenzahl gelesen, wenn „Rampentore“ leer oder 0 war (170 Einheiten)."""
    flaechen, _ = lade_bestand([
        einheit(id=1, ramepntore="11 Stk.", anzahl_rampentore_2=4.0),
        einheit(id=2, ramepntore="0", anzahl_rampentore_2=1.0),
        einheit(id=3, ramepntore="keine (nur ebenerdige Tore)", anzahl_rampentore_2=4.0),
        einheit(id=4, anzahl_rampentore_2=3.0),
    ], HEUTE)
    assert [(f.rampen, f.tore_ebenerdig) for f in flaechen] == [(11, 4), (0, 1), (0, 4), (None, 3)]
    assert all("ebenerdige Andienung" in f.merkmale for f in flaechen)
    g = aus_suchprofil(suchprofil(text="▪️ ~9.000 m² Hallenfläche\n▪️ mind. 4 Rampen", lat=51.15, lng=7.27, radius=20000))
    e = abgleich([einheit(id=3, ramepntore="keine (nur ebenerdige Tore)", anzahl_rampentore_2=4.0)]).pruefe(g)
    assert "keine Rampen laut Objekt (gewünscht 4), 4 ebenerdige Tore" in e.vorschlaege[0].pruefen


@pytest.mark.parametrize("text, merkmal, vorhanden", [
    ("Kranbahnanlagen nachrüstbar", "Kran", False),                              # alle Texte aus dem Bestand vom 26.11.2026
    ("Krananlagen können nachgerüstet werden", "Kran", False),
    ("Ausrüstung mit Kranbahnen möglich", "Kran", False),
    ("4 Kranbahnen mit jeweils bis zu 5 t Traglast", "Kran", True),
    ("Kranbahn (5t, 10t)", "Kran", True),
    ("Gleisanschluss möglich", "Gleisanschluss", False),
    ("Gleisanschluss vorhanden, derzeit deaktiviert", "Gleisanschluss", False),
    ("optionaler Gleisanschluss verfügbar", "Gleisanschluss", False),
    ("Am Gleisdreieck 1-5", "Gleisanschluss", False),
    ("eigener Gleisanschluss am Grundstück", "Gleisanschluss", True),
    ("Büro mit Fußbodenheizung/-kühlung", "Kühlung", False),
    ("Kühlung der Serverräume", "Kühlung", False),
    ("Kühlwasser aus eigener Brunnenanlage", "Kühlung", False),
    ("3.074 m² Tiefkühllager (−28 °C)", "Kühlung", True),
    ("Kühllager mit ca. 7.400 m² Fläche bei 3–8 °C", "Kühlung", True),
])
def test_merkmal_nur_wenn_vorhanden(text, merkmal, vorhanden):
    """Vorher reichte das Wort: Ein Gesuch mit Kran als Bedingung bekam Hallen, in denen ein Kran
    „nachrüstbar“ ist, und ein Kühlgesuch Büros mit Fußbodenkühlung."""
    roh = einheit()
    roh["description_note"] = {"label": "Beschreibung", "value": text}
    flaechen, _ = lade_bestand([roh], HEUTE)
    assert (merkmal in flaechen[0].merkmale) is vorhanden


def test_teilbar_wert_der_nicht_zur_flaeche_passt_ist_keiner():
    flaechen, _ = lade_bestand([einheit(id=1, lagerflache=7270.0, lagerflache_teilbar_ab=8.0),
                                einheit(id=2, lagerflache=2250.0, lagerflache_teilbar_ab=123.0)], HEUTE)
    assert [f.teilbar_ab for f in flaechen] == [None, 123]


def test_altbestand_adressen():
    """Altbestand, wie er am 26.11.2026 in Propstack steht: Ort im PLZ-Feld, nur Leitregion, PLZ ohne Null."""
    flaechen, _ = lade_bestand([
        einheit(id=1, strasse="Merseburger Straße", plz="Leipzig", ort="", region=None),
        einheit(id=2, strasse="04 Grimma", plz="Deutschland", ort="", region=None),
        einheit(id=3, strasse="Marl", plz="Deutschland", ort="", region=None),
        einheit(id=4, strasse="Bahnhofstraße", plz="4451", ort="Borsdorf", region=None),
    ], HEUTE)
    assert [(f.ort, f.plz, f.land) for f in flaechen] == [
        ("Leipzig", "", None), ("Grimma", "", "Sachsen"), ("Marl", "", None), ("Borsdorf", "04451", "Sachsen")]


def test_gezeichnetes_deutschland_ist_kein_gebiet():
    """Ein Vieleck um ganz Deutschland zählte als Gebiet – und lieferte fünf Hallen quer durchs Land."""
    deutschland = [[5.9, 47.3], [15.0, 47.3], [15.0, 55.0], [5.9, 55.0]]
    e = abgleich([REMSCHEID]).pruefe(aus_suchprofil(suchprofil(text="▪️ ~9.000 m² Hallenfläche", polygon=deutschland)))
    assert e.vorschlaege == [] and e.grund_ohne_vorschlag.startswith("kein Gebiet im Suchprofil – 1 passende Objekte bundesweit")
    nrw = [[6.0, 50.5], [9.0, 50.5], [9.0, 52.5], [6.0, 52.5]]
    assert len(abgleich([REMSCHEID]).pruefe(aus_suchprofil(suchprofil(text="▪️ ~9.000 m² Hallenfläche", polygon=nrw))).vorschlaege) == 1
    # acht Bundesländer angekreuzt, aber ein Umkreis gezogen: Der Umkreis gilt
    mit_umkreis = suchprofil(text="▪️ ~9.000 m² Hallenfläche", lat=51.15, lng=7.27, radius=20000, laender=["Bayern"] * 8)
    assert len(abgleich([REMSCHEID]).pruefe(aus_suchprofil(mit_umkreis)).vorschlaege) == 1


def test_frankfurt_oder_ist_nicht_frankfurt_am_main():
    main_ = einheit(id=1, ort="Frankfurt am Main", plz="60314", lat=50.11, lng=8.68)
    oder = einheit(id=2, ort="Frankfurt (Oder)", plz="15234", lat=52.34, lng=14.55, strasse="Oderweg")
    muelheim = einheit(id=3, ort="Mülheim an der Ruhr", plz="45473", lat=51.43, lng=6.88, strasse="Ruhrweg")
    a = abgleich([main_, oder, muelheim])
    treffer = lambda orte: [v.erste.id for v in a.pruefe(aus_suchprofil(suchprofil(text="▪️ ~9.000 m² Hallenfläche", orte=orte))).vorschlaege]  # noqa: E731
    assert treffer(["Frankfurt (Oder)"]) == [2] and treffer(["Frankfurt am Main"]) == [1] and treffer(["Mülheim"]) == [3]


def test_neue_einheit_bleibt_hinter_dem_projekt_sichtbar():
    """Vorher: Im Lauf „nur neu“ verschwand eine neue Einheit, wenn eine ältere desselben Projekts mehr Punkte hatte."""
    g = aus_suchprofil(suchprofil(text="▪️ ~5.000 m² Hallenfläche", lat=51.22, lng=6.78, radius=25000))
    alt = einheit(id=10, projekt_id=518706, lat=51.23, lng=6.82, lagerflache=5000.0, hallenhohe=12.0, frei_ab="sofort")
    neu = einheit(id=11, projekt_id=518706, lat=51.23, lng=6.82, lagerflache=6900.0, angelegt="2026-11-24", strasse="Neuer Weg")
    v = abgleich([alt, neu]).pruefe(g).vorschlaege[0]
    assert v.erste.id == 10 and v.neu and "weitere Einheit im Projekt neu im Bestand" in v.gruende and v.weitere_im_projekt == [11]


def test_vergleich_zaehlt_ab_dem_zeitpunkt_des_laufs_und_trennt_einheit_von_projekt():
    """Vorher: Ein Deal vom Nachmittag des Lauftags zählte nicht (verglichen wurde nur das Datum)."""
    alt = fuer_vergleich({**_daten(), "kopf": {"erzeugt": "2026-11-26T21:26:00+00:00"}})
    v = alt["gesuche"][0]["vorschlaege"][0]
    v.update(projekt_id=411492, weitere_im_projekt=[5159362], dubletten=[5159399])
    deal = lambda zeit, **kw: {"client_id": 28988960, "property_id": None, "project_id": None, "created_at": zeit, **kw}  # noqa: E731
    assert vergleich(alt, [deal("2026-11-26T16:30:00.000+01:00", property_id=5159361)])["angeboten"] == 0        # vor dem Lauf
    spaeter = vergleich(alt, [deal("2026-11-26T23:30:00.000+01:00", property_id=5159361)])
    assert (spaeter["angeboten"], spaeter["ueber_einheit"], spaeter["ueber_projekt"]) == (1, 1, 0)
    assert vergleich(alt, [deal("2026-12-03T10:00:00.000+01:00", property_id=5159399)])["ueber_einheit"] == 1     # der Zwilling
    assert vergleich(alt, [deal("2026-12-03T10:00:00.000+01:00", property_id=5159362)])["ueber_projekt"] == 1     # andere Einheit des Projekts
    assert vergleich(alt, [deal("2026-12-03T10:00:00.000+01:00", project_id=411492)])["ueber_projekt"] == 1
    ohne_uhrzeit = {**alt, "erzeugt": None}
    assert vergleich(ohne_uhrzeit, [deal("2026-11-26T16:30:00.000+01:00", property_id=5159361)])["genau"] is False


def test_bericht_ohne_datum_bricht_nicht_ab_und_nennt_ausgeschlossene_profile():
    """Vorher: Ein Suchprofil ohne `created_at` warf den ganzen Bericht um. Und Profile, die der Text als
    Ankauf oder Grundstück lesen ließ, fehlten ohne Spur – ein falsch gelesenes Mietgesuch wäre nie aufgefallen."""
    roh = suchprofil(text="▪️ ~9.000 m² Hallenfläche", lat=51.15, lng=7.27, radius=20000)
    roh["created_at"] = roh["updated_at"] = None
    g = aus_suchprofil(roh)
    ankauf = aus_suchprofil(suchprofil(id=2, text="Bestands-Logistikimmobilien ab 5.000 m². Vermietungsgrad mind. 80%", vermarktung=None))
    kopf = {"gesuche_geprueft": 1, "flaechen": 1, "flaechen_geschaetzt": 0, "flaechen_ohne_lage": 0, "gesuche_mit_vorschlag": 1,
            "vorschlaege_gezeigt": 1, "je_gesuch": 5, "vorschlaege_gesamt": 1}
    daten = als_daten([abgleich([REMSCHEID]).pruefe(g)], [ankauf], {}, {}, HEUTE, kopf)
    text = als_text(daten)
    assert "Suchprofil 11072931 vom ohne Datum" in text
    assert daten["aufraeumen"]["nicht_abgeglichen"][0]["hinweis"] == "Ankauf oder Grundstück laut Text"
    assert "Nicht abgeglichen – laut Text kein Hallengesuch zur Miete: Kontakt 28988960 – Suchprofil 2" in text


def test_kontakte_werden_nachgeladen_statt_vorausgesetzt(tmp_path, monkeypatch):
    """Vorher: Lag im Ordner nur ein Teil der Kontakte (ein Lauf mit --gesuch), liefen die übrigen
    Gesuche ohne Namen – und Testprofile damit als echte Gesuche durch den Abgleich. Ohne Schlüssel
    lässt sich nichts nachladen: Dann steht es als Fehler im Lauf."""
    (tmp_path / "kontakte.json").write_text('{"1": {"name": "Erika Beispiel", "firma": ""}}', encoding="utf-8")
    monkeypatch.delenv("PROPSTACK_API_KEY", raising=False)
    monkeypatch.delenv("PROPSTACK_API_V1", raising=False)
    kontakte, fehlt, nicht_lesbar = Quelle(str(tmp_path)).kontakte([1, 2])
    assert list(kontakte) == [1] and fehlt == [] and nicht_lesbar == [2]

    class Propstack:
        def kontakte(self, ids):
            return {2: {"name": "Max Mustermann", "firma": ""}}, [3], []

    quelle = Quelle(str(tmp_path))
    quelle._ps = Propstack()
    monkeypatch.setenv("PROPSTACK_API_V1", "x")
    kontakte, fehlt, nicht_lesbar = quelle.kontakte([1, 2, 3])
    assert sorted(kontakte) == [1, 2] and fehlt == [3] and nicht_lesbar == []
    assert Quelle(str(tmp_path)).kontakte([1, 2, 3])[1] == [3]          # gemerkt, nicht jedes Mal neu gefragt
