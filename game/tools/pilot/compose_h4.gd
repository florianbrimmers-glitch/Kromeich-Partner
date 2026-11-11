extends SceneTree

# Vorbild, jetziger Stand und Pilot nebeneinander, beschriftet (It. 72).
#
#   xvfb-run -a -s "-screen 0 1640x860x24" godot --path game/ \
#       --resolution 1640x860 --script tools/pilot/compose_h4.gd -- \
#       <vorbild.png> <jetzt.png> <pilot.png> <ziel.png>
#
# Jedes Bild wird mittig auf das Hochformat der Kampfflaeche zugeschnitten
# (das Vorbild ist ein Querformat-Bildschirmfoto) und auf gleiche Groesse
# gebracht. Gebaut in einem eigenen SubViewport - die Fensterskalierung des
# Projekts liess sich nicht abschalten (siehe compose_pilot.gd).

const TITLES := ["Heroes 4 (Vorbild)", "Jetzt im Spiel", "Pilot (neu)"]
const W := 520
const H := 742
const GAP := 12
const HEAD := 64


func _fit(img: Image) -> Image:
	var want: float = float(W) / float(H)
	var iw: int = img.get_width()
	var ih: int = img.get_height()
	var cw: int = iw
	var ch: int = ih
	if float(iw) / float(ih) > want:
		cw = int(ih * want)
	else:
		ch = int(iw / want)
	var out := img.get_region(Rect2i((iw - cw) / 2, (ih - ch) / 2, cw, ch))
	out.resize(W, H, Image.INTERPOLATE_LANCZOS)
	return out


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var size := Vector2i(3 * W + 4 * GAP, H + HEAD + 2 * GAP)
	var vp := SubViewport.new()
	vp.size = size
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(vp)
	var holder := Control.new()
	vp.add_child(holder)
	var bg := ColorRect.new()
	bg.color = Color(0.08, 0.09, 0.11)
	bg.size = Vector2(size)
	holder.add_child(bg)
	for i in range(3):
		var img := Image.load_from_file(args[i])
		if img == null or img.is_empty():
			print("fehlt ", args[i])
			continue
		img.convert(Image.FORMAT_RGBA8)
		var tr := TextureRect.new()
		tr.texture = ImageTexture.create_from_image(_fit(img))
		var x: float = GAP + i * (W + GAP)
		tr.position = Vector2(x, HEAD + GAP)
		holder.add_child(tr)
		var lb := Label.new()
		lb.text = TITLES[i]
		lb.add_theme_font_size_override("font_size", 32)
		lb.add_theme_color_override("font_color", Color(0.95, 0.88, 0.6))
		lb.position = Vector2(x, 12)
		lb.size = Vector2(W, HEAD - 12)
		lb.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		holder.add_child(lb)
	for k in range(4):
		await process_frame
	var err: int = vp.get_texture().get_image().save_png(args[3])
	print("Vergleich err=%d -> %s" % [err, args[3]])
	quit(0)
