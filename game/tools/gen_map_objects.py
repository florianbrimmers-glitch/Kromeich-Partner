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
import math
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


# --- Zweite Welle (It. 78) ------------------------------------------------

def campfire():
    """Lagerfeuer mit Kesseln - Silhouette: Flamme ueber Steinring."""
    o = head("Lagerfeuer: Gold und Ressourcen") + shadow(18)
    o += ell(32, 50, 15, 5, "#6b665f")
    for x in (20, 44):
        o += line(x, 52, 32, 40, "#5c4326", 4.0)
    o += poly([(24, 48), (28, 30), (32, 38), (36, 22), (40, 48)], "#e8782c", 1.5)
    o += poly([(28, 48), (31, 36), (34, 42), (36, 48)], "#ffd35a", 0)
    o += rect(44, 42, 10, 10, "#c9a24a", 1.5, 2)
    return o + "</svg>\n"


def artifact():
    """Artefakt auf Sockel - Silhouette: leuchtende Kugel."""
    o = head("Artefakt am Boden") + shadow(15)
    o += rect(22, 44, 20, 10, "#7d776e", 2.0, 2)
    o += ell(32, 32, 12, 12, "#8a6ab0")
    o += ell(28, 28, 4, 4, "#e6d8ff", 0)
    for a, b in ((32, 12), (14, 32), (50, 32)):
        o += line(32, 32, a, b, "#ffe6a6", 1.5)
    return o + "</svg>\n"


def watermill():
    """Muehle mit grossem Rad - Silhouette: Kreis neben Haus."""
    o = head("Wassermuehle: Gold pro Woche") + shadow(20)
    o += rect(26, 26, 26, 28, "#b8a47c")
    o += poly([(23, 28), (39, 12), (55, 28)], "#7a3a2c")
    o += ('  <circle cx="20" cy="40" r="13" fill="none" stroke="#5c4326" '
          'stroke-width="4"/>\n')
    for k in range(4):
        a = k * math.pi / 4
        o += line(20 - 12 * math.cos(a), 40 - 12 * math.sin(a),
                  20 + 12 * math.cos(a), 40 + 12 * math.sin(a), "#6b5330", 2.0)
    o += '  <path d="M 4 56 Q 20 50 36 56" fill="none" stroke="#4a8ab0" stroke-width="3"/>\n'
    return o + "</svg>\n"


def stables():
    """Langer Stall mit Hufeisen - Silhouette: flaches Langhaus."""
    o = head("Stallungen: Bewegung bis Wochenende") + shadow(22)
    o += rect(8, 32, 48, 22, "#8a5a34")
    o += poly([(5, 34), (16, 20), (48, 20), (59, 34)], "#6b4a2a")
    for x in (14, 28, 42):
        o += rect(x, 40, 8, 14, "#3a2a18", 1.5)
    o += ('  <path d="M 26 14 a 6 6 0 1 1 12 0 l -3 0 a 3 3 0 1 0 -6 0 Z" '
          'fill="#c8d2dc" stroke="%s" stroke-width="1.5"/>\n' % LINE)
    return o + "</svg>\n"


def oasis():
    """Wasserloch mit Palme - Silhouette: Wedel ueber Teich."""
    o = head("Oase: Bewegung") + shadow(20)
    o += ell(32, 48, 20, 7, "#d6c08a")
    o += ell(32, 48, 14, 4.5, "#4a8ab0", 1.5)
    o += line(40, 48, 34, 16, "#7a5a30", 4.0)
    for dx, dy in ((-14, 4), (14, 6), (-10, -6), (10, -6), (0, -10)):
        o += line(34, 16, 34 + dx, 16 + dy, "#3f7a2a", 4.0)
    return o + "</svg>\n"


def lookout():
    """Hoher Holzturm - Silhouette: schmales Hochformat mit Plattform."""
    o = head("Aussichtsturm: weite Sicht") + shadow(14)
    for x1, x2 in ((22, 28), (42, 36)):
        o += line(x1, 56, x2, 18, "#6b5330", 3.5)
    o += line(24, 44, 40, 30, "#5c4326", 2.0)
    o += line(40, 44, 24, 30, "#5c4326", 2.0)
    o += rect(20, 12, 24, 8, "#8a5a34", 2.0)
    o += poly([(18, 12), (32, 2), (46, 12)], "#7a3a2c")
    return o + "</svg>\n"


def arena():
    """Rund-Arena - Silhouette: Oval mit Boegen."""
    o = head("Arena: Angriff oder Verteidigung") + shadow(23)
    o += ell(32, 42, 24, 13, "#b3aa98")
    o += ell(32, 40, 16, 7, "#c9b47a", 1.5)
    for x in (12, 22, 32, 42, 52):
        o += rect(x - 2.5, 44, 5, 7, "#3a2a18", 1.0)
    o += line(26, 30, 38, 42, "#c8d2dc", 3.0)
    o += line(38, 30, 26, 42, "#c8d2dc", 3.0)
    return o + "</svg>\n"


def fountain():
    """Brunnenschale mit Fontaene - Silhouette: Tropfen ueber Schale."""
    o = head("Gluecksbrunnen: Glueck") + shadow(18)
    o += ell(32, 46, 18, 7, "#b3aa98")
    o += ell(32, 44, 13, 4, "#4a8ab0", 1.5)
    o += rect(29, 26, 6, 18, "#b3aa98", 1.5)
    o += '  <path d="M 32 26 Q 22 14 18 30 M 32 26 Q 42 14 46 30" fill="none" stroke="#8ad0f0" stroke-width="3"/>\n'
    o += ('  <path d="M 32 6 l 3 6 6 1 -4.5 4.5 1 6 -5.5 -3 -5.5 3 1 -6 -4.5 -4.5 6 -1 Z" '
          'fill="#7ad04a" stroke="%s" stroke-width="1.2"/>\n' % LINE)
    return o + "</svg>\n"


def temple():
    """Tempel mit Saeulen und Giebel - Silhouette: Dreieck auf Saeulen."""
    o = head("Tempel: Moral") + shadow(22)
    o += rect(10, 48, 44, 6, "#9a9182")
    for x in (15, 25, 35, 45):
        o += rect(x, 28, 4, 20, "#e6dcc4", 1.5)
    o += rect(10, 24, 44, 5, "#cfc7b0", 1.5)
    o += poly([(8, 24), (32, 10), (56, 24)], "#cfc7b0")
    o += ell(32, 18, 3, 3, "#e6c247", 1.0)
    return o + "</svg>\n"


def tree():
    """Uralter Baum - Silhouette: breite Krone, dicker Stamm."""
    o = head("Baum des Wissens: eine Stufe") + shadow(22)
    o += poly([(26, 56), (28, 34), (36, 34), (38, 56)], "#6b5330")
    o += ell(20, 28, 13, 11, "#2c5223")
    o += ell(44, 28, 13, 11, "#2c5223")
    o += ell(32, 18, 18, 13, "#417a31")
    for x, y in ((24, 16), (38, 22), (30, 28), (44, 14)):
        o += ell(x, y, 2.5, 2.5, "#ffe08a", 0.8)
    return o + "</svg>\n"


def witch_hut():
    """Krumme Huette auf Stelzen - Silhouette: schiefes Spitzdach."""
    o = head("Hexenhuette: eine Faehigkeit") + shadow(18)
    for x in (20, 44):
        o += line(x, 56, x, 42, "#5c4326", 3.0)
    o += poly([(16, 42), (18, 28), (46, 26), (48, 42)], "#6b5a3a")
    o += poly([(12, 30), (36, 6), (52, 28)], "#3e4a2a")
    o += rect(28, 32, 7, 8, "#ffcf7a", 1.2)
    o += ell(40, 8, 3, 3, "#8a6ab0", 1.0)
    return o + "</svg>\n"


def magic_shrine():
    """Obelisk mit Rune - Silhouette: spitze Saeule."""
    o = head("Schrein der Magie: ein Zauber") + shadow(16)
    o += rect(18, 48, 28, 7, "#5e5868")
    o += poly([(24, 48), (27, 12), (32, 6), (37, 12), (40, 48)], "#7a7490")
    o += poly([(24, 48), (27, 12), (32, 6), (32, 48)], "#9a94b0", 0)
    o += ('  <path d="M 32 18 L 32 38 M 26 24 L 38 32 M 38 24 L 26 32" '
          'stroke="#8ad0ff" stroke-width="2.5" fill="none"/>\n')
    return o + "</svg>\n"


def prison():
    """Kerker mit Gitter - Silhouette: Block mit Gitterfenster."""
    o = head("Gefaengnis: Held befreien") + shadow(20)
    o += rect(12, 22, 40, 32, "#6b665f")
    for k in range(4):
        o += rect(11 + k * 11, 15, 8, 8, "#5a5650", 1.5)
    o += rect(22, 30, 20, 16, "#1a1612", 1.5)
    for x in (26, 32, 38):
        o += line(x, 30, x, 46, "#9aa0a8", 2.5)
    return o + "</svg>\n"


def trading_post():
    """Marktstand mit Waage - Silhouette: Zeltdach ueber Tresen."""
    o = head("Handelsposten: Ressourcen tauschen") + shadow(21)
    o += rect(12, 38, 40, 16, "#8a5a34")
    for x in (14, 48):
        o += rect(x - 1.5, 20, 3, 18, "#5c4326", 1.0)
    o += poly([(8, 22), (32, 10), (56, 22)], "#c93a2c")
    o += poly([(8, 22), (20, 16), (20, 22)], "#e6dcc4", 0)
    o += poly([(32, 22), (44, 16), (44, 22)], "#e6dcc4", 0)
    o += line(22, 30, 42, 30, "#c9a24a", 2.0)
    o += ell(22, 34, 4, 2, "#c9a24a", 1.2)
    o += ell(42, 34, 4, 2, "#c9a24a", 1.2)
    return o + "</svg>\n"


OBJECTS = {
    "shrine_att": shrine_att,
    "shrine_def": shrine_def,
    "shrine_power": shrine_power,
    "shrine_know": shrine_know,
    "well": well,
    "learning": learning,
    "windmill": windmill,
    "campfire": campfire,
    "artifact": artifact,
    "watermill": watermill,
    "stables": stables,
    "oasis": oasis,
    "lookout": lookout,
    "arena": arena,
    "fountain": fountain,
    "temple": temple,
    "tree": tree,
    "witch_hut": witch_hut,
    "magic_shrine": magic_shrine,
    "prison": prison,
    "trading_post": trading_post,
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
