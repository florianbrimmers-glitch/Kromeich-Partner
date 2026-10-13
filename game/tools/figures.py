"""Koerperbibliothek fuer die Kampffiguren im Heroes-4-Stil (It. 74).

Wird von gen_creatures.py benutzt (Blender-Python, kein eigenes main).

WARUM NEU: die bisherigen Figuren waren aus achsenparallelen Quadern
gestapelt und komplett in der Fraktionsfarbe eingefaerbt - ein Speertraeger
war ein gelber Kasten. Am Vorbild (Heroes 4, Kontaktbogen aus der
Might-and-Magic-Wiki) sind drei Dinge anders, und genau die setzt diese
Bibliothek um:

  1. DURCHGEHENDE KOERPER. Ein Punkt-Skelett mit einer Dicke je Punkt bekommt
     per Skin-Modifier eine geschlossene Haut, Subdivision glaettet sie. Die
     HALTUNG steckt im Skelett (Standbein, Spielbein, verdrehter Rumpf) -
     keine Nahtstellen an Schulter, Huefte, Hals (Pilot It. 71).
  2. NATUERLICHE MATERIALIEN. Haut, Leder, Stahl, Knochen, Fell. Die
     Fraktionsfarbe sitzt nur auf STOFF - Wappenrock, Schild, Umhang,
     Satteldecke. So erkennt man die Seite, und die Figur bleibt eine Figur.
  3. PROPORTIONEN DES VORBILDS: Kopf rund ein Siebtel der Koerperhoehe,
     lange Beine, schmale Taille; Zwerg und Goblin gedrungen, Oger massig.

KOORDINATEN: z oben, -y ist VORN (zur Gegenseite, BattleField3D dreht die
Figur je Seite), x seitlich. Die Groesse ist hier frei - am Ende passt
gen_creatures.fit_to_tier jede Figur auf ihre Stufe ein.
"""

import math
import random

import bpy
import mathutils

import blender_kit as bk

# Subdivision schrumpft den Skin-Kaefig um rund ein Drittel (Pilot It. 71).
SKIN_FATTEN = 1.45


# ---------------------------------------------------------------- Farben

# Fraktionsfarbe nur fuer Stoff, gedeckt statt grell.
FACTION_CLOTH = {
    "menschen": ("#5b3a8a", "#d8b44a"),     # Lila mit Gold, wie Heroes 4
    "waldvolk": ("#3f6b2e", "#c9a24a"),
    "totenreich": ("#3d2f52", "#8fd6a8"),
    "orkstaemme": ("#8a2f26", "#c9a24a"),
}
SKIN = {"human": "#d6a582", "elf": "#e2bf9c", "dwarf": "#c99672",
        "orc": "#6d7f45", "goblin": "#7f9a3e", "ogre": "#9a8a62",
        "cyclops": "#b88c6a", "pale": "#c9c4c8", "rot": "#7c8564",
        "bone": "#ddd5bf"}
STEEL = "#a7aeb6"
STEEL_DARK = "#4c5058"
GOLD = "#c9a24a"
LEATHER = "#6b4a2e"
LEATHER_DARK = "#4a3320"
WOOD = "#7a5a34"
CLOTH_PLAIN = "#7d7362"


def faction_of(unit):
    return unit.get("faction", "menschen")


def cloth(unit, accent=False):
    a, b = FACTION_CLOTH.get(faction_of(unit), FACTION_CLOTH["menschen"])
    return b if accent else a


# ---------------------------------------------------------------- Bausteine

def _activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def skin(name, verts, edges, radii, col, root=0, levels=2, smooth=True):
    """Haut um ein Punkt-Skelett. radii: Zahl oder (x, y) je Punkt."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    _activate(ob)
    ob.modifiers.new("skin", "SKIN")
    for i, r in enumerate(radii):
        rx, ry = (r, r) if not isinstance(r, tuple) else r
        me.skin_vertices[0].data[i].radius = (rx * SKIN_FATTEN, ry * SKIN_FATTEN)
        me.skin_vertices[0].data[i].use_root = (i == root)
    s = ob.modifiers.new("sub", "SUBSURF")
    s.levels = levels
    bpy.ops.object.modifier_apply(modifier="skin")
    bpy.ops.object.modifier_apply(modifier="sub")
    for p in me.polygons:
        p.use_smooth = smooth
    me.materials.append(bk.material("m" + col, col, rough=0.8))
    return ob


def chain(n):
    return [(i, i + 1) for i in range(n - 1)]


def tube(name, pts, radii, col, levels=1):
    return skin(name, pts, chain(len(pts)), radii, col, levels=levels)


def ball(r, loc, col, squash=(1.0, 1.0, 1.0), subdiv=2):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdiv, radius=r,
                                          location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.scale = squash
    bpy.ops.object.transform_apply(scale=True)
    ob.location = loc
    bpy.ops.object.transform_apply(location=True)
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.data.materials.append(bk.material("m" + col, col, rough=0.75))
    return ob


def cone(r1, r2, depth, loc, col, rot=(0, 0, 0), verts=12, smooth=True):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2,
                                    depth=depth, location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.rotation_euler = rot
    bpy.ops.object.transform_apply(rotation=True)
    ob.location = loc
    bpy.ops.object.transform_apply(location=True)
    for p in ob.data.polygons:
        p.use_smooth = smooth
    ob.data.materials.append(bk.material("m" + col, col, rough=0.6))
    return ob


def slab(size, loc, col, rot=(0, 0, 0)):
    """Flache Platte (Schild, Wappenrock, Klinge). size = Halbmasse."""
    return bk.box(size, loc, col, 0.004, rot=rot, segments=1)


def lump(loc, r, col, strength=0.4, squash=0.8, seed=0, subdiv=2):
    """Verformter Ball - Laub, Maehne, Fell."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdiv, radius=r,
                                          location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.scale = (1.0, 1.0, squash)
    bpy.ops.object.transform_apply(scale=True)
    off = mathutils.Vector((seed * 1.7, seed * 0.9, seed * 2.3))
    for v in ob.data.vertices:
        n = mathutils.noise.noise(v.co * (2.2 / r) + off)
        v.co += v.normal * n * strength * r
    ob.location = loc
    bpy.ops.object.transform_apply(location=True)
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.data.materials.append(bk.material("m" + col, col, rough=0.9))
    return ob


def rot_z(p, ang, cx=0.0, cy=0.0):
    x, y, z = p
    c, s = math.cos(ang), math.sin(ang)
    x -= cx
    y -= cy
    return (cx + x * c - y * s, cy + x * s + y * c, z)


# ---------------------------------------------------------------- Zweibeiner

class Pose:
    """Haltung eines Zweibeiners - wohin die Haende und der Kopf kommen.

    Alle Masse relativ zur Koerperhoehe H (Scheitel). Das Vorbild hat einen
    Kopf von rund einem Siebtel der Hoehe; Zwerg und Goblin weichen davon
    bewusst ab.
    """

    def __init__(self, H=1.8, head=1 / 7.2, leg=0.53, shoulder=0.13,
                 hip=0.075, twist=18.0, step=0.10, hunch=0.0, bulk=1.0,
                 lean=0.0):
        self.H = H
        self.head_r = H * head * 0.5
        self.leg = H * leg
        self.shoulder = H * shoulder
        self.hip = H * hip
        self.twist = math.radians(twist)
        self.step = H * step
        self.hunch = H * hunch
        self.bulk = bulk
        self.lean = H * lean


def biped(name, P, mats, arms="ready", legs="stride"):
    """Beine, Becken, Rumpf, Arme, Hals. Gibt (teile, punkte) zurueck.

    mats: dict mit legs, torso, arms, skin. punkte: Kopf, linke/rechte Hand,
    Schulterlinie - dort setzen Kopfschmuck, Waffen, Schild an.
    """
    H = P.H
    L = P.leg
    s = P.step
    b = P.bulk
    parts = []
    # Beine: linkes vor (Standbein), rechtes zurueck.
    if legs == "sit":
        # Reiter: Oberschenkel nach vorn-aussen ueber den Pferderuecken,
        # Unterschenkel haengt an der Flanke herab.
        sw = P.sit_w if hasattr(P, "sit_w") else 0.16 * H
        lv = [
            (0.0, 0.0, L + 0.03 * H),
            (P.hip, -0.01 * H, L),
            (sw, -0.20 * H, L - 0.04 * H),
            (sw * 1.05, -0.16 * H, L - 0.27 * H),
            (sw * 1.05, -0.22 * H, L - 0.29 * H),
            (-P.hip, -0.01 * H, L),
            (-sw, -0.20 * H, L - 0.04 * H),
            (-sw * 1.05, -0.16 * H, L - 0.27 * H),
            (-sw * 1.05, -0.22 * H, L - 0.29 * H),
        ]
    else:
        lv = None
    lv = lv or [
        (0.0, 0.0, L + 0.03 * H),                        # 0 Becken
        (P.hip, -0.01 * H, L),                           # 1 Huefte L
        (P.hip * 1.05, -0.55 * s, L * 0.52),             # 2 Knie L
        (P.hip * 1.0, -0.45 * s, 0.045 * H),             # 3 Knoechel L
        (P.hip * 1.0, -0.45 * s - 0.07 * H, 0.02 * H),   # 4 Zeh L
        (-P.hip, 0.01 * H, L),                           # 5 Huefte R
        (-P.hip * 1.05, 0.45 * s, L * 0.50),             # 6 Knie R
        (-P.hip * 1.1, 0.80 * s, 0.045 * H),             # 7 Knoechel R
        (-P.hip * 1.1, 0.80 * s - 0.07 * H, 0.02 * H),   # 8 Zeh R
    ]
    th = 0.052 * H * b
    lr = [0.075 * H * b, th, th * 0.72, th * 0.48, th * 0.42,
          th, th * 0.72, th * 0.48, th * 0.42]
    # JEDES BEIN EINE EIGENE KETTE vom Becken aus. Als ein Netz mit dem
    # Becken als Mittelpunkt erzeugte der Skin-Modifier bei kraeftigen
    # Figuren (Oger, Behemoth) eckige Krausen, die auch die Glaettung nicht
    # mehr rund bekam.
    for a in (1, 5):
        idx = [0, a, a + 1, a + 2, a + 3]
        pv = [lv[i] for i in idx]
        pv[0] = (lv[a][0] * 0.3, lv[a][1], lv[0][2])
        pr = [lr[1] * 0.95] + [lr[i] for i in idx[1:]]
        parts.append(skin(name + "_leg", pv, chain(5), pr, mats["legs"]))
    if mats.get("boots") and legs != "sit":
        for a, t in ((3, 4), (7, 8)):
            ax, ay, az = lv[a]
            parts.append(tube(name + "_boot", [(ax, ay + 0.005 * H, az + 0.11 * H),
                                               (ax, ay, az), lv[t]],
                              [th * 0.62, th * 0.58, th * 0.5], mats["boots"]))

    # Rumpf mit Drehung gegen die Huefte.
    tw = P.twist
    top = L + 0.30 * H

    def R(x, y, z):
        return rot_z((x, y, z), tw)

    hy = -P.hunch
    tv = [
        (0.0, 0.0, L + 0.03 * H),                        # 0 Becken
        R(0.0, hy * 0.3 - 0.005 * H, L + 0.12 * H),      # 1 Taille
        R(0.0, hy * 0.7 - 0.01 * H, top - 0.06 * H),     # 2 Brust
        R(0.0, hy * 1.2 - 0.015 * H, top + 0.025 * H),   # 3 Hals
    ]
    tr = [0.072 * H * b, (0.068 * H * b, 0.05 * H * b),
          (0.095 * H * b, 0.062 * H * b), 0.03 * H * b]
    parts.append(skin(name + "_torso", tv, chain(4), tr, mats["torso"]))

    # Arme. "ready": rechte Hand vorn auf Hueft-/Brusthoehe (Waffe), linke
    # Hand vorn tiefer (Schild/Bogengriff). "raise": rechte Hand erhoben.
    sh_z = top - 0.02 * H
    shL = R(P.shoulder, hy, sh_z)
    shR = R(-P.shoulder, hy, sh_z)
    if arms == "raise":
        elR = R(-P.shoulder * 1.4, hy + 0.02 * H, sh_z + 0.05 * H)
        haR = R(-P.shoulder * 1.2, hy - 0.06 * H, sh_z + 0.20 * H)
    elif arms == "reach":
        elR = R(-P.shoulder * 1.1, hy - 0.12 * H, sh_z - 0.03 * H)
        haR = R(-P.shoulder * 0.9, hy - 0.28 * H, sh_z - 0.02 * H)
    elif arms == "low":
        elR = R(-P.shoulder * 1.5, hy - 0.10 * H, sh_z - 0.22 * H)
        haR = R(-P.shoulder * 1.4, hy - 0.22 * H, 0.06 * H)
    elif arms == "wide":
        elR = R(-P.shoulder * 1.9, hy - 0.02 * H, sh_z - 0.10 * H)
        haR = R(-P.shoulder * 2.0, hy - 0.10 * H, sh_z - 0.22 * H)
    else:
        elR = R(-P.shoulder * 1.35, hy + 0.03 * H, sh_z - 0.15 * H)
        haR = R(-P.shoulder * 1.0, hy - 0.14 * H, sh_z - 0.22 * H)
    elL = R(P.shoulder * 1.35, hy - 0.02 * H, sh_z - 0.15 * H)
    haL = R(P.shoulder * 0.9, hy - 0.17 * H, sh_z - 0.22 * H)
    if arms == "reach":
        elL = R(P.shoulder * 1.1, hy - 0.12 * H, sh_z - 0.05 * H)
        haL = R(P.shoulder * 0.9, hy - 0.27 * H, sh_z - 0.06 * H)
    elif arms == "low":
        elL = R(P.shoulder * 1.5, hy - 0.10 * H, sh_z - 0.22 * H)
        haL = R(P.shoulder * 1.4, hy - 0.20 * H, 0.06 * H)
    elif arms == "wide":
        elL = R(P.shoulder * 1.9, hy - 0.02 * H, sh_z - 0.10 * H)
        haL = R(P.shoulder * 2.0, hy - 0.10 * H, sh_z - 0.22 * H)
    ar = 0.034 * H * b
    # Arme ebenfalls je eine eigene Kette (siehe Beine).
    for sh, el, ha in ((shL, elL, haL), (shR, elR, haR)):
        inner = (sh[0] * 0.55 + tv[2][0] * 0.45, sh[1] * 0.55 + tv[2][1] * 0.45,
                 sh[2] - 0.01 * H)
        parts.append(skin(name + "_arm", [inner, sh, el, ha], chain(4),
                          [ar * 1.05, ar, ar * 0.8, ar * 0.62], mats["arms"]))
    # Haende als kleine Kugeln in Hautfarbe (oder Handschuh).
    for h in (haL, haR):
        parts.append(ball(ar * 0.95, h, mats.get("hands", mats["skin"]), subdiv=1))

    head = (tv[3][0], tv[3][1] - 0.005 * H, tv[3][2] + P.head_r * 1.05)
    parts.append(ball(P.head_r, head, mats["skin"], squash=(0.92, 1.0, 1.08)))
    pts = dict(head=head, handL=haL, handR=haR, shL=shL, shR=shR,
               chest=tv[2], pelvis=tv[0], waist=tv[1], top=top, tw=tw,
               footL=lv[3], footR=lv[7])
    return parts, pts


def tabard(name, P, pts, col, trim=None, strip=True):
    """Waffenrock: ausgestellter Rock um die Huefte plus eine Bahn vorn.

    ZWEI FLACHE PLATTEN (vorn und hinten, so der erste Anlauf) lasen sich
    von der Seite als Kasten - und von der Seite sieht man die Figuren auf
    dem Brett fast immer. Ein Rock hat aus jeder Richtung dieselbe Form.
    """
    H = P.H
    b = P.bulk
    parts = []
    z_top = P.leg + 0.10 * H
    z_bot = P.leg - 0.13 * H
    r_top = 0.085 * H * b
    r_bot = 0.115 * H * b
    parts.append(cone(r_bot, r_top, z_top - z_bot, (0, 0, (z_top + z_bot) / 2),
                      col, verts=18))
    if trim:
        parts.append(cone(r_bot * 1.03, r_bot * 1.0, 0.02 * H,
                          (0, 0, z_bot + 0.01 * H), trim, verts=18))
    # Vorderbahn von der Brust bis zum Rocksaum.
    if strip:
        zt = pts["chest"][2] + 0.03 * H
        h = (zt - z_bot) * 0.5
        tw = pts["tw"] * 0.6
        c = rot_z((0, -0.088 * H * b, z_bot + h), tw)
        parts.append(slab((0.05 * H * b, 0.006, h), c, col, rot=(0, 0, tw)))
    # Guertel.
    parts.append(cone(r_top * 1.02, r_top * 1.02, 0.03 * H,
                      (0, 0, z_top - 0.005 * H), LEATHER_DARK, verts=18))
    return parts


def cape(name, P, pts, col):
    """Umhang hinten: Bahn von den Schultern bis zur Wade, leicht wehend."""
    H = P.H
    sh = pts["chest"]
    zt = pts["top"]
    zb = 0.18 * H
    w = 0.10 * H * P.bulk
    vs, fs = [], []
    rows = 5
    for i in range(rows):
        t = i / (rows - 1)
        z = zt - (zt - zb) * t
        y = 0.07 * H + t * 0.10 * H
        ww = w * (1.0 + 0.3 * t)
        for x in (-ww, 0.0, ww):
            vs.append(rot_z((x, y, z), pts["tw"]))
    for i in range(rows - 1):
        for j in range(2):
            a = i * 3 + j
            fs.append((a, a + 1, a + 4, a + 3))
    me = bpy.data.meshes.new(name + "_cape")
    me.from_pydata(vs, [], fs)
    ob = bpy.data.objects.new(name + "_cape", me)
    bpy.context.collection.objects.link(ob)
    _activate(ob)
    sol = ob.modifiers.new("solid", "SOLIDIFY")
    sol.thickness = 0.012 * H
    bpy.ops.object.modifier_apply(modifier="solid")
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(bk.material("m" + col, col, rough=0.9))
    return [ob]


# ---------------------------------------------------------------- Kopfteile

def helm(kind, P, pts, mats):
    H = P.H
    x, y, z = pts["head"]
    r = P.head_r
    out = []
    if kind == "helm_conical":
        out.append(cone(r * 1.12, r * 0.15, r * 1.3, (x, y, z + r * 0.55),
                        STEEL, verts=16))
        out.append(cone(r * 1.18, r * 1.18, r * 0.18, (x, y, z + r * 0.05),
                        STEEL_DARK, verts=16))
        out.append(slab((r * 0.07, r * 0.07, r * 0.35), (x, y - r * 1.0, z - r * 0.1),
                        STEEL))
    elif kind == "helm_great":
        # Topfhelm mit runder Kalotte und Sehschlitz, Helmbusch.
        out.append(cone(r * 1.08, r * 1.08, r * 1.6, (x, y, z), STEEL, verts=16))
        out.append(ball(r * 1.08, (x, y, z + r * 0.8), STEEL, squash=(1, 1, 0.55)))
        out.append(slab((r * 0.75, r * 0.04, r * 0.06), (x, y - r * 1.06, z + r * 0.15),
                        "#202226"))
        out.append(lump((x, y + r * 0.2, z + r * 1.45), r * 0.5,
                        mats.get("plume", "#a8342c"), squash=0.7, seed=3))
    elif kind == "helm_horned":
        out.append(cone(r * 1.1, r * 1.0, r * 1.5, (x, y, z), STEEL_DARK, verts=16))
        out.append(ball(r * 1.05, (x, y, z + r * 0.75), STEEL_DARK, squash=(1, 1, 0.6)))
        for sx in (-1, 1):
            out.append(tube("horn", [(x + sx * r * 0.8, y, z + r * 0.6),
                                     (x + sx * r * 1.6, y + r * 0.1, z + r * 1.1),
                                     (x + sx * r * 1.9, y - r * 0.2, z + r * 1.9)],
                            [r * 0.22, r * 0.14, r * 0.04], "#d9d0b6"))
    elif kind == "cap":
        out.append(ball(r * 1.08, (x, y + r * 0.05, z + r * 0.25), LEATHER,
                        squash=(1, 1, 0.7)))
        out.append(lump((x - r * 0.4, y + r * 0.4, z + r * 0.9), r * 0.35,
                        mats.get("plume", GOLD), squash=0.5, seed=5))
    elif kind in ("hood", "cowl"):
        col = mats.get("hood", mats["torso"])
        out.append(ball(r * 1.25, (x, y + r * 0.18, z + r * 0.12), col,
                        squash=(1, 1.05, 1.15)))
        out.append(cone(r * 1.0, r * 0.1, r * 1.3, (x, y + r * 0.7, z + r * 0.3),
                        col, rot=(math.radians(-60), 0, 0), verts=10))
        # Gesichtsoeffnung dunkel.
        out.append(ball(r * 0.7, (x, y - r * 0.62, z), "#1c1a1a",
                        squash=(1, 0.5, 1.1)))
    elif kind == "halo":
        out.append(lump((x, y + r * 0.1, z + r * 0.45), r * 0.95, "#c9a86a",
                        squash=0.6, seed=9))
        bpy.ops.mesh.primitive_torus_add(major_radius=r * 1.1, minor_radius=r * 0.08,
                                         location=(x, y + r * 0.1, z + r * 1.6))
        ob = bpy.context.active_object
        ob.data.materials.append(bk.material("halo", "#f2d98a", rough=0.3))
        out.append(ob)
    elif kind == "beard":
        out.append(lump((x, y - r * 0.55, z - r * 0.55), r * 0.85, "#8a5a32",
                        squash=1.2, seed=2))
        out.append(cone(r * 1.1, r * 0.4, r * 1.0, (x, y, z + r * 0.55), STEEL,
                        verts=16))
    elif kind == "tusked":
        for sx in (-1, 1):
            out.append(cone(r * 0.13, r * 0.02, r * 0.6,
                            (x + sx * r * 0.45, y - r * 0.85, z - r * 0.25),
                            "#e8e0c8", rot=(math.radians(-20), 0, 0), verts=6))
        out.append(ball(r * 1.0, (x, y + r * 0.1, z + r * 0.35), STEEL_DARK,
                        squash=(1, 1, 0.6)))
    elif kind == "eared":
        for sx in (-1, 1):
            out.append(cone(r * 0.35, r * 0.02, r * 1.4,
                            (x + sx * r * 1.25, y + r * 0.1, z + r * 0.25),
                            mats["skin"], rot=(0, math.radians(sx * 75), 0), verts=6))
    elif kind == "fanged":
        out.append(ball(r * 1.02, (x, y + r * 0.1, z + r * 0.35), "#1c1820",
                        squash=(1, 1, 0.55)))
    elif kind in ("skull", "skull_glow"):
        # Knochenschaedel: Augenhoehlen dunkel (oder gluehend).
        eye = "#7dffb0" if kind == "skull_glow" else "#1a1814"
        for sx in (-1, 1):
            out.append(ball(r * 0.22, (x + sx * r * 0.38, y - r * 0.78, z + r * 0.1),
                            eye, subdiv=1))
        out.append(ball(r * 0.6, (x, y - r * 0.45, z - r * 0.65), mats["skin"],
                        squash=(1, 0.8, 0.6)))
    elif kind == "rotten":
        out.append(ball(r * 0.25, (x + r * 0.35, y - r * 0.8, z + r * 0.1),
                        "#d8d0a0", subdiv=1))
    elif kind == "small":
        pass
    elif kind == "one_eye":
        out.append(ball(r * 0.42, (x, y - r * 0.82, z + r * 0.15), "#f2efe6",
                        subdiv=2))
        out.append(ball(r * 0.2, (x, y - r * 1.12, z + r * 0.15), "#2a1c12",
                        subdiv=1))
    return out


# ---------------------------------------------------------------- Waffen

def weapon(kind, P, pts, mats):
    H = P.H
    hx, hy, hz = pts["handR"]
    lx, ly, lz = pts["handL"]
    out = []
    if kind == "spear":
        # Waagerecht zum Gegner eingelegt - hochgereckt kreuzt er bei der
        # Draufsicht das Gesicht (Pilot It. 71).
        # KUERZER ALS ECHT (1.0 statt 1.25 H): fit_to_tier normiert die
        # Raumdiagonale, und jede Spiessverlaengerung machte den Traeger
        # kleiner.
        ln = 1.0 * H
        out.append(tube("shaft", [(hx, hy + 0.30 * H, hz + 0.02 * H),
                                  (hx, hy - ln + 0.30 * H, hz + 0.10 * H)],
                        [0.013 * H, 0.012 * H], WOOD))
        out.append(cone(0.03 * H, 0.0, 0.13 * H,
                        (hx, hy - ln + 0.23 * H, hz + 0.11 * H), STEEL,
                        rot=(math.radians(93), 0, 0), verts=4, smooth=False))
    elif kind == "lance":
        # AUFRECHT mit Wimpel, wie der Champion im Vorbild. Waagerecht
        # eingelegt machte die Lanze das Pferd so lang, dass die
        # Grundflaechen-Grenze den ganzen Kavalier kleiner zog als den
        # Moench eine Stufe darunter.
        ln = 1.25 * H
        top = (hx, hy - 0.20 * H, hz + ln)
        out.append(tube("lance", [(hx, hy + 0.04 * H, hz - 0.25 * H), top],
                        [0.025 * H, 0.012 * H], mats.get("lance", "#d8c8a0")))
        out.append(cone(0.06 * H, 0.05 * H, 0.05 * H, (hx, hy + 0.01 * H, hz + 0.1 * H),
                        STEEL, verts=12))
        pen = mats.get("pennant", GOLD)
        vs = [(hx, top[1] + 0.02 * H, top[2] - 0.08 * H),
              (hx, top[1] + 0.05 * H, top[2] - 0.30 * H),
              (hx, top[1] + 0.40 * H, top[2] - 0.17 * H)]
        out.append(sheet("pennant", vs, [(0, 1, 2)], pen, 0.01 * H))
    elif kind in ("sword", "twin_swords", "greatsword"):
        hands = [(hx, hy, hz)]
        if kind == "twin_swords":
            hands.append((lx, ly, lz))
        blade = 0.42 * H if kind != "greatsword" else 0.62 * H
        for i, (x, y, z) in enumerate(hands):
            ang = math.radians(-35 if i == 0 else 35)
            tip = (x, y - math.sin(math.radians(55)) * blade,
                   z + math.cos(math.radians(55)) * blade)
            if i == 1:
                tip = (x + 0.15 * H, y - 0.3 * blade, z + 0.9 * blade)
            out.append(tube("blade", [(x, y, z), tip],
                            [0.018 * H, 0.006 * H], "#c9d2db"))
            out.append(slab((0.05 * H, 0.008 * H, 0.008 * H), (x, y, z + 0.01 * H),
                            GOLD))
    elif kind in ("bow", "longbow"):
        # Bogen QUER vor dem Koerper in der linken Hand (It. 61): senkrecht
        # gehalten ist er bei Zellgroesse ein Strich.
        span = 0.62 * H if kind == "longbow" else 0.48 * H
        pts_b = []
        for k in range(7):
            a = math.radians(-60 + 20 * k)
            pts_b.append((lx + math.sin(a) * span * 0.5,
                          ly - 0.05 * H - math.cos(a) * 0.09 * H,
                          lz + 0.04 * H))
        out.append(tube("bow", pts_b, [0.008 * H, 0.011 * H, 0.014 * H, 0.016 * H,
                                       0.014 * H, 0.011 * H, 0.008 * H], WOOD))
        out.append(tube("string", [pts_b[0], (lx, ly + 0.04 * H, lz + 0.04 * H),
                                   pts_b[-1]], [0.003 * H] * 3, "#e8e2d0"))
        out.append(cone(0.035 * H, 0.03 * H, 0.32 * H,
                        (-0.06 * H, 0.09 * H, pts["top"] - 0.04 * H), LEATHER,
                        rot=(math.radians(-15), math.radians(20), 0)))
    elif kind == "crossbow":
        out.append(slab((0.022 * H, 0.20 * H, 0.026 * H), (hx, hy - 0.10 * H, hz),
                        WOOD))
        out.append(tube("xbow", [(hx - 0.17 * H, hy - 0.26 * H, hz),
                                 (hx, hy - 0.29 * H, hz),
                                 (hx + 0.17 * H, hy - 0.26 * H, hz)],
                        [0.008 * H, 0.012 * H, 0.008 * H], STEEL_DARK))
    elif kind == "axe":
        out.append(tube("haft", [(hx, hy, hz - 0.06 * H), (hx, hy - 0.08 * H, hz + 0.34 * H)],
                        [0.013 * H, 0.012 * H], WOOD))
        out.append(slab((0.006 * H, 0.08 * H, 0.06 * H),
                        (hx, hy - 0.13 * H, hz + 0.30 * H), STEEL))
    elif kind == "dagger":
        out.append(tube("dagger", [(hx, hy, hz), (hx, hy - 0.16 * H, hz + 0.05 * H)],
                        [0.012 * H, 0.004 * H], "#c9d2db"))
    elif kind == "club":
        out.append(tube("club", [(hx, hy + 0.04 * H, hz - 0.04 * H),
                                 (hx - 0.03 * H, hy - 0.14 * H, hz + 0.32 * H)],
                        [0.025 * H, 0.06 * H], WOOD, levels=2))
    elif kind == "boulder":
        out.append(lump((hx, hy - 0.06 * H, hz + 0.14 * H), 0.12 * H, "#8a857a",
                        strength=0.3, squash=0.9, seed=4))
    elif kind in ("staff", "staff_orb"):
        out.append(tube("staff", [(hx, hy, hz - 0.62 * H), (hx, hy, hz + 0.40 * H)],
                        [0.014 * H, 0.012 * H], WOOD))
        if kind == "staff_orb":
            out.append(ball(0.05 * H, (hx, hy, hz + 0.45 * H), "#7dffb0"))
    elif kind == "branch":
        out.append(tube("branch", [(hx, hy, hz), (hx - 0.05 * H, hy - 0.2 * H, hz + 0.25 * H),
                                   (hx - 0.12 * H, hy - 0.28 * H, hz + 0.42 * H)],
                        [0.04 * H, 0.025 * H, 0.012 * H], "#5a4128"))
    return out


def shield(P, pts, col, trim):
    """Rundschild vorn an der linken Hand (It. 61: seitlich war es eine Kante)."""
    H = P.H
    lx, ly, lz = pts["handL"]
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.15 * H,
                                        depth=0.025 * H, location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.rotation_euler = (math.radians(82), 0, math.radians(-25))
    bpy.ops.object.transform_apply(rotation=True)
    ob.location = (lx + 0.03 * H, ly - 0.05 * H, lz + 0.07 * H)
    bpy.ops.object.transform_apply(location=True)
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.data.materials.append(bk.material("m" + col, col, rough=0.7))
    boss = ball(0.03 * H, (lx + 0.02 * H, ly - 0.08 * H, lz + 0.07 * H), trim, subdiv=1)
    return [ob, boss]


def feather_wings(P, pts, col, span=1.0, up=0.55):
    """Federfluegel: je Seite ein Facher aus Federbahnen, nach oben-hinten.

    Flach von OBEN sichtbar - senkrechte Platten sind aus der Kamera kaum
    zu sehen (It. 54).
    """
    H = P.H
    out = []
    cx, cy, cz = pts["chest"]
    root_z = cz + 0.04 * H
    for sx in (-1, 1):
        for k in range(6):
            a = math.radians(25 + k * 12)
            ln = (0.55 - 0.05 * k) * H * span
            x0 = cx + sx * 0.07 * H
            p0 = (x0, cy + 0.08 * H, root_z)
            p1 = (x0 + sx * math.cos(a) * ln * 0.55, cy + 0.14 * H + k * 0.01 * H,
                  root_z + math.sin(a) * ln * up)
            p2 = (x0 + sx * math.cos(a) * ln, cy + 0.22 * H + k * 0.02 * H,
                  root_z + math.sin(a) * ln * up * 1.4)
            out.append(tube("feather", [p0, p1, p2],
                            [0.03 * H, 0.04 * H, 0.012 * H], col))
    return out


# ---------------------------------------------------------------- Hilfen

def move(parts, d):
    """Teile verschieben (Lage ist bereits in die Punkte eingebacken)."""
    for ob in parts:
        for v in ob.data.vertices:
            v.co.x += d[0]
            v.co.y += d[1]
            v.co.z += d[2]
    return parts


def shift_pts(pts, d):
    out = {}
    for k, v in pts.items():
        if isinstance(v, tuple) and len(v) == 3:
            out[k] = (v[0] + d[0], v[1] + d[1], v[2] + d[2])
        elif k == "top":
            out[k] = v + d[2]
        else:
            out[k] = v
    return out


def sheet(name, verts, faces, col, thick, rough=0.85):
    """Flaeche mit Dicke - Flughaut, Umhang, Satteldecke."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    _activate(ob)
    sol = ob.modifiers.new("solid", "SOLIDIFY")
    sol.thickness = thick
    sol.offset = 0.0
    bpy.ops.object.modifier_apply(modifier="solid")
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(bk.material("m" + col, col, rough=rough))
    return ob


# ---------------------------------------------------------------- Vierbeiner

class Quad:
    """Masse eines Vierbeiners, relativ zur Widerristhoehe 1.

    kind: horse (lange Beine, langer Hals), lion (Katze: tiefer, kraeftige
    Pranken), wolf (schmal, Kopf vorgestreckt), heavy (massig, tief).
    """

    def __init__(self, kind="horse"):
        self.kind = kind
        T = {
            #        Rumpflaenge, Beinlaenge, Rumpfdicke, Halslaenge, Halswinkel, Kopf
            "horse": (1.00, 0.74, 0.150, 0.40, 50.0, 0.38),
            "lion":  (0.92, 0.55, 0.165, 0.26, 40.0, 0.22),
            "wolf":  (0.86, 0.55, 0.120, 0.24, 28.0, 0.24),
            "heavy": (0.95, 0.48, 0.230, 0.18, 15.0, 0.26),
        }[kind]
        self.body, self.leg, self.girth, self.neck, self.neck_ang, self.head = T


def quadruped(name, Q, mats, gait=0.12):
    """Rumpf, Hals und vier Beine als EINE Haut, Kopf eigen.

    Gibt (teile, punkte) zurueck: withers (Widerrist, dort sitzt ein
    Reiter oder setzen Fluegel an), head, muzzle, tail.
    mats: body, legs (Unterbeine/Hufe), head (optional).
    """
    B, Lg, G = Q.body, Q.leg, Q.girth
    zb = Lg + G * 0.6                    # Rumpfmitte
    hip_y, sh_y = B * 0.40, -B * 0.38
    w = G * 0.55
    v = [
        (0, B * 0.55, zb + G * 0.15),    # 0 Schwanzansatz
        (0, hip_y, zb + G * 0.10),       # 1 Kruppe
        (0, 0.0, zb),                    # 2 Mitte
        (0, sh_y, zb + G * 0.15),        # 3 Brust/Widerrist
    ]
    r = [G * 0.55, G * 0.95, G * 0.92, G * 1.0]
    e = [(0, 1), (1, 2), (2, 3)]
    # Hals.
    a = math.radians(Q.neck_ang)
    n0 = v[3]
    n1 = (0, n0[1] - math.cos(a) * Q.neck * 0.5, n0[2] + math.sin(a) * Q.neck * 0.5)
    n2 = (0, n0[1] - math.cos(a) * Q.neck, n0[2] + math.sin(a) * Q.neck)
    v += [n1, n2]
    r += [G * 0.62, G * 0.42]
    e += [(3, 4), (4, 5)]
    # Beine: vorn gestreckt mit Knie, hinten mit Sprunggelenk nach hinten.
    # Diagonalgang: links vorn und rechts hinten vor.
    hooves = []
    legs = []
    for sx in (-1, 1):
        for front in (True, False):
            y0 = sh_y if front else hip_y
            fwd = (1 if (sx > 0) == front else -1) * gait * Lg
            top = (sx * w, y0, zb - G * 0.15)
            if front:
                j1 = (sx * w * 0.95, y0 - fwd * 0.3, Lg * 0.62)       # Ellbogen/Knie
                j2 = (sx * w * 0.9, y0 + fwd * 0.6, Lg * 0.30)        # Vorderfusswurzel
            else:
                j1 = (sx * w * 1.0, y0 - fwd * 0.2 - Lg * 0.12, Lg * 0.70)  # Knie (Stifle)
                j2 = (sx * w * 0.95, y0 + fwd * 0.6 + Lg * 0.14, Lg * 0.36)  # Sprunggelenk
            foot = (sx * w * 0.9, y0 + fwd, 0.035 * Lg)
            hooves.append(foot)
            th = G * (0.42 if Q.kind != "heavy" else 0.52)
            # JEDES BEIN EINE EIGENE KETTE, beginnend im Rumpf. Am Rumpf
            # angehaengt (vier Kanten an Schulter und Huefte) wurden die
            # Gelenkknoten eckig - Drache und Einhorn sahen aus wie Kisten.
            inner = (sx * w * 0.3, y0, zb)
            legs.append(([inner, top, j1, j2, foot],
                         [G * 0.6, G * 0.62, th, th * 0.62, th * 0.55]))
    parts = [skin(name + "_body", v, e, r, mats["body"], root=2)]
    for lv_, lr_ in legs:
        parts.append(skin(name + "_leg", lv_, chain(5), lr_, mats["body"]))
    # Hufe/Pfoten.
    for f in hooves:
        parts.append(ball(G * 0.30, (f[0], f[1] - G * 0.06, f[2]),
                          mats["legs"], squash=(1, 1.15, 0.7), subdiv=1))
    pts = dict(withers=(0, sh_y + G * 0.2, zb + G * 0.95), neck=n2,
               rump=v[1], tail=v[0], chest=v[3], mid=v[2], zb=zb,
               hooves=hooves)
    return parts, pts


def horse_head(Q, pts, col, dark):
    """Pferdekopf: Schaedel -> Maul als Rohr, schraeg nach unten-vorn."""
    G = Q.girth
    x, y, z = pts["neck"]
    hl = Q.head
    a = math.radians(-50)
    poll = (0, y - G * 0.05, z + G * 0.2)
    muz = (0, poll[1] - math.cos(a) * hl, poll[2] + math.sin(a) * hl)
    out = [tube("head", [poll, ((poll[0] + muz[0]) / 2, (poll[1] + muz[1]) / 2,
                                (poll[2] + muz[2]) / 2), muz],
                [hl * 0.34, hl * 0.27, hl * 0.21], col)]
    out.append(ball(hl * 0.17, (0, muz[1] - hl * 0.03, muz[2] - hl * 0.02), dark,
                    squash=(1.05, 1, 0.8), subdiv=1))
    # Ohren, Augen nach der KOPFLAENGE bemessen, nicht nach der Rumpfdicke:
    # beim schlanken Pferd waren sie sonst zwei Pixel gross.
    for sx in (-1, 1):
        out.append(cone(hl * 0.09, 0.0, hl * 0.36,
                        (sx * hl * 0.12, poll[1] + hl * 0.04, poll[2] + hl * 0.30),
                        col, rot=(math.radians(-15), math.radians(sx * 12), 0),
                        verts=6))
        out.append(ball(hl * 0.06, (sx * hl * 0.20, poll[1] - hl * 0.30,
                                    poll[2] - hl * 0.10), "#1a1612", subdiv=1))
    return out, dict(poll=poll, muzzle=muz)


def mane_tail(Q, pts, col, tail_len=0.6, mane=True):
    G = Q.girth
    out = []
    if mane:
        n0, n1 = pts["chest"], pts["neck"]
        for k in range(5):
            t = k / 4.0
            p = (0, n0[1] + (n1[1] - n0[1]) * t + G * 0.30,
                 n0[2] + (n1[2] - n0[2]) * t + G * 0.50)
            out.append(lump(p, Q.head * 0.22, col, strength=0.35, squash=1.2, seed=k))
    tx, ty, tz = pts["tail"]
    out.append(tube("tail", [(0, ty, tz), (0, ty + tail_len * 0.35, tz - tail_len * 0.1),
                             (0, ty + tail_len * 0.5, tz - tail_len * 0.5),
                             (0, ty + tail_len * 0.55, tz - tail_len * 0.85)],
                    [G * 0.16, G * 0.22, G * 0.2, G * 0.08], col))
    return out


def membrane_wing(pts_root, sx, span, col, bone, lift=0.5, back=0.3,
                  fingers=4, skin_on=True):
    """Flughaut (Drache, Fledermaus): Arm mit gespreizten Fingern, dazwischen
    Haut.

    NACH HINTEN GESCHWUNGEN, nicht seitlich hoch. Auf dem Brett sieht man
    die Figuren im Profil (sie schauen zur Gegenseite); ein Fluegel, der
    nur seitlich nach oben steht, ist von dort eine Kante - im ersten
    Anlauf stand ueber jedem Drachen ein Brett. Geschwungen hat die Flaeche
    eine Ausdehnung nach hinten, die man im Profil UND von oben sieht.
    """
    x, y, z = pts_root
    s_ = span
    elbow = (x + sx * 0.28 * s_, y + 0.12 * s_, z + 0.42 * s_ * lift)
    wrist = (x + sx * 0.42 * s_, y + 0.32 * s_, z + 0.80 * s_ * lift)
    out = [tube("warm", [(x, y, z), elbow, wrist],
                [s_ * 0.045, s_ * 0.032, s_ * 0.022], bone)]
    tips = []
    for k in range(fingers):
        t = k / max(1, fingers - 1)
        ln = s_ * (0.52 - 0.14 * t)
        d = (sx * (0.35 - 0.25 * t), 0.35 + 0.35 * t, 0.25 - 0.95 * t)
        n = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
        tip = (wrist[0] + d[0] / n * ln, wrist[1] + d[1] / n * ln,
               wrist[2] + d[2] / n * ln)
        tips.append(tip)
        out.append(tube("finger", [wrist, tip], [s_ * 0.016, s_ * 0.005], bone))
    if skin_on:
        root_b = (x, y + back * s_ * 1.6, z - s_ * 0.04)
        vs = [wrist, elbow, (x, y, z)] + tips + [root_b]
        fs = []
        n = len(tips)
        for k in range(n - 1):
            fs.append((0, 3 + k, 3 + k + 1))
        fs.append((0, 3 + n - 1, 3 + n))
        fs.append((0, 3 + n, 2, 1))
        out.append(sheet("membrane", vs, fs, col, s_ * 0.012))
    return out


def robe(name, H, col, hem=0.0, flare=1.0, lean=0.0):
    """Gewand als Glocke: Saum weit, oben schmal. Gibt (teil, schulterhoehe)."""
    z_sh = 0.80 * H
    v = [(0, -lean * 0.2, hem + 0.02 * H), (0, -lean * 0.4, hem + 0.25 * H),
         (0, -lean * 0.7, 0.55 * H), (0, -lean, z_sh), (0, -lean, z_sh + 0.05 * H)]
    r = [0.12 * H * flare, 0.095 * H * flare, 0.075 * H, 0.072 * H, 0.03 * H]
    return skin(name + "_robe", v, chain(len(v)), r, col), z_sh


def tree_body(name, H, bark, big=False):
    """Baumwesen: Wurzelbeine, Stamm, Astarme - EINE Haut aus Rinde."""
    trunk = 0.11 * H * (1.25 if big else 1.0)
    leg = 0.20 * H
    top = 0.78 * H
    v = [(0, 0, leg + 0.05 * H),                                   # 0 Becken
         (0, -0.01 * H, 0.45 * H), (0, -0.02 * H, 0.62 * H),        # 1, 2 Stamm
         (0, 0.0, top)]                                            # 3 Krone
    r = [trunk * 1.15, trunk, trunk * 0.9, trunk * 0.75]
    e = [(0, 1), (1, 2), (2, 3)]
    for sx in (-1, 1):
        i = len(v)
        v += [(sx * trunk * 0.7, -0.06 * H * sx, leg * 0.55),
              (sx * trunk * 1.1, -0.06 * H * sx - 0.06 * H, 0.03 * H)]
        r += [trunk * 0.55, trunk * 0.45]
        e += [(0, i), (i, i + 1)]
        # Wurzelzehen.
        j = len(v)
        v += [(sx * trunk * 1.6, -0.06 * H * sx - 0.12 * H, 0.015 * H)]
        r += [trunk * 0.18]
        e += [(i + 1, j)]
    hands = []
    for sx in (-1, 1):
        i = len(v)
        # Arme nach VORN gestreckt: im Profil sichtbar, seitlich steckten
        # sie hinter dem Stamm.
        el = (sx * 0.20 * H, -0.14 * H, 0.60 * H)
        ha = (sx * 0.24 * H, -0.33 * H, 0.52 * H)
        v += [el, ha]
        r += [trunk * 0.42, trunk * 0.3]
        e += [(2, i), (i, i + 1)]
        hands.append(ha)
        # Zweigfinger.
        for k in (-1, 0, 1):
            j = len(v)
            v += [(ha[0] + sx * 0.02 * H + k * 0.04 * H, ha[1] - 0.08 * H,
                   ha[2] - 0.04 * H + k * 0.03 * H)]
            r += [trunk * 0.1]
            e += [(i + 1, j)]
    parts = [skin(name + "_bark", v, e, r, bark, root=0)]
    return parts, dict(top=top, handL=hands[1], handR=hands[0], trunk=trunk,
                       face=(0, -trunk * 0.95, 0.60 * H))


def feather_wing(root, sx, span, col, col2, lift=0.6, back=0.35,
                 spread=0.45):
    """Federfluegel als FLACHE Schwinge mit gezackter Hinterkante.

    Einzelne Federrohre (feather_wings) lasen sich im Pilot wie Finger;
    eine Flaeche mit Federspitzen am Rand liest sich als Fluegel. Eine
    zweite, kleinere Lage (Deckfedern) in der Zweitfarbe gibt Tiefe.

    Die Vorderkante laeuft nach HINTEN-oben-aussen (siehe membrane_wing:
    im Profil war ein seitlich gestellter Fluegel eine Kante).
    """
    x, y, z = root
    out = []
    for layer, (k, c, dz) in enumerate(((1.0, col, 0.0), (0.55, col2, 0.015 * span))):
        s_ = span * k
        lead = []
        for t in (0.0, 0.35, 0.7, 1.0):
            lead.append((x + sx * spread * s_ * t,
                         y + 0.55 * s_ * t * t - 0.04 * s_ * math.sin(math.pi * t),
                         z + dz + lift * s_ * t * (1.5 - 0.5 * t)))
        tip = lead[-1]
        rb = (x + sx * 0.03 * s_, y + back * s_ * 1.3, z + dz - 0.06 * s_)
        trail = []
        n = 9
        for i in range(1, n):
            t = i / n
            px = tip[0] + (rb[0] - tip[0]) * t
            py = tip[1] + (rb[1] - tip[1]) * t
            pz = tip[2] + (rb[2] - tip[2]) * t
            # Federspitzen: jede zweite Ecke nach hinten-unten gezogen.
            o = 0.07 * s_ if i % 2 else 0.0
            trail.append((px, py + o * 0.6, pz - o))
        vs = lead + trail + [rb]
        cx = sum(v[0] for v in vs) / len(vs)
        cy = sum(v[1] for v in vs) / len(vs)
        cz = sum(v[2] for v in vs) / len(vs)
        vs.append((cx + sx * 0.02 * s_, cy, cz))
        c_i = len(vs) - 1
        fs = [(c_i, i, i + 1) for i in range(len(vs) - 2)]
        fs.append((c_i, len(vs) - 2, 0))
        out.append(sheet("wing", vs, fs, c, 0.012 * span))
        if layer == 0:
            out.append(tube("wbone", lead[:3], [0.035 * span, 0.03 * span,
                                                0.018 * span], col))
    return out


def caparison(Q, pts, col, trim):
    """Satteldecke ueber Ruecken und Flanken - die Fraktionsfarbe am Pferd."""
    G = Q.girth
    zb = pts["zb"]
    y0, y1 = pts["chest"][1] + G * 0.2, pts["rump"][1] - G * 0.1
    rows, cols = 4, 9
    vs, fs = [], []
    for i in range(rows):
        y = y0 + (y1 - y0) * i / (rows - 1)
        for j in range(cols):
            a = math.pi * (0.08 + 0.84 * j / (cols - 1))
            rr = G * 1.32
            vs.append((math.cos(a) * rr, y, zb + G * 0.15 + math.sin(a) * rr * 0.95
                       - (G * 0.35 if j in (0, cols - 1) else 0.0)))
    for i in range(rows - 1):
        for j in range(cols - 1):
            a = i * cols + j
            fs.append((a, a + 1, a + cols + 1, a + cols))
    out = [sheet("capar", vs, fs, col, G * 0.05)]
    # Goldborte unten an beiden Seiten.
    for j in (0, cols - 1):
        bot = [vs[i * cols + j] for i in range(rows)]
        out.append(tube("trim", bot, [G * 0.06] * rows, trim, levels=1))
    return out
