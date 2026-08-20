from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, propstack, report, slack
from .models import NewUnit, ProjectActivity, ProjectInfo, PruefTask, ReportData

logger = logging.getLogger(__name__)


def berechne_fenster(jetzt: datetime, stunden: int) -> tuple[datetime, datetime]:
    """Rollierendes Fenster: [jetzt - stunden, jetzt). Kein persistierter Zustand –
    fällt ein Lauf aus, ist die Woche danach wieder korrekt."""
    return jetzt - timedelta(hours=stunden), jetzt


def darf_laufen(jetzt: datetime, ziel_stunde: int | None) -> bool:
    """GitHub-Actions-Cron kennt nur UTC, Berlin wechselt zwischen CET und CEST.
    Der Workflow feuert deshalb zu beiden Zeiten; hier läuft nur die richtige durch."""
    return ziel_stunde is None or jetzt.hour == ziel_stunde


def klassifiziere_projekte(
    einheiten: list[NewUnit],
    projekte: dict[int, ProjectInfo],
    fruehestes_datum,
    since: datetime,
) -> tuple[list[ProjectActivity], list[ProjectActivity]]:
    """Neue Einheiten nach Projekt bündeln und je Projekt entscheiden: neu oder bestehend?

    Ein Projekt gilt als neu, wenn seine früheste Einheit ebenfalls im Fenster liegt –
    Propstack liefert für Projekte selbst keinen Zeitstempel. `fruehestes_datum` wird
    injiziert, damit die Klassifikation ohne Netz testbar bleibt."""
    nach_projekt: dict[int, list[NewUnit]] = {}
    for unit in einheiten:
        if unit.project_id:
            nach_projekt.setdefault(unit.project_id, []).append(unit)

    neu: list[ProjectActivity] = []
    bestehend: list[ProjectActivity] = []

    for project_id, units in nach_projekt.items():
        flaechen = [u.property_space_value for u in units if u.property_space_value]
        stammdaten = projekte.get(project_id)
        eintrag = ProjectActivity(
            project=stammdaten or ProjectInfo(id=project_id),
            neue_einheiten=len(units),
            gesamtflaeche=sum(flaechen) if flaechen else None,
            ist_neu=False,
            gefunden=stammdaten is not None,
        )
        erste = fruehestes_datum(project_id)
        # Kein Datum ermittelbar -> als neu behandeln, damit nichts stillschweigend
        # aus dem Report fällt; die Fußnote erklärt die Datierung.
        eintrag.ist_neu = erste is None or erste >= since
        (neu if eintrag.ist_neu else bestehend).append(eintrag)

    def schluessel(eintrag: ProjectActivity) -> tuple[int, str]:
        return -eintrag.neue_einheiten, eintrag.project.label()

    return sorted(neu, key=schluessel), sorted(bestehend, key=schluessel)


def teile_aufgaben(aufgaben: list[PruefTask]) -> tuple[list[PruefTask], list[PruefTask]]:
    """Abgeschlossene (done) und – nur wenn eingeschaltet – bearbeitete, offene Aufgaben.

    Propstack führt kein completed_at; updated_at ist der einzige Zeitstempel für den
    Abschluss und liegt bei abgeschlossenen Aufgaben deutlich nach der Anlage."""
    abgeschlossen = [t for t in aufgaben if t.done is True]
    if not config.include_touched():
        return abgeschlossen, []
    bearbeitet = [
        t for t in aufgaben
        if t.done is not True
        and t.updated_at
        and t.original_created_at
        and t.updated_at > t.original_created_at
    ]
    return abgeschlossen, bearbeitet


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s – %(message)s"
    )

    jetzt = datetime.now(ZoneInfo(config.BERLIN_TZ))
    ziel_stunde = config.run_hour_berlin()
    if not darf_laufen(jetzt, ziel_stunde):
        logger.info(
            "Übersprungen: %02d Uhr Berliner Zeit, erwartet %02d Uhr (Sommer-/Winterzeit-Guard)",
            jetzt.hour, ziel_stunde,
        )
        return 0

    since, until = berechne_fenster(jetzt, config.report_hours())
    logger.info("Berichtsfenster %s bis %s", since.isoformat(), until.isoformat())

    einheiten = propstack.fetch_new_units(since, until)
    projekte = propstack.fetch_projects_index() if einheiten else {}
    neue_projekte, bestehende_projekte = klassifiziere_projekte(
        einheiten, projekte, propstack.earliest_unit_created_at, since
    )
    aufgaben = propstack.fetch_pruef_tasks(since, until, config.pruefer_broker_ids())
    abgeschlossen, bearbeitet = teile_aufgaben(aufgaben)

    data = ReportData(
        since=since.isoformat(),
        until=until.isoformat(),
        neue_projekte=neue_projekte,
        bestehende_projekte=bestehende_projekte,
        neue_einheiten=einheiten,
        einheiten_ohne_projekt=[u for u in einheiten if not u.project_id],
        abgeschlossene_aufgaben=abgeschlossen,
        bearbeitete_aufgaben=bearbeitet,
    )
    text = report.build(data)

    empfaenger = config.report_recipient()
    if config.dry_run():
        logger.info("[DRY_RUN] Würde an %s senden:\n%s", empfaenger, text)
        gesendet, erfolg = False, True
    else:
        gesendet = slack.send_dm(empfaenger, text)
        erfolg = gesendet

    _schreibe_log(data, empfaenger=empfaenger, gesendet=gesendet)
    logger.info(
        "Fertig: %d neue Projekte, %d neue Einheiten, %d abgeschlossene Prüfaufgaben",
        len(neue_projekte), len(einheiten), len(abgeschlossen),
    )
    return 0 if erfolg else 1


def _schreibe_log(data: ReportData, *, empfaenger: str, gesendet: bool) -> None:
    """Eine JSONL-Zeile pro Lauf – wird als Actions-Artifact hochgeladen."""
    zeile = {
        "fenster_von": data.since,
        "fenster_bis": data.until,
        "empfaenger": empfaenger,
        "gesendet": gesendet,
        "dry_run": config.dry_run(),
        "pruefer_broker_ids": config.pruefer_broker_ids(),
        "neue_projekte": [p.project.id for p in data.neue_projekte],
        "bestehende_projekte": [p.project.id for p in data.bestehende_projekte],
        "neue_einheiten": [u.id for u in data.neue_einheiten],
        "einheiten_ohne_projekt": [u.id for u in data.einheiten_ohne_projekt],
        "abgeschlossene_aufgaben": [t.id for t in data.abgeschlossene_aufgaben],
        "bearbeitete_aufgaben": [t.id for t in data.bearbeitete_aufgaben],
    }
    try:
        with open(config.report_log_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(zeile, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("Report-Log konnte nicht geschrieben werden: %s", e)


if __name__ == "__main__":
    raise SystemExit(main())
