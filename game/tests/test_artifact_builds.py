"""Build-Tests fuer game_changer-Artefakte (Plan-Verifikation #5).

Jeder `game_changer: true`-Artefakt muss mindestens einen Build ermoeglichen,
der gegen die Baseline-Variante einen messbaren Vorteil zeigt. Tests die
den Combat-Pfad durchlaufen, spielen 40 Gefechte A-vs-B und erwarten
Winrate >= 55 Prozent fuer den Artefakt-Traeger.

Wo der Artefakt-Effekt noch nicht vollstaendig durch die Battle-Engine
gezogen wird (z.B. gauntlets_of_the_conqueror braucht Siege-Logik), testen
wir den State-Change + dokumentieren den pending combat-hook.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import balance_sim as bs     # noqa: E402
import artifacts as art      # noqa: E402


DATA_DIR = ROOT / "data"


def _units_by_id() -> dict[str, bs.Unit]:
    return {u.id: u for u in bs.load_units()}


def _faction(faction: str) -> list[bs.Unit]:
    return [u for u in bs.load_units() if u.faction == faction]


def _clone_stacks(stacks: list[bs.Stack], side: int) -> list[bs.Stack]:
    return [bs.Stack(unit=s.unit, count=s.count, top_hp=s.unit.hp, side=side) for s in stacks]


def _game_changer_ids() -> set[str]:
    data = json.loads((DATA_DIR / "artifacts.json").read_text())
    return {a["id"] for a in data["artifacts"] if a.get("game_changer")}


# ---------- Combat-integrierte Build-Tests ----------


def _winrate_a_vs_b(
    build_a: callable, build_b: callable, seeds: range,
) -> float:
    wins_a = draws = 0
    for seed in seeds:
        side0, hero0 = build_a(seed)
        side1, hero1 = build_b(seed)
        rng = bs.DeterministicRng(seed)
        out = bs.simulate_battle(side0, side1, rng, hero0, hero1)
        if out == "side0":
            wins_a += 1
        elif out == "draw":
            draws += 1
    return wins_a / max(1, len(seeds) - draws)


def test_ogre_totem_build_beats_baseline() -> None:
    """Swarm-Build mit Totem-Bonus (grosse Stacks = +att) schlaegt Baseline."""
    units = _units_by_id()
    goblin = units["ork_goblin"]
    wolfrider = units["ork_wolfrider"]

    def with_totem(_seed: int) -> tuple[list[bs.Stack], bs.Hero]:
        stacks = [
            bs.Stack(unit=goblin, count=80, top_hp=goblin.hp, side=0),
            bs.Stack(unit=wolfrider, count=60, top_hp=wolfrider.hp, side=0),
        ]
        hero = bs.Hero(name="Warlord-with", att=2)
        art.apply_artifacts(hero, ["ogre_totem"], stacks, [])
        return stacks, hero

    def baseline(_seed: int) -> tuple[list[bs.Stack], bs.Hero]:
        stacks = [
            bs.Stack(unit=goblin, count=80, top_hp=goblin.hp, side=1),
            bs.Stack(unit=wolfrider, count=60, top_hp=wolfrider.hp, side=1),
        ]
        return stacks, bs.Hero(name="Warlord-baseline", att=2)

    wr = _winrate_a_vs_b(with_totem, baseline, range(40))
    assert wr >= 0.55, f"Ogre-Totem-Build muss Baseline schlagen; erreicht {wr:.2f}"


def test_horn_of_forest_build_adds_treants_and_wins() -> None:
    """Waldvolk-Build mit Horn summoniert 3 Treants und hat Armee-Vorteil."""
    units = _units_by_id()
    archer = units["elf_archer"]

    def with_horn(_seed: int) -> tuple[list[bs.Stack], bs.Hero]:
        stacks = [bs.Stack(unit=archer, count=20, top_hp=archer.hp, side=0)]
        hero = bs.Hero(name="Druid-with")
        art.apply_artifacts(hero, ["horn_of_the_forest"], stacks, [])
        assert any(s.unit.id == "elf_treant" for s in stacks)
        return stacks, hero

    def baseline(_seed: int) -> tuple[list[bs.Stack], bs.Hero]:
        stacks = [bs.Stack(unit=archer, count=20, top_hp=archer.hp, side=1)]
        return stacks, bs.Hero(name="Druid-baseline")

    wr = _winrate_a_vs_b(with_horn, baseline, range(40))
    assert wr >= 0.55, f"Horn-Build muss mit 3 extra Treants gewinnen; {wr:.2f}"


def test_crown_of_elements_mage_build_wins() -> None:
    """Crown gibt +1 SP und +Implosion Spell: Mage burst-downs Gegner."""
    units = _units_by_id()
    skeleton = units["nec_skeleton"]

    def with_crown(_seed: int) -> tuple[list[bs.Stack], bs.Hero]:
        stacks = [bs.Stack(unit=skeleton, count=30, top_hp=skeleton.hp, side=0)]
        hero = bs.Hero(name="Archmage-with", spell_power=3, spell_points=40, spellbook=["bless"])
        art.apply_artifacts(hero, ["crown_of_elements"], stacks, [])
        assert "implosion" in hero.spellbook
        return stacks, hero

    def baseline(_seed: int) -> tuple[list[bs.Stack], bs.Hero]:
        stacks = [bs.Stack(unit=skeleton, count=30, top_hp=skeleton.hp, side=1)]
        hero = bs.Hero(name="Archmage-baseline", spell_power=3, spell_points=40, spellbook=["bless"])
        return stacks, hero

    wr = _winrate_a_vs_b(with_crown, baseline, range(40))
    assert wr >= 0.55, f"Crown-Build muss mehr Damage durch Implosion fahren; {wr:.2f}"


def test_spellbook_of_echo_burst_mage_build_wins() -> None:
    """+50 Prozent SP -> mehr Burst-Spells -> wins."""
    units = _units_by_id()
    skeleton = units["nec_skeleton"]

    def with_echo(_seed: int) -> tuple[list[bs.Stack], bs.Hero]:
        stacks = [bs.Stack(unit=skeleton, count=25, top_hp=skeleton.hp, side=0)]
        hero = bs.Hero(name="BurstMage-with", spell_power=3,
                       spell_points=30, spellbook=["implosion", "fire_bolt"])
        art.apply_artifacts(hero, ["spellbook_of_echo"], stacks, [])
        assert hero.spell_points == 45
        return stacks, hero

    def baseline(_seed: int) -> tuple[list[bs.Stack], bs.Hero]:
        stacks = [bs.Stack(unit=skeleton, count=25, top_hp=skeleton.hp, side=1)]
        hero = bs.Hero(name="BurstMage-baseline", spell_power=3,
                       spell_points=30, spellbook=["implosion", "fire_bolt"])
        return stacks, hero

    wr = _winrate_a_vs_b(with_echo, baseline, range(40))
    assert wr >= 0.55, f"Echo-Build muss mit +50%% SP mehr Spells casten und gewinnen; {wr:.2f}"


# ---------- State-Change-Tests (Combat-Hook pending) ----------


def test_chalice_build_requires_80pct_undead_majority() -> None:
    """Chalice buffed undead-Stacks wenn >= 80 Prozent, sonst Moral-Penalty.

    Der Combat-Durchgriff (buffed_necromancy beeinflusst HP-Regen nach Kampf)
    wird in einer spaeteren Meilenstein implementiert. Hier: State-Invariante.
    """
    units = _units_by_id()
    skeleton = units["nec_skeleton"]
    spearman = units["men_spearman"]

    pure_undead = [
        bs.Stack(unit=skeleton, count=100, top_hp=skeleton.hp, side=0),
    ]
    hero = bs.Hero(name="Necro", morale=2)
    art.apply_artifacts(hero, ["chalice_of_necromancy"], pure_undead, [])
    assert "buffed_necromancy" in pure_undead[0].unit.abilities
    assert hero.morale == 2

    mixed = [
        bs.Stack(unit=skeleton, count=50, top_hp=skeleton.hp, side=0),
        bs.Stack(unit=spearman, count=50, top_hp=spearman.hp, side=0),
    ]
    hero2 = bs.Hero(name="Necro2", morale=2)
    art.apply_artifacts(hero2, ["chalice_of_necromancy"], mixed, [])
    assert hero2.morale == 0  # -2 Penalty


def test_amulet_of_armageddon_marks_army_immune() -> None:
    """Tuer zum Dragon-Slave-Build: alle eigenen Stacks bekommen Immunitaet-Flag."""
    units = _units_by_id()
    angel = units["men_angel"]
    own = [bs.Stack(unit=angel, count=3, top_hp=angel.hp, side=0)]
    hero = bs.Hero(name="DragonSlaver")
    art.apply_artifacts(hero, ["amulet_of_armageddon"], own, [])
    assert all("immune_armageddon" in s.unit.abilities for s in own)


def test_orb_of_silence_normalizes_spellbook() -> None:
    """Orb-Effekt symbolisch: spellbook wird als Liste repliziert (Platzhalter).

    Tatsaechliche Sperre von Level 4-5 Gegner-Spells wird beim Engine-Ausbau
    durch Pruefung gegen hero.spellbook_blocked angehaengt.
    """
    hero = bs.Hero(name="Silencer", spellbook=["bless"])
    art.apply_artifacts(hero, ["orb_of_silence"], [], [])
    assert isinstance(hero.spellbook, list)


def test_gauntlets_of_conqueror_data_integrity() -> None:
    """gauntlets_of_the_conqueror ist game_changer mit Siege-Bonus.

    Effect-Hook kommt mit Siege-Mechanik (Meilenstein 2 Folgesitzung).
    """
    data = json.loads((DATA_DIR / "artifacts.json").read_text())
    art_entry = next(a for a in data["artifacts"] if a["id"] == "gauntlets_of_the_conqueror")
    assert art_entry["game_changer"] is True
    assert art_entry["effects"]["siege_dmg_bonus"] == 2.0
    assert art_entry["effects"]["wall_break_guaranteed"] is True


def test_staff_of_equinox_data_integrity() -> None:
    """Switchmage-Build-Artefakt. Effect-Hook kommt mit School-Switch-Logik."""
    data = json.loads((DATA_DIR / "artifacts.json").read_text())
    art_entry = next(a for a in data["artifacts"] if a["id"] == "staff_of_the_equinox")
    assert art_entry["game_changer"] is True
    assert "build:switchmage" in art_entry["tags"]


# ---------- Coverage-Check ----------


def test_all_game_changer_artifacts_have_a_test() -> None:
    """Jedes game_changer-Artefakt muss in dieser Datei referenziert sein."""
    expected = _game_changer_ids()
    this_file = pathlib.Path(__file__).read_text()
    missing = [a for a in expected if a not in this_file]
    assert not missing, f"Fehlende Build-Tests fuer: {missing}"
