"""Die 28 Kampffiguren im Heroes-4-Stil, je Einheit ein Bauplan (It. 74).

Benutzt die Koerperbibliothek figures.py. Jeder Bauplan gibt eine Liste
von Teilen zurueck; gen_creatures.build verschmilzt sie, dreht die Figur
in ihre Haltung und passt sie mit fit_to_tier auf die Stufe ein - die
GROESSE wird hier also nicht festgelegt, nur die Form.

WAS AUS DEM REZEPT (gen_unit_sprites.RECIPES) KOMMT UND WAS NICHT: Kopf
und Waffe stehen dort und gelten hier weiter (helm_conical heisst auch in
3D Kegelhelm). Der Koerper dagegen ist je Einheit gebaut - "humanoid/slim"
war fuer Speertraeger, Bogenschuetze, Elf und Vampir derselbe Rumpf, und
genau das machte sie im alten Satz verwechselbar. Am Vorbild unterscheiden
sie sich an Kleidung, Haltung und Material, nicht an der Silhouettenklasse.

Vorbilder: die Kreaturenbilder von Heroes 4 (Pikeman, Crossbowman,
Crusader, Monk, Champion, Angel, Dwarf, Elf, Unicorn, Skeleton, Zombie,
Ghost, Vampire, Dark Champion, Bone Dragon, Orc, Ogre Mage, Cyclops,
Behemoth, Wolf, Thunderbird, Griffin).
"""

import math

import figures as fg
from figures import (GOLD, LEATHER, LEATHER_DARK, SKIN, STEEL, STEEL_DARK,
                     WOOD, Pose, Quad, ball, biped, cape, cone, helm, lump,
                     tabard, tube, weapon)

rad = math.radians


def _mats(**kw):
    m = dict(legs=LEATHER, torso=LEATHER, arms=LEATHER, skin=SKIN["human"])
    m.update(kw)
    return m


def _rider(unit, P, mats, mount_pts, Q, head_kind, wpn, shield_col=None,
           trim=GOLD, tabard_col=None):
    """Reiter auf den Ruecken setzen: Becken auf den Sattel."""
    parts, pts = biped(unit["id"] + "_r", P, mats, arms="ready", legs="sit")
    out = list(parts)
    if tabard_col:
        out += tabard(unit["id"], P, pts, tabard_col, trim)
    out += helm(head_kind, P, pts, mats)
    out += weapon(wpn, P, pts, mats)
    if shield_col:
        out += fg.shield(P, pts, shield_col, trim)
    wx, wy, wz = mount_pts["withers"]
    seat = (0.0, wy + Q.girth * 0.9, wz - Q.girth * 0.15)
    d = (seat[0] - pts["pelvis"][0], seat[1] - pts["pelvis"][1],
         seat[2] - pts["pelvis"][2])
    fg.move(out, d)
    return out


# ================================================================ Menschen

def men_spearman(u):
    P = Pose(H=1.8, twist=24, step=0.11)
    m = _mats(legs=fg.cloth(u), torso="#8c9096", arms="#8c9096",
              hands=LEATHER, boots=LEATHER_DARK)
    parts, pts = biped(u["id"], P, m)
    parts += tabard(u["id"], P, pts, fg.cloth(u), GOLD)
    parts += helm("helm_conical", P, pts, m)
    parts += weapon("spear", P, pts, m)
    parts += fg.shield(P, pts, fg.cloth(u), GOLD)
    return parts


def men_archer(u):
    # Armbruster (Heroes 4: Crossbowman): Lederwams ueber lila Hemd.
    P = Pose(H=1.8, twist=-20, step=0.09)
    m = _mats(legs=fg.cloth(u), torso=LEATHER, arms=fg.cloth(u),
              hands=LEATHER, boots=LEATHER_DARK, plume=GOLD)
    parts, pts = biped(u["id"], P, m)
    parts += tabard(u["id"], P, pts, fg.cloth(u), GOLD)
    parts += helm("cap", P, pts, m)
    parts += weapon("crossbow", P, pts, m)
    # Bolzenkoecher an der Huefte.
    px, py, pz = pts["pelvis"]
    parts.append(cone(0.04 * P.H, 0.035 * P.H, 0.22 * P.H,
                      (px + 0.13 * P.H, py + 0.04 * P.H, pz), LEATHER_DARK))
    return parts


def men_crusader(u):
    P = Pose(H=1.9, twist=28, step=0.12, bulk=1.15, shoulder=0.14)
    m = _mats(legs=STEEL, torso=STEEL, arms=STEEL, hands=STEEL_DARK,
              boots=STEEL_DARK, plume="#e8e2d0")
    parts, pts = biped(u["id"], P, m)
    parts += tabard(u["id"], P, pts, "#e8e2d6", fg.cloth(u))
    # Kreuz auf dem Wappenrock - das Zeichen des Kreuzritters.
    cx, cy, cz = pts["chest"]
    tw = pts["tw"] * 0.6
    for sz, sx in (((0.012, 0.007, 0.07), 0), ((0.045, 0.007, 0.012), 1)):
        c = fg.rot_z((0, -0.068 * P.H * P.bulk - 0.006, cz - 0.08 * P.H), tw)
        parts.append(fg.slab((sz[0] * P.H, sz[1], sz[2] * P.H), c, "#a8342c",
                             rot=(0, 0, tw)))
    parts += cape(u["id"], P, pts, fg.cloth(u))
    parts += helm("helm_great", P, pts, m)
    parts += weapon("twin_swords", P, pts, m)
    return parts


def men_monk(u):
    H = 1.8
    robe_col = "#8a6e52"
    body, z_sh = fg.robe(u["id"], H, robe_col, flare=1.05)
    parts = [body]
    P = Pose(H=H)
    # Kordel in Fraktionsfarbe.
    parts.append(cone(0.105 * H, 0.105 * H, 0.025 * H, (0, 0, 0.50 * H),
                      fg.cloth(u), verts=16))
    shL, shR = (0.10 * H, 0, z_sh), (-0.10 * H, 0, z_sh)
    haR = (-0.10 * H, -0.15 * H, z_sh - 0.20 * H)
    haL = (0.03 * H, -0.16 * H, z_sh - 0.24 * H)
    for sh, ha, sx in ((shL, haL, 1), (shR, haR, -1)):
        el = (sx * 0.15 * H, -0.05 * H, z_sh - 0.17 * H)
        parts.append(tube("sleeve", [sh, el, ha], [0.045 * H, 0.05 * H, 0.06 * H],
                          robe_col))
        parts.append(ball(0.03 * H, ha, SKIN["human"], subdiv=1))
    head = (0, -0.01 * H, z_sh + 0.05 * H + P.head_r)
    parts.append(ball(P.head_r, head, SKIN["human"], squash=(0.92, 1, 1.08)))
    pts = dict(head=head, handR=haR, handL=haL, top=z_sh, chest=(0, 0, z_sh))
    parts += helm("cowl", P, pts, dict(torso=robe_col, hood=robe_col,
                                      skin=SKIN["human"]))
    parts += weapon("staff", P, pts, {})
    return parts


def men_cavalier(u):
    Q = Quad("horse")
    m = dict(body="#e6e0d4", legs="#6b625a")
    parts, pts = fg.quadruped(u["id"], Q, m)
    hp, _ = fg.horse_head(Q, pts, "#e6e0d4", "#9a8f84")
    parts += hp
    parts += fg.mane_tail(Q, pts, "#d0c8b8")
    parts += fg.caparison(Q, pts, fg.cloth(u), GOLD)
    P = Pose(H=1.05, twist=0)
    rm = _mats(legs=STEEL, torso=STEEL, arms=STEEL, hands=STEEL_DARK,
               lance="#e8e0c8", pennant=fg.cloth(u))
    parts += _rider(u, P, rm, pts, Q, "helm_conical", "lance",
                    shield_col=fg.cloth(u), tabard_col=fg.cloth(u))
    return parts


def men_angel(u):
    P = Pose(H=2.0, twist=20, step=0.10, bulk=1.1)
    m = _mats(legs="#e8e4da", torso="#d9c48a", arms=SKIN["human"],
              boots="#c9a24a", skin=SKIN["human"])
    parts, pts = biped(u["id"], P, m, arms="raise")
    parts += tabard(u["id"], P, pts, "#f2eee4", GOLD)
    parts += helm("halo", P, pts, m)
    parts += weapon("sword", P, pts, m)
    cx, cy, cz = pts["chest"]
    for sx in (-1, 1):
        parts += fg.feather_wing((cx + sx * 0.06 * P.H, cy + 0.08 * P.H,
                                  cz + 0.02 * P.H), sx, 0.95 * P.H,
                                 "#f4f1ea", "#dcd6ca", lift=0.75, back=0.30)
    return parts


# ================================================================ Waldvolk

def elf_dwarf(u):
    P = Pose(H=1.3, head=1 / 4.6, leg=0.40, shoulder=0.17, hip=0.09,
             bulk=1.55, twist=16, step=0.08)
    m = _mats(legs="#4a5a7a", torso="#8c9096", arms="#8c9096", hands=LEATHER,
              boots=LEATHER_DARK, skin=SKIN["dwarf"])
    parts, pts = biped(u["id"], P, m)
    parts += tabard(u["id"], P, pts, fg.cloth(u), GOLD)
    parts += helm("beard", P, pts, m)
    parts += weapon("axe", P, pts, m)
    return parts


def elf_archer(u):
    P = Pose(H=1.95, leg=0.55, twist=-26, step=0.10, bulk=0.9)
    m = _mats(legs="#6b5a3e", torso=fg.cloth(u), arms="#5d6b3a",
              hands=SKIN["elf"], boots=LEATHER, skin=SKIN["elf"],
              hood=fg.cloth(u))
    parts, pts = biped(u["id"], P, m)
    parts += cape(u["id"], P, pts, "#4d5a2e")
    parts += helm("hood", P, pts, m)
    parts += weapon("longbow", P, pts, m)
    return parts


def _wings_on_quad(Q, pts, col, col2, span):
    wx, wy, wz = pts["withers"]
    out = []
    for sx in (-1, 1):
        out += fg.feather_wing((sx * Q.girth * 0.45, wy + Q.girth * 0.3, wz),
                               sx, span, col, col2, lift=0.6, back=0.40)
    return out


def elf_pegasus(u):
    Q = Quad("horse")
    m = dict(body="#ece8e0", legs="#a8a29a")
    parts, pts = fg.quadruped(u["id"], Q, m, gait=0.18)
    hp, _ = fg.horse_head(Q, pts, "#ece8e0", "#b8b0a6")
    parts += hp
    parts += fg.mane_tail(Q, pts, "#dcd4c4")
    parts += _wings_on_quad(Q, pts, "#f4f1ea", "#d8d2c6", 0.85)
    return parts


def elf_unicorn(u):
    Q = Quad("horse")
    m = dict(body="#f2efe8", legs="#c9b98a")
    parts, pts = fg.quadruped(u["id"], Q, m, gait=0.14)
    hp, hd = fg.horse_head(Q, pts, "#f2efe8", "#c8c0b4")
    parts += hp
    # Maehne in Regenbogenfarben wie beim Vorbild, gedeckt.
    G = Q.girth
    n0, n1 = pts["chest"], pts["neck"]
    cols = ["#c96a5a", "#d9a24a", "#8fb85a", "#5a8fc9", "#8a6ab0"]
    for k, p in enumerate(fg.mane_points(Q, pts)):
        parts.append(lump(p, Q.head * 0.19, cols[k % len(cols)], strength=0.35,
                          squash=1.3, seed=k))
    parts += fg.mane_tail(Q, pts, "#e8e0f0", mane=False)
    px, py, pz = hd["poll"]
    hl = Q.head
    parts.append(cone(hl * 0.08, 0.0, hl * 1.3, (0, py - hl * 0.45, pz + hl * 0.42),
                      GOLD, rot=(rad(-48), 0, 0), verts=8))
    return parts


def _crown(top, r, cols, n, seed, spread=1.0):
    out = []
    for k in range(n):
        a = k * 2.4
        d = r * (0.0 if k == 0 else 0.75) * spread
        p = (top[0] + math.cos(a) * d, top[1] + math.sin(a) * d * 0.8,
             top[2] + r * (0.25 if k == 0 else -0.05 + 0.1 * (k % 3)))
        out.append(lump(p, r * (0.85 if k == 0 else 0.62), cols[k % len(cols)],
                        strength=0.45, squash=0.75, seed=seed + k))
    return out


def _tree(u, big):
    H = 1.9
    bark = "#82623f" if not big else "#735638"
    parts, pts = fg.tree_body(u["id"], H, bark, big=big)
    leaf = ["#4f7a2e", "#3f6b26", "#5f8a36"] if not big else \
        ["#3f6b26", "#2f5a20", "#5a7a2a", "#8a7a2e"]
    top = (0, 0.02 * H, pts["top"] + 0.08 * H)
    parts += _crown(top, 0.22 * H if not big else 0.27 * H, leaf,
                    5 if not big else 7, 11 if not big else 21)
    # Gesicht im Stamm: zwei dunkle Augenhoehlen mit Glimmen, ein Mund.
    fx, fy, fz = pts["face"]
    for sx in (-1, 1):
        parts.append(ball(0.022 * H, (sx * 0.04 * H, fy - 0.005 * H, fz + 0.03 * H),
                          "#e8d870", subdiv=1))
    parts.append(fg.slab((0.035 * H, 0.01 * H, 0.008 * H),
                         (0, fy - 0.01 * H, fz - 0.05 * H), "#2a1e14"))
    if big:
        # Moos und Pilze an den Schultern - der alte Baum.
        for sx in (-1, 1):
            parts.append(lump((sx * 0.12 * H, -0.02 * H, 0.66 * H), 0.06 * H,
                              "#6f8a3a", squash=0.5, seed=31 + sx))
    return parts


def elf_treant(u):
    return _tree(u, False)


def elf_treefather(u):
    return _tree(u, True)


def _dragon(u, body, belly, wing, bone_only=False):
    Q = Quad("lion")
    Q.body, Q.leg, Q.girth = 1.05, 0.36, 0.20 if not bone_only else 0.07
    Q.neck, Q.neck_ang, Q.head = 0.55, 55.0, 0.30
    parts, pts = fg.quadruped(u["id"], Q, dict(body=body, legs=belly), gait=0.10)
    G = 0.22
    nx, ny, nz = pts["neck"]
    # Kopf: Schaedel und Schnauze, schraeg nach unten-vorn.
    skull = (0, ny - 0.02, nz + 0.05)
    snout = (0, ny - 0.30, nz - 0.06)
    parts.append(tube("dhead", [skull, snout], [G * 0.45, G * 0.24], body))
    for sx in (-1, 1):
        parts.append(tube("dhorn", [(sx * G * 0.25, skull[1] + 0.03, skull[2] + 0.06),
                                    (sx * G * 0.45, skull[1] + 0.18, skull[2] + 0.18),
                                    (sx * G * 0.40, skull[1] + 0.30, skull[2] + 0.22)],
                          [G * 0.12, G * 0.07, G * 0.02], "#e8dcc0"))
        eye = "#e8d050" if not bone_only else "#c83a2a"
        parts.append(ball(G * 0.07, (sx * G * 0.22, skull[1] - 0.10, skull[2] + 0.05),
                          eye, subdiv=1))
    # Schwanz in einer Kurve nach hinten und zur Seite.
    tx, ty, tz = pts["tail"]
    tail = [(0, ty, tz), (0.05, ty + 0.25, tz - 0.12), (0.18, ty + 0.45, tz - 0.25),
            (0.36, ty + 0.52, tz - 0.32), (0.52, ty + 0.48, tz - 0.34)]
    parts.append(tube("dtail", tail,
                      [Q.girth * 0.55, Q.girth * 0.42, Q.girth * 0.3,
                       Q.girth * 0.18, Q.girth * 0.05], body))
    if bone_only:
        # Rippen: Boegen beidseits der Wirbelsaeule.
        my = pts["mid"]
        for k in range(6):
            y = pts["chest"][1] + 0.08 + k * 0.10
            for sx in (-1, 1):
                parts.append(tube("rib", [(0, y, my[2] + 0.04),
                                          (sx * 0.13, y + 0.02, my[2] - 0.02),
                                          (sx * 0.12, y + 0.03, my[2] - 0.16),
                                          (sx * 0.03, y + 0.03, my[2] - 0.22)],
                                  [0.016, 0.014, 0.012, 0.008], body))
    else:
        # Rueckenzacken.
        for k in range(6):
            t = k / 5.0
            y = pts["chest"][1] + (pts["tail"][1] - pts["chest"][1]) * t
            parts.append(cone(G * 0.12, 0.0, G * 0.35,
                              (0, y, pts["zb"] + G * 1.05 - 0.04 * t), belly,
                              rot=(rad(20), 0, 0), verts=5))
    wx, wy, wz = pts["withers"]
    for sx in (-1, 1):
        # Spannweite unter 1: breiter stiess der Knochendrache an die
        # Grundflaechen-Grenze und wurde kleiner als der Schwarzritter.
        parts += fg.membrane_wing((sx * 0.08, wy + 0.05, wz), sx, 0.85, wing,
                                  body, lift=0.5, back=0.40,
                                  skin_on=not bone_only)
    return parts


def elf_goldwyrm(u):
    return _dragon(u, "#c9a24a", "#e8d8a0", "#b0803a")


def nec_bonedragon(u):
    return _dragon(u, "#ddd5bf", "#c8bea4", "#ddd5bf", bone_only=True)


# ================================================================ Totenreich

BONE = SKIN["bone"]


def nec_skeleton(u):
    P = Pose(H=1.8, bulk=0.42, twist=18, step=0.10)
    m = _mats(legs=BONE, torso=BONE, arms=BONE, skin=BONE)
    parts, pts = biped(u["id"], P, m)
    # Brustkorb: vier Rippenringe um die Wirbelsaeule.
    cx, cy, cz = pts["chest"]
    for k in range(4):
        z = cz - 0.03 * P.H - k * 0.035 * P.H
        r = (0.07 - 0.008 * k) * P.H
        for sx in (-1, 1):
            parts.append(tube("rib", [(0, cy + 0.03 * P.H, z),
                                      (sx * r, cy, z - 0.01 * P.H),
                                      (sx * r * 0.5, cy - r * 0.9, z - 0.02 * P.H)],
                              [0.008 * P.H, 0.007 * P.H, 0.005 * P.H], BONE))
    parts.append(tube("loin", [(0.08 * P.H, -0.02 * P.H, P.leg + 0.05 * P.H),
                               (0, -0.06 * P.H, P.leg - 0.05 * P.H),
                               (-0.08 * P.H, -0.02 * P.H, P.leg + 0.05 * P.H)],
                      [0.03 * P.H, 0.05 * P.H, 0.03 * P.H], "#4a3a4e"))
    parts += helm("skull", P, pts, m)
    parts += weapon("sword", P, pts, m)
    parts += fg.shield(P, pts, fg.cloth(u), "#8a8478")
    return parts


def nec_zombie(u):
    P = Pose(H=1.8, hunch=0.06, twist=10, step=0.07, lean=0.04)
    m = _mats(legs="#5a4e3e", torso="#6b6450", arms=SKIN["rot"],
              skin=SKIN["rot"], boots="#3a3228")
    parts, pts = biped(u["id"], P, m, arms="reach")
    parts += helm("rotten", P, pts, m)
    # Zerrissener Hemdsaum.
    for k, sx in enumerate((-1, 0, 1)):
        parts.append(cone(0.035 * P.H, 0.0, 0.10 * P.H,
                          (sx * 0.06 * P.H, -0.05 * P.H, P.leg - 0.02 * P.H),
                          "#6b6450", rot=(rad(180), 0, 0), verts=5))
    return parts


def nec_wight(u):
    H = 1.8
    ghost = "#a6d8b6"
    # Schleier als Drehkoerper mit Falten, nach unten in eine Spitze
    # auslaufend und nach hinten wehend.
    prof = [(0.0, 0.004 * H), (0.12 * H, 0.05 * H), (0.30 * H, 0.10 * H),
            (0.50 * H, 0.10 * H), (0.64 * H, 0.085 * H), (0.72 * H, 0.06 * H),
            (0.76 * H, 0.0)]
    parts = [fg.lathe(u["id"] + "_veil", prof, ghost, folds=7, depth=0.18,
                      lean=(0.0, 0.14 * H))]
    P = Pose(H=H)
    z_sh = 0.68 * H
    for sx in (-1, 1):
        sh = (sx * 0.10 * H, 0, z_sh)
        el = (sx * 0.20 * H, -0.12 * H, z_sh - 0.04 * H)
        ha = (sx * 0.20 * H, -0.30 * H, z_sh - 0.02 * H)
        parts.append(tube("garm", [sh, el, ha], [0.045 * H, 0.04 * H, 0.025 * H],
                          ghost))
        for k in (-1, 0, 1):
            parts.append(tube("claw", [ha, (ha[0] + k * 0.03 * H, ha[1] - 0.07 * H,
                                            ha[2] - 0.02 * H)],
                              [0.01 * H, 0.003 * H], "#d8f0dc"))
    head = (0, -0.01 * H, z_sh + 0.06 * H + P.head_r)
    parts.append(ball(P.head_r, head, "#c8e8d0"))
    pts = dict(head=head, top=z_sh)
    parts += helm("hood", P, pts, dict(torso=ghost, hood=ghost, skin=ghost))
    for sx in (-1, 1):
        parts.append(ball(0.016 * H, (sx * 0.03 * H, head[1] - P.head_r * 0.9,
                                      head[2]), "#e8fff0", subdiv=1))
    return parts


def nec_vampire(u):
    P = Pose(H=1.9, leg=0.54, twist=-14, step=0.06, bulk=0.9)
    m = _mats(legs="#1e1a22", torso="#2a2430", arms="#1e1a22",
              hands=SKIN["pale"], boots="#141216", skin=SKIN["pale"])
    parts, pts = biped(u["id"], P, m, arms="wide")
    # Umhang: aussen schwarz, innen in Fraktionsfarbe (beim Vorbild rot).
    parts += cape(u["id"], P, pts, "#141216")
    inner = cape(u["id"] + "_in", P, pts, "#7a1f2a")
    fg.move(inner, (0, -0.012 * P.H, 0.0))
    parts += inner
    # Hoher Kragen.
    cx, cy, cz = pts["chest"]
    for sx in (-1, 1):
        parts.append(fg.slab((0.05 * P.H, 0.006 * P.H, 0.06 * P.H),
                             (sx * 0.06 * P.H, cy + 0.05 * P.H, pts["top"] + 0.05 * P.H),
                             "#7a1f2a", rot=(rad(-15), 0, rad(sx * 25))))
    parts += helm("fanged", P, pts, m)
    return parts


def nec_lich(u):
    H = 1.85
    robe_col = "#3a3340"
    body, z_sh = fg.robe(u["id"], H, robe_col, flare=1.1)
    parts = [body]
    P = Pose(H=H)
    parts.append(cone(0.11 * H, 0.11 * H, 0.03 * H, (0, 0, 0.52 * H),
                      fg.cloth(u, accent=True), verts=16))
    haR = (-0.12 * H, -0.12 * H, z_sh - 0.12 * H)
    haL = (0.14 * H, -0.12 * H, z_sh - 0.10 * H)
    for sx, ha in ((1, haL), (-1, haR)):
        sh = (sx * 0.10 * H, 0, z_sh)
        el = (sx * 0.18 * H, 0.0, z_sh - 0.14 * H)
        parts.append(tube("sleeve", [sh, el, ha], [0.045 * H, 0.05 * H, 0.06 * H],
                          robe_col))
        parts.append(ball(0.025 * H, ha, BONE, subdiv=1))
    # Schulterstuecke in Fraktionsfarbe.
    for sx in (-1, 1):
        parts.append(ball(0.06 * H, (sx * 0.10 * H, 0, z_sh + 0.01 * H),
                          fg.cloth(u), squash=(1.1, 1, 0.6)))
    head = (0, -0.01 * H, z_sh + 0.05 * H + P.head_r)
    parts.append(ball(P.head_r, head, BONE, squash=(0.92, 1, 1.05)))
    pts = dict(head=head, handR=haR, handL=haL, top=z_sh, chest=(0, 0, z_sh))
    parts += helm("skull_glow", P, pts, dict(skin=BONE))
    # Krone.
    for k in range(5):
        a = rad(-90 + (k - 2) * 30)
        parts.append(cone(0.012 * H, 0.0, 0.05 * H,
                          (math.cos(a) * P.head_r * 0.85, head[1] + math.sin(a) * P.head_r * 0.85,
                           head[2] + P.head_r * 0.85), GOLD, verts=4))
    parts += weapon("staff_orb", P, pts, {})
    return parts


def nec_blackknight(u):
    P = Pose(H=2.0, twist=-26, step=0.12, bulk=1.2, shoulder=0.145)
    dark = "#34353c"
    m = _mats(legs=dark, torso=dark, arms=dark, hands="#22232a",
              boots="#22232a")
    parts, pts = biped(u["id"], P, m, arms="raise")
    parts += tabard(u["id"], P, pts, fg.cloth(u), "#8a8478")
    parts += cape(u["id"], P, pts, "#4a1c24")
    # Schulterpanzer.
    for k in ("shL", "shR"):
        parts.append(ball(0.07 * P.H, pts[k], "#2a2b31", squash=(1.1, 1, 0.7)))
    parts += helm("helm_horned", P, pts, m)
    parts += weapon("greatsword", P, pts, m)
    return parts


# ================================================================ Orks

def ork_goblin(u):
    P = Pose(H=1.25, head=1 / 4.4, leg=0.42, hunch=0.05, bulk=0.85,
             twist=20, step=0.10)
    m = _mats(legs=LEATHER, torso="#6b4a2e", arms=SKIN["goblin"],
              skin=SKIN["goblin"], boots=LEATHER_DARK)
    parts, pts = biped(u["id"], P, m)
    parts += tabard(u["id"], P, pts, fg.cloth(u), None)
    parts += helm("eared", P, pts, m)
    # Nase und Augen - das Gesicht macht den Goblin.
    hx, hy, hz = pts["head"]
    r = P.head_r
    parts.append(cone(r * 0.2, 0.0, r * 0.6, (hx, hy - r * 1.1, hz - r * 0.05),
                      SKIN["goblin"], rot=(rad(-100), 0, 0), verts=6))
    for sx in (-1, 1):
        parts.append(ball(r * 0.16, (hx + sx * r * 0.35, hy - r * 0.85, hz + r * 0.2),
                          "#e8d050", subdiv=1))
    parts += weapon("dagger", P, pts, m)
    return parts


def ork_wolfrider(u):
    Q = Quad("wolf")
    fur = "#6e6a64"
    parts, pts = fg.quadruped(u["id"], Q, dict(body=fur, legs="#4a4642"),
                              gait=0.16)
    G = Q.girth
    nx, ny, nz = pts["neck"]
    skull = (0, ny - 0.02, nz + 0.04)
    snout = (0, ny - 0.26, nz - 0.03)
    parts.append(tube("whead", [skull, snout], [G * 0.62, G * 0.25], fur))
    parts.append(ball(G * 0.14, (0, snout[1] - 0.03, snout[2]), "#1a1612", subdiv=1))
    for sx in (-1, 1):
        parts.append(cone(G * 0.18, 0.0, G * 0.55,
                          (sx * G * 0.32, skull[1] + 0.03, skull[2] + G * 0.55),
                          fur, verts=5))
        parts.append(ball(G * 0.09, (sx * G * 0.3, skull[1] - 0.09, skull[2] + 0.04),
                          "#e8c040", subdiv=1))
    # Buschiger Schwanz.
    tx, ty, tz = pts["tail"]
    parts.append(tube("wtail", [(0, ty, tz), (0, ty + 0.14, tz + 0.02),
                                (0, ty + 0.30, tz - 0.06)],
                      [G * 0.3, G * 0.42, G * 0.12], fur))
    # Nackenfell.
    parts.append(lump((0, pts["chest"][1], pts["zb"] + G * 0.9), G * 0.7, "#5a5650",
                      squash=0.7, seed=7))
    P = Pose(H=0.85, head=1 / 4.4, leg=0.42, bulk=0.85, twist=0)
    P.sit_w = 0.17
    rm = _mats(legs=LEATHER, torso="#6b4a2e", arms=SKIN["goblin"],
               skin=SKIN["goblin"])
    parts += _rider(u, P, rm, pts, Q, "eared", "spear",
                    tabard_col=fg.cloth(u), trim=None)
    return parts


def ork_orc(u):
    P = Pose(H=1.9, twist=-24, step=0.11, bulk=1.25, shoulder=0.145,
             head=1 / 7.8)
    m = _mats(legs="#5a4630", torso=SKIN["orc"], arms=SKIN["orc"],
              skin=SKIN["orc"], hands=SKIN["orc"], boots=LEATHER_DARK)
    parts, pts = biped(u["id"], P, m)
    parts += tabard(u["id"], P, pts, fg.cloth(u), None)
    # Lederriemen quer ueber die Brust und Schulterpanzer.
    cx, cy, cz = pts["chest"]
    parts.append(tube("strap", [pts["shL"], (0, cy - 0.075 * P.H, cz - 0.04 * P.H),
                                (-0.08 * P.H, cy - 0.04 * P.H, P.leg + 0.12 * P.H)],
                      [0.014 * P.H] * 3, LEATHER_DARK))
    parts.append(ball(0.045 * P.H, pts["shL"], LEATHER_DARK, squash=(1.2, 1.1, 0.55)))
    parts += helm("tusked", P, pts, m)
    parts += weapon("crossbow", P, pts, m)
    return parts


def _brute(u, skin_col, head_kind, wpn, arms, H):
    P = Pose(H=H, head=1 / 8.0, leg=0.44, shoulder=0.19, hip=0.085,
             bulk=1.35, hunch=0.05, twist=14, step=0.10)
    m = _mats(legs="#5a4630", torso=skin_col, arms=skin_col, skin=skin_col,
              hands=skin_col, boots=LEATHER_DARK)
    parts, pts = biped(u["id"], P, m, arms=arms)
    # Bauch.
    parts.append(ball(0.10 * P.H, (0, -0.05 * P.H, P.leg + 0.13 * P.H), skin_col,
                      squash=(1.0, 0.9, 0.95)))
    parts += tabard(u["id"], P, pts, fg.cloth(u), None, strip=False)
    parts += helm(head_kind, P, pts, m)
    parts += weapon(wpn, P, pts, m)
    return parts


def ork_ogre(u):
    return _brute(u, SKIN["ogre"], "small", "club", "ready", 2.1)


def ork_cyclops(u):
    return _brute(u, SKIN["cyclops"], "one_eye", "boulder", "raise", 2.3)


def ork_roc(u):
    H = 1.6
    brown, light = "#6b4a2e", "#d8c8a0"
    # Rumpf liegend, Hals nach vorn-oben.
    v = [(0, 0.36 * H, 0.52 * H), (0, 0.15 * H, 0.50 * H), (0, -0.05 * H, 0.54 * H),
         (0, -0.16 * H, 0.66 * H), (0, -0.20 * H, 0.78 * H)]
    parts = [fg.skin(u["id"] + "_body", v, fg.chain(5),
                     [0.06 * H, 0.15 * H, 0.14 * H, 0.08 * H, 0.06 * H], brown)]
    head = (0, -0.23 * H, 0.84 * H)
    parts.append(ball(0.075 * H, head, light, squash=(0.9, 1.1, 0.95)))
    parts.append(tube("beak", [(0, head[1] - 0.05 * H, head[2]),
                               (0, head[1] - 0.13 * H, head[2] - 0.01 * H),
                               (0, head[1] - 0.16 * H, head[2] - 0.05 * H)],
                      [0.03 * H, 0.018 * H, 0.004 * H], "#d9a83a"))
    for sx in (-1, 1):
        parts.append(ball(0.014 * H, (sx * 0.045 * H, head[1] - 0.04 * H,
                                      head[2] + 0.02 * H), "#1a1612", subdiv=1))
        hip = (sx * 0.08 * H, 0.12 * H, 0.42 * H)
        knee = (sx * 0.09 * H, 0.06 * H, 0.24 * H)
        foot = (sx * 0.09 * H, 0.0, 0.02 * H)
        parts.append(tube("rleg", [hip, knee, foot], [0.04 * H, 0.025 * H, 0.02 * H],
                          "#d9a83a"))
        for k in (-1, 0, 1):
            parts.append(tube("talon", [foot, (foot[0] + k * 0.04 * H, foot[1] - 0.07 * H,
                                               0.01 * H)],
                              [0.012 * H, 0.006 * H], "#d9a83a"))
        parts += fg.feather_wing((sx * 0.08 * H, 0.0, 0.60 * H), sx, 0.78 * H,
                                 brown, "#8a6238", lift=0.75, back=0.4)
    # Schwanzfedern als Faecher.
    for k in (-1, 0, 1):
        parts.append(tube("tailf", [(0, 0.34 * H, 0.52 * H),
                                    (k * 0.08 * H, 0.52 * H, 0.46 * H)],
                          [0.03 * H, 0.04 * H], "#5a3c24"))
    return parts


def ork_behemoth(u):
    P = Pose(H=2.4, head=1 / 8.0, leg=0.40, shoulder=0.20, hip=0.09,
             bulk=1.45, hunch=0.12, twist=10, step=0.10)
    fur = "#6e6660"
    m = _mats(legs=fur, torso=fur, arms=fur, skin="#8a8078", hands="#4a4440",
              boots="#4a4440")
    parts, pts = biped(u["id"], P, m, arms="low")
    # Zottelfell auf Ruecken und Schultern.
    cx, cy, cz = pts["chest"]
    for k in range(4):
        parts.append(lump((((k % 2) * 2 - 1) * 0.06 * P.H, cy + 0.06 * P.H,
                           cz - k * 0.06 * P.H), 0.09 * P.H, "#5e5852",
                          squash=0.8, seed=40 + k))
    hx, hy, hz = pts["head"]
    r = P.head_r
    for sx in (-1, 1):
        parts.append(tube("bhorn", [(hx + sx * r * 0.6, hy, hz + r * 0.5),
                                    (hx + sx * r * 1.5, hy + r * 0.3, hz + r * 1.0),
                                    (hx + sx * r * 1.6, hy - r * 0.4, hz + r * 1.6)],
                          [r * 0.3, r * 0.2, r * 0.05], "#d9d0b6"))
        parts.append(ball(r * 0.15, (hx + sx * r * 0.35, hy - r * 0.85, hz + r * 0.15),
                          "#e85a2a", subdiv=1))
    # Krallen an den Haenden.
    for k in ("handL", "handR"):
        x, y, z = pts[k]
        for d in (-1, 0, 1):
            parts.append(tube("bclaw", [(x, y, z), (x + d * 0.03 * P.H, y - 0.07 * P.H,
                                                    z - 0.03 * P.H)],
                              [0.015 * P.H, 0.004 * P.H], "#e8e0c8"))
    return parts


# ================================================================ Greif

def men_griffin(u):
    Q = Quad("lion")
    tawny, brown, white = "#b08850", "#6b4a2e", "#ece6d8"
    parts, pts = fg.quadruped(u["id"], Q, dict(body=tawny, legs="#d9a83a"),
                              gait=0.12)
    G = Q.girth
    # Federbrust und Adlerkopf.
    parts.append(lump((0, pts["chest"][1] - G * 0.3, pts["zb"] + G * 0.4), G * 1.05,
                      brown, strength=0.25, squash=1.1, seed=5))
    nx, ny, nz = pts["neck"]
    head = (0, ny - G * 0.2, nz + G * 0.55)
    parts.append(ball(G * 0.62, head, white, squash=(0.9, 1.15, 0.95)))
    parts.append(tube("gbeak", [(0, head[1] - G * 0.45, head[2]),
                                (0, head[1] - G * 0.95, head[2] - G * 0.1),
                                (0, head[1] - G * 1.1, head[2] - G * 0.4)],
                      [G * 0.24, G * 0.14, G * 0.03], "#d9a83a"))
    for sx in (-1, 1):
        parts.append(ball(G * 0.09, (sx * G * 0.32, head[1] - G * 0.3, head[2] + G * 0.15),
                          "#1a1612", subdiv=1))
    parts += _wings_on_quad(Q, pts, brown, "#8a6238", 0.85)
    tx, ty, tz = pts["tail"]
    parts.append(tube("gtail", [(0, ty, tz), (0, ty + 0.18, tz - 0.05),
                                (0, ty + 0.32, tz - 0.20)],
                      [G * 0.15, G * 0.1, G * 0.08], tawny))
    parts.append(lump((0, ty + 0.34, tz - 0.24), G * 0.25, brown, seed=9))
    return parts


BUILD = {f.__name__: f for f in (
    men_spearman, men_archer, men_griffin, men_crusader, men_monk,
    men_cavalier, men_angel,
    elf_dwarf, elf_archer, elf_pegasus, elf_treant, elf_unicorn,
    elf_treefather, elf_goldwyrm,
    nec_skeleton, nec_zombie, nec_wight, nec_vampire, nec_lich,
    nec_blackknight, nec_bonedragon,
    ork_goblin, ork_wolfrider, ork_orc, ork_ogre, ork_roc, ork_cyclops,
    ork_behemoth,
)}
