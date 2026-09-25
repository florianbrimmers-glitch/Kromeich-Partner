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

# DACHMATERIAL NACH FUNKTION (It. 70).
#
# Bis dahin nahm jedes Dach pal["roof"] - und bei den Menschen sind sogar
# roof, roof_light und roof_dark drei Blautoene. In der Stadt standen
# damit gleiche Dachfarben auf gleichen Dachformen. Eine echte Stadt
# deckt nach Zweck: der Stall mit Stroh, die Schmiede mit Schiefer (Funken
# und Russ), die repraesentativen Bauten in der Farbe ihres Herrn.
#
# NUR FUER DIE RAEUMLICHE ANSICHT. Die 2D-Rezepte bleiben unberuehrt.
# Stroh gedaempft: #b8984f kam unter ACES und Saettigung 1.22 als grelles
# Gelb heraus und war das Hellste in der ganzen Stadt.
THATCH = {"menschen": "#9c8349", "waldvolk": "#8d7c45",
          "totenreich": "#6c6773", "orks": "#86693c"}
# Kupfer mit Gruenspan fuer Turmspitzen - bewusst KEINE Palettenfarbe, damit
# sich die Spitze vom Dach darunter abhebt.
COPPER = {"menschen": "#5d8a76", "waldvolk": "#b0893f",
          "totenreich": "#4d7a66", "orks": "#8a5634"}
# Tierhaut fuer die Zeltdaecher der Orks.
HIDE = "#7a5a3a"
SLATE = {"menschen": "#3b4350", "waldvolk": "#344230",
         "totenreich": "#26232f", "orks": "#2f2618"}

# Welches Dach auf welchem Bau - Form, Material, Hoehenfaktor.
#   Material: ein Schluessel der Fraktionspalette ODER "thatch"/"slate".
# Fehlt ein Bau hier, gilt das Rezept aus gen_city_buildings.py.
ROOF_3D = {
    # Hausform: der GIEBEL zeigt zur Kamera, Schiefer.
    "schmiede": ("gable_front", "slate", 1.00),
    # Langer Stall mit Strohdach, First quer.
    "reiterei": ("gable", "thatch", 1.10),
    # Das Spitzengebaeude: steiles Walmdach in der Farbe des Herrn.
    "zitadelle": ("pyramid", "roof", 1.45),
    # Kirchenschiff mit Glockenturm und Kupferspitze.
    "kapelle": ("chapel", "roof", 1.00),
}

# DACHSTIL JE FRAKTION (It. 70).
#
# Bis dahin waren die Formen in allen vier Staedten gleich, nur umgefaerbt -
# die Orkstadt war die Menschenstadt in Braun. Hier bekommt jede Fraktion
# eine Neigung und eine Ersetzung einzelner Formen:
#   Menschen    Grundform.
#   Orks        steile Zeltdaecher aus Tierhaut statt Walmdach und Spitze.
#   Totenreich  gotisch steil - alles spitzer und hoeher.
#   Waldvolk    gerundet: Kuppeln statt Pyramiden, flachere Giebel.
ROOF_STYLE = {
    "menschen": dict(steep=1.00, swap={}),
    "orks": dict(steep=1.30, swap={"pyramid": "tent", "spike": "tent"}),
    "totenreich": dict(steep=1.55, swap={}),
    "waldvolk": dict(steep=0.85, swap={"pyramid": "dome", "spike": "dome"}),
}


def roof_color(key, pal, fac):
    if key == "thatch":
        return THATCH[fac]
    if key == "slate":
        return SLATE[fac]
    if key == "copper":
        return COPPER[fac]
    return pal[key]


def trim(sx, sy, top, rise, along, col):
    """Firstbalken und Traufbretter in dunklem Holz.

    Ohne sie verschmelzen beide Dachflaechen bei 44 Grad Neigung zu EINER
    Flaeche gleicher Farbe - das Strohdach der Reiterei las sich als flache
    gelbe Platte. Die dunkle Linie oben und unten zeichnet die Dachform.

    sx / sy sind die MASZE DES DACHES (wie bei bk.prism), nicht des Baus -
    die erste Fassung bekam die schon vergroesserte Breite und rechnete
    noch einmal drauf; die Bretter standen als lose Stangen neben dem Haus.
    """
    t = 0.022
    hx, hy = sx * 0.5, sy * 0.5
    if along == "x":
        return [box((hx, t, t), (0, 0, top + rise), col, 0.0),
                box((hx, t * 0.8, t * 0.8), (0, -hy, top), col, 0.0),
                box((hx, t * 0.8, t * 0.8), (0, hy, top), col, 0.0)]
    return [box((t, hy, t), (0, 0, top + rise), col, 0.0),
            box((t * 0.8, hy, t * 0.8), (-hx, 0, top), col, 0.0),
            box((t * 0.8, hy, t * 0.8), (hx, 0, top), col, 0.0)]


def roof(kind, pal, w, top, rise, col=None):
    """Dach auf einem Koerper der Breite w, Oberkante top."""
    d = w * 0.62
    if kind == "gable":
        # First QUER: die Dachflaeche zeigt zur Kamera. Mit Ueberstand an
        # Traufe und Ortgang - ohne ihn sitzt das Dach wie ein Deckel auf.
        return [bk.prism(w * 1.08, d * 1.22, rise, (0, 0, top),
                         col or pal["roof"], along="x")] + \
            trim(w * 1.08, d * 1.22, top, rise, "x", pal["line"])
    if kind == "gable_front":
        # First IN DIE TIEFE: der dreieckige Giebel zeigt zur Kamera.
        return [bk.prism(w * 1.10, d * 1.16, rise, (0, 0, top),
                         col or pal["roof"], along="y")] + \
            trim(w * 1.10, d * 1.16, top, rise, "y", pal["line"])
    if kind == "chapel":
        # KIRCHENSCHIFF + GLOCKENTURM. Vorher stand hier ein achteckiger
        # Kegel, dessen Fuss breiter war als der Bau - bei 44 Grad sah er
        # aus wie ein blauer Edelstein. Eine Kapelle erkennt man am
        # schmalen Turm VOR dem Schiff, nicht an einem grossen Kegel.
        out = [bk.prism(w * 1.06, d * 1.14, rise, (0, 0, top),
                        col or pal["roof"], along="y")]
        out += trim(w * 1.06, d * 1.14, top, rise, "y", pal["line"])
        bw = w * 0.20
        by = -d * 0.36
        bh = rise * 1.25
        out.append(box((bw, bw, bh * 0.5), (0, by, top + bh * 0.5),
                       pal["wall_mid"], 0.01))
        out.append(box((bw * 1.1, bw * 1.1, u(5)), (0, by, top + bh),
                       pal["wall_dark"], 0.005))
        spire_c = COPPER.get(pal.get("_fac", ""), pal["roof_light"])
        out.append(cone(bw * 1.25, rise * 2.1, (0, by, top + bh + rise * 1.05),
                        spire_c, verts=4, rot=(0, 0, rad(45))))
        return out
    if kind == "tent":
        # Orks: steiles Zeltdach aus Tierhaut, sechseckig, mit
        # herausragenden Stangen an der Spitze.
        out = [cone(w * 0.64, rise * 1.6, (0, 0, top + rise * 0.8),
                    col if col and col != pal["roof"] else HIDE, verts=6)]
        for a in (0, 120, 240):
            x = math.cos(rad(a)) * w * 0.05
            y = math.sin(rad(a)) * w * 0.05
            out.append(box((u(3), u(3), rise * 0.35),
                           (x, y, top + rise * 1.6 + rise * 0.15),
                           pal["wood"], 0.0))
        return out
    if kind == "pyramid":
        return [cone(w * 0.70, rise, (0, 0, top + rise * 0.5),
                     col or pal["roof"], verts=4, rot=(0, 0, rad(45)))]
    if kind == "spire":
        # Hoch und schlank: achteckig, doppelte Hoehe, schmaler Fuss.
        return [cone(w * 0.40, rise * 2.2, (0, 0, top + rise * 1.1),
                     col or pal["roof"], verts=8)]
    if kind == "spike":
        return [cone(w * 0.56, rise * 1.5, (0, 0, top + rise * 0.75),
                     col or pal["roof_dark"], verts=6)]
    if kind == "dome":
        # ERST am Ursprung stauchen, DANN hinstellen. ball() backt die Lage
        # sofort ins Mesh (siehe bk._bake) - eine Stauchung danach wirkt um
        # den WELTursprung und zieht die Kuppel nach unten. Beim Waldvolk
        # klebte sie dadurch als Linse vorn an der Zitadelle. Die Form war
        # vor It. 70 nie in Gebrauch, darum fiel es nicht auf.
        ob = ball(w * 0.50, (0, 0, 0), col or pal["roof_light"], subdiv=2)
        ob.scale = (1.0, 1.0, 0.70)
        bpy.ops.object.transform_apply(scale=True)
        ob.location = (0, 0, top)
        bpy.ops.object.transform_apply(location=True)
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
        # Auch der Turm folgt dem Fraktionsstil - sonst traegt er als
        # einziger Bau die Menschen-Spitze.
        tstyle = ROOF_STYLE[fac]
        tkind = tstyle["swap"].get("spike", "spike")
        trise = u(70) * tstyle["steep"]
        parts += roof(tkind, pal, w, h + u(20), trise)
        h += u(20) + trise * {"spike": 1.5, "tent": 1.95}.get(tkind, 1.0)
    else:
        parts.append(box((w * 0.5, d * 0.5, h * 0.5), (0, 0, h * 0.5),
                         pal["wall_mid"], 0.02))
        top = h
        kind3, colk, rf = ROOF_3D.get(bid, (r.get("roof"), None, 1.0))
        style = ROOF_STYLE[fac]
        kind3 = style["swap"].get(kind3, kind3)
        rf *= style["steep"]
        col3 = roof_color(colk, pal, fac) if colk else None
        pal = dict(pal, _fac=fac)
        if r.get("roof"):
            rise = u(r.get("rise", 40)) * rf
            parts += roof(kind3, pal, w, top, rise, col3)
            top += rise * {"spire": 2.2, "chapel": 3.4, "tent": 1.95}.get(
                kind3, 1.0) if kind3 != "dome" else w * 0.35
        if r.get("upper"):
            uw, uh, ur, urise = r["upper"]
            uw3 = u(uw)
            uh3 = u(uh)
            parts.append(box((uw3 * 0.5, uw3 * 0.31, uh3 * 0.5),
                             (0, 0, h + uh3 * 0.5), pal["wall_mid"], 0.02))
            ukind = kind3 if bid in ROOF_3D else style["swap"].get(ur, ur)
            rise = u(urise) * rf
            parts += roof(ukind, pal, uw3, h + uh3, rise, col3)
            top = h + uh3 + rise
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


def scaffolding(w, d, h, pal):
    """Geruest um einen Rohbau: vier Eckstangen und EIN Laufbrett-Ring.

    Die Stangen stehen auf der GRUNDFLAECHE des Gebaeudes - dadurch
    unterscheidet sich das Geruest eines breiten Marktes von dem einer
    schmalen Kapelle, auch wenn der Rohbau darunter noch niedrig ist.
    """
    px = w * 0.5 + u(14)
    py = d * 0.5 + u(14)
    top = h + u(26)
    parts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box((u(5), u(5), top * 0.5), (sx * px, sy * py, top * 0.5),
                             pal["wood"], 0.0))
    # Laufbrett NUR an den beiden Laengsseiten. Ein geschlossener Ring
    # sah von oben aus wie ein Deckel und verdeckte den Rohbau - genau der
    # Fehler des alten Geruests, dessen zwei breite Bretter bei 44 Grad
    # Neigung zu einer flachen Tafel verschmolzen.
    for sy in (-1, 1):
        parts.append(box((px, u(4), u(4)), (0, sy * py, h * 0.82),
                         pal["roof_light"], 0.0))
    # Leiter an einer Seite: zwei Holme, drei Sprossen.
    lx = -px - u(10)
    for sx in (-1, 1):
        parts.append(box((u(3), u(3), top * 0.44), (lx, sx * u(16), top * 0.44),
                         pal["wood"], 0.0))
    for i in range(3):
        parts.append(box((u(3), u(17), u(3)),
                         (lx, 0, top * (0.28 + 0.24 * i)), pal["wood"], 0.0))
    # Baumaterial daneben - macht den Platz als Baustelle lesbar, nicht als
    # halbes Gebaeude.
    parts.append(box((u(18), u(12), u(8)), (w * 0.22, py - u(16), u(8)),
                     pal["wall_dark"], 0.01))
    parts.append(box((u(11), u(9), u(6)), (-w * 0.26, py - u(14), u(6)),
                     pal["wall_dark"], 0.01))
    return parts


def build_site(bid):
    """Baustelle JE BAUPLATZ - das raeumliche Gegenstueck zu
    gen_city_buildings.build_construction(). Rohbau auf 45 Prozent Hoehe,
    kein Dach, kein Zierrat, dazu Geruest.

    WARUM JE BAUPLATZ (It. 69): bis dahin gab es EIN Geruest fuer alle
    neun Plaetze. Eine frische Stadt - der haeufigste Anblick im Spiel -
    zeigte damit neun identische Kaesten, waehrend die 2D-Ansicht seit
    It. 18 neun eigene construction-<id>.svg hat. Der Nutzer hat genau das
    auf dem Geraet gesehen: "sehr schwierig in den Farben zu sehen was was
    ist".

    FRAKTIONSNEUTRAL wie in 2D: eine Baustelle ist Geruest und Rohmauer,
    keine Fraktionsarchitektur. Das spart 27 Modelle und hebt den Rohbau
    grau vom Hofboden ab, der in jeder Fraktion erdfarben ist.
    """
    r = cb.RECIPES[bid]
    # NICHT cb.SCAFFOLD: dessen wall_mid (#9a9086) kam unter dem Licht der
    # Stadt fast weiss heraus, und neun weisse Kaesten sind so wenig
    # unterscheidbar wie neun graue. Der Rohbau ist Bruchstein, das Geruest
    # helles Holz - der Kontrast liegt zwischen den beiden, nicht zum Hof.
    pal = dict(cb.SCAFFOLD, wall_mid="#6b6359", wall_dark="#4e483f",
               roof_light="#b79a63", wood="#a8843f")
    w = u(r["w"])
    d = w * 0.62
    parts = []

    if r.get("custom") == "wall":
        # Mauerbahn: ein angefangener Abschnitt, ueber die ganze Breite.
        h = u(52)
        parts.append(box((w * 0.5, d * 0.22, h * 0.5), (0, 0, h * 0.5),
                         pal["wall_mid"], 0.02))
    elif r.get("custom") == "scout":
        # Spaeherturm: der Mast steht schon, die Plattform fehlt.
        h = u(118)
        parts.append(box((u(20), u(20), h * 0.5), (0, 0, h * 0.5),
                         pal["wood"], 0.01))
        d = u(40)
    elif r.get("tower"):
        h = u(r["h"]) * 0.32
        parts.append(cone(w * 0.5, h, (0, 0, h * 0.5), pal["wall_mid"],
                          verts=10))
    else:
        # FUNDAMENT ALS MAUERRING, nicht als Klotz. Ein voller Quader auf
        # 32 Prozent Hoehe ist breiter als hoch: bei 44 Grad Neigung sieht
        # man fast nur seine Deckflaeche, und neun Bauplaetze werden zu
        # neun grauen Platten. Ein Ring zeigt den Boden dazwischen, wirft
        # Schatten nach innen und liest sich sofort als angefangener Bau.
        h = u(r["h"]) * 0.30
        t = u(24)
        parts += [
            box((w * 0.5, t * 0.5, h * 0.5), (0, d * 0.5 - t * 0.5, h * 0.5),
                pal["wall_mid"], 0.015),
            box((w * 0.5, t * 0.5, h * 0.5), (0, -d * 0.5 + t * 0.5, h * 0.5),
                pal["wall_mid"], 0.015),
            box((t * 0.5, d * 0.5 - t, h * 0.5),
                (-w * 0.5 + t * 0.5, 0, h * 0.5), pal["wall_dark"], 0.015),
            box((t * 0.5, d * 0.5 - t, h * 0.5),
                (w * 0.5 - t * 0.5, 0, h * 0.5), pal["wall_dark"], 0.015),
        ]
        # Ein angefangener Pfeiler INNEN gibt dem Ring Tiefe - sonst liest
        # er sich von oben als gezeichnetes Rechteck.
        parts.append(box((t * 0.55, t * 0.55, h * 0.85),
                         (w * 0.18, -d * 0.12, h * 0.85), pal["wall_mid"],
                         0.015))

    # VERWORFEN: eine gezahnte Mauerkrone. Die Zaehne standen als helle
    # Streifen quer ueber dem Rohbau und machten aus neun unterschiedlichen
    # Bauplaetzen wieder neun gestreifte Kaesten - dasselbe Muster wie bei
    # den Schulterstuecken des Kreuzritters (It. 32). Die Silhouette traegt
    # den Unterschied, nicht die Verzierung.

    parts += scaffolding(w, d, h, pal)
    merge("city_site_%s" % bid, parts)


def make_scaffold():
    """Das alte, bauplatz-unabhaengige Geruest. Es bleibt als Notausgang
    fuer einen Bauplatz ohne eigene Baustelle (CityView3D faellt darauf
    zurueck), so wie 2D auf construction.svg zurueckfaellt."""
    parts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box((0.022, 0.022, 0.34), (sx * 0.34, sy * 0.24, 0.34),
                             "#8a6a3a", 0.0))
    parts.append(box((0.36, 0.26, 0.016), (0, 0, 0.40), "#9a7a44", 0.01))
    parts.append(box((0.36, 0.26, 0.016), (0, 0, 0.66), "#9a7a44", 0.01))
    parts.append(box((0.30, 0.22, 0.10), (0, 0, 0.10), "#6a6055", 0.02))
    merge("city_scaffold", parts)


# --------------------------------------------------------------- Pruefer

VIEW = os.path.join(HERE, "..", "scripts", "ui", "CityView3D.gd")

# Hoechstens so viel darf von der Silhouette eines Gebaeudes hinter einem
# anderen verschwinden. 0.45 ist nicht gegriffen: bei diesem Wert geht der
# Lauf gerade noch durch, den ich in city3d-menschen-voll.png als leserlich
# beurteilt habe - jedes der neun Gebaeude ist dort als es selbst erkennbar.
MAX_HIDDEN = 0.45


def view_consts():
    """Die Zahlen des Hofs kommen AUS CityView3D.gd, nicht aus einer Kopie.

    Eine zweite Kopie waere genau die Doppelung, an der It. 36/37, It. 42
    und It. 33 gescheitert sind: die Regel wird woanders nachgebaut und
    driftet still auseinander. gen_city_bg.py liest aus demselben Grund
    city_layout.json statt eigener Koordinaten.
    """
    import re
    txt = open(VIEW, encoding="utf-8").read()
    out = {}
    for m in re.finditer(r"^const (\w+) := (-?[0-9.]+)$", txt, re.M):
        out[m.group(1)] = float(m.group(2))
    need = ["YARD_W", "YARD_D", "PITCH", "PLOT_Y_LO", "PLOT_Y_HI",
            "YARD_Y_LO", "YARD_Y_HI", "BUILDING_SCALE"]
    missing = [k for k in need if k not in out]
    if missing:
        raise SystemExit("CityView3D.gd: Konstanten fehlen: %s" % missing)
    return out


def dims_of(name):
    ob = bpy.data.objects[name]
    import mathutils
    cs = [ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
    return (max(c.x for c in cs) - min(c.x for c in cs),
            max(c.y for c in cs) - min(c.y for c in cs),
            max(c.z for c in cs))


def check_occlusion(layout):
    """Kein Bauplatz darf einen anderen verdecken.

    DIE REGEL IST DIESELBE WIE BEIM GELAENDE (It. 53): bei der Neigung p
    verdeckt die Hoehe h genau h / tan(p) Einheiten Tiefe DAHINTER. Bis
    It. 69 war sie auf die Stadt nie angewendet - bei 44 Grad verdeckte
    1 Einheit Hoehe 1.04 Einheiten Tiefe, waehrend die Reihenabstaende bei
    0.13 bis 1.30 lagen. Fuenf von neun Plaetzen verschwanden hinter ihrem
    Vordermann, und das war der Hauptgrund, warum die raeumliche Stadt
    unleserlich aussah.

    Geprueft wird mit den ECHTEN Maszen der gebauten Meshes, nicht mit
    Schaetzungen aus den Rezepten.
    """
    c = view_consts()
    tan_p = math.tan(math.radians(abs(c["PITCH"])))
    plots = layout["buildings"]

    def depth(y):
        t = (y - c["PLOT_Y_LO"]) / (c["PLOT_Y_HI"] - c["PLOT_Y_LO"])
        t = min(1.0, max(0.0, t))
        return c["YARD_Y_LO"] + t * (c["YARD_Y_HI"] - c["YARD_Y_LO"])

    info = {}
    for bid, pl in plots.items():
        sc = pl.get("s", 1.0) * c["BUILDING_SCALE"]
        # Das groesste Modell ueber alle Fraktionen zaehlt - eine Stadt
        # zeigt immer nur eine, aber leserlich muessen alle vier sein.
        w = d = h = 0.0
        for fac in FACTIONS:
            fw, fd, fh = dims_of("b_%s_%s" % (fac, bid))
            w, d, h = max(w, fw), max(d, fd), max(h, fh)
        info[bid] = dict(x=(pl["x"] - 0.5) * c["YARD_W"],
                         z=(depth(pl["y"]) - 0.5) * c["YARD_D"],
                         w=w * sc, d=d * sc, h=h * sc)

    # WIE VIEL verdeckt wird, nicht OB. In jeder Schraegsicht ueberschneiden
    # sich Baukoerper ein wenig - das ist Tiefe, kein Fehler. Unleserlich
    # wird es erst, wenn von einem Gebaeude kaum noch etwas uebrig bleibt.
    #
    # Gerechnet wird in Bildschirmhoehe: bei der Neigung p liegt ein Punkt
    # (Hoehe y, Tiefe z) auf  y*cos(p) - z*sin(p).  Ein Baukoerper reicht
    # damit von seiner vorderen Unterkante bis zu seiner hinteren Oberkante.
    sin_p = math.sin(math.radians(abs(c["PITCH"])))
    cos_p = math.cos(math.radians(abs(c["PITCH"])))

    def span(q):
        lo = -(q["z"] + q["d"] / 2) * sin_p
        hi = q["h"] * cos_p - (q["z"] - q["d"] / 2) * sin_p
        return lo, hi

    bad = []
    ids = sorted(info)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            pa, pb = info[a], info[b]
            ox = (min(pa["x"] + pa["w"] / 2, pb["x"] + pb["w"] / 2)
                  - max(pa["x"] - pa["w"] / 2, pb["x"] - pb["w"] / 2))
            if ox <= 0:
                continue
            near, far = (a, b) if pa["z"] > pb["z"] else (b, a)
            pn, pf = info[near], info[far]
            nlo, nhi = span(pn)
            flo, fhi = span(pf)
            oy = min(nhi, fhi) - max(nlo, flo)
            if oy <= 0:
                continue
            # Anteil der Silhouette des HINTEREN Baus, den der vordere deckt.
            hidden = (oy / (fhi - flo)) * min(1.0, ox / pf["w"])
            if hidden > MAX_HIDDEN:
                bad.append("%s verdeckt %s zu %.0f Prozent"
                           % (near, far, hidden * 100.0))
    if bad:
        raise SystemExit("Bauplaetze verdecken sich zu stark (Grenze %.0f "
                         "Prozent):\n  %s" % (MAX_HIDDEN * 100.0,
                                              "\n  ".join(bad)))
    print("[OK] kein Bauplatz ist zu mehr als %.0f Prozent verdeckt "
          "(%d Paare geprueft)"
          % (MAX_HIDDEN * 100.0, len(ids) * (len(ids) - 1) // 2))


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
    for bid in ids:
        build_site(bid)
    make_ground()
    make_props()
    make_scaffold()
    check_occlusion(layout)

    try:
        out = sys.argv[sys.argv.index("--") + 1]
    except (ValueError, IndexError):
        out = "city.glb"
    bk.export(out)


if __name__ == "__main__":
    main()
