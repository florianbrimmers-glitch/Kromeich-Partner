#!/usr/bin/env python3
"""PILOT: selbst gebaute Kreaturen mit Skin-Modifier (It. 71).

    /opt/blender/blender -b --factory-startup -noaudio \
        --python game/tools/pilot/gen_pilot_own.py -- game/pilot_assets/own.glb

WOZU: der Nutzer hat gefragt, ob es mit fertigen CC0-Modellen besser
aussieht - und angemerkt, dass ich so etwas auch selbst bauen kann. Dieser
Generator ist die zweite Haelfte des Vergleichs: dieselben sechs Einheiten
wie im CC0-Pilot, aber selbst gebaut, und zwar NICHT aus gestapelten
Quadern wie gen_creatures.py.

DIE TECHNIK: ein Skelett aus Punkten, jeder mit einer Dicke. Der
Skin-Modifier legt eine geschlossene Haut darum, Subdivision glaettet sie.
Das ergibt durchgehende, organische Koerper ohne Nahtstellen - genau die
Stellen, an denen die Quader-Figuren als Spielzeug zu erkennen sind
(Schulter an Rumpf, Hals an Kopf, Bein an Huefte). Die HALTUNG steckt im
Skelett selbst: Standbein, Spielbein, verdrehter Rumpf, ungleiche Arme
(Befund aus It. 67: keine Figur in Olden Era steht gerade).

Die Groesse kommt aus gen_creatures.fit_to_tier - dieselbe Regel wie im
Spiel, damit der Vergleich fair ist.

NUR PILOT: die Ausgabe liegt in game/pilot_assets/ (in .gitignore) und
wird vom Spiel nicht geladen.
"""

import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import blender_kit as bk  # noqa: E402
import gen_creatures as gc  # noqa: E402

box = bk.box
cone = bk.cone
ball = bk.ball


# Subdivision SCHRUMPFT den Skin-Kaefig: was als Dicke angegeben ist, kommt
# nur zu rund zwei Dritteln an. Der zweite Entwurf hatte die Radien schon
# um ein Drittel erhoeht und sah trotzdem gleich duenn aus - die Ursache war
# nicht die Zahl, sondern die Glaettung. Einmal zentral ausgeglichen.
SKIN_FATTEN = 1.45


def skin(name, verts, edges, radii, col, root=0, levels=2):
    """Haut um ein Punkt-Skelett. radii: eine Dicke je Punkt."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    m = ob.modifiers.new("skin", "SKIN")
    m.use_smooth_shade = True
    # Die Dicken erst NACH dem Modifier setzen - die Datenebene entsteht
    # mit ihm.
    for i, r in enumerate(radii):
        rx, ry = (r, r) if not isinstance(r, tuple) else r
        me.skin_vertices[0].data[i].radius = (rx * SKIN_FATTEN,
                                               ry * SKIN_FATTEN)
        me.skin_vertices[0].data[i].use_root = (i == root)
    s = ob.modifiers.new("sub", "SUBSURF")
    s.levels = levels
    s.render_levels = levels
    bpy.ops.object.modifier_apply(modifier="skin")
    bpy.ops.object.modifier_apply(modifier="sub")
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(bk.material(name + "_m", col, rough=0.75))
    return ob


def smooth(ob):
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def chain(points):
    """Kanten fuer eine Punktkette."""
    return [(i, i + 1) for i in range(len(points) - 1)]


# ------------------------------------------------------------- Humanoid

def humanoid(name, pal, *, stance=1.0, squat=1.0, head_r=0.16, hunch=0.0,
             armour=True, helmet="kettle", weapon="spear", shield=True,
             ears=False, hood=False):
    """Zweibeiner in Kampfhaltung.

    Koordinaten: z oben, -y nach VORN (zur Kamera nach dem Export), x
    seitlich. Linkes Bein vorn (Standbein), rechtes zurueckgesetzt, Rumpf
    um die Hochachse gegen die Beine verdreht - die vier Abweichungen aus
    It. 67.
    """
    s = stance
    L = 0.92 * squat           # Hueftbreite in Hoehe
    parts = []

    # Beine + Becken als EIN Skelett - kein Spalt an der Huefte.
    lv = [
        (0.0, 0.0, L + 0.04),                       # 0 Becken
        (0.11, -0.02, L),                           # 1 Huefte L
        (0.13, -0.12 * s, L * 0.55),                # 2 Knie L (vor)
        (0.13, -0.08 * s, 0.07),                    # 3 Knoechel L
        (0.13, -0.20 * s, 0.035),                   # 4 Zeh L
        (-0.11, 0.02, L),                           # 5 Huefte R
        (-0.13, 0.10 * s, L * 0.52),                # 6 Knie R (zurueck)
        (-0.15, 0.22 * s, 0.07),                    # 7 Knoechel R
        (-0.15, 0.10 * s, 0.035),                   # 8 Zeh R
    ]
    le = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8)]
    # Kraeftig statt drahtig: der erste Entwurf hatte Streichholz-Beine.
    lr = [0.18, 0.13, 0.095, 0.072, 0.060, 0.13, 0.095, 0.072, 0.060]
    parts.append(skin(name + "_legs", lv, le, lr, pal["legs"]))

    # Rumpf + Arme. Verdreht: Schulterlinie dreht gegen die Huefte.
    tw = math.radians(24.0)

    def rot(x, y, z):
        return (x * math.cos(tw) - y * math.sin(tw),
                x * math.sin(tw) + y * math.cos(tw), z)

    top = L + 0.62 * squat
    tv = [
        (0.0, 0.0, L + 0.04),                                   # 0 Becken
        rot(0.0, -0.02 - hunch * 0.5, L + 0.30 * squat),        # 1 Taille
        rot(0.0, -0.03 - hunch, top - 0.08),                    # 2 Brust
        rot(0.0, -0.05 - hunch * 1.4, top + 0.06),              # 3 Hals
        rot(0.21, -0.02 - hunch, top - 0.04),                   # 4 Schulter L
        rot(0.31, -0.14, top - 0.30),                           # 5 Ellbogen L
        rot(0.24, -0.32, top - 0.42),                           # 6 Hand L
        rot(-0.21, -0.02 - hunch, top - 0.04),                  # 7 Schulter R
        rot(-0.33, 0.02, top - 0.26),                           # 8 Ellbogen R
        rot(-0.28, -0.20, top - 0.34),                          # 9 Hand R
    ]
    te = [(0, 1), (1, 2), (2, 3), (2, 4), (4, 5), (5, 6), (2, 7), (7, 8),
          (8, 9)]
    tr = [0.17, 0.16, (0.24, 0.18), 0.08, 0.10, 0.075, 0.065, 0.10,
          0.075, 0.065]
    parts.append(skin(name + "_torso", tv, te, tr,
                      pal["armour"] if armour else pal["cloth"]))

    hx, hy, hz = tv[3]
    hz += head_r * 0.95
    hy -= 0.02
    head = ball(head_r, (hx, hy, hz), pal["skin"], subdiv=3)
    parts.append(smooth(head))
    if ears:
        for sx in (-1, 1):
            parts.append(cone(head_r * 0.45, head_r * 1.6,
                              (hx + sx * head_r * 1.15, hy + 0.02, hz + 0.03),
                              pal["skin"], verts=6,
                              rot=(0, math.radians(-sx * 70), 0)))
    if helmet == "kettle":
        parts.append(smooth(cone(head_r * 1.30, head_r * 0.9,
                                 (hx, hy, hz + head_r * 0.55),
                                 pal["metal"], verts=16)))
        parts.append(box((head_r * 1.35, head_r * 1.35, 0.012),
                         (hx, hy, hz + head_r * 0.15), pal["metal"], 0.006,
                         segments=1))
    elif helmet == "hood":
        hood_ob = ball(head_r * 1.18, (hx, hy + 0.025, hz + 0.02),
                       pal["cloth"], subdiv=3)
        parts.append(smooth(hood_ob))
    # Guertel bricht die lange Rumpfform.
    parts.append(smooth(cone(0.155, 0.05, (0.0, -0.01, L + 0.10),
                             pal["leather"], verts=16)))

    lhx, lhy, lhz = tv[6]
    rhx, rhy, rhz = tv[9]
    if weapon == "spear":
        # Speer quer vor dem Koerper, von der rechten Hand zur Spitze vorn
        # oben - die Diagonale aus der Satyr-Referenz (It. 67).
        ln = 1.55
        ax = math.radians(-58)
        # WAAGERECHT ZUM GEGNER, eingelegt wie eine Lanze. Hochgereckt kreuzt
        # bei 46 Grad Draufsicht JEDER Speer das Gesicht - zwei Entwuerfe
        # haben das gezeigt, egal wie weit seitlich der Schaft lag.
        cx, cy, cz = rhx - 0.02, rhy - 0.55, rhz + 0.06
        parts.append(box((0.024, ln * 0.5, 0.024), (cx, cy, cz),
                         pal["wood"], 0.0, rot=(math.radians(6), 0, 0),
                         segments=1))
        parts.append(cone(0.055, 0.22, (cx, cy - ln * 0.5 - 0.09, cz - 0.08),
                          pal["metal"], verts=4,
                          rot=(math.radians(96), 0, 0)))
    elif weapon == "bow":
        # Bogen: eine Skin-Kette im Bogen, der Griff in der linken Hand.
        pts = []
        for k in range(7):
            a = math.radians(-60 + 20 * k)
            pts.append((lhx + 0.02, lhy - 0.10 - math.cos(a) * 0.10,
                        lhz + math.sin(a) * 0.42))
        parts.append(skin(name + "_bow", pts, chain(pts),
                          [0.012, 0.016, 0.02, 0.024, 0.02, 0.016, 0.012],
                          pal["wood"], levels=1))
        parts.append(box((0.004, 0.004, 0.40), (lhx + 0.02, lhy - 0.02, lhz),
                         "#e8e2d0", 0.0, segments=1))
        # Koecher auf dem Ruecken.
        parts.append(smooth(cone(0.06, 0.38, (-0.08, 0.16, top - 0.05),
                                 pal["leather"], verts=12,
                                 rot=(math.radians(-14), math.radians(18), 0))))
    elif weapon == "club":
        parts.append(smooth(cone(0.07, 0.62, (rhx + 0.02, rhy - 0.14, rhz + 0.24),
                                 pal["wood"], verts=10,
                                 rot=(math.radians(-38), 0, math.radians(-10)))))

    if shield:
        sh = bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.24,
                                                 depth=0.04,
                                                 location=(lhx + 0.05,
                                                           lhy - 0.06, lhz + 0.10))
        sob = bpy.context.active_object
        sob.rotation_euler = (math.radians(80), 0, math.radians(-30))
        bk._bake(sob)
        sob.data.materials.append(bk.material("shield_m", pal["shield"]))
        parts.append(smooth(sob))
        parts.append(smooth(ball(0.05, (lhx + 0.03, lhy - 0.10, lhz + 0.10),
                                 pal["metal"], subdiv=2)))
    return parts


# ------------------------------------------------------------- Vierbeiner

def quadruped(name, pal, *, length=1.0, height=1.0, mass=1.0, neck_up=0.5,
              head_r=0.13, snout=0.16, tail=0.5, tail_up=0.2, horns=False,
              ears=True, mane=False):
    """Vierbeiner im Schritt: diagonales Beinpaar vorn, Kopf zur Seite.

    Achse: -y ist VORN. Ruecken leicht abfallend zur Kruppe (Brust tiefer
    als die Kruppe, Befund aus It. 30).
    """
    Lh = 0.62 * height                 # Rueckenhoehe
    sl = 0.55 * length                 # halbe Rumpflaenge
    parts = []

    sv = [
        (0.0, sl + tail * 0.85, Lh + tail_up * 0.6),     # 0 Schwanzspitze
        (0.0, sl + tail * 0.35, Lh + tail_up * 0.25),    # 1 Schwanzmitte
        (0.0, sl, Lh),                                   # 2 Kruppe
        (0.0, 0.0, Lh + 0.02),                           # 3 Mitte
        (0.0, -sl, Lh + 0.04),                           # 4 Widerrist
        (0.06, -sl - 0.18 * neck_up - 0.10, Lh + 0.30 * neck_up + 0.10),  # 5 Hals
        (0.10, -sl - 0.26 - 0.10 * neck_up, Lh + 0.42 * neck_up + 0.12),  # 6 Kopf
        (0.12, -sl - 0.26 - 0.10 * neck_up - snout,
         Lh + 0.42 * neck_up + 0.06),                    # 7 Schnauze
    ]
    se = chain(sv)
    sr = [0.025, 0.05 * mass, 0.17 * mass, (0.17 * mass, 0.19 * mass),
          0.19 * mass, 0.11 * mass, head_r, head_r * 0.62]
    parts.append(skin(name + "_body", sv, se, sr, pal["coat"], root=3))

    # Beine: vorn L vorgesetzt, hinten R vorgesetzt (diagonaler Schritt).
    def leg(x, y, fwd, front):
        kz = Lh * 0.48
        knee_y = y + (-0.06 if front else 0.08) + fwd * 0.5
        pts = [(x, y, Lh - 0.06), (x * 1.05, knee_y, kz),
               (x * 1.05, y + fwd, 0.10), (x * 1.05, y + fwd - 0.05, 0.03)]
        rr = [0.12 * mass, 0.075 * mass ** 0.5, 0.058 * mass ** 0.5,
              0.065 * mass ** 0.5]
        return skin(name + "_leg", pts, chain(pts), rr, pal["leg"])

    w = 0.13 * mass
    parts.append(leg(w, -sl + 0.05, -0.16, True))
    parts.append(leg(-w, -sl + 0.05, 0.06, True))
    parts.append(leg(w, sl - 0.05, 0.08, False))
    parts.append(leg(-w, sl - 0.05, -0.14, False))

    hx, hy, hz = sv[6]
    if ears:
        for sx in (-1, 1):
            parts.append(cone(head_r * 0.35, head_r * 1.1,
                              (hx + sx * head_r * 0.55, hy + 0.04,
                               hz + head_r * 0.95), pal["coat"], verts=5,
                              rot=(math.radians(-12), math.radians(sx * 12), 0)))
    if horns:
        for sx in (-1, 1):
            pts = [(hx + sx * head_r * 0.6, hy, hz + head_r * 0.5),
                   (hx + sx * head_r * 1.5, hy - 0.02, hz + head_r * 0.8),
                   (hx + sx * head_r * 1.8, hy - 0.10, hz + head_r * 1.5)]
            parts.append(skin(name + "_horn", pts, chain(pts),
                              [0.05, 0.035, 0.012], pal["horn"], levels=1))
    if mane:
        for k in range(5):
            t = k / 4.0
            x = 0.0 + 0.06 * t
            y = -sl + (sv[5][1] + sl) * t
            z = Lh + 0.12 + (sv[5][2] - Lh) * t
            parts.append(smooth(ball(0.06 - 0.008 * k, (x, y, z), pal["mane"],
                                     subdiv=2)))
    # Auge: ein dunkler Punkt gibt dem Kopf eine Richtung.
    for sx in (-1, 1):
        parts.append(ball(head_r * 0.16, (hx + sx * head_r * 0.62,
                                          hy - head_r * 0.45, hz + head_r * 0.2),
                          "#141210", subdiv=1))
    return parts


def rider(name, pal, saddle_y, saddle_z):
    """Reiter IM Sattel: Beine haengen seitlich am Rumpf herab."""
    parts = []
    lv = [(0.0, saddle_y, saddle_z), (0.17, saddle_y - 0.05, saddle_z - 0.05),
          (0.20, saddle_y - 0.12, saddle_z - 0.30),
          (0.19, saddle_y - 0.05, saddle_z - 0.52),
          (-0.17, saddle_y - 0.05, saddle_z - 0.05),
          (-0.20, saddle_y - 0.12, saddle_z - 0.30),
          (-0.19, saddle_y - 0.05, saddle_z - 0.52)]
    le = [(0, 1), (1, 2), (2, 3), (0, 4), (4, 5), (5, 6)]
    parts.append(skin(name + "_rlegs", lv, le,
                      [0.13, 0.085, 0.065, 0.05, 0.085, 0.065, 0.05],
                      pal["legs"]))
    t = saddle_z + 0.55
    tv = [(0.0, saddle_y, saddle_z), (0.0, saddle_y - 0.04, saddle_z + 0.28),
          (0.0, saddle_y - 0.06, t), (0.20, saddle_y - 0.06, t + 0.02),
          (0.30, saddle_y - 0.22, t - 0.16), (0.26, saddle_y - 0.42, t - 0.10),
          (-0.20, saddle_y - 0.04, t + 0.02), (-0.30, saddle_y - 0.08, t - 0.24),
          (-0.24, saddle_y - 0.24, t - 0.30)]
    te = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (2, 6), (6, 7), (7, 8)]
    parts.append(skin(name + "_rtorso", tv, te,
                      [0.13, 0.12, (0.18, 0.14), 0.07, 0.055, 0.045, 0.07,
                       0.055, 0.045], pal["armour"]))
    hr = 0.11
    parts.append(smooth(ball(hr, (0.0, saddle_y - 0.08, t + 0.17), pal["skin"],
                             subdiv=3)))
    parts.append(smooth(cone(hr * 1.25, hr * 1.3,
                             (0.0, saddle_y - 0.08, t + 0.26), pal["metal"],
                             verts=16)))
    # Lanze nach vorn gesenkt.
    lx, ly, lz = tv[5]
    parts.append(box((0.016, 0.85, 0.016), (lx + 0.02, ly - 0.55, lz + 0.05),
                     pal["wood"], 0.0, rot=(math.radians(8), 0, 0), segments=1))
    parts.append(cone(0.04, 0.16, (lx + 0.02, ly - 1.45, lz + 0.18),
                      pal["metal"], verts=4, rot=(math.radians(98), 0, 0)))
    return parts


# ------------------------------------------------------------- Besetzung

MEN = dict(legs="#4a3f35", armour="#9aa4ae", cloth="#3a5a9a", skin="#e0b08a",
           metal="#b9c1c9", leather="#6b4a2a", wood="#7a5a32",
           shield="#3a5a9a")
ARCHER = dict(MEN, armour="#4c6a3a", cloth="#3d5a30", legs="#5a4630")
GOBLIN = dict(legs="#4a3a26", armour="#5a3c22", cloth="#5a3c22",
              skin="#6f9a3a", metal="#7a7a72", leather="#3e2a18",
              wood="#6a4a2a", shield="#6a4a2a")
HORSE = dict(coat="#e9e4dc", leg="#d8d1c6", horn="#d8cfb8", mane="#c9c0b2")
WOLF = dict(coat="#6e6a66", leg="#5e5a57", horn="#ccc", mane="#4e4a48")
BEAST = dict(coat="#5a3a2a", leg="#4a2f22", horn="#e3d8bc", mane="#3a261a")


def build(uid, tier, parts):
    ob = bk.merge(uid, parts)
    gc.fit_to_tier(ob, tier)
    return ob


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    build("men_spearman", 1, humanoid("sp", MEN, weapon="spear",
                                      helmet="kettle", shield=True))
    build("men_archer", 2, humanoid("ar", ARCHER, weapon="bow",
                                    helmet="hood", shield=False,
                                    armour=False))
    # Kuerzer und hoeher als im ersten Entwurf - der war ein Windhund.
    cav = quadruped("hs", HORSE, length=0.80, height=1.40, mass=0.95,
                    neck_up=1.2, head_r=0.13, snout=0.22, tail=0.45,
                    tail_up=-0.25, mane=True)
    cav += rider("rd", MEN, 0.02, 0.62 * 1.40 + 0.16)
    build("men_cavalier", 6, cav)

    build("ork_goblin", 1, humanoid("gb", GOBLIN, squat=0.72, head_r=0.15,
                                    hunch=0.10, armour=True, helmet=None,
                                    weapon="club", shield=False, ears=True))
    # Kurz und hochbeinig, Kopf erhoben - der erste Entwurf lag flach wie
    # eine Echse.
    build("ork_wolfrider", 2, quadruped("wf", WOLF, length=0.62, height=1.05,
                                        mass=0.85, neck_up=0.75, head_r=0.14,
                                        snout=0.20, tail=0.50, tail_up=0.30))
    build("ork_behemoth", 7, quadruped("bh", BEAST, length=1.05, height=1.05,
                                       mass=1.45, neck_up=0.05, head_r=0.17,
                                       snout=0.14, tail=0.35, tail_up=0.0,
                                       horns=True, ears=False, mane=True))

    try:
        out = sys.argv[sys.argv.index("--") + 1]
    except (ValueError, IndexError):
        out = "own.glb"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bk.export(out)


if __name__ == "__main__":
    main()
