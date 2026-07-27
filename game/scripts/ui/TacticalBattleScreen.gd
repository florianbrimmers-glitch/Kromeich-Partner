extends Control

signal battle_finished(result: Dictionary)

# Obstacle-Modul per preload statt ueber class_name. Im Android-Export
# koennen Cross-File-class_name-Aufrufe stillschweigend fehlschlagen
# (siehe Pathfinder.gd): static Methoden liefern dann 0/false statt der
# realen Werte. Preload umgeht das, weil es direkt die Script-Datei
# referenziert, nicht den globalen Klassen-Cache.
const Obstacles := preload("res://scripts/core/BattleObstacles.gd")
# Kampf-Faehigkeiten (M6b) - gleiche preload-Begruendung wie oben.
const Abil := preload("res://scripts/core/Abilities.gd")
# Status-Effekte mit Dauer (M6b Teil 2).
const Fx := preload("res://scripts/core/StatusFx.gd")
# Moral + Glueck (M6).
const Mor := preload("res://scripts/core/Morale.gd")

const GRID_COLS := 10
const GRID_ROWS := 8

var _player_name: String = "Held"
var _enemy_name: String = "Gegner"
var _player_bonus: int = 0
var _allow_flee: bool = true
var _rng: RandomNumberGenerator
var _finished: bool = false
var _round: int = 1
# Moral/Glueck gelten je Seite fuer die ganze Schlacht (HoMM3-Verhalten:
# kein Neuberechnen, wenn Stacks fallen). Moral kommt aus der Armee-
# Zusammenstellung, Glueck von aussen (Kapellen, siehe WorldMapScreen).
var _p_morale: int = 0
var _e_morale: int = 0
var _p_luck: int = 0
var _e_luck: int = 0
# Ergebnis des letzten Glueckswurfs fuer das Kampf-Log.
var _last_luck: float = 1.0
# Belagerung (M9). _siege = Mauer steht auf dem Feld; _wall_hp haelt die
# Restpunkte je Segment-Position. Verteidiger ist immer Seite 1 (die
# Stadt), Angreifer der Spieler - KI-Angriffe auf eigene Staedte laufen
# weiter ueber die Auto-Abrechnung im WorldMapScreen.
const SIEGE_DEF_BONUS := 2
var _siege: bool = false
var _wall_hp: Dictionary = {}
var _tower_dmg: int = 0

var _p_stacks: Array = []
var _e_stacks: Array = []
var _turn_order: Array = []
var _active_slot: int = 0
var _reachable: Dictionary = {}
var _obstacles: Array = []
# Schneller Lookup Vector2i -> kind, vermeidet Lineardurchlauf in
# der Pfadsuche. Wird in set_battle aus _obstacles gefuellt.
var _ob_map: Dictionary = {}
var _terrain_id: int = 0

var _grid_area: Control
var _info_lbl: Label
var _action_lbl: Label
var _wait_btn: Button
var _flee_btn: Button

# Kampf-Log: die letzten LOG_LINES Aktionen, damit Spieler sehen kann,
# was in den Zuegen davor passiert ist (Schaden, Verluste, Bewegungen).
const LOG_LINES := 5
var _log: Array = []


func set_battle(ctx: Dictionary) -> void:
	_player_name = String(ctx.get("player_name", "Held"))
	_enemy_name  = String(ctx.get("enemy_name",  "Gegner"))
	_player_bonus = int(ctx.get("player_bonus", 0))
	_allow_flee  = bool(ctx.get("allow_flee", true))
	_rng = RandomNumberGenerator.new()
	_rng.seed = int(ctx.get("seed", 42))
	_finished = false
	_round = 1
	_log.clear()
	_terrain_id = int(ctx.get("terrain_id", 0))
	_obstacles = Obstacles.generate(_terrain_id, int(ctx.get("seed", 42)), GRID_COLS, GRID_ROWS)
	# Belagerung: Mauer-Reihe dazu. Gelaende-Obstacles der Mauer-Spalte
	# fallen weg, damit die Reihe nicht doppelt belegt ist.
	_siege = bool(ctx.get("siege", false))
	_tower_dmg = int(ctx.get("tower_dmg", 0))
	_wall_hp.clear()
	if _siege:
		var wcol: int = Obstacles.wall_col(GRID_COLS)
		var kept: Array = []
		for o in _obstacles:
			if int(Vector2i(o["pos"]).x) != wcol:
				kept.append(o)
		_obstacles = kept
		for w in Obstacles.siege_walls(GRID_COLS, GRID_ROWS):
			_obstacles.append(w)
			_wall_hp[Vector2i(w["pos"])] = int(w["hp"])
	_ob_map.clear()
	for o in _obstacles:
		_ob_map[Vector2i(o["pos"])] = int(o["kind"])
	_p_stacks = _make_stacks(ctx.get("player_stacks", []), 0)
	_e_stacks = _make_stacks(ctx.get("enemy_stacks", []), 1)
	_p_morale = Mor.morale_for(_p_stacks)
	_e_morale = Mor.morale_for(_e_stacks)
	_p_luck = int(ctx.get("player_luck", 0))
	_e_luck = int(ctx.get("enemy_luck", 0))
	_last_luck = 1.0
	_log_unhandled_abilities()
	_place_stacks()
	_rebuild_order()
	_active_slot = 0
	if _flee_btn != null:
		_flee_btn.visible = _allow_flee
	_refresh()
	_step()


func _make_stacks(list: Array, side: int) -> Array:
	var out: Array = []
	for entry in list:
		var d: Dictionary = entry
		var uid: String = String(d.get("type", "men_spearman"))
		var cnt: int = int(d.get("count", 0))
		if cnt <= 0:
			continue
		out.append({
			"type": uid, "count": cnt, "count_start": cnt,
			"top_hp": UnitType.hp_of(uid),
			"side": side, "pos": Vector2i(0, 0),
			"retaliated": false, "waited": false,
			"shots_left": UnitType.shots_of(uid),
			# M6b: Konter-Zaehler (unlimited_retaliations), gelaufene
			# Felder dieses Zuges (Jousting) und Status-Effekte mit Dauer.
			"retaliations": 0, "tiles_moved": 0, "status": {},
			# M6: max ein Extrazug aus Moral pro Runde und Stack.
			"morale_extra_used": false,
		})
	return out


# Nur wer Munition hat, darf schiessen (M4 Teil 3). Leergeschossene
# Schuetzen kaempfen im Nahkampf weiter - mit ability-abhaengigem Malus
# (CombatMath).
func _can_shoot(stack: Dictionary) -> bool:
	return UnitType.is_ranged(String(stack["type"])) \
		and int(stack.get("shots_left", 0)) > 0


# Abilities, die der Kampf bereits auswertet. Alles andere wird beim
# Kampfstart einmal geloggt (Inventur fuer M6b), aber ignoriert.
const HANDLED_ABILITIES: Array = [
	# M4 Teil 3
	"ranged", "melee_penalty_half", "no_melee_penalty",
	# M6b Teil 1
	"flying", "double_attack", "double_shot", "unlimited_retaliations",
	"no_retaliation", "defense_ignore_25pct", "jousting_bonus",
	"jousting_bonus_light", "polearm_bonus_vs_cavalry", "life_drain_50pct",
	"regeneration_per_turn", "regeneration_if_half_hp",
	# M6b Teil 2 (Status-Effekte + Todeswolke)
	"root_enemy_on_hit_20pct", "blind_enemy_on_hit_15pct", "bash_stun_10pct",
	"disease_on_hit", "curse_on_hit_10pct", "aging_on_hit_10pct",
	"death_cloud_aoe_small",
	# M6 (Moral/Glueck/Erzfeind)
	"undead", "morale_aura", "hates:necro_tier7",
	# M9 (Belagerung)
	"attack_wall",
]


# Status-Effekte des Angreifers auf das Ziel wuerfeln; liefert das
# Log-Fragment (leer, wenn nichts gegriffen hat).
func _roll_status(attacker_uid: String, target: Dictionary) -> String:
	var applied: Array = Fx.apply_on_hit(attacker_uid, target, _rng)
	if applied.is_empty():
		return ""
	return "  [%s]" % Fx.names_text(applied)


# Kleine Todeswolke (Lich): Nachbar-Stacks des Ziels nehmen halben
# Schaden mit. Trifft nur die Seite des Ziels, nicht die eigene.
func _apply_aoe(attacker_uid: String, target: Dictionary, dmg: int) -> String:
	var frac: float = Fx.aoe_fraction(attacker_uid)
	if frac <= 0.0 or dmg <= 0:
		return ""
	var splash: int = int(float(dmg) * frac)
	if splash <= 0:
		return ""
	var side_arr: Array = _p_stacks if int(target["side"]) == 0 else _e_stacks
	var tpos: Vector2i = Vector2i(target["pos"])
	var hit: int = 0
	var killed: int = 0
	for s in side_arr:
		if s == target or int(s["count"]) <= 0:
			continue
		if _adj(Vector2i(s["pos"]), tpos):
			killed += _apply_dmg(s, splash)
			hit += 1
	if hit == 0:
		return ""
	return "  Wolke: %d Nachbar(n) je %d Sch., -%d" % [hit, splash, killed]


# Ein Nahkampf-Angriff inkl. Konter und Lebensentzug. Rueckgabe: Text-
# Fragment fuer das Kampf-Log. Wird von Spieler- und KI-Pfad benutzt,
# damit beide Seiten exakt dieselben Ability-Regeln sehen.
func _melee_exchange(attacker: Dictionary, target: Dictionary) -> String:
	var a_uid: String = String(attacker["type"])
	var t_uid: String = String(target["type"])
	# Leergeschossene Fernkaempfer schlagen mit Malus zu (M4 Teil 3).
	var a_ranged: bool = UnitType.is_ranged(a_uid)
	var hits: int = Abil.attacks_per_turn(a_uid, false)
	var dmg_sum: int = 0
	var killed: int = 0
	var struck: int = 0
	var drain: float = Abil.drain_fraction(a_uid)
	var counter_dmg: int = 0
	var counter_kill: int = 0
	var status_txt: String = ""
	var woke: bool = false
	for _i in range(hits):
		if int(target["count"]) <= 0 or int(attacker["count"]) <= 0:
			break
		var dmg: int = _dmg(attacker, target, a_ranged)
		var luck_txt: String = _luck_suffix()
		if luck_txt != "" and not status_txt.contains(luck_txt):
			status_txt += luck_txt
		dmg_sum += dmg
		killed += _apply_dmg(target, dmg)
		struck += 1
		# Nahkampf-Treffer weckt geblendete Ziele (vor dem Konter-Check,
		# damit ein geweckter Stack sofort zurueckschlagen darf).
		if Fx.wake_on_melee(target):
			woke = true
		# Lebensentzug heilt anteilig am zugefuegten Schaden (Vampir).
		if drain > 0.0:
			CombatMath.heal(attacker, int(float(dmg) * drain))
		status_txt += _roll_status(a_uid, target)
		# Konter nach jedem Treffer pruefen: unlimited_retaliations laesst
		# den Verteidiger jedes Mal zurueckschlagen, no_retaliation des
		# Angreifers unterdrueckt den Konter komplett. Betaeubte/geblendete
		# Verteidiger kontern nicht.
		if int(target["count"]) > 0 and not Fx.blocks_turn(target) \
				and Abil.retaliation_allowed(
				t_uid, a_uid, int(target.get("retaliations", 0))):
			target["retaliations"] = int(target.get("retaliations", 0)) + 1
			target["retaliated"] = true
			var rdmg: int = max(1, _dmg(target, attacker, UnitType.is_ranged(t_uid)) / 2)
			counter_dmg += rdmg
			counter_kill += _apply_dmg(attacker, rdmg)
	var msg: String = "%d Sch., -%d" % [dmg_sum, killed]
	if struck > 1:
		msg = "%dx (%s)" % [struck, msg]
	msg += status_txt
	if woke:
		msg += "  (geweckt)"
	if counter_dmg > 0:
		msg += "  Konter: %d Sch., -%d" % [counter_dmg, counter_kill]
	return msg


func _log_unhandled_abilities() -> void:
	var seen: Dictionary = {}
	for s in _p_stacks + _e_stacks:
		for a in UnitType.abilities_of(String(s["type"])):
			if not HANDLED_ABILITIES.has(String(a)):
				seen[String(a)] = true
	if not seen.is_empty():
		print("TacticalBattle: ignorierte Abilities (M6b): ", ", ".join(seen.keys()))


func _place_stacks() -> void:
	for i in range(_p_stacks.size()):
		_p_stacks[i]["pos"] = Vector2i(1, _row(i, _p_stacks.size()))
	for i in range(_e_stacks.size()):
		_e_stacks[i]["pos"] = Vector2i(GRID_COLS - 2, _row(i, _e_stacks.size()))


func _row(i: int, n: int) -> int:
	if n <= 1:
		return GRID_ROWS / 2
	return (GRID_ROWS / (n + 1)) * (i + 1)


func _rebuild_order() -> void:
	# HoMM-aehnliches Warten: Stacks, die gewartet haben, rutschen ans
	# Ende der Reihenfolge und ziehen erst, nachdem alle Nicht-Warter
	# dran waren. Innerhalb jeder Gruppe weiter nach Initiative sortiert.
	var normal: Array = []
	var waiters: Array = []
	for i in range(_p_stacks.size()):
		if int(_p_stacks[i]["count"]) <= 0:
			continue
		var e := {"side": 0, "idx": i,
			"speed": UnitType.speed_of(String(_p_stacks[i]["type"])),
			"waited": bool(_p_stacks[i].get("waited", false))}
		if bool(e["waited"]):
			waiters.append(e)
		else:
			normal.append(e)
	for i in range(_e_stacks.size()):
		if int(_e_stacks[i]["count"]) <= 0:
			continue
		var e2 := {"side": 1, "idx": i,
			"speed": UnitType.speed_of(String(_e_stacks[i]["type"])),
			"waited": bool(_e_stacks[i].get("waited", false))}
		if bool(e2["waited"]):
			waiters.append(e2)
		else:
			normal.append(e2)
	var by_speed := func(a, b): return int(a["speed"]) > int(b["speed"])
	normal.sort_custom(by_speed)
	waiters.sort_custom(by_speed)
	_turn_order = normal + waiters


func _active_stack() -> Dictionary:
	if _active_slot >= _turn_order.size():
		return {}
	var slot: Dictionary = _turn_order[_active_slot]
	var arr: Array = _p_stacks if int(slot["side"]) == 0 else _e_stacks
	var idx: int = int(slot["idx"])
	if idx >= arr.size() or int(arr[idx]["count"]) <= 0:
		return {}
	return arr[idx]


func _step() -> void:
	if _finished:
		return
	if _turn_order.is_empty():
		_next_round()
		return
	if _active_slot >= _turn_order.size():
		_next_round()
		return
	var slot: Dictionary = _turn_order[_active_slot]
	# Betaeubte/geblendete Stacks verlieren ihren Zug (M6b Teil 2) -
	# gilt fuer beide Seiten, damit die Regel symmetrisch bleibt.
	var st: Dictionary = _active_stack()
	if not st.is_empty() and Fx.blocks_turn(st):
		var who: String = "Held" if int(slot["side"]) == 0 else "Feind"
		_set_action("%s %s ist %s - Zug verloren." % [
			who, UnitType.short_of(String(st["type"])), Fx.marker_name(st)])
		_advance()
		return
	# Schlechte Moral kann den Zug kosten (M6). Untote sind immun.
	if not st.is_empty() and not Mor.immune_to_bad_morale(String(st["type"])):
		var mor: int = _p_morale if int(slot["side"]) == 0 else _e_morale
		if Mor.rolls_freeze(mor, _rng):
			var who2: String = "Held" if int(slot["side"]) == 0 else "Feind"
			_set_action("%s %s: keine Moral - Zug verloren." % [
				who2, UnitType.short_of(String(st["type"]))])
			_advance()
			return
	if int(slot["side"]) == 0:
		_build_reachable()
		_refresh()
	else:
		_ai_turn()


func _next_round() -> void:
	_round += 1
	for s in _p_stacks + _e_stacks:
		s["retaliated"] = false
		s["waited"] = false
		s["retaliations"] = 0
		s["tiles_moved"] = 0
		s["morale_extra_used"] = false
		Fx.tick(s)
		_regenerate(s)
	# Belagerungs-Runde: erst schiesst der Turm, dann arbeitet das
	# Katapult - beides einmal pro Runde, bevor die Stacks ziehen.
	_tower_shot()
	_catapult_shot()
	_rebuild_order()
	_active_slot = 0
	_step()


# --- Belagerung (M9) ---

func _walls_standing() -> bool:
	return not _wall_hp.is_empty()


# Schaden auf ein Mauer-Segment. Bei 0 verschwindet es aus _obstacles UND
# _ob_map - damit ist das Feld sofort passierbar und schussdurchlaessig,
# ohne dass Pathing oder Schusslinie etwas von Mauern wissen muessen.
func _damage_wall(pos: Vector2i, dmg: int) -> String:
	if not _wall_hp.has(pos):
		return ""
	var left: int = int(_wall_hp[pos]) - dmg
	if left > 0:
		_wall_hp[pos] = left
		for o in _obstacles:
			if Vector2i(o["pos"]) == pos:
				o["hp"] = left
		return "Mauer broeckelt"
	_wall_hp.erase(pos)
	_ob_map.erase(pos)
	var keep: Array = []
	for o in _obstacles:
		if Vector2i(o["pos"]) != pos:
			keep.append(o)
	_obstacles = keep
	return "Bresche!"


# Das Katapult des Angreifers feuert einmal pro Runde auf das Segment,
# das dem Tor am naechsten liegt - so entsteht die Bresche dort, wo der
# Durchbruch taktisch etwas bringt.
func _catapult_shot() -> void:
	if not _siege or not _walls_standing():
		return
	var gate: int = Obstacles.gate_row(GRID_ROWS)
	var best: Vector2i = Vector2i(-1, -1)
	var best_d: int = 9999
	for pos in _wall_hp.keys():
		var d: int = abs(int((pos as Vector2i).y) - gate)
		if d < best_d:
			best_d = d
			best = pos
	if best.x < 0:
		return
	var res: String = _damage_wall(best, 1)
	if res != "":
		_set_action("Katapult -> Mauer (%d,%d): %s" % [best.x, best.y, res])


# Pfeilturm der Stadt: solange die Mauer steht, trifft er einmal pro
# Runde den groessten Angreifer-Stack.
func _tower_shot() -> void:
	if not _siege or _tower_dmg <= 0 or not _walls_standing():
		return
	var target: Dictionary = {}
	var best: int = -1
	for s in _p_stacks:
		if int(s["count"]) > 0 and int(s["count"]) > best:
			best = int(s["count"])
			target = s
	if target.is_empty():
		return
	var killed: int = _apply_dmg(target, _tower_dmg)
	_set_action("Pfeilturm -> %s: %d Sch., -%d" % [
		UnitType.short_of(String(target["type"])), _tower_dmg, killed])


# Rundenstart-Regeneration (Baumvater heilt immer, Gespenst nur
# angeschlagen). Heilt die vorderste Einheit, keine Wiederbelebung.
func _regenerate(stack: Dictionary) -> void:
	if int(stack["count"]) <= 0:
		return
	var uid: String = String(stack["type"])
	var hp_max: int = UnitType.hp_of(uid)
	var gain: int = Abil.regen_hp(uid, int(stack["top_hp"]), hp_max)
	if gain > 0:
		stack["top_hp"] = min(hp_max, int(stack["top_hp"]) + gain)


func _advance() -> void:
	_active_slot += 1
	if _active_slot >= _turn_order.size():
		_next_round()
		return
	var next_side: int = int(_turn_order[_active_slot]["side"])
	if next_side == 1:
		get_tree().create_timer(0.30).timeout.connect(_step)
	else:
		_step()


func _build_reachable() -> void:
	_reachable.clear()
	var st: Dictionary = _active_stack()
	if st.is_empty():
		return
	var start: Vector2i = st["pos"]
	# Verwurzelt (Treant-Treffer): der Stack bleibt stehen, darf aber
	# weiter angreifen, wenn ein Gegner neben ihm steht.
	if Fx.blocks_move(st):
		_reachable[start] = 0
		return
	var spd: int = UnitType.speed_of(String(st["type"]))
	var blocked: Array = []
	for s in _p_stacks:
		if Vector2i(s["pos"]) != start and int(s["count"]) > 0:
			blocked.append(Vector2i(s["pos"]))
	for s in _e_stacks:
		if int(s["count"]) > 0:
			blocked.append(Vector2i(s["pos"]))
	var dist: Dictionary = _dijkstra_for(start, blocked,
		Abil.ignores_obstacles(String(st["type"])))
	for k in dist.keys():
		if int(dist[k]) <= spd:
			_reachable[k] = int(dist[k])


func _adj(a: Vector2i, b: Vector2i) -> bool:
	return abs(a.x - b.x) + abs(a.y - b.y) == 1


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build_ui()


func _build_ui() -> void:
	var bg := ColorRect.new()
	bg.color = Color(0.04, 0.05, 0.08)
	bg.mouse_filter = Control.MOUSE_FILTER_STOP
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(bg)

	var title := Label.new()
	title.text = "KAMPF"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.set_anchors_preset(Control.PRESET_TOP_WIDE)
	title.offset_top = 30.0
	title.offset_bottom = 100.0
	title.add_theme_font_size_override("font_size", 52)
	title.add_theme_color_override("font_color", Color(0.95, 0.85, 0.40))
	add_child(title)

	_info_lbl = Label.new()
	_info_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_info_lbl.set_anchors_preset(Control.PRESET_TOP_WIDE)
	_info_lbl.offset_top = 105.0
	_info_lbl.offset_bottom = 175.0
	_info_lbl.add_theme_font_size_override("font_size", 28)
	_info_lbl.add_theme_color_override("font_color", Color(0.9, 0.92, 0.96))
	add_child(_info_lbl)

	_action_lbl = Label.new()
	_action_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	_action_lbl.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	_action_lbl.set_anchors_preset(Control.PRESET_TOP_WIDE)
	_action_lbl.offset_left = 40.0
	_action_lbl.offset_right = -40.0
	_action_lbl.offset_top = 178.0
	_action_lbl.offset_bottom = 318.0
	_action_lbl.add_theme_font_size_override("font_size", 22)
	_action_lbl.add_theme_color_override("font_color", Color(0.80, 0.88, 1.0))
	add_child(_action_lbl)

	_grid_area = Control.new()
	_grid_area.set_anchors_preset(Control.PRESET_FULL_RECT)
	_grid_area.offset_left = 30.0
	_grid_area.offset_right = -30.0
	_grid_area.offset_top = 330.0
	_grid_area.offset_bottom = -220.0
	_grid_area.mouse_filter = Control.MOUSE_FILTER_STOP
	_grid_area.draw.connect(_draw_grid)
	_grid_area.resized.connect(func(): _grid_area.queue_redraw())
	_grid_area.gui_input.connect(_on_grid_input)
	add_child(_grid_area)

	_wait_btn = Button.new()
	_wait_btn.text = "Warten"
	_wait_btn.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	_wait_btn.offset_left = 50.0
	_wait_btn.offset_top = -170.0
	_wait_btn.offset_right = 480.0
	_wait_btn.offset_bottom = -50.0
	_wait_btn.add_theme_font_size_override("font_size", 38)
	_wait_btn.pressed.connect(_on_wait)
	add_child(_wait_btn)

	_flee_btn = Button.new()
	_flee_btn.text = "Fliehen"
	_flee_btn.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	_flee_btn.offset_left = -480.0
	_flee_btn.offset_top = -170.0
	_flee_btn.offset_right = -50.0
	_flee_btn.offset_bottom = -50.0
	_flee_btn.add_theme_font_size_override("font_size", 38)
	_flee_btn.pressed.connect(_on_flee)
	add_child(_flee_btn)


func _geom() -> Array:
	var sz: Vector2 = _grid_area.size
	var cell: float = min(sz.x / float(GRID_COLS), sz.y / float(GRID_ROWS))
	var ox: float = (sz.x - cell * GRID_COLS) * 0.5
	var oy: float = (sz.y - cell * GRID_ROWS) * 0.5
	return [Vector2(ox, oy), cell]


func _cell_at(p: Vector2) -> Vector2i:
	var g: Array = _geom()
	var o: Vector2 = g[0]; var c: float = g[1]
	if c <= 0.0: return Vector2i(-1, -1)
	var cx: int = int((p.x - o.x) / c)
	var cy: int = int((p.y - o.y) / c)
	if cx < 0 or cx >= GRID_COLS or cy < 0 or cy >= GRID_ROWS:
		return Vector2i(-1, -1)
	return Vector2i(cx, cy)


func _draw_grid() -> void:
	var g: Array = _geom()
	var o: Vector2 = g[0]; var c: float = g[1]
	if c <= 0.0: return
	var gw := c * GRID_COLS; var gh := c * GRID_ROWS

	_grid_area.draw_rect(Rect2(o, Vector2(gw, gh)), Color(0.10, 0.12, 0.16), true)

	_draw_obstacles(o, c)

	var active: Dictionary = _active_stack()
	var active_pos := Vector2i(-1, -1)
	if not active.is_empty() and int(_turn_order[_active_slot]["side"]) == 0:
		active_pos = Vector2i(active["pos"])

	for cell in _reachable.keys():
		var cv: Vector2i = cell
		if cv == active_pos: continue
		var r := Rect2(o + Vector2(float(cv.x)*c, float(cv.y)*c), Vector2(c, c))
		_grid_area.draw_rect(r, Color(0.25, 0.45, 0.28, 0.5), true)

	for s in _e_stacks:
		if int(s["count"]) <= 0: continue
		var ep: Vector2i = Vector2i(s["pos"])
		for d in [Vector2i(1,0), Vector2i(-1,0), Vector2i(0,1), Vector2i(0,-1)]:
			if (ep + d) == active_pos or _reachable.has(ep + d):
				var r2 := Rect2(o + Vector2(float(ep.x)*c, float(ep.y)*c), Vector2(c, c))
				_grid_area.draw_rect(r2, Color(0.55, 0.20, 0.20, 0.6), true)
				break

	var lc := Color(0.22, 0.27, 0.35)
	for col in range(GRID_COLS + 1):
		var x: float = o.x + col * c
		_grid_area.draw_line(Vector2(x, o.y), Vector2(x, o.y + gh), lc, 1.5)
	for row in range(GRID_ROWS + 1):
		var y: float = o.y + row * c
		_grid_area.draw_line(Vector2(o.x, y), Vector2(o.x + gw, y), lc, 1.5)

	var r_active: float = c * 0.40
	for i in range(_p_stacks.size()):
		var s: Dictionary = _p_stacks[i]
		if int(s["count"]) <= 0: continue
		var sp: Vector2i = Vector2i(s["pos"])
		var ctr := o + Vector2((float(sp.x)+0.5)*c, (float(sp.y)+0.5)*c)
		# Seiten-Ring bleibt auch mit Sprite: er sagt auf einen Blick, wem
		# der Stack gehoert - die Silhouette allein tut das nicht.
		var col_fill := Color(0.95, 0.80, 0.25) if sp != active_pos else Color(1.0, 0.95, 0.4)
		_draw_token(ctr, c, r_active, s, col_fill, Color(0.5, 0.35, 0.05))
		if sp == active_pos:
			_grid_area.draw_arc(ctr, r_active + 4, 0, TAU, 32, Color(1,1,0.5,0.7), 2.5)
		_draw_lbl(ctr, UnitType.short_of(String(s["type"])) + str(int(s["count"])), c)
		_draw_hp_bar(ctr, c, int(s["top_hp"]), UnitType.hp_of(String(s["type"])))
		_draw_status_marker(ctr, c, s)
		if bool(s.get("waited", false)):
			_draw_wait_marker(ctr, r_active)

	for i in range(_e_stacks.size()):
		var s: Dictionary = _e_stacks[i]
		if int(s["count"]) <= 0: continue
		var sp: Vector2i = Vector2i(s["pos"])
		var ctr := o + Vector2((float(sp.x)+0.5)*c, (float(sp.y)+0.5)*c)
		_draw_token(ctr, c, r_active, s, Color(0.5, 0.5, 0.55), Color(0.85, 0.25, 0.25))
		_draw_lbl(ctr, UnitType.short_of(String(s["type"])) + str(int(s["count"])), c)
		_draw_hp_bar(ctr, c, int(s["top_hp"]), UnitType.hp_of(String(s["type"])))
		_draw_status_marker(ctr, c, s)
		if bool(s.get("waited", false)):
			_draw_wait_marker(ctr, r_active)


# Ein Stack-Token: Seiten-Scheibe + Ring, darauf das Einheiten-Sprite
# (M10). Fehlt eine SVG, bleibt die alte Kreis-Darstellung uebrig - das
# Spiel ist also nie von den Assets abhaengig.
func _draw_token(ctr: Vector2, cell: float, r: float, s: Dictionary,
		fill: Color, ring: Color) -> void:
	var tex: Texture2D = _unit_texture(String(s["type"]))
	if tex == null:
		# Kein Sprite: alte Darstellung (helle Scheibe, Kuerzel darauf).
		_grid_area.draw_circle(ctr, r, fill)
		_grid_area.draw_arc(ctr, r, 0, TAU, 32, ring, 3.0)
		return
	# Mit Sprite MUSS die Scheibe dunkel sein: die Token tragen die
	# Fraktionsfarbe, und Menschen-Gold auf goldener Scheibe war praktisch
	# unsichtbar. Seite steckt jetzt im Ring, nicht in der Flaeche.
	_grid_area.draw_circle(ctr, r, fill.darkened(0.72))
	var size: float = cell * 0.92
	_grid_area.draw_texture_rect(tex,
		Rect2(ctr - Vector2(size, size) * 0.5, Vector2(size, size)), false)
	_grid_area.draw_arc(ctr, r, 0, TAU, 32, ring, 3.0)


# Sprite-Lookup mit Cache. Konvention: assets/units/<fraktion>/<id>.svg,
# Fraktions-Verzeichnis wie in CityScreen.FACTION_DIRS. Nicht gefundene
# Pfade werden als null gecacht, damit der Render-Loop nicht jeden Frame
# erneut sucht.
const UNIT_FACTION_DIRS := ["waldvolk", "menschen", "totenreich", "orks"]
var _unit_tex_cache: Dictionary = {}


func _unit_texture(uid: String) -> Texture2D:
	if _unit_tex_cache.has(uid):
		return _unit_tex_cache[uid] as Texture2D
	var fid: int = UnitType.faction_of(uid)
	var tex: Texture2D = null
	if fid >= 0 and fid < UNIT_FACTION_DIRS.size():
		var path: String = "res://assets/units/%s/%s.svg" % [UNIT_FACTION_DIRS[fid], uid]
		if ResourceLoader.exists(path):
			tex = load(path) as Texture2D
	_unit_tex_cache[uid] = tex
	return tex


# Zeichnet die Obstacle-Formen auf dem Grid: Stein als graue Raute,
# Baumstamm als braunes Horizontal-Oval, Busch als gruene Punktwolke,
# Sumpf als braun-gruenes Feld. Formen unterscheiden sich deutlich,
# damit der Spieler auf einen Blick Bewegungs-/Schuss-Regeln ablesen
# kann, ohne auf Mouseover angewiesen zu sein.
func _draw_obstacles(o: Vector2, c: float) -> void:
	# KIND als Integer-Literal, siehe _dijkstra_for: cross-class
	# class_name-Referenzen sind im Android-Export unzuverlaessig.
	# 0=Stein, 1=Baumstamm, 2=Busch, 3=Sumpf.
	for ob in _obstacles:
		var pos: Vector2i = Vector2i(ob["pos"])
		var kind: int = int(ob["kind"])
		var ctr := o + Vector2((float(pos.x) + 0.5) * c, (float(pos.y) + 0.5) * c)
		if kind == 0:
			var pts := PackedVector2Array([
				Vector2(ctr.x, ctr.y - c * 0.38),
				Vector2(ctr.x + c * 0.38, ctr.y),
				Vector2(ctr.x, ctr.y + c * 0.38),
				Vector2(ctr.x - c * 0.38, ctr.y),
			])
			_grid_area.draw_colored_polygon(pts, Color(0.55, 0.55, 0.58))
			var outline := PackedVector2Array(pts)
			outline.append(pts[0])
			_grid_area.draw_polyline(outline, Color(0.25, 0.25, 0.28), 2.0)
		elif kind == 1:
			var tl := ctr + Vector2(-c * 0.42, -c * 0.18)
			_grid_area.draw_rect(Rect2(tl, Vector2(c * 0.84, c * 0.36)), Color(0.46, 0.30, 0.18), true)
			_grid_area.draw_rect(Rect2(tl, Vector2(c * 0.84, c * 0.36)), Color(0.22, 0.14, 0.08), false, 2.0)
			_grid_area.draw_line(
				Vector2(ctr.x - c * 0.30, ctr.y),
				Vector2(ctr.x + c * 0.30, ctr.y),
				Color(0.28, 0.18, 0.10), 1.5)
		elif kind == 2:
			_grid_area.draw_circle(ctr + Vector2(-c * 0.18, c * 0.05), c * 0.22, Color(0.22, 0.45, 0.22))
			_grid_area.draw_circle(ctr + Vector2(c * 0.18, -c * 0.05), c * 0.22, Color(0.26, 0.50, 0.25))
			_grid_area.draw_circle(ctr, c * 0.25, Color(0.30, 0.55, 0.28))
		elif kind == 3:
			_grid_area.draw_rect(
				Rect2(o + Vector2(float(pos.x) * c, float(pos.y) * c), Vector2(c, c)),
				Color(0.30, 0.36, 0.20), true)
			_grid_area.draw_circle(ctr + Vector2(-c * 0.20, -c * 0.10), c * 0.08, Color(0.18, 0.24, 0.12))
			_grid_area.draw_circle(ctr + Vector2(c * 0.22, c * 0.15), c * 0.08, Color(0.18, 0.24, 0.12))
		elif kind == 4:
			# Stadtmauer (M9): Quaderblock mit Zinnen. Angeschlagene
			# Segmente (hp 1) bekommen Risse, damit der Spieler sieht,
			# wo die naechste Katapult-Kugel die Bresche schlaegt.
			var cell_tl := o + Vector2(float(pos.x) * c, float(pos.y) * c)
			_grid_area.draw_rect(Rect2(cell_tl + Vector2(c * 0.06, c * 0.16),
				Vector2(c * 0.88, c * 0.72)), Color(0.52, 0.50, 0.46), true)
			# Zinnen oben.
			for z in range(3):
				_grid_area.draw_rect(Rect2(
					cell_tl + Vector2(c * (0.08 + 0.30 * float(z)), c * 0.04),
					Vector2(c * 0.22, c * 0.14)), Color(0.58, 0.56, 0.52), true)
			# Fugen.
			_grid_area.draw_line(cell_tl + Vector2(c * 0.06, c * 0.44),
				cell_tl + Vector2(c * 0.94, c * 0.44), Color(0.34, 0.32, 0.30), 1.5)
			_grid_area.draw_line(cell_tl + Vector2(c * 0.50, c * 0.16),
				cell_tl + Vector2(c * 0.50, c * 0.44), Color(0.34, 0.32, 0.30), 1.5)
			_grid_area.draw_line(cell_tl + Vector2(c * 0.28, c * 0.44),
				cell_tl + Vector2(c * 0.28, c * 0.88), Color(0.34, 0.32, 0.30), 1.5)
			_grid_area.draw_rect(Rect2(cell_tl + Vector2(c * 0.06, c * 0.16),
				Vector2(c * 0.88, c * 0.72)), Color(0.24, 0.23, 0.22), false, 2.0)
			if int(ob.get("hp", Obstacles.WALL_SEGMENT_HP)) <= 1:
				var crack := Color(0.15, 0.13, 0.12)
				_grid_area.draw_line(cell_tl + Vector2(c * 0.30, c * 0.20),
					cell_tl + Vector2(c * 0.46, c * 0.52), crack, 2.5)
				_grid_area.draw_line(cell_tl + Vector2(c * 0.46, c * 0.52),
					cell_tl + Vector2(c * 0.36, c * 0.84), crack, 2.5)
				_grid_area.draw_line(cell_tl + Vector2(c * 0.62, c * 0.30),
					cell_tl + Vector2(c * 0.74, c * 0.60), crack, 2.0)


# Kleiner Cyan-Ring auf der Oberseite eines Stacks, der gewartet hat:
# signalisiert, dass er in dieser Runde spaeter noch einmal dran kommt.
# Status-Kuerzel ueber dem Stack (W=verwurzelt, B=geblendet, S=betaeubt,
# K=krank, F=verflucht, A=gealtert). Violett, damit es sich von HP-Balken
# und Warte-Marker abhebt.
func _draw_status_marker(ctr: Vector2, cell: float, s: Dictionary) -> void:
	var txt: String = Fx.marker_text(s)
	if txt == "":
		return
	var font: Font = ThemeDB.fallback_font
	var fs: int = int(cell * 0.26)
	var sz: Vector2 = font.get_string_size(txt, HORIZONTAL_ALIGNMENT_LEFT, -1, fs)
	_grid_area.draw_string(font,
		Vector2(ctr.x - sz.x * 0.5, ctr.y - cell * 0.34),
		txt, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(0.85, 0.55, 1.0))


func _draw_wait_marker(ctr: Vector2, r: float) -> void:
	var p := Vector2(ctr.x, ctr.y - r)
	_grid_area.draw_circle(p, max(4.0, r * 0.22), Color(0.25, 0.75, 0.95))
	_grid_area.draw_arc(p, max(4.0, r * 0.22), 0, TAU, 16, Color(0.05, 0.10, 0.15), 2.0)


# HP-Balken unter dem Stack: nur sichtbar, wenn die vorderste Einheit
# angekratzt ist. Gruen -> Gelb -> Rot je nach Rest-HP, damit der Spieler
# auf einen Blick sieht, ob der naechste Treffer den Top-Krieger faellt.
func _draw_hp_bar(ctr: Vector2, cell: float, top_hp: int, max_hp: int) -> void:
	if max_hp <= 0 or top_hp >= max_hp: return
	var frac: float = clampf(float(top_hp) / float(max_hp), 0.0, 1.0)
	var w: float = cell * 0.70
	var h: float = max(4.0, cell * 0.08)
	var top_left := Vector2(ctr.x - w * 0.5, ctr.y + cell * 0.32)
	_grid_area.draw_rect(Rect2(top_left, Vector2(w, h)), Color(0.15, 0.05, 0.05), true)
	var fill_col := Color(0.85, 0.25, 0.20)
	if frac > 0.66:
		fill_col = Color(0.35, 0.80, 0.35)
	elif frac > 0.33:
		fill_col = Color(0.95, 0.80, 0.25)
	_grid_area.draw_rect(Rect2(top_left, Vector2(w * frac, h)), fill_col, true)
	_grid_area.draw_rect(Rect2(top_left, Vector2(w, h)), Color(0.05, 0.05, 0.05), false, 1.0)


func _draw_lbl(ctr: Vector2, txt: String, cell: float) -> void:
	var font: Font = get_theme_default_font()
	if font == null: return
	var fs: int = int(max(16.0, cell * 0.38))
	var sz: Vector2 = font.get_string_size(txt, HORIZONTAL_ALIGNMENT_CENTER, -1.0, fs)
	# Seit die Token-Scheibe dunkel ist (M10), braucht die Beschriftung
	# helle Schrift mit dunklem Schlagschatten - sonst verschwindet sie
	# auf der Scheibe. Sie sitzt leicht unterhalb der Mitte, damit Kopf
	# und Hoerner der Silhouette frei bleiben.
	var pos := Vector2(ctr.x - sz.x * 0.5, ctr.y + cell * 0.22)
	_grid_area.draw_string(font, pos + Vector2(1.5, 1.5),
		txt, HORIZONTAL_ALIGNMENT_CENTER, -1.0, fs, Color(0, 0, 0, 0.85))
	_grid_area.draw_string(font, pos,
		txt, HORIZONTAL_ALIGNMENT_CENTER, -1.0, fs, Color(0.98, 0.96, 0.90))


func _refresh() -> void:
	if _info_lbl == null: return
	var p_sum := 0
	for s in _p_stacks: p_sum += int(s["count"])
	var e_sum := 0
	for s in _e_stacks: e_sum += int(s["count"])
	# Moral/Glueck der Spielerseite mit anzeigen - die Armee-Mischung ist
	# damit direkt im Kampf ablesbar (M6).
	_info_lbl.text = "%s %d (%s)  vs  %s %d   Runde %d" % [
		_player_name, p_sum, Mor.status_text(_p_morale, _p_luck),
		_enemy_name, e_sum, _round]
	if _grid_area != null:
		_grid_area.queue_redraw()


func _set_action(txt: String) -> void:
	_log.append(txt)
	if _log.size() > LOG_LINES:
		_log = _log.slice(_log.size() - LOG_LINES)
	if _action_lbl != null:
		_action_lbl.text = "\n".join(_log)


func _on_grid_input(event: InputEvent) -> void:
	if _finished: return
	if not (event is InputEventMouseButton): return
	var mb: InputEventMouseButton = event
	if not mb.pressed or mb.button_index != MOUSE_BUTTON_LEFT: return
	if _turn_order.is_empty() or _active_slot >= _turn_order.size(): return
	if int(_turn_order[_active_slot]["side"]) != 0: return

	var cell: Vector2i = _cell_at(mb.position)
	if cell.x < 0: return

	var active: Dictionary = _active_stack()
	if active.is_empty(): return

	for i in range(_e_stacks.size()):
		var es: Dictionary = _e_stacks[i]
		if int(es["count"]) <= 0: continue
		if Vector2i(es["pos"]) == cell:
			_try_attack_enemy(i)
			return

	# Mauer-Angriff (M9): Einheiten mit attack_wall koennen ein Segment
	# selbst niederschlagen, statt auf das Katapult zu warten. Das ist
	# die Daseinsberechtigung des Zyklopen.
	if _try_attack_wall(active, cell):
		return

	if _reachable.has(cell) and cell != Vector2i(active["pos"]):
		active["tiles_moved"] = int(_reachable.get(cell, 0))
		active["pos"] = cell
		_set_action("Held %s bewegt sich." % UnitType.short_of(String(active["type"])))
		_build_reachable()
		_end_player_turn()


# Tap auf ein Mauer-Segment mit einer attack_wall-Einheit. Rueckgabe
# true = Aktion verbraucht (Zug beendet).
func _try_attack_wall(active: Dictionary, cell: Vector2i) -> bool:
	if not _siege or not _wall_hp.has(cell):
		return false
	var uid: String = String(active["type"])
	if not UnitType.has_ability(uid, "attack_wall"):
		return false
	var res: String = _damage_wall(cell, 1)
	_set_action("%s schlaegt gegen die Mauer: %s" % [UnitType.short_of(uid), res])
	_end_player_turn()
	return true


func _try_attack_enemy(e_idx: int) -> void:
	var active: Dictionary = _active_stack()
	var estack: Dictionary = _e_stacks[e_idx]
	var epos: Vector2i = Vector2i(estack["pos"])
	var apos: Vector2i = Vector2i(active["pos"])
	var uid: String = String(active["type"])

	var atk_s: String = UnitType.short_of(uid)
	var def_s: String = UnitType.short_of(String(estack["type"]))
	# Schiessen nur mit Munition - leergeschossene Schuetzen fallen in
	# die Nahkampf-Zweige unten (dort mit Fernkaempfer-Malus).
	if _can_shoot(active):
		var mod: Dictionary = Obstacles.line_modifier(_obstacles, apos, epos)
		if bool(mod["blocked"]):
			_set_action("Held %s: keine Schusslinie (Stein im Weg)." % atk_s)
			return
		var adjacent: bool = _adj(apos, epos)
		# Doppelschuss (Erz-Elfen) feuert zweimal - kostet 2 Munition.
		var volleys: int = Abil.attacks_per_turn(uid, true)
		var dmg: int = 0
		var killed: int = 0
		var fired: int = 0
		var extra: String = ""
		for _v in range(volleys):
			if int(estack["count"]) <= 0 or int(active["shots_left"]) <= 0:
				break
			var d1: int = _dmg(active, estack, adjacent)
			if bool(mod["halve"]):
				d1 = max(1, d1 / 2)
			dmg += d1
			killed += _apply_dmg(estack, d1)
			active["shots_left"] = int(active["shots_left"]) - 1
			fired += 1
			extra += _luck_suffix()
			extra += _roll_status(uid, estack)
			extra += _apply_aoe(uid, estack, d1)
		var suffix: String = "  (halb: Baumstamm)" if bool(mod["halve"]) else ""
		var shot_txt: String = "%d Sch., -%d" % [dmg, killed]
		if fired > 1:
			shot_txt = "%dx (%s)" % [fired, shot_txt]
		_set_action("Held %s -> %s: %s%s%s  [%d Schuss]" % [
			atk_s, def_s, shot_txt, suffix, extra, int(active["shots_left"])])
		_end_player_turn()
		return

	if _adj(apos, epos):
		_set_action("Held %s -> %s: %s" % [atk_s, def_s, _melee_exchange(active, estack)])
		_end_player_turn()
		return

	var best := Vector2i(-1, -1)
	var best_d := 9999
	for d in [Vector2i(1,0), Vector2i(-1,0), Vector2i(0,1), Vector2i(0,-1)]:
		var n: Vector2i = epos + d
		if _reachable.has(n):
			var dist: int = int(_reachable[n])
			if dist < best_d:
				best_d = dist
				best = n
	if best.x < 0:
		_set_action("Ausser Reichweite.")
		return
	# Anmarsch zaehlt fuer den Jousting-Bonus.
	active["tiles_moved"] = best_d
	active["pos"] = best
	_set_action("Held %s vor -> %s: %s" % [atk_s, def_s, _melee_exchange(active, estack)])
	_end_player_turn()


func _end_player_turn() -> void:
	var side: int = 0
	var idx: int = _acting_idx()
	_rebuild_order()
	if _check_end(): return
	# Gute Moral kann eine zweite Aktion schenken (M6).
	if _claim_morale_extra(side, idx):
		_build_reachable()
		_refresh()
		return
	_advance()


# Array-Index des gerade ziehenden Stacks (stabil, weil Stacks nie aus
# _p_stacks/_e_stacks entfernt werden - sie fallen nur auf count 0).
func _acting_idx() -> int:
	if _active_slot >= _turn_order.size():
		return -1
	return int(_turn_order[_active_slot]["idx"])


# Prueft den Extrazug und setzt _active_slot wieder auf denselben Stack.
# Rueckgabe true = der Stack darf nochmal ziehen.
func _claim_morale_extra(side: int, idx: int) -> bool:
	if idx < 0:
		return false
	var arr: Array = _p_stacks if side == 0 else _e_stacks
	if idx >= arr.size():
		return false
	var s: Dictionary = arr[idx]
	if int(s["count"]) <= 0 or bool(s.get("morale_extra_used", false)):
		return false
	# Gute Moral gilt auch fuer Untote (siehe Morale.gd-Kopf).
	if Fx.blocks_turn(s):
		return false
	var mor: int = _p_morale if side == 0 else _e_morale
	if not Mor.rolls_extra_turn(mor, _rng):
		return false
	# Slot des Stacks in der neu gebauten Reihenfolge finden.
	for i in range(_turn_order.size()):
		if int(_turn_order[i]["side"]) == side and int(_turn_order[i]["idx"]) == idx:
			s["morale_extra_used"] = true
			_active_slot = i
			_set_action("Moral! %s %s zieht nochmal." % [
				"Held" if side == 0 else "Feind", UnitType.short_of(String(s["type"]))])
			return true
	return false


func _ai_turn() -> void:
	var slot: Dictionary = _turn_order[_active_slot]
	var estack: Dictionary = _e_stacks[int(slot["idx"])]
	if int(estack["count"]) <= 0:
		_rebuild_order()
		_advance()
		return

	var best_target: Dictionary = {}
	var best_threat := -1.0
	# Ranged-Priority: Fernkaempfer sind gefaehrlich, weil sie hinter
	# Schwert-Schilden frei schiessen. Die KI sucht sie erst gezielt;
	# nur wenn keine Ranged-Ziele (mehr) leben, faellt sie auf den
	# staerksten Nahkaempfer-Stack zurueck.
	var has_ranged: bool = false
	for ps in _p_stacks:
		if int(ps["count"]) > 0 and _can_shoot(ps):
			has_ranged = true
			break
	for ps in _p_stacks:
		if int(ps["count"]) <= 0: continue
		if has_ranged and not _can_shoot(ps):
			continue
		var th: float = float(int(ps["count"])) / float(max(1, int(estack["count"])))
		if th > best_threat:
			best_threat = th
			best_target = ps
	if best_target.is_empty():
		_advance()
		return

	var epos: Vector2i = Vector2i(estack["pos"])
	var tpos: Vector2i = Vector2i(best_target["pos"])
	var uid: String = String(estack["type"])

	var atk_s: String = UnitType.short_of(uid)
	var def_s: String = UnitType.short_of(String(best_target["type"]))
	if _can_shoot(estack):
		var mod: Dictionary = Obstacles.line_modifier(_obstacles, epos, tpos)
		if not bool(mod["blocked"]):
			var adjacent: bool = _adj(epos, tpos)
			var volleys: int = Abil.attacks_per_turn(uid, true)
			var dmg: int = 0
			var killed: int = 0
			var fired: int = 0
			var extra: String = ""
			for _v in range(volleys):
				if int(best_target["count"]) <= 0 or int(estack["shots_left"]) <= 0:
					break
				var d1: int = _dmg(estack, best_target, adjacent)
				if bool(mod["halve"]):
					d1 = max(1, d1 / 2)
				dmg += d1
				killed += _apply_dmg(best_target, d1)
				estack["shots_left"] = int(estack["shots_left"]) - 1
				fired += 1
				extra += _luck_suffix()
				extra += _roll_status(uid, best_target)
				extra += _apply_aoe(uid, best_target, d1)
			var suffix: String = "  (halb: Baumstamm)" if bool(mod["halve"]) else ""
			var shot_txt: String = "%d Sch., -%d" % [dmg, killed]
			if fired > 1:
				shot_txt = "%dx (%s)" % [fired, shot_txt]
			_set_action("Feind %s -> %s: %s%s%s" % [atk_s, def_s, shot_txt, suffix, extra])
			_rebuild_order()
			if _check_end(): return
			_advance()
			return
		# LOS blockiert (Stein) -> faellt durch auf Melee-Pathing unten.

	var spd: int = UnitType.speed_of(uid)
	# Verwurzelte KI-Stacks bleiben stehen und greifen nur Nachbarn an.
	if Fx.blocks_move(estack):
		spd = 0
	# Hindernisliste: alle anderen lebenden Stacks blockieren Felder.
	var blocked: Array = []
	for s in _p_stacks:
		if int(s["count"]) > 0:
			blocked.append(Vector2i(s["pos"]))
	for s in _e_stacks:
		if int(s["count"]) > 0:
			var pp2: Vector2i = Vector2i(s["pos"])
			if pp2 != epos:
				blocked.append(pp2)
	var dist_map := _bfs_for(epos, blocked, Abil.ignores_obstacles(uid))

	# Primaerziel zuerst pruefen, dann alle anderen lebenden Gegner als
	# Opportunity-Targets: wenn das Primaerziel diese Runde nicht
	# erreichbar ist, aber ein anderer Stack schon, wird der unterwegs
	# angegriffen statt blind weiter zu marschieren.
	var atk_target: Dictionary = {}
	var atk_cell: Vector2i = Vector2i(-1, -1)
	var primary_cell: Vector2i = _attack_cell_for(epos, tpos, dist_map, spd)
	if primary_cell.x >= 0:
		atk_target = best_target
		atk_cell = primary_cell
	else:
		var best_count: int = -1
		for ps in _p_stacks:
			if int(ps["count"]) <= 0: continue
			if ps == best_target: continue
			var c: Vector2i = _attack_cell_for(epos, Vector2i(ps["pos"]), dist_map, spd)
			if c.x < 0: continue
			if int(ps["count"]) > best_count:
				best_count = int(ps["count"])
				atk_target = ps
				atk_cell = c

	if not atk_target.is_empty():
		if atk_cell != epos:
			# Anmarsch-Distanz merken (Jousting-Bonus).
			estack["tiles_moved"] = int(dist_map.get(atk_cell, 0))
			estack["pos"] = atk_cell
			epos = atk_cell
		var def_s2: String = UnitType.short_of(String(atk_target["type"]))
		# Fernkaempfer mit blockierter Schusslinie oder leerem Koecher
		# gleiten hier hinein und kassieren den korrekten Nahkampfabzug.
		_set_action("Feind %s -> %s: %s" % [atk_s, def_s2, _melee_exchange(estack, atk_target)])
	else:
		# Niemand diese Runde erreichbar -> marschiere Richtung Primaerziel.
		var best_step: Vector2i = epos
		var best_to_target: int = abs(epos.x - tpos.x) + abs(epos.y - tpos.y)
		for cell in dist_map.keys():
			var cv: Vector2i = cell
			var d: int = int(dist_map[cv])
			if d <= 0 or d > spd:
				continue
			var mt: int = abs(cv.x - tpos.x) + abs(cv.y - tpos.y)
			if mt < best_to_target:
				best_to_target = mt
				best_step = cv
		if best_step != epos:
			estack["tiles_moved"] = int(dist_map.get(best_step, 0))
			estack["pos"] = best_step
			_set_action("Feind %s bewegt sich." % atk_s)
		else:
			_set_action("Feind %s wartet." % atk_s)

	var acted_idx: int = _acting_idx()
	_rebuild_order()
	if _check_end(): return
	# Extrazug aus guter Moral: derselbe Stack zieht direkt nochmal.
	# Mehr als eine Wiederholung ist unmoeglich (morale_extra_used).
	if _claim_morale_extra(1, acted_idx):
		_ai_turn()
		return
	_advance()


func _dijkstra_for(start: Vector2i, blocked: Array, flying: bool = false) -> Dictionary:
	# Kuerzeste-Pfad-Distanzen vom Startfeld, respektiert Feldkosten der
	# Obstacles (Busch/Sumpf = 2) und blockierende Obstacles (Stein/Baum).
	# Fuer 10x8 Felder genuegt ein simpler O(N^2)-Loop statt echter
	# Priority-Queue. Obstacle-Kind/Block-Checks sind inline als Integer-
	# Vergleiche, weil Cross-File-class_name-Aufrufe im Android-Export
	# historisch unzuverlaessig waren (siehe Pathfinder.gd).
	# KIND: 0=Stein, 1=Baumstamm, 2=Busch, 3=Sumpf, 4=Stadtmauer.
	var dist: Dictionary = {start: 0}
	var visited: Dictionary = {}
	while true:
		var cur := Vector2i(-9999, -9999)
		var cur_d: int = 0x3fffffff
		for k in dist.keys():
			if visited.has(k):
				continue
			var kd: int = int(dist[k])
			if kd < cur_d:
				cur_d = kd
				cur = k
		if cur_d == 0x3fffffff:
			break
		visited[cur] = true
		for d in [Vector2i(1,0), Vector2i(-1,0), Vector2i(0,1), Vector2i(0,-1)]:
			var n: Vector2i = cur + d
			if n.x < 0 or n.x >= GRID_COLS or n.y < 0 or n.y >= GRID_ROWS:
				continue
			if n in blocked:
				continue
			var step_cost: int = 1
			# Flieger (M6b) ueberqueren Stein/Baum/Mauer und ignorieren
			# Gelaende-Aufschlaege - besetzte Felder bleiben tabu.
			if _ob_map.has(n) and not flying:
				var kind: int = int(_ob_map[n])
				# 0=Stein, 1=Baumstamm, 4=Stadtmauer blocken; 2=Busch,
				# 3=Sumpf kosten doppelt. Kinds bewusst als Literale,
				# siehe Funktionskopf.
				if kind == 0 or kind == 1 or kind == 4:
					continue
				if kind == 2 or kind == 3:
					step_cost = 2
			var nd: int = cur_d + step_cost
			if not dist.has(n) or nd < int(dist[n]):
				dist[n] = nd
	return dist


func _bfs_for(start: Vector2i, blocked: Array, flying: bool = false) -> Dictionary:
	# Alter BFS-Alias -> delegiert jetzt auf Dijkstra, damit KI-
	# Pfadsuche dieselben Obstacle-Regeln wie der Spieler sieht.
	return _dijkstra_for(start, blocked, flying)


func _attack_cell_for(from: Vector2i, target_pos: Vector2i, dist_map: Dictionary, spd: int) -> Vector2i:
	# Liefert das naechstgelegene Nachbarfeld von target_pos, das innerhalb
	# der Bewegungsreichweite erreichbar ist. Wenn der Angreifer schon
	# adjacent steht, bleibt er stehen. Rueckgabe (-1,-1) = nicht erreichbar.
	if _adj(from, target_pos):
		return from
	var best := Vector2i(-1, -1)
	var best_d: int = 9999
	for d in [Vector2i(1,0), Vector2i(-1,0), Vector2i(0,1), Vector2i(0,-1)]:
		var n: Vector2i = target_pos + d
		if not dist_map.has(n): continue
		var nd: int = int(dist_map[n])
		if nd <= spd and nd < best_d:
			best_d = nd
			best = n
	return best


func _dmg(attacker: Dictionary, defender: Dictionary, melee_penalty: bool) -> int:
	var a_bonus: int = _player_bonus if int(attacker["side"]) == 0 else 0
	var d_bonus: int = _player_bonus if int(defender["side"]) == 0 else 0
	# Belagerung: die Stadt-Seite (1) steht hinter der Mauer und ist
	# schwerer zu treffen, solange kein Segment gefallen ist.
	if _siege and int(defender["side"]) == 1 and _walls_standing():
		d_bonus += SIEGE_DEF_BONUS
	# tiles_moved speist den Jousting-Bonus (Kavalier/Wolfsreiter).
	var opts: Dictionary = {"tiles_moved": int(attacker.get("tiles_moved", 0))}
	var dmg: int = CombatMath.damage(attacker, defender, melee_penalty, a_bonus, d_bonus, _rng, opts)
	# Glueck wirkt auf den einzelnen Schlag (M6): Volltreffer x2, Pech x0.5.
	var luck: int = _p_luck if int(attacker["side"]) == 0 else _e_luck
	_last_luck = 1.0
	if luck != 0:
		_last_luck = Mor.luck_factor(luck, _rng)
		if _last_luck != 1.0:
			dmg = max(1, int(float(dmg) * _last_luck))
	return dmg


# Log-Zusatz zum letzten Glueckswurf ("" wenn normal).
func _luck_suffix() -> String:
	if _last_luck > 1.0:
		return "  Volltreffer!"
	if _last_luck < 1.0:
		return "  Pech"
	return ""


func _apply_dmg(stack: Dictionary, dmg: int) -> int:
	return CombatMath.apply(stack, dmg)


func _check_end() -> bool:
	if _finished: return true
	var p_alive := false
	for s in _p_stacks:
		if int(s["count"]) > 0: p_alive = true; break
	var e_alive := false
	for s in _e_stacks:
		if int(s["count"]) > 0: e_alive = true; break
	if p_alive and e_alive: return false
	_finished = true
	var cas: Dictionary = {}
	for s in _p_stacks:
		var uid: String = String(s["type"])
		var lost: int = int(s.get("count_start", 0)) - int(s["count"])
		if lost > 0: cas[uid] = int(cas.get(uid, 0)) + lost
	if not p_alive:
		battle_finished.emit({"outcome": "defeat", "casualties": cas})
	else:
		battle_finished.emit({"outcome": "victory", "casualties": cas})
	return true


func _on_wait() -> void:
	if _finished: return
	if _turn_order.is_empty() or _active_slot >= _turn_order.size(): return
	if int(_turn_order[_active_slot]["side"]) != 0: return
	var active: Dictionary = _active_stack()
	if active.is_empty(): return
	if bool(active.get("waited", false)):
		# Doppelwarten nicht erlaubt (HoMM-Konvention): stattdessen Zug
		# einfach aussetzen, damit der Spieler weiterkommt.
		_set_action("Held %s pausiert." % UnitType.short_of(String(active["type"])))
		if _check_end(): return
		_advance()
		return
	active["waited"] = true
	_set_action("Held %s wartet -> zieht spaeter." % UnitType.short_of(String(active["type"])))
	_rebuild_order()
	if _check_end(): return
	# Kein _advance: rebuild hat den Warter ans Ende geschoben, der neue
	# Stack auf _active_slot ist der naechste Handler.
	_step()


func _on_flee() -> void:
	if _finished or not _allow_flee: return
	_finished = true
	battle_finished.emit({"outcome": "flee", "casualties": {}})
