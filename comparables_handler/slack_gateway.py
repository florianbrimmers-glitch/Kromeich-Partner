from __future__ import annotations

import logging
import os

import httpx

from . import aggregate, config
from .models import RegionStats, RunReport

logger = logging.getLogger(__name__)

SLACK_API_URL = "https://slack.com/api"

MONATE = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.slack_bot_token()}"}


def eur(value: float | None, einheit: str = "") -> str:
    """4.58 -> '4,58 €/m²' (deutsches Dezimalkomma)."""
    if value is None:
        return "–"
    return f"{value:.2f}".replace(".", ",") + (f" {einheit}" if einheit else "")


def _run_url() -> str | None:
    """Link auf den Actions-Lauf (dort hängen CSV und PDF als Artefakt)."""
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def spanne(stat: RegionStats) -> str:
    """" (Spanne 4,05–4,90)" – leer bei nur einem Wert.

    Bei n=1 wäre "Spanne 4,58–4,58" Etikettenschwindel.
    """
    if (stat.min_kaltmiete is None or stat.max_kaltmiete is None
            or stat.min_kaltmiete == stat.max_kaltmiete):
        return ""
    return f" (Spanne {eur(stat.min_kaltmiete)}–{eur(stat.max_kaltmiete)})"


def _zeile(stat: RegionStats) -> str:
    nk = f", NK {eur(stat.median_nebenkosten)}" if stat.median_nebenkosten is not None else ""
    return (
        f"• *{stat.key} {stat.label}*: Median {eur(stat.median_kaltmiete, '€/m²')}"
        f"{spanne(stat)}{nk} – n={stat.n} aus {stat.n_objekte} Objekt(en)"
    )


def _einzelzeile(stat: RegionStats) -> str:
    """Einzelwerte ohne Median-Anspruch: die tatsächlichen Werte zeigen."""
    if stat.min_kaltmiete is not None and stat.max_kaltmiete is not None and \
            stat.min_kaltmiete != stat.max_kaltmiete:
        werte = f"{eur(stat.min_kaltmiete)} / {eur(stat.max_kaltmiete)} €/m²"
    else:
        werte = eur(stat.median_kaltmiete, "€/m²")
    nk = f", NK {eur(stat.median_nebenkosten)}" if stat.median_nebenkosten is not None else ""
    return f"• *{stat.key} {stat.label}*: {werte}{nk} – n={stat.n}"


def _kennzahlen_block(tabellen: list, stand_vorher: str | None) -> list[str]:
    """Kompakte Marktgebiets-Kennzahlen für Slack (Top-Märkte + Summen)."""
    zeilen: list[str] = ["\n*Kennzahlen nach Marktgebiet* (Median Nettokaltmiete)"]
    for tabelle in tabellen:
        if not tabelle.zeilen:
            continue
        teile = []
        for z in tabelle.zeilen:
            if z.ebene != "position":
                continue
            veraenderung = ""
            if z.veraenderung_prozent is not None:
                vorzeichen = "+" if z.veraenderung_prozent > 0 else ""
                veraenderung = (
                    f" ({vorzeichen}{z.veraenderung_prozent:.1f}".replace(".", ",") + " %)"
                )
            teile.append(f"{z.label} {eur(z.median_jetzt)}{veraenderung} (n={z.n})")
        gesamt = tabelle.gesamt
        kopf = f"  *{tabelle.flaechenart}*"
        if gesamt:
            kopf += f" – gesamt {eur(gesamt.median_jetzt, '€/m²')}, n={gesamt.n}"
        zeilen.append(kopf)
        if teile:
            zeilen.append("  " + " · ".join(teile))
    if stand_vorher:
        zeilen.append(f"  _Veränderung gegenüber Stand {stand_vorher}._")
    else:
        zeilen.append(
            "  _Veränderung erst ab dem nächsten Vergleichsstand – "
            "die Zeitreihe beginnt mit diesem Lauf._"
        )
    return zeilen


def baue_nachricht(
    stats: list[RegionStats], report: RunReport, stand: str,
    tabellen: list | None = None, stand_vorher: str | None = None,
) -> str:
    """Der monatliche Slack-Post. Reine Funktion – im Test ohne Netz prüfbar."""
    zeilen = [f"*Vergleichsmieten aus Mietangeboten – Stand {stand}*"]

    ges = aggregate.gesamt(stats)
    if ges is None or ges.n == 0:
        zeilen.append(
            "\n:warning: Keine verwertbaren Mieten gefunden. "
            f"{report.propstack.units_geladen} Propstack-Einheit(en) und "
            f"{report.dateien_eindeutig} Drive-Dokument(e) geprüft, "
            f"{report.zeilen_ausgeschlossen} Zeile(n) ausgeschlossen."
        )
        if report.propstack.units_geladen and not report.propstack.mit_miete:
            # KEIN einziger Betrag ist etwas anderes als eine niedrige Quote:
            # das riecht nach falschem Feldnamen, nicht nach fehlenden Daten.
            zeilen.append(
                "Keine *einzige* Einheit trug einen Betrag in den geprüften Feldern – "
                "das deutet auf einen falschen Feldnamen hin, nicht auf fehlende "
                "Daten (`scripts/propstack_miet_audit.py`)."
            )
        return "\n".join(zeilen)

    arten = aggregate.flaechenarten(stats)
    zeilen.append(
        f"*{ges.n} bekannte Mieten* an {ges.n_objekte} Standort(en), "
        f"{len(arten)} Flächenart(en)"
    )

    # Getrennt je Flächenart: Hallen- und Büromieten liegen in ganz anderen
    # Größenordnungen, ein gemeinsamer Median wäre eine Phantasiezahl.
    for art in arten:
        art_ges = aggregate.art_gesamt(stats, art)
        if art_ges is None:
            continue
        zeilen.append(
            f"\n*{art}* – Median {eur(art_ges.median_kaltmiete, '€/m²')}"
            f"{spanne(art_ges)}, n={art_ges.n} an {art_ges.n_objekte} Standort(en)"
        )

        leit = aggregate.leitregionen(stats, art)
        for s in leit:
            zeilen.append("  " + _zeile(s))

        einzeln = aggregate.einzelwerte(stats, art)
        if einzeln:
            zeilen.append(
                f"  _Einzelwerte (n<{config.MIN_N_LEITREGION}, kein Median):_ "
                + " · ".join(
                    f"{s.key} {eur(s.median_kaltmiete)} (n={s.n})" for s in einzeln
                )
            )
        if not leit and not einzeln:
            zon = aggregate.zonen(stats, art)
            zeilen.extend("  " + _zeile(s) for s in zon)

    if tabellen:
        zeilen.extend(_kennzahlen_block(tabellen, stand_vorher))

    ps = report.propstack
    if ps.units_geladen:
        # Bewusst absolut formuliert: Vermieter veröffentlichen ihre Mieten
        # nicht, ein niedriger Anteil ist der Normalfall und kein Mangel.
        # Zählbar ist, wie viele Mieten wir KENNEN.
        zeilen.append(
            f"\n_Aus Propstack: {ps.mit_miete} hinterlegte Mieten "
            f"(von {ps.units_geladen} Miet-Einheiten insgesamt)._"
        )

    fuss = [
        f"Quellen: Propstack {ges.n_propstack} · Drive {ges.n_drive}",
        f"eigene Angebote: {ges.n_eigene} · erhaltene: {ges.n_erhalten}",
        f"Ausgeschlossen: {report.zeilen_ausgeschlossen} Zeile(n)",
    ]
    if report.versionen_uebersprungen:
        fuss.append(f"ältere Versionen: {report.versionen_uebersprungen}")
    if report.dateien_kopien_uebersprungen:
        fuss.append(f"Mehrfachablagen: {report.dateien_kopien_uebersprungen}")
    zeilen.append("\n_" + " · ".join(fuss) + "_")

    url = _run_url()
    if url:
        zeilen.append(f"_Datensatz (CSV) als Artefakt: {url}_")

    if report.fehler:
        zeilen.append(f"\n:warning: {len(report.fehler)} Fehler im Lauf – siehe Actions-Log.")

    return "\n".join(zeilen)


def poste(text: str) -> bool:
    """Postet den Report in den Zielkanal.

    Im DRY_RUN/NO_WRITE nur geloggt – ein monatlicher Post ist nicht
    zurücknehmbar, deshalb ist der Default bewusst still.
    """
    if config.no_write() or config.dry_run():
        logger.info(
            "[%s] Würde in %s posten:\n%s",
            "NO_WRITE" if config.no_write() else "DRY_RUN", config.slack_channel(), text,
        )
        return False
    try:
        response = httpx.post(
            f"{SLACK_API_URL}/chat.postMessage",
            headers=_headers(),
            json={"channel": config.slack_channel(), "text": text, "unfurl_links": False},
            timeout=30.0,
        )
        data = response.json()
        if not data.get("ok"):
            logger.error("chat.postMessage fehlgeschlagen: %s", data.get("error"))
            return False
        logger.info("Report in %s gepostet", config.slack_channel())
        return True
    except httpx.HTTPError as e:
        logger.error("chat.postMessage error: %s", e)
        return False
