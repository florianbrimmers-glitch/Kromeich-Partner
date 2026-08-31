#!/usr/bin/env python3
"""Erzeugt die Geraeusche des Spiels als WAV.

    python3 tools/gen_sfx.py

Schreibt assets/sfx/<name>.wav - 22050 Hz, mono, 16 Bit.
NICHT von Hand editieren, hier aendern und neu laufen lassen.

WARUM SELBST ERZEUGT statt CC0-Material geladen: die Scope-Notiz sagte
"CC0-Sound", und ein frueher Versuch scheiterte an einer toten
Download-URL. Selbst erzeugte Geraeusche sind noch freier als CC0 - keine
Attribution, keine Lizenzdatei, kein Fremdmaterial im Repo - und sie passen
zur Pipeline-Entscheidung des Nutzers ("alles aus einer Hand"). Der Preis
ist ein schlichter, retro-artiger Klang; gemalte Orchestermusik wird das
nicht.

WIE DAS GEPRUEFT WIRD: hoeren kann ich nichts. Der Generator misst
stattdessen jede Datei - Dauer, Spitzenwert, Effektivwert und Nulldurch-
gaenge - und bricht ab, wenn etwas still, uebersteuert oder
gleichspannungsbehaftet ist. Das ist das Gegenstueck zum "immer ansehen"
bei der Grafik.
"""
import math
import os
import struct
import wave

RATE = 22050
OUT = os.path.join("assets", "sfx")

# Grenzwerte der Selbstpruefung.
PEAK_MIN = 0.20      # darunter ist es praktisch still
PEAK_MAX = 0.99      # darueber uebersteuert es
RMS_MIN = 0.010      # ein einzelner Knacks reicht nicht
DC_MAX = 0.06        # Gleichspannungsanteil


# --------------------------------------------------------------- Bausteine
# Alle Bausteine liefern Listen von Floats in -1..1 und werden addiert.

def _n(dur):
    return max(1, int(RATE * dur))


def env_ad(n, attack=0.01, decay=None, curve=2.0):
    """Attack-Decay-Huelle. Ohne Attack knackt jeder Ton am Anfang."""
    a = max(1, int(RATE * attack))
    d = n - a if decay is None else max(1, int(RATE * decay))
    out = []
    for i in range(n):
        if i < a:
            out.append(i / a)
        else:
            x = (i - a) / max(1, d)
            out.append(max(0.0, (1.0 - x) ** curve))
    return out


def tone(dur, f0, f1=None, shape="sine", amp=1.0, attack=0.01, curve=2.0):
    """Ton mit optionalem Tonhoehen-Verlauf von f0 nach f1."""
    n = _n(dur)
    e = env_ad(n, attack, curve=curve)
    f1 = f0 if f1 is None else f1
    out = []
    phase = 0.0
    for i in range(n):
        t = i / max(1, n - 1)
        f = f0 + (f1 - f0) * t
        phase += 2.0 * math.pi * f / RATE
        if shape == "sine":
            v = math.sin(phase)
        elif shape == "square":
            v = 1.0 if math.sin(phase) >= 0 else -1.0
        elif shape == "saw":
            v = 2.0 * ((phase / (2.0 * math.pi)) % 1.0) - 1.0
        else:  # tri
            v = 2.0 * abs(2.0 * ((phase / (2.0 * math.pi)) % 1.0) - 1.0) - 1.0
        out.append(v * e[i] * amp)
    return out


# Eigener Rauschgenerator statt random: derselbe Lauf muss dieselbe Datei
# ergeben, damit ein Neubau nicht jedes Mal andere Bytes schreibt.
class Noise:
    def __init__(self, seed=1):
        self.s = seed & 0x7FFFFFFF or 1

    def next(self):
        # xorshift32
        x = self.s
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.s = x & 0x7FFFFFFF or 1
        return (self.s / 0x3FFFFFFF) - 1.0


def noise(dur, amp=1.0, lowpass=0.35, attack=0.002, curve=2.0, seed=1):
    """Rauschband mit einpoligem Tiefpass. lowpass 1.0 = offen, klein =
    dunkel."""
    n = _n(dur)
    e = env_ad(n, attack, curve=curve)
    rng = Noise(seed)
    out = []
    prev = 0.0
    for i in range(n):
        prev += lowpass * (rng.next() - prev)
        out.append(prev * e[i] * amp)
    return out


def mix(*parts):
    n = max(len(p) for p in parts)
    out = [0.0] * n
    for p in parts:
        for i, v in enumerate(p):
            out[i] += v
    return out


def seq(*parts):
    out = []
    for p in parts:
        out.extend(p)
    return out


def delay(dur, part):
    return [0.0] * _n(dur) + list(part)


def normalize(buf, peak=0.85):
    m = max(abs(v) for v in buf) or 1.0
    k = peak / m
    return [v * k for v in buf]


# ------------------------------------------------------------------ Rezepte

def s_ui_tap():
    return normalize(mix(tone(0.055, 1200, 900, "tri", 0.8, 0.002, 3.0),
                         noise(0.03, 0.25, 0.7, 0.001, 4.0, 3)), 0.55)


def s_ui_back():
    return normalize(tone(0.09, 700, 420, "tri", 0.8, 0.003, 2.5), 0.55)


def s_build():
    """Bau: dumpfer Schlag plus Holz-Klack."""
    return normalize(mix(
        tone(0.20, 150, 90, "sine", 1.0, 0.004, 2.2),
        noise(0.16, 0.55, 0.18, 0.002, 2.5, 11),
        delay(0.10, tone(0.10, 520, 380, "tri", 0.4, 0.002, 3.0)),
    ))


def s_recruit():
    """Rekrutieren: kurzer Zweiklang, aufsteigend."""
    return normalize(mix(
        tone(0.16, 620, 620, "tri", 0.7, 0.005, 2.0),
        delay(0.07, tone(0.18, 930, 930, "tri", 0.6, 0.005, 2.0)),
    ), 0.7)


def s_coin():
    return normalize(mix(
        tone(0.10, 1750, 1750, "tri", 0.6, 0.002, 3.0),
        delay(0.05, tone(0.12, 2400, 2300, "tri", 0.45, 0.002, 3.0)),
    ), 0.6)


def s_resource():
    return normalize(mix(
        noise(0.14, 0.6, 0.5, 0.002, 2.5, 23),
        tone(0.10, 420, 300, "tri", 0.35, 0.003, 2.5),
    ), 0.6)


def s_melee_hit():
    """Nahkampf: Aufprall, kein Metall-Klingeln - das wuerde bei jedem
    Schlag nerven."""
    return normalize(mix(
        tone(0.13, 210, 70, "sine", 1.0, 0.002, 2.0),
        noise(0.10, 0.75, 0.30, 0.001, 3.0, 31),
    ))


def s_arrow_shot():
    return normalize(noise(0.16, 0.9, 0.85, 0.004, 1.6, 41), 0.6)


def s_arrow_hit():
    return normalize(mix(
        noise(0.07, 0.8, 0.55, 0.001, 4.0, 43),
        tone(0.09, 330, 180, "tri", 0.5, 0.002, 3.0),
    ), 0.7)


def s_spell_cast():
    """Zauber: aufsteigendes Schimmern."""
    return normalize(mix(
        tone(0.38, 320, 1150, "sine", 0.7, 0.02, 1.4),
        tone(0.38, 480, 1720, "sine", 0.35, 0.03, 1.4),
        noise(0.34, 0.18, 0.9, 0.05, 1.5, 53),
    ), 0.75)


def s_spell_hit():
    return normalize(mix(
        tone(0.22, 900, 160, "saw", 0.7, 0.002, 1.8),
        noise(0.18, 0.5, 0.6, 0.001, 2.2, 59),
    ))


def s_heal():
    return normalize(mix(
        tone(0.30, 660, 990, "sine", 0.7, 0.03, 1.6),
        delay(0.08, tone(0.28, 1320, 1320, "sine", 0.3, 0.03, 1.8)),
    ), 0.65)


def s_death():
    """Zerfall: dunkles Rutschen nach unten."""
    return normalize(mix(
        tone(0.34, 240, 60, "tri", 0.8, 0.004, 1.6),
        noise(0.32, 0.6, 0.22, 0.01, 1.5, 67),
    ), 0.8)


def s_wall_break():
    return normalize(mix(
        tone(0.30, 120, 45, "sine", 1.0, 0.002, 1.8),
        noise(0.40, 0.9, 0.35, 0.001, 1.4, 71),
        delay(0.12, noise(0.26, 0.5, 0.5, 0.004, 2.0, 73)),
    ))


def s_catapult():
    return normalize(mix(
        tone(0.26, 95, 55, "sine", 1.0, 0.003, 1.8),
        noise(0.20, 0.45, 0.16, 0.002, 2.2, 79),
    ))


def s_level_up():
    """Aufstieg: Dreiklang aufwaerts."""
    return normalize(seq(
        tone(0.13, 523, 523, "tri", 0.7, 0.006, 2.0),
        tone(0.13, 659, 659, "tri", 0.7, 0.006, 2.0),
        tone(0.26, 784, 784, "tri", 0.8, 0.006, 1.6),
    ), 0.75)


def s_victory():
    return normalize(seq(
        tone(0.16, 523, 523, "tri", 0.8, 0.006, 2.0),
        tone(0.16, 784, 784, "tri", 0.8, 0.006, 2.0),
        tone(0.16, 1047, 1047, "tri", 0.8, 0.006, 2.0),
        tone(0.42, 1319, 1319, "tri", 0.9, 0.008, 1.4),
    ), 0.8)


def s_defeat():
    return normalize(seq(
        tone(0.22, 392, 392, "tri", 0.8, 0.008, 2.0),
        tone(0.22, 330, 330, "tri", 0.8, 0.008, 2.0),
        tone(0.50, 262, 220, "tri", 0.9, 0.010, 1.5),
    ), 0.8)


def s_day_end():
    """Tagesende: weiche Glocke."""
    return normalize(mix(
        tone(0.55, 880, 870, "sine", 0.8, 0.008, 1.3),
        tone(0.55, 1760, 1740, "sine", 0.22, 0.010, 1.6),
    ), 0.6)


def s_week_event():
    """Wochenwechsel: kurzes Hornsignal - deutlich anders als die
    Tagesglocke, weil es die wichtigere Nachricht ist."""
    return normalize(seq(
        tone(0.20, 349, 349, "saw", 0.7, 0.012, 2.0),
        tone(0.34, 523, 523, "saw", 0.8, 0.012, 1.5),
    ), 0.7)


SOUNDS = {
    "ui_tap": s_ui_tap,
    "ui_back": s_ui_back,
    "build": s_build,
    "recruit": s_recruit,
    "coin": s_coin,
    "resource": s_resource,
    "melee_hit": s_melee_hit,
    "arrow_shot": s_arrow_shot,
    "arrow_hit": s_arrow_hit,
    "spell_cast": s_spell_cast,
    "spell_hit": s_spell_hit,
    "heal": s_heal,
    "death": s_death,
    "wall_break": s_wall_break,
    "catapult": s_catapult,
    "level_up": s_level_up,
    "victory": s_victory,
    "defeat": s_defeat,
    "day_end": s_day_end,
    "week_event": s_week_event,
}


# -------------------------------------------------------- Selbstpruefung

def measure(buf):
    n = len(buf)
    peak = max(abs(v) for v in buf) if n else 0.0
    rms = math.sqrt(sum(v * v for v in buf) / n) if n else 0.0
    dc = sum(buf) / n if n else 0.0
    zc = 0
    for i in range(1, n):
        if (buf[i - 1] < 0.0) != (buf[i] < 0.0):
            zc += 1
    return {"n": n, "dur": n / RATE, "peak": peak, "rms": rms,
            "dc": dc, "zc": zc}


def check(name, m):
    """Hoeren kann ich nichts - also messen. Diese Pruefungen fangen genau
    die Fehler, die man sonst erst am Geraet merkt: stille Datei, Clipping,
    Gleichspannung (knackt beim Abspielen), Ein-Sample-Knacks."""
    bad = []
    if m["dur"] < 0.03:
        bad.append("%s: zu kurz (%.3f s)" % (name, m["dur"]))
    if m["dur"] > 2.0:
        bad.append("%s: zu lang (%.2f s)" % (name, m["dur"]))
    if m["peak"] < PEAK_MIN:
        bad.append("%s: praktisch still (Spitze %.3f)" % (name, m["peak"]))
    if m["peak"] > PEAK_MAX:
        bad.append("%s: uebersteuert (Spitze %.3f)" % (name, m["peak"]))
    if m["rms"] < RMS_MIN:
        bad.append("%s: kaum Energie (RMS %.4f)" % (name, m["rms"]))
    if abs(m["dc"]) > DC_MAX:
        bad.append("%s: Gleichspannung %.3f (knackt)" % (name, m["dc"]))
    if m["zc"] < 4:
        bad.append("%s: nur %d Nulldurchgaenge (Knacks statt Klang)"
                   % (name, m["zc"]))
    return bad


def write_wav(path, buf):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        frames = bytearray()
        for v in buf:
            s = int(max(-1.0, min(1.0, v)) * 32767)
            frames += struct.pack("<h", s)
        w.writeframes(bytes(frames))


def main():
    os.makedirs(OUT, exist_ok=True)
    problems = []
    total = 0
    for name, fn in SOUNDS.items():
        buf = fn()
        m = measure(buf)
        problems += check(name, m)
        path = os.path.join(OUT, name + ".wav")
        write_wav(path, buf)
        total += os.path.getsize(path)
        print("[OK] %-11s %.2f s  Spitze %.2f  RMS %.3f  %5d Byte"
              % (name, m["dur"], m["peak"], m["rms"], os.path.getsize(path)))
    print("%d Geraeusche, %d KB gesamt" % (len(SOUNDS), total // 1024))
    if problems:
        print("")
        for p in problems:
            print("[WARNUNG] %s" % p)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
