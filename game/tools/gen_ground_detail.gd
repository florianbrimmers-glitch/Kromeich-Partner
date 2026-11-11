extends SceneTree

# Strukturkarten fuer den Schlachtfeldboden (It. 73).
#
#   godot --headless --path game/ --script tools/gen_ground_detail.gd -- \
#       <ordner-mit-den-poly-haven-jpgs>
#
# Quelle: drei Bodenfotos von Poly Haven (CC0, siehe
# assets/textures/battle/SOURCES.md). Aus jedem wird die reine
# HELLIGKEITSSCHWANKUNG gerechnet - Helligkeit je Pixel durch den
# Mittelwert, gespeichert als Wert/2 (0.5 = Mittel) in einem 8-Bit-Graubild.
# Die Farbe kommt nicht aus dem Foto, sondern aus der Palette im Shader
# (battle_ground.gdshader): echte Kleinstruktur, gemalter Farbton.
#
# VORAB GERECHNET, nicht im Spiel: im Pilot lief diese Rechnung bei jedem
# Start als GDScript-Schleife ueber eine Million Pixel je Bild - auf dem
# Handy mehrere Sekunden Ladezeit fuer etwas, das sich nie aendert.
#
# Die Quell-JPGs werden nicht eingecheckt (zusammen 2,6 MB); die erzeugten
# Graubilder schon, genau wie die glb-Dateien - die CI braucht weder
# Internet noch dieses Werkzeug.

const OUT := "res://assets/textures/battle/detail_%s.png"
const SIZE := 512
const SOURCES := {
	"grass_a": "leafy_grass.jpg",
	"grass_b": "sparse_grass.jpg",
	"dirt": "dirt_aerial_02.jpg",
}


func _init() -> void:
	var src_dir: String = OS.get_cmdline_user_args()[0]
	DirAccess.make_dir_recursive_absolute(
		ProjectSettings.globalize_path("res://assets/textures/battle"))
	for key in SOURCES.keys():
		var img := Image.load_from_file(src_dir.path_join(SOURCES[key]))
		if img == null or img.is_empty():
			push_error("fehlt: " + String(SOURCES[key]))
			quit(1)
			return
		img.convert(Image.FORMAT_RGB8)
		img.resize(SIZE, SIZE, Image.INTERPOLATE_LANCZOS)
		var lum := PackedFloat32Array()
		lum.resize(SIZE * SIZE)
		var sum := 0.0
		for y in range(SIZE):
			for x in range(SIZE):
				var c: Color = img.get_pixel(x, y)
				var l: float = c.r * 0.299 + c.g * 0.587 + c.b * 0.114
				lum[y * SIZE + x] = l
				sum += l
		var mean: float = maxf(0.01, sum / float(SIZE * SIZE))
		var out := Image.create(SIZE, SIZE, false, Image.FORMAT_L8)
		for y in range(SIZE):
			for x in range(SIZE):
				var v: float = clampf(lum[y * SIZE + x] / mean * 0.5, 0.0, 1.0)
				out.set_pixel(x, y, Color(v, v, v))
		var path: String = OUT % key
		var err: int = out.save_png(ProjectSettings.globalize_path(path))
		print("%s <- %s  Mittel %.3f  err=%d" % [path, SOURCES[key], mean, err])
	quit(0)
