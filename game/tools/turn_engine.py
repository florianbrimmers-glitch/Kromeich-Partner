"""
TurnEngine: bindet MapGen, Economy und Battle zu einem Adventure-Loop.

Pro Runde:
  1. Tages-Tick (Income + evtl. Wochen-Growth)
  2. Jeder Spieler: plant eine Action (naechstes Ziel, Recruit, Fight)
  3. Ausfuehrung bis Move-Points weg sind
  4. Log fuer CLI-Ausgabe

Keine Real-UI: rein textbasiert, deterministisch.
"""
from __future__ import annotations

import dataclasses
from typing import Iterable

import balance_sim as bs
import economy as eco
import map_gen as mg


@dataclasses.dataclass
class Hero:
    owner: int
    name: str
    x: int
    y: int
    move_points: int = 1500
    army: list[bs.Stack] = dataclasses.field(default_factory=list)
    stats: bs.Hero = dataclasses.field(default_factory=bs.Hero)


@dataclasses.dataclass
class Player:
    slot: int
    faction: str
    treasury: eco.Resources = dataclasses.field(default_factory=lambda: eco.Resources(gold=10000, wood=10, ore=10))
    heroes: list[Hero] = dataclasses.field(default_factory=list)
    towns: list[eco.Town] = dataclasses.field(default_factory=list)
    mines: list[eco.Mine] = dataclasses.field(default_factory=list)
    defeated: bool = False


@dataclasses.dataclass
class GameEvent:
    day: int
    actor: str
    text: str


@dataclasses.dataclass
class GameState:
    day: int
    map_: mg.GeneratedMap
    players: list[Player]
    neutral_monsters: list[mg.MapObject]  # die noch leben
    unowned_mines: list[eco.Mine]
    events: list[GameEvent] = dataclasses.field(default_factory=list)

    def week(self) -> int:
        return (self.day - 1) // 7 + 1


# ---------- State-Aufbau ----------


def build_initial_state(gen_map: mg.GeneratedMap, factions_order: list[str], units_by_faction: dict[str, list[bs.Unit]]) -> GameState:
    players: list[Player] = []

    for slot, faction in enumerate(factions_order):
        p = Player(slot=slot, faction=faction)
        # Nur die dem Slot zugewiesenen Town- und Hero-Objekte aus der Map uebernehmen
        town_obj = next((o for o in gen_map.objects if o.kind == "town" and o.owner == slot), None)
        hero_obj = next((o for o in gen_map.objects if o.kind == "hero" and o.owner == slot), None)
        if town_obj:
            town = eco.Town(
                owner=slot, faction=faction, x=town_obj.x, y=town_obj.y,
                has_castle=False,
                dwelling_levels={1: 1, 2: 1},  # Start mit T1+T2 Dwelling
            )
            eco.apply_weekly_growth(town, units_by_faction)
            p.towns.append(town)
        if hero_obj:
            # Starthero mit kleiner Armee: T1 + T2
            starter_army = []
            for u in units_by_faction.get(faction, []):
                if u.tier in (1, 2):
                    starter_army.append(bs.Stack(unit=u, count=(10 if u.tier == 1 else 5), top_hp=u.hp, side=slot))
            hero = Hero(
                owner=slot, name=f"Starthero-{faction}", x=hero_obj.x, y=hero_obj.y,
                army=starter_army,
                stats=bs.Hero(name=f"Starthero-{faction}", att=1, def_=1, spell_power=1, spell_points=10,
                              spellbook=["bless", "haste"]),
            )
            p.heroes.append(hero)
        players.append(p)

    neutral_monsters = [o for o in gen_map.objects if o.kind == "monster"]
    unowned_mines = [eco.Mine(owner=None, resource=o.meta.get("resource", "gold"), x=o.x, y=o.y)
                     for o in gen_map.objects if o.kind == "mine"]

    return GameState(day=1, map_=gen_map, players=players,
                     neutral_monsters=neutral_monsters, unowned_mines=unowned_mines)


# ---------- Actions ----------


def _nearest(origin: tuple[int, int], candidates: Iterable[tuple[int, int]]) -> tuple[int, int] | None:
    best = None
    best_d = 10**9
    ox, oy = origin
    for c in candidates:
        d = abs(c[0] - ox) + abs(c[1] - oy)
        if d < best_d:
            best_d = d
            best = c
    return best


def _move_cost(hero: Hero, tx: int, ty: int) -> int:
    # Manhattan-Distanz * 100 Move-Points pro Hex. Einfaches MVP.
    return (abs(hero.x - tx) + abs(hero.y - ty)) * 100


def _recruit_available(player: Player, units_by_faction: dict[str, list[bs.Unit]]) -> list[GameEvent]:
    """Kaufe so viele Einheiten, wie Gold reicht, beginnend bei hohem Tier."""
    evs: list[GameEvent] = []
    if not player.heroes or not player.towns:
        return evs
    hero = player.heroes[0]
    town = player.towns[0]
    cost_guess = {1: 60, 2: 120, 3: 250, 4: 500, 5: 800, 6: 1500, 7: 3000}
    for unit in sorted(units_by_faction.get(player.faction, []), key=lambda u: -u.tier):
        available = town.available_units.get(unit.id, 0)
        if available <= 0:
            continue
        price = cost_guess.get(unit.tier, 500)
        buyable = min(available, player.treasury.gold // max(1, price))
        if buyable <= 0:
            continue
        player.treasury.gold -= buyable * price
        town.available_units[unit.id] = available - buyable
        # In Armee einsortieren (merge oder neuer Stack)
        existing = next((s for s in hero.army if s.unit.id == unit.id), None)
        if existing:
            existing.count += buyable
        else:
            hero.army.append(bs.Stack(unit=unit, count=buyable, top_hp=unit.hp, side=player.slot))
        evs.append(GameEvent(day=0, actor=player.faction,
                             text=f"rekrutiert {buyable}x {unit.id} (kosten {buyable*price}g)"))
    return evs


def _step_player(state: GameState, player: Player, rng: bs.DeterministicRng, units_by_faction: dict[str, list[bs.Unit]]) -> None:
    if player.defeated or not player.heroes:
        return
    hero = player.heroes[0]

    # 1. Rekrutieren
    state.events.extend(dataclasses.replace(e, day=state.day) for e in _recruit_available(player, units_by_faction))

    # 2. Naechstes Ziel: freie Mine > Monster mit lootbarer Beute > Gegner-Stadt
    my_owned_mine_coords = {(m.x, m.y) for m in player.mines}

    mine_targets = [(m.x, m.y) for m in state.unowned_mines if (m.x, m.y) not in my_owned_mine_coords]
    monster_targets = [(o.x, o.y) for o in state.neutral_monsters]
    enemy_town_targets = [
        (t.x, t.y) for p in state.players for t in p.towns if p.slot != player.slot
    ]
    enemy_hero_targets = [
        (h.x, h.y) for p in state.players for h in p.heroes if p.slot != player.slot and not p.defeated
    ]

    targets = mine_targets + monster_targets + enemy_hero_targets + enemy_town_targets
    target = _nearest((hero.x, hero.y), targets)
    if target is None:
        return

    # 3. Bewegen soweit Move-Points reichen
    cost = _move_cost(hero, *target)
    if cost > hero.move_points:
        # nur Teilweg gehen — naehere uns linear
        dx = target[0] - hero.x
        dy = target[1] - hero.y
        steps = min(hero.move_points // 100, abs(dx) + abs(dy))
        for _ in range(steps):
            if abs(dx) > abs(dy):
                hero.x += 1 if dx > 0 else -1
                dx -= 1 if dx > 0 else -1
            elif dy != 0:
                hero.y += 1 if dy > 0 else -1
                dy -= 1 if dy > 0 else -1
        hero.move_points = 0
        return

    hero.x, hero.y = target
    hero.move_points -= cost

    # 4. Interaction am Zielpunkt
    _interact(state, player, hero, rng, units_by_faction)


def _interact(state: GameState, player: Player, hero: Hero, rng: bs.DeterministicRng, units_by_faction: dict[str, list[bs.Unit]]) -> None:
    # Mine?
    mine = next((m for m in state.unowned_mines if m.x == hero.x and m.y == hero.y), None)
    if mine is not None:
        mine.owner = player.slot
        state.unowned_mines.remove(mine)
        player.mines.append(mine)
        state.events.append(GameEvent(day=state.day, actor=player.faction,
                                     text=f"erobert {mine.resource}-Mine bei ({mine.x},{mine.y})"))
        return

    # Neutrales Monster?
    mon = next((m for m in state.neutral_monsters if m.x == hero.x and m.y == hero.y), None)
    if mon is not None:
        _fight_neutral(state, player, hero, mon, rng, units_by_faction)
        return

    # Gegner-Held?
    for other in state.players:
        if other.slot == player.slot or other.defeated:
            continue
        enemy_hero = next((h for h in other.heroes if h.x == hero.x and h.y == hero.y), None)
        if enemy_hero is not None:
            _fight_pvp(state, player, hero, other, enemy_hero, rng)
            return

    # Gegner-Stadt?
    for other in state.players:
        if other.slot == player.slot:
            continue
        enemy_town = next((t for t in other.towns if t.x == hero.x and t.y == hero.y), None)
        if enemy_town is not None:
            state.events.append(GameEvent(day=state.day, actor=player.faction,
                                         text=f"erobert {other.faction}-Stadt! ({enemy_town.x},{enemy_town.y})"))
            enemy_town.owner = player.slot
            other.towns.remove(enemy_town)
            player.towns.append(enemy_town)
            if not other.towns and not any(h.army for h in other.heroes):
                other.defeated = True
                state.events.append(GameEvent(day=state.day, actor=other.faction, text="besiegt."))
            return


def _fight_neutral(state: GameState, player: Player, hero: Hero, mon: mg.MapObject, rng: bs.DeterministicRng, units_by_faction: dict[str, list[bs.Unit]]) -> None:
    tier = mon.meta.get("tier", 1)
    pool = [u for u in units_by_faction.get("orkstaemme", []) if u.tier == tier]  # generische Monster
    if not pool:
        pool = [u for u in units_by_faction.get("orkstaemme", []) if u.tier == 1]
    unit = pool[0]
    enemy_stacks = [bs.Stack(unit=unit, count=max(1, 5 + tier * 3), top_hp=unit.hp, side=1)]
    hero_army_copy = [bs.Stack(unit=s.unit, count=s.count, top_hp=s.top_hp, side=0) for s in hero.army]
    outcome = bs.simulate_battle(hero_army_copy, enemy_stacks, rng, hero.stats, bs.Hero(name="Neutral"))
    if outcome == "side0":
        # Verluste zurueck in Hero-Armee schreiben
        hero.army = [s for s in hero_army_copy if s.alive]
        state.neutral_monsters.remove(mon)
        state.events.append(GameEvent(day=state.day, actor=player.faction,
                                     text=f"schlaegt Monster (T{tier} x{enemy_stacks[0].count}); Verluste: "
                                          f"{sum(s.count for s in hero_army_copy if s.alive)} lebend"))
    else:
        hero.army = []
        state.events.append(GameEvent(day=state.day, actor=player.faction,
                                     text=f"verliert gegen Monster-Stack T{tier}!"))
        if not any(p.heroes and any(h.army for h in p.heroes) for p in [player]) and not player.towns:
            player.defeated = True


def _fight_pvp(state: GameState, attacker: Player, hero_a: Hero, defender: Player, hero_b: Hero, rng: bs.DeterministicRng) -> None:
    a_copy = [bs.Stack(unit=s.unit, count=s.count, top_hp=s.top_hp, side=0) for s in hero_a.army]
    b_copy = [bs.Stack(unit=s.unit, count=s.count, top_hp=s.top_hp, side=1) for s in hero_b.army]
    outcome = bs.simulate_battle(a_copy, b_copy, rng, hero_a.stats, hero_b.stats)
    state.events.append(GameEvent(day=state.day, actor=f"{attacker.faction} vs {defender.faction}",
                                 text=f"PvP-Kampf: {outcome}"))
    if outcome == "side0":
        hero_a.army = [s for s in a_copy if s.alive]
        hero_b.army = []
        defender.heroes.remove(hero_b)
        if not defender.heroes and not defender.towns:
            defender.defeated = True
    elif outcome == "side1":
        hero_b.army = [s for s in b_copy if s.alive]
        hero_a.army = []
        attacker.heroes.remove(hero_a)
        if not attacker.heroes and not attacker.towns:
            attacker.defeated = True


# ---------- Top-Level ----------


def advance_day(state: GameState, rng: bs.DeterministicRng, units_by_faction: dict[str, list[bs.Unit]]) -> None:
    for player in state.players:
        eco.tick_day(player.treasury, player.towns, player.mines, state.day, units_by_faction)
        for h in player.heroes:
            h.move_points = 1500

    for player in state.players:
        _step_player(state, player, rng, units_by_faction)

    state.day += 1


def winners(state: GameState) -> list[int]:
    alive = [p.slot for p in state.players if not p.defeated]
    return alive
