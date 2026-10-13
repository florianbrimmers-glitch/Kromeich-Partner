#!/usr/bin/env python3
"""PILOT: stilisierte Natur, selbst gebaut (It. 72).

    /opt/blender/blender -b --factory-startup -noaudio \
        --python game/tools/pilot/gen_nature_own.py -- game/pilot_assets/nature.glb

WARUM SELBST GEBAUT: Der erste Anlauf nahm Poly-Haven-Modelle (CC0). Das
sind Fotogrammetrie-Vorlagen fuer Filmbilder - ein Baum hat 1,6 Millionen
Flaechen. Auf ein Spielbudget von 9.000 reduziert, verschwanden die Blaetter
und es blieb kahles Astwerk; die Bilder sahen nach totem Wald aus. Das
passende CC0-Paket ("Ultimate Stylized Nature") war auf Google Drive wegen
erschoepftem Download-Kontingent nicht zu holen.

Der Stil zielt auf "wie Heroes 4, nur nicht ganz so realistisch": Laub in
weichen, klumpigen Ballen statt einzelner Blaetter, gedeckte Gruentoene mit
Variation je Ballen, Felsen kantig mit Moos auf der Oberseite.

TECHNIK:
  - Staemme und Aeste per Skin-Modifier (wie gen_pilot_own.py), mit
    Ausgleich fuer das Schrumpfen durch Subdivision.
  - Laubballen: Ikosaeder, mit einem Rauschfeld VERFORMT (Displace) und
    geglaettet - ein glatter Ball liest sich als Kugel, ein verformter als
    Laub.
  - Felsen: verformter Ikosaeder, flach schattiert, Flaechen mit nach oben
    zeigender Normalen bekommen Moos.

Alle Groessen in Zellen (1 Zelle = 1 Einheit).
"""

import math
import os
import random
import sys

import bpy
import mathutils

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import blender_kit as bk  # noqa: E402

SKIN_FATTEN = 1.45


def _activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def skin(name, verts, edges, radii, col, levels=2):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    _activate(ob)
    m = ob.modifiers.new("skin", "SKIN")
    for i, r in enumerate(radii):
        me.skin_vertices[0].data[i].radius = (r * SKIN_FATTEN, r * SKIN_FATTEN)
        me.skin_vertices[0].data[i].use_root = (i == 0)
    s = ob.modifiers.new("sub", "SUBSURF")
    s.levels = levels
    bpy.ops.object.modifier_apply(modifier="skin")
    bpy.ops.object.modifier_apply(modifier="sub")
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(bk.material(name + "_m", col, rough=0.9))
    return ob


def lump(loc, radius, col, strength=0.35, scale=0.9, squash=0.8, seed=0,
         subdiv=3, smooth=True):
    """Verformter Ball - Laub oder Busch."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdiv, radius=radius,
                                          location=loc)
    ob = bpy.context.active_object
    ob.scale = (1.0, 1.0, squash)
    tex = bpy.data.textures.new("n%d" % seed, "CLOUDS")
    tex.noise_scale = scale * radius
    tex.noise_depth = 2
    d = ob.modifiers.new("disp", "DISPLACE")
    d.texture = tex
    d.strength = strength * radius
    d.mid_level = 0.5
    # Rauschfeld je Ballen versetzen, sonst sehen alle gleich aus.
    d.texture_coords = "LOCAL"
    ob.location = loc
    _activate(ob)
    bpy.ops.object.modifier_apply(modifier="disp")
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    me = ob.data
    off = mathutils.Vector((seed * 1.7, seed * 0.9, seed * 2.3))
    for v in me.vertices:
        n = mathutils.noise.noise(v.co * (2.2 / radius) + off)
        v.co += v.normal * n * strength * radius * 0.6
    for p in me.polygons:
        p.use_smooth = smooth
    bk._bake(ob)
    me.materials.append(bk.material("m" + col, col, rough=0.95))
    return ob


def broadleaf(name, h, rng, greens, bark="#5a4630"):
    """Laubbaum: Stamm mit drei bis vier Aesten, Laubballen an den Enden."""
    parts = []
    lean = rng.uniform(-0.12, 0.12)
    trunk_top = (lean * h, rng.uniform(-0.08, 0.08) * h, h * 0.52)
    verts = [(0, 0, 0), (lean * h * 0.4, 0, h * 0.25), trunk_top]
    edges = [(0, 1), (1, 2)]
    radii = [0.11 * h / 3, 0.075 * h / 3, 0.06 * h / 3]
    ends = []
    n = rng.randint(3, 4)
    for k in range(n):
        a = k * (2 * math.pi / n) + rng.uniform(-0.4, 0.4)
        reach = rng.uniform(0.22, 0.34) * h
        end = (trunk_top[0] + math.cos(a) * reach,
               trunk_top[1] + math.sin(a) * reach,
               trunk_top[2] + rng.uniform(0.14, 0.26) * h)
        verts.append(end)
        edges.append((2, len(verts) - 1))
        radii.append(0.025 * h / 3)
        ends.append(end)
    parts.append(skin(name + "_trunk", verts, edges, radii, bark))
    # Laub: grosser Mittelballen plus einer je Ast, leicht ueberlappend.
    crown = (trunk_top[0], trunk_top[1], trunk_top[2] + 0.30 * h)
    parts.append(lump(crown, 0.30 * h, rng.choice(greens), seed=rng.randint(0, 999)))
    for e in ends:
        parts.append(lump(e, rng.uniform(0.19, 0.25) * h, rng.choice(greens),
                          seed=rng.randint(0, 999)))
    return parts


def pine(name, h, rng, greens):
    parts = [skin(name + "_trunk", [(0, 0, 0), (0, 0, h * 0.95)], [(0, 1)],
                  [0.07 * h / 3, 0.03 * h / 3], "#4f3b28")]
    tiers = 4
    for t in range(tiers):
        f = t / float(tiers)
        r = (0.34 - 0.22 * f) * h * 0.55
        z = h * (0.22 + 0.62 * f)
        bpy.ops.mesh.primitive_cone_add(vertices=9, radius1=r, depth=h * 0.34,
                                        location=(0, 0, z))
        ob = bpy.context.active_object
        me = ob.data
        for v in me.vertices:
            if v.co.z < 0:
                v.co.x *= rng.uniform(0.9, 1.15)
                v.co.y *= rng.uniform(0.9, 1.15)
                v.co.z += rng.uniform(-0.05, 0.03) * h
        for p in me.polygons:
            p.use_smooth = False
        bk._bake(ob)
        me.materials.append(bk.material("m" + greens[t % len(greens)],
                                        greens[t % len(greens)], rough=0.95))
        parts.append(ob)
    return parts


def bush(name, h, rng, greens, blossom=None):
    parts = []
    for k in range(rng.randint(3, 5)):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0.0, 0.28) * h
        r = rng.uniform(0.45, 0.62) * h
        parts.append(lump((math.cos(a) * d, math.sin(a) * d, r * 0.55), r,
                          rng.choice(greens), strength=0.4, squash=0.75,
                          seed=rng.randint(0, 999), subdiv=2))
    if blossom:
        for k in range(14):
            a = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(0.2, 0.55) * h
            parts.append(bk.ball(0.05 * h, (math.cos(a) * d, math.sin(a) * d,
                                           rng.uniform(0.55, 0.95) * h),
                                 blossom, subdiv=1))
    return parts


def rock(name, h, rng, grey="#7d7a72", moss="#5d7a3a"):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=h * 0.75,
                                          location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.scale = (rng.uniform(1.0, 1.4), rng.uniform(0.8, 1.1), 0.62)
    bpy.ops.object.transform_apply(scale=True)
    me = ob.data
    off = mathutils.Vector((rng.uniform(0, 50),) * 3)
    for v in me.vertices:
        n = mathutils.noise.noise(v.co * (1.8 / h) + off)
        v.co += v.normal * n * h * 0.32
        if v.co.z < -h * 0.05:
            v.co.z = -h * 0.05
    me.materials.append(bk.material("rock_" + grey, grey, rough=0.9))
    me.materials.append(bk.material("moss_" + moss, moss, rough=0.95))
    for p in me.polygons:
        p.use_smooth = False
        if p.normal.z > 0.72:
            p.material_index = 1
    bk._bake(ob)
    return [ob]


def flowers(name, h, rng, petal):
    parts = []
    for k in range(rng.randint(6, 9)):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0, 0.22)
        x, y = math.cos(a) * d, math.sin(a) * d
        z = rng.uniform(0.7, 1.0) * h
        parts.append(bk.box((0.006, 0.006, z * 0.5), (x, y, z * 0.5),
                            "#3f6a2a", 0.0, segments=1))
        parts.append(bk.ball(0.045, (x, y, z), petal, subdiv=1))
    return parts


def grass(name, h, rng, greens):
    parts = []
    for k in range(rng.randint(9, 13)):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0, 0.12)
        tilt = rng.uniform(-0.45, 0.45)
        parts.append(bk.cone(0.022, h * rng.uniform(0.7, 1.0),
                             (math.cos(a) * d, math.sin(a) * d, h * 0.45),
                             rng.choice(greens), verts=3,
                             rot=(tilt, rng.uniform(-0.45, 0.45), a)))
    return parts


# Dunkler als es im Farbwaehler aussieht: von oben beschienen, unter ACES
# und Saettigung 1.22 kamen die ersten Kronen fast weissgelb heraus.
LEAF = ["#3f6a24", "#4c7629", "#557f2f", "#3a6222"]
LEAF_WARM = ["#66742a", "#717f2e", "#5b7026"]
PINE = ["#2f5a2c", "#386633", "#2a5028"]
BUSH = ["#4a7a2c", "#5a8a32", "#3f6c28"]


def main():
    try:
        out = sys.argv[sys.argv.index("--") + 1]
    except (ValueError, IndexError):
        out = "nature.glb"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rng = random.Random(4711)
    made = []

    def build(name, parts):
        ob = bk.merge(name, parts)
        made.append("%s(%d)" % (name, len(ob.data.polygons)))

    for i in range(3):
        build("tree_leaf_%d" % i, broadleaf("tl%d" % i, rng.uniform(2.6, 3.3),
                                            rng, LEAF))
    build("tree_leaf_warm", broadleaf("tw", 2.8, rng, LEAF_WARM))
    for i in range(2):
        build("tree_pine_%d" % i, pine("tp%d" % i, rng.uniform(3.0, 3.6), rng,
                                       PINE))
    build("bush_plain_0", bush("b0", 0.62, rng, BUSH))
    build("bush_plain_1", bush("b1", 0.78, rng, BUSH))
    build("bush_flower_pink", bush("bp", 0.66, rng, BUSH, "#d98aa8"))
    build("bush_flower_red", bush("br", 0.60, rng, BUSH, "#c4483c"))
    for i in range(3):
        build("rock_%d" % i, rock("r%d" % i, rng.uniform(0.35, 0.6), rng))
    build("flower_yellow", flowers("fy", 0.22, rng, "#e8c84a"))
    build("flower_white", flowers("fw", 0.20, rng, "#ece6d8"))
    build("flower_blue", flowers("fb", 0.20, rng, "#6f86d0"))
    for i in range(2):
        build("grass_%d" % i, grass("g%d" % i, rng.uniform(0.24, 0.34), rng,
                                    ["#55832f", "#6a9638", "#4a7429"]))
    print("NATUR:", ", ".join(made))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bk.export(out)


if __name__ == "__main__":
    main()
