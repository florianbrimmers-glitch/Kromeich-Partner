"""Bestand und Abgleich (angebots_radar/bestand.py, abgleich.py, bericht.py), ohne Netz.

Die Fälle sind die, an denen die Regeln am 26.11.2026 ausgerichtet wurden: die echten Angebote
des Teams aus der Pipeline „300 Mieter“ und die Eigenheiten der Einheiten in Propstack.
"""
from __future__ import annotations

from datetime import date

from angebots_radar.abgleich import GROESSER, KOMBINATION, PASST, TEILBAR, Abgleich, Angebote
from angebots_radar.bericht import als_daten, als_text, vergleich
from angebots_radar.bestand import ALTBESTAND, VERMARKTUNG, hallenflaeche, lade_bestand, verfuegbar_als
from angebots_radar.gesuch import aus_suchprofil

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
    """24.11.2026: sieben Hillwood-Einheiten wurden ein zweites Mal angelegt (Kirchlengern 3158471/6572519)."""
    g = aus_suchprofil(suchprofil(text="▪️ ~10.000 m² Hallenfläche", polygon=[[8.0, 52.0], [9.0, 52.0], [9.0, 52.5], [8.0, 52.5]]))
    alt = einheit(id=3158471, projekt_id=411492, strasse="Hamerstraße", ort="Kirchlengern", lat=52.2, lng=8.63, lagerflache=9824.0)
    neu = einheit(id=6572519, projekt_id=623999, strasse="Hamerstraße", ort="Kirchlengern", lat=52.2, lng=8.63, lagerflache=9824.0,
                  angelegt="2026-11-24")
    e = abgleich([alt, neu]).pruefe(g)
    assert len(e.vorschlaege) == 1 and len(e.vorschlaege[0].dubletten) == 1


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
        einheit(id=2, projekt_id=560425),                                 # Deal zum Projekt (property_id leer)
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
