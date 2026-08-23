from __future__ import annotations

import logging

import uvicorn

from . import config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
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
    uvicorn.run("hallentinder.api:app", host=config.host(), port=config.port(), log_level="info")


if __name__ == "__main__":
    main()
