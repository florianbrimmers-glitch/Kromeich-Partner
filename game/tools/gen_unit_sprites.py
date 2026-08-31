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
import math
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


def tapered(pts, widths, fill, p, sw=2.5):
    """Umriss aus einer MITTELLINIE plus Breitenprofil.

    Warum diese Technik (It. 32): Drachen aus gestapelten Formen (Ellipse
    plus Hals plus Schweif) sind viermal misslungen - die Uebergaenge
    zwischen den Massen bleiben sichtbar und das Ergebnis liest sich als
    Vogel mit angeklebten Teilen. Hier wird der Umriss GERECHNET: entlang
    der Mittellinie werden Normalen bestimmt und links wie rechts um die
    halbe Breite versetzt. Ergebnis ist EIN organischer Koerper, der von
    der Schweifspitze bis zum Kopf durchlaeuft und in der Mitte dick ist.
    """
    left = []
    right = []
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        if i == 0:
            dx, dy = pts[1][0] - x, pts[1][1] - y
        elif i == n - 1:
            dx, dy = x - pts[-2][0], y - pts[-2][1]
        else:
            dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        w = widths[i] * 0.5
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    return poly(left + right[::-1], fill, p, sw)


def spine_spikes(pts, idxs, p, widths=None, base=5.0, grow=1.6):
    """Zacken entlang der Mittellinie. WICHTIG: die Basis sitzt auf dem
    UMRISS (halbe Koerperbreite nach aussen versetzt), nicht auf der
    Mittellinie - sonst liegen die Dreiecke mitten in der Flaeche und lesen
    sich als aufgemalte Pfeilspitzen statt als Zacken auf dem Ruecken.
    """
    out = []
    n = len(pts)
    for k, i in enumerate(idxs):
        x, y = pts[i]
        if i == 0:
            dx, dy = pts[1][0] - x, pts[1][1] - y
        elif i == n - 1:
            dx, dy = x - pts[-2][0], y - pts[-2][1]
        else:
            dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        ln = math.hypot(dx, dy) or 1.0
        tx, ty = dx / ln, dy / ln
        nx, ny = -ty, tx
        if ny > 0:                      # obere Normale
            nx, ny = ty, -tx
        off = 0.0 if widths is None else widths[i] * 0.5 - 1.5
        bx, by = x + nx * off, y + ny * off
        h = base + k * grow
        out.append(poly([(bx - tx * 3.4, by - ty * 3.4),
                         (bx + nx * h, by + ny * h),
                         (bx + tx * 3.4, by + ty * 3.4)], p["accent"], p, 1.6))
    return out


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


def animal_leg(p, x, top, foot="hoof", far=False, w=10.0, kick=0.0):
    """EIN Tierbein mit Gelenkknick. Vorher waren die vier Beine gerade
    Rechtecke gleicher Breite - bei 96 px lasen sie sich als Striche unter
    einem Klumpen, nicht als Beine. Der Knick und der Fuss tragen die
    Erkennbarkeit; `far` schiebt das Bein farblich nach hinten.

    foot: hoof (Huf), paw (Tatze), talon (Greifvogel-Fang)
    kick: Versatz des Fusses gegen die Schulter - erzeugt Schrittstellung.
    """
    col = p["mid"] if far else p["main"]
    knee_y = top + (GROUND - top) * 0.50
    out = []
    out.append(poly([
        (x - w * 0.60, top), (x + w * 0.60, top),
        (x + w * 0.42 + kick * 0.5, knee_y),
        (x + w * 0.30 + kick, GROUND - 7),
        (x - w * 0.30 + kick, GROUND - 7),
        (x - w * 0.46 + kick * 0.5, knee_y),
    ], col, p, 2.2))
    fx = x + kick
    if foot == "hoof":
        out.append(poly([(fx - w * 0.38, GROUND - 8), (fx + w * 0.38, GROUND - 8),
                         (fx + w * 0.46, GROUND), (fx - w * 0.46, GROUND)],
                        p["dark"], p, 2.0))
    elif foot == "paw":
        out.append(poly([(fx - w * 0.42, GROUND - 8), (fx + w * 0.62, GROUND - 8),
                         (fx + w * 0.78, GROUND), (fx - w * 0.54, GROUND)],
                        col, p, 2.0))
        for k in range(2):
            out.append(stroke_path("M %.1f %.1f l 3.5 4.5"
                                   % (fx + w * 0.20 + k * 4.0, GROUND - 5),
                                   p["dark"], 1.8))
    else:  # talon
        out.append(poly([(fx - w * 0.30, GROUND - 9), (fx + w * 0.30, GROUND - 9),
                         (fx + w * 0.30, GROUND - 3), (fx - w * 0.30, GROUND - 3)],
                        p["accent"], p, 1.8))
        for k in (-1, 0, 1):
            out.append(stroke_path("M %.1f %.1f q %.1f 4 %.1f 5"
                                   % (fx, GROUND - 4, k * 4.0, k * 7.0),
                                   p["accent"], 2.6))
    return out


def quad_legs(p, body_y, w=8, front=26, back=26, col=None,
              foot_front="hoof", foot_back="hoof"):
    """Vier Beine ums Rumpfmittel. Hinterlaeufe zuerst (liegen hinten)."""
    out = []
    out += animal_leg(p, CX - back + 4, body_y - 2, foot_back, True, w * 0.9, -2.0)
    out += animal_leg(p, CX + front - 4, body_y - 2, foot_front, True, w * 0.9, 2.0)
    out += animal_leg(p, CX - back, body_y, foot_back, False, w, 2.0)
    out += animal_leg(p, CX + front, body_y, foot_front, False, w, -2.0)
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
        # Topfhelm. Vorher ein RECHTECK - und weil der Rumpf von
        # `humanoid broad` auch eines ist und die beiden Schwerter als
        # senkrechte Balken danebenstanden, las sich der Kreuzritter als
        # Kiste mit Tuerrahmen (It. 47, am Kontaktbogen gesehen).
        #
        # Jetzt bricht die Form an drei Stellen: die Kalotte oben ist
        # gerundet, das Kinn laeuft schmal zu, und der Helmbusch ist breit
        # genug, um die Silhouette oben aufzureissen. Ein Helm, der sich
        # vom Rumpf unterscheidet, macht aus zwei Rechtecken eine Figur.
        o.append(path("M %.1f %.1f q 0 -%.1f %.1f -%.1f q %.1f 0 %.1f %.1f "
                      "l -%.1f %.1f l -%.1f 0 Z"
                      % (cx - r, cy + r * 0.15,
                         r * 1.5, r, r * 1.15,
                         r, r, r * 1.15,
                         r * 0.35, r * 0.95,
                         r * 1.3),
                      p["metal"], p))
        # Sehschlitz.
        o.append(stroke_path("M %.1f %.1f L %.1f %.1f" % (cx - r * 0.72, cy,
                                                          cx + r * 0.72, cy), p["line"], 3.5))
        # Helmbusch: breit und nach hinten geneigt, nicht der duenne Dorn
        # von vorher (der verschwand auf dem Token voellig).
        # Hoehe bewusst knapp: der Pruefer am Ende der Datei meldet alles,
        # was aus der 128er-Flaeche laeuft, und der erste Versuch stand mit
        # y -6 darueber. Lieber ein kurzer Busch als ein abgeschnittener.
        o.append(path("M %.1f %.1f q %.1f -%.1f %.1f -%.1f q -%.1f %.1f -%.1f %.1f Z"
                      % (cx - r * 0.4, cy - r * 0.85,
                         r * 0.1, r * 0.4, r * 0.85, r * 0.62,
                         r * 0.18, r * 0.2, r * 0.85, r * 0.34),
                      p["accent"], p, 1.6))
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
    elif kind == "cowl":
        # Kapuze fuer die KEGEL-Silhouette (It. 47). `hood` schwingt
        # bewusst asymmetrisch nach unten aus - auf dem schmalen Koerper
        # des Elfen-Schuetzen und beim Gespenst liest sich das als
        # Umhang. Auf dem breiten Moenchs-Kegel lag derselbe Schwung
        # halb NEBEN dem Koerper und wurde zum Haken: die Figur sah aus
        # wie eine Glocke mit Griff (am Kontaktbogen gesehen).
        #
        # Diese Variante ist symmetrisch und sitzt OBEN AUF: runde
        # Kalotte, gerade Unterkante, dunkles Gesicht in der Mitte. Der
        # Kegel bleibt Kegel, der Kopf wird ein Kopf.
        # EIN Bogen mit dem Kontrollpunkt genau ueber der Mitte - das ist
        # symmetrisch. Der erste Anlauf hat die zwei Boegen von `hood`
        # uebernommen und nur die Zahlen geaendert: der linke stieg auf
        # y 18, der rechte fiel auf y 70, und die "symmetrische" Kapuze
        # sass wieder schief neben dem Kegel. Am Bild gesehen, nicht am
        # Code - im Code sah die Zeile symmetrisch aus.
        # Schmaler als die Schultern und RUND, nicht spitz: mit r Breite
        # und Kontrollpunkt 2,2r hoch war es ein Lampenschirm. Und das
        # Gesicht muss gross genug sein, um als Gesicht durchzugehen -
        # ein dunkler Schlitz reicht nicht.
        o.append(path("M %.1f %.1f q %.1f -%.1f %.1f 0 Z"
                      % (cx - r * 0.82, cy + r * 0.62, r * 0.82, r * 1.5,
                         r * 1.64),
                      p["light"], p))
        o.append(ell(cx, cy + r * 0.12, r * 0.5, r * 0.42, p["line"], p, 0.0))
        # Schulterlinie: trennt Kapuze und Kutte, sonst laufen zwei Flaechen
        # derselben Familie ineinander (bei den Menschen sind `light` und
        # `main` beide gelb).
        o.append(stroke_path("M %.1f %.1f L %.1f %.1f"
                             % (cx - r * 0.8, cy + r * 0.64,
                                cx + r * 0.8, cy + r * 0.64), p["dark"], 3.0))
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
            # HAUER, die den Kopfumriss BRECHEN (It. 48). Vorher endeten
            # sie innerhalb des Kopfes: fast weiss auf hellem Ork-Rosa,
            # und der Orkschuetze hatte auf dem Token ein Smiley-Gesicht.
            # Ein Hauer liest sich nur, wenn er ueber die Silhouette
            # hinausragt.
            o.append(path("M %.1f %.1f q %.1f %.1f %.1f -%.1f"
                          % (cx + s * r * 0.34, cy + r * 0.5,
                             s * r * 0.5, r * 0.55, s * r * 0.95, r * 0.55),
                          "#efe6cf", p, 2.2))
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
        # Schnauze statt Blatt: keilfoermiger Schaedel, Kieferlinie, Auge,
        # zwei nach HINTEN gelegte Hoerner. Die erste Fassung war ein
        # weicher Keil mit zwei Strichen und las sich als Kapuze.
        o.append(poly([(cx - r * 1.15, cy - r * 0.55),
                       (cx + r * 1.35, cy - r * 0.15),
                       (cx + r * 1.45, cy + r * 0.35),
                       (cx - r * 0.30, cy + r * 0.85),
                       (cx - r * 1.05, cy + r * 0.35)], p["light"], p))
        # Kieferlinie
        o.append(stroke_path("M %.1f %.1f L %.1f %.1f"
                             % (cx - r * 0.55, cy + r * 0.30,
                                cx + r * 1.34, cy + r * 0.12), p["line"], 2.2))
        o.append(blob(cx + r * 0.05, cy - r * 0.18, r * 0.2, r * 0.22, p["line"]))
        for k in (0, 1):
            o.append(poly([(cx - r * 0.75 + k * r * 0.34, cy - r * 0.45),
                           (cx - r * 1.35 + k * r * 0.30, cy - r * 1.35),
                           (cx - r * 0.45 + k * r * 0.34, cy - r * 0.55)],
                          p["accent"], p, 1.8))
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
        # GEKREUZT, nicht senkrecht (It. 47). Vorher standen zwei fast
        # senkrechte Klingen links und rechts NEBEN dem Rumpf - zusammen
        # mit dem rechteckigen Torso ergab das einen Tuerrahmen. Und ohne
        # Parierstange fehlte das eine Merkmal, an dem man ein Schwert
        # ueberhaupt erkennt (`sword` und `greatsword` haben sie beide).
        #
        # Jetzt zwei diagonale Klingen, die sich hinter den Schultern
        # kreuzen: das ist die Lesart, die man von einem Kreuzritter
        # erwartet, und sie bricht die Senkrechte des Rumpfes.
        for sgn, x0, x1 in ((1, 44.0, 104.0), (-1, 84.0, 24.0)):
            dx: float = 3.5 * sgn
            o.append(poly([(x0 - dx, 86.0), (x0 + dx, 82.0),
                           (x1 + dx, 16.0), (x1 - dx, 20.0)], p["metal"], p, 2.0))
            # Parierstange quer zur Klinge, nahe am Griff.
            gx: float = x0 + (x1 - x0) * 0.12
            gy: float = 86.0 - 70.0 * 0.12
            o.append(poly([(gx - 9.0 * sgn, gy - 5.0), (gx + 7.0 * sgn, gy - 10.0),
                           (gx + 9.0 * sgn, gy - 2.0), (gx - 7.0 * sgn, gy + 3.0)],
                          p["accent"], p, 1.6))
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
        # Umriss + Holzfarbe, gleiche Begruendung wie bei `longbow` unten:
        # ein reiner p["line"]-Strich ist auf dem dunklen Token unsichtbar,
        # und uebrig bleibt die helle Sehne als senkrechter Balken.
        o.append(path("M 96 26 q 20 32 0 64", None, p, 7.5))
        o.append(stroke_path("M 96 26 q 20 32 0 64", p["wood"], 4.5))
        o.append(stroke_path("M 96 26 L 96 90", "#f2e8c8", 2.0))
        o.append(poly([(96, 58), (74, 55), (74, 61)], p["metal"], p, 1.5))
    elif kind == "longbow":
        # Der Bogen wird ZWEIMAL gezogen: dicker dunkler Umriss, darauf die
        # Holzfarbe. `path(..., None, p, w)` zeichnet nur einen Strich in
        # p["line"] - also dunkel auf dunklem Grund, und genau deshalb war
        # vom Langbogen auf dem Token nur die helle SEHNE zu sehen: ein
        # senkrechter Balken neben der Figur (It. 48). Alles andere im
        # Spritesatz ist umrandet und gefuellt; der Bogen war die Ausnahme.
        o.append(path("M 98 18 q 24 40 0 80", None, p, 7.5))
        o.append(stroke_path("M 98 18 q 24 40 0 80", p["wood"], 4.5))
        # Sehne duenn und ruhig - sie ist nicht das Erkennungsmerkmal.
        o.append(stroke_path("M 98 18 L 98 98", "#f2e8c8", 2.0))
        o.append(stroke_path("M 98 58 L 68 58", p["wood"], 3.0))
        o.append(poly([(70, 58), (60, 54), (60, 62)], p["metal"], p, 1.5))
    elif kind == "crossbow":
        # Vorher: ein 30 px kurzer Stiel plus ein enger Bogen am Ende -
        # auf dem Token ein senkrechter Balken, und der Ork sah aus, als
        # halte er ein Brett (It. 48). Eine Armbrust erkennt man an der
        # T-FORM: langer Schaft quer vor dem Koerper, dazu ein BREITER
        # Bogen quer zum Schaft, und die Sehne dahinter.
        # Unsere Figuren stehen FRONTAL. Ein Bogen, der senkrecht aufspannt,
        # ist von vorn ein Strich - der zweite Versuch las sich als
        # Schwertklinge. Von vorn liest sich eine Armbrust als T: SCHAFT
        # senkrecht, BOGEN breit und quer darueber, Sehne als Gerade
        # dahinter. Genau das steht hier.
        o.append(stroke_path("M 94 34 L 86 96", p["wood"], 6.0))
        o.append(path("M 66 46 q 28 -20 56 0", None, p, 7.5))
        o.append(stroke_path("M 66 46 q 28 -20 56 0", p["wood"], 4.5))
        o.append(stroke_path("M 67 47 L 121 47", "#f2e8c8", 2.2))
        # Buegel am unteren Ende (Steigbuegel der Armbrust).
        o.append(path("M 86 92 q 10 6 0 12", None, p, 3.5))
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
    """Fluegelpaare. It. 30 komplett neu gezeichnet: die alten Formen waren
    glatte Blaetter (feather) bzw. eine Strichreihe (bone) - bei 96 px las
    sich das erste als Fisch und das zweite als Rechen. Jetzt hat jeder
    Fluegel eine NACH HINTEN GESCHWUNGENE Vorderkante und eine gezackte
    bzw. gebogene Hinterkante; das ist die Silhouette, die man als Fluegel
    erkennt.

    WICHTIG: keine festen Minuszeichen in die Formatzeichenkette schreiben.
    Der erste Anlauf hatte "-%.1f" und setzte dort einen bereits mit s
    multiplizierten Wert ein - fuer s=-1 kam "--25.3" heraus, also
    ungueltiges SVG. Alle Verschiebungen tragen ihr Vorzeichen selbst.
    """
    o = []
    if kind == "feather":
        # Drei Federlagen je Seite, nach hinten-oben gestaffelt.
        for s in (-1, 1):
            x0 = CX + s * 10
            for k, (dx, dy, ln) in enumerate((
                    (0.42, -30.0, 0.72), (0.72, -20.0, 0.92), (0.92, -6.0, 1.0))):
                o.append(poly([
                    (x0, cy - 6.0 + k * 5.0),
                    (x0 + s * span * dx, cy + dy),
                    (x0 + s * span * ln, cy + dy + 12.0),
                    (x0 + s * span * (ln - 0.18), cy + dy + 20.0),
                    (x0, cy + 6.0 + k * 5.0),
                ], p["light"] if k < 2 else p["mid"], p, 2.0))
    elif kind == "membrane" or kind == "bone":
        # Drachenfluegel: ECKIGE Silhouette mit drei vorstehenden
        # Fingerspitzen an der Hinterkante. Die erste Fassung hatte eine
        # weiche Bogenkante - in Fraktionsgruen las sie sich als Blatt und
        # in Knochenfarbe als Lappen. Die Zacken sind das Merkmal, an dem
        # ein Fluegel bei 96 px als Drachenfluegel erkannt wird.
        rotten = (kind == "bone")
        for s in (-1, 1):
            x0 = CX + s * 8
            pts = [
                (x0, cy - 4.0),
                (x0 + s * span * 0.46, cy - 28.0),
                (x0 + s * span, cy - 17.0),
                (x0 + s * span * 0.80, cy - 1.0),
                (x0 + s * span * 0.86, cy + 9.0),
                (x0 + s * span * 0.54, cy + 3.0),
                (x0 + s * span * 0.60, cy + 15.0),
                (x0 + s * span * 0.26, cy + 8.0),
                (x0 + s * span * 0.30, cy + drop),
                (x0, cy + 8.0),
            ]
            o.append(poly(pts, p["dark"] if rotten else p["mid"], p, 2.4))
            # Fingerknochen zu den drei Spitzen.
            for k, f in enumerate((0.80, 0.54, 0.26)):
                o.append(stroke_path("M %.1f %.1f L %.1f %.1f"
                                     % (x0 + s * 3.0, cy - 1.0,
                                        x0 + s * span * f,
                                        cy - 1.0 + k * 5.0),
                                     p["bone"] if rotten else p["accent"],
                                     3.0 if rotten else 2.2))
            if rotten:
                for k in range(2):
                    o.append(blob(x0 + s * span * (0.40 + k * 0.20),
                                  cy + 1.0 + k * 5.0, 3.6, 2.8, p["line"]))
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
    elif kind == "dragon_membrane" or kind == "dragon_bone":
        # PROFIL-Fluegel fuer den Drachenkoerper. Zwei Dinge waren vorher
        # falsch: das Paar stand symmetrisch nach beiden Seiten ab (Huhn),
        # und die Zackenkante lag hinter dem Rumpf, war also unsichtbar.
        # Jetzt liegt der ganze Fluegel OBERHALB der Rueckenlinie und
        # schwingt nach hinten-oben; nur so ist die Kante zu sehen.
        rotten = (kind == "dragon_bone")
        ax, ay = CX + 2.0, cy          # Schulteransatz
        for far in (True, False):
            f = 0.62 if far else 1.0
            ox, oy = (9.0, 5.0) if far else (0.0, 0.0)
            # Beim Knochendrachen ist der Koerper HELL - eine hellgraue
            # Membran verschwand darin. Der nahe Fluegel ist deshalb dunkel
            # mit knochenfarbenen Fingern, der ferne fast schwarz.
            if rotten:
                fill = p["line"] if far else p["dark"]
            else:
                fill = p["dark"] if far else p["light"]
            sx, sy = ax + ox, ay + oy
            pts = [
                (sx, sy),
                (sx - span * 0.30 * f, sy - 26.0 * f),      # Vorderkante
                (sx - span * 0.86 * f, sy - 30.0 * f),      # Fluegelspitze
                (sx - span * 0.66 * f, sy - 16.0 * f),      # Zacke 1 Kerbe
                (sx - span * 0.70 * f, sy - 6.0 * f),       # Zacke 1 Spitze
                (sx - span * 0.44 * f, sy - 12.0 * f),      # Zacke 2 Kerbe
                (sx - span * 0.46 * f, sy - 2.0 * f),       # Zacke 2 Spitze
                (sx - span * 0.20 * f, sy - 8.0 * f),       # Zacke 3 Kerbe
                (sx - span * 0.20 * f, sy + 2.0 * f),       # Zacke 3 Spitze
            ]
            o.append(poly(pts, fill, p, 2.4))
            if not far:
                for k, fr in enumerate((0.66, 0.44, 0.20)):
                    o.append(stroke_path("M %.1f %.1f L %.1f %.1f"
                                         % (sx - 2.0, sy - 2.0,
                                            sx - span * fr, sy - 14.0 + k * 4.0),
                                         p["bone"] if rotten else p["dark"],
                                         3.0 if rotten else 2.2))
                if rotten:
                    for k in range(2):
                        o.append(blob(sx - span * (0.34 + k * 0.18),
                                      sy - 14.0 + k * 5.0, 3.4, 2.6, p["line"]))
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
    # NICHT beim Gebeugten - dort las sie sich als Schuerze.
    if build != "hunched":
        o.append(poly([(CX - sh * 0.45, top + 4), (CX + sh * 0.45, top + 4),
                       (CX + wa * 0.5, GROUND - 40), (CX - wa * 0.5, GROUND - 40)],
                      p["light"], p, 1.8))
    else:
        o.append(blob(CX, GROUND - 46.0, sh * 0.5, 10.0, p["dark"]))
    # VERSUCHT UND VERWORFEN (It. 32): Schulterstuecke (Pauldrons) am
    # breiten Rumpf. Sie standen als freischwebende Platten neben dem
    # Torso und machten den Kreuzritter zum Roboter mit erhobenen Armen -
    # schlechter als der Kasten, den sie beheben sollten. Wer es erneut
    # versucht, muss sie mit dem Rumpf-Polygon VERSCHMELZEN, nicht
    # daneben legen.
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
    """Massige, vorgebeugte Gestalt: Schultern hoeher als der Kopf, zwei
    Arme (einer bis zum Boden), kurze dicke Beine. Vorher war es ein
    Trapez mit einem Strich als Arm - kaum von `humanoid broad` zu
    unterscheiden."""
    o = []
    o += legs(p, GROUND - 24, w=17, spread=18)
    # Rumpf: unten schmaler, oben ausgestellt (Schultern).
    o.append(path("M %.1f 44 Q %.1f 36 %.1f 44 L %.1f %.1f Q %.1f %.1f %.1f %.1f Z"
                  % (CX - 34.0, CX, CX + 34.0,
                     CX + 21.0, GROUND - 22.0,
                     CX, GROUND - 16.0, CX - 21.0, GROUND - 22.0),
                  p["main"], p))
    # Bauchpartie hell - sonst ist der Rumpf eine Volltonflaeche.
    o.append(blob(CX, GROUND - 44.0, 17.0, 15.0, p["light"]))
    # Langer Arm links bis fast zum Boden, kurzer Arm rechts.
    o.append(poly([(CX - 30.0, 46.0), (CX - 18.0, 48.0),
                   (CX - 22.0, GROUND - 18.0), (CX - 34.0, GROUND - 20.0)],
                  p["mid"], p, 2.2))
    o.append(ell(CX - 28.0, GROUND - 16.0, 8.0, 7.0, p["mid"], p, 2.2))
    o.append(poly([(CX + 20.0, 48.0), (CX + 32.0, 46.0),
                   (CX + 30.0, 74.0), (CX + 20.0, 72.0)], p["mid"], p, 2.2))
    # Schulterhoecker: der Kopf sitzt dazwischen und wirkt dadurch klein.
    for s in (-1, 1):
        o.append(ell(CX + s * 27.0, 44.0, 11.0, 9.0, p["light"], p, 2.2))
    return o, 30.0


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
    """Kein Beinpaar - der Umriss laeuft unten in ZERFETZTE Zipfel aus.
    Vorher war es eine glatte Tropfenform, also ein weisser Klumpen ohne
    Merkmal. Der gezackte Saum und die schmalen Schultern machen den
    Unterschied zum Moench (robed) und zum Zombie."""
    o = []
    hem = GROUND - 2.0
    pts = [(CX - 14.0, 48.0), (CX + 14.0, 48.0), (CX + 26.0, 80.0)]
    # Fuenf Zipfel, tief eingeschnitten - erst ab dieser Tiefe liest der
    # Saum bei 96 px als zerfetzt und nicht als Wellenlinie.
    for k, dy in enumerate((0.0, 22.0, 6.0, 26.0, 2.0)):
        x = CX + 21.0 - k * 10.5
        pts.append((x, hem - dy))
        pts.append((x - 5.5, hem - dy - 22.0))
    pts.append((CX - 26.0, 80.0))
    o.append(poly(pts, p["mid"], p))
    # Klauenarme, weit ausgestellt - macht die Silhouette breit statt rund.
    for s in (-1, 1):
        o.append(poly([(CX + s * 11.0, 54.0), (CX + s * 30.0, 66.0),
                       (CX + s * 24.0, 74.0), (CX + s * 8.0, 66.0)],
                      p["main"], p, 2.0))
        for k in (-1, 1):
            o.append(stroke_path("M %.1f 68 l %.1f 8"
                                 % (CX + s * 27.0, k * 4.0), p["light"], 2.2))
    return o, 36.0


# Der Rumpf der Tiere liegt links von der Mitte, damit Hals und Kopf nach
# rechts Platz haben, ohne aus der 128er ViewBox zu laufen.
BX = CX - 8.0


def _body_path(top, bottom, back_x, front_x, croup=6.0, top_front=None):
    """Rumpf als gefuellter Pfad statt Ellipse. Eine Ellipse ist vorn und
    hinten gleich - genau daran lasen sich Greif, Pegasus, Einhorn und
    Behemoth als derselbe Klumpen. Hier ist die BRUST tiefer als die
    Kruppe, und die Ruecken-/Bauchlinie ist gebogen."""
    tf = top if top_front is None else top_front
    return ("M %.1f %.1f Q %.1f %.1f %.1f %.1f L %.1f %.1f "
            "Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f "
            "L %.1f %.1f Q %.1f %.1f %.1f %.1f Z"
            % (back_x, (top + bottom) * 0.5,
               back_x - 2.0, top + croup, back_x + 14.0, top + croup * 0.4,
               front_x - 14.0, tf,
               front_x + 3.0, tf, front_x + 5.0, tf + (bottom - tf) * 0.45,
               front_x + 6.0, bottom - 2.0, front_x - 12.0, bottom,
               back_x + 16.0, bottom,
               back_x - 1.0, bottom - 1.0, back_x, (top + bottom) * 0.5))


def _neck(p, from_xy, to_xy, w_bottom, w_top):
    """Gefuellter, sich verjuengender Hals. Vorher war es ein Strich mit
    konstanter Breite - der Kopf sass dadurch wie angeklebt."""
    x0, y0 = from_xy
    x1, y1 = to_xy
    return poly([(x0 - w_bottom * 0.5, y0), (x0 + w_bottom * 0.5, y0 + 2.0),
                 (x1 + w_top * 0.5, y1 + 4.0), (x1 - w_top * 0.5, y1)],
                p["main"], p, 2.2)


def sil_quadruped(p, kind="horse"):
    """Vierbeiner. Drei deutlich verschiedene Bauarten:
      horse  - schlank, langer Hals, Hufe, Schweif (Pegasus, Einhorn)
      lion   - tiefe Brust, Greifvogel-Faenge vorn, Tatzen hinten (Greif)
      heavy  - massig, kurzer Hals, Kopf tief vorn (Behemoth)
    """
    o = []
    if kind == "heavy":
        # Bison-Umriss: der Ruecken faellt nach hinten ab, die Schulter ist
        # der hoechste Punkt und der Kopf sitzt TIEF davor. Der erste
        # Anlauf hatte einen waagerechten Ruecken und einen grossen runden
        # Kopf oben vorn - das las sich als Schwein mit Ball.
        top, bottom, back_x, front_x = 66.0, 94.0, BX - 32.0, BX + 28.0
        top_front = 50.0
        o += quad_legs(p, bottom - 2, w=15, front=22, back=26,
                       foot_front="paw", foot_back="paw")
        neck_from = (BX + 22.0, 58.0)
        head_xy = (BX + 40.0, 72.0)
        nw = (26.0, 20.0)
    elif kind == "lion":
        top, bottom, back_x, front_x = 62.0, 90.0, BX - 30.0, BX + 28.0
        top_front = None
        o += quad_legs(p, bottom - 2, w=11, front=22, back=24,
                       foot_front="talon", foot_back="paw")
        neck_from = (BX + 22.0, 66.0)
        head_xy = (BX + 40.0, 42.0)
        nw = (20.0, 15.0)
    else:
        top, bottom, back_x, front_x = 64.0, 90.0, BX - 30.0, BX + 26.0
        top_front = None
        o += quad_legs(p, bottom - 2, w=10, front=21, back=23,
                       foot_front="hoof", foot_back="hoof")
        neck_from = (BX + 20.0, 68.0)
        head_xy = (BX + 40.0, 38.0)
        nw = (17.0, 13.0)

    # Schweif ZUERST (liegt hinter dem Rumpf).
    if kind == "horse":
        o.append(stroke_path("M %.1f %.1f q %.1f 14 %.1f 26"
                             % (back_x + 3.0, top + 4.0, -14.0, -12.0),
                             p["accent"], 7.0))
    elif kind == "lion":
        o.append(stroke_path("M %.1f %.1f q %.1f -12 %.1f 6"
                             % (back_x + 3.0, top + 8.0, -18.0, -24.0),
                             p["main"], 6.0))
        o.append(ell(back_x - 21.0, top + 14.0, 6.0, 6.0, p["accent"], p, 2.0))
    else:
        o.append(poly([(back_x + 4.0, top + 6.0), (back_x - 22.0, top + 2.0),
                       (back_x - 20.0, top + 14.0), (back_x + 4.0, top + 18.0)],
                      p["mid"], p, 2.2))

    o.append(path(_body_path(top, bottom, back_x, front_x, top_front=top_front),
                  p["main"], p))
    # Keule hinten und Schulter vorn OHNE Kontur: Volumen ohne zusaetzliche
    # Linien, die bei 96 px als Kritzel lesen.
    o.append(blob(back_x + 15.0, (top + bottom) * 0.5 + 1.0,
                  13.0, (bottom - top) * 0.42, p["mid"]))
    o.append(blob(front_x - 13.0, (top + bottom) * 0.5,
                  12.0, (bottom - top) * 0.40, p["light"]))
    o.append(_neck(p, neck_from, head_xy, nw[0], nw[1]))
    if kind == "heavy":
        # Kamm entlang der Rueckenlinie, hinten kurz, vorn lang - er
        # betont das Gefaelle statt es zu ueberdecken.
        for k in range(5):
            bx = BX - 20.0 + k * 11.0
            by = top - (top - top_front) * (k / 4.0) + 2.0
            hl = 5.0 + k * 2.5
            o.append(poly([(bx, by), (bx + 5.0, by - hl), (bx + 10.0, by)],
                          p["light"], p, 1.8))
    return o, head_xy


def sil_mounted(p, mount="horse"):
    """Reittier plus Reiter. Der Reiter sitzt jetzt IM Sattel: Bein am
    Rumpf, Torso darueber, Arm nach vorn. Vorher war es ein schwebendes
    Rechteck auf dem Ruecken."""
    o, headpos = sil_quadruped(p, "horse" if mount == "horse" else "lion")
    if mount == "wolf":
        # Nackenmaehne statt Hufe: der Wolf soll kein Pferd sein.
        for k in range(4):
            o.append(poly([(BX + 12.0 + k * 5.0, 62.0),
                           (BX + 16.0 + k * 5.0, 48.0),
                           (BX + 20.0 + k * 5.0, 62.0)], p["dark"], p, 1.8))
    # Reiterbein am Rumpf (dunkel, liegt auf dem Tier).
    o.append(poly([(BX - 6.0, 60.0), (BX + 6.0, 60.0),
                   (BX + 4.0, 84.0), (BX - 4.0, 84.0)], p["dark"], p, 2.0))
    # Torso
    o.append(poly([(BX - 12.0, 34.0), (BX + 10.0, 36.0),
                   (BX + 7.0, 62.0), (BX - 8.0, 62.0)], p["accent"], p))
    # Arm nach vorn - haelt die Lanze bzw. den Speer.
    o.append(stroke_path("M %.1f 44 L %.1f 52" % (BX + 6.0, BX + 24.0),
                         p["accent"], 7.0))
    return o, headpos, (BX - 3.0, 24.0)


def sil_bird(p):
    """Greifvogel im Anflug: gestreckter, nach vorn geneigter Rumpf,
    Schwanzfedern nach HINTEN OBEN, Faenge nach vorn, Kopf tief und
    vorgestreckt.

    Vorher war es ein aufrechter Vogel mit fast rundem Rumpf, Federn nach
    unten und Fluegeln in Rumpfhoehe - am Kontaktbogen ein TRUTHAHN
    (It. 48). Die drei Aenderungen, die daraus einen Raubvogel machen:
    Rumpf breiter als hoch, Schwanz nach oben statt nach unten, und die
    Fluegel setzen ueber der Rumpfmitte an (Datenfeld `wing`, deshalb dort
    geaendert). `bird` hat genau EINEN Nutzer (ork_roc), das war ohne
    Nebenwirkung moeglich.
    """
    o = []
    # Schwanzfedern hinter dem Rumpf, nach hinten OBEN gefaechert.
    # Schwanz WAAGERECHT nach hinten, nicht nach oben: nach oben
    # gefaechert kam er mit den (jetzt erhobenen) Fluegeln ins Gehege -
    # zwei helle Faecher links oben, die um dieselbe Lesart konkurrierten.
    # Nach UNTEN war es der Truthahn. Waagerecht ist beides nicht.
    for k in (-1, 0, 1):
        o.append(poly([(BX - 8.0, 60.0 + k * 2.0),
                       (BX - 40.0, 60.0 + k * 8.0),
                       (BX - 8.0, 68.0 + k * 2.0)], p["mid"], p, 2.0))
    o += animal_leg(p, BX + 6.0, 74.0, "talon", True, 9.0, -5.0)
    o += animal_leg(p, BX + 19.0, 76.0, "talon", False, 10.0, 4.0)
    # Rumpf: breiter als hoch und nach vorn gekippt.
    o.append(ell(BX + 8.0, 62.0, 25.0, 18.0, p["main"], p))
    o.append(blob(BX + 15.0, 66.0, 13.0, 11.0, p["light"]))
    # Kurzer, VORGESTRECKTER Hals - nicht der aufgerichtete Truthahnhals.
    o.append(_neck(p, (BX + 18.0, 52.0), (BX + 32.0, 42.0), 14.0, 11.0))
    return o, (BX + 34.0, 38.0)


# Mittellinie des Drachenkoerpers: Schweifspitze unten links, Rumpf in der
# Mitte, Hals steigt nach rechts oben. Die Breiten gehoeren dazu.
DRAGON_SPINE = [
    (BX - 50.0, GROUND - 4.0), (BX - 39.0, GROUND - 9.0), (BX - 28.0, 93.0),
    (BX - 16.0, 87.0), (BX - 4.0, 81.0), (BX + 8.0, 75.0),
    (BX + 18.0, 65.0), (BX + 25.0, 51.0), (BX + 30.0, 39.0), (BX + 34.0, 31.0),
]
DRAGON_WIDTH = [3.0, 8.0, 15.0, 23.0, 28.0, 28.0, 22.0, 15.0, 12.0, 11.0]


def sil_dragon(p):
    """Drache im Profil, Kopf oben rechts. Der Koerper ist EIN gerechneter
    Umriss (tapered) von der Schweifspitze bis zum Halsansatz.

    Vier Anlaeufe vorher, jedes Mal wurde ein Vogel daraus:
      1. Ellipse mit zwei Striemen                       -> Ente
      2. runder Rumpf + symmetrisches Fluegelpaar        -> Huhn
      3. handgesetzter Umriss von Schweif bis Kopf       -> diagonaler
         Streifen (Rumpf zwischen den Kanten zu duenn)
      4. getrennte Massen Schweif/Rumpf/Hals             -> Teile sichtbar
         aneinandergeklebt
    Der Unterschied jetzt: keine Naht mehr, weil es nur einen Koerper gibt,
    und der Schweif liegt lang am Boden.
    """
    o = []
    o += animal_leg(p, BX - 8.0, 82.0, "talon", True, 11.0, -4.0)
    o.append(tapered(DRAGON_SPINE, DRAGON_WIDTH, p["main"], p))
    # Bauchseite heller: gibt dem Koerper Rundung ohne zweite Kontur.
    belly = [(x, y + 6.0) for x, y in DRAGON_SPINE[2:6]]
    o.append(tapered(belly, [10.0, 13.0, 13.0, 10.0], p["light"], p, 0.0))
    o += animal_leg(p, BX + 9.0, 84.0, "talon", False, 12.0, 3.0)
    o += spine_spikes(DRAGON_SPINE, [3, 4, 5, 6, 7, 8], p, DRAGON_WIDTH,
                      base=5.0, grow=0.6)
    return o, (BX + 38.0, 26.0)


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
                           wing=("feather", 42, 66)),
    "men_crusader":   dict(sil=("humanoid", "broad"),  head="helm_great",   wpn="twin_swords"),
    "men_monk":       dict(sil=("robed", None),        head="cowl",         wpn="staff"),
    "men_cavalier":   dict(sil=("mounted", "horse"),   head="helm_conical", wpn="lance"),
    "men_angel":      dict(sil=("humanoid", "broad"),  head="halo",         wpn="sword",
                           wing=("feather", 47, 44)),
    # --- Waldvolk
    "elf_dwarf":      dict(sil=("squat", None),        head="beard",        wpn="axe"),
    "elf_archer":     dict(sil=("humanoid", "slim"),   head="hood",         wpn="longbow"),
    "elf_pegasus":    dict(sil=("quadruped", "horse"), head="mane",         wpn="none",
                           wing=("feather", 40, 66)),
    "elf_treant":     dict(sil=("tree", False),        head="bare",         wpn="branch"),
    "elf_unicorn":    dict(sil=("quadruped", "horse"), head="horn_single",  wpn="none"),
    "elf_treefather": dict(sil=("tree", True),         head="crown_leaf",   wpn="branch"),
    "elf_goldwyrm":   dict(sil=("dragon", None),       head="draconic",     wpn="none",
                           wing=("dragon_membrane", 52, 58)),
    # --- Totenreich
    "nec_skeleton":   dict(sil=("skeletal", None),     head="skull",        wpn="sword"),
    "nec_zombie":     dict(sil=("humanoid", "hunched"), head="rotten",      wpn="none"),
    "nec_wight":      dict(sil=("spectre", None),      head="hood",         wpn="claws"),
    "nec_vampire":    dict(sil=("humanoid", "slim"),   head="fanged",       wpn="claws",
                           wing=("bat", 45, 38)),
    "nec_lich":       dict(sil=("robed", None),        head="skull_glow",   wpn="staff_orb"),
    "nec_blackknight": dict(sil=("humanoid", "broad"), head="helm_horned",  wpn="greatsword"),
    "nec_bonedragon": dict(sil=("dragon", None),       head="skull",        wpn="none",
                           wing=("dragon_bone", 52, 58)),
    # --- Orks
    "ork_goblin":     dict(sil=("squat", None),        head="eared",        wpn="dagger"),
    "ork_wolfrider":  dict(sil=("mounted", "wolf"),    head="tusked",       wpn="spear"),
    "ork_orc":        dict(sil=("humanoid", "broad"),  head="tusked",       wpn="crossbow"),
    "ork_ogre":       dict(sil=("brute", None),        head="small",        wpn="club"),
    "ork_roc":        dict(sil=("bird", None),         head="beak",         wpn="none",
                           # Ansatz UEBER der Rumpfmitte: in Rumpfhoehe
                           # faecherten die Fluegel wie beim Haushuhn.
                           wing=("feather", 46, 44)),
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
        # 20 statt 17 (It. 47): auf dem KEGEL sitzt der Kopf ueber einer
        # sehr breiten Flaeche, und mit 17 war er auf dem Token nur noch
        # ein Nubbel - die Figur las sich als Glocke. Am Kontaktbogen in
        # Token-Groesse entschieden, nicht in der Vergroesserung.
        head_at = (CX, hy, 20.0)
    elif kind == "skeletal":
        body, hy = sil_skeletal(p)
        head_at = (CX, hy, 16.0)
    elif kind == "spectre":
        body, hy = sil_spectre(p)
        head_at = (CX, hy, 17.0)
    elif kind == "bird":
        body, hp = sil_bird(p)
        head_at = (hp[0], hp[1], 15.0)
    elif kind == "tree":
        body, hy = sil_tree(p, arg)
        head_at = (CX, hy, 19.0 if arg else 15.0)
    elif kind == "quadruped":
        body, hp = sil_quadruped(p, arg)
        head_at = (hp[0], hp[1], 14.0 if arg == "heavy" else 16.0)
    elif kind == "dragon":
        body, hp = sil_dragon(p)
        head_at = (hp[0], hp[1], 12.0)
    elif kind == "mounted":
        body, hp, rp = sil_mounted(p, arg)
        head_at = (hp[0], hp[1], 12.0)
        rider_head = (rp[0], rp[1], 13.0)
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
    # It. 30: kleiner und ohne Kontur. Vorher waren es sieben weisse
    # Scheiben mit dunklem Rand direkt unter der Figur - bei 96 px zog die
    # Punktreihe mehr Aufmerksamkeit als die Kreatur darueber.
    out = []
    total_w = (tier - 1) * 9.0
    x0 = CX - total_w / 2.0
    for i in range(tier):
        out.append('  <circle cx="%.1f" cy="%.1f" r="2.6" fill="%s" '
                   'opacity="0.75"/>' % (x0 + i * 9.0, GROUND + 8.0, p["light"]))
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
