"""Zeitreihe der Monats-Mediane – ohne sie gäbe es keine Veränderungsspalte."""

import json
from datetime import date

from comparables_handler import snapshots

VERLAUF = [
    {"stand": "2025-08", "werte": {"Halle/Lager|Düsseldorf": 5.50}},
    {"stand": "2026-02", "werte": {"Halle/Lager|Düsseldorf": 5.80}},
    {"stand": "2026-07", "werte": {"Halle/Lager|Düsseldorf": 6.00}},
]


def test_aktueller_stand_als_monatsschluessel():
    assert snapshots.aktueller_stand(date(2026, 8, 12)) == "2026-08"
    assert snapshots.aktueller_stand(date(2026, 1, 5)) == "2026-01"


def test_vorjahresvergleich_findet_den_passenden_stand():
    treffer = snapshots.vergleichs_snapshot(VERLAUF, "2026-08", monate=12, toleranz=3)
    assert treffer["stand"] == "2025-08"


def test_naechstgelegener_stand_gewinnt():
    """Läuft der Job nicht lückenlos, zählt der nächstgelegene in der Toleranz."""
    verlauf = [{"stand": "2025-10", "werte": {}}, {"stand": "2025-06", "werte": {}}]
    treffer = snapshots.vergleichs_snapshot(verlauf, "2026-08", monate=12, toleranz=3)
    assert treffer["stand"] == "2025-10"      # 2 Monate Abstand statt 2 -> gleich, erster gewinnt


def test_ausserhalb_der_toleranz_kein_vergleich():
    """Lieber keine Veränderung als eine gegen eine unpassende Basis."""
    verlauf = [{"stand": "2024-01", "werte": {}}]
    assert snapshots.vergleichs_snapshot(verlauf, "2026-08", monate=12, toleranz=3) is None


def test_erster_lauf_hat_keine_basis():
    assert snapshots.vergleichs_snapshot([], "2026-08", monate=12, toleranz=3) is None


def test_zukuenftige_staende_werden_ignoriert():
    verlauf = [{"stand": "2027-01", "werte": {}}]
    assert snapshots.vergleichs_snapshot(verlauf, "2026-08", monate=12, toleranz=3) is None


def test_anhaengen_ersetzt_denselben_monat():
    """Zwei Läufe im selben Monat dürfen keine zwei Stände erzeugen."""
    verlauf = snapshots.anhaengen(list(VERLAUF), "2026-07", {"Halle/Lager|Düsseldorf": 6.20})
    staende = [s["stand"] for s in verlauf]
    assert staende == ["2025-08", "2026-02", "2026-07"]
    assert verlauf[-1]["werte"]["Halle/Lager|Düsseldorf"] == 6.20


def test_anhaengen_haelt_die_reihenfolge():
    verlauf = snapshots.anhaengen(list(VERLAUF), "2026-08", {})
    assert [s["stand"] for s in verlauf] == ["2025-08", "2026-02", "2026-07", "2026-08"]


def test_roundtrip(tmp_path):
    pfad = str(tmp_path / "snap.json")
    assert snapshots.schreiben(pfad, VERLAUF)
    assert snapshots.laden(pfad) == VERLAUF


def test_fehlende_datei_ist_kein_fehler(tmp_path):
    assert snapshots.laden(str(tmp_path / "gibtsnicht.json")) == []


def test_kaputte_datei_bricht_den_lauf_nicht(tmp_path):
    pfad = tmp_path / "kaputt.json"
    pfad.write_text("{kein json", encoding="utf-8")
    assert snapshots.laden(str(pfad)) == []


def test_falsches_format_wird_ignoriert(tmp_path):
    pfad = tmp_path / "objekt.json"
    pfad.write_text(json.dumps({"stand": "2026-08"}), encoding="utf-8")
    assert snapshots.laden(str(pfad)) == []


def test_eintraege_ohne_stand_fliegen_raus(tmp_path):
    pfad = tmp_path / "teils.json"
    pfad.write_text(json.dumps([{"werte": {}}, {"stand": "2026-08", "werte": {}}]),
                    encoding="utf-8")
    assert [s["stand"] for s in snapshots.laden(str(pfad))] == ["2026-08"]


def test_leerer_pfad_schaltet_die_ablage_ab():
    assert snapshots.laden("") == []
    assert snapshots.schreiben("", VERLAUF) is False
