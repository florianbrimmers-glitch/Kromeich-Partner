"""Architektur-Baukasten fuer die Stadtgebaeude im Heroes-4-Stil (It. 76).

Wird von city_buildings3d.py benutzt (Blender-Python, kein eigenes main).

WARUM NEU: die Gebaeude aus It. 56/70 waren je EIN Quader mit einem Dach
darauf - im Panorama aus It. 75 der groesste Abstand zum Vorbild. Ein
Heroes-4-Gebaeude liest sich an Dingen, die ein Quader nicht hat:

  * SOCKEL und ECKQUADER: das Haus steht auf etwas, die Kanten sind gefasst.
  * FENSTER mit Rahmen und Sims, manche erleuchtet; TUEREN mit Rundbogen.
  * FACHWERK oder Steinlagen statt einer glatten Wand.
  * DAECHER mit Ziegelreihen, Ueberstand, First - und Tuerme mit Kegeldach.
  * ZINNEN, BANNER, SCHORNSTEINE: die Silhouette oben ist zerklueftet.

KOORDINATEN wie ueberall in den Generatoren: z oben, -y ist VORN (zur
Kamera), Masse als VOLLE Breite/Tiefe/Hoehe (anders als bk.box, das
Halbmasse nimmt - die Bausteine hier rechnen es um). `x, y` ist die Mitte
der Grundflaeche, `base` die Hoehe des Fusses.
"""

import math

import bpy

import blender_kit as bk

rad = math.radians


def _shade(ob, smooth=True):
    for p in ob.data.polygons:
        p.use_smooth = smooth
    return ob


def block(w, d, h, col, x=0.0, y=0.0, base=0.0, bevel=0.012, taper=1.0, rot_z=0.0):
    """Quader mit voller Breite/Tiefe/Hoehe, Fuss bei base."""
    b = min(bevel, w * 0.2, d * 0.2, h * 0.2)
    return bk.box((w * 0.5, d * 0.5, h * 0.5), (x, y, base + h * 0.5), col, b,
                  rot=(0, 0, rot_z) if rot_z else None, taper=taper, segments=1)


def cyl(r, h, col, x=0.0, y=0.0, base=0.0, r_top=None, verts=16, smooth=True):
    """Zylinder (oder Kegelstumpf), Fuss bei base."""
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r,
                                    radius2=r if r_top is None else r_top,
                                    depth=h, location=(x, y, base + h * 0.5))
    ob = bpy.context.active_object
    bk._bake(ob)
    ob.data.materials.append(bk.material("k" + col, col))
    return _shade(ob, smooth)


def cone_roof(r, rise, col, x=0.0, y=0.0, base=0.0, verts=16, flare=1.0):
    """Kegeldach. flare > 1 laesst es an der Traufe ueberstehen."""
    return cyl(r * flare, rise, col, x, y, base, r_top=0.0, verts=verts)


def dome(r, col, x=0.0, y=0.0, base=0.0, squash=0.75):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=18, ring_count=9, radius=r,
                                         location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.scale = (1.0, 1.0, squash)
    bpy.ops.object.transform_apply(scale=True)
    # Untere Haelfte wegschneiden: eine Kuppel ist keine Kugel.
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    kill = [v for v in bm.verts if v.co.z < -0.001]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    ob.location = (x, y, base)
    bpy.ops.object.transform_apply(location=True)
    ob.data.materials.append(bk.material("k" + col, col))
    return _shade(ob)


# ---------------------------------------------------------------- Waende

def plinth(w, d, h, col, x=0.0, y=0.0, base=0.0):
    """Sockel: etwas breiter als die Wand, dunkler."""
    return block(w + 0.04, d + 0.04, h, col, x, y, base, bevel=0.01)


def quoins(w, d, h, col, x=0.0, y=0.0, base=0.0, n=4):
    """Eckquader: abwechselnd lange und kurze Steine an den vier Ecken."""
    out = []
    s = h / n
    for sx in (-1, 1):
        for sy in (-1, 1):
            for k in range(n):
                long_ = (k % 2 == 0)
                bw = 0.07 if long_ else 0.045
                out.append(block(bw, bw if not long_ else 0.045, s * 0.86, col,
                                 x + sx * (w * 0.5 - bw * 0.35),
                                 y + sy * (d * 0.5 - 0.02),
                                 base + k * s + s * 0.07, bevel=0.006))
    return out


def courses(w, d, h, col, x=0.0, y=0.0, base=0.0, n=3, depth=0.008):
    """Gesimse: schmale Baender rund um die Wand - Steinlagen fuers Auge."""
    out = []
    for k in range(1, n + 1):
        z = base + h * k / (n + 1)
        out.append(block(w + depth * 2, d + depth * 2, 0.018, col, x, y, z - 0.009,
                         bevel=0.004))
    return out


def timber(w, d, h, col, x=0.0, y=0.0, base=0.0, faces=("front", "side")):
    """Fachwerk auf Vorder- und Seitenwand: Pfosten, Riegel, Streben."""
    out = []
    t = 0.022
    e = 0.006
    if "front" in faces:
        yf = y - d * 0.5 - e
        n = max(2, int(w / 0.28))
        for i in range(n + 1):
            px = x - w * 0.5 + w * i / n
            out.append(block(t, t, h, col, px, yf, base, bevel=0.0))
        for z in (base + 0.01, base + h * 0.5, base + h - t):
            out.append(block(w, t, t, col, x, yf, z, bevel=0.0))
        # Streben im aeusseren Feld links und rechts.
        for sx in (-1, 1):
            cx = x + sx * (w * 0.5 - w / n * 0.5)
            ln = math.hypot(w / n, h * 0.5)
            ang = math.atan2(h * 0.5, w / n) * sx
            ob = bk.box((ln * 0.5, t * 0.5, t * 0.5), (cx, yf, base + h * 0.25), col, 0.0,
                        rot=(0, -ang, 0))
            out.append(ob)
    if "side" in faces:
        for sx in (-1, 1):
            xf = x + sx * (w * 0.5 + e)
            n = max(2, int(d / 0.28))
            for i in range(n + 1):
                py = y - d * 0.5 + d * i / n
                out.append(block(t, t, h, col, xf, py, base, bevel=0.0))
            out.append(block(t, d, t, col, xf, y, base + h * 0.5, bevel=0.0))
            out.append(block(t, d, t, col, xf, y, base + h - t, bevel=0.0))
    return out


def window(x, yf, z, ww, wh, frame, glass, arched=False, sill=True, face="front"):
    """Fenster auf einer Wand (yf = Lage der Wandflaeche). Rahmen, Scheibe,
    Kreuz, Sims. face="side": x ist dann die Wandflaeche, yf die Lage."""
    out = []
    if face == "front":
        out.append(block(ww + 0.03, 0.02, wh + 0.03, frame, x, yf - 0.006, z - 0.015, bevel=0.003))
        out.append(block(ww, 0.02, wh, glass, x, yf - 0.012, z, bevel=0.0))
        out.append(block(0.008, 0.02, wh, frame, x, yf - 0.016, z, bevel=0.0))
        out.append(block(ww, 0.02, 0.008, frame, x, yf - 0.016, z + wh * 0.55, bevel=0.0))
        if arched:
            bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=ww * 0.5, depth=0.02,
                                                location=(x, yf - 0.012, z + wh),
                                                rotation=(rad(90), 0, 0))
            ob = bpy.context.active_object
            bk._bake(ob)
            ob.data.materials.append(bk.material("k" + glass, glass))
            out.append(ob)
        if sill:
            out.append(block(ww + 0.05, 0.035, 0.014, frame, x, yf - 0.012, z - 0.022, bevel=0.003))
    else:
        out.append(block(0.02, ww + 0.03, wh + 0.03, frame, x, yf, z - 0.015, bevel=0.003))
        out.append(block(0.02, ww, wh, glass, x, yf, z, bevel=0.0))
    return out


def window_row(w, yf, z, n, ww, wh, frame, glass, x=0.0, arched=False, lit=()):
    out = []
    for i in range(n):
        px = x - w * 0.5 + w * (i + 0.5) / n
        g = glass[1] if i in lit else glass[0]
        out += window(px, yf, z, ww, wh, frame, g, arched=arched)
    return out


def side_windows(d, xf, z, n, ww, wh, frame, glass, y=0.0):
    out = []
    for sx in (-1, 1):
        for i in range(n):
            py = y - d * 0.5 + d * (i + 0.5) / n
            out += window(sx * xf, py, z, ww, wh, frame, glass, face="side")
    return out


def door(x, yf, base, dw, dh, frame, wood, arched=True, steps=None):
    """Tuer mit Rundbogen, Rahmen und Stufe."""
    out = [block(dw + 0.05, 0.03, dh + 0.03, frame, x, yf - 0.004, base, bevel=0.004),
           block(dw, 0.03, dh, wood, x, yf - 0.012, base, bevel=0.0)]
    if arched:
        for r, col, off in ((dw * 0.5 + 0.025, frame, 0.004), (dw * 0.5, wood, 0.012)):
            bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=r, depth=0.03,
                                                location=(x, yf - off, base + dh),
                                                rotation=(rad(90), 0, 0))
            ob = bpy.context.active_object
            bk._bake(ob)
            ob.data.materials.append(bk.material("k" + col, col))
            out.append(ob)
    if steps:
        out.append(block(dw + 0.12, 0.10, 0.03, steps, x, yf - 0.05, base - 0.03, bevel=0.005))
    return out


# ---------------------------------------------------------------- Daecher

def gable_roof(w, d, top, rise, col, ridge, x=0.0, y=0.0, along="x",
               over=0.07, rows=4, row_col=None):
    """Satteldach mit Ueberstand, Firstbalken und ZIEGELREIHEN.

    Die Reihen sind schmale Leisten quer zur Dachflaeche - sie machen aus
    einer glatten Platte ein gedecktes Dach, und sie fangen das Licht.
    along="x": First quer (Dachflaeche zur Kamera), "y": Giebel zur Kamera.
    """
    sx = w + 2 * over
    sy = d + 2 * over
    out = [bk.prism(sx, sy, rise, (x, y, top), col, along=along)]
    rc = row_col or col
    t = 0.012
    if along == "x":
        half = sy * 0.5
        ang = math.atan2(rise, half)
        out.append(bk.box((sx * 0.5 + 0.01, 0.03, 0.03), (x, y, top + rise), ridge, 0.005))
        for sgn in (-1, 1):
            for k in range(1, rows + 1):
                f = k / (rows + 1)
                py = y + sgn * half * (1 - f)
                pz = top + rise * f
                out.append(bk.box((sx * 0.5, t, t * 0.6),
                                  (x, py + sgn * 0.004, pz + 0.006), rc, 0.0,
                                  rot=(sgn * ang, 0, 0)))
    else:
        half = sx * 0.5
        ang = math.atan2(rise, half)
        out.append(bk.box((0.03, sy * 0.5 + 0.01, 0.03), (x, y, top + rise), ridge, 0.005))
        for sgn in (-1, 1):
            for k in range(1, rows + 1):
                f = k / (rows + 1)
                px = x + sgn * half * (1 - f)
                pz = top + rise * f
                out.append(bk.box((t, sy * 0.5, t * 0.6),
                                  (px + sgn * 0.004, y, pz + 0.006), rc, 0.0,
                                  rot=(0, -sgn * ang, 0)))
        # Giebeldreieck vorn in Wandfarbe ist Sache des Aufrufers.
    return out


def hip_roof(w, d, top, rise, col, x=0.0, y=0.0, over=0.07):
    """Walmdach als vierseitige Pyramide ueber einem Rechteck."""
    ob = bk.cone(1.0, 1.0, (0, 0, 0), col, verts=4, rot=(0, 0, rad(45)))
    # Einheitspyramide (Radius 1 = Ecke bei sqrt(0.5)) auf w x d strecken.
    ob.scale = ((w + 2 * over) / math.sqrt(2), (d + 2 * over) / math.sqrt(2), rise)
    bpy.ops.object.transform_apply(scale=True)
    ob.location = (x, y, top + rise * 0.5)
    bpy.ops.object.transform_apply(location=True)
    return [ob]


def crenels(w, d, top, col, x=0.0, y=0.0, mw=0.07, mh=0.08, wall=0.06,
            kind="std", sides=("front", "back", "left", "right")):
    """Zinnen auf einer Mauerkrone: Brustwehr plus Zinnenzaehne.

    kind: std (rechteckig), spike (Totenreich, spitz), stake (Orks,
    angespitzte Pfaehle).
    """
    out = []
    step = mw * 2.0

    def tooth(px, py):
        if kind == "spike":
            return bk.cone(mw * 0.55, mh * 1.8, (px, py, top + mh * 0.9), col,
                           verts=4, rot=(0, 0, rad(45)))
        if kind == "stake":
            return cyl(mw * 0.35, mh * 1.6, col, px, py, top, r_top=0.0, verts=6)
        return block(mw, wall, mh, col, px, py, top, bevel=0.004)

    for s in sides:
        if s in ("front", "back"):
            py = y + (-1 if s == "front" else 1) * (d * 0.5 - wall * 0.5)
            n = max(2, int(w / step))
            for i in range(n):
                out.append(tooth(x - w * 0.5 + (i + 0.5) * w / n, py))
        else:
            px = x + (-1 if s == "left" else 1) * (w * 0.5 - wall * 0.5)
            n = max(2, int(d / step))
            for i in range(n):
                out.append(tooth(px, y - d * 0.5 + (i + 0.5) * d / n))
    return out


def round_tower(r, h, wall, dark, x=0.0, y=0.0, base=0.0, roof=None, roof_col=None,
                rise=None, crenel=None, slits=None, verts=16):
    """Rundturm: Sockel, Schaft, Gesims, Zinnen ODER Kegeldach, Schiessscharten."""
    out = [cyl(r * 1.08, h * 0.12, dark, x, y, base, verts=verts),
           cyl(r, h, wall, x, y, base, r_top=r * 0.94, verts=verts)]
    top = base + h
    out.append(cyl(r * 1.10, 0.05, dark, x, y, top - 0.02, verts=verts))
    if crenel:
        n = max(6, int(2 * math.pi * r / 0.13))
        for i in range(n):
            if i % 2:
                continue
            a = 2 * math.pi * i / n
            px, py = x + math.cos(a) * r * 1.02, y + math.sin(a) * r * 1.02
            if crenel == "spike":
                out.append(bk.cone(0.04, 0.14, (px, py, top + 0.10), crenel_col(dark),
                                   verts=4))
            elif crenel == "stake":
                out.append(cyl(0.025, 0.14, "#5a4026", px, py, top + 0.02, r_top=0.0, verts=6))
            else:
                out.append(block(0.07, 0.07, 0.08, wall, px, py, top + 0.02, bevel=0.004))
    if roof:
        rs = rise or r * 2.0
        if roof == "dome":
            out.append(dome(r * 1.05, roof_col, x, y, top + 0.03))
        elif roof == "tent":
            out.append(cone_roof(r * 1.15, rs * 0.9, roof_col, x, y, top + 0.03, verts=7))
        else:
            v = 8 if roof == "spire" else verts
            out.append(cone_roof(r * (0.95 if roof == "spire" else 1.18),
                                 rs * (1.5 if roof == "spire" else 1.0),
                                 roof_col, x, y, top + 0.03, verts=v))
    if slits:
        for a in (-90, -55, -125):
            px = x + math.cos(rad(a)) * r * 1.0
            py = y + math.sin(rad(a)) * r * 1.0
            out.append(block(0.022, 0.03, 0.10, slits, px, py, base + h * 0.55, bevel=0.0,
                             rot_z=rad(a + 90)))
            out.append(block(0.022, 0.03, 0.10, slits, px, py, base + h * 0.28, bevel=0.0,
                             rot_z=rad(a + 90)))
    return out


def crenel_col(c):
    return c


def banner(x, y, base, pole_h, col, trim, w=0.14, h=0.24, wood="#5a4026"):
    """Fahnenstange mit Wimpel (zur Seite wehend)."""
    out = [cyl(0.012, pole_h, wood, x, y, base, verts=6),
           bk.cone(0.02, 0.04, (x, y, base + pole_h + 0.02), trim, verts=6)]
    vs = [(x, y, base + pole_h - 0.02), (x, y, base + pole_h - 0.02 - h),
          (x + w, y + 0.02, base + pole_h - 0.02 - h * 0.62),
          (x + w * 0.65, y + 0.01, base + pole_h - 0.02 - h * 0.25)]
    import figures as fg
    out.append(fg.sheet("flag", vs, [(0, 1, 2, 3)], col, 0.008))
    return out


def hanging_banner(x, yf, z_top, w, h, col, trim):
    """Banner an der Wand, mit gezacktem Saum."""
    out = [block(w + 0.02, 0.012, 0.02, trim, x, yf - 0.012, z_top, bevel=0.0),
           block(w, 0.01, h, col, x, yf - 0.014, z_top - h, bevel=0.0)]
    out.append(bk.cone(w * 0.5, h * 0.25, (x, yf - 0.014, z_top - h - h * 0.12), col,
                       verts=3, rot=(rad(90), rad(180), 0)))
    return out


def chimney(x, y, base, h, col, cap):
    return [block(0.09, 0.09, h, col, x, y, base, bevel=0.006),
            block(0.12, 0.12, 0.025, cap, x, y, base + h, bevel=0.004)]


def fence(x0, x1, y, h, col, n=6):
    out = []
    for i in range(n):
        px = x0 + (x1 - x0) * i / (n - 1)
        out.append(block(0.025, 0.025, h, col, px, y, 0.0, bevel=0.0))
    for z in (h * 0.45, h * 0.85):
        out.append(block(abs(x1 - x0), 0.018, 0.02, col, (x0 + x1) * 0.5, y, z, bevel=0.0))
    return out


def palisade(cx, cy, rx, ry, h, col, n=14, a0=0.0, a1=360.0):
    """Ring aus angespitzten Pfaehlen (Orks)."""
    out = []
    for i in range(n):
        a = rad(a0 + (a1 - a0) * i / max(1, n - (0 if a1 - a0 < 360 else 0)))
        px, py = cx + math.cos(a) * rx, cy + math.sin(a) * ry
        hh = h * (0.85 + 0.3 * ((i * 37) % 7) / 7.0)
        out.append(cyl(0.032, hh, col, px, py, 0.0, verts=6))
        out.append(cyl(0.032, 0.07, col, px, py, hh, r_top=0.0, verts=6))
    return out


def leaves(x, y, z, r, cols, n=4, seed=0):
    """Laubballen (Waldvolk: Baeume, die mit den Haeusern verwachsen)."""
    import figures as fg
    out = []
    for k in range(n):
        a = k * 2.3 + seed
        out.append(fg.lump((x + math.cos(a) * r * 0.5, y + math.sin(a) * r * 0.4,
                            z + (k % 2) * r * 0.25), r * (0.75 if k else 0.9),
                           cols[k % len(cols)], strength=0.4, squash=0.75, seed=seed + k))
    return out


def skull(x, y, z, s, col, eye="#1a1612"):
    import figures as fg
    out = [fg.ball(s, (x, y, z), col, squash=(0.9, 1.0, 1.0), subdiv=2),
           fg.ball(s * 0.6, (x, y - s * 0.35, z - s * 0.55), col, squash=(1, 0.8, 0.6), subdiv=1)]
    for sx in (-1, 1):
        out.append(fg.ball(s * 0.22, (x + sx * s * 0.35, y - s * 0.8, z + s * 0.05), eye,
                           subdiv=1))
    return out


def horns(x, y, z, s, col):
    import figures as fg
    out = []
    for sx in (-1, 1):
        out.append(fg.tube("horn", [(x + sx * s * 0.3, y, z), (x + sx * s * 1.0, y, z + s * 0.6),
                                    (x + sx * s * 1.1, y - s * 0.3, z + s * 1.3)],
                           [s * 0.16, s * 0.10, s * 0.02], col))
    return out
