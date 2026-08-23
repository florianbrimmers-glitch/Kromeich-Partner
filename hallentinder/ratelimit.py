from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from . import config

FENSTER_SEKUNDEN = 3600


class RateLimiter:
    """Einfaches Sliding-Window pro IP – die App ist öffentlich erreichbar."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._treffer: dict[str, deque[float]] = defaultdict(deque)

    def erlaubt(self, schluessel: str) -> bool:
        grenze = config.rate_limit_per_hour()
        if grenze <= 0:
            return True
        jetzt = time.time()
        with self._lock:
            eintraege = self._treffer[schluessel]
            while eintraege and jetzt - eintraege[0] > FENSTER_SEKUNDEN:
                eintraege.popleft()
            if len(eintraege) >= grenze:
                return False
            eintraege.append(jetzt)
            if len(self._treffer) > 10_000:
                self._aufraeumen(jetzt)
            return True

    def _aufraeumen(self, jetzt: float) -> None:
        leer = [k for k, v in self._treffer.items() if not v or jetzt - v[-1] > FENSTER_SEKUNDEN]
        for k in leer:
            del self._treffer[k]

    def reset(self) -> None:
        with self._lock:
            self._treffer.clear()


limiter = RateLimiter()
