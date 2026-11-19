from __future__ import annotations

import logging
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from . import config
from .classifier import extract_events, html_to_text
from .asana_gateway import build_task, create_event_task, list_section_tasks
from .dedup import find_duplicate
from .logbuch import append_record
from .models import DecisionRecord, RunReport
from .slack_gateway import (
    add_checkmark,
    fetch_channel_messages,
    fetch_file_text,
    get_bot_user_id,
    get_permalink,
    has_bot_checkmark,
    post_thread_reply,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _in_scan_window(msg: dict, oldest: float, latest: float | None) -> bool:
    ts = float(msg.get("ts", "0"))
    if ts < oldest:
        return False
    if latest and ts > latest:
        return False
    return True


def _collect_messages() -> list[dict]:
    now = datetime.now(timezone.utc)
    oldest = (now - timedelta(hours=config.scan_hours())).timestamp()
    latest = (
        (now - timedelta(hours=config.scan_latest_hours())).timestamp()
        if config.scan_latest_hours()
        else None
    )
    parents = fetch_channel_messages(
        hours=config.scan_hours(),
        latest_hours=config.scan_latest_hours(),
    )
    messages = [m for m in parents if _in_scan_window(m, oldest, latest)]
    messages.sort(key=lambda m: float(m.get("ts", "0")))
    return messages


def _gather_source(msg: dict) -> tuple[str, str]:
    """Baut (Titel, Inhalt) aus Dateititeln + Nachrichtentext + HTML-Anhängen."""
    files = msg.get("files", []) or []
    titles = [f.get("title") or f.get("name") or "" for f in files]
    title = " | ".join(t for t in titles if t).strip()

    parts: list[str] = []
    msg_text = (msg.get("text") or "").strip()
    if msg_text:
        parts.append(msg_text)
    for f in files:
        raw = fetch_file_text(f)
        if raw:
            parts.append(html_to_text(raw))
    content = "\n\n".join(p for p in parts if p)
    return title, content


def _gueltiges_datum(datum_iso: str | None) -> str | None:
    """Nur ein echtes JJJJ-MM-TT geht als Fälligkeit an Asana. Liefert die KI etwas
    anderes („2027-06-16/17“), wird die Aufgabe ohne Fälligkeit angelegt – statt gar nicht."""
    if not datum_iso:
        return None
    try:
        return date.fromisoformat(datum_iso.strip()).isoformat()
    except ValueError:
        logger.warning("Kein gültiges Datum für die Fälligkeit: %r – Aufgabe ohne Fälligkeit", datum_iso)
        return None


def _existing_tasks() -> list[dict]:
    """Bestehende Aufgaben des Ziel-Abschnitts. Bei Fehler leere Liste – dann wird
    ohne Dublettencheck gearbeitet (lieber ein Doppeleintrag als ein verlorenes Event)."""
    try:
        return list_section_tasks()
    except Exception as e:
        logger.warning("Bestand nicht abrufbar (%s) – Dublettencheck für diesen Lauf deaktiviert", e)
        return []


def _process_message(msg: dict, run_id: str, report: RunReport, existing: list[dict]) -> None:
    ts = msg["ts"]
    title, content = _gather_source(msg)

    if not title and not content:
        logger.info("Nachricht %s: kein Text/Anhang – übersprungen", ts)
        report.nicht_events += 1
        return

    extraction = extract_events(title, content)
    time.sleep(2)
    if extraction is None:
        report.fehler.append(f"Nachricht {ts}: nicht extrahierbar")
        append_record(DecisionRecord(
            run_id=run_id, verarbeitet_am=datetime.now(timezone.utc).isoformat(),
            message_ts=ts, text_auszug=(title or content)[:300],
            fehler="Extraktion fehlgeschlagen (Retry im nächsten Lauf)",
        ))
        return

    permalink = get_permalink(ts) or ""
    events = extraction.events
    logger.info("Nachricht %s: %d Event-Kandidat(en) extrahiert", ts, len(events))

    vorbereitet = 0
    angelegt = 0
    schon_da = 0
    fehlgeschlagen = 0
    for idx, event in enumerate(events):
        record = DecisionRecord(
            run_id=run_id, verarbeitet_am=datetime.now(timezone.utc).isoformat(),
            message_ts=ts, event_index=idx, permalink=permalink,
            text_auszug=(title or content)[:300], event=event,
        )
        if not event.ist_event:
            report.nicht_events += 1
            logger.info("  Event %s#%d: kein konkretes Event (%s)", ts, idx, event.begruendung)
            append_record(record)
            continue

        report.events_erkannt += 1
        name, notes = build_task(event, permalink)
        record.aufgabe_name = name
        record.aufgabe_notes = notes
        vorbereitet += 1

        # Dublettencheck gegen den Abschnitt (inkl. der in DIESEM Lauf angelegten
        # Aufgaben): dasselbe Event kommt oft aus zwei Nachrichten – einmal als
        # Einzel-Einladung, einmal in einem Sammel-Newsletter.
        dup_gid, dup_grund = find_duplicate(event, existing)
        time.sleep(1)
        if dup_gid:
            record.duplikat_von = dup_gid
            report.duplikate += 1
            schon_da += 1
            logger.info("  Event %s#%d: %r steht bereits in der Liste (gid %s: %s) – übersprungen",
                        ts, idx, name, dup_gid, dup_grund)
            append_record(record)
            continue

        # DRY_RUN: Aufgabe nur vorbereiten/loggen, nicht in Asana anlegen
        if config.dry_run():
            logger.info("  [DRY_RUN] Event %s#%d: Aufgabe NICHT angelegt (vorbereitet: %r)", ts, idx, name)
            existing.append({"gid": f"dry-run-{ts}-{idx}", "name": name})
            append_record(record)
            continue

        try:
            url = create_event_task(name, notes, due_on=_gueltiges_datum(event.datum_iso))
            record.asana_task_url = url
            record.in_asana = url is not None
            if url:
                report.aufgaben_erstellt += 1
                angelegt += 1
            # neu angelegte Aufgabe sofort in den Vergleichsbestand aufnehmen
            existing.append({"gid": (url or "").rsplit("/", 1)[-1] or f"neu-{ts}-{idx}", "name": name})
            logger.info("  Event %s#%d: '%s' -> Asana %s", ts, idx, name, url or "(NO_WRITE)")
        except Exception as e:  # pro Event weiterlaufen
            logger.exception("  Asana-Anlage fehlgeschlagen für %s#%d", ts, idx)
            record.fehler = str(e)
            report.fehler.append(f"Asana-Anlage {ts}#{idx} ({name}): {e}")
            fehlgeschlagen += 1
        finally:
            append_record(record)

    if fehlgeschlagen:
        # Kein ✅ und keine Erfolgsmeldung: Sonst gälte die Nachricht als erledigt,
        # obwohl ein Event nie in Asana ankam (z. B. bei abgelaufenem Token – jede
        # Nacht, jedes Event, bei grünem Lauf). Der Lauf endet rot; beim Nachholen
        # schützt der Dublettencheck die schon angelegten Events.
        logger.error("Nachricht %s: %d Event(s) nicht in Asana angelegt – kein ✅", ts, fehlgeschlagen)
        return

    add_checkmark(ts)
    n_events = sum(1 for e in events if e.ist_event)
    if not config.dry_run() and not config.no_write():
        reply = f"{angelegt} Event(s) als Aufgabe im Marketing-Projekt (Abschnitt „Events\") angelegt."
        if schon_da:
            reply += f" {schon_da} stand(en) schon in der Liste."
    else:
        reply = f"{n_events} Event(s) erkannt (Dry-Run – noch nicht in Asana angelegt)."
    post_thread_reply(msg.get("thread_ts") or ts, reply)


def run_pipeline() -> RunReport:
    report = RunReport()
    run_id = uuid.uuid4().hex[:12]

    if config.no_write():
        logger.info("=== NO_WRITE – reiner Lese-/Loglauf, keine Writes, keine Reactions ===")
    elif config.dry_run():
        logger.info("=== DRY RUN – Events werden erkannt/geloggt, aber nicht in Asana angelegt ===")

    bot_user_id = get_bot_user_id()
    logger.info("Bot-User-ID: %s, Kanal: %s", bot_user_id, config.EVENTS_CHANNEL)

    messages = _collect_messages()
    report.nachrichten_gesehen = len(messages)
    logger.info("%d Nachrichten im Scan-Fenster (%dh)", len(messages), config.scan_hours())

    # Bestand des Ziel-Abschnitts einmal laden; die Liste wächst im Lauf mit,
    # damit auch zwei Nachrichten desselben Laufs gegeneinander geprüft werden.
    existing = _existing_tasks()

    for i, msg in enumerate(messages, 1):
        preview = (msg.get("text") or (msg.get("files", [{}]) or [{}])[0].get("title") or "")[:80]
        logger.info("--- Nachricht %d/%d (%s): %s ---", i, len(messages), msg["ts"], preview)

        if msg.get("user") == bot_user_id:
            logger.info("Eigene Nachricht – übersprungen")
            continue
        if has_bot_checkmark(msg, bot_user_id):
            logger.info("Bereits verarbeitet (eigenes ✅) – übersprungen")
            report.bereits_verarbeitet += 1
            continue

        try:
            _process_message(msg, run_id, report, existing)
        except Exception as e:  # pro Nachricht weiterlaufen
            logger.exception("Fehler bei Nachricht %s", msg.get("ts"))
            report.fehler.append(f"Nachricht {msg.get('ts')}: {e}")

    _print_summary(report)
    return report


def _print_summary(report: RunReport) -> None:
    logger.info("=" * 60)
    logger.info("Zusammenfassung #events-Handler")
    logger.info("  Nachrichten im Fenster:   %d", report.nachrichten_gesehen)
    logger.info("  Bereits verarbeitet (✅): %d", report.bereits_verarbeitet)
    logger.info("  Events erkannt:           %d", report.events_erkannt)
    logger.info("  Nicht-Events/leer:        %d", report.nicht_events)
    logger.info("  Asana-Aufgaben erstellt:  %d", report.aufgaben_erstellt)
    logger.info("  Dubletten übersprungen:   %d", report.duplikate)
    logger.info("  Fehler:                   %d", len(report.fehler))
    for fehler in report.fehler:
        logger.info("    - %s", fehler)
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        ergebnis = run_pipeline()
    except Exception:
        logger.exception("Pipeline-Totalausfall")
        sys.exit(1)
    # Rot, wenn etwas nicht verarbeitet werden konnte: Der nächste Lauf sieht die
    # Nachricht meist nicht mehr, und ein grüner Lauf mit Fehlern fällt niemandem auf.
    # Nachholen: workflow_dispatch mit größerem Scan-Fenster.
    sys.exit(1 if ergebnis.fehler else 0)
