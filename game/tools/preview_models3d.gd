extends SceneTree

# Musterblatt aller 3D-Modelle (It. 53).
#
#   xvfb-run -a -s "-screen 0 900x900x24" godot --path game/ \
#       --resolution 900x900 --script tools/preview_models3d.gd
#
# Das Gegenstueck zu unit-tokens-preview.png, nur raeumlich: alles, was der
# Generator baut, EINMAL nebeneinander und in Kachelgroesse.
#
# WARUM ES DAS BRAUCHT: auf der ganzen Weltkarte faellt ein zu grosses
# Modell nicht auf - es sieht nur "voll" aus. Erst nebeneinander sieht man,
# dass ein Baum hoeher war als eine Kachel breit ist und die Stadt ueber
# ihr Feld hinausragte. Beide Fehler standen im ersten Entwurf und sind auf
# der Karte niemandem aufgefallen, mir zuerst auch nicht.
#
# Es geht durch WorldMap3D.refresh, nicht an ihr vorbei: ein Werkzeug mit
# eigenem Aufbau wuerde den eigenen Aufbau pruefen, nicht den des Spiels.

const Map3D := preload("res://scripts/ui/WorldMap3D.gd")

const W := 14
const H := 9

# Die zehn Kartenobjekte in der Reihenfolge der OBJECT_*-Konstanten.
const OBJ_MODEL := {
	0: "obj_mine", 1: "obj_treasure", 2: "obj_pile", 3: "obj_shrine_att",
	4: "obj_shrine_def", 5: "obj_shrine_power", 6: "obj_shrine_know",
	7: "obj_well", 8: "obj_learning", 9: "obj_windmill",
}


func _init() -> void:
	var view := Map3D.new()
	root.add_child(view)
	await process_frame

	# Links sechs Gelaendespalten (die Deko streut die Ansicht selbst),
	# rechts Gras als Buehne fuer alles, was auf einer Kachel steht.
	var tiles: Array = []
	var fog: Array = []
	for y in range(H):
		for x in range(W):
			tiles.append(x if x < 6 else 0)
			# Die untere Reihe im Nebel: so steht die Abdunklung neben der
			# vollen Farbe und laesst sich vergleichen.
			fog.append(1 if y == H - 1 else 2)

	var cities: Array = []
	for i in range(4):
		cities.append({"pos": Vector2i(7 + i * 2, 1), "faction": i,
			"color": Color(0.45, 1.0, 0.45)})
	var objects: Array = []
	for k in OBJ_MODEL.keys():
		var idx: int = int(k)
		objects.append({"pos": Vector2i(7 + idx % 7, 3 + (idx / 7) * 2),
			"kind": idx})
	view.refresh({
		"tiles": tiles, "width": W, "height": H, "fog": fog, "seed": 4711,
		"cities": cities, "objects": objects,
		"monsters": [{"pos": Vector2i(12, 5), "color": Color(1.0, 0.35, 0.35)},
			{"pos": Vector2i(13, 5), "color": Color(0.45, 1.0, 0.45)}],
		"heroes": [{"pos": Vector2i(10, 5), "color": Color(1.0, 0.92, 0.45)}],
		"enemies": [{"pos": Vector2i(11, 5), "color": Color(0.85, 0.15, 0.15)}],
		"faction_dirs": ["waldvolk", "menschen", "totenreich", "orks"],
		"object_model": OBJ_MODEL,
	})
	view.look_at_map(Vector2(float(W) * 0.5 - 0.5, float(H) * 0.5 - 0.5),
		float(W) + 1.0)
	for i in range(4):
		await process_frame
	var path := "user://models3d-sheet.png"
	var err: int = root.get_texture().get_image().save_png(path)
	var total := 0
	for k in view._multi.keys():
		total += (view._multi[k] as MultiMeshInstance3D).multimesh.instance_count
	print("Modelle: %d, Aufstellungen: %d -> %s (err=%d)"
		% [view._meshes.size(), total, ProjectSettings.globalize_path(path), err])
	quit(0)
