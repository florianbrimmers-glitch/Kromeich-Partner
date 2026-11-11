"""Die neun Stadtgebaeude im Heroes-4-Stil, je Fraktion (It. 76).

Benutzt den Baukasten city_kit.py. Jeder Bauplan bekommt den Stil der
Fraktion (`STYLE`) und gibt eine Liste von Teilen zurueck; gen_city3d.py
verschmilzt sie zu b_<fraktion>_<bau>.

GLEICHER BAUPLAN, ANDERE FRAKTION: die Zitadelle ist bei allen vier eine
Burg mit Bergfried, Vorwerk und Tuermen - so erkennt man den Bau in jeder
Stadt wieder. Was die Fraktion ausmacht, steckt im Stil:

  Menschen    heller Kalkstein, blaue Schieferdaecher, Fachwerk, Kegeltuerme.
  Waldvolk    Sandstein und Holz, Moosdaecher, Kuppeln, Laub waechst mit.
  Totenreich  dunkler Stein, steile gotische Spitzen, gruenes Licht, Knochen.
  Orks        grober Stein und Holz, Tierhaut, Zeltdaecher, Palisaden, Schaedel.

BREITEN kommen aus gen_city_buildings.RECIPES (dieselbe Quelle wie die
2D-Sprites), damit die Grundflaechen zu den Bauplaetzen passen, die das
Layout und der Verdeckungs-Test kennen.
"""

import math

import blender_kit as bk
import city_kit as ck

rad = math.radians

STYLE = {
    "menschen": dict(
        wall="#b9b09e", wall_dark="#857c6c", plaster="#d6cbb2", timber="#4a3624",
        roof="#3e5a8a", rows="#30496f", ridge="#2a3346", thatch="#a08850",
        spire="#3e5a8a", glass="#2a3240", glow="#ffcf7a", door="#5a3e24",
        frame="#8f8676", banner="#5b3a8a", trim="#d8b44a", wood="#6b4f30",
        merlon="std", tower_roof="cone", steep=1.0, extra=None),
    "waldvolk": dict(
        wall="#b8a67c", wall_dark="#6e6450", plaster="#d2bd8e", timber="#4f3a22",
        roof="#5a7a34", rows="#46622a", ridge="#3a2a1a", thatch="#8a7a44",
        spire="#6a8a3a", glass="#24301c", glow="#ffe89a", door="#5c4527",
        frame="#6e6450", banner="#3f6b2e", trim="#c9a24a", wood="#6b5330",
        merlon="std", tower_roof="dome", steep=0.9, extra="leaves"),
    "totenreich": dict(
        wall="#706a7a", wall_dark="#46424f", plaster="#5e5868", timber="#2a2630",
        roof="#3a3448", rows="#2a2636", ridge="#1c1a22", thatch="#4a4458",
        spire="#2e5a4a", glass="#0e1a14", glow="#7dffb0", door="#2b2436",
        frame="#3a3644", banner="#3d2f52", trim="#8fd6a8", wood="#3a3444",
        merlon="spike", tower_roof="spire", steep=1.6, extra="bones"),
    "orks": dict(
        wall="#8a7458", wall_dark="#5e4a30", plaster="#9c7c52", timber="#4a3418",
        roof="#7a5a3a", rows="#5a3e22", ridge="#3a2614", thatch="#86693c",
        spire="#8a3a26", glass="#1a1008", glow="#ffb257", door="#3a2614",
        frame="#5e4a30", banner="#8a2f26", trim="#c9a24a", wood="#6b5028",
        merlon="stake", tower_roof="tent", steep=1.3, extra="skulls"),
}

BONE = "#ddd5bf"
LEAF = ["#4f7a2e", "#3f6b26", "#5f8a36"]


def _glass(st):
    return (st["glass"], st["glow"])


def _tower(st, r, h, x, y, base=0.0, roof=True, crenel=False):
    return ck.round_tower(r, h, st["wall"], st["wall_dark"], x, y, base,
                          roof=st["tower_roof"] if roof else None,
                          roof_col=st["roof"] if st["tower_roof"] != "spire" else st["roof"],
                          rise=r * 1.9 * st["steep"],
                          crenel=st["merlon"] if crenel else None,
                          slits=st["glass"])


def _main_roof(st, w, d, top, rise, along="x", col=None):
    rise *= st["steep"]
    col = col or st["roof"]
    if st["tower_roof"] == "dome" and along == "dome":
        return [ck.dome(min(w, d) * 0.55, col, 0, 0, top)]
    return ck.gable_roof(w, d, top, rise, col, st["ridge"], along=along,
                         row_col=st["rows"])


def _extras(st, w, d, h, x=0.0, y=0.0, n=2, seed=0):
    """Fraktions-Zierrat an einem Baukoerper."""
    out = []
    if st["extra"] == "leaves":
        # Baeume, die mit dem Haus verwachsen sind: Stamm an der Ecke, Krone
        # ueber dem Dach. Kleine Laubballen allein lasen sich als Buesche
        # und die Waldstadt sah aus wie die Menschenstadt in Gruen.
        for k in range(n):
            sx = -1 if k % 2 == 0 else 1
            tx, ty = x + sx * w * 0.52, y + d * 0.30
            th = h * (1.05 + 0.25 * k)
            out.append(ck.cyl(0.07, th, "#5a4128", tx, ty, 0.0, r_top=0.04, verts=8))
            out += ck.leaves(tx, ty, th, 0.30, LEAF, n=5, seed=seed + k)
        # Ranken an der Front.
        for sx in (-0.35, 0.3):
            out.append(ck.block(0.05, 0.012, h * 0.7, "#3f6b26", x + sx * w, y - d * 0.5 - 0.01,
                                0.05, bevel=0.0))
    elif st["extra"] == "bones":
        for sx in (-1, 1):
            out += ck.skull(x + sx * w * 0.32, y - d * 0.5 - 0.03, h * 0.82, 0.05, BONE,
                            eye="#7dffb0")
            out.append(ck.cyl(0.018, h * 0.5, BONE, x + sx * w * 0.55, y - d * 0.5 - 0.06, 0.0,
                              r_top=0.0, verts=6))
    elif st["extra"] == "skulls":
        for sx in (-1, 1):
            px = x + sx * (w * 0.5 + 0.12)
            out.append(ck.cyl(0.02, h * 0.9, st["wood"], px, y - d * 0.45, 0.0, verts=6))
            out += ck.skull(px, y - d * 0.45, h * 0.9 + 0.05, 0.055, BONE)
            out += ck.horns(px, y - d * 0.45, h * 0.9 + 0.08, 0.06, BONE)
    return out


# ================================================================ Bauten

def zitadelle(st, w):
    """Burg: Bergfried hinten, Vorwerk mit Tor vorn, vier Tuerme."""
    d = w * 0.72
    out = [ck.plinth(w, d, 0.08, st["wall_dark"])]
    # Bergfried.
    kw, kd, kh = w * 0.56, d * 0.55, 1.05
    ky = d * 0.16
    out.append(ck.block(kw, kd, kh, st["wall"], 0, ky, 0.08))
    out += ck.courses(kw, kd, kh, st["wall_dark"], 0, ky, 0.08, n=2)
    out += ck.quoins(kw, kd, kh, st["wall_dark"], 0, ky, 0.08, n=5)
    out += ck.window_row(kw * 0.8, ky - kd * 0.5, 0.08 + kh * 0.55, 3, 0.07, 0.13,
                         st["frame"], _glass(st), arched=True, lit=(1,))
    out += ck.window_row(kw * 0.6, ky - kd * 0.5, 0.08 + kh * 0.82, 2, 0.06, 0.09,
                         st["frame"], _glass(st), arched=True)
    top = 0.08 + kh
    if st["tower_roof"] == "tent":
        out.append(ck.cone_roof(kw * 0.62, 0.55 * st["steep"], st["roof"], 0, ky, top, verts=6))
        out += ck.horns(0, ky - kd * 0.5, top - 0.05, 0.14, BONE)
    elif st["tower_roof"] == "dome":
        out.append(ck.dome(kw * 0.5, st["roof"], 0, ky, top))
    else:
        out += ck.hip_roof(kw, kd, top, 0.42 * st["steep"], st["roof"], 0, ky)
    out += ck.crenels(kw, kd, top, st["wall"], 0, ky, kind=st["merlon"],
                      sides=("front",)) if st["tower_roof"] in ("cone", "spire") else []
    # Vorwerk mit Tor.
    vw, vd, vh = w * 0.92, d * 0.30, 0.52
    vy = -d * 0.30
    out.append(ck.block(vw, vd, vh, st["wall"], 0, vy, 0.08))
    out += ck.crenels(vw, vd, 0.08 + vh, st["wall"], 0, vy, kind=st["merlon"],
                      sides=("front",))
    out += ck.door(0, vy - vd * 0.5, 0.08, 0.22, 0.24, st["frame"], st["door"],
                   steps=st["wall_dark"])
    out += ck.hanging_banner(-vw * 0.28, vy - vd * 0.5, 0.08 + vh - 0.04, 0.10, 0.22,
                             st["banner"], st["trim"])
    out += ck.hanging_banner(vw * 0.28, vy - vd * 0.5, 0.08 + vh - 0.04, 0.10, 0.22,
                             st["banner"], st["trim"])
    # Tuerme: vorn niedriger, hinten hoeher.
    for sx in (-1, 1):
        out += _tower(st, 0.17, 0.85, sx * w * 0.47, vy, 0.08, crenel=False)
        out += _tower(st, 0.14, 1.35, sx * kw * 0.52, ky + kd * 0.35, 0.08)
    out += ck.banner(0.0, ky, top + (0.42 * st["steep"] if st["tower_roof"] not in
                                     ("tent", "dome") else 0.5), 0.35, st["banner"],
                     st["trim"])
    out += _extras(st, w * 0.9, d, 0.9, 0, vy, n=2, seed=1)
    return out


def kapelle(st, w):
    """Kirchenschiff mit Giebel zur Kamera, Glockenturm davor, Strebepfeiler."""
    nw, nd, nh = w * 0.62, w * 0.95, 0.58
    out = [ck.plinth(nw, nd, 0.06, st["wall_dark"], 0, 0.08)]
    out.append(ck.block(nw, nd, nh, st["wall"], 0, 0.08, 0.06))
    out += ck.quoins(nw, nd, nh, st["wall_dark"], 0, 0.08, 0.06, n=3)
    for sy in (-0.25, 0.1, 0.4):
        for sx in (-1, 1):
            out.append(ck.block(0.07, 0.09, nh * 0.85, st["wall_dark"],
                                sx * (nw * 0.5 + 0.03), sy, 0.06, taper=0.7))
    out += ck.side_windows(nd * 0.7, nw * 0.5 + 0.005, 0.06 + nh * 0.42, 3, 0.06, 0.16,
                           st["frame"], st["glow"], y=0.12)
    out += _main_roof(st, nw, nd, 0.06 + nh, 0.42, along="y")
    # Turm vorn.
    tw = 0.30
    ty = 0.08 - nd * 0.5 - tw * 0.30
    th = 1.05
    out.append(ck.block(tw, tw, th, st["wall"], 0, ty, 0.0))
    out += ck.quoins(tw, tw, th, st["wall_dark"], 0, ty, 0.0, n=5)
    out += ck.door(0, ty - tw * 0.5, 0.0, 0.13, 0.20, st["frame"], st["door"],
                   steps=st["wall_dark"])
    # Schalloeffnungen der Glockenstube.
    out += ck.window(0, ty - tw * 0.5, th - 0.22, 0.09, 0.12, st["frame"], "#141210",
                     arched=True, sill=False)
    out.append(ck.block(tw + 0.04, tw + 0.04, 0.04, st["wall_dark"], 0, ty, th - 0.02))
    spire_h = 0.55 * (1.0 if st["tower_roof"] != "spire" else 1.6)
    if st["tower_roof"] == "dome":
        out.append(ck.dome(tw * 0.62, st["spire"], 0, ty, th + 0.02))
        out.append(ck.cyl(0.012, 0.18, st["trim"], 0, ty, th + 0.2, verts=6))
    elif st["tower_roof"] == "tent":
        out.append(ck.cone_roof(tw * 0.7, spire_h, st["roof"], 0, ty, th + 0.02, verts=6))
    else:
        out.append(bk.cone(tw * 0.68, spire_h, (0, ty, th + 0.02 + spire_h * 0.5),
                           st["spire"], verts=4, rot=(0, 0, rad(45))))
    # Zeichen auf der Spitze.
    tip = th + 0.02 + spire_h
    out.append(ck.block(0.016, 0.016, 0.14, st["trim"], 0, ty, tip - 0.02, bevel=0.0))
    out.append(ck.block(0.08, 0.016, 0.016, st["trim"], 0, ty, tip + 0.06, bevel=0.0))
    out += _extras(st, nw, nd, nh, 0, 0.08, n=2, seed=3)
    return out


def wachturm(st, w):
    """Hoher Rundturm mit Zinnenkranz und Dach, Tor unten, Banner oben."""
    r = w * 0.30
    h = 1.55
    out = _tower(st, r, h, 0, 0, 0.0, roof=False, crenel=False)
    # Ueberkragende Wehrplattform mit Konsolen.
    top = h
    out.append(ck.cyl(r * 1.25, 0.10, st["wall"], 0, 0, top, verts=18))
    for k in range(10):
        a = 2 * math.pi * k / 10
        out.append(ck.block(0.05, 0.05, 0.09, st["wall_dark"], math.cos(a) * r * 1.1,
                            math.sin(a) * r * 1.1, top - 0.08, bevel=0.004))
    out += ck.round_tower(r * 1.22, 0.02, st["wall"], st["wall_dark"], 0, 0, top + 0.10,
                          crenel=st["merlon"], roof=st["tower_roof"], roof_col=st["roof"],
                          rise=r * 2.0 * st["steep"])
    out += ck.door(0, -r * 0.98, 0.0, 0.12, 0.20, st["frame"], st["door"],
                   steps=st["wall_dark"])
    out += ck.window(0, -r * 0.95, h * 0.62, 0.06, 0.11, st["frame"], st["glow"],
                     arched=True)
    out += ck.banner(r * 0.9, 0, top + 0.12, 0.42, st["banner"], st["trim"])
    if st["extra"] == "leaves":
        out += ck.leaves(r * 0.8, r * 0.3, h * 0.5, 0.16, LEAF, n=3, seed=7)
    elif st["extra"] == "bones":
        out += ck.skull(0, -r * 1.0, h * 0.85, 0.05, BONE, eye="#7dffb0")
    elif st["extra"] == "skulls":
        out += ck.palisade(0, 0, r * 1.6, r * 1.6, 0.30, st["wood"], n=12, a0=200, a1=340)
    return out


def schmiede(st, w):
    """Werkstatt: Steinsockel, Fachwerk-Obergeschoss, Giebel zur Kamera,
    grosser Schornstein, offene Esse mit Glut und Amboss davor."""
    bw, bd = w * 0.58, w * 0.55
    bx = -w * 0.15
    out = [ck.plinth(bw, bd, 0.05, st["wall_dark"], bx)]
    out.append(ck.block(bw, bd, 0.36, st["wall"], bx, 0, 0.05))
    out += ck.quoins(bw, bd, 0.36, st["wall_dark"], bx, 0, 0.05, n=3)
    out.append(ck.block(bw + 0.06, bd + 0.06, 0.34, st["plaster"], bx, 0, 0.41))
    out += ck.timber(bw + 0.06, bd + 0.06, 0.34, st["timber"], bx, 0, 0.41)
    out += ck.door(bx - bw * 0.2, -bd * 0.5, 0.05, 0.13, 0.22, st["frame"], st["door"])
    out += ck.window(bx + bw * 0.22, -bd * 0.5 - 0.03, 0.55, 0.07, 0.10, st["frame"],
                     st["glow"])
    out += _main_roof(st, bw + 0.06, bd + 0.06, 0.75, 0.40, along="y")
    out += ck.chimney(bx + bw * 0.28, bd * 0.18, 0.6, 0.62, st["wall_dark"], "#2a2622")
    # Esse unter einem Pultdach, rechts vorn.
    ex, ey = w * 0.30, -bd * 0.12
    for px in (ex - 0.2, ex + 0.2):
        out.append(ck.block(0.04, 0.04, 0.42, st["wood"], px, ey - 0.18, 0.0, bevel=0.0))
    out.append(ck.block(0.48, 0.42, 0.03, st["thatch"], ex, ey, 0.42, bevel=0.004,
                        rot_z=0.0))
    out.append(ck.block(0.24, 0.20, 0.16, st["wall_dark"], ex, ey + 0.05, 0.0))
    out.append(ck.block(0.16, 0.14, 0.02, st["glow"], ex, ey + 0.05, 0.16, bevel=0.0))
    out.append(ck.block(0.10, 0.05, 0.08, "#3a3a3e", ex - 0.05, ey - 0.25, 0.06, bevel=0.005))
    out.append(ck.cyl(0.035, 0.07, st["wood"], ex - 0.05, ey - 0.25, 0.0, verts=8))
    out += _extras(st, bw, bd, 0.7, bx, 0, n=1, seed=5)
    return out


def reiterei(st, w):
    """Langer Stall mit Strohdach, Stalltueren, Heuboden-Gaube, Koppel davor."""
    bw, bd, bh = w * 0.92, w * 0.42, 0.40
    by = 0.12
    out = [ck.plinth(bw, bd, 0.04, st["wall_dark"], 0, by)]
    out.append(ck.block(bw, bd, bh, st["plaster"], 0, by, 0.04))
    out += ck.timber(bw, bd, bh, st["timber"], 0, by, 0.04)
    for i in range(4):
        px = -bw * 0.36 + i * bw * 0.24
        out.append(ck.block(0.16, 0.03, 0.24, st["door"], px, by - bd * 0.5 - 0.012, 0.04,
                            bevel=0.0))
        out.append(ck.block(0.16, 0.035, 0.014, st["timber"], px, by - bd * 0.5 - 0.02, 0.17,
                            bevel=0.0))
    roof_col = st["thatch"] if st["tower_roof"] != "tent" else st["roof"]
    out += ck.gable_roof(bw, bd, 0.04 + bh, 0.36 * st["steep"], roof_col, st["ridge"],
                         0, by, along="x", over=0.09, rows=5,
                         row_col=_darker(roof_col))
    # Gaube mit Heuluke.
    out.append(ck.block(0.20, 0.14, 0.18, st["plaster"], 0, by - bd * 0.40, 0.04 + bh + 0.04))
    out += ck.gable_roof(0.20, 0.14, 0.04 + bh + 0.22, 0.12, roof_col, st["ridge"], 0,
                         by - bd * 0.40, along="y", over=0.03, rows=1)
    out.append(ck.block(0.09, 0.02, 0.10, "#2a2016", 0, by - bd * 0.40 - 0.075,
                        0.04 + bh + 0.07, bevel=0.0))
    # Koppel und Traenke.
    fy = -w * 0.38
    out += ck.fence(-bw * 0.45, bw * 0.45, fy, 0.20, st["wood"], n=7)
    for sx in (-1, 1):
        out += ck.fence(sx * bw * 0.45, sx * bw * 0.45, fy, 0.20, st["wood"], n=2)
    out.append(ck.block(0.24, 0.08, 0.06, st["wood"], bw * 0.25, fy + 0.16, 0.0))
    out.append(ck.block(0.20, 0.05, 0.01, "#4a6a8a", bw * 0.25, fy + 0.16, 0.06, bevel=0.0))
    # Heuballen.
    out.append(ck.cyl(0.07, 0.12, "#c9a85a", -bw * 0.32, fy + 0.16, 0.0, verts=12))
    out += _extras(st, bw, bd, bh + 0.2, 0, by, n=2, seed=9)
    return out


def markt(st, w):
    """Marktplatz: drei Staende mit gestreiften Planen, Brunnen in der Mitte."""
    out = []
    stripes = (st["banner"], st["plaster"])
    for k, (sx, sy, rz) in enumerate(((-0.55, 0.12, 8.0), (0.0, 0.25, 0.0),
                                      (0.55, 0.10, -8.0))):
        cx, cy = sx * w * 0.62, sy * w * 0.4
        sw, sd = 0.42, 0.30
        for px in (-1, 1):
            for py in (-1, 1):
                out.append(ck.block(0.03, 0.03, 0.40 if py < 0 else 0.48, st["wood"],
                                    cx + px * sw * 0.45, cy + py * sd * 0.45, 0.0, bevel=0.0))
        out.append(ck.block(sw, sd * 0.45, 0.20, st["wood"], cx, cy - sd * 0.25, 0.0))
        # Ware auf dem Tresen.
        for j, c in enumerate(("#c9563a", "#d8b44a", "#7a9a3a")):
            out.append(ck.block(0.07, 0.07, 0.05, c, cx - 0.12 + j * 0.12, cy - sd * 0.25,
                                0.20, bevel=0.01))
        # Gestreifte Plane, schraeg nach vorn.
        n = 5
        for i in range(n):
            px = cx - sw * 0.5 + sw * (i + 0.5) / n
            out.append(bk.box((sw / n * 0.5, sd * 0.62, 0.012), (px, cy, 0.46),
                              stripes[i % 2], 0.0, rot=(rad(14), 0, 0)))
    # Brunnen.
    out.append(ck.cyl(0.20, 0.12, st["wall"], 0, -w * 0.18, 0.0, verts=16))
    out.append(ck.cyl(0.17, 0.01, "#4a6a8a", 0, -w * 0.18, 0.12, verts=16))
    out.append(ck.cyl(0.04, 0.26, st["wall_dark"], 0, -w * 0.18, 0.0, verts=10))
    out.append(ck.cyl(0.08, 0.03, st["wall"], 0, -w * 0.18, 0.26, verts=12))
    # Faesser und Kisten.
    out.append(ck.cyl(0.06, 0.13, st["wood"], -w * 0.42, -w * 0.22, 0.0, verts=10))
    out.append(ck.cyl(0.06, 0.13, st["wood"], -w * 0.34, -w * 0.28, 0.0, verts=10))
    out.append(ck.block(0.12, 0.12, 0.10, st["wood"], w * 0.40, -w * 0.25, 0.0))
    out.append(ck.block(0.09, 0.09, 0.08, st["wood"], w * 0.42, -w * 0.25, 0.10))
    if st["extra"] == "leaves":
        out += ck.leaves(0, w * 0.32, 0.45, 0.22, LEAF, n=4, seed=11)
        out.append(ck.cyl(0.05, 0.45, st["wood"], 0, w * 0.32, 0.0, verts=8))
    elif st["extra"] == "skulls":
        out += ck.palisade(0, 0.05, w * 0.55, w * 0.32, 0.28, st["wood"], n=10, a0=20, a1=160)
    elif st["extra"] == "bones":
        out += ck.skull(0, -w * 0.18, 0.32, 0.05, BONE, eye="#7dffb0")
    return out


def kaserne(st, w):
    """Zweigeschossige Kaserne mit Zinnen, Ecktuermchen, Bannern und
    Uebungspuppen davor."""
    bw, bd, bh = w * 0.82, w * 0.46, 0.78
    by = 0.10
    out = [ck.plinth(bw, bd, 0.06, st["wall_dark"], 0, by)]
    out.append(ck.block(bw, bd, bh, st["wall"], 0, by, 0.06))
    out += ck.courses(bw, bd, bh, st["wall_dark"], 0, by, 0.06, n=1)
    out += ck.quoins(bw, bd, bh, st["wall_dark"], 0, by, 0.06, n=4)
    yf = by - bd * 0.5
    out += ck.window_row(bw * 0.9, yf, 0.06 + bh * 0.20, 4, 0.06, 0.10, st["frame"],
                         _glass(st), lit=(2,))
    out += ck.window_row(bw * 0.9, yf, 0.06 + bh * 0.62, 5, 0.06, 0.10, st["frame"],
                         _glass(st), arched=True, lit=(0, 3))
    out += ck.door(0, yf, 0.06, 0.16, 0.24, st["frame"], st["door"], steps=st["wall_dark"])
    top = 0.06 + bh
    if st["tower_roof"] in ("cone", "spire"):
        out.append(ck.block(bw - 0.04, bd - 0.04, 0.03, st["wall_dark"], 0, by, top - 0.01))
        out += ck.crenels(bw, bd, top, st["wall"], 0, by, kind=st["merlon"])
    else:
        out += _main_roof(st, bw, bd, top, 0.30, along="x")
    for sx in (-1, 1):
        tx = sx * bw * 0.5
        out.append(ck.block(0.24, 0.24, bh + 0.30, st["wall"], tx, yf + 0.08, 0.06))
        out += ck.crenels(0.24, 0.24, bh + 0.36, st["wall"], tx, yf + 0.08,
                          mw=0.05, mh=0.06, wall=0.05, kind=st["merlon"])
        out += ck.hanging_banner(sx * bw * 0.25, yf, top - 0.06, 0.12, 0.30, st["banner"],
                                 st["trim"])
    # Uebungspuppen.
    for k, px in enumerate((-bw * 0.32, bw * 0.30)):
        py = yf - 0.32
        out.append(ck.block(0.03, 0.03, 0.30, st["wood"], px, py, 0.0, bevel=0.0))
        out.append(ck.block(0.20, 0.03, 0.03, st["wood"], px, py, 0.22, bevel=0.0))
        out.append(ck.cyl(0.055, 0.14, st["thatch"], px, py, 0.12, verts=8))
        out.append(ck.cyl(0.04, 0.06, st["thatch"], px, py, 0.27, verts=8))
    out += _extras(st, bw, bd, bh, 0, by, n=2, seed=13)
    return out


def spaeher(st, w):
    """Holzerner Ausguck auf vier schraegen Beinen, mit Huette und Leiter."""
    h = 1.35
    out = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            out.append(ck.cyl(0.035, h, st["wood"], sx * 0.20, sy * 0.20, 0.0,
                              verts=6))
    for z in (0.35, 0.80):
        out.append(ck.block(0.46, 0.03, 0.03, st["wood"], 0, -0.20, z, bevel=0.0))
        out.append(ck.block(0.46, 0.03, 0.03, st["wood"], 0, 0.20, z, bevel=0.0))
        out.append(ck.block(0.03, 0.46, 0.03, st["wood"], -0.20, 0, z, bevel=0.0))
        out.append(ck.block(0.03, 0.46, 0.03, st["wood"], 0.20, 0, z, bevel=0.0))
    # Kreuzstreben vorn.
    for sgn in (-1, 1):
        out.append(bk.box((0.30, 0.012, 0.012), (0, -0.21, 0.58), st["wood"], 0.0,
                          rot=(0, rad(sgn * 48), 0)))
    out.append(ck.block(0.62, 0.62, 0.05, st["wood"], 0, 0, h))
    out.append(ck.block(0.44, 0.44, 0.28, st["plaster"] if st["extra"] != "skulls"
                        else st["wood"], 0, 0, h + 0.05))
    out += ck.timber(0.44, 0.44, 0.28, st["timber"], 0, 0, h + 0.05, faces=("front",))
    out.append(ck.block(0.14, 0.02, 0.10, "#1a1612", 0, -0.23, h + 0.15, bevel=0.0))
    if st["tower_roof"] == "dome":
        out.append(ck.dome(0.36, st["roof"], 0, 0, h + 0.33))
    elif st["tower_roof"] == "tent":
        out.append(ck.cone_roof(0.42, 0.40, st["roof"], 0, 0, h + 0.33, verts=6))
    else:
        out += ck.hip_roof(0.44, 0.44, h + 0.33, 0.30 * st["steep"], st["roof"])
    # Leiter.
    for sx in (-1, 1):
        out.append(bk.box((0.012, 0.012, h * 0.52), (sx * 0.08, -0.40, h * 0.5), st["wood"],
                          0.0, rot=(rad(-14), 0, 0)))
    for k in range(6):
        z = 0.12 + k * 0.2
        out.append(ck.block(0.17, 0.014, 0.014, st["wood"], 0, -0.43 + z * 0.24, z,
                            bevel=0.0))
    out += ck.banner(0.24, 0.24, h + 0.05, 0.62, st["banner"], st["trim"])
    if st["extra"] == "skulls":
        out += ck.skull(0, -0.32, h - 0.05, 0.05, BONE)
    elif st["extra"] == "leaves":
        out += ck.leaves(0.25, 0.3, h * 0.5, 0.18, LEAF, n=3, seed=17)
    return out


def mauer(st, w):
    """Torhaus: Mauerstueck mit Zinnen, zwei Tortuerme, Fallgitter."""
    d = 0.34
    out = [ck.plinth(w, d, 0.06, st["wall_dark"])]
    wh = 0.58
    for sx in (-1, 1):
        # Mauerabschnitte links und rechts des Torhauses.
        cx = sx * w * 0.36
        out.append(ck.block(w * 0.28, d, wh, st["wall"], cx, 0, 0.06))
        out += ck.crenels(w * 0.28, d, 0.06 + wh, st["wall"], cx, 0, kind=st["merlon"],
                          sides=("front", "back"))
    # Torhaus.
    gw, gd, gh = w * 0.44, d + 0.14, 0.92
    out.append(ck.block(gw, gd, gh, st["wall"], 0, 0, 0.06))
    out += ck.quoins(gw, gd, gh, st["wall_dark"], 0, 0, 0.06, n=5)
    out += ck.crenels(gw, gd, 0.06 + gh, st["wall"], 0, 0, kind=st["merlon"])
    # Torbogen mit Fallgitter.
    out += ck.door(0, -gd * 0.5, 0.06, 0.26, 0.32, st["wall_dark"], "#16130f")
    for k in range(5):
        out.append(ck.block(0.014, 0.02, 0.40, "#3a3a3e", -0.10 + k * 0.05, -gd * 0.5 - 0.02,
                            0.10, bevel=0.0))
    out += ck.window_row(gw * 0.6, -gd * 0.5, 0.06 + gh * 0.66, 2, 0.05, 0.09, st["frame"],
                         _glass(st), arched=True, lit=(1,))
    for sx in (-1, 1):
        out += _tower(st, 0.16, 1.05, sx * gw * 0.62, -0.02, 0.06, roof=True)
    out += ck.hanging_banner(0, -gd * 0.5, 0.06 + gh - 0.06, 0.16, 0.20, st["banner"],
                             st["trim"])
    if st["extra"] == "bones":
        out += ck.skull(0, -gd * 0.5 - 0.02, 0.06 + 0.44, 0.06, BONE, eye="#7dffb0")
    elif st["extra"] == "skulls":
        for sx in (-1, 1):
            out += ck.palisade(sx * w * 0.36, -d * 0.9, w * 0.14, 0.04, 0.32, st["wood"], n=5,
                               a0=0, a1=180)
        out += ck.horns(0, -gd * 0.5, 0.06 + gh - 0.1, 0.12, BONE)
    elif st["extra"] == "leaves":
        out += ck.leaves(-w * 0.42, 0.15, wh + 0.1, 0.16, LEAF, n=3, seed=19)
    return out


def _darker(hexstr, k=0.78):
    h = hexstr.lstrip("#")
    c = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v * k))) for v in c)


BUILD = {f.__name__: f for f in (zitadelle, kapelle, wachturm, schmiede, reiterei,
                                 markt, kaserne, spaeher, mauer)}
