"""
CLI-Kampf fuer die Kommandozeile. Spielt einen deterministischen Kampf
zwischen zwei Fraktionen und druckt das Turn-Log.

Beispiele:
    python game/tools/play_battle.py --a menschen --b totenreich --week 4 --seed 42
    python game/tools/play_battle.py --a waldvolk --b orkstaemme --spells bless,haste,slow
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import balance_sim as bs  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CLI-Kampf")
    p.add_argument("--a", default="menschen", help="Fraktion A (Seite 0)")
    p.add_argument("--b", default="totenreich", help="Fraktion B (Seite 1)")
    p.add_argument("--week", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--hero-a-att", type=int, default=3)
    p.add_argument("--hero-a-def", type=int, default=2)
    p.add_argument("--hero-a-power", type=int, default=2)
    p.add_argument("--hero-a-sp", type=int, default=30)
    p.add_argument("--hero-b-att", type=int, default=3)
    p.add_argument("--hero-b-def", type=int, default=2)
    p.add_argument("--hero-b-power", type=int, default=2)
    p.add_argument("--hero-b-sp", type=int, default=30)
    p.add_argument("--spells", default="bless,haste,slow,weakness,magic_arrow",
                   help="Kommaseparierte Spellbook fuer beide Helden")
    p.add_argument("--verbose", action="store_true", help="Alle Turn-Events loggen")
    args = p.parse_args(argv)

    units = bs.load_units()
    by_f: dict[str, list[bs.Unit]] = {}
    for u in units:
        by_f.setdefault(u.faction, []).append(u)

    if args.a not in by_f or args.b not in by_f:
        print(f"Fehler: Fraktion unbekannt. Verfuegbar: {sorted(by_f)}", file=sys.stderr)
        return 2

    rng = bs.DeterministicRng(args.seed)
    side0 = bs.build_army(by_f[args.a], week=args.week, side=0)
    side1 = bs.build_army(by_f[args.b], week=args.week, side=1)

    spellbook = [s.strip() for s in args.spells.split(",") if s.strip()]
    hero_a = bs.Hero(name=f"Held-{args.a}", att=args.hero_a_att, def_=args.hero_a_def,
                    spell_power=args.hero_a_power, spell_points=args.hero_a_sp, spellbook=spellbook)
    hero_b = bs.Hero(name=f"Held-{args.b}", att=args.hero_b_att, def_=args.hero_b_def,
                    spell_power=args.hero_b_power, spell_points=args.hero_b_sp, spellbook=spellbook)

    print(f"=== Kampf: {args.a} vs {args.b}  (Woche {args.week}, Seed {args.seed}) ===")
    print()
    print(f"{args.a}-Armee:")
    for s in side0:
        print(f"  {s.count:5d}x {s.unit.id:20s} (T{s.unit.tier}, HP {s.unit.hp})")
    print(f"{args.b}-Armee:")
    for s in side1:
        print(f"  {s.count:5d}x {s.unit.id:20s} (T{s.unit.tier}, HP {s.unit.hp})")
    print()

    log: list[bs.TurnEvent] = []
    outcome = bs.simulate_battle(side0, side1, rng, hero_a, hero_b, log)

    if args.verbose:
        last_turn = 0
        for ev in log:
            if ev.turn != last_turn:
                print(f"\n--- Runde {ev.turn} ---")
                last_turn = ev.turn
            print(f"  {ev.actor}: {ev.action}")
        print()

    side0_survivors = sum(s.count for s in side0)
    side1_survivors = sum(s.count for s in side1)
    print(f"Ergebnis: {outcome}")
    print(f"Ueberlebende {args.a}: {side0_survivors}")
    print(f"Ueberlebende {args.b}: {side1_survivors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
