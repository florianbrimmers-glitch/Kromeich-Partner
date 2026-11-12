"""Wochenreport-DM aus den Dashboard-Daten – ohne Propstack-Key, ohne Slack-Token.

Die Daten kommen über den Propstack-Connector (Tool dashboard_daten, Abruf "alles")
und liegen nach dem Zerlegen als ein Verzeichnis mit einer JSON-Datei je Dokument vor
(meta/stand.json, meta/projekte.json, wochen/<Woche>.json, pruefung/<Teil>.json).
Dieses Modul schneidet daraus die letzten 7 Tage und baut den Text, den die Routine
über den Slack-Connector an Oguzhan schickt. Gesendet wird hier nichts.

Nur Standardbibliothek (kein pydantic, kein httpx), damit die Routine ohne
Paketinstallation auskommt:

    python3 -m weekly_report.wochen_dm --daten <verzeichnis> --out <datei> [--bis ISO-Zeit]

Fachlich wie der bisherige GitHub-Actions-Report (main.py):
- neue Einheiten = angelegt im Fenster
- ein Projekt gilt als neu, wenn seine früheste Einheit im Fenster liegt
- abgeschlossene Prüfaufgaben = erledigt und zuletzt geändert im Fenster
"""
from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, report

# Der Slack-Connector nimmt höchstens 5000 Zeichen je Textelement. Etwas Luft lassen.
MAX_ZEICHEN = 4800


@dataclass
class Einheit:
    id: int
    titel: str | None
    property_space_value: float | None
    marketing_type: str | None
    project_id: int | None

    def label(self) -> str:
        return self.titel or f"Einheit {self.id}"


@dataclass
class Projekt:
    id: int
    titel: str | None

    def label(self) -> str:
        return self.titel or f"Projekt {self.id}"


@dataclass
class Aktivitaet:
    project: Projekt
    neue_einheiten: int
    gesamtflaeche: float | None
    ist_neu: bool
    gefunden: bool


@dataclass
class Aufgabe:
    id: int
    titel: str | None
    updated_at: str | None
    original_created_at: str | None
    property_names: list[str] = field(default_factory=list)
    project_names: list[str] = field(default_factory=list)

    def label(self) -> str:
        return (self.titel or "").strip() or f"Aufgabe {self.id}"


@dataclass
class Daten:
    since: str
    until: str
    neue_projekte: list[Aktivitaet] = field(default_factory=list)
    bestehende_projekte: list[Aktivitaet] = field(default_factory=list)
    neue_einheiten: list[Einheit] = field(default_factory=list)
    abgeschlossene_aufgaben: list[Aufgabe] = field(default_factory=list)
    bearbeitete_aufgaben: list[Aufgabe] = field(default_factory=list)


def _zeit(iso: str | None) -> datetime | None:
    return datetime.fromisoformat(iso) if iso else None


def _im_fenster(iso: str | None, since: datetime, until: datetime) -> bool:
    t = _zeit(iso)
    return t is not None and since <= t < until


def lade(verzeichnis: pathlib.Path) -> dict[str, dict]:
    """Alle Dokumente des zerlegten Abrufs: {"wochen/2026-KW46": {...}, ...}."""
    return {
        f"{p.parent.name}/{p.stem}": json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(verzeichnis.glob("*/*.json"))
    }


def baue_daten(dokumente: dict[str, dict], since: datetime, until: datetime) -> Daten:
    """Reine Funktion: Dashboard-Dokumente -> Inhalt des Wochenreports."""
    stand = dokumente["meta/stand"]
    fenster_von = _zeit(stand["fenster_von"])
    if fenster_von and fenster_von > since:
        raise ValueError(
            f"Dashboard-Daten reichen nur bis {stand['fenster_von']} zurück, der Report braucht {since.isoformat()}"
        )

    einheiten = [
        Einheit(
            id=e["id"],
            titel=e.get("titel"),
            property_space_value=e.get("flaeche"),
            marketing_type=e.get("vermarktung"),
            project_id=e.get("projekt_id"),
        )
        for name, doc in dokumente.items()
        if name.startswith("wochen/")
        for e in doc.get("einheiten", [])
        if _im_fenster(e.get("angelegt"), since, until)
    ]
    angelegt = {
        e["id"]: e.get("angelegt")
        for name, doc in dokumente.items() if name.startswith("wochen/")
        for e in doc.get("einheiten", [])
    }
    einheiten.sort(key=lambda u: angelegt.get(u.id) or "", reverse=True)

    projekte = dokumente.get("meta/projekte", {}).get("projekte", {})
    nach_projekt: dict[int, list[Einheit]] = {}
    for u in einheiten:
        if u.project_id:
            nach_projekt.setdefault(u.project_id, []).append(u)

    neu: list[Aktivitaet] = []
    bestehend: list[Aktivitaet] = []
    for pid, units in nach_projekt.items():
        meta = projekte.get(str(pid), {})
        flaechen = [u.property_space_value for u in units if u.property_space_value]
        erste = _zeit(meta.get("erste_einheit"))
        eintrag = Aktivitaet(
            project=Projekt(id=pid, titel=meta.get("titel")),
            neue_einheiten=len(units),
            gesamtflaeche=sum(flaechen) if flaechen else None,
            # Kein Datum ermittelbar -> als neu behandeln, damit nichts stillschweigend
            # aus dem Report fällt (wie main.klassifiziere_projekte).
            ist_neu=erste is None or erste >= since,
            gefunden=meta.get("vorhanden", True) is not False,
        )
        (neu if eintrag.ist_neu else bestehend).append(eintrag)

    def schluessel(a: Aktivitaet) -> tuple[int, str]:
        return -a.neue_einheiten, a.project.label()

    aufgaben = [
        Aufgabe(
            id=a["id"],
            titel=a.get("titel"),
            updated_at=a.get("geaendert"),
            original_created_at=a.get("angelegt"),
            property_names=[a["bezug"]] if a.get("bezug") else [],
        )
        for name, doc in dokumente.items()
        if name.startswith("pruefung/")
        for a in doc.get("aufgaben", [])
        if a.get("erledigt") is True and _im_fenster(a.get("geaendert"), since, until)
    ]
    aufgaben.sort(key=lambda t: t.updated_at or "", reverse=True)

    return Daten(
        since=since.isoformat(),
        until=until.isoformat(),
        neue_projekte=sorted(neu, key=schluessel),
        bestehende_projekte=sorted(bestehend, key=schluessel),
        neue_einheiten=einheiten,
        abgeschlossene_aufgaben=aufgaben,
    )


def baue_text(daten: Daten, max_zeichen: int = MAX_ZEICHEN) -> str:
    """Standard-Markdown für den Slack-Connector, gekürzt bis es in ein Textelement passt.

    Die Zahlen je Block bleiben immer vollständig; gekürzt wird nur die Zahl der
    Detailzeilen ("… und N weitere")."""
    for max_zeilen in (config.MAX_DETAIL_LINES, 8, 6, 4, 2, 0):
        text = report.build(daten, stil=report.MARKDOWN, max_zeilen=max_zeilen)
        if len(text) <= max_zeichen:
            return text
    raise ValueError(f"Nachricht passt auch ohne Detailzeilen nicht in {max_zeichen} Zeichen")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--daten", required=True, help="Verzeichnis mit den zerlegten Dashboard-Dokumenten")
    parser.add_argument("--out", required=True, help="Datei für den Nachrichtentext")
    parser.add_argument("--bis", help="Ende des Fensters (ISO-Zeit), Standard: jetzt")
    parser.add_argument("--stunden", type=int, default=config.report_hours())
    args = parser.parse_args()

    until = datetime.fromisoformat(args.bis) if args.bis else datetime.now(ZoneInfo(config.BERLIN_TZ))
    since = until - timedelta(hours=args.stunden)
    daten = baue_daten(lade(pathlib.Path(args.daten)), since, until)
    text = baue_text(daten)
    pathlib.Path(args.out).write_text(text, encoding="utf-8")
    print(
        f"{len(daten.neue_projekte)} neue Projekte, {len(daten.neue_einheiten)} neue Einheiten, "
        f"{len(daten.bestehende_projekte)} bestehende Projekte mit neuen Einheiten, "
        f"{len(daten.abgeschlossene_aufgaben)} abgeschlossene Prüfaufgaben – {len(text)} Zeichen"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
