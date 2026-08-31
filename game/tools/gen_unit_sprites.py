#!/usr/bin/env python3
"""Erzeugt die 28 Kampf-Token als SVG.

    python3 tools/gen_unit_sprites.py

Schreibt assets/units/<fraktion>/<id>.svg. NICHT von Hand editieren -
hier aendern und neu laufen lassen.

WARUM NEU GEBAUT (It. 20): der Vorgaenger baute alle 28 Token aus FUENF
Rollen-Koerpern (Fernkampf/Flieger/Reiter/Riese/Nahkampf). Innerhalb einer
Fraktion teilten sich also sieben Stufen fuenf Formen - Skelett, Zombie,
Wicht und Vampir waren derselbe blasse Klumpen, Greif und Pegasus dieselbe
Fluegelform. Jetzt hat JEDE Einheit ein eigenes Rezept aus einer
Teile-Bibliothek, wie bei den Gebaeuden in gen_city_buildings.py.

WO DIE TOKEN LANDEN: ausschliesslich im Kampfgitter
(TacticalBattleScreen._unit_texture -> _draw_token), Groesse cell * 0.92,
also rund 86 px auf dem Handy. Kein Rekrutier-Panel, keine Armee-Liste
zeigt sie. Alles ist auf diese eine Groesse hin entschieden:

  - ViewBox 128 statt 64. Godot rastert SVG in ViewBox-Groesse; aus 64 px
    Quelle auf 86 px Ziel wird alles weich.
  - KONTUR auf jeder Silhouette. Ohne sie verschwimmt die Figur mit der
    dunklen Token-Scheibe - das war der groesste Einzelfehler vorher.
  - Die Figur fuellt rund 85 Prozent der Boxhoehe (vorher etwa 55).
  - Keine Linie duenner als ~2 Einheiten, sonst verschwindet sie.

Zwei Selbstpruefungen brechen den Lauf ab: Bildgrenzen und
Rezept-Eindeutigkeit (siehe check_bounds / check_unique).
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNITS = os.path.join(ROOT, "data", "units.json")
OUT_DIR = os.path.join(ROOT, "assets", "units")

SIZE = 128
CX = 64.0
GROUND = 114.0   # Standlinie: hier stehen alle Fuesse
TOP = 16.0       # hoeher darf nichts

# Muss zu FACTION_DIRS in WorldMapScreen/CityScreen passen.
FACTION_DIR = {
    "waldvolk": "waldvolk",
    "menschen": "menschen",
    "totenreich": "totenreich",
    "orkstaemme": "orks",
}
FACTION_RGB = {
    "waldvolk": (0.45, 0.85, 0.45),
    "menschen": (0.95, 0.85, 0.35),
    "totenreich": (0.70, 0.45, 0.90),
    "orkstaemme": (0.95, 0.35, 0.30),
}
BONE = (0.88, 0.86, 0.78)


def hexcol(rgb, scale=1.0, mix_white=0.0):
    out = []
    for c in rgb:
        v = c * scale
        v = v + (1.0 - v) * mix_white
        out.append(max(0, min(255, int(round(v * 255)))))
    return "#%02x%02x%02x" % tuple(out)


# --------------------------------------------------------------- Primitive
# Jede gefuellte Form bekommt die Kontur mit. `p` ist die Palette:
# main / dark / light / line / metal / accent.

def ell(cx, cy, rx, ry, fill, p, sw=2.5, op=1.0):
    o = ' opacity="%.2f"' % op if op != 1.0 else ""
    return ('  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s" '
            'stroke="%s" stroke-width="%.1f"%s/>' % (cx, cy, rx, ry, fill, p["line"], sw, o))


def poly(pts, fill, p, sw=2.5, op=1.0):
    d = " ".join("%.1f,%.1f" % q for q in pts)
    o = ' opacity="%.2f"' % op if op != 1.0 else ""
    return ('  <polygon points="%s" fill="%s" stroke="%s" stroke-width="%.1f" '
            'stroke-linejoin="round"%s/>' % (d, fill, p["line"], sw, o))


def path(d, fill, p, sw=2.5, op=1.0):
    o = ' opacity="%.2f"' % op if op != 1.0 else ""
    f = fill if fill else "none"
    return ('  <path d="%s" fill="%s" stroke="%s" stroke-width="%.1f" '
            'stroke-linejoin="round" stroke-linecap="round"%s/>' % (d, f, p["line"], sw, o))


def stroke_path(d, col, sw, op=1.0):
    o = ' opacity="%.2f"' % op if op != 1.0 else ""
    return ('  <path d="%s" fill="none" stroke="%s" stroke-width="%.1f" '
            'stroke-linecap="round" stroke-linejoin="round"%s/>' % (d, col, sw, o))


def blob(cx, cy, rx, ry, fill):
    """Gefuellte Form ohne Kontur - fuer Details INNERHALB einer Silhouette,
    die schon eine Kontur hat."""
    return ('  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s"/>'
            % (cx, cy, rx, ry, fill))


# ------------------------------------------------------------------ Beine

def legs(p, top, w=9, spread=13, col=None):
    # p["dark"] lag zu nah an der Kontur - die Beine verschwanden.
    c = col or p["mid"]
    out = []
    for s in (-1, 1):
        x = CX + s * spread
        out.append(poly([(x - w * 0.5, top), (x + w * 0.5, top),
                         (x + w * 0.5, GROUND - 4), (x + w * 0.5 + 3, GROUND),
                         (x - w * 0.5 - 3, GROUND)], c, p))
    return out


def quad_legs(p, body_y, w=8, front=26, back=26, col=None):
    """Vier Beine: hinten dunkler, damit Tiefe entsteht."""
    c = col or p["main"]
    out = []
    for s, off, shade in ((-1, back, 0.0), (1, front, 0.0),
                          (-1, back - 9, 1.0), (1, front - 9, 1.0)):
        x = CX + s * off
        fill = p["mid"] if shade else c
        out.append(poly([(x - w * 0.5, body_y), (x + w * 0.5, body_y),
                         (x + w * 0.5, GROUND - 3), (x + w * 0.5 + 2.5, GROUND),
                         (x - w * 0.5 - 2.5, GROUND)], fill, p))
    return out


# ------------------------------------------------------------------ Koepfe

def head(kind, p, cx, cy, r):
    """Kopfformen. Der Kopf traegt einen grossen Teil der Erkennbarkeit -
    bei 86 px sieht man Silhouette und Kopf, sonst nichts."""
    o = []
    if kind == "helm_conical":
        o.append(poly([(cx - r, cy + r * 0.5), (cx - r * 0.8, cy - r * 0.4),
                       (cx, cy - r * 1.5), (cx + r * 0.8, cy - r * 0.4),
                       (cx + r, cy + r * 0.5)], p["metal"], p))
        o.append(stroke_path("M %.1f %.1f L %.1f %.1f" % (cx - r * 0.6, cy + r * 0.1,
                                                          cx + r * 0.6, cy + r * 0.1),
                             p["line"], 3.0))
    elif kind == "helm_great":
        o.append(poly([(cx - r, cy - r), (cx + r, cy - r),
                       (cx + r * 0.9, cy + r), (cx - r * 0.9, cy + r)], p["metal"], p))
        o.append(stroke_path("M %.1f %.1f L %.1f %.1f" % (cx - r * 0.7, cy,
                                                          cx + r * 0.7, cy), p["line"], 3.5))
        o.append(poly([(cx - 2.5, cy - r), (cx + 2.5, cy - r),
                       (cx + 1.5, cy - r - 11), (cx - 1.5, cy - r - 11)], p["accent"], p, 2.0))
    elif kind == "helm_horned":
        o.append(ell(cx, cy, r, r * 1.05, p["metal"], p))
        for s in (-1, 1):
            o.append(path("M %.1f %.1f q %.1f -%.1f %.1f -%.1f"
                          % (cx + s * r * 0.8, cy - r * 0.2,
                             s * r * 0.9, r * 0.3, s * r * 1.1, r * 1.4),
                          None, p, 4.0))
        o.append(stroke_path("M %.1f %.1f L %.1f %.1f" % (cx - r * 0.6, cy + 1,
                                                          cx + r * 0.6, cy + 1), p["line"], 3.0))
    elif kind == "cap":
        o.append(ell(cx, cy, r, r, p["light"], p))
        o.append(path("M %.1f %.1f q %.1f -%.1f %.1f 0" % (cx - r, cy - r * 0.25,
                                                           r, r * 1.2, r * 2),
                      p["accent"], p, 2.0))
    elif kind == "hood":
        o.append(path("M %.1f %.1f q 0 -%.1f %.1f -%.1f q %.1f %.1f %.1f %.1f Z"
                      % (cx - r * 1.1, cy + r * 0.7, r * 2.4, r * 1.1, r * 0.6,
                         r * 1.1, r * 1.8, r * 1.1, r * 2.3), p["light"], p))
        o.append(ell(cx, cy + r * 0.15, r * 0.62, r * 0.5, p["line"], p, 0.0))
    elif kind == "skull":
        o.append(path("M %.1f %.1f a %.1f %.1f 0 1 1 %.1f 0 l -%.1f %.1f "
                      "l -%.1f 0 Z"
                      % (cx - r, cy, r, r, r * 2, r * 0.55, r * 1.15, r * 0.9),
                      p["bone"], p))
        for s in (-1, 1):
            o.append(blob(cx + s * r * 0.42, cy - r * 0.1, r * 0.25, r * 0.3, p["line"]))
        o.append(poly([(cx - 2, cy + r * 0.35), (cx + 2, cy + r * 0.35),
                       (cx, cy + r * 0.75)], p["line"], p, 0.0))
    elif kind == "skull_glow":
        o += head("skull", p, cx, cy, r)
        for s in (-1, 1):
            o.append(blob(cx + s * r * 0.42, cy - r * 0.1, r * 0.19, r * 0.22, p["glow"]))
    elif kind == "bare":
        o.append(ell(cx, cy, r, r * 1.05, p["light"], p))
        for s in (-1, 1):
            o.append(blob(cx + s * r * 0.4, cy - r * 0.15, r * 0.14, r * 0.18, p["line"]))
    elif kind == "rotten":
        o.append(ell(cx, cy, r, r * 1.02, p["light"], p))
        o.append(blob(cx - r * 0.4, cy - r * 0.1, r * 0.2, r * 0.24, p["line"]))
        o.append(stroke_path("M %.1f %.1f l %.1f %.1f" % (cx + r * 0.18, cy - r * 0.3,
                                                          r * 0.5, r * 0.35), p["line"], 2.5))
        o.append(stroke_path("M %.1f %.1f q %.1f %.1f %.1f 0"
                             % (cx - r * 0.4, cy + r * 0.45, r * 0.4, -r * 0.3, r * 0.8),
                             p["line"], 2.2))
    elif kind == "fanged":
        o.append(ell(cx, cy, r, r * 1.05, p["light"], p))
        for s in (-1, 1):
            o.append(blob(cx + s * r * 0.4, cy - r * 0.15, r * 0.16, r * 0.2, p["accent"]))
            o.append(poly([(cx + s * r * 0.28, cy + r * 0.3),
                           (cx + s * r * 0.52, cy + r * 0.3),
                           (cx + s * r * 0.4, cy + r * 0.85)], "#ffffff", p, 0.0))
    elif kind == "tusked":
        o.append(ell(cx, cy, r * 1.05, r, p["light"], p))
        for s in (-1, 1):
            o.append(blob(cx + s * r * 0.42, cy - r * 0.2, r * 0.16, r * 0.2, p["line"]))
            o.append(path("M %.1f %.1f q %.1f %.1f %.1f -%.1f"
                          % (cx + s * r * 0.3, cy + r * 0.45,
                             s * r * 0.25, r * 0.5, s * r * 0.55, r * 0.25),
                          "#efe6cf", p, 2.0))
    elif kind == "eared":
        o.append(ell(cx, cy, r * 0.95, r, p["light"], p))
        for s in (-1, 1):
            o.append(poly([(cx + s * r * 0.7, cy - r * 0.3), (cx + s * r * 1.9, cy - r * 1.1),
                           (cx + s * r * 0.85, cy + r * 0.45)], p["light"], p, 2.0))
        for s in (-1, 1):
            o.append(blob(cx + s * r * 0.35, cy - r * 0.1, r * 0.15, r * 0.19, p["line"]))
    elif kind == "one_eye":
        o.append(ell(cx, cy, r, r * 1.05, p["light"], p))
        o.append(ell(cx, cy - r * 0.1, r * 0.42, r * 0.42, "#f4ecd8", p, 2.0))
        o.append(blob(cx, cy - r * 0.1, r * 0.2, r * 0.2, p["line"]))
    elif kind == "beak":
        o.append(ell(cx, cy, r, r * 0.95, p["light"], p))
        o.append(poly([(cx + r * 0.5, cy - r * 0.25), (cx + r * 1.75, cy + r * 0.2),
                       (cx + r * 0.5, cy + r * 0.5)], p["accent"], p, 2.0))
        o.append(blob(cx + r * 0.15, cy - r * 0.25, r * 0.2, r * 0.22, p["line"]))
    elif kind == "draconic":
        o.append(path("M %.1f %.1f q %.1f -%.1f %.1f -%.1f l %.1f %.1f q -%.1f %.1f -%.1f %.1f Z"
                      % (cx - r * 1.3, cy + r * 0.4, r * 0.6, r * 1.3, r * 2.5, r * 0.7,
                         r * 0.4, r * 0.9, r * 0.9, r * 0.5, r * 2.9, r * 0.2),
                      p["light"], p))
        o.append(blob(cx + r * 0.55, cy - r * 0.35, r * 0.22, r * 0.24, p["line"]))
        for s in (0, 1):
            o.append(path("M %.1f %.1f l %.1f -%.1f" % (cx - r * 0.5 + s * r * 0.7,
                                                        cy - r * 0.5, r * 0.5, r * 1.1),
                          None, p, 3.5))
    elif kind == "horned":
        o.append(ell(cx, cy, r * 1.05, r, p["light"], p))
        for s in (-1, 1):
            o.append(path("M %.1f %.1f q %.1f -%.1f %.1f -%.1f"
                          % (cx + s * r * 0.75, cy - r * 0.3,
                             s * r * 0.7, r * 0.9, s * r * 0.35, r * 1.5),
                          None, p, 4.5))
            o.append(blob(cx + s * r * 0.4, cy, r * 0.15, r * 0.18, p["line"]))
    elif kind == "horn_single":
        o.append(path("M %.1f %.1f q %.1f -%.1f %.1f -%.1f l %.1f %.1f Z"
                      % (cx - r, cy + r * 0.5, r * 0.3, r * 1.2, r * 1.7, r * 0.3,
                         r * 0.3, r * 1.1), p["light"], p))
        o.append(poly([(cx + r * 0.35, cy - r * 0.75), (cx + r * 0.85, cy - r * 0.55),
                       (cx + r * 1.75, cy - r * 1.95)], p["accent"], p, 2.0))
        o.append(blob(cx + r * 0.45, cy - r * 0.15, r * 0.17, r * 0.2, p["line"]))
    elif kind == "mane":
        o.append(path("M %.1f %.1f q %.1f -%.1f %.1f -%.1f l %.1f %.1f Z"
                      % (cx - r, cy + r * 0.5, r * 0.3, r * 1.2, r * 1.7, r * 0.3,
                         r * 0.3, r * 1.1), p["light"], p))
        o.append(path("M %.1f %.1f q -%.1f %.1f -%.1f %.1f l %.1f %.1f Z"
                      % (cx - r * 0.4, cy - r * 0.9, r * 1.0, r * 0.2, r * 0.8, r * 1.6,
                         r * 0.9, -r * 0.5), p["accent"], p, 2.0))
        o.append(blob(cx + r * 0.45, cy - r * 0.15, r * 0.17, r * 0.2, p["line"]))
    elif kind == "beard":
        o.append(ell(cx, cy - r * 0.25, r, r * 0.8, p["light"], p))
        o.append(path("M %.1f %.1f q %.1f %.1f %.1f 0 l -%.1f %.1f Z"
                      % (cx - r * 0.9, cy + r * 0.25, r * 0.9, r * 1.9, r * 1.8,
                         r * 0.2, r * 0.3), "#e8e0cc", p, 2.0))
        for s in (-1, 1):
            o.append(blob(cx + s * r * 0.35, cy - r * 0.35, r * 0.14, r * 0.17, p["line"]))
    elif kind == "crown_leaf":
        o.append(ell(cx, cy, r * 1.15, r * 0.95, p["dark"], p))
        for i, s in enumerate((-1.1, -0.5, 0.2, 0.9)):
            o.append(ell(cx + s * r * 0.9, cy - r * 0.55 - abs(s) * 2, r * 0.6, r * 0.5,
                         p["light"], p, 2.0))
        for s in (-1, 1):
            o.append(blob(cx + s * r * 0.3, cy + r * 0.25, r * 0.13, r * 0.16, p["line"]))
    elif kind == "small":
        o.append(ell(cx, cy, r * 0.85, r * 0.9, p["light"], p))
        for s in (-1, 1):
            o.append(blob(cx + s * r * 0.32, cy - r * 0.1, r * 0.14, r * 0.16, p["line"]))
    elif kind == "halo":
        o.append(ell(cx, cy, r, r * 1.05, p["light"], p))
        for s in (-1, 1):
            o.append(blob(cx + s * r * 0.35, cy - r * 0.1, r * 0.13, r * 0.16, p["line"]))
        o.append('  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="none" '
                 'stroke="%s" stroke-width="4"/>' % (cx, cy - r * 1.5, r * 1.05, r * 0.36,
                                                     p["accent"]))
    else:
        raise ValueError("unbekannter Kopf: %s" % kind)
    return o


# ----------------------------------------------------------------- Waffen

def weapon(kind, p):
    o = []
    if kind == "spear":
        o.append(stroke_path("M 92 30 L 76 104", p["wood"], 5.0))
        o.append(poly([(94, 20), (99, 34), (88, 34)], p["metal"], p, 2.0))
    elif kind == "lance":
        o.append(stroke_path("M 100 34 L 34 66", p["wood"], 6.0))
        o.append(poly([(104, 30), (110, 42), (96, 41)], p["metal"], p, 2.0))
    elif kind == "sword":
        o.append(poly([(92, 60), (100, 58), (104, 16), (95, 18)], p["metal"], p, 2.0))
        o.append(poly([(87, 60), (105, 57), (106, 65), (88, 68)], p["accent"], p, 2.0))
    elif kind == "greatsword":
        o.append(poly([(88, 74), (100, 71), (104, 12), (91, 15)], p["metal"], p, 2.5))
        o.append(poly([(82, 72), (108, 68), (109, 78), (83, 82)], p["accent"], p, 2.0))
        o.append(stroke_path("M 90 80 L 95 96", p["wood"], 5.0))
    elif kind == "twin_swords":
        o.append(poly([(92, 62), (100, 60), (106, 20), (97, 22)], p["metal"], p, 2.0))
        o.append(poly([(36, 60), (28, 62), (22, 22), (31, 20)], p["metal"], p, 2.0))
    elif kind == "axe":
        o.append(stroke_path("M 92 34 L 86 100", p["wood"], 5.5))
        o.append(path("M 90 32 q 20 4 16 26 q -14 -6 -20 -4 Z", p["metal"], p, 2.0))
    elif kind == "hammer":
        o.append(stroke_path("M 92 36 L 86 100", p["wood"], 5.5))
        o.append(poly([(80, 24), (106, 20), (108, 40), (82, 44)], p["metal"], p, 2.5))
    elif kind == "club":
        o.append(stroke_path("M 96 44 L 84 100", p["wood"], 7.0))
        o.append(ell(99, 32, 15, 17, p["wood"], p))
        for dx, dy in ((-6, -6), (7, -3), (0, 8)):
            o.append(poly([(99 + dx - 3, 32 + dy), (99 + dx + 3, 32 + dy),
                           (99 + dx, 32 + dy - 8)], p["metal"], p, 1.5))
    elif kind == "dagger":
        o.append(poly([(88, 66), (94, 64), (97, 42), (90, 44)], p["metal"], p, 2.0))
        o.append(poly([(85, 66), (98, 63), (99, 69), (86, 72)], p["wood"], p, 1.5))
    elif kind == "staff":
        o.append(stroke_path("M 92 32 L 88 108", p["wood"], 5.5))
        o.append(ell(93, 24, 10, 10, p["accent"], p, 2.5))
    elif kind == "staff_orb":
        o.append(stroke_path("M 94 30 L 88 108", p["wood"], 5.5))
        o.append(ell(95, 21, 12, 12, p["glow"], p, 2.5))
        o.append(blob(92, 18, 4, 4, "#ffffff"))
    elif kind == "bow":
        o.append(path("M 96 26 q 20 32 0 64", None, p, 5.0))
        o.append(stroke_path("M 96 26 L 96 90", "#f2e8c8", 2.5))
        o.append(poly([(96, 58), (74, 55), (74, 61)], p["metal"], p, 1.5))
    elif kind == "longbow":
        o.append(path("M 98 18 q 24 40 0 80", None, p, 5.0))
        o.append(stroke_path("M 98 18 L 98 98", "#f2e8c8", 2.5))
        o.append(stroke_path("M 98 58 L 68 58", p["wood"], 3.0))
        o.append(poly([(70, 58), (60, 54), (60, 62)], p["metal"], p, 1.5))
    elif kind == "crossbow":
        o.append(stroke_path("M 74 62 L 104 56", p["wood"], 6.0))
        o.append(path("M 98 40 q 14 16 0 32", None, p, 4.5))
        o.append(stroke_path("M 98 40 L 98 72", "#f2e8c8", 2.2))
    elif kind == "claws":
        for s in (-1, 1):
            for k in range(3):
                x = CX + s * (30 + k * 5)
                o.append(path("M %.1f 66 q %.1f 10 %.1f 20" % (x, s * 3, s * 1),
                              None, p, 3.5))
    elif kind == "boulder":
        o.append(ell(96, 34, 17, 15, p["stone"], p))
        o.append(blob(91, 30, 6, 5, p["light"]))
    elif kind == "branch":
        for s in (-1, 1):
            o.append(stroke_path("M %.1f 62 q %.1f -14 %.1f -30"
                                 % (CX + s * 16, s * 18, s * 30), p["wood"], 6.0))
            o.append(ell(CX + s * 48, 30, 13, 10, p["light"], p, 2.0))
    elif kind == "none":
        pass
    else:
        raise ValueError("unbekannte Waffe: %s" % kind)
    return o


def shield(p, x=32, y=64):
    return [path("M %.1f %.1f q -13 0 -13 13 l 0 9 q 0 13 13 15 q 13 -2 13 -15 "
                 "l 0 -9 q 0 -13 -13 -13 Z" % (x, y), p["accent"], p),
            stroke_path("M %.1f %.1f L %.1f %.1f" % (x, y + 4, x, y + 32), p["metal"], 3.0)]


# ------------------------------------------------------------------ Fluegel

def wings(kind, p, cy=52, span=44, drop=18):
    o = []
    # WICHTIG: keine festen Minuszeichen in die Formatzeichenkette schreiben.
    # Der erste Anlauf hatte "-%.1f" und setzte dort einen bereits mit s
    # multiplizierten Wert ein - fuer s=-1 kam "--25.3" heraus, also
    # ungueltiges SVG. Alle Verschiebungen tragen ihr Vorzeichen selbst.
    if kind == "feather":
        for s in (-1, 1):
            x0 = CX + s * 12
            o.append(path("M %.1f %.1f q %.1f %.1f %.1f %.1f q %.1f %.1f %.1f %.1f Z"
                          % (x0, cy,
                             s * span * 0.5, -26.0, s * span, -12.0,
                             s * span * -0.1, 30.0, s * span * -0.55, drop),
                          p["light"], p))
            for k in range(3):
                o.append(stroke_path("M %.1f %.1f L %.1f %.1f"
                                     % (CX + s * (18 + k * 8), cy - 4,
                                        CX + s * (30 + k * 11), cy + 10 + k * 4),
                                     p["line"], 2.0))
    elif kind == "bat":
        for s in (-1, 1):
            o.append(path("M %.1f %.1f q %.1f %.1f %.1f %.1f q %.1f %.1f %.1f %.1f "
                          "q %.1f %.1f %.1f %.1f Z"
                          % (CX + s * 10, cy,
                             s * span * 0.4, -24.0, s * span, -16.0,
                             s * -4.0, 16.0, s * span * -0.35, 6.0,
                             s * -2.0, 14.0, s * span * -0.5, drop),
                          p["dark"], p))
            o.append(stroke_path("M %.1f %.1f L %.1f %.1f"
                                 % (CX + s * 12, cy, CX + s * span * 0.95, cy - 15),
                                 p["line"], 2.2))
    elif kind == "bone":
        for s in (-1, 1):
            o.append(stroke_path("M %.1f %.1f q %.1f -%.1f %.1f -%.1f"
                                 % (CX + s * 11, cy, s * span * 0.5, 26.0,
                                    s * span, 14.0), p["bone"], 5.0))
            for k in range(3):
                o.append(stroke_path("M %.1f %.1f L %.1f %.1f"
                                     % (CX + s * (22 + k * 12), cy - 7 - k * 4,
                                        CX + s * (26 + k * 13), cy + 12 + k * 3),
                                     p["bone"], 3.5))
    elif kind == "insect":
        for s in (-1, 1):
            o.append(ell(CX + s * span * 0.55, cy - 10, span * 0.42, 13,
                         p["light"], p, 2.2, 0.75))
            o.append(ell(CX + s * span * 0.42, cy + 8, span * 0.3, 9,
                         p["light"], p, 2.2, 0.6))
    else:
        raise ValueError("unbekannte Fluegel: %s" % kind)
    return o


# -------------------------------------------------------------- Silhouetten

def sil_humanoid(p, build="slim"):
    """Aufrechte Gestalt. build: slim / broad / hunched."""
    o = []
    if build == "broad":
        sh, wa, top, hy = 25.0, 15.0, 52.0, 34.0
    elif build == "hunched":
        sh, wa, top, hy = 21.0, 16.0, 58.0, 40.0
    else:
        sh, wa, top, hy = 18.0, 12.0, 52.0, 33.0
    o += legs(p, GROUND - 34, spread=11 if build == "slim" else 14)
    o.append(poly([(CX - sh, top), (CX + sh, top),
                   (CX + wa, GROUND - 32), (CX - wa, GROUND - 32)], p["main"], p))
    # Helle Brustplatte: gibt dem Rumpf Binnenkontrast statt Volltonflaeche.
    o.append(poly([(CX - sh * 0.45, top + 4), (CX + sh * 0.45, top + 4),
                   (CX + wa * 0.5, GROUND - 40), (CX - wa * 0.5, GROUND - 40)],
                  p["light"], p, 1.8))
    if build == "hunched":
        # Haengende Arme - der Zombie soll schon an der Haltung kenntlich sein.
        for s in (-1, 1):
            o.append(stroke_path("M %.1f %.1f q %.1f 18 %.1f 30"
                                 % (CX + s * sh * 0.9, top + 6, s * 6, s * 2),
                                 p["main"], 8.0))
    return o, hy


def sil_squat(p):
    o = []
    o += legs(p, GROUND - 20, w=11, spread=13)
    o.append(poly([(CX - 26, 62), (CX + 26, 62),
                   (CX + 20, GROUND - 18), (CX - 20, GROUND - 18)], p["main"], p))
    return o, 46.0


def sil_brute(p):
    """Breite Schultern, langer Arm bis fast zum Boden."""
    o = []
    o += legs(p, GROUND - 26, w=15, spread=17)
    o.append(poly([(CX - 36, 40), (CX + 36, 40),
                   (CX + 22, GROUND - 24), (CX - 22, GROUND - 24)], p["main"], p))
    o.append(stroke_path("M %.1f 46 q -14 26 -8 44" % (CX - 32), p["main"], 12.0))
    return o, 24.0


def sil_robed(p):
    """Kegel ohne Beine - Moench und Lich."""
    o = []
    o.append(path("M %.1f %.1f q -6 -46 %.1f -50 q %.1f 4 %.1f 50 Z"
                  % (CX - 32, GROUND, 32.0, 32.0, 32.0), p["main"], p))
    o.append(stroke_path("M %.1f %.1f L %.1f %.1f" % (CX, 56.0, CX, GROUND - 4),
                         p["dark"], 3.0))
    return o, 44.0


def sil_skeletal(p):
    o = []
    for s in (-1, 1):
        o.append(stroke_path("M %.1f 74 L %.1f %.1f" % (CX + s * 8, CX + s * 13, GROUND),
                             p["bone"], 6.0))
    o.append(path("M %.1f 48 q %.1f -8 %.1f 0 l -4 26 q -%.1f 8 -%.1f 0 Z"
                  % (CX - 17, 17.0, 34.0, 13.0, 26.0), p["bone"], p))
    for k in range(3):
        o.append(stroke_path("M %.1f %.1f L %.1f %.1f"
                             % (CX - 14 + k * 0.7, 56 + k * 7, CX + 14 - k * 0.7, 56 + k * 7),
                             p["line"], 2.2))
    return o, 34.0


def sil_spectre(p):
    """Kein Beinpaar - laeuft nach unten in einen Schweif aus."""
    o = []
    o.append(path("M %.1f 50 q -10 34 4 %.1f q %.1f 8 %.1f -%.1f q 14 -30 4 -%.1f Z"
                  % (CX - 22, GROUND - 50, 18.0, 36.0, 4.0, 64.0),
                  p["main"], p))
    o.append(stroke_path("M %.1f 66 q 10 22 -2 40" % (CX - 8), p["dark"], 3.0, 0.7))
    o.append(stroke_path("M %.1f 66 q -10 22 2 40" % (CX + 8), p["dark"], 3.0, 0.7))
    return o, 38.0


def sil_quadruped(p, kind="horse"):
    """Vierbeiner. kind steuert Rumpf und Hals."""
    o = []
    if kind == "heavy":
        body_y, rx, ry, neck_dx, neck_dy = 70.0, 31.0, 17.0, 27.0, 74.0
        o += quad_legs(p, body_y + 6, w=12, front=25, back=25)
    elif kind == "lion":
        body_y, rx, ry, neck_dx, neck_dy = 74.0, 27.0, 14.0, 25.0, 78.0
        o += quad_legs(p, body_y + 4, w=8, front=22, back=22)
    else:
        body_y, rx, ry, neck_dx, neck_dy = 74.0, 26.0, 13.0, 24.0, 74.0
        o += quad_legs(p, body_y + 4, w=7, front=22, back=22)
    o.append(ell(CX, body_y, rx, ry, p["main"], p))
    # Hals als kraeftiger Bogen nach oben-vorn; der Kopf sitzt am Ende.
    head_x = CX + neck_dx
    head_y = GROUND - neck_dy
    o.append(stroke_path("M %.1f %.1f Q %.1f %.1f %.1f %.1f"
                         % (CX + rx * 0.5, body_y - ry * 0.4,
                            CX + rx * 0.95, body_y - ry * 1.4,
                            head_x - 3, head_y + 10), p["main"], 14.0))
    return o, (head_x, head_y)


def sil_mounted(p, mount="horse"):
    """Reittier plus Reiter. Der Reiter macht die Silhouette hoch und
    schmal - das unterscheidet sie vom nackten Vierbeiner."""
    o, headpos = sil_quadruped(p, "horse" if mount == "horse" else "lion")
    if mount == "wolf":
        for s in (-1, 1):
            o.append(poly([(CX + 26 + s * 4, 46), (CX + 34, 34), (CX + 30 + s * 4, 50)],
                          p["dark"], p, 2.0))
    # Reiter: Torso auf dem Ruecken
    o.append(poly([(CX - 20, 34), (CX + 6, 34), (CX + 2, 62), (CX - 16, 62)],
                  p["accent"], p))
    return o, headpos, (CX - 8.0, 24.0)


def sil_bird(p):
    o = []
    for s in (-1, 1):
        o.append(stroke_path("M %.1f 84 L %.1f %.1f" % (CX + s * 10, CX + s * 15, GROUND),
                             p["accent"], 6.0))
        for k in (-1, 0, 1):
            o.append(stroke_path("M %.1f %.1f l %.1f 5" % (CX + s * 15, GROUND,
                                                           k * 7), p["accent"], 3.0))
    o.append(ell(CX, 78, 21, 17, p["main"], p))
    o.append(stroke_path("M %.1f 68 Q %.1f 52 %.1f 48" % (CX + 6, CX + 16, CX + 12),
                         p["main"], 12.0))
    return o, 42.0


def sil_dragon(p):
    """Langer Hals, Rumpf, Schweif - liest sich sofort als Drache."""
    o = []
    o.append(stroke_path("M %.1f 92 q -34 6 -40 -10" % (CX - 6), p["dark"], 9.0))
    for s in (-1, 1):
        o.append(poly([(CX + s * 12, 92), (CX + s * 20, 92), (CX + s * 17, GROUND)],
                      p["dark"], p, 2.0))
    o.append(ell(CX + 2, 84, 25, 16, p["main"], p))
    o.append(stroke_path("M %.1f 76 Q %.1f 52 %.1f 44" % (CX + 14, CX + 34, CX + 28),
                         p["main"], 12.0))
    return o, (CX + 30.0, 40.0)


def sil_tree(p, big=False):
    o = []
    w = 26.0 if big else 18.0
    o.append(path("M %.1f %.1f q -%.1f -40 %.1f -60 q %.1f 20 %.1f 60 Z"
                  % (CX - w - 10, GROUND, 4.0, w * 0.55, w * 1.5, w + 10),
                  p["wood"], p))
    for s in (-1, 1):
        o.append(stroke_path("M %.1f %.1f q %.1f 10 %.1f 12"
                             % (CX + s * w * 0.4, GROUND - 6, s * 10, s * 16),
                             p["wood"], 6.0))
    return o, 44.0 if big else 48.0


# ------------------------------------------------------------------ Rezepte
# (Silhouette, Kopf, Waffe) muss ueber alle 28 EINDEUTIG sein - check_unique
# bricht sonst ab. Genau diese Eindeutigkeit fehlte dem Vorgaenger.

RECIPES = {
    # --- Menschen
    "men_spearman":   dict(sil=("humanoid", "slim"),   head="helm_conical", wpn="spear", shield=True),
    "men_archer":     dict(sil=("humanoid", "slim"),   head="cap",          wpn="bow"),
    "men_griffin":    dict(sil=("quadruped", "lion"),  head="beak",         wpn="claws",
                           wing=("feather", 46, 40)),
    "men_crusader":   dict(sil=("humanoid", "broad"),  head="helm_great",   wpn="twin_swords"),
    "men_monk":       dict(sil=("robed", None),        head="hood",         wpn="staff"),
    "men_cavalier":   dict(sil=("mounted", "horse"),   head="helm_conical", wpn="lance"),
    "men_angel":      dict(sil=("humanoid", "broad"),  head="halo",         wpn="sword",
                           wing=("feather", 47, 44)),
    # --- Waldvolk
    "elf_dwarf":      dict(sil=("squat", None),        head="beard",        wpn="axe"),
    "elf_archer":     dict(sil=("humanoid", "slim"),   head="hood",         wpn="longbow"),
    "elf_pegasus":    dict(sil=("quadruped", "horse"), head="mane",         wpn="none",
                           wing=("feather", 45, 40)),
    "elf_treant":     dict(sil=("tree", False),        head="bare",         wpn="branch"),
    "elf_unicorn":    dict(sil=("quadruped", "horse"), head="horn_single",  wpn="none"),
    "elf_treefather": dict(sil=("tree", True),         head="crown_leaf",   wpn="branch"),
    "elf_goldwyrm":   dict(sil=("dragon", None),       head="draconic",     wpn="none",
                           wing=("insect", 44, 40)),
    # --- Totenreich
    "nec_skeleton":   dict(sil=("skeletal", None),     head="skull",        wpn="sword"),
    "nec_zombie":     dict(sil=("humanoid", "hunched"), head="rotten",      wpn="none"),
    "nec_wight":      dict(sil=("spectre", None),      head="hood",         wpn="claws"),
    "nec_vampire":    dict(sil=("humanoid", "slim"),   head="fanged",       wpn="claws",
                           wing=("bat", 45, 38)),
    "nec_lich":       dict(sil=("robed", None),        head="skull_glow",   wpn="staff_orb"),
    "nec_blackknight": dict(sil=("humanoid", "broad"), head="helm_horned",  wpn="greatsword"),
    "nec_bonedragon": dict(sil=("dragon", None),       head="skull",        wpn="none",
                           wing=("bone", 46, 42)),
    # --- Orks
    "ork_goblin":     dict(sil=("squat", None),        head="eared",        wpn="dagger"),
    "ork_wolfrider":  dict(sil=("mounted", "wolf"),    head="tusked",       wpn="spear"),
    "ork_orc":        dict(sil=("humanoid", "broad"),  head="tusked",       wpn="crossbow"),
    "ork_ogre":       dict(sil=("brute", None),        head="small",        wpn="club"),
    "ork_roc":        dict(sil=("bird", None),         head="beak",         wpn="none",
                           wing=("feather", 48, 46)),
    "ork_cyclops":    dict(sil=("brute", None),        head="one_eye",      wpn="boulder"),
    "ork_behemoth":   dict(sil=("quadruped", "heavy"), head="horned",       wpn="none"),
}


def palette(unit):
    fac = unit["faction"]
    undead = "undead" in unit["abilities"]
    rgb = BONE if undead else FACTION_RGB[fac]
    accent = FACTION_RGB[fac]
    return {
        "main": hexcol(rgb, scale=0.82),
        "dark": hexcol(rgb, scale=0.46),
        "mid": hexcol(rgb, scale=0.62),
        "light": hexcol(rgb, mix_white=0.34),
        # Kontur: sehr dunkel, aber im Farbton der Fraktion - eine reine
        # schwarze Linie sieht bei allen vier gleich aus.
        "line": hexcol(rgb, scale=0.16),
        "metal": "#c8d2dc" if not undead else "#9aa4ae",
        "accent": hexcol(accent, scale=0.9),
        "wood": "#7a5a34",
        "stone": "#8e8880",
        "bone": "#e6ddc8",
        "glow": "#7dffb0" if undead else hexcol(accent, mix_white=0.5),
    }


def build(unit):
    r = RECIPES[unit["id"]]
    p = palette(unit)
    kind, arg = r["sil"]
    body = []
    head_at = None
    rider_head = None

    if kind == "humanoid":
        body, hy = sil_humanoid(p, arg)
        head_at = (CX, hy, 18.0)
    elif kind == "squat":
        body, hy = sil_squat(p)
        head_at = (CX, hy, 18.0)
    elif kind == "brute":
        body, hy = sil_brute(p)
        head_at = (CX, hy, 16.0)
    elif kind == "robed":
        body, hy = sil_robed(p)
        head_at = (CX, hy, 17.0)
    elif kind == "skeletal":
        body, hy = sil_skeletal(p)
        head_at = (CX, hy, 16.0)
    elif kind == "spectre":
        body, hy = sil_spectre(p)
        head_at = (CX, hy, 17.0)
    elif kind == "bird":
        body, hy = sil_bird(p)
        head_at = (CX + 14, hy, 14.0)
    elif kind == "tree":
        body, hy = sil_tree(p, arg)
        head_at = (CX, hy, 19.0 if arg else 15.0)
    elif kind == "quadruped":
        body, hp = sil_quadruped(p, arg)
        head_at = (hp[0], hp[1], 17.0)
    elif kind == "dragon":
        body, hp = sil_dragon(p)
        head_at = (hp[0], hp[1], 16.0)
    elif kind == "mounted":
        body, hp, rp = sil_mounted(p, arg)
        head_at = (hp[0], hp[1], 13.0)
        rider_head = (rp[0], rp[1], 14.0)
    else:
        raise ValueError("unbekannte Silhouette: %s" % kind)

    out = []
    # Fluegel VOR dem Koerper, damit sie dahinter liegen.
    if r.get("wing"):
        wk, span, cy = r["wing"]
        out += wings(wk, p, cy=cy, span=span)
    out += body
    # Bei Reitern traegt das Reittier einen schlichten Kopf, der Reiter den
    # aus dem Rezept - sonst sieht man den Reiter gar nicht.
    if rider_head is not None:
        out += head("small", p, head_at[0], head_at[1], head_at[2])
        out += head(r["head"], p, rider_head[0], rider_head[1], rider_head[2])
    else:
        out += head(r["head"], p, head_at[0], head_at[1], head_at[2])
    out += weapon(r["wpn"], p)
    if r.get("shield"):
        out += shield(p)
    return out, p


def tier_pips(tier, p):
    """Stufe als Punktreihe am Sockel - schneller lesbar als eine Zahl und
    stoert die Silhouette nicht."""
    out = []
    total_w = (tier - 1) * 13
    x0 = CX - total_w / 2.0
    for i in range(tier):
        out.append('  <circle cx="%.1f" cy="%.1f" r="4.0" fill="#f4f0e4" '
                   'stroke="%s" stroke-width="1.2"/>' % (x0 + i * 13, GROUND + 9, p["line"]))
    return out


def make_svg(unit):
    p = palette(unit)
    inner, _ = build(unit)
    undead = "undead" in unit["abilities"]
    tier = unit["tier"]
    # Stufe skaliert dezent um den Fusspunkt, damit alle auf derselben
    # Standlinie stehen. Der Rahmen ist eng - deshalb nur 0.88..1.0.
    scale = 0.88 + 0.02 * (tier - 1)
    body = ('  <g transform="translate(%.1f,%.1f) scale(%.2f) translate(-%.1f,-%.1f)">\n'
            % (CX, GROUND, scale, CX, GROUND)) + "\n".join(inner) + "\n  </g>"
    aura = ""
    if undead:
        # Knochenhaut wuerde die Seite verschlucken - die Fraktionsfarbe
        # kommt als Aura zurueck.
        aura = ('  <ellipse cx="%.1f" cy="66" rx="42" ry="48" fill="%s" opacity="0.18"/>\n'
                % (CX, hexcol(FACTION_RGB[unit["faction"]], scale=0.9)))
    shadow_rx = 22 + 2.4 * tier
    pips = "\n".join(tier_pips(tier, p))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!-- Kampf-Token %s (%s), Stufe %d.\n'
            '     Generiert von tools/gen_unit_sprites.py - nicht per Hand editieren,\n'
            '     sondern den Generator anpassen und neu laufen lassen. -->\n'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'width="%d" height="%d">\n'
            '  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="7" fill="#000" opacity="0.42"/>\n'
            '%s%s\n%s\n</svg>\n'
            % (unit["name"], unit["id"], unit["tier"], SIZE, SIZE, SIZE, SIZE,
               CX, GROUND + 3, shadow_rx, aura, body, pips))


# ------------------------------------------------------------- Selbstpruefung

_PATH_ARGS = {"M": 2, "L": 2, "T": 2, "Q": 4, "S": 4, "C": 6, "A": 7,
              "H": 1, "V": 1, "Z": 0}


def _path_points(d):
    """Liefert die ABSOLUTEN Punkte eines Pfades.

    Zwei Fallen, beide teuer bezahlt:
    - Bei Boegen (A) sind nur die LETZTEN zwei der sieben Zahlen
      Koordinaten; Radien und Flags sind keine (Lehrgeld aus It. 18).
    - KLEINBUCHSTABEN sind relativ zum aktuellen Punkt. Ohne
      Cursor-Verfolgung meldet die Pruefung bei jedem `q -6 -46 32 -50`
      negative Koordinaten - also ueberall Fehlalarm und damit nichts.
    """
    toks = re.findall(r'[MLTQSCAHVZmltqscahvz]|-?\d+(?:\.\d+)?', d)
    pts = []
    i = 0
    cmd = "M"
    rel = False
    cur = [0.0, 0.0]
    start = [0.0, 0.0]
    while i < len(toks):
        tk = toks[i]
        if tk.upper() in _PATH_ARGS and not _is_num(tk):
            rel = tk.islower()
            cmd = tk.upper()
            i += 1
            if cmd == "Z":
                cur = list(start)
                continue
        n = _PATH_ARGS[cmd]
        if i + n > len(toks):
            break
        args = [float(x) for x in toks[i:i + n]]
        i += n
        if cmd == "H":
            cur[0] = cur[0] + args[0] if rel else args[0]
            pts.append(tuple(cur))
            continue
        if cmd == "V":
            cur[1] = cur[1] + args[0] if rel else args[0]
            pts.append(tuple(cur))
            continue
        # Zwischenpunkte zaehlen mit: eine Kontrollstelle weit ausserhalb
        # zieht die Kurve mit sich.
        base = list(cur)
        coords = args[-2:] if cmd == "A" else args
        for k in range(0, len(coords) - 1, 2):
            px = base[0] + coords[k] if rel else coords[k]
            py = base[1] + coords[k + 1] if rel else coords[k + 1]
            pts.append((px, py))
        cur = list(pts[-1])
        if cmd == "M":
            start = list(cur)
            # Weitere Paare nach M gelten als L.
            cmd = "L"
    return pts


def _is_num(tok):
    return tok[0].isdigit() or tok[0] in "-."


def check_bounds(svg, label):
    """Relative Pfadbefehle (q/l) haengen vom Startpunkt ab und werden hier
    NICHT verfolgt - die Pruefung faengt grobe Ausreisser, nicht jedes
    Pixel. Der Kontaktbogen bleibt die eigentliche Kontrolle."""
    pts = []
    for m in re.finditer(r'points="([^"]+)"', svg):
        for pair in m.group(1).split():
            x, y = pair.split(",")
            pts.append((float(x), float(y)))
    for m in re.finditer(r'<(?:circle|ellipse) cx="([-\d.]+)" cy="([-\d.]+)" '
                         r'r(?:x)?="([-\d.]+)"(?: ry="([-\d.]+)")?', svg):
        cx, cy, rx = (float(g) for g in m.groups()[:3])
        ry = float(m.group(4)) if m.group(4) else rx
        pts += [(cx - rx, cy - ry), (cx + rx, cy + ry)]
    for m in re.finditer(r'\sd="([^"]+)"', svg):
        pts += _path_points(m.group(1))
    bad = []
    if not pts:
        return ["%s: keine Geometrie" % label]
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    if min(ys) < -2 or max(ys) > SIZE + 2:
        bad.append("%s: laeuft senkrecht raus (y %.0f..%.0f)" % (label, min(ys), max(ys)))
    if min(xs) < -2 or max(xs) > SIZE + 2:
        bad.append("%s: laeuft seitlich raus (x %.0f..%.0f)" % (label, min(xs), max(xs)))
    return bad


def check_unique():
    """Kein Paar (Silhouette, Kopf, Waffe) darf zweimal vorkommen. Genau das
    war der Fehler des Vorgaengers: fuenf Rollen-Koerper fuer 28 Einheiten,
    also sahen vier Totenreich-Stufen identisch aus."""
    seen = {}
    bad = []
    for uid, r in RECIPES.items():
        key = (r["sil"], r["head"], r["wpn"])
        if key in seen:
            bad.append("%s und %s teilen sich Silhouette/Kopf/Waffe %s"
                       % (seen[key], uid, key))
        seen[key] = uid
    return bad


def main():
    units = json.load(open(UNITS))["units"]
    problems = check_unique()
    missing = [u["id"] for u in units if u["id"] not in RECIPES]
    if missing:
        problems.append("kein Rezept fuer: %s" % ", ".join(missing))
    written = 0
    for u in units:
        if u["id"] not in RECIPES:
            continue
        svg = make_svg(u)
        problems += check_bounds(svg, u["id"])
        d = os.path.join(OUT_DIR, FACTION_DIR[u["faction"]])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, u["id"] + ".svg"), "w") as f:
            f.write(svg)
        written += 1
    print("%d Token-SVGs geschrieben nach %s" % (written, OUT_DIR))
    if problems:
        print("")
        for pr in problems:
            print("[WARNUNG] %s" % pr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
