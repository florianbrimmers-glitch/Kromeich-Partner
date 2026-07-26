#!/usr/bin/env python3
"""Erzeugt die 28 Kampf-Token-SVGs aus data/units.json.

    python3 game/tools/gen_unit_sprites.py

Ziel: assets/units/<fraktions-dir>/<unit-id>.svg (64x64 viewBox, gleiche
Konventionen wie die Stadt-Sprites: Schatten-Ellipse unten, Gradients,
dunkle Konturen).

Warum generiert statt handgemalt: die Token muessen zu den Daten passen
(Fraktionsfarbe, Tier, Fernkampf/Flug), und wenn units.json sich aendert,
soll ein Lauf reichen. Die Sandbox kann keine PNGs malen - gemalte
Sprites bleiben spaetere externe Zulieferung, diese SVGs sind die
spielbare Zwischenstufe und ersetzen die bisherigen Kreise.

Silhouette nach Rolle (aus den Daten abgeleitet, nicht hart gelistet):
  Fernkampf  (shots > 0)          Figur mit Bogen
  Flieger    (flying)             Koerper mit Fluegeln
  Reiter     (jousting*)          Reiter auf Vierbeiner
  Riese      (hp >= 60)           breiter Klotz mit Schultern
  sonst                           Figur mit Klinge
Untote (undead) bekommen knochenfarbene Haut, alle anderen die
Fraktionsfarbe. Tier steht als Punktreihe unten am Sockel.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNITS = os.path.join(ROOT, "data", "units.json")
OUT_DIR = os.path.join(ROOT, "assets", "units")

# Muss zu FACTION_DIRS in WorldMapScreen/CityScreen passen.
FACTION_DIR = {
    "waldvolk": "waldvolk",
    "menschen": "menschen",
    "totenreich": "totenreich",
    "orkstaemme": "orks",
}
# Fraktionsfarben wie FACTION_COLORS in WorldMapScreen.gd.
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


def body_ranged(main, dark, light):
    return f"""  <!-- Bogen -->
  <path d="M44,18 Q54,32 44,46" fill="none" stroke="{dark}" stroke-width="2.5"/>
  <line x1="44" y1="18" x2="44" y2="46" stroke="{light}" stroke-width="1"/>
  <!-- Koerper -->
  <ellipse cx="28" cy="34" rx="9" ry="13" fill="{main}" stroke="{dark}" stroke-width="1.5"/>
  <circle cx="28" cy="17" r="7" fill="{light}" stroke="{dark}" stroke-width="1.5"/>
  <!-- Arm zum Bogen -->
  <line x1="30" y1="28" x2="44" y2="30" stroke="{dark}" stroke-width="3"/>
  <!-- Pfeil -->
  <line x1="30" y1="30" x2="50" y2="30" stroke="{light}" stroke-width="1.2"/>
  <polygon points="50,30 46,27.5 46,32.5" fill="{light}"/>
  <!-- Beine -->
  <line x1="25" y1="45" x2="22" y2="54" stroke="{dark}" stroke-width="3"/>
  <line x1="31" y1="45" x2="34" y2="54" stroke="{dark}" stroke-width="3"/>"""


def body_flying(main, dark, light):
    return f"""  <!-- Fluegel -->
  <path d="M30,26 C16,12 8,20 10,32 C14,28 22,28 30,32 Z"
        fill="{light}" stroke="{dark}" stroke-width="1.5" opacity="0.95"/>
  <path d="M34,26 C48,12 56,20 54,32 C50,28 42,28 34,32 Z"
        fill="{light}" stroke="{dark}" stroke-width="1.5" opacity="0.95"/>
  <!-- Koerper -->
  <ellipse cx="32" cy="36" rx="8" ry="14" fill="{main}" stroke="{dark}" stroke-width="1.5"/>
  <circle cx="32" cy="18" r="6.5" fill="{main}" stroke="{dark}" stroke-width="1.5"/>
  <!-- Klauen -->
  <line x1="29" y1="49" x2="26" y2="55" stroke="{dark}" stroke-width="2.5"/>
  <line x1="35" y1="49" x2="38" y2="55" stroke="{dark}" stroke-width="2.5"/>"""


def body_mounted(main, dark, light):
    return f"""  <!-- Reittier -->
  <ellipse cx="32" cy="40" rx="18" ry="9" fill="{main}" stroke="{dark}" stroke-width="1.5"/>
  <path d="M46,36 L54,28 L52,38 Z" fill="{main}" stroke="{dark}" stroke-width="1.2"/>
  <line x1="20" y1="47" x2="18" y2="56" stroke="{dark}" stroke-width="3"/>
  <line x1="28" y1="48" x2="27" y2="56" stroke="{dark}" stroke-width="3"/>
  <line x1="38" y1="48" x2="39" y2="56" stroke="{dark}" stroke-width="3"/>
  <line x1="44" y1="47" x2="46" y2="56" stroke="{dark}" stroke-width="3"/>
  <!-- Reiter -->
  <ellipse cx="30" cy="24" rx="6" ry="9" fill="{light}" stroke="{dark}" stroke-width="1.5"/>
  <circle cx="30" cy="12" r="5" fill="{light}" stroke="{dark}" stroke-width="1.5"/>
  <!-- Lanze -->
  <line x1="22" y1="30" x2="58" y2="18" stroke="{dark}" stroke-width="2"/>
  <polygon points="58,18 52,17 53,22" fill="{light}"/>"""


def body_giant(main, dark, light):
    return f"""  <!-- Breiter Koerper -->
  <path d="M18,52 L20,26 Q32,18 44,26 L46,52 Z"
        fill="{main}" stroke="{dark}" stroke-width="1.8"/>
  <!-- Schultern -->
  <ellipse cx="18" cy="27" rx="7" ry="6" fill="{light}" stroke="{dark}" stroke-width="1.5"/>
  <ellipse cx="46" cy="27" rx="7" ry="6" fill="{light}" stroke="{dark}" stroke-width="1.5"/>
  <circle cx="32" cy="14" r="7.5" fill="{light}" stroke="{dark}" stroke-width="1.5"/>
  <!-- Fauststreitkolben -->
  <line x1="48" y1="30" x2="56" y2="46" stroke="{dark}" stroke-width="3"/>
  <circle cx="57" cy="49" r="5" fill="{dark}"/>
  <!-- Beine -->
  <rect x="21" y="50" width="8" height="7" fill="{dark}"/>
  <rect x="35" y="50" width="8" height="7" fill="{dark}"/>"""


def body_melee(main, dark, light):
    return f"""  <!-- Koerper -->
  <ellipse cx="30" cy="34" rx="9" ry="13" fill="{main}" stroke="{dark}" stroke-width="1.5"/>
  <circle cx="30" cy="17" r="7" fill="{light}" stroke="{dark}" stroke-width="1.5"/>
  <!-- Schild -->
  <path d="M18,26 L24,24 L24,40 Q21,44 18,40 Z"
        fill="{light}" stroke="{dark}" stroke-width="1.4"/>
  <!-- Klinge -->
  <line x1="38" y1="42" x2="48" y2="14" stroke="{light}" stroke-width="3"/>
  <line x1="34" y1="40" x2="44" y2="44" stroke="{dark}" stroke-width="2.5"/>
  <!-- Beine -->
  <line x1="27" y1="45" x2="24" y2="54" stroke="{dark}" stroke-width="3"/>
  <line x1="33" y1="45" x2="36" y2="54" stroke="{dark}" stroke-width="3"/>"""


def crest(tier, dark, light):
    """Ab Tier 5 Hoerner/Krone am Kopf - trennt Elite von Fussvolk auf
    einen Blick, auch wenn die Rolle-Silhouette dieselbe ist."""
    if tier < 5:
        return ""
    # Spitzen bleiben bei y >= 3: mit der Tier-Skalierung (bis 1.04) wuerde
    # alles darueber oben aus dem 64er-viewBox herausragen und abgeschnitten.
    if tier >= 7:
        return (f'  <polygon points="24,11 22,4 28,8" fill="{light}" stroke="{dark}" stroke-width="1"/>\n'
                f'  <polygon points="40,11 42,4 36,8" fill="{light}" stroke="{dark}" stroke-width="1"/>\n'
                f'  <polygon points="32,7 30,3 34,3" fill="{light}" stroke="{dark}" stroke-width="1"/>')
    return (f'  <polygon points="25,11 23,5 29,9" fill="{light}" stroke="{dark}" stroke-width="1"/>\n'
            f'  <polygon points="39,11 41,5 35,9" fill="{light}" stroke="{dark}" stroke-width="1"/>')


# Ability -> kleines Erkennungszeichen. Reihenfolge = Prioritaet, es
# werden maximal zwei gezeichnet, damit die Silhouette lesbar bleibt.
def trait_marks(unit, dark, light):
    ab = unit["abilities"]
    marks = []

    def m(svg):
        marks.append("  " + svg)

    if "morale_aura" in ab:
        # Wie beim Crest: nicht ueber y=3, sonst schneidet die Tier-
        # Skalierung den Schein oben ab.
        m(f'<path d="M22,10 Q32,3 42,10" fill="none" stroke="{light}" stroke-width="2"/>')
    if "life_drain_50pct" in ab:
        m(f'<polygon points="28,22 30,28 32,22" fill="{light}"/>'
          f'<polygon points="34,22 36,28 38,22" fill="{light}"/>')
    if any(a.startswith("regeneration") for a in ab):
        m(f'<path d="M46,20 Q54,14 52,24 Q46,26 46,20 Z" fill="{light}" stroke="{dark}" stroke-width="1"/>')
    if "death_cloud_aoe_small" in ab:
        m(f'<g fill="{light}" opacity="0.75"><circle cx="12" cy="20" r="4"/>'
          f'<circle cx="8" cy="26" r="3"/><circle cx="16" cy="27" r="2.5"/></g>')
    if "double_attack" in ab:
        m(f'<line x1="36" y1="42" x2="52" y2="20" stroke="{light}" stroke-width="2.5"/>')
    if "unlimited_retaliations" in ab:
        m(f'<g fill="{light}"><polygon points="14,24 11,20 17,21"/>'
          f'<polygon points="14,32 10,30 16,29"/><polygon points="15,40 11,39 17,37"/></g>')
    if "bash_stun_10pct" in ab:
        m(f'<line x1="46" y1="44" x2="56" y2="24" stroke="{dark}" stroke-width="4"/>'
          f'<circle cx="57" cy="21" r="6" fill="{dark}" stroke="{light}" stroke-width="1"/>')
    if "attack_wall" in ab:
        m(f'<rect x="48" y="16" width="12" height="8" fill="{dark}" stroke="{light}" stroke-width="1"/>')
    if "polearm_bonus_vs_cavalry" in ab:
        m(f'<line x1="20" y1="52" x2="46" y2="6" stroke="{dark}" stroke-width="2.5"/>'
          f'<polygon points="46,6 42,10 48,12" fill="{light}"/>')
    if "defense_ignore_25pct" in ab:
        m(f'<path d="M8,30 L16,26 L12,34 L18,38" fill="none" stroke="{light}" stroke-width="2"/>')
    if any(a.startswith("magic_") or a.startswith("spell_") for a in ab):
        m(f'<polygon points="52,34 56,40 52,46 48,40" fill="{light}" stroke="{dark}" stroke-width="1"/>')
    if "undead" in ab:
        # Rippen auf dem Rumpf.
        m(f'<g stroke="{dark}" stroke-width="1" opacity="0.8">'
          f'<line x1="25" y1="30" x2="37" y2="30"/><line x1="25" y1="35" x2="37" y2="35"/>'
          f'<line x1="26" y1="40" x2="36" y2="40"/></g>')
    return "\n".join(marks[:2])


def pick_body(unit):
    ab = unit["abilities"]
    st = unit["stats"]
    if st["shots"] > 0:
        return body_ranged, "Fernkampf"
    if "flying" in ab:
        return body_flying, "Flieger"
    if any(a.startswith("jousting") for a in ab):
        return body_mounted, "Reiter"
    if st["hp"] >= 60:
        return body_giant, "Riese"
    return body_melee, "Nahkampf"


def tier_pips(tier, dark):
    """Tier als Punktreihe am Sockel - auf dem Handy schneller lesbar als
    eine Zahl, und sie stoert die Silhouette nicht."""
    out = [f'  <g stroke="{dark}" stroke-width="0.6">']
    total_w = (tier - 1) * 7
    x0 = 32 - total_w / 2.0
    for i in range(tier):
        out.append(f'    <circle cx="{x0 + i * 7:.1f}" cy="60" r="2.2" fill="#f4f0e4"/>')
    out.append("  </g>")
    return "\n".join(out)


def make_svg(unit):
    fac = unit["faction"]
    rgb = BONE if "undead" in unit["abilities"] else FACTION_RGB[fac]
    accent = FACTION_RGB[fac]
    main = hexcol(rgb, scale=0.85)
    dark = hexcol(rgb, scale=0.35)
    light = hexcol(rgb, mix_white=0.35)
    body_fn, role = pick_body(unit)
    tier = unit["tier"]
    inner = body_fn(main, dark, light)
    marks = trait_marks(unit, dark, light)
    if marks:
        inner += "\n" + marks
    cr = crest(tier, dark, light)
    if cr:
        inner += "\n" + cr
    # Tier skaliert die Figur: T1 klein, T7 raumfuellend. Skaliert wird um
    # den Fusspunkt (32,56), damit alle Token auf derselben Standlinie
    # stehen - sonst schweben die kleinen in der Luft.
    scale = 0.74 + 0.05 * (tier - 1)
    body = (f'  <g transform="translate(32,56) scale({scale:.2f}) translate(-32,-56)">\n'
            f"{inner}\n  </g>")
    # Untote tragen die Fraktionsfarbe als Aura, damit die Seite trotz
    # Knochenhaut erkennbar bleibt.
    aura = ""
    if "undead" in unit["abilities"]:
        aura = (f'  <ellipse cx="32" cy="34" rx="21" ry="24" fill="{hexcol(accent, scale=0.9)}"'
                f' opacity="0.16"/>\n')
    shadow_rx = 10 + 1.6 * tier
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Kampf-Token {unit['name']} ({unit['id']}), Tier {unit['tier']}, Rolle {role}.
     Generiert von tools/gen_unit_sprites.py - nicht per Hand editieren,
     sondern den Generator anpassen und neu laufen lassen. -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <ellipse cx="32" cy="57" rx="{shadow_rx:.0f}" ry="4" fill="#000" opacity="0.40"/>
{aura}{body}
{tier_pips(unit['tier'], dark)}
</svg>
"""


def main():
    units = json.load(open(UNITS))["units"]
    written = 0
    for u in units:
        d = os.path.join(OUT_DIR, FACTION_DIR[u["faction"]])
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, u["id"] + ".svg")
        with open(path, "w") as f:
            f.write(make_svg(u))
        written += 1
    print(f"{written} Token-SVGs geschrieben nach {OUT_DIR}")


if __name__ == "__main__":
    main()
