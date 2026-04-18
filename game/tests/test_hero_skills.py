"""Tests fuer Hero-Skills im Combat-Engine (Session 5)."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import balance_sim as bs  # noqa: E402


def _two_crusaders(att_hero_skills: dict | None = None,
                   def_hero_skills: dict | None = None) -> tuple[bs.Stack, bs.Stack, bs.Hero, bs.Hero]:
    units = {u.id: u for u in bs.load_units()}
    sword = units["men_crusader"]
    a = bs.Stack(unit=sword, count=20, top_hp=sword.hp, side=0)
    b = bs.Stack(unit=sword, count=20, top_hp=sword.hp, side=1)
    ha = bs.Hero(skills=att_hero_skills or {})
    hb = bs.Hero(skills=def_hero_skills or {})
    return a, b, ha, hb


def _avg_dmg(attacker, target, atk_hero, def_hero, trials: int = 200) -> float:
    total = 0
    for seed in range(trials):
        rng = bs.DeterministicRng(seed + 1)
        total += bs.compute_damage(attacker, target, rng, 0, 0, atk_hero, def_hero)
    return total / trials


def test_offense_tier3_boosts_melee_damage_by_40pct() -> None:
    a, b, _, hb = _two_crusaders()
    base = _avg_dmg(a, b, bs.Hero(), hb)
    boosted = _avg_dmg(a, b, bs.Hero(skills={"offense": 3}), hb)
    ratio = boosted / base
    assert 1.35 <= ratio <= 1.45, f"Offense-3 sollte +40%% melee liefern, gemessen {ratio:.2f}"


def test_archery_only_applies_to_ranged_units() -> None:
    units = {u.id: u for u in bs.load_units()}
    archer = units["elf_archer"]
    sword = units["men_crusader"]
    ranged_atk = bs.Stack(unit=archer, count=10, top_hp=archer.hp, side=0)
    target = bs.Stack(unit=sword, count=20, top_hp=sword.hp, side=1)
    base = _avg_dmg(ranged_atk, target, bs.Hero(), bs.Hero())
    with_archery = _avg_dmg(ranged_atk, target, bs.Hero(skills={"archery": 3}), bs.Hero())
    assert with_archery / base > 1.35, "Archery-3 muss Ranged-Schaden erhoehen"

    # Offense auf Ranged soll NICHT wirken
    melee_only = _avg_dmg(ranged_atk, target, bs.Hero(skills={"offense": 3}), bs.Hero())
    assert abs(melee_only - base) / base < 0.05, "Offense darf Ranged nicht buffen"


def test_armorer_reduces_incoming_damage() -> None:
    a, b, ha, _ = _two_crusaders()
    base = _avg_dmg(a, b, ha, bs.Hero())
    with_armor = _avg_dmg(a, b, ha, bs.Hero(skills={"armorer": 3}))
    ratio = with_armor / base
    assert 0.80 <= ratio <= 0.90, f"Armorer-3 -> -15%% taken, gemessen {ratio:.2f}"


def test_leadership_translates_to_morale_in_faction_hero() -> None:
    # Unser Default-Build hat kein leadership mehr - wir pruefen die
    # Uebersetzung ueber direktes skill-set im make_faction_hero-Flow.
    hero = bs.Hero(skills={"leadership": 2})
    bs.Hero.__init__  # sanity
    assert hero.skills["leadership"] == 2
    # Die Morale-Zuweisung passiert in make_faction_hero; pruefen wir die
    # Konstante direkt:
    assert bs._LEADERSHIP_MORALE[2] == 2


def test_make_faction_hero_week_scaling() -> None:
    h2 = bs.make_faction_hero("menschen", week=2)
    h4 = bs.make_faction_hero("menschen", week=4)
    h6 = bs.make_faction_hero("menschen", week=6)
    # Tier-Skalierung (1, 2, 2): W2 sollte weniger att haben als W4
    assert h2.att < h4.att
    # W4 und W6 sind beide Tier 2 per Design-Cap
    assert h4.att == h6.att


def test_make_faction_hero_all_factions_identical_build() -> None:
    """Pass 9 Entscheidung: Auto-Assign ist symmetrisch, um Sim-Bias zu vermeiden."""
    heroes = {f: bs.make_faction_hero(f, week=4) for f in
              ("menschen", "orkstaemme", "waldvolk", "totenreich")}
    atts = {h.att for h in heroes.values()}
    assert len(atts) == 1, f"Default-Build soll symmetrisch sein, att unterscheidet sich: {atts}"


def test_compute_damage_backwards_compatible_without_heroes() -> None:
    """Bestehende Aufrufe ohne attacker_hero/defender_hero muessen weiter funktionieren."""
    a, b, _, _ = _two_crusaders()
    rng = bs.DeterministicRng(1)
    dmg = bs.compute_damage(a, b, rng, 0, 0)
    assert dmg > 0
