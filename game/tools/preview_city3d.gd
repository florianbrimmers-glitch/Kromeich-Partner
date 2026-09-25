extends SceneTree

# Der raeumliche Stadtschirm in Geraetegroesse (It. 56).
#
#   xvfb-run -a -s "-screen 0 720x1280x24" godot --path game/ \
#       --resolution 720x1280 --script tools/preview_city3d.gd
#
# BRAUCHT EINEN ECHTEN GRAFIKKONTEXT (siehe preview_world3d.gd). Es nimmt
# einen ECHTEN CityScreen mit refresh(ctx) und schaltet ueber DEN KNOPF um,
# den auch der Spieler drueckt; gespeichert werden BEIDE Ansichten
# derselben Stadt.

const CS := preload("res://scripts/ui/CityScreen.gd")
const UnitArt := preload("res://scripts/core/UnitArt.gd")

const CASES := [
	{"name": "menschen-voll", "faction": 1, "built": ["zitadelle", "kapelle",
		"schmiede", "markt", "kaserne", "wachturm", "reiterei", "spaeher",
		"mauer"]},
	{"name": "orks-halb", "faction": 3,
		"built": ["kaserne", "markt", "schmiede"]},
	# NEUE STADT - der haeufigste Anblick im Spiel und bis It. 69 in keinem
	# Vorschauwerkzeug enthalten. Beide Faelle oben haben etwas gebaut;
	# dass alle NEUN Baustellen identisch aussahen, konnte deshalb keine
	# Vorschau zeigen. Der Nutzer hat es auf dem Handy gesehen.
	{"name": "orks-neu", "faction": 3, "built": []},
	{"name": "menschen-neu", "faction": 1, "built": []},
	# Alle vier Fraktionen ausgebaut: die Dachmaterialien (It. 70) haengen
	# an der Palette, also muss jede einmal zu sehen sein.
	{"name": "orks-voll", "faction": 3, "built": ["zitadelle", "kapelle",
		"schmiede", "markt", "kaserne", "wachturm", "reiterei", "spaeher",
		"mauer"]},
	{"name": "totenreich-voll", "faction": 2, "built": ["zitadelle",
		"kapelle", "schmiede", "markt", "kaserne", "wachturm", "reiterei",
		"spaeher", "mauer"]},
	{"name": "waldvolk-voll", "faction": 0, "built": ["zitadelle",
		"kapelle", "schmiede", "markt", "kaserne", "wachturm", "reiterei",
		"spaeher", "mauer"]},
]


func _init() -> void:
	var defs: Array = _building_defs()
	for case in CASES:
		var cs = CS.new()
		cs.set_anchors_preset(Control.PRESET_FULL_RECT)
		root.add_child(cs)
		await process_frame
		# open(), nicht refresh(): _ready setzt `visible = false`, der
		# Schirm wird erst beim Oeffnen sichtbar. Mit refresh() blieb das
		# Bild einfach grau - und zwar ohne eine einzige Fehlermeldung.
		cs.open({
			"city": {"faction": int(case["faction"]),
				"buildings": case["built"], "garrison": []},
			"buildings": defs,
			"faction_names": ["Waldvolk", "Menschen", "Totenreich", "Orks"],
			"faction_colors": [Color(0.45, 0.85, 0.45), Color(0.95, 0.85, 0.35),
				Color(0.70, 0.45, 0.90), Color(0.95, 0.35, 0.30)],
			"wallet": Wallet.new(), "own_city": true, "hero_here": false,
			"day": 1, "week": 1, "month": 1,
		})
		for i in range(3):
			await process_frame
		var e2: int = root.get_texture().get_image().save_png(
			"user://city2d-%s.png" % String(case["name"]))

		cs.call("_toggle_view3d")
		for i in range(6):
			await process_frame
		var path: String = "user://city3d-%s.png" % String(case["name"])
		var err: int = root.get_texture().get_image().save_png(path)
		var v = cs.get("_city3d")
		var total := 0
		for k in v._multi.keys():
			total += (v._multi[k] as MultiMeshInstance3D).multimesh.instance_count
		print("%s: %d Aufstellungen in %d Gruppen -> %s (err=%d, 2D err=%d)"
			% [String(case["name"]), total, v._multi.size(),
				ProjectSettings.globalize_path(path), err, e2])
		cs.queue_free()
		await process_frame
	quit(0)


func _building_defs() -> Array:
	var f := FileAccess.open("res://data/factions.json", FileAccess.READ)
	var d: Dictionary = JSON.parse_string(f.get_as_text()) as Dictionary
	if d.has("buildings"):
		return d["buildings"] as Array
	# Rueckfall: die neun Bauplaetze aus dem Layout, ohne Beschreibung.
	var g := FileAccess.open("res://data/city_layout.json", FileAccess.READ)
	var l: Dictionary = JSON.parse_string(g.get_as_text()) as Dictionary
	var out: Array = []
	for bid in (l["buildings"] as Dictionary).keys():
		out.append({"id": String(bid), "name": String(bid).capitalize()})
	return out
