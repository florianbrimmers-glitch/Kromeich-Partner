#!/usr/bin/env python3
"""Kartenobjekte der Weltkarte im Heroes-4-Stil (It. 77).

    /opt/blender/blender -b --factory-startup -noaudio \
        --python tools/gen_mapobj3d.py -- game/assets/models/mapobj.glb

Die zehn Objekte (Mine, Truhe, Haufen, vier Schreine, Brunnen,
Lehrmeister, Windmuehle) waren in world.glb (gen_models.py, It. 53) ein
paar gestapelte Quader. Neben der neuen Karte mit Waeldern, Seen und Burgen
stachen sie als Klotzwerk heraus. Gebaut wird mit dem Architektur-Baukasten
der Stadt (city_kit.py), damit Karte und Stadt dieselbe Bausprache haben.

GLEICHE NAMEN WIE IN world.glb: WorldMap3D laedt diese Datei NACH world.glb,
die neuen Modelle ersetzen also die alten, ohne dass sich an der Zuordnung
(WorldMapScreen.MAP3D_OBJECT_MODEL) etwas aendert. world.glb bleibt fuer die
2D-gleichen Altteile (Marker, Deko) unveraendert.

MASSSTAB: eine Kachel ist 1.0; jedes Objekt bleibt innerhalb von 0.9, damit
erkennbar ist, auf welchem Feld es steht (test_world3d prueft das).
"""

import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_kit as bk  # noqa: E402
import city_kit as ck  # noqa: E402
import figures as fg  # noqa: E402

rad = math.radians

STONE = "#b3aa98"
STONE_DARK = "#7d7566"
WOOD = "#6b4f30"
WOOD_DARK = "#4a3624"
ROOF = "#3e5a8a"
ROOF_ROWS = "#30496f"
RED = "#8a2f26"
GOLD = "#d8b44a"
GLASS = "#2a3240"
GLOW = "#ffcf7a"


def obj(name, parts):
    ob = bk.merge(name, parts)
    bpy.ops.object.shade_smooth_by_angle(angle=rad(35))
    return ob


def mine():
    """Stollen im Fels: Felshuegel, Holzrahmen, Lore mit Erz, Schienen."""
    out = []
    for k, (x, y, r) in enumerate(((0.0, 0.10, 0.34), (-0.22, 0.16, 0.24),
                                   (0.24, 0.14, 0.22))):
        out.append(fg.lump((x, y, 0.08), r, "#7a7468", strength=0.25, squash=0.85, seed=3 + k))
    out.append(ck.block(0.20, 0.06, 0.22, "#1a1612", 0, -0.14, 0.0, bevel=0.0))
    for sx in (-1, 1):
        out.append(ck.block(0.035, 0.05, 0.26, WOOD, sx * 0.12, -0.17, 0.0, bevel=0.0))
    out.append(ck.block(0.30, 0.06, 0.04, WOOD, 0, -0.17, 0.25, bevel=0.0))
    for sx in (-1, 1):
        out.append(ck.block(0.012, 0.30, 0.012, "#4a4a4e", sx * 0.05, -0.32, 0.0, bevel=0.0))
    out.append(ck.block(0.14, 0.10, 0.07, WOOD_DARK, 0.0, -0.36, 0.02))
    for k in range(4):
        out.append(fg.ball(0.03, (-0.03 + k * 0.025, -0.36 + (k % 2) * 0.02, 0.10),
                           "#c9a24a" if k % 2 else "#5a5e66", subdiv=1))
    out += ck.banner(0.22, -0.18, 0.15, 0.30, RED, GOLD, w=0.10, h=0.12)
    return obj("obj_mine", out)


def treasure():
    """Truhe mit gewoelbtem Deckel, Beschlaegen und Goldmuenzen."""
    out = [ck.block(0.32, 0.20, 0.14, WOOD, 0, 0, 0.0)]
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.10, depth=0.32,
                                        location=(0, 0.0, 0.14), rotation=(0, rad(90), 0))
    lid = bpy.context.active_object
    bk._bake(lid)
    lid.data.materials.append(bk.material("k" + WOOD_DARK, WOOD_DARK))
    out.append(lid)
    for sx in (-0.12, 0.12):
        out.append(ck.block(0.03, 0.22, 0.26, GOLD, sx, 0, 0.0, bevel=0.0))
    out.append(ck.block(0.05, 0.02, 0.06, GOLD, 0, -0.11, 0.09, bevel=0.0))
    for k in range(7):
        a = k * 0.9
        out.append(ck.cyl(0.03, 0.012, GOLD, math.cos(a) * 0.22, -0.20 + math.sin(a) * 0.06,
                          0.0, verts=10))
    return obj("obj_treasure", out)


def pile():
    """Haufen: Bretter, Erzbrocken, Kisten - Rohstoffe zum Einsammeln."""
    out = []
    for k in range(4):
        out.append(bk.box((0.20, 0.03, 0.025), (0.02 * k - 0.05, -0.05 + k * 0.05, 0.025 + 0.05 * (k % 2)),
                          WOOD, 0.005, rot=(0, 0, rad(10 * k - 15))))
    out.append(ck.block(0.14, 0.14, 0.12, WOOD_DARK, 0.18, 0.10, 0.0))
    out.append(ck.block(0.10, 0.10, 0.08, WOOD, 0.18, 0.10, 0.12))
    for k in range(5):
        out.append(fg.lump((-0.18 + k * 0.05, 0.14 - (k % 2) * 0.05, 0.04), 0.06,
                           "#6a6e76" if k % 2 else "#8a7a5a", strength=0.3, seed=k))
    return obj("obj_pile", out)


def shrine_att():
    """Soeldnerlager: zwei Zelte, Waffenstaender, Lagerfeuer, Banner."""
    out = []
    for k, (x, y, c) in enumerate(((-0.18, 0.08, RED), (0.16, 0.14, "#a08850"))):
        out.append(ck.cone_roof(0.17, 0.30, c, x, y, 0.0, verts=6))
        out.append(ck.block(0.06, 0.02, 0.12, "#1a1612", x, y - 0.15, 0.0, bevel=0.0))
    out.append(ck.block(0.24, 0.03, 0.03, WOOD, 0.05, -0.22, 0.16, bevel=0.0))
    for sx in (-1, 1):
        out.append(ck.block(0.025, 0.025, 0.18, WOOD, 0.05 + sx * 0.11, -0.22, 0.0, bevel=0.0))
    for k in range(3):
        out.append(fg.tube("spear", [(-0.03 + k * 0.08, -0.20, 0.0), (-0.03 + k * 0.08, -0.24, 0.30)],
                           [0.006, 0.006], WOOD_DARK))
        out.append(bk.cone(0.015, 0.05, (-0.03 + k * 0.08, -0.245, 0.32), "#c9d2db", verts=4))
    out.append(ck.cyl(0.07, 0.02, "#3a3430", -0.02, -0.02, 0.0, verts=10))
    out.append(bk.cone(0.04, 0.10, (-0.02, -0.02, 0.07), "#ff9a3a", verts=6))
    out += ck.banner(0.30, -0.10, 0.0, 0.45, RED, GOLD, w=0.12, h=0.16)
    return obj("obj_shrine_att", out)


def shrine_def():
    """Wehrturm: gedrungener Steinturm mit Zinnen und Schild am Tor."""
    out = ck.round_tower(0.18, 0.46, STONE, STONE_DARK, 0, 0.05, 0.0, crenel="std",
                         slits="#1a1612")
    out += ck.door(0, -0.13, 0.0, 0.09, 0.13, STONE_DARK, WOOD_DARK)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.07, depth=0.02,
                                        location=(0, -0.16, 0.30), rotation=(rad(90), 0, 0))
    sh = bpy.context.active_object
    bk._bake(sh)
    sh.data.materials.append(bk.material("k" + ROOF, ROOF))
    out.append(sh)
    out += ck.banner(0.0, 0.05, 0.50, 0.25, ROOF, GOLD, w=0.10, h=0.12)
    return obj("obj_shrine_def", out)


def shrine_power():
    """Sternwarte: Turm mit Kuppel, Fernrohr und Sternenspitze."""
    out = ck.round_tower(0.15, 0.50, "#9a94a8", "#5e5868", 0, 0.05, 0.0)
    out.append(ck.dome(0.17, "#3a4a7a", 0, 0.05, 0.52))
    out.append(fg.tube("scope", [(0.02, -0.05, 0.62), (0.12, -0.22, 0.74)], [0.025, 0.018],
                       GOLD))
    out.append(ck.cyl(0.008, 0.10, GOLD, 0, 0.05, 0.68, verts=6))
    out.append(fg.ball(0.03, (0, 0.05, 0.80), "#ffe89a", subdiv=1))
    out += ck.window(0, -0.10, 0.28, 0.06, 0.09, "#5e5868", GLOW, arched=True)
    return obj("obj_shrine_power", out)


def shrine_know():
    """Garten: Hecke im Rund, Pavillon mit Kuppel, Beete."""
    out = []
    for k in range(10):
        a = 2 * math.pi * k / 10
        if 4 < k < 6:
            continue
        out.append(fg.lump((math.cos(a) * 0.32, math.sin(a) * 0.30, 0.05), 0.08,
                           "#3f6b26", strength=0.3, squash=0.9, seed=k))
    for sx in (-1, 1):
        for sy in (-1, 1):
            out.append(ck.cyl(0.02, 0.22, "#e6dcc4", sx * 0.09, sy * 0.09, 0.0, verts=8))
    out.append(ck.cyl(0.15, 0.03, "#e6dcc4", 0, 0, 0.22, verts=16))
    out.append(ck.dome(0.14, "#5a7a34", 0, 0, 0.25))
    for k, c in enumerate(("#c96a8a", "#d8b44a", "#8a6ab0", "#c9563a")):
        a = 2 * math.pi * k / 4 + 0.4
        out.append(fg.lump((math.cos(a) * 0.20, math.sin(a) * 0.18, 0.02), 0.045, c,
                           strength=0.3, squash=0.6, seed=20 + k))
    return obj("obj_shrine_know", out)


def well():
    """Brunnen: Steinring, Holzgestell mit Dach und Eimer."""
    out = [ck.cyl(0.16, 0.14, STONE, 0, 0, 0.0, verts=16),
           ck.cyl(0.12, 0.02, "#2a4a6a", 0, 0, 0.13, verts=16)]
    for sx in (-1, 1):
        out.append(ck.block(0.03, 0.03, 0.34, WOOD, sx * 0.15, 0, 0.0, bevel=0.0))
    out.append(ck.block(0.34, 0.025, 0.025, WOOD, 0, 0, 0.30, bevel=0.0))
    out += ck.gable_roof(0.36, 0.24, 0.34, 0.12, ROOF, WOOD_DARK, along="x", over=0.03,
                         rows=2, row_col=ROOF_ROWS)
    out.append(ck.cyl(0.03, 0.05, WOOD_DARK, 0.04, 0, 0.20, verts=8))
    return obj("obj_well", out)


def learning():
    """Lehrmeister: kleiner Saeulentempel mit Giebel und Lesepult."""
    out = [ck.block(0.62, 0.44, 0.06, STONE_DARK, 0, 0.04, 0.0),
           ck.block(0.56, 0.38, 0.04, STONE, 0, 0.04, 0.06)]
    for sx in (-1, 0, 1):
        for sy in (-1, 1):
            out.append(ck.cyl(0.03, 0.30, "#e6dcc4", sx * 0.22, 0.04 + sy * 0.14, 0.10, verts=10))
    out.append(ck.block(0.58, 0.40, 0.04, STONE, 0, 0.04, 0.40))
    out += ck.gable_roof(0.58, 0.40, 0.44, 0.14, "#8a3a2e", "#5a2a20", 0, 0.04, along="x",
                         over=0.02, rows=2)
    out.append(ck.block(0.07, 0.07, 0.14, WOOD, 0, 0.0, 0.10))
    out.append(bk.box((0.06, 0.05, 0.01), (0, -0.01, 0.255), "#e6dcc4", 0.0,
                      rot=(rad(-20), 0, 0)))
    return obj("obj_learning", out)


def windmill():
    """Windmuehle: Rundturm, Kegeldach, vier Fluegel zur Kamera."""
    out = [ck.cyl(0.17, 0.50, "#d6cbb2", 0, 0.05, 0.0, r_top=0.13, verts=14),
           ck.cone_roof(0.16, 0.20, "#8a3a2e", 0, 0.05, 0.50, verts=14)]
    out += ck.door(0, -0.12, 0.0, 0.07, 0.11, STONE_DARK, WOOD_DARK)
    out += ck.window(0, -0.10, 0.30, 0.05, 0.06, STONE_DARK, GLOW)
    hub = (0, -0.11, 0.48)
    out.append(fg.ball(0.03, hub, WOOD_DARK, subdiv=1))
    for k in range(4):
        a = rad(20 + 90 * k)
        tip = (math.cos(a) * 0.38, -0.12, 0.48 + math.sin(a) * 0.38)
        out.append(fg.tube("sail_arm", [hub, tip], [0.012, 0.008], WOOD))
        # Segel als Gitter-Flaeche neben dem Arm.
        nx, nz = -math.sin(a) * 0.07, math.cos(a) * 0.07
        vs = [(hub[0] + math.cos(a) * 0.08, -0.125, hub[2] + math.sin(a) * 0.08),
              (tip[0], -0.125, tip[2]),
              (tip[0] + nx, -0.125, tip[2] + nz),
              (hub[0] + math.cos(a) * 0.08 + nx, -0.125, hub[2] + math.sin(a) * 0.08 + nz)]
        out.append(fg.sheet("sail", vs, [(0, 1, 2, 3)], "#e6dcc4", 0.006))
    return obj("obj_windmill", out)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for f in (mine, treasure, pile, shrine_att, shrine_def, shrine_power, shrine_know,
              well, learning, windmill):
        f()
    try:
        out = sys.argv[sys.argv.index("--") + 1]
    except (ValueError, IndexError):
        out = "mapobj.glb"
    bk.export(out)


if __name__ == "__main__":
    main()
