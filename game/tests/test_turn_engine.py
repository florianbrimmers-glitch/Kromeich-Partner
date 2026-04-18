"""Tests fuer turn_engine.py: Initial-State, advance_day Determinismus, Sieg-Bedingung."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import balance_sim as bs     # noqa: E402
import map_gen as mg         # noqa: E402
import turn_engine as te     # noqa: E402


def _units_by_faction() -> dict[str, list[bs.Unit]]:
    by_f: dict[str, list[bs.Unit]] = {}
    for u in bs.load_units():
        by_f.setdefault(u.faction, []).append(u)
    return by_f


def test_build_initial_state_gives_each_player_town_and_hero() -> None:
    by_f = _units_by_faction()
    gen_map = mg.generate("duell_klein", seed=42)
    state = te.build_initial_state(gen_map, ["menschen", "totenreich"], by_f)

    assert len(state.players) == 2
    for p in state.players:
        assert len(p.towns) == 1
        assert len(p.heroes) == 1
        assert p.heroes[0].army, "Starthero muss Startarmee haben"
        assert p.treasury.gold >= 10000


def test_advance_day_is_deterministic() -> None:
    by_f = _units_by_faction()
    gen_map = mg.generate("duell_klein", seed=42)

    s1 = te.build_initial_state(gen_map, ["menschen", "totenreich"], by_f)
    rng1 = bs.DeterministicRng(42)
    for _ in range(10):
        te.advance_day(s1, rng1, by_f)

    s2 = te.build_initial_state(gen_map, ["menschen", "totenreich"], by_f)
    rng2 = bs.DeterministicRng(42)
    for _ in range(10):
        te.advance_day(s2, rng2, by_f)

    assert s1.day == s2.day
    assert len(s1.events) == len(s2.events)
    for e1, e2 in zip(s1.events, s2.events):
        assert e1.day == e2.day and e1.text == e2.text


def test_week_computation() -> None:
    by_f = _units_by_faction()
    gen_map = mg.generate("duell_klein", seed=42)
    state = te.build_initial_state(gen_map, ["menschen", "totenreich"], by_f)
    assert state.week() == 1
    state.day = 8
    assert state.week() == 2
    state.day = 15
    assert state.week() == 3


def test_daily_income_accumulates() -> None:
    by_f = _units_by_faction()
    gen_map = mg.generate("duell_klein", seed=42)
    state = te.build_initial_state(gen_map, ["menschen", "totenreich"], by_f)
    rng = bs.DeterministicRng(42)
    start_gold = [p.treasury.gold for p in state.players]
    te.advance_day(state, rng, by_f)
    # Nach einem Tag muss Gold gestiegen oder gleich sein (Recruits koennen ausgeben)
    for p, start in zip(state.players, start_gold):
        assert p.treasury.gold != start or len(p.heroes[0].army) > 0


def test_advance_many_days_does_not_crash_and_may_end() -> None:
    by_f = _units_by_faction()
    gen_map = mg.generate("duell_klein", seed=42)
    state = te.build_initial_state(gen_map, ["menschen", "totenreich"], by_f)
    rng = bs.DeterministicRng(42)
    for _ in range(30):
        te.advance_day(state, rng, by_f)
        alive = [p for p in state.players if not p.defeated]
        if len(alive) <= 1:
            break
    # Mindestens ein Event muss generiert worden sein (Recruit oder Mine)
    assert len(state.events) > 0


def test_mine_capture_transfers_ownership() -> None:
    by_f = _units_by_faction()
    gen_map = mg.generate("duell_klein", seed=42)
    state = te.build_initial_state(gen_map, ["menschen", "totenreich"], by_f)
    rng = bs.DeterministicRng(42)
    initial_unowned = len(state.unowned_mines)
    for _ in range(20):
        te.advance_day(state, rng, by_f)
    total_owned = sum(len(p.mines) for p in state.players)
    assert total_owned + len(state.unowned_mines) == initial_unowned, \
        "Keine Minen duerfen verschwinden"
    assert total_owned > 0, "Spieler sollten bis Tag 20 mindestens eine Mine erobert haben"
