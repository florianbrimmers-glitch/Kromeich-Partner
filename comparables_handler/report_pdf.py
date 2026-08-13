from __future__ import annotations

import logging
import os

from . import aggregate, config
from .models import KennzahlenTabelle, RegionStats, RunReport
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


def _font_verzeichnisse() -> list[str]:
    """Wo nach den K&P-Schriften gesucht wird, in dieser Reihenfolge.

    1. Der kp-design-Skill – die Single Source of Truth des Corporate Designs.
    2. assets/fonts im Repository – der Fallback für GitHub Actions, wo es
       keinen Skill gibt. Ohne diesen Pfad rendert der Monatslauf mit
       Helvetica/Times: gemessen am 13.08.2026 war die nach Asana geladene
       Datei byte-identisch mit einem Lauf ohne Schriften (16.299 statt 53.615
       Bytes). Inhaltlich richtig, aber nicht CI-treu – und genau diese Datei
       geht ins Kundengespräch.
    """
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [
        os.path.join(config.kp_design_dir(), "assets", "fonts"),
        os.path.join(repo, "assets", "fonts"),
    ]


def _finde_font(datei: str) -> str | None:
    for verzeichnis in _font_verzeichnisse():
        pfad = os.path.join(verzeichnis, datei)
        if os.path.exists(pfad):
            return pfad
    return None


def _registriere_fonts() -> dict[str, str]:
    """Bettet die K&P-Schriften ein, wenn sie irgendwo zu finden sind."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    namen: dict[str, str] = {}
    for logisch, datei in _FONT_DATEIEN.items():
        pfad = _finde_font(datei)
        if pfad is None:
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
            "K&P-Schriften nicht gefunden (gesucht in: %s) – PDF nutzt "
            "Standardschriften und ist NICHT CI-treu.",
            ", ".join(_font_verzeichnisse()),
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


# --- Vertraulichkeitsstufe --------------------------------------------------
# Die Mieten stammen überwiegend aus `intern_mietpreis_*`: Konditionen, die K&P
# aus Mandaten und Anfragen kennt und die der Vermieter NICHT veröffentlicht.
# Als Aggregat über viele Standorte ist das eine Marktaussage; bei n=1 ist die
# ausgewiesene Zahl exakt die Miete EINES Objekts – dann gibt das Dokument
# fremde Vertragskonditionen weiter. Für die externe Fassung fallen deshalb
# alle Zeilen unter MIN_N_EXTERN weg, ebenso die Objektliste.


def externe_kennzahlen(tabelle: KennzahlenTabelle) -> KennzahlenTabelle:
    """Kennzahlen-Tabelle ohne rückrechenbare Zeilen.

    Zwischen- und Gesamtsummen bleiben, solange sie selbst MIN_N_EXTERN
    erreichen – sie sind über mehrere Märkte gebildet und geben keine
    einzelne Kondition preis. Dass n sich dadurch nicht mehr zur Summe
    addiert, ist gewollt und wird im PDF benannt.
    """
    gefiltert = tabelle.model_copy(deep=True)
    gefiltert.zeilen = [z for z in tabelle.zeilen if z.n >= config.MIN_N_EXTERN]
    if tabelle.gesamt is not None and tabelle.gesamt.n < config.MIN_N_EXTERN:
        gefiltert.gesamt = None
    # Anteile sind über den gesamten Datenbestand gebildet und nennen keine
    # Miete – sie bleiben. Nur bei insgesamt zu kleiner Basis fallen sie weg.
    if any(z.n < config.MIN_N_EXTERN for z in tabelle.anteile):
        gefiltert.anteile = []
    return gefiltert


def externe_stats(stats: list[RegionStats]) -> list[RegionStats]:
    """Regionsstatistiken ohne rückrechenbare Zeilen.

    Einzelwerte (n < MIN_N_LEITREGION) fallen komplett weg – sie sind der Kern
    des Problems: eine Zeile, ein Objekt, eine fremde Miete. Gesamtzeilen
    bleiben immer, sie tragen die Datenbasis-Aussage.
    """
    return [
        s for s in stats
        if s.ebene == "gesamt"
        or (s.ebene != "leitregion_einzel" and s.n >= config.MIN_N_EXTERN)
    ]


def _prozent(wert: float | None, punkte: bool = False) -> str:
    """12.4 -> '+12,4 %' bzw. '+12,4 %-Pkte.' – leer, wenn keine Basis."""
    if wert is None:
        return "–"
    vorzeichen = "+" if wert > 0 else ""
    text = f"{vorzeichen}{wert:.1f}".replace(".", ",")
    return f"{text} %-Pkte." if punkte else f"{text} %"


def kennzahlen_tabelle(tabelle, breiten: list[float], fonts: dict[str, str], stand_vorher: str | None):
    """Kennzahlen im Marktbericht-Layout.

    Gruppen-Kopfzeilen ohne Werte, Positionen eingerückt, Zwischensummen in
    Grün, Gesamtsumme als volle grüne Zeile, Anteile darunter abgesetzt.
    """
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    vorher_kopf = stand_vorher or "Vorperiode"
    daten: list[list[str]] = [
        ["", "n", "Ø-MIETE", "SPITZE", vorher_kopf, "MEDIAN", "VERÄNDERUNG"]
    ]
    stil: list = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(DUNKELGRUEN)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), fonts["KP-Body-Bold"]),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 1), (-1, -1), fonts["KP-Body"]),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor(DUNKELGRAU)),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]

    zeile_index = 0
    letzte_gruppe = None

    def _werte(z, einrueckung: str = "") -> list[str]:
        einheit = "%" if z.ist_prozentwert else ""
        jetzt = (f"{z.median_jetzt:.1f}".replace(".", ",") + " %"
                 if z.ist_prozentwert and z.median_jetzt is not None
                 else eur(z.median_jetzt, einheit))
        vorher = (f"{z.median_vorher:.1f}".replace(".", ",") + " %"
                  if z.ist_prozentwert and z.median_vorher is not None
                  else eur(z.median_vorher))
        return [
            einrueckung + z.label,
            str(z.n) if not z.ist_prozentwert else "",
            "" if z.ist_prozentwert else eur(z.durchschnittsmiete),
            "" if z.ist_prozentwert else eur(z.spitzenmiete),
            vorher,
            jetzt,
            _prozent(z.veraenderung_prozent, punkte=z.ist_prozentwert),
        ]

    for z in tabelle.zeilen:
        # Gruppen-Kopfzeile einschieben (wie "Flächenumsatz bedeutende …")
        if z.gruppe and z.gruppe != letzte_gruppe and z.ebene == "position":
            zeile_index += 1
            daten.append([z.gruppe, "", "", "", "", "", ""])
            stil += [
                ("FONTNAME", (0, zeile_index), (-1, zeile_index), fonts["KP-Body-Bold"]),
                ("BACKGROUND", (0, zeile_index), (-1, zeile_index), colors.white),
            ]
            letzte_gruppe = z.gruppe

        zeile_index += 1
        if z.ebene == "zwischensumme":
            daten.append(_werte(z))
            stil += [
                ("TEXTCOLOR", (0, zeile_index), (-1, zeile_index), colors.HexColor("#1E7A4E")),
                ("FONTNAME", (0, zeile_index), (-1, zeile_index), fonts["KP-Body-Bold"]),
                ("BACKGROUND", (0, zeile_index), (-1, zeile_index), colors.HexColor(ZEBRA)),
                ("LINEABOVE", (0, zeile_index), (-1, zeile_index), 0.6,
                 colors.HexColor(HAIRLINE)),
            ]
            letzte_gruppe = None
        else:
            daten.append(_werte(z, "   "))
            if zeile_index % 2 == 0:
                stil.append(("BACKGROUND", (0, zeile_index), (-1, zeile_index),
                             colors.HexColor("#FAFAF7")))

    if tabelle.gesamt:
        zeile_index += 1
        daten.append(_werte(tabelle.gesamt))
        stil += [
            ("BACKGROUND", (0, zeile_index), (-1, zeile_index), colors.HexColor(DUNKELGRUEN)),
            ("TEXTCOLOR", (0, zeile_index), (-1, zeile_index), colors.white),
            ("FONTNAME", (0, zeile_index), (-1, zeile_index), fonts["KP-Body-Bold"]),
        ]

    for z in tabelle.anteile:
        zeile_index += 1
        daten.append(_werte(z))
        stil += [
            ("TEXTCOLOR", (0, zeile_index), (-1, zeile_index), colors.HexColor("#1E7A4E")),
            ("BACKGROUND", (0, zeile_index), (-1, zeile_index), colors.HexColor(ZEBRA)),
        ]
        if z is tabelle.anteile[0]:
            stil.append(("LINEABOVE", (0, zeile_index), (-1, zeile_index), 0.6,
                         colors.HexColor(HAIRLINE)))

    t = Table(daten, colWidths=breiten, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle(stil))
    return t


def _spanne_text(stat: RegionStats) -> str:
    """", Spanne 4,05 bis 4,90 €/m²" – leer bei nur einem Wert."""
    if (stat.min_kaltmiete is None or stat.max_kaltmiete is None
            or stat.min_kaltmiete == stat.max_kaltmiete):
        return ""
    return f", Spanne {eur(stat.min_kaltmiete)} bis {eur(stat.max_kaltmiete)} €/m²"


def hat_effektivmiete(stats: list[RegionStats]) -> bool:
    """Trägt die Effektivmiete Information, oder ist sie nur die Kaltmiete?

    Propstack führt keine mietfreien Zeiten – dort ist die Effektivmiete
    zwangsläufig gleich der Kaltmiete. Eine zweite identische Spalte im
    Kundengespräch ist Ballast, deshalb wird sie dann weggelassen.
    """
    return any(
        s.median_effektivmiete is not None
        and s.median_kaltmiete is not None
        and abs(s.median_effektivmiete - s.median_kaltmiete) >= 0.01
        for s in stats
    )


def _stats_zeilen(stats: list[RegionStats], mit_effektiv: bool = True) -> list[list[str]]:
    zeilen = []
    for s in stats:
        # Bei nur einem Wert keine Pseudo-Spanne "6,40 – 6,40" ausweisen
        if (s.min_kaltmiete is not None and s.max_kaltmiete is not None
                and s.min_kaltmiete != s.max_kaltmiete):
            spanne = f"{eur(s.min_kaltmiete)} – {eur(s.max_kaltmiete)}"
        else:
            spanne = "–"
        zeile = [f"{s.key}  {s.label}", eur(s.median_kaltmiete), spanne,
                 eur(s.median_nebenkosten)]
        if mit_effektiv:
            zeile.append(eur(s.median_effektivmiete))
        # n IST die Zahl der Standorte (Aggregationsbasis) – deshalb hier
        # daneben die Zahl der dahinterliegenden Einheiten und nicht noch
        # einmal dieselbe Zahl unter anderem Namen.
        zeile += [str(s.n), str(s.n_einheiten)]
        zeilen.append(zeile)
    return zeilen


def erzeuge_pdf(
    stats: list[RegionStats], report: RunReport, stand: str, pfad: str,
    tabellen: list | None = None, stand_vorher: str | None = None,
    fassung: str = config.VERTRAULICH_INTERN,
) -> str | None:
    """K&P-PDF. Rückgabe: Pfad oder None bei Fehler.

    `fassung` entscheidet über die Vertraulichkeitsstufe (siehe config) und ist
    bewusst ein Parameter und keine Umgebungsvariable: derselbe Lauf rendert
    beide Fassungen aus denselben Zahlen.
    """
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

    extern = fassung == config.VERTRAULICH_EXTERN
    if extern:
        unterdrueckt = len([
            s for s in stats
            if s.ebene in ("leitregion", "leitregion_einzel", "zone")
        ]) - len([
            s for s in externe_stats(stats)
            if s.ebene in ("leitregion", "zone")
        ])
        stats = externe_stats(stats)
        tabellen = [externe_kennzahlen(t) for t in (tabellen or [])]
        tabellen = [t for t in tabellen if t.zeilen or t.gesamt]
        logger.info(
            "Externe Fassung: %d Zeile(n) unter n=%d unterdrückt, keine Objektliste",
            unterdrueckt, config.MIN_N_EXTERN,
        )

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
    eyebrow = ParagraphStyle(
        "eyebrow", fontName=fonts["KP-Body-Bold"], fontSize=8.5, leading=12,
        textColor=colors.HexColor("#5F7A3A"), spaceBefore=6, spaceAfter=3,
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
        fuss = ("Kromeich & Partner – Marktauswertung, Weitergabe nur an den Adressaten"
                if extern else
                "Kromeich & Partner – Vertraulich, nur zur internen Verwendung")
        canv.drawString(rand, 12 * mm, fuss)
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

    arten = aggregate.flaechenarten(stats)

    # --- Kennzahlen-Seite im Marktbericht-Layout --------------------------
    if tabellen:
        flow.append(Paragraph("Kennzahlen Mietniveau Deutschland", titel_stil))
        untertitel = (
            f"Nettokaltmiete {arten[0]} in €/m² pro Monat (Median)."
            if len(arten) == 1 else
            "Nettokaltmiete in €/m² pro Monat (Median), je Flächenart."
        )
        flow.append(Paragraph(
            untertitel + " Gegliedert nach den bedeutenden Logistikmärkten "
            "und den sonstigen Standorten.", body,
        ))
        # 7 Spalten: Region | n | Ø | Spitze | Vorperiode | Median | Veränderung
        kz_spalten = (11, 19, 18, 22, 20, 26)
        kz_breiten = [inhalt_w - sum(kz_spalten) * mm] + [b * mm for b in kz_spalten]
        for tabelle in tabellen:
            if not tabelle.zeilen:
                continue
            flow.append(Paragraph(tabelle.flaechenart, eyebrow))
            flow.append(kennzahlen_tabelle(tabelle, kz_breiten, fonts, stand_vorher))
            flow.append(Spacer(1, 5 * mm))

        hinweise = [
            "<b>n</b> ist die Zahl der belegten Mieten. n summiert sich über die Gruppen – "
            "die Mietwerte nicht: sie werden je Gruppe über alle Datenpunkte neu berechnet.",
            "<b>Ø-Miete</b> ist das arithmetische Mittel, bewusst <b>nicht flächengewichtet</b>: "
            "die Flächenangaben im CRM sind dafür zu unzuverlässig. "
            f"<b>Spitze</b> ist das {int(config.SPITZENMIETE_PERZENTIL * 100)}. Perzentil und "
            "damit nicht der Höchstwert – ein einzelner Ausreißer soll das Spitzenniveau "
            "nicht bestimmen. Bei wenigen Datenpunkten nähert sich die Spitzenmiete "
            "zwangsläufig dem Maximum.",
        ]
        if extern:
            hinweise.append(
                f"<b>Ausgewiesen werden nur Märkte mit mindestens "
                f"{config.MIN_N_EXTERN} Datenpunkten.</b> Die Konditionen stammen aus "
                "Mandaten und Anfragen und sind vom Vermieter nicht veröffentlicht; "
                "einzelne Verträge werden deshalb nicht ausgewiesen. Aus demselben "
                "Grund addiert sich n nicht zur Gesamtzahl – die Summenzeilen sind "
                "über alle Datenpunkte gebildet, auch über die nicht gezeigten."
            )
        if stand_vorher:
            hinweise.append(
                f"Die Veränderung vergleicht den aktuellen Median mit dem Stand "
                f"{stand_vorher}. Anteile werden in Prozentpunkten ausgewiesen."
            )
        else:
            hinweise.append(
                "<b>Die Veränderungsspalte ist noch leer:</b> sie vergleicht mit dem "
                "Stand vor zwölf Monaten, und dieser Lauf ist der erste erfasste. "
                "Propstack führt keine Miethistorie, die Zeitreihe entsteht ab jetzt "
                "mit jedem Monatslauf."
            )
        for hinweis in hinweise:
            flow.append(Paragraph(hinweis, klein))
        flow.append(PageBreak())

    flow.append(Paragraph("Datenbasis", titel_stil))
    if len(arten) == 1:
        flow.append(Paragraph(
            f"Grundlage sind <b>{ges.n_einheiten} belegte Mieten</b> an {ges.n} Standorten "
            f"für <b>{arten[0]}</b>.", body,
        ))
    else:
        flow.append(Paragraph(
            f"Grundlage sind <b>{ges.n_einheiten} belegte Mieten</b> an {ges.n} Standorten, "
            f"aufgeteilt auf {len(arten)} Flächenarten.", body,
        ))
    flow.append(Paragraph(
        "Mietkonditionen sind am Markt nicht öffentlich – Vermieter veröffentlichen sie "
        "in der Regel nicht. Die hier ausgewerteten Werte stammen aus eigenen Mandaten, "
        "Beratungsprojekten und konkreten Anfragen und sind damit belegte Konditionen, "
        "keine Schätzungen aus Marktberichten.", body,
    ))
    if extern:
        flow.append(Paragraph(
            f"Weil diese Konditionen nicht öffentlich sind, weist diese Fassung nur "
            f"Märkte mit mindestens <b>{config.MIN_N_EXTERN} Datenpunkten</b> aus. "
            "Einzelne Objekte, ihre Mieten und die Objektliste bleiben intern.", body,
        ))
    if len(arten) > 1:
        flow.append(Paragraph(
            "<b>Die Flächenarten werden getrennt ausgewertet.</b> Hallen- und Lagerflächen, "
            "Büroflächen und Mezzanine liegen in grundlegend verschiedenen Preisniveaus; "
            "ein gemeinsamer Median über alle Flächenarten würde keinen Markt beschreiben.",
            body,
        ))
    else:
        flow.append(Paragraph(
            f"Ausgewertet werden ausschließlich <b>{arten[0]}</b>. Andere Flächenarten "
            "(Büro, Mezzanine, Service- und Kellerflächen) liegen in anderen Preisniveaus "
            "und sind nicht Teil dieser Auswertung.", body,
        ))

    mit_effektiv = hat_effektivmiete(stats)
    kopf = ["Region", "Median", "Spanne", "NK"]
    # Spalte bewusst nicht "Median" nennen: bei n=1 wäre das irreführend.
    kopf_einzel = ["Region", "Wert", "von – bis", "NK"]
    breiten = [0.0, 21 * mm, 36 * mm, 18 * mm]
    if mit_effektiv:
        kopf.append("Effektiv")
        kopf_einzel.append("Effektiv")
        breiten.append(21 * mm)
    kopf += ["Standorte", "Einheiten"]
    kopf_einzel += ["Standorte", "Einheiten"]
    breiten += [19 * mm, 18 * mm]
    breiten[0] = inhalt_w - sum(breiten[1:])

    for art in arten:
        art_ges = aggregate.art_gesamt(stats, art)
        if art_ges is None:
            continue

        flow.append(Paragraph(art, titel_stil))
        flow.append(Paragraph(
            f"Median <b>{eur(art_ges.median_kaltmiete, '€/m²')}</b>{_spanne_text(art_ges)} – "
            f"{art_ges.n} Standorte mit {art_ges.n_einheiten} erfassten Einheiten.", body,
        ))

        leit = aggregate.leitregionen(stats, art)
        if leit:
            flow.append(Paragraph("Leitregionen (2-stellige Postleitzahl)", eyebrow))
            flow.append(_tabelle(kopf, _stats_zeilen(leit, mit_effektiv), breiten, fonts))
            flow.append(Spacer(1, 3 * mm))

        einzeln = aggregate.einzelwerte(stats, art)
        if einzeln:
            flow.append(Paragraph(
                f"Einzelwerte (weniger als {config.MIN_N_LEITREGION} Datenpunkte – belegt, "
                "aber ohne belastbaren Median)", eyebrow,
            ))
            flow.append(_tabelle(kopf_einzel, _stats_zeilen(einzeln, mit_effektiv), breiten, fonts))
            flow.append(Spacer(1, 3 * mm))

        zon = aggregate.zonen(stats, art)
        if zon:
            flow.append(Paragraph("Postleitzonen (1-stellige Postleitzahl)", eyebrow))
            flow.append(_tabelle(kopf, _stats_zeilen(zon, mit_effektiv), breiten, fonts))
        flow.append(Spacer(1, 5 * mm))

    flow.append(PageBreak())
    flow.append(Paragraph("Methodik", titel_stil))

    # Die Quellenbeschreibung muss zum Lauf passen: der Regelbetrieb liest
    # Propstack, der Drive-Zweig ist die Ergänzung um Fremdangebote.
    quellen = {
        config.QUELLE_PROPSTACK:
            "<b>Datenquelle:</b> die in Propstack gepflegten Mietkonditionen aller "
            "Miet-Einheiten. Ausgelesen werden ausschließlich die in der Maske "
            "geführten Mietpreis-Felder je Flächenart.",
        config.QUELLE_DRIVE:
            "<b>Datenquelle:</b> alle Mietangebote im Google Drive – Ordner „03. Leasing“ "
            "und „Mietangebote“ sowie alle Dateien mit „Mietangebot“ im Titel. "
            "Mehrfachablagen derselben Datei werden über eine Inhalts-Prüfsumme "
            "zusammengefasst.",
        config.QUELLE_BEIDE:
            "<b>Datenquelle:</b> die in Propstack gepflegten Mietkonditionen, ergänzt um "
            "die Mietangebote im Google Drive (Ordner „03. Leasing“ und „Mietangebote“ "
            "sowie alle Dateien mit „Mietangebot“ im Titel).",
    }
    for punkt in (
        quellen.get(report.quelle or config.quelle(), quellen[config.QUELLE_PROPSTACK]),
        "<b>Ein Datenpunkt je Standort (n):</b> die Einheiten einer Adresse werden zu "
        "einem Wert zusammengefasst (Median). Ohne diesen Schritt würde ein Objekt mit "
        "vierzehn gleich bepreisten Einheiten den Markt vierzehnmal bestimmen. Die Spalte "
        "„Einheiten“ nennt die Zahl der dahinterliegenden Einzelwerte.",
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

    if extern:
        flow.append(Paragraph(
            f"<b>Diese Fassung ist zur Weitergabe bestimmt.</b> Sie weist nur Märkte mit "
            f"mindestens {config.MIN_N_EXTERN} Standorten aus und enthält keine Objektliste. "
            "Die Konditionen einzelner Objekte sind uns aus Mandaten und Anfragen bekannt "
            "und werden nicht weitergegeben.", body,
        ))

    # Die Objektliste ordnet jede Zeile einem konkreten Standort zu – zusammen
    # mit einem Regions-Median bei kleinem n wäre die Miete eines einzelnen
    # Objekts ableitbar. Sie bleibt der internen Fassung vorbehalten.
    if not extern:
        flow.append(Paragraph("Erfasste Objekte", titel_stil))
        flow.append(Paragraph(
            "Die Auswertung stützt sich auf folgende Objekte: "
            + "; ".join(ges.objekte) + ".", klein,
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
