"""
Monte-Carlo-Balance-Simulator fuer Kromeich Heroes.

Lest game/data/*.json und simuliert Fraktion-vs-Fraktion-Matchups.
Spiegelt die Schadensformel aus scripts/core/Battle.cs (deterministisch
bei gleicher Seed). Wenn Battle.cs geaendert wird, muss dieses Skript
parallel aktualisiert werden.

Verwendung:
    python balance_sim.py --matchups=all --runs=2000
    python balance_sim.py --matchups=menschen:totenreich --runs=5000 --week=4
    python balance_sim.py --seed=42 --json  # maschinenlesbare Ausgabe

Zielkorridor (in balance_notes.md festgehalten): jede Fraktion 45-55 Prozent
Winrate gegen jede andere.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys
from typing import Iterable

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"

# -------- xorshift64: identisch zu scripts/core/DeterministicRng.cs --------


class DeterministicRng:
    def __init__(self, seed: int) -> None:
        self.state = seed if seed != 0 else 0x9E3779B97F4A7C15

    def _next(self) -> int:
        x = self.state & 0xFFFFFFFFFFFFFFFF
        x ^= (x << 13) & 0xFFFFFFFFFFFFFFFF
        x ^= (x >> 7) & 0xFFFFFFFFFFFFFFFF
        x ^= (x << 17) & 0xFFFFFFFFFFFFFFFF
        self.state = x
        return x

    def next_int(self, lo: int, hi: int) -> int:
        return lo + self._next() % (hi - lo + 1)

    def next_double(self) -> float:
        return (self._next() >> 11) / (1 << 53)


# -------- Datenmodell --------


@dataclasses.dataclass
class Unit:
    id: str
    faction: str
    tier: int
    att: int
    def_: int
    hp: int
    dmg_lo: int
    dmg_hi: int
    speed: int
    shots: int
    abilities: list[str]

    @classmethod
    def from_json(cls, obj: dict) -> "Unit":
        s = obj["stats"]
        return cls(
            id=obj["id"],
            faction=obj["faction"],
            tier=obj["tier"],
            att=s["att"],
            def_=s["def"],
            hp=s["hp"],
            dmg_lo=s["dmg"][0],
            dmg_hi=s["dmg"][1],
            speed=s["speed"],
            shots=s.get("shots", 0),
            abilities=obj.get("abilities", []),
        )


@dataclasses.dataclass
class Stack:
    unit: Unit
    count: int
    top_hp: int
    side: int

    @property
    def alive(self) -> bool:
        return self.count > 0

    @property
    def total_hp(self) -> int:
        return (self.count - 1) * self.unit.hp + self.top_hp

    def take_damage(self, dmg: int) -> None:
        if dmg <= 0:
            return
        total = self.total_hp - dmg
        if total <= 0:
            self.count = 0
            self.top_hp = 0
            return
        max_hp = self.unit.hp
        self.count = ((total - 1) // max_hp) + 1
        rem = total % max_hp
        self.top_hp = max_hp if rem == 0 else rem


# -------- Kampf --------


def compute_damage(attacker: Stack, target: Stack, rng: DeterministicRng) -> int:
    base = rng.next_int(attacker.unit.dmg_lo, attacker.unit.dmg_hi)
    stack_dmg = base * attacker.count
    diff = attacker.unit.att - target.unit.def_
    if diff > 0:
        mod = 1.0 + min(3.0, 0.05 * diff)
    elif diff < 0:
        mod = max(0.3, 1.0 + 0.025 * diff)
    else:
        mod = 1.0
    if "defense_ignore_40pct" in attacker.unit.abilities:
        mod *= 1.0 + 0.4 * max(0, target.unit.def_) / max(1, attacker.unit.att)
    if "double_attack" in attacker.unit.abilities:
        mod *= 1.5
    return max(1, int(stack_dmg * mod))


def simulate_battle(side0: list[Stack], side1: list[Stack], rng: DeterministicRng) -> str:
    if not side0 or not side1:
        return "draw"
    for _turn in range(100):
        order = sorted(
            (s for s in side0 + side1 if s.alive),
            key=lambda s: (-s.unit.speed, -s.count),
        )
        for attacker in order:
            if not attacker.alive:
                continue
            pool = side1 if attacker.side == 0 else side0
            alive_targets = [s for s in pool if s.alive]
            if not alive_targets:
                break
            target = max(
                alive_targets,
                key=lambda t: (t.unit.dmg_lo + t.unit.dmg_hi) * t.count / max(1, attacker.total_hp),
            )
            dmg = compute_damage(attacker, target, rng)
            target.take_damage(dmg)
            if "no_retaliation" not in target.unit.abilities and target.alive:
                retal = compute_damage(target, attacker, rng) // 2
                attacker.take_damage(retal)
        s0 = any(s.alive for s in side0)
        s1 = any(s.alive for s in side1)
        if not s0 and not s1:
            return "draw"
        if not s0:
            return "side1"
        if not s1:
            return "side0"
    return "draw"


# -------- Armee-Bau: Wochen-basiert --------

WEEKLY_GROWTH_DEFAULTS = {1: 22, 2: 12, 3: 7, 4: 4, 5: 3, 6: 2, 7: 1}


def build_army(units_of_faction: list[Unit], week: int, side: int, start_gold: int = 10000) -> list[Stack]:
    # Einfacher Ansatz: kauft von T7 abwaerts, solange Gold reicht;
    # Anzahl = weekly_growth * (week Wochen), keine Upgrades.
    by_tier = sorted(units_of_faction, key=lambda u: -u.tier)
    gold = start_gold + 2000 * (week - 1)
    stacks: list[Stack] = []
    for u in by_tier:
        available = WEEKLY_GROWTH_DEFAULTS.get(u.tier, 1) * week
        cost_guess = {1: 60, 2: 120, 3: 250, 4: 500, 5: 800, 6: 1500, 7: 3000}.get(u.tier, 500)
        buyable = min(available, gold // max(1, cost_guess))
        if buyable <= 0:
            continue
        gold -= buyable * cost_guess
        stacks.append(Stack(unit=u, count=buyable, top_hp=u.hp, side=side))
    return stacks


# -------- Runner --------


def load_units() -> list[Unit]:
    path = DATA_DIR / "units.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Unit.from_json(u) for u in data["units"]]


def run_matchup(
    units_by_faction: dict[str, list[Unit]],
    a: str,
    b: str,
    runs: int,
    week: int,
    seed: int,
) -> dict:
    wins_a = wins_b = draws = 0
    for i in range(runs):
        rng = DeterministicRng(seed + i)
        side0 = build_army(units_by_faction[a], week, side=0)
        side1 = build_army(units_by_faction[b], week, side=1)
        out = simulate_battle(side0, side1, rng)
        if out == "side0":
            wins_a += 1
        elif out == "side1":
            wins_b += 1
        else:
            draws += 1
    total = max(1, runs - draws)
    return {
        "a": a,
        "b": b,
        "winrate_a": wins_a / total,
        "winrate_b": wins_b / total,
        "draws": draws,
        "runs": runs,
    }


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Balance-Simulator")
    p.add_argument("--matchups", default="all", help="'all' oder 'fac_a:fac_b'")
    p.add_argument("--runs", type=int, default=1000)
    p.add_argument("--week", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--json", action="store_true", help="Maschinenlesbare Ausgabe")
    args = p.parse_args(argv)

    units = load_units()
    factions: dict[str, list[Unit]] = {}
    for u in units:
        factions.setdefault(u.faction, []).append(u)

    pairs: list[tuple[str, str]] = []
    if args.matchups == "all":
        keys = sorted(factions.keys())
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                pairs.append((a, b))
    else:
        a, b = args.matchups.split(":")
        pairs.append((a.strip(), b.strip()))

    results = [run_matchup(factions, a, b, args.runs, args.week, args.seed) for a, b in pairs]

    if args.json:
        json.dump(results, sys.stdout, indent=2)
        print()
    else:
        print(f"Balance-Simulator  |  Woche {args.week}  |  {args.runs} Runs/Matchup  |  Seed {args.seed}")
        print("-" * 72)
        for r in results:
            wa = r["winrate_a"] * 100
            wb = r["winrate_b"] * 100
            flag = "OK" if 45 <= wa <= 55 else "!!"
            print(f"[{flag}] {r['a']:12} vs {r['b']:12}  {wa:5.1f} Prozent  :  {wb:5.1f} Prozent   (Draws: {r['draws']})")
        print("-" * 72)
        print("Ziel: Winrate 45-55 Prozent. '!!' = out of range -> balance_notes.md konsultieren.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
