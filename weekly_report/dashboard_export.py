"""Datenexport für das Propstack-Dashboard (claude.ai-Artifact).

Das Dashboard darf Propstack nicht selbst abfragen: die Seite läuft in einer
abgeschotteten Umgebung, die Anfragen an fremde Server blockiert. Stattdessen holt
ein täglicher Claude-Lauf die Daten mit diesem Skript und schreibt sie in die
Datenbank des Artifacts. Das Dashboard rechnet Zeiträume, Wochenverlauf und
Klassifikation (neues vs. bestehendes Projekt) selbst daraus.

Aufbau der Ausgabe (ein Verzeichnis, eine JSON-Datei pro Datenbank-Dokument):

    meta/stand.json            Zeitpunkt, Fenster, Zähler
    meta/projekte.json         alle Projekte, auf die Einheiten im Fenster zeigen,
                               mit Titel und frühester Einheit (= Anlagedatum)
    wochen/<JJJJ-KWnn>.json    neue Einheiten je ISO-Woche
    pruefung/teil-<nn>.json    Prüfaufgaben: der ganze offene Bestand plus alles,
                               was im Fenster angelegt oder erledigt wurde

Aufgeteilt, weil ein Dokument höchstens 256 KiB groß sein darf: Einheiten pro Woche
(Spitzenwochen ~68 KB), Prüfaufgaben in Paketen zu je AUFGABEN_PRO_TEIL, weil der
offene Bestand wächst.

    python -m weekly_report.dashboard_export --out <verzeichnis> [--tage 91]
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, propstack
from .models import NewUnit, PruefTask

logger = logging.getLogger(__name__)

STANDARD_TAGE = 91  # 13 volle Wochen für den Verlauf
MAX_DOKUMENT_BYTES = 256 * 1024
AUFGABEN_PRO_TEIL = 400  # ~90 KB je Teil bei langen Titeln


def wochen_schluessel(zeitpunkt: datetime) -> str:
    """ISO-Kalenderwoche in Berliner Zeit als Dokument-ID, z. B. "2026-KW39".

    Muss mit keyVon() im Dashboard übereinstimmen, sonst landet eine Einheit vom
    Sonntagabend in einer anderen Woche als die, unter der das Dashboard sie zählt."""
    jahr, woche, _ = zeitpunkt.astimezone(ZoneInfo(config.BERLIN_TZ)).isocalendar()
    return f"{jahr}-KW{woche:02d}"


def aufgaben_art(titel: str | None) -> str:
    """Art einer Prüfaufgabe = Titel vor dem ersten Doppelpunkt.

    Die Automatisierungen benennen ihre Aufgaben nach festem Muster
    ("Pruefung Panattoni Welle 3: …", "Newsletter-Vermietung prüfen: …"). Die
    ASCII-Schreibweise aus dem Exposé-Workflow ("Pruefung") wird mit "Prüfung"
    zusammengeführt, sonst zerfiele eine Art in zwei Gruppen."""
    if not titel or ":" not in titel:
        return "Sonstige"
    art = titel.split(":", 1)[0].strip()
    art = re.sub(r"\bPruefung\b", "Prüfung", art)
    art = re.sub(r"\bpruefen\b", "prüfen", art)
    return art or "Sonstige"


def _einheit(u: NewUnit) -> dict:
    return {
        "id": u.id,
        "titel": u.label(),
        "flaeche": u.property_space_value,
        "vermarktung": u.marketing_type,
        "stadt": u.city,
        "projekt_id": u.project_id,
        "angelegt": u.created_at,
    }


def _aufgabe(t: PruefTask) -> dict:
    bezug = t.property_names or t.project_names
    return {
        "id": t.id,
        "titel": t.label(),
        "art": aufgaben_art(t.title),
        "erledigt": t.done is True,
        "angelegt": t.original_created_at,
        # Propstack führt kein Abschlussdatum; bei erledigten Aufgaben ist die letzte
        # Änderung der einzige Zeitstempel dafür.
        "geaendert": t.updated_at,
        "bezug": bezug[0] if bezug else None,
    }


def _relevant(t: PruefTask, since: datetime) -> bool:
    """Offen (zählt immer zum Bestand) oder im Fenster angelegt bzw. erledigt."""
    if t.done is not True:
        return True
    if t.original_created_at and datetime.fromisoformat(t.original_created_at) >= since:
        return True
    return bool(t.updated_at) and datetime.fromisoformat(t.updated_at) >= since


def baue_dokumente(
    einheiten: list[NewUnit],
    projekt_titel: dict[int, str],
    projekt_beginn: dict[int, str | None],
    aufgaben: list[PruefTask],
    *,
    since: datetime,
    until: datetime,
    tage: int,
    broker_ids: list[int],
) -> dict[str, dict]:
    """Reine Funktion: Rohdaten -> {"collection/doc_id": body}. Ohne Netz testbar."""
    wochen: dict[str, dict] = {}
    for u in einheiten:
        if u.created_at:
            key = wochen_schluessel(datetime.fromisoformat(u.created_at))
            wochen.setdefault(key, {"woche": key, "einheiten": []})["einheiten"].append(_einheit(u))

    projekte = {
        str(pid): {
            "titel": projekt_titel.get(pid),
            # Fehlt der Titel, gibt es das Projekt nicht mehr (GET /projects/:id -> 404),
            # die Einheiten zeigen aber noch darauf. Das Dashboard verlinkt es dann nicht.
            "vorhanden": pid in projekt_titel,
            "erste_einheit": projekt_beginn.get(pid),
        }
        for pid in sorted({u.project_id for u in einheiten if u.project_id})
    }

    pruefung = sorted(
        (_aufgabe(t) for t in aufgaben if _relevant(t, since)),
        key=lambda a: (a["angelegt"] or "", a["id"]),
    )
    teile = [pruefung[i:i + AUFGABEN_PRO_TEIL] for i in range(0, len(pruefung), AUFGABEN_PRO_TEIL)]

    dokumente: dict[str, dict] = {
        "meta/stand": {
            "aktualisiert": until.isoformat(),
            "fenster_von": since.isoformat(),
            "fenster_bis": until.isoformat(),
            "tage": tage,
            "pruefer_broker_ids": broker_ids,
            "anzahl_einheiten": len(einheiten),
            "anzahl_projekte": len(projekte),
            "anzahl_offen": sum(not a["erledigt"] for a in pruefung),
            "anzahl_aufgaben": len(pruefung),
            "wochen": sorted(wochen),
            "pruefung_teile": [f"teil-{i:02d}" for i in range(1, len(teile) + 1)],
        },
        "meta/projekte": {"projekte": projekte},
    }
    for key, body in wochen.items():
        dokumente[f"wochen/{key}"] = body
    for i, teil in enumerate(teile, start=1):
        dokumente[f"pruefung/teil-{i:02d}"] = {"teil": i, "aufgaben": teil}
    return dokumente


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s – %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True, help="Zielverzeichnis für die JSON-Dateien")
    parser.add_argument("--tage", type=int, default=STANDARD_TAGE)
    args = parser.parse_args()

    until = datetime.now(ZoneInfo(config.BERLIN_TZ))
    since = until - timedelta(days=args.tage)
    broker_ids = config.pruefer_broker_ids()

    einheiten = propstack.fetch_new_units(since, until)
    index = propstack.fetch_projects_index()
    projekt_ids = sorted({u.project_id for u in einheiten if u.project_id})
    beginn: dict[int, str | None] = {}
    for pid in projekt_ids:
        erste = propstack.earliest_unit_created_at(pid)
        beginn[pid] = erste.isoformat() if erste else None
    aufgaben = propstack.fetch_all_tasks(broker_ids)

    dokumente = baue_dokumente(
        einheiten,
        {pid: p.label() for pid, p in index.items()},
        beginn,
        aufgaben,
        since=since,
        until=until,
        tage=args.tage,
        broker_ids=broker_ids,
    )

    out = pathlib.Path(args.out)
    for pfad, body in dokumente.items():
        text = json.dumps(body, ensure_ascii=False)
        groesse = len(text.encode("utf-8"))
        if groesse > MAX_DOKUMENT_BYTES:
            raise SystemExit(f"{pfad}: {groesse} Bytes, Grenze {MAX_DOKUMENT_BYTES}")
        ziel = out / f"{pfad}.json"
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(text, encoding="utf-8")
        logger.info("%s: %d Bytes", pfad, groesse)

    stand = dokumente["meta/stand"]
    logger.info(
        "Fertig: %d Einheiten, %d Projekte in %d Wochen; %d Prüfaufgaben (%d offen) in %d Teil(en)",
        stand["anzahl_einheiten"], stand["anzahl_projekte"], len(stand["wochen"]),
        stand["anzahl_aufgaben"], stand["anzahl_offen"], len(stand["pruefung_teile"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
