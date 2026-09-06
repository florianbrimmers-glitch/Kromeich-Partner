"""Gemeinsame Bausteine fuer die Blender-Generatoren (It. 53).

    import blender_kit as bk

WARUM EINE EIGENE DATEI: `gen_models.py` (Weltkarte) und
`gen_creatures.py` (Kreaturen) brauchen dieselben vier Handgriffe -
Quader, Kegel, Material, Verschmelzen. Eine Kopie davon in beiden Dateien
waere dieselbe Falle wie die nachgebaute Nachbarschaft im Durchspiel-Test
(It. 42) und die eigenen Zahlen in den Vorschauwerkzeugen (It. 36/37):
sie laufen beim naechsten Umbau auseinander, und zwar still.

ALLE MASSE SIND HALBMASSE - Abstand von der Mitte zur Kante. Der erste
Anlauf hat sie als volle Kantenlaenge gelesen; damit war jedes Teil halb
so gross, und weil eine Kachel dann 0.5 breit ist, aber im Abstand 1.0
steht, zerfiel die Karte in schwebende Plaettchen.
"""

import math

import bpy


def srgb(hexstr):
    """Hex -> linearer RGBA. glTF-Materialien rechnen linear; gibt man den
    sRGB-Wert direkt weiter, wirkt jede Farbe deutlich zu hell."""
    h = hexstr.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


_mat_cache = {}


def material(name, hexstr, rough=0.85):
    """Materialien werden nach FARBE zwischengespeichert, nicht nach Name.

    Ohne den Zwischenspeicher bekommt jeder Quader sein eigenes Material.
    Beim Verschmelzen bleiben daraus eigene Flaechengruppen - eine Kreatur
    aus fuenfzehn Teilen hatte fuenfzehn davon, obwohl sie nur fuenf Farben
    traegt. Das kostet Dateigroesse und, schwerer wiegend, EINEN
    ZEICHENAUFRUF PRO GRUPPE: der Sinn des MultiMesh war, dass ein Modell
    einen Aufruf kostet.
    """
    key = (hexstr, round(rough, 3))
    if key in _mat_cache:
        return _mat_cache[key]
    m = bpy.data.materials.new(name)
    _mat_cache[key] = m
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = srgb(hexstr)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = 0.0
    m.diffuse_color = srgb(hexstr)
    return m


_n = [0]


def _uniq(prefix):
    _n[0] += 1
    return "%s_%d" % (prefix, _n[0])


def _bake(ob):
    """Lage, Drehung und Groesse in die MESHDATEN schreiben.

    WARUM DAS SEIN MUSS: `merge` verschmilzt in das ERSTE Teil, und das
    Ergebnis behaelt dessen Objektursprung. Godot liest aus dem glb nur
    das Mesh, nicht die Knotenlage - ein Ursprung ungleich null geht dabei
    verloren. Kegel und Kugel hatten ihn zuerst nicht eingebacken: Moench
    und Lich standen deshalb bis zur Huefte im Boden (ihr erstes Teil ist
    der Kegel, Ursprung 0.34 ueber dem Fuss), und die Markierungsscheiben
    lagen 0.01 zu tief. Gesehen hat man nur Letzteres nicht.
    """
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def box(size, loc, hexstr, bevel=0.02, rot=None, name=None, taper=1.0,
        segments=0):
    """Quader mit angefaster Kante, wahlweise nach oben verjuengt.

    Die Fase ist der ganze Trick am Low-Poly-Look: ohne sie verschmelzen
    benachbarte Flaechen gleicher Farbe zu einer Masse, mit ihr faengt
    jede Kante einen Lichtsaum. Zwei Segmente statt einem runden die
    Kante spuerbar ab, ohne dass daraus ein rundes Modell wird.

    `taper` skaliert die OBERE Flaeche: 0.7 macht aus dem Quader einen
    Stumpf, 1.3 einen umgekehrten. Damit bekommen Rumpf, Hals und Beine
    eine Form statt einer Kastenkontur - das ist der Unterschied zwischen
    "Figur" und "Klotz", und er kostet keine einzige zusaetzliche Flaeche.

    REIHENFOLGE IST WICHTIG: die Verjuengung passiert, solange das Mesh
    noch um seinen eigenen Nullpunkt liegt. Nach transform_apply steckt
    die Position in den Punkten, und ein Skalieren der oberen Flaeche
    wuerde das Teil verschieben statt es zu formen.
    """
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    ob = bpy.context.active_object
    ob.name = name or _uniq("box")
    ob.scale = (size[0] * 2.0, size[1] * 2.0, size[2] * 2.0)
    if rot:
        ob.rotation_euler = rot
    if taper != 1.0:
        me = ob.data
        zmax = max(v.co.z for v in me.vertices)
        for v in me.vertices:
            if abs(v.co.z - zmax) < 1e-6:
                v.co.x *= taper
                v.co.y *= taper
    bpy.ops.object.transform_apply(scale=True, rotation=bool(rot))
    if bevel > 0:
        # ZWEI FASENSTUFEN NUR AN GROSSEN TEILEN (segments=0 heisst
        # "entscheide selbst"). Die zweite Stufe rundet sichtbar ab, aber
        # sie verdoppelt die Flaechen - und an einem 3 cm langen Horn
        # sieht das niemand. Ohne diese Unterscheidung wuchs der
        # Kreaturensatz von 1,0 auf 3,1 MB, und rund zwei Drittel davon
        # steckten in Teilen, die auf dem Schirm wenige Pixel gross sind.
        seg = segments
        if seg <= 0:
            seg = 2 if min(size) > 0.06 else 1
        bpy.ops.object.modifier_add(type="BEVEL")
        ob.modifiers["Bevel"].width = bevel
        ob.modifiers["Bevel"].segments = seg
        bpy.ops.object.modifier_apply(modifier="Bevel")
    ob.data.materials.append(material(ob.name + "_m", hexstr))
    return ob


def cone(radius, depth, loc, hexstr, verts=6, rot=None, name=None):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=radius,
                                    depth=depth, location=loc)
    ob = bpy.context.active_object
    ob.name = name or _uniq("cone")
    if rot:
        ob.rotation_euler = rot
    _bake(ob)
    ob.data.materials.append(material(ob.name + "_m", hexstr))
    return ob


def ball(radius, loc, hexstr, subdiv=1, name=None):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdiv, radius=radius,
                                          location=loc)
    ob = bpy.context.active_object
    ob.name = name or _uniq("ball")
    _bake(ob)
    ob.data.materials.append(material(ob.name + "_m", hexstr))
    return ob


def plane(size, loc, hexstr, name=None):
    """Flache Flaeche OHNE Seitenflaechen.

    WOFUER: Kacheln, die luecken- und nahtlos aneinanderstossen sollen.
    Ein Quader hat Seitenflaechen, und die zweier benachbarter Kacheln
    liegen bei voller Kachelbreite exakt aufeinander - sie streiten sich
    dann um die Tiefe (Z-Fighting), was in Baendern aufblitzt. Der Ausweg
    ueber eine Fase oder eine kleinere Kachel loest das, hinterlaesst aber
    eine sichtbare Fuge. Eine Flaeche hat das Problem gar nicht: zwei
    benachbarte liegen in derselben Ebene, ueberlappen sich aber nicht.
    """
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=loc)
    ob = bpy.context.active_object
    ob.name = name or _uniq("plane")
    ob.scale = (size[0], size[1], 1.0)
    _bake(ob)
    ob.data.materials.append(material(ob.name + "_m", hexstr))
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


def export(path):
    # Y-up: Godot rechnet mit Y nach oben, Blender mit Z. Der Exporter
    # dreht das, wenn man ihn laesst - sonst liegt die ganze Welt flach.
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB",
                              export_yup=True, export_apply=True)
    names = sorted(o.name for o in bpy.data.objects)
    tris = sum(len(o.data.polygons) for o in bpy.data.objects
               if o.type == "MESH")
    print("MODELLE %d: %s" % (len(names), ", ".join(names)))
    print("FLAECHEN gesamt: %d" % tris)


def rad(deg):
    return math.radians(deg)
