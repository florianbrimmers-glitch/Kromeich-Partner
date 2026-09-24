extends SceneTree

# Headless-Tests fuer die raeumlichen Kreaturen und das Kampffeld (It. 54):
#
#   godot --headless --path game/ --script tools/test_creatures3d.gd
#
# WIE AUSSEHEN wird hier nicht geprueft - dafuer gibt es
# tools/preview_creatures3d.gd. Diese Suite haelt die Stellen fest, an
# denen etwas SCHIEF sein kann, ohne dass ein Bild es verraet:
#
#  * Eine Einheit ohne Modell faellt stumm aus (_fill kehrt einfach um).
#  * Ein Modell, dessen Ursprung nicht eingebacken ist, verliert seinen
#    Versatz beim Laden - Moench und Lich standen so bis zur Huefte im
#    Boden, und die Markierungsscheiben lagen 0.01 zu tief. Das eine sah
#    man, das andere nicht.
#  * Ein Modell breiter als eine Zelle ragt ins Nachbarfeld, und dann ist
#    nicht mehr zu sehen, wo die Einheit steht.
#  * Die Groesse erzaehlt die Stufe. Laeuft die Reihenfolge auseinander,
#    ist die Aussage falsch, aber das Bild sieht normal aus.

const Field := preload("res://scripts/ui/BattleField3D.gd")
const Scene3D := preload("res://scripts/ui/Scene3D.gd")

var _fails: int = 0
var _done: Array = []
var _f = null
var _units: Array = []


func _init() -> void:
	_units = _load_units()
	_f = Field.new()
	root.add_child(_f)
	await process_frame

	await _test_every_unit_has_a_model()
	await _test_stands_on_the_ground()
	await _test_fits_the_cell()
	await _test_size_tells_the_tier()
	await _test_instance_colors_enabled()
	await _test_field_places_everything()
	await _test_screen_integration()

	var missing: Array = []
	for m in get_method_list():
		var mn: String = String(m["name"])
		if mn.begins_with("_test") and not _done.has(mn):
			missing.append(mn)
	_check(missing.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)" % str(missing))

	print("")
	if _fails == 0:
		print("Kreaturen-3D-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Kreaturen-3D-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _load_units() -> Array:
	var f := FileAccess.open("res://data/units.json", FileAccess.READ)
	return (JSON.parse_string(f.get_as_text()) as Dictionary)["units"] as Array


func _test_every_unit_has_a_model() -> void:
	print("== Jede Einheit aus units.json hat ein Modell ==")
	var missing: Array = []
	for u in _units:
		var id: String = String((u as Dictionary)["id"])
		if not _f._meshes.has(id):
			missing.append(id)
	_check(missing.is_empty(),
		"%d Einheiten, keine ohne Modell (fehlend: %s)" % [_units.size(), str(missing)])
	# Und die Gegenrichtung: ein Modell ohne Einheit ist eine Leiche im
	# glb, die niemand mehr aufraeumt.
	var ids: Dictionary = {}
	for u in _units:
		ids[String((u as Dictionary)["id"])] = true
	var orphan: Array = []
	for name in _f._meshes.keys():
		var n: String = String(name)
		if (n.begins_with("men_") or n.begins_with("elf_")
				or n.begins_with("nec_") or n.begins_with("ork_")) \
				and not ids.has(n):
			orphan.append(n)
	_check(orphan.is_empty(), "kein Modell ohne Einheit (%s)" % str(orphan))
	# Und die Hindernisse: jede Art, die BattleField3D nennen kann, muss
	# es geben. Ein fehlendes Modell faellt sonst stumm aus.
	var no_ob: Array = []
	for k in Field.OBSTACLE_MODEL.keys():
		if not _f._meshes.has(String(Field.OBSTACLE_MODEL[k])):
			no_ob.append(String(Field.OBSTACLE_MODEL[k]))
	if not _f._meshes.has("ob_wall_cracked"):
		no_ob.append("ob_wall_cracked")
	_check(no_ob.is_empty(), "jede Hindernisart hat ein Modell (%s)" % str(no_ob))
	_done.append("_test_every_unit_has_a_model")


func _test_stands_on_the_ground() -> void:
	print("== Jede Figur steht auf dem Boden ==")
	var bad: Array = []
	for u in _units:
		var id: String = String((u as Dictionary)["id"])
		if not _f._meshes.has(id):
			continue
		var a: AABB = (_f._meshes[id] as Mesh).get_aabb()
		# Das Gespenst schwebt ABSICHTLICH - es hat keine Beine, und auf
		# dem Boden stehend waere es ein Mann im Bettlaken. Genau deshalb
		# steht es hier namentlich und mit eigener Erwartung: eine stille
		# Ausnahme waere in beide Richtungen wertlos.
		var floats: bool = id == "nec_wight"
		var lo: float = 0.06 if floats else -0.02
		var hi: float = 0.14 if floats else 0.03
		if a.position.y < lo or a.position.y > hi:
			bad.append("%s (Unterkante %+.3f, erwartet %.2f..%.2f)"
				% [id, a.position.y, lo, hi])
	_check(bad.is_empty(),
		"jede Figur auf dem Boden, das Gespenst darueber (%s)" % str(bad))
	_done.append("_test_stands_on_the_ground")


# Die erlaubte Grundflaeche je Stufe kommt AUS DEM GENERATOR, nicht aus
# einer zweiten Tabelle hier. Eine Kopie waere genau die Doppelung, an der
# It. 36/37, It. 42 und It. 33 gescheitert sind: die Zahl wird woanders
# nachgebaut und driftet still auseinander. gen_city3d.py liest aus
# demselben Grund die Hofzahlen aus CityView3D.gd.
func _caps_from_generator() -> Dictionary:
	var out: Dictionary = {}
	var f := FileAccess.open("res://tools/gen_creatures.py", FileAccess.READ)
	if f == null:
		return out
	var txt: String = f.get_as_text()
	var i: int = txt.find("MAX_XY_BY_TIER")
	if i < 0:
		return out
	var j: int = txt.find("}", i)
	if j < 0:
		return out
	var body: String = txt.substr(i, j - i)
	var re := RegEx.new()
	re.compile("(\\d+)\\s*:\\s*([0-9.]+)")
	for m in re.search_all(body):
		out[int(m.get_string(1))] = float(m.get_string(2))
	return out


func _test_fits_the_cell() -> void:
	print("== Jede Figur bleibt auf ihrer Zelle ==")
	var caps: Dictionary = _caps_from_generator()
	_check(caps.size() == 7,
		"Grundflaechen-Tabelle aus gen_creatures.py gelesen (%d Stufen)"
		% caps.size())
	var over: Array = []
	for u in _units:
		var ud: Dictionary = u as Dictionary
		var id: String = String(ud["id"])
		if not _f._meshes.has(id):
			continue
		var cap: float = float(caps.get(int(ud["tier"]), 0.98)) * Scene3D.CELL
		var a: AABB = (_f._meshes[id] as Mesh).get_aabb()
		if a.size.x > cap + 0.01 or a.size.z > cap + 0.01:
			over.append("%s (%.2f x %.2f, erlaubt %.2f)"
				% [id, a.size.x, a.size.z, cap])
	_check(over.is_empty(),
		"keine Figur breiter als ihre Stufe erlaubt (%s)" % str(over))
	_done.append("_test_fits_the_cell")


# Die Groesse IST die Stufenanzeige (in 2D uebernimmt das die Punktreihe am
# Sockel). Innerhalb einer Fraktion muss sie deshalb monoton wachsen.
#
# GEMESSEN WIRD DIE RAUMDIAGONALE, nicht die Hoehe.
#
# Das stand hier schon vor It. 69 und war richtig: ein Vierbeiner ist lang
# statt hoch, ein Baum breit statt hoch - der Greif waere sonst "kleiner"
# als der Armbruster, ohne es zu sein.
#
# It. 69 hat den GENERATOR umgestellt (er normiert jetzt die Hoehe, nicht
# die Diagonale, weil in der Diagonale Breite und Tiefe mitsteckten und
# breite Wesen dadurch flach wurden). Ich habe daraufhin auch diesen Test
# auf die Hoehe umgestellt - und er war sofort rot, mit Recht: die
# Grundflaechen-Grenze drueckt breite Figuren unter ihre Stufenhoehe.
# Die Diagonale bleibt also das Mass fuer "wie gross ist das Wesen"; die
# Hoehe ist nur, woran der Generator skaliert.
func _test_size_tells_the_tier() -> void:
	print("== Groesse waechst mit der Stufe ==")
	var by_fac: Dictionary = {}
	for u in _units:
		var ud: Dictionary = u as Dictionary
		var id: String = String(ud["id"])
		if not _f._meshes.has(id):
			continue
		var fac: String = String(ud["faction"])
		if not by_fac.has(fac):
			by_fac[fac] = []
		(by_fac[fac] as Array).append({
			"tier": int(ud["tier"]), "id": id,
			"h": (_f._meshes[id] as Mesh).get_aabb().size.length(),
		})
	for fac in by_fac.keys():
		var arr: Array = by_fac[fac]
		arr.sort_custom(func(a, b): return int(a["tier"]) < int(b["tier"]))
		var bad: Array = []
		for i in range(1, arr.size()):
			if float(arr[i]["h"]) <= float(arr[i - 1]["h"]) + 0.01:
				bad.append("%s (%.2f) nicht groesser als %s (%.2f)"
					% [arr[i]["id"], arr[i]["h"], arr[i - 1]["id"], arr[i - 1]["h"]])
		_check(bad.is_empty(), "%s: Stufe 1..7 wird durchgehend groesser (%s)"
			% [String(fac), str(bad)])
	_done.append("_test_size_tells_the_tier")


func _test_instance_colors_enabled() -> void:
	print("== Materialien nehmen die Instanzfarbe an ==")
	var off: Array = []
	for name in _f._meshes.keys():
		var m: Mesh = _f._meshes[String(name)] as Mesh
		for i in range(m.get_surface_count()):
			var mat := m.surface_get_material(i) as StandardMaterial3D
			if mat == null or not mat.vertex_color_use_as_albedo:
				off.append("%s[%d]" % [String(name), i])
	_check(off.is_empty(), "alle Materialien mit Instanzfarbe (aus: %s)" % str(off))
	_done.append("_test_instance_colors_enabled")


func _test_field_places_everything() -> void:
	print("== Das Kampffeld stellt auf, was der Kontext nennt ==")
	var stacks: Array = [
		{"pos": Vector2i(1, 2), "type": "men_spearman", "side": 0, "active": true},
		{"pos": Vector2i(1, 5), "type": "men_archer", "side": 0},
		{"pos": Vector2i(6, 2), "type": "ork_goblin", "side": 1},
	]
	_f.refresh({"cols": 8, "rows": 8, "terrain": 0, "seed": 3,
		# kind 0 ist der Stein (Obstacles.KIND), als Literal wie im
		# Kampfschirm - cross-class class_name-Referenzen sind im
		# Android-Export unzuverlaessig.
		"stacks": stacks, "obstacles": [{"pos": Vector2i(4, 4), "kind": 0}],
		"move": [Vector2i(2, 2), Vector2i(3, 2)], "targets": [Vector2i(6, 2)]})
	# Boden: das Brett SIND 64 Zellen, dazu kommt seit It. 69 der Rand, der
	# den Rest des Bildes fuellt (vorher standen dort 55 Prozent schwarze
	# Flaeche). Wie viele Randkacheln es sind, haengt vom Seitenverhaeltnis
	# des Viewports ab - eine feste Zahl waere hier eine Kopie der
	# Kamerarechnung. Geprueft wird deshalb, was wirklich gelten muss.
	var gname: String = String(Field.GROUND_MODEL[0])
	var gc: int = _count(gname)
	_check(gc >= 64, "mindestens die 64 Brettzellen (%d, Modell %s)"
		% [gc, gname])
	_check(gc > 64, "das Brett hat einen Rand (%d Bodenkacheln)" % gc)
	# DER RAND LAESST DIE BRETTFLAECHE AUS. Tut er das nicht, liegen zwei
	# Kacheln aufeinander und streiten sich um die Tiefe - genau der
	# Z-Fight, dessen dunkle Linien It. 69 beseitigt hat.
	#
	# Geprueft wird ueber die ANZAHL, nicht ueber die Positionen: headless
	# liefert MultiMesh.get_instance_transform fuer JEDE Instanz den
	# Ursprung (nachgemessen), genau wie get_instance_color seit It. 58
	# schwarz liefert. Ein Positionsvergleich waere hier dauerhaft rot und
	# wuerde nichts aussagen. Der Ausschnitt kommt aus apron_rect() - der
	# Funktion, die auch die Ansicht benutzt.
	var ar: Rect2i = _f.apron_rect(8, 8)
	var ganz: int = ar.size.x * ar.size.y
	# Brett (64) + Rand (Rest) = genau einmal jede Zelle des Ausschnitts.
	# Ohne die Auslassung waeren es 64 mehr.
	_check(gc == ganz,
		"jede Zelle des Ausschnitts genau einmal belegt (%d von %d)"
		% [gc, ganz])
	for s in stacks:
		var t: String = String((s as Dictionary)["type"])
		_check(_count(t) == 1, "%s steht einmal (%d)" % [t, _count(t)])
	_check(_count("ob_stone") == 1, "ein Hindernis (%d)" % _count("ob_stone"))
	# Ringe: drei Seiten-/Aktivringe plus zwei Laufziele plus ein Angriffsziel.
	_check(_count("marker_ring") == 6, "sechs Ringe (%d)" % _count("marker_ring"))

	# Aufstellungsphase: die erlaubte Flaeche bekommt Ringe, und der
	# Stapel, den man gerade umstellt, einen eigenen. Ohne das waere die
	# Taktikphase in 3D nicht bedienbar - man saehe nicht, wohin man setzen
	# darf und welchen Stapel man in der Hand hat.
	var zone: Array = []
	for zy in range(8):
		zone.append(Vector2i(1, zy))
		zone.append(Vector2i(2, zy))
	_f.refresh({"cols": 8, "rows": 8, "terrain": 0, "seed": 3,
		"stacks": stacks, "obstacles": [], "move": [], "targets": [],
		"zone": zone, "picked": Vector2i(1, 5)})
	# 16 Zonenfelder plus drei Stapelringe.
	_check(_count("marker_ring") == 19,
		"Zonenflaeche und Stapel zusammen 19 Ringe (%d)" % _count("marker_ring"))
	# DIE FARBE DES RINGS WIRD HIER NICHT GEPRUEFT. `get_instance_color`
	# liest headless nur Schwarz zurueck (der Dummy-Renderer haelt die
	# Instanzdaten nicht vor) - ein Vergleich waere immer rot, und zwar
	# ohne Aussage. Geprueft wird stattdessen die REGEL an ihrem Ursprung:
	# `_field3d_ctx` muss in der Aufstellungsphase die erlaubte Flaeche und
	# den umgestellten Stapel melden (siehe _test_screen_integration).

	# Zweiter Durchlauf ohne Einheiten: nichts darf stehenbleiben.
	_f.refresh({"cols": 8, "rows": 8, "terrain": 0, "seed": 3,
		"stacks": [], "obstacles": [], "move": [], "targets": []})
	var left: Array = []
	for s in stacks:
		var t2: String = String((s as Dictionary)["type"])
		if _count(t2) != 0:
			left.append(t2)
	_check(left.is_empty(), "gefallene Stapel verschwinden (%s)" % str(left))
	_check(_count("marker_ring") == 0, "und ihre Ringe mit ihnen (%d)"
		% _count("marker_ring"))
	_done.append("_test_field_places_everything")


# Der Umschalter, der Kontext und der Tipp AM ECHTEN KAMPFSCHIRM. Ohne
# diesen Test wuerde die Suite nur die Ansicht fuer sich pruefen - genau
# der Fehler, den die Vorschau-Werkzeuge in It. 36/37 gemacht haben.
func _test_screen_integration() -> void:
	print("== Einbettung in den Kampfschirm ==")
	var TBS := load("res://scripts/ui/TacticalBattleScreen.gd")
	var bs = TBS.new()
	bs.fx_speed = 0.0
	root.add_child(bs)
	await process_frame
	bs.set_battle({
		"player_stacks": [{"type": "men_spearman", "count": 20},
			{"type": "men_archer", "count": 8}],
		"enemy_stacks": [{"type": "ork_goblin", "count": 25}],
		"seed": 31337, "terrain_id": 0, "allow_flee": true,
	})
	await process_frame

	_check(not bool(bs.get("_field3d_on")), "startet in der 2D-Ansicht")
	_check(bs.get("_field3d") == null,
		"die 3D-Ansicht wird erst beim Einschalten gebaut")

	bs.call("_toggle_view3d")
	await process_frame
	await process_frame
	_check(bool(bs.get("_field3d_on")), "Umschalter aktiviert die 3D-Ansicht")
	var f = bs.get("_field3d")
	_check(f != null and f.is_built(), "das Brett ist aufgebaut")

	# Der Kontext muss dieselbe Runde beschreiben, die der Schirm fuehrt:
	# jeder lebende Stapel genau einmal, an seinem Platz.
	var ctx: Dictionary = bs.call("_field3d_ctx")
	var seen: Dictionary = {}
	for st in (ctx["stacks"] as Array):
		seen[String((st as Dictionary)["type"])] = Vector2i((st as Dictionary)["pos"])
	var wrong: Array = []
	for arr in [bs.get("_p_stacks"), bs.get("_e_stacks")]:
		for st in (arr as Array):
			var sd: Dictionary = st as Dictionary
			if int(sd["count"]) <= 0:
				continue
			var t: String = String(sd["type"])
			if not seen.has(t) or seen[t] != Vector2i(sd["pos"]):
				wrong.append(t)
	_check(wrong.is_empty() and seen.size() == 3,
		"alle drei Stapel stehen im Kontext an ihrem Platz (%s, %d)"
			% [str(wrong), seen.size()])

	# Der Tipp muss dieselbe Zelle treffen, auf der die Ansicht zeichnet.
	var bad: Array = []
	for cy in range(0, 8, 2):
		for cx in range(0, 8, 2):
			var cell := Vector2i(cx, cy)
			var screen: Vector2 = f.project_cell(cell, 0.0)
			var back: Vector2i = bs.call("_cell_at", screen)
			if back != cell:
				bad.append("%s -> %s" % [str(cell), str(back)])
	_check(bad.is_empty(), "16 Zellmitten treffen sich selbst (daneben: %s)"
		% str(bad))

	# DER EFFEKT-LAYER rechnet ausschliesslich ueber _cell_center und die
	# Zellgroesse. Folgt _cell_center der aktiven Ansicht, laufen Pfeile,
	# Einschlaege und Schadenszahlen ohne eigene Rechnung ueber dem
	# raeumlichen Brett - genau das ist hier zu pruefen.
	var off3: Array = []
	for c3 in [Vector2i(0, 0), Vector2i(3, 4), Vector2i(7, 7)]:
		var via_center: Vector2 = bs.call("_cell_center", c3, Vector2.ZERO, 100.0)
		var via_cam: Vector2 = f.project_cell(c3, 0.0)
		if via_center.distance_to(via_cam) > 0.5:
			off3.append("%s: %s vs %s" % [str(c3), str(via_center), str(via_cam)])
	_check(off3.is_empty(),
		"_cell_center folgt in 3D der Kamera (%s)" % str(off3))

	bs.call("_toggle_view3d")
	await process_frame
	_check(not bool(bs.get("_field3d_on")), "Umschalter fuehrt zurueck nach 2D")
	# Und in 2D wieder die Pixelrechnung: Ursprung plus halbe Zelle.
	var c2: Vector2 = bs.call("_cell_center", Vector2i(3, 4), Vector2(10.0, 20.0),
		100.0)
	_check(c2.is_equal_approx(Vector2(10.0 + 3.5 * 100.0, 20.0 + 4.5 * 100.0)),
		"_cell_center rechnet in 2D wieder in Pixeln (%s)" % str(c2))
	bs.queue_free()
	await process_frame

	# Aufstellungsphase: die erlaubte Flaeche und der umgestellte Stapel
	# muessen im Kontext stehen, sonst ist die Taktikphase in 3D nicht
	# bedienbar.
	var bt = TBS.new()
	bt.fx_speed = 0.0
	root.add_child(bt)
	await process_frame
	bt.set_battle({
		"player_stacks": [{"type": "elf_dwarf", "count": 20},
			{"type": "elf_archer", "count": 10}],
		"enemy_stacks": [{"type": "nec_skeleton", "count": 30}],
		"seed": 31337, "terrain_id": 0, "player_tactics": 2,
	})
	await process_frame
	_check(bool(bt.get("_tactics_phase")), "die Aufstellungsphase laeuft")
	var tctx: Dictionary = bt.call("_field3d_ctx")
	var cols: Dictionary = {}
	for z in (tctx["zone"] as Array):
		cols[(z as Vector2i).x] = true
	var want_cols: int = int(bt.get("_tactics_cols")) + 1
	_check(cols.size() == want_cols and (tctx["zone"] as Array).size()
			== want_cols * int(bt.GRID_ROWS),
		"die erlaubte Flaeche umfasst %d Spalten mal %d Reihen (%d Felder in %d Spalten)"
			% [want_cols, bt.GRID_ROWS, (tctx["zone"] as Array).size(), cols.size()])
	# Einen Stapel "in die Hand nehmen" - im Spiel macht das ein Tipp auf
	# ihn; hier reicht der Zustand, den der Tipp setzt.
	bt.set("_tactics_pick", 0)
	var tctx2: Dictionary = bt.call("_field3d_ctx")
	_check(Vector2i(tctx2["picked"]) == Vector2i((bt.get("_p_stacks") as Array)[0]["pos"]),
		"der umgestellte Stapel steht im Kontext (%s)" % str(tctx2["picked"]))
	bt.queue_free()
	await process_frame
	_done.append("_test_screen_integration")


func _count(model: String) -> int:
	var mmi = _f._multi.get(model)
	return 0 if mmi == null else (mmi as MultiMeshInstance3D).multimesh.instance_count
