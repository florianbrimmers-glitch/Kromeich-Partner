from __future__ import annotations

import logging

import uvicorn

from . import config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if config.no_write():
        logging.getLogger(__name__).warning("NO_WRITE=true – es werden keine Daten nach Propstack geschrieben")
    uvicorn.run("hallentinder.api:app", host=config.host(), port=config.port(), log_level="info")


if __name__ == "__main__":
    main()
