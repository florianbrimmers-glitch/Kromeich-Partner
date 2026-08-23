from __future__ import annotations

import threading
import time

import pytest

from hallentinder import catalog, config

from .fixtures import BESTAND


@pytest.fixture
def cache(monkeypatch):
    aufrufe = []

    def fake_list_units(per=100):
        aufrufe.append(time.time())
        return BESTAND

    monkeypatch.setattr(catalog.propstack, "list_units", fake_list_units)
    return catalog._Cache(), aufrufe


def test_erster_abruf_laedt_zweiter_kommt_aus_dem_cache(cache):
    c, aufrufe = cache
    assert len(c.get()) == len(catalog.build_cards(BESTAND))
    c.get()
    c.get()
    assert len(aufrufe) == 1


def test_veralteter_cache_liefert_sofort_und_laedt_im_hintergrund(cache, monkeypatch):
    """Der volle Abruf dauert live ~2 Minuten – niemand darf darauf warten."""
    c, aufrufe = cache
    c.get()
    monkeypatch.setattr(config, "cache_ttl", lambda: 0)

    start = time.time()
    karten = c.get()
    assert time.time() - start < 0.5, "veralteter Stand muss sofort zurückkommen"
    assert karten, "es wird der alte Stand ausgeliefert, keine leere Liste"

    for _ in range(50):
        if len(aufrufe) > 1:
            break
        time.sleep(0.02)
    assert len(aufrufe) == 2, "Hintergrund-Aktualisierung wurde nicht angestoßen"


def test_hintergrundfehler_laesst_den_alten_stand_stehen(cache, monkeypatch):
    c, _ = cache
    c.get()
    monkeypatch.setattr(config, "cache_ttl", lambda: 0)

    def kaputt(per=100):
        raise RuntimeError("Propstack down")

    monkeypatch.setattr(catalog.propstack, "list_units", kaputt)
    assert c.get(), "trotz Fehler beim Nachladen bleibt der alte Bestand nutzbar"
    time.sleep(0.1)
    assert c.get(), "auch beim nächsten Aufruf"


def test_ohne_bestand_wird_der_fehler_durchgereicht(monkeypatch):
    def kaputt(per=100):
        raise RuntimeError("Propstack down")

    monkeypatch.setattr(catalog.propstack, "list_units", kaputt)
    with pytest.raises(RuntimeError):
        catalog._Cache().get()


def test_parallele_abrufe_loesen_nur_eine_aktualisierung_aus(monkeypatch):
    """Während ein Nachladen läuft, darf kein zweites starten – sonst prasseln
    bei jedem Request 23 Propstack-Seitenabrufe los."""
    c = catalog._Cache()
    aufrufe = []
    freigabe = threading.Event()

    def langsam(per=100):
        aufrufe.append(1)
        freigabe.wait(timeout=5)
        return BESTAND

    monkeypatch.setattr(catalog.propstack, "list_units", langsam)
    freigabe.set()
    c.get()                       # erster, blockierender Ladevorgang
    freigabe.clear()
    monkeypatch.setattr(config, "cache_ttl", lambda: 0)

    threads = [threading.Thread(target=c.get) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2)

    assert len(aufrufe) == 2, f"erwartet: ein laufendes Nachladen, tatsächlich {len(aufrufe) - 1}"
    freigabe.set()
