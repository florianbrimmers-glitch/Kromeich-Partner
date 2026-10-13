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


# ---------------------------------------------------------------- Gebaeude
#
# Seit It. 76 stehen die Bauplaene in city_buildings3d.py (Baukasten:
# city_kit.py). Die Dach- und Zierfunktionen aus It. 56/70 (roof,
# ornaments, signature, ROOF_3D, ROOF_STYLE) sind damit entfallen.

def build_one(bid, fac):
    """Ein Gebaeude im Heroes-4-Stil (It. 76): Bauplan aus
    city_buildings3d.py, Stil der Fraktion, Breite aus dem 2D-Rezept."""
    import city_buildings3d as cb3
    r = cb.RECIPES[bid]
    w = u(r["w"])
    parts = cb3.BUILD[bid](cb3.STYLE[fac], w)
    ob = merge("b_%s_%s" % (fac, bid), parts)
    # Harte Kanten an Mauer, Dach und Zinnen, weich an Kuppeln und Laub.
    bpy.ops.object.shade_smooth_by_angle(angle=rad(35))
    return ob


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
#
# Der Verdeckungs-Pruefer stand bis It. 74 hier und rechnete mit der
# orthogonalen Hofkamera. Seit dem Panorama (It. 75: Perspektive,
# Terrassen) misst ihn `tools/test_city3d.gd` im BILD - mit den echten
# Mesh-Massen, der echten Kamera und dem Gelaende, auf dem die Gebaeude
# stehen. Eine Nachrechnung der Projektion hier waere eine zweite Kamera.


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

    try:
        out = sys.argv[sys.argv.index("--") + 1]
    except (ValueError, IndexError):
        out = "city.glb"
    bk.export(out)


if __name__ == "__main__":
    main()
