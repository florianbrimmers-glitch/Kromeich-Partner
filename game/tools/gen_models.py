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
import sys

import bpy

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

def srgb(hexstr):
    """Hex -> linearer RGBA. glTF-Materialien rechnen linear; gibt man den
    sRGB-Wert direkt weiter, wirkt jede Farbe deutlich zu hell."""
    h = hexstr.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


def material(name, hexstr, rough=0.85):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = srgb(hexstr)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = 0.0
    m.diffuse_color = srgb(hexstr)
    return m


def box(name, size, loc, hexstr, bevel=0.02, rot=None):
    """Quader mit angefaster Kante. Die Fase ist der ganze Trick am
    Low-Poly-Look: ohne sie verschmelzen benachbarte Flaechen gleicher
    Farbe zu einer Masse, mit ihr faengt jede Kante einen Lichtsaum."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    # `size` sind HALBMASSE (Abstand von der Mitte zur Kante) - so sind
    # alle Zahlen hier geschrieben. Der Grundkoerper misst 1.0, also
    # verdoppeln.
    #
    # WARUM DAS HIER STEHT: im ersten Anlauf hat `box` die Werte als volle
    # Kantenlaenge genommen. Damit war JEDES Teil halb so gross - und weil
    # eine Kachel dann 0.5 breit ist, aber im Abstand 1.0 gesetzt wird,
    # zerfiel die Karte in schwebende Plaettchen mit Luecken dazwischen.
    # Genau so sah der allererste Prototyp aus; der Fehler ist beim
    # Uebertragen ins Projekt zurueckgekommen.
    ob.scale = (size[0] * 2.0, size[1] * 2.0, size[2] * 2.0)
    if rot:
        ob.rotation_euler = rot
    bpy.ops.object.transform_apply(scale=True, rotation=bool(rot))
    if bevel > 0:
        bpy.ops.object.modifier_add(type="BEVEL")
        ob.modifiers["Bevel"].width = bevel
        ob.modifiers["Bevel"].segments = 1
        bpy.ops.object.modifier_apply(modifier="Bevel")
    ob.data.materials.append(material(name + "_m", hexstr))
    return ob


def cone(name, radius, depth, loc, hexstr, verts=6):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=radius,
                                    depth=depth, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.data.materials.append(material(name + "_m", hexstr))
    return ob


def merge(name, objs):
    """Teile zu EINEM Mesh verschmelzen. Godot instanziiert die Modelle
    ueber MultiMesh - dafuer muss je Modell genau ein Mesh herauskommen."""
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = name
    return ob


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
        ob = box("t_" + name, (TILE * 0.5, TILE * 0.5, h * 0.5),
                 (0, 0, top - h * 0.5), col, bevel=0.015)
        ob.location = (0, 0, 0)


def make_deco():
    """Deko, die auf einer Kachel steht: Baum fuer Wald, Fels fuer Gebirge,
    Schilf fuer Sumpf. Godot streut sie deterministisch."""
    # HOEHE IST HIER EIN VERDECKUNGSPROBLEM, kein Geschmack: der erste Baum
    # war 1.01 hoch, also hoeher als eine Kachel breit ist. Bei 34 Grad
    # Neigung deckte er die Kachel dahinter fast ganz zu, und eine
    # Waldflaeche wurde zur Hecke, hinter der die Karte verschwand.
    trunk = box("d1", (0.04, 0.04, 0.10), (0, 0, 0.10), "#4a3520", 0.01)
    c1 = box("d2", (0.17, 0.17, 0.15), (0, 0, 0.35), "#2c5220", 0.07)
    c2 = box("d3", (0.11, 0.11, 0.10), (0, 0, 0.58), "#3e6c20", 0.05)
    merge("deco_tree", [trunk, c1, c2])

    r1 = box("e1", (0.18, 0.17, 0.14), (0, 0, 0.14), "#6f6a63", 0.05,
             rot=(0, 0, math.radians(18)))
    r2 = box("e2", (0.11, 0.10, 0.20), (0.13, -0.08, 0.20), "#7d7870", 0.04,
             rot=(0, math.radians(7), math.radians(-25)))
    merge("deco_rock", [r1, r2])

    stalks = []
    for i, (dx, dz, hh) in enumerate([(-0.12, 0.08, 0.26), (0.10, -0.06, 0.32),
                                      (0.02, 0.16, 0.20)]):
        stalks.append(box("s%d" % i, (0.02, 0.02, hh * 0.5), (dx, dz, hh * 0.5),
                          "#6b7a45", 0.0))
    merge("deco_reed", stalks)


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
        parts.append(box("k%d" % idx, (0.19, 0.19, 0.46), (-0.15, 0.12, 0.46),
                         light, 0.03))
        if fac == "waldvolk":
            parts.append(cone("kd%d" % idx, 0.25, 0.34, (-0.15, 0.12, 1.09),
                              dark, verts=8))
        elif fac == "menschen":
            parts.append(box("kd%d" % idx, (0.14, 0.14, 0.14), (-0.15, 0.12, 1.06),
                             dark, 0.05))
        elif fac == "totenreich":
            parts.append(cone("kd%d" % idx, 0.20, 0.44, (-0.15, 0.12, 1.14),
                              dark, verts=4))
        else:
            parts.append(box("kd%d" % idx, (0.21, 0.21, 0.08), (-0.15, 0.12, 1.00),
                             dark, 0.03, rot=(0, 0, math.radians(45))))
        parts.append(box("kh%d" % idx, (0.24, 0.17, 0.22), (0.18, -0.16, 0.22),
                         light, 0.03))
        parts.append(box("kr%d" % idx, (0.27, 0.20, 0.07), (0.18, -0.16, 0.51),
                         dark, 0.04))
        parts.append(box("kw%d" % idx, (0.38, 0.06, 0.15), (0.0, 0.34, 0.15),
                         dark, 0.02))
        merge("city_" + fac, parts)


def make_hero():
    """Held: Sockel, Koerper, Kopf, Banner. Der Sockel traegt spaeter den
    Besitzer-Ring, deshalb ist er breiter als die Figur."""
    parts = [
        box("h1", (0.22, 0.22, 0.04), (0, 0, 0.04), "#d8c85a", 0.02),
        box("h2", (0.15, 0.15, 0.27), (0, 0, 0.36), "#e8d878", 0.04),
        box("h3", (0.12, 0.12, 0.12), (0, 0, 0.76), "#f2e8c8", 0.05),
        box("h4", (0.02, 0.02, 0.30), (0.18, 0.0, 0.42), "#8a7a3a", 0.0),
        box("h5", (0.01, 0.10, 0.12), (0.18, 0.10, 0.66), "#c8443a", 0.0),
    ]
    merge("hero", parts)


def make_monster():
    """Wachender Gegner auf der Karte. Die Kreaturenmodelle kommen erst in
    der naechsten Iteration; hier steht EIN Platzhalter mit eigener
    Silhouette - geduckt, breit, mit Hoernern. Vorher lag an dieser Stelle
    die weisse Markierungsscheibe, und die sah nicht nach Gegner aus,
    sondern nach Fehler."""
    merge("monster", [
        box("g1", (0.20, 0.16, 0.20), (0, 0, 0.22), "#4a3a4e", 0.05),
        box("g2", (0.13, 0.12, 0.11), (0, -0.10, 0.53), "#5c4860", 0.04),
        box("g3", (0.03, 0.03, 0.12), (-0.11, -0.08, 0.68), "#d8cfa8", 0.0,
            rot=(0, math.radians(-22), 0)),
        box("g4", (0.03, 0.03, 0.12), (0.11, -0.08, 0.68), "#d8cfa8", 0.0,
            rot=(0, math.radians(22), 0)),
        box("g5", (0.07, 0.07, 0.14), (-0.22, 0.02, 0.16), "#3a2e3e", 0.03),
        box("g6", (0.07, 0.07, 0.14), (0.22, 0.02, 0.16), "#3a2e3e", 0.03),
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
        box("m1", (0.30, 0.24, 0.20), (0, 0.08, 0.20), "#7a6b5c", 0.05),
        box("m2", (0.09, 0.05, 0.11), (0, -0.15, 0.11), "#1c1610", 0.0),
        box("m3", (0.03, 0.03, 0.15), (-0.12, -0.16, 0.15), "#5a4025", 0.0),
        box("m4", (0.03, 0.03, 0.15), (0.12, -0.16, 0.15), "#5a4025", 0.0),
        box("m5", (0.15, 0.03, 0.03), (0, -0.16, 0.28), "#5a4025", 0.0),
    ])
    # Truhe.
    merge("obj_treasure", [
        box("c1", (0.20, 0.14, 0.11), (0, 0, 0.11), "#6b4a2a", 0.03),
        box("c2", (0.21, 0.15, 0.05), (0, 0, 0.26), "#d8b45a", 0.04),
    ])
    # Ressourcen-Haufen.
    merge("obj_pile", [
        box("p1", (0.20, 0.20, 0.11), (0, 0, 0.11), "#9a7a4a", 0.05),
        box("p2", (0.12, 0.12, 0.09), (0.06, 0.05, 0.30), "#b8944f", 0.04),
        box("p3", (0.07, 0.07, 0.06), (-0.10, -0.07, 0.28), "#d8b45a", 0.03),
    ])
    # Vier Schreine: gleiche Grundform, andere Kroenung und Farbe.
    for name, col in [("shrine_att", "#c85a4a"), ("shrine_def", "#5a86c8"),
                      ("shrine_power", "#a06bd0"), ("shrine_know", "#5ab88a")]:
        merge("obj_" + name, [
            box(name + "1", (0.17, 0.17, 0.07), (0, 0, 0.07), "#8a8378", 0.03),
            box(name + "2", (0.09, 0.09, 0.28), (0, 0, 0.40), "#b5aea0", 0.02),
            box(name + "3", (0.13, 0.13, 0.09), (0, 0, 0.76), col, 0.04),
        ])
    # Brunnen.
    merge("obj_well", [
        box("w1", (0.19, 0.19, 0.10), (0, 0, 0.10), "#8a8378", 0.04),
        box("w2", (0.14, 0.14, 0.04), (0, 0, 0.22), "#2f6f95", 0.02),
        box("w3", (0.02, 0.02, 0.24), (-0.15, 0, 0.34), "#4a3520", 0.0),
        box("w4", (0.02, 0.02, 0.24), (0.15, 0, 0.34), "#4a3520", 0.0),
        box("w5", (0.20, 0.14, 0.03), (0, 0, 0.60), "#6b4a2a", 0.02),
    ])
    # Lehrmeister: Turm mit Buch.
    merge("obj_learning", [
        box("l1", (0.16, 0.16, 0.42), (0, 0, 0.42), "#b5aea0", 0.03),
        box("l2", (0.19, 0.19, 0.06), (0, 0, 0.90), "#5a86c8", 0.03),
    ])
    # Windmuehle: Turm mit Fluegelkreuz.
    merge("obj_windmill", [
        box("n1", (0.15, 0.15, 0.40), (0, 0, 0.40), "#d8cfa8", 0.03),
        box("n2", (0.18, 0.18, 0.08), (0, 0, 0.88), "#9d3b32", 0.03),
        box("n3", (0.03, 0.32, 0.03), (-0.16, 0, 0.72), "#6b4a2a", 0.0,
            rot=(math.radians(30), 0, 0)),
        box("n4", (0.03, 0.03, 0.32), (-0.16, 0, 0.72), "#6b4a2a", 0.0,
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
    make_deco()
    make_cities()
    make_hero()
    make_monster()
    make_objects()
    make_markers()

    try:
        out = sys.argv[sys.argv.index("--") + 1]
    except (ValueError, IndexError):
        out = "world.glb"

    # Y-up: Godot rechnet mit Y nach oben, Blender mit Z. Der Exporter
    # dreht das, wenn man ihn laesst - sonst liegt die ganze Welt flach.
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB",
                              export_yup=True, export_apply=True)

    names = sorted(o.name for o in bpy.data.objects)
    tris = sum(len(o.data.polygons) for o in bpy.data.objects
               if o.type == "MESH")
    print("MODELLE %d: %s" % (len(names), ", ".join(names)))
    print("FLAECHEN gesamt: %d" % tris)


if __name__ == "__main__":
    main()
