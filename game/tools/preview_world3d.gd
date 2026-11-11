extends SceneTree

# Vollvorschau der RAEUMLICHEN Weltkarte in Geraetegroesse (It. 53).
#
#   xvfb-run -a -s "-screen 0 720x1280x24" godot --path game/ \
#       --resolution 720x1280 --script tools/preview_world3d.gd
#
# ACHTUNG, ANDERS ALS ALLE ANDEREN VORSCHAU-WERKZEUGE: dieses hier braucht
# einen echten Grafikkontext. Die 2D-Vorschauen setzen ihr Bild
# rechnerisch aus Image-Aufrufen zusammen und laufen deshalb mit
# --headless; 3D muss wirklich gerendert werden, und --headless hat gar
# keinen Renderer. Unter einem virtuellen Bildschirm (Xvfb) nimmt Godot
# Mesas Software-OpenGL - langsam, aber es zeigt genau das, was auf dem
# Geraet zu sehen waere.
#
# Es nimmt eine ECHTE Karte aus _start(seed) und schaltet die Ansicht mit
# DEM KNOPF um, den auch der Spieler drueckt. Der erste Entwurf hat die
# 2D-Karte von Hand ausgeblendet und eine eigene WorldMap3D danebengestellt
# - damit haette er die Einbettung (SubViewport, Kamera aus _view_offset,
# Tap ueber den Strahl) gar nicht geprueft, sondern nur die Modelle.

const SEEDS := [4711, 90210]


func _init() -> void:
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	for sd in SEEDS:
		var wm = scene.instantiate()
		root.add_child(wm)
		await process_frame
		wm.call("_start", sd, 1)
		await process_frame

		# ZUERST die 2D-Karte mit demselben Ausschnitt speichern. Der
		# Vergleich ist der eigentliche Zweck: beide Ansichten muessen
		# denselben Kartenausschnitt zeigen, sonst springt das Bild beim
		# Umschalten. Die Kamera rechnet sich aus _view_offset und
		# _tile_size - stimmt der Ausschnitt nicht, ist genau diese
		# Umrechnung falsch.
		var h0 = wm.call("get", "_hero")
		if h0 != null:
			wm.call("_center_view_on", h0.position)
		for i in range(3):
			await process_frame
		var err2: int = root.get_texture().get_image().save_png(
			"user://world2d-%d.png" % sd)

		wm.call("_toggle_view3d")
		# Auf den HELDEN schauen, nicht auf die Kartenmitte: zu Spielbeginn
		# liegt fast alles im Nebel, und die Mitte ist schwarz. Das geht
		# ueber dieselbe Zentrierung, die auch ein Tap auf die Minikarte
		# ausloest - die Kamera folgt daraus.
		var h = wm.call("get", "_hero")
		if h != null:
			wm.call("_center_view_on", h.position)
		for i in range(6):
			await process_frame

		var img: Image = root.get_texture().get_image()
		var path: String = "user://world3d-%d.png" % sd
		var err: int = img.save_png(path)
		var view = wm.get("_map3d")
		var total := 0
		for k in view._multi.keys():
			total += (view._multi[k] as MultiMeshInstance3D).multimesh.instance_count
		print("Seed %d: %d Aufstellungen in %d Gruppen -> %s (err=%d, 2D-Vergleich err=%d)"
			% [sd, total, view._multi.size(),
				ProjectSettings.globalize_path(path), err, err2])

		wm.queue_free()
		await process_frame
	quit(0)
