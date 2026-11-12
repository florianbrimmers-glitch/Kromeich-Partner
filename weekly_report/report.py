from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from . import config

if TYPE_CHECKING:
    # Nur für die Typen: build() arbeitet mit allem, was dieselben Felder hat. So läuft
    # der Wochenreport aus den Dashboard-Daten (wochen_dm) ohne pydantic.
    from .models import NewUnit, ProjectActivity, PruefTask, ReportData


@dataclass(frozen=True)
class Stil:
    """Auszeichnung der Nachricht. Slack-API (chat.postMessage) spricht mrkdwn, der
    Slack-Connector in Claude erwartet Standard-Markdown."""

    fett: Callable[[str], str]
    kursiv: Callable[[str], str]
    link: Callable[[str, str], str]  # (url, text)


MRKDWN = Stil(fett=lambda t: f"*{t}*", kursiv=lambda t: f"_{t}_", link=lambda u, t: f"<{u}|{t}>")
MARKDOWN = Stil(fett=lambda t: f"**{t}**", kursiv=lambda t: f"_{t}_", link=lambda u, t: f"[{t}]({u})")


def _de_number(value: float | None) -> str | None:
    """1234.5 -> "1.234,5" – deutsche Tausenderpunkte, Komma nur wenn nötig."""
    if value is None:
        return None
    gerundet = round(value, 1)
    if gerundet == int(gerundet):
        return f"{int(gerundet):,}".replace(",", ".")
    ganz, _, rest = f"{gerundet:.1f}".partition(".")
    return f"{int(ganz):,}".replace(",", ".") + "," + rest


def _de_date(iso: str | None) -> str:
    if not iso:
        return "?"
    return datetime.fromisoformat(iso).strftime("%d.%m.")


def _unit_link(unit_id: int) -> str:
    return f"{config.PROPSTACK_APP_BASE}/properties/{unit_id}"


def _project_link(project_id: int) -> str:
    return f"{config.PROPSTACK_APP_BASE}/projects/{project_id}"


def _block(
    titel: str, anzahl: int, zeilen: list[str], leer_text: str, stil: Stil, max_zeilen: int
) -> list[str]:
    """Ein Report-Block. Leere Blöcke verschwinden nicht – eine sichtbare Null ist
    die Information, dass in der Woche nichts passiert ist."""
    out = [stil.fett(f"{titel}: {anzahl}")]
    if not zeilen:
        out.append(stil.kursiv(leer_text))
        return out
    out.extend(zeilen[:max_zeilen])
    rest = len(zeilen) - max_zeilen
    if rest > 0:
        out.append(f"… und {rest} weitere")
    return out


def _project_line(eintrag: ProjectActivity, stil: Stil) -> str:
    teile = [f"{eintrag.neue_einheiten} Einheit" + ("en" if eintrag.neue_einheiten != 1 else "")]
    flaeche = _de_number(eintrag.gesamtflaeche)
    if flaeche:
        teile.append(f"{flaeche} m²")
    zeile = f"• {stil.fett(eintrag.project.label())} — {', '.join(teile)}"
    if not eintrag.gefunden:
        # Kein Link: das Projekt existiert nicht mehr, die Einheiten hängen als Waisen
        # daran. Lieber benennen als eine tote Verknüpfung anbieten.
        return zeile + " · " + stil.kursiv("Projekt in Propstack nicht mehr vorhanden")
    return zeile + " · " + stil.link(_project_link(eintrag.project.id), "öffnen")


def _unit_line(unit: NewUnit, stil: Stil) -> str:
    teile = []
    flaeche = _de_number(unit.property_space_value)
    if flaeche:
        teile.append(f"{flaeche} m²")
    if unit.marketing_type:
        teile.append(unit.marketing_type)
    detail = f" — {', '.join(teile)}" if teile else ""
    return f"• {stil.fett(unit.label())}{detail} · " + stil.link(_unit_link(unit.id), "öffnen")


def _task_line(task: PruefTask, stil: Stil, *, abgeschlossen: bool) -> str:
    verb = "abgeschlossen" if abgeschlossen else "bearbeitet"
    zeile = f"• {stil.fett(task.label())} — {verb} {_de_date(task.updated_at)}"
    if task.original_created_at:
        zeile += f", angelegt {_de_date(task.original_created_at)}"
    bezug = task.property_names or task.project_names
    if bezug:
        zeile += f" · {bezug[0]}"
    return zeile


def build(data: ReportData, stil: Stil = MRKDWN, max_zeilen: int = config.MAX_DETAIL_LINES) -> str:
    """ReportData -> Slack-Nachricht (Standard: mrkdwn). Reine Formatierung, keine API-Aufrufe."""
    von = datetime.fromisoformat(data.since).strftime("%d.%m.")
    bis = datetime.fromisoformat(data.until).strftime("%d.%m.%Y")

    zeilen: list[str] = [f":bar_chart: {stil.fett('Propstack-Wochenreport')} · {von}–{bis}", ""]

    zeilen += _block(
        "Neue Projekte",
        len(data.neue_projekte),
        [_project_line(p, stil) for p in data.neue_projekte],
        "Keine neuen Projekte im Berichtszeitraum.",
        stil, max_zeilen,
    )
    zeilen.append("")

    zeilen += _block(
        "Neue Objekte/Einheiten",
        len(data.neue_einheiten),
        [_unit_line(u, stil) for u in data.neue_einheiten],
        "Keine neuen Objekte im Berichtszeitraum.",
        stil, max_zeilen,
    )
    zeilen.append("")

    if data.bestehende_projekte:
        zeilen += _block(
            "Bestehende Projekte mit neuen Einheiten",
            len(data.bestehende_projekte),
            [_project_line(p, stil) for p in data.bestehende_projekte],
            "",
            stil, max_zeilen,
        )
        zeilen.append("")

    zeilen += _block(
        "Abgeschlossene Prüfaufgaben",
        len(data.abgeschlossene_aufgaben),
        [_task_line(t, stil, abgeschlossen=True) for t in data.abgeschlossene_aufgaben],
        "Keine im Berichtszeitraum abgeschlossen.",
        stil, max_zeilen,
    )

    if data.bearbeitete_aufgaben:
        zeilen.append("")
        zeilen += _block(
            "Bearbeitet, aber offen",
            len(data.bearbeitete_aufgaben),
            [_task_line(t, stil, abgeschlossen=False) for t in data.bearbeitete_aufgaben],
            "",
            stil, max_zeilen,
        )

    zeilen += [
        "",
        stil.kursiv(
            "Projekte werden über ihre früheste Einheit datiert – Propstack liefert für "
            "Projekte keinen Zeitstempel. Projekte ganz ohne Einheit erscheinen daher nicht."
        ),
    ]
    return "\n".join(zeilen)
