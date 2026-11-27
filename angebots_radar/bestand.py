"""Die Einheiten aus Propstack (`GET /v1/units?expand=1`) als angebotsfähiger Bestand.

Stand 26.11.2026 (2.551 Einheiten, nur gelesen): 1.310 Datensätze kommen für ein Angebot in Frage –
1.110 in Vermarktung, 200 Altbestand ohne Propstack-Status, aber „Status Logistik“ = Aktiv.
Das fängt dieses Modul ab:

- **267 davon haben keine Koordinaten** (245 in Vermarktung) – eine Umkreissuche sieht sie nicht,
  auch Propstacks eigenes Suchprofil-Matching nicht. Hier bekommen sie eine geschätzte Lage:
  erst über andere Einheiten desselben Projekts, dann über die Postleitzahl (fünf, dann drei
  Stellen) aus dem übrigen Bestand. Der Vorschlag nennt das („Lage geschätzt“).
- **„Lagerfläche teilbar ab“ steht bei 152 Einheiten um den Faktor 1.000 zu klein** im Feld
  (10.385 m² als 10.385 gespeichert). Werte unter 100 werden als Tausender gelesen, wenn das zur
  Fläche passt.
- **„Bezug“ steht an drei Stellen:** „frei ab“ (Freitext), das Feld „Bezug“ (Freitext oder nur die
  Art: „Quartal“, „Datum“) und „Bezug Datum“. Der Text gilt. Steht dort „auf Anfrage“, wird aus
  einem alten Datum im dritten Feld kein „sofort“ (14 Einheiten).
- **„Lagerfläche verfügbar“ liegt bei 31 Einheiten deutlich unter „Lagerfläche“** (3.919 m² frei
  von 14.086 m²). Abgeglichen wird, was frei ist; die Gesamtfläche steht als Hinweis dabei.
- **Dieselbe Halle steht teils zweimal in Propstack** (zwei Projekte, gleiche Adresse, gleiche
  Fläche). Sie zählt einmal; ein Angebot zu einem der beiden Datensätze gilt für beide, und ein
  frisch angelegter Zwilling macht die Halle nicht „neu“.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .felder import PLZ_ZU_LAND, bundesland, custom, ort_schluessel, plz5, quartal, skalar, zahl

STATUS_VERMARKTUNG = 163674
VERMARKTUNG = "Vermarktung"
ALTBESTAND = "ohne Propstack-Status"


@dataclass
class Flaeche:
    id: int
    bezeichnung: str
    ort: str
    plz: str
    land: str | None                 # Bundesland
    strasse: str
    hausnummer: str
    projekt_id: int | None
    projekt_titel: str
    gruppe: str                      # VERMARKTUNG oder ALTBESTAND
    flaeche: float | None            # Hallen-/Lagerfläche in m²
    teilbar_ab: float | None
    hoehe: float | None
    rampen: float | None
    bezug_text: str
    bezug: tuple[int, int] | None
    lat: float | None = None
    lng: float | None = None
    lage_geschaetzt: str | None = None    # „Projekt“, „PLZ“, „PLZ-Gebiet“, „Ort“
    eigentuemer: str = ""
    eigentuemer_kontakt_ids: tuple[int, ...] = ()
    provision: str = ""
    miete_halle: float | None = None      # intern, €/m²
    merkmale: tuple[str, ...] = ()        # was die Einheit zu Besonderheiten sagt
    angelegt: str = ""                    # JJJJ-MM-TT
    geaendert: str = ""                   # JJJJ-MM-TT
    voll_vermietet_laut_feld: bool = False   # Custom-Feld „Vermietungsstand“ sagt 100 %
    betreuer: str = ""
    flaeche_gesamt: float | None = None      # „Lagerfläche“, wenn nur ein Teil davon frei ist
    flaeche_hinweis: str = ""                # Widerspruch zwischen den Flächenfeldern
    tore_ebenerdig: float | None = None
    kennung: str = ""                        # „unit 1.2“, „halle 2“ – der letzte Teil des Namens
    zwillinge: tuple[int, ...] = ()          # dieselbe Halle unter anderer ID
    zwillings_projekte: tuple[int, ...] = ()

    @property
    def url(self) -> str:
        return f"https://crm.propstack.de/app/portfolio/properties/{self.id}"


def verfuegbar_als(unit: dict) -> str | None:
    """Kommt die Einheit für ein Angebot in Frage – und in welcher Gruppe? None = nein.
    Dieselbe Regel wie scripts/gesuch_matching.py (Stresstest 19.11.2026, Befund 4)."""
    if skalar(unit.get("rented")) is True or skalar(unit.get("archived")) is True:
        return None
    logistik = custom(unit, "status_logistik")
    if logistik == "Inaktiv":
        return None
    status = unit.get("property_status")
    if isinstance(status, dict):
        return VERMARKTUNG if status.get("id") == STATUS_VERMARKTUNG else None
    return ALTBESTAND if logistik == "Aktiv" else None


def _koordinaten(unit: dict) -> tuple[float, float] | None:
    lat, lng = zahl(skalar(unit.get("lat"))), zahl(skalar(unit.get("lng")))
    return (lat, lng) if lat and lng else None


_STRASSENWORT = re.compile(r"stra(?:ß|ss)e|str\.|weg\b|allee|platz|ring\b|damm\b|ufer|gasse|chaussee|park\b|hafen|\d", re.IGNORECASE)


def _plz(unit: dict) -> str:
    """Fünfstellige PLZ. Im Altbestand steht sie teils in der Straße („40764 Langenfeld“), im
    Osten teils ohne führende Null („4451“)."""
    for key in ("zip_code", "street", "address"):
        if plz := plz5(str(skalar(unit.get(key)) or "")):
            return plz
    return ""


def _plz_gebiet(unit: dict) -> str:
    """Altbestand: „04 Grimma“, „44 Castrop-Rauxel“ – nur die Leitregion steht da."""
    m = re.match(r"\s*(\d{2})\s+\D", str(skalar(unit.get("street")) or ""))
    return m.group(1) if m else ""


def _ort(unit: dict) -> str:
    ort = str(skalar(unit.get("city")) or "").strip()
    if ort:
        return ort
    # Altbestand, drei Schreibweisen: der Ort im PLZ-Feld („Merseburger Straße“ / „Leipzig“),
    # „40764 Langenfeld (Rheinland)“ oder „04 Grimma“ in der Straße, oder nur der Ort als Straße („Marl“).
    plz_feld = str(skalar(unit.get("zip_code")) or "").strip()
    if plz_feld and not re.search(r"\d", plz_feld) and plz_feld != "Deutschland":
        return plz_feld
    strasse = str(skalar(unit.get("street")) or "").strip()
    if m := re.match(r"\d{2,5}\s+(.+)", strasse):
        return m.group(1).strip()
    if strasse and plz_feld == "Deutschland" and not _STRASSENWORT.search(strasse):
        return strasse
    return ""


def _bezeichnung(unit: dict) -> str:
    """Überschrift und Name: Einheiten heißen oft nur „Unit 1“ – erst die Überschrift sagt, wo."""
    titel = str(skalar(unit.get("title")) or "").strip()
    name = str(skalar(unit.get("name")) or "").strip(" -")
    if titel and name and name.casefold() not in titel.casefold():
        return f"{titel} – {name}"
    return titel or name or f"Einheit {unit['id']}"


def _teilbar(unit: dict, flaeche: float | None) -> float | None:
    wert = zahl(custom(unit, "lagerflache_teilbar_ab"))
    if not wert:
        return None
    if wert < 100:
        # 10.385 m² als 10.385 gespeichert (152 Einheiten, 26.11.2026). Passt das Tausendfache nicht
        # zur Fläche („8.0“ bei 7.270 m²), ist der Wert nicht zu deuten – dann lieber keiner.
        wert *= 1000
        if flaeche and wert > flaeche * 1.02:
            return None
    if flaeche and wert >= flaeche * 0.98:
        return None                     # „teilbar ab“ = ganze Fläche heißt: nicht teilbar
    return wert


# Ein Wort allein belegt nichts: „Kranbahnanlagen nachrüstbar“, „Gleisanschluss möglich“, „Gleisanschluss
# vorhanden, derzeit deaktiviert“, „Am Gleisdreieck 1-5“, „Büro mit Fußbodenheizung/-kühlung“,
# „Kühlung der Serverräume“ (alles Bestand 26.11.2026). Gezählt wird nur, was vorhanden ist.
_NUR_MOEGLICH_DANACH = re.compile(r"m(?:ö|oe)glich|nachr(?:ü|ue)st|nachger(?:ü|ue)stet|optional|realisierbar|deaktiviert|stillgelegt|"
                                  r"au(?:ß|ss)er betrieb|r(?:ü|ue)ckgebaut", re.IGNORECASE)
_NUR_MOEGLICH_DAVOR = re.compile(r"\b(ohne|kein\w*|optional\w*|ausr(?:ü|ue)stung mit|vorbereitet f(?:ü|ue)r|k(?:ö|oe)nnen)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)
_TEILSATZ_ENDE = re.compile(r"\n|\s{2,}|\s[-–]\s|[·•;]|\.\s")
_KUEHLUNG = re.compile(r"tiefk(?:ü|ue)hl|k(?:ü|ue)hl(?:lager|halle|haus|h(?:ä|ae)user|fl(?:ä|ae)che|zelle|raum|r(?:ä|ae)ume|logistik|bereich)|"
                       r"temperaturgef(?:ü|ue)hrt|frische(?:lager|logistik)", re.IGNORECASE)
_KRAN = re.compile(r"\b\w*kran(?:bahn\w*|anlage\w*|schiene\w*)?\b|\bkr(?:ä|ae|a)ne\b", re.IGNORECASE)
_GLEIS = re.compile(r"gleisanschl\w*|bahnanschl\w*|bahngleis\w*|\bgleis-\s", re.IGNORECASE)


def _vorhanden(muster: re.Pattern, text: str) -> bool:
    """Steht es da – und zwar als vorhanden, nicht als „möglich“ oder „nachrüstbar“?"""
    for m in muster.finditer(text):
        danach = text[m.end():m.end() + 45]
        if ende := _TEILSATZ_ENDE.search(danach):
            danach = danach[:ende.start()]
        if _NUR_MOEGLICH_DANACH.search(danach) or _NUR_MOEGLICH_DAVOR.search(text[max(0, m.start() - 40):m.start()]):
            continue
        return True
    return False


def _merkmale(unit: dict) -> tuple[str, ...]:
    """Was an der Einheit zu den Besonderheiten eines Gesuchs steht (gesuch._BESONDERHEITEN)."""
    funde = []
    text = " ".join(str(skalar(unit.get(k)) or "") for k in ("title", "name", "furnishing_note", "description_note"))
    text += " " + " ".join(str(custom(unit, k) or "") for k in (
        "zusatzausstattung", "zusatzausstattung_1", "zusatzausstattung_2", "zusatzausstattung_2_1", "zusatzausstattung_3",
        "weitere_ausstattungsmerkmale", "ausstattung", "usp"))
    wgk = str(custom(unit, "wgk") or "")
    if (wgk and not re.search(r"nicht|kein", wgk, re.IGNORECASE)) or custom(unit, "batterielager") is True \
            or re.search(r"batterielager|gefahrstoff|gefahrgut|\bwgk\b", text, re.IGNORECASE):
        funde.append("Gefahrgut/WGK/Batterie")
    kuehlanlage = str(custom(unit, "kuhlanlage") or "")
    if skalar(unit.get("rs_category")) == "COLD_STORAGE" or _vorhanden(_KUEHLUNG, text) \
            or (kuehlanlage.strip() and not re.search(r"nein|kein|klimatisiert", kuehlanlage, re.IGNORECASE)):
        funde.append("Kühlung")
    if _vorhanden(_KRAN, text):
        funde.append("Kran")
    if _vorhanden(_GLEIS, text):
        funde.append("Gleisanschluss")
    if re.search(r"freifl|au(?:ß|ss)enfl", text, re.IGNORECASE):
        funde.append("Freifläche")
    if re.search(r"produktion|werkstatt", text, re.IGNORECASE) or custom(unit, "objektkategorie") == "Halle/Produktion":
        funde.append("Produktion/Werkstatt")
    if re.search(r"ebenerdig", text, re.IGNORECASE) or (zahl(custom(unit, "anzahl_rampentore_2")) or 0) > 0:
        funde.append("ebenerdige Andienung")
    if re.search(r"24\s?/\s?7", text):
        funde.append("24/7")
    if custom(unit, "sprinkleranlage") or re.search(r"sprinkler", text, re.IGNORECASE):
        funde.append("Sprinkler")
    return tuple(funde)


HALLEN_KATEGORIEN = {"HALL", "INDUSTRY_HALL", "STORAGE_AREA", "STORAGE_HALL", "HIGH_LACK_STORAGE", "COLD_STORAGE"}


_SPANNE = re.compile(r"(\d[\d.,]*)\s*(?:m\s?[²2]|qm)?\s*(?:bis|–|—|-)\s*(\d[\d.,]*)\s*(?:m\s?[²2]|qm)", re.IGNORECASE)


def verfuegbar_laut_text(text) -> tuple[float | None, float | None]:
    """„Lagerfläche verfügbar“ ist Freitext: „3.919 m²“ → (None, 3919); „10.000 – 25.000 m² BGF“ →
    (10000, 25000), also frei bis 25.000 m², in Teilen ab 10.000 m²."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return None, float(text)
    if not isinstance(text, str):
        return None, None
    if m := _SPANNE.search(text):
        von, bis = zahl(m.group(1)), zahl(m.group(2))
        if von and bis and von < bis:
            return von, bis
    return None, zahl(text)


def hallenflaeche(unit: dict) -> float | None:
    """Die Hallen-/Lagerfläche – nicht irgendeine Fläche. Die Objektart taugt dafür nicht: Der
    Altbestand aus dem Import 01/2025 steht als „APARTMENT“ in Propstack (174 Einheiten, fast alle
    mit Lagerfläche), und Büro-Datensätze tragen die Bürofläche als Gesamtfläche. Also zählt das
    Feld Lagerfläche; die Gesamtfläche nur bei einer Halle ohne dieses Feld."""
    flaeche = (
        zahl(custom(unit, "lagerflache"))
        or verfuegbar_laut_text(custom(unit, "lagerflache_verfugbar"))[1]      # Altbestand: nur als Text „20.170 m²“
        or zahl(skalar(unit.get("industrial_area")))
    )
    if not flaeche and skalar(unit.get("rs_category")) in HALLEN_KATEGORIEN:
        flaeche = zahl(skalar(unit.get("property_space_value")))
    return flaeche or None


def freie_flaeche(unit: dict) -> tuple[float | None, float | None, float | None, str]:
    """(Fläche für den Abgleich, Gesamtfläche falls größer, „teilbar ab“ aus dem Text, Hinweis).

    Ist nur ein Teil der Halle frei, zählt der freie Teil – sonst geht eine 14.086-m²-Halle an ein
    Gesuch über 12.000 m², obwohl noch 3.919 m² zu haben sind (31 Einheiten, 26.11.2026). Sagt das
    Feld „verfügbar“ mehr als die Lagerfläche (12 Einheiten), bleibt die Lagerfläche stehen und der
    Widerspruch wird genannt: Welche Zahl stimmt, lässt sich aus den Feldern nicht entscheiden."""
    gesamt = hallenflaeche(unit)
    ab, frei = verfuegbar_laut_text(custom(unit, "lagerflache_verfugbar"))
    if not gesamt or not frei:
        return gesamt, None, None, ""
    if frei < gesamt * 0.9:
        return frei, gesamt, ab, ""
    if frei > gesamt * 1.1:
        return gesamt, None, None, f"Feld „Lagerfläche verfügbar“ nennt {frei:,.0f} m²".replace(",", ".")
    return gesamt, None, ab if ab and ab < gesamt * 0.98 else None, ""


_BEZUG_NUR_ART = {"quartal", "datum", "jahr", "monat"}


def bezug_von(unit: dict, heute: date) -> tuple[str, tuple[int, int] | None]:
    """(Text für den Vorschlag, Quartal oder None). Der Text gilt: „frei ab“, dann das Feld „Bezug“.
    Nennen beide einen Termin, zählt der spätere. Sagt der Text „auf Anfrage“, bleibt der Bezug
    offen – ein altes „Bezug Datum“ macht daraus kein „sofort“. Nur ohne jeden Text gilt das Datum."""
    texte = []
    for wert in (skalar(unit.get("free_from")), custom(unit, "bezug")):
        t = str(wert or "").strip()
        if t and t.casefold() not in _BEZUG_NUR_ART and t not in texte:
            texte.append(t)
    lesbar = [q for q in (quartal(t, heute, spaetestes=True) for t in texte) if q is not None]
    if lesbar:
        return texte[0], max(lesbar)
    if texte:
        return texte[0], None
    datum = str(custom(unit, "bezug_datum") or "")[:10]
    if datum and not datum.startswith("1970"):
        return datum, quartal(datum, heute, spaetestes=True)
    return "", None


def _rampen(unit: dict) -> float | None:
    """Feld „Rampentore“: „11 Stk.“ → 11, „keine (nur ebenerdige Tore)“ → 0. Das Feld
    `anzahl_rampentore_2` ist trotz seines Namens „Ebenerdige Tore“ (propstack-mcp/src/propstack/
    howto.ts) – als Rampenzahl gelesen stünden bei 170 Einheiten falsche Rampen im Vorschlag."""
    roh = custom(unit, "ramepntore")
    if roh in (None, ""):
        return None
    if isinstance(roh, str) and re.search(r"\bkeine?\b", roh, re.IGNORECASE):
        return 0.0
    return zahl(roh)


def _kennung(unit: dict) -> str:
    """Der letzte Teil des Namens: „Offenbergweg 5 – Unit 1.2“ und „Unit 1.2“ → „unit 1.2“."""
    name = str(skalar(unit.get("name")) or "").strip(" -–")
    return re.split(r"\s+[–-]\s+", name)[-1].strip().casefold() if name else ""


def aus_einheit(unit: dict, gruppe: str, heute: date) -> Flaeche:
    flaeche, gesamt, teilbar_text, flaechen_hinweis = freie_flaeche(unit)
    bezug_text, bezug = bezug_von(unit, heute)
    punkt = _koordinaten(unit)
    plz = _plz(unit)
    projekt = unit.get("project") if isinstance(unit.get("project"), dict) else {}
    makler = unit.get("broker") if isinstance(unit.get("broker"), dict) else {}
    eigentuemer_ids = tuple(
        int(r["client_id"]) for r in (unit.get("relationships") or [])
        if isinstance(r, dict) and r.get("internal_name") == "owner" and r.get("client_id")
    )
    return Flaeche(
        id=unit["id"],
        bezeichnung=_bezeichnung(unit),
        ort=_ort(unit),
        plz=plz,
        land=bundesland(skalar(unit.get("region")), plz) or PLZ_ZU_LAND.get(_plz_gebiet(unit)),
        strasse=str(skalar(unit.get("street")) or "").strip(),
        hausnummer=str(skalar(unit.get("house_number")) or "").strip(),
        projekt_id=skalar(unit.get("project_id")),
        projekt_titel=str(projekt.get("title") or "").strip(),
        gruppe=gruppe,
        flaeche=flaeche,
        teilbar_ab=_teilbar(unit, flaeche) or (teilbar_text if teilbar_text and flaeche and teilbar_text < flaeche * 0.98 else None),
        hoehe=zahl(custom(unit, "hallenhohe")) or zahl(skalar(unit.get("hall_height"))),
        rampen=_rampen(unit),
        bezug_text=bezug_text,
        bezug=bezug,
        lat=punkt[0] if punkt else None,
        lng=punkt[1] if punkt else None,
        # Altbestand: „133927 Björn Hecker SIGNA …“ – die Nummer davor ist eine alte Kennung
        eigentuemer=re.sub(r"^\d{4,}\s+", "", str(custom(unit, "eigentumer") or "").strip()),
        eigentuemer_kontakt_ids=eigentuemer_ids,
        provision=str(custom(unit, "provision_extern") or skalar(unit.get("courtage")) or "").strip(),
        miete_halle=zahl(custom(unit, "intern_mietpreis_hallenflache")),
        merkmale=_merkmale(unit),
        angelegt=str(skalar(unit.get("created_at")) or "")[:10],
        geaendert=str(skalar(unit.get("updated_at")) or "")[:10],
        # 26.11.2026: zehn Einheiten gelten als frei und tragen zugleich „100%“ (2019 steht in einer
        # Bemerkung „nur noch Büroflächen vakant“). Welche Angabe stimmt, entscheidet ein Mensch –
        # der Vorschlag bleibt, bekommt aber den Hinweis und rutscht nach hinten.
        voll_vermietet_laut_feld=bool(re.match(r"\s*100\s?%", str(custom(unit, "vermietungsstand_einheiten") or ""))),
        betreuer=str(makler.get("name") or "").strip(),
        flaeche_gesamt=gesamt,
        flaeche_hinweis=flaechen_hinweis,
        tore_ebenerdig=zahl(custom(unit, "anzahl_rampentore_2")),
        kennung=_kennung(unit),
    )


def _mittel(punkte: list[tuple[float, float]]) -> tuple[float, float]:
    return sum(p[0] for p in punkte) / len(punkte), sum(p[1] for p in punkte) / len(punkte)


def schaetze_lagen(flaechen: list[Flaeche], alle_einheiten: list[dict]) -> int:
    """Einheiten ohne Koordinaten bekommen eine geschätzte Lage aus dem übrigen Bestand (auch aus
    vermieteten Einheiten – deren Adresse stimmt ja). Gibt zurück, wie viele ohne Lage bleiben."""
    je_projekt: dict[int, list] = defaultdict(list)
    je_plz: dict[str, list] = defaultdict(list)
    je_plz3: dict[str, list] = defaultdict(list)
    je_ort: dict[str, list] = defaultdict(list)
    for unit in alle_einheiten:
        punkt = _koordinaten(unit)
        if not punkt:
            continue
        if pid := skalar(unit.get("project_id")):
            je_projekt[pid].append(punkt)
        if plz := _plz(unit):
            je_plz[plz].append(punkt)
            je_plz3[plz[:3]].append(punkt)
        if ort := ort_schluessel(_ort(unit)):
            je_ort[ort].append(punkt)

    offen = 0
    for f in flaechen:
        if f.lat is not None:
            continue
        for quelle, punkte in (
            ("Projekt", je_projekt.get(f.projekt_id) if f.projekt_id else None),
            ("PLZ", je_plz.get(f.plz) if f.plz else None),
            ("Ort", je_ort.get(ort_schluessel(f.ort)) if f.ort else None),
            ("PLZ-Gebiet", je_plz3.get(f.plz[:3]) if f.plz else None),
        ):
            if punkte:
                f.lat, f.lng = _mittel(punkte)
                f.lage_geschaetzt = quelle
                break
        else:
            offen += 1
    return offen


def fasse_zwillinge(flaechen: list[Flaeche]) -> list[Flaeche]:
    """Dieselbe Halle, zweimal angelegt: gleicher Ort, gleiche Straße und Hausnummer, gleiche Fläche,
    gleiche Bezeichnung der Einheit – aber in zwei Projekten oder einmal mit und einmal ohne Projekt
    (26.11.2026: elf Hallen in Kirchlengern, Bünde, Porta Westfalica und Rheine). Übrig bleibt ein
    Datensatz je Halle (Vermarktung vor Altbestand, dann der ältere); er merkt sich die IDs und
    Projekte der anderen und trägt das früheste Anlagedatum der Gruppe.

    Gleiche Adresse und gleiche Fläche allein reichen nicht: In einem Gewerbepark stehen sechs
    Einheiten zu je 388 m² („Unit 2“ und „Unit 2.02“ sind zwei Einheiten), und „Essen I“ und
    „Essen II“ sind zwei Flächen. Deshalb muss die Bezeichnung übereinstimmen, und zwei Einheiten
    desselben Projekts gelten nie als Dublette."""
    gruppen: dict[tuple, list[Flaeche]] = defaultdict(list)
    for f in flaechen:
        if f.strasse and f.flaeche and f.kennung and ort_schluessel(f.ort):
            gruppen[(ort_schluessel(f.ort), f.strasse.casefold(), f.hausnummer.casefold(), round(f.flaeche), f.kennung)].append(f)
    raus: set[int] = set()
    for gruppe in gruppen.values():
        if len(gruppe) < 2 or len({f.projekt_id for f in gruppe}) != len(gruppe):
            continue
        bleibt = min(gruppe, key=lambda f: (f.gruppe != VERMARKTUNG, f.angelegt or "9999", f.id))
        andere = [f for f in gruppe if f is not bleibt]
        bleibt.zwillinge = tuple(f.id for f in andere)
        bleibt.zwillings_projekte = tuple(f.projekt_id for f in andere if f.projekt_id)
        daten = [f.angelegt for f in gruppe if f.angelegt]
        bleibt.angelegt = min(daten) if daten else bleibt.angelegt
        raus.update(f.id for f in andere)
    return [f for f in flaechen if f.id not in raus]


def lade_bestand(einheiten: list[dict], heute: date) -> tuple[list[Flaeche], int]:
    """(angebotsfähige Flächen ohne Zwillinge, davon ohne jede Lage)."""
    flaechen = [aus_einheit(u, gruppe, heute) for u in einheiten if (gruppe := verfuegbar_als(u))]
    ohne_lage = schaetze_lagen(flaechen, einheiten)
    return fasse_zwillinge(flaechen), ohne_lage
