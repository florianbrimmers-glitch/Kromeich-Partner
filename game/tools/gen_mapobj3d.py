#!/usr/bin/env python3
"""Kartenobjekte der Weltkarte im Heroes-4-Stil (It. 77).

    /opt/blender/blender -b --factory-startup -noaudio \
        --python tools/gen_mapobj3d.py -- game/assets/models/mapobj.glb

Die zehn ersten Objekte (Mine, Truhe, Haufen, vier Schreine, Brunnen,
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


# --- Zweite Welle (It. 78) ------------------------------------------------

def campfire():
    """Lagerfeuer: Steinring, Flammen, Kessel, Saecke und Kiste mit Gold."""
    out = []
    for k in range(9):
        a = 2 * math.pi * k / 9
        out.append(fg.lump((math.cos(a) * 0.11, math.sin(a) * 0.11, 0.02), 0.035,
                           "#7a7468", strength=0.3, seed=40 + k, subdiv=1))
    for k in range(3):
        a = rad(60 * k)
        out.append(fg.tube("log", [(math.cos(a) * 0.09, math.sin(a) * 0.09, 0.02),
                                   (-math.cos(a) * 0.09, -math.sin(a) * 0.09, 0.05)],
                           [0.018, 0.018], WOOD_DARK))
    out.append(bk.cone(0.07, 0.18, (0, 0, 0.12), "#ff8a2a", verts=7))
    out.append(bk.cone(0.04, 0.12, (0.01, -0.01, 0.15), "#ffd35a", verts=6))
    # Dreibein mit Kessel
    for k in range(3):
        a = rad(90 + 120 * k)
        out.append(fg.tube("tri", [(math.cos(a) * 0.15, math.sin(a) * 0.15, 0.0), (0, 0, 0.32)],
                           [0.008, 0.008], WOOD))
    out.append(fg.ball(0.05, (0, 0, 0.22), "#2a2a2e", squash=(1, 1, 0.8), subdiv=1))
    out.append(ck.block(0.13, 0.10, 0.09, WOOD, 0.24, 0.10, 0.0))
    for k in range(5):
        out.append(ck.cyl(0.025, 0.01, GOLD, 0.21 + (k % 3) * 0.03, 0.08 + (k // 3) * 0.04, 0.09,
                          verts=8))
    for k, (x, y) in enumerate(((-0.24, 0.10), (-0.20, 0.20))):
        out.append(fg.ball(0.06, (x, y, 0.05), "#b09a6a", squash=(1, 0.9, 0.9), subdiv=1))
    return obj("obj_campfire", out)


def artifact():
    """Artefakt am Boden: Steinsockel, schwebende Kugel, Lichtsplitter."""
    out = [ck.cyl(0.13, 0.05, STONE_DARK, 0, 0, 0.0, verts=8),
           ck.cyl(0.08, 0.14, STONE, 0, 0, 0.05, r_top=0.06, verts=8),
           ck.cyl(0.10, 0.03, STONE_DARK, 0, 0, 0.19, verts=8),
           fg.ball(0.08, (0, 0, 0.33), "#9a6ad8", subdiv=2)]
    for k in range(4):
        a = rad(45 + 90 * k)
        out.append(bk.cone(0.025, 0.09, (math.cos(a) * 0.13, math.sin(a) * 0.13, 0.36),
                           "#ffe6a6", verts=4))
    for k in range(5):
        a = k * 1.3
        out.append(fg.lump((math.cos(a) * 0.22, math.sin(a) * 0.2, 0.01), 0.04,
                           "#6a6458", strength=0.3, seed=60 + k, subdiv=1))
    return obj("obj_artifact", out)


def watermill():
    """Wassermuehle: Fachwerkhaus, grosses Rad vorn am Bach."""
    out = [ck.block(0.36, 0.24, 0.26, "#d6cbb2", 0.06, 0.12, 0.0)]
    out += ck.timber(0.36, 0.24, 0.26, WOOD_DARK, 0.06, 0.12, 0.0)
    out += ck.gable_roof(0.36, 0.24, 0.26, 0.16, "#8a3a2e", "#5a2a20", 0.06, 0.12,
                         along="x", over=0.04, rows=2)
    out += ck.window(0.14, 0.0, 0.12, 0.05, 0.06, WOOD_DARK, GLOW)
    # Rad zur Kamera (Achse entlang y), damit man es als Rad erkennt.
    cx, cy, cz = -0.10, -0.06, 0.16
    bpy.ops.mesh.primitive_torus_add(major_radius=0.15, minor_radius=0.014,
                                     location=(cx, cy, cz), rotation=(rad(90), 0, 0))
    ring = bpy.context.active_object
    bk._bake(ring)
    ring.data.materials.append(bk.material("k" + WOOD, WOOD))
    out.append(ring)
    for k in range(8):
        a = 2 * math.pi * k / 8
        out.append(fg.tube("spoke", [(cx, cy, cz), (cx + math.cos(a) * 0.15, cy, cz + math.sin(a) * 0.15)],
                           [0.008, 0.008], WOOD_DARK))
        out.append(bk.box((0.012, 0.06, 0.05), (cx + math.cos(a) * 0.16, cy, cz + math.sin(a) * 0.16),
                          WOOD_DARK, 0.0, rot=(0, -a, 0)))
    out.append(fg.ball(0.025, (cx, cy - 0.01, cz), WOOD_DARK, subdiv=1))
    out.append(bk.box((0.40, 0.07, 0.005), (0.0, -0.10, 0.004), "#3e6e94", 0.0))
    return obj("obj_watermill", out)

def stables():
    """Stallungen: langes Holzhaus, Boxen, Koppelzaun, Heuballen."""
    out = [ck.block(0.56, 0.24, 0.20, WOOD, 0, 0.10, 0.0)]
    out += ck.gable_roof(0.56, 0.24, 0.20, 0.13, "#7a5a34", WOOD_DARK, 0, 0.10,
                         along="x", over=0.04, rows=3)
    for k in range(3):
        out.append(ck.block(0.10, 0.02, 0.13, "#2a1e14", -0.18 + k * 0.18, -0.02, 0.0,
                            bevel=0.0))
        out.append(ck.block(0.10, 0.025, 0.02, WOOD_DARK, -0.18 + k * 0.18, -0.03, 0.06,
                            bevel=0.0))
    out += ck.fence(-0.30, 0.30, -0.30, 0.09, WOOD_DARK, n=7)
    for k, (x, y) in enumerate(((0.33, -0.12), (0.36, 0.02))):
        out.append(ck.cyl(0.06, 0.09, "#d8c070", x, y, 0.0, verts=10))
    # Hufeisen-Schild ueber dem Tor
    bpy.ops.mesh.primitive_torus_add(major_radius=0.04, minor_radius=0.008,
                                     location=(0, -0.025, 0.26), rotation=(rad(90), 0, 0))
    hs = bpy.context.active_object
    bk._bake(hs)
    hs.data.materials.append(bk.material("k#c8d2db", "#c8d2db"))
    out.append(hs)
    return obj("obj_stables", out)


def oasis():
    """Oase: Sandfleck, Wasserloch, zwei Palmen, Felsen."""
    out = [ck.cyl(0.34, 0.012, "#d6c08a", 0, 0, 0.0, verts=20),
           ck.cyl(0.17, 0.016, "#3e7ea4", -0.03, -0.02, 0.0, verts=20)]
    for k, (x, y, h, lean) in enumerate(((0.15, 0.13, 0.48, 0.06), (-0.18, 0.15, 0.40, -0.05))):
        top = (x + lean, y, h)
        out.append(fg.tube("palm", [(x, y, 0.0), (x + lean * 0.4, y, h * 0.5), top],
                           [0.025, 0.02, 0.015], "#7a5a30"))
        for j in range(6):
            a = 2 * math.pi * j / 6 + k
            tip = (top[0] + math.cos(a) * 0.15, top[1] + math.sin(a) * 0.15, h - 0.08)
            mid = (top[0] + math.cos(a) * 0.08, top[1] + math.sin(a) * 0.08, h + 0.02)
            out.append(fg.tube("frond", [top, mid, tip], [0.022, 0.018, 0.004], "#3f7a2a"))
    for k in range(3):
        out.append(fg.lump((0.10 - k * 0.12, -0.24, 0.02), 0.05, "#a89070", strength=0.3,
                           seed=70 + k, subdiv=1))
    return obj("obj_oasis", out)


def lookout():
    """Aussichtsturm: hohes Holzgeruest, Plattform, Dach, Fahne."""
    out = []
    pts = ((-0.12, -0.12), (0.12, -0.12), (0.12, 0.12), (-0.12, 0.12))
    for (x, y) in pts:
        out.append(fg.tube("leg", [(x * 1.4, y * 1.4, 0.0), (x * 0.8, y * 0.8, 0.62)],
                           [0.02, 0.016], WOOD))
    for z in (0.18, 0.40):
        f = 1.4 - (z / 0.62) * 0.6
        out.append(ck.block(0.24 * f + 0.03, 0.24 * f + 0.03, 0.02, WOOD_DARK, 0, 0, z,
                            bevel=0.0))
    out.append(ck.block(0.26, 0.26, 0.03, WOOD_DARK, 0, 0, 0.62, bevel=0.0))
    for (x, y) in pts:
        out.append(ck.block(0.02, 0.02, 0.18, WOOD, x * 0.95, y * 0.95, 0.65, bevel=0.0))
    out.append(ck.cone_roof(0.20, 0.14, "#7a3a2e", 0, 0, 0.83, verts=4))
    out += ck.banner(0, 0, 0.97, 0.12, RED, GOLD, w=0.08, h=0.06)
    return obj("obj_lookout", out)


def arena():
    """Arena: Rund aus Steinboegen, Sandplatz, zwei Banner."""
    out = [ck.cyl(0.40, 0.03, STONE_DARK, 0, 0, 0.0, verts=24),
           ck.cyl(0.30, 0.035, "#c9b47a", 0, 0, 0.0, verts=24)]
    n = 14
    for k in range(n):
        a = 2 * math.pi * k / n
        if math.sin(a) < -0.6:
            continue        # vorne offen, damit man hineinsieht
        x, y = math.cos(a) * 0.35, math.sin(a) * 0.33
        out.append(ck.block(0.05, 0.06, 0.24, STONE, x, y, 0.0, rot_z=a))
        a2 = a + math.pi / n
        out.append(ck.block(0.12, 0.07, 0.04, STONE_DARK, math.cos(a2) * 0.35,
                            math.sin(a2) * 0.33, 0.24, rot_z=a2 + math.pi / 2))
    for sx in (-1, 1):
        out += ck.banner(sx * 0.22, -0.26, 0.0, 0.40, RED if sx < 0 else ROOF, GOLD,
                         w=0.08, h=0.12)
    out.append(fg.tube("sword", [(0.0, 0.0, 0.03), (0.0, 0.0, 0.22)], [0.012, 0.004], "#c9d2db"))
    out.append(ck.block(0.08, 0.02, 0.015, GOLD, 0, 0, 0.08, bevel=0.0))
    return obj("obj_arena", out)


def fountain():
    """Gluecksbrunnen: Becken, Mittelsaeule, Schale, gruener Glueckskristall."""
    out = [ck.cyl(0.26, 0.08, STONE, 0, 0, 0.0, verts=20),
           ck.cyl(0.22, 0.02, "#4a8ab0", 0, 0, 0.07, verts=20),
           ck.cyl(0.04, 0.24, STONE, 0, 0, 0.08, verts=10),
           ck.cyl(0.11, 0.03, STONE, 0, 0, 0.28, r_top=0.13, verts=14),
           ck.cyl(0.10, 0.01, "#6ab0d8", 0, 0, 0.305, verts=14)]
    out.append(bk.cone(0.045, 0.12, (0, 0, 0.40), "#5ad05a", verts=4))
    out.append(bk.cone(0.045, 0.06, (0, 0, 0.33), "#5ad05a", verts=4, rot=(rad(180), 0, 0)))
    for k in range(4):
        a = rad(45 + 90 * k)
        out.append(fg.tube("jet", [(math.cos(a) * 0.05, math.sin(a) * 0.05, 0.30),
                                   (math.cos(a) * 0.13, math.sin(a) * 0.13, 0.34),
                                   (math.cos(a) * 0.19, math.sin(a) * 0.19, 0.09)],
                           [0.008, 0.008, 0.006], "#9ad8f0"))
    return obj("obj_fountain", out)


def temple():
    """Tempel: runder Saeulentempel (Tholos) mit goldener Kuppel auf Stufen."""
    out = [ck.cyl(0.30, 0.04, STONE_DARK, 0, 0, 0.0, verts=24),
           ck.cyl(0.26, 0.04, STONE, 0, 0, 0.04, verts=24),
           ck.cyl(0.14, 0.24, "#e6dcc4", 0, 0, 0.08, verts=16)]
    for k in range(10):
        a = 2 * math.pi * k / 10
        out.append(ck.cyl(0.022, 0.28, "#f0e8d4", math.cos(a) * 0.22, math.sin(a) * 0.22, 0.08,
                          verts=8))
    out.append(ck.cyl(0.25, 0.04, "#cfc7b0", 0, 0, 0.36, verts=24))
    out.append(ck.dome(0.22, GOLD, 0, 0, 0.40))
    out.append(ck.cyl(0.01, 0.10, GOLD, 0, 0, 0.55, verts=6))
    out.append(fg.ball(0.025, (0, 0, 0.66), "#fff0b0", subdiv=1))
    out += ck.door(0, -0.14, 0.08, 0.07, 0.14, STONE_DARK, "#5a3a20")
    return obj("obj_temple", out)

def tree():
    """Baum des Wissens: knorriger Riesenbaum, Wurzeln, leuchtende Fruechte."""
    out = [fg.tube("trunk", [(0, 0.04, 0.0), (0.02, 0.04, 0.25), (-0.01, 0.04, 0.42)],
                   [0.10, 0.07, 0.06], "#6b5330")]
    for k in range(5):
        a = 2 * math.pi * k / 5 + 0.3
        out.append(fg.tube("root", [(0, 0.04, 0.05),
                                    (math.cos(a) * 0.20, 0.04 + math.sin(a) * 0.18, 0.0)],
                           [0.04, 0.015], "#6b5330"))
    for k, (x, y, z) in enumerate(((0.16, 0.04, 0.42), (-0.16, 0.06, 0.40), (0.0, 0.04, 0.56))):
        out.append(fg.tube("bough", [(0, 0.04, 0.38), (x, y, z)], [0.04, 0.02], "#6b5330"))
    out += ck.leaves(0.0, 0.04, 0.52, 0.22, ("#2f5a24", "#3f7030", "#4a7a34"), n=6, seed=5)
    for k in range(7):
        a = k * 2.1
        out.append(fg.ball(0.025, (math.cos(a) * 0.22, 0.04 + math.sin(a) * 0.12 - 0.06,
                                   0.44 + (k % 3) * 0.07), "#ffd86a", subdiv=1))
    return obj("obj_tree", out)


def witch_hut():
    """Hexenhuette: schiefe Huette auf Stelzen, Krummdach, Kessel, Totenkopf."""
    out = []
    for (x, y) in ((-0.14, -0.08), (0.14, -0.08), (-0.14, 0.18), (0.14, 0.18)):
        out.append(fg.tube("stilt", [(x, y, 0.0), (x * 0.9, y, 0.14)], [0.018, 0.015], WOOD_DARK))
    out.append(ck.block(0.34, 0.30, 0.20, "#6b5a3a", 0, 0.05, 0.14, taper=0.9, rot_z=rad(4)))
    out.append(ck.cone_roof(0.26, 0.34, "#3e4a2a", 0.02, 0.05, 0.34, verts=7))
    out.append(fg.tube("tip", [(0.02, 0.05, 0.66), (0.10, 0.02, 0.74)], [0.03, 0.005], "#3e4a2a"))
    out += ck.window(0.0, -0.105, 0.22, 0.06, 0.06, WOOD_DARK, "#a0e070")
    for k in range(3):
        out.append(ck.block(0.10, 0.03, 0.012, WOOD, 0, -0.14 - k * 0.04, 0.10 - k * 0.04,
                            bevel=0.0))
    out.append(fg.ball(0.07, (0.24, -0.20, 0.06), "#2a2a2e", squash=(1, 1, 0.8), subdiv=1))
    out.append(ck.cyl(0.055, 0.01, "#7ad04a", 0.24, -0.20, 0.10, verts=10))
    out += ck.skull(-0.24, -0.20, 0.05, 0.05, "#e6dcc4")
    return obj("obj_witch_hut", out)


def magic_shrine():
    """Schrein der Magie: Obelisk mit Leuchtrunen in einem Steinkreis."""
    out = [ck.cyl(0.16, 0.05, "#5e5868", 0, 0, 0.0, verts=8),
           ck.block(0.12, 0.12, 0.46, "#7a7490", 0, 0, 0.05, taper=0.55),
           bk.cone(0.05, 0.10, (0, 0, 0.56), "#9a94b0", verts=4)]
    for z in (0.18, 0.30, 0.42):
        out.append(ck.block(0.05, 0.01, 0.05, "#8ad0ff", 0, -0.055 + (z - 0.18) * 0.04, z,
                            bevel=0.0))
    out.append(fg.ball(0.035, (0, 0, 0.64), "#8ad0ff", subdiv=1))
    for k in range(6):
        a = 2 * math.pi * k / 6 + 0.25
        out.append(ck.block(0.06, 0.04, 0.12 + (k % 2) * 0.05, "#8a8496",
                            math.cos(a) * 0.30, math.sin(a) * 0.28, 0.0, rot_z=a))
    return obj("obj_magic_shrine", out)


def prison():
    """Gefaengnis: gedrungener Kerker mit Zinnen, Gittertor, Ketten."""
    out = [ck.block(0.48, 0.36, 0.30, "#6b665f", 0, 0.05, 0.0),
           ck.block(0.50, 0.38, 0.04, "#5a5650", 0, 0.05, 0.30)]
    out += ck.crenels(0.50, 0.38, 0.34, "#5a5650", 0, 0.05)
    out += ck.door(0, -0.13, 0.0, 0.12, 0.17, "#5a5650", "#1a1612")
    for k in range(4):
        out.append(ck.cyl(0.006, 0.17, "#9aa0a8", -0.045 + k * 0.03, -0.14, 0.0, verts=6))
    for sx in (-1, 1):
        out += ck.window(sx * 0.15, -0.13, 0.18, 0.05, 0.06, "#5a5650", "#1a1612")
    for sx in (-1, 1):
        out += ck.round_tower(0.08, 0.40, "#6b665f", "#5a5650", sx * 0.24, -0.10, 0.0,
                              crenel="std")
    return obj("obj_prison", out)


def trading_post():
    """Handelsposten: Marktstand mit Streifendach, Faesser, Kisten, Waage."""
    out = [ck.block(0.44, 0.18, 0.13, WOOD, 0, -0.02, 0.0)]
    for (x, y) in ((-0.21, -0.10), (0.21, -0.10), (-0.21, 0.16), (0.21, 0.16)):
        out.append(ck.cyl(0.015, 0.32, WOOD_DARK, x, y, 0.0, verts=6))
    out += ck.gable_roof(0.48, 0.32, 0.32, 0.09, RED, "#e6dcc4", 0, 0.03, along="x",
                         over=0.03, rows=3, row_col="#e6dcc4")
    for k, (x, y) in enumerate(((0.30, 0.12), (0.33, -0.02))):
        out.append(ck.cyl(0.055, 0.12, "#7a5a34", x, y, 0.0, verts=12))
        out.append(ck.cyl(0.058, 0.01, "#4a4a4e", x, y, 0.09, verts=12))
    out.append(ck.block(0.10, 0.10, 0.08, WOOD_DARK, -0.31, 0.06, 0.0))
    out.append(ck.block(0.08, 0.08, 0.07, WOOD, -0.30, 0.06, 0.08))
    out.append(ck.cyl(0.006, 0.08, GOLD, 0, -0.04, 0.13, verts=6))
    out.append(ck.block(0.14, 0.01, 0.01, GOLD, 0, -0.04, 0.21, bevel=0.0))
    for sx in (-1, 1):
        out.append(ck.cyl(0.03, 0.01, GOLD, sx * 0.07, -0.04, 0.17, verts=10))
    for k in range(4):
        out.append(fg.ball(0.025, (-0.12 + k * 0.03, -0.05, 0.15), ("#c96a3a", "#7ab04a",
                                                                    "#d8b44a", "#8a3a8a")[k],
                           subdiv=1))
    return obj("obj_trading_post", out)


# --- Dritte Welle (It. 79) ------------------------------------------------

def dwelling():
    """Behausung: Rundhuette aus Stein und Holz, Strohkegel, Banner, Pferch."""
    out = [ck.cyl(0.20, 0.20, "#a89878", 0, 0.06, 0.0, verts=14),
           ck.cone_roof(0.25, 0.26, "#b89a5a", 0, 0.06, 0.20, verts=14)]
    out += ck.door(0, -0.14, 0.0, 0.08, 0.12, STONE_DARK, WOOD_DARK)
    out += ck.window(0.10, -0.12, 0.10, 0.04, 0.04, WOOD_DARK, GLOW)
    out += ck.banner(-0.24, -0.12, 0.0, 0.42, RED, GOLD, w=0.10, h=0.13)
    out += ck.fence(0.10, 0.34, -0.26, 0.07, WOOD_DARK, n=5)
    out += ck.fence(-0.34, -0.10, -0.26, 0.07, WOOD_DARK, n=5)
    for k in range(3):
        out.append(ck.cyl(0.04, 0.05, "#d8c070", 0.28, 0.06 + k * 0.08, 0.0, verts=8))
    return obj("obj_dwelling", out)


def crypt():
    """Krypta: Gruft mit Spitzdach, schwarzem Tor, Grabsteinen und Totenkopf."""
    out = [ck.block(0.40, 0.34, 0.26, "#6a6672", 0, 0.08, 0.0),
           ck.block(0.44, 0.38, 0.03, "#4e4a56", 0, 0.08, 0.26)]
    out += ck.gable_roof(0.44, 0.38, 0.29, 0.16, "#3e3a46", "#2a2630", 0, 0.08, along="y",
                         over=0.02, rows=0)
    out += ck.door(0, -0.09, 0.0, 0.11, 0.17, "#4e4a56", "#141018")
    out += ck.skull(0, -0.10, 0.22, 0.03, "#e6dcc4")
    for k, (x, y, h) in enumerate(((-0.30, -0.18, 0.12), (0.30, -0.16, 0.10), (-0.32, 0.18, 0.11),
                                   (0.31, 0.20, 0.13))):
        out.append(ck.block(0.07, 0.03, h, "#8a8494", x, y, 0.0, bevel=0.01))
    out.append(fg.tube("cross", [(0, 0.08, 0.45), (0, 0.08, 0.58)], [0.012, 0.012], "#9aa0a8"))
    out.append(fg.tube("crossb", [(-0.04, 0.08, 0.54), (0.04, 0.08, 0.54)], [0.01, 0.01], "#9aa0a8"))
    for k in range(4):
        out.append(fg.lump((-0.2 + k * 0.13, -0.30, 0.0), 0.04, "#3a4a2a", strength=0.3,
                           seed=90 + k, subdiv=1))
    return obj("obj_crypt", out)


def dwarf_treasury():
    """Zwergenschatz: Felshuegel mit Steintor, Goldbalken und Muenzhaufen."""
    out = []
    for k, (x, y, r) in enumerate(((0.0, 0.14, 0.32), (-0.24, 0.18, 0.22), (0.25, 0.16, 0.22))):
        out.append(fg.lump((x, y, 0.06), r, "#7a7468", strength=0.25, squash=0.8, seed=110 + k))
    out.append(ck.block(0.26, 0.08, 0.28, "#9a9282", 0, -0.12, 0.0))
    out.append(ck.block(0.16, 0.06, 0.20, "#1a1612", 0, -0.15, 0.0, bevel=0.0))
    out.append(ck.block(0.30, 0.09, 0.05, GOLD, 0, -0.12, 0.28))
    for k in range(3):
        out.append(ck.block(0.03, 0.01, 0.03, "#ffd86a", -0.07 + k * 0.07, -0.17, 0.29, bevel=0.0))
    for sx in (-1, 1):
        out.append(fg.ball(0.06, (sx * 0.22, -0.24, 0.02), GOLD, squash=(1, 1, 0.5), subdiv=1))
        out.append(ck.block(0.08, 0.04, 0.03, "#ffd86a", sx * 0.20, -0.32, 0.0, bevel=0.0))
    return obj("obj_dwarf_treasury", out)


def dragon_hoard():
    """Drachenhort: dunkle Hoehle, Goldberg, Knochen, Drachenschaedel."""
    out = []
    for k, (x, y, r) in enumerate(((0.0, 0.16, 0.33), (-0.22, 0.10, 0.21), (0.23, 0.12, 0.21))):
        out.append(fg.lump((x, y, 0.08), r, "#5a5048", strength=0.3, squash=0.85, seed=130 + k))
    out.append(fg.ball(0.17, (0, -0.10, 0.02), "#1a1612", squash=(1.0, 0.5, 0.9), subdiv=2))
    out.append(fg.ball(0.16, (0, -0.24, 0.0), GOLD, squash=(1.2, 0.8, 0.35), subdiv=2))
    for k in range(6):
        a = k * 1.1
        out.append(ck.cyl(0.025, 0.01, "#ffd86a", math.cos(a) * 0.20, -0.26 + math.sin(a) * 0.08,
                          0.03, verts=8))
    out += ck.skull(0.24, -0.26, 0.04, 0.05, "#e6dcc4")
    out += ck.horns(0.24, -0.26, 0.07, 0.05, "#e6dcc4")
    for k in range(2):
        out.append(fg.tube("bone", [(-0.30 + k * 0.06, -0.30, 0.01), (-0.18 + k * 0.04, -0.22, 0.01)],
                           [0.012, 0.012], "#e6dcc4"))
    # Fluegelspitze ueber dem Huegel: der Drache schlaeft drinnen.
    out.append(bk.cone(0.05, 0.22, (0.12, 0.22, 0.48), "#8a2f26", verts=4, rot=(0, rad(25), 0)))
    out.append(bk.cone(0.04, 0.16, (0.02, 0.24, 0.46), "#8a2f26", verts=4, rot=(0, rad(-15), 0)))
    return obj("obj_dragon_hoard", out)


# --- Vierte Welle (It. 80) ------------------------------------------------

def portal():
    """Portal: Steinbogen auf Stufen, darin ein leuchtender Wirbel."""
    out = [ck.cyl(0.30, 0.04, STONE_DARK, 0, 0, 0.0, verts=10),
           ck.cyl(0.26, 0.03, STONE, 0, 0, 0.04, verts=10)]
    for sx in (-1, 1):
        out.append(ck.block(0.08, 0.10, 0.36, "#8a8494", sx * 0.17, 0, 0.07))
    pts = [(math.cos(rad(a)) * 0.17, 0.0, 0.43 + math.sin(rad(a)) * 0.13) for a in range(0, 181, 20)]
    out.append(fg.tube("arch", pts, [0.05] * len(pts), "#8a8494"))
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.13, depth=0.02,
                                        location=(0, 0, 0.30), rotation=(rad(90), 0, 0))
    disc = bpy.context.active_object
    disc.scale = (1.0, 1.55, 1.0)
    bk._bake(disc)
    disc.data.materials.append(bk.material("k#6ac8f0", "#6ac8f0"))
    out.append(disc)
    for k in range(3):
        bpy.ops.mesh.primitive_torus_add(major_radius=0.04 + k * 0.03, minor_radius=0.006,
                                         location=(0, -0.015, 0.30), rotation=(rad(90), 0, 0))
        ring = bpy.context.active_object
        bk._bake(ring)
        ring.data.materials.append(bk.material("k#e6f6ff", "#e6f6ff"))
        out.append(ring)
    out.append(fg.ball(0.03, (0, 0, 0.60), "#6ac8f0", subdiv=1))
    return obj("obj_portal", out)


def seer_hut():
    """Seherhuette: spitzes Fellzelt, Totem mit Auge, Raeucherschale."""
    out = [ck.cone_roof(0.24, 0.50, "#6a4a8a", 0, 0.06, 0.0, verts=8),
           ck.block(0.10, 0.02, 0.15, "#1a1612", 0, -0.15, 0.0, bevel=0.0)]
    for k in range(4):
        a = rad(45 + 90 * k)
        out.append(fg.tube("pole", [(math.cos(a) * 0.05, 0.06 + math.sin(a) * 0.05, 0.44),
                                    (math.cos(a) * 0.09, 0.06 + math.sin(a) * 0.09, 0.60)],
                           [0.01, 0.008], WOOD_DARK))
    out.append(ck.cyl(0.03, 0.40, WOOD, 0.26, -0.12, 0.0, verts=8))
    out.append(fg.ball(0.05, (0.26, -0.15, 0.36), "#f2ece0", squash=(1, 0.5, 0.7), subdiv=1))
    out.append(fg.ball(0.022, (0.26, -0.18, 0.36), "#2a3a6a", subdiv=1))
    out.append(ck.cyl(0.06, 0.04, "#7a5a34", -0.24, -0.16, 0.0, verts=10))
    out.append(bk.cone(0.03, 0.10, (-0.24, -0.16, 0.09), "#c9a0ff", verts=6))
    return obj("obj_seer_hut", out)


def _mine_hill(seed, col="#7a7468"):
    out = []
    for k, (x, y, r) in enumerate(((0.0, 0.14, 0.30), (-0.22, 0.16, 0.20), (0.22, 0.14, 0.20))):
        out.append(fg.lump((x, y, 0.06), r, col, strength=0.25, squash=0.85, seed=seed + k))
    return out


def mine_wood():
    """Saegewerk: Holzhalle, Saegeblatt, Stammstapel."""
    out = [ck.block(0.40, 0.26, 0.20, WOOD, 0, 0.10, 0.0)]
    out += ck.gable_roof(0.40, 0.26, 0.20, 0.12, "#5a3a20", WOOD_DARK, 0, 0.10, along="x",
                         over=0.03, rows=2)
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.09, depth=0.01,
                                        location=(-0.06, -0.06, 0.12), rotation=(rad(90), 0, 0))
    saw = bpy.context.active_object
    bk._bake(saw)
    saw.data.materials.append(bk.material("k#c8d2db", "#c8d2db"))
    out.append(saw)
    for k in range(5):
        out.append(fg.tube("log", [(0.10, -0.12 - (k % 3) * 0.05, 0.03 + (k // 3) * 0.05),
                                   (0.34, -0.12 - (k % 3) * 0.05, 0.03 + (k // 3) * 0.05)],
                           [0.025, 0.025], "#8a6a40"))
    return obj("obj_mine_wood", out)


def mine_ore():
    """Erzgrube: Fels, Foerderturm, Lore mit grauem Erz."""
    out = _mine_hill(150)
    for sx in (-1, 1):
        out.append(fg.tube("leg", [(sx * 0.10, -0.16, 0.0), (sx * 0.04, -0.16, 0.36)],
                           [0.015, 0.012], WOOD))
    out.append(ck.block(0.14, 0.04, 0.03, WOOD_DARK, 0, -0.16, 0.34, bevel=0.0))
    out.append(ck.cyl(0.04, 0.02, "#4a4a4e", 0, -0.18, 0.33, verts=10))
    out.append(ck.block(0.14, 0.10, 0.07, WOOD_DARK, 0.20, -0.30, 0.02))
    for k in range(4):
        out.append(fg.ball(0.03, (0.17 + k * 0.025, -0.30, 0.10), "#6a6e76", subdiv=1))
    return obj("obj_mine_ore", out)


def mine_mercury():
    """Alchemistenlabor: Steinhaus mit Kuppel, Kolben, Rauch."""
    out = [ck.block(0.30, 0.26, 0.24, STONE, 0, 0.08, 0.0),
           ck.dome(0.14, "#5a7a8a", 0, 0.08, 0.24)]
    out += ck.door(0, -0.05, 0.0, 0.07, 0.12, STONE_DARK, WOOD_DARK)
    out.append(ck.cyl(0.03, 0.18, STONE_DARK, 0.10, 0.14, 0.24, verts=8))
    for k in range(3):
        out.append(fg.ball(0.04 + k * 0.01, (0.11 + k * 0.02, 0.15, 0.46 + k * 0.07), "#d8e0e6",
                           subdiv=1))
    for k, c in enumerate(("#c0d0e0", "#9ae0c0", "#e0a0d0")):
        out.append(fg.ball(0.04, (-0.24 + k * 0.08, -0.22, 0.04), c, subdiv=1))
        out.append(ck.cyl(0.01, 0.05, c, -0.24 + k * 0.08, -0.22, 0.07, verts=6))
    return obj("obj_mine_mercury", out)


def mine_sulfur():
    """Schwefelgrube: gelbe Duenen, dampfender Spalt."""
    out = _mine_hill(170, "#b8a040")
    out.append(fg.ball(0.10, (0, -0.16, 0.0), "#3a3018", squash=(1.2, 0.6, 0.3), subdiv=1))
    for k in range(3):
        out.append(fg.ball(0.05 + k * 0.015, (0.02 * k, -0.18, 0.10 + k * 0.08), "#e8e0b0",
                           subdiv=1))
    for k in range(4):
        out.append(fg.lump((-0.26 + k * 0.17, -0.30, 0.01), 0.04, "#e6d040", strength=0.3,
                           seed=180 + k, subdiv=1))
    return obj("obj_mine_sulfur", out)


def mine_crystal():
    """Kristallhoehle: Felshuegel, aus dem blaue Kristalle wachsen."""
    out = _mine_hill(190, "#6a6a78")
    out.append(ck.block(0.16, 0.06, 0.18, "#1a1612", 0, -0.13, 0.0, bevel=0.0))
    for k, (x, y, h, tilt) in enumerate(((-0.18, -0.16, 0.26, -15), (0.20, -0.14, 0.22, 18),
                                         (0.0, 0.10, 0.34, 0), (-0.08, -0.26, 0.14, -25),
                                         (0.12, -0.28, 0.12, 25))):
        out.append(bk.cone(0.05, h, (x, y, h * 0.5), "#7ad0f0", verts=5, rot=(0, rad(tilt), 0)))
    return obj("obj_mine_crystal", out)


def mine_gems():
    """Edelsteinteich: kleiner Teich, bunte Steine am Ufer, Felsen."""
    out = [ck.cyl(0.30, 0.012, "#7a7468", 0, 0, 0.0, verts=18),
           ck.cyl(0.22, 0.016, "#3e7ea4", 0, 0.02, 0.0, verts=18)]
    for k, c in enumerate(("#d84a8a", "#4ad08a", "#8a6ad8", "#e6c247", "#d84a4a", "#4aa0e0")):
        a = 2 * math.pi * k / 6 + 0.3
        out.append(bk.cone(0.035, 0.07, (math.cos(a) * 0.27, math.sin(a) * 0.25, 0.035), c,
                           verts=5))
    for k in range(3):
        out.append(fg.lump((-0.24 + k * 0.24, 0.30, 0.03), 0.06, "#8a8478", strength=0.3,
                           seed=200 + k, subdiv=1))
    return obj("obj_mine_gems", out)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for f in (mine, treasure, pile, shrine_att, shrine_def, shrine_power, shrine_know,
              well, learning, windmill, campfire, artifact, watermill, stables, oasis,
              lookout, arena, fountain, temple, tree, witch_hut, magic_shrine, prison,
              trading_post, dwelling, crypt, dwarf_treasury, dragon_hoard, portal, seer_hut,
              mine_wood, mine_ore, mine_mercury, mine_sulfur, mine_crystal, mine_gems):
        f()
    try:
        out = sys.argv[sys.argv.index("--") + 1]
    except (ValueError, IndexError):
        out = "mapobj.glb"
    bk.export(out)


if __name__ == "__main__":
    main()
