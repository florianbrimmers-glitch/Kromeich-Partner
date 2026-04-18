"""
Ressourcen-Buchhaltung, Stadt-Einkommen, Einheiten-Wachstum.

Reiner Python-Code, wird vom Simulator und vom Adventure-CLI verwendet.
Spiegelt scripts/core/Economy.cs (C#-Mirror kommt parallel).
"""
from __future__ import annotations

import dataclasses

RESOURCES = ("gold", "wood", "ore", "mercury", "sulfur", "crystal", "gems")


@dataclasses.dataclass
class Resources:
    gold: int = 0
    wood: int = 0
    ore: int = 0
    mercury: int = 0
    sulfur: int = 0
    crystal: int = 0
    gems: int = 0

    def add(self, other: "Resources") -> None:
        for r in RESOURCES:
            setattr(self, r, getattr(self, r) + getattr(other, r))

    def can_afford(self, cost: "Resources") -> bool:
        return all(getattr(self, r) >= getattr(cost, r) for r in RESOURCES)

    def subtract(self, cost: "Resources") -> None:
        for r in RESOURCES:
            setattr(self, r, getattr(self, r) - getattr(cost, r))

    def copy(self) -> "Resources":
        return Resources(**{r: getattr(self, r) for r in RESOURCES})

    def as_dict(self) -> dict[str, int]:
        return {r: getattr(self, r) for r in RESOURCES}


@dataclasses.dataclass
class Town:
    owner: int
    faction: str
    x: int
    y: int
    # Gebaeude: Einfache Stufen. 0 = nicht gebaut, N = Stufe N.
    # Jede Stufe +1 erhoeht den Wachstums-Multiplikator bei der naechsten Wochen-Rekrutierung.
    dwelling_levels: dict[int, int] = dataclasses.field(default_factory=dict)
    has_castle: bool = False
    has_capitol: bool = False
    # Verfuegbare Einheiten im Dwelling (angesammelt pro Woche)
    available_units: dict[str, int] = dataclasses.field(default_factory=dict)

    def daily_income(self) -> Resources:
        gold = 500 if self.has_capitol else (1000 if self.has_castle else 250)
        return Resources(gold=gold)


@dataclasses.dataclass
class Mine:
    owner: int | None
    resource: str  # "gold" | "wood" | "ore" | "crystal" | "gems" | "sulfur" | "mercury"
    x: int
    y: int

    def daily_income(self) -> Resources:
        out = Resources()
        if self.owner is None:
            return out
        amount = 1000 if self.resource == "gold" else 1
        setattr(out, self.resource, amount)
        return out


WEEKLY_GROWTH_BY_TIER = {1: 22, 2: 12, 3: 7, 4: 4, 5: 3, 6: 2, 7: 1}


def apply_weekly_growth(town: Town, units_by_faction: dict[str, list]) -> None:
    """Erhoeht available_units-Counts gemaess Tier-Standard-Growth."""
    for unit in units_by_faction.get(town.faction, []):
        base = WEEKLY_GROWTH_BY_TIER.get(unit.tier, 1)
        # Jede gebaute Dwelling-Stufe erhoeht Growth um 50 Prozent
        level = town.dwelling_levels.get(unit.tier, 0)
        mult = 1.0 + 0.5 * level
        amount = int(base * mult) if level > 0 else 0
        town.available_units[unit.id] = town.available_units.get(unit.id, 0) + amount


def tick_day(
    player_treasury: Resources,
    towns: list[Town],
    mines: list[Mine],
    day_index: int,
    units_by_faction: dict[str, list] | None = None,
) -> None:
    """Wendet Tages-Einkommen an. Wenn Wochenanfang (day_index % 7 == 1), auch Growth."""
    for t in towns:
        player_treasury.add(t.daily_income())
    for m in mines:
        player_treasury.add(m.daily_income())
    if day_index % 7 == 1 and units_by_faction is not None:
        for t in towns:
            apply_weekly_growth(t, units_by_faction)
