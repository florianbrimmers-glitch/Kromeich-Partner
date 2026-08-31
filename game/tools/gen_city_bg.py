#!/usr/bin/env python3
"""Erzeugt die Stadt-Hintergruende fuer alle vier Fraktionen als SVG.

    python3 tools/gen_city_bg.py

Schreibt assets/city/<fraktion>/bg.svg und bg_walled.svg.
NICHT die SVGs von Hand editieren - hier aendern und neu laufen lassen.

Herkunft: dieser Generator hat zuerst als Entwurf auf einer Design-Leinwand
gelebt (Waldvolk/Totenreich/Orks, vom Nutzer freigegeben). Jetzt im Repo,
plus Menschen und die Mauer-Varianten.

Regel der Komposition: das BAUBAND bleibt frei. Die neun Bauplaetze liegen
laut data/city_layout.json ("buildings") bei x 0.23-0.77, y 0.475-0.80 -
dort darf nur Boden, Weg und flaches Detail liegen. Fraktionscharakter
kommt in das leere obere Drittel (y < 0.34) und in den Rahmen. Ein erster
Entwurf hatte Ringstrasse und Plaza-Baum mitten auf den Bauplaetzen; das
Gebaeude-Sprite waere in die Baumkrone gewachsen.
"""
import math, random

W, H = 1080, 1600
PLOTS = [
    ("Kapelle", 0.33, 0.475), ("Zitadelle", 0.67, 0.475),
    ("Schmiede", 0.29, 0.535), ("Reiterei", 0.71, 0.535),
    ("Markt", 0.23, 0.645), ("Wachturm", 0.77, 0.645),
    ("Kaserne", 0.36, 0.72), ("Spaeher", 0.64, 0.72),
    ("Stadtmauer", 0.50, 0.80),
]
# Luecken zwischen den Bauplatz-Reihen - hier duerfen Wege laufen.
LANES = [0.415, 0.590, 0.683, 0.762, 0.870]
SPINE_X = 0.50


def region(rng, cx, cy, rx, ry, points=11, jitter=0.16):
    """Weiche, unregelmaessige geschlossene Flaeche."""
    pts = []
    for i in range(points):
        a = i * math.tau / points
        f = 1.0 + rng.uniform(-jitter, jitter)
        pts.append((cx + math.cos(a) * rx * f, cy + math.sin(a) * ry * f))
    d = [f"M {pts[0][0]:.0f} {pts[0][1]:.0f}"]
    for i in range(points):
        p, n = pts[i], pts[(i + 1) % points]
        mx, my = (p[0] + n[0]) / 2.0, (p[1] + n[1]) / 2.0
        d.append(f"Q {p[0]:.0f} {p[1]:.0f} {mx:.0f} {my:.0f}")
    d.append("Z")
    return " ".join(d)


def lit_region(rng, cx, cy, rx, ry, base, light, shade, points=11, jitter=0.16, op=1.0):
    """Flaeche mit Licht oben-links und Schatten unten-rechts."""
    d = region(rng, cx, cy, rx, ry, points, jitter)
    return "\n".join([
        f'<path d="{d}" fill="{shade}" opacity="{op:.2f}" transform="translate(10 12)"/>',
        f'<path d="{d}" fill="{base}" opacity="{op:.2f}"/>',
        f'<path d="{d}" fill="{light}" opacity="{op*0.5:.2f}" transform="translate(-14 -16)"/>'])


def clump(rng, cx, cy, r, dark, base, light, squash=0.86):
    """Eine Krone / ein Findling mit Schlagschatten und Licht oben-links."""
    return "\n".join([
        f'<ellipse cx="{cx+r*0.14:.0f}" cy="{cy+r*0.16:.0f}" rx="{r*1.03:.0f}" ry="{r*squash:.0f}" fill="{dark}" opacity="0.6"/>',
        f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="{r:.0f}" ry="{r*squash:.0f}" fill="{base}"/>',
        f'<ellipse cx="{cx-r*0.30:.0f}" cy="{cy-r*0.32:.0f}" rx="{r*0.46:.0f}" ry="{r*0.38:.0f}" fill="{light}" opacity="0.72"/>'])


def frame_band(rng, dark, base, light, n_side=17, n_top=15, r0=40, r1=92):
    """Rahmen aus gestaffelten Silhouetten: links, rechts, unten, oben.
    Bleibt bewusst ausserhalb x 0.12-0.88 im Bauband."""
    out = []
    for row in range(3):
        t = row / 2.0
        for side in (0, 1):
            for _ in range(n_side):
                yy = rng.uniform(-40, H + 40)
                # im Bauband weiter nach aussen ruecken
                inner = 0.115 if 0.40 * H < yy < 0.90 * H else 0.175
                xx = (rng.uniform(-40, W * inner) if side == 0
                      else rng.uniform(W * (1 - inner), W + 40))
                xx += (1 if side else -1) * t * 44
                r = rng.uniform(r0, r1) * (0.72 + 0.42 * (1 - t))
                out.append(clump(rng, xx, yy, r, dark, base, light))
    for row in range(3):
        t = row / 2.0
        for _ in range(n_top):
            out.append(clump(rng, rng.uniform(-40, W + 40),
                             rng.uniform(-50, H * 0.10) + t * 46,
                             rng.uniform(r0, r1) * (0.7 + 0.4 * (1 - t)),
                             dark, base, light))
        for _ in range(n_top):
            out.append(clump(rng, rng.uniform(-40, W + 40),
                             rng.uniform(H * 0.94, H + 60) - t * 46,
                             rng.uniform(r0, r1) * (0.8 + 0.4 * t),
                             dark, base, light))
    return "\n".join(out)


def streets(rng, edge, fill, w_main=24, w_lane=14, crossing=None):
    """Wegenetz in den Luecken: eine geschwungene Hauptachse und Querwege
    zwischen den Bauplatz-Reihen. Beruehrt keinen Bauplatz.
    Die Querwege sind bewusst unterschiedlich lang, versetzt und gebogen -
    gleich lange Parallelen lesen sich als Leiter, nicht als Stadt."""
    paths = []
    sx = SPINE_X * W
    paths.append((f"M {sx-26:.0f} {H*0.30:.0f} C {sx+32:.0f} {H*0.44:.0f} "
                  f"{sx-30:.0f} {H*0.62:.0f} {sx+16:.0f} {H*0.78:.0f} "
                  f"S {sx-12:.0f} {H*0.94:.0f} {sx+4:.0f} {H+60:.0f}", w_main))
    # (Spannweite links, Spannweite rechts) je Luecke - absichtlich unsymmetrisch
    spans = [(0.30, 0.24), (0.36, 0.34), (0.26, 0.35), (0.33, 0.25), (0.22, 0.28)]
    for i, ly in enumerate(LANES):
        y = ly * H
        sl, sr = spans[i]
        x0, x1 = W * (0.5 - sl), W * (0.5 + sr)
        bow = rng.uniform(28, 52) * (1 if i % 2 else -1)
        paths.append((f"M {x0:.0f} {y+rng.uniform(-14,14):.0f} "
                      f"Q {(x0+x1)/2:.0f} {y+bow:.0f} {x1:.0f} {y+rng.uniform(-14,14):.0f}",
                      w_lane * rng.uniform(0.8, 1.25)))
    out = []
    for d, wd in paths:
        out.append(f'<path d="{d}" fill="none" stroke="{edge}" stroke-width="{wd+10:.0f}" stroke-linecap="round"/>')
    for d, wd in paths:
        out.append(f'<path d="{d}" fill="none" stroke="{fill}" stroke-width="{wd:.0f}" stroke-linecap="round"/>')
    if crossing:
        cx, cy = SPINE_X * W, LANES[1] * H
        out.append(f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="86" ry="42" fill="{crossing[0]}"/>')
        out.append(f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="86" ry="42" fill="none" stroke="{crossing[1]}" stroke-width="4"/>')
        out.append(f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="46" ry="23" fill="none" stroke="{crossing[1]}" stroke-width="3" opacity="0.8"/>')
        for k in range(12):
            a = k * math.tau / 12.0
            out.append(f'<line x1="{cx+math.cos(a)*46:.0f}" y1="{cy+math.sin(a)*23:.0f}" '
                       f'x2="{cx+math.cos(a)*86:.0f}" y2="{cy+math.sin(a)*42:.0f}" '
                       f'stroke="{crossing[1]}" stroke-width="2.5" opacity="0.55"/>')
    return "\n".join(out)



def apron(rng, y, base, light, shade, h=110):
    """Irregulaere Gelaendeschuerze - begraebt die geraden Unterkanten von
    Kamm- und Kegelpolygonen im Boden."""
    return lit_region(rng, W * 0.5, y, W * 0.72, h, base, light, shade, 17, 0.22)


def ground_detail(rng, n, cols, r0=6, r1=16):
    """Kleinkram im Bauband - flach, damit Gebaeude-Sprites davor lesbar sind."""
    out = []
    for _ in range(n):
        x = rng.uniform(W * 0.10, W * 0.90)
        y = rng.uniform(H * 0.40, H * 0.90)
        r = rng.uniform(r0, r1)
        c = rng.choice(cols)
        out.append(f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{r:.0f}" ry="{r*0.5:.0f}" '
                   f'fill="{c}" opacity="{rng.uniform(0.25, 0.6):.2f}"/>')
    return "\n".join(out)


DEFS = """  <defs>
    <linearGradient id="ground" x1="0.15" y1="0" x2="0.85" y2="1">
      <stop offset="0%" stop-color="{g0}"/>
      <stop offset="55%" stop-color="{g1}"/>
      <stop offset="100%" stop-color="{g2}"/>
    </linearGradient>
    <radialGradient id="vig" cx="50%" cy="45%" r="78%">
      <stop offset="0%" stop-color="#000" stop-opacity="0"/>
      <stop offset="58%" stop-color="#000" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0.55"/>
    </radialGradient>
    <radialGradient id="daylight" cx="18%" cy="10%" r="95%">
      <stop offset="0%" stop-color="{sun}" stop-opacity="{sunop}"/>
      <stop offset="55%" stop-color="{sun}" stop-opacity="{sunop2}"/>
      <stop offset="100%" stop-color="{sun}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="pglow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{pg}" stop-opacity="{pgop}"/>
      <stop offset="100%" stop-color="{pg}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="band" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#fff" stop-opacity="0.13"/>
      <stop offset="45%" stop-color="#fff" stop-opacity="0.05"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0.16"/>
    </linearGradient>
    <filter id="soft" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="30"/></filter>
    <filter id="soft2" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="10"/></filter>
    <filter id="mist" x="-70%" y="-70%" width="240%" height="240%"><feGaussianBlur stdDeviation="40"/></filter>
    <filter id="grain" x="-5%" y="-5%" width="110%" height="110%">
      <feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves="3" seed="{seed}" result="n"/>
      <feColorMatrix in="n" type="saturate" values="0"/>
    </filter>
  </defs>"""


# ---------------------------------------------------------------- Waldvolk

def waldvolk():
    rng = random.Random(101)
    pal = dict(g0="#3f6130", g1="#35532b", g2="#24401f", sun="#ffe6a6",
               sunop="0.26", sunop2="0.07", pg="#ffe6a6", pgop="0.30",
               wall_stone="#7d6a44", wall_dark="#3a3020", wall_light="#a8935f")
    s = ['<rect x="0" y="0" width="1080" height="1600" fill="url(#ground)"/>']
    # Lichtung: helle Flaeche unter dem Bauband
    s.append(lit_region(rng, W*0.50, H*0.655, W*0.44, H*0.275, "#5f8d3d", "#79a750", "#2c4a20", 19, 0.15))
    for cx, cy, rx, ry in [(W*0.24, H*0.50, 120, 74), (W*0.76, H*0.52, 112, 70),
                           (W*0.22, H*0.75, 104, 66), (W*0.78, H*0.74, 108, 68),
                           (W*0.50, H*0.885, 210, 62)]:
        s.append(lit_region(rng, cx, cy, rx, ry, "#6d9946", "#86b059", "#3d6127", 9, 0.20, 0.7))
    # Bach am linken Rand, laeuft an den Bauplaetzen vorbei
    s.append('<path d="M 84 -40 C 130 260 42 520 96 760 C 140 960 60 1200 108 1660" '
             'fill="none" stroke="#2b4a52" stroke-width="46" stroke-linecap="round" opacity="0.85"/>')
    s.append('<path d="M 84 -40 C 130 260 42 520 96 760 C 140 960 60 1200 108 1660" '
             'fill="none" stroke="#6fb3bd" stroke-width="26" stroke-linecap="round" opacity="0.75"/>')
    s.append(streets(rng, "#8a7748", "#dcc98f", crossing=("#cdbb8b", "#8a7a4f")))
    # Rahmen: Waldrand
    s.append(frame_band(rng, "#1a2f16", "#2d5424", "#4a7d35"))
    # Wahrzeichen: Uraltbaum im leeren oberen Drittel
    s.append(great_tree())
    s.append(ground_detail(rng, 64, ["#8fbf66", "#4d7a33", "#c9d98a"]))
    return "\n".join(s), 3, pal


def great_tree():
    tx, ty = W*0.50, H*0.285
    out = [f'<ellipse cx="{tx+30:.0f}" cy="{ty+250:.0f}" rx="330" ry="86" fill="#16290f" opacity="0.45" filter="url(#soft)"/>']
    # Wurzelfaecher nach unten
    for dx in (-210, -120, -46, 40, 128, 214):
        out.append(f'<path d="M {tx+dx*0.30:.0f} {ty+150:.0f} Q {tx+dx*0.8:.0f} {ty+220:.0f} {tx+dx:.0f} {ty+268:.0f}" '
                   f'fill="none" stroke="#4d3a20" stroke-width="{22 if abs(dx)>150 else 30}" stroke-linecap="round"/>')
    out.append(f'<path d="M {tx-72:.0f} {ty+262:.0f} q 20 -150 -8 -246 q 86 -34 156 0 q -28 96 -6 246 Z" fill="#5c4527"/>')
    out.append(f'<path d="M {tx-72:.0f} {ty+262:.0f} q 20 -150 -8 -246 q 40 -16 74 -8 q -18 118 -6 254 Z" fill="#75593a" opacity="0.8"/>')
    # Kronen-Scheitel muss oberhalb y=0 bleiben: ty 456 minus 208 minus
    # Radius 138 = 110. Vorher lag ty bei 392 und der Scheitel bei -8, die
    # Krone war im Spiel oben abgeschnitten.
    canopy = [(-196, -66, 108, "#274b1f"), (186, -50, 100, "#274b1f"),
              (-98, -150, 124, "#356629"), (102, -160, 120, "#356629"),
              (0, -208, 138, "#417a31"), (-188, -174, 88, "#2e5824"),
              (178, -182, 84, "#2e5824"), (-38, -86, 116, "#3b7130"), (62, -78, 108, "#3b7130")]
    for dx, dy, r, c in canopy:
        out.append(f'<ellipse cx="{tx+dx+14:.0f}" cy="{ty+dy+16:.0f}" rx="{r*1.02:.0f}" ry="{r*0.84:.0f}" fill="#16300f" opacity="0.5"/>')
    for dx, dy, r, c in canopy:
        out.append(f'<ellipse cx="{tx+dx:.0f}" cy="{ty+dy:.0f}" rx="{r:.0f}" ry="{r*0.82:.0f}" fill="{c}"/>')
    for dx, dy, r, _ in canopy[:6]:
        out.append(f'<ellipse cx="{tx+dx-r*0.32:.0f}" cy="{ty+dy-r*0.34:.0f}" rx="{r*0.44:.0f}" ry="{r*0.34:.0f}" '
                   f'fill="#6fa74b" opacity="0.55"/>')
    return "\n".join(out)


# -------------------------------------------------------------- Totenreich

def totenreich():
    rng = random.Random(202)
    pal = dict(g0="#3d3849", g1="#332f40", g2="#242131", sun="#c3b2e0",
               sunop="0.16", sunop2="0.05", pg="#7dffb0", pgop="0.36",
               wall_stone="#605a75", wall_dark="#231f30", wall_light="#8b85a0")
    s = ['<rect x="0" y="0" width="1080" height="1600" fill="url(#ground)"/>']
    s.append(lit_region(rng, W*0.50, H*0.655, W*0.44, H*0.275, "#4e4760", "#605874", "#2a2635", 19, 0.15))
    for cx, cy, rx, ry in [(W*0.24, H*0.50, 118, 72), (W*0.76, H*0.52, 112, 70),
                           (W*0.22, H*0.75, 104, 64), (W*0.78, H*0.74, 106, 66),
                           (W*0.50, H*0.885, 206, 60)]:
        s.append(lit_region(rng, cx, cy, rx, ry, "#585070", "#6b6383", "#332f3f", 9, 0.20, 0.65))
    # Risse - nur in den Wegluecken, nicht auf den Bauplaetzen
    for ly in LANES:
        for _ in range(5):
            x0 = rng.uniform(W*0.14, W*0.86); y0 = ly*H + rng.uniform(-26, 26)
            d = [f"M {x0:.0f} {y0:.0f}"]; cx0, cy0 = x0, y0
            for _ in range(4):
                cx0 += rng.uniform(-70, 70); cy0 += rng.uniform(-22, 22)
                d.append(f"L {cx0:.0f} {cy0:.0f}")
            s.append(f'<path d="{" ".join(d)}" fill="none" stroke="#1d1a28" stroke-width="4" opacity="0.6"/>')
    s.append(streets(rng, "#4a4459", "#a9a2b8", crossing=("#8f8aa2", "#5b5570")))
    # Grabsteine + tote Baeume als Rahmen
    s.append(frame_band(rng, "#191627", "#2a2639", "#3f3a52", n_side=13, n_top=11, r0=34, r1=74))
    s.append(graveyard(rng))
    s.append(bone_gate())
    # Bodennebel in den Luecken
    for ly in LANES:
        s.append(f'<ellipse cx="{W*0.5:.0f}" cy="{ly*H:.0f}" rx="{W*0.52:.0f}" ry="42" '
                 f'fill="#cfe8d8" opacity="0.10" filter="url(#mist)"/>')
    s.append(ground_detail(rng, 46, ["#8c86a0", "#2a2636", "#6f6a84"]))
    return "\n".join(s), 7, pal


def graveyard(rng):
    """Grabsteine in Reihen an den Raendern, jeder mit Bodenschatten -
    frei gestreute Pillen sahen aus, als schwebten sie."""
    out = []
    for side in (0, 1):
        for col in range(2):
            for k in range(9):
                yy = H * 0.06 + k * (H * 0.105) + rng.uniform(-24, 24)
                inner = 0.10 if 0.40 * H < yy < 0.90 * H else 0.165
                base_x = W * (inner * (0.35 + 0.55 * col)) if side == 0 \
                    else W * (1 - inner * (0.35 + 0.55 * col))
                xx = base_x + rng.uniform(-16, 16)
                hgt = rng.uniform(52, 96) * (0.8 + 0.3 * col)
                wid = hgt * rng.uniform(0.44, 0.58)
                tilt = rng.uniform(-10, 10)
                out.append(
                    f'<ellipse cx="{xx:.0f}" cy="{yy+4:.0f}" rx="{wid*0.8:.0f}" ry="{wid*0.26:.0f}" fill="#15121f" opacity="0.55"/>'
                    f'<g transform="rotate({tilt:.1f} {xx:.0f} {yy:.0f})">'
                    f'<path d="M {xx-wid/2:.0f} {yy:.0f} L {xx-wid/2:.0f} {yy-hgt+wid*0.5:.0f} '
                    f'a {wid*0.5:.0f} {wid*0.5:.0f} 0 0 1 {wid:.0f} 0 L {xx+wid/2:.0f} {yy:.0f} Z" fill="#605a75"/>'
                    f'<path d="M {xx-wid/2:.0f} {yy:.0f} L {xx-wid/2:.0f} {yy-hgt+wid*0.5:.0f} '
                    f'a {wid*0.5:.0f} {wid*0.5:.0f} 0 0 1 {wid*0.4:.0f} {-wid*0.32:.0f} '
                    f'L {xx-wid*0.1:.0f} {yy:.0f} Z" fill="#7d7791" opacity="0.85"/>'
                    f'<rect x="{xx-wid*0.30:.0f}" y="{yy-hgt*0.62:.0f}" width="{wid*0.6:.0f}" height="5" rx="2" fill="#3f3a52" opacity="0.8"/>'
                    f'</g>')
    return "\n".join(out)


def bone_gate():
    gx, gy = W*0.50, H*0.255
    out = [f'<ellipse cx="{gx:.0f}" cy="{gy+40:.0f}" rx="360" ry="230" fill="url(#pglow)"/>',
           f'<ellipse cx="{gx+26:.0f}" cy="{gy+236:.0f}" rx="300" ry="72" fill="#151221" opacity="0.55" filter="url(#soft)"/>']
    # Mausoleumsblock
    out.append(f'<path d="M {gx-250:.0f} {gy+230:.0f} L {gx-190:.0f} {gy-40:.0f} L {gx+190:.0f} {gy-40:.0f} '
               f'L {gx+250:.0f} {gy+230:.0f} Z" fill="#3a3550"/>')
    out.append(f'<path d="M {gx-250:.0f} {gy+230:.0f} L {gx-190:.0f} {gy-40:.0f} L {gx-30:.0f} {gy-40:.0f} '
               f'L {gx-60:.0f} {gy+230:.0f} Z" fill="#4a4466" opacity="0.85"/>')
    out.append(f'<path d="M {gx-206:.0f} {gy-40:.0f} L {gx:.0f} {gy-186:.0f} L {gx+206:.0f} {gy-40:.0f} Z" fill="#4f4869"/>')
    out.append(f'<path d="M {gx-206:.0f} {gy-40:.0f} L {gx:.0f} {gy-186:.0f} L {gx:.0f} {gy-40:.0f} Z" fill="#5f577e" opacity="0.8"/>')
    out.append(f'<path d="M {gx-296:.0f} {gy+248:.0f} L {gx-262:.0f} {gy+196:.0f} L {gx+262:.0f} {gy+196:.0f} L {gx+296:.0f} {gy+248:.0f} Z" fill="#2f2b42"/>')
    out.append(f'<rect x="{gx-262:.0f}" y="{gy+186:.0f}" width="524" height="14" rx="5" fill="#5b5474"/>')
    # Torbogen mit Gruenfeuer
    out.append(f'<path d="M {gx-84:.0f} {gy+230:.0f} L {gx-84:.0f} {gy+40:.0f} a 84 96 0 0 1 168 0 L {gx+84:.0f} {gy+230:.0f} Z" fill="#12101c"/>')
    out.append(f'<path d="M {gx-58:.0f} {gy+230:.0f} L {gx-58:.0f} {gy+52:.0f} a 58 68 0 0 1 116 0 L {gx+58:.0f} {gy+230:.0f} Z" fill="#7dffb0" opacity="0.30"/>')
    out.append(f'<ellipse cx="{gx:.0f}" cy="{gy+150:.0f}" rx="66" ry="96" fill="#7dffb0" opacity="0.35" filter="url(#soft2)"/>')
    # Saeulen
    for dx in (-206, 206):
        out.append(f'<rect x="{gx+dx-22:.0f}" y="{gy-30:.0f}" width="44" height="262" rx="10" fill="#565073"/>')
        out.append(f'<rect x="{gx+dx-22:.0f}" y="{gy-30:.0f}" width="16" height="262" rx="8" fill="#6d6690" opacity="0.8"/>')
        out.append(f'<circle cx="{gx+dx:.0f}" cy="{gy-52:.0f}" r="26" fill="#7dffb0" opacity="0.55" filter="url(#soft2)"/>')
        out.append(f'<circle cx="{gx+dx:.0f}" cy="{gy-52:.0f}" r="12" fill="#d8ffe8"/>')
    return "\n".join(out)


# -------------------------------------------------------------------- Orks

def orks():
    rng = random.Random(303)
    pal = dict(g0="#7c6135", g1="#6b5230", g2="#4a3a22", sun="#ffcf8a",
               sunop="0.22", sunop2="0.06", pg="#ff8a2c", pgop="0.40",
               wall_stone="#8a6c3d", wall_dark="#2b2011", wall_light="#b08c52")
    s = ['<rect x="0" y="0" width="1080" height="1600" fill="url(#ground)"/>']
    s.append(lit_region(rng, W*0.50, H*0.655, W*0.44, H*0.275, "#816538", "#9a7c47", "#4c3a20", 19, 0.15))
    for cx, cy, rx, ry in [(W*0.24, H*0.50, 118, 72), (W*0.76, H*0.52, 112, 70),
                           (W*0.22, H*0.75, 104, 64), (W*0.78, H*0.74, 106, 66),
                           (W*0.50, H*0.885, 206, 60)]:
        s.append(lit_region(rng, cx, cy, rx, ry, "#8d6f3f", "#a6854d", "#59431f", 9, 0.20, 0.65))
    # ausgetretene Erde entlang der Wege
    for ly in LANES:
        s.append(lit_region(rng, W*0.5, ly*H, W*0.42, 46, "#6d5329", "#7d6132", "#4a3819", 11, 0.22, 0.55))
    s.append(streets(rng, "#5b4523", "#b79055", crossing=("#a8834b", "#5b4523")))
    # Palisade + Findlinge als Rahmen
    s.append(frame_band(rng, "#2b2011", "#4a3a20", "#6b5530", n_side=11, n_top=9, r0=36, r1=78))
    s.append(palisade(rng))
    s.append(volcano_forge())
    # Feuerstellen in den Luecken
    for lx, ly in [(0.19, 0.59), (0.81, 0.59), (0.30, 0.87), (0.70, 0.87)]:
        cx, cy = lx*W, ly*H
        s.append(f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="54" ry="30" fill="#ff8a2c" opacity="0.28" filter="url(#soft2)"/>')
        s.append(f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="30" ry="16" fill="#3a2a13"/>')
        s.append(f'<ellipse cx="{cx:.0f}" cy="{cy-3:.0f}" rx="18" ry="9" fill="#ff9c3d"/>')
        s.append(f'<ellipse cx="{cx:.0f}" cy="{cy-5:.0f}" rx="9" ry="5" fill="#ffe0a0"/>')
    s.append(ground_detail(rng, 80, ["#c39a5c", "#4a3819", "#8f7a4a"]))
    return "\n".join(s), 11, pal


def palisade(rng):
    out = []
    for _ in range(34):
        yy = rng.uniform(-20, H + 20)
        inner = 0.10 if 0.40 * H < yy < 0.90 * H else 0.165
        side = rng.random() < 0.5
        xx = rng.uniform(4, W*inner) if side else rng.uniform(W*(1-inner), W-4)
        hgt = rng.uniform(70, 140); wid = rng.uniform(18, 28)
        tilt = rng.uniform(-11, 11)
        out.append(f'<g transform="rotate({tilt:.1f} {xx:.0f} {yy:.0f})">'
                   f'<path d="M {xx-wid/2+7:.0f} {yy+8:.0f} L {xx-wid/2+7:.0f} {yy-hgt+22:.0f} '
                   f'L {xx+7:.0f} {yy-hgt+8:.0f} L {xx+wid/2+7:.0f} {yy-hgt+22:.0f} L {xx+wid/2+7:.0f} {yy+8:.0f} Z" fill="#221909" opacity="0.6"/>'
                   f'<path d="M {xx-wid/2:.0f} {yy:.0f} L {xx-wid/2:.0f} {yy-hgt+14:.0f} '
                   f'L {xx:.0f} {yy-hgt:.0f} L {xx+wid/2:.0f} {yy-hgt+14:.0f} L {xx+wid/2:.0f} {yy:.0f} Z" fill="#5d4726"/>'
                   f'<rect x="{xx-wid/2:.0f}" y="{yy-hgt+14:.0f}" width="{wid*0.34:.0f}" height="{hgt-14:.0f}" fill="#7a5f34" opacity="0.75"/>'
                   f'</g>')
    return "\n".join(out)


def volcano_forge():
    """Kaldera statt Pyramide. Der erste Versuch war ein Dreieck mit
    geraden Lavastrahlen - das las sich als Pyramide mit Laserstrahlen.
    Jetzt: unregelmaessiger Kamm im Hintergrund, davor ein Kegel mit
    Kraterkerbe, Lava laeuft NACH UNTEN und faechert sich auf."""
    vx, vy = W * 0.50, H * 0.30
    rim_y = vy - 168
    out = [f'<ellipse cx="{vx:.0f}" cy="{vy-40:.0f}" rx="440" ry="280" fill="url(#pglow)"/>']
    # Hintergrundkamm - zackig, aber nicht symmetrisch
    ridge = "M -60 %.0f" % (vy + 240)
    for x, y in [(40, vy + 96), (150, vy + 150), (250, vy + 40), (340, vy + 118),
                 (430, vy + 20), (640, vy + 36), (740, vy + 130), (830, vy + 54),
                 (930, vy + 146), (1010, vy + 70), (1140, vy + 240)]:
        ridge += " L %.0f %.0f" % (x, y)
    out.append(f'<path d="{ridge} Z" fill="#33270f" opacity="0.95"/>')
    # Kegel: linke Flanke heller (Licht oben-links)
    cone_l = f"M {vx-330:.0f} {vy+250:.0f} L {vx-190:.0f} {rim_y+92:.0f} L {vx-96:.0f} {rim_y+8:.0f} L {vx-30:.0f} {rim_y-8:.0f} L {vx:.0f} {vy+250:.0f} Z"
    cone_r = f"M {vx:.0f} {vy+250:.0f} L {vx-30:.0f} {rim_y-8:.0f} L {vx+86:.0f} {rim_y+16:.0f} L {vx+206:.0f} {rim_y+110:.0f} L {vx+346:.0f} {vy+250:.0f} Z"
    out.append(f'<path d="{cone_r}" fill="#41321a"/>')
    out.append(f'<path d="{cone_l}" fill="#57431f"/>')
    # Kraterkerbe
    out.append(f'<path d="M {vx-96:.0f} {rim_y+8:.0f} Q {vx-30:.0f} {rim_y+34:.0f} {vx+86:.0f} {rim_y+16:.0f} '
               f'Q {vx-10:.0f} {rim_y+62:.0f} {vx-96:.0f} {rim_y+8:.0f} Z" fill="#2a1f0c"/>')
    out.append(f'<ellipse cx="{vx-6:.0f}" cy="{rim_y+30:.0f}" rx="88" ry="24" fill="#ff7a1e" opacity="0.85"/>')
    out.append(f'<ellipse cx="{vx-6:.0f}" cy="{rim_y+30:.0f}" rx="46" ry="12" fill="#ffe0a0"/>')
    out.append(f'<ellipse cx="{vx-6:.0f}" cy="{rim_y+26:.0f}" rx="130" ry="52" fill="#ff7a1e" opacity="0.45" filter="url(#soft2)"/>')
    # Lavastroeme: oben schmal, nach unten breiter und kuehler - gleich
    # dicke Striche lasen sich als Schlaeuche.
    def flow(x0, x1, wtop, wbot, bow):
        y0, y1 = rim_y + 34, vy + 250
        my = (y0 + y1) * 0.5
        mx = (x0 + x1) * 0.5 + bow
        left = (f"M {x0-wtop/2:.0f} {y0:.0f} Q {mx-wtop*0.8:.0f} {my:.0f} {x1-wbot/2:.0f} {y1:.0f}")
        right = (f"L {x1+wbot/2:.0f} {y1:.0f} Q {mx+wtop*0.8:.0f} {my:.0f} {x0+wtop/2:.0f} {y0:.0f} Z")
        core_l = (f"M {x0-wtop*0.2:.0f} {y0:.0f} Q {mx-wtop*0.3:.0f} {my:.0f} {x1-wbot*0.22:.0f} {y1-16:.0f}")
        core_r = (f"L {x1+wbot*0.22:.0f} {y1-16:.0f} Q {mx+wtop*0.3:.0f} {my:.0f} {x0+wtop*0.2:.0f} {y0:.0f} Z")
        return (f'<path d="{left} {right}" fill="#8c3308" opacity="0.95"/>'
                f'<path d="{left} {right}" fill="#ff7a1e" opacity="0.85" transform="translate(0 -4)"/>'
                f'<path d="{core_l} {core_r}" fill="#ffd18a" opacity="0.75"/>')
    out.append(flow(vx-40, vx-124, 14, 40, -18))
    out.append(flow(vx+4, vx+22, 22, 62, 6))
    out.append(flow(vx+46, vx+132, 12, 34, 24))
    out.append(apron(random.Random(77), vy + 268, "#6d5329", "#7b6034", "#43331a", 96))
    # Glutbecken am Fuss
    out.append(f'<ellipse cx="{vx:.0f}" cy="{vy+250:.0f}" rx="250" ry="34" fill="#ff7a1e" opacity="0.35" filter="url(#soft2)"/>')
    # Rauch ueber dem Krater
    for k, (dy, r, op) in enumerate([(-90, 110, 0.20), (-180, 142, 0.14), (-280, 176, 0.09)]):
        out.append(f'<ellipse cx="{vx + k*46 - 40:.0f}" cy="{rim_y+dy:.0f}" rx="{r}" ry="{r*0.58:.0f}" '
                   f'fill="#b3a894" opacity="{op}" filter="url(#mist)"/>')
    # Schmiedehalle davor, aus der Kaldera gespeist
    hx, hy = vx, vy + 214
    out.append(f'<ellipse cx="{hx+18:.0f}" cy="{hy+62:.0f}" rx="210" ry="42" fill="#241a09" opacity="0.55" filter="url(#soft2)"/>')
    out.append(f'<path d="M {hx-180:.0f} {hy+58:.0f} L {hx-150:.0f} {hy-52:.0f} L {hx+150:.0f} {hy-52:.0f} '
               f'L {hx+180:.0f} {hy+58:.0f} Z" fill="#33260f"/>')
    out.append(f'<path d="M {hx-180:.0f} {hy+58:.0f} L {hx-150:.0f} {hy-52:.0f} L {hx-16:.0f} {hy-52:.0f} '
               f'L {hx-40:.0f} {hy+58:.0f} Z" fill="#48371a" opacity="0.9"/>')
    out.append(f'<path d="M {hx-166:.0f} {hy-52:.0f} L {hx:.0f} {hy-116:.0f} L {hx+166:.0f} {hy-52:.0f} Z" fill="#3d2e13"/>')
    out.append(f'<path d="M {hx-52:.0f} {hy+58:.0f} L {hx-52:.0f} {hy-16:.0f} a 52 40 0 0 1 104 0 L {hx+52:.0f} {hy+58:.0f} Z" fill="#ff8a2c" opacity="0.75"/>')
    out.append(f'<ellipse cx="{hx:.0f}" cy="{hy+30:.0f}" rx="58" ry="42" fill="#ffe0a0" opacity="0.55" filter="url(#soft2)"/>')
    for dx in (-150, 150):
        out.append(f'<rect x="{hx+dx-14:.0f}" y="{hy-96:.0f}" width="28" height="156" rx="6" fill="#2c2109"/>')
        out.append(f'<ellipse cx="{hx+dx:.0f}" cy="{hy-104:.0f}" rx="20" ry="14" fill="#ff8a2c" opacity="0.9"/>')
    return "\n".join(out)




def svg_doc(body, seed, pal, walled=False):
    """Vollflaechiges SVG 1080x1600. Der CityScreen zeichnet es als
    draw_texture_rect ueber die ganze Buehne, deshalb keine Transparenz und
    kein Rand."""
    parts = [DEFS.format(seed=seed, **pal), body]
    if walled:
        parts.append(wall_ring(pal))
    # Licht, Vignette und Korn zuletzt - genau wie im Entwurf.
    parts.append('<rect x="0" y="0" width="1080" height="1600" fill="url(#daylight)"/>')
    parts.append('<rect x="0" y="0" width="1080" height="1600" fill="url(#vig)"/>')
    parts.append('<rect x="0" y="0" width="1080" height="1600" filter="url(#grain)" '
                 'opacity="0.05" style="mix-blend-mode: overlay;"/>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!-- Erzeugt von tools/gen_city_bg.py - nicht von Hand editieren. -->\n'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1600" '
            'width="1080" height="1600">\n' + "\n".join(parts) + '\n</svg>\n')


def wall_ring(pal):
    """Mauerring um das Bauband - die bg_walled-Variante. CityScreen nimmt
    sie, sobald "mauer" gebaut ist (siehe CityScreen._draw, has_wall).
    Bisher hatte das nur Menschen als PNG; jetzt alle vier.

    Der Ring MUSS aussen um x 0.12-0.88 / y 0.42-0.88 herumlaufen, sonst
    liegt Mauerwerk auf einem Bauplatz."""
    rng = random.Random(4242)
    stone = pal["wall_stone"]
    dark = pal["wall_dark"]
    light = pal["wall_light"]
    out = []
    # Ring als unregelmaessige Bahn: aussen dunkel, innen hell (Licht
    # oben-links), damit er zum Rest der Beleuchtung passt.
    ring = region(rng, W * 0.5, H * 0.655, W * 0.475, H * 0.305, points=15, jitter=0.05)
    out.append(f'<path d="{ring}" fill="none" stroke="{dark}" stroke-width="76" stroke-linejoin="round"/>')
    out.append(f'<path d="{ring}" fill="none" stroke="{stone}" stroke-width="58" stroke-linejoin="round"/>')
    out.append(f'<path d="{ring}" fill="none" stroke="{light}" stroke-width="16" '
               f'stroke-linejoin="round" opacity="0.55" transform="translate(-7 -8)"/>')
    # Zinnen als gestrichelte Linie AUF dem Ringpfad. Erster Versuch setzte
    # 46 Rechtecke auf eine perfekte Ellipse - der Ring selbst ist aber
    # unregelmaessig, also lagen die Bloecke daneben und lasen sich als
    # Perlenkette. Ein Strich auf demselben Pfad kann nicht verrutschen.
    out.append(f'<path d="{ring}" fill="none" stroke="{stone}" stroke-width="88" '
               f'stroke-dasharray="26 22" stroke-linecap="butt" opacity="0.95"/>')
    out.append(f'<path d="{ring}" fill="none" stroke="{dark}" stroke-width="88" '
               f'stroke-dasharray="2 46" stroke-linecap="butt" opacity="0.45"/>')
    # Torturm unten in der Mitte, wo die Hauptachse das Bauband verlaesst.
    gx, gy = W * 0.5, H * 0.655 + H * 0.305
    out.append(f'<rect x="{gx-92:.0f}" y="{gy-74:.0f}" width="184" height="120" rx="8" '
               f'fill="{stone}" stroke="{dark}" stroke-width="6"/>')
    out.append(f'<rect x="{gx-92:.0f}" y="{gy-74:.0f}" width="62" height="120" rx="8" '
               f'fill="{light}" opacity="0.35"/>')
    out.append(f'<path d="M {gx-40:.0f} {gy+46:.0f} L {gx-40:.0f} {gy-14:.0f} '
               f'a 40 34 0 0 1 80 0 L {gx+40:.0f} {gy+46:.0f} Z" fill="{dark}"/>')
    return "\n".join(out)



# --------------------------------------------------------------- Menschen

def menschen():
    """Sandstein-Hof mit Burgfried. Ersetzt das gemalte Canva-PNG: der
    Nutzer wollte alle vier Staedte aus einer Hand, und das eine gemalte
    Bild passte stilistisch zu keinem anderen Screen im Spiel."""
    rng = random.Random(404)
    pal = dict(g0="#6f6146", g1="#61543d", g2="#463c2b", sun="#ffeec2",
               sunop="0.30", sunop2="0.09", pg="#ffe6a6", pgop="0.32",
               wall_stone="#9b8660", wall_dark="#463a24", wall_light="#c4ad7d")
    s = ['<rect x="0" y="0" width="1080" height="1600" fill="url(#ground)"/>']
    # Gepflasterter Hof unter dem Bauband
    s.append(lit_region(rng, W*0.50, H*0.655, W*0.44, H*0.275,
                        "#8a7a5a", "#a39270", "#4b4130", 19, 0.15))
    for cx, cy, rx, ry in [(W*0.24, H*0.50, 120, 74), (W*0.76, H*0.52, 112, 70),
                           (W*0.22, H*0.75, 104, 66), (W*0.78, H*0.74, 108, 68),
                           (W*0.50, H*0.885, 210, 62)]:
        s.append(lit_region(rng, cx, cy, rx, ry, "#968563", "#ab9a76", "#5c4f3a", 9, 0.20, 0.7))
    # Pflasterfugen nur in den Wegluecken - nie auf einem Bauplatz.
    for ly in LANES:
        y = ly * H
        for k in range(9):
            x = W * (0.14 + 0.09 * k)
            s.append(f'<line x1="{x:.0f}" y1="{y-26:.0f}" x2="{x+14:.0f}" y2="{y+26:.0f}" '
                     f'stroke="#4b4130" stroke-width="2.5" opacity="0.35"/>')
    s.append(streets(rng, "#7a6a4a", "#d8c9a4", crossing=("#c9b98f", "#7a6a4a")))
    # Rahmen: Hecken und Zypressen statt Wald - Menschen sind kultiviert.
    s.append(frame_band(rng, "#2b3320", "#455230", "#6b7d46", n_side=13, n_top=11,
                        r0=34, r1=76))
    s.append(keep())
    s.append(ground_detail(rng, 56, ["#c9b98f", "#5c4f3a", "#e0d3ae"]))
    return "\n".join(s), 5, pal


def keep():
    """Burgfried im leeren oberen Drittel: Wehrturm mit Nebentuermen,
    Bannern und Torbogen. Endet oberhalb y 540, damit kein Gebaeude-Sprite
    hineinragt (oberste Bauplatz-Reihe liegt bei y 760, Sprite reicht bis
    ~590 hoch)."""
    kx, ky = W * 0.50, H * 0.255
    out = [f'<ellipse cx="{kx+26:.0f}" cy="{ky+236:.0f}" rx="300" ry="70" '
           f'fill="#2e2718" opacity="0.5" filter="url(#soft)"/>']
    # Sockel
    out.append(f'<path d="M {kx-286:.0f} {ky+240:.0f} L {kx-248:.0f} {ky+186:.0f} '
               f'L {kx+248:.0f} {ky+186:.0f} L {kx+286:.0f} {ky+240:.0f} Z" fill="#6f6045"/>')
    # Hauptturm
    out.append(f'<path d="M {kx-104:.0f} {ky+196:.0f} L {kx-88:.0f} {ky-150:.0f} '
               f'L {kx+88:.0f} {ky-150:.0f} L {kx+104:.0f} {ky+196:.0f} Z" fill="#8f7f5e"/>')
    out.append(f'<path d="M {kx-104:.0f} {ky+196:.0f} L {kx-88:.0f} {ky-150:.0f} '
               f'L {kx-8:.0f} {ky-150:.0f} L {kx-16:.0f} {ky+196:.0f} Z" fill="#ab9a76" opacity="0.85"/>')
    # Zinnenkranz
    for k in range(7):
        bx = kx - 92 + k * 31
        out.append(f'<rect x="{bx:.0f}" y="{ky-176:.0f}" width="21" height="30" rx="3" fill="#7d6d4e"/>')
    # Spitzdach
    out.append(f'<path d="M {kx-96:.0f} {ky-176:.0f} L {kx:.0f} {ky-286:.0f} '
               f'L {kx+96:.0f} {ky-176:.0f} Z" fill="#4a5a72"/>')
    out.append(f'<path d="M {kx-96:.0f} {ky-176:.0f} L {kx:.0f} {ky-286:.0f} '
               f'L {kx:.0f} {ky-176:.0f} Z" fill="#5e7290" opacity="0.9"/>')
    # Nebentuerme
    for dx in (-206, 206):
        out.append(f'<rect x="{kx+dx-42:.0f}" y="{ky-56:.0f}" width="84" height="252" rx="6" fill="#847454"/>')
        out.append(f'<rect x="{kx+dx-42:.0f}" y="{ky-56:.0f}" width="30" height="252" rx="6" '
                   f'fill="#a3926f" opacity="0.7"/>')
        out.append(f'<path d="M {kx+dx-52:.0f} {ky-56:.0f} L {kx+dx:.0f} {ky-142:.0f} '
                   f'L {kx+dx+52:.0f} {ky-56:.0f} Z" fill="#4a5a72"/>')
        out.append(f'<path d="M {kx+dx-3:.0f} {ky-142:.0f} l 0 -40 l 46 14 l -46 14 Z" fill="#a8342c"/>')
    # Torbogen
    out.append(f'<path d="M {kx-52:.0f} {ky+196:.0f} L {kx-52:.0f} {ky+46:.0f} '
               f'a 52 46 0 0 1 104 0 L {kx+52:.0f} {ky+196:.0f} Z" fill="#3a3122"/>')
    out.append(f'<path d="M {kx-38:.0f} {ky+196:.0f} L {kx-38:.0f} {ky+56:.0f} '
               f'a 38 34 0 0 1 76 0 L {kx+38:.0f} {ky+196:.0f} Z" fill="#5a4d34"/>')
    # Fenster
    for dy in (-90, -20, 50):
        for dx2 in (-38, 22):
            out.append(f'<rect x="{kx+dx2:.0f}" y="{ky+dy:.0f}" width="16" height="30" rx="7" '
                       f'fill="#2b2418"/>')
    return "\n".join(out)


FACTIONS = {
    "waldvolk": waldvolk,
    "menschen": menschen,
    "totenreich": totenreich,
    "orks": orks,
}


def main():
    import os
    for name, fn in FACTIONS.items():
        body, seed, pal = fn()
        outdir = os.path.join("assets", "city", name)
        os.makedirs(outdir, exist_ok=True)
        for walled in (False, True):
            fname = "bg_walled.svg" if walled else "bg.svg"
            path = os.path.join(outdir, fname)
            with open(path, "w") as f:
                f.write(svg_doc(body, seed, pal, walled))
            print("[OK] %s (%d KB)" % (path, os.path.getsize(path) // 1024))


if __name__ == "__main__":
    main()
