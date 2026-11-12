"""Erzeugt test/dashboard-golden.fixture.json – den Abgleich von dashboard_daten mit dem bisherigen Python-Export.

Der Test test/dashboard-golden.test.ts spielt dem Connector die hier aufgezeichneten Propstack-Antworten vor und
vergleicht jedes Dokument mit dem, was der echte Export daraus macht: Es läuft weekly_report.dashboard_export.main()
selbst, nur das Netz (propstack._request) und die Uhr sind ersetzt. Aufgezeichnet werden auch die Anfragen – der
Connector muss dieselben Abfragen stellen wie der Export (gleiche Parameter, gleiche Seiten).

Die Daten sind erfunden (keine echten Objekte), decken aber die Sonderfälle ab: Fenstergrenzen auf die Millisekunde,
Wochenwechsel in Berliner Zeit, Ende und Beginn der Sommerzeit, Jahreswechsel (KW53), Custom-Field-Objekte,
fehlende Titel, gelöschtes Projekt, Aufgaben-Arten, mehrere Prüfer, Seiten exakt an der Seitengrenze.

    python3 propstack-mcp/test/dashboard-golden.erzeugen.py      (im Wurzelverzeichnis des Repos)
"""
from __future__ import annotations

import json
import os
import pathlib
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HIER = pathlib.Path(__file__).resolve()
WURZEL = HIER.parents[2]
sys.path.insert(0, str(WURZEL))
os.environ["PROPSTACK_API_KEY"] = "test"
os.environ.pop("PROPSTACK_KEY_OBJEKTE", None)
os.environ.pop("PROPSTACK_KEY_TASKS", None)

from weekly_report import dashboard_export, propstack  # noqa: E402

BERLIN = ZoneInfo("Europe/Berlin")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
SEITE = 7  # Seitengröße im Test – der Connector bekommt dieselbe, damit die Anfragen übereinstimmen


def ms(zeitpunkt: datetime) -> int:
    return (zeitpunkt - EPOCH) // timedelta(milliseconds=1)


def propstack_zeit(zeitpunkt: datetime) -> str:
    """Schreibweise der Propstack-API: Berliner Zeit mit Millisekunden."""
    return zeitpunkt.astimezone(BERLIN).isoformat(timespec="milliseconds")


def instant(iso: str | None) -> float:
    return datetime.fromisoformat(iso).timestamp() if iso else float("-inf")


# ---------- erfundene Daten ----------

def einheit(uid: int, created_at: str | None, projekt, form: int) -> dict:
    ort = f"Musterstadt {uid % 13}"
    titel = f"Logistikhalle in ({uid % 90 + 10}) {ort} – Halle {uid % 7 + 1}"
    row: dict = {"id": uid, "created_at": created_at, "project_id": projekt, "unit_id": f"U{uid % 9}", "rs_type": "INDUSTRY"}
    if form == 0:
        row.update(title=titel, city=ort, property_space_value=1000.0 + uid % 5000, marketing_type="RENT")
    elif form == 1:
        row.update(
            title={"label": "Überschrift", "value": titel},
            city={"label": "Stadt", "value": ort},
            property_space_value=2500 + uid % 300,
            marketing_type={"label": "Vermarktungsart", "value": "RENT", "pretty_value": "Miete"},
        )
    elif form == 2:
        row.update(title=None, name=f"Halle {uid % 40}", property_space_value="4200.5", marketing_type="BUY")
    elif form == 3:
        row.update(title="", name=None, address=f"Musterweg {uid % 99 + 1}, 12345 {ort}, Deutschland", property_space_value="7,25")
    elif form == 4:
        row.update(property_space_value=None, marketing_type=None, city=None)
    else:
        row.update(
            title={"label": "Überschrift", "value": None},
            name={"label": "Name", "value": f"Unit {uid % 20}"},
            property_space_value={"label": "Fläche", "value": "1500"},
            project_id=str(projekt) if projekt else None,
        )
    return row


def projekt(pid: int, form: int) -> dict:
    if form == 0:
        return {"id": pid, "title": f"Logistikpark ({pid % 90 + 10}) Beispielort", "name": f"Park {pid}", "address": "Parkweg 1"}
    if form == 1:
        return {"id": pid, "title": {"label": "Überschrift", "value": f"Gewerbepark Nord {pid % 50}"}}
    if form == 2:
        return {"id": pid, "title": None, "name": f"Projektname {pid}"}
    if form == 3:
        return {"id": pid, "title": "", "name": "", "address": f"Industriestraße {pid % 80}, 40000 Ort"}
    return {"id": pid}


AUFGABEN_TITEL = [
    "Pruefung Panattoni Welle 3: Park Rheine",
    "Prüfung: Logistikfläche in (85) Kirchheim",
    "Pruefung: Logistikhalle in (45) Waltrop",
    "Newsletter-Vermietung prüfen: Bauer Property",
    "Objekt pruefen: Halle 7",
    'Gesuch "FIRMA" "Kontakt" | "Größe"',
    None,
    "   ",
    ": nur Doppelpunkt",
    "Pruefungen: Mehrzahl bleibt",
    "Ueberpruefung: bleibt",
    "Flächenupdate abgleichen: Panattoni: Teil 2",
    {"label": "Titel", "value": "Pruefung GARBE Welle 4: Hamburg"},
    "  Prüfung Mileway  : Köln ",
    "Pruefung_intern: Unterstrich zählt als Wortzeichen",
    "Überpruefen: Umlaut davor",
]


def aufgabe(tid: int, broker: int, titel, done, angelegt: str | None, geaendert: str | None, bezug: int) -> dict:
    row: dict = {"id": tid, "title": titel, "done": done, "broker_id": broker, "original_created_at": angelegt, "updated_at": geaendert, "item_type": "reminder"}
    if bezug == 0:
        row.update(property_names=[f"Unit {tid % 9}.1"], project_names=[])
    elif bezug == 1:
        row.update(property_names=[], project_names=[f"Park {tid % 11}"])
    elif bezug == 2:
        row.update(property_names=["", None, "Echte Einheit"], project_names=["Projekt daneben"])
    elif bezug == 3:
        row.update(property_names="kein Array", project_names=["Nur Projekt"])
    return row


def datensatz(since: datetime, until: datetime, broker_ids: list[int], rng: random.Random, *, zufall: int, kanten: list[str], projekte: list[int], aufgaben_je_broker: list[int]) -> dict:
    naechste = iter(range(6_000_000 + rng.randrange(1000), 9_000_000))
    einheiten: list[dict] = []

    def neu(created_at: str | None, pid=None, form=None):
        uid = next(naechste)
        einheiten.append(einheit(uid, created_at, pid, rng.randrange(6) if form is None else form))

    wahl = lambda: rng.choice(projekte) if projekte and rng.random() < 0.7 else None  # noqa: E731
    # Fenstergrenzen auf die Millisekunde: since ≤ angelegt < until
    grenzen = [since, since - timedelta(milliseconds=1), until, until - timedelta(milliseconds=1)]
    for zeitpunkt in grenzen:
        neu(propstack_zeit(zeitpunkt), wahl())
    for iso in kanten:
        neu(iso, wahl())
    spanne = (until - since) + timedelta(days=4)
    for _ in range(zufall):
        neu(propstack_zeit(since - timedelta(days=3) + spanne * rng.random()), wahl())
    # gleicher Zeitstempel zweimal (Reihenfolge bei Gleichstand) und eine Einheit ohne Anlagedatum
    doppelt = propstack_zeit(since + timedelta(days=5, hours=3))
    neu(doppelt, wahl(), 0)
    neu(doppelt, wahl(), 1)
    neu(None, wahl(), 0)
    # jedes Projekt hat mindestens eine Einheit im Fenster und eine frühere außerhalb (datiert das Projekt)
    alt: list[dict] = []
    for index, pid in enumerate(projekte):
        neu(propstack_zeit(since + timedelta(days=1 + index, minutes=index)), pid, index % 6)
        if index % 3 != 2:
            alt.append(einheit(5_000_000 + index, propstack_zeit(since - timedelta(days=200 + 17 * index, seconds=index)), pid, 0))

    vorhandene = [pid for index, pid in enumerate(projekte) if index != 1]  # Projekt an Position 1 ist gelöscht
    projektliste = [projekt(pid, index % 5) for index, pid in enumerate(vorhandene)]
    projektliste += [projekt(700_000 + i, i % 5) for i in range(9)]  # unbeteiligte Projekte
    rng.shuffle(projektliste)

    aufgaben: dict[int, list[dict]] = {}
    for broker, anzahl in zip(broker_ids, aufgaben_je_broker):
        zeilen = []
        feste = [
            (None, propstack_zeit(since - timedelta(days=400)), propstack_zeit(since - timedelta(days=400))),      # offen, uralt
            (True, propstack_zeit(since - timedelta(days=30)), propstack_zeit(since - timedelta(days=2))),          # erledigt, alt
            (True, propstack_zeit(since - timedelta(days=30)), propstack_zeit(since)),                              # erledigt genau am Fensterbeginn
            (True, propstack_zeit(since - timedelta(days=30)), propstack_zeit(since - timedelta(milliseconds=1))),  # 1 ms davor
            (True, propstack_zeit(since), None),                                                                    # angelegt am Fensterbeginn
            (True, None, None),                                                                                     # erledigt, ohne Zeitstempel
            (False, propstack_zeit(since - timedelta(days=90)), propstack_zeit(since - timedelta(days=80))),        # false = offen
            (None, None, propstack_zeit(since + timedelta(days=3))),                                                # offen ohne Anlagedatum
            (1, propstack_zeit(since + timedelta(days=2)), propstack_zeit(since + timedelta(days=4))),              # 1 = erledigt
            (0, propstack_zeit(since + timedelta(days=2)), propstack_zeit(since + timedelta(days=4))),              # gleicher Zeitstempel, andere ID
        ]
        for index in range(anzahl):
            if index < len(feste):
                done, angelegt, geaendert = feste[index]
            else:
                start = since - timedelta(days=60) + (until - since + timedelta(days=60)) * rng.random()
                done = rng.choice([True, True, None, False])
                angelegt = propstack_zeit(start)
                geaendert = propstack_zeit(start + timedelta(days=rng.randrange(0, 20), minutes=rng.randrange(600)))
            tid = 440_000_000 + broker % 1000 * 1000 + index * 7 + rng.randrange(5)
            zeilen.append(aufgabe(tid, broker, AUFGABEN_TITEL[index % len(AUFGABEN_TITEL)], done, angelegt, geaendert, index % 5))
        rng.shuffle(zeilen)
        aufgaben[broker] = zeilen

    rng.shuffle(einheiten)
    return {"einheiten": einheiten, "alt": alt, "projekte": projektliste, "aufgaben": aufgaben, "ohne_beginn": projekte[2] if len(projekte) > 2 else None}


# ---------- nachgestellte Propstack-API ----------

def server(daten: dict, mitschnitt: list):
    def berlin_tag(iso: str) -> str:
        return datetime.fromisoformat(iso).astimezone(BERLIN).strftime("%Y-%m-%d")

    def antwort(pfad: str, params: dict):
        per, page = int(params.get("per", 25)), int(params.get("page", 1))
        if pfad == "/units" and "project_id" in params:
            pid = int(params["project_id"])
            if pid == daten["ohne_beginn"]:
                zeilen = []
            else:
                alle = daten["einheiten"] + daten["alt"]
                zeilen = sorted((u for u in alle if u.get("project_id") and int(u["project_id"]) == pid and u["created_at"]), key=lambda u: instant(u["created_at"]))
            return {"data": zeilen[(page - 1) * per: page * per]}
        if pfad == "/units":
            von, bis = params["created_at_from"], params["created_at_to"]
            zeilen = sorted(
                (u for u in daten["einheiten"] if u["created_at"] is None or von <= berlin_tag(u["created_at"]) <= bis),
                key=lambda u: -u["id"],
            )
            return {"data": zeilen[(page - 1) * per: page * per], "meta": {"total_count": len(zeilen)}}
        if pfad == "/projects":
            return daten["projekte"][(page - 1) * per: page * per]  # nackte Liste wie die echte API
        if pfad == "/activities":
            assert params["item_type"] == "reminder" and params["sort_by"] == "updated_at" and params["order"] == "desc"
            zeilen = sorted(daten["aufgaben"][int(params["broker_id"])], key=lambda t: -instant(t["updated_at"]))
            return {"data": zeilen[(page - 1) * per: page * per], "meta": {"total_count": len(zeilen)}}
        raise AssertionError(pfad)

    class Antwort:
        def __init__(self, inhalt):
            self._inhalt = inhalt

        def json(self):
            return self._inhalt

    def request(method: str, path: str, *, key: str, params: dict | None = None):
        assert method == "GET" and key == "test"
        inhalt = antwort(path, params or {})
        mitschnitt.append({"pfad": path, "params": {k: str(v) for k, v in (params or {}).items()}, "antwort": inhalt})
        return Antwort(inhalt)

    return request


def laufe(name: str, until: datetime, tage: int, broker_ids: list[int], rng: random.Random, **optionen) -> dict:
    since = until - timedelta(days=tage)
    daten = datensatz(since, until, broker_ids, rng, **optionen)
    mitschnitt: list = []

    class FesteUhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return until

    original = (propstack._request, propstack.PAGE_SIZE, propstack.time.sleep, dashboard_export.datetime, sys.argv)
    propstack._request = server(daten, mitschnitt)
    propstack.PAGE_SIZE = SEITE
    propstack.time.sleep = lambda _sekunden: None
    dashboard_export.datetime = FesteUhr
    os.environ["PRUEFER_BROKER_IDS"] = ",".join(str(b) for b in broker_ids)
    try:
        with tempfile.TemporaryDirectory() as ziel:
            sys.argv = ["dashboard_export", "--out", ziel, "--tage", str(tage)]
            assert dashboard_export.main() == 0
            dokumente = {
                str(pfad.relative_to(ziel))[: -len(".json")]: json.loads(pfad.read_text(encoding="utf-8"))
                for pfad in sorted(pathlib.Path(ziel).rglob("*.json"))
            }
    finally:
        propstack._request, propstack.PAGE_SIZE, propstack.time.sleep, dashboard_export.datetime, sys.argv = original
    stand = dokumente["meta/stand"]
    print(f"{name}: {len(mitschnitt)} Anfragen, {len(dokumente)} Dokumente – {stand['anzahl_einheiten']} Einheiten, {stand['anzahl_projekte']} Projekte, "
          f"{stand['anzahl_aufgaben']} Aufgaben ({stand['anzahl_offen']} offen), Wochen {stand['wochen'][0] if stand['wochen'] else '–'} … {stand['wochen'][-1] if stand['wochen'] else '–'}")
    return {"name": name, "until_ms": ms(until), "tage": tage, "broker_ids": broker_ids, "anfragen": mitschnitt, "dokumente": dokumente}


def zeit_tabelle() -> dict:
    wochen = [
        "2026-09-28T00:00:00.000+02:00", "2026-09-27T23:59:59.999+02:00", "2026-09-27T22:30:00.000+00:00", "2026-09-27T21:59:59.999+00:00",
        "2027-01-01T00:00:00.000+01:00", "2027-01-03T23:59:59.999+01:00", "2027-01-04T00:00:00.000+01:00", "2026-12-28T00:00:00.000+01:00",
        "2026-12-27T23:00:00.000+00:00", "2026-01-01T12:00:00.000+01:00", "2025-12-29T00:00:00.000+01:00", "2024-12-30T08:00:00.000+01:00",
        "2026-10-25T02:30:00.000+02:00", "2026-10-25T02:30:00.000+01:00", "2026-03-29T03:00:00.000+02:00", "2026-03-29T01:59:59.999+01:00",
        "2026-08-19T11:29:56.983+02:00", "2028-12-31T23:59:59.000+01:00", "2029-01-01T00:00:00.000+01:00", "2032-01-01T10:00:00.000+01:00",
    ]
    iso = [
        "2026-08-19T11:29:56.983+02:00", "2026-08-19T11:29:56.000+02:00", "2025-03-19T09:52:39.301+01:00", "2026-11-11T15:39:39.284+01:00",
        "2026-08-19T11:29:56+02:00", "2026-08-19T11:29:56.1+02:00", "2026-08-19T11:29:56.123456+02:00", "2026-08-19T09:29:56.050+00:00",
        "2026-08-19T09:29:56.983Z", "2026-08-19 11:29:56.983+02:00", "2026-08-19T11:29+02:00", "2026-08-19T11:29:56.983+0200",
    ]
    fenster = []
    for jahr, monat, tag, stunde, minute, sekunde, mikro, tage in [
        (2026, 11, 12, 9, 47, 42, 960000, 91),   # über das Ende der Sommerzeit
        (2027, 1, 15, 0, 30, 0, 0, 28),          # über den Jahreswechsel, ohne Sekundenbruchteil
        (2026, 6, 28, 2, 30, 0, 500000, 91),     # since fällt in die Lücke am Beginn der Sommerzeit (29.03. 02:30 gibt es nicht)
        (2027, 1, 24, 2, 30, 0, 0, 91),          # since fällt in die doppelte Stunde am Ende der Sommerzeit
        (2026, 3, 29, 3, 0, 0, 7000, 1),         # ein Tag zurück über den Beginn der Sommerzeit
        (2026, 10, 25, 2, 59, 59, 999000, 1),    # ein Tag zurück, erste der beiden 02:59
        (2026, 3, 1, 0, 0, 0, 0, 91),            # über den Jahreswechsel zurück
        (2028, 2, 29, 23, 59, 59, 1000, 60),     # Schalttag
        (2026, 5, 15, 12, 0, 0, 0, 7),
        (2026, 1, 1, 0, 0, 0, 0, 1),
    ]:
        until = datetime(jahr, monat, tag, stunde, minute, sekunde, mikro, tzinfo=BERLIN)
        since = until - timedelta(days=tage)
        fenster.append({
            "until_ms": ms(until), "tage": tage,
            "until_iso": until.isoformat(), "since_iso": since.isoformat(), "since_ms": ms(since),
            "created_at_from": (since - timedelta(days=1)).strftime("%Y-%m-%d"),
            "created_at_to": (until + timedelta(days=1)).strftime("%Y-%m-%d"),
        })
    return {
        "wochen": [[text, dashboard_export.wochen_schluessel(datetime.fromisoformat(text))] for text in wochen],
        "isoformat": [[text, datetime.fromisoformat(text).isoformat()] for text in iso],
        "fenster": fenster,
        "aufgaben_art": [[titel, dashboard_export.aufgaben_art(propstack._scalar(titel))] for titel in AUFGABEN_TITEL],
    }


def main() -> None:
    rng = random.Random(20261112)
    szenarien = [
        laufe(
            "Sommerzeit-Ende im Fenster, ein Prüfer", datetime(2026, 11, 12, 9, 47, 42, 960000, tzinfo=BERLIN), 91, [254958], rng,
            zufall=34, projekte=[590101, 590102, 590103, 590104, 590105, 590106, 590107, 590108],
            aufgaben_je_broker=[33],
            kanten=["2026-09-27T23:59:59.999+02:00", "2026-09-28T00:00:00.000+02:00", "2026-10-25T02:30:00.000+02:00", "2026-10-25T02:30:00.000+01:00"],
        ),
        laufe(
            "Jahreswechsel, zwei Prüfer, Seite exakt voll", datetime(2027, 1, 15, 0, 30, 0, tzinfo=BERLIN), 28, [254958, 387451], rng,
            zufall=6, projekte=[601001, 601002, 601003], aufgaben_je_broker=[14, 5],
            kanten=["2026-12-31T23:59:59.500+01:00", "2027-01-01T00:00:00.000+01:00", "2027-01-03T23:59:00.000+01:00", "2027-01-04T00:00:00.000+01:00", "2026-12-27T23:30:00.000+01:00"],
        ),
        laufe(
            "Fensterbeginn in der Lücke am Beginn der Sommerzeit", datetime(2026, 6, 28, 2, 30, 0, 500000, tzinfo=BERLIN), 91, [254958], rng,
            zufall=3, projekte=[610001], aufgaben_je_broker=[3],
            kanten=["2026-03-29T03:30:00.500+02:00", "2026-03-29T03:30:00.499+02:00", "2026-03-29T01:59:59.999+01:00"],
        ),
        laufe(
            "Fensterbeginn in der doppelten Stunde, keine Projekte", datetime(2027, 1, 24, 2, 30, 0, tzinfo=BERLIN), 91, [254958], rng,
            zufall=3, projekte=[], aufgaben_je_broker=[2],
            kanten=["2026-10-25T02:30:00.000+02:00", "2026-10-25T02:29:59.999+02:00", "2026-10-25T02:30:00.000+01:00"],
        ),
    ]
    ausgabe = {"seite": SEITE, "szenarien": szenarien, "zeit": zeit_tabelle()}
    ziel = HIER.with_name("dashboard-golden.fixture.json")
    ziel.write_text(json.dumps(ausgabe, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{ziel.relative_to(WURZEL)}: {ziel.stat().st_size} Bytes")


if __name__ == "__main__":
    main()
