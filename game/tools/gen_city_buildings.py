#!/usr/bin/env python3
"""Erzeugt die Gebaeude-Sprites fuer alle vier Fraktionen als SVG.

    python3 tools/gen_city_buildings.py

Schreibt assets/city/<fraktion>/<gebaeude>.svg - 9 Gebaeude x 4 Fraktionen
= 36 Dateien. NICHT von Hand editieren, hier aendern und neu laufen lassen.

WARUM DAS EXISTIERT: vorher gab es Sprites nur fuer `menschen`, und auch
dort fehlte die Zitadelle. CityScreen._draw_plot faellt fuer ein GEBAUTES
Gebaeude ohne Sprite auf _draw_iso_block zurueck - einen Volltonquader in
Fraktionsfarbe. Auf dem Geraet war das ein violetter Wuerfel mitten in der
Totenreich-Stadt. 28 von 36 Sprites fehlten.

FORMAT IST VERBINDLICH:
  - ViewBox 512x512.
  - Die BODENRAUTE des Gebaeudes liegt mittig bei y = GROUND_Y = 288.
    CityScreen._draw_sprite_at verankert mit SPRITE_GROUND_FRAC = 0.56,
    also 0.56 * 512 = 287. Weicht der Anker ab, schweben die Gebaeude
    ueber ihrer Raute oder versinken darin.
  - Transparenter Hintergrund, keine Bodenplatte ausser der eigenen Raute.

AUFBAU: kein Handzeichnen von 36 Motiven. Eine Teile-Bibliothek
(Iso-Koerper, Daecher, Zierteile) plus 9 Rezepte plus 4 Paletten. Ein
Gebaeude ist ein Rezept, die Fraktion tauscht Farben und Zierteile - so
koennen die vier Staedte gar nicht auseinanderdriften.

Licht kommt von oben-links, wie in den Hintergruenden (tools/gen_city_bg.py):
Dachflaeche hell, linke Wand mittel, rechte Wand dunkel.
"""
import math
import os
import re

SIZE = 512
CX = 256.0        # horizontale Mitte
GROUND_Y = 288.0  # Bodenraute-Mitte, siehe Kopf

# Iso-Verhaeltnis: eine Grundflaeche der Breite w wird w/2 hoch
# dargestellt (2:1-Dimetrie, dieselbe Projektion wie die Iso-Rauten im
# CityScreen).
ISO = 0.5


# --------------------------------------------------------------- Bausteine

def poly(pts, fill, stroke=None, sw=0.0, op=1.0):
    d = " ".join("%.1f,%.1f" % (x, y) for x, y in pts)
    s = '<polygon points="%s" fill="%s"' % (d, fill)
    if op != 1.0:
        s += ' opacity="%.2f"' % op
    if stroke:
        s += ' stroke="%s" stroke-width="%.1f" stroke-linejoin="round"' % (stroke, sw)
    return s + "/>"


def ground_shadow(w, op=0.30, flat=False):
    """Schatten unter dem Gebaeude. Setzt es optisch auf den Boden.

    `flat` fuer Koerper, deren Grundflaeche KEINE Iso-Raute ist (Mauerbahn,
    Holzturm): eine Raute darunter stand dort als dunkles Dreieck neben dem
    Motiv heraus."""
    y = GROUND_Y + 6
    if flat:
        hw = w * 0.5
        return ('<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="#000000" '
                'opacity="%.2f"/>' % (CX, y + 4, hw * 0.92, 18.0, op))
    hw = w * 0.5
    hh = hw * ISO
    return poly([(CX - hw * 1.06, y), (CX, y - hh * 1.06),
                 (CX + hw * 1.06, y), (CX, y + hh * 1.06)],
                "#000000", op=op)


def iso_box(w, h, pal, top_key="roof", inset=0.0, base_y=None):
    """Quader in 2:1-Iso. Liefert (svg, top_pts) - top_pts ist die
    Deckraute, auf die ein Dach oder ein weiterer Koerper aufsetzt."""
    by = GROUND_Y if base_y is None else base_y
    hw = w * 0.5 - inset
    hh = hw * ISO
    ty = by - h
    # Bodenraute
    b_n = (CX, by - hh)
    b_e = (CX + hw, by)
    b_s = (CX, by + hh)
    b_w = (CX - hw, by)
    # Deckraute
    t_n = (CX, ty - hh)
    t_e = (CX + hw, ty)
    t_s = (CX, ty + hh)
    t_w = (CX - hw, ty)
    out = [
        # linke Wand (mittel), rechte Wand (dunkel)
        poly([b_w, b_s, t_s, t_w], pal["wall_mid"], pal["line"], 2.0),
        poly([b_s, b_e, t_e, t_s], pal["wall_dark"], pal["line"], 2.0),
        # Deckflaeche
        poly([t_n, t_e, t_s, t_w], pal[top_key], pal["line"], 2.0),
    ]
    return "\n".join(out), (t_n, t_e, t_s, t_w, ty, hw, hh)


def iso_tower(w, h, pal, base_y=None):
    """Runder Turm: Schaft als Rechteck mit Rundung, Deckel als Ellipse.
    Fuer Wachturm und Spaeher - ein Quader liest sich dort wie ein Haus."""
    by = GROUND_Y if base_y is None else base_y
    hw = w * 0.5
    hh = hw * ISO
    ty = by - h
    out = [
        '<path d="M %.1f %.1f L %.1f %.1f A %.1f %.1f 0 0 0 %.1f %.1f L %.1f %.1f Z" '
        'fill="%s" stroke="%s" stroke-width="2"/>'
        % (CX - hw, ty, CX - hw, by, hw, hh, CX + hw, by, CX + hw, ty,
           pal["wall_mid"], pal["line"]),
        # rechte Haelfte dunkler
        '<path d="M %.1f %.1f L %.1f %.1f A %.1f %.1f 0 0 0 %.1f %.1f L %.1f %.1f Z" '
        'fill="%s" opacity="0.55"/>'
        % (CX + hw * 0.12, ty, CX + hw * 0.12, by, hw, hh, CX + hw, by, CX + hw, ty,
           pal["wall_dark"]),
        '<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s" stroke="%s" stroke-width="2"/>'
        % (CX, ty, hw, hh, pal["roof"], pal["line"]),
    ]
    return "\n".join(out), (None, None, None, None, ty, hw, hh)


# --------------------------------------------------------------- Daecher

def roof_gable(top, pal, rise):
    """Satteldach: First laeuft in der Bildschirm-Senkrechten (N-S-Achse
    der Iso-Raute), links die belichtete, rechts die abgeschattete Schraege.

    Erster Versuch war ein Viereck von W nach E ueber den First - das ergab
    keine planare Flaeche und las sich als flache Platte auf dem Dach. Beide
    Schraegen sind Fuenfecke: First, N-Ecke, Seiten-Ecke, S-Ecke, First."""
    t_n, t_e, t_s, t_w, ty, hw, hh = top
    r_n = (CX, ty - hh - rise)
    r_s = (CX, ty + hh - rise)
    out = [
        poly([r_n, t_n, t_w, t_s, r_s], pal["roof_light"], pal["line"], 2.0),
        poly([r_n, t_n, t_e, t_s, r_s], pal["roof_dark"], pal["line"], 2.0),
    ]
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="3"/>'
               % (r_n[0], r_n[1], r_s[0], r_s[1], pal["line"]))
    return "\n".join(out)


def roof_pyramid(top, pal, rise):
    t_n, t_e, t_s, t_w, ty, hw, hh = top
    apex = (CX, ty - rise)
    return "\n".join([
        poly([t_w, t_n, apex], pal["roof_light"], pal["line"], 2.0),
        poly([t_n, t_e, apex], pal["roof"], pal["line"], 2.0),
        poly([t_e, t_s, apex], pal["roof_dark"], pal["line"], 2.0),
        poly([t_s, t_w, apex], pal["roof"], pal["line"], 2.0),
    ])


def roof_spike(top, pal, rise):
    """Sehr steile Spitze - Kapelle, Zitadellen-Turm."""
    return roof_pyramid(top, pal, rise * 1.7)


def roof_dome(top, pal, rise):
    t_n, t_e, t_s, t_w, ty, hw, hh = top
    return "\n".join([
        '<path d="M %.1f %.1f A %.1f %.1f 0 0 1 %.1f %.1f Z" fill="%s" stroke="%s" stroke-width="2"/>'
        % (CX - hw, ty, hw, rise, CX + hw, ty, pal["roof"], pal["line"]),
        '<path d="M %.1f %.1f A %.1f %.1f 0 0 1 %.1f %.1f Z" fill="%s" opacity="0.55"/>'
        % (CX - hw, ty, hw * 0.62, rise * 0.9, CX + hw * 0.1, ty, pal["roof_light"]),
    ])


def roof_flat(top, pal, rise):
    """Flachdach mit Zinnenkranz - Mauer, Kaserne."""
    t_n, t_e, t_s, t_w, ty, hw, hh = top
    out = []
    n = 5
    for i in range(n):
        f = -1.0 + 2.0 * (i + 0.5) / n
        bx = CX + f * hw * 0.86
        byy = ty + f * hh * 0.0
        bw = hw * 0.26
        out.append(poly([(bx - bw * 0.5, byy), (bx + bw * 0.5, byy),
                         (bx + bw * 0.5, byy - rise), (bx - bw * 0.5, byy - rise)],
                        pal["roof"], pal["line"], 2.0))
    return "\n".join(out)


ROOFS = {"gable": roof_gable, "pyramid": roof_pyramid, "spike": roof_spike,
         "dome": roof_dome, "flat": roof_flat}


# -------------------------------------------------------------- Zierteile

def door(pal, w=52, h=76, dy=0.0):
    x = CX - w * 0.5
    y = GROUND_Y + 6 - h + dy
    return ('<path d="M %.1f %.1f L %.1f %.1f A %.1f %.1f 0 0 1 %.1f %.1f L %.1f %.1f Z" '
            'fill="%s" stroke="%s" stroke-width="2"/>'
            % (x, y + h, x, y + h * 0.45, w * 0.5, h * 0.45, x + w, y + h * 0.45,
               x + w, y + h, pal["door"], pal["line"]))


def windows(pal, rows=2, cols=2, w=20, h=28, spread=100, top=120):
    out = []
    for r in range(rows):
        for c in range(cols):
            fx = -1.0 + 2.0 * (c + 0.5) / cols
            x = CX + fx * spread * 0.5 - w * 0.5
            y = GROUND_Y - top + r * (h + 22)
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" '
                       'fill="%s" stroke="%s" stroke-width="2"/>'
                       % (x, y, w, h, w * 0.45, pal["glow"], pal["line"]))
    return "\n".join(out)


def banner(pal, dx=0.0, top=250, h=86):
    x = CX + dx
    y = GROUND_Y - top
    return "\n".join([
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="5"/>'
        % (x, y, x, y + h + 40, pal["line"]),
        poly([(x, y), (x + 54, y + 16), (x, y + 34)], pal["accent"], pal["line"], 2.0),
    ])


def chimney(pal, dx=-74.0, top=196, h=84, smoke=True):
    x = CX + dx
    y = GROUND_Y - top
    out = [poly([(x - 17, y + h), (x - 17, y), (x + 17, y), (x + 17, y + h)],
                pal["wall_dark"], pal["line"], 2.0)]
    if smoke:
        # Radien und Abstaende bewusst klein: mit y-22-k*30 und r bis 29
        # ragte die oberste Wolke bis y=-19, also aus der ViewBox.
        for k in range(3):
            out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" opacity="%.2f"/>'
                       % (x + 7 + k * 12, y - 16 - k * 20, 12 + k * 4,
                          pal["smoke"], 0.34 - k * 0.09))
    return "\n".join(out)


def forge_glow(pal, dy=40.0):
    y = GROUND_Y - dy
    return "\n".join([
        '<ellipse cx="%.1f" cy="%.1f" rx="62" ry="30" fill="%s" opacity="0.45"/>'
        % (CX, y, pal["accent"]),
        '<ellipse cx="%.1f" cy="%.1f" rx="30" ry="15" fill="%s" opacity="0.85"/>'
        % (CX, y - 3, pal["glow"]),
    ])


def palisade_ring(pal, w=300, n=9):
    """Spitze Pfaehle vor dem Gebaeude - Ork-Kennzeichen."""
    out = []
    for i in range(n):
        f = -1.0 + 2.0 * (i + 0.5) / n
        x = CX + f * w * 0.5
        y = GROUND_Y + 4 + abs(f) * -8
        h = 54 + (i % 3) * 12
        tilt = (i % 5 - 2) * 3.0
        out.append(poly([(x - 9 + tilt, y), (x - 9 + tilt * 1.4, y - h + 12),
                         (x + tilt * 1.7, y - h), (x + 9 + tilt * 1.4, y - h + 12),
                         (x + 9 + tilt, y)], pal["wood"], pal["line"], 2.0))
    return "\n".join(out)


def bones(pal, w=250):
    """Totenreich-Signatur: kleine Schaedel auf Pfaehlen am Sockel.

    Erster Versuch waren lange Knochen als Schraegstriche quer ueber das
    Gebaeude - bei 150 px las sich das als Kratzer im Bild, nicht als
    Zierrat. Jetzt klein, tief und am Rand."""
    out = []
    for f in (-1.0, 1.0):
        x = CX + f * (w * 0.5 + 16)
        y = GROUND_Y + 4
        # Pfahl
        out.append(poly([(x - 4, y), (x - 4, y - 46), (x + 4, y - 46), (x + 4, y)],
                        pal["wood"], pal["line"], 1.5))
        # Schaedel
        out.append('<circle cx="%.1f" cy="%.1f" r="13" fill="%s" stroke="%s" '
                   'stroke-width="1.5"/>' % (x, y - 56, pal["bone"], pal["line"]))
        out.append(poly([(x - 8, y - 50), (x + 8, y - 50), (x + 5, y - 40), (x - 5, y - 40)],
                        pal["bone"], pal["line"], 1.5))
        for ex in (-5, 5):
            out.append('<circle cx="%.1f" cy="%.1f" r="3.4" fill="%s"/>'
                       % (x + ex, y - 58, pal["line"]))
        # Gruenfeuer-Funken ueber dem Schaedel
        out.append('<circle cx="%.1f" cy="%.1f" r="5" fill="%s" opacity="0.75"/>'
                   % (x, y - 76, pal["glow"]))
    return "\n".join(out)


def vines(pal, w=280):
    """Waldvolk-Signatur: Busch-Gruppen am Sockel plus eine kurze Ranke.

    Erster Versuch setzte zwei Blattsaeulen auf festen Abstand +-96 px vom
    Zentrum; bei breiten Gebaeuden (Markt, Mauer) schwebten sie neben dem
    Motiv statt daran. Jetzt an der tatsaechlichen Gebaeudekante."""
    out = []
    for f in (-1.0, 1.0):
        bx = CX + f * (w * 0.5 - 6)
        by = GROUND_Y + 6
        # Buschgruppe am Fuss
        for dx, dy, r in ((0, 0, 26), (f * 22, 5, 19), (f * -14, 6, 16)):
            out.append('<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s"/>'
                       % (bx + dx + 4, by + dy + 3, r, r * 0.66, pal["leaf_dark"]))
        for dx, dy, r in ((0, 0, 26), (f * 22, 5, 19), (f * -14, 6, 16)):
            out.append('<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s"/>'
                       % (bx + dx, by + dy, r, r * 0.66, pal["leaf"]))
        # Kurze Ranke die Wand hoch
        out.append('<path d="M %.1f %.1f Q %.1f %.1f %.1f %.1f" fill="none" stroke="%s" '
                   'stroke-width="5" stroke-linecap="round"/>'
                   % (bx, by - 14, bx - f * 14, by - 58, bx - f * 4, by - 96,
                      pal["leaf_dark"]))
        for k in range(3):
            ly = by - 34 - k * 26
            out.append('<ellipse cx="%.1f" cy="%.1f" rx="13" ry="8" fill="%s"/>'
                       % (bx - f * (8 + k * 2), ly, pal["leaf"]))
    return "\n".join(out)


def stall(pal):
    """Marktstand: Tisch mit gestreifter Plane."""
    y = GROUND_Y - 6
    out = [poly([(CX - 132, y), (CX - 118, y - 54), (CX + 118, y - 54), (CX + 132, y)],
                pal["wood"], pal["line"], 2.0)]
    for k in range(5):
        x0 = CX - 118 + k * 48
        col = pal["accent"] if k % 2 == 0 else pal["roof_light"]
        out.append(poly([(x0, y - 54), (x0 + 48, y - 54), (x0 + 42, y - 96), (x0 - 6, y - 96)],
                        col, pal["line"], 1.5))
    out.append('<circle cx="%.1f" cy="%.1f" r="16" fill="%s"/>' % (CX + 96, y - 18, pal["glow"]))
    return "\n".join(out)


def stable_fence(pal):
    """Koppel-Zaun - Reiterei."""
    y = GROUND_Y + 2
    out = []
    for f in (-1.0, 1.0):
        x = CX + f * 150
        out.append(poly([(x - 8, y), (x - 8, y - 74), (x + 8, y - 74), (x + 8, y)],
                        pal["wood"], pal["line"], 2.0))
    for h in (28, 56):
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="9"/>'
                   % (CX - 150, y - h, CX + 150, y - h, pal["wood"]))
    return "\n".join(out)


def wall_piece(pal):
    """Mauerstueck mit Tor und zwei Flankentuermen. Ein Kasten mit Dach las
    sich wie eine Kaserne - eine Stadtmauer muss auf einen Blick als Mauer
    erkennbar sein, weil sie das Belagerungs-Gameplay traegt."""
    out = []
    span_w, span_h = 250.0, 92.0
    ty = GROUND_Y - span_h
    hh = span_w * 0.5 * ISO * 0.35
    # Mauerbahn zwischen den Tuermen (flach, kaum Tiefe)
    out.append(poly([(CX - span_w * 0.5, GROUND_Y), (CX - span_w * 0.5, ty),
                     (CX + span_w * 0.5, ty), (CX + span_w * 0.5, GROUND_Y)],
                    pal["wall_mid"], pal["line"], 2.0))
    out.append(poly([(CX - span_w * 0.5, ty), (CX + span_w * 0.5, ty),
                     (CX + span_w * 0.5, ty - hh), (CX - span_w * 0.5, ty - hh)],
                    pal["roof_light"], pal["line"], 2.0))
    # Quaderfugen - macht es als Mauerwerk lesbar
    for r in range(3):
        y = ty + 22 + r * 24
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                   'stroke-width="2" opacity="0.45"/>'
                   % (CX - span_w * 0.5, y, CX + span_w * 0.5, y, pal["line"]))
    # Zinnen auf der Bahn
    for i in range(7):
        f = -1.0 + 2.0 * (i + 0.5) / 7
        bx = CX + f * span_w * 0.42
        out.append(poly([(bx - 14, ty - hh), (bx + 14, ty - hh),
                         (bx + 14, ty - hh - 26), (bx - 14, ty - hh - 26)],
                        pal["wall_mid"], pal["line"], 2.0))
    # Flankentuerme
    for f in (-1.0, 1.0):
        tx = CX + f * (span_w * 0.5 + 34)
        th = 150.0
        tty = GROUND_Y - th
        out.append(poly([(tx - 34, GROUND_Y), (tx - 34, tty), (tx + 34, tty),
                         (tx + 34, GROUND_Y)], pal["wall_mid"], pal["line"], 2.0))
        out.append(poly([(tx + 12, GROUND_Y), (tx + 12, tty), (tx + 34, tty),
                         (tx + 34, GROUND_Y)], pal["wall_dark"], None, 0.0, 0.6))
        out.append('<ellipse cx="%.1f" cy="%.1f" rx="34" ry="13" fill="%s" '
                   'stroke="%s" stroke-width="2"/>' % (tx, tty, pal["roof"], pal["line"]))
        for k in range(3):
            bx = tx - 24 + k * 24
            out.append(poly([(bx - 9, tty - 4), (bx + 9, tty - 4),
                             (bx + 9, tty - 28), (bx - 9, tty - 28)],
                            pal["wall_mid"], pal["line"], 2.0))
    return "\n".join(out), (None, None, None, None, ty - hh - 26, span_w * 0.5, hh)


def scout_tower(pal):
    """Spaeherturm: schlanker Schaft mit auskragender Ausguck-Plattform und
    Leiter. Ohne die Plattform war er nur ein kleinerer Wachturm."""
    hw, h = 52.0, 168.0
    ty = GROUND_Y - h
    out = [
        '<path d="M %.1f %.1f L %.1f %.1f A %.1f %.1f 0 0 0 %.1f %.1f L %.1f %.1f Z" '
        'fill="%s" stroke="%s" stroke-width="2"/>'
        % (CX - hw, ty + 40, CX - hw, GROUND_Y, hw, hw * ISO, CX + hw, GROUND_Y,
           CX + hw, ty + 40, pal["wood"], pal["line"]),
        '<path d="M %.1f %.1f L %.1f %.1f A %.1f %.1f 0 0 0 %.1f %.1f L %.1f %.1f Z" '
        'fill="%s" opacity="0.5"/>'
        % (CX + hw * 0.15, ty + 40, CX + hw * 0.15, GROUND_Y, hw, hw * ISO,
           CX + hw, GROUND_Y, CX + hw, ty + 40, pal["wall_dark"]),
    ]
    # Leiter
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="5"/>'
               % (CX - 24, GROUND_Y, CX - 24, ty + 44, pal["line"]))
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="5"/>'
               % (CX + 4, GROUND_Y, CX + 4, ty + 44, pal["line"]))
    for k in range(6):
        yy = GROUND_Y - 18 - k * 24
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="4"/>'
                   % (CX - 24, yy, CX + 4, yy, pal["line"]))
    # Auskragende Plattform
    pw = 96.0
    out.append(poly([(CX - pw, ty + 44), (CX + pw, ty + 44),
                     (CX + pw * 0.82, ty + 20), (CX - pw * 0.82, ty + 20)],
                    pal["wood"], pal["line"], 2.0))
    out.append('<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s" '
               'stroke="%s" stroke-width="2"/>' % (CX, ty + 20, pw * 0.82, 16,
                                                   pal["roof_light"], pal["line"]))
    # Bruestung + Kegeldach
    out.append(poly([(CX - 72, ty + 20), (CX - 72, ty - 6), (CX + 72, ty - 6),
                     (CX + 72, ty + 20)], pal["wood"], pal["line"], 2.0))
    out.append(poly([(CX - 84, ty - 6), (CX, ty - 62), (CX + 84, ty - 6)],
                    pal["roof"], pal["line"], 2.0))
    out.append(poly([(CX - 84, ty - 6), (CX, ty - 62), (CX, ty - 6)],
                    pal["roof_light"], None, 0.0, 0.85))
    return "\n".join(out), (None, None, None, None, ty - 62, 84.0, 16.0)


# ----------------------------------------------------------------- Rezepte
# Ein Gebaeude = Koerper + Dach + Zierteile. Die Reihenfolge im Ergebnis
# ist Zeichenreihenfolge (hinten nach vorne).

def build(bid, pal):
    r = RECIPES[bid]
    parts = [ground_shadow(r["w"], flat=bool(r.get("custom")))]
    if r.get("custom"):
        svg, top = CUSTOM[r["custom"]](pal)
    else:
        body_fn = iso_tower if r.get("tower") else iso_box
        svg, top = body_fn(r["w"], r["h"], pal)
    parts.append(svg)
    if r.get("roof"):
        parts.append(ROOFS[r["roof"]](top, pal, r.get("rise", 60)))
    # Aufbau (zweiter Koerper oben drauf), z.B. Zitadellen-Turm
    if r.get("upper"):
        uw, uh, uroof, urise = r["upper"]
        svg2, top2 = iso_box(uw, uh, pal, base_y=GROUND_Y - r["h"])
        parts.append(svg2)
        parts.append(ROOFS[uroof](top2, pal, urise))
    for orn in r["orn"]:
        parts.append(ORN[orn](pal))
    # Fraktions-Zierteil zum Schluss, damit es vorne liegt
    if r.get("faction_orn", True):
        parts.append(SIGNATURES[pal["signature"]](pal, r["w"]))
    return "\n".join(parts)


RECIPES = {
    # Hoehen-Budget: der oberste Punkt muss >= ~40 bleiben (GROUND_Y 288),
    # sonst laeuft das Motiv aus der 512er ViewBox. check_bounds() prueft
    # das am fertigen SVG - die Zitadelle war im ersten Anlauf oben ab.
    #
    # Silhouette ist das Unterscheidungsmerkmal, nicht die Farbe: auf dem
    # Handy sind die Sprites ~150 px breit, da zaehlt nur die Form.
    # kapelle    schmal + steile Spitze
    # zitadelle  breiter Sockel + aufgesetzter Turm (hoechstes Gebaeude)
    # schmiede   Satteldach + Schornstein + Glut
    # reiterei   sehr flach + breites Tor + Koppel davor
    # markt      kein Haus, sondern Stand mit gestreifter Plane
    # wachturm   hoher Rundturm
    # kaserne    langer flacher Block mit Zinnen
    # spaeher    schlanker Holzturm mit Ausguck-Plattform
    # mauer      Mauerbahn mit Tor und zwei Flankentuermen
    "kapelle":   dict(w=200, h=128, roof="spike", rise=54,
                      orn=["door", "windows_tall"]),
    "zitadelle": dict(w=330, h=88, roof=None, upper=(180, 108, "pyramid", 54),
                      orn=["door", "banner_pair", "windows_wide"]),
    "schmiede":  dict(w=280, h=100, roof="gable", rise=72,
                      orn=["chimney", "forge_glow"]),
    "reiterei":  dict(w=306, h=70, roof="gable", rise=84,
                      orn=["gate", "stable_fence"]),
    "markt":     dict(w=300, h=80, roof=None, orn=["stall"]),
    "wachturm":  dict(w=168, h=196, tower=True, roof=None,
                      orn=["windows_high", "banner_top"]),
    "kaserne":   dict(w=330, h=104, roof="flat", rise=32,
                      orn=["door", "windows_wide", "banner_side"]),
    "spaeher":   dict(custom="scout", w=210, h=0, roof=None, orn=[]),
    "mauer":     dict(custom="wall", w=340, h=0, roof=None, orn=[]),
}

CUSTOM = {"wall": wall_piece, "scout": scout_tower}

ORN = {
    "door": lambda p: door(p),
    "door_wide": lambda p: door(p, w=76, h=84),
    "door_small": lambda p: door(p, w=40, h=62),
    "gate": lambda p: door(p, w=96, h=92),
    "windows": lambda p: windows(p),
    "windows_tall": lambda p: windows(p, rows=1, cols=1, w=40, h=52, top=118),
    "windows_wide": lambda p: windows(p, rows=1, cols=3, w=22, h=30, spread=210, top=92),
    "windows_high": lambda p: windows(p, rows=2, cols=1, w=24, h=32, spread=0, top=162),
    "banner_pair": lambda p: banner(p, dx=-146, top=132) + "\n" + banner(p, dx=130, top=132),
    "banner_side": lambda p: banner(p, dx=-140, top=136),
    "banner_top": lambda p: banner(p, dx=-6, top=228, h=54),
    "chimney": lambda p: chimney(p),
    "forge_glow": lambda p: forge_glow(p),
    "stall": lambda p: stall(p),
    "stable_fence": lambda p: stable_fence(p),
}

# Fraktions-Signaturen: bekommen die Gebaeudebreite, damit sie an der
# tatsaechlichen Kante sitzen statt auf festem Abstand.
SIGNATURES = {
    "palisade": lambda p, w: palisade_ring(p, w=w + 40, n=max(7, int(w / 34))),
    "bones": lambda p, w: bones(p, w=w),
    "vines": lambda p, w: vines(p, w=w),
    "nothing": lambda p, w: "",
}


# ---------------------------------------------------------------- Paletten
# Quelle der Absicht: data/factions.json (theme, affinity_schools) und
# assets/city/ART_SPEC.md. Die Farben liegen bewusst nahe an den
# Hintergruenden aus tools/gen_city_bg.py.

PALETTES = {
    "menschen": dict(
        wall_mid="#c9b184", wall_dark="#9a8460", roof="#4a5a72",
        roof_light="#5e7290", roof_dark="#374556", line="#2c2418",
        door="#6b5330", glow="#ffd98a", accent="#a8342c", wood="#7a5f34",
        smoke="#cfc6b4", bone="#e6dfcc", leaf="#5d9542", leaf_dark="#356328",
        signature="nothing"),
    "waldvolk": dict(
        wall_mid="#a8874f", wall_dark="#7b6034", roof="#3b7130",
        roof_light="#4f9040", roof_dark="#2a5122", line="#1f2a14",
        door="#5c4527", glow="#ffe89a", accent="#c8a24a", wood="#6b5330",
        smoke="#d4dcc4", bone="#e6dfcc", leaf="#6fa74b", leaf_dark="#356328",
        signature="vines"),
    "totenreich": dict(
        wall_mid="#8b85a0", wall_dark="#605a75", roof="#4a4466",
        roof_light="#5f577e", roof_dark="#332f45", line="#18141f",
        door="#2b2436", glow="#7dffb0", accent="#7dffb0", wood="#4a4459",
        smoke="#cfe8d8", bone="#e8e4d4", leaf="#6b7d8f", leaf_dark="#3f4a55",
        signature="bones"),
    "orks": dict(
        wall_mid="#8a6c3d", wall_dark="#5d4726", roof="#4a3a20",
        roof_light="#6b5530", roof_dark="#33260f", line="#1d1409",
        door="#33260f", glow="#ffb257", accent="#a8452c", wood="#6b5028",
        smoke="#b3a894", bone="#ded7c2", leaf="#7d8a4a", leaf_dark="#4a5228",
        signature="palisade"),
}


# ------------------------------------------------------------- Baustellen
# Fraktionsneutral (assets/city/_shared/), weil CityScreen fuer ungebaute
# Plaetze erst construction-<id>.svg und dann construction.svg sucht -
# beides ohne Fraktions-Verzeichnis. Vorher fehlte construction-zitadelle,
# die Zitadelle fiel deshalb auf die generische Baustelle zurueck.

SCAFFOLD = dict(
    wall_mid="#9a9086", wall_dark="#6f665d", roof="#7d746a",
    roof_light="#b0a79c", roof_dark="#5a534b", line="#2f2b26",
    door="#4a443c", glow="#c9b98f", accent="#a8542c", wood="#8a6c3d",
    smoke="#c4bdb2", bone="#ded7c8", leaf="#7d8a5a", leaf_dark="#4a5238",
    signature="nothing")


def scaffolding(w, h):
    """Geruest ueber der halbfertigen Mauer: Pfosten, zwei Riegel, Leiter."""
    out = []
    hw = w * 0.5
    top = GROUND_Y - h - 58
    for f in (-1.0, 1.0):
        x = CX + f * (hw * 0.88)
        out.append(poly([(x - 6, GROUND_Y + 8), (x - 6, top), (x + 6, top),
                         (x + 6, GROUND_Y + 8)], SCAFFOLD["wood"], SCAFFOLD["line"], 2.0))
    for k in (0, 1):
        y = top + 26 + k * 46
        out.append(poly([(CX - hw * 0.94, y), (CX + hw * 0.94, y),
                         (CX + hw * 0.94, y + 10), (CX - hw * 0.94, y + 10)],
                        SCAFFOLD["wood"], SCAFFOLD["line"], 2.0))
    # Leiter an der linken Seite
    lx = CX - hw * 0.55
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="5"/>'
               % (lx, GROUND_Y + 6, lx, top + 20, SCAFFOLD["line"]))
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="5"/>'
               % (lx + 26, GROUND_Y + 6, lx + 26, top + 20, SCAFFOLD["line"]))
    for k in range(5):
        yy = GROUND_Y - 8 - k * 26
        if yy < top + 20:
            break
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="4"/>'
                   % (lx, yy, lx + 26, yy, SCAFFOLD["line"]))
    return "\n".join(out)


def build_construction(bid):
    """Halbfertiger Rohbau: Sockel auf 45 Prozent Hoehe, kein Dach, kein
    Zierrat - dafuer Geruest. Die Silhouette bleibt erkennbar (breit/schmal,
    Turm/Kasten), damit man den Bauplatz auch unfertig zuordnen kann."""
    r = RECIPES[bid]
    w = r["w"]
    parts = [ground_shadow(w, flat=bool(r.get("custom")))]
    if r.get("custom"):
        # Eigene Koerper (Mauer, Spaeherturm): halbe Hoehe ueber einen
        # flachen Stumpf andeuten, statt die Sonderform nachzubauen.
        stub = 56.0
        parts.append(poly([(CX - w * 0.42, GROUND_Y), (CX - w * 0.42, GROUND_Y - stub),
                           (CX + w * 0.42, GROUND_Y - stub), (CX + w * 0.42, GROUND_Y)],
                          SCAFFOLD["wall_mid"], SCAFFOLD["line"], 2.0))
        h_used = stub
    elif r.get("tower"):
        h_used = r["h"] * 0.45
        svg, _ = iso_tower(w, h_used, SCAFFOLD)
        parts.append(svg)
    else:
        h_used = r["h"] * 0.45
        svg, top = iso_box(w, h_used, SCAFFOLD, top_key="roof_light")
        parts.append(svg)
        # Angefangene Mauerkroenung
        parts.append(roof_flat(top, SCAFFOLD, 16))
    parts.append(scaffolding(w, h_used))
    return "\n".join(parts)


def svg_doc(body):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!-- Erzeugt von tools/gen_city_buildings.py - nicht von Hand editieren.\n'
            '     Bodenraute-Mitte bei y=%d (CityScreen SPRITE_GROUND_FRAC 0.56). -->\n'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'width="%d" height="%d">\n%s\n</svg>\n'
            % (GROUND_Y, SIZE, SIZE, SIZE, SIZE, body))


# Anzahl Parameter je Pfad-Kommando. Wichtig fuer A (Bogen): dort sind nur
# die LETZTEN zwei der sieben Zahlen Koordinaten - rx, ry und die drei Flags
# sind keine. Ein naiver Paarweise-Parser hat daraus (0,0) und (0,1) gelesen
# und deshalb bei jedem Turm "laeuft aus dem Bild" gemeldet.
_PATH_ARGS = {"M": 2, "L": 2, "T": 2, "Q": 4, "S": 4, "C": 6, "A": 7,
              "H": 1, "V": 1, "Z": 0}


def _path_points(d):
    toks = re.findall(r'[MLTQSCAHVZmltqscahvz]|-?\d+(?:\.\d+)?', d)
    pts = []
    i = 0
    cmd = "M"
    while i < len(toks):
        if toks[i].upper() in _PATH_ARGS:
            cmd = toks[i].upper()
            i += 1
            if cmd == "Z":
                continue
        n = _PATH_ARGS[cmd]
        if i + n > len(toks):
            break
        args = [float(x) for x in toks[i:i + n]]
        i += n
        if cmd in ("H", "V"):
            continue
        pts.append((args[-2], args[-1]))
    return pts


def check_bounds(svg, label):
    """Prueft am fertigen SVG, dass nichts aus der ViewBox laeuft. Die
    Zitadelle war im ersten Anlauf oben abgeschnitten, und im Sprite-Blatt
    fiel es kaum auf - so ein Fehler soll laut sein, nicht leise."""
    nums = []
    for attr in ("points",):
        for m in re.finditer(r'%s="([^"]+)"' % attr, svg):
            for pair in m.group(1).split():
                x, y = pair.split(",")
                nums.append((float(x), float(y)))
    for m in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)"', svg):
        x, y, w, h = (float(g) for g in m.groups())
        nums += [(x, y), (x + w, y + h)]
    for m in re.finditer(r'<(?:circle|ellipse) cx="([-\d.]+)" cy="([-\d.]+)" r(?:x)?="([-\d.]+)"(?: ry="([-\d.]+)")?', svg):
        cx, cy, rx = (float(g) for g in m.groups()[:3])
        ry = float(m.group(4)) if m.group(4) else rx
        nums += [(cx - rx, cy - ry), (cx + rx, cy + ry)]
    for m in re.finditer(r'\sd="([^"]+)"', svg):
        nums += _path_points(m.group(1))
    if not nums:
        return ["%s: keine Geometrie gefunden" % label]
    xs = [p[0] for p in nums]
    ys = [p[1] for p in nums]
    problems = []
    if min(ys) < 4.0:
        problems.append("%s: laeuft oben aus dem Bild (min y = %.0f)" % (label, min(ys)))
    if max(ys) > SIZE - 4:
        problems.append("%s: laeuft unten aus dem Bild (max y = %.0f)" % (label, max(ys)))
    if min(xs) < 4.0 or max(xs) > SIZE - 4:
        problems.append("%s: laeuft seitlich aus dem Bild (x %.0f..%.0f)"
                        % (label, min(xs), max(xs)))
    return problems


def main():
    total = 0
    problems = []
    for fac, pal in PALETTES.items():
        outdir = os.path.join("assets", "city", fac)
        os.makedirs(outdir, exist_ok=True)
        for bid in RECIPES:
            svg = svg_doc(build(bid, pal))
            problems += check_bounds(svg, "%s/%s" % (fac, bid))
            with open(os.path.join(outdir, bid + ".svg"), "w") as f:
                f.write(svg)
            total += 1
        print("[OK] %-11s %d Gebaeude" % (fac, len(RECIPES)))
    shared = os.path.join("assets", "city", "_shared")
    os.makedirs(shared, exist_ok=True)
    for bid in RECIPES:
        svg = svg_doc(build_construction(bid))
        problems += check_bounds(svg, "_shared/construction-%s" % bid)
        with open(os.path.join(shared, "construction-%s.svg" % bid), "w") as f:
            f.write(svg)
        total += 1
    print("[OK] %-11s %d Baustellen" % ("_shared", len(RECIPES)))
    print("%d Sprites geschrieben." % total)
    if problems:
        print("")
        for p in problems:
            print("[WARNUNG] %s" % p)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
