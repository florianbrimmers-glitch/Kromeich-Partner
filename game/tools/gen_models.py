#!/usr/bin/env python3
"""3D-Modelle fuer die raeumliche Weltkarte (It. 53).

    /opt/blender/blender -b --factory-startup -noaudio \
        --python tools/gen_models.py -- game/assets/models/world.glb

WARUM EIN SKRIPT UND KEINE HANDGEBAUTE DATEI: dieselbe Begruendung wie bei
gen_unit_sprites.py und gen_world_tiles.py. Eine .blend-Datei, in der
jemand geklickt hat, laesst sich nicht sinnvoll versionieren, nicht
nachrechnen und nicht in einem Rutsch umfaerben. Hier stehen die Zahlen im
Code, jede Aenderung ist ein Diff, und der ganze Satz entsteht in einem
Lauf neu.

DIE CI BRAUCHT BLENDER NICHT. Wie bei den SVGs wird das Ergebnis
(world.glb) eingecheckt; die Testlaeufe fassen den Generator nicht an.

FARBEN KOMMEN AUS gen_world_tiles.py. Weltkarte in 3D und Minikarte in 2D
zeigen dieselbe Welt - laufen die Paletten auseinander, sieht es nach zwei
verschiedenen Spielen aus.

STIL: Low-Poly, flaechig, kantenbetont. Das passt zur flachen 2D-Grafik
und ist auf dem Handy mit gl_compatibility (GLES3) bezahlbar. Keine
Texturen - nur Material-Grundfarben, damit die APK nicht waechst.
"""

import math
import os
import sys

import bpy

# Die Helfer liegen in blender_kit.py - siehe dort, warum sie nicht
# doppelt im Code stehen. Blender legt das Skriptverzeichnis NICHT von
# selbst in den Suchpfad.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_kit as bk  # noqa: E402

box = bk.box
cone = bk.cone
merge = bk.merge
rad = bk.rad
material = bk.material
srgb = bk.srgb


# ---------------------------------------------------------------- Grundmasse

# Eine Kachel FUELLT ihren Platz. Der erste Prototyp hatte 0.5 breite
# Kacheln bei 1.0 Abstand - dazwischen klaffte ueberall der Hintergrund.
TILE = 1.0
# Grundhoehe der Gelaendeplatte. Flach genug, dass die Karte lesbar bleibt,
# dick genug, dass die Seitenflaechen Licht fangen und die Kachelkanten
# sichtbar werden.
BASE = 0.18

# Gelaendeart -> (Farbe aus gen_world_tiles.py, Hoehenversatz).
# Die Reihenfolge folgt MapGen.TILE_* (0 Gras, 1 Wald, 2 Wasser, 3 Gebirge,
# 4 Sand, 5 Sumpf) - die Namen hier sind die, unter denen Godot die Meshes
# im glb findet.
# WIE HOCH DARF HOHES GELAENDE SEIN: bei fester Neigung verschiebt eine
# Hoehe h ihre Oberflaeche auf dem Bild um h / tan(34 Grad) = h * 1.48
# KACHELREIHEN nach oben. Das Gebirge stand zuerst 1.10 hoch - seine
# Oberflaeche erschien damit da, wo die Kachel 1.6 Reihen dahinter liegt.
# Auf dem Musterblatt verschmolz die Gebirgsspalte zu einer Wand, in der
# keine Kachelgrenze mehr zu sehen war, und ein Tipp auf den Gipfel haette
# zwei Felder danebengelegen. 0.40 verschiebt um eine halbe Reihe: die
# Stufe ist deutlich, die Karte bleibt lesbar.
TERRAIN = [
    ("grass",    "#5a8c3a",  0.00),
    ("forest",   "#2c5220",  0.10),
    ("water",    "#2f6f95", -0.22),
    ("mountain", "#6f6a63",  0.40),
    ("sand",     "#d8bd84", -0.02),
    ("swamp",    "#4a5b34", -0.08),
]

# Fraktionsfarben wie in gen_unit_sprites.py (Reihenfolge FACTION_DIRS:
# 0 waldvolk, 1 menschen, 2 totenreich, 3 orks).
FACTIONS = [
    ("waldvolk",   "#73d973", "#3f8f3f"),
    ("menschen",   "#f2d95a", "#9d3b32"),
    ("totenreich", "#b374e6", "#4a2d63"),
    ("orks",       "#f25a4d", "#7d2b24"),
]


# ---------------------------------------------------------------- Helfer

# ---------------------------------------------------------------- Bausteine

def make_terrain():
    """Sechs Gelaendeplatten. Der Nullpunkt liegt so, dass die OBERSEITE
    einer Grasplatte auf y = 0 sitzt - dann steht alles andere ohne
    Umrechnung auf der Kachel."""
    for name, col, extra in TERRAIN:
        # `extra` IST die Oberkante, nicht ein Zuschlag zur Dicke. Im
        # ersten Anlauf stand hier `top = min(extra, 0.0)` - damit lag die
        # Oberkante von Wald UND Gebirge bei 0, die Platte wuchs nur nach
        # unten. Auf dem Bild war das Gebirge deshalb flach wie eine
        # Wiese, und die Felsen standen ohne Berg herum.
        top = extra
        h = BASE + max(extra, 0.0)
        # FASE FAST WEG (It. 62). Bis It. 61 hatte jede Kachel 0.015
        # Fase - ohne Licht war das noetig, damit man ueberhaupt eine
        # Kante sah. Mit Sonne und Schatten kippt es ins Gegenteil: jede
        # Fase faengt einen hellen Saum, und aus 468 Saeumen wird ein
        # Gitternetz ueber der ganzen Landschaft. Olden Era hat kein
        # sichtbares Raster; wir jetzt auch fast keins mehr.
        ob = box((TILE * 0.5, TILE * 0.5, h * 0.5),
                 (0, 0, top - h * 0.5), col, bevel=0.003,
                 name="t_" + name)
        ob.location = (0, 0, 0)


def make_battle_ground():
    """Flache Boeden fuer das SCHLACHTFELD (It. 69).

    Das Kampfbrett ist eben - dort braucht keine Kachel Hoehe, und die
    Gelaendeplatten der Weltkarte haben sie nur, damit Wald und Gebirge
    sich abheben. Als Quader aneinandergelegt bringen sie aber genau den
    Fehler mit, den make_fog() unten beschreibt: bei voller Kachelbreite
    liegen die SEITENflaechen benachbarter Quader deckungsgleich, und seit
    die Fase auf 0.003 steht, halten sie einander nicht mehr auseinander.
    Auf dem Schlachtfeld sind die Kacheln 115 px gross statt 60 - dort
    waren die Z-Fighting-Baender als dunkle Linien quer ueber Brett und
    Rand zu sehen. Gemessen lagen sie exakt auf Zellgrenzen (83 px
    Abstand bei 115.6 px Zellbreite und 46 Grad Neigung).

    Eine FLAECHE hat keine Seitenflaechen, die kollidieren koennen - und
    von oben sieht man ohnehin nur die Oberseite.
    """
    for name, col, _extra in TERRAIN:
        ob = bk.plane((TILE, TILE), (0, 0, 0.0), col, name="bt_" + name)
        ob.location = (0, 0, 0)


def make_fog():
    """Platte fuer UNERFORSCHTES Gelaende.

    WARUM ES SIE GIBT: der erste Entwurf hat unerforschte Kacheln gar nicht
    gebaut - "die ehrlichere Darstellung". Der Vergleich mit der 2D-Karte
    zeigte das Gegenteil. Dort liegt ueber dem ganzen Kartenrechteck ein
    Wolkenfeld, der Spieler sieht also, WIE GROSS die Welt ist und wo sie
    aufhoert. In 3D stand die erkundete Insel im Nichts, und die Ausdehnung
    der Karte war nicht mehr abzulesen. Eine Leerstelle sagt nicht
    "unbekannt", sie sagt gar nichts.
    """
    # EINE FLAECHE, KEIN QUADER - und das ist kein Sparzwang.
    #
    # Bei voller Kachelbreite liegen die SEITENflaechen benachbarter
    # Quader exakt aufeinander. Solange die Fase 0.015 betrug, hielt sie
    # sie auseinander; mit 0.002 (It. 62, gegen das Gitternetz ueber der
    # Landschaft) wurden sie deckungsgleich - und deckungsgleiche Flaechen
    # streiten sich um die Tiefe. Das Ergebnis waren drei helle Querlinien
    # quer durch das Nebelfeld, an festen Weltpositionen, unabhaengig von
    # Aufloesung und Schatten. So sieht Z-Fighting aus: nicht ueberall,
    # sondern in Baendern dort, wo die Tiefenwerte kollidieren.
    # Eingekreist habe ich es, indem ich die Nebelplatten testweise gar
    # nicht gebaut habe - dann waren die Linien weg.
    #
    # Der naechste Anlauf (Kachel auf 0.985 verkleinert) nahm die Baender
    # weg und hinterliess ein feines dunkles Fugenraster. Eine Flaeche hat
    # weder das eine noch das andere: keine Seitenflaechen, die kollidieren
    # koennen, und trotzdem Kante an Kante. Von oben sieht man ohnehin nur
    # die Oberseite.
    # SEHR DUNKEL, und dunkler als vorher noetig: seit It. 62 steht eine
    # Sonne am Himmel und ein kuehles Umgebungslicht daneben. Die Platte
    # schaut nach oben, faengt also beides voll ab - mit #1b1f27 wurde
    # aus dem Nebelfeld ein blaues Meer.
    ob = bk.plane((TILE, TILE), (0, 0, 0.0), "#0b0d11", name="t_fog")
    ob.location = (0, 0, 0)


def make_deco():
    """Deko, die auf einer Kachel steht: Baum fuer Wald, Fels fuer Gebirge,
    Schilf fuer Sumpf. Godot streut sie deterministisch."""
    # HOEHE IST HIER EIN VERDECKUNGSPROBLEM, kein Geschmack: der erste Baum
    # war 1.01 hoch, also hoeher als eine Kachel breit ist. Bei 34 Grad
    # Neigung deckte er die Kachel dahinter fast ganz zu, und eine
    # Waldflaeche wurde zur Hecke, hinter der die Karte verschwand.
    trunk = box((0.04, 0.04, 0.10), (0, 0, 0.10), "#4a3520", 0.01)
    c1 = box((0.17, 0.17, 0.15), (0, 0, 0.35), "#2c5220", 0.07)
    c2 = box((0.11, 0.11, 0.10), (0, 0, 0.58), "#3e6c20", 0.05)
    merge("deco_tree", [trunk, c1, c2])

    r1 = box((0.18, 0.17, 0.14), (0, 0, 0.14), "#6f6a63", 0.05,
             rot=(0, 0, math.radians(18)))
    r2 = box((0.11, 0.10, 0.20), (0.13, -0.08, 0.20), "#7d7870", 0.04,
             rot=(0, math.radians(7), math.radians(-25)))
    merge("deco_rock", [r1, r2])

    stalks = []
    for i, (dx, dz, hh) in enumerate([(-0.12, 0.08, 0.26), (0.10, -0.06, 0.32),
                                      (0.02, 0.16, 0.20)]):
        stalks.append(box((0.02, 0.02, hh * 0.5), (dx, dz, hh * 0.5),
                          "#6b7a45", 0.0))
    merge("deco_reed", stalks)


def make_scatter():
    """Bodenbewuchs: Grasbuschel, Blume, kleiner Stein.

    WARUM DAS DER GROESSTE HEBEL IST: bis It. 61 war eine Wiese eine
    Flaeche in genau einem Gruen. Kein Spiel dieses Jahrzehnts sieht so
    aus - was den Eindruck macht, ist nicht die Aufloesung der Modelle,
    sondern dass der Boden BEWACHSEN ist. Drei winzige Modelle, dicht
    gestreut und in Groesse und Drehung variiert, tun dafuer mehr als
    doppelt so viele Flaechen an den grossen Modellen.

    Sie sind bewusst sehr klein (unter 0.12 hoch): bei 34 Grad Neigung
    verschiebt jede Hoehe ihre Spitze um das 1.5-fache nach oben, und
    Bewuchs, der die Kachel dahinter verdeckt, ist Unkraut.
    """
    merge("deco_grass", [
        box((0.012, 0.010, 0.045), (-0.03, 0.01, 0.045), "#6f9b45", 0.0,
            rot=(rad(9), 0, rad(-12))),
        box((0.011, 0.010, 0.055), (0.00, -0.01, 0.055), "#7cab4c", 0.0,
            rot=(rad(-6), 0, rad(5))),
        box((0.010, 0.009, 0.040), (0.03, 0.02, 0.040), "#5f8a3c", 0.0,
            rot=(0, 0, rad(16))),
    ])
    merge("deco_flower", [
        box((0.008, 0.008, 0.040), (0, 0, 0.040), "#5f8a3c", 0.0),
        box((0.022, 0.022, 0.010), (0, 0, 0.086), "#e8c85a", 0.004),
        box((0.009, 0.009, 0.008), (0, 0, 0.098), "#f2e6a8", 0.003),
    ])
    merge("deco_stone", [
        box((0.035, 0.030, 0.022), (0, 0, 0.022), "#8e8880", 0.010,
            rot=(0, 0, rad(22))),
        box((0.018, 0.016, 0.014), (0.04, -0.02, 0.014), "#9d968c", 0.006,
            rot=(0, 0, rad(-14))),
    ])


def make_cities():
    """Je Fraktion eine Silhouette: Bergfried, Halle, Mauerstueck. Die
    Dachform unterscheidet die Fraktionen - auf Kachelgroesse ist die
    Silhouette das Einzige, was man auseinanderhaelt."""
    # EINE STADT PASST AUF EINE KACHEL. Der erste Entwurf mass 1.19 in der
    # Breite bei 1.0 Kachelbreite - auf der Karte ragte er sichtbar ins
    # Nachbarfeld, und man konnte nicht mehr sagen, auf welchem Feld die
    # Stadt eigentlich steht. Dasselbe gilt fuer die Hoehe: 1.62 hoch
    # verschiebt die Turmspitze um 2.4 Kachelreihen nach oben.
    for idx, (fac, light, dark) in enumerate(FACTIONS):
        parts = []
        parts.append(box((0.19, 0.19, 0.46), (-0.15, 0.12, 0.46),
                         light, 0.03))
        if fac == "waldvolk":
            parts.append(cone(0.25, 0.34, (-0.15, 0.12, 1.09),
                              dark, verts=8))
        elif fac == "menschen":
            parts.append(box((0.14, 0.14, 0.14), (-0.15, 0.12, 1.06),
                             dark, 0.05))
        elif fac == "totenreich":
            parts.append(cone(0.20, 0.44, (-0.15, 0.12, 1.14),
                              dark, verts=4))
        else:
            parts.append(box((0.21, 0.21, 0.08), (-0.15, 0.12, 1.00),
                             dark, 0.03, rot=(0, 0, math.radians(45))))
        parts.append(box((0.24, 0.17, 0.22), (0.18, -0.16, 0.22),
                         light, 0.03))
        parts.append(box((0.27, 0.20, 0.07), (0.18, -0.16, 0.51),
                         dark, 0.04))
        parts.append(box((0.38, 0.06, 0.15), (0.0, 0.34, 0.15),
                         dark, 0.02))
        merge("city_" + fac, parts)


def make_hero():
    """Held: Sockel, Koerper, Kopf, Banner. Der Sockel traegt spaeter den
    Besitzer-Ring, deshalb ist er breiter als die Figur."""
    parts = [
        box((0.22, 0.22, 0.04), (0, 0, 0.04), "#d8c85a", 0.02),
        box((0.15, 0.15, 0.27), (0, 0, 0.36), "#e8d878", 0.04),
        box((0.12, 0.12, 0.12), (0, 0, 0.76), "#f2e8c8", 0.05),
        box((0.02, 0.02, 0.30), (0.18, 0.0, 0.42), "#8a7a3a", 0.0),
        box((0.01, 0.10, 0.12), (0.18, 0.10, 0.66), "#c8443a", 0.0),
    ]
    merge("hero", parts)


def make_monster():
    """Wachender Gegner auf der Karte. Die Kreaturenmodelle kommen erst in
    der naechsten Iteration; hier steht EIN Platzhalter mit eigener
    Silhouette - geduckt, breit, mit Hoernern. Vorher lag an dieser Stelle
    die weisse Markierungsscheibe, und die sah nicht nach Gegner aus,
    sondern nach Fehler."""
    merge("monster", [
        box((0.20, 0.16, 0.20), (0, 0, 0.22), "#4a3a4e", 0.05),
        box((0.13, 0.12, 0.11), (0, -0.10, 0.53), "#5c4860", 0.04),
        box((0.03, 0.03, 0.12), (-0.11, -0.08, 0.68), "#d8cfa8", 0.0,
            rot=(0, math.radians(-22), 0)),
        box((0.03, 0.03, 0.12), (0.11, -0.08, 0.68), "#d8cfa8", 0.0,
            rot=(0, math.radians(22), 0)),
        box((0.07, 0.07, 0.14), (-0.22, 0.02, 0.16), "#3a2e3e", 0.03),
        box((0.07, 0.07, 0.14), (0.22, 0.02, 0.16), "#3a2e3e", 0.03),
    ])


def make_objects():
    """Die zehn Kartenobjekte. Reihenfolge und Namen folgen den
    OBJECT_*-Konstanten im WorldMapScreen."""
    # Mine: Stollenmund am Hang.
    #
    # DER ERSTE ENTWURF WAR EIN SCHWARZER WUERFEL. Der Huegel stand in
    # #5c5148 (fast so dunkel wie das Loch), und das Loch selbst mass die
    # halbe Breite - auf dem Musterblatt blieb davon eine schwarze Kiste
    # ohne erkennbare Form. Jetzt ist der Huegel hell genug, dass seine
    # Kanten Licht fangen, das Loch klein und von Balken gerahmt.
    merge("obj_mine", [
        box((0.30, 0.24, 0.20), (0, 0.08, 0.20), "#7a6b5c", 0.05),
        box((0.09, 0.05, 0.11), (0, -0.15, 0.11), "#1c1610", 0.0),
        box((0.03, 0.03, 0.15), (-0.12, -0.16, 0.15), "#5a4025", 0.0),
        box((0.03, 0.03, 0.15), (0.12, -0.16, 0.15), "#5a4025", 0.0),
        box((0.15, 0.03, 0.03), (0, -0.16, 0.28), "#5a4025", 0.0),
    ])
    # Truhe.
    merge("obj_treasure", [
        box((0.20, 0.14, 0.11), (0, 0, 0.11), "#6b4a2a", 0.03),
        box((0.21, 0.15, 0.05), (0, 0, 0.26), "#d8b45a", 0.04),
    ])
    # Ressourcen-Haufen.
    merge("obj_pile", [
        box((0.20, 0.20, 0.11), (0, 0, 0.11), "#9a7a4a", 0.05),
        box((0.12, 0.12, 0.09), (0.06, 0.05, 0.30), "#b8944f", 0.04),
        box((0.07, 0.07, 0.06), (-0.10, -0.07, 0.28), "#d8b45a", 0.03),
    ])
    # Vier Schreine: gleiche Grundform, andere Kroenung und Farbe.
    for name, col in [("shrine_att", "#c85a4a"), ("shrine_def", "#5a86c8"),
                      ("shrine_power", "#a06bd0"), ("shrine_know", "#5ab88a")]:
        merge("obj_" + name, [
            box((0.17, 0.17, 0.07), (0, 0, 0.07), "#8a8378", 0.03),
            box((0.09, 0.09, 0.28), (0, 0, 0.40), "#b5aea0", 0.02),
            box((0.13, 0.13, 0.09), (0, 0, 0.76), col, 0.04),
        ])
    # Brunnen.
    merge("obj_well", [
        box((0.19, 0.19, 0.10), (0, 0, 0.10), "#8a8378", 0.04),
        box((0.14, 0.14, 0.04), (0, 0, 0.22), "#2f6f95", 0.02),
        box((0.02, 0.02, 0.24), (-0.15, 0, 0.34), "#4a3520", 0.0),
        box((0.02, 0.02, 0.24), (0.15, 0, 0.34), "#4a3520", 0.0),
        box((0.20, 0.14, 0.03), (0, 0, 0.60), "#6b4a2a", 0.02),
    ])
    # Lehrmeister: Turm mit Buch.
    merge("obj_learning", [
        box((0.16, 0.16, 0.42), (0, 0, 0.42), "#b5aea0", 0.03),
        box((0.19, 0.19, 0.06), (0, 0, 0.90), "#5a86c8", 0.03),
    ])
    # Windmuehle: Turm mit Fluegelkreuz.
    merge("obj_windmill", [
        box((0.15, 0.15, 0.40), (0, 0, 0.40), "#d8cfa8", 0.03),
        box((0.18, 0.18, 0.08), (0, 0, 0.88), "#9d3b32", 0.03),
        box((0.03, 0.32, 0.03), (-0.16, 0, 0.72), "#6b4a2a", 0.0,
            rot=(math.radians(30), 0, 0)),
        box((0.03, 0.03, 0.32), (-0.16, 0, 0.72), "#6b4a2a", 0.0,
            rot=(math.radians(30), 0, 0)),
    ])


def make_markers():
    """Flache Scheiben fuer die Ueberlagerungen: Reichweite, Bedrohung,
    Auswahl. Sie liegen knapp ueber der Kachel und bekommen ihre Farbe in
    Godot, deshalb hier neutral weiss."""
    # Die Scheibe traegt die Bedrohungsfarbe unter einem Gegner. Bei 0.46
    # Radius fuellte sie fast die ganze Kachel und leuchtete staerker als
    # alles andere im Bild - die Farbe soll melden, nicht schreien.
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=TILE * 0.32,
                                        depth=0.02, location=(0, 0, 0.01))
    ob = bpy.context.active_object
    ob.name = "marker_disc"
    ob.data.materials.append(material("marker_m", "#ffffff", rough=1.0))

    # Der Ring liegt UM das Modell herum, nicht darunter: bei 0.42 lag er
    # innerhalb des Stadtgrundrisses und war komplett verdeckt.
    bpy.ops.mesh.primitive_torus_add(major_radius=TILE * 0.455,
                                     minor_radius=0.03,
                                     major_segments=16, minor_segments=6,
                                     location=(0, 0, 0.02))
    ob = bpy.context.active_object
    ob.name = "marker_ring"
    ob.data.materials.append(material("ring_m", "#ffffff", rough=1.0))


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    make_terrain()
    make_battle_ground()
    make_fog()
    make_deco()
    make_scatter()
    make_cities()
    make_hero()
    make_monster()
    make_objects()
    make_markers()

    try:
        out = sys.argv[sys.argv.index("--") + 1]
    except (ValueError, IndexError):
        out = "world.glb"

    bk.export(out)


if __name__ == "__main__":
    main()
