"""Smoke- und Determinismus-Tests fuer balance_sim.py."""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import balance_sim as bs  # noqa: E402


def test_rng_is_deterministic() -> None:
    a = bs.DeterministicRng(42)
    b = bs.DeterministicRng(42)
    for _ in range(100):
        assert a._next() == b._next()


def test_rng_different_seeds_diverge() -> None:
    a = bs.DeterministicRng(1)
    b = bs.DeterministicRng(2)
    diffs = sum(a._next() != b._next() for _ in range(100))
    assert diffs > 95


def test_units_json_loads_and_has_four_factions() -> None:
    units = bs.load_units()
    assert len(units) == 28, f"Erwarte 28 Einheiten (4 Fraktionen x 7 Tiers), habe {len(units)}"
    by_faction: dict[str, list[bs.Unit]] = {}
    for u in units:
        by_faction.setdefault(u.faction, []).append(u)
    assert set(by_faction.keys()) == {"menschen", "waldvolk", "totenreich", "orkstaemme"}
    for faction, lst in by_faction.items():
        tiers = sorted(u.tier for u in lst)
        assert tiers == [1, 2, 3, 4, 5, 6, 7], f"{faction}: Tiers unvollstaendig: {tiers}"


def test_battle_is_deterministic_same_seed() -> None:
    units = bs.load_units()
    by_f: dict[str, list[bs.Unit]] = {}
    for u in units:
        by_f.setdefault(u.faction, []).append(u)

    def run(seed: int) -> str:
        rng = bs.DeterministicRng(seed)
        a = bs.build_army(by_f["menschen"], week=4, side=0)
        b = bs.build_army(by_f["orkstaemme"], week=4, side=1)
        return bs.simulate_battle(a, b, rng)

    assert run(123) == run(123)
    assert run(42) == run(42)


def test_build_army_respects_week() -> None:
    units = bs.load_units()
    by_f: dict[str, list[bs.Unit]] = {}
    for u in units:
        by_f.setdefault(u.faction, []).append(u)

    def total_hp(stacks: list[bs.Stack]) -> int:
        return sum(s.count * s.unit.hp for s in stacks)

    wk1 = total_hp(bs.build_army(by_f["menschen"], week=1, side=0))
    wk4 = total_hp(bs.build_army(by_f["menschen"], week=4, side=0))
    assert wk4 > wk1, f"Woche 4 sollte hoeheren Armee-HP-Pool haben als Woche 1 (wk1={wk1}, wk4={wk4})"


def test_artifacts_have_8_game_changers() -> None:
    path = ROOT / "data" / "artifacts.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    game_changers = [a for a in data["artifacts"] if a.get("game_changer")]
    assert len(game_changers) >= 8, f"Mindestens 8 game_changer erwartet, {len(game_changers)} gefunden"


def test_spells_cover_all_schools() -> None:
    path = ROOT / "data" / "spells.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    schools_in_spells = {s["school"] for s in data["spells"]}
    expected = {"licht", "ordnung", "natur", "chaos", "tod"}
    assert expected <= schools_in_spells, f"Fehlende Schulen: {expected - schools_in_spells}"


def test_factions_json_matches_units_json() -> None:
    path = ROOT / "data" / "factions.json"
    fac_data = json.loads(path.read_text(encoding="utf-8"))
    declared_factions = {f["id"] for f in fac_data["factions"]}
    units = bs.load_units()
    unit_factions = {u.faction for u in units}
    assert declared_factions == unit_factions
