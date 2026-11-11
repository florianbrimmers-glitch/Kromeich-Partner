extends SceneTree

# Headless-Preview: malt alle 28 Kampf-Token in eine Kontaktbogen-PNG,
# eine Zeile je Fraktion, Tier 1-7 von links nach rechts. So sehe ich
# ohne Display, ob die Silhouetten unterscheidbar sind.
#
#   /tmp/Godot_v4.6-stable_linux.x86_64 --headless --path game/ \
#     --script tools/preview_unit_tokens.gd
#
# Ergebnis: user://unit-tokens-preview.png (Pfad wird ausgegeben).

const TILE := 128
const OUT_PATH := "user://unit-tokens-preview.png"
const FACTION_DIRS := ["waldvolk", "menschen", "totenreich", "orks"]


func _init() -> void:
	var canvas := Image.create(TILE * 7, TILE * 4, false, Image.FORMAT_RGBA8)
	# Zeilenweise unterschiedlich getoenter Hintergrund, damit die
	# Fraktionen im Kontaktbogen auseinanderfallen.
	var row_bg: Array = [
		Color(0.09, 0.14, 0.10), Color(0.15, 0.13, 0.08),
		Color(0.12, 0.09, 0.15), Color(0.16, 0.09, 0.08),
	]
	for fid in range(4):
		for x in range(TILE * 7):
			for y in range(TILE):
				canvas.set_pixel(x, fid * TILE + y, row_bg[fid])

	var missing: int = 0
	for fid in range(4):
		var ids: Array = UnitType.ids_for_faction(fid)
		for t in range(ids.size()):
			var uid: String = String(ids[t])
			var path: String = "res://assets/units/%s/%s.svg" % [FACTION_DIRS[fid], uid]
			if not ResourceLoader.exists(path):
				print("[FEHLT] %s" % path)
				missing += 1
				continue
			var tex: Texture2D = load(path) as Texture2D
			if tex == null:
				print("[FEHLT] %s (load == null)" % path)
				missing += 1
				continue
			var img: Image = tex.get_image()
			# Importierte Texturen koennen VRAM-komprimiert sein - vor
			# resize/blend zwingend dekomprimieren (siehe game/CLAUDE.md).
			if img.is_compressed():
				img.decompress()
			img.convert(Image.FORMAT_RGBA8)
			img.resize(TILE, TILE, Image.INTERPOLATE_LANCZOS)
			canvas.blend_rect(img, Rect2i(0, 0, TILE, TILE),
				Vector2i(t * TILE, fid * TILE))
			print("[OK] %s (T%d)" % [uid, UnitType.tier_of(uid)])

	var err: int = canvas.save_png(OUT_PATH)
	print("")
	print("fehlende Token: %d" % missing)
	print("save_err=%d -> %s" % [err, ProjectSettings.globalize_path(OUT_PATH)])
	quit(0)
