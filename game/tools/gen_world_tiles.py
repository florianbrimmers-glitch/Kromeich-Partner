#!/usr/bin/env python3
"""Erzeugt das Weltkarten-Tileset als SVG.

    python3 tools/gen_world_tiles.py

Schreibt nach assets/world/terrain/:
  <gelaende>_0..3.svg   je Gelaendeart VIER Varianten
  fringe_<seite>.svg    weiche Uebergangs-Franse (weiss, wird eingefaerbt)
  fog_0..3.svg          unerforschter Nebel, gemustert statt schwarz

NICHT von Hand editieren - hier aendern und neu laufen lassen.

WARUM VARIANTEN: vorher lag je Gelaendeart EINE Kachel. grass.svg hatte
seine Bluete auf Pixel (52,20) - also stand auf jeder Wiese der Karte
dieselbe Bluete an derselben Stelle. Auf dem Geraet las sich das als
Tapetenmuster, nicht als Landschaft. Der WorldMapScreen waehlt die Variante
deterministisch aus Feldkoordinate und Karten-Seed, damit dieselbe Karte
immer gleich aussieht (Save/Load, Screenshots).

WARUM FRANSEN: Gelaendearten stiessen mit kerzengeraden Kanten aneinander -
ein Schachbrett aus Farbfeldern. Die Franse laesst das NACHBAR-Material in
die Kachel hineinlaufen; sie ist weiss und wird beim Zeichnen mit der Farbe
des Nachbarn moduliert, deshalb genuegen vier Dateien fuer alle
Kombinationen.

Kacheln muessen SEITLICH KACHELN: am Rand gleiche Farbe, keine Form, die
ueber die Kante laeuft.
"""
import math
import os
import random

T = 64  # Kachelgroesse
VARIANTS = 6  # 4 waren bei ~30 Kacheln im Blick noch als Muster erkennbar
OUT = os.path.join("assets", "world", "terrain")


def head(comment):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!-- %s\n     Erzeugt von tools/gen_world_tiles.py. -->\n'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'width="%d" height="%d">\n' % (comment, T, T, T, T))


def mix(c0, c1, f=0.5):
    a = [int(c0[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def base(c0, c1):
    """FLACHE Grundfarbe, kein Verlauf.

    Erster Versuch hatte je Kachel einen senkrechten Verlauf hell->dunkel.
    Im Feld ergab das Querstreifen alle 64 px, weil ein Verlauf nicht
    kacheln kann. Tiefe kommt jetzt allein aus der Deko."""
    return '  <rect width="%d" height="%d" fill="%s"/>\n' % (T, T, mix(c0, c1, 0.45))


# --- Deko-Bausteine ------------------------------------------------------
# Alle halten Abstand zum Rand (INSET), damit die Kacheln seitlich passen.
INSET = 9


def spot(rng, col, r0=6, r1=11, op=(0.35, 0.6)):
    x = rng.uniform(INSET, T - INSET)
    y = rng.uniform(INSET, T - INSET)
    r = rng.uniform(r0, r1)
    return ('  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s" '
            'opacity="%.2f"/>\n' % (x, y, r, r * 0.42, col,
                                    rng.uniform(*op)))


def tuft(rng, col):
    x = rng.uniform(INSET, T - INSET)
    y = rng.uniform(INSET + 4, T - INSET)
    out = '  <g stroke="%s" stroke-width="1.3" stroke-linecap="round" opacity="0.75">\n' % col
    for k in range(3):
        out += ('    <line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>\n'
                % (x + k * 2.0, y, x + k * 2.0 + rng.uniform(-1.5, 2.0), y - rng.uniform(3.5, 5.5)))
    return out + '  </g>\n'


def flower(rng, petal, heart):
    x = rng.uniform(INSET + 3, T - INSET - 3)
    y = rng.uniform(INSET + 3, T - INSET - 3)
    out = ""
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        out += ('  <circle cx="%.1f" cy="%.1f" r="1.2" fill="%s"/>\n'
                % (x + dx, y + dy, petal))
    return out + '  <circle cx="%.1f" cy="%.1f" r="0.9" fill="%s"/>\n' % (x, y, heart)


def crown(rng, dark, mid, light, r0=7, r1=11):
    """Baumkrone mit Schatten - Wald."""
    x = rng.uniform(INSET + 2, T - INSET - 2)
    y = rng.uniform(INSET + 2, T - INSET - 2)
    r = rng.uniform(r0, r1)
    return ('  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s" opacity="0.7"/>\n'
            '  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s"/>\n'
            '  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s" opacity="0.8"/>\n'
            % (x + 1.6, y + 1.8, r, r * 0.86, dark,
               x, y, r, r * 0.86, mid,
               x - r * 0.3, y - r * 0.32, r * 0.42, r * 0.34, light))


def wave(rng, col):
    y = rng.uniform(INSET, T - INSET)
    w = rng.uniform(14, 24)
    x = rng.uniform(4, T - w - 4)
    return ('  <path d="M %.1f %.1f q %.1f -3.5 %.1f 0 q %.1f 3.5 %.1f 0" fill="none" '
            'stroke="%s" stroke-width="1.8" stroke-linecap="round" opacity="%.2f"/>\n'
            % (x, y, w * 0.25, w * 0.5, w * 0.25, w * 0.5, col, rng.uniform(0.35, 0.6)))


def rock(rng, dark, mid, light):
    x = rng.uniform(INSET + 3, T - INSET - 3)
    y = rng.uniform(INSET + 5, T - INSET)
    w = rng.uniform(9, 15)
    h = rng.uniform(9, 16)
    return ('  <polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="%s"/>\n'
            '  <polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="%s"/>\n'
            '  <polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="%s" opacity="0.85"/>\n'
            % (x - w * 0.5, y, x, y - h, x + w * 0.5, y, dark,
               x - w * 0.5, y, x, y - h, x + w * 0.12, y, mid,
               x - w * 0.5, y, x - w * 0.16, y - h * 0.72, x - w * 0.05, y, light))


def dune(rng, col):
    y = rng.uniform(INSET, T - INSET)
    w = rng.uniform(18, 30)
    x = rng.uniform(3, T - w - 3)
    return ('  <path d="M %.1f %.1f q %.1f -4.5 %.1f 0" fill="none" stroke="%s" '
            'stroke-width="1.6" stroke-linecap="round" opacity="%.2f"/>\n'
            % (x, y, w * 0.5, w, col, rng.uniform(0.30, 0.5)))


def bubble(rng, col):
    x = rng.uniform(INSET, T - INSET)
    y = rng.uniform(INSET, T - INSET)
    r = rng.uniform(1.6, 3.4)
    return ('  <circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s" '
            'stroke-width="1.2" opacity="%.2f"/>\n' % (x, y, r, col, rng.uniform(0.4, 0.7)))


# --- Gelaende-Rezepte ----------------------------------------------------

TERRAIN = {
    "grass": dict(c0="#5a8c3a", c1="#3e6c20", seed=11, deco=[
        (spot, dict(col="#6e9a48"), 2),
        (tuft, dict(col="#7eac56"), 3),
        (flower, dict(petal="#f0d048", heart="#c93a2c"), 1),
    ]),
    "forest": dict(c0="#3d6b2c", c1="#264a18", seed=22, deco=[
        (spot, dict(col="#335c22"), 1),
        (crown, dict(dark="#1b3117", mid="#2c5223", light="#487a33"), 3),
        (tuft, dict(col="#4e7f3a"), 1),
    ]),
    "water": dict(c0="#2f6f95", c1="#1d4d6e", seed=33, deco=[
        (spot, dict(col="#3f83aa", r0=9, r1=16, op=(0.25, 0.4)), 2),
        (wave, dict(col="#8fd0e8"), 3),
        (bubble, dict(col="#bfe6f5"), 1),
    ]),
    "mountain": dict(c0="#6f6a63", c1="#4a4640", seed=44, deco=[
        (spot, dict(col="#7c766e", op=(0.25, 0.4)), 1),
        (rock, dict(dark="#3a3630", mid="#6b655d", light="#928b81"), 3),
    ]),
    "sand": dict(c0="#d8bd84", c1="#b89a60", seed=55, deco=[
        (spot, dict(col="#e3cb9a", op=(0.25, 0.45)), 2),
        (dune, dict(col="#a8894f"), 3),
    ]),
    "swamp": dict(c0="#4a5b34", c1="#333f22", seed=66, deco=[
        (spot, dict(col="#3c4f2a", r0=8, r1=14, op=(0.4, 0.6)), 2),
        (bubble, dict(col="#8fae62"), 3),
        (tuft, dict(col="#6b8442"), 2),
    ]),
}


def terrain_tile(name, variant):
    cfg = TERRAIN[name]
    rng = random.Random(cfg["seed"] * 100 + variant)
    out = head("Gelaende %s, Variante %d von %d" % (name, variant, VARIANTS))
    out += base(cfg["c0"], cfg["c1"])
    for fn, kw, n in cfg["deco"]:
        for _ in range(n):
            out += fn(rng, **kw)
    return out + "</svg>\n"


# --- Uebergangs-Fransen --------------------------------------------------

def fringe(side):
    """Weiche Zunge entlang EINER Kante, weiss. Der Screen faerbt sie mit
    der Farbe des Nachbarfeldes ein - so decken vier Dateien alle
    Gelaende-Kombinationen ab.

    Zwei Lagen: eine tiefe mit wenig Deckkraft, eine flache mit mehr.
    Das ergibt den Verlauf ohne SVG-Maske (die Godot-Rasterisierung mit
    Masken ist nicht verlaesslich)."""
    rng = random.Random(hash(side) & 0xFFFF)
    out = head("Uebergangs-Franse %s (weiss, wird eingefaerbt)" % side)

    def band(depth, op, wobble, steps=8):
        pts = []
        for i in range(steps + 1):
            f = i / steps
            d = depth * (0.55 + 0.45 * math.sin(f * math.pi * 2.4 + wobble))
            pts.append((f * T, d))
        # Randpunkte auf 0 ziehen, damit benachbarte Kacheln zusammenpassen.
        pts[0] = (0.0, depth * 0.5)
        pts[-1] = (float(T), depth * 0.5)
        d_attr = "M 0 0 " + " ".join("L %.1f %.1f" % p for p in pts) + " L %d 0 Z" % T
        return '  <path d="%s" fill="#ffffff" opacity="%.2f"/>\n' % (d_attr, op)

    # Flach halten: mit 22 px Tiefe und hoher Deckkraft ergab sich an jeder
    # Gelaendegrenze ein breiter Farbschleier, die Karte wirkte verwaschen.
    body = band(15.0, 0.30, 0.0) + band(7.0, 0.52, 1.7)
    rot = {"top": 0, "right": 90, "bottom": 180, "left": 270}[side]
    if rot:
        out += '  <g transform="rotate(%d %d %d)">\n%s  </g>\n' % (rot, T // 2, T // 2, body)
    else:
        out += body
    return out + "</svg>\n"


# --- Kriegsnebel ---------------------------------------------------------

def fog_tile(variant):
    """Unerforscht. Vorher war das eine Volltonflaeche (0.04,0.04,0.06) mit
    Gitterlinien darauf - auf dem Geraet ein schwarzes Loch mit Raster.
    Jetzt gewolkt, damit es als Nebel liest."""
    rng = random.Random(900 + variant)
    out = head("Kriegsnebel, Variante %d" % variant)
    out += base("#14161f", "#0b0c12")
    for _ in range(3):
        x = rng.uniform(INSET + 4, T - INSET - 4)
        y = rng.uniform(INSET + 4, T - INSET - 4)
        r = rng.uniform(9, 15)
        out += ('  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="#242836" '
                'opacity="%.2f"/>\n' % (x, y, r, r * 0.62, rng.uniform(0.30, 0.5)))
    for _ in range(2):
        out += ('  <circle cx="%.1f" cy="%.1f" r="%.1f" fill="#30354a" opacity="%.2f"/>\n'
                % (rng.uniform(INSET, T - INSET), rng.uniform(INSET, T - INSET),
                   rng.uniform(3, 6), rng.uniform(0.14, 0.26)))
    return out + "</svg>\n"


def main():
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for name in TERRAIN:
        for v in range(VARIANTS):
            with open(os.path.join(OUT, "%s_%d.svg" % (name, v)), "w") as f:
                f.write(terrain_tile(name, v))
            n += 1
        print("[OK] %-9s %d Varianten" % (name, VARIANTS))
    for side in ("top", "right", "bottom", "left"):
        with open(os.path.join(OUT, "fringe_%s.svg" % side), "w") as f:
            f.write(fringe(side))
        n += 1
    print("[OK] %-9s 4 Seiten" % "fringe")
    for v in range(VARIANTS):
        with open(os.path.join(OUT, "fog_%d.svg" % v), "w") as f:
            f.write(fog_tile(v))
        n += 1
    print("[OK] %-9s %d Varianten" % ("fog", VARIANTS))
    print("%d Kacheln geschrieben." % n)


if __name__ == "__main__":
    main()
