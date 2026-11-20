from __future__ import annotations

import json
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
from .match_ai import propose_search_terms, select_open_match
from .models import (
    Deal,
    Decision,
    DecisionRecord,
    MatchResult,
    MatchStatus,
    RunReport,
    Tier,
)
from .propstack import (
    TaskPayload,
    absage_hindernis,
    create_task,
    fetch_vermietungs_pipelines,
    get_open_deals,
    set_rented,
)
from .review_dedup import OffeneReviews
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


# Kennung im Entscheidungslog für "keine neue Aufgabe, es liegt schon eine offene vor"
BEREITS_OFFEN = "Keine neue Aufgabe"


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

    # Abgesagt werden nur Deals der Vermietung, nie ein Deal in der Abschluss-Phase
    try:
        vermietungs_pipelines: set[int] | None = fetch_vermietungs_pipelines()
    except Exception as e:
        logger.error("Deal-Pipelines nicht lesbar (%s) – nur Deals ohne Pipeline werden abgesagt", e)
        vermietungs_pipelines = None

    absagen = 0
    for unit in match.units:
        for open_deal in get_open_deals(unit.id):
            hindernis = absage_hindernis(open_deal, vermietungs_pipelines)
            if hindernis:
                aktionen.append(f"Deal {open_deal.get('id')} an Unit {unit.id} nicht abgesagt ({hindernis})")
                continue
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


def _auswertungszeile(msg: dict, idx: int, deal: Deal, match: MatchResult | None, decision: Decision,
                      bereits_abgeschlossen: bool) -> None:
    """Eine maschinenlesbare Zeile je Vermietung – nur im Lese-Lauf (NO_WRITE). Damit lässt
    sich ein Lauf über alte Digests gegen die geprüften Urteile legen
    (scripts/radar_zuordnung_messen.py), ohne das Entscheidungslog vom Runner zu holen."""
    if not config.no_write() or not deal.ist_vermietung:
        return
    logger.info("AUSWERTUNG %s", json.dumps({
        "ts": msg.get("ts"), "idx": idx, "objekt": deal.objekt_name, "mieter": deal.mieter,
        "vermieter": deal.vermieter, "groesse": deal.groessen_hinweis, "ort": deal.stadt,
        "verlaengerung": deal.ist_verlaengerung,
        "status": match.status.value if match else None,
        "units": [u.id for u in match.units] if match else [],
        "anderer_eigentuemer": bool(match and match.anderer_eigentuemer),
        "bereits_abgeschlossen": bereits_abgeschlossen,
        "stufe": decision.tier.value,
        "grund": (match.grund if match else decision.grund)[:300],
    }, ensure_ascii=False))


def _review_unit_ids(match: MatchResult | None) -> list[int]:
    """Die Einheiten, mit denen eine Review-Aufgabe verknüpft wird."""
    return [u.id for u in match.units] if match and match.units else []


def _stufe_b(
    msg: dict, deal: Deal, match: MatchResult | None, decision: Decision, permalink: str,
    offene_reviews: OffeneReviews | None = None,
) -> list[str]:
    """Review-Aufgabe statt Ausführung – höchstens eine offene je Einheit."""
    slack_datum = datetime.fromtimestamp(float(msg["ts"]), tz=timezone.utc).date().isoformat()

    # Newsletter-Review-Aufgaben gehen zentral an den Review-Sitz (Marktbeobachtung),
    # unabhängig vom Objekt-Makler.
    broker_id = config.BROKER_REVIEW
    broker_name = config.BROKER_REVIEW_NAME
    unit = match.units[0] if match and match.units else None
    if unit is None and match and match.kandidaten:
        unit = match.kandidaten[0]

    objekt = deal.objekt_name or (unit.adresse() if unit else None)
    titel = f"{config.REVIEW_TITEL_PRAEFIX}: {objekt or msg.get('text', '')[:60]}"

    unit_ids = _review_unit_ids(match)
    if offene_reviews is not None:
        vorhanden, task_id = offene_reviews.vorhanden(unit_ids)
        if vorhanden:
            logger.info("Keine neue Review-Aufgabe: zu Unit(s) %s liegt schon eine offene (Task %s)", unit_ids, task_id)
            return [f"{BEREITS_OFFEN}: offene Review-Aufgabe zur selben Einheit vorhanden (Task {task_id}, Units {unit_ids})"]

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
        property_ids=unit_ids or None,
    )
    task_id = create_task(task)
    if offene_reviews is not None:
        offene_reviews.merke(unit_ids, task_id)
    return [f"Review-Aufgabe an {broker_name} ({broker_id}), Task {task_id}"]


def _process_message(
    msg: dict, run_id: str, report: RunReport, offene_reviews: OffeneReviews | None = None,
) -> None:
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
    schon_offen = 0
    schon_zu = 0
    fremd = 0
    nur_verlaengert = 0
    gescheitert = 0

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
            bereits_abgeschlossen = False
            if deal.ist_vermietung and deal.ist_verlaengerung:
                report.vermietungen += 1   # zählt als Meldung, braucht aber keine Objektsuche
            elif deal.ist_vermietung:
                report.vermietungen += 1
                terms = propose_search_terms(deal)
                candidates = gather_candidates(deal, extra_queries=terms)
                if candidates:
                    match, bereits_abgeschlossen = select_open_match(deal, candidates)
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

            _auswertungszeile(msg, idx, deal, match, decision, bereits_abgeschlossen)

            if decision.tier == Tier.NONE:
                if bereits_abgeschlossen:
                    report.bereits_abgeschlossen += 1
                    schon_zu += 1
                elif deal.ist_vermietung and deal.ist_verlaengerung:
                    report.verlaengerungen += 1
                    nur_verlaengert += 1
                elif match is not None and match.anderer_eigentuemer:
                    report.anderer_eigentuemer += 1
                    fremd += 1
                else:
                    report.ignoriert += 1
                continue
            if decision.tier == Tier.A:
                record.ausgefuehrte_aktionen = _stufe_a(msg, deal, match, permalink)
                report.stufe_a += 1
                gesetzt += 1
            else:
                record.ausgefuehrte_aktionen = _stufe_b(msg, deal, match, decision, permalink, offene_reviews)
                if record.ausgefuehrte_aktionen and record.ausgefuehrte_aktionen[0].startswith(BEREITS_OFFEN):
                    report.bereits_offen += 1
                    schon_offen += 1
                else:
                    report.stufe_b += 1
                    reviews += 1
        except Exception as e:  # pro Deal weiterlaufen
            logger.exception("Fehler bei Deal %s#%d", msg.get("ts"), idx)
            record.fehler = str(e)
            report.fehler.append(f"Deal {msg.get('ts')}#{idx}: {e}")
            gescheitert += 1
        finally:
            append_record(record)

    if gescheitert:
        # Kein ✅ und keine Sammel-Antwort: Sonst gälte der Digest als ausgewertet, obwohl
        # ein Deal verloren ging. Der Lauf endet rot, der nächste Lauf sieht den Digest
        # wieder (Fenster 50 h) – was schon eine Aufgabe hat, schützt der Dublettenschutz.
        logger.error("Nachricht %s: %d Deal(s) nicht verarbeitet – kein ✅", msg["ts"], gescheitert)
        return

    # ✅ + Sammel-Antwort erst nach allen Deals der Message
    add_checkmark(msg["ts"])
    vermietungen = sum(1 for d in extraction.deals if d.ist_vermietung)
    reply = (
        f"Logistik-Deal Radar ausgewertet: {len(extraction.deals)} Deals, "
        f"{vermietungen} Vermietung(en) – {gesetzt} Einheit(en) auf vermietet gesetzt, "
        f"{reviews} Review-Aufgabe(n) erstellt."
    )
    if schon_offen:
        reply += f" {schon_offen} ohne neue Aufgabe: zur Einheit liegt schon eine offene Review-Aufgabe."
    if schon_zu:
        reply += f" {schon_zu} ohne Aufgabe: Einheit ist in Propstack bereits vermietet/abgeschlossen."
    if fremd:
        reply += f" {fremd} ohne Aufgabe: Das Objekt am Ort gehört einem anderen Eigentümer als dem Vermieter der Meldung."
    if nur_verlaengert:
        reply += f" {nur_verlaengert} ohne Aufgabe: bloße Vertragsverlängerung."
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
    offene_reviews = OffeneReviews()
    logger.info("%d Nachrichten im Scan-Fenster (%dh)", len(messages), config.scan_hours())

    for i, msg in enumerate(messages, 1):
        preview = (msg.get("text") or "")[:80]
        logger.info("--- Nachricht %d/%d (%s): %s ---", i, len(messages), msg["ts"], preview)

        if not config.ignore_checkmark() and has_bot_checkmark(msg, bot_user_id):
            logger.info("Bereits verarbeitet (eigenes ✅) – übersprungen")
            report.bereits_verarbeitet += 1
            continue

        if not (msg.get("text") or "").strip():
            logger.info("Kein Text – übersprungen")
            report.ignoriert += 1
            continue

        _process_message(msg, run_id, report, offene_reviews)

    if offene_reviews.laden_fehlgeschlagen:
        report.fehler.append(
            f"Offene Review-Aufgaben nicht lesbar ({offene_reviews.fehler}) – in diesem Lauf ohne Dublettenschutz angelegt"
        )

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
    logger.info("  Schon offene Aufgabe:     %d", report.bereits_offen)
    logger.info("  Bereits abgeschlossen:    %d", report.bereits_abgeschlossen)
    logger.info("  Anderer Eigentümer:       %d", report.anderer_eigentuemer)
    logger.info("  Nur Verlängerung:         %d", report.verlaengerungen)
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
