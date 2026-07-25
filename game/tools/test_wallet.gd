extends SceneTree

# Headless-Tests fuer M3 Teil 1 (Wallet + Ressourcen):
#
#   godot --headless --path game/ --script tools/test_wallet.gd
#
# Abgedeckt: Wallet-Mathe, can_afford/pay, Hero-gold-Property-
# Kompatibilitaet, Save-Roundtrip mit Wallet, v1-Fixture-Mapping
# (gold -> wallet), Ressourcen-Minen-Einkommen im echten Spiel.

const SaveLib := preload("res://scripts/core/SaveManager.gd")

var _fails: int = 0


func _init() -> void:
	_test_wallet_math()
	_test_hero_gold_property()
	_test_save_roundtrip()
	await _test_mine_income()

	print("")
	if _fails == 0:
		print("Wallet-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Wallet-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_wallet_math() -> void:
	print("== Wallet-Mathe ==")
	var w := Wallet.new()
	_check(w.get_amount("gold") == 0, "leeres Wallet -> 0")
	w.add("gold", 500)
	w.add("wood", 10)
	_check(w.get_amount("gold") == 500 and w.get_amount("wood") == 10, "add")
	w.add("gold", -600)
	_check(w.get_amount("gold") == 0, "add unter 0 clamp't auf 0")
	w.set_amount("gold", 1000)
	_check(w.can_afford({"gold": 800, "wood": 5}), "can_afford true")
	_check(not w.can_afford({"gold": 800, "ore": 1}), "can_afford false bei fehlendem Erz")
	_check(not w.pay({"gold": 800, "ore": 1}), "pay verweigert -> nichts abgezogen")
	_check(w.get_amount("gold") == 1000, "Bestand nach verweigertem pay unveraendert")
	_check(w.pay({"gold": 800, "wood": 5}), "pay ok")
	_check(w.get_amount("gold") == 200 and w.get_amount("wood") == 5, "Bestand nach pay")
	# Roundtrip
	var w2 := Wallet.from_dict(JSON.parse_string(JSON.stringify(w.to_dict())))
	_check(w2.get_amount("gold") == 200 and w2.get_amount("wood") == 5, "Wallet JSON-Roundtrip")
	_check(Wallet.display_name("gems") == "Edelsteine", "display_name deutsch")
	_check(Wallet.short_name("wood") == "H", "short_name Kuerzel")


func _test_hero_gold_property() -> void:
	print("== Hero.gold-Property ==")
	var h := Hero.new(Vector2i.ZERO)
	h.gold = 777
	_check(h.wallet.get_amount("gold") == 777, "gold-Setter schreibt ins Wallet")
	h.wallet.add("gold", 23)
	_check(h.gold == 800, "gold-Getter liest aus dem Wallet")
	h.gold -= 300
	_check(h.gold == 500, "compound assignment (-=) laeuft")


func _test_save_roundtrip() -> void:
	print("== Save-Kompatibilitaet ==")
	var h := Hero.new(Vector2i(2, 3))
	h.gold = 400
	h.wallet.add("crystal", 3)
	var d2: Dictionary = JSON.parse_string(JSON.stringify(h.to_dict()))
	var h2 := Hero.from_dict(d2)
	_check(h2.gold == 400 and h2.wallet.get_amount("crystal") == 3,
		"Hero-Roundtrip mit Wallet")
	# v1-Format (nur "gold", kein "wallet") muss weiter laden.
	var v1 := {"position": [1, 1], "gold": 250, "army": {}, "xp": 0, "level": 1}
	var h3 := Hero.from_dict(v1)
	_check(h3.gold == 250, "v1-Save (gold-Feld) mappt ins Wallet")
	# Eingechecktes v1-Fixture: Hero-Teil laden.
	var ff := FileAccess.open("res://tools/fixtures/save_v1.json", FileAccess.READ)
	_check(ff != null, "Fixture vorhanden")
	if ff != null:
		var fx: Dictionary = JSON.parse_string(ff.get_as_text())
		var fh := Hero.from_dict(fx["hero"])
		_check(fh.gold >= 0, "Fixture-Hero laedt (gold=%d)" % fh.gold)


func _test_mine_income() -> void:
	print("== Ressourcen-Minen im Spiel ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm := scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 777, 1)
	# Es muessen Minen mit Nicht-Gold-Ressourcen existieren.
	var kinds: Dictionary = {}
	var pile_count: int = 0
	var obj_mine: int = wm.get("OBJECT_MINE")
	var obj_pile: int = wm.get("OBJECT_PILE")
	for o in (wm.get("_objects") as Array):
		if int(o["kind"]) == obj_mine:
			kinds[String(o.get("resource", "gold"))] = true
		elif int(o["kind"]) == obj_pile:
			pile_count += 1
	_check(kinds.has("wood") and kinds.has("ore"), "Holz- und Erz-Mine platziert (%s)" % str(kinds.keys()))
	_check(pile_count > 0, "Ressourcen-Haufen platziert (%d)" % pile_count)
	# Holz-Mine dem Spieler geben, 1 Tag -> Holz waechst.
	var hero: Hero = wm.get("_hero")
	var owner_hero: int = wm.get("OWNER_HERO")
	for o in (wm.get("_objects") as Array):
		if int(o["kind"]) == obj_mine and String(o.get("resource", "")) == "wood":
			o["owner"] = owner_hero
			break
	var wood_before: int = hero.wallet.get_amount("wood")
	wm.call("_on_end_turn")
	await process_frame
	var wood_after: int = hero.wallet.get_amount("wood")
	_check(wood_after == wood_before + 2, "Holz-Mine liefert +2/Tag (%d -> %d)" % [wood_before, wood_after])
	# Save-Roundtrip mit resource-Feld
	var s1: Dictionary = wm.call("_capture_state")
	var s1j: Dictionary = JSON.parse_string(JSON.stringify(s1))
	_check(wm.call("_restore_state", s1j), "Restore mit resource-Feldern")
	var s2: Dictionary = wm.call("_capture_state")
	_check(JSON.stringify(s1) == JSON.stringify(s2), "capture->restore->capture stabil")
	wm.queue_free()
	await process_frame
