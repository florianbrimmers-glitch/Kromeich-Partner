"""Tests fuer artifacts.py: Effekte triggern, Preconditions halten, Data-Integritaet."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import balance_sim as bs     # noqa: E402
import artifacts as art      # noqa: E402


def _units_by_id() -> dict[str, bs.Unit]:
    return {u.id: u for u in bs.load_units()}


def _stack(unit: bs.Unit, count: int, side: int = 0) -> bs.Stack:
    return bs.Stack(unit=unit, count=count, top_hp=unit.hp, side=side)


def test_artifact_ids_match_json() -> None:
    ids = set(art.load_artifact_ids())
    # Alle ARTIFACT_EFFECTS muessen auch im JSON stehen
    for effect_id in art.ARTIFACT_EFFECTS:
        assert effect_id in ids, f"Effect {effect_id} fehlt in artifacts.json"


def test_crown_of_elements_buffs_hero() -> None:
    hero = bs.Hero(name="Mage", spell_power=3, spell_points=20, spellbook=["bless"])
    art.apply_artifacts(hero, ["crown_of_elements"], [], [])
    assert hero.spell_power == 4
    assert hero.spell_points == 30
    assert "implosion" in hero.spellbook


def test_ogre_totem_awards_attack_per_large_stack() -> None:
    units = _units_by_id()
    goblin = units["ork_goblin"]
    ogre = units["ork_ogre"]
    hero = bs.Hero(name="Chief", att=5)
    own = [_stack(goblin, 60), _stack(ogre, 20), _stack(goblin, 50, side=0)]
    art.apply_artifacts(hero, ["ogre_totem"], own, [])
    # 2 Stacks >= 50 Einheiten -> +2 att
    assert hero.att == 7


def test_horn_of_the_forest_only_for_waldvolk() -> None:
    units = _units_by_id()
    orc = units["ork_orc"]
    elf = units["elf_archer"]
    hero = bs.Hero(name="Druid")

    own_orks = [_stack(orc, 10)]
    art.apply_artifacts(hero, ["horn_of_the_forest"], own_orks, [])
    assert all(s.unit.id != "elf_treant" for s in own_orks), \
        "Orks duerfen keinen Treant-Summon bekommen"

    own_elfs = [_stack(elf, 10)]
    before = len(own_elfs)
    art.apply_artifacts(hero, ["horn_of_the_forest"], own_elfs, [])
    assert any(s.unit.id == "elf_treant" for s in own_elfs)
    assert len(own_elfs) == before + 1


def test_chalice_of_necromancy_requires_undead_majority() -> None:
    units = _units_by_id()
    skeleton = units["nec_skeleton"]
    spearman = units["men_spearman"]

    # 80 Prozent Untot -> buff
    hero = bs.Hero(name="Lich", morale=1)
    mostly_undead = [_stack(skeleton, 80), _stack(spearman, 20)]
    art.apply_artifacts(hero, ["chalice_of_necromancy"], mostly_undead, [])
    assert any("buffed_necromancy" in s.unit.abilities for s in mostly_undead)
    assert hero.morale == 1  # Kein Penalty

    # Nur 30 Prozent Untot -> Penalty
    hero2 = bs.Hero(name="Lich2", morale=1)
    mixed = [_stack(skeleton, 30), _stack(spearman, 70)]
    art.apply_artifacts(hero2, ["chalice_of_necromancy"], mixed, [])
    assert hero2.morale == -1


def test_blade_of_dragonslaying_triggers_against_tier7_flying() -> None:
    units = _units_by_id()
    angel = units["men_angel"]
    goblin = units["ork_goblin"]

    hero = bs.Hero(name="Slayer", att=10)
    # Kein T7 Flyer -> kein Bonus
    art.apply_artifacts(hero, ["blade_of_dragonslaying"], [], [_stack(goblin, 10, side=1)])
    assert hero.att == 10

    # T7 Flyer vorhanden -> +5 Att
    hero2 = bs.Hero(name="Slayer2", att=10)
    art.apply_artifacts(hero2, ["blade_of_dragonslaying"], [], [_stack(angel, 3, side=1)])
    assert hero2.att == 15


def test_spellbook_of_echo_boosts_spell_points() -> None:
    hero = bs.Hero(name="Echo", spell_points=40)
    art.apply_artifacts(hero, ["spellbook_of_echo"], [], [])
    assert hero.spell_points == 60


def test_apply_unknown_artifact_is_safe() -> None:
    hero = bs.Hero(name="Zero")
    # Nicht-existierender Effekt darf nicht crashen und nichts aendern
    art.apply_artifacts(hero, ["does_not_exist_42"], [], [])
    assert hero.att == 0
    assert hero.spell_points == 10
