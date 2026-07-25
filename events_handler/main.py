from __future__ import annotations

import logging
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from . import config
from .classifier import extract_events, html_to_text
from .asana_gateway import build_task, create_event_task
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


def _process_message(msg: dict, run_id: str, report: RunReport) -> None:
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

        # DRY_RUN: Aufgabe nur vorbereiten/loggen, nicht in Asana anlegen
        if config.dry_run():
            logger.info("  [DRY_RUN] Event %s#%d: Aufgabe NICHT angelegt (vorbereitet: %r)", ts, idx, name)
            append_record(record)
            continue

        try:
            url = create_event_task(name, notes)
            record.asana_task_url = url
            record.in_asana = url is not None
            if url:
                report.aufgaben_erstellt += 1
            logger.info("  Event %s#%d: '%s' -> Asana %s", ts, idx, name, url or "(NO_WRITE)")
        except Exception as e:  # pro Event weiterlaufen
            logger.exception("  Asana-Anlage fehlgeschlagen für %s#%d", ts, idx)
            record.fehler = str(e)
            report.fehler.append(f"Asana-Anlage {ts}#{idx} ({name}): {e}")
        finally:
            append_record(record)

    add_checkmark(ts)
    n_events = sum(1 for e in events if e.ist_event)
    if not config.dry_run() and not config.no_write():
        reply = f"{n_events} Event(s) als Aufgabe im Marketing-Projekt (Abschnitt „Events\") angelegt."
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
            _process_message(msg, run_id, report)
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
    logger.info("  Fehler:                   %d", len(report.fehler))
    for fehler in report.fehler:
        logger.info("    - %s", fehler)
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception:
        logger.exception("Pipeline-Totalausfall")
        sys.exit(1)
