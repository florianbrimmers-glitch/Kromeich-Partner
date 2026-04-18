"""
End-to-End-CLI: spielt eine komplette Partie auf einer Zufallskarte.

Beispiel:
    python game/tools/play_adventure.py --template duell_klein --seed 42 --turns 40

Deterministisch: gleicher Seed -> identischer Spielverlauf.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import balance_sim as bs  # noqa: E402
import map_gen as mg      # noqa: E402
import turn_engine as te  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Adventure-Loop-CLI")
    p.add_argument("--template", default="duell_klein")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--turns", type=int, default=30)
    p.add_argument("--factions", default="menschen,totenreich",
                   help="Kommaseparierte Fraktionen pro Slot")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    units = bs.load_units()
    by_f: dict[str, list[bs.Unit]] = {}
    for u in units:
        by_f.setdefault(u.faction, []).append(u)

    factions = [f.strip() for f in args.factions.split(",")]
    for f in factions:
        if f not in by_f:
            print(f"Unbekannte Fraktion: {f}. Verfuegbar: {sorted(by_f)}", file=sys.stderr)
            return 2

    gen_map = mg.generate(args.template, args.seed)
    state = te.build_initial_state(gen_map, factions, by_f)

    print(f"=== Kromeich Heroes Adventure ===")
    print(f"Map: {args.template}  Seed: {args.seed}  Runden: {args.turns}")
    print(f"Spieler: {', '.join(f'Slot {p.slot}: {p.faction}' for p in state.players)}")
    print()

    rng = bs.DeterministicRng(args.seed)
    for _ in range(args.turns):
        te.advance_day(state, rng, by_f)
        alive_players = [p for p in state.players if not p.defeated]
        if len(alive_players) <= 1:
            break

    if args.verbose:
        last_day = 0
        for ev in state.events:
            if ev.day != last_day:
                print(f"\n--- Tag {ev.day}  (Woche {(ev.day-1)//7+1}, Tag {((ev.day-1)%7)+1}) ---")
                last_day = ev.day
            print(f"  {ev.actor}: {ev.text}")
        print()

    # Zusammenfassung
    print("=" * 60)
    print(f"Stand nach Tag {state.day - 1}:")
    for player in state.players:
        status = "BESIEGT" if player.defeated else "aktiv"
        army_sum = sum(sum(s.count for s in h.army) for h in player.heroes)
        mines = len(player.mines)
        gold = player.treasury.gold
        print(f"  Slot {player.slot} ({player.faction}, {status}): "
              f"{len(player.towns)} Staedte, {len(player.heroes)} Helden, "
              f"{army_sum} Einheiten, {mines} Minen, {gold} Gold")

    # Event-Statistik
    if state.events:
        kinds = Counter()
        for ev in state.events:
            if "rekrutiert" in ev.text:
                kinds["recruit"] += 1
            elif "erobert" in ev.text and "Mine" in ev.text:
                kinds["mine_capture"] += 1
            elif "erobert" in ev.text and "Stadt" in ev.text:
                kinds["town_capture"] += 1
            elif "Monster" in ev.text:
                kinds["monster_fight"] += 1
            elif "PvP" in ev.text:
                kinds["pvp_fight"] += 1
        print()
        print("Event-Statistik:")
        for k, v in kinds.most_common():
            print(f"  {k:20s} {v}")

    survivors = [p.slot for p in state.players if not p.defeated]
    print()
    print(f"Ueberlebende: Slot(s) {survivors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
