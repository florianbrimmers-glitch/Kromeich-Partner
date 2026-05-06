from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

from .models import WarehouseCandidate
from .overpass_client import parse_candidates, query_warehouses

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Bekannte Stadtzentren als Shortcuts für --center.
_CITY_PRESETS: dict[str, tuple[float, float]] = {
    "munich": (48.1374, 11.5755),
    "muenchen": (48.1374, 11.5755),
    "münchen": (48.1374, 11.5755),
    "berlin": (52.5200, 13.4050),
    "hamburg": (53.5511, 9.9937),
    "frankfurt": (50.1109, 8.6821),
    "koeln": (50.9375, 6.9603),
    "stuttgart": (48.7758, 9.1829),
}

SLACK_POST_URL = "https://slack.com/api/chat.postMessage"
SLACK_CHANNEL_ID = os.environ.get("SLACK_LOGISTICS_CHANNEL_ID") or "C07SJMXQWEA"


def _parse_center(value: str) -> tuple[float, float]:
    key = value.strip().lower()
    if key in _CITY_PRESETS:
        return _CITY_PRESETS[key]
    if "," in value:
        lat_str, lon_str = value.split(",", 1)
        return float(lat_str.strip()), float(lon_str.strip())
    raise ValueError(
        f"Unbekanntes Center '{value}'. Erlaubt: {', '.join(sorted(_CITY_PRESETS))} oder 'lat,lon'."
    )


def _write_csv(path: Path, candidates: list[WarehouseCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            [
                "rank",
                "name_or_operator",
                "area_sqm",
                "address",
                "city",
                "zip_code",
                "lat",
                "lon",
                "website",
                "phone",
                "email",
                "building",
                "osm_url",
                "maps_url",
            ]
        )
        for i, c in enumerate(candidates, 1):
            writer.writerow(
                [
                    i,
                    c.display_name,
                    int(c.area_sqm),
                    c.address_line,
                    c.city or "",
                    c.zip_code or "",
                    c.lat,
                    c.lon,
                    c.website or "",
                    c.phone or "",
                    c.email or "",
                    c.building or "",
                    c.osm_url,
                    c.maps_url,
                ]
            )


def _format_slack_summary(
    candidates: list[WarehouseCandidate],
    center_label: str,
    radius_km: int,
    min_area: int,
    top_n: int = 10,
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f":package: *Logistik-Kandidaten {center_label} (+{radius_km}km) – {today}*",
        f"Gefunden: {len(candidates)} Hallen ≥ {min_area} qm (OSM-Grundfläche).",
        "_Hinweis: OSM zeigt Gesamt-Grundfläche, nicht freie Mietfläche – bitte direkt anfragen._",
        "",
        f"*Top {min(top_n, len(candidates))}:*",
    ]
    for i, c in enumerate(candidates[:top_n], 1):
        addr = c.address_line or "Adresse unbekannt"
        link = f"<{c.maps_url}|Karte>"
        contact_bits: list[str] = []
        if c.website:
            contact_bits.append(f"<{c.website}|Web>")
        if c.phone:
            contact_bits.append(c.phone)
        contact_str = f" — {' · '.join(contact_bits)}" if contact_bits else ""
        lines.append(
            f"{i}. *{c.display_name}* — {int(c.area_sqm):,} qm — {addr} ({link}){contact_str}".replace(",", ".")
        )
    return "\n".join(lines)


def _send_slack(message: str) -> None:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        logger.warning("SLACK_BOT_TOKEN not set, skipping Slack notification")
        return
    try:
        response = httpx.post(
            SLACK_POST_URL,
            json={"channel": SLACK_CHANNEL_ID, "text": message},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            logger.error("Slack API error: %s", data.get("error", "unknown"))
        else:
            logger.info("Slack notification sent to %s", SLACK_CHANNEL_ID)
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Slack notification failed: %s", e)


def _print_summary(candidates: list[WarehouseCandidate], top_n: int = 15) -> None:
    logger.info("=" * 60)
    logger.info("LOGISTIK-KANDIDATEN: %d Treffer", len(candidates))
    logger.info("=" * 60)
    for i, c in enumerate(candidates[:top_n], 1):
        logger.info(
            "  %2d. %-40s  %7d qm  %s",
            i,
            c.display_name[:40],
            int(c.area_sqm),
            c.address_line or c.maps_url,
        )
    if len(candidates) > top_n:
        logger.info("  ... (+%d weitere in CSV)", len(candidates) - top_n)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Findet Logistik-Hallen via OpenStreetMap Overpass API."
    )
    parser.add_argument("--center", default="munich", help="Stadt-Preset oder 'lat,lon' (Default: munich)")
    parser.add_argument("--radius", type=int, default=40, help="Suchradius in km (Default: 40)")
    parser.add_argument("--min-area", type=int, default=5000, help="Mindestfläche pro Halle in qm (Default: 5000)")
    parser.add_argument(
        "--no-logistics-filter",
        action="store_true",
        help="Auch Industrie-Gebäude ohne Logistik-Hinweis aufnehmen",
    )
    parser.add_argument("--output-dir", default="out", help="CSV-Output-Verzeichnis (Default: out/)")
    parser.add_argument("--slack", action="store_true", help="Top-Treffer an Slack senden")
    parser.add_argument("--top", type=int, default=10, help="Anzahl Top-Treffer für Slack/Konsole")
    args = parser.parse_args(argv)

    try:
        lat, lon = _parse_center(args.center)
    except ValueError as e:
        parser.error(str(e))
        return 2

    radius_m = args.radius * 1000
    elements = query_warehouses(lat, lon, radius_m)
    candidates = parse_candidates(
        elements,
        min_area_sqm=args.min_area,
        require_logistics_hint=not args.no_logistics_filter,
    )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    center_slug = args.center.lower().replace(",", "_").replace(" ", "")
    output_path = Path(args.output_dir) / f"logistics_candidates_{center_slug}_{timestamp}.csv"
    _write_csv(output_path, candidates)
    logger.info("CSV geschrieben: %s", output_path)

    _print_summary(candidates, top_n=args.top)

    if args.slack and candidates:
        center_label = args.center.capitalize()
        msg = _format_slack_summary(candidates, center_label, args.radius, args.min_area, top_n=args.top)
        _send_slack(msg)

    return 0


if __name__ == "__main__":
    sys.exit(main())
