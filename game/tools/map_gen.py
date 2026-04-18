"""
Zonen-basierter Zufallskarten-Generator (angelehnt an HotA RMG).

Pipeline:
  1. Template laden (map_templates.json)
  2. Zonen-Kreise auf Raster projizieren
  3. Tiles fuellen: Zone-Inner = passable, Zwischenraum = Mountain/Water
  4. Verbindungen zwischen Zonen schneiden (Korridor-Tiles)
  5. Objekte platzieren: Town pro player_start, Mines/Artefakte/Monster in jeder Zone
  6. ASCII-Rendern (fuer CLI + Tests)

Determinismus: gleicher Seed -> identische Karte, byte-fuer-byte.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys
from typing import Iterable

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from balance_sim import DeterministicRng  # noqa: E402

# Tile-Codes fuer ASCII-Render
T_GRASS = "."
T_FOREST = "f"
T_MOUNTAIN = "^"
T_WATER = "~"
T_ROAD = "+"
T_TOWN = "T"
T_MINE = "M"
T_ARTIFACT = "A"
T_MONSTER = "X"
T_HERO = "H"


@dataclasses.dataclass
class Zone:
    id: str
    kind: str
    center: tuple[int, int]
    radius: int
    owner: int | None = None


@dataclasses.dataclass
class MapObject:
    x: int
    y: int
    kind: str
    owner: int | None = None
    meta: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class GeneratedMap:
    width: int
    height: int
    tiles: list[list[str]]
    objects: list[MapObject]
    seed: int
    template_id: str

    def render_ascii(self) -> str:
        grid = [row[:] for row in self.tiles]
        for o in self.objects:
            if 0 <= o.x < self.width and 0 <= o.y < self.height:
                glyph = {
                    "town": T_TOWN,
                    "mine": T_MINE,
                    "artifact": T_ARTIFACT,
                    "monster": T_MONSTER,
                    "hero": T_HERO,
                }.get(o.kind, "?")
                grid[o.y][o.x] = glyph
        return "\n".join("".join(row) for row in grid)


def _load_template(template_id: str) -> dict:
    data = json.loads((DATA_DIR / "map_templates.json").read_text(encoding="utf-8"))
    for t in data["templates"]:
        if t["id"] == template_id:
            return t
    raise ValueError(f"Template '{template_id}' nicht gefunden. Verfuegbar: {[t['id'] for t in data['templates']]}")


def _zones_from_template(tpl: dict) -> list[Zone]:
    out: list[Zone] = []
    for z in tpl["zones"]:
        out.append(Zone(
            id=z["id"],
            kind=z["kind"],
            center=tuple(z["center"]),  # type: ignore[arg-type]
            radius=int(z["radius"]),
            owner=z.get("owner"),
        ))
    return out


def _fill_base(width: int, height: int, zones: list[Zone], water_pct: int, rng: DeterministicRng) -> list[list[str]]:
    tiles = [[T_MOUNTAIN for _ in range(width)] for _ in range(height)]

    # Zonen-Inneres: Gras/Wald
    for y in range(height):
        for x in range(width):
            for z in zones:
                dx, dy = x - z.center[0], y - z.center[1]
                if dx * dx + dy * dy <= z.radius * z.radius:
                    tiles[y][x] = T_GRASS
                    if rng.next_double() < 0.18:
                        tiles[y][x] = T_FOREST
                    break

    # Wasser-Sprinkler (einfach, kein kontinentales Noise)
    if water_pct > 0:
        for _ in range((width * height * water_pct) // 100):
            x = rng.next_int(0, width - 1)
            y = rng.next_int(0, height - 1)
            if tiles[y][x] == T_MOUNTAIN:
                tiles[y][x] = T_WATER

    return tiles


def _carve_corridor(tiles: list[list[str]], a: tuple[int, int], b: tuple[int, int]) -> None:
    x, y = a
    while (x, y) != b:
        if x != b[0]:
            x += 1 if b[0] > x else -1
        elif y != b[1]:
            y += 1 if b[1] > y else -1
        if tiles[y][x] in (T_MOUNTAIN, T_WATER):
            tiles[y][x] = T_ROAD


def _apply_connections(tiles: list[list[str]], zones: dict[str, Zone], tpl: dict) -> None:
    for a_id, b_id in tpl.get("connections", []):
        a, b = zones[a_id], zones[b_id]
        _carve_corridor(tiles, a.center, b.center)


def _place_objects(
    zones: list[Zone],
    tiles: list[list[str]],
    tpl: dict,
    rng: DeterministicRng,
) -> list[MapObject]:
    objs: list[MapObject] = []
    richness = tpl.get("richness", "normal")
    mines_per_zone = {"poor": 1, "normal": 2, "rich": 3}[richness]
    artifacts_per_zone = {"poor": 0, "normal": 1, "rich": 2}[richness]
    monsters_per_zone = {"poor": 3, "normal": 4, "rich": 5}[richness]

    def rand_tile_in_zone(z: Zone, exclude: set[tuple[int, int]]) -> tuple[int, int] | None:
        for _ in range(60):
            x = z.center[0] + rng.next_int(-z.radius, z.radius)
            y = z.center[1] + rng.next_int(-z.radius, z.radius)
            if (x, y) in exclude:
                continue
            if 0 <= y < len(tiles) and 0 <= x < len(tiles[0]):
                if tiles[y][x] in (T_GRASS, T_FOREST, T_ROAD):
                    return x, y
        return None

    for z in zones:
        used: set[tuple[int, int]] = set()
        if z.kind == "player_start":
            # Stadt im Zentrum
            t = (z.center[0], z.center[1])
            objs.append(MapObject(x=t[0], y=t[1], kind="town", owner=z.owner))
            used.add(t)
            # Starthero eine Kachel daneben
            hx, hy = z.center[0] + 1, z.center[1]
            objs.append(MapObject(x=hx, y=hy, kind="hero", owner=z.owner))
            used.add((hx, hy))

        for _ in range(mines_per_zone):
            p = rand_tile_in_zone(z, used)
            if p:
                kind = ["gold", "wood", "ore", "crystal"][rng.next_int(0, 3)]
                objs.append(MapObject(x=p[0], y=p[1], kind="mine", meta={"resource": kind}, owner=z.owner))
                used.add(p)

        for _ in range(artifacts_per_zone):
            p = rand_tile_in_zone(z, used)
            if p:
                objs.append(MapObject(x=p[0], y=p[1], kind="artifact"))
                used.add(p)

        for _ in range(monsters_per_zone):
            p = rand_tile_in_zone(z, used)
            if p:
                tier = rng.next_int(1, 5) if z.kind == "neutral_rich" else rng.next_int(1, 3)
                objs.append(MapObject(x=p[0], y=p[1], kind="monster", meta={"tier": tier}))
                used.add(p)

    return objs


def generate(template_id: str, seed: int) -> GeneratedMap:
    tpl = _load_template(template_id)
    rng = DeterministicRng(seed)
    w, h = tpl["size"][0], tpl["size"][1]

    zones = _zones_from_template(tpl)
    tiles = _fill_base(w, h, zones, tpl.get("water_pct", 0), rng)
    _apply_connections(tiles, {z.id: z for z in zones}, tpl)
    objects = _place_objects(zones, tiles, tpl, rng)

    return GeneratedMap(width=w, height=h, tiles=tiles, objects=objects, seed=seed, template_id=template_id)


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Zufallskarten-Generator")
    p.add_argument("--template", default="duell_klein", help="Template-ID aus map_templates.json")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--render", action="store_true", help="ASCII-Render ausgeben")
    p.add_argument("--json", action="store_true", help="Maschinenlesbare Ausgabe")
    args = p.parse_args(argv)

    m = generate(args.template, args.seed)

    if args.json:
        json.dump({
            "template": m.template_id,
            "seed": m.seed,
            "size": [m.width, m.height],
            "objects": [dataclasses.asdict(o) for o in m.objects],
        }, sys.stdout, indent=2)
        print()
    else:
        print(f"Template: {m.template_id}  Seed: {m.seed}  Groesse: {m.width}x{m.height}")
        print(f"Objekte: {len(m.objects)}  ({sum(1 for o in m.objects if o.kind == 'town')} Staedte, "
              f"{sum(1 for o in m.objects if o.kind == 'mine')} Minen, "
              f"{sum(1 for o in m.objects if o.kind == 'artifact')} Artefakte, "
              f"{sum(1 for o in m.objects if o.kind == 'monster')} Monster-Stacks)")
        if args.render:
            print()
            print(m.render_ascii())
    return 0


if __name__ == "__main__":
    sys.exit(main())
