"""Tests fuer erweiterte Battle-Engine: Helden, Spells, Morale."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import balance_sim as bs  # noqa: E402


def _make_armies() -> tuple[list[bs.Stack], list[bs.Stack]]:
    units = bs.load_units()
    by_f: dict[str, list[bs.Unit]] = {}
    for u in units:
        by_f.setdefault(u.faction, []).append(u)
    return (
        bs.build_army(by_f["menschen"], week=4, side=0),
        bs.build_army(by_f["totenreich"], week=4, side=1),
    )


def test_hero_att_bonus_accelerates_win() -> None:
    # Mit hoher Helden-Att sollte Seite 0 oft schneller gewinnen.
    wins_boosted = wins_plain = 0
    for i in range(80):
        s0, s1 = _make_armies()
        rng = bs.DeterministicRng(100 + i)
        hero = bs.Hero(att=15, def_=0, spellbook=[])
        out = bs.simulate_battle(s0, s1, rng, hero, bs.Hero())
        if out == "side0": wins_boosted += 1

        s0, s1 = _make_armies()
        rng = bs.DeterministicRng(100 + i)
        out = bs.simulate_battle(s0, s1, rng, bs.Hero(), bs.Hero())
        if out == "side0": wins_plain += 1

    assert wins_boosted >= wins_plain, f"Boost war wirkungslos: {wins_boosted} vs {wins_plain}"


def test_bless_sets_dmg_to_max() -> None:
    units = bs.load_units()
    archer = next(u for u in units if u.id == "elf_archer")
    s = bs.Stack(unit=archer, count=10, top_hp=archer.hp, side=0, bless=3)
    target = bs.Stack(unit=archer, count=10, top_hp=archer.hp, side=1)
    rng = bs.DeterministicRng(1)
    # Mit bless sollte base == dmg_hi; Stack-dmg = 10 * 5 = 50, multipliziert mit mod
    dmg = bs.compute_damage(s, target, rng)
    min_expected = 10 * archer.dmg_hi
    assert dmg >= min_expected, f"Bless-Dmg zu niedrig: {dmg} < {min_expected}"


def test_spellbook_cast_consumes_sp() -> None:
    units = bs.load_units()
    by_f: dict[str, list[bs.Unit]] = {}
    for u in units:
        by_f.setdefault(u.faction, []).append(u)
    s0 = bs.build_army(by_f["menschen"], week=4, side=0)
    s1 = bs.build_army(by_f["totenreich"], week=4, side=1)
    hero = bs.Hero(spell_points=30, spellbook=["magic_arrow", "bless"])
    rng = bs.DeterministicRng(42)
    bs.simulate_battle(s0, s1, rng, hero, bs.Hero())
    assert hero.spell_points < 30, "Held hat keine Spells gecastet (SP unveraendert)"


def test_morale_does_not_affect_undead() -> None:
    # Untote mit schlechtem Helden-Morale: Skip duerfte nicht greifen.
    units = bs.load_units()
    by_f: dict[str, list[bs.Unit]] = {}
    for u in units:
        by_f.setdefault(u.faction, []).append(u)
    s0 = bs.build_army(by_f["totenreich"], week=4, side=0)
    s1 = bs.build_army(by_f["menschen"], week=4, side=1)
    hero = bs.Hero(morale=-3)  # Skip-Chance bei 9 Prozent
    log: list[bs.TurnEvent] = []
    bs.simulate_battle(s0, s1, bs.DeterministicRng(1), hero, bs.Hero(), log)
    skip_events = [e for e in log if "Zug ausgelassen" in e.action]
    undead_skips = [e for e in skip_events if e.actor.startswith("nec_")]
    assert not undead_skips, f"Untote sollten immun gegen Moral sein, waren aber: {undead_skips}"
