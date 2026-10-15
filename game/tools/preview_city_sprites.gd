extends SceneTree

# Headless-Preview-Renderer: laedt alle Stadt-SVGs, malt sie in ein Bild
# und speichert es als PNG. So sehe ich nach jeder SVG-Aenderung sofort,
# wie's aussieht - auch ohne Display.
#
#   /tmp/Godot_v4.6-stable_linux.x86_64 --headless --path game/ \
#     --script tools/preview_city_sprites.gd
#
# Ergebnis: /tmp/kromeich-sprites-preview.png

const ASSETS := [
	"res://assets/city/menschen/kaserne.svg",
	"res://assets/city/menschen/schmiede.svg",
	"res://assets/city/menschen/reiterei.svg",
	"res://assets/city/menschen/markt.svg",
	"res://assets/city/menschen/wachturm.svg",
	"res://assets/city/menschen/kapelle.svg",
	"res://assets/city/menschen/spaeher.svg",
	"res://assets/city/_shared/construction.svg",
]
const TILE := 256
const COLS := 4
const ROWS := 2
const OUT_PATH := "user://city-sprites-preview.png"


func _init() -> void:
	var canvas := Image.create(TILE * COLS, TILE * ROWS, false, Image.FORMAT_RGBA8)
	# Hintergrund: dunkler Stein-Look wie im Spiel-Backdrop.
	canvas.fill(Color(0.10, 0.12, 0.14, 1.0))

	for i in range(ASSETS.size()):
		var path: String = ASSETS[i]
		var tex: Texture2D = load(path) as Texture2D
		if tex == null:
			push_warning("kein Sprite: %s" % path)
			continue
		var img: Image = tex.get_image()
		# Auf TILE-Groesse skalieren.
		img.resize(TILE, TILE, Image.INTERPOLATE_LANCZOS)
		var col: int = i % COLS
		var row: int = i / COLS
		var x: int = col * TILE
		var y: int = row * TILE
		canvas.blend_rect(img, Rect2i(0, 0, TILE, TILE), Vector2i(x, y))
		print("[OK] %s" % path)

	var save_err: int = canvas.save_png(OUT_PATH)
	print("save_err=%d -> %s" % [save_err, ProjectSettings.globalize_path(OUT_PATH)])
	quit(0)
