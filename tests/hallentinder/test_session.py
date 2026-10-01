from __future__ import annotations

from hallentinder import catalog, config
from hallentinder.models import SearchProfile, SwipeRichtung
from hallentinder.session import SessionStore

from .fixtures import BESTAND


def profil() -> SearchProfile:
    return SearchProfile(ort="49076", flaeche_min=0, flaeche_max=0)


def test_swipe_ist_idempotent_und_umkehrbar():
    store = SessionStore()
    session = store.anlegen(profil(), catalog.build_cards(BESTAND), 50)
    store.swipe(session.token, 1, SwipeRichtung.LIKE)
    store.swipe(session.token, 1, SwipeRichtung.LIKE)
    assert session.likes == [1]
    store.swipe(session.token, 1, SwipeRichtung.DISLIKE)
    assert session.likes == []
    assert session.dislikes == [1]


def test_fremde_unit_id_wird_ignoriert():
    store = SessionStore()
    session = store.anlegen(profil(), catalog.build_cards(BESTAND), 50)
    store.swipe(session.token, 999999, SwipeRichtung.LIKE)
    assert session.likes == []


def test_abgelaufene_session_wird_verworfen(monkeypatch):
    store = SessionStore()
    session = store.anlegen(profil(), catalog.build_cards(BESTAND), 50)
    session.erstellt_um -= config.SESSION_TTL_SECONDS + 1
    assert store.holen(session.token) is None
    assert store.anzahl() == 0


def test_unbekanntes_token():
    assert SessionStore().holen("gibtesnicht") is None


def test_gelikte_karten_in_deck_reihenfolge():
    store = SessionStore()
    session = store.anlegen(profil(), catalog.build_cards(BESTAND), 50)
    store.swipe(session.token, 3, SwipeRichtung.LIKE)
    store.swipe(session.token, 1, SwipeRichtung.LIKE)
    assert [k.id for k in session.gelikte_karten()] == [1, 3]
