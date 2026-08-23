from __future__ import annotations

import logging
import os
import socket

import uvicorn

from . import config


def _lan_adresse() -> str | None:
    """Die IP, über die andere Geräte im Netz diesen Rechner erreichen.

    Der UDP-connect verschickt nichts – er lässt nur das Betriebssystem die
    Route wählen und verrät dabei die passende Quelladresse. 192.0.2.1 ist
    dokumentierter Testbereich (RFC 5737), also garantiert kein echtes Ziel."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("192.0.2.1", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def _zugangshinweis(port: int) -> list[str]:
    zeilen = [f"Auf diesem Rechner: http://localhost:{port}"]
    adresse = _lan_adresse()
    if adresse:
        zeilen.append(f"Für Kollegen im gleichen WLAN: http://{adresse}:{port}")
    else:
        zeilen.append("Eigene Netzwerkadresse nicht ermittelbar – IP manuell nachsehen.")
    zeilen.append("Der Bestand wird jetzt geladen (~2 Minuten). Bereit, sobald die Zeile "
                  "'Bestand im Cache: … vermietbare Hallen' erscheint.")
    return zeilen


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not os.environ.get("PROPSTACK_API_KEY"):
        raise SystemExit(
            "PROPSTACK_API_KEY ist nicht gesetzt – ohne den Key gibt es keinen Objektbestand.\n"
            "Start z.B. so:  PROPSTACK_API_KEY=xxx python -m hallentinder.main\n"
            "Den Key gibt es in Propstack unter Verwaltung -> API-Schlüssel."
        )
    log = logging.getLogger(__name__)
    if config.no_write():
        log.warning(
            "NO_WRITE=true (Default) – Anfragen werden NUR GELOGGT, es entstehen keine "
            "Kontakte und keine Deals in Propstack. Für den Echtbetrieb NO_WRITE=false setzen."
        )
    else:
        log.warning(
            "NO_WRITE=false – Anfragen erzeugen echte Kontakte und Deals in Propstack. "
            "Deals lassen sich per API nicht wieder löschen."
        )
    for zeile in _zugangshinweis(config.port()):
        log.info(zeile)

    uvicorn.run("hallentinder.api:app", host=config.host(), port=config.port(), log_level="info")


if __name__ == "__main__":
    main()
