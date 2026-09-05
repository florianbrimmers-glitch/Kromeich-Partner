extends SceneTree

# Der raeumliche Kampfschirm in Geraetegroesse (It. 55).
#
#   xvfb-run -a -s "-screen 0 720x1280x24" godot --path game/ \
#       --resolution 720x1280 --script tools/preview_battle3d.gd
#
# BRAUCHT EINEN ECHTEN GRAFIKKONTEXT, anders als preview_battle_full.gd:
# das aeltere Werkzeug setzt sein Bild rechnerisch aus Image-Aufrufen
# zusammen und laeuft deshalb mit --headless; 3D muss wirklich gerendert
# werden, und --headless hat gar keinen Renderer.
#
# Es nimmt einen ECHTEN TacticalBattleScreen mit set_battle() und schaltet
# ueber DEN KNOPF um, den auch der Spieler drueckt. Gespeichert werden
# BEIDE Ansichten desselben Kampfes - der Vergleich ist der Zweck: dieselbe
# Aufstellung, dieselben Zahlen, dieselben Laufziele.

const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")

const CASES := [
	{"terrain": 0, "name": "gras",
		"player": [{"type": "men_spearman", "count": 24},
			{"type": "men_archer", "count": 12},
			{"type": "men_cavalier", "count": 5}],
		"enemy": [{"type": "ork_goblin", "count": 30},
			{"type": "ork_ogre", "count": 4},
			{"type": "ork_behemoth", "count": 1}]},
	{"terrain": 5, "name": "sumpf",
		"player": [{"type": "elf_dwarf", "count": 18},
			{"type": "elf_archer", "count": 9},
			{"type": "elf_goldwyrm", "count": 2}],
		"enemy": [{"type": "nec_skeleton", "count": 40},
			{"type": "nec_lich", "count": 6},
			{"type": "nec_bonedragon", "count": 2}]},
]


func _init() -> void:
	for case in CASES:
		var bs = TBS.new()
		bs.fx_speed = 0.0
		root.add_child(bs)
		await process_frame
		bs.set_battle({
			"player_stacks": case["player"],
			"enemy_stacks": case["enemy"],
			"seed": 31337, "terrain_id": int(case["terrain"]),
			"allow_flee": true, "player_att": 3, "player_def": 2,
		})
		for i in range(3):
			await process_frame
		var name: String = String(case["name"])
		var e2: int = root.get_texture().get_image().save_png(
			"user://battle2d-%s.png" % name)

		bs.call("_toggle_view3d")
		for i in range(6):
			await process_frame
		var path: String = "user://battle3d-%s.png" % name
		var err: int = root.get_texture().get_image().save_png(path)
		var f = bs.get("_field3d")
		var total := 0
		for k in f._multi.keys():
			total += (f._multi[k] as MultiMeshInstance3D).multimesh.instance_count
		print("%s: %d Aufstellungen in %d Gruppen, Zelle %.1f px -> %s (err=%d, 2D err=%d)"
			% [name, total, f._multi.size(), f.cell_pixels(),
				ProjectSettings.globalize_path(path), err, e2])
		bs.queue_free()
		await process_frame
	quit(0)
