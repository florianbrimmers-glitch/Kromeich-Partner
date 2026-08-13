from __future__ import annotations

import logging
import re
import unicodedata

from . import config, propstack_gateway, regions
from .models import ComparableZeile, DriveDoc, Mietangebot, PropstackReport

logger = logging.getLogger(__name__)

_STRASSE_RE = re.compile(r"(stra(ss|ß)e|str\.?)\b", re.IGNORECASE)
_NICHT_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _entumlauten(text: str) -> str:
    ersetzt = (
        text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
        .replace("Ä", "Ae").replace("Ö", "Oe").replace("Ü", "Ue")
        .replace("ß", "ss")
    )
    return unicodedata.normalize("NFKD", ersetzt).encode("ascii", "ignore").decode("ascii")


def normalisiere_text(value: str | None) -> str:
    """'Balke-Dürr-Allee 7' -> 'balkeduerrallee7' (Vergleichsform)."""
    if not value:
        return ""
    return _NICHT_ALNUM_RE.sub("", _entumlauten(value).lower())


def normalisiere_strasse(value: str | None) -> str:
    """Straßenschreibweisen vereinheitlichen: 'Hamborner Str. 12' == 'Hamborner Straße 12'."""
    if not value:
        return ""
    return normalisiere_text(_STRASSE_RE.sub("str", _entumlauten(value).lower()))


# --- Propstack: Einheit -> Report-Zeile ------------------------------------
def _propstack_objektname(unit: dict) -> str:
    skalar = propstack_gateway.skalar
    for feld in ("name", "title", "street"):
        wert = skalar(unit.get(feld))
        if wert and str(wert).strip():
            return str(wert).strip()
    return f"Unit {unit.get('id')}"


def _propstack_adresse(unit: dict) -> str | None:
    skalar = propstack_gateway.skalar
    strasse = skalar(unit.get("street"))
    nummer = skalar(unit.get("house_number"))
    if not strasse:
        return None
    return f"{strasse} {nummer}".strip() if nummer is not None else str(strasse).strip()


def propstack_zu_zeilen_einer_unit(
    unit: dict, statistik: PropstackReport
) -> list[ComparableZeile]:
    """Eine Propstack-Einheit -> eine Zeile JE FLÄCHENART mit Miete.

    Hallen-, Büro- und Mezzaninemieten liegen in getrennten Feldern und in
    völlig verschiedenen Größenordnungen (4-8 vs. 12-14 vs. 3-4 €/m²). Sie
    werden deshalb als eigene Datenpunkte mit eigener Flächenart geführt und
    später getrennt aggregiert.

    Leere Liste, wenn es kein Mietobjekt ist oder keine Fläche eine Miete
    trägt. Das ist der Normalfall und keine Mängelmeldung: Mieten werden am
    Markt nicht geteilt.
    """
    skalar = propstack_gateway.skalar

    if not propstack_gateway.ist_mietobjekt(unit):
        statistik.keine_mietobjekte += 1
        return []

    plz = regions.normalize_plz(skalar(unit.get("zip_code")))
    leit = regions.leitregion(plz)
    zon = regions.zone(plz)
    vermietet = skalar(unit.get("rented")) is True
    if vermietet:
        statistik.vermietet += 1

    unit_id = str(unit.get("id"))
    objekt = _propstack_objektname(unit)
    basis = dict(
        quelle=config.QUELLE_PROPSTACK,
        file_id=unit_id,
        datei=objekt,
        quelle_link=f"https://app.propstack.de/properties/{unit_id}",
        vermietet=vermietet,
        objekt=objekt,
        adresse=_propstack_adresse(unit),
        plz=plz,
        ort=skalar(unit.get("city")),
        region_key=leit[0] if leit else None,
        region_label=leit[1] if leit else None,
        zone_key=zon[0] if zon else None,
        zone_label=zon[1] if zon else None,
        # Propstack führt eigene Mandate: die Miete ist eine ANGEBOTSMIETE von K&P.
        anbieter=(skalar((unit.get("broker") or {}).get("name"))
                  if isinstance(unit.get("broker"), dict) else None),
        datum=(skalar(unit.get("updated_at")) or skalar(unit.get("created_at")) or None),
        eigenes_angebot=True,
        confidence=1.0,   # strukturiertes Feld, keine LLM-Schätzung
    )

    gewuenscht = config.ausgewertete_flaechenarten()
    zeilen: list[ComparableZeile] = []
    for art in config.FLAECHENARTEN:
        kaltmiete, miete_feld = propstack_gateway.hole_betrag(unit, art.miete_felder)
        if kaltmiete is None:
            continue
        if art.name not in gewuenscht:
            # Nicht ausgewertete Flächenart (Standard: alles außer Halle/Lager).
            # Gezählt, damit die Auslassung im Log sichtbar bleibt.
            statistik.flaechenart_uebersprungen += 1
            continue

        miete_bis, _ = propstack_gateway.hole_betrag(unit, art.miete_bis_felder)
        nebenkosten, _ = propstack_gateway.hole_betrag(unit, art.nk_felder)
        flaeche, _ = propstack_gateway.hole_flaeche(unit, art.flaeche_felder)
        flaeche, flaechen_hinweis = pruefe_flaeche(flaeche)
        if flaechen_hinweis:
            statistik.flaeche_unplausibel += 1

        # Die Custom Fields stehen bereits in €/m²/Monat – hier wird NICHT
        # über die Fläche gerechnet. Unplausible NK werden verworfen, ohne
        # die Miete zu entwerten.
        if nebenkosten is not None and not (
            config.NEBENKOSTEN_MIN_EUR_QM <= nebenkosten <= config.NEBENKOSTEN_MAX_EUR_QM
        ):
            nebenkosten = None

        hinweis = []
        if miete_bis is not None and miete_bis != kaltmiete:
            hinweis.append(f"Spanne bis {miete_bis:.2f} €/m²".replace(".", ","))
        if vermietet:
            hinweis.append("vermietet")
        if flaechen_hinweis:
            hinweis.append(flaechen_hinweis)

        zeile = ComparableZeile(
            **basis,
            nutzungsart=art.name,
            miete_feld=miete_feld,
            flaeche_qm=flaeche,
            kaltmiete_eur_qm=kaltmiete,
            nebenkosten_eur_qm=nebenkosten,
            effektivmiete_eur_qm=effektivmiete(kaltmiete, None, None),
            option_hinweis=" · ".join(hinweis) or None,
        )
        zeile.ausschluss_grund = _plausibilitaet(zeile)
        if zeile.ausschluss_grund is None and not plz:
            zeile.ausschluss_grund = "keine PLZ – Region nicht zuordenbar"

        statistik.mit_miete += 1
        if miete_feld:
            statistik.miete_felder[miete_feld] = statistik.miete_felder.get(miete_feld, 0) + 1
        if flaeche is None:
            statistik.ohne_flaeche += 1
        zeilen.append(zeile)

    if not zeilen:
        statistik.ohne_miete += 1
        if propstack_gateway.preis_auf_anfrage(unit):
            statistik.preis_auf_anfrage += 1

    return zeilen


def propstack_zu_zeilen(
    units: list[dict], statistik: PropstackReport
) -> list[ComparableZeile]:
    statistik.units_geladen = len(units)
    zeilen: list[ComparableZeile] = []
    for unit in units:
        zeilen.extend(propstack_zu_zeilen_einer_unit(unit, statistik))
    return zeilen


# --- Ausschluss auf Dateinamen-Ebene (vor dem LLM-Call) --------------------
def _enthaelt_wort(name: str, marker: str) -> bool:
    """Marker als GANZES Wort (deutsche Plural-Endung erlaubt).

    Ohne die rechte Wortgrenze würde "Musterhausener Weg" als Vorlage gelten
    und ein echtes Angebot verschwinden lassen.
    """
    return re.search(rf"\b{re.escape(marker)}(n|en)?\b", name) is not None


def datei_ausschluss(dateiname: str) -> str | None:
    """Grund, warum eine Datei gar nicht extrahiert wird – oder None.

    Läuft VOR dem Claude-Call und spart damit Kosten für Vorlagen, die eigene
    Büromiete und Anlagen-Beiblätter (Task-Vorgabe für den Ausschluss).
    """
    name = _entumlauten(dateiname).lower()
    if any(marker in name for marker in config.EIGENMIETE_MARKER):
        return "Kromeich-Eigenmiete (eigene Büromiete, kein Marktangebot)"
    if any(_enthaelt_wort(name, marker) for marker in config.VORLAGE_MARKER):
        return "Vorlage/Muster (kein echtes Angebot)"
    if any(_enthaelt_wort(name, marker) for marker in config.ANLAGEN_MARKER):
        return "Anlage/Beiblatt (keine eigenen Konditionen)"
    return None


def angebot_ausschluss(angebot: Mietangebot) -> str | None:
    """Ausschlussgrund aus der Extraktion selbst – oder None."""
    if angebot.ist_eigenmiete:
        return "Kromeich-Eigenmiete (laut Extraktion)"
    if angebot.ist_vorlage:
        return "Vorlage/Muster (laut Extraktion)"
    if angebot.ist_anlage:
        return "Anlage/Beiblatt (laut Extraktion)"
    if not angebot.ist_mietangebot:
        return "kein Mietangebot"
    if angebot.confidence < config.CONFIDENCE_THRESHOLD:
        return f"Confidence {angebot.confidence:.2f} unter Schwelle {config.CONFIDENCE_THRESHOLD}"
    return None


def ist_eigenes_angebot(angebot: Mietangebot) -> bool | None:
    """Eigenes vs. erhaltenes Angebot (Task: 'Flag eigene vs. erhaltene')."""
    if angebot.eigenes_angebot is not None:
        return angebot.eigenes_angebot
    anbieter = _entumlauten(angebot.anbieter or "").lower()
    if anbieter and any(marker in anbieter for marker in config.EIGENE_ANBIETER_MARKER):
        return True
    return None


# --- Versions-Dedup über Dokumente hinweg ---------------------------------
def objekt_key(angebot: Mietangebot, file_id: str) -> str:
    """Identität des Angebots für den Versionsvergleich.

    Ohne belastbare Objektkennung wird bewusst NICHT gruppiert (file_id als
    Key) – lieber eine Dublette in der Statistik als ein verlorenes Angebot.
    """
    plz = regions.normalize_plz(angebot.plz)
    adresse = normalisiere_strasse(angebot.adresse)
    anbieter = normalisiere_text(angebot.anbieter)
    if plz and adresse:
        return f"adr|{plz}|{adresse}|{anbieter}"
    if angebot.objekt:
        return f"obj|{normalisiere_text(angebot.objekt)}|{anbieter}"
    if adresse:
        return f"str|{adresse}|{anbieter}"
    return f"file|{file_id}"


def _version_sortkey(paar: tuple[DriveDoc, Mietangebot]) -> tuple[str, str]:
    """Jüngste Version gewinnt: Angebotsdatum, sonst Drive-modifiedTime."""
    doc, angebot = paar
    return (angebot.datum or "", doc.modified_time or "")


def dedupliziere_versionen(
    paare: list[tuple[DriveDoc, Mietangebot]],
) -> tuple[list[tuple[DriveDoc, Mietangebot]], list[tuple[DriveDoc, str]]]:
    """Pro Objekt+Anbieter nur die jüngste Fassung behalten (Task-Vorgabe).

    Rückgabe: (behaltene Paare, verworfene als (doc, Grund)).
    """
    gruppen: dict[str, list[tuple[DriveDoc, Mietangebot]]] = {}
    for doc, angebot in paare:
        gruppen.setdefault(objekt_key(angebot, doc.file_id), []).append((doc, angebot))

    behalten: list[tuple[DriveDoc, Mietangebot]] = []
    verworfen: list[tuple[DriveDoc, str]] = []
    for gruppe in gruppen.values():
        if len(gruppe) == 1:
            behalten.append(gruppe[0])
            continue
        sortiert = sorted(gruppe, key=_version_sortkey, reverse=True)
        neuste = sortiert[0]
        behalten.append(neuste)
        for doc, _ in sortiert[1:]:
            verworfen.append((
                doc,
                f"älteres Duplikat/Version – jüngste Fassung ist {neuste[0].name}",
            ))
    return behalten, verworfen


# --- Normalisierung auf Report-Zeilen -------------------------------------
def effektivmiete(
    kaltmiete: float | None, laufzeit_monate: int | None, mietfreie_monate: float | None
) -> float | None:
    """Kaltmiete über die Laufzeit geglättet um die mietfreie Zeit."""
    if kaltmiete is None:
        return None
    if not mietfreie_monate:
        return round(kaltmiete, 2)
    if not laufzeit_monate or laufzeit_monate <= 0:
        return None
    if mietfreie_monate >= laufzeit_monate:
        return None
    return round(kaltmiete * (laufzeit_monate - mietfreie_monate) / laufzeit_monate, 2)


def normalisiere_nutzungsart(wert: str | None) -> str | None:
    """Freitext-Nutzungsart auf die Flächenart-Vokabel bringen.

    Das LLM liest aus den Drive-Angeboten "Logistik" oder "Halle", Propstack
    führt "Halle/Lager". Ohne diese Abbildung stünden Drive- und
    Propstack-Zeilen desselben Marktes in getrennten Abschnitten.
    Unbekannte Werte bleiben unverändert – lieber ein eigener Abschnitt als
    eine falsche Einordnung.
    """
    if not wert:
        return wert
    schluessel = _entumlauten(str(wert)).strip().lower()
    return config.NUTZUNGSART_SYNONYME.get(schluessel, wert)


def pruefe_flaeche(flaeche: float | None) -> tuple[float | None, str | None]:
    """Unplausible Fläche verwerfen – aber NICHT den Datenpunkt.

    Die Fläche ist nur Größenkontext; die Mieten stehen bereits als €/m². Eine
    kaputte Fläche darf also keine gültige Miete entwerten.

    Realer Fall in Propstack (gemessen 12.08.2026, ~190 Einheiten betroffen):
    in `*_gesamt`-Felder wurde die deutsche Tausendertrennung in ein
    Dezimalfeld getippt – "10.403" wird als 10,403 m² gespeichert und als
    "10,40 m²" angezeigt. Der Verdacht wird als Hinweis mitgegeben, damit die
    Daten in Propstack korrigiert werden können; hochgerechnet wird NICHT.
    """
    if flaeche is None:
        return None, None
    if config.FLAECHE_MIN_QM <= flaeche <= config.FLAECHE_MAX_QM:
        return flaeche, None
    verdacht = ""
    if 0 < flaeche < 100 and round(flaeche % 1, 3) not in (0.0,):
        verdacht = " – Verdacht: Tausendertrennung in Propstack"
    return None, f"Fläche {flaeche} m² unplausibel, verworfen{verdacht}"


def _plausibilitaet(zeile: ComparableZeile) -> str | None:
    if zeile.kaltmiete_eur_qm is None:
        return "keine Kaltmiete extrahierbar"
    if zeile.kaltmiete_eur_qm > config.KALTMIETE_MAX_EUR_QM:
        return (
            f"Kaltmiete {zeile.kaltmiete_eur_qm} €/m² über "
            f"{config.KALTMIETE_MAX_EUR_QM} – sieht wie eine absolute "
            "Monatsmiete aus, nicht wie €/m²"
        )
    if zeile.kaltmiete_eur_qm < config.KALTMIETE_MIN_EUR_QM:
        return f"Kaltmiete {zeile.kaltmiete_eur_qm} €/m² unter {config.KALTMIETE_MIN_EUR_QM}"
    if zeile.laufzeit_monate is not None and not (
        config.LAUFZEIT_MIN_MONATE <= zeile.laufzeit_monate <= config.LAUFZEIT_MAX_MONATE
    ):
        return f"Laufzeit {zeile.laufzeit_monate} Monate unplausibel"
    return None


def zu_zeilen(doc: DriveDoc, angebot: Mietangebot) -> list[ComparableZeile]:
    """Ein Angebot -> eine Zeile je Laufzeit-Option (Task-Vorgabe).

    Ausgeschlossene Zeilen bleiben MIT Grund erhalten, damit im Datensatz
    nachvollziehbar ist, warum ein Angebot nicht in den Median eingeht.
    """
    plz = regions.normalize_plz(angebot.plz)
    leit = regions.leitregion(plz)
    zon = regions.zone(plz)
    eigen = ist_eigenes_angebot(angebot)
    nutzungsart = normalisiere_nutzungsart(angebot.nutzungsart)
    # Anders als bei Propstack werden nicht ausgewertete Flächenarten hier
    # NICHT verworfen, sondern mit Grund im Datensatz behalten: Drive-Zeilen
    # sind wenige und haben einen LLM-Call gekostet.
    art_ausschluss = (
        None if nutzungsart in config.ausgewertete_flaechenarten()
        else f"Flächenart {nutzungsart or 'unbekannt'} nicht im Report"
    )

    optionen = angebot.optionen or []
    if not optionen:
        logger.info("%s: Angebot ohne Konditions-Option", doc.name)

    zeilen: list[ComparableZeile] = []
    for option in optionen or [None]:
        flaeche = (option.flaeche_qm if option else None) or angebot.flaeche_qm
        kaltmiete = option.kaltmiete_eur_qm if option else None
        aus_absolut = False

        # Absolute Monatsmiete auf €/m² umrechnen (Task-Regel)
        if kaltmiete is None and option and option.kaltmiete_absolut_eur and flaeche:
            if flaeche > 0:
                kaltmiete = round(option.kaltmiete_absolut_eur / flaeche, 2)
                aus_absolut = True

        flaeche, _ = pruefe_flaeche(flaeche) if not aus_absolut else (flaeche, None)
        nebenkosten = option.nebenkosten_eur_qm if option else None
        if nebenkosten is not None and not (
            config.NEBENKOSTEN_MIN_EUR_QM <= nebenkosten <= config.NEBENKOSTEN_MAX_EUR_QM
        ):
            logger.info(
                "%s: Nebenkosten %s €/m² unplausibel – Feld verworfen, Kaltmiete bleibt",
                doc.name, nebenkosten,
            )
            nebenkosten = None

        laufzeit = option.laufzeit_monate if option else None
        mietfrei = option.mietfreie_monate if option else None

        zeile = ComparableZeile(
            file_id=doc.file_id,
            datei=doc.name,
            quelle_link=doc.web_link,
            fundstellen=doc.fundstellen,
            objekt=angebot.objekt,
            adresse=angebot.adresse,
            plz=plz,
            ort=angebot.ort,
            region_key=leit[0] if leit else None,
            region_label=leit[1] if leit else None,
            zone_key=zon[0] if zon else None,
            zone_label=zon[1] if zon else None,
            anbieter=angebot.anbieter,
            empfaenger=angebot.empfaenger,
            datum=angebot.datum,
            eigenes_angebot=eigen,
            flaeche_qm=flaeche,
            nutzungsart=nutzungsart,
            laufzeit_monate=laufzeit,
            kaltmiete_eur_qm=kaltmiete,
            nebenkosten_eur_qm=nebenkosten,
            mietfreie_monate=mietfrei,
            effektivmiete_eur_qm=effektivmiete(kaltmiete, laufzeit, mietfrei),
            sicherheit=angebot.sicherheit,
            indexierung=angebot.indexierung,
            option_hinweis=option.hinweis if option else None,
            normalisiert_aus_absolut=aus_absolut,
            confidence=angebot.confidence,
        )
        zeile.ausschluss_grund = art_ausschluss or _plausibilitaet(zeile)
        if zeile.ausschluss_grund is None and not plz:
            zeile.ausschluss_grund = "keine PLZ – Region nicht zuordenbar"
        zeilen.append(zeile)

    return zeilen
