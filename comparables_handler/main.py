from __future__ import annotations

import logging
import sys
import time
import uuid
from datetime import datetime, timezone

from . import (
    aggregate, asana_gateway, cache, config, drive_gateway, extractor,
    kennzahlen, logbuch, normalize, propstack_gateway, report_pdf, snapshots,
)
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


def _propstack_zeilen(report: RunReport) -> list[ComparableZeile]:
    """Primärquelle: die in Propstack gepflegten Mieten."""
    units = propstack_gateway.fetch_units(nur_miete=True)
    zeilen = normalize.propstack_zu_zeilen(units, report.propstack)

    ps = report.propstack
    logger.info(
        "Propstack: %d Einheiten, davon %d mit Miete und %d ohne "
        "(%d davon 'Preis auf Anfrage')",
        ps.units_geladen, ps.mit_miete, ps.ohne_miete, ps.preis_auf_anfrage,
    )
    if ps.miete_felder:
        logger.info("Mieten gefunden in: %s", ", ".join(
            f"{feld}={anzahl}" for feld, anzahl in sorted(
                ps.miete_felder.items(), key=lambda x: -x[1])
        ))
    if ps.units_geladen and not ps.mit_miete:
        report.fehler.append(
            f"Propstack: keine einzige der {ps.units_geladen} Miet-Einheiten trägt eine "
            "Miete in den geprüften Feldern – Feldnamen mit "
            "scripts/propstack_miet_audit.py klären"
        )
    return zeilen


def _drive_zeilen(report: RunReport, run_id: str) -> list[ComparableZeile]:
    """Ergänzungsquelle: erhaltene Fremdangebote aus dem Drive."""
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
    return zeilen


def _kennzahlen(
    zeilen: list[ComparableZeile], stats: list, report: RunReport
) -> tuple[list, str | None]:
    """Kennzahlen-Tabellen bauen und den Lauf als Snapshot fortschreiben.

    Der Periodenvergleich entsteht ausschließlich aus dieser Ablage – Propstack
    führt keine Miethistorie. Beim ersten Lauf bleibt die Veränderungsspalte
    deshalb leer, statt eine erfundene Basis auszuweisen.
    """
    stand_kurz = snapshots.aktueller_stand()
    verlauf = snapshots.laden(config.snapshot_path())
    vergleich = snapshots.vergleichs_snapshot(
        verlauf, stand_kurz, config.VERGLEICH_MONATE, config.VERGLEICH_TOLERANZ_MONATE,
    )

    tabellen = [
        kennzahlen.baue_tabelle(zeilen, art, vergleich)
        for art in aggregate.flaechenarten(stats)
    ]
    tabellen = [t for t in tabellen if t.zeilen]

    if tabellen and not config.no_write():
        verlauf = snapshots.anhaengen(
            verlauf, stand_kurz, kennzahlen.snapshot_werte(tabellen))
        snapshots.schreiben(config.snapshot_path(), verlauf)
    elif config.no_write():
        logger.info("[NO_WRITE] Snapshot %s wird nicht fortgeschrieben", stand_kurz)

    return tabellen, (vergleich or {}).get("stand")


def run_pipeline() -> RunReport:
    report = RunReport()
    run_id = uuid.uuid4().hex[:12]
    stand = _stand()
    report.quelle = config.quelle()

    if config.no_write():
        logger.info("=== NO_WRITE – reiner Lese-/Loglauf, kein Slack-Post ===")
    elif config.dry_run():
        logger.info("=== DRY RUN – Report wird gebaut und geloggt, aber nicht gepostet ===")

    logger.info(
        "Quelle: %s | Flächenarten: %s | Stand: %s | Zielkanal: %s | PDF-Fassung: %s",
        report.quelle, ", ".join(config.ausgewertete_flaechenarten()),
        stand, config.slack_channel(), config.vertraulichkeit(),
    )

    zeilen: list[ComparableZeile] = []
    if config.nutzt_propstack():
        try:
            zeilen.extend(_propstack_zeilen(report))
        except Exception as e:
            logger.exception("Propstack-Abruf fehlgeschlagen")
            report.fehler.append(f"Propstack: {e}")
    if config.nutzt_drive():
        try:
            zeilen.extend(_drive_zeilen(report, run_id))
        except Exception as e:
            logger.exception("Drive-Auswertung fehlgeschlagen")
            report.fehler.append(f"Drive: {e}")

    report.zeilen_gesamt = len(zeilen)
    report.zeilen_verwertbar = sum(1 for z in zeilen if z.verwertbar)
    report.zeilen_ausgeschlossen = report.zeilen_gesamt - report.zeilen_verwertbar
    for zeile in zeilen:
        if zeile.ausschluss_grund:
            logger.info("Zeile ausgeschlossen (%s/%s): %s",
                        zeile.quelle, zeile.datei, zeile.ausschluss_grund)

    logbuch.schreibe_dataset(zeilen)

    # Aggregation + Ausgabe
    stats = aggregate.aggregiere(zeilen)
    report.regionen = len(aggregate.leitregionen(stats)) + len(aggregate.zonen(stats))

    # Kennzahlen-Tabellen im Marktbericht-Layout, inkl. Periodenvergleich
    tabellen, stand_vorher = _kennzahlen(zeilen, stats, report)

    text = baue_nachricht(stats, report, stand, tabellen, stand_vorher)
    logger.info("Report:\n%s", text)
    report.slack_gepostet = poste(text)

    if config.make_pdf():
        # Beide Fassungen aus DENSELBEN Zahlen – siehe config.pdf_fassungen().
        for fassung in config.pdf_fassungen():
            pfad = report_pdf.erzeuge_pdf(
                stats, report, stand, config.pdf_path(fassung), tabellen,
                stand_vorher, fassung,
            )
            if pfad:
                report.pdfs[fassung] = pfad

    # Ablage in Asana: eine Unteraufgabe je Monat unter der Oberaufgabe.
    # Läuft NACH dem PDF, weil die Dateien angehängt werden.
    try:
        report.asana_task_url = asana_gateway.veroeffentliche(
            stats, report, stand, report.pdfs, tabellen, stand_vorher,
        )
    except Exception as e:
        logger.exception("Asana-Ablage fehlgeschlagen")
        report.fehler.append(f"Asana: {e}")

    _print_summary(report, stats)
    return report


def _print_summary(report: RunReport, stats: list) -> None:
    logger.info("=" * 60)
    logger.info("Zusammenfassung Comparables-Report (Quelle: %s)", report.quelle)
    if config.nutzt_propstack():
        ps = report.propstack
        logger.info("  -- Propstack --")
        logger.info("  Miet-Einheiten geladen:     %d", ps.units_geladen)
        logger.info("    Einheiten mit Miete:      %d", ps.units_geladen - ps.ohne_miete)
        logger.info("    Einheiten ohne Miete:     %d", ps.ohne_miete)
        logger.info("      davon Preis auf Anfrage:%d", ps.preis_auf_anfrage)
        logger.info("  Mieten gefunden (Zeilen):   %d", ps.mit_miete)
        logger.info("    ohne Flächenangabe:       %d", ps.ohne_flaeche)
        logger.info("    Fläche verworfen:         %d (Datenfehler in Propstack)",
                    ps.flaeche_unplausibel)
        logger.info("    Flächenart nicht im Report:%d", ps.flaechenart_uebersprungen)
        logger.info("    als vermietet markiert:   %d", ps.vermietet)
        for feld, anzahl in sorted(ps.miete_felder.items(), key=lambda x: -x[1]):
            logger.info("    Miete aus %-22s %d", feld + ":", anzahl)
        logger.info("  -- Drive --")
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
    logger.info("  PDF-Fassungen:              %s",
                ", ".join(f"{f}: {p}" for f, p in report.pdfs.items()) or "–")
    logger.info("  Asana-Monatsbericht:        %s",
                report.asana_task_url or f"– ({config.asana_grund() or 'nicht angelegt'})")
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
