extends SceneTree

# Headless-Tests fuer die Spielmeldungen (It. 50):
#
#   godot --headless --path game/ --script tools/test_messages.gd
#
# Der Anlass: die Meldungen trugen Kuerzel aus der Entwicklung ("SIEG!
# -3 A  +120 G  +45 XP", "Held Sp -> Ge: 12 Sch., -2"). Wer das Spiel
# nicht gebaut hat, konnte nicht wissen, dass "A" die eigenen Verluste
# sind.
#
# Der eigentliche Grund fuer eine eigene Suite ist aber die BREITE:
# ausgeschriebene Meldungen sind laenger, und die Beschriftungen haben
# feste Groessen. Eine Meldung, die rechts hinauslaeuft, ist schlechter
# als ein Kuerzel. Gemessen wird in Geraetegroesse.

const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")

const DEVICE_W := 1080
const DEVICE_H := 1920

var _fails: int = 0
var _done: Array = []


func _init() -> void:
	await _test_no_abbreviations()
	await _test_widths()

	var missing: Array = []
	for m in get_method_list():
		var mn: String = String(m["name"])
		if mn.begins_with("_test") and not _done.has(mn):
			missing.append(mn)
	_check(missing.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)" % str(missing))

	print("")
	if _fails == 0:
		print("Meldungs-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Meldungs-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


# Die Kuerzel duerfen im SPIELERTEXT nicht wiederkommen. Geprueft wird
# ueber die Quelltexte, weil sich die Meldungen sonst nur einzeln
# erwischen lassen - und genau dann schleicht sich beim naechsten Umbau
# wieder eines ein.
func _test_no_abbreviations() -> void:
	print("== Keine Entwickler-Kuerzel im Spielertext ==")
	var bad: Array = []
	var patterns: Array = [
		["Sch\\., -", "'12 Sch., -2' statt Schaden und Verlusten"],
		["\\+%d G\\b", "'+120 G' statt Gold"],
		["-%d A\\b", "'-3 A' statt gefallener Einheiten"],
		["%d XP\\b", "'45 XP' statt Erfahrung"],
	]
	for path in ["res://scripts/ui/WorldMapScreen.gd",
			"res://scripts/ui/TacticalBattleScreen.gd",
			"res://scripts/ui/CityScreen.gd"]:
		var f := FileAccess.open(path, FileAccess.READ)
		if f == null:
			continue
		var text: String = f.get_as_text()
		f.close()
		for line in text.split("\n"):
			var l: String = String(line)
			# Kommentare duerfen die alten Kuerzel zitieren - sie
			# erklaeren ja, warum es sie nicht mehr gibt.
			if l.strip_edges().begins_with("#"):
				continue
			for pat in patterns:
				var re := RegEx.new()
				re.compile(String(pat[0]))
				if re.search(l) != null:
					bad.append("%s: %s" % [path.get_file(), String(pat[1])])
	_check(bad.is_empty(), "keine Kuerzel mehr im Code (%s)" % str(bad))

	# Und keine Entwickler-Spur im Spieler-Kanal: die 21 Schritte der
	# Kartenerzeugung standen bis It. 50 auf dem Schirm.
	var wmf := FileAccess.open("res://scripts/ui/WorldMapScreen.gd", FileAccess.READ)
	var wtext: String = wmf.get_as_text() if wmf != null else ""
	if wmf != null:
		wmf.close()
	var re2 := RegEx.new()
	re2.compile('_set_status\\("STEP')
	_check(re2.search(wtext) == null,
		"keine STEP-Meldung mehr ueber _set_status")
	_check(wtext.contains("func _trace("),
		"es gibt einen eigenen Kanal fuers Protokoll")
	_done.append("_test_no_abbreviations")


# Passen die laengsten Meldungen in ihre Beschriftung?
func _test_widths() -> void:
	print("")
	print("== Meldungen passen in ihre Zeile ==")
	var wm = (load("res://scenes/WorldMap.tscn") as PackedScene).instantiate()
	root.add_child(wm)
	await process_frame
	wm.set_anchors_preset(Control.PRESET_TOP_LEFT)
	wm.size = Vector2(DEVICE_W, DEVICE_H)
	await process_frame
	wm.call("_start", 42, 1)
	await process_frame
	await process_frame

	# Die laengsten Faelle, die im Spiel wirklich vorkommen: viele
	# Verluste, viel Gold, Stufenaufstieg, langer Fraktionsname.
	var hero = wm.get("_hero")
	hero.level = 12
	var samples: Array = [
		"Sieg! %s, %s - Stufe %d erreicht!" % [
			wm.call("_losses_text", 88), wm.call("_gain_text", 98765, 4321), 12],
		"Gegner-Held besiegt! %s, %s - Stufe %d erreicht!" % [
			wm.call("_losses_text", 88), wm.call("_gain_text", 98765, 4321), 12],
		"Stadtwache besiegt (Totenreich)! %s, %s - Stufe %d erreicht!" % [
			wm.call("_losses_text", 88), wm.call("_gain_text", 0, 4321), 12],
		"Schatz gefunden: 98765 Gold, %s" % wm.call("_losses_text", 88),
		"KAPITULIERT: -98765 G, Armee gerettet, Rueckzug in die Stadt",
	]
	var lbl: Label = wm.get("_combat_label")
	_check(lbl != null, "Kampfzeile gefunden")
	if lbl != null:
		var avail: float = lbl.get_rect().size.x
		var fnt: Font = lbl.get_theme_font("font")
		var fs: int = lbl.get_theme_font_size("font_size")
		_check(avail > 400.0, "Kampfzeile ist %d px breit" % int(avail))
		# Mit Umbruch zaehlt nicht die Breite, sondern die ZEILENZAHL: die
		# Zeile ist 100 px hoch, bei Schriftgroesse 34 sind das zwei
		# Zeilen. Was in drei Zeilen umbricht, wird unten abgeschnitten.
		_check(int(lbl.autowrap_mode) != 0, "Kampfzeile bricht um")
		var lines_fit: int = int(lbl.get_rect().size.y
			/ float(fnt.get_height(fs)))
		_check(lines_fit >= 2, "und hat Platz fuer %d Zeilen" % lines_fit)
		var too_long: Array = []
		for msg in samples:
			var w: float = fnt.get_string_size(String(msg),
				HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
			var need: int = int(ceil(w / avail))
			if need > lines_fit:
				too_long.append("%d Zeilen: %s" % [need, String(msg)])
		_check(too_long.is_empty(),
			"jede Meldung passt in %d Zeilen (%s)" % [lines_fit, str(too_long)])

	# Die Statuszeile ist der Rueckmeldungs-Kanal. Sie ist SCHMAL (die
	# Info-Tafel daneben nimmt sich, was sie braucht), deshalb bricht sie
	# um - und die echten Meldungen muessen in ihr Zeilenbudget passen.
	var st: Label = wm.get_node_or_null(^"TopBar/StatusLabel") as Label
	_check(st != null, "Statuszeile gefunden")
	if st != null:
		_check(not st.text.contains("Reach") and not st.text.contains("Tile")
				and not st.text.contains("STEP"),
			"Statuszeile ohne Entwicklerausgaben ('%s')" % st.text)
		_check(int(st.autowrap_mode) != 0, "Statuszeile bricht um")
		var sfnt: Font = st.get_theme_font("font")
		var sfs: int = st.get_theme_font_size("font_size")
		var swide: float = st.get_rect().size.x
		var slines: int = int(st.get_rect().size.y / float(sfnt.get_height(sfs)))
		_check(swide > 150.0 and slines >= 2,
			"Statuszeile: %d px breit, Platz fuer %d Zeilen" % [int(swide), slines])
		# Die laengsten Rueckmeldungen, die das Spiel wirklich gibt.
		var status_samples: Array = [
			"Anwerben nur in einer eigenen Stadt",
			"Kapituliert - Rueckzug in die Stadt",
			"Geflohen - die Armee ist verloren",
			"Armee voll - max 6 Stacks",
			"Held muss in der Stadt stehen",
			"Stadttor - der Tag ist zu Ende",
			"Tageseinnahme: %s" % wm.call("_gain_text", 98765, 4321),
			"Zu teuer: braucht %s" % Wallet.cost_text({"gold": 2500}),
		]
		var st_over: Array = []
		for m3 in status_samples:
			var w3: float = sfnt.get_string_size(String(m3),
				HORIZONTAL_ALIGNMENT_LEFT, -1, sfs).x
			var need3: int = int(ceil(w3 / swide))
			if need3 > slines:
				st_over.append("%d Zeilen: %s" % [need3, String(m3)])
		_check(st_over.is_empty(),
			"jede Rueckmeldung passt in %d Zeilen (%s)" % [slines, str(st_over)])

	wm.queue_free()
	await process_frame

	# Kampfschirm: drei Zeilen Verlauf, die laengsten Meldungen mit den
	# laengsten Kreaturennamen.
	var bs = TBS.new()
	bs.fx_speed = 0.0
	root.add_child(bs)
	await process_frame
	bs.set_anchors_preset(Control.PRESET_TOP_LEFT)
	bs.size = Vector2(DEVICE_W, DEVICE_H)
	await process_frame
	var longest: String = ""
	for uid in UnitType.all_ids():
		var nm: String = UnitType.name_of(String(uid))
		if nm.length() > longest.length():
			longest = nm
	var battle_samples: Array = [
		"Gegnerischer %s beschiesst %s: 3 Schuesse, 188 Schaden, 12 gefallen"
			% [longest, longest],
		"%s rueckt vor und greift %s an: 188 Schaden, 12 gefallen - Konter: 99 Schaden, 4 gefallen"
			% [longest, longest],
		"%s wartet und zieht spaeter in der Runde." % longest,
	]
	var albl: Label = bs.get("_action_lbl")
	_check(albl != null, "Kampf-Aktionszeile gefunden")
	if albl != null:
		var aw: float = albl.get_rect().size.x
		var afnt: Font = albl.get_theme_font("font")
		var afs: int = albl.get_theme_font_size("font_size")
		_check(int(albl.autowrap_mode) != 0, "Aktionszeile bricht um")
		var afit: int = int(albl.get_rect().size.y / float(afnt.get_height(afs)))
		_check(afit >= 3, "und hat Platz fuer %d Zeilen" % afit)
		var over: Array = []
		for msg2 in battle_samples:
			var w2: float = afnt.get_string_size(String(msg2),
				HORIZONTAL_ALIGNMENT_LEFT, -1, afs).x
			var need2: int = int(ceil(w2 / aw))
			if need2 > afit:
				over.append("%d Zeilen: %s" % [need2, String(msg2)])
		_check(over.is_empty(),
			"jede Kampfmeldung passt in %d Zeilen (%s)" % [afit, str(over)])
	bs.queue_free()
	await process_frame
	_done.append("_test_widths")
