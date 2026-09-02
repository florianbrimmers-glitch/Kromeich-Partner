extends SceneTree

# Headless-Tests fuer die Artefakte (It. 51, kleine Fassung):
#
#   godot --headless --path game/ --script tools/test_artifacts.gd
#
# Abgedeckt:
#   1. Daten: jede ID einmal, nur erlaubte Werte, sinnvolle Seltenheiten
#   2. Der Bonus liegt OBEN AUF dem Rohwert - ein Stufenaufstieg hebt den
#      Rohwert, das Ablegen nimmt den Bonus wieder mit
#   3. Speichern/Laden blaeht die Werte nicht auf (der haeufigste Fehler
#      bei abgeleiteten Werten)
#   4. Kein Primaerwert wird negativ (die Klinge des Zorns hat ein Minus)
#   5. Truhen: jede vierte haelt ein Artefakt, stabil ueber Aufrufe
#   6. Aufnehmen, volle Ausruestung, Tauschen, Ablegen

const Art := preload("res://scripts/core/Artifacts.gd")
const SaveLib := preload("res://scripts/core/SaveManager.gd")
const Move := preload("res://scripts/core/Movement.gd")

var _fails: int = 0
var _done: Array = []


func _init() -> void:
	_test_data()
	_test_bonus_on_top()
	_test_save_roundtrip()
	_test_never_negative()
	await _test_chests()
	await _test_take_and_swap()
	await _test_pickup_by_tap()
	await _test_review_findings()

	var missing: Array = []
	for m in get_method_list():
		var mn: String = String(m["name"])
		if mn.begins_with("_test") and not _done.has(mn):
			missing.append(mn)
	_check(missing.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)" % str(missing))

	print("")
	if _fails == 0:
		print("Artefakt-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Artefakt-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_data() -> void:
	print("== Daten ==")
	var defs: Array = Art.all_defs()
	_check(defs.size() >= 5, "%d Artefakte" % defs.size())
	var seen: Dictionary = {}
	var bad_stat: Array = []
	var no_effect: Array = []
	var bad_rarity: Array = []
	for d in defs:
		var dd: Dictionary = d as Dictionary
		var id: String = String(dd.get("id", ""))
		_check(id != "" and not seen.has(id), "ID '%s' ist da und einmalig" % id)
		seen[id] = true
		var b: Dictionary = dd.get("bonus", {}) as Dictionary
		if b.is_empty():
			no_effect.append(id)
		for k in b.keys():
			if not Art.STAT_IDS.has(String(k)):
				bad_stat.append("%s: %s" % [id, String(k)])
		if int(dd.get("rarity", 0)) <= 0:
			bad_rarity.append(id)
		_check(String(dd.get("name", "")) != "", "  %s hat einen Namen" % id)
	# Ein Tippfehler im Wert-Schluessel wuerde sonst still nichts tun.
	_check(bad_stat.is_empty(), "nur erlaubte Werte (%s)" % str(bad_stat))
	_check(no_effect.is_empty(), "kein Artefakt ohne Wirkung (%s)" % str(no_effect))
	_check(bad_rarity.is_empty(), "jedes hat eine Seltenheit (%s)" % str(bad_rarity))
	_check(Art.summary("klinge_des_zorns").contains("-1"),
		"ein Minus steht auch als Minus da ('%s')" % Art.summary("klinge_des_zorns"))
	_check(not Art.exists("gibt_es_nicht"), "unbekannte ID wird erkannt")
	_check(Art.bonus(["gibt_es_nicht"], "att") == 0,
		"und zaehlt null statt zu stuerzen")
	_done.append("_test_data")


func _test_bonus_on_top() -> void:
	print("")
	print("== Der Bonus liegt oben auf ==")
	var h := Hero.new(Vector2i.ZERO, 40)
	h.add_primary("attack", 3)
	_check(h.att == 3 and h.att_base == 3, "ohne Artefakt sind Wert und Rohwert gleich")
	h.artifacts.append("schwert_der_wacht")
	_check(h.att == 5, "mit Schwert der Wacht +2 (ist %d)" % h.att)
	_check(h.att_base == 3, "der Rohwert bleibt 3 (ist %d)" % h.att_base)
	# DER Fehler, den diese Bauart verhindern soll: ein Stufenaufstieg darf
	# den Artefakt-Bonus nicht in den Rohwert einbetonieren.
	h.add_primary("attack", 1)
	_check(h.att_base == 4, "Stufenaufstieg hebt den Rohwert auf 4 (ist %d)" % h.att_base)
	_check(h.att == 6, "und der Wert auf 6 (ist %d)" % h.att)
	h.artifacts.clear()
	_check(h.att == 4, "abgelegt bleibt der Rohwert 4 (ist %d)" % h.att)
	# Wissen wirkt ueber das Mana-Maximum weiter.
	h.knowledge = 2
	var before: int = HeroSpellsLib.max_mana(h.knowledge)
	h.artifacts.append("helm_der_klarheit")
	_check(HeroSpellsLib.max_mana(h.knowledge) > before,
		"Wissen aus einem Artefakt hebt das Mana-Maximum (%d -> %d)"
		% [before, HeroSpellsLib.max_mana(h.knowledge)])
	_done.append("_test_bonus_on_top")


const HeroSpellsLib := preload("res://scripts/core/HeroSpells.gd")


func _test_save_roundtrip() -> void:
	print("")
	print("== Speichern und Laden blaeht nichts auf ==")
	var h := Hero.new(Vector2i(3, 4), 40)
	h.add_primary("attack", 5)
	h.add_primary("defense", 2)
	h.artifacts.append("schwert_der_wacht")
	h.artifacts.append("panzer_des_riesen")
	var att_before: int = h.att
	var def_before: int = h.def
	var d: Dictionary = h.to_dict()
	_check(int(d["att"]) == 5, "gespeichert wird der ROHWERT (%d)" % int(d["att"]))
	_check((d["artifacts"] as Array).size() == 2, "und die Artefakt-Liste")
	# Zweimal durch: ein Fehler hier waechst mit jedem Speichern.
	var h2 := Hero.from_dict(d)
	var h3 := Hero.from_dict(h2.to_dict())
	_check(h3.att == att_before and h3.def == def_before,
		"nach zweimal Speichern/Laden dieselben Werte (%d/%d statt %d/%d)"
		% [h3.att, h3.def, att_before, def_before])
	_check(h3.att_base == 5, "und derselbe Rohwert (%d)" % h3.att_base)
	# Ein ausgemustertes Artefakt darf einen Spielstand nicht sprengen.
	var d2: Dictionary = h.to_dict()
	(d2["artifacts"] as Array).append("gibt_es_nicht_mehr")
	var h4 := Hero.from_dict(d2)
	_check(h4.artifacts.size() == 2,
		"unbekanntes Artefakt faellt beim Laden raus (%d getragen)" % h4.artifacts.size())
	_done.append("_test_save_roundtrip")


func _test_never_negative() -> void:
	print("")
	print("== Kein Wert wird negativ ==")
	var h := Hero.new(Vector2i.ZERO, 40)
	h.artifacts.append("klinge_des_zorns")   # +3 Angriff, -1 Verteidigung
	_check(h.att == 3, "das Plus wirkt (%d)" % h.att)
	_check(h.def == 0, "das Minus druecke nicht unter null (%d)" % h.def)
	h.add_primary("defense", 3)
	_check(h.def == 2, "mit Rohwert 3 bleibt 2 uebrig (%d)" % h.def)
	h.artifacts.clear()
	_check(h.def == 3, "und abgelegt sind es wieder 3 (%d)" % h.def)
	_done.append("_test_never_negative")


func _test_chests() -> void:
	print("")
	print("== Truhen ==")
	var wm = (load("res://scenes/WorldMap.tscn") as PackedScene).instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 4711, 1)
	await process_frame

	var kind: int = int(wm.get("OBJECT_TREASURE"))
	var arts: int = 0
	var total: int = 0
	var unstable: Array = []
	for sd in [1, 42, 777, 4711]:
		wm.call("_start", sd, 1)
		for x in range(16):
			for y in range(16):
				total += 1
				var o: Dictionary = {"kind": kind, "pos": Vector2i(x, y)}
				var a: String = String(wm.call("_chest_artifact", o))
				if a != "":
					arts += 1
					# Stabil ueber Aufrufe: sonst wechselt eine Truhe beim
					# Neuzeichnen ihren Inhalt (die Lehre aus It. 35).
					if String(wm.call("_chest_artifact", o)) != a:
						unstable.append(str(Vector2i(x, y)))
					if not Art.exists(a):
						unstable.append("unbekannt: " + a)
	var pct: float = 100.0 * float(arts) / float(maxi(1, total))
	var soll: float = 100.0 / float(wm.get("ARTIFACT_CHEST_EVERY"))
	_check(absf(pct - soll) < 6.0,
		"%.1f %% der Truhen halten ein Artefakt (Soll %.0f %%)" % [pct, soll])
	_check(unstable.is_empty(), "und der Inhalt ist stabil (%s)" % str(unstable))
	# Nur Truhen, keine anderen Objekte.
	_check(String(wm.call("_chest_artifact",
		{"kind": int(wm.get("OBJECT_PILE")), "pos": Vector2i(2, 2)})) == "",
		"ein Ressourcen-Haufen haelt keine Artefakte")
	wm.queue_free()
	await process_frame
	_done.append("_test_chests")


func _test_take_and_swap() -> void:
	print("")
	print("== Aufnehmen, tauschen, ablegen ==")
	var wm = (load("res://scenes/WorldMap.tscn") as PackedScene).instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 4711, 1)
	await process_frame
	var h = wm.get("_hero")
	h.artifacts.clear()

	for id in ["schwert_der_wacht", "panzer_des_riesen", "klinge_des_zorns"]:
		wm.call("_take_artifact", h, id)
	_check(h.artifacts.size() == Art.MAX_SLOTS,
		"drei Plaetze sind belegt (%d)" % h.artifacts.size())
	# Dasselbe Stueck zweimal bringt nichts und darf keinen Platz kosten.
	var msg: String = String(wm.call("_take_artifact", h, "schwert_der_wacht"))
	_check(h.artifacts.size() == Art.MAX_SLOTS and msg.contains("schon"),
		"dasselbe Artefakt zweimal wird abgewiesen ('%s')" % msg)

	# Voll: das Tausch-Panel geht auf, statt den Fund wortlos zu schlucken.
	# Geprueft wird WISSEN - der Helm gibt nur Wissen. Die Review fand hier
	# einen Vergleich auf att, den ein vorzeitiges Anhaengen nie geaendert
	# haette.
	var know_full: int = h.knowledge
	wm.call("_take_artifact", h, "helm_der_klarheit")
	var panel: Panel = wm.get("_art_panel")
	_check(panel != null and panel.visible, "bei voller Ausruestung oeffnet der Tausch")
	_check(h.artifacts.size() == Art.MAX_SLOTS and h.knowledge == know_full,
		"und bis zur Entscheidung aendert sich nichts (Wissen %d)" % h.knowledge)

	wm.call("_swap_artifact", "panzer_des_riesen")
	_check(not h.artifacts.has("panzer_des_riesen")
			and h.artifacts.has("helm_der_klarheit"),
		"getauscht: %s" % str(h.artifacts))
	_check(h.artifacts.size() == Art.MAX_SLOTS,
		"immer noch drei (%d)" % h.artifacts.size())
	_check(not panel.visible, "und das Panel ist zu")

	# Ablegen ueber das Heldenblatt.
	var before: int = h.att
	wm.call("_drop_artifact", "schwert_der_wacht")
	_check(h.artifacts.size() == Art.MAX_SLOTS - 1,
		"abgelegt (%d getragen)" % h.artifacts.size())
	_check(h.att == before - 2, "und der Bonus ist weg (%d statt %d)" % [h.att, before])

	# Mana darf nach dem Ablegen nicht ueber dem neuen Deckel liegen.
	h.artifacts.clear()
	wm.call("_take_artifact", h, "helm_der_klarheit")
	h.mana = int(wm.call("_hero_max_mana"))
	wm.call("_drop_artifact", "helm_der_klarheit")
	_check(int(h.mana) <= int(wm.call("_hero_max_mana")),
		"Mana bleibt unter dem Deckel (%d von %d)"
		% [int(h.mana), int(wm.call("_hero_max_mana"))])

	# GEOMETRIE in Geraetegroesse: das Tausch-Panel und die neue Zeile im
	# Heldenblatt. Das Blatt hat eine FESTE Hoehe und war in It. 43 schon
	# randvoll (1180 von 1180 px) - eine weitere Zeile ist genau der Fall,
	# vor dem die Messung dort warnen sollte.
	wm.set_anchors_preset(Control.PRESET_TOP_LEFT)
	wm.size = Vector2(1080, 1920)
	await process_frame
	h.artifacts.clear()
	for id2 in ["schwert_der_wacht", "panzer_des_riesen", "klinge_des_zorns"]:
		wm.call("_take_artifact", h, id2)
	wm.call("_show_artifact_swap", "krone_der_weisen", h, Vector2i(-1, -1))
	await process_frame
	var screen := Rect2(Vector2.ZERO, Vector2(1080, 1920))
	var ap: Panel = wm.get("_art_panel")
	_check(ap != null and screen.encloses(ap.get_rect()),
		"Tausch-Panel liegt ganz auf dem Schirm %s" % str(ap.get_rect()))
	ap.visible = false

	h.skills = {"wisdom": 3}
	h.knowledge = 10
	h.army = {"men_spearman": 9, "men_archer": 5, "men_griffin": 3,
		"men_crusader": 2, "men_monk": 4, "men_angel": 1}
	wm.set("_player_faction", 0)
	wm.call("_open_hero_panel")
	await process_frame
	var hp: Panel = wm.get("_hero_panel")
	_check(hp != null and screen.encloses(hp.get_rect()),
		"Heldenblatt liegt ganz auf dem Schirm %s" % str(hp.get_rect()))
	var vb2: VBoxContainer = null
	for c2 in hp.get_children():
		if c2 is VBoxContainer:
			vb2 = c2 as VBoxContainer
	if vb2 != null:
		var used: float = 0.0
		var closer: Control = null
		for c3 in vb2.get_children():
			var cc: Control = c3 as Control
			used += cc.get_rect().size.y
			if cc is Button and String((cc as Button).text) == "Schliessen":
				closer = cc
		used += float(vb2.get_child_count() - 1) * 16.0
		_check(used <= vb2.get_rect().size.y + 1.0,
			"Inhalt passt mit der Ausruestungs-Zeile ins Blatt (%d von %d px)"
			% [int(used), int(vb2.get_rect().size.y)])
		_check(closer != null and screen.encloses(closer.get_global_rect()),
			"und der Schliessen-Knopf bleibt erreichbar")

	wm.queue_free()
	await process_frame
	_done.append("_test_take_and_swap")
# END ZU ENDE: auf eine Artefakt-Truhe tippen und sie tragen.
#
# Der Durchspiel-Test faengt das NICHT: sein Test-Spieler nimmt nur
# Kaempfe an, die die Karte gruen faerbt, und Truhen sind bewacht - in
# zwei Seeds hat er keine einzige geholt. Ohne diese Pruefung waere der
# ganze Abholweg (Tap -> _handle_tap -> Objekt -> _take_artifact) nie
# durchlaufen, obwohl die Truhen auf der Karte liegen.
func _test_pickup_by_tap() -> void:
	print("")
	print("== Truhe antippen und Artefakt tragen ==")
	var wm = (load("res://scenes/WorldMap.tscn") as PackedScene).instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 4711, 1)
	await process_frame

	# Eine Truhe mit Artefakt suchen und neben den Helden legen.
	var kind: int = int(wm.get("OBJECT_TREASURE"))
	var chest: Dictionary = {}
	for o in (wm.get("_objects") as Array):
		if int(o["kind"]) == kind and String(wm.call("_chest_artifact", o)) != "":
			chest = o
			break
	_check(not chest.is_empty(), "Artefakt-Truhe auf der Karte gefunden")
	if chest.is_empty():
		wm.queue_free()
		await process_frame
		_done.append("_test_pickup_by_tap")
		return
	var expected: String = String(wm.call("_chest_artifact", chest))
	# Wache weg: der Kampf ist hier nicht der Prueffall, der Abholweg ist es.
	chest["guard"] = 0
	var h = wm.get("_hero")
	h.artifacts.clear()
	# Ein BEGEHBARES Nachbarfeld im Kartenbereich - nicht blind links
	# daneben. Laege die Truhe auf Spalte 0, stuende der Held bei x = -1,
	# _recompute_costs griffe ausserhalb des Feldes zu, und die Suite
	# hinge bis zum CI-Timeout statt rot zu werden (Review-Befund).
	h.position = _walkable_neighbour(wm, Vector2i(chest["pos"]))
	_check(h.position.x >= 0, "begehbares Nachbarfeld gefunden %s" % str(h.position))
	h.mp = h.max_mp
	wm.call("_recompute_costs")
	var gold_before: int = (wm.get("_purse") as Wallet).get_amount("gold")

	# Tap wie ein Spieler.
	var origin: Vector2 = wm.call("_map_origin")
	var ts: float = float(wm.get("_tile_size"))
	var cell: Vector2i = Vector2i(chest["pos"])
	wm.call("_handle_tap", origin + Vector2(float(cell.x) + 0.5,
		float(cell.y) + 0.5) * ts)
	await process_frame

	_check(h.artifacts.has(expected),
		"nach dem Tap getragen: %s (erwartet %s)" % [str(h.artifacts), expected])
	_check((wm.get("_purse") as Wallet).get_amount("gold") == gold_before,
		"und KEIN Gold dazu - die Truhe gibt das eine ODER das andere")
	var still: bool = false
	for o2 in (wm.get("_objects") as Array):
		if Vector2i(o2["pos"]) == cell and int(o2["kind"]) == kind:
			still = true
	_check(not still, "die Truhe ist von der Karte verschwunden")

	wm.queue_free()
	await process_frame
	_done.append("_test_pickup_by_tap")


# Die Befunde der Code-Review zu It. 51, jeder als Pruefung (It. 52).
func _test_review_findings() -> void:
	print("")
	print("== Befunde der Code-Review ==")
	var wm = (load("res://scenes/WorldMap.tscn") as PackedScene).instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 4711, 1)
	await process_frame
	var kind: int = int(wm.get("OBJECT_TREASURE"))
	var h = wm.get("_hero")
	var purse: Wallet = wm.get("_purse")

	# 1) Truhe mit schon getragenem Artefakt gibt GOLD, nicht nichts.
	var chest: Dictionary = {}
	for o in (wm.get("_objects") as Array):
		if int(o["kind"]) == kind and String(wm.call("_chest_artifact", o)) != "":
			chest = o
			break
	_check(not chest.is_empty(), "Artefakt-Truhe gefunden")
	var art: String = String(wm.call("_chest_artifact", chest))
	h.artifacts.clear()
	h.equip(art)
	var gold0: int = purse.get_amount("gold")
	var idx: int = (wm.get("_objects") as Array).find(chest)
	var msg: String = String(wm.call("_open_chest", chest, idx, h))
	_check(purse.get_amount("gold") == gold0 + int(chest["gold"]),
		"schon getragen -> Gold statt nichts ('%s')" % msg)
	_check((wm.get("_objects") as Array).find(chest) < 0, "und die Truhe ist weg")

	# 2) Volle Ausruestung: die Truhe BLEIBT liegen, bis entschieden ist.
	wm.call("_start", 4711, 1)
	h = wm.get("_hero")
	purse = wm.get("_purse")
	chest = {}
	for o2 in (wm.get("_objects") as Array):
		if int(o2["kind"]) == kind and String(wm.call("_chest_artifact", o2)) != "":
			chest = o2
			break
	art = String(wm.call("_chest_artifact", chest))
	h.artifacts.clear()
	for id in ["schwert_der_wacht", "panzer_des_riesen", "klinge_des_zorns"]:
		if id != art:
			h.equip(id)
	while h.artifacts.size() < Art.MAX_SLOTS:
		h.equip("krone_der_weisen" if art != "krone_der_weisen" else "stab_der_kraft")
	idx = (wm.get("_objects") as Array).find(chest)
	gold0 = purse.get_amount("gold")
	wm.call("_open_chest", chest, idx, h)
	var panel: Panel = wm.get("_art_panel")
	_check(panel != null and panel.visible, "voll: Tausch-Panel offen")
	_check((wm.get("_objects") as Array).find(chest) >= 0,
		"voll: die Truhe liegt noch auf der Karte")
	_check(purse.get_amount("gold") == gold0, "voll: kein Gold gebucht")
	# Waehrend die Entscheidung offen ist, erreicht KEIN Tap die Karte.
	var pos_before: Vector2i = h.position
	var origin: Vector2 = wm.call("_map_origin")
	var ts: float = float(wm.get("_tile_size"))
	wm.call("_handle_tap", origin + Vector2(float(pos_before.x) + 1.5,
		float(pos_before.y) + 0.5) * ts)
	_check(h.position == pos_before, "offenes Panel sperrt die Karte")
	_check(bool(wm.call("_modal_open")), "_modal_open sagt es auch")
	# Ablehnen: Truhe bleibt, Fund bleibt.
	wm.call("_decline_artifact")
	_check(not panel.visible, "abgelehnt: Panel zu")
	_check((wm.get("_objects") as Array).find(chest) >= 0,
		"abgelehnt: die Truhe liegt weiter da")
	_check(String(wm.get("_art_found")) == "", "abgelehnt: keine offene Entscheidung")

	# 3) Tausch prueft neu: wechselt der Held zwischendurch, trifft es
	#    trotzdem den GEBUNDENEN Helden - und nie ueber MAX_SLOTS.
	idx = (wm.get("_objects") as Array).find(chest)
	wm.call("_open_chest", chest, idx, h)
	var other: Hero = Hero.new(h.position + Vector2i(1, 0), int(wm.get("BASE_MAX_MP")))
	(wm.get("_heroes") as Array).append(other)
	wm.set("_active_hero", 1)
	var drop: String = String(h.artifacts[0])
	wm.call("_swap_artifact", drop)
	_check(h.artifacts.has(art) and not h.artifacts.has(drop),
		"Tausch trifft den gebundenen Helden (%s)" % str(h.artifacts))
	_check(other.artifacts.is_empty(), "und nicht den zwischendurch aktiven")
	_check(h.artifacts.size() == Art.MAX_SLOTS, "nie mehr als %d" % Art.MAX_SLOTS)
	_check((wm.get("_objects") as Array).find(chest) < 0,
		"nach dem Tausch ist die Truhe weg")
	wm.set("_active_hero", 0)

	# 4) Ein kaputter Tausch (abzulegendes Stueck ist weg) faellt sauber.
	h.artifacts.clear()
	for id2 in ["schwert_der_wacht", "panzer_des_riesen", "klinge_des_zorns"]:
		h.equip(id2)
	wm.call("_take_artifact", h, "helm_der_klarheit")
	h.unequip("schwert_der_wacht")   # jemand hat es zwischendurch abgelegt
	wm.call("_swap_artifact", "schwert_der_wacht")
	_check(not h.artifacts.has("helm_der_klarheit") and h.artifacts.size() == 2,
		"abzulegendes Stueck fehlt -> kein Tausch, nichts angehaengt (%s)" % str(h.artifacts))

	# 5) _start raeumt das Panel auf.
	wm.call("_take_artifact", h, "helm_der_klarheit")
	wm.call("_take_artifact", h, "krone_der_weisen")   # jetzt voll -> Panel
	_check(bool(wm.get("_art_panel").visible), "Panel offen vor dem Neustart")
	wm.call("_start", 90210, 1)
	_check(not bool(wm.get("_art_panel").visible), "_start schliesst das Panel")
	_check(String(wm.get("_art_found")) == "", "und vergisst den Fund")

	# 6) from_dict kappt bei MAX_SLOTS.
	var hd: Dictionary = Hero.new(Vector2i.ZERO, 40).to_dict()
	hd["artifacts"] = ["schwert_der_wacht", "panzer_des_riesen", "klinge_des_zorns",
		"helm_der_klarheit", "krone_der_weisen"]
	var loaded := Hero.from_dict(hd)
	_check(loaded.artifacts.size() == Art.MAX_SLOTS,
		"uebervoller Stand laedt mit %d statt 5" % loaded.artifacts.size())

	# 7) Rohwert nie negativ, auch nicht ueber den Setter.
	var neg := Hero.new(Vector2i.ZERO, 40)
	neg.att = -3
	_check(neg.att_base == 0 and neg.att == 0, "negativer Rohwert wird geklemmt")
	neg.equip("schwert_der_wacht")
	_check(neg.att == 2, "und ein Artefakt wirkt darauf sichtbar (%d)" % neg.att)

	wm.queue_free()
	await process_frame
	_done.append("_test_review_findings")


# Ein begehbares Nachbarfeld innerhalb der Karte, oder (-1,-1).
func _walkable_neighbour(wm, cell: Vector2i) -> Vector2i:
	var w: int = int(wm.get("MAP_WIDTH"))
	var hgt: int = int(wm.get("MAP_HEIGHT"))
	var tiles: Array = (wm.get("_map") as Dictionary)["tiles"]
	for d in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
		var c: Vector2i = cell + d
		if c.x < 0 or c.y < 0 or c.x >= w or c.y >= hgt:
			continue
		if Move.is_passable(int(tiles[c.y * w + c.x])):
			return c
	return Vector2i(-1, -1)
