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


def _zeile(stat: RegionStats) -> str:
    spanne = ""
    if stat.min_kaltmiete is not None and stat.max_kaltmiete is not None:
        if stat.min_kaltmiete == stat.max_kaltmiete:
            spanne = ""
        else:
            spanne = f" (Spanne {eur(stat.min_kaltmiete)}–{eur(stat.max_kaltmiete)})"
    nk = f", NK {eur(stat.median_nebenkosten)}" if stat.median_nebenkosten is not None else ""
    return (
        f"• *{stat.key} {stat.label}*: Median {eur(stat.median_kaltmiete, '€/m²')}"
        f"{spanne}{nk} – n={stat.n} aus {stat.n_objekte} Objekt(en)"
    )


def baue_nachricht(stats: list[RegionStats], report: RunReport, stand: str) -> str:
    """Der monatliche Slack-Post. Reine Funktion – im Test ohne Netz prüfbar."""
    zeilen = [f"*Vergleichsmieten aus Mietangeboten – Stand {stand}*"]

    ges = aggregate.gesamt(stats)
    if ges is None or ges.n == 0:
        zeilen.append(
            "\n:warning: Keine verwertbaren Angebote gefunden. "
            f"{report.dateien_eindeutig} Dokument(e) geprüft, "
            f"{report.zeilen_ausgeschlossen} Zeile(n) ausgeschlossen."
        )
        return "\n".join(zeilen)

    zeilen.append(
        f"Datenbasis: {ges.n_objekte} Objekt(e), {ges.n} Laufzeit-Option(en) "
        f"aus {report.dateien_eindeutig} Drive-Dokument(en) – "
        f"Gesamt-Median {eur(ges.median_kaltmiete, '€/m²')} "
        f"(Spanne {eur(ges.min_kaltmiete)}–{eur(ges.max_kaltmiete)})"
    )

    leit = aggregate.leitregionen(stats)
    if leit:
        zeilen.append(f"\n*Leitregionen* (2-stellige PLZ, ab n={config.MIN_N_LEITREGION})")
        zeilen.extend(_zeile(s) for s in leit)
    else:
        zeilen.append(
            f"\n_Keine Leitregion erreicht n={config.MIN_N_LEITREGION} – "
            "Auswertung nur auf Zonen-Ebene._"
        )

    zon = aggregate.zonen(stats)
    if zon:
        zeilen.append("\n*Postleitzonen* (1-stellige PLZ)")
        zeilen.extend(_zeile(s) for s in zon)

    fuss = [
        f"Eigene Angebote: {ges.n_eigene} · erhaltene: {ges.n_erhalten}",
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
