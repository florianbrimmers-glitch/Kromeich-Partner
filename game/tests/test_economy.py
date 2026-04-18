"""Tests fuer economy.py: Ressourcen-Arithmetik, Tages-Tick, Growth."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import balance_sim as bs  # noqa: E402
import economy as eco     # noqa: E402


def test_resources_add_and_subtract() -> None:
    a = eco.Resources(gold=100, wood=5)
    a.add(eco.Resources(gold=50, ore=3))
    assert a.gold == 150
    assert a.wood == 5
    assert a.ore == 3
    a.subtract(eco.Resources(gold=20, wood=2))
    assert a.gold == 130
    assert a.wood == 3


def test_resources_can_afford() -> None:
    purse = eco.Resources(gold=1000, wood=5, crystal=2)
    assert purse.can_afford(eco.Resources(gold=500, wood=3))
    assert purse.can_afford(eco.Resources(gold=1000, crystal=2))
    assert not purse.can_afford(eco.Resources(gold=2000))
    assert not purse.can_afford(eco.Resources(crystal=3))


def test_resources_copy_is_independent() -> None:
    a = eco.Resources(gold=100)
    b = a.copy()
    b.gold = 999
    assert a.gold == 100


def test_town_daily_income_scales_with_buildings() -> None:
    t = eco.Town(owner=0, faction="menschen", x=0, y=0)
    assert t.daily_income().gold == 250
    t.has_castle = True
    assert t.daily_income().gold == 1000
    t.has_capitol = True
    assert t.daily_income().gold == 500  # capitol ersetzt castle-Bonus im MVP-Modell


def test_mine_income_only_when_owned() -> None:
    m = eco.Mine(owner=None, resource="gold", x=0, y=0)
    assert m.daily_income().gold == 0
    m.owner = 1
    assert m.daily_income().gold == 1000
    crystal_mine = eco.Mine(owner=1, resource="crystal", x=0, y=0)
    assert crystal_mine.daily_income().crystal == 1
    assert crystal_mine.daily_income().gold == 0


def test_apply_weekly_growth_only_for_built_dwellings() -> None:
    units = bs.load_units()
    by_f: dict[str, list[bs.Unit]] = {}
    for u in units:
        by_f.setdefault(u.faction, []).append(u)

    town = eco.Town(owner=0, faction="menschen", x=0, y=0, dwelling_levels={1: 1, 2: 1})
    eco.apply_weekly_growth(town, by_f)
    t1_units = [u for u in by_f["menschen"] if u.tier == 1]
    t3_units = [u for u in by_f["menschen"] if u.tier == 3]
    assert t1_units and town.available_units.get(t1_units[0].id, 0) > 0
    # T3 ohne Dwelling -> 0
    assert town.available_units.get(t3_units[0].id, 0) == 0


def test_tick_day_at_week_start_triggers_growth() -> None:
    units = bs.load_units()
    by_f: dict[str, list[bs.Unit]] = {}
    for u in units:
        by_f.setdefault(u.faction, []).append(u)

    purse = eco.Resources(gold=0)
    town = eco.Town(owner=0, faction="menschen", x=0, y=0, dwelling_levels={1: 1}, has_castle=True)
    # Tag 1 = Wochenanfang -> Growth + Income
    eco.tick_day(purse, [town], [], day_index=1, units_by_faction=by_f)
    assert purse.gold == 1000  # Castle-Income
    t1_unit = next(u for u in by_f["menschen"] if u.tier == 1)
    assert town.available_units[t1_unit.id] > 0
    # Tag 2 kein Wochenanfang -> nur Income, Count bleibt stabil
    before = town.available_units[t1_unit.id]
    eco.tick_day(purse, [town], [], day_index=2, units_by_faction=by_f)
    assert purse.gold == 2000
    assert town.available_units[t1_unit.id] == before
