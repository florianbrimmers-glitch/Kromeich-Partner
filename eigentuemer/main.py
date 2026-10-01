from __future__ import annotations

import logging

import uvicorn

from . import config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger(__name__)

    log.info("Daten liegen in: %s", config.daten_verzeichnis())
    log.info("Objekt einstellen:  http://localhost:%d/", config.port())
    log.info("Interne Prüfung:    http://localhost:%d/pruefung.html", config.port())
    if config.passwort_wurde_erzeugt():
        log.warning(
            "Zugang zur Prüfansicht – Benutzername frei wählbar (er landet im Protokoll), "
            "Passwort: %s", config.pruef_passwort(),
        )
        log.warning("Dauerhaft eigenes Passwort setzen: EIGENTUEMER_PRUEF_PASSWORT=...")

    uvicorn.run("eigentuemer.api:app", host=config.host(), port=config.port(), log_level="info")


if __name__ == "__main__":
    main()
