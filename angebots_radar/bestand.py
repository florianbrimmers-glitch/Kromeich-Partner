"""Die Einheiten aus Propstack (`GET /v1/units?expand=1`) als angebotsfähiger Bestand.

Stand 26.11.2026 (2.551 Einheiten, nur gelesen): 1.310 kommen für ein Angebot in Frage –
1.110 in Vermarktung, 200 Altbestand ohne Propstack-Status, aber „Status Logistik“ = Aktiv.
Drei Dinge fängt dieses Modul ab:

- **267 davon haben keine Koordinaten** (245 in Vermarktung) – eine Umkreissuche sieht sie nicht,
  auch Propstacks eigenes Suchprofil-Matching nicht. Hier bekommen sie eine geschätzte Lage:
  erst über andere Einheiten desselben Projekts, dann über die Postleitzahl (fünf, dann drei
  Stellen) aus dem übrigen Bestand. Der Vorschlag nennt das („Lage geschätzt“).
- **„Lagerfläche teilbar ab“ steht bei 152 Einheiten um den Faktor 1.000 zu klein** im Feld
  (10.385 m² als 10.385 gespeichert). Werte unter 50 werden als Tausender gelesen.
- **„Bezug“ ist Freitext.** Gelesen wird, was sich lesen lässt (felder.quartal); der Text bleibt
  im Vorschlag stehen.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .felder import bundesland, custom, ort_schluessel, quartal, skalar, zahl

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


def _plz(unit: dict) -> str:
    """Fünfstellige PLZ. Im Altbestand steht sie teils in der Straße („40764 Langenfeld“)."""
    for key in ("zip_code", "street", "address"):
        if m := re.search(r"\b(\d{5})\b", str(skalar(unit.get(key)) or "")):
            return m.group(1)
    return ""


def _ort(unit: dict) -> str:
    ort = str(skalar(unit.get("city")) or "").strip()
    if ort:
        return ort
    # Altbestand: „40764 Langenfeld (Rheinland)“ oder „04 Grimma“ in der Straße, der Ort im PLZ-Feld
    strasse = str(skalar(unit.get("street")) or "")
    if m := re.match(r"\s*\d{2,5}\s+(.+)", strasse):
        return m.group(1).strip()
    plz_feld = str(skalar(unit.get("zip_code")) or "").strip()
    return plz_feld if plz_feld and not plz_feld.isdigit() and plz_feld != "Deutschland" else ""


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
    if wert < 50:                       # 10.385 m² als 10.385 gespeichert (152 Einheiten, 26.11.2026)
        wert *= 1000
    if flaeche and wert >= flaeche * 0.98:
        return None                     # „teilbar ab“ = ganze Fläche heißt: nicht teilbar
    return wert


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
    if re.search(r"k(?:ü|ue)hl|tiefk", text, re.IGNORECASE):
        funde.append("Kühlung")
    if re.search(r"\bkran|kranbahn", text, re.IGNORECASE):
        funde.append("Kran")
    if re.search(r"gleis", text, re.IGNORECASE):
        funde.append("Gleisanschluss")
    if re.search(r"freifl|au(?:ß|ss)enfl", text, re.IGNORECASE):
        funde.append("Freifläche")
    if re.search(r"produktion|werkstatt", text, re.IGNORECASE) or custom(unit, "objektkategorie") == "Halle/Produktion":
        funde.append("Produktion/Werkstatt")
    if re.search(r"ebenerdig", text, re.IGNORECASE):
        funde.append("ebenerdige Andienung")
    if re.search(r"24\s?/\s?7", text):
        funde.append("24/7")
    if custom(unit, "sprinkleranlage") or re.search(r"sprinkler", text, re.IGNORECASE):
        funde.append("Sprinkler")
    return tuple(funde)


HALLEN_KATEGORIEN = {"HALL", "INDUSTRY_HALL", "STORAGE_AREA", "STORAGE_HALL", "HIGH_LACK_STORAGE", "COLD_STORAGE"}


def hallenflaeche(unit: dict) -> float | None:
    """Die Hallen-/Lagerfläche – nicht irgendeine Fläche. Die Objektart taugt dafür nicht: Der
    Altbestand aus dem Import 01/2025 steht als „APARTMENT“ in Propstack (174 Einheiten, fast alle
    mit Lagerfläche), und Büro-Datensätze tragen die Bürofläche als Gesamtfläche. Also zählt das
    Feld Lagerfläche; die Gesamtfläche nur bei einer Halle ohne dieses Feld."""
    flaeche = (
        zahl(custom(unit, "lagerflache"))
        or zahl(custom(unit, "lagerflache_verfugbar"))      # Altbestand: nur als Text „20.170 m²“
        or zahl(skalar(unit.get("industrial_area")))
    )
    if not flaeche and skalar(unit.get("rs_category")) in HALLEN_KATEGORIEN:
        flaeche = zahl(skalar(unit.get("property_space_value")))
    return flaeche or None


def aus_einheit(unit: dict, gruppe: str, heute: date) -> Flaeche:
    flaeche = hallenflaeche(unit)
    bezug_text = str(custom(unit, "bezug") or skalar(unit.get("free_from")) or "").strip()
    bezug = quartal(str(custom(unit, "bezug_datum") or ""), heute, spaetestes=True) or quartal(bezug_text, heute, spaetestes=True)
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
        land=bundesland(skalar(unit.get("region")), plz),
        strasse=str(skalar(unit.get("street")) or "").strip(),
        projekt_id=skalar(unit.get("project_id")),
        projekt_titel=str(projekt.get("title") or "").strip(),
        gruppe=gruppe,
        flaeche=flaeche,
        teilbar_ab=_teilbar(unit, flaeche),
        hoehe=zahl(custom(unit, "hallenhohe")) or zahl(skalar(unit.get("hall_height"))),
        rampen=zahl(custom(unit, "ramepntore")) or zahl(custom(unit, "anzahl_rampentore_2")),   # so heißt das Feld
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


def lade_bestand(einheiten: list[dict], heute: date) -> tuple[list[Flaeche], int]:
    """(angebotsfähige Flächen, davon ohne jede Lage)."""
    flaechen = [aus_einheit(u, gruppe, heute) for u in einheiten if (gruppe := verfuegbar_als(u))]
    ohne_lage = schaetze_lagen(flaechen, einheiten)
    return flaechen, ohne_lage
