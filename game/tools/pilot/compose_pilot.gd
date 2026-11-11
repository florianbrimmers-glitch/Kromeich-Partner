extends SceneTree

# Setzt die Pilotbilder nebeneinander, beschriftet (It. 71).
#
#   xvfb-run -a -s "-screen 0 1584x830x24" godot --path game/ \
#       --resolution 1584x830 --script tools/pilot/compose_pilot.gd
#
# Liest, was preview_pilot.gd geschrieben hat, und legt je Ansicht (nah,
# brett) ein Vergleichsbild an: links der jetzige Stand, Mitte CC0, rechts
# selbst gebaut. Schrift gibt es im Image-Objekt nicht - deshalb echte
# Labels in der Szene und ein Bildschirmfoto davon.

const COLS := [
	{"key": "jetzt", "title": "Jetzt im Spiel"},
	{"key": "cc0", "title": "CC0 (Quaternius)"},
	{"key": "eigen", "title": "Selbst gebaut (neu)"},
]
const W := 520
const H := 742
const GAP := 12
const HEAD := 64


func _init() -> void:
	# EIGENER SUBVIEWPORT MIT FESTER GROESSE. Das Projekt skaliert seine
	# Oberflaeche auf die Handygroesse (canvas_items, 1080x1920), und das
	# Hauptfenster liess sich davon zur Laufzeit nicht abbringen - weder ueber
	# content_scale_mode noch ueber content_scale_factor. Ein SubViewport hat
	# diese Skalierung gar nicht.
	var size := Vector2i(3 * W + 4 * GAP, H + HEAD + 2 * GAP)
	for view in ["nah", "brett"]:
		var vp := SubViewport.new()
		vp.size = size
		vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		root.add_child(vp)
		var holder := Control.new()
		vp.add_child(holder)
		var bg := ColorRect.new()
		bg.color = Color(0.08, 0.09, 0.11)
		bg.size = Vector2(3 * W + 4 * GAP, H + HEAD + 2 * GAP)
		holder.add_child(bg)
		for i in range(COLS.size()):
			var c: Dictionary = COLS[i]
			var x: float = GAP + i * (W + GAP)
			var path: String = "user://pilot-%s-%s.png" % [c["key"], view]
			var img := Image.load_from_file(ProjectSettings.globalize_path(path))
			if img == null or img.is_empty():
				continue
			img.resize(W, H, Image.INTERPOLATE_LANCZOS)
			var tr := TextureRect.new()
			tr.texture = ImageTexture.create_from_image(img)
			tr.position = Vector2(x, HEAD + GAP)
			holder.add_child(tr)
			var lb := Label.new()
			lb.text = String(c["title"])
			lb.add_theme_font_size_override("font_size", 32)
			lb.add_theme_color_override("font_color", Color(0.95, 0.88, 0.6))
			lb.position = Vector2(x, 12)
			lb.size = Vector2(W, HEAD - 12)
			lb.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			holder.add_child(lb)
		for k in range(4):
			await process_frame
		var out: String = "user://pilot-vergleich-%s.png" % view
		var err: int = vp.get_texture().get_image().save_png(out)
		print("%s err=%d -> %s" % [view, err, ProjectSettings.globalize_path(out)])
		vp.queue_free()
		await process_frame
	quit(0)
