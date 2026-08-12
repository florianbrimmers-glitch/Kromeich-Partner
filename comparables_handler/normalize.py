from __future__ import annotations

import logging
import re
import unicodedata

from . import config, regions
from .models import ComparableZeile, DriveDoc, Mietangebot

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


def _plausibilitaet(zeile: ComparableZeile) -> str | None:
    if zeile.kaltmiete_eur_qm is None:
        return "keine Kaltmiete extrahierbar"
    if not (config.KALTMIETE_MIN_EUR_QM <= zeile.kaltmiete_eur_qm <= config.KALTMIETE_MAX_EUR_QM):
        return (
            f"Kaltmiete {zeile.kaltmiete_eur_qm} €/m² außerhalb "
            f"{config.KALTMIETE_MIN_EUR_QM}-{config.KALTMIETE_MAX_EUR_QM}"
        )
    if zeile.flaeche_qm is not None and not (
        config.FLAECHE_MIN_QM <= zeile.flaeche_qm <= config.FLAECHE_MAX_QM
    ):
        return f"Fläche {zeile.flaeche_qm} m² unplausibel"
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
            nutzungsart=angebot.nutzungsart,
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
        zeile.ausschluss_grund = _plausibilitaet(zeile)
        if zeile.ausschluss_grund is None and not plz:
            zeile.ausschluss_grund = "keine PLZ – Region nicht zuordenbar"
        zeilen.append(zeile)

    return zeilen
