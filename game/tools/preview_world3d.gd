extends SceneTree

# Vollvorschau der RAEUMLICHEN Weltkarte in Geraetegroesse (It. 53).
#
#   xvfb-run -a godot --path game/ --resolution 720x1280 \
#       --script tools/preview_world3d.gd
#
# ACHTUNG, ANDERS ALS ALLE ANDEREN VORSCHAU-WERKZEUGE: dieses hier braucht
# einen echten Grafikkontext. Die 2D-Vorschauen setzen ihr Bild
# rechnerisch aus Image-Aufrufen zusammen und laufen deshalb mit
# --headless; 3D muss wirklich gerendert werden, und --headless hat gar
# keinen Renderer. Unter einem virtuellen Bildschirm (Xvfb) nimmt Godot
# Mesas Software-OpenGL - langsam, aber es zeigt genau das, was auf dem
# Geraet zu sehen waere.
#
# Es nimmt eine ECHTE Karte aus _start(seed) und den Kontext, den die
# Ansicht auch im Spiel bekommt (_map3d_ctx). Ein Werkzeug mit eigenen
# Zahlen wuerde sich selbst bestaetigen - die Lehre aus It. 36/37.

const Map3D := preload("res://scripts/ui/WorldMap3D.gd")

const SEEDS := [4711, 90210]


func _init() -> void:
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	for sd in SEEDS:
		var wm = scene.instantiate()
		root.add_child(wm)
		await process_frame
		wm.call("_start", sd, 1)
		await process_frame

		# Die 2D-Karte UND den deckenden Hintergrund ausblenden: beide
		# liegen als Control ueber der 3D-Welt. Im Spiel sitzt die
		# raeumliche Ansicht spaeter in einem SubViewport INNERHALB der
		# Kartenflaeche, dort stellt sich die Frage nicht.
		var area: Control = wm.get("_map_area")
		if area != null:
			area.visible = false
		var bg := wm.get_node_or_null(^"Background") as Control
		if bg != null:
			bg.visible = false

		var view := Map3D.new()
		root.add_child(view)
		await process_frame

		var ctx: Dictionary = wm.call("_map3d_ctx")
		print("  Modelle geladen: ", view._meshes.size())
		view.refresh(ctx)
		var total := 0
		for k in view._multi.keys():
			total += (view._multi[k] as MultiMeshInstance3D).multimesh.instance_count
		print("  MultiMesh-Gruppen: ", view._multi.size(), " Aufstellungen: ", total)
		# Auf die Kartenmitte schauen, ganze Breite im Bild.
		var w: int = int(ctx["width"])
		var h: int = int(ctx["height"])
		# Auf den HELDEN schauen, nicht auf die Kartenmitte: zu Spielbeginn
		# liegt fast alles im Nebel, und die Mitte ist schwarz.
		var focus := Vector2(float(w) * 0.5, float(h) * 0.5)
		var hs: Array = ctx["heroes"] as Array
		if not hs.is_empty():
			var hp: Vector2i = (hs[0] as Dictionary)["pos"]
			focus = Vector2(float(hp.x), float(hp.y))
		view.look_at_map(focus, 9.0)

		print("  Kamera: ", view._cam.position, " ", view._cam.rotation_degrees,
			" size=", view._cam.size, " current=", view._cam.current)
		for i in range(4):
			await process_frame
		var img: Image = root.get_texture().get_image()
		var path: String = "user://world3d-%d.png" % sd
		var err: int = img.save_png(path)
		print("Seed %d: %d Kacheln, %d Staedte, %d Objekte, %d Monster -> %s (err=%d)"
			% [sd, (ctx["tiles"] as Array).size(), (ctx["cities"] as Array).size(),
				(ctx["objects"] as Array).size(), (ctx["monsters"] as Array).size(),
				ProjectSettings.globalize_path(path), err])

		view.queue_free()
		wm.queue_free()
		await process_frame
	quit(0)
