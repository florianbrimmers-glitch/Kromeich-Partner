#!/usr/bin/env python3
"""PILOT: CC0-Modelle von Quaternius als Kampffiguren (It. 71).

    /opt/blender/blender -b --factory-startup -noaudio \
        --python game/tools/pilot/gen_pilot_cc0.py -- \
        game/pilot_assets/cc0.glb <ordner-mit-den-paketen>

Der Paketordner enthaelt die entpackten Google-Drive-Ordner der Pakete
"RPG Characters" (dl_rpg) und "Ultimate Animated Animals" (dl_animals).
Beide sind CC0 1.0 - geprueft an der License-Datei IM Paket, nicht nur an
der Webseite.

WAS PASSIERT:
  1. Modell importieren (glTF, wo es eins gibt - dort kommen die Texturen
     zuverlaessig mit; sonst FBX).
  2. EINE Pose aus der mitgelieferten Animation waehlen und ins Mesh
     backen. Ohne das stuende jede Figur in der T-Pose, mit ausgestreckten
     Armen - der unnatuerlichste Anblick ueberhaupt.
  3. Alle Teile zu einem Mesh verschmelzen (MultiMesh braucht eines je
     Modell) und mit gen_creatures.fit_to_tier auf die Stufengroesse
     bringen - DIESELBE Regel wie im Spiel, damit der Vergleich fair ist.

LUECKE, UND DAS IST EIN BEFUND: fuer ork_goblin gibt es in den freien
Paketen kein Modell (der Goblin aus dem Vorschaubild von "Animated
Monster" ist im kostenlosen Download nicht enthalten). Der Pilot zeigt an
dieser Stelle das jetzige Modell. Ebenso hat der Kavalier keinen Reiter -
die Figuren haben keine Sitz-Animation, und eine Figur in Standhaltung
auf ein Pferd zu stellen, saehe schlechter aus als gar keine.
"""

import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import blender_kit as bk  # noqa: E402
import gen_creatures as gc  # noqa: E402

# (Einheit, Stufe, Datei relativ zum Paketordner, bevorzugte Posen)
SOURCES = [
    ("men_spearman", 1, "dl_rpg/glTF/Warrior.gltf",
     ["Idle_Attacking", "Idle_Weapon", "Idle"]),
    ("men_archer", 2, "dl_rpg/glTF/Ranger.gltf",
     ["Idle_Attacking", "Idle_Weapon", "Idle"]),
    ("men_cavalier", 6, "dl_animals/glTF/Horse_White.gltf", ["Walk", "Idle"]),
    ("ork_wolfrider", 2, "dl_animals/glTF/Wolf.gltf", ["Walk", "Idle"]),
    ("ork_behemoth", 7, "dl_animals/glTF/Bull.gltf", ["Walk", "Idle"]),
]

# Wo in der Animation die Pose genommen wird (Anteil der Laenge). Ein
# Drittel in einen Schritt hinein steht ein Vierbeiner im diagonalen
# Schritt - die lebendigste Standhaltung.
POSE_AT = 0.30


def import_any(path):
    if path.lower().endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)


def pick_action(actions, wanted):
    for w in wanted:
        for a in actions:
            # Namen sehen je nach Format anders aus: "Idle_CharacterArmature"
            # (glTF) oder "AnimalArmature|AnimalArmature|Idle" (FBX).
            tail = a.name.split("|")[-1]
            if tail == w or tail.startswith(w + "_"):
                return a
    return actions[0] if actions else None


def is_child_of(ob, arm):
    p = ob.parent
    while p is not None:
        if p == arm:
            return True
        p = p.parent
    return False


def bake_one(uid, tier, path, wanted):
    objs_before = set(bpy.data.objects)
    acts_before = set(bpy.data.actions)
    import_any(path)
    new = [o for o in bpy.data.objects if o not in objs_before]
    acts = [a for a in bpy.data.actions if a not in acts_before]
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    if arm is None:
        raise SystemExit("%s: kein Skelett in %s" % (uid, path))

    act = pick_action(acts, wanted)
    if act is not None:
        arm.animation_data_create()
        arm.animation_data.action = act
        f0, f1 = act.frame_range
        bpy.context.scene.frame_set(int(f0 + (f1 - f0) * POSE_AT))
    print("%s: Pose %s" % (uid, act.name if act else "(keine)"))

    # Nur Meshes, die am Skelett haengen - lose Hilfsobjekte (der Krieger
    # bringt eine nackte Icosphere ohne Material mit) bleiben draussen.
    meshes = [o for o in new if o.type == "MESH" and is_child_of(o, arm)]
    dg = bpy.context.evaluated_depsgraph_get()
    baked = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev)
        nob = bpy.data.objects.new(uid + "_part", me)
        bpy.context.collection.objects.link(nob)
        nob.matrix_world = o.matrix_world.copy()
        baked.append(nob)

    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)

    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in baked:
        o.select_set(True)
    bpy.context.view_layer.objects.active = baked[0]
    bk._bake(baked[0])
    ob = bk.merge(uid, baked)
    bk._bake(ob)
    gc.fit_to_tier(ob, tier)
    return ob


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    out, root = args[0], args[1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for uid, tier, rel, wanted in SOURCES:
        bake_one(uid, tier, os.path.join(root, rel), wanted)
    # Uebrig gebliebene Aktionen mit exportieren wuerde nur die Datei
    # aufblaehen - die Posen sind eingebacken.
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bk.export(out)


if __name__ == "__main__":
    main()
