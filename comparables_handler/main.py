from __future__ import annotations

import logging
import sys
import time
import uuid
from datetime import datetime, timezone

from . import aggregate, cache, config, drive_gateway, extractor, logbuch, normalize, report_pdf
from .models import ComparableZeile, DecisionRecord, DriveDoc, Mietangebot, RunReport
from .slack_gateway import MONATE, baue_nachricht, poste

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _stand() -> str:
    now = datetime.now(timezone.utc)
    return f"{MONATE[now.month - 1]} {now.year}"


def _record(run_id: str, doc: DriveDoc, **felder) -> DecisionRecord:
    return DecisionRecord(
        run_id=run_id,
        verarbeitet_am=datetime.now(timezone.utc).isoformat(),
        file_id=doc.file_id,
        datei=doc.name,
        mime_type=doc.mime_type,
        quelle_link=doc.web_link,
        gefunden_via=doc.gefunden_via,
        fundstellen=doc.fundstellen,
        **felder,
    )


def _lade_inhalt(doc: DriveDoc) -> list[dict] | None:
    """Dokument laden und in Content-Blöcke für Claude überführen."""
    if doc.mime_type in (config.MIME_GDOC, config.MIME_GSLIDES, config.MIME_GSHEET):
        text = drive_gateway.export_text(doc)
        return extractor.build_content(doc, None, text)

    data = drive_gateway.download_bytes(doc)
    if data is None:
        return None
    return extractor.build_content(doc, data, None)


def _extrahiere(
    docs: list[DriveDoc], run_id: str, report: RunReport
) -> list[tuple[DriveDoc, Mietangebot]]:
    """Alle Dokumente extrahieren (mit Cache) und Ausschlüsse anwenden."""
    alter_cache = cache.laden()
    # Nur die in DIESEM Lauf berührten Einträge werden zurückgeschrieben,
    # damit gelöschte/überschriebene Dateien nicht für immer im Cache bleiben.
    neuer_cache: dict[str, Mietangebot] = {}
    paare: list[tuple[DriveDoc, Mietangebot]] = []

    for i, doc in enumerate(docs, 1):
        logger.info("--- Dokument %d/%d: %s (%d Fundstelle(n)) ---", i, len(docs), doc.name, doc.fundstellen)

        grund = normalize.datei_ausschluss(doc.name)
        if grund:
            logger.info("  übersprungen: %s", grund)
            report.regel_uebersprungen += 1
            logbuch.append_record(_record(run_id, doc, uebersprungen=grund))
            continue

        if doc.mime_type not in config.SUPPORTED_MIMETYPES:
            grund = f"Format {doc.mime_type} nicht unterstützt"
            logger.info("  übersprungen: %s", grund)
            report.format_uebersprungen += 1
            logbuch.append_record(_record(run_id, doc, uebersprungen=grund))
            continue

        angebot = cache.hole(alter_cache, doc.file_id, doc.modified_time)
        aus_cache = angebot is not None

        if not aus_cache:
            try:
                content = _lade_inhalt(doc)
            except Exception as e:
                logger.exception("  Laden fehlgeschlagen")
                report.fehler.append(f"{doc.name}: Laden fehlgeschlagen ({e})")
                logbuch.append_record(_record(run_id, doc, fehler=str(e)))
                continue

            if content is None:
                grund = "kein lesbarer Inhalt"
                logger.info("  übersprungen: %s", grund)
                report.format_uebersprungen += 1
                logbuch.append_record(_record(run_id, doc, uebersprungen=grund))
                continue

            angebot = extractor.extract_angebot(content)
            time.sleep(2)
            if angebot is None:
                report.fehler.append(f"{doc.name}: Extraktion fehlgeschlagen")
                logbuch.append_record(_record(
                    run_id, doc, fehler="Extraktion fehlgeschlagen (Retry im nächsten Lauf)",
                ))
                continue
            report.extrahiert += 1
        else:
            logger.info("  aus Cache")
            report.aus_cache += 1

        cache.merken(neuer_cache, doc.file_id, doc.modified_time, angebot)

        grund = normalize.angebot_ausschluss(angebot)
        if grund:
            logger.info("  kein Comparable: %s (%s)", grund, angebot.begruendung)
            report.keine_mietangebote += 1
            logbuch.append_record(_record(
                run_id, doc, angebot=angebot, aus_cache=aus_cache, uebersprungen=grund,
            ))
            continue

        logger.info(
            "  Angebot: %s | %s %s | %d Option(en) | Anbieter %s",
            angebot.objekt or "?", angebot.plz or "?", angebot.ort or "?",
            len(angebot.optionen), angebot.anbieter or "?",
        )
        paare.append((doc, angebot))

    cache.schreiben(neuer_cache)
    return paare


def run_pipeline() -> RunReport:
    report = RunReport()
    run_id = uuid.uuid4().hex[:12]
    stand = _stand()

    if config.no_write():
        logger.info("=== NO_WRITE – reiner Lese-/Loglauf, kein Slack-Post ===")
    elif config.dry_run():
        logger.info("=== DRY RUN – Report wird gebaut und geloggt, aber nicht gepostet ===")

    logger.info("Stand: %s | Zielkanal: %s", stand, config.slack_channel())

    # 1. Drive-Discovery inkl. Datei-Dedup (Mehrfachablagen)
    docs, rohtreffer, kopien = drive_gateway.discover_documents()
    report.dateien_gefunden = rohtreffer
    report.dateien_eindeutig = len(docs)
    report.dateien_kopien_uebersprungen = kopien

    grenze = config.max_documents()
    if grenze and len(docs) > grenze:
        logger.warning(
            "MAX_DOCUMENTS=%d gesetzt – %d von %d Dokumenten werden NICHT ausgewertet",
            grenze, len(docs) - grenze, len(docs),
        )
        report.fehler.append(
            f"MAX_DOCUMENTS={grenze}: {len(docs) - grenze} Dokument(e) nicht ausgewertet"
        )
        docs = docs[:grenze]
        report.dateien_eindeutig = len(docs)

    # 2. Extraktion pro Dokument
    paare = _extrahiere(docs, run_id, report)

    # 3. Versions-Dedup: pro Objekt+Anbieter zählt die jüngste Fassung
    paare, verworfen = normalize.dedupliziere_versionen(paare)
    report.versionen_uebersprungen = len(verworfen)
    for doc, grund in verworfen:
        logger.info("Version übersprungen: %s – %s", doc.name, grund)
        logbuch.append_record(_record(run_id, doc, uebersprungen=grund))

    # 4. Normalisierung auf Report-Zeilen (eine je Laufzeit-Option)
    zeilen: list[ComparableZeile] = []
    for doc, angebot in paare:
        doc_zeilen = normalize.zu_zeilen(doc, angebot)
        zeilen.extend(doc_zeilen)
        logbuch.append_record(_record(
            run_id, doc, angebot=angebot, zeilen=len(doc_zeilen),
        ))

    report.zeilen_gesamt = len(zeilen)
    report.zeilen_verwertbar = sum(1 for z in zeilen if z.verwertbar)
    report.zeilen_ausgeschlossen = report.zeilen_gesamt - report.zeilen_verwertbar
    for zeile in zeilen:
        if zeile.ausschluss_grund:
            logger.info("Zeile ausgeschlossen (%s): %s", zeile.datei, zeile.ausschluss_grund)

    logbuch.schreibe_dataset(zeilen)

    # 5. Aggregation + Ausgabe
    stats = aggregate.aggregiere(zeilen)
    report.regionen = len(aggregate.leitregionen(stats)) + len(aggregate.zonen(stats))

    text = baue_nachricht(stats, report, stand)
    logger.info("Report:\n%s", text)
    report.slack_gepostet = poste(text)

    if config.make_pdf():
        report.pdf_erstellt = report_pdf.erzeuge_pdf(stats, report, stand, config.pdf_path())

    _print_summary(report, stats)
    return report


def _print_summary(report: RunReport, stats: list) -> None:
    logger.info("=" * 60)
    logger.info("Zusammenfassung Comparables-Report")
    logger.info("  Drive-Treffer (roh):        %d", report.dateien_gefunden)
    logger.info("  Mehrfachablagen entfernt:   %d", report.dateien_kopien_uebersprungen)
    logger.info("  Eindeutige Dokumente:       %d", report.dateien_eindeutig)
    logger.info("  Per Regel übersprungen:     %d", report.regel_uebersprungen)
    logger.info("  Format übersprungen:        %d", report.format_uebersprungen)
    logger.info("  Neu extrahiert:             %d", report.extrahiert)
    logger.info("  Aus Cache:                  %d", report.aus_cache)
    logger.info("  Keine Mietangebote:         %d", report.keine_mietangebote)
    logger.info("  Ältere Versionen entfernt:  %d", report.versionen_uebersprungen)
    logger.info("  Report-Zeilen:              %d", report.zeilen_gesamt)
    logger.info("    davon verwertbar:         %d", report.zeilen_verwertbar)
    logger.info("    davon ausgeschlossen:     %d", report.zeilen_ausgeschlossen)
    logger.info("  Regionen ausgewiesen:       %d", report.regionen)
    logger.info("  Slack gepostet:             %s", report.slack_gepostet)
    logger.info("  PDF:                        %s", report.pdf_erstellt or "–")
    logger.info("  Fehler:                     %d", len(report.fehler))
    for fehler in report.fehler:
        logger.info("    - %s", fehler)
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception:
        logger.exception("Pipeline-Totalausfall")
        sys.exit(1)
