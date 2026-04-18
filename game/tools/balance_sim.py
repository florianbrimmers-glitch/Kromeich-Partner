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
    cost: dict[str, int]
    weekly_growth: int = 0

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
            cost=dict(obj.get("cost", {"gold": 100})),
            weekly_growth=obj.get("weekly_growth", 1),
        )


@dataclasses.dataclass
class Hero:
    name: str = "Held"
    att: int = 0
    def_: int = 0
    spell_power: int = 1
    knowledge: int = 1
    morale: int = 0   # -3..+3
    spell_points: int = 10
    spellbook: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Stack:
    unit: Unit
    count: int
    top_hp: int
    side: int
    bless: int = 0     # Runden bless aktiv -> dmg_lo = dmg_hi
    curse: int = 0     # Runden curse aktiv -> dmg_hi = dmg_lo
    haste: int = 0     # Runden +3 speed
    slow: int = 0      # Runden -3 speed
    weakness: int = 0  # Runden -3 att
    shield: int = 0    # Runden -15% melee dmg taken

    @property
    def alive(self) -> bool:
        return self.count > 0

    @property
    def total_hp(self) -> int:
        return (self.count - 1) * self.unit.hp + self.top_hp

    @property
    def effective_speed(self) -> int:
        return self.unit.speed + (3 if self.haste > 0 else 0) - (3 if self.slow > 0 else 0)

    def decay_buffs(self) -> None:
        for f in ("bless", "curse", "haste", "slow", "weakness", "shield"):
            v = getattr(self, f)
            if v > 0:
                setattr(self, f, v - 1)

    def take_damage(self, dmg: int) -> None:
        if dmg <= 0:
            return
        if self.shield > 0:
            dmg = max(1, int(dmg * 0.85))
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


def compute_damage(
    attacker: Stack,
    target: Stack,
    rng: DeterministicRng,
    hero_att_bonus: int = 0,
    hero_def_bonus: int = 0,
) -> int:
    # bless / curse / weakness modifizieren Wuerfelbereich und att
    lo = attacker.unit.dmg_lo if attacker.curse <= 0 else attacker.unit.dmg_lo
    hi = attacker.unit.dmg_hi if attacker.bless <= 0 else attacker.unit.dmg_hi
    if attacker.bless > 0:
        lo = hi = attacker.unit.dmg_hi
    elif attacker.curse > 0:
        lo = hi = attacker.unit.dmg_lo
    base = rng.next_int(lo, hi) if lo < hi else lo
    stack_dmg = base * attacker.count

    att = attacker.unit.att + hero_att_bonus - (3 if attacker.weakness > 0 else 0)
    defn = target.unit.def_ + hero_def_bonus
    diff = att - defn
    if diff > 0:
        mod = 1.0 + min(3.0, 0.05 * diff)
    elif diff < 0:
        mod = max(0.3, 1.0 + 0.025 * diff)
    else:
        mod = 1.0
    if "defense_ignore_25pct" in attacker.unit.abilities:
        mod *= 1.0 + 0.25 * max(0, defn) / max(1, att)
    elif "defense_ignore_40pct" in attacker.unit.abilities:
        mod *= 1.0 + 0.4 * max(0, defn) / max(1, att)
    if "double_attack" in attacker.unit.abilities:
        mod *= 1.5
    return max(1, int(stack_dmg * mod))


@dataclasses.dataclass
class TurnEvent:
    turn: int
    actor: str
    action: str


SPELL_EFFECTS: dict[str, dict] = {
    "bless":      {"target": "friendly", "duration": 3, "apply": lambda s: setattr(s, "bless", 3)},
    "haste":      {"target": "friendly", "duration": 3, "apply": lambda s: setattr(s, "haste", 3)},
    "shield":     {"target": "friendly", "duration": 3, "apply": lambda s: setattr(s, "shield", 3)},
    "slow":       {"target": "enemy",    "duration": 3, "apply": lambda s: setattr(s, "slow", 3)},
    "weakness":   {"target": "enemy",    "duration": 3, "apply": lambda s: setattr(s, "weakness", 3)},
    "curse":      {"target": "enemy",    "duration": 3, "apply": lambda s: setattr(s, "curse", 3)},
    "magic_arrow": {"target": "enemy",   "dmg": "10+10*power"},
    "fire_bolt":   {"target": "enemy",   "dmg": "15+15*power"},
    "implosion":   {"target": "enemy",   "dmg": "75+25*power", "sp_cost": 35},
}

SPELL_SP_COST = {
    "bless": 5, "haste": 6, "shield": 5, "slow": 8, "weakness": 5, "curse": 7,
    "magic_arrow": 5, "fire_bolt": 8, "implosion": 35,
}


def _eval_spell_damage(formula: str, power: int) -> int:
    # minimaler Parser fuer Strings wie "75+25*power"
    base, _, rest = formula.partition("+")
    per_power, _, _ = rest.partition("*power")
    return int(base) + int(per_power) * power


def _pick_spell_for_hero(hero: Hero, own_stacks: list[Stack], enemy_stacks: list[Stack]) -> str | None:
    # Greedy: wenn genug SP fuer Burst-Spell und Gegner-Stack > attacker-Stack-HP, cast.
    # Sonst: Bless auf groessten eigenen Stack wenn noch nicht geblessed.
    for spell in ("implosion", "fire_bolt", "magic_arrow"):
        if spell in hero.spellbook and hero.spell_points >= SPELL_SP_COST[spell]:
            return spell
    for spell in ("bless", "haste"):
        if spell in hero.spellbook and hero.spell_points >= SPELL_SP_COST[spell]:
            if any(getattr(s, spell.split("_")[0], 0) == 0 for s in own_stacks if s.alive):
                return spell
    for spell in ("slow", "weakness"):
        if spell in hero.spellbook and hero.spell_points >= SPELL_SP_COST[spell]:
            return spell
    return None


def _cast_spell(spell: str, hero: Hero, own_stacks: list[Stack], enemy_stacks: list[Stack], rng: DeterministicRng, log: list[TurnEvent]) -> None:
    cfg = SPELL_EFFECTS[spell]
    hero.spell_points -= SPELL_SP_COST[spell]
    if cfg.get("dmg"):
        target = max((s for s in enemy_stacks if s.alive), key=lambda s: s.total_hp, default=None)
        if target:
            dmg = _eval_spell_damage(cfg["dmg"], hero.spell_power)
            target.take_damage(dmg)
            log.append(TurnEvent(0, hero.name, f"wirkt {spell} auf {target.unit.id} ({dmg} Schaden)"))
    elif cfg.get("apply"):
        pool = own_stacks if cfg["target"] == "friendly" else enemy_stacks
        target = max((s for s in pool if s.alive), key=lambda s: s.count, default=None)
        if target:
            cfg["apply"](target)
            log.append(TurnEvent(0, hero.name, f"wirkt {spell} auf {target.unit.id}"))


def _maybe_morale_skip_or_extra(stack: Stack, hero_morale: int, rng: DeterministicRng, log: list[TurnEvent]) -> str:
    # HoMM3-Stil: +N Morale -> N*4 Prozent Chance Extra-Zug. -N -> N*3 Prozent Skip.
    if "undead" in stack.unit.abilities:
        return "normal"
    m = hero_morale
    if m > 0 and rng.next_double() < m * 0.04:
        log.append(TurnEvent(0, stack.unit.id, "hohe Moral! zusaetzlicher Zug"))
        return "extra"
    if m < 0 and rng.next_double() < abs(m) * 0.03:
        log.append(TurnEvent(0, stack.unit.id, "schlechte Moral! Zug ausgelassen"))
        return "skip"
    return "normal"


def simulate_battle(
    side0: list[Stack],
    side1: list[Stack],
    rng: DeterministicRng,
    hero0: Hero | None = None,
    hero1: Hero | None = None,
    log: list[TurnEvent] | None = None,
) -> str:
    if not side0 or not side1:
        return "draw"
    hero0 = hero0 or Hero()
    hero1 = hero1 or Hero()
    _log = log if log is not None else []

    for turn in range(1, 101):
        # Helden-Spellphase (1x pro Runde, zuerst der schnellere Held)
        for side, hero, own, enemy in [
            (0, hero0, side0, side1), (1, hero1, side1, side0),
        ]:
            spell = _pick_spell_for_hero(hero, own, enemy)
            if spell:
                _cast_spell(spell, hero, own, enemy, rng, _log)

        order = sorted(
            (s for s in side0 + side1 if s.alive),
            key=lambda s: (-s.effective_speed, -s.count),
        )

        for attacker in order:
            if not attacker.alive:
                continue
            morale_state = _maybe_morale_skip_or_extra(
                attacker, hero0.morale if attacker.side == 0 else hero1.morale, rng, _log,
            )
            if morale_state == "skip":
                continue
            actions = 2 if morale_state == "extra" else 1

            for _ in range(actions):
                if not attacker.alive:
                    break
                pool = side1 if attacker.side == 0 else side0
                alive_targets = [s for s in pool if s.alive]
                if not alive_targets:
                    break
                target = max(
                    alive_targets,
                    key=lambda t: (t.unit.dmg_lo + t.unit.dmg_hi) * t.count / max(1, attacker.total_hp),
                )
                h_att = (hero0 if attacker.side == 0 else hero1).att
                h_def = (hero1 if attacker.side == 0 else hero0).def_
                dmg = compute_damage(attacker, target, rng, h_att, h_def)
                target.take_damage(dmg)
                _log.append(TurnEvent(turn, attacker.unit.id, f"-> {target.unit.id}: {dmg} dmg"))
                if "no_retaliation" not in target.unit.abilities and target.alive:
                    th_att = (hero1 if attacker.side == 0 else hero0).att
                    th_def = (hero0 if attacker.side == 0 else hero1).def_
                    retal = compute_damage(target, attacker, rng, th_att, th_def) // 2
                    attacker.take_damage(retal)

        for s in side0 + side1:
            s.decay_buffs()

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

def build_army(units_of_faction: list[Unit], week: int, side: int, start_gold: int = 10000) -> list[Stack]:
    """Baut eine Test-Armee gemaess wirklichen Unit-Kosten.

    Budget: start_gold + 2500*(week-1). Sekundaer-Ressourcen bewusst knapp
    gehalten (crystal/gems/sulfur/mercury je 4 + week-1), damit T7-spam
    limitiert ist wie im Original.
    """
    by_tier = sorted(units_of_faction, key=lambda u: -u.tier)
    purse = {
        "gold":    start_gold + 2500 * (week - 1),
        "wood":    10 + 3 * (week - 1),
        "ore":     10 + 3 * (week - 1),
        "mercury": 4 + (week - 1),
        "sulfur":  4 + (week - 1),
        "crystal": 4 + (week - 1),
        "gems":    4 + (week - 1),
    }
    stacks: list[Stack] = []
    for u in by_tier:
        available = u.weekly_growth * week
        # Wie viele sind mit Gold und allen Nebenressourcen kaufbar?
        max_buy = available
        for res, cost in u.cost.items():
            if cost > 0:
                max_buy = min(max_buy, purse.get(res, 0) // cost)
        if max_buy <= 0:
            continue
        for res, cost in u.cost.items():
            purse[res] = purse.get(res, 0) - cost * max_buy
        stacks.append(Stack(unit=u, count=max_buy, top_hp=u.hp, side=side))
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


def run_robust_matchup(
    units_by_faction: dict[str, list[Unit]],
    a: str,
    b: str,
    runs_per_seed: int,
    weeks: list[int],
    seeds: list[int],
) -> dict:
    """Aggregiert Winrates ueber mehrere Seeds UND mehrere Wochen.

    Ergebnis zeigt Mittelwert plus Spannweite (min/max), damit wir
    sehen ob ein Matchup seed-sensitiv ist.
    """
    per_week: dict[int, list[float]] = {w: [] for w in weeks}
    for week in weeks:
        for seed in seeds:
            wins_a = wins_b = draws = 0
            for i in range(runs_per_seed):
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
            total = max(1, runs_per_seed - draws)
            per_week[week].append(wins_a / total)
    all_rates = [r for rates in per_week.values() for r in rates]
    return {
        "a": a, "b": b,
        "winrate_a_mean": sum(all_rates) / len(all_rates),
        "winrate_a_min":  min(all_rates),
        "winrate_a_max":  max(all_rates),
        "per_week_mean": {w: sum(rs) / len(rs) for w, rs in per_week.items()},
        "seeds": seeds,
        "weeks": weeks,
        "runs_per_seed": runs_per_seed,
    }


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Balance-Simulator")
    p.add_argument("--matchups", default="all", help="'all' oder 'fac_a:fac_b'")
    p.add_argument("--runs", type=int, default=1000)
    p.add_argument("--week", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--robust", action="store_true",
                   help="Multi-Seed (10) und Multi-Woche (2,4,6) Aggregation")
    p.add_argument("--weeks", default="2,4,6", help="Komma-Liste fuer --robust")
    p.add_argument("--seeds", type=int, default=10, help="Anzahl Seeds fuer --robust")
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

    if args.robust:
        weeks = [int(w) for w in args.weeks.split(",")]
        seeds = [args.seed + 1000 * k for k in range(args.seeds)]
        runs_per_seed = max(1, args.runs // args.seeds)
        results = [
            run_robust_matchup(factions, a, b, runs_per_seed, weeks, seeds)
            for a, b in pairs
        ]
        if args.json:
            json.dump(results, sys.stdout, indent=2)
            print()
        else:
            print(f"Balance-Simulator ROBUST  |  Wochen {weeks}  |  {args.seeds} Seeds x {runs_per_seed} Runs")
            print("-" * 80)
            for r in results:
                mean = r["winrate_a_mean"] * 100
                lo = r["winrate_a_min"] * 100
                hi = r["winrate_a_max"] * 100
                flag = "OK" if 45 <= mean <= 55 else ("ok" if 40 <= mean <= 60 else "!!")
                pw = " ".join(f"W{w}={v*100:.0f}" for w, v in r["per_week_mean"].items())
                print(f"[{flag}] {r['a']:12} vs {r['b']:12}  mean {mean:5.1f}  (range {lo:4.0f}-{hi:4.0f})  {pw}")
            print("-" * 80)
            print("Ziel: mean 45-55 Prozent (OK). 40-60 Prozent = akzeptabel (ok). Sonst '!!'.")
        return 0

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
