from __future__ import annotations

import logging
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from . import config
from .classifier import extract_deals
from .decision import decide, due_date_plus_business_days
from .logbuch import append_record
from .matcher import gather_candidates
from .match_ai import select_match
from .models import (
    Deal,
    Decision,
    DecisionRecord,
    MatchResult,
    MatchStatus,
    RunReport,
    Tier,
)
from .propstack import TaskPayload, create_task, get_open_deals, set_rented
from .slack_gateway import (
    add_checkmark,
    fetch_channel_messages,
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
    """Digest-Nachrichten aus dem Scan-Fenster, aufsteigend nach ts."""
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


def _stufe_a(msg: dict, deal: Deal, match: MatchResult, permalink: str) -> list[str]:
    """Vermietung direkt ausführen: rented=true, Doku-Notiz, offene Deals absagen."""
    slack_datum = datetime.fromtimestamp(float(msg["ts"]), tz=timezone.utc).date().isoformat()
    quelle = f"Quelle: Slack #newsletter (Logistik-Deal Radar) vom {slack_datum}<br>{permalink}"
    aktionen: list[str] = []

    unit_ids = [u.id for u in match.units]
    for unit in match.units:
        set_rented(unit.id)
        aktionen.append(f"Unit {unit.id} rented=true")

    doku = TaskPayload(
        title=f"Vermietet (Newsletter): {match.units[0].adresse()}",
        body=(
            f"Vermietung aus dem Logistik-Deal Radar erkannt.<br>"
            f"Mieter: {deal.mieter or '–'} · Vermieter: {deal.vermieter or '–'}<br>"
            f"Original: {msg.get('text', '')[:1500]}<br>{quelle}"
        ),
        is_reminder=False,
        property_ids=unit_ids,
    )
    doku_id = create_task(doku)
    aktionen.append(f"Doku-Notiz angelegt (Task {doku_id})")

    absagen = 0
    for unit in match.units:
        for open_deal in get_open_deals(unit.id):
            client_id = open_deal.get("client_id") or (open_deal.get("client") or {}).get("id")
            if not client_id:
                logger.warning("Deal ohne client_id an Unit %s – übersprungen: %s", unit.id, open_deal.get("id"))
                continue
            absage = TaskPayload(
                title="Absage",
                body=f"Fläche vermietet (Newsletter) – automatische Absage.<br>{quelle}",
                reservation_reason_id=config.RESERVATION_REASON_ABSAGE,
                client_ids=[client_id],
                property_ids=[unit.id],
            )
            task_id = create_task(absage)
            aktionen.append(f"Absage Deal (Kunde {client_id}, Unit {unit.id}, Task {task_id})")
            absagen += 1

    return aktionen


def _stufe_b(msg: dict, deal: Deal, match: MatchResult | None, decision: Decision, permalink: str) -> list[str]:
    """Review-Aufgabe statt Ausführung."""
    slack_datum = datetime.fromtimestamp(float(msg["ts"]), tz=timezone.utc).date().isoformat()

    # Newsletter-Review-Aufgaben gehen zentral an Marek (Marktbeobachtung),
    # unabhängig vom Objekt-Makler.
    broker_id = config.BROKER_MAREK
    broker_name = "Marek"
    unit = match.units[0] if match and match.units else None
    if unit is None and match and match.kandidaten:
        unit = match.kandidaten[0]

    objekt = deal.objekt_name or (unit.adresse() if unit else None)
    titel = f"Newsletter-Vermietung prüfen: {objekt or msg.get('text', '')[:60]}"

    body_teile = [
        f"Vermietung aus dem Logistik-Deal Radar vom {slack_datum}:",
        f"<blockquote>{msg.get('text', '')[:2000]}</blockquote>",
        f"Mieter: {deal.mieter or '–'} · Vermieter: {deal.vermieter or '–'} · Größe: {deal.groessen_hinweis or '–'}",
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
    return [f"Review-Aufgabe an {broker_name} ({broker_id}), Task {task_id}"]


def _process_message(msg: dict, run_id: str, report: RunReport) -> None:
    text = (msg.get("text") or "").strip()

    extraction = extract_deals(text)
    time.sleep(3)
    if extraction is None:
        report.fehler.append(f"Nachricht {msg['ts']}: nicht extrahierbar")
        record = DecisionRecord(
            run_id=run_id,
            verarbeitet_am=datetime.now(timezone.utc).isoformat(),
            message_ts=msg["ts"],
            text_auszug=text[:300],
            fehler="Extraktion fehlgeschlagen (Retry im nächsten Lauf)",
        )
        append_record(record)
        return

    logger.info("Nachricht %s: %d Deals extrahiert", msg["ts"], len(extraction.deals))
    report.deals_gesamt += len(extraction.deals)

    permalink = get_permalink(msg["ts"]) or ""
    gesetzt = 0
    reviews = 0

    for idx, deal in enumerate(extraction.deals):
        record = DecisionRecord(
            run_id=run_id,
            verarbeitet_am=datetime.now(timezone.utc).isoformat(),
            message_ts=msg["ts"],
            deal_index=idx,
            permalink=permalink,
            text_auszug=text[:300],
            deal=deal,
        )
        try:
            match: MatchResult | None = None
            if deal.ist_vermietung:
                report.vermietungen += 1
                candidates = gather_candidates(deal)
                if candidates:
                    match = select_match(deal, candidates)
                else:
                    match = MatchResult(status=MatchStatus.NONE, grund="Keine Kandidaten gefunden")
                record.match = match

            decision = decide(deal, match)
            record.decision = decision
            logger.info(
                "Deal %s#%d: typ=%s vermietung=%s match=%s -> Stufe %s (%s)",
                msg["ts"], idx, deal.deal_typ.value, deal.ist_vermietung,
                match.status.value if match else "-",
                decision.tier.value, decision.grund,
            )

            if decision.tier == Tier.NONE:
                report.ignoriert += 1
                continue
            if decision.tier == Tier.A:
                record.ausgefuehrte_aktionen = _stufe_a(msg, deal, match, permalink)
                report.stufe_a += 1
                gesetzt += 1
            else:
                record.ausgefuehrte_aktionen = _stufe_b(msg, deal, match, decision, permalink)
                report.stufe_b += 1
                reviews += 1
        except Exception as e:  # pro Deal weiterlaufen
            logger.exception("Fehler bei Deal %s#%d", msg.get("ts"), idx)
            record.fehler = str(e)
            report.fehler.append(f"Deal {msg.get('ts')}#{idx}: {e}")
        finally:
            append_record(record)

    # ✅ + Sammel-Antwort erst nach allen Deals der Message
    add_checkmark(msg["ts"])
    vermietungen = sum(1 for d in extraction.deals if d.ist_vermietung)
    reply = (
        f"Logistik-Deal Radar ausgewertet: {len(extraction.deals)} Deals, "
        f"{vermietungen} Vermietung(en) – {gesetzt} Einheit(en) auf vermietet gesetzt, "
        f"{reviews} Review-Aufgabe(n) erstellt."
    )
    post_thread_reply(msg.get("thread_ts") or msg["ts"], reply)


def run_pipeline() -> RunReport:
    report = RunReport()
    run_id = uuid.uuid4().hex[:12]

    if config.no_write():
        logger.info("=== NO_WRITE – reiner Lese-/Loglauf, keine Writes, keine Reactions ===")
    elif config.dry_run():
        logger.info("=== DRY RUN – Vermietungen nur als Review-Aufgabe (Stufe B) ===")

    bot_user_id = get_bot_user_id()
    logger.info("Bot-User-ID: %s, Kanal: %s", bot_user_id, config.NEWSLETTER_CHANNEL)

    messages = _collect_messages()
    report.nachrichten_gesehen = len(messages)
    logger.info("%d Nachrichten im Scan-Fenster (%dh)", len(messages), config.scan_hours())

    for i, msg in enumerate(messages, 1):
        preview = (msg.get("text") or "")[:80]
        logger.info("--- Nachricht %d/%d (%s): %s ---", i, len(messages), msg["ts"], preview)

        if has_bot_checkmark(msg, bot_user_id):
            logger.info("Bereits verarbeitet (eigenes ✅) – übersprungen")
            report.bereits_verarbeitet += 1
            continue

        if not (msg.get("text") or "").strip():
            logger.info("Kein Text – übersprungen")
            report.ignoriert += 1
            continue

        _process_message(msg, run_id, report)

    _print_summary(report)
    return report


def _print_summary(report: RunReport) -> None:
    logger.info("=" * 60)
    logger.info("Zusammenfassung #newsletter-Handler")
    logger.info("  Nachrichten im Fenster:   %d", report.nachrichten_gesehen)
    logger.info("  Bereits verarbeitet (✅): %d", report.bereits_verarbeitet)
    logger.info("  Deals gesamt:             %d", report.deals_gesamt)
    logger.info("  davon Vermietungen:       %d", report.vermietungen)
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
