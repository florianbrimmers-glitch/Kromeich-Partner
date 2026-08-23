"""Einmaliger Schreibtest der Deal-Anlage gegen die Live-Propstack-API.

Verifiziert das Payload-Schema von POST /client_properties – die einzige
Annahme, die sich lesend nicht klären lässt. Legt dafür einen deutlich
markierten Testkontakt und ein bis zwei Deals an und räumt anschließend
wieder auf.

Läuft nur mit HALLENTINDER_SCHREIBTEST=ja, damit er nicht versehentlich
gestartet wird. NO_WRITE muss aus sein – sonst gäbe es nichts zu prüfen.

    HALLENTINDER_SCHREIBTEST=ja PROPSTACK_API_KEY=xxx python -m hallentinder.schreibtest
"""
from __future__ import annotations

import logging
import os
from datetime import date

import httpx

from . import catalog, config, propstack

logger = logging.getLogger("hallentinder.schreibtest")

TEST_EMAIL = "hallentinder-schreibtest@kromeichpartner.de"
TEST_NACHNAME = "TESTLAUF Hallentinder"
TEST_NOTIZ = (
    "AUTOMATISCHER TESTLAUF der Hallentinder-Anbindung – keine echte Anfrage. "
    "Dieser Datensatz wird direkt im Anschluss wieder gelöscht."
)

# Reihenfolge der Payload-Varianten: die erste, die durchgeht, ist die richtige.
def varianten(client_id: int, property_id: int) -> list[tuple[str, dict]]:
    return [
        ("client_property-Hülle mit note",
         {"client_property": {"client_id": client_id, "property_id": property_id, "note": TEST_NOTIZ}}),
        ("client_property-Hülle ohne note",
         {"client_property": {"client_id": client_id, "property_id": property_id}}),
        ("flach mit note",
         {"client_id": client_id, "property_id": property_id, "note": TEST_NOTIZ}),
        ("flach ohne note",
         {"client_id": client_id, "property_id": property_id}),
    ]


def _titel(text: str) -> None:
    print(f"\n{'=' * 68}\n{text}\n{'=' * 68}")


def _fehlertext(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code} – {e.response.text[:300]}"
    return str(e)


def testkontakt_anlegen() -> int:
    _titel("1. Testkontakt")
    vorhanden = propstack.find_contact_by_email(TEST_EMAIL)
    if vorhanden:
        print(f"Testkontakt existiert bereits: {vorhanden} (aus einem früheren Lauf)")
        return vorhanden

    antwort = propstack._request(
        "POST", "/contacts",
        key=config.propstack_key(),
        json={"client": {
            "last_name": TEST_NACHNAME,
            "first_name": "Bitte loeschen",
            "email": TEST_EMAIL,
            "description": f"Automatischer Schreibtest der Hallentinder-Anbindung vom {date.today().isoformat()}",
        }},
    )
    kontakt_id = antwort.json().get("id")
    print(f"Testkontakt angelegt: {kontakt_id}")
    return int(kontakt_id)


def schema_ermitteln(kontakt_id: int, unit_ids: list[int]) -> tuple[str | None, list[int]]:
    _titel("2. Payload-Schema von POST /client_properties")
    treffer: str | None = None
    angelegt: list[int] = []

    for unit_id in unit_ids:
        if treffer:
            # Schema steht – zweiten Deal direkt damit anlegen, als Gegenprobe
            payload = dict(varianten(kontakt_id, unit_id))[treffer]
            try:
                antwort = propstack._request(
                    "POST", "/client_properties", key=config.propstack_key_objekte(), json=payload
                )
                deal_id = antwort.json().get("id")
                angelegt.append(int(deal_id))
                print(f"  Gegenprobe mit Objekt {unit_id}: erfolgreich (Deal {deal_id})")
            except Exception as e:
                print(f"  Gegenprobe mit Objekt {unit_id}: FEHLGESCHLAGEN – {_fehlertext(e)}")
            continue

        print(f"\nObjekt {unit_id} – Varianten der Reihe nach:")
        for label, payload in varianten(kontakt_id, unit_id):
            try:
                antwort = propstack._request(
                    "POST", "/client_properties", key=config.propstack_key_objekte(), json=payload
                )
            except Exception as e:
                print(f"  [ ] {label:<34} {_fehlertext(e)}")
                continue

            daten = antwort.json()
            deal_id = daten.get("id")
            print(f"  [x] {label:<34} HTTP {antwort.status_code}, Deal-ID {deal_id}")
            print(f"      Antwortfelder: {', '.join(sorted(daten)[:20]) if isinstance(daten, dict) else type(daten)}")
            treffer = label
            if deal_id:
                angelegt.append(int(deal_id))
            break

    return treffer, angelegt


def aufraeumen(kontakt_id: int, deal_ids: list[int]) -> None:
    _titel("3. Aufräumen")
    for deal_id in deal_ids:
        try:
            propstack._request("DELETE", f"/client_properties/{deal_id}", key=config.propstack_key_objekte())
            print(f"  Deal {deal_id} gelöscht")
        except Exception as e:
            print(f"  Deal {deal_id} NICHT gelöscht – {_fehlertext(e)}")

    try:
        propstack._request("DELETE", f"/contacts/{kontakt_id}", key=config.propstack_key())
        print(f"  Testkontakt {kontakt_id} gelöscht")
    except Exception as e:
        print(f"  Testkontakt {kontakt_id} NICHT gelöscht – {_fehlertext(e)}")
        print(f"  Bitte manuell entfernen: {TEST_EMAIL}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if os.environ.get("HALLENTINDER_SCHREIBTEST", "").lower() != "ja":
        raise SystemExit("Abbruch: HALLENTINDER_SCHREIBTEST=ja setzen (dieser Lauf schreibt in Propstack).")
    if not os.environ.get("PROPSTACK_API_KEY"):
        raise SystemExit("FEHLER: PROPSTACK_API_KEY nicht gesetzt.")
    if config.no_write():
        raise SystemExit("Abbruch: NO_WRITE=true – dann gäbe es nichts zu verifizieren.")

    print("SCHREIBTEST – legt einen markierten Testkontakt und Deals an und löscht sie wieder.\n")

    karten = catalog.cards()
    if len(karten) < 2:
        raise SystemExit("Abbruch: zu wenige Objekte im Bestand.")
    unit_ids = [karten[0].id, karten[1].id]
    print(f"Verwendete Objekte: {unit_ids}")

    kontakt_id = testkontakt_anlegen()
    treffer, deal_ids = schema_ermitteln(kontakt_id, unit_ids)
    aufraeumen(kontakt_id, deal_ids)

    _titel("Ergebnis")
    if treffer:
        print(f"Funktionierendes Schema: {treffer}")
        erwartet = "client_property-Hülle mit note"
        if treffer == erwartet:
            print("Das entspricht dem, was propstack.create_deal sendet – keine Anpassung nötig.")
        else:
            print(f"ABWEICHUNG: create_deal sendet '{erwartet}' und muss angepasst werden.")
    else:
        print("KEINE Variante hat funktioniert – die Fehlermeldungen oben zeigen, woran es liegt.")


if __name__ == "__main__":
    main()
