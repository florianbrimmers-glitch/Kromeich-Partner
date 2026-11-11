extends SceneTree

# PILOT-VERGLEICH (It. 71): dieselbe Kampfaufstellung mit drei Modellsaetzen.
#
#   xvfb-run -a -s "-screen 0 1040x1485x24" godot --path game/ \
#       --resolution 1040x1485 --script tools/pilot/preview_pilot.gd
#
# Gerendert wird mit DERSELBEN Klasse wie im Spiel (BattleField3D): gleiche
# Kamera, gleiches Licht, gleiche Ringe und gleicher Rand. Getauscht wird nur
# die Kreaturen-Datei. Die Fenstergroesse ist die gemessene Gitterflaeche des
# Kampfschirms (1040 x 1485, It. 69) - also genau das, was auf dem Handy
# zwischen Kopfzeile und Knopfreihe steht.
#
# Je Satz zwei Bilder: das ganze Brett (so sieht man es im Spiel) und eine
# Nahaufnahme (so sieht man, was die Modelle koennen).

const Field := preload("res://scripts/ui/BattleField3D.gd")

const SETS := [
	{"name": "jetzt", "path": "res://assets/models/creatures.glb"},
	{"name": "cc0", "path": "res://pilot_assets/cc0.glb"},
	{"name": "eigen", "path": "res://pilot_assets/own.glb"},
]

# Menschen gegen Orks - eine Paarung, die es im Spiel gibt, und fuer die es
# in jedem Satz alle sechs Figuren gibt.
const STACKS := [
	{"pos": Vector2i(2, 2), "type": "men_spearman", "side": 0, "active": true},
	{"pos": Vector2i(2, 4), "type": "men_archer", "side": 0},
	{"pos": Vector2i(2, 6), "type": "men_cavalier", "side": 0},
	{"pos": Vector2i(5, 2), "type": "ork_goblin", "side": 1},
	{"pos": Vector2i(5, 4), "type": "ork_wolfrider", "side": 1},
	{"pos": Vector2i(5, 6), "type": "ork_behemoth", "side": 1},
]


func _init() -> void:
	for set in SETS:
		var path: String = String(set["path"])
		if not ResourceLoader.exists(path):
			print("%s: Datei fehlt (%s) - uebersprungen" % [set["name"], path])
			continue
		var f = Field.new()
		# Die Hindernisse (Stein, Busch) liegen in creatures.glb - deshalb
		# wird sie IMMER geladen und der Pilotsatz darueber gelegt. Gleiche
		# Namen ueberschreiben, die Hindernisse bleiben.
		f.model_paths = [Field.WORLD_PATH, Field.CREATURES_PATH, path]
		root.add_child(f)
		await process_frame
		f.refresh({"cols": 8, "rows": 8, "terrain": 0, "seed": 7,
			"stacks": STACKS,
			"obstacles": [{"pos": Vector2i(4, 1), "kind": 0},
				{"pos": Vector2i(3, 5), "kind": 2}],
			"move": [], "targets": []})
		f.frame_board(8, 8)
		for i in range(4):
			await process_frame
		var a: String = "user://pilot-%s-brett.png" % set["name"]
		var e1: int = root.get_texture().get_image().save_png(a)

		# Nahaufnahme: zwei Zellen breit auf die Mitte zwischen den Linien.
		f.look_at_cells(Vector2(3.5, 4.0), 4.2)
		for i in range(4):
			await process_frame
		var b: String = "user://pilot-%s-nah.png" % set["name"]
		var e2: int = root.get_texture().get_image().save_png(b)
		print("%s: Brett err=%d, nah err=%d -> %s" % [set["name"], e1, e2,
			ProjectSettings.globalize_path(a)])
		f.queue_free()
		await process_frame
	quit(0)
