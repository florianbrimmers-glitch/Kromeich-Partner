#!/usr/bin/env python3
"""3D-Modelle der 28 Kreaturen (It. 54).

    /opt/blender/blender -b --factory-startup -noaudio \
        --python tools/gen_creatures.py -- game/assets/models/creatures.glb

DIE REZEPTE KOMMEN AUS gen_unit_sprites.py, NICHT AUS DIESER DATEI.
Dort steht seit It. 26 eine Tabelle RECIPES, die jeder Einheit eine
Silhouette, einen Kopf, eine Waffe und Fluegel zuordnet - und `palette()`
gibt die Farben. Beides wird hier importiert. Baute ich die Zuordnung neu,
haette ich zwei Beschreibungen derselben Kreatur: der Greif waere in 2D
ein Loewe mit Schnabel und in 3D irgendwann ein Vogel. Genau diese Sorte
Doppelung hat in It. 36/37 vier Vorschauwerkzeuge und in It. 42 den
Durchspiel-Test falsch gemacht.

SEIT It. 74 STEHT DIE FORM JE EINHEIT in figures_units.py (Bibliothek:
figures.py). Kopf und Waffe heissen dort weiter wie im Rezept; der Koerper
dagegen ist je Einheit gebaut, weil "humanoid/slim" fuer vier verschiedene
Wesen derselbe Rumpf war. Jede Einheit braucht weiterhin ein Rezept -
build() bricht ab, wenn eines fehlt.

MASSSTAB: eine Kampffeld-Zelle ist 1.0, wie eine Kachel der Weltkarte.
Die Figuren stehen mit den Fuessen auf z = 0 und schauen nach -Y, also zur
Kamera. Die Hoehe folgt der Stufe (siehe HEIGHT), die Grundflaeche bleibt
unter einer Zelle - sonst ist nicht mehr zu sehen, auf welchem Feld eine
Kreatur steht (der Fehler, den die Staedte in It. 53 hatten).
"""

import json
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_kit as bk  # noqa: E402
import gen_unit_sprites as spr  # noqa: E402

box = bk.box
cone = bk.cone
ball = bk.ball
merge = bk.merge
rad = bk.rad


def bpy_cos(deg):
    return math.cos(math.radians(deg))


def bpy_sin(deg):
    return math.sin(math.radians(deg))

HERE = os.path.dirname(os.path.abspath(__file__))
UNITS = os.path.join(HERE, "..", "data", "units.json")

# Hoehe je Stufe. Stufe 1 ist knapp kniehoch zur Zelle, Stufe 7 ueberragt
# sie deutlich - der Groessenunterschied IST die Stufenanzeige, so wie die
# Punktreihe am Sockel es in 2D ist.
#
# Die Obergrenze ist keine Geschmacksfrage: bei der Kampfkamera (40 Grad)
# verschiebt eine Hoehe h ihre Spitze um h / tan(40) = h * 1.19 Zellreihen
# nach oben. Bei 1.25 sind das anderthalb Reihen - mehr wuerde die Reihe
# dahinter zudecken, und das Brett hat nur acht.
# Stufe -> RAUMDIAGONALE der fertigen Figur. Alle Koerper werden mit H = 1
# gebaut, also nur in ihrer FORM, und am Ende auf dieses Mass gebracht.
#
# WARUM SO HERUM: zuerst stand hier eine Hoehe je Stufe, und jede
# Koerperform hat einen anderen Anteil davon in die Hoehe gesteckt - ein
# Vierbeiner ist lang statt hoch, ein Baum breit statt hoch. Damit war der
# Greif (Stufe 3) kleiner als der Armbruster (Stufe 2) und der Kavalier
# (6) kleiner als der Moench (5). Auf dem Brett sagt die Groesse aber die
# Stufe - in 2D uebernimmt das die Punktreihe am Sockel, in 3D gibt es
# nichts anderes. Eine Zahl je Stufe, EINMAL angewandt: dann kann die
# Reihenfolge gar nicht mehr auseinanderlaufen, und die Suite prueft es.
# GROESSE JE STUFE, als Raumdiagonale der Bounding-Box.
#
# Vorher: 0.72 bis 1.30. Das war schlicht ZU KLEIN. Bei 46 Grad Neigung
# erscheint eine Hoehe h als h * cos(46) = 0.69 Zellbreiten auf dem
# Schirm; aus einer Diagonale von 0.72 wurde eine Figur von rund einer
# halben Zelle. In Heroes ist eine Kreatur ungefaehr so hoch wie ihre
# Zelle breit. Die Zahlen sind deshalb um gut die Haelfte groesser.
#
# WARUM DIE DIAGONALE UND NICHT DIE HOEHE: ich habe It. 69 zuerst auf
# Hoehe umgestellt, weil in der Diagonale Breite und Tiefe mitstecken und
# breite Wesen dadurch flacher werden. Der Test war sofort rot - und zu
# Recht: mit Hoehen-Normierung ist die GESAMTGROESSE nicht mehr monoton
# (ein Greif mit ausgebreiteten Fluegeln wurde groesser als der
# Kreuzritter eine Stufe darueber). Die Diagonale ist das ehrliche Mass
# fuer "wie viel Wesen steht da"; dass ein Drache dabei lang statt hoch
# ist, ist richtig so.
TIER_SPAN = {1: 1.12, 2: 1.24, 3: 1.40, 4: 1.53, 5: 1.66, 6: 1.80,
             7: 2.02}

# Nichts darf ueber seine Zelle hinausragen - sonst ist nicht zu sehen, wo
# eine Einheit steht (der Fehler, den die Staedte in It. 53 hatten). Wer
# nach der Stufengroesse zu breit waere, wird nachtraeglich kleiner.
# GRUNDFLAECHE JE STUFE.
#
# Die Regel aus It. 53 - eine Figur darf ihre Zelle nicht verdecken - ist
# richtig und bleibt. Falsch war, sie fuer alle Stufen auf dieselbe Zahl zu
# setzen: 13 der 28 Figuren stiessen an die Grenze, fast alle mit
# ausgebreiteten Fluegeln (Greif, Ross, Engel, Knochendrache, Goldwyrm).
# Bei ihnen zog die Grenze die ganze Figur klein, die Hoehe mit - genau
# die Wesen, die eindrucksvoll sein sollen, wurden am staerksten gestaucht.
#
# Hoehere Stufen duerfen deshalb etwas ueber ihre Zelle hinausragen. Das
# ist vertretbar, weil unter jeder Figur ein Ring auf dem Boden liegt, der
# die Zelle unabhaengig von der Figur markiert - und weil ein Drache, der
# in sein Feld passt, kein Drache ist.
#
# EINE QUELLE: tools/test_creatures3d.gd liest diese Tabelle aus DIESER
# Datei, statt sie nachzubauen.
MAX_XY_BY_TIER = {1: 0.98, 2: 0.98, 3: 1.02, 4: 1.08, 5: 1.14, 6: 1.22,
                  7: 1.32}


def fit_to_tier(ob, tier):
    """Gleichmaessig skalieren, Fuesse bleiben auf z = 0."""
    import mathutils

    def dims():
        cs = [ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
        xs = [c.x for c in cs]
        ys = [c.y for c in cs]
        zs = [c.z for c in cs]
        return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs),
                min(zs))

    w, d, h, z0 = dims()
    span = (w * w + d * d + h * h) ** 0.5
    if span <= 0.0001:
        return
    k = TIER_SPAN[int(tier)] / span
    cap = MAX_XY_BY_TIER[int(tier)]
    if w * k > cap:
        k = cap / w
    if d * k > cap:
        k = min(k, cap / d)
    ob.scale = (k, k, k)
    bpy.ops.object.transform_apply(scale=True)
    _w, _d, _h, z1 = dims()
    ob.location.z -= z1
    bpy.ops.object.transform_apply(location=True)


# ---------------------------------------------------------------- Aufbau
#
# SEIT It. 74 STEHT DER KOERPER JE EINHEIT in figures_units.py, gebaut mit
# der Koerperbibliothek figures.py (durchgehende Haut statt gestapelter
# Quader, Fraktionsfarbe nur auf Stoff). Hier bleibt, was fuer alle gilt:
# Verschmelzen, Drehen, Einpassen auf die Stufe.

# Leichte Drehung aus der Achse: eine Figur, die exakt zur Kamera schaut,
# wirkt aufgestellt. Wer eine Stangenwaffe oder einen Bogen traegt, dreht
# staerker - so zeigt die Waffe quer durch die Silhouette.
#
# LANGE WESEN (Reittiere, Drachen) stehen schraeg, in Dreiviertelansicht
# wie im Vorbild. Das hat auch einen Grund in der Groesse: fit_to_tier
# misst die Raumdiagonale UND kappt die Grundflaeche je Achse. Laengs
# gestellt stiess ein Pferd mit Kopf und Schweif an die Kappung und wurde
# kleiner als die Stufe darunter; schraeg verteilt sich dieselbe Laenge
# auf beide Achsen, die Diagonale bleibt gleich.
YAW = {"men_spearman": 22.0, "men_archer": -24.0, "elf_archer": -26.0,
       "ork_orc": -20.0, "men_crusader": 18.0, "nec_blackknight": -18.0,
       "men_cavalier": 34.0, "ork_wolfrider": -30.0, "men_griffin": 30.0,
       "elf_pegasus": -32.0, "elf_unicorn": 32.0, "elf_goldwyrm": -34.0,
       "nec_bonedragon": -34.0, "ork_behemoth": -12.0}


def yaw_for(uid):
    import zlib
    if uid in YAW:
        return YAW[uid]
    h = zlib.crc32(uid.encode("utf-8"))
    return (8.0 + float(h % 9)) * (1 if (h >> 4) & 1 else -1)


def build(unit):
    import figures_units as fu
    uid = unit["id"]
    if uid not in spr.RECIPES:
        raise SystemExit("Ohne Rezept: %s" % uid)
    out = fu.BUILD[uid](unit)
    ob = merge(uid, out)
    # HARTE KANTEN, wo Flaechen im Winkel stossen (Helmrand, Klinge,
    # Schild, Sohle), weich, wo sie fliessen (Haut). Alles glatt
    # schattiert war der zweite Grund fuer das "Rundliche" (It. 74b).
    bpy.ops.object.shade_smooth_by_angle(angle=rad(40))
    ob.rotation_euler = (0, 0, rad(yaw_for(uid)))
    bpy.ops.object.transform_apply(rotation=True)
    fit_to_tier(ob, int(unit["tier"]))
    if uid == "nec_wight":
        # ERST NACH dem Einpassen anheben: fit_to_tier setzt die
        # Unterkante auf null, und damit stand das Gespenst wieder auf dem
        # Boden. Ein Gespenst, das auf dem Boden steht, ist ein Mann im
        # Bettlaken.
        ob.location.z += 0.09
        bpy.ops.object.transform_apply(location=True)
    return ob


# ---------------------------------------------------------------- Hindernisse
#
# Die Kampf-Hindernisse (Obstacles.KIND: 0 Stein, 1 Baumstamm, 2 Busch,
# 3 Sumpfloch, 4 Mauer) stehen hier und nicht bei den Weltkarten-Modellen:
# sie gehoeren zum Schlachtfeld, und die Weltkarten-Deko hat andere
# Groessen. Die Namen folgen OBSTACLE_ART im TacticalBattleScreen.

OBSTACLES = {
    0: ("ob_stone", "#8e8880"),
    1: ("ob_log", "#7a5a34"),
    2: ("ob_bush", "#3e6c20"),
    3: ("ob_swamp", "#4a5b34"),
    4: ("ob_wall", "#9a9086"),
}


def make_obstacles():
    stone = "#8e8880"
    merge("ob_stone", [
        box((0.22, 0.20, 0.15), (0, 0, 0.15), stone, 0.06,
            rot=(0, 0, rad(14))),
        box((0.13, 0.12, 0.20), (0.16, -0.09, 0.20), "#9d968c", 0.05,
            rot=(0, rad(8), rad(-24))),
    ])
    merge("ob_log", [
        box((0.34, 0.11, 0.11), (0, 0, 0.11), "#7a5a34", 0.09,
            rot=(0, 0, rad(-9))),
        box((0.05, 0.05, 0.09), (-0.30, 0.06, 0.20), "#5a4025", 0.02,
            rot=(0, rad(38), 0)),
    ])
    merge("ob_bush", [
        box((0.20, 0.18, 0.13), (0, 0, 0.13), "#2c5220", 0.08),
        box((0.13, 0.12, 0.10), (0.09, -0.07, 0.30), "#3e6c20", 0.06),
        box((0.09, 0.09, 0.08), (-0.11, 0.06, 0.26), "#4a7a26", 0.05),
    ])
    # Sumpfloch: eine EINGESENKTE Flaeche. Als Huegel waere es das
    # Gegenteil von dem, was es im Kampf bedeutet.
    merge("ob_swamp", [
        box((0.40, 0.36, 0.035), (0, 0, -0.02), "#3a4a28", 0.03),
        box((0.24, 0.20, 0.02), (0.03, -0.04, 0.005), "#55663a", 0.02),
    ])
    merge("ob_wall", [
        box((0.44, 0.13, 0.30), (0, 0, 0.30), "#9a9086", 0.03),
        box((0.46, 0.15, 0.05), (0, 0, 0.63), "#7f766d", 0.02),
    ])
    # Gerissene Mauer: dieselbe Silhouette mit einer Luecke oben - der
    # Spieler soll sehen, wo die naechste Katapultkugel die Bresche
    # schlaegt.
    merge("ob_wall_cracked", [
        box((0.44, 0.13, 0.20), (0, 0, 0.20), "#9a9086", 0.03),
        box((0.15, 0.13, 0.14), (-0.28, 0, 0.47), "#8b8279", 0.03),
        box((0.11, 0.13, 0.09), (0.30, 0, 0.44), "#8b8279", 0.03,
            rot=(0, rad(-12), 0)),
    ])


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    units = json.load(open(UNITS, encoding="utf-8"))["units"]
    missing = [u["id"] for u in units if u["id"] not in spr.RECIPES]
    if missing:
        raise SystemExit("Ohne Rezept: %s" % missing)
    for u in units:
        build(u)
    make_obstacles()

    try:
        out = sys.argv[sys.argv.index("--") + 1]
    except (ValueError, IndexError):
        out = "creatures.glb"
    bk.export(out)


if __name__ == "__main__":
    main()
