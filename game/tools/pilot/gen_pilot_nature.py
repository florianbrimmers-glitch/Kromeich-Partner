#!/usr/bin/env python3
"""PILOT: Ausstattung fuer das Kampffeld im Heroes-4-Stil (It. 72).

    /opt/blender/blender -b --factory-startup -noaudio \
        --python game/tools/pilot/gen_pilot_nature.py -- \
        game/pilot_assets/nature.glb <ordner-mit-den-poly-haven-modellen>

QUELLE: Poly Haven (CC0). Geplant war "Ultimate Stylized Nature" von
Quaternius - Google Drive meldete fuer dessen Dateien "Quota exceeded",
das Download-Kontingent war erschoepft.

Poly-Haven-Modelle sind FOTOGRAMMETRIE fuer Film und Standbild, keine
Spielmodelle: eine Tanne wog 487 MB, ein kleiner Baum 101 MB. Jedes
Modell wird deshalb auf ein Flaechenbudget REDUZIERT (Decimate) - das ist
derselbe Schritt, den jede Spiele-Pipeline mit solchen Vorlagen macht.

Jede Datei wird zu EINEM Modell und auf eine Zielhoehe in Zellen gebracht,
abgelesen am Heroes-4-Kampfbild: Baeume gut doppelt bis dreifach so hoch
wie eine Figur, Bueche knie- bis hufthoch, Blumen und Gras Bodendecker.
Die Namen beginnen mit der Klasse (tree_, bush_, rock_, flower_, grass_) -
preview_h4_battle.gd streut danach.
"""

import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import blender_kit as bk  # noqa: E402

# Poly-Haven-Kennung -> (Modellname, Zielhoehe in Zellen, Flaechenbudget)
WANT = [
    ("island_tree_01", "tree_island_1", 3.2, 9000),
    ("island_tree_02", "tree_island_2", 2.9, 9000),
    ("searsia_lucida", "tree_searsia", 2.2, 6000),
    ("searsia_burchellii", "bush_searsia", 1.0, 3000),
    ("shrub_01", "bush_shrub", 0.7, 2500),
    ("dead_tree_trunk", "rock_deadtrunk", 0.6, 1500),
    ("rock_moss_set_01", "rock_moss", 0.55, 1500),
    ("boulder_01", "rock_boulder", 0.8, 1500),
    ("flower_gazania", "flower_gazania", 0.24, 800),
    ("celandine_01", "flower_celandine", 0.20, 800),
    ("grass_medium_01", "grass_1", 0.34, 1200),
    ("grass_medium_02", "grass_2", 0.30, 1200),
]


def import_one(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def height_of(ob):
    import mathutils
    zs = [(ob.matrix_world @ mathutils.Vector(c)).z for c in ob.bound_box]
    return max(zs) - min(zs), min(zs)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    out, src = args[0], args[1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    done = []
    for fname, name, target, budget in WANT:
        path = os.path.join(src, fname, fname + "_1k.gltf")
        if not os.path.exists(path):
            print("FEHLT", fname)
            continue
        new = import_one(path)
        meshes = [o for o in new if o.type == "MESH"]
        for o in new:
            if o.type != "MESH":
                # Leere Elternknoten weg, ihre Lage bleibt in den Kindern.
                for c in o.children:
                    mw = c.matrix_world.copy()
                    c.parent = None
                    c.matrix_world = mw
        for o in new:
            if o.type != "MESH":
                bpy.data.objects.remove(o, do_unlink=True)
        for o in bpy.context.selected_objects:
            o.select_set(False)
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.object.transform_apply(location=False, rotation=True,
                                       scale=True)
        ob = bk.merge(name, meshes)
        faces = len(ob.data.polygons)
        if faces > budget:
            m = ob.modifiers.new("dec", "DECIMATE")
            m.ratio = budget / float(faces)
            bpy.ops.object.modifier_apply(modifier="dec")
        print("%-18s %8d -> %6d Flaechen" % (name, faces, len(ob.data.polygons)))
        h, z0 = height_of(ob)
        k = target / max(h, 1e-4)
        ob.scale = (k, k, k)
        bpy.ops.object.transform_apply(scale=True)
        h2, z1 = height_of(ob)
        ob.location = (0.0, 0.0, -z1)
        bpy.ops.object.transform_apply(location=True)
        # Mitte des Fusses auf den Ursprung.
        import mathutils
        cs = [ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
        cx = (max(c.x for c in cs) + min(c.x for c in cs)) * 0.5
        cy = (max(c.y for c in cs) + min(c.y for c in cs)) * 0.5
        ob.location = (-cx, -cy, 0.0)
        bpy.ops.object.transform_apply(location=True)
        done.append("%s %.2f" % (name, h2))
    print("NATUR:", ", ".join(done))
    bk.export(out)


if __name__ == "__main__":
    main()
