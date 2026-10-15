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


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def foot(name, ankle, toe, w, col):
    """Fuss/Stiefel als verjuengter Keil statt runder Kugel - flache Sohle,
    harte Kante. Ein Wurstende am Bein war der rundlichste Teil der Figur."""
    import mathutils as mu
    d = mu.Vector(toe) - mu.Vector(ankle)
    d.z = 0.0
    ln = max(d.length, 1e-4)
    ang = math.atan2(d.x, -d.y)
    c = ((ankle[0] + toe[0]) / 2, (ankle[1] + toe[1]) / 2, w * 0.55)
    ob = bk.box((w * 0.85, ln * 0.62, w * 0.55), c, col, w * 0.25,
                rot=(0, 0, ang), taper=0.8, segments=1)
    return ob


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
    th = 0.048 * H * b
    # JEDES BEIN EINE EIGENE KETTE vom Becken aus. Als ein Netz mit dem
    # Becken als Mittelpunkt erzeugte der Skin-Modifier bei kraeftigen
    # Figuren (Oger, Behemoth) eckige Krausen, die auch die Glaettung nicht
    # mehr rund bekam.
    #
    # FORM STATT WURST (It. 74b): Oberschenkel, schmales Knie, Wade, duenner
    # Knoechel. Mit nur Huefte-Knie-Knoechel und gleichmaessig fallender
    # Dicke war jedes Bein ein Schlauch - das "Rundliche", das der Nutzer
    # am ersten Satz bemaengelt hat.
    for a in (1, 5):
        hip, knee, ank = lv[a], lv[a + 1], lv[a + 2]
        pv = [(hip[0] * 0.3, hip[1], lv[0][2]), hip, lerp(hip, knee, 0.4), knee,
              lerp(knee, ank, 0.3), lerp(knee, ank, 0.8), ank]
        pr = [th * 0.95, th, th * 0.92, th * 0.56, th * 0.66, th * 0.42, th * 0.38]
        parts.append(skin(name + "_leg", pv, chain(len(pv)), pr, mats["legs"]))
    if legs != "sit":
        for a, t in ((3, 4), (7, 8)):
            col = mats.get("boots", mats["legs"])
            if mats.get("boots"):
                ax, ay, az = lv[a]
                parts.append(tube(name + "_boot", [(ax, ay, az + 0.12 * H), (ax, ay, az)],
                                  [th * 0.56, th * 0.5], col))
            back = lerp(lv[t], lv[a], 1.35)
            parts.append(foot(name + "_foot", (back[0], back[1], 0), lv[t], th * 0.62, col))

    # Rumpf mit Drehung gegen die Huefte.
    tw = P.twist
    top = L + 0.30 * H

    def R(x, y, z):
        return rot_z((x, y, z), tw)

    hy = -P.hunch
    # V-FORM: breite Brust, schmale Taille, eigener Hals. Vorher vier
    # Punkte mit aehnlicher Dicke - ein Fass.
    tv = [
        (0.0, 0.0, L + 0.03 * H),                        # 0 Becken
        R(0.0, hy * 0.3 - 0.005 * H, L + 0.12 * H),      # 1 Taille
        R(0.0, hy * 0.7 - 0.01 * H, top - 0.06 * H),     # 2 Brust
        R(0.0, hy * 1.2 - 0.015 * H, top + 0.025 * H),   # 3 Hals
    ]
    tv5 = [tv[0], tv[1], lerp(tv[1], tv[2], 0.55), tv[2],
           lerp(tv[2], tv[3], 0.55), tv[3]]
    tr = [(0.068 * H * b, 0.048 * H * b), (0.056 * H * b, 0.042 * H * b),
          (0.078 * H * b, 0.052 * H * b), (0.092 * H * b, 0.055 * H * b),
          0.045 * H * b, 0.024 * H * b]
    parts.append(skin(name + "_torso", tv5, chain(6), tr, mats["torso"]))

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
    ar = 0.031 * H * b
    # Arme je eine eigene Kette (siehe Beine): Schulter, Oberarm,
    # schmaler Ellbogen, Unterarm, Handgelenk.
    for sh, el, ha in ((shL, elL, haL), (shR, elR, haR)):
        inner = (sh[0] * 0.55 + tv[2][0] * 0.45, sh[1] * 0.55 + tv[2][1] * 0.45,
                 sh[2] - 0.01 * H)
        pv = [inner, sh, lerp(sh, el, 0.45), el, lerp(el, ha, 0.3),
              lerp(el, ha, 0.85)]
        parts.append(skin(name + "_arm", pv, chain(6),
                          [ar * 1.1, ar * 1.15, ar * 0.92, ar * 0.62, ar * 0.74,
                           ar * 0.46], mats["arms"]))
    # Haende: abgeflachte Kugel, nicht rund.
    for h in (haL, haR):
        parts.append(ball(ar * 0.8, h, mats.get("hands", mats["skin"]),
                          squash=(0.75, 1.0, 1.15), subdiv=1))

    head = (tv[3][0], tv[3][1] - 0.005 * H, tv[3][2] + P.head_r * 1.05)
    parts.append(ball(P.head_r, head, mats["skin"], squash=(0.86, 0.98, 1.1)))
    # Kinn und Nase: ohne sie ist der Kopf eine Kugel.
    parts.append(ball(P.head_r * 0.55, (head[0], head[1] - P.head_r * 0.45,
                                        head[2] - P.head_r * 0.55),
                      mats["skin"], squash=(1.0, 0.9, 0.8), subdiv=1))
    parts.append(cone(P.head_r * 0.16, 0.0, P.head_r * 0.4,
                      (head[0], head[1] - P.head_r * 1.0, head[2] - P.head_r * 0.05),
                      mats["skin"], rot=(math.radians(-100), 0, 0), verts=5))
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
    """Umhang: legt sich als Bogen um Schultern und Ruecken und faellt in
    Falten bis zur Wade.

    Die erste Fassung war eine flache Bahn hinter dem Ruecken - von der
    Seite ein Brett neben der Figur. Ein Bogen mit Falten wirft eigene
    Schatten und liest sich aus jeder Richtung als Stoff.
    """
    H = P.H
    zt = pts["top"]
    zb = 0.16 * H
    w = 0.10 * H * P.bulk
    vs, fs = [], []
    rows, cols = 6, 11
    for i in range(rows):
        t = i / (rows - 1)
        z = zt - (zt - zb) * t
        r = w * (1.0 + 0.55 * t)
        cy = 0.02 * H + t * 0.07 * H
        for j in range(cols):
            u = j / (cols - 1)
            ang = math.radians(-80 + 160 * u)
            fold = 1.0 + (0.10 * t) * math.sin(u * math.pi * 5)
            x = math.sin(ang) * r * fold
            y = cy + math.cos(ang) * r * 0.75 * fold
            vs.append(rot_z((x, y, z), pts["tw"]))
    for i in range(rows - 1):
        for j in range(cols - 1):
            a = i * cols + j
            fs.append((a, a + 1, a + cols + 1, a + cols))
    return [sheet(name + "_cape", vs, fs, col, 0.010 * H, rough=0.9)]


def lathe(name, profile, col, folds=0, depth=0.0, segs=24, lean=(0.0, 0.0)):
    """Drehkoerper aus einem Profil [(z, r), ...] mit Faltenwurf.

    Fuer Kutten und Gewaender: der Skin-Modifier machte daraus einen
    glatten Sack. Falten (`folds` Stueck, `depth` als Anteil des Radius)
    wachsen nach unten - oben liegt der Stoff an, unten faellt er.
    """
    vs, fs = [], []
    n = len(profile)
    zmax = max(z for z, _ in profile)
    zmin = min(z for z, _ in profile)
    for i, (z, r) in enumerate(profile):
        t = (zmax - z) / max(1e-6, zmax - zmin)
        for j in range(segs):
            a = 2 * math.pi * j / segs
            rr = r * (1.0 + depth * t * math.sin(a * folds))
            vs.append((math.cos(a) * rr + lean[0] * t, math.sin(a) * rr + lean[1] * t, z))
    for i in range(n - 1):
        for j in range(segs):
            a = i * segs + j
            b = i * segs + (j + 1) % segs
            fs.append((a, b, b + segs, a + segs))
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    _activate(ob)
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(bk.material("m" + col, col, rough=0.9))
    return ob


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
            "horse": (1.00, 0.74, 0.150, 0.42, 62.0, 0.34),
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
    # Hals kraeftig: am Ansatz fast so dick wie die Brust (Pferdehals).
    r += [G * (0.78 if Q.kind == "horse" else 0.62),
          G * (0.55 if Q.kind == "horse" else 0.42)]
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
    """Pferdekopf mit Ganaschen, flacher Stirn, Nasenruecken und Maul.

    Der erste Kopf war ein Rohr mit drei Punkten - im Spiel nicht vom
    Hals zu unterscheiden (Nutzer: "Pferdekoepfe nachbessern"). Ein
    Pferdekopf liest sich an drei Dingen: breite Backe oben hinten, langer
    schmaler Nasenruecken, Maul mit Nuestern; dazu aufgestellte Ohren.
    """
    G = Q.girth
    x, y, z = pts["neck"]
    hl = Q.head
    a = math.radians(-58)
    poll = (0, y - G * 0.02, z + G * 0.18)
    ax = (0, -math.cos(a), math.sin(a))          # Kopfachse (nach vorn-unten)

    def at(t, up=0.0):
        return (0, poll[1] + ax[1] * hl * t, poll[2] + ax[2] * hl * t + up)

    pv = [at(0.0), at(0.22), at(0.55), at(0.82), at(0.97)]
    pr = [(hl * 0.15, hl * 0.17), (hl * 0.16, hl * 0.17), (hl * 0.12, hl * 0.13),
          (hl * 0.12, hl * 0.13), (hl * 0.10, hl * 0.10)]
    out = [skin("hhead", pv, chain(5), pr, col)]
    # Ganasche: breite Backe unten hinten.
    out.append(ball(hl * 0.19, (0, at(0.25)[1] + hl * 0.06, at(0.25)[2] - hl * 0.10),
                    col, squash=(0.78, 1.0, 1.0)))
    # Maul mit Nuestern und Unterlippe.
    tip = at(0.95)
    out.append(ball(hl * 0.12, (0, tip[1] - hl * 0.01, tip[2] - hl * 0.02), dark,
                    squash=(1.0, 0.9, 0.9), subdiv=1))
    for sx in (-1, 1):
        out.append(ball(hl * 0.035, (sx * hl * 0.06, tip[1] - hl * 0.08,
                                     tip[2] + hl * 0.01), "#1a1612", subdiv=1))
        # Ohren: aufgestellt, nach vorn geneigt.
        out.append(cone(hl * 0.07, 0.0, hl * 0.30,
                        (sx * hl * 0.09, poll[1] + hl * 0.03, poll[2] + hl * 0.20),
                        col, rot=(math.radians(-18), math.radians(sx * 10), 0),
                        verts=6))
        e = at(0.22)
        out.append(ball(hl * 0.045, (sx * hl * 0.15, e[1] - hl * 0.02, e[2] + hl * 0.05),
                        "#1a1612", subdiv=1))
    return out, dict(poll=poll, muzzle=tip)


def mane_points(Q, pts, n=7):
    """Punkte auf dem MAEHNENKAMM: entlang des Halses, nach hinten-oben
    versetzt (senkrecht zur Halsrichtung). Vorher sassen die Buesche auf
    der Linie Brust-Kopf plus festem Versatz - beim steilen Hals schwebten
    sie als Kugeln neben dem Kopf."""
    G = Q.girth
    n0, n1 = pts["chest"], pts["neck"]
    a = math.radians(Q.neck_ang)
    perp = (0, math.sin(a), math.cos(a))
    out = []
    for k in range(n):
        t = 0.15 + 0.85 * k / (n - 1)
        rr = G * (0.70 - 0.25 * t)
        out.append((0, n0[1] + (n1[1] - n0[1]) * t + perp[1] * rr,
                    n0[2] + (n1[2] - n0[2]) * t + perp[2] * rr))
    return out


def mane_tail(Q, pts, col, tail_len=0.6, mane=True):
    G = Q.girth
    out = []
    if mane:
        for k, p in enumerate(mane_points(Q, pts)):
            ob = lump(p, Q.head * 0.19, col, strength=0.35, squash=1.3, seed=k)
            out.append(ob)
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

    NACH HINTEN GESCHWUNGEN, nicht seitlich hoch (im Profil sonst eine
    Kante). Seit It. 74b mit BOGENKANTE: zwischen zwei Fingern ist die Haut
    zum Handgelenk hin eingezogen und durchgewoelbt. Als glatte Dreiecke
    war es ein Brett ("Pappe"); die Bogenkante ist, woran man eine
    Flughaut erkennt.
    """
    import mathutils as mu
    x, y, z = pts_root
    s_ = span
    root = mu.Vector((x, y, z))
    elbow = root + mu.Vector((sx * 0.28 * s_, 0.12 * s_, 0.42 * s_ * lift))
    wrist = root + mu.Vector((sx * 0.42 * s_, 0.32 * s_, 0.80 * s_ * lift))
    out = [tube("warm", [tuple(root), tuple(elbow), tuple(wrist)],
                [s_ * 0.05, s_ * 0.036, s_ * 0.026], bone)]
    out.append(cone(s_ * 0.022, 0.0, s_ * 0.09, tuple(wrist + mu.Vector((0, -0.02 * s_, 0.05 * s_))),
                    "#e8dcc0", rot=(math.radians(-30), 0, 0), verts=6))
    tips = []
    for k in range(fingers):
        t = k / max(1, fingers - 1)
        ln = s_ * (0.56 - 0.14 * t)
        d = mu.Vector((sx * (0.35 - 0.25 * t), 0.35 + 0.35 * t, 0.25 - 0.95 * t))
        d.normalize()
        knuck = wrist + d * ln * 0.5 + mu.Vector((0, 0, 0.03 * s_))
        tip = wrist + d * ln
        tips.append(tip)
        out.append(tube("finger", [tuple(wrist), tuple(knuck), tuple(tip)],
                        [s_ * 0.02, s_ * 0.013, s_ * 0.004], bone))
    if skin_on:
        root_b = root + mu.Vector((0, back * s_ * 1.6, -s_ * 0.04))
        edge = tips + [root_b]
        n_up = mu.Vector((0, 0, 1))
        vs, fs = [tuple(wrist)], []
        for k in range(len(edge) - 1):
            a_, b_ = edge[k], edge[k + 1]
            mid = (a_ + b_) * 0.5
            # Bogen: Kantenmitte zum Handgelenk gezogen, Flaeche gewoelbt.
            scal = mid.lerp(wrist, 0.28)
            bel = ((wrist + a_ + b_) / 3.0) - n_up * 0.05 * s_
            i0 = len(vs)
            vs += [tuple(a_), tuple(scal), tuple(bel)]
            fs += [(0, i0, i0 + 2), (i0, i0 + 1, i0 + 2), (i0 + 2, i0 + 1, 0)]
        # Armteil: Schulter, Ellbogen, Handgelenk, Rumpfansatz.
        i0 = len(vs)
        vs += [tuple(root), tuple(elbow), tuple(root_b)]
        fs += [(0, i0 + 1, i0), (0, i0, i0 + 2)]
        out.append(sheet("membrane", vs, fs, col, s_ * 0.010))
    return out


def robe(name, H, col, hem=0.0, flare=1.0, lean=0.0):
    """Gewand als Glocke: Saum weit, oben schmal. Gibt (teil, schulterhoehe)."""
    z_sh = 0.80 * H
    # Drehkoerper mit Falten statt Skin-Sack (It. 74b): Saum weit und
    # gewellt, Taille schmal, Schultern rund.
    prof = [(hem + 0.0, 0.0), (hem + 0.005 * H, 0.17 * H * flare),
            (hem + 0.10 * H, 0.155 * H * flare), (0.35 * H, 0.12 * H * flare),
            (0.55 * H, 0.095 * H), (0.68 * H, 0.105 * H), (z_sh - 0.03 * H, 0.11 * H),
            (z_sh + 0.02 * H, 0.085 * H), (z_sh + 0.06 * H, 0.035 * H),
            (z_sh + 0.065 * H, 0.0)]
    return lathe(name + "_robe", prof, col, folds=9, depth=0.10,
                 lean=(0.0, -lean)), z_sh


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


def _darker(hexstr, k):
    h = hexstr.lstrip("#")
    c = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v * k))) for v in c)


def feather_blade(base, d, n, ln, w, col, thick):
    """Eine Feder: lanzettfoermige Flaeche mit Kiel, in der Fluegelebene."""
    import mathutils as mu
    d = mu.Vector(d).normalized()
    side = d.cross(mu.Vector(n)).normalized() * w
    b = mu.Vector(base)
    vs = [b, b + d * ln * 0.3 + side * 0.9, b + d * ln * 0.75 + side * 0.75,
          b + d * ln, b + d * ln * 0.75 - side * 0.75, b + d * ln * 0.3 - side * 0.9]
    # Leicht gewoelbt: Mitte nach oben.
    vs[3] = vs[3] - mu.Vector(n) * ln * 0.06
    fs = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5)]
    return sheet("feather", [tuple(v) for v in vs], fs, col, thick)


def feather_wing(root, sx, span, col, col2, lift=0.6, back=0.35,
                 spread=0.45):
    """Federfluegel aus EINZELNEN FEDERN in drei Lagen (It. 74b).

    Die erste Fassung war eine Flaeche mit gezackter Kante - der Nutzer
    nannte sie zu Recht Pappe. Ein Fluegel liest sich an seinen Federn:
    lange Handschwingen an der Spitze, Armschwingen am Arm, kurze
    Deckfedern obendrauf in der Zweitfarbe. Jede Feder ist eine eigene,
    leicht gewoelbte Flaeche; die Lagen liegen versetzt uebereinander.

    Die Vorderkante laeuft nach HINTEN-oben-aussen: im Profil (so sieht
    man die Figuren auf dem Brett) war ein seitlich gestellter Fluegel
    eine Kante.
    """
    import mathutils as mu
    x, y, z = root
    s_ = span
    sh = mu.Vector(root)
    el = sh + mu.Vector((sx * spread * 0.40 * s_, 0.10 * s_, lift * 0.45 * s_))
    wr = sh + mu.Vector((sx * spread * 0.75 * s_, 0.24 * s_, lift * 0.85 * s_))
    tipv = sh + mu.Vector((sx * spread * 1.0 * s_, 0.50 * s_, lift * 1.0 * s_))
    chord = mu.Vector((0, 1.0, -0.55)).normalized()   # nach hinten-unten
    n = (wr - sh).cross(chord).normalized()
    if n.z < 0:
        n = -n
    thick = 0.008 * s_
    out = [tube("wbone", [tuple(sh), tuple(el), tuple(wr), tuple(lerp(wr, tipv, 0.5))],
                [0.040 * s_, 0.034 * s_, 0.026 * s_, 0.016 * s_], col2)]
    dark = _darker(col, 0.82)
    # Handschwingen: vom Handgelenk zur Spitze, Richtung dreht von hinten
    # nach aussen.
    k_n = 7
    for k in range(k_n):
        t = k / (k_n - 1)
        base = mu.Vector(lerp(wr, tipv, t * 0.8))
        along = (tipv - wr).normalized()
        d = chord.lerp(along, 0.25 + 0.65 * t)
        out.append(feather_blade(tuple(base - n * 0.002 * k), d, n,
                                 s_ * (0.42 + 0.12 * t), s_ * 0.075, dark, thick))
    # Armschwingen: vom Ellbogen bis Handgelenk, nach hinten-unten.
    for k in range(7):
        t = k / 6
        base = mu.Vector(lerp(sh, wr, 0.2 + 0.8 * t))
        out.append(feather_blade(tuple(base + n * 0.003 * k), chord, n,
                                 s_ * (0.34 + 0.06 * t), s_ * 0.08, col, thick))
    # Deckfedern obenauf.
    for k in range(9):
        t = k / 8
        base = mu.Vector(lerp(sh, tipv, 0.05 + 0.7 * t)) + n * 0.02 * s_
        out.append(feather_blade(tuple(base), chord.lerp((tipv - sh).normalized(),
                                                         0.3 * t), n,
                                 s_ * (0.20 - 0.05 * t), s_ * 0.07, col2, thick))
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
