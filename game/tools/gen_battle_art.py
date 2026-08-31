#!/usr/bin/env python3
"""Erzeugt die Schlachtfeld-Grafik als SVG.

    python3 tools/gen_battle_art.py

Schreibt nach assets/battle/:
  ground/<gelaende>_0..3.svg   Kampfboden, vier Varianten je Gelaendeart
  backdrop/<gelaende>.svg      Kulisse OBERHALB des Gitters (Ferne)
  fore/<gelaende>.svg          Bewuchs UNTERHALB des Gitters (Vordergrund)
  obstacles/<art>.svg          Stein, Baumstamm, Busch, Sumpf, Mauer

NICHT von Hand editieren - hier aendern und neu laufen lassen.

WARUM: der Kampfboden war eine Volltonfarbe je Gelaende mit einer
Schachbrett-Nuance, die Hindernisse waren im Code gezeichnete Rauten,
Ovale und Punktwolken. Vor allem aber stand ueber und unter dem Gitter
zusammen rund 40 Prozent der Flaeche leer: das Gitter ist
breitenbegrenzt (10 Spalten), die Kampf-Flaeche auf dem Handy aber viel
hoeher als breit. Kulisse und Vordergrund fuellen diese Baender, damit
das Gitter in einer Landschaft steht statt in einem Farbverlauf.

Gelaende-Reihenfolge = MapGen.TILE_*: 0 Gras, 1 Wald, 2 Wasser/Kueste,
3 Gebirge, 4 Sand, 5 Sumpf. Die Grundfarben spiegeln TERRAIN_GROUND in
TacticalBattleScreen.gd - der Boden muss zum Verlauf dahinter passen.

Boden-Kacheln muessen KACHELN: flache Grundfarbe (ein Verlauf ergibt im
Feld Streifen) und Deko mit Abstand zum Rand.
"""
import math
import os
import random

T = 64            # Boden-Kachel
BAND_W = 540      # Kulissen-Baender (werden im Screen auf die Breite gezogen)
BACK_H = 200
FORE_H = 130
OUT = os.path.join("assets", "battle")

# Spiegelt TacticalBattleScreen.TERRAIN_GROUND (dort als Color 0..1).
TERRAIN = [
    dict(name="grass",    base="#2e4728", deco="#3c5c33", dark="#1d2f1a", lit="#4a6b3d"),
    dict(name="forest",   base="#22381f", deco="#2e4a28", dark="#152414", lit="#3c5c33"),
    dict(name="coast",    base="#293a4d", deco="#33485e", dark="#1a2733", lit="#41586f"),
    dict(name="mountain", base="#42403d", deco="#524f4b", dark="#2a2826", lit="#615d58"),
    dict(name="sand",     base="#574d33", deco="#6b5f40", dark="#38311f", lit="#7d6f4c"),
    dict(name="swamp",    base="#333b29", deco="#414a33", dark="#20261a", lit="#4d5840"),
]

INSET = 9


def head(comment, w, h):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!-- %s\n     Erzeugt von tools/gen_battle_art.py. -->\n'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'width="%d" height="%d">\n' % (comment, w, h, w, h))



def poly_pts(pts, fill, op=1.0, stroke=None, sw=1.5):
    """Polygon aus (x, y)-TUPELN. Bewusst so und nicht als lange
    Formatzeichenkette: dort standen x- und y-Werte abwechselnd, und bei
    den Sand-Felsnadeln waren sie vertauscht - die Punkte lagen weit
    unter dem Band, ohne dass es im Code auffiel."""
    d = " ".join("%.0f,%.0f" % (x, y) for x, y in pts)
    s = '  <polygon points="%s" fill="%s"' % (d, fill)
    if op != 1.0:
        s += ' opacity="%.2f"' % op
    if stroke:
        s += ' stroke="%s" stroke-width="%.1f"' % (stroke, sw)
    return s + "/>\n"


# ------------------------------------------------------------------- Boden

def ground_tile(cfg, v):
    """Flache Grundfarbe plus Streu. Kein Verlauf - ein Verlauf je Kachel
    ergibt im Feld Querstreifen alle 64 px (Lehrgeld aus It. 19)."""
    rng = random.Random(hash(cfg["name"]) % 9973 + v * 17)
    out = head("Kampfboden %s, Variante %d" % (cfg["name"], v), T, T)
    out += '  <rect width="%d" height="%d" fill="%s"/>\n' % (T, T, cfg["base"])
    # Weiche Flecken - geben Tiefe, ohne die Einheiten zu stoeren.
    for _ in range(3):
        x = rng.uniform(INSET, T - INSET)
        y = rng.uniform(INSET, T - INSET)
        r = rng.uniform(10, 30)
        out += ('  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s" '
                'opacity="%.2f"/>\n' % (x, y, r, r * rng.uniform(0.35, 0.7),
                                        cfg["deco"], rng.uniform(0.16, 0.30)))
    name = cfg["name"]
    # Bueschel nur in ZWEI von sechs Varianten (It. 36). Vorher lag es in
    # jeder Variante, also bei 80 Zellen rund 20 Mal an derselben Stelle
    # relativ zur Kachel - in der komponierten Ansicht ein sichtbares
    # Raster aus "V"-Zeichen. Dasselbe Muster-Problem wie bei den
    # Weltkarten-Kacheln (It. 34).
    if name in ("grass", "forest", "swamp") and v in (1, 4):
        x = rng.uniform(INSET + 6, T - INSET - 6)
        y = rng.uniform(INSET + 8, T - INSET)
        out += ('  <g stroke="%s" stroke-width="2.4" stroke-linecap="round" '
                'opacity="0.16">\n' % cfg["lit"])
        for k in (0, 1):
            out += ('    <line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>\n'
                    % (x + k * 5.0, y, x + k * 5.0 + (2.5 if k else -2.5), y - 8.0))
        out += "  </g>\n"
    if name in ("mountain", "sand", "coast"):
        for _ in range(2):
            x = rng.uniform(INSET, T - INSET)
            y = rng.uniform(INSET, T - INSET)
            w = rng.uniform(10, 20)
            out += ('  <path d="M %.1f %.1f q %.1f -3.5 %.1f 0" fill="none" stroke="%s" '
                    'stroke-width="2" stroke-linecap="round" opacity="%.2f"/>\n'
                    % (x, y, w * 0.5, w, cfg["lit"], rng.uniform(0.16, 0.28)))
    if name == "swamp":
        for _ in range(2):
            out += ('  <circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s" '
                    'stroke-width="1.6" opacity="0.55"/>\n'
                    % (rng.uniform(INSET, T - INSET), rng.uniform(INSET, T - INSET),
                       rng.uniform(2, 4), cfg["lit"]))
    return out + "</svg>\n"


# ---------------------------------------------------------------- Kulisse

def _ridge(rng, y0, amp, col, op=1.0, steps=9):
    """Silhouetten-Kamm ueber die volle Bandbreite."""
    pts = ["0,%.0f" % BACK_H]
    for i in range(steps + 1):
        x = BAND_W * i / steps
        y = y0 + math.sin(i * 1.7 + rng.random() * 2.0) * amp - rng.uniform(0, amp * 0.5)
        pts.append("%.0f,%.0f" % (x, y))
    pts.append("%d,%d" % (BAND_W, BACK_H))
    return ('  <polygon points="%s" fill="%s" opacity="%.2f"/>\n'
            % (" ".join(pts), col, op))


def _far_horizon(rng, cfg):
    """Zwei ferne Kammlinien im OBEREN Drittel des Bandes (It. 36).
    Vorher lag der ganze Inhalt der Kulisse in den unteren 80 von 200
    Einheiten - auf dem Geraet (Band 326 px hoch) blieben oben rund 200 px
    fast leer. Drei Tiefenlagen statt einer geben dem Band Raum."""
    out = ""
    out += _ridge(rng, 52, 26, cfg["dark"], 0.45, steps=7)
    out += _ridge(rng, 88, 20, cfg["dark"], 0.62, steps=9)
    # Zwei sehr flache Duenste darueber, damit die Kaemme nicht als
    # gezeichnete Kanten in der Leere stehen.
    for k in range(2):
        out += ('  <rect x="0" y="%.0f" width="%d" height="%.0f" fill="%s" '
                'opacity="0.06"/>\n' % (40 + k * 26, BAND_W, 26, cfg["lit"]))
    return out


def backdrop(cfg):
    """Ferne oberhalb des Gitters. Transparent nach oben, damit der
    Verlauf des Screens durchscheint."""
    rng = random.Random(hash(cfg["name"]) % 7919)
    name = cfg["name"]
    out = head("Kampf-Kulisse %s (Ferne, ueber dem Gitter)" % name, BAND_W, BACK_H)
    # Himmel: gestaffelte Baender von oben (fast durchsichtig) zum Horizont.
    # Vorher war die obere Haelfte des Bandes LEER - auf dem Geraet ergab
    # das oberhalb des Gitters rund 150 px dunkelgruene Leere, weil der
    # Screen dort nur seinen eigenen Verlauf zeigt (It. 36). Kein
    # SVG-Gradient, sondern Baender: derselbe Grund wie bei den Kacheln,
    # nur dass es hier ums Rastern in ungewohnter Groesse geht.
    sky_steps = 7
    for i in range(sky_steps):
        y0 = BACK_H * 0.05 + i * (BACK_H * 0.62 / sky_steps)
        out += ('  <rect x="0" y="%.0f" width="%d" height="%.0f" fill="%s" '
                'opacity="%.3f"/>\n'
                % (y0, BAND_W, BACK_H * 0.62 / sky_steps + 1.0, cfg["lit"],
                   0.04 + 0.035 * i))
    out += _far_horizon(rng, cfg)
    # Dunst am Horizont
    out += ('  <rect x="0" y="%d" width="%d" height="%d" fill="%s" opacity="0.35"/>\n'
            % (BACK_H - 70, BAND_W, 70, cfg["deco"]))
    if name == "mountain":
        out += _ridge(rng, 96, 46, cfg["dark"], 0.85)
        out += _ridge(rng, 132, 34, cfg["base"], 0.95)
        for _ in range(4):
            x = rng.uniform(30, BAND_W - 30)
            h = rng.uniform(40, 70)
            out += ('  <polygon points="%.0f,%.0f %.0f,%.0f %.0f,%.0f" fill="%s" '
                    'opacity="0.9"/>\n' % (x - h * 0.6, 150, x, 150 - h, x + h * 0.6, 150,
                                           cfg["deco"]))
            out += ('  <polygon points="%.0f,%.0f %.0f,%.0f %.0f,%.0f" fill="#cfd6dc" '
                    'opacity="0.55"/>\n' % (x - h * 0.2, 150 - h * 0.66, x, 150 - h,
                                            x + h * 0.2, 150 - h * 0.66))
    elif name == "coast":
        out += _ridge(rng, 128, 18, cfg["dark"], 0.8)
        # Wasserband mit Schaumlinien
        out += ('  <rect x="0" y="130" width="%d" height="%d" fill="#31536b" '
                'opacity="0.85"/>\n' % (BAND_W, BACK_H - 130))
        for k in range(6):
            y = 142 + k * 10
            out += ('  <path d="M 0 %.0f q 30 -5 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 '
                    't 60 0 t 60 0 t 60 0" fill="none" stroke="#8fd0e8" stroke-width="2" '
                    'opacity="%.2f"/>\n' % (y, 0.35 - k * 0.04))
    elif name == "sand":
        out += _ridge(rng, 120, 26, cfg["dark"], 0.8)
        out += _ridge(rng, 148, 18, cfg["base"], 0.9)
        # Felsnadeln. Der erste Anlauf waren Saeulen mit Kappe - das las
        # sich als Pilze, nicht als Wueste.
        for _ in range(4):
            x = rng.uniform(40, BAND_W - 40)
            h = rng.uniform(34, 56)
            w = rng.uniform(13, 22)
            base_y = 176.0
            out += poly_pts([(x - w, base_y), (x - w * 0.4, base_y - h),
                             (x + w * 0.35, base_y - h * 0.8), (x + w, base_y)],
                            cfg["dark"], 0.9)
            out += poly_pts([(x - w, base_y), (x - w * 0.4, base_y - h),
                             (x - w * 0.05, base_y)], cfg["deco"], 0.65)
    elif name == "swamp":
        out += _ridge(rng, 134, 22, cfg["dark"], 0.85)
        for _ in range(7):
            x = rng.uniform(10, BAND_W - 10)
            h = rng.uniform(30, 62)
            out += ('  <path d="M %.0f 180 q -3 -%.0f 2 -%.0f" fill="none" stroke="%s" '
                    'stroke-width="4" opacity="0.85"/>\n' % (x, h * 0.6, h, cfg["dark"]))
            out += ('  <ellipse cx="%.0f" cy="%.0f" rx="13" ry="8" fill="%s" '
                    'opacity="0.7"/>\n' % (x + 2, 180 - h, cfg["deco"]))
        for k in range(3):
            out += ('  <ellipse cx="%.0f" cy="%.0f" rx="%.0f" ry="14" fill="#cfe8d8" '
                    'opacity="0.10"/>\n' % (BAND_W * (0.2 + 0.3 * k), 172, 120))
    else:
        # Gras und Wald: gestaffelter Baumsaum.
        rows = 3 if name == "grass" else 4
        for row in range(rows):
            ridge_col = cfg["dark"] if row == 0 else cfg["base"]
            crown_col = cfg["base"] if row == 0 else cfg["deco"]
            # Hoeher ansetzen und weiter staffeln (It. 36): mit 150+16*row
            # klebte der ganze Saum am unteren Rand des Bandes.
            base_y = 122 + row * 22
            out += _ridge(rng, base_y - 24, 12, ridge_col, 0.9)
            n = 9 + row * 3
            for i in range(n):
                x = BAND_W * (i + 0.5) / n + rng.uniform(-14, 14)
                r = rng.uniform(16, 26) * (0.8 + 0.25 * row)
                out += ('  <ellipse cx="%.0f" cy="%.0f" rx="%.0f" ry="%.0f" fill="%s" '
                        'stroke="%s" stroke-width="1.5" opacity="0.95"/>\n'
                        % (x, base_y - r * 0.5, r, r * 0.85, crown_col, ridge_col))
    return out + "</svg>\n"


def foreground(cfg):
    """Bewuchs unterhalb des Gitters: naeher, dunkler, groesser. Gibt dem
    Gitter eine Vorderkante statt eines Farbverlaufs."""
    rng = random.Random(hash(cfg["name"]) % 6151 + 3)
    name = cfg["name"]
    out = head("Kampf-Vordergrund %s (unter dem Gitter)" % name, BAND_W, FORE_H)
    # Das Band muss GEFUELLT sein: es steht fuer Boden, der auf den
    # Betrachter zulaeuft. Im ersten Anlauf war es transparent mit Kleinkram
    # am unteren Rand, dazwischen klaffte eine Luecke.
    out += ('  <defs><linearGradient id="fg" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0" stop-color="%s"/>'
            '<stop offset="1" stop-color="%s"/></linearGradient></defs>\n'
            % (cfg["base"], cfg["dark"]))
    out += '  <rect width="%d" height="%d" fill="url(#fg)"/>\n' % (BAND_W, FORE_H)
    # Vorderkante des Schlachtfelds
    out += ('  <rect x="0" y="0" width="%d" height="6" fill="%s" opacity="0.6"/>\n'
            % (BAND_W, cfg["dark"]))
    if name in ("mountain", "coast"):
        for _ in range(9):
            x = rng.uniform(-10, BAND_W + 10)
            w = rng.uniform(26, 54)
            h = rng.uniform(20, 40)
            out += ('  <polygon points="%.0f,%.0f %.0f,%.0f %.0f,%.0f %.0f,%.0f" '
                    'fill="%s"/>\n' % (x - w * 0.5, FORE_H, x - w * 0.28, FORE_H - h,
                                       x + w * 0.3, FORE_H - h * 0.8, x + w * 0.5, FORE_H,
                                       cfg["dark"]))
    elif name == "sand":
        for _ in range(7):
            x = rng.uniform(-10, BAND_W + 10)
            out += ('  <ellipse cx="%.0f" cy="%.0f" rx="%.0f" ry="%.0f" fill="%s"/>\n'
                    % (x, FORE_H - 4, rng.uniform(40, 80), rng.uniform(14, 26), cfg["dark"]))
    else:
        for _ in range(11):
            x = rng.uniform(-10, BAND_W + 10)
            r = rng.uniform(22, 42)
            out += ('  <ellipse cx="%.0f" cy="%.0f" rx="%.0f" ry="%.0f" fill="%s"/>\n'
                    % (x, FORE_H * 0.86 - r * 0.2, r, r * 0.8, cfg["dark"]))
        for _ in range(6):
            x = rng.uniform(0, BAND_W)
            y0 = FORE_H * 0.72
            out += '  <g stroke="%s" stroke-width="3" stroke-linecap="round">\n' % cfg["base"]
            for k in range(3):
                out += ('    <line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f"/>\n'
                        % (x + k * 5, y0, x + k * 5 + rng.uniform(-5, 6),
                           y0 - rng.uniform(16, 30)))
            out += "  </g>\n"
    return out + "</svg>\n"


# --------------------------------------------------------------- Hindernisse
# Ersetzen die im Code gezeichneten Rauten/Ovale/Punktwolken. Der Screen
# faellt auf die alten Formen zurueck, wenn eine Datei fehlt.

def obstacle(kind):
    out = head("Kampf-Hindernis %s" % kind, T, T)
    sh = '  <ellipse cx="32" cy="56" rx="21" ry="5" fill="#000" opacity="0.35"/>\n'
    if kind == "stone":
        out += sh
        out += ('  <polygon points="10,54 18,22 34,12 52,26 54,54" fill="#6b665f" '
                'stroke="#26241f" stroke-width="2.5" stroke-linejoin="round"/>\n')
        out += ('  <polygon points="10,54 18,22 34,12 32,54" fill="#8a847a" '
                'opacity="0.85"/>\n')
        out += ('  <path d="M 24 26 L 30 40 L 22 48" fill="none" stroke="#3a3630" '
                'stroke-width="2"/>\n')
    elif kind == "log":
        out += sh
        out += ('  <rect x="5" y="24" width="54" height="26" rx="12" fill="#5c4326" '
                'stroke="#26190c" stroke-width="2.5"/>\n')
        out += ('  <ellipse cx="10" cy="37" rx="6" ry="13" fill="#8a6a3c" '
                'stroke="#26190c" stroke-width="2"/>\n')
        out += '  <ellipse cx="10" cy="37" rx="2.6" ry="6" fill="#5c4326"/>\n'
        out += ('  <path d="M 22 30 q 16 8 30 4" fill="none" stroke="#3d2c17" '
                'stroke-width="2"/>\n')
        out += ('  <path d="M 26 44 q 14 -4 26 -2" fill="none" stroke="#3d2c17" '
                'stroke-width="2"/>\n')
    elif kind == "bush":
        out += sh
        for cx, cy, r, col in ((22, 40, 15, "#2c5223"), (44, 38, 14, "#37652b"),
                               (33, 30, 17, "#417a31")):
            out += ('  <ellipse cx="%d" cy="%d" rx="%d" ry="%d" fill="%s" '
                    'stroke="#16250f" stroke-width="2.5"/>\n' % (cx, cy, r, int(r * 0.88), col))
        out += '  <ellipse cx="27" cy="26" rx="6" ry="5" fill="#5d9542" opacity="0.9"/>\n'
        out += '  <circle cx="46" cy="46" r="3" fill="#c93a2c"/>\n'
    elif kind == "swamp":
        # KEIN Vollflaechen-Rechteck (It. 36): das deckte die ganze Kachel
        # und ergab in der komponierten Ansicht ein hartes 104-px-Quadrat
        # mitten auf dem Feld - das einzige rechtwinklige Element im Bild.
        # Der Tuempel ist jetzt eine unregelmaessige Lache mit weichem Rand.
        out += ('  <path d="M 6 38 q 2 -14 14 -17 q 12 -3 22 1 q 12 4 15 14 '
                'q 2 10 -8 14 q -14 5 -28 2 q -13 -3 -15 -14 Z" '
                'fill="#2b3520" opacity="0.75"/>\n')
        out += ('  <ellipse cx="32" cy="37" rx="23" ry="14" fill="#39481f" '
                'stroke="#1a2210" stroke-width="2"/>\n')
        for cx, cy, r in ((20, 30, 4), (38, 42, 5), (30, 22, 3)):
            out += ('  <circle cx="%d" cy="%d" r="%d" fill="none" stroke="#8fae62" '
                    'stroke-width="2" opacity="0.8"/>\n' % (cx, cy, r))
        out += ('  <path d="M 12 50 q 6 -12 4 -20" fill="none" stroke="#6b8442" '
                'stroke-width="3"/>\n')
        out += ('  <path d="M 52 52 q -5 -14 -2 -22" fill="none" stroke="#6b8442" '
                'stroke-width="3"/>\n')
    elif kind in ("wall", "wall_cracked"):
        out += ('  <rect x="4" y="12" width="56" height="46" fill="#6b665f" '
                'stroke="#26241f" stroke-width="2.5"/>\n')
        for z in range(3):
            out += ('  <rect x="%d" y="3" width="14" height="11" fill="#7d776e" '
                    'stroke="#26241f" stroke-width="2"/>\n' % (6 + z * 19))
        # Quaderfugen
        for y in (26, 40):
            out += ('  <line x1="4" y1="%d" x2="60" y2="%d" stroke="#3a3630" '
                    'stroke-width="2"/>\n' % (y, y))
        for x, y0, y1 in ((22, 12, 26), (42, 26, 40), (16, 40, 58), (46, 40, 58)):
            out += ('  <line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#3a3630" '
                    'stroke-width="2"/>\n' % (x, y0, x, y1))
        if kind == "wall_cracked":
            out += ('  <path d="M 20 14 L 30 34 L 22 44 L 32 56" fill="none" '
                    'stroke="#17140f" stroke-width="3"/>\n')
            out += ('  <path d="M 42 20 L 48 38" fill="none" stroke="#17140f" '
                    'stroke-width="2.5"/>\n')
    else:
        raise ValueError("unbekanntes Hindernis: %s" % kind)
    return out + "</svg>\n"


OBSTACLES = ["stone", "log", "bush", "swamp", "wall", "wall_cracked"]
GROUND_VARIANTS = 6


def main():
    n = 0
    for sub in ("ground", "backdrop", "fore", "obstacles"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    for cfg in TERRAIN:
        for v in range(GROUND_VARIANTS):
            with open(os.path.join(OUT, "ground", "%s_%d.svg" % (cfg["name"], v)), "w") as f:
                f.write(ground_tile(cfg, v))
            n += 1
        with open(os.path.join(OUT, "backdrop", "%s.svg" % cfg["name"]), "w") as f:
            f.write(backdrop(cfg))
        with open(os.path.join(OUT, "fore", "%s.svg" % cfg["name"]), "w") as f:
            f.write(foreground(cfg))
        n += 2
        print("[OK] %-9s %d Boden + Kulisse + Vordergrund" % (cfg["name"], GROUND_VARIANTS))
    for k in OBSTACLES:
        with open(os.path.join(OUT, "obstacles", "%s.svg" % k), "w") as f:
            f.write(obstacle(k))
        n += 1
    print("[OK] %-9s %d Stueck" % ("Hindernis", len(OBSTACLES)))
    print("%d Dateien geschrieben nach %s" % (n, OUT))


if __name__ == "__main__":
    main()
