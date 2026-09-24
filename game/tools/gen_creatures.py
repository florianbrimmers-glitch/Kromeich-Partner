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

WAS HIER NEU ENTSTEHT, IST NUR DIE RAEUMLICHE FORM zu jedem Begriff der
Rezeptsprache: was "humanoid/slim" als Koerper heisst, was "helm_conical"
als Kopf heisst, was "lance" als Waffe heisst.

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
TIER_SPAN = {1: 0.72, 2: 0.80, 3: 0.90, 4: 0.99, 5: 1.07, 6: 1.16, 7: 1.30}

# Nichts darf ueber seine Zelle hinausragen - sonst ist nicht zu sehen, wo
# eine Einheit steht (der Fehler, den die Staedte in It. 53 hatten). Wer
# nach der Stufengroesse zu breit waere, wird nachtraeglich kleiner.
MAX_XY = 0.98


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
    if w * k > MAX_XY:
        k = MAX_XY / w
    if d * k > MAX_XY:
        k = min(k, MAX_XY / d)
    ob.scale = (k, k, k)
    bpy.ops.object.transform_apply(scale=True)
    _w, _d, _h, z1 = dims()
    ob.location.z -= z1
    bpy.ops.object.transform_apply(location=True)


# ---------------------------------------------------------------- Koerper
#
# Jede Funktion gibt (teile, kopf, hand, fluegel) zurueck:
#   kopf    (x, y, z, r) - wohin der Kopf gehoert und wie gross er ist
#   hand    (x, y, z)    - wo die Waffe sitzt
#   fluegel (x, y, z)    - wo Fluegel ansetzen

# --- Gliedmassen aus zwei Stuecken ----------------------------------------
#
# EIN GERADER QUADER IST KEIN ARM. Bis It. 63 bestand jedes Bein und jeder
# Arm aus genau einem achsenparallelen Kasten - das ist der Hauptgrund,
# warum die Figuren als Klotz gelesen wurden und nicht als Wesen. Zwei
# Stuecke mit einem Knick dazwischen kosten eine Handvoll Flaechen und
# geben der Silhouette einen Gelenkpunkt, den das Auge sofort findet.

def limb(p, x, y, z_top, length, w, col, out_deg=0.0, bend_deg=0.0,
         foot=None, foot_fwd=0.0):
    """Zwei Glieder von z_top nach unten, mit Knick.

    `out_deg` neigt das obere Stueck seitwaerts (Drehung um Y),
    `bend_deg` knickt das untere nach vorn oder hinten (Drehung um X).

    DIE ACHSEN AUSEINANDERZUHALTEN IST DER GANZE PUNKT. Im ersten Anlauf
    hiess der zweite Wert `fore_deg`, drehte aber ebenfalls um Y - der
    Knick ging also zur Seite statt nach hinten, und die Vierbeiner
    spreizten die Beine wie Kaefer. `foot_fwd` schiebt den Fuss nach vorn:
    beim Zweibeiner richtig, beim Tier nicht, wo die Pfote unter dem Bein
    steht.
    """
    half = length * 0.5
    upper_z = z_top - half * 0.5
    parts = [
        box((w, w * 1.05, half * 0.5), (x, y, upper_z), col, w * 0.55,
            rot=(0, rad(out_deg), 0), taper=0.86),
    ]
    dx = half * math.sin(math.radians(out_deg))
    dy = half * math.sin(math.radians(bend_deg))
    lower_z = z_top - half - half * 0.5
    parts.append(box((w * 0.86, w * 0.92, half * 0.5),
                     (x + dx, y, lower_z), col, w * 0.5,
                     rot=(rad(bend_deg), 0, 0), taper=0.88))
    if foot is not None:
        parts.append(box((w * 1.15, w * (1.15 + foot_fwd), w * 0.5),
                         (x + dx, y + dy - w * foot_fwd * 0.6, w * 0.5),
                         foot, w * 0.45))
    return parts


# --- HALTUNG ---------------------------------------------------------------
#
# DER GROESSTE EINZELNE UNTERSCHIED ZU ECHTER SPIELGRAFIK, und er kostet
# keine einzige Flaeche.
#
# Erst in It. 67 habe ich mir Referenz angesehen - Einheiten aus Heroes:
# Olden Era in Kampfgroesse. Befund: KEIN EINZIGES Wesen dort steht
# gerade. Der Satyr lehnt mit dem Speer quer vor dem Koerper und einem
# Bein vor; der Halbling steht auf einem Bein mit ungleichen Armen; der
# Drache kauert mit weggedrehtem Kopf. Meine Figuren standen bis dahin
# ausnahmslos stramm, symmetrisch, achsenparallel und blickten geradeaus.
#
# Symmetrie ist das, was eine Figur zur Spielzeugfigur macht. Vier
# Abweichungen davon reichen: ein Bein vor, Rumpf verdreht, Kopf gedreht,
# Arme ungleich.
#
# Die Werte kommen deterministisch aus der Einheiten-ID (crc32), damit
# nicht alle 28 dieselbe Haltung haben und trotzdem jeder Lauf dasselbe
# Ergebnis liefert. Wo die Waffe die Haltung diktiert, steht sie explizit
# in STANCE.
# Die Werte waren im ersten Anlauf zu zaghaft. Gegen die Referenz gehalten
# war der Unterschied da, aber die Figuren standen weiter "leicht aus dem
# Gleichgewicht" statt "in Aktion". Die Referenz uebertreibt: Rumpf um 30
# bis 40 Grad verdreht, Arme weit, Waffe quer durch die Silhouette.
DEFAULT_STANCE = dict(lead=1, step=0.075, twist=26.0, head_turn=0.07,
                      lean=0.04, arm_hi=0.09, yaw=14.0)

STANCE = {
    # Speer und Lanze quer vor dem Koerper: Waffenarm hoch, Rumpf stark
    # verdreht - so haelt man eine Stangenwaffe, und so liest man sie auch.
    "men_spearman": dict(twist=38.0, arm_hi=0.15, step=0.10, yaw=22.0),
    "ork_wolfrider": dict(twist=30.0, arm_hi=0.13),
    # Schuetzen ziehen den fuehrenden Arm vor und den anderen zurueck.
    "men_archer": dict(twist=-34.0, arm_hi=0.05, step=0.08, yaw=-26.0),
    "elf_archer": dict(twist=-36.0, arm_hi=0.05, step=0.085, yaw=-28.0),
    "ork_orc": dict(twist=-30.0, arm_hi=0.06, yaw=-22.0),
    # Schwerkaempfer stehen breit, Gewicht hinten, Waffe hoch.
    "men_crusader": dict(twist=28.0, arm_hi=0.19, step=0.11, lean=0.06,
                         yaw=24.0),
    "nec_blackknight": dict(twist=-26.0, arm_hi=0.18, step=0.10, yaw=-20.0),
    # Der Zombie haengt: kaum Verdrehung, viel Neigung, Arme tief.
    "nec_zombie": dict(twist=14.0, arm_hi=-0.07, lean=0.13, step=0.045,
                       yaw=10.0),
}


def stance_for(uid):
    import zlib
    st = dict(DEFAULT_STANCE)
    h = zlib.crc32(uid.encode("utf-8"))
    st["lead"] = 1 if (h & 1) == 0 else -1
    st["twist"] = st["twist"] + float((h >> 1) % 11) - 5.0
    st["step"] = st["step"] + float((h >> 5) % 5) * 0.008
    st["head_turn"] = st["head_turn"] * (0.6 + float((h >> 9) % 9) * 0.1)
    st["yaw"] = st["yaw"] * (0.5 + float((h >> 13) % 11) * 0.1) * st["lead"]
    st.update(STANCE.get(uid, {}))
    return st


def sil_humanoid(p, build, H, st):
    lean = float(st.get("lean", 0.0))
    lead = int(st.get("lead", 1))
    step = float(st.get("step", 0.0))
    twist = float(st.get("twist", 0.0)) * lead
    arm_hi = float(st.get("arm_hi", 0.0))
    sw, hw = 0.20, 0.16
    if build == "broad":
        sw, hw = 0.25, 0.20
    elif build == "hunched":
        sw, hw, lean = 0.21, 0.17, lean + 0.07
    leg = 0.36 * H
    tor = 0.38 * H
    parts = []
    # EIN BEIN VOR, EINS ZURUECK. Das vordere traegt weniger, knickt also
    # staerker; das hintere ist gestreckt. Zwei Beine nebeneinander sind
    # eine Puppe.
    for sx in (-1, 1):
        front: bool = (sx == lead)
        parts += limb(p, sx * 0.085, (-step if front else step * 0.8),
                      leg, leg, 0.062, p["dark"],
                      out_deg=sx * 3.0,
                      bend_deg=(-13.0 if front else -3.0),
                      foot=p["dark"], foot_fwd=0.9)
    # RUMPF MIT BRUST UND TAILLE, und um die Hochachse verdreht.
    parts.append(box((hw * 0.88, 0.10, tor * 0.5), (0, -lean * 0.5,
                     leg + tor * 0.5), p["main"], 0.035,
                     rot=(0, 0, rad(twist * 0.45)),
                     taper=(sw / (hw * 0.88))))
    parts.append(box((sw, 0.105, 0.05), (0, -lean, leg + tor - 0.03),
                     p["mid"], 0.028, rot=(0, 0, rad(twist))))
    parts.append(box((sw * 0.30, sw * 0.30, 0.045 * H),
                     (0, -lean, leg + tor + 0.035 * H), p["light"], 0.012,
                     taper=0.85))
    # ARME UNGLEICH: der Waffenarm (Seite `lead`) setzt hoeher an und
    # greift weiter nach vorn, der andere haengt zurueck.
    for sx in (-1, 1):
        wpn: bool = (sx == lead)
        sh_x: float = sx * (sw + 0.035)
        sh_z: float = leg + tor - 0.03 + (arm_hi if wpn else -arm_hi * 0.5)
        parts += limb(p, sh_x, -lean - (0.09 if wpn else -0.07), sh_z,
                      tor * 0.86, 0.048, p["main"],
                      out_deg=sx * (2.0 if wpn else 19.0),
                      bend_deg=(-42.0 if wpn else -4.0))
    top = leg + tor + 0.07 * H
    # Der Kopf sitzt leicht aus der Achse - eine Figur, die genau
    # geradeaus schaut, wirkt wie aufgestellt.
    hx: float = float(st.get("head_turn", 0.0)) * lead
    return parts, (hx, -lean - 0.02, top + 0.075 * H, 0.125 * H), \
        (sw + 0.05, -0.12, leg + tor * 0.34 + arm_hi), \
        (0, 0.08, leg + tor * 0.8)


def sil_squat(p, H, st):
    leg = 0.20 * H
    tor = 0.44 * H
    parts = []
    lead = int(st.get("lead", 1))
    step = float(st.get("step", 0.0))
    for sx in (-1, 1):
        parts += limb(p, sx * 0.095, (-step if sx == lead else step * 0.8),
                      leg, leg, 0.072, p["dark"], out_deg=sx * 4.0,
                      bend_deg=(-12.0 if sx == lead else -3.0),
                      foot=p["dark"], foot_fwd=0.9)
    parts.append(box((0.19, 0.125, tor * 0.5), (0, 0, leg + tor * 0.5),
                     p["main"], 0.045, taper=1.14))
    parts.append(box((0.10, 0.09, 0.035), (0, 0, leg + tor + 0.02),
                     p["light"], 0.012, taper=0.85))
    for sx in (-1, 1):
        parts += limb(p, sx * 0.25, 0, leg + tor * 0.94, tor * 0.80, 0.052,
                      p["main"], out_deg=sx * 5.0, bend_deg=-12.0)
    top = leg + tor + 0.05
    return parts, (0, 0, top + 0.085 * H, 0.145 * H), \
        (0.25, -0.07, leg + tor * 0.32), (0, 0.09, top - 0.05)


def sil_brute(p, H, st):
    leg = 0.28 * H
    tor = 0.44 * H
    parts = []
    lead = int(st.get("lead", 1))
    step = float(st.get("step", 0.0)) * 1.2
    for sx in (-1, 1):
        parts += limb(p, sx * 0.13, (-step if sx == lead else step * 0.8),
                      leg, leg, 0.092, p["dark"], out_deg=sx * 5.0,
                      bend_deg=(-14.0 if sx == lead else -4.0),
                      foot=p["dark"], foot_fwd=0.8)
    # Breite Schultern, schmale Huefte - beim Schlaeger noch staerker als
    # beim Menschen.
    parts.append(box((0.22, 0.155, tor * 0.5), (0, -0.02, leg + tor * 0.5),
                     p["main"], 0.055, taper=1.30))
    # Arme bis zum Knie - das ist die Silhouette des Schlaegers.
    for sx in (-1, 1):
        parts += limb(p, sx * 0.33, -0.03, leg + tor * 0.92, tor * 1.05,
                      0.072, p["main"], out_deg=sx * 4.0, bend_deg=-10.0)
    top = leg + tor
    # Der Kopf sitzt TIEF und vorn: kein Hals, Schultern hoeher als der Kopf.
    return parts, (0, -0.06, top - 0.01, 0.115 * H), \
        (0.33, -0.10, leg + tor * 0.05), (0, 0.11, top - 0.06)


def sil_robed(p, H):
    hgt = 0.80 * H
    parts = [
        cone(0.28, hgt, (0, 0, hgt * 0.5), p["main"], verts=8),
        box((0.155, 0.10, 0.05), (0, 0, hgt - 0.02), p["mid"], 0.03),
        box((0.045, 0.045, 0.16 * H), (-0.18, -0.04, hgt * 0.72), p["main"], 0.02),
        box((0.045, 0.045, 0.16 * H), (0.18, -0.04, hgt * 0.72), p["main"], 0.02),
    ]
    return parts, (0, 0, hgt + 0.09 * H, 0.135 * H), \
        (0.19, -0.07, hgt * 0.64), (0, 0.09, hgt - 0.05)


def sil_skeletal(p, H, st):
    leg = 0.38 * H
    tor = 0.34 * H
    parts = [
        box((0.038, 0.04, leg * 0.5),
            (-0.075, (-st.get("step", 0.0) if st.get("lead", 1) == -1
                      else st.get("step", 0.0) * 0.8), leg * 0.5),
            p["bone"], 0.01),
        box((0.038, 0.04, leg * 0.5),
            (0.075, (-st.get("step", 0.0) if st.get("lead", 1) == 1
                     else st.get("step", 0.0) * 0.8), leg * 0.5),
            p["bone"], 0.01),
        # Rippen: drei Platten mit Luecke. Der Zwischenraum ist das
        # Erkennungsmerkmal - ein geschlossener Rumpf sieht nur duenn aus.
        box((0.135, 0.075, 0.022), (0, 0, leg + tor * 0.28), p["bone"], 0.01),
        box((0.125, 0.075, 0.022), (0, 0, leg + tor * 0.55), p["bone"], 0.01),
        box((0.110, 0.070, 0.022), (0, 0, leg + tor * 0.82), p["bone"], 0.01),
        box((0.032, 0.045, tor * 0.5), (0, 0, leg + tor * 0.5), p["mid"], 0.01),
        box((0.16, 0.07, 0.026), (0, 0, leg + tor), p["bone"], 0.01),
        box((0.034, 0.034, tor * 0.46), (-0.175, 0, leg + tor * 0.7),
            p["bone"], 0.01),
        box((0.034, 0.034, tor * 0.46), (0.175, 0, leg + tor * 0.7),
            p["bone"], 0.01),
    ]
    top = leg + tor
    return parts, (0, 0, top + 0.08 * H, 0.11 * H), \
        (0.18, -0.06, leg + tor * 0.5), (0, 0.07, top - 0.04)


def sil_spectre(p, H):
    # KEINE BEINE, und der Saum haengt UEBER dem Boden. Ein Gespenst, das
    # auf dem Boden steht, ist ein Mann im Bettlaken.
    hem = 0.09
    hgt = 0.68 * H
    parts = [
        cone(0.26, hgt, (0, 0, hem + hgt * 0.5), p["main"], verts=8),
        box((0.14, 0.09, 0.045), (0, 0, hem + hgt - 0.02), p["mid"], 0.03),
        box((0.04, 0.04, 0.15 * H), (-0.17, -0.06, hem + hgt * 0.74),
            p["main"], 0.02),
        box((0.04, 0.04, 0.15 * H), (0.17, -0.06, hem + hgt * 0.74),
            p["main"], 0.02),
    ]
    return parts, (0, -0.01, hem + hgt + 0.08 * H, 0.125 * H), \
        (0.18, -0.09, hem + hgt * 0.66), (0, 0.08, hem + hgt - 0.04)


def sil_bird(p, H):
    leg = 0.28 * H
    parts = [
        box((0.036, 0.036, leg * 0.5), (-0.09, 0.03, leg * 0.5), p["dark"], 0.01),
        box((0.036, 0.036, leg * 0.5), (0.09, 0.03, leg * 0.5), p["dark"], 0.01),
        box((0.07, 0.065, 0.018), (-0.09, -0.02, 0.018), p["dark"], 0.01),
        box((0.07, 0.065, 0.018), (0.09, -0.02, 0.018), p["dark"], 0.01),
        # Rumpf liegend, Schwanz nach hinten-oben.
        box((0.20, 0.24, 0.145), (0, 0.02, leg + 0.14), p["main"], 0.06),
        box((0.11, 0.15, 0.04), (0, 0.34, leg + 0.20), p["mid"], 0.02,
            rot=(rad(-16), 0, 0)),
        box((0.075, 0.075, 0.10), (0, -0.17, leg + 0.25), p["main"], 0.03),
    ]
    return parts, (0, -0.20, leg + 0.37, 0.105 * H), \
        (0, -0.20, leg + 0.08), (0, 0.02, leg + 0.24)


def sil_tree(p, H, big):
    """Baumwesen: Treant und Baumvater.

    EIN BAUMWESEN IST KEIN BAUM. Bis It. 64 war es genau das - ein
    gerader Stamm mit einem gruenen Kasten obendrauf und zwei Stoecken als
    Armen. Auf dem Musterblatt stand es zwischen lauter Figuren mit
    Gelenken und war das einzige, was noch wie Moebel aussah.

    Was es zur Figur macht, in der Reihenfolge ihrer Wirkung:
      * ZWEI WURZELBEINE mit Knick. Ein Wesen, das geht, hat Beine - das
        sagt mehr als jedes Detail an der Krone.
      * Ein Stamm, der nach oben schmaler wird, statt einer Saeule.
      * Astarme in zwei Stuecken, weit ausgestellt.
      * Eine Krone aus mehreren versetzten Blattballen statt EINEM Kasten.
        Ein Kasten liest sich als Dach, drei ueberlappende Ballen als Laub.
    """
    trunk_r = 0.185 if big else 0.15
    trunk_h = (0.42 if big else 0.46) * H
    leg_h = 0.17 * H
    parts = []
    for sx in (-1, 1):
        parts += limb(p, sx * trunk_r * 0.60, 0.0, leg_h, leg_h,
                      trunk_r * 0.46, p["wood"], out_deg=sx * 9.0,
                      bend_deg=-7.0, foot=p["wood"], foot_fwd=0.6)
    # Wurzelanlauf: der Uebergang von den Beinen in den Stamm. Ohne ihn
    # stehen zwei Stoecke unter einer Saeule.
    parts.append(box((trunk_r * 1.30, trunk_r * 1.20, 0.045 * H),
                     (0, 0, leg_h + 0.03 * H), p["wood"], trunk_r * 0.30,
                     taper=0.84))
    parts.append(box((trunk_r, trunk_r * 0.92, trunk_h * 0.5),
                     (0, 0, leg_h + trunk_h * 0.5), p["wood"], trunk_r * 0.26,
                     taper=0.76))
    # ARME TIEFER UND FLACHER. Im ersten Anlauf sassen sie bei 0.88 der
    # Stammhoehe und fielen steil nach unten - damit steckten sie im Laub
    # und waren auf dem Musterblatt gar nicht zu sehen. Ein Baumwesen
    # erkennt man aber genau daran, dass es ARME hat und nicht nur Krone.
    for sx in (-1, 1):
        parts += limb(p, sx * (trunk_r + 0.05), -0.02,
                      leg_h + trunk_h * 0.62, 0.34 * H, trunk_r * 0.34,
                      p["wood"], out_deg=sx * 52.0, bend_deg=-22.0)
    # Krone: drei bis fuenf Ballen, versetzt und unterschiedlich gross.
    top = leg_h + trunk_h
    balls = [(0.00, 0.00, 0.05, 1.00),
             (-0.62, 0.14, -0.03, 0.74),
             (0.56, -0.16, 0.00, 0.68)]
    if big:
        balls += [(0.10, 0.06, 0.40, 0.80), (-0.34, -0.20, 0.34, 0.62)]
    crown_top = top
    for i, (bx, by, bz, bs) in enumerate(balls):
        r = trunk_r * 1.55 * bs
        z = top + 0.085 * H + bz * H
        ob = ball(r, (bx * trunk_r * 1.9, by * trunk_r * 1.9, z),
                  p["main"] if i % 2 == 0 else p["mid"], subdiv=1)
        ob.scale = (1.0, 0.94, 0.78)
        bpy.ops.object.transform_apply(scale=True)
        parts.append(ob)
        crown_top = max(crown_top, z + r * 0.78)
    # Der Kopf ist ein Knoten im STAMM, nicht ein Ball in der Krone: so
    # schaut das Wesen nach vorn, statt eine Kugel im Laub zu haben.
    head_z = top - 0.02 * H
    return parts, (0, -trunk_r * 0.72, head_z, 0.105 * H), \
        (trunk_r + 0.16, -0.06, leg_h + trunk_h * 0.72), \
        (0, 0.06, leg_h + trunk_h * 0.9)


def sil_quadruped(p, H, kind):
    # DER ERSTE ANLAUF SAH AUS WIE EIN TISCH: eine Platte auf vier
    # Stiften, und der Kopf schwebte einen halben Schritt davor in der
    # Luft, weil ich ihn ans rechnerische Ende eines gedrehten Halses
    # gesetzt hatte, statt ihn AUF den Hals zu setzen. Jetzt sitzt der
    # Kopf am oberen Ende des Halses und ueberlappt ihn.
    leg = {"horse": 0.38, "lion": 0.33, "heavy": 0.30}[kind] * H
    body_l = {"horse": 0.30, "lion": 0.29, "heavy": 0.32}[kind]
    body_w = {"horse": 0.155, "lion": 0.165, "heavy": 0.215}[kind]
    body_h = {"horse": 0.105, "lion": 0.105, "heavy": 0.135}[kind]
    lw = 0.05 if kind != "heavy" else 0.075
    parts = []
    # GELENKBEINE statt vier Stiften. Bei einem Vierbeiner faellt das noch
    # staerker auf als beim Humanoiden: ein Tier auf geraden Stangen ist
    # ein Tisch, und genau so las sich der erste Entwurf.
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts += limb(p, sx * (body_w - lw), sy * (body_l - 0.07),
                          leg, leg, lw, p["dark"],
                          out_deg=sx * 1.5, bend_deg=sy * -10.0,
                          foot=p["dark"], foot_fwd=0.25)
    body_z = leg + body_h
    # Rumpf zur Kruppe hin schmaler - ein gleichmaessiger Kasten ist der
    # Unterschied zwischen Tier und Kiste.
    parts.append(box((body_w, body_l, body_h), (0, 0.03, body_z),
                     p["main"], body_w * 0.30, taper=0.86))
    parts.append(box((body_w * 0.94, body_l * 0.55, body_h * 0.82),
                     (0, -body_l * 0.34, body_z + body_h * 0.28),
                     p["main"], body_w * 0.28, taper=0.90))
    # Hals als kurzer, schraeger Klotz VOM Rumpf aus - Fuss am Widerrist,
    # Ende dort, wo der Kopf sitzt.
    neck_len = 0.20 * H
    nx, nz = -body_l * 0.80, body_z + body_h * 0.6
    parts.append(box((body_w * 0.46, 0.055, neck_len * 0.5),
                     (0, nx + 0.03, nz + neck_len * 0.42), p["main"], 0.028,
                     rot=(rad(28), 0, 0), taper=0.80))
    if kind == "heavy":
        parts.append(box((body_w * 0.85, 0.07, 0.05),
                         (0, 0.03, body_z + body_h + 0.03), p["mid"], 0.03))
    head_at = (0, nx - 0.06, nz + neck_len * 0.85, 0.105 * H)
    return parts, head_at, (0, nx, leg * 0.45), (0, 0.06, body_z + body_h)


def sil_dragon(p, H):
    leg = 0.22 * H
    parts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box((0.055, 0.055, leg * 0.5),
                             (sx * 0.15, sy * 0.17, leg * 0.5), p["dark"], 0.02))
    parts.append(box((0.185, 0.21, 0.125), (0, 0.03, leg + 0.125),
                     p["main"], 0.06))
    # Hals in zwei Stufen nach vorn-oben, Schwanz in zwei nach hinten.
    # LAENGE IST HIER BEGRENZT: der erste Drache mass 1.16 in der Tiefe bei
    # 1.0 Zelle - Hals und Schwanz ragten in die Nachbarfelder, und auf dem
    # Brett war nicht mehr zu sehen, wo er steht.
    # HALS STEIL NACH OBEN, Kopf UEBER dem Rumpf statt davor.
    #
    # Der erste Anlauf hat den Hals verlaengert und nach vorn gelegt. Das
    # war der falsche Hebel gleich zweimal: der Drache las sich weiter als
    # Vierbeiner, UND er wurde kleiner - `fit_to_tier` normiert auf die
    # Raumdiagonale, also bezahlt jede Verlaengerung mit Koerpergroesse.
    # Hoehe kostet dasselbe, bringt aber eine Silhouette, die kein
    # Vierbeiner hat: aufgerichteter Hals, Kopf oben.
    parts.append(box((0.075, 0.075, 0.11), (0, -0.11, leg + 0.28),
                     p["main"], 0.03, rot=(rad(16), 0, 0)))
    parts.append(box((0.060, 0.060, 0.10), (0, -0.15, leg + 0.47),
                     p["main"], 0.03, rot=(rad(22), 0, 0)))
    parts.append(box((0.065, 0.11, 0.05), (0, 0.28, leg + 0.13),
                     p["mid"], 0.02, rot=(rad(-12), 0, 0)))
    parts.append(box((0.04, 0.09, 0.035), (0, 0.42, leg + 0.19),
                     p["mid"], 0.02, rot=(rad(-26), 0, 0)))
    return parts, (0, -0.20, leg + 0.62, 0.105 * H), \
        (0, -0.22, leg + 0.12), (0, 0.02, leg + 0.24)


def sil_mounted(p, H, mount):
    parts, head, _hand, wing = sil_quadruped(
        p, H * 0.90, "horse" if mount == "horse" else "lion")
    seat = head[2] - 0.22 * H
    # Der Reiter ist ein eigener, kleiner Oberkoerper - ohne ihn ist ein
    # Kavalier nur ein Pferd.
    parts += [
        box((0.11, 0.085, 0.12 * H), (0, 0.04, seat + 0.12 * H),
            p["accent"], 0.03),
        box((0.04, 0.04, 0.11 * H), (-0.145, 0.02, seat + 0.14 * H),
            p["accent"], 0.02),
        box((0.04, 0.04, 0.11 * H), (0.145, 0.02, seat + 0.14 * H),
            p["accent"], 0.02),
    ]
    rider = (0, 0.04, seat + 0.27 * H, 0.10 * H)
    return parts, rider, head, (0.155, -0.05, seat + 0.17 * H), wing


# Jede Koerperform bekommt die Haltung mit. Die meisten ignorieren sie
# noch - der Humanoide zuerst, weil dort die Haelfte der Kreaturen haengt
# und der Unterschied am deutlichsten ist.
BODIES = {
    "humanoid": lambda p, a, H, st: sil_humanoid(p, a, H, st),
    "squat": lambda p, a, H, st: sil_squat(p, H, st),
    "brute": lambda p, a, H, st: sil_brute(p, H, st),
    "robed": lambda p, a, H, st: sil_robed(p, H),
    "skeletal": lambda p, a, H, st: sil_skeletal(p, H, st),
    "spectre": lambda p, a, H, st: sil_spectre(p, H),
    "bird": lambda p, a, H, st: sil_bird(p, H),
    "tree": lambda p, a, H, st: sil_tree(p, H, bool(a)),
    "quadruped": lambda p, a, H, st: sil_quadruped(p, H, a),
    "dragon": lambda p, a, H, st: sil_dragon(p, H),
}


# ---------------------------------------------------------------- Koepfe

# EINE Regel fuer den Grundschaedel, danach die Aufsaetze.
#
# Der erste Anlauf hat den Standardkopf sofort gebaut und in den
# Sonderfaellen mit `out[0] = box(...)` ERSETZT. Der ersetzte Quader blieb
# aber als eigenes Objekt in der Szene stehen: das glb enthielt elf
# heimatlose "box_N"-Modelle, und jede dieser Kreaturen trug einen zweiten
# Kopf in sich, den man nur nicht sah, weil der neue darueber lag.
HEAD_BASE = {
    "helm_great": (1.05, 0.95, 1.05, "metal", 0.20, 0.0),
    "helm_horned": (1.00, 0.90, 1.00, "metal", 0.25, 0.0),
    "cowl": (0.80, 0.70, 0.80, "line", 0.30, -0.15),
    "hood": (0.80, 0.70, 0.80, "line", 0.30, -0.15),
    "bare": (0.80, 0.75, 0.80, "wood", 0.30, 0.0),
    "draconic": (0.72, 1.35, 0.68, "main", 0.25, -0.30),
    "skull": (0.85, 0.85, 0.85, "bone", 0.30, 0.0),
    "skull_glow": (0.85, 0.85, 0.85, "bone", 0.30, 0.0),
    "rotten": (1.00, 0.80, 0.85, "mid", 0.40, 0.0),
}


# Koepfe, die einem WESEN gehoeren, nicht einem Helm: als Ikosaeder statt
# als Wuerfel. Ein Helm darf eckig sein, ein Schaedel nicht - und bis
# It. 63 war beides derselbe Quader mit einer Fase.
ROUND_HEADS = {"beak", "mane", "horn_single", "draconic", "rotten",
               "tusked", "eared", "one_eye", "horned", "small", "bare",
               "fanged"}


def head(kind, p, at):
    x, y, z, r = at
    fx, fy, fz, col, bev, dy = HEAD_BASE.get(kind, (1.0, 0.85, 1.0, "light",
                                                    0.35, 0.0))
    if kind in ROUND_HEADS:
        hb = ball(r * 1.02, (x, y + r * dy, z), p[col], subdiv=1)
        hb.scale = (fx, fy * 1.05, fz)
        bpy.ops.object.transform_apply(scale=True)
        out = [hb]
    else:
        out = [box((r * fx, r * fy, r * fz), (x, y + r * dy, z), p[col],
                   r * bev)]
    if kind == "helm_conical":
        out.append(cone(r * 1.05, r * 1.5, (x, y, z + r * 1.4), p["metal"],
                        verts=8))
    elif kind == "helm_great":
        out.append(box((r * 0.75, 0.012, r * 0.16), (x, y - r * 0.95, z),
                       p["line"], 0.0))
    elif kind == "helm_horned":
        for sx in (-1, 1):
            out.append(cone(r * 0.34, r * 1.5, (x + sx * r * 1.3, y, z + r * 0.5),
                            p["bone"], verts=6, rot=(0, rad(sx * 62), 0)))
    elif kind in ("cap", "small"):
        out.append(box((r * 0.95, r * 0.85, r * 0.28), (x, y, z + r * 1.0),
                       p["mid"], r * 0.2))
    elif kind in ("cowl", "hood"):
        out.append(cone(r * 1.25, r * 2.0, (x, y + r * 0.1, z + r * 0.45),
                        p["main"], verts=8))
    elif kind == "beak":
        out.append(cone(r * 0.5, r * 1.3, (x, y - r * 1.1, z - r * 0.1),
                        p["accent"], verts=6, rot=(rad(-90), 0, 0)))
    elif kind == "halo":
        # Ein RING, keine Platte. Als volle Scheibe (1.5 r im Quadrat)
        # stand ueber dem Engel ein leuchtendes Schild - auf dem
        # Musterblatt das auffaelligste Teil des ganzen Bogens.
        for a in range(6):
            ang = a * 60
            out.append(box((r * 0.30, r * 0.10, 0.014),
                           (x + r * 0.95 * bpy_cos(ang),
                            y + r * 0.2 + r * 0.95 * bpy_sin(ang),
                            z + r * 1.55), p["glow"], 0.0,
                           rot=(0, 0, rad(ang + 90))))
    elif kind == "beard":
        out.append(box((r * 0.9, r * 0.55, r * 0.9),
                       (x, y - r * 0.6, z - r * 0.75), p["light"], r * 0.3))
    elif kind == "mane":
        for i, dz in enumerate((0.5, 0.0, -0.5)):
            out.append(box((r * 0.16, r * 0.5, r * 0.42),
                           (x, y + r * (0.8 + 0.25 * i), z + r * dz),
                           p["accent"], r * 0.15))
    elif kind == "horn_single":
        out.append(cone(r * 0.28, r * 2.2, (x, y - r * 0.9, z + r * 1.1),
                        p["glow"], verts=6, rot=(rad(-42), 0, 0)))
    elif kind == "crown_leaf":
        for sx in (-1, 0, 1):
            out.append(box((r * 0.3, r * 0.3, r * 0.5),
                           (x + sx * r * 0.8, y, z + r * 1.2), p["main"],
                           r * 0.2))
    elif kind == "draconic":
        for sx in (-1, 1):
            out.append(cone(r * 0.22, r * 1.1, (x + sx * r * 0.6, y + r * 0.7,
                            z + r * 0.7), p["dark"], verts=5,
                            rot=(rad(-30), 0, 0)))
    elif kind in ("skull", "skull_glow"):
        col = p["glow"] if kind == "skull_glow" else p["line"]
        for sx in (-1, 1):
            out.append(box((r * 0.2, 0.012, r * 0.2),
                           (x + sx * r * 0.38, y - r * 0.85, z + r * 0.12),
                           col, 0.0))
        out.append(box((r * 0.55, r * 0.35, r * 0.25),
                       (x, y - r * 0.5, z - r * 0.85), p["bone"], r * 0.1))
    elif kind == "rotten":
        out.append(box((r * 0.35, r * 0.35, r * 0.3),
                       (x - r * 0.7, y, z - r * 0.3), p["main"], r * 0.3))
    elif kind == "fanged":
        for sx in (-1, 1):
            out.append(cone(r * 0.13, r * 0.45,
                            (x + sx * r * 0.32, y - r * 0.75, z - r * 0.6),
                            p["bone"], verts=4, rot=(rad(180), 0, 0)))
    elif kind == "eared":
        for sx in (-1, 1):
            out.append(box((r * 0.5, 0.014, r * 0.32),
                           (x + sx * r * 1.25, y + r * 0.1, z + r * 0.3),
                           p["light"], 0.0, rot=(0, rad(sx * -22), 0)))
    elif kind == "tusked":
        for sx in (-1, 1):
            out.append(cone(r * 0.16, r * 0.7,
                            (x + sx * r * 0.45, y - r * 0.7, z - r * 0.5),
                            p["bone"], verts=5))
    elif kind == "one_eye":
        out.append(box((r * 0.42, 0.014, r * 0.42), (x, y - r * 0.9, z + r * 0.1),
                       p["glow"], 0.0))
    elif kind == "horned":
        for sx in (-1, 1):
            out.append(cone(r * 0.3, r * 1.6,
                            (x + sx * r * 1.1, y, z + r * 0.9), p["bone"],
                            verts=6, rot=(0, rad(sx * 38), 0)))
    return out


# ---------------------------------------------------------------- Waffen

def weapon(kind, p, at):
    x, y, z = at
    if kind in ("none", "claws"):
        # Klauen sind Teil der Hand, keine Waffe im Bild - drei kurze
        # Spitzen wuerden bei Zellgroesse nur als Rauschen ankommen.
        return []
    if kind in ("spear", "lance"):
        ln = 0.36 if kind == "lance" else 0.32
        return [box((0.013, 0.013, ln * 0.5), (x, y - 0.04, z + ln * 0.18),
                    p["wood"], 0.0, rot=(rad(16), 0, 0)),
                cone(0.03, 0.10, (x, y - 0.11, z + ln * 0.62), p["metal"],
                     verts=5, rot=(rad(16), 0, 0))]
    if kind in ("sword", "greatsword"):
        ln = 0.34 if kind == "greatsword" else 0.24
        return [box((0.016, 0.008, ln * 0.5), (x, y, z + ln * 0.5),
                    p["metal"], 0.005),
                box((0.05, 0.012, 0.012), (x, y, z + 0.02), p["dark"], 0.005)]
    if kind == "twin_swords":
        out = []
        for sx in (-1, 1):
            out.append(box((0.014, 0.008, 0.11), (x * sx, y, z + 0.11),
                           p["metal"], 0.005, rot=(0, rad(sx * 18), 0)))
        return out
    if kind == "axe":
        return [box((0.012, 0.012, 0.13), (x, y, z + 0.10), p["wood"], 0.0),
                box((0.055, 0.014, 0.055), (x + 0.05, y, z + 0.20),
                    p["metal"], 0.01)]
    if kind == "dagger":
        return [box((0.010, 0.007, 0.055), (x, y - 0.02, z + 0.05),
                    p["metal"], 0.004)]
    if kind == "club":
        return [box((0.018, 0.018, 0.10), (x, y - 0.02, z + 0.08),
                    p["wood"], 0.01),
                box((0.045, 0.045, 0.07), (x, y - 0.02, z + 0.22),
                    p["wood"], 0.02)]
    if kind in ("staff", "staff_orb"):
        out = [box((0.011, 0.011, 0.22), (x, y - 0.02, z + 0.10),
                   p["wood"], 0.0)]
        if kind == "staff_orb":
            out.append(ball(0.035, (x, y - 0.02, z + 0.35), p["glow"]))
        return out
    if kind in ("bow", "longbow"):
        # QUER VOR DEM KOERPER, nicht senkrecht daneben. Senkrecht war der
        # Bogen bei Zellgroesse ein Strich, und Speertraeger und
        # Armbruster unterschieden sich nur noch am Helm. Quer gehalten
        # gibt er der Figur eine eigene Breite - genau das, was man aus
        # der Entfernung sieht.
        ln = 0.34 if kind == "longbow" else 0.28
        out = [box((0.012, 0.012, ln * 0.5), (x - 0.02, y - 0.09, z + 0.10),
                   p["wood"], 0.0, rot=(rad(90), 0, rad(18))),
               box((0.005, 0.005, ln * 0.46), (x - 0.02, y - 0.12, z + 0.10),
                   p["light"], 0.0, rot=(rad(90), 0, rad(18)))]
        # Zwei geknickte Enden machen aus dem Stab einen Bogen.
        for sz in (-1, 1):
            out.append(box((0.011, 0.011, 0.05),
                           (x - 0.02 + sz * 0.02, y - 0.09 + sz * ln * 0.46,
                            z + 0.10 + sz * 0.012),
                           p["wood"], 0.0, rot=(rad(58 * sz), 0, 0)))
        return out
    if kind == "crossbow":
        return [box((0.012, 0.09, 0.012), (x, y - 0.06, z + 0.04),
                    p["wood"], 0.0),
                box((0.075, 0.012, 0.010), (x, y - 0.13, z + 0.04),
                    p["dark"], 0.0)]
    if kind == "boulder":
        return [ball(0.075, (x + 0.02, y - 0.05, z + 0.10), p["stone"])]
    if kind == "branch":
        return [box((0.020, 0.020, 0.13), (x, y - 0.03, z + 0.08),
                    p["wood"], 0.01, rot=(0, rad(-18), 0)),
                box((0.045, 0.018, 0.035), (x + 0.07, y - 0.03, z + 0.19),
                    p["main"], 0.02)]
    return []


# ---------------------------------------------------------------- Fluegel

def wings(kind, p, at, span):
    """FLUEGEL LIEGEN FLACH, NICHT HOCHKANT.

    Der erste Anlauf hat sie als senkrechte Platten gebaut - 0.012 duenn in
    der Tiefe, hoch in Z. Das ist die Ansicht von der SEITE gedacht. Die
    Kamera schaut aber unter 40 Grad von oben, und eine senkrechte Platte
    ist von dort fast nichts: auf dem Musterblatt hatten Greif, Pegasus und
    Engel sichtbar KEINE Fluegel. Jetzt sind es flache Platten (duenn in Z,
    breit in X und Y), leicht nach hinten-oben gestellt - so, wie man einen
    Vogel von oben sieht.
    """
    x, y, z = at
    s = span / 100.0          # Die Rezepte geben die Spannweite in SVG-px.
    out = []
    for sx in (-1, 1):
        if kind == "feather":
            for i, (dx, dy, w, ln) in enumerate([(0.30, 0.02, 0.26, 0.20),
                                                 (0.58, 0.10, 0.22, 0.16),
                                                 (0.82, 0.20, 0.15, 0.12)]):
                out.append(box((w * s * 0.5, ln * s * 0.9, 0.012),
                               (x + sx * dx * s, y + dy * s,
                                z + 0.03 + 0.02 * i),
                               p["light"] if i else p["mid"], 0.008,
                               rot=(0, rad(sx * -8), rad(sx * -12))))
        elif kind in ("bat", "dragon_membrane"):
            # ZWEI SEGMENTE STATT EINER PLATTE, nach hinten gefaechert:
            # eine einzelne Platte las sich als Brett, und der Knochen
            # davor war bei Zellgroesse ein schwarzer Balken quer durchs
            # Bild. Der Knochen ist jetzt duenn und liegt AUF der Haut.
            col = p["dark"] if kind == "bat" else p["mid"]
            for i, (dx, dy, w, d, tilt) in enumerate(
                    [(0.34, -0.02, 0.34, 0.30, 12), (0.72, 0.14, 0.30, 0.24, 22)]):
                out.append(box((w * s * 0.5, d * s * 0.5, 0.009),
                               (x + sx * dx * s, y + dy * s, z + 0.05 + 0.012 * i),
                               col, 0.0,
                               rot=(0, rad(sx * -8), rad(sx * -tilt))))
            out.append(box((0.52 * s, 0.010, 0.010),
                           (x + sx * 0.50 * s, y - 0.15 * s, z + 0.07),
                           p["line"], 0.0, rot=(0, rad(sx * -12), 0)))
        elif kind == "dragon_bone":
            # Nur Streben, keine Haut - daran erkennt man den Knochendrachen.
            for i in range(3):
                out.append(box((0.44 * s, 0.012, 0.012),
                               (x + sx * 0.44 * s, y + (i - 1) * 0.13 * s,
                                z + 0.05 + 0.015 * i),
                               p["bone"], 0.0,
                               rot=(0, rad(sx * -(6 + 5 * i)), 0)))
    return out


# ---------------------------------------------------------------- Aufbau

def build(unit):
    r = spr.RECIPES[unit["id"]]
    p = spr.palette(unit)
    # Form bei H = 1; die Groesse macht fit_to_tier ganz am Ende.
    H = 1.0
    kind, arg = r["sil"]

    st = stance_for(unit["id"])
    rider_head = None
    if kind == "mounted":
        parts, head_at, mount_head, hand, wing_at = sil_mounted(p, H, arg)
        rider_head = head_at
        head_at = mount_head
    else:
        parts, head_at, hand, wing_at = BODIES[kind](p, arg, H, st)

    out = []
    if r.get("wing"):
        wk, span, _cy = r["wing"]
        out += wings(wk, p, wing_at, span)
    out += parts
    if rider_head is not None:
        # Wie in 2D: das Reittier bekommt einen schlichten Kopf, der Reiter
        # den aus dem Rezept - sonst sieht man den Reiter gar nicht.
        out += head("small", p, head_at)
        out += head(r["head"], p, rider_head)
    else:
        out += head(r["head"], p, head_at)
    out += weapon(r["wpn"], p, hand)
    if r.get("shield"):
        # BREIT UND VORN, nicht schmal an der Seite. Als 0.024 dicke Platte
        # neben dem Arm war es aus der Entfernung eine Kante; jetzt deckt
        # es den halben Oberkoerper und gibt dem Speertraeger seine eigene
        # Silhouette gegenueber dem Armbruster.
        hx, hy, hz = hand
        out.append(box((0.075, 0.014, 0.095), (-hx * 0.85, hy - 0.06, hz + 0.02),
                       p["accent"], 0.03, rot=(0, 0, rad(6))))
        out.append(box((0.030, 0.010, 0.036), (-hx * 0.85, hy - 0.08, hz + 0.02),
                       p["metal"], 0.02))
    ob = merge(unit["id"], out)
    yaw = float(st.get("yaw", 0.0)) if kind != "mounted" else 0.0
    if abs(yaw) > 0.01:
        ob.rotation_euler = (0, 0, rad(yaw))
        bpy.ops.object.transform_apply(rotation=True)
    fit_to_tier(ob, int(unit["tier"]))
    if kind == "spectre":
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
