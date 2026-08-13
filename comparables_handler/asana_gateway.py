"""Monatsbericht als Asana-Unteraufgabe mit PDF-Anhang.

Struktur (mit K&P festgelegt am 13.08.2026):

    03. (VER) Vermietung / Leasingpaket
      └─ Vergleichsmieten – Monatsberichte        (Oberaufgabe, ASANA_PARENT_TASK_ID)
           ├─ Vergleichsmieten August 2026        (je Lauf eine Unteraufgabe)
           │    ├─ Vergleichsmieten_August_2026.pdf          (intern)
           │    └─ Vergleichsmieten_August_2026_extern.pdf   (freigegeben)
           └─ Vergleichsmieten September 2026
                └─ …

WICHTIG – zwei verschiedene Zugänge:

Der Asana-MCP-Connector (Claude-Session) kann Aufgaben anlegen, aber KEINE
Dateien anhängen; ein Attachment-Tool existiert dort nicht. Der Upload läuft
deshalb über die REST-API mit einem Personal Access Token – dasselbe Secret,
das der events_handler nutzt (`ASANA_ACCESS_TOKEN` u.a.). Ohne Token macht
dieser Handler nichts und sagt es im Log; der Report selbst läuft weiter.

Idempotenz: zwei Läufe im selben Monat dürfen nicht zwei Unteraufgaben
erzeugen. Gesucht wird über den exakten Namen; existiert die Unteraufgabe, wird
ihre Beschreibung aktualisiert und die Anhänge werden ERSETZT (erst der neue
hochgeladen, dann der alte entfernt). Überspringen wäre falsch: ein
Wiederholungslauf trägt den neueren Stand, und eine überholte Datei mit dem
Namen des aktuellen Monats bliebe sonst liegen.
"""
from __future__ import annotations

import logging
import os
import time

import httpx

from . import aggregate, config
from .models import RegionStats, RunReport

logger = logging.getLogger(__name__)

ASANA_BASE_URL = "https://app.asana.com/api/1.0"
MAX_ATTEMPTS = 4

# Asana nimmt bis 100 MB; unsere PDFs liegen bei ~50 KB. Die Grenze steht hier
# nur, damit ein versehentlich riesiges Artefakt nicht in einen Timeout läuft.
MAX_ANHANG_BYTES = 25 * 1024 * 1024


def _headers(json: bool = True) -> dict:
    kopf = {
        "Authorization": f"Bearer {config.asana_token()}",
        "Accept": "application/json",
    }
    if json:
        # Beim Multipart-Upload MUSS dieser Header fehlen, sonst setzt httpx
        # die Boundary nicht und Asana antwortet mit 400.
        kopf["Content-Type"] = "application/json"
    return kopf


def _request(method: str, path: str, *, json: dict | None = None,
             params: dict | None = None) -> httpx.Response:
    """Asana-Request mit Retry (Backoff 2**attempt) bei 429/5xx/Netzfehlern.

    Bewusst dieselbe Fehlerbehandlung wie events_handler/asana_gateway.py – die
    Handler sind eigenständig, das Verhalten gegenüber Asana aber gleich.
    """
    last_error: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            time.sleep(2**attempt)
        try:
            response = httpx.request(
                method, f"{ASANA_BASE_URL}{path}",
                headers=_headers(), json=json, params=params, timeout=30.0,
            )
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning("Asana %s %s: HTTP %s (Versuch %d/%d)",
                               method, path, response.status_code, attempt + 1, MAX_ATTEMPTS)
                last_error = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response)
                continue
            if response.status_code >= 400:
                logger.error("Asana %s %s fehlgeschlagen: HTTP %s – %s",
                             method, path, response.status_code, response.text[:500])
                response.raise_for_status()
            return response
        except httpx.HTTPStatusError:
            raise
        except httpx.HTTPError as e:
            logger.warning("Asana %s %s: %s (Versuch %d/%d)",
                           method, path, e, attempt + 1, MAX_ATTEMPTS)
            last_error = e

    raise last_error if last_error else RuntimeError(f"Asana {method} {path} fehlgeschlagen")


# --- Aufgabe finden / anlegen ----------------------------------------------
def finde_unteraufgabe(parent_gid: str, name: str) -> str | None:
    """GID der Unteraufgabe mit genau diesem Namen, sonst None."""
    daten = _request("GET", f"/tasks/{parent_gid}/subtasks",
                     params={"opt_fields": "name", "limit": 100}).json()
    for eintrag in daten.get("data") or []:
        if (eintrag.get("name") or "").strip() == name.strip():
            return eintrag.get("gid")
    return None


def vorhandene_anhaenge(task_gid: str) -> dict[str, str]:
    """Dateiname -> Anhang-GID der bereits hängenden Dateien."""
    daten = _request("GET", "/attachments", params={
        "parent": task_gid, "opt_fields": "name", "limit": 100,
    }).json()
    return {
        (a.get("name") or "").strip(): a.get("gid")
        for a in (daten.get("data") or []) if a.get("gid")
    }


def loesche_anhang(gid: str) -> bool:
    """Alten Anhang entfernen, nachdem der neue hängt."""
    try:
        _request("DELETE", f"/attachments/{gid}")
        return True
    except Exception as e:
        # Zwei Dateien gleichen Namens sind unschön, aber harmlos – die
        # Aufgabe hat dann den neuen UND den alten Stand. Kein Abbruch.
        logger.warning("Alter Anhang %s konnte nicht entfernt werden: %s", gid, e)
        return False


def haenge_datei_an(task_gid: str, pfad: str, name: str | None = None) -> str | None:
    """Datei an eine Aufgabe anhängen (POST /attachments, multipart).

    Rückgabe: GID des Anhangs oder None. Ein fehlgeschlagener Upload ist kein
    Grund, den Lauf abzubrechen – der Report existiert dann trotzdem.
    """
    if not os.path.exists(pfad):
        logger.warning("Anhang %s existiert nicht – übersprungen", pfad)
        return None
    groesse = os.path.getsize(pfad)
    if groesse > MAX_ANHANG_BYTES:
        logger.warning("Anhang %s ist %.1f MB – über der Grenze, übersprungen",
                       pfad, groesse / 1024 / 1024)
        return None

    dateiname = name or os.path.basename(pfad)
    with open(pfad, "rb") as f:
        inhalt = f.read()

    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            time.sleep(2**attempt)
        try:
            response = httpx.post(
                f"{ASANA_BASE_URL}/attachments",
                headers=_headers(json=False),
                data={"parent": task_gid},
                files={"file": (dateiname, inhalt, "application/pdf")},
                timeout=120.0,
            )
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning("Asana-Upload %s: HTTP %s (Versuch %d/%d)",
                               dateiname, response.status_code, attempt + 1, MAX_ATTEMPTS)
                last_error = RuntimeError(f"HTTP {response.status_code}")
                continue
            if response.status_code >= 400:
                logger.error("Asana-Upload %s fehlgeschlagen: HTTP %s – %s",
                             dateiname, response.status_code, response.text[:500])
                return None
            gid = ((response.json().get("data") or {}).get("gid"))
            logger.info("Asana-Anhang hochgeladen: %s (%.0f KB, gid %s)",
                        dateiname, groesse / 1024, gid)
            return gid
        except httpx.HTTPError as e:
            logger.warning("Asana-Upload %s: %s (Versuch %d/%d)",
                           dateiname, e, attempt + 1, MAX_ATTEMPTS)
            last_error = e

    logger.error("Asana-Upload %s endgültig fehlgeschlagen: %s", dateiname, last_error)
    return None


# --- Inhalt der Unteraufgabe ----------------------------------------------
def aufgaben_name(stand: str) -> str:
    """'August 2026' -> 'Vergleichsmieten August 2026'.

    Der Name ist der Idempotenz-Schlüssel: er muss aus dem Stand allein
    reproduzierbar sein, sonst legt ein zweiter Lauf eine zweite Aufgabe an.
    """
    return f"Vergleichsmieten {stand}"


def anhang_name(stand: str, fassung: str) -> str:
    """Dateiname im Anhang – sprechend, nicht 'comparables_report.pdf'."""
    stamm = f"Vergleichsmieten_{stand.replace(' ', '_')}"
    if fassung == config.VERTRAULICH_EXTERN:
        return f"{stamm}_extern.pdf"
    return f"{stamm}.pdf"


def _lauf_link() -> str | None:
    """Link auf den GitHub-Actions-Lauf, wenn wir in Actions laufen."""
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def baue_notiz(
    stats: list[RegionStats], report: RunReport, stand: str,
    tabellen: list | None = None, stand_vorher: str | None = None,
) -> str:
    """Beschreibung der Unteraufgabe: die Zahlen, die man ohne PDF sehen will."""
    zeilen: list[str] = [f"Vergleichsmieten – Stand {stand}", ""]

    ges = aggregate.gesamt(stats)
    arten = aggregate.flaechenarten(stats)
    if ges is None or ges.n == 0:
        zeilen.append("Keine verwertbaren Mieten in diesem Lauf.")
        return "\n".join(zeilen)

    art = arten[0] if arten else ""
    art_ges = aggregate.art_gesamt(stats, art) if art else None
    basis = art_ges or ges

    def _eur(wert: float | None) -> str:
        return f"{wert:.2f}".replace(".", ",") if wert is not None else "–"

    zeilen.append(f"Flächenart: {art or 'alle'}")
    zeilen.append(f"Datenbasis: {basis.n} Standorte, {basis.n_einheiten} erfasste Einheiten")
    zeilen.append(f"Median: {_eur(basis.median_kaltmiete)} €/m²/Monat")

    # Ø und Spitze stehen nur in der Kennzahlen-Tabelle (Gesamtzeile).
    kennzahl = None
    for tabelle in tabellen or []:
        if tabelle.flaechenart == art and tabelle.gesamt:
            kennzahl = tabelle.gesamt
            break
    if kennzahl:
        zeilen.append(f"Ø-Miete: {_eur(kennzahl.durchschnittsmiete)} €/m²  ·  "
                      f"Spitzenmiete: {_eur(kennzahl.spitzenmiete)} €/m²")
        if kennzahl.veraenderung_prozent is not None and stand_vorher:
            vz = "+" if kennzahl.veraenderung_prozent > 0 else ""
            zeilen.append(
                f"Veränderung gegen {stand_vorher}: {vz}"
                f"{kennzahl.veraenderung_prozent:.1f}".replace(".", ",") + " %")
        elif not stand_vorher:
            zeilen.append("Periodenvergleich: noch keine Basis "
                          "(Zeitreihe beginnt mit diesem Lauf)")

    for tabelle in tabellen or []:
        if tabelle.flaechenart != art:
            continue
        markt = [z for z in tabelle.zeilen if z.ebene == "position"]
        if markt:
            zeilen += ["", "Märkte (Median, n = Standorte):"]
            zeilen += [f"  {z.label}: {_eur(z.median_jetzt)} €/m² (n={z.n})" for z in markt]
        break

    zeilen += [
        "",
        "Anhänge – zwei Fassungen:",
        f"  {anhang_name(stand, config.VERTRAULICH_INTERN)} – INTERN. Enthält Einzelwerte "
        "und die Liste der erfassten Objekte. Nicht nach außen geben.",
        f"  {anhang_name(stand, config.VERTRAULICH_EXTERN)} – für Kundengespräche "
        f"freigegeben. Nur Märkte ab {config.MIN_N_EXTERN} Standorten, keine Objektliste.",
    ]

    quelle_text = {
        config.QUELLE_PROPSTACK: "Propstack",
        config.QUELLE_DRIVE: "Google Drive",
        config.QUELLE_BEIDE: "Propstack + Google Drive",
    }.get(report.quelle, report.quelle)
    zeilen += ["", f"Quelle: {quelle_text}"]
    if report.quelle in (config.QUELLE_PROPSTACK, config.QUELLE_BEIDE):
        ps = report.propstack
        zeilen.append(f"Propstack: {ps.units_geladen} Miet-Einheiten geprüft, "
                      f"{ps.mit_miete} mit hinterlegter Miete")
    if report.fehler:
        zeilen += ["", f"Hinweise aus dem Lauf ({len(report.fehler)}):"]
        zeilen += [f"  - {f}" for f in report.fehler[:5]]
    link = _lauf_link()
    if link:
        zeilen += ["", f"Lauf: {link}"]
    zeilen += ["", "(automatisch erzeugt – comparables_handler)"]
    return "\n".join(zeilen)


# --- Orchestrierung --------------------------------------------------------
# Anhänge in fester Reihenfolge: die interne Fassung ist die vollständige und
# steht deshalb oben. Alphabetisch stünde "extern" vor "intern".
_FASSUNG_REIHENFOLGE = (config.VERTRAULICH_INTERN, config.VERTRAULICH_EXTERN)


def _in_reihenfolge(pdfs: dict[str, str]) -> list[tuple[str, str]]:
    bekannt = [(f, pdfs[f]) for f in _FASSUNG_REIHENFOLGE if f in pdfs]
    rest = [(f, p) for f, p in sorted(pdfs.items()) if f not in _FASSUNG_REIHENFOLGE]
    return bekannt + rest


def veroeffentliche(
    stats: list[RegionStats], report: RunReport, stand: str,
    pdfs: dict[str, str], tabellen: list | None = None,
    stand_vorher: str | None = None,
) -> str | None:
    """Monatsbericht als Unteraufgabe anlegen/aktualisieren. Rückgabe: Link.

    Kein Token oder keine Oberaufgabe konfiguriert -> übersprungen, nicht
    abgebrochen. Der Comparables-Report ist auch ohne Asana vollständig.
    """
    if not config.asana_aktiv():
        logger.info("Asana übersprungen: %s", config.asana_grund())
        return None

    parent = config.asana_parent_task_id()
    name = aufgaben_name(stand)
    notiz = baue_notiz(stats, report, stand, tabellen, stand_vorher)

    if config.no_write():
        modus = "NO_WRITE"
        logger.info("[%s] Würde Asana-Unteraufgabe %r unter %s anlegen/aktualisieren, "
                    "Anhänge: %s", modus, name, parent,
                    ", ".join(anhang_name(stand, f) for f, _ in _in_reihenfolge(pdfs))
                    or "keine")
        logger.info("[%s] Beschreibung:\n%s", modus, notiz)
        return None

    gid = finde_unteraufgabe(parent, name)
    if gid:
        logger.info("Asana-Unteraufgabe %r existiert (gid %s) – wird aktualisiert", name, gid)
        _request("PUT", f"/tasks/{gid}", json={"data": {"notes": notiz}})
    else:
        erstellt = _request("POST", "/tasks", json={"data": {
            "parent": parent, "name": name, "notes": notiz,
        }}).json().get("data") or {}
        gid = erstellt.get("gid")
        if not gid:
            logger.error("Asana: Unteraufgabe konnte nicht angelegt werden")
            report.fehler.append("Asana: Unteraufgabe konnte nicht angelegt werden")
            return None
        logger.info("Asana-Unteraufgabe angelegt: %r (gid %s)", name, gid)

    # Anhänge ERSETZEN, nicht überspringen: ein Wiederholungslauf findet
    # gleichnamige Dateien vor, trägt aber den neueren Stand. Übersprungen
    # bliebe eine überholte Datei mit dem Namen des aktuellen Monats liegen –
    # genau so wäre am 13.08.2026 die nicht CI-treue Fassung stehengeblieben.
    # Reihenfolge: erst hochladen, dann die alte löschen. Bricht der Upload ab,
    # hat die Aufgabe weiterhin den alten Anhang statt keinen.
    vorhanden = vorhandene_anhaenge(gid)
    anzuhaengen = [(anhang_name(stand, f), p) for f, p in _in_reihenfolge(pdfs)]
    if config.asana_dataset_anhaengen():
        anzuhaengen.append((
            f"Vergleichsmieten_{stand.replace(' ', '_')}_Datensatz.csv",
            config.dataset_path(),
        ))

    for dateiname, pfad in anzuhaengen:
        if haenge_datei_an(gid, pfad, dateiname) is None:
            report.fehler.append(f"Asana: Anhang {dateiname} fehlgeschlagen")
            continue
        alt = vorhanden.get(dateiname)
        if alt:
            logger.info("Anhang %s ersetzt (alter Stand %s entfernt)", dateiname, alt)
            loesche_anhang(alt)

    url = f"https://app.asana.com/0/0/{gid}"
    logger.info("Asana-Monatsbericht: %s", url)
    return url
