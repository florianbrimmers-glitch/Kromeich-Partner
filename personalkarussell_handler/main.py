from __future__ import annotations

import logging
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from . import config
from .classifier import build_thread_context, classify_message
from .decision import decide_message, decide_wechsel, due_date_plus_business_days
from .logbuch import append_record
from .matcher import (
    alte_links,
    eindeutig_ueber_verknuepfung,
    firmen_suchbegriff,
    match_company,
    match_person,
)
from .models import (
    Classification,
    Decision,
    DecisionRecord,
    MatchStatus,
    RunReport,
    Tier,
    Wechsel,
    WechselPlan,
)
from .propstack import (
    TaskPayload,
    create_task,
    get_company_links,
    get_company_name,
    get_contact,
    link_company,
    rename_company,
    search_contacts,
    unlink,
    update_contact,
)
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

KANAL = "#personalkarussel-logistik"


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
    """(Nachricht, Thread-Kontext) für alle Nachrichten im Scan-Fenster, inkl. Thread-Antworten."""
    now = datetime.now(timezone.utc)
    oldest = (now - timedelta(hours=config.scan_hours())).timestamp()
    latest = (
        (now - timedelta(hours=config.scan_latest_hours())).timestamp()
        if config.scan_latest_hours()
        else None
    )

    discovery_hours = max(config.scan_hours(), config.thread_lookback_hours())
    parents = fetch_channel_messages(hours=discovery_hours, latest_hours=config.scan_latest_hours())

    candidates: list[tuple[dict, str | None]] = []
    for parent in parents:
        if _in_scan_window(parent, oldest, latest) and not _is_own_message(parent, bot_user_id):
            candidates.append((parent, None))

        if parent.get("reply_count", 0) > 0:
            replies = fetch_thread_replies(parent["ts"])
            for idx, reply in enumerate(replies):
                if not _in_scan_window(reply, oldest, latest) or _is_own_message(reply, bot_user_id):
                    continue
                prior = [r.get("text", "") for r in replies[:idx] if not _is_own_message(r, bot_user_id)]
                candidates.append((reply, build_thread_context(parent.get("text", ""), prior)))
            time.sleep(1)

    candidates.sort(key=lambda c: float(c[0].get("ts", "0")))
    return candidates


def _slack_datum(msg: dict) -> str:
    return datetime.fromtimestamp(float(msg["ts"]), tz=timezone.utc).strftime("%d.%m.%Y")


def _plane(cls: Classification, wechsel: Wechsel) -> WechselPlan:
    """Propstack-Abgleich für einen Wechsel – nur lesend."""
    plan = WechselPlan(wechsel=wechsel)

    if wechsel.nachname:
        records = search_contacts(wechsel.name())
        plan.person = match_person(records, wechsel.vorname, wechsel.nachname)
        if plan.person.status == MatchStatus.NONE:
            # Volltextsuche findet "Fröhlich" nicht immer über "Froehlich" – Nachname allein nachschieben
            plan.person = match_person(search_contacts(wechsel.nachname), wechsel.vorname, wechsel.nachname)

    links = []
    if plan.person and plan.person.status == MatchStatus.UNIQUE:
        links = get_company_links(plan.person.person.id)

    if wechsel.neue_firma:
        firmenfeld = plan.person.person.company if plan.person and plan.person.person else None
        plan.firma = eindeutig_ueber_verknuepfung(
            match_company(search_contacts(firmen_suchbegriff(wechsel.neue_firma)), wechsel.neue_firma),
            links,
            firmenfeld,
        )

    if plan.person and plan.person.person and plan.firma and plan.firma.company:
        plan.alte_links = alte_links(links, plan.person.person, wechsel.alte_firma, plan.firma.company.id)

    plan.decision = decide_wechsel(cls, wechsel, plan.person, plan.firma, links)
    return plan


def _stufe_a(msg: dict, plan: WechselPlan, permalink: str) -> list[str]:
    """Wechsel ausführen.

    Reihenfolge: neue Verknüpfung, alte Verknüpfungen entfernen, erst dann das
    Firmenfeld ändern. Bricht ein Schritt ab, fehlt nie die Firmenzuordnung.

    Absicherung: Am 05.10.2026 hat das Ändern des Firmenfelds einer Person die
    bisher verknüpfte Firma mitumbenannt (Swiss Life, Tim Hamacher). Mit frischen
    Testdaten ließ sich das nicht nachstellen – deshalb werden die Namen aller
    beteiligten Firmen vorher gemerkt, danach geprüft und notfalls zurückgesetzt."""
    person = plan.person.person
    ziel = plan.firma.company
    w = plan.wechsel
    aktionen: list[str] = []

    namen_vorher = {link.company_id: link.company_name for link in get_company_links(person.id)}
    namen_vorher[ziel.id] = ziel.name

    link_company(person.id, ziel.id)
    aktionen.append(f"{person.name()} mit {ziel.name} verknüpft")

    for link in plan.alte_links:
        unlink(link.relationship_id)
        aktionen.append(f"Verknüpfung zu {link.company_name} entfernt")

    detail = get_contact(person.id)  # Listenabfrage liefert keine Beschreibung
    bisher = detail.get("company") or w.alte_firma or "unbekannt"
    vermerk = f"{_slack_datum(msg)}: Wechsel {bisher} → {ziel.name} (Slack {KANAL})"
    beschreibung = "\n".join(t for t in ((detail.get("description") or "").rstrip(), vermerk) if t)
    felder: dict = {"company": ziel.name, "description": beschreibung}
    if w.neue_position:
        felder["position"] = w.neue_position
    update_contact(person.id, felder)
    aktionen.append(f"Firma auf {ziel.name} gesetzt, Vermerk ergänzt")

    zurueckbenannt: list[str] = []
    if not config.no_write():
        for company_id, name in namen_vorher.items():
            jetzt = get_company_name(company_id)
            if name and jetzt and jetzt != name:
                rename_company(company_id, name)
                zurueckbenannt.append(f"{name} (war kurz '{jetzt}')")
                aktionen.append(f"Firma {company_id} zurückbenannt: '{jetzt}' -> '{name}'")

    hinweis = ""
    if zurueckbenannt:
        hinweis = ("<br><br>Achtung: Propstack hat beim Ändern verknüpfte Firmen umbenannt, "
                   "der Name wurde zurückgesetzt: " + ", ".join(zurueckbenannt))
    notiz = TaskPayload(
        title=f"Wechsel zu {ziel.name}",
        body=(
            f"Laut Slack {KANAL} vom {_slack_datum(msg)} von {bisher} zu {ziel.name} gewechselt."
            f"<br>Original: {msg.get('text', '')}<br>{permalink}"
            "<br><br>E-Mail, Telefon und Position stammen ggf. noch vom alten Arbeitgeber."
            f"{hinweis}"
        ),
        is_reminder=False,
        client_ids=[person.id],
    )
    task_id = create_task(notiz)
    aktionen.append(f"Notiz angelegt (Task {task_id})")
    return aktionen


def _stufe_b(msg: dict, titel: str, decision: Decision, plan: WechselPlan | None, permalink: str) -> list[str]:
    """Review-Aufgabe an das Sammelpostfach."""
    teile = [
        f"Slack {KANAL} vom {_slack_datum(msg)}:",
        f"<blockquote>{msg.get('text', '')}</blockquote>",
        f"Permalink: {permalink}",
        f"Einordnung: {decision.grund}",
    ]
    client_ids = None
    if plan and plan.person:
        if plan.person.kandidaten:
            teile.append("Kontakte in Propstack:<br>" + "<br>".join(
                f"- {p.name()} ({p.company or 'ohne Firma'}, id {p.id})" for p in plan.person.kandidaten[:10]
            ))
        if plan.person.person:
            client_ids = [plan.person.person.id]
    if plan and plan.firma and plan.firma.kandidaten:
        teile.append("Firmen in Propstack:<br>" + "<br>".join(
            f"- {c.name} (id {c.id})" for c in plan.firma.kandidaten[:10]
        ))
    if decision.geplante_aktionen:
        teile.append("Vorbereitete Aktion:<br>" + "<br>".join(f"- {a}" for a in decision.geplante_aktionen))

    task_id = create_task(TaskPayload(
        title=titel,
        body="<br><br>".join(teile),
        broker_id=config.BROKER_REVIEW_FALLBACK,
        is_reminder=True,
        due_date=due_date_plus_business_days(2),
        client_ids=client_ids,
    ))
    return [f"Review-Aufgabe an {config.BROKER_REVIEW_FALLBACK_NAME} ({config.BROKER_REVIEW_FALLBACK}), Task {task_id}"]


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

        msg_decision = decide_message(cls)
        if msg_decision and msg_decision.tier == Tier.NONE:
            logger.info("Nachricht %s: ignoriert (%s)", msg["ts"], cls.begruendung)
            report.ignoriert += 1
            return

        permalink = get_permalink(msg["ts"]) or ""
        record.permalink = permalink
        zeilen: list[str] = []

        if msg_decision:  # LinkedIn, Umfirmierung, nicht auswertbar
            titel = f"Personalkarussell prüfen: {text[:60]}"
            record.ausgefuehrte_aktionen += _stufe_b(msg, titel, msg_decision, None, permalink)
            report.stufe_b += 1
            zeilen.append(f"Review-Aufgabe an {config.BROKER_REVIEW_FALLBACK_NAME} ({msg_decision.grund})")
        else:
            for wechsel in cls.wechsel:
                plan = _plane(cls, wechsel)
                record.plaene.append(plan)
                d = plan.decision
                logger.info("  %s -> Stufe %s (%s)", wechsel.name(), d.tier.value, d.grund)
                if d.tier == Tier.A and d.bereits_aktuell:
                    zeilen.append(f"✅ {wechsel.name()}: steht in Propstack bereits bei {plan.firma.company.name}")
                elif d.tier == Tier.A:
                    record.ausgefuehrte_aktionen += _stufe_a(msg, plan, permalink)
                    report.stufe_a += 1
                    zeilen.append(f"✅ {wechsel.name()}: in Propstack auf {plan.firma.company.name} umgestellt")
                else:
                    titel = f"Personalkarussell prüfen: {wechsel.name()}"
                    record.ausgefuehrte_aktionen += _stufe_b(msg, titel, d, plan, permalink)
                    report.stufe_b += 1
                    zeilen.append(f"Review-Aufgabe an {config.BROKER_REVIEW_FALLBACK_NAME}: {d.grund}")

        add_checkmark(msg["ts"])
        post_thread_reply(msg.get("thread_ts") or msg["ts"], "\n".join(zeilen))
    except Exception as e:  # pro Nachricht weiterlaufen; ohne ✅ -> Retry im nächsten Lauf
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
        logger.info("=== DRY RUN – alles läuft als Stufe B (Review-Aufgaben) ===")

    bot_user_id = get_bot_user_id()
    logger.info("Bot-User-ID: %s, Kanal: %s", bot_user_id, config.PERSONALKARUSSELL_CHANNEL)

    candidates = _collect_candidates(bot_user_id)
    report.nachrichten_gesehen = len(candidates)
    logger.info("%d Nachrichten im Scan-Fenster (%dh)", len(candidates), config.scan_hours())

    for i, (msg, context) in enumerate(candidates, 1):
        logger.info("--- Nachricht %d/%d (%s): %s ---", i, len(candidates), msg["ts"], (msg.get("text") or "")[:80])
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
    logger.info("Zusammenfassung %s-Handler", KANAL)
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
