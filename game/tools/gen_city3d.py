#!/usr/bin/env python3
"""3D-Modelle der Stadt (It. 56).

    /opt/blender/blender -b --factory-startup -noaudio \
        --python tools/gen_city3d.py -- game/assets/models/city.glb

DIE REZEPTE KOMMEN AUS gen_city_buildings.py, NICHT AUS DIESER DATEI.
Dort steht seit It. 20 eine Tabelle RECIPES (Breite, Hoehe, Dachform,
Aufsatz, Zierteile) und PALETTES je Fraktion mit ihrer SIGNATURE
(Palisade, Knochen, Ranken). Beides wird importiert. Baute ich die
Zuordnung neu, waere die Kapelle in 2D schmal mit steiler Spitze und in
3D irgendwann ein Kasten - dieselbe Doppelung, die It. 36/37 in vier
Vorschauwerkzeugen und It. 42 im Durchspiel-Test falsch gemacht hat.

MASSSTAB: die 2D-Rezepte rechnen in Pixeln einer 512er ViewBox. UNIT
rechnet das in Weltmeter um, sodass ein 300 px breites Gebaeude zwei
Einheiten misst - so gross wie zwei Kacheln der Weltkarte. Der Hof selbst
ist BAUPLATZ-Raster, kein Kachelgitter: die Plaetze kommen aus
data/city_layout.json, derselben Datei, aus der auch die 2D-Ansicht und
tools/gen_city_bg.py lesen.

SILHOUETTE IST DAS UNTERSCHEIDUNGSMERKMAL, nicht die Farbe - dieselbe
Regel wie bei den Sprites. Deshalb bildet dieser Generator vor allem die
FORM nach (Dach, Turm, Aufsatz, Hoehe) und nur die Zierteile, die die
Silhouette veraendern: Schornstein, Banner, Marktplane, Koppel und die
Fraktions-Signatur.
"""

import json
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_kit as bk  # noqa: E402
import gen_city_buildings as cb  # noqa: E402

box = bk.box
cone = bk.cone
ball = bk.ball
merge = bk.merge
rad = bk.rad

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT = os.path.join(HERE, "..", "data", "city_layout.json")

# 300 px breit = 1.7 Einheiten. Bezugsgroesse ist der Hof: er ist 6 breit
# (YARD_W in CityView3D.gd), ein mittleres Gebaeude nimmt damit gut ein
# Viertel der Hofbreite ein - dasselbe Verhaeltnis wie auf dem 2D-Schirm,
# wo ein Bauplatz hoechstens 300 von 1080 px misst.
UNIT = 1.7 / 300.0

FACTIONS = ["menschen", "waldvolk", "totenreich", "orks"]


def u(px):
    return float(px) * UNIT


# ---------------------------------------------------------------- Daecher

def roof(kind, pal, w, top, rise):
    """Dach auf einem Koerper der Breite w, Oberkante top."""
    d = w * 0.62
    if kind == "gable":
        # Satteldach: ein Prisma. In Blender gibt es das als Kegel mit
        # vier Ecken, um 45 Grad gedreht und flachgedrueckt - hier
        # einfacher als zwei geneigte Platten, die nie ganz schliessen.
        ob = cone(w * 0.72, rise, (0, 0, top + rise * 0.5), pal["roof"],
                  verts=4, rot=(0, 0, rad(45)))
        ob.scale = (1.0, 0.86, 1.0)
        bpy.ops.object.transform_apply(scale=True)
        return [ob]
    if kind == "pyramid":
        return [cone(w * 0.70, rise, (0, 0, top + rise * 0.5), pal["roof"],
                     verts=4, rot=(0, 0, rad(45)))]
    if kind == "spike":
        return [cone(w * 0.56, rise * 1.5, (0, 0, top + rise * 0.75),
                     pal["roof_dark"], verts=6)]
    if kind == "dome":
        ob = ball(w * 0.52, (0, 0, top), pal["roof_light"], subdiv=2)
        ob.scale = (1.0, 1.0, 0.62)
        bpy.ops.object.transform_apply(scale=True)
        return [ob]
    if kind == "flat":
        # Flachdach mit Zinnen: die Zinnen SIND die Silhouette, ohne sie
        # ist die Kaserne ein Schuhkarton.
        out = [box((w * 0.52, d * 0.52, rise * 0.30), (0, 0, top + rise * 0.30),
                   pal["roof_dark"], 0.01)]
        n = max(3, int(w / (0.12 / UNIT)))
        for i in range(n):
            x = -w * 0.48 + (i + 0.5) * (w * 0.96 / n)
            out.append(box((w * 0.030, d * 0.52, rise * 0.34),
                           (x, 0, top + rise * 0.90), pal["roof"], 0.005))
        return out
    return []


# ---------------------------------------------------------------- Zierteile

def ornaments(names, pal, w, h):
    d = w * 0.62
    out = []
    for n in names:
        if n == "chimney":
            out.append(box((w * 0.06, w * 0.06, h * 0.42),
                           (-w * 0.30, d * 0.18, h + h * 0.28),
                           pal["wall_dark"], 0.01))
        elif n == "forge_glow":
            out.append(box((w * 0.16, 0.01, h * 0.26),
                           (0, -d * 0.52, h * 0.26), pal["glow"], 0.0))
        elif n.startswith("banner"):
            xs = [-w * 0.44, w * 0.44] if n == "banner_pair" else [-w * 0.44]
            if n == "banner_top":
                xs = [0.0]
            for x in xs:
                out.append(box((0.012, 0.012, h * 0.34), (x, -d * 0.42,
                               h + h * 0.20), pal["wood"], 0.0))
                out.append(box((0.006, w * 0.10, h * 0.20),
                               (x, -d * 0.42 + w * 0.10, h + h * 0.30),
                               pal["accent"], 0.0))
        elif n == "stall":
            # Der Markt ist kein Haus: gestreifte Plane auf vier Pfosten.
            for sx in (-1, 1):
                for sy in (-1, 1):
                    out.append(box((w * 0.025, w * 0.025, h * 0.5),
                                   (sx * w * 0.42, sy * d * 0.40, h * 0.5),
                                   pal["wood"], 0.0))
            for i in range(5):
                x = -w * 0.46 + i * (w * 0.92 / 4.0)
                col = pal["accent"] if i % 2 == 0 else pal["wall_mid"]
                out.append(box((w * 0.10, d * 0.48, h * 0.06),
                               (x, 0, h * 1.06), col, 0.01,
                               rot=(rad(6), 0, 0)))
        elif n == "stable_fence":
            for i in range(5):
                x = -w * 0.46 + i * (w * 0.92 / 4.0)
                out.append(box((w * 0.02, w * 0.02, h * 0.30),
                               (x, -d * 0.95, h * 0.30), pal["wood"], 0.0))
            out.append(box((w * 0.48, 0.012, h * 0.045),
                           (0, -d * 0.95, h * 0.46), pal["wood"], 0.0))
        elif n.startswith("windows"):
            out.append(box((w * 0.26, 0.01, h * 0.16),
                           (0, -d * 0.52, h * 0.62), pal["glow"], 0.0))
        elif n in ("door", "door_wide", "door_small", "gate"):
            fw = {"door": 0.13, "door_wide": 0.18, "door_small": 0.09,
                  "gate": 0.24}[n]
            out.append(box((w * fw, 0.012, h * 0.34),
                           (0, -d * 0.52, h * 0.34), pal["door"], 0.0))
    return out


def signature(kind, pal, w, h):
    """Fraktions-Zierteil. Es laeuft um das Gebaeude und ist damit das
    Erste, was man aus der Entfernung sieht - genau wie in 2D."""
    d = w * 0.62
    out = []
    if kind == "palisade":
        n = max(7, int(w / u(34)))
        for i in range(n):
            a = math.tau * i / n
            out.append(box((w * 0.022, w * 0.022, h * 0.24),
                           (math.cos(a) * w * 0.66, math.sin(a) * d * 0.90,
                            h * 0.24), pal["wood"], 0.0))
    elif kind == "bones":
        for sx in (-1, 1):
            out.append(box((w * 0.02, w * 0.02, h * 0.36),
                           (sx * w * 0.60, -d * 0.70, h * 0.36),
                           pal["bone"], 0.0))
            out.append(box((w * 0.09, w * 0.02, w * 0.02),
                           (sx * w * 0.60, -d * 0.70, h * 0.70),
                           pal["bone"], 0.0))
    elif kind == "vines":
        for sx in (-1, 1):
            out.append(box((w * 0.05, w * 0.05, h * 0.30),
                           (sx * w * 0.50, -d * 0.52, h * 0.30),
                           pal["leaf_dark"], 0.02))
            out.append(box((w * 0.07, w * 0.05, h * 0.10),
                           (sx * w * 0.50, -d * 0.52, h * 0.68),
                           pal["leaf"], 0.03))
    return out


# ---------------------------------------------------------------- Gebaeude

def build_one(bid, fac):
    r = cb.RECIPES[bid]
    pal = cb.PALETTES[fac]
    w = u(r["w"])
    h = u(r["h"]) if r["h"] else 0.0
    d = w * 0.62
    parts = []

    if r.get("custom") == "wall":
        # Mauerbahn mit Tor und zwei Flankentuermen.
        parts += [
            box((w * 0.5, d * 0.22, u(56)), (0, 0, u(56)), pal["wall_mid"], 0.02),
            box((w * 0.5, d * 0.24, u(10)), (0, 0, u(120)), pal["wall_dark"], 0.01),
            box((u(46), d * 0.26, u(76)), (-w * 0.42, 0, u(76)),
                pal["wall_mid"], 0.02),
            box((u(46), d * 0.26, u(76)), (w * 0.42, 0, u(76)),
                pal["wall_mid"], 0.02),
            box((u(34), 0.012, u(60)), (0, -d * 0.24, u(60)), pal["door"], 0.0),
        ]
        h = u(132)
    elif r.get("custom") == "scout":
        # Schlanker Holzturm mit Ausguck-Plattform.
        parts += [
            box((u(20), u(20), u(96)), (0, 0, u(96)), pal["wood"], 0.01),
            box((u(58), u(46), u(9)), (0, 0, u(200)), pal["wood"], 0.02),
            box((u(52), u(40), u(26)), (0, 0, u(232)), pal["wall_mid"], 0.02),
            cone(u(58), u(52), (0, 0, u(276)), pal["roof"], verts=6),
        ]
        h = u(300)
    elif r.get("tower"):
        parts.append(cone(w * 0.5, h, (0, 0, h * 0.5), pal["wall_mid"],
                          verts=10))
        parts.append(cone(w * 0.60, u(20), (0, 0, h + u(10)),
                          pal["wall_dark"], verts=10))
        parts += roof("spike", pal, w, h + u(20), u(70))
        h += u(20) + u(70)
    else:
        parts.append(box((w * 0.5, d * 0.5, h * 0.5), (0, 0, h * 0.5),
                         pal["wall_mid"], 0.02))
        top = h
        if r.get("roof"):
            parts += roof(r["roof"], pal, w, top, u(r.get("rise", 40)))
            top += u(r.get("rise", 40))
        if r.get("upper"):
            uw, uh, ur, urise = r["upper"]
            uw3 = u(uw)
            uh3 = u(uh)
            parts.append(box((uw3 * 0.5, uw3 * 0.31, uh3 * 0.5),
                             (0, 0, h + uh3 * 0.5), pal["wall_mid"], 0.02))
            parts += roof(ur, pal, uw3, h + uh3, u(urise))
            top = h + uh3 + u(urise)
        h = top

    parts += ornaments(r.get("orn", []), pal, w, u(r["h"]) if r["h"] else h)
    if r.get("faction_orn", True):
        parts += signature(pal["signature"], pal, w, u(r["h"]) if r["h"] else h)
    return merge("b_%s_%s" % (fac, bid), parts)


# ---------------------------------------------------------------- Hof

def make_ground():
    """Hofboden, Weg und Platz. Der Boden ist EIN Stueck: der Hof wird nie
    Feld fuer Feld angetippt, sondern immer als Ganzes gezeigt.

    BODEN UND WEG SIND 1x1 GROSS und werden in der Ansicht auf die
    Hofgroesse gezogen (Massstab je Aufstellung). Stuenden die Masse hier,
    gaebe es sie zweimal - einmal als YARD_W/YARD_D in CityView3D.gd und
    einmal als Zahl in diesem Generator; beim naechsten Umbau des Hofs
    laegen Boden und Bauplaetze auseinander.
    """
    # Dunkler als vorher: seit It. 62 scheint eine Sonne auf den Hof, und
    # #5f5a4a wurde damit zu einem hellen Beige, auf dem die Gebaeude
    # keinen Halt mehr hatten.
    box((0.5, 0.5, 0.04), (0, 0, -0.04), "#46402f", 0.0, name="city_ground")
    box((0.5, 0.5, 0.006), (0, 0, 0.006), "#63583f", 0.0, name="city_road")
    # Pflastersteine fuer den Weg: ohne sie ist er ein leerer Streifen,
    # und genau das war nach dem Bewuchs ringsum das Auffaelligste.
    merge("city_cobble", [
        box((0.055, 0.045, 0.008), (0, 0, 0.008), "#7a6e52", 0.006),
        box((0.040, 0.038, 0.008), (0.075, 0.03, 0.008), "#6b6049", 0.006,
            rot=(0, 0, rad(20))),
        box((0.036, 0.034, 0.008), (-0.06, -0.05, 0.008), "#847858", 0.006,
            rot=(0, 0, rad(-14))),
    ])
    ob = cone(0.62, 0.02, (0, 0, 0.012), "#948a70", verts=16,
              name="city_plaza")
    ob.scale = (1.0, 0.62, 1.0)
    bpy.ops.object.transform_apply(scale=True)


def make_props():
    """Was im Hof herumsteht: Fass, Kiste, Karren, Laterne, Baum.

    WARUM DAS NOETIG IST: der Hof war eine leere Flaeche mit neun
    Gebaeuden darauf. Auf der Weltkarte hat genau dieselbe Behandlung -
    dicht gestreuter Bewuchs - den groessten Unterschied gemacht; die
    Stadt hat sie nie bekommen. Eine Stadt ohne Gerumpel zwischen den
    Haeusern liest sich als Architekturmodell, nicht als Ort, an dem
    jemand wohnt.
    """
    merge("city_barrel", [
        box((0.075, 0.075, 0.10), (0, 0, 0.10), "#6b4a2a", 0.035),
        box((0.082, 0.082, 0.012), (0, 0, 0.055), "#4a3520", 0.004),
        box((0.082, 0.082, 0.012), (0, 0, 0.150), "#4a3520", 0.004),
    ])
    merge("city_crate", [
        box((0.085, 0.075, 0.075), (0, 0, 0.075), "#8a6a3a", 0.012),
        box((0.088, 0.012, 0.012), (0, 0, 0.075), "#5f4726", 0.0),
    ])
    merge("city_cart", [
        box((0.20, 0.10, 0.05), (0, 0, 0.16), "#7a5a34", 0.015),
        box((0.035, 0.035, 0.09), (-0.13, 0.11, 0.09), "#4a3520", 0.03,
            rot=(rad(90), 0, 0)),
        box((0.035, 0.035, 0.09), (-0.13, -0.11, 0.09), "#4a3520", 0.03,
            rot=(rad(90), 0, 0)),
        box((0.022, 0.022, 0.16), (0.19, 0, 0.20), "#6b4a2a", 0.0,
            rot=(0, rad(66), 0)),
    ])
    merge("city_lamp", [
        box((0.028, 0.028, 0.030), (0, 0, 0.030), "#4a4640", 0.010),
        box((0.016, 0.016, 0.20), (0, 0, 0.23), "#3a3730", 0.006),
        box((0.045, 0.045, 0.050), (0, 0, 0.48), "#ffd98a", 0.018),
        box((0.052, 0.052, 0.014), (0, 0, 0.53), "#3a3730", 0.006),
    ])
    merge("city_tree", [
        box((0.05, 0.05, 0.16), (0, 0, 0.16), "#4a3520", 0.015),
        box((0.20, 0.19, 0.15), (0, 0, 0.46), "#2f5a24", 0.075),
        box((0.13, 0.12, 0.10), (0.03, -0.02, 0.68), "#3e7a2c", 0.05),
    ])
    # Bodenflicken: flache, leicht andersfarbige Flaechen. Sie kosten fast
    # nichts und nehmen dem Hof das Gleichmaessige - dieselbe Idee wie die
    # Farbstreuung je Kachel auf der Weltkarte, nur ohne Kacheln.
    # Der Flicken ist NUR eine Nuance heller als der Hof (#46402f). Beim
    # ersten Anlauf war er mit #5a5240 deutlich heller und wurde bis 3.2
    # Einheiten gross skaliert - auf einem 6 Einheiten breiten Hof lagen
    # damit graue Platten herum, die ueber den Rand hinausragten. Ein
    # Flicken soll die Flaeche BRECHEN, nicht sie ersetzen.
    # SIEBENECK, kein Quadrat. Als gedrehtes Quadrat las sich der Flicken
    # als Blatt Papier auf dem Boden - eine gerade Kante mit vier Ecken
    # sieht immer nach Absicht aus. Ein Vieleck mit ungerader Eckenzahl
    # liest sich als Flaeche.
    import bpy as _b
    _b.ops.mesh.primitive_cylinder_add(vertices=7, radius=0.5, depth=0.008,
                                       location=(0, 0, 0.004))
    ob = _b.context.active_object
    ob.name = "city_patch"
    bk._bake(ob)
    ob.data.materials.append(bk.material("city_patch_m", "#4d472f"))


def make_scaffold():
    """Baustelle: Geruest statt Gebaeude. Fraktionsneutral, wie die
    2D-Baustellen in assets/city/_shared/."""
    parts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box((0.022, 0.022, 0.34), (sx * 0.34, sy * 0.24, 0.34),
                             "#8a6a3a", 0.0))
    parts.append(box((0.36, 0.26, 0.016), (0, 0, 0.40), "#9a7a44", 0.01))
    parts.append(box((0.36, 0.26, 0.016), (0, 0, 0.66), "#9a7a44", 0.01))
    parts.append(box((0.30, 0.22, 0.10), (0, 0, 0.10), "#6a6055", 0.02))
    merge("city_scaffold", parts)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    layout = json.load(open(LAYOUT, encoding="utf-8"))
    ids = list(layout["buildings"].keys())
    missing = [b for b in ids if b not in cb.RECIPES]
    if missing:
        raise SystemExit("Ohne Rezept: %s" % missing)
    for fac in FACTIONS:
        for bid in ids:
            build_one(bid, fac)
    make_ground()
    make_props()
    make_scaffold()

    try:
        out = sys.argv[sys.argv.index("--") + 1]
    except (ValueError, IndexError):
        out = "city.glb"
    bk.export(out)


if __name__ == "__main__":
    main()
