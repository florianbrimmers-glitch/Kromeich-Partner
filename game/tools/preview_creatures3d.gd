extends SceneTree

# Musterblatt aller 28 Kreaturen in Zellgroesse (It. 54).
#
#   xvfb-run -a -s "-screen 0 1200x900x24" godot --path game/ \
#       --resolution 1200x900 --script tools/preview_creatures3d.gd
#
# Das raeumliche Gegenstueck zum Kontaktbogen der 2D-Sprites. Es geht durch
# BattleField3D, nicht an ihr vorbei: ein Werkzeug mit eigenem Aufbau
# wuerde den eigenen Aufbau pruefen (die Lehre aus It. 36/37).
#
# VIER REIHEN, SIEBEN SPALTEN - Fraktion mal Stufe. Nebeneinander sieht
# man, was auf dem Brett allein nie auffaellt: ob zwei Silhouetten
# verwechselbar sind und ob die Groesse wirklich die Stufe erzaehlt.

const Field := preload("res://scripts/ui/BattleField3D.gd")

const FACTIONS := ["menschen", "waldvolk", "totenreich", "orkstaemme"]


func _init() -> void:
	var f := Field.new()
	root.add_child(f)
	await process_frame

	var units: Array = _units()
	var stacks: Array = []
	for u in units:
		var ud: Dictionary = u as Dictionary
		var col: int = int(ud["tier"]) - 1
		var row: int = FACTIONS.find(String(ud["faction"]))
		if row < 0:
			continue
		stacks.append({
			"pos": Vector2i(col, row * 2),
			"type": String(ud["id"]),
			# Beide Seiten im Bild: so sieht man, ob eine Kreatur nach
			# links wie nach rechts lesbar ist.
			"side": 0 if row % 2 == 0 else 1,
			"active": col == 3,
		})
	f.refresh({"cols": 7, "rows": 8, "terrain": 0, "seed": 7,
		"stacks": stacks, "obstacles": [], "move": [], "targets": []})
	# ZWEI REIHEN LUFT OBEN. Beim ersten Lauf war die oberste Reihe
	# angeschnitten: eine Figur steht zwar auf ihrer Zelle, ihr Kopf
	# erscheint bei 40 Grad Neigung aber gut eine Reihe weiter oben.
	f.look_at_cells(Vector2(3.0, 3.6), 9.6)
	for i in range(4):
		await process_frame
	for ch in f.get_children():
		if ch is DirectionalLight3D:
			print("  DBG Licht rot=", (ch as DirectionalLight3D).rotation_degrees,
				" energie=", (ch as DirectionalLight3D).light_energy,
				" schatten=", (ch as DirectionalLight3D).shadow_enabled)
		if ch is WorldEnvironment:
			var e := (ch as WorldEnvironment).environment
			print("  DBG Umgebung quelle=", e.ambient_light_source,
				" energie=", e.ambient_light_energy,
				" tonemap=", e.tonemap_mode)
	var path := "user://creatures3d-sheet.png"
	var err: int = root.get_texture().get_image().save_png(path)
	var missing: Array = []
	for u in units:
		if not f._meshes.has(String((u as Dictionary)["id"])):
			missing.append(String((u as Dictionary)["id"]))
	print("Kreaturen: %d, ohne Modell: %s -> %s (err=%d)"
		% [units.size(), str(missing), ProjectSettings.globalize_path(path), err])
	quit(0)


func _units() -> Array:
	var f := FileAccess.open("res://data/units.json", FileAccess.READ)
	var d: Dictionary = JSON.parse_string(f.get_as_text()) as Dictionary
	return d["units"] as Array
