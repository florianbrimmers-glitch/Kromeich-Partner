from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

from . import config
from .models import HallCard, SearchProfile, SwipeRichtung


@dataclass
class Session:
    token: str
    profil: SearchProfile
    karten: list[HallCard]
    radius_km: int
    erstellt_um: float
    cursor: int = 0
    likes: list[int] = field(default_factory=list)
    dislikes: list[int] = field(default_factory=list)
    lead_gesendet: bool = False

    def abgelaufen(self, jetzt: float) -> bool:
        return jetzt - self.erstellt_um > config.SESSION_TTL_SECONDS

    def karte(self, unit_id: int) -> HallCard | None:
        return next((k for k in self.karten if k.id == unit_id), None)

    def gelikte_karten(self) -> list[HallCard]:
        return [k for k in self.karten if k.id in self.likes]


class SessionStore:
    """In-Memory-Store mit TTL. Bewusst kein Persistenz-Layer: eine Session ist
    ein unverbindlicher Besuch, erst der Lead landet im CRM."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}

    def _aufraeumen(self, jetzt: float) -> None:
        abgelaufen = [t for t, s in self._sessions.items() if s.abgelaufen(jetzt)]
        for token in abgelaufen:
            del self._sessions[token]
        if len(self._sessions) > config.MAX_SESSIONS:
            ueberzaehlig = sorted(self._sessions.values(), key=lambda s: s.erstellt_um)
            for session in ueberzaehlig[: len(self._sessions) - config.MAX_SESSIONS]:
                self._sessions.pop(session.token, None)

    def anlegen(self, profil: SearchProfile, karten: list[HallCard], radius_km: int) -> Session:
        jetzt = time.time()
        session = Session(
            token=secrets.token_urlsafe(24),
            profil=profil,
            karten=karten,
            radius_km=radius_km,
            erstellt_um=jetzt,
        )
        with self._lock:
            self._aufraeumen(jetzt)
            self._sessions[session.token] = session
        return session

    def holen(self, token: str) -> Session | None:
        jetzt = time.time()
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if session.abgelaufen(jetzt):
                del self._sessions[token]
                return None
            return session

    def swipe(self, token: str, unit_id: int, richtung: SwipeRichtung) -> Session | None:
        """Swipe merken – idempotent, ein Objekt zählt höchstens einmal."""
        session = self.holen(token)
        if session is None:
            return None
        if session.karte(unit_id) is None:
            return session
        with self._lock:
            if unit_id in session.likes:
                session.likes.remove(unit_id)
            if unit_id in session.dislikes:
                session.dislikes.remove(unit_id)
            if richtung is SwipeRichtung.LIKE:
                session.likes.append(unit_id)
            else:
                session.dislikes.append(unit_id)
        return session

    def anzahl(self) -> int:
        with self._lock:
            return len(self._sessions)


store = SessionStore()
