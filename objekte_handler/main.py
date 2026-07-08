from __future__ import annotations

import logging
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from . import config
from .classifier import build_thread_context, classify_message
from .decision import decide, due_date_plus_business_days
from .logbuch import append_record
from .matcher import find_unit
from .models import (
    Classification,
    Decision,
    DecisionRecord,
    MatchResult,
    MessageType,
    RunReport,
    Tier,
    Unit,
)
from .propstack import TaskPayload, create_task, get_open_deals, set_rented
from .slack_gateway import (
    add_checkmark,
    fetch_channel_messages,
    fetch_thread_replies,
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


def _is_own_message(msg: dict, bot_user_id: str) -> bool:
    return msg.get("user") == bot_user_id or bool(msg.get("bot_id"))


def _in_scan_window(msg: dict, oldest: float, latest: float | None) -> bool:
    ts = float(msg.get("ts", "0"))
    if ts < oldest:
        return False
    if latest and ts > latest:
        return False
    return True


def _collect_candidates(bot_user_id: str) -> list[tuple[dict, str | None]]:
    """Liefert (Nachricht, Thread-Kontext) für alle Nachrichten im Scan-Fenster.

    Parents werden über das breitere Discovery-Fenster geholt, damit auch Replies
    auf ältere Threads gefunden werden."""
    now = datetime.now(timezone.utc)
    oldest = (now - timedelta(hours=config.scan_hours())).timestamp()
    latest = (
        (now - timedelta(hours=config.scan_latest_hours())).timestamp()
        if config.scan_latest_hours()
        else None
    )

    parents = fetch_channel_messages(
        hours=config.thread_lookback_hours(),
        latest_hours=config.scan_latest_hours(),
    )

    candidates: list[tuple[dict, str | None]] = []
    for parent in parents:
        if _in_scan_window(parent, oldest, latest) and not _is_own_message(parent, bot_user_id):
            candidates.append((parent, None))

        if parent.get("reply_count", 0) > 0:
            replies = fetch_thread_replies(parent["ts"])
            for idx, reply in enumerate(replies):
                if not _in_scan_window(reply, oldest, latest) or _is_own_message(reply, bot_user_id):
                    continue
                prior = [
                    r.get("text", "") for r in replies[:idx]
                    if not _is_own_message(r, bot_user_id)
                ]
                context = build_thread_context(parent.get("text", ""), prior)
                candidates.append((reply, context))
            time.sleep(1)

    candidates.sort(key=lambda c: float(c[0].get("ts", "0")))
    return candidates


def _stufe_a(msg: dict, cls: Classification, match: MatchResult, permalink: str) -> list[str]:
    """Vermietet-Meldung direkt ausführen: rented=true, Doku-Notiz, Deals absagen."""
    slack_datum = datetime.fromtimestamp(float(msg["ts"]), tz=timezone.utc).date().isoformat()
    quelle = f"Quelle: Slack #objekte vom {slack_datum}<br>{permalink}"
    aktionen: list[str] = []

    unit_ids = [u.id for u in match.units]
    for unit in match.units:
        set_rented(unit.id)
        aktionen.append(f"Unit {unit.id} rented=true")

    doku = TaskPayload(
        title=f"Vermietet: {match.units[0].adresse()}",
        body=f"Vermietet gemeldet via Slack.<br>Original: {msg.get('text', '')}<br>{quelle}",
        is_reminder=False,
        property_ids=unit_ids,
    )
    doku_id = create_task(doku)
    aktionen.append(f"Doku-Notiz angelegt (Task {doku_id})")

    absagen = 0
    for unit in match.units:
        for deal in get_open_deals(unit.id):
            client_id = deal.get("client_id") or (deal.get("client") or {}).get("id")
            if not client_id:
                logger.warning("Deal ohne client_id an Unit %s – übersprungen: %s", unit.id, deal.get("id"))
                continue
            absage = TaskPayload(
                title="Absage",
                body=f"Fläche vermietet – automatische Absage.<br>{quelle}",
                reservation_reason_id=config.RESERVATION_REASON_ABSAGE,
                client_ids=[client_id],
                property_ids=[unit.id],
            )
            task_id = create_task(absage)
            aktionen.append(f"Absage Deal (Kunde {client_id}, Unit {unit.id}, Task {task_id})")
            absagen += 1

    add_checkmark(msg["ts"])
    reply = (
        f"✅ Erledigt: {match.units[0].adresse()} auf vermietet gesetzt"
        f" ({len(unit_ids)} Einheit{'en' if len(unit_ids) != 1 else ''}), "
        f"{absagen} offene Deals abgesagt, Doku-Notiz angelegt."
    )
    post_thread_reply(msg.get("thread_ts") or msg["ts"], reply)
    return aktionen


def _stufe_b(msg: dict, cls: Classification | None, match: MatchResult | None,
             decision: Decision, permalink: str) -> list[str]:
    """Review-Aufgabe statt Ausführung."""
    slack_datum = datetime.fromtimestamp(float(msg["ts"]), tz=timezone.utc).date().isoformat()

    broker_id = config.BROKER_OGUZHAN
    broker_name = "Oguzhan"
    unit: Unit | None = match.units[0] if match and match.units else None
    if unit is None and match and match.kandidaten:
        unit = match.kandidaten[0]
    if cls and cls.typ == MessageType.STATUS_ANWEISUNG and unit and unit.broker_id:
        broker_id = unit.broker_id
        broker_name = unit.broker_name or str(unit.broker_id)
    if cls and cls.typ == MessageType.FLAECHENUPDATE and unit and unit.broker_id:
        broker_id = unit.broker_id
        broker_name = unit.broker_name or str(unit.broker_id)

    if cls and cls.typ == MessageType.FEHLT_IN_PS:
        titel = f"Objekt fehlt in Propstack: {cls.objekt_name or msg.get('text', '')[:60]}"
    elif cls and cls.typ == MessageType.FLAECHENUPDATE:
        titel = f"Flächenupdate abgleichen: {cls.objekt_name or msg.get('text', '')[:60]}"
    else:
        objekt = (cls.objekt_name if cls else None) or (unit.adresse() if unit else None)
        titel = f"Slack #objekte prüfen: {objekt or msg.get('text', '')[:60]}"

    body_teile = [
        f"Slack-Nachricht vom {slack_datum}:",
        f"<blockquote>{msg.get('text', '')}</blockquote>",
        f"Permalink: {permalink}",
        f"Einordnung: {decision.grund}",
    ]
    if match and match.grund:
        body_teile.append(f"Objekt-Matching: {match.grund}")
    if match and match.kandidaten:
        kandidaten = "<br>".join(f"- {u.adresse()} (Unit {u.id})" for u in match.kandidaten[:10])
        body_teile.append(f"Kandidaten:<br>{kandidaten}")
    if decision.geplante_aktionen:
        body_teile.append("Vorbereitete Aktion:<br>" + "<br>".join(f"- {a}" for a in decision.geplante_aktionen))

    task = TaskPayload(
        title=titel,
        body="<br><br>".join(body_teile),
        broker_id=broker_id,
        is_reminder=True,
        due_date=due_date_plus_business_days(2),
        property_ids=[u.id for u in match.units] if match and match.units else None,
    )
    task_id = create_task(task)

    add_checkmark(msg["ts"])
    post_thread_reply(
        msg.get("thread_ts") or msg["ts"],
        f"Nicht automatisch ausgeführt – Review-Aufgabe an {broker_name} erstellt. ({decision.grund})",
    )
    return [f"Review-Aufgabe an {broker_name} ({broker_id}), Task {task_id}"]


def _process_message(msg: dict, context: str | None, run_id: str, report: RunReport) -> None:
    text = (msg.get("text") or "").strip()
    record = DecisionRecord(
        run_id=run_id,
        verarbeitet_am=datetime.now(timezone.utc).isoformat(),
        message_ts=msg["ts"],
        thread_ts=msg.get("thread_ts"),
        text_auszug=text[:300],
    )

    try:
        cls = classify_message(text, context)
        time.sleep(3)
        record.classification = cls

        if cls is None:
            report.fehler.append(f"Nachricht {msg['ts']}: nicht klassifizierbar")
            record.fehler = "Klassifikation fehlgeschlagen (Retry im nächsten Lauf)"
            return

        match: MatchResult | None = None
        if cls.typ in (MessageType.STATUS_ANWEISUNG, MessageType.FLAECHENUPDATE):
            match = find_unit(cls)
            record.match = match

        decision = decide(cls, match)
        record.decision = decision
        logger.info(
            "Nachricht %s: typ=%s match=%s -> Stufe %s (%s)",
            msg["ts"], cls.typ.value,
            match.status.value if match else "-",
            decision.tier.value, decision.grund,
        )

        if decision.tier == Tier.NONE:
            report.ignoriert += 1
            return

        permalink = get_permalink(msg["ts"]) or ""

        if decision.tier == Tier.A:
            record.ausgefuehrte_aktionen = _stufe_a(msg, cls, match, permalink)
            report.stufe_a += 1
        else:
            record.ausgefuehrte_aktionen = _stufe_b(msg, cls, match, decision, permalink)
            report.stufe_b += 1

        record.permalink = permalink
    except Exception as e:  # pro Nachricht weiterlaufen
        logger.exception("Fehler bei Nachricht %s", msg.get("ts"))
        record.fehler = str(e)
        report.fehler.append(f"Nachricht {msg.get('ts')}: {e}")
    finally:
        append_record(record)


def run_pipeline() -> RunReport:
    report = RunReport()
    run_id = uuid.uuid4().hex[:12]

    if config.no_write():
        logger.info("=== NO_WRITE – reiner Lese-/Loglauf, keine Writes, keine Reactions ===")
    elif config.dry_run():
        logger.info("=== DRY RUN – Woche-1-Regel: alles läuft als Stufe B ===")

    bot_user_id = get_bot_user_id()
    logger.info("Bot-User-ID: %s, Kanal: %s", bot_user_id, config.OBJEKTE_CHANNEL)

    candidates = _collect_candidates(bot_user_id)
    report.nachrichten_gesehen = len(candidates)
    logger.info("%d Nachrichten im Scan-Fenster (%dh)", len(candidates), config.scan_hours())

    for i, (msg, context) in enumerate(candidates, 1):
        preview = (msg.get("text") or "")[:80]
        logger.info("--- Nachricht %d/%d (%s): %s ---", i, len(candidates), msg["ts"], preview)

        if has_bot_checkmark(msg, bot_user_id):
            logger.info("Bereits verarbeitet (eigenes ✅) – übersprungen")
            report.bereits_verarbeitet += 1
            continue

        if not (msg.get("text") or "").strip():
            logger.info("Kein Text – übersprungen")
            report.ignoriert += 1
            continue

        _process_message(msg, context, run_id, report)

    _print_summary(report)
    return report


def _print_summary(report: RunReport) -> None:
    logger.info("=" * 60)
    logger.info("Zusammenfassung #objekte-Handler")
    logger.info("  Nachrichten im Fenster:   %d", report.nachrichten_gesehen)
    logger.info("  Bereits verarbeitet (✅): %d", report.bereits_verarbeitet)
    logger.info("  Ignoriert:                %d", report.ignoriert)
    logger.info("  Stufe A (ausgeführt):     %d", report.stufe_a)
    logger.info("  Stufe B (Review-Aufgabe): %d", report.stufe_b)
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
