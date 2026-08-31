#!/usr/bin/env python3
"""Erzeugt die Sprites der Bonus-Karten-Objekte (M5) als SVG.

    python3 tools/gen_map_objects.py

Schreibt assets/world/objects/<art>.svg. NICHT von Hand editieren.

Die drei alten Objekte (chest, mine, pile) sind handgeschriebene SVGs und
bleiben, wie sie sind - sie wurden bei 64 px geprueft und sind klar
lesbar. Dieser Generator liefert nur die sieben NEUEN:

  shrine_att    Soeldnerlager (Zelt mit Schwertern)   -> +1 Angriff
  shrine_def    Wehrturm (Turm mit Schild)            -> +1 Verteidigung
  shrine_power  Sternwarte (Kuppel mit Stern)         -> +1 Zauberkraft
  shrine_know   Garten der Erkenntnis (Baum + Buch)   -> +1 Wissen
  well          Brunnen (Schacht mit Dach)            -> Mana voll
  learning      Lehrmeister (Pult mit Buch)           -> XP
  windmill      Windmuehle (Turm mit Fluegeln)        -> Ressource

ZIELGROESSE: 64 px auf der Weltkarte (Kachelgroesse), gezeichnet mit
10 Prozent Rand-Abstand wie die vorhandenen Objekte. Bei der Groesse
zaehlt nur die Silhouette - jedes Motiv braucht eine eigene Grundform,
sonst sehen sie alle wie kleine Haeuser aus.
"""
import os

T = 64
OUT = os.path.join("assets", "world", "objects")

LINE = "#241c12"


def head(comment):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!-- %s\n     Erzeugt von tools/gen_map_objects.py. -->\n'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d">\n'
            % (comment, T, T))


def shadow(rx=20, ry=5, cy=57):
    return ('  <ellipse cx="32" cy="%d" rx="%d" ry="%d" fill="#000" '
            'opacity="0.40"/>\n' % (cy, rx, ry))


def poly(pts, fill, sw=2.0, stroke=LINE, op=None):
    d = " ".join("%.1f,%.1f" % q for q in pts)
    o = ' opacity="%.2f"' % op if op is not None else ""
    return ('  <polygon points="%s" fill="%s" stroke="%s" stroke-width="%.1f" '
            'stroke-linejoin="round"%s/>\n' % (d, fill, stroke, sw, o))


def rect(x, y, w, h, fill, sw=2.0, rx=0):
    return ('  <rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%d" '
            'fill="%s" stroke="%s" stroke-width="%.1f"/>\n'
            % (x, y, w, h, rx, fill, LINE, sw))


def ell(cx, cy, rx, ry, fill, sw=2.0):
    return ('  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s" '
            'stroke="%s" stroke-width="%.1f"/>\n' % (cx, cy, rx, ry, fill, LINE, sw))


def line(x1, y1, x2, y2, col, sw=2.0):
    return ('  <line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
            'stroke-width="%.1f" stroke-linecap="round"/>\n' % (x1, y1, x2, y2, col, sw))


def shrine_att():
    """Zelt mit gekreuzten Schwertern - Silhouette: Dreieck."""
    o = head("Soeldnerlager: +1 Angriff") + shadow(19)
    o += poly([(8, 54), (32, 16), (56, 54)], "#8a5a34")
    o += poly([(8, 54), (32, 16), (32, 54)], "#a87a4c", 0)
    # Eingangsschlitz
    o += poly([(27, 54), (32, 34), (37, 54)], "#3a2a18", 1.5)
    # Gekreuzte Schwerter davor
    o += line(16, 50, 34, 22, "#c8d2dc", 3.5)
    o += line(48, 50, 30, 22, "#c8d2dc", 3.5)
    o += line(28, 30, 40, 30, "#7a5a18", 3.0)
    o += '  <polygon points="30,12 34,12 32,20" fill="#c93a2c"/>\n'
    return o + "</svg>\n"


def shrine_def():
    """Rundturm mit Schild - Silhouette: schmales Hochformat."""
    o = head("Wehrturm: +1 Verteidigung") + shadow(16)
    o += rect(20, 20, 24, 34, "#7d776e")
    o += rect(20, 20, 9, 34, "#989187", 0)
    for k in range(3):
        o += rect(19 + k * 9, 13, 8, 8, "#6b665f", 1.5)
    for y in (30, 40):
        o += line(20, y, 44, y, LINE, 1.5)
    # Schild am Turm
    o += ('  <path d="M 32 30 q -9 0 -9 9 l 0 5 q 0 9 9 11 q 9 -2 9 -11 '
          'l 0 -5 q 0 -9 -9 -9 Z" fill="#7a3a2c" stroke="%s" '
          'stroke-width="2"/>\n' % LINE)
    o += line(32, 33, 32, 52, "#e6c247", 2.0)
    o += line(25, 40, 39, 40, "#e6c247", 2.0)
    return o + "</svg>\n"


def shrine_power():
    """Kuppel mit Stern - Silhewtte: Halbkreis auf Sockel."""
    o = head("Sternwarte: +1 Zauberkraft") + shadow(19)
    o += rect(14, 38, 36, 16, "#5f577e")
    o += ('  <path d="M 12 38 a 20 20 0 0 1 40 0 Z" fill="#6d6690" '
          'stroke="%s" stroke-width="2"/>\n' % LINE)
    o += ('  <path d="M 12 38 a 20 20 0 0 1 20 -20 L 32 38 Z" fill="#8b85a8" '
          'opacity="0.85"/>\n')
    # Stern
    o += ('  <polygon points="32,14 35,24 45,24 37,30 40,40 32,34 24,40 27,30 '
          '19,24 29,24" fill="#ffe6a6" stroke="%s" stroke-width="1.2"/>\n' % LINE)
    o += line(14, 46, 50, 46, LINE, 1.5)
    return o + "</svg>\n"


def shrine_know():
    """Baum mit Buch davor - Silhouette: runde Krone."""
    o = head("Garten der Erkenntnis: +1 Wissen") + shadow(19)
    o += rect(28, 34, 8, 20, "#6b5330", 2.0)
    o += ell(24, 28, 13, 11, "#2c5223")
    o += ell(41, 26, 12, 10, "#37652b")
    o += ell(32, 19, 14, 12, "#417a31")
    o += ell(27, 15, 5, 4, "#5d9542", 0)
    # Aufgeschlagenes Buch am Fuss
    o += poly([(18, 54), (32, 48), (32, 54)], "#e8e0cc", 1.5)
    o += poly([(46, 54), (32, 48), (32, 54)], "#cfc7b0", 1.5)
    o += line(32, 48, 32, 54, LINE, 1.5)
    return o + "</svg>\n"


def well():
    """Schacht mit Dach auf zwei Pfosten - Silhouette: Dach ueber Ring."""
    o = head("Brunnen: Mana auffuellen") + shadow(19)
    o += ell(32, 46, 17, 8, "#6b665f")
    o += ell(32, 45, 11, 5, "#2f5b6b", 1.5)
    o += rect(15, 38, 34, 10, "#7d776e", 2.0, 2)
    for x in (18, 46):
        o += rect(x - 3, 18, 6, 22, "#6b5330", 1.5)
    o += poly([(10, 20), (32, 8), (54, 20)], "#8a5a34")
    o += poly([(10, 20), (32, 8), (32, 20)], "#a87a4c", 0)
    # Eimer an der Kurbel
    o += line(32, 20, 32, 30, LINE, 1.5)
    o += rect(28, 30, 8, 7, "#5c4326", 1.5)
    return o + "</svg>\n"


def learning():
    """Lesepult mit Buch - Silhouette: schraege Platte."""
    o = head("Lehrmeister: Erfahrung") + shadow(18)
    o += rect(29, 34, 6, 20, "#6b5330", 2.0)
    o += rect(20, 50, 24, 5, "#5c4326", 2.0, 2)
    o += poly([(12, 34), (52, 34), (48, 22), (16, 22)], "#7a5f34")
    # Buch auf dem Pult
    o += poly([(16, 30), (32, 25), (32, 33)], "#f2ece0", 1.5)
    o += poly([(48, 30), (32, 25), (32, 33)], "#dcd4c2", 1.5)
    o += line(32, 25, 32, 33, LINE, 1.5)
    for y in (27, 30):
        o += line(20, y + 1, 29, y - 1, "#9a9182", 1.2)
        o += line(35, y - 1, 44, y + 1, "#9a9182", 1.2)
    return o + "</svg>\n"


def windmill():
    """Turm mit vier Fluegeln - Silhouette: Kegel plus Kreuz."""
    o = head("Windmuehle: Ressource pro Woche") + shadow(17)
    o += poly([(20, 54), (24, 24), (40, 24), (44, 54)], "#b8a47c")
    o += poly([(20, 54), (24, 24), (32, 24), (32, 54)], "#d0bc94", 0)
    o += poly([(21, 24), (32, 12), (43, 24)], "#7a3a2c")
    o += rect(28, 44, 8, 10, "#5c4326", 1.5)
    # Fluegelkreuz, bewusst asymmetrisch gedreht
    o += line(32, 22, 32, 4, "#f2e8c8", 3.0)
    o += line(32, 22, 50, 22, "#f2e8c8", 3.0)
    o += line(32, 22, 32, 40, "#f2e8c8", 3.0)
    o += line(32, 22, 14, 22, "#f2e8c8", 3.0)
    o += ('  <circle cx="32" cy="22" r="3.5" fill="#7a5a18" stroke="%s" '
          'stroke-width="1.5"/>\n' % LINE)
    return o + "</svg>\n"


OBJECTS = {
    "shrine_att": shrine_att,
    "shrine_def": shrine_def,
    "shrine_power": shrine_power,
    "shrine_know": shrine_know,
    "well": well,
    "learning": learning,
    "windmill": windmill,
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in OBJECTS.items():
        with open(os.path.join(OUT, name + ".svg"), "w") as f:
            f.write(fn())
        print("[OK] %s.svg" % name)
    print("%d Objekt-Sprites geschrieben nach %s" % (len(OBJECTS), OUT))


if __name__ == "__main__":
    main()
