#!/usr/bin/env python3
"""
Überführt einen Google-Drive-Ordnerbaum in eine geteilte Ablage – ohne Mitwirkung
des bisherigen Eigentümers.

Hintergrund: Liegt die Unternehmensablage im "My Drive" eines fremden Kontos, kann
die Eigentümerschaft nicht übertragen werden. Was bleibt, ist Kopieren: Eine Kopie
gehört dem Konto, das sie anlegt – bzw. der geteilten Ablage, wenn direkt dorthin
kopiert wird. Genau das macht dieses Skript.

Strategie pro Objekt:
  * Ordner            -> im Ziel neu angelegt (Ordner sind nicht kopierbar)
  * eigene Dateien    -> VERSCHOBEN (Historie, Kommentare, Zeitstempel bleiben)
  * fremde Dateien    -> KOPIERT   (Eigentümer wird die geteilte Ablage)
  * Verknüpfungen     -> im zweiten Durchlauf auf die neuen Ziele neu angelegt

Jede Aktion landet in einem Manifest (CSV). Das Manifest ist dreierlei:
Wiederaufsetzpunkt nach Abbruch, alt->neu-ID-Mapping zum Nachziehen von Links in
Asana/Notion/Propstack, und Herkunftsnachweis für die kopierten Dateien (deren
Original-Zeitstempel durch das Kopieren verloren gehen).

Anmeldung über dieselben Secrets wie die übrigen Automatisierungen:
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
Der Refresh-Token braucht zusätzlich den Scope https://www.googleapis.com/auth/drive
(der Gmail-Token aus der Kontakt-Pipeline reicht NICHT).

Nutzung:
  # 1. Trockenlauf: zeigt Aktionen und Datenmenge, ändert nichts
  python3 scripts/drive_migrate_copy.py --source <QUELL_ORDNER_ID> \\
      --target <ZIEL_ORDNER_ID> --manifest migration.csv --dry-run

  # 2. Echtlauf (abbrechbar, per --manifest wiederaufsetzbar)
  python3 scripts/drive_migrate_copy.py --source <QUELL_ORDNER_ID> \\
      --target <ZIEL_ORDNER_ID> --manifest migration.csv

  # 3. Nachkontrolle: prüft jede Manifest-Zeile im Ziel (md5 bei Binärdateien)
  python3 scripts/drive_migrate_copy.py --manifest migration.csv --verify
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import random
import sys
import time

from google.auth.transport.requests import Request  # noqa: F401  (von Credentials benötigt)
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"

LIST_FIELDS = (
    "nextPageToken, files(id, name, mimeType, size, md5Checksum, createdTime, "
    "modifiedTime, owners(emailAddress), shortcutDetails(targetId), "
    "capabilities(canCopy, canDownload))"
)
MANIFEST_COLUMNS = [
    "aktion", "status", "pfad", "name", "mime_type", "alt_id", "neu_id",
    "eigentuemer_alt", "erstellt_alt", "geaendert_alt", "groesse", "md5", "fehler",
]
RETRY_STATUS = {429, 500, 502, 503, 504}
# Drive quittiert mit 403 sowohl Ratenbegrenzung (wiederholen!) als auch fehlende
# Rechte (niemals wiederholen – sonst kostet jede gesperrte Datei Minuten Backoff).
RETRY_403_GRUENDE = (
    "ratelimitexceeded",
    "userratelimitexceeded",
    "quotaexceeded",
    "sharingratelimitexceeded",
    "backenderror",
    "internalerror",
)

logger = logging.getLogger("drive-migration")


# --------------------------------------------------------------------------- Auth

def build_service():
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
    missing = [
        name for name, value in (
            ("GOOGLE_CLIENT_ID", client_id),
            ("GOOGLE_CLIENT_SECRET", client_secret),
            ("GOOGLE_REFRESH_TOKEN", refresh_token),
        ) if not value
    ]
    if missing:
        sys.exit(f"FEHLER: {', '.join(missing)} nicht gesetzt.")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def whoami(service) -> str:
    about = service.about().get(fields="user(emailAddress)").execute()
    return about["user"]["emailAddress"]


# ------------------------------------------------------------------- API-Aufrufe

def ist_wiederholbar(err: HttpError) -> bool:
    status = getattr(err.resp, "status", None)
    if status in RETRY_STATUS:
        return True
    if status == 403:
        text = (err.content or b"").decode("utf-8", "ignore").lower()
        text += str(getattr(err.resp, "reason", "")).lower()
        return any(grund in text for grund in RETRY_403_GRUENDE)
    return False


def with_retry(request_factory, what: str, max_retries: int = 6):
    """Führt einen API-Aufruf mit exponentiellem Backoff aus.

    Drive quittiert Massenoperationen regelmäßig mit rateLimitExceeded. Ohne
    Backoff bricht ein Lauf über mehrere tausend Dateien mitten im Baum ab.
    """
    for versuch in range(max_retries + 1):
        try:
            return request_factory().execute()
        except HttpError as err:
            if not ist_wiederholbar(err) or versuch == max_retries:
                raise
            wartezeit = min(2 ** versuch, 64) + random.uniform(0, 1)
            logger.warning("%s: HTTP %s – neuer Versuch in %.1fs",
                           what, getattr(err.resp, "status", "?"), wartezeit)
            time.sleep(wartezeit)


def list_children(service, folder_id: str) -> list[dict]:
    kinder: list[dict] = []
    seite = None
    while True:
        antwort = with_retry(
            lambda: service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields=LIST_FIELDS,
                pageSize=1000,
                pageToken=seite,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ),
            f"Auflisten von {folder_id}",
        )
        kinder.extend(antwort.get("files", []))
        seite = antwort.get("nextPageToken")
        if not seite:
            return kinder


def herkunft(datei: dict, pfad: str) -> str:
    """Herkunftsvermerk für die Dateibeschreibung.

    Beim Kopieren verliert die Datei Erstellungsdatum und letzten Bearbeiter.
    Bei Vertrags- und Steuerunterlagen ist genau das der nachweisrelevante Teil,
    deshalb wandert es in die Beschreibung – und zusätzlich ins Manifest.
    """
    eigentuemer = (datei.get("owners") or [{}])[0].get("emailAddress", "unbekannt")
    return (
        "Migriert aus der Alt-Ablage.\n"
        f"Original-ID: {datei['id']}\n"
        f"Original-Eigentümer: {eigentuemer}\n"
        f"Original erstellt: {datei.get('createdTime', '?')}\n"
        f"Original geändert: {datei.get('modifiedTime', '?')}\n"
        f"Original-Pfad: {pfad}"
    )


# ------------------------------------------------------------------------ Manifest

class Manifest:
    def __init__(self, pfad: str, dry_run: bool):
        self.pfad = pfad
        self.dry_run = dry_run
        self.erledigt: dict[str, str] = {}
        self.zeilen: list[dict] = []
        if os.path.exists(pfad):
            with open(pfad, newline="", encoding="utf-8") as fh:
                for zeile in csv.DictReader(fh):
                    self.zeilen.append(zeile)
                    if zeile.get("status") == "ok" and zeile.get("alt_id"):
                        self.erledigt[zeile["alt_id"]] = zeile.get("neu_id", "")
            logger.info("Manifest gelesen: %d Objekte bereits erledigt", len(self.erledigt))
        self._fh = None
        self._writer = None
        if not dry_run:
            neu = not os.path.exists(pfad)
            self._fh = open(pfad, "a", newline="", encoding="utf-8")
            self._writer = csv.DictWriter(self._fh, fieldnames=MANIFEST_COLUMNS)
            if neu:
                self._writer.writeheader()
                self._fh.flush()

    def schreibe(self, **felder) -> None:
        zeile = {spalte: felder.get(spalte, "") for spalte in MANIFEST_COLUMNS}
        if zeile["status"] == "ok" and zeile["alt_id"]:
            self.erledigt[zeile["alt_id"]] = zeile["neu_id"]
        if self._writer:
            self._writer.writerow(zeile)
            self._fh.flush()  # zeilenweise, damit ein Abbruch nichts verliert

    def close(self) -> None:
        if self._fh:
            self._fh.close()


# ----------------------------------------------------------------------- Migration

class Migration:
    def __init__(self, service, manifest: Manifest, ich: str, dry_run: bool, move_own: bool):
        self.service = service
        self.manifest = manifest
        self.ich = ich
        self.dry_run = dry_run
        self.move_own = move_own
        self.verknuepfungen: list[tuple[dict, str, str]] = []
        self.zaehler = {"ordner": 0, "kopiert": 0, "verschoben": 0, "uebersprungen": 0, "fehler": 0}
        self.bytes_gesamt = 0

    # -- Ordner ------------------------------------------------------------
    def ordner_anlegen(self, name: str, ziel_parent: str, pfad: str) -> str:
        if self.dry_run:
            return f"DRY-{name}"
        angelegt = with_retry(
            lambda: self.service.files().create(
                body={"name": name, "mimeType": FOLDER_MIME, "parents": [ziel_parent]},
                fields="id",
                supportsAllDrives=True,
            ),
            f"Ordner anlegen {pfad}",
        )
        return angelegt["id"]

    # -- Dateien -----------------------------------------------------------
    def datei_verschieben(self, datei: dict, ziel_parent: str, quell_parent: str) -> str:
        verschoben = with_retry(
            lambda: self.service.files().update(
                fileId=datei["id"],
                addParents=ziel_parent,
                removeParents=quell_parent,
                fields="id",
                supportsAllDrives=True,
            ),
            f"Verschieben {datei['name']}",
        )
        return verschoben["id"]

    def datei_kopieren(self, datei: dict, ziel_parent: str, pfad: str) -> str:
        kopie = with_retry(
            lambda: self.service.files().copy(
                fileId=datei["id"],
                body={
                    "name": datei["name"],
                    "parents": [ziel_parent],
                    "description": herkunft(datei, pfad),
                },
                fields="id",
                supportsAllDrives=True,
            ),
            f"Kopieren {datei['name']}",
        )
        return kopie["id"]

    def datei_verarbeiten(self, datei: dict, ziel_parent: str, quell_parent: str, pfad: str) -> None:
        basis = {
            "pfad": pfad,
            "name": datei["name"],
            "mime_type": datei["mimeType"],
            "alt_id": datei["id"],
            "eigentuemer_alt": (datei.get("owners") or [{}])[0].get("emailAddress", ""),
            "erstellt_alt": datei.get("createdTime", ""),
            "geaendert_alt": datei.get("modifiedTime", ""),
            "groesse": datei.get("size", ""),
            "md5": datei.get("md5Checksum", ""),
        }
        if datei["id"] in self.manifest.erledigt:
            self.zaehler["uebersprungen"] += 1
            return

        eigentuemer = basis["eigentuemer_alt"]
        eigene_datei = self.move_own and eigentuemer == self.ich
        aktion = "verschieben" if eigene_datei else "kopieren"

        if not eigene_datei and not datei.get("capabilities", {}).get("canCopy", True):
            # Kommt vor, wenn der Eigentümer "Betrachter dürfen nicht kopieren" gesetzt hat.
            self.zaehler["fehler"] += 1
            logger.error("NICHT KOPIERBAR: %s (Eigentümer hat Kopieren gesperrt)", pfad)
            self.manifest.schreibe(aktion=aktion, status="fehler", fehler="canCopy=false", **basis)
            return

        if self.dry_run:
            logger.info("[dry-run] %-12s %s", aktion, pfad)
            self.zaehler["verschoben" if eigene_datei else "kopiert"] += 1
            self.bytes_gesamt += int(datei.get("size") or 0)
            return

        try:
            if eigene_datei:
                try:
                    neu_id = self.datei_verschieben(datei, ziel_parent, quell_parent)
                except HttpError as err:
                    # Verschieben scheitert, wenn wir im Quellordner kein Schreibrecht
                    # haben (Elternteil lässt sich dann nicht entfernen) -> kopieren.
                    logger.warning("Verschieben von %s fehlgeschlagen (%s) – kopiere", pfad, err)
                    eigene_datei = False
                    aktion = "kopieren"
                    neu_id = self.datei_kopieren(datei, ziel_parent, pfad)
            else:
                neu_id = self.datei_kopieren(datei, ziel_parent, pfad)
        except HttpError as err:
            self.zaehler["fehler"] += 1
            logger.error("FEHLER bei %s: %s", pfad, err)
            self.manifest.schreibe(aktion=aktion, status="fehler", fehler=str(err), **basis)
            return

        self.zaehler["verschoben" if eigene_datei else "kopiert"] += 1
        self.bytes_gesamt += int(datei.get("size") or 0)
        self.manifest.schreibe(aktion=aktion, status="ok", neu_id=neu_id, **basis)
        logger.info("%-12s %s", aktion, pfad)

    # -- Baumlauf ----------------------------------------------------------
    def baum_durchlaufen(self, quell_id: str, ziel_id: str, pfad: str = "") -> None:
        for eintrag in sorted(list_children(self.service, quell_id), key=lambda f: f["name"]):
            kind_pfad = f"{pfad}/{eintrag['name']}"
            if eintrag["mimeType"] == SHORTCUT_MIME:
                # Verknüpfungen zeigen auf IDs, die es im Ziel erst nach dem
                # Hauptlauf gibt -> zweiter Durchlauf.
                self.verknuepfungen.append((eintrag, ziel_id, kind_pfad))
            elif eintrag["mimeType"] == FOLDER_MIME:
                vorhandene = self.manifest.erledigt.get(eintrag["id"])
                neu_id = vorhandene or self.ordner_anlegen(eintrag["name"], ziel_id, kind_pfad)
                if not vorhandene:
                    self.zaehler["ordner"] += 1
                    self.manifest.schreibe(
                        aktion="ordner", status="ok", pfad=kind_pfad, name=eintrag["name"],
                        mime_type=FOLDER_MIME, alt_id=eintrag["id"], neu_id=neu_id,
                        eigentuemer_alt=(eintrag.get("owners") or [{}])[0].get("emailAddress", ""),
                    )
                self.baum_durchlaufen(eintrag["id"], neu_id, kind_pfad)
            else:
                self.datei_verarbeiten(eintrag, ziel_id, quell_id, kind_pfad)

    def verknuepfungen_nachziehen(self) -> None:
        for eintrag, ziel_parent, pfad in self.verknuepfungen:
            ziel_alt = (eintrag.get("shortcutDetails") or {}).get("targetId", "")
            ziel_neu = self.manifest.erledigt.get(ziel_alt)
            if not ziel_neu:
                logger.warning("Verknüpfung %s zeigt außerhalb des Baums – übersprungen", pfad)
                self.manifest.schreibe(
                    aktion="verknuepfung", status="fehler", pfad=pfad, name=eintrag["name"],
                    mime_type=SHORTCUT_MIME, alt_id=eintrag["id"],
                    fehler=f"Ziel {ziel_alt} nicht migriert",
                )
                continue
            if self.dry_run:
                logger.info("[dry-run] verknuepfung  %s", pfad)
                continue
            neu = with_retry(
                lambda: self.service.files().create(
                    body={
                        "name": eintrag["name"],
                        "mimeType": SHORTCUT_MIME,
                        "parents": [ziel_parent],
                        "shortcutDetails": {"targetId": ziel_neu},
                    },
                    fields="id",
                    supportsAllDrives=True,
                ),
                f"Verknüpfung {pfad}",
            )
            self.manifest.schreibe(
                aktion="verknuepfung", status="ok", pfad=pfad, name=eintrag["name"],
                mime_type=SHORTCUT_MIME, alt_id=eintrag["id"], neu_id=neu["id"],
            )


# --------------------------------------------------------------------- Kontrolle

def letzter_stand(manifest_pfad: str) -> list[dict]:
    """Letzte Zeile je Objekt.

    Das Manifest wird nur angehängt (damit ein Abbruch nichts verliert), und ein
    Wiederanlauf versucht fehlgeschlagene Objekte erneut. Dadurch kann dasselbe
    Objekt mehrfach vorkommen – für die Bewertung zählt der jüngste Eintrag,
    sonst gilt eine im zweiten Lauf geglückte Datei weiter als offen.
    """
    je_objekt: dict[str, dict] = {}
    ohne_id: list[dict] = []
    with open(manifest_pfad, newline="", encoding="utf-8") as fh:
        for zeile in csv.DictReader(fh):
            if zeile.get("alt_id"):
                je_objekt[zeile["alt_id"]] = zeile
            else:
                ohne_id.append(zeile)
    return list(je_objekt.values()) + ohne_id


def verify(service, manifest_pfad: str) -> int:
    """Prüft jede erfolgreiche Manifest-Zeile im Ziel. Rückgabe: Anzahl Abweichungen."""
    if not os.path.exists(manifest_pfad):
        sys.exit(f"FEHLER: Manifest {manifest_pfad} nicht gefunden.")
    geprueft = abweichungen = 0
    for zeile in letzter_stand(manifest_pfad):
        if zeile.get("status") != "ok" or not zeile.get("neu_id"):
            if zeile.get("status") == "fehler":
                abweichungen += 1
                print(f"OFFEN     {zeile['pfad']}  ({zeile.get('fehler', '')})")
            continue
        geprueft += 1
        try:
            ziel = with_retry(
                lambda: service.files().get(
                    fileId=zeile["neu_id"],
                    fields="id, name, size, md5Checksum, trashed",
                    supportsAllDrives=True,
                ),
                f"Prüfen {zeile['pfad']}",
            )
        except HttpError as err:
            abweichungen += 1
            print(f"FEHLT     {zeile['pfad']}  ({err})")
            continue
        if ziel.get("trashed"):
            abweichungen += 1
            print(f"IM PAPIERKORB {zeile['pfad']}")
        elif zeile.get("md5") and ziel.get("md5Checksum") and zeile["md5"] != ziel["md5Checksum"]:
            abweichungen += 1
            print(f"MD5 ABWEICHUNG {zeile['pfad']}")
    print(f"\nGeprüft: {geprueft} · Abweichungen: {abweichungen}")
    return abweichungen


# -------------------------------------------------------------------------- CLI

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", help="ID des Quellordners (Alt-Ablage)")
    parser.add_argument("--target", help="ID des Zielordners in der geteilten Ablage")
    parser.add_argument("--manifest", required=True, help="CSV-Manifest (Wiederaufsetzpunkt und ID-Mapping)")
    parser.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts ändern")
    parser.add_argument("--verify", action="store_true", help="nur Nachkontrolle gegen das Manifest")
    parser.add_argument("--no-move-own", action="store_true",
                        help="auch eigene Dateien kopieren statt verschieben")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    service = build_service()

    if args.verify:
        sys.exit(1 if verify(service, args.manifest) else 0)

    if not args.source or not args.target:
        sys.exit("FEHLER: --source und --target sind für den Migrationslauf erforderlich.")

    ich = whoami(service)
    logger.info("Angemeldet als %s", ich)
    if args.dry_run:
        logger.info("TROCKENLAUF – es wird nichts verändert")

    manifest = Manifest(args.manifest, args.dry_run)
    migration = Migration(service, manifest, ich, args.dry_run, move_own=not args.no_move_own)
    try:
        migration.baum_durchlaufen(args.source, args.target)
        migration.verknuepfungen_nachziehen()
    except KeyboardInterrupt:
        logger.warning("Abbruch durch Nutzer – Manifest ist gültig, Lauf ist wiederaufsetzbar")
    finally:
        manifest.close()

    z = migration.zaehler
    logger.info(
        "Fertig. Ordner: %d · kopiert: %d · verschoben: %d · übersprungen: %d · Fehler: %d · %.2f GB",
        z["ordner"], z["kopiert"], z["verschoben"], z["uebersprungen"], z["fehler"],
        migration.bytes_gesamt / 1024 ** 3,
    )
    if z["fehler"]:
        logger.error("%d Objekte nicht migriert – siehe Spalte 'fehler' im Manifest", z["fehler"])
        sys.exit(1)


if __name__ == "__main__":
    main()
