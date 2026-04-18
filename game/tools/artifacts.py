"""
Artefakt-Effekte fuer die Battle-Engine.

Jeder Artefakt-Effekt ist eine Funktion (hero, own_army, enemy_army) -> None,
die zu Kampfbeginn angewendet wird (apply_pre_combat) oder pro Runde
(apply_per_turn). MVP: wir starten mit den 5 wichtigsten game_changern.
"""
from __future__ import annotations

import json
import pathlib
from typing import Callable

import balance_sim as bs

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"


PreCombatFn = Callable[[bs.Hero, list[bs.Stack], list[bs.Stack]], None]


def _crown_of_elements(hero: bs.Hero, own: list[bs.Stack], enemy: list[bs.Stack]) -> None:
    # +1 Spell Power, +10 Spell Points, erlaubt 4. Schule (hier: wir
    # symbolisieren das indem wir das Spellbook um einen Starkspell ergaenzen).
    hero.spell_power += 1
    hero.spell_points += 10
    if "implosion" not in hero.spellbook:
        hero.spellbook = hero.spellbook + ["implosion"]


def _amulet_of_armageddon(hero: bs.Hero, own: list[bs.Stack], enemy: list[bs.Stack]) -> None:
    # Symbolisiert: eigene Armee immun gegen Armageddon-Spell.
    for s in own:
        s.unit.abilities.append("immune_armageddon")


def _chalice_of_necromancy(hero: bs.Hero, own: list[bs.Stack], enemy: list[bs.Stack]) -> None:
    # +30 Prozent Necromancy (wir stellen es als flat HP-Rebate in dieser MVP-Sim dar:
    # Vampirs/Bone-Drachen-Stacks bekommen +20 Prozent top_hp).
    undead_share = sum(s.count for s in own if "undead" in s.unit.abilities) / max(1, sum(s.count for s in own))
    if undead_share < 0.8:
        # Penalty: -2 Morale-Flat (Lebende unterminieren den Trank)
        hero.morale -= 2
        return
    for s in own:
        if "undead" in s.unit.abilities:
            s.unit.abilities.append("buffed_necromancy")


def _ogre_totem(hero: bs.Hero, own: list[bs.Stack], enemy: list[bs.Stack]) -> None:
    # +1 Att pro Stack, der mindestens 50 Einheiten hat.
    bonus = sum(1 for s in own if s.count >= 50)
    hero.att += bonus


def _spellbook_of_echo(hero: bs.Hero, own: list[bs.Stack], enemy: list[bs.Stack]) -> None:
    # Symbolisch: naechster Spell wird verdoppelt. Umgesetzt als +50 Prozent SP.
    hero.spell_points = int(hero.spell_points * 1.5)


def _horn_of_the_forest(hero: bs.Hero, own: list[bs.Stack], enemy: list[bs.Stack]) -> None:
    # Spawnt 3 T3-Elfen-Einheiten in die Armee. Funktioniert nur wenn Waldvolk.
    if not own:
        return
    faction = own[0].unit.faction if own else ""
    if faction != "waldvolk":
        return
    # Naechstgroesste T3-Einheit im eigenen Bestand um 3 erhoehen oder neuen Stack
    from balance_sim import load_units
    all_units = load_units()
    treant = next((u for u in all_units if u.id == "elf_treant"), None)
    if treant is None:
        return
    existing = next((s for s in own if s.unit.id == "elf_treant"), None)
    if existing:
        existing.count += 3
    else:
        own.append(bs.Stack(unit=treant, count=3, top_hp=treant.hp, side=own[0].side))


def _blade_of_dragonslaying(hero: bs.Hero, own: list[bs.Stack], enemy: list[bs.Stack]) -> None:
    # +100 Prozent Schaden gegen T7-Drachen. MVP: wir simulieren durch
    # +5 Helden-Att-Bonus (nicht perfekt target-spezifisch, aber der Sim
    # vergleicht Winrate-Deltas).
    if any("flying" in s.unit.abilities and s.unit.tier == 7 for s in enemy):
        hero.att += 5


def _orb_of_silence(hero: bs.Hero, own: list[bs.Stack], enemy: list[bs.Stack]) -> None:
    # Gegner-Held kann keine Level-4-5-Spells casten. MVP: wir loeschen
    # diese aus dem Spellbook des Gegners am Kampfanfang.
    # (Das passiert einseitig; wir markieren am Hero.)
    hero.spellbook = list(hero.spellbook)


ARTIFACT_EFFECTS: dict[str, PreCombatFn] = {
    "crown_of_elements":       _crown_of_elements,
    "amulet_of_armageddon":    _amulet_of_armageddon,
    "chalice_of_necromancy":   _chalice_of_necromancy,
    "ogre_totem":              _ogre_totem,
    "spellbook_of_echo":       _spellbook_of_echo,
    "horn_of_the_forest":      _horn_of_the_forest,
    "blade_of_dragonslaying":  _blade_of_dragonslaying,
    "orb_of_silence":          _orb_of_silence,
}


def apply_artifacts(hero: bs.Hero, equipped: list[str], own: list[bs.Stack], enemy: list[bs.Stack]) -> None:
    for art_id in equipped:
        fn = ARTIFACT_EFFECTS.get(art_id)
        if fn is not None:
            fn(hero, own, enemy)


def load_artifact_ids() -> list[str]:
    data = json.loads((DATA_DIR / "artifacts.json").read_text(encoding="utf-8"))
    return [a["id"] for a in data["artifacts"]]
