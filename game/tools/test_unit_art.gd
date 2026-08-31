extends SceneTree

# Headless-Tests fuer die Kreatur-Bilder in der Oberflaeche (It. 29):
#
#   godot --headless --path game/ --script tools/test_unit_art.gd
#
# Abgedeckt:
#   1. UnitArt: jede der 28 Einheiten hat ein Sprite, der Pfad benutzt das
#      VERZEICHNIS (orks) und nicht den Fraktionsnamen aus units.json
#      (orkstaemme) - dieser Fehler hat schon einmal eine Vorschau
#      "kaputt" aussehen lassen, obwohl die Dateien da waren
#   2. Werte-Zeile stimmt mit units.json ueberein
#   3. Rekrutier-Panel: Bild + Werte in jeder Zeile
#   4. Garnisons-Panel: Bild in jeder Zeile
#   5. Heldenblatt auf der Weltkarte: oeffnet, listet die Armee mit Bild,
#      und sagt bei leerer Armee etwas Sinnvolles
#
# Jede Test-Funktion setzt am Ende eine Marke - ein Laufzeitfehler bricht
# in GDScript nur die Funktion ab, die Suite bliebe sonst gruen.

const UnitArt := preload("res://scripts/core/UnitArt.gd")

# Geraetegroesse (Portrait, wie im Export).
const DEVICE_W := 1080
const DEVICE_H := 1920

var _fails: int = 0
var _done: Array = []


func _init() -> void:
	_test_module()
	_test_recruit_panel()
	_test_garrison_panel()
	await _test_hero_panel()

	# Abschluss-Marken: die Soll-Liste kommt aus der Methodentabelle des
	# Skripts selbst (It. 31, vorher eine Liste von Hand). Damit faellt
	# zweierlei auf: eine Funktion, die mitten drin abbricht, UND eine neue
	# Testfunktion, die niemand aus _init aufruft.
	var missing: Array = []
	for m in get_method_list():
		var mn: String = String(m["name"])
		if mn.begins_with("_test") and not _done.has(mn):
			missing.append(mn)
	_check(missing.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)"
		% str(missing))

	print("")
	if _fails == 0:
		print("Kreatur-Bild-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Kreatur-Bild-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_module() -> void:
	print("== UnitArt ==")
	var ids: Array = UnitType.all_ids()
	_check(ids.size() == 28, "28 Einheiten in units.json (sind %d)" % ids.size())
	var missing: Array = []
	var bad_dir: Array = []
	for uid in ids:
		var u: String = String(uid)
		if UnitArt.texture_for(u) == null:
			missing.append(u)
		var path: String = UnitArt.path_for(u)
		if path.contains("orkstaemme") or path.is_empty():
			bad_dir.append(u)
	_check(missing.is_empty(), "jede Einheit hat ein Sprite (fehlen: %s)" % str(missing))
	_check(bad_dir.is_empty(), "Pfade benutzen das Verzeichnis, nicht den JSON-Namen (%s)"
		% str(bad_dir))
	_check(UnitArt.path_for("ork_goblin").contains("/orks/"),
		"Orks liegen unter /orks/ (ist '%s')" % UnitArt.path_for("ork_goblin"))
	_check(UnitArt.texture_for("gibt_es_nicht") == null,
		"unbekannte ID gibt null statt eines Absturzes")
	_check(UnitArt.icon("gibt_es_nicht", 64) == null,
		"und kein leeres Bild-Element (der Aufrufer behaelt seine Textzeile)")
	var ic: TextureRect = UnitArt.icon("nec_skeleton", 96)
	_check(ic != null and ic.texture != null, "icon() liefert ein bestuecktes TextureRect")
	if ic != null:
		_check(int(ic.custom_minimum_size.x) == 96, "in der angeforderten Groesse")
		ic.free()

	# Werte-Zeile gegen die JSON.
	var t: Dictionary = UnitType.get_type("men_archer")
	var line: String = UnitArt.stat_line("men_archer")
	_check(line.contains("A%d" % int(t["att"])) and line.contains("V%d" % int(t["def"])),
		"Werte-Zeile nennt Angriff und Verteidigung ('%s')" % line)
	_check(line.contains("TP%d" % int(t["hp"])), "und die Trefferpunkte")
	_check(line.contains("Schuss"), "Fernkaempfer zeigen ihre Munition")
	_check(not UnitArt.stat_line("men_spearman").contains("Schuss"),
		"Nahkaempfer nicht")
	_done.append("_test_module")


func _city_ctx(hero: Hero, city: Dictionary) -> Dictionary:
	return {
		"city": city, "hero": hero,
		"buildings": [
			{"id": "kaserne", "name": "Kaserne", "cost": {"gold": 500}, "effect": "x"},
		],
		"faction_names": ["Waldvolk", "Menschen", "Totenreich", "Orks"],
		"faction_colors": [Color.GREEN, Color.GOLD, Color.PURPLE, Color.RED],
		"calendar": "T1 W1 M1 J1", "hero_here": true,
	}


# Zaehlt die TextureRects in einer Zeile.
func _icons_in(node: Node) -> int:
	var n: int = 0
	for c in node.get_children():
		if c is TextureRect and (c as TextureRect).texture != null:
			n += 1
	return n


func _test_recruit_panel() -> void:
	print("")
	print("== Rekrutier-Panel ==")
	var cs := CityScreen.new()
	cs.size = Vector2(1080, 1920)
	root.add_child(cs)
	var hero := Hero.new(Vector2i(0, 0))
	hero.gold = 5000
	var city: Dictionary = {"faction": 1, "pos": Vector2i(0, 0),
		"buildings": ["kaserne"], "pools": {"men_spearman": 3, "men_archer": 2}}
	cs.open(_city_ctx(hero, city))
	cs._open_recruit_panel("kaserne")
	_check(cs._recruit_panel.visible, "Panel steht")
	var rows: Array = cs._recruit_rows_box.get_children()
	_check(rows.size() == 2, "zwei Zeilen (sind %d)" % rows.size())
	var without_icon: Array = []
	for r in rows:
		if _icons_in(r) != 1:
			without_icon.append(str(r))
	_check(without_icon.is_empty(), "jede Zeile zeigt genau ein Kreatur-Bild")
	# Die Werte muessen in der Zeile stehen - vorher stand dort nur Name,
	# Tier, Bestand und Wachstum.
	var lbl: Label = cs._recruit_labels["men_archer"] as Label
	_check(lbl != null and lbl.text.contains("Armbruster"),
		"Name in der Zeile ('%s')" % (lbl.text if lbl != null else ""))
	_check(lbl != null and lbl.text.contains("TP%d" % UnitType.hp_of("men_archer")),
		"Kampfwerte in der Zeile")
	_check(lbl != null and lbl.text.contains("+%d/Wo" % UnitType.growth_of("men_archer")),
		"Wachstum weiterhin drin")
	cs.queue_free()
	_done.append("_test_recruit_panel")


func _test_garrison_panel() -> void:
	print("")
	print("== Garnisons-Panel ==")
	var cs := CityScreen.new()
	cs.size = Vector2(1080, 1920)
	root.add_child(cs)
	var hero := Hero.new(Vector2i(0, 0))
	hero.army = {"men_spearman": 4}
	var city: Dictionary = {"faction": 1, "pos": Vector2i(0, 0),
		"buildings": ["kaserne"], "pools": {},
		"garrison_army": {"men_archer": 2, "nec_skeleton": 7}}
	cs.open(_city_ctx(hero, city))
	cs._open_garrison_panel()
	_check(cs._gar_panel.visible, "Panel steht")
	var rows: Array = []
	for c in cs._gar_rows.get_children():
		if c is HBoxContainer:
			rows.append(c)
	_check(rows.size() == 3, "drei Einheiten-Zeilen (sind %d)" % rows.size())
	var no_icon: int = 0
	for r in rows:
		if _icons_in(r) != 1:
			no_icon += 1
	_check(no_icon == 0, "jede Zeile zeigt ein Kreatur-Bild (%d ohne)" % no_icon)
	cs.queue_free()
	_done.append("_test_garrison_panel")


func _test_hero_panel() -> void:
	print("")
	print("== Heldenblatt auf der Weltkarte ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	# Der Knopf muss in der Szene liegen, sonst gibt es das Blatt im Spiel
	# nicht - der Code allein reicht nicht.
	var btn = wm.get_node_or_null(wm.hero_button_path)
	_check(btn != null, "Held-Knopf steckt in WorldMap.tscn")
	wm.call("_start", 321, 1)
	await process_frame

	var hero = wm.get("_hero")
	hero.army = {"men_angel": 1, "men_spearman": 12, "men_archer": 5}
	wm.call("_open_hero_panel")
	await process_frame
	_check(wm.get("_hero_panel") != null and wm.get("_hero_panel").visible,
		"Blatt steht")
	var box = wm.get("_hero_panel_army")
	var rows: Array = []
	for c in box.get_children():
		if c is HBoxContainer:
			rows.append(c)
	_check(rows.size() == 3, "drei Stacks gelistet (sind %d)" % rows.size())
	var no_icon: int = 0
	for r in rows:
		if _icons_in(r) != 1:
			no_icon += 1
	_check(no_icon == 0, "jeder Stack mit Bild (%d ohne)" % no_icon)
	# Sortierung nach Tier: der Speertraeger (T1) steht vor dem Engel (T7).
	var first_text: String = ""
	for c in (rows[0] as HBoxContainer).get_children():
		if c is Label:
			first_text = (c as Label).text
	_check(first_text.contains("Speertraeger"),
		"nach Tier sortiert, T1 oben ('%s')" % first_text.split("\n")[0])
	# Werte des Helden stehen mit drauf.
	var stats = wm.get("_hero_panel_stats")
	_check(stats != null and stats.text.contains("Angriff"),
		"Heldenwerte im Blatt")

	# Leere Armee: Hinweis statt leerer Flaeche.
	hero.army = {}
	wm.call("_fill_hero_panel")
	await process_frame
	var has_hint := false
	for c in box.get_children():
		if c is Label and (c as Label).text.contains("Keine Einheiten"):
			has_hint = true
	_check(has_hint, "leere Armee erklaert sich")

	# ABENTEUER-ZAUBER-ZEILE (It. 43). Sie kommt nur, wenn der Held den
	# Zauber ueberhaupt kennt - Weisheit III und die richtige Schule.
	var srow = wm.get("_hero_panel_spells")
	_check(srow != null, "Zauber-Zeile ist im Blatt angelegt")
	_check(srow.get_child_count() == 0,
		"ohne Weisheit steht dort nichts (sind %d)" % srow.get_child_count())

	# GEOMETRIE IN GERAETEGROESSE (It. 43). Das Blatt hat eine FESTE Hoehe;
	# jede neue Zeile nimmt der Armee-Liste Platz weg. Zwei Dinge muessen
	# gelten: das Blatt bleibt auf dem Schirm, und sein Inhalt passt hinein
	# - sonst rutscht der Schliessen-Knopf unter den Rand und das Blatt
	# laesst sich auf dem Geraet nicht mehr zumachen.
	wm.set_anchors_preset(Control.PRESET_TOP_LEFT)
	wm.size = Vector2(DEVICE_W, DEVICE_H)
	await process_frame
	# Vollprogramm: Zauber-Zeile BESETZT, Wechsel-Zeile besetzt, lange
	# Armee. Die Fraktion wird auf Waldvolk gestellt, denn nur die Schule
	# Natur kennt das Stadttor - sonst messe ich eine leere Zeile und
	# glaube, es passe alles.
	wm.set("_player_faction", 0)
	hero.skills = {"wisdom": 3, "logistics": 2, "estates": 1}
	hero.knowledge = 10
	hero.army = {"men_spearman": 12, "men_archer": 5, "men_griffin": 3,
		"men_crusader": 2, "men_angel": 1}
	var h2 := Hero.new(hero.position + Vector2i(2, 0),
		int(wm.get("BASE_MAX_MP")))
	(wm.get("_heroes") as Array).append(h2)
	wm.call("_recompute_fog_player")
	wm.call("_recompute_costs")
	wm.call("_fill_hero_panel")
	await process_frame
	_check(srow.get_child_count() == 1,
		"mit Weisheit III und Natur steht das Stadttor da (sind %d)"
		% srow.get_child_count())
	_check((wm.get("_hero_panel_switch") as HBoxContainer).get_child_count() == 2,
		"und zwei Wechsel-Knoepfe")
	var panel: Panel = wm.get("_hero_panel")
	var prect: Rect2 = panel.get_rect()
	var screen := Rect2(Vector2.ZERO, Vector2(DEVICE_W, DEVICE_H))
	_check(screen.encloses(prect), "Blatt liegt ganz auf dem Schirm %s" % str(prect))
	var vb: VBoxContainer = null
	for c2 in panel.get_children():
		if c2 is VBoxContainer:
			vb = c2 as VBoxContainer
	_check(vb != null, "Inhalts-Box gefunden")
	if vb != null:
		var used: float = 0.0
		var closer: Control = null
		for c3 in vb.get_children():
			var cc: Control = c3 as Control
			used += cc.get_rect().size.y
			if cc is Button and String((cc as Button).text) == "Schliessen":
				closer = cc
		used += float(vb.get_child_count() - 1) * 16.0   # separation
		_check(used <= vb.get_rect().size.y + 1.0,
			"Inhalt passt in das Blatt (%d von %d px)"
			% [int(used), int(vb.get_rect().size.y)])
		_check(closer != null, "Schliessen-Knopf ist da")
		if closer != null:
			_check(screen.encloses(closer.get_global_rect()),
				"und liegt auf dem Schirm %s" % str(closer.get_global_rect()))

	wm.queue_free()
	await process_frame
	_done.append("_test_hero_panel")
