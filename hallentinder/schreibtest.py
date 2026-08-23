"""Einmaliger Schreibtest der Deal-Anlage gegen die Live-Propstack-API.

Verifiziert das Payload-Schema von POST /client_properties – die einzige
Annahme, die sich lesend nicht klären lässt. Legt dafür einen deutlich
markierten Testkontakt und ein bis zwei Deals an und räumt anschließend
wieder auf.

Zwei Modi über HALLENTINDER_SCHREIBTEST:

    ja       – vollständiger Test (legt an, prüft, räumt auf)
    pruefen  – räumt nur nach: prüft, ob Datensätze aus einem früheren Lauf
               noch existieren, und versucht sie zu entfernen

Ohne diese Variable passiert nichts; bei NO_WRITE=true bricht der Lauf ab.

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


def deal_existiert(deal_id: int, property_id: int) -> dict | None:
    """Propstack kennt keinen GET auf einen einzelnen Deal – über die Liste
    der Deals des Objekts suchen.

    Bewusst nicht über propstack.get_open_deals: das filtert abgeschlossene
    Deals weg, und ein Testdatensatz mit Status 'lost' wäre dann unsichtbar,
    obwohl er noch existiert."""
    seite = 1
    while seite <= 10:
        antwort = propstack._request(
            "GET", "/client_properties",
            key=config.propstack_key_objekte(),
            params={"property_id": property_id, "page": seite, "per": 100},
        )
        eintraege = propstack._items(antwort.json())
        if not eintraege:
            return None
        for deal in eintraege:
            if deal.get("id") == deal_id:
                return deal
        if len(eintraege) < 100:
            return None
        seite += 1
    return None


def loeschversuche(deal_id: int) -> bool:
    """Der naheliegende Pfad liefert 404 – weitere Varianten durchprobieren."""
    pfade = [
        ("DELETE", f"/client_properties/{deal_id}"),
        ("DELETE", f"/deals/{deal_id}"),
    ]
    for methode, pfad in pfade:
        try:
            propstack._request(methode, pfad, key=config.propstack_key_objekte())
            print(f"    {methode} {pfad}: erfolgreich")
            return True
        except Exception as e:
            print(f"    {methode} {pfad}: {_fehlertext(e)}")
    return False


def nachraeumen() -> None:
    """Prüft Datensätze eines früheren Laufs und versucht sie zu entfernen.

    IDs über HALLENTINDER_ALTLASTEN als 'deal_id:property_id,…',
    Kontakt über HALLENTINDER_ALTKONTAKT."""
    _titel("Nachräumen eines früheren Schreibtests")

    roh = os.environ.get("HALLENTINDER_ALTLASTEN", "").strip()
    paare = []
    for eintrag in roh.split(","):
        if ":" in eintrag:
            deal, prop = eintrag.split(":", 1)
            paare.append((int(deal.strip()), int(prop.strip())))
    if not paare:
        print("Keine IDs übergeben (HALLENTINDER_ALTLASTEN).")

    offen = []
    for deal_id, property_id in paare:
        deal = deal_existiert(deal_id, property_id)
        if deal is None:
            print(f"\n  Deal {deal_id} (Objekt {property_id}): existiert nicht mehr –")
            print("    beim Löschen des Testkontakts mit entfernt worden.")
            continue
        print(f"\n  Deal {deal_id} (Objekt {property_id}): EXISTIERT NOCH")
        print(f"    Status/Kategorie: {deal.get('category')!r}, Kontakt: {deal.get('client_id')}")
        if not loeschversuche(deal_id):
            offen.append((deal_id, property_id))

    kontakt = os.environ.get("HALLENTINDER_ALTKONTAKT", "").strip()
    if kontakt:
        try:
            antwort = propstack._request("GET", f"/contacts/{kontakt}", key=config.propstack_key())
            print(f"\n  Testkontakt {kontakt}: existiert noch – {antwort.json().get('name')!r}")
        except Exception as e:
            print(f"\n  Testkontakt {kontakt}: nicht mehr abrufbar ({_fehlertext(e)[:60]}) – gelöscht.")

    _titel("Ergebnis")
    if offen:
        print("Diese Testdatensätze konnten NICHT per API entfernt werden und müssen")
        print("in Propstack von Hand gelöscht werden:")
        for deal_id, property_id in offen:
            print(f"  Deal {deal_id} am Objekt {property_id}")
    else:
        print("Keine Testdatensätze mehr vorhanden.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    modus = os.environ.get("HALLENTINDER_SCHREIBTEST", "").lower()
    if modus not in ("ja", "pruefen"):
        raise SystemExit("Abbruch: HALLENTINDER_SCHREIBTEST=ja oder =pruefen setzen.")
    if not os.environ.get("PROPSTACK_API_KEY"):
        raise SystemExit("FEHLER: PROPSTACK_API_KEY nicht gesetzt.")
    if config.no_write():
        raise SystemExit("Abbruch: NO_WRITE=true – dann gäbe es nichts zu verifizieren.")

    if modus == "pruefen":
        nachraeumen()
        return

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
