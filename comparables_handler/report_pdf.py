from __future__ import annotations

import logging
import os

from . import aggregate, config
from .models import RegionStats, RunReport
from .slack_gateway import eur

logger = logging.getLogger(__name__)

# K&P-Styleguide (siehe kp-design-Skill, kp_brand.py – dort Single Source of Truth)
DUNKELGRUEN = "#19372C"
NEONGRUEN = "#BCED09"
DUNKELGRAU = "#191919"
HELLGRUEN = "#C2D076"
ZEBRA = "#F2F7EC"
HAIRLINE = "#C0C0C0"

BAND_H_MM = 48

# Reihenfolge: Jomolhari für Headlines, Poppins für Fließtext. Fehlen die
# TTFs (kp-design-Skill nicht vorhanden), rendert reportlab mit Standard-
# schriften weiter – das PDF ist dann nicht CI-treu, aber vollständig.
_FONT_DATEIEN = {
    "KP-Headline": "Jomolhari-Regular.ttf",
    "KP-Body": "Poppins-Regular.ttf",
    "KP-Body-Bold": "Poppins-Bold.ttf",
}
_FALLBACK = {"KP-Headline": "Times-Roman", "KP-Body": "Helvetica", "KP-Body-Bold": "Helvetica-Bold"}


def _registriere_fonts() -> dict[str, str]:
    """Bettet die K&P-Schriften ein, wenn der kp-design-Skill vorliegt."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_dir = os.path.join(config.kp_design_dir(), "assets", "fonts")
    namen: dict[str, str] = {}
    for logisch, datei in _FONT_DATEIEN.items():
        pfad = os.path.join(font_dir, datei)
        if not os.path.exists(pfad):
            namen[logisch] = _FALLBACK[logisch]
            continue
        try:
            pdfmetrics.registerFont(TTFont(logisch, pfad))
            namen[logisch] = logisch
        except Exception as e:  # defekte TTF soll das PDF nicht verhindern
            logger.warning("Schrift %s nicht ladbar (%s) – Fallback", datei, e)
            namen[logisch] = _FALLBACK[logisch]

    if any(v.startswith(("Times", "Helvetica")) for v in namen.values()):
        logger.warning(
            "K&P-Schriften nicht gefunden (%s) – PDF nutzt Standardschriften. "
            "KP_DESIGN_DIR auf den kp-design-Skill setzen für CI-Treue.", font_dir,
        )
    return namen


def _tabelle(kopf: list[str], zeilen: list[list[str]], breiten: list[float], fonts: dict[str, str]):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    tabelle = Table([kopf] + zeilen, colWidths=breiten, repeatRows=1, hAlign="LEFT")
    stil = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(DUNKELGRUEN)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), fonts["KP-Body-Bold"]),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 1), (-1, -1), fonts["KP-Body"]),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor(DUNKELGRAU)),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor(HAIRLINE)),
    ]
    for index in range(1, len(zeilen) + 1):
        if index % 2 == 0:
            stil.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor(ZEBRA)))
    tabelle.setStyle(TableStyle(stil))
    return tabelle


def _stats_zeilen(stats: list[RegionStats]) -> list[list[str]]:
    zeilen = []
    for s in stats:
        spanne = (
            f"{eur(s.min_kaltmiete)} – {eur(s.max_kaltmiete)}"
            if s.min_kaltmiete is not None and s.max_kaltmiete is not None
            else "–"
        )
        zeilen.append([
            f"{s.key}  {s.label}",
            eur(s.median_kaltmiete),
            spanne,
            eur(s.median_nebenkosten),
            eur(s.median_effektivmiete),
            str(s.n),
            str(s.n_objekte),
        ])
    return zeilen


def erzeuge_pdf(stats: list[RegionStats], report: RunReport, stand: str, pfad: str) -> str | None:
    """K&P-PDF für Kundengespräche. Rückgabe: Pfad oder None bei Fehler."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
        )
    except ImportError:
        logger.error("reportlab fehlt – PDF wird nicht erzeugt (pip install reportlab)")
        return None

    fonts = _registriere_fonts()
    seite_w, seite_h = A4
    rand = 20 * mm
    inhalt_w = seite_w - 2 * rand

    titel_stil = ParagraphStyle(
        "titel", fontName=fonts["KP-Headline"], fontSize=17, leading=21,
        textColor=colors.HexColor(DUNKELGRUEN), spaceBefore=12, spaceAfter=6,
    )
    body = ParagraphStyle(
        "body", fontName=fonts["KP-Body"], fontSize=10, leading=15,
        textColor=colors.HexColor(DUNKELGRAU), spaceAfter=5,
    )
    klein = ParagraphStyle(
        "klein", fontName=fonts["KP-Body"], fontSize=8, leading=12,
        textColor=colors.HexColor("#5A5A5A"), spaceAfter=3,
    )

    def _kopf(canv, doc):
        canv.saveState()
        if doc.page == 1:
            band = BAND_H_MM * mm
            canv.setFillColor(colors.HexColor(DUNKELGRUEN))
            canv.rect(0, seite_h - band, seite_w, band, fill=1, stroke=0)
            canv.setFillColor(colors.HexColor(NEONGRUEN))
            canv.rect(0, seite_h - band - 2.5 * mm, seite_w, 2.5 * mm, fill=1, stroke=0)
            canv.setFillColor(colors.white)
            canv.setFont(fonts["KP-Headline"], 9)
            canv.drawRightString(seite_w - rand, seite_h - 13 * mm, "KROMEICH & PARTNER")
            canv.setFont(fonts["KP-Headline"], 25)
            canv.drawString(rand, seite_h - 30 * mm, "VERGLEICHSMIETEN")
            canv.setFillColor(colors.HexColor(NEONGRUEN))
            canv.setFont(fonts["KP-Body"], 10)
            canv.drawString(rand, seite_h - 38 * mm, f"Auswertung aus Mietangeboten – Stand {stand}")
        else:
            canv.setFillColor(colors.HexColor(HELLGRUEN))
            canv.rect(0, seite_h - 6 * mm, seite_w, 1.2 * mm, fill=1, stroke=0)
        canv.setFillColor(colors.HexColor("#8A8A8A"))
        canv.setFont(fonts["KP-Body"], 7.5)
        canv.drawRightString(seite_w - rand, 12 * mm, f"Seite {doc.page}")
        canv.drawString(rand, 12 * mm, "Kromeich & Partner – Vertraulich, nur zur internen Verwendung")
        canv.restoreState()

    doc = SimpleDocTemplate(
        pfad, pagesize=A4, leftMargin=rand, rightMargin=rand,
        topMargin=(BAND_H_MM + 14) * mm, bottomMargin=18 * mm,
        title=f"Vergleichsmieten aus Mietangeboten – {stand}",
        author="Kromeich & Partner",
    )

    ges = aggregate.gesamt(stats)
    flow: list = []

    if ges is None or ges.n == 0:
        flow.append(Paragraph("Keine verwertbaren Angebote", titel_stil))
        flow.append(Paragraph(
            f"Im Lauf wurden {report.dateien_eindeutig} Dokument(e) geprüft, aber keine "
            "verwertbaren Konditionen extrahiert.", body,
        ))
        doc.build(flow, onFirstPage=_kopf, onLaterPages=_kopf)
        return pfad

    flow.append(Paragraph("Datenbasis", titel_stil))
    flow.append(Paragraph(
        f"Grundlage sind <b>{ges.n} belegte Mieten</b> an {ges.n_objekte} Standorten. "
        f"Der Median der Nettokaltmiete liegt bei <b>{eur(ges.median_kaltmiete, '€/m²')}</b> "
        f"pro Monat, die Spanne reicht von {eur(ges.min_kaltmiete)} bis "
        f"{eur(ges.max_kaltmiete)} €/m².", body,
    ))
    flow.append(Paragraph(
        "Mietkonditionen sind am Markt nicht öffentlich – Vermieter veröffentlichen sie "
        "in der Regel nicht. Die hier ausgewerteten Werte stammen aus eigenen Mandaten, "
        "Beratungsprojekten und konkreten Anfragen und sind damit belegte Konditionen, "
        "keine Schätzungen aus Marktberichten.", body,
    ))

    kopf = ["Region", "Median", "Spanne", "NK", "Effektiv", "n", "Objekte"]
    breiten = [
        inhalt_w - 5 * 21 * mm - 24 * mm,
        21 * mm, 36 * mm, 18 * mm, 21 * mm, 12 * mm, 16 * mm,
    ]

    leit = aggregate.leitregionen(stats)
    if leit:
        flow.append(Paragraph("Leitregionen (2-stellige Postleitzahl)", titel_stil))
        flow.append(_tabelle(kopf, _stats_zeilen(leit), breiten, fonts))
        flow.append(Spacer(1, 4 * mm))
        flow.append(Paragraph(
            f"Als Median ausgewiesen ab n={config.MIN_N_LEITREGION} Datenpunkten.", klein,
        ))

    einzeln = aggregate.einzelwerte(stats)
    if einzeln:
        flow.append(Paragraph("Einzelwerte", titel_stil))
        flow.append(Paragraph(
            f"Regionen mit weniger als {config.MIN_N_LEITREGION} Datenpunkten. Die Werte sind "
            "belegt, tragen aber keinen belastbaren Median – sie sind als Einzelfälle zu lesen.",
            klein,
        ))
        flow.append(Spacer(1, 2 * mm))
        flow.append(_tabelle(kopf, _stats_zeilen(einzeln), breiten, fonts))

    zon = aggregate.zonen(stats)
    if zon:
        flow.append(Paragraph("Postleitzonen (1-stellige Postleitzahl)", titel_stil))
        flow.append(_tabelle(kopf, _stats_zeilen(zon), breiten, fonts))

    flow.append(PageBreak())
    flow.append(Paragraph("Methodik", titel_stil))
    for punkt in (
        "<b>Datenquelle:</b> alle Mietangebote im Google Drive – Ordner „03. Leasing“ und "
        "„Mietangebote“ sowie alle Dateien mit „Mietangebot“ im Titel. Mehrfachablagen "
        "derselben Datei werden über eine Inhalts-Prüfsumme zusammengefasst.",
        "<b>Eine Zeile pro Laufzeit-Option:</b> nennt ein Angebot je Laufzeit einen eigenen "
        "Preis (Laufzeitstaffel), zählt jede Stufe als eigener Datenpunkt. Deshalb ist n "
        "größer als die Zahl der Objekte.",
        "<b>Normalisierung:</b> absolute Mieten werden über die Fläche in €/m²/Monat "
        "umgerechnet, Jahresmieten auf den Monat. Die Effektivmiete glättet die Kaltmiete "
        "um die mietfreie Zeit über die Laufzeit.",
        "<b>Versionen:</b> liegen mehrere Fassungen zum selben Objekt und Anbieter vor, "
        "zählt ausschließlich die jüngste.",
        "<b>Ausschlüsse:</b> eigene Vorlagen, die Kromeich-Büromiete, Anlagen ohne eigene "
        "Konditionen sowie Werte außerhalb des Plausibilitätsbereichs "
        f"({eur(config.KALTMIETE_MIN_EUR_QM)}–{eur(config.KALTMIETE_MAX_EUR_QM)} €/m²).",
        "<b>Median statt Mittelwert:</b> einzelne Ausreißer verschieben den Median nicht.",
        "<b>Zur Größe der Datenbasis:</b> Mieten werden am Markt nicht geteilt. Jeder hier "
        "ausgewiesene Wert ist eine konkret bekannte Kondition aus einem Mandat, einem "
        "Beratungsprojekt oder einer Anfrage – die absolute Zahl der Datenpunkte ist "
        "deshalb der aussagekräftige Maßstab, nicht ihr Anteil am Gesamtbestand.",
    ):
        flow.append(Paragraph(punkt, body))

    flow.append(Paragraph("Erfasste Objekte", titel_stil))
    flow.append(Paragraph(
        "Die Auswertung stützt sich auf folgende Objekte: " + "; ".join(ges.objekte) + ".", klein,
    ))
    flow.append(Spacer(1, 3 * mm))
    flow.append(KeepTogether(Paragraph(
        "Die Angaben stammen aus indikativen Mietangeboten und sind keine abgeschlossenen "
        "Mietverträge. Sie dienen der Orientierung über das aktuelle Angebotsniveau und "
        "stellen keine Wertermittlung dar.", klein,
    )))

    try:
        doc.build(flow, onFirstPage=_kopf, onLaterPages=_kopf)
    except Exception as e:
        logger.exception("PDF-Erzeugung fehlgeschlagen")
        report.fehler.append(f"PDF: {e}")
        return None

    logger.info("PDF erstellt: %s", pfad)
    return pfad
