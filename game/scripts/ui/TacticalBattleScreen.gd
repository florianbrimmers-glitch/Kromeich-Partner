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
# Effekt-Schicht (It. 17). Alias Vfx, weil Fx oben schon StatusFx ist.
const Vfx := preload("res://scripts/core/BattleVfx.gd")
# Zauber (M8). Wie HeroSkills eine reine Datenschicht: sie loest die
# Formeln aus spells.json in Zahlen auf, der Screen wirkt sie nur.
const Spl := preload("res://scripts/core/HeroSpells.gd")
# Geraeusche (M11) ueber die statische Fassade - der Sfx-Autoload
# fehlt bei "godot --script tools/x.gd", ein direkter Aufruf wuerde
# dort zur Laufzeit scheitern und die Testfunktion abbrechen.
const Sound := preload("res://scripts/core/SfxBus.gd")
# Kreatur-Sprites (It. 29). Gleiche preload-Begruendung wie oben.
const UnitArt := preload("res://scripts/core/UnitArt.gd")

# Gitter (It. 49: 10 -> 8 Spalten). Gemessen war eine Zelle auf dem
# 1080er Geraet 104 px breit, also rund 6,6 mm - die uebliche Empfehlung
# fuer Tippziele liegt bei etwa 9 mm. Mit 8 Spalten sind es 130 px
# (8,3 mm). Die Zellgroesse rechnet `_geom()` aus der Flaeche, sie musste
# nirgends nachgezogen werden; dasselbe gilt fuer die Token-Faktoren aus
# It. 36, die alle relativ zur Zelle sind.
const GRID_COLS := 8
const GRID_ROWS := 8

# Startreihen: Spieler auf Spalte 1, Gegner auf GRID_COLS - 2. Der Abstand
# dazwischen ist das Mass, an dem die Tempo-Werte haengen.
const START_GAP := GRID_COLS - 3
# Auf DIESEN Abstand sind die `speed`-Werte in units.json getunt (das alte
# Gitter mit 10 Spalten). Steht START_GAP gleich TUNED_GAP, ist die
# Skalierung unten wirkungslos - die Zahl luegt also nicht, wenn jemand
# das Gitter zurueckdreht.
const TUNED_GAP := 7

# --- Token-Groesse (It. 36) ------------------------------------------------
# In der komponierten Ansicht bei echter Geraetegroesse (Zelle 104 px) waren
# die Kreaturen verloren: die Scheibe nahm 0.40 der Zelle ein, das Sprite
# 0.92 - und weil die Figur im SVG nur rund 85 % der Bildhoehe fuellt, kam
# eine Figur von etwa 45 px auf einer 104-px-Zelle heraus. Auf dem Handy
# sind das keine Kreaturen, sondern Spielsteine.
#
# Jetzt fuellt das Sprite die Zelle ganz und ragt bewusst leicht darueber
# hinaus (HoMM3 macht es genauso: grosse Kreaturen ueberlappen ihr Feld).
# LIFT hebt die Figur, damit ihre Fuesse auf der Scheibe stehen statt in
# der Zellmitte zu schweben.
# Als Konstanten, weil tools/preview_battle_full.gd sie AUSLIEST - eine
# Kopie im Vorschau-Werkzeug waere die naechste Stelle, die auseinanderlaeuft.
const TOKEN_DISC_FRAC := 0.44
const TOKEN_SPRITE_FRAC := 1.14
const TOKEN_SPRITE_LIFT := 0.10

# --- Effekte (It. 17) -----------------------------------------------------
# Queue mit laufenden Effekten. Die Zugkette wartet, solange ein
# blockierender Effekt lebt (siehe _advance).
var _fx: Array = []
# Tempo-Regler. 0.0 = alles sofort fertig -> die Kette laeuft wie vor
# It. 17 durch. TESTS SETZEN DAS AUF 0.0 (siehe test_battle/test_siege),
# sonst warten sie auf Animationen, die headless nie ankommen.
var fx_speed: float = 1.0
# Farben fuer Schadenszahlen: die Seite, die EINSTECKT, bestimmt die Farbe.
const FX_COL_PLAYER_HURT := Color(1.0, 0.55, 0.45)
const FX_COL_ENEMY_HURT := Color(1.0, 0.94, 0.72)
# Verzoegerung, mit der _apply_dmg seine Treffer-Effekte startet. Der
# Angriffs-Pfad setzt sie auf die Flugzeit des Geschosses bzw. auf den
# Scheitel des Ausfallschritts und danach zurueck auf 0. So bleibt
# _apply_dmg der einzige Trichter, ohne dass der Einschlag zu frueh kommt.
var _fx_delay: float = 0.0

var _player_name: String = "Held"
var _enemy_name: String = "Gegner"
var _player_bonus: int = 0
# M7: getrennte Helden-Boni. Vorher fuellte _player_bonus beide Seiten der
# Formel, ein Angriffsbonus hob also auch die Verteidigung.
var _p_att: int = 0
var _p_def: int = 0
# Skill-Prozente, fertig gerechnet vom Weltkarten-Screen. Der Kampf kennt
# keine Skills, nur Zahlen.
var _p_archery_pct: int = 0
var _p_offense_pct: int = 0
var _p_armorer_pct: int = 0

# --- Zauber (M8) ---------------------------------------------------------
# Der Weltkarten-Screen gibt Mana, Zauberkraft und die Liste der wirkbaren
# Zauber mit; der Kampf gibt das verbrauchte Mana im Ergebnis zurueck.
var _p_mana: int = 0
var _p_power: int = 0
var _p_spells: Array = []
# Ein Zauber pro Runde (HoMM3-Regel). Zaehler statt Bool, damit spaetere
# Artefakte mehr erlauben koennen, ohne die Logik umzubauen.
var _casts_left: int = 0
# Gewaehlter Zauber, wartet auf das Ziel-Tippen. Leer = kein Zielmodus.
var _pending_spell: String = ""
var _spell_btn: Button = null
var _spell_panel: Panel = null
# Untere Knopfreihe (It. 42). Vier Plaetze: Warten, Zauber, Fliehen,
# Kapitulieren. BTN_TOP/BOTTOM sind Offsets vom UNTEREN Rand, deshalb
# negativ; die Reihe liegt damit in dem Band, das _grid_area unten frei
# laesst (offset_bottom -310).
const BTN_SLOTS := 4

# Raeumliche Ansicht (It. 55). ZWEITE ANSICHT, KEIN ERSATZ - wie bei der
# Weltkarte in It. 53b. Sie sitzt als SubViewport IN der Gitterflaeche und
# liest dasselbe Modell ueber _field3d_ctx(); Kampfmathematik,
# Zugreihenfolge und Balance sind davon nicht beruehrt.
const Field3D := preload("res://scripts/ui/BattleField3D.gd")

var _view3d_btn: Button
var _field3d = null
var _field3d_vp: SubViewport = null
var _field3d_on: bool = false
const BTN_PAD := 14.0
const BTN_TOP := -170.0
const BTN_BOTTOM := -50.0
const BTN_FONT := 28

var _allow_flee: bool = true
# Kapitulieren: Gold gegen die eigene Armee (HoMM3-Regel). Preis und
# Erlaubnis kommen von aussen - der Kampf-Screen kennt keinen Geldbeutel.
var _allow_surrender: bool = false
var _surrender_cost: int = 0
var _surrender_btn: Button = null
var _rng: RandomNumberGenerator
var _art_seed: int = 42
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
# Zaehler fuer uebersprungene Zuege, getrennt nach Ursache. Bewusst
# Zaehler und kein "letzter Wert": ein Zug-Ueberspringen loest sofort die
# naechste Aktion aus, ein Einzelwert waere im selben Aufruf schon wieder
# ueberschrieben - und das 3-zeilige Kampf-Log verliert die Meldung
# ebenfalls. Die Tests messen damit Differenzen.
var _skips_status: int = 0
var _skips_moral: int = 0
# Belagerung (M9). _siege = Mauer steht auf dem Feld; _wall_hp haelt die
# Restpunkte je Segment-Position. Verteidiger ist immer Seite 1 (die
# Stadt), Angreifer der Spieler - KI-Angriffe auf eigene Staedte laufen
# weiter ueber die Auto-Abrechnung im WorldMapScreen.
const SIEGE_DEF_BONUS := 2
var _siege: bool = false
var _wall_hp: Dictionary = {}
var _tower_dmg: int = 0

# --- Taktik (M7 Teil 2) --------------------------------------------------
# Aufstellungsphase VOR der ersten Runde: der Spieler darf seine Stacks
# innerhalb der ersten Spalten frei umstellen. Der Skill liefert die Zahl
# der Spalten (1-3); ohne Skill gibt es die Phase nicht.
#
# WARUM EINE EIGENE PHASE und kein Vorab-Sortieren: die Reihenfolge der
# Stacks bestimmt bisher allein _row(), also stehen Schuetzen zufaellig
# vorn. Genau das soll der Spieler entscheiden koennen - und zwar sehend,
# mit dem Gelaende und der Gegneraufstellung vor Augen.
const TACTICS_FIRST_COL := 1
var _tactics_cols: int = 0
var _tactics_phase: bool = false
var _tactics_pick: int = -1
var _tactics_btn: Button = null

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
const LOG_LINES := 3
var _log: Array = []


func set_battle(ctx: Dictionary) -> void:
	_player_name = String(ctx.get("player_name", "Held"))
	_enemy_name  = String(ctx.get("enemy_name",  "Gegner"))
	_player_bonus = int(ctx.get("player_bonus", 0))
	_p_att = int(ctx.get("player_att", _player_bonus))
	_p_def = int(ctx.get("player_def", _player_bonus))
	_p_archery_pct = int(ctx.get("player_archery_pct", 0))
	_p_offense_pct = int(ctx.get("player_offense_pct", 0))
	_p_armorer_pct = int(ctx.get("player_armorer_pct", 0))
	_p_mana = int(ctx.get("player_mana", 0))
	_p_power = int(ctx.get("player_spell_power", 0))
	_p_spells = (ctx.get("player_spells", []) as Array).duplicate()
	_casts_left = Spl.CASTS_PER_ROUND
	_pending_spell = ""
	# Die Aufstellungszone bleibt in der EIGENEN Haelfte. Die alte Schranke
	# GRID_COLS - 4 war auf dem 10er-Brett gutmuetig (Zone bis Spalte 4,
	# Gegner auf 8); auf dem 8er haette sie bis Spalte 5 gereicht, mit dem
	# Gegner auf 6 - Taktik III haette den Kampf in Runde 1 erzwungen.
	_tactics_cols = clampi(int(ctx.get("player_tactics", 0)), 0, GRID_COLS / 2 - 2)
	_tactics_pick = -1
	_allow_flee  = bool(ctx.get("allow_flee", true))
	_allow_surrender = bool(ctx.get("allow_surrender", false))
	_surrender_cost = int(ctx.get("surrender_cost", 0))
	_rng = RandomNumberGenerator.new()
	_rng.seed = int(ctx.get("seed", 42))
	# Eigene Kopie fuer die Boden-Varianten: das Zeichnen darf _rng NICHT
	# anfassen, sonst verschieben sich die Kampfwuerfel.
	_art_seed = int(ctx.get("seed", 42))
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
	# Fuehrung (M7) addiert auf die Armee-Moral; Clamp wie in Morale.gd,
	# sonst koennte der Skill den +-3-Rahmen sprengen.
	_p_morale = clampi(Mor.morale_for(_p_stacks)
		+ int(ctx.get("player_morale_bonus", 0)), -3, 3)
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
	_refresh_surrender_button()
	_refresh_spell_button()
	_refresh()
	# Taktik zuerst: die Zugkette startet erst, wenn der Spieler fertig
	# aufgestellt hat.
	if _tactics_cols > 0 and not _p_stacks.is_empty():
		_begin_tactics()
	else:
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
	return "  Todeswolke: %d Nachbarn je %d Schaden, %s" % [hit, splash, _fallen(killed)]


# Ein Nahkampf-Angriff inkl. Konter und Lebensentzug. Rueckgabe: Text-
# Fragment fuer das Kampf-Log. Wird von Spieler- und KI-Pfad benutzt,
# damit beide Seiten exakt dieselben Ability-Regeln sehen.
func _melee_exchange(attacker: Dictionary, target: Dictionary) -> String:
	var a_uid: String = String(attacker["type"])
	var t_uid: String = String(target["type"])
	# Ausfallschritt hier und nicht an den drei Aufrufstellen: derselbe
	# Trichter-Gedanke wie bei _apply_dmg. Der Treffer landet auf dem
	# Scheitel der Bewegung.
	var a_pos: Vector2i = Vector2i(attacker["pos"])
	var t_pos: Vector2i = Vector2i(target["pos"])
	# Laeuft noch ein Anmarsch? Dann erst danach zuschlagen.
	var march: float = Vfx.time_left_of(_fx, Vfx.MOVE)
	Vfx.spawn(_fx, Vfx.LUNGE, {"from": a_pos, "to": t_pos, "delay": march})
	Sound.play("melee_hit")
	_fx_delay = march + Vfx.lunge_delay()
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
				t_uid, a_uid, int(target.get("retaliations", 0)),
				Fx.extra_retaliations(target)):
			target["retaliations"] = int(target.get("retaliations", 0)) + 1
			target["retaliated"] = true
			var rdmg: int = max(1, _dmg(target, attacker, UnitType.is_ranged(t_uid)) / 2)
			counter_dmg += rdmg
			# Der Konter kommt NACH dem Treffer, sonst liegen beide Zahlen
			# im selben Frame uebereinander.
			var back_delay: float = _fx_delay
			_fx_delay = back_delay + Vfx.DUR[Vfx.IMPACT]
			Vfx.spawn(_fx, Vfx.LUNGE, {"from": t_pos, "to": a_pos,
				"delay": back_delay + Vfx.DUR[Vfx.IMPACT] - Vfx.lunge_delay()})
			counter_kill += _apply_dmg(attacker, rdmg)
			_fx_delay = back_delay
	_fx_delay = 0.0
	var msg: String = "%d Schaden, %s" % [dmg_sum, _fallen(killed)]
	if struck > 1:
		msg = "%d Angriffe, %s" % [struck, msg]
	msg += status_txt
	if woke:
		msg += "  (geweckt)"
	if counter_dmg > 0:
		msg += " - Konter: %d Schaden, %s" % [counter_dmg, _fallen(counter_kill)]
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


# --- Taktik-Phase ---------------------------------------------------------

# Erlaubte Spalten: TACTICS_FIRST_COL bis einschliesslich
# TACTICS_FIRST_COL + Stufe. Stufe 1 gibt also zwei Spalten (umstellen und
# eine nach vorn), Stufe 3 vier. Die Mitte des Feldes bleibt in jedem Fall
# tabu - clampi in set_battle haelt die Zone von der Gegnerseite weg.
func _tactics_allows(cell: Vector2i) -> bool:
	if cell.y < 0 or cell.y >= GRID_ROWS:
		return false
	return cell.x >= TACTICS_FIRST_COL and cell.x <= TACTICS_FIRST_COL + _tactics_cols


func _begin_tactics() -> void:
	_tactics_phase = true
	_tactics_pick = -1
	if _tactics_btn != null:
		_tactics_btn.visible = true
	# Die Kampf-Knoepfe haben in der Aufstellung keine Bedeutung.
	if _wait_btn != null:
		_wait_btn.visible = false
	if _flee_btn != null:
		_flee_btn.visible = false
	if _surrender_btn != null:
		_surrender_btn.visible = false
	if _spell_btn != null:
		_spell_btn.visible = false
	_set_action("Taktik: Stack antippen, dann Zielfeld (%d Spalten)."
		% (_tactics_cols + 1))
	_refresh()


func _end_tactics() -> void:
	if not _tactics_phase:
		return
	_tactics_phase = false
	_tactics_pick = -1
	if _tactics_btn != null:
		_tactics_btn.visible = false
	if _wait_btn != null:
		_wait_btn.visible = true
	if _flee_btn != null:
		_flee_btn.visible = _allow_flee
	_refresh_surrender_button()
	_refresh_spell_button()
	_set_action("Aufstellung steht.")
	# Reihenfolge neu, damit ein leer gelaufener Slot nicht haengt; die
	# Positionen haben die Initiative nicht veraendert, aber das ist die
	# einzige Stelle, die _turn_order und _active_slot konsistent setzt.
	_rebuild_order()
	_active_slot = 0
	_refresh()
	_step()


# Ein Tap waehrend der Aufstellung. Erst Stack waehlen, dann Zielfeld.
func _tactics_tap(cell: Vector2i) -> void:
	for i in range(_p_stacks.size()):
		var s: Dictionary = _p_stacks[i]
		if int(s["count"]) <= 0:
			continue
		if Vector2i(s["pos"]) == cell:
			_tactics_pick = i
			_set_action("%s gewaehlt - Zielfeld antippen."
				% UnitType.name_of(String(s["type"])))
			_refresh()
			return
	if _tactics_pick < 0:
		_set_action("Taktik: zuerst einen eigenen Stack antippen.")
		return
	if not _tactics_allows(cell):
		_set_action("Taktik: nur die ersten %d Spalten." % (_tactics_cols + 1))
		return
	if _ob_map.has(cell):
		_set_action("Taktik: Feld ist blockiert.")
		return
	for s2 in _e_stacks:
		if int(s2["count"]) > 0 and Vector2i(s2["pos"]) == cell:
			_set_action("Taktik: Feld ist besetzt.")
			return
	_p_stacks[_tactics_pick]["pos"] = cell
	_tactics_pick = -1
	_refresh()


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
		_skips_status += 1
		Vfx.popup(_fx, Vector2i(st["pos"]), Fx.marker_name(st),
			Color(0.75, 0.70, 1.0))
		_set_action("%s %s ist %s und setzt aus." % [
			who, UnitType.name_of(String(st["type"])), Fx.marker_name(st)])
		_advance()
		return
	# Schlechte Moral kann den Zug kosten (M6). Untote sind immun.
	if not st.is_empty() and not Mor.immune_to_bad_morale(String(st["type"])):
		var mor: int = _p_morale if int(slot["side"]) == 0 else _e_morale
		if Mor.rolls_freeze(mor, _rng):
			var who2: String = "Held" if int(slot["side"]) == 0 else "Feind"
			_skips_moral += 1
			Vfx.popup(_fx, Vector2i(st["pos"]), "Moral!", Color(1.0, 0.55, 0.45))
			_set_action("%s %s hat schlechte Moral und setzt aus." % [
				who2, UnitType.name_of(String(st["type"]))])
			_advance()
			return
	if int(slot["side"]) == 0:
		_build_reachable()
		_refresh()
	else:
		_ai_turn()


func _next_round() -> void:
	if _finished:
		return
	_round += 1
	# Neue Runde, neuer Zauber (HoMM3-Regel).
	_casts_left = Spl.CASTS_PER_ROUND
	_pending_spell = ""
	_refresh_spell_button()
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
	Vfx.wall_break(_fx, pos)
	Sound.play("wall_break")
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
	# Steinkugel von ausserhalb des Feldes, hoher Bogen. Das Katapult
	# selbst steht nicht auf dem Gitter - Startfeld links vor der Reihe.
	var from := Vector2i(-1, best.y)
	var flight: float = Vfx.shot(_fx, from, best, true)
	Sound.play("catapult")
	_fx_delay = flight
	var res: String = _damage_wall(best, 1)
	if res == "":
		Vfx.spawn(_fx, Vfx.SHAKE, {"amp": 4.0, "delay": flight})
	_fx_delay = 0.0
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
	# Der Turm steht hinter der Mauer, also rechts ausserhalb des Gitters.
	var tpos: Vector2i = Vector2i(target["pos"])
	_fx_delay = Vfx.shot(_fx, Vector2i(GRID_COLS, tpos.y), tpos)
	var killed: int = _apply_dmg(target, _tower_dmg)
	_fx_delay = 0.0
	_set_action("Pfeilturm trifft %s: %d Schaden, %s" % [
		UnitType.name_of(String(target["type"])), _tower_dmg, _fallen(killed)])


# Rundenstart-Regeneration (Baumvater heilt immer, Gespenst nur
# angeschlagen). Heilt die vorderste Einheit, keine Wiederbelebung.
func _regenerate(stack: Dictionary) -> void:
	if int(stack["count"]) <= 0:
		return
	var uid: String = String(stack["type"])
	var hp_max: int = UnitType.hp_of(uid)
	var gain: int = Abil.regen_hp(uid, int(stack["top_hp"]), hp_max)
	if gain > 0:
		var before: int = int(stack["top_hp"])
		stack["top_hp"] = min(hp_max, int(stack["top_hp"]) + gain)
		Vfx.healed(_fx, Vector2i(stack["pos"]), int(stack["top_hp"]) - before)


# Zugkette. Vor It. 17 lief sie mit einer Pauschal-Pause von 0.30 s vor
# KI-Zuegen durch; Animationen waeren unsichtbar geblieben, weil der
# naechste Zug losrennt, bevor der Treffer gezeichnet ist. Jetzt wartet
# die Kette, bis alle blockierenden Effekte abgelaufen sind, und legt vor
# KI-Zuegen zusaetzlich die Mindestpause ein.
func _advance() -> void:
	_active_slot += 1
	if _active_slot >= _turn_order.size():
		_wait_for_fx(_next_round)
		return
	var next_side: int = int(_turn_order[_active_slot]["side"])
	if next_side == 1:
		_wait_for_fx(_step, AI_TURN_PAUSE)
	else:
		_wait_for_fx(_step)


const AI_TURN_PAUSE := 0.30


# Ruft `fn` auf, sobald die Effekt-Queue frei ist (plus optionale
# Mindestpause). Bei fx_speed <= 0 - also in den Tests - laeuft es
# synchron durch, genau wie vor It. 17.
func _wait_for_fx(fn: Callable, extra: float = 0.0) -> void:
	# Nach Kampfende nichts mehr planen: das Overlay wird vom Aufrufer
	# freigegeben, ein noch wartender Aufruf wuerde auf eine tote Instanz
	# zeigen.
	if _finished:
		return
	if fx_speed <= 0.0:
		# Synchron durch - so verspricht es der Kommentar oben, und so war
		# es fuer `extra` bis It. 38 NICHT: dort lag ein 0.3-s-Timer.
		Vfx.advance(_fx, 1.0, 0.0)
		fn.call()
		return
	# EINE Uhr fuer die ganze Kette (It. 38). Vorher haing die Wartezeit an
	# get_tree().create_timer() - einer zweiten Uhr, die fx_speed ignoriert.
	# Zwei Folgen: bei einem "schnellen Kampf" (fx_speed > 1) haette die
	# KI-Pause nicht mitskaliert, und headless (wo keine Echtzeit laeuft)
	# feuerte der Timer nie - der Kampf stand still, mit dem Gegner am Zug
	# und ohne laufenden Effekt. Genau so sah der scheinbare Patt aus, den
	# der Durchspiel-Test gemeldet hat.
	if extra > 0.0:
		Vfx.pause(_fx, extra)
	if Vfx.busy_time_left(_fx) <= 0.0:
		fn.call()
		return
	_pending_fn = fn


# Naechster Schritt der Zugkette, sobald die Effekt-Queue frei ist.
# Ersetzt den frueheren SceneTree-Timer (It. 38).
var _pending_fn: Callable = Callable()


func _process(delta: float) -> void:
	if not _fx.is_empty():
		if Vfx.advance(_fx, delta, fx_speed) and _grid_area != null:
			_grid_area.queue_redraw()
	if _pending_fn.is_valid() and Vfx.busy_time_left(_fx) <= 0.0:
		var fn: Callable = _pending_fn
		# ZUERST leeren, DANN aufrufen: fn setzt gleich den naechsten
		# Wartezustand, und der duerfte sonst wieder ueberschrieben werden.
		_pending_fn = Callable()
		if not _finished:
			fn.call()


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
	# M8: Beschleunigen/Verlangsamen aendern die Reichweite. Minimum 1,
	# sonst kann ein Stack durch Verlangsamen komplett festkleben.
	var spd: int = _reach_of(UnitType.speed_of(String(st["type"])) + Fx.spd_mod(st))
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


# Reichweite eines Stacks in FELDERN. `speed` aus units.json ist auf ein
# Brett mit TUNED_GAP Spalten Abstand getunt; auf einem schmaleren muss
# die Reichweite mitschrumpfen.
#
# WARUM NUR DIE REICHWEITE UND NICHT `speed` SELBST (It. 49): `speed`
# steuert ZWEI Dinge - wie weit ein Stack zieht (hier) und wer zuerst am
# Zug ist (`_rebuild_order`). Skaliert man den Wert selbst, faellt auch
# die Zugreihenfolge groeber: mit Faktor 0,71 landen Tempo 5 und 6 beide
# auf 4, ebenso 8 und 9 auf 6 - zehn Einheiten verlieren ihren Rang.
# Gemessen ist beides gleich gut (vier Fernkampf-gegen-Nahkampf-Paarungen,
# je 16 Kaempfe, beide Sichten: 0.25 / 0.94 / 0.19 / 0.81 gegen die
# 10-Spalten-Basis 0.25 / 0.94 / 0.19 / 0.75). Bei gleichem Ergebnis
# gewinnt der Eingriff, der weniger anfasst.
#
# OHNE diese Skalierung verliert der Fernkampf massiv: dieselben vier
# Paarungen kamen auf 0.00 / 0.56 / 0.06 / 0.38 - im Mittel 0,28 weniger.
# Auf dem kurzen Brett sind die Nahkaempfer eine Runde frueher da.
func _reach_of(base: int) -> int:
	if START_GAP >= TUNED_GAP:
		return maxi(1, base)
	# DIE REGEL: proportional skalieren - aber NIE frueher am Gegner sein
	# als auf dem getunten Brett.
	#
	# Reines Runden und reines Abrunden treffen beide nur die Haelfte der
	# Tempo-Stufen, weil ganze Felder auf einem kurzen Brett grob sind:
	#   Tempo 4 (anteilig 2,86): abgerundet 2 ist 30 % zu langsam - der
	#     Fernkampf gewann in der Messung 0,19 mehr als vorher.
	#   Tempo 5 (anteilig 3,57): gerundet 4 schafft die vier Felder in
	#     EINEM Zug statt in zwei - der Nahkampf ist eine Runde zu frueh
	#     da. Genau das hat test_hero_skills gemeldet (6 Goblins gegen 20
	#     Schuetzen, drei starben am Konter, bevor der Test zu zaehlen
	#     anfing).
	# Also runden UND die Rundenzahl als Schranke: was zaehlt, ist der Weg
	# bis auf EIN Feld an den Gegner (Luecke - 1), denn geschlagen wird aus
	# dem Nachbarfeld.
	var reach: int = maxi(1, int(round(
		float(base) * float(START_GAP) / float(TUNED_GAP))))
	var tuned_turns: int = _turns_to_contact(TUNED_GAP, maxi(1, base))
	while reach > 1 and _turns_to_contact(START_GAP, reach) < tuned_turns:
		reach -= 1
	return reach


# Zuege, bis ein Stack mit dieser Reichweite aus einer Luecke von `gap`
# Spalten heraus zuschlagen kann.
func _turns_to_contact(gap: int, reach: int) -> int:
	return int(ceil(float(maxi(1, gap - 1)) / float(maxi(1, reach))))


# "keine Verluste" / "1 gefallen" / "3 gefallen". Der Satzbau steht an
# EINER Stelle, sonst schreibt ihn jede der acht Meldungen anders (It. 50).
func _fallen(n: int) -> String:
	if n <= 0:
		return "keine Verluste"
	if n == 1:
		return "1 gefallen"
	return "%d gefallen" % n


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

	# Kopfzeile schlank halten: Titel und Info in einer Zeile. Frueher
	# frassen Titel (70 px), Info (70 px) und ein 5-zeiliges Log (140 px)
	# zusammen 330 px, waehrend unter dem Gitter Platz frei blieb.
	var title := Label.new()
	title.text = "KAMPF"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.set_anchors_preset(Control.PRESET_TOP_WIDE)
	title.offset_top = 20.0
	title.offset_bottom = 70.0
	title.add_theme_font_size_override("font_size", 36)
	title.add_theme_color_override("font_color", Color(0.95, 0.85, 0.40))
	add_child(title)

	_info_lbl = Label.new()
	_info_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_info_lbl.set_anchors_preset(Control.PRESET_TOP_WIDE)
	_info_lbl.offset_top = 68.0
	_info_lbl.offset_bottom = 118.0
	_info_lbl.add_theme_font_size_override("font_size", 26)
	_info_lbl.add_theme_color_override("font_color", Color(0.9, 0.92, 0.96))
	add_child(_info_lbl)

	# Kampf-Log UNTER das Gitter, in die frueher leere Zone ueber den
	# Buttons. Drei Zeilen reichen fuer den Verlauf einer Runde.
	_action_lbl = Label.new()
	_action_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	_action_lbl.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	_action_lbl.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_action_lbl.offset_left = 40.0
	_action_lbl.offset_right = -40.0
	_action_lbl.offset_top = -300.0
	_action_lbl.offset_bottom = -180.0
	# Umbruch statt Abschneiden: mit vollen Kreaturennamen wird die
	# laengste Meldung ("Schwarzritter rueckt vor und greift
	# Schwarzritter an: ... - Konter: ...") 1158 px lang, die Zeile ist
	# 1000 breit (It. 50).
	_action_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_action_lbl.add_theme_font_size_override("font_size", 22)
	_action_lbl.add_theme_color_override("font_color", Color(0.80, 0.88, 1.0))
	add_child(_action_lbl)

	# Umschalter 2D/3D (It. 55). OBEN RECHTS, nicht in der Knopfreihe:
	# die hat vier Plaetze, und ein fuenfter haette jeden Knopf auf 188 px
	# gebracht - "Kapitulieren" passt da bei Schriftgroesse 28 nicht mehr
	# hinein. Dieselbe Lehre wie It. 53b, wo derselbe Knopf der Statuszeile
	# der Weltkarte die halbe Breite genommen hat.
	_view3d_btn = Button.new()
	_view3d_btn.text = "3D"
	_view3d_btn.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	_view3d_btn.offset_left = -120.0
	_view3d_btn.offset_right = -20.0
	_view3d_btn.offset_top = 16.0
	_view3d_btn.offset_bottom = 74.0
	_view3d_btn.add_theme_font_size_override("font_size", 24)
	_view3d_btn.pressed.connect(_toggle_view3d)
	add_child(_view3d_btn)

	_grid_area = Control.new()
	_grid_area.set_anchors_preset(Control.PRESET_FULL_RECT)
	_grid_area.offset_left = 20.0
	_grid_area.offset_right = -20.0
	_grid_area.offset_top = 125.0
	_grid_area.offset_bottom = -310.0
	_grid_area.mouse_filter = Control.MOUSE_FILTER_STOP
	_grid_area.draw.connect(_draw_grid)
	_grid_area.resized.connect(func(): _grid_area.queue_redraw())
	_grid_area.gui_input.connect(_on_grid_input)
	add_child(_grid_area)

	_wait_btn = Button.new()
	_wait_btn.text = "Warten"
	_wait_btn.add_theme_font_size_override("font_size", BTN_FONT)
	_wait_btn.pressed.connect(_on_wait)
	_place_btn(_wait_btn, 0)
	add_child(_wait_btn)

	_spell_btn = Button.new()
	_spell_btn.text = "Zauber"
	_spell_btn.add_theme_font_size_override("font_size", BTN_FONT)
	_spell_btn.pressed.connect(_on_spell_button)
	_place_btn(_spell_btn, 1)
	add_child(_spell_btn)

	_flee_btn = Button.new()
	_flee_btn.text = "Fliehen"
	_flee_btn.add_theme_font_size_override("font_size", BTN_FONT)
	_flee_btn.pressed.connect(_on_flee)
	_place_btn(_flee_btn, 2)
	add_child(_flee_btn)

	# Kapitulieren (It. 42): Gold gegen die eigene Armee. Der Preis steht
	# auf dem Knopf, sonst ist es ein Blindkauf.
	_surrender_btn = Button.new()
	_surrender_btn.text = "Kapitulieren"
	_surrender_btn.add_theme_font_size_override("font_size", BTN_FONT)
	_surrender_btn.pressed.connect(_on_surrender)
	_place_btn(_surrender_btn, 3)
	add_child(_surrender_btn)

	# "Kampf beginnen" liegt allein in derselben Reihe (die vier oben sind
	# in der Aufstellungsphase unsichtbar) und darf deshalb die ganze
	# Breite haben.
	_tactics_btn = Button.new()
	_tactics_btn.text = "Kampf beginnen"
	_tactics_btn.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_tactics_btn.offset_left = BTN_PAD
	_tactics_btn.offset_right = -BTN_PAD
	_tactics_btn.offset_top = BTN_TOP
	_tactics_btn.offset_bottom = BTN_BOTTOM
	_tactics_btn.add_theme_font_size_override("font_size", 38)
	_tactics_btn.visible = false
	_tactics_btn.pressed.connect(_end_tactics)
	add_child(_tactics_btn)


# Ein Platz von BTN_SLOTS in der unteren Knopfreihe, ueber BRUCH-ANKER -
# damit haengt die Reihe an KEINER Bildschirmzahl und teilt sich auf jedem
# Geraet gleich auf.
#
# Vorher hatte jeder der vier Knoepfe eigene Offsets in Pixeln, und genau
# daran lagen "Zauber" (500-624) und "Fliehen" (600-1030) auf dem Geraet 24
# Pixel uebereinander: der spaeter eingehaengte Fliehen-Knopf hat in der
# Ueberdeckung den Tap gefressen. Gefunden durch MESSEN, nicht durch
# Hinsehen (It. 42) - deshalb prueft test_battle die Reihe jetzt.
func _place_btn(btn: Button, slot: int) -> void:
	btn.anchor_top = 1.0
	btn.anchor_bottom = 1.0
	btn.anchor_left = float(slot) / float(BTN_SLOTS)
	btn.anchor_right = float(slot + 1) / float(BTN_SLOTS)
	btn.offset_left = BTN_PAD
	btn.offset_right = -BTN_PAD
	btn.offset_top = BTN_TOP
	btn.offset_bottom = BTN_BOTTOM


# --- Raeumliche Ansicht (It. 55) ------------------------------------------

func _toggle_view3d() -> void:
	_field3d_on = not _field3d_on
	if _field3d_on and _field3d == null:
		_build_field3d()
	if _field3d_vp != null:
		(_field3d_vp.get_parent() as Control).visible = _field3d_on
	if _view3d_btn != null:
		_view3d_btn.text = "2D" if _field3d_on else "3D"
	_field3d_apply()
	_grid_area.queue_redraw()


# Erst beim ersten Einschalten. Wer bei 2D bleibt, zahlt weder das glb noch
# einen zweiten Viewport.
func _build_field3d() -> void:
	if _grid_area == null:
		return
	var cont := SubViewportContainer.new()
	cont.stretch = true
	cont.set_anchors_preset(Control.PRESET_FULL_RECT)
	# DER TAP GEHOERT WEITER DER GITTERFLAECHE. Faengt der Container die
	# Eingabe ab, laeuft jeder Zug ins Leere - und zwar still.
	cont.mouse_filter = Control.MOUSE_FILTER_IGNORE
	# HINTER die eigene Zeichnung der Gitterflaeche. Ein Control zeichnet
	# erst sich selbst, dann seine Kinder - ohne das lagen die
	# Stapelgroessen UNTER dem 3D-Bild und waren einfach weg. Sichtbar war
	# davon nichts: das Brett sah vollstaendig aus, nur ohne Zahlen.
	cont.show_behind_parent = true
	_grid_area.add_child(cont)
	_field3d_vp = SubViewport.new()
	# Eigene 3D-Welt - siehe WorldMapScreen._build_map3d. Ohne das stand
	# das Kampfbrett auf der Weltkarte.
	_field3d_vp.own_world_3d = true
	_field3d_vp.transparent_bg = false
	_field3d_vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	cont.add_child(_field3d_vp)
	_field3d = Field3D.new()
	_field3d_vp.add_child(_field3d)


func _field3d_apply() -> void:
	if not _field3d_on or _field3d == null:
		return
	_field3d.refresh(_field3d_ctx())
	_field3d.frame_board(GRID_COLS, GRID_ROWS)
	# Ruetteln bei schweren Treffern: in 2D wandert der Zeichen-Ursprung,
	# in 3D der ganze Viewport. Nur die Effekte zu ruetteln und das Brett
	# stehen zu lassen saehe nach Fehler aus.
	var cont := _field3d_vp.get_parent() as Control
	if cont != null:
		cont.position = _shake_offset()


# Derselbe Zustand, den _draw_grid zeichnet - aus DENSELBEN Feldern. Eine
# eigene Ableitung waere eine zweite Wahrheit ueber dieselbe Runde.
func _field3d_ctx() -> Dictionary:
	var stacks: Array = []
	var active: Dictionary = _active_stack()
	var active_pos := Vector2i(-1, -1)
	if not active.is_empty():
		active_pos = Vector2i(active["pos"])
	for arr in [_p_stacks, _e_stacks]:
		for st in arr:
			var sd: Dictionary = st as Dictionary
			if int(sd["count"]) <= 0:
				continue
			var pos: Vector2i = Vector2i(sd["pos"])
			stacks.append({
				"pos": pos, "type": String(sd["type"]),
				"side": int(sd["side"]), "active": pos == active_pos,
				# Ausfallschritt und Gleiten in ZELLEN statt Pixeln: die
				# raeumliche Ansicht rechnet in Zellen, und dieselbe
				# Funktion liefert in 2D die Pixel dafuer.
				"offset": _stack_offset(pos, 1.0),
			})
	var obst: Array = []
	for ob in _obstacles:
		var od: Dictionary = ob as Dictionary
		obst.append({
			"pos": Vector2i(od["pos"]), "kind": int(od["kind"]),
			"cracked": int(od.get("hp", 99)) <= 1,
		})
	# Laufziele und Angriffsziele wie in _draw_grid: das eigene Feld ist
	# kein Laufziel, und angreifbar ist ein Gegner, neben dem der aktive
	# Stapel steht oder stehen kann.
	var move: Array = []
	var own_turn: bool = not active.is_empty() \
		and int(_turn_order[_active_slot]["side"]) == 0
	if own_turn:
		for cell in _reachable.keys():
			if Vector2i(cell) != active_pos:
				move.append(Vector2i(cell))
	var targets: Array = []
	if own_turn:
		for s in _e_stacks:
			var es: Dictionary = s as Dictionary
			if int(es["count"]) <= 0:
				continue
			var ep: Vector2i = Vector2i(es["pos"])
			for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1),
					Vector2i(0, -1)]:
				if (ep + d) == active_pos or _reachable.has(ep + d):
					targets.append(ep)
					break
	# Aufstellungsphase: erlaubte Flaeche und der Stapel, den man gerade
	# umstellt. Dieselbe Bedingung wie das blaue Feld in _draw_grid - ohne
	# sie waere die Taktikphase in 3D nicht bedienbar.
	var zone: Array = []
	var picked := Vector2i(-1, -1)
	if _tactics_phase:
		for tx in range(TACTICS_FIRST_COL, TACTICS_FIRST_COL + _tactics_cols + 1):
			for ty in range(GRID_ROWS):
				zone.append(Vector2i(tx, ty))
		if _tactics_pick >= 0 and _tactics_pick < _p_stacks.size():
			picked = Vector2i(_p_stacks[_tactics_pick]["pos"])
	return {
		"cols": GRID_COLS, "rows": GRID_ROWS, "terrain": _terrain_id,
		"seed": _seed3d(), "stacks": stacks, "obstacles": obst,
		"move": move, "targets": targets, "zone": zone, "picked": picked,
	}


# Die Streuung der Hindernisse haengt am Gelaende, nicht an der Runde -
# sonst drehten sich die Steine bei jedem Zug.
func _seed3d() -> int:
	return _terrain_id * 977 + GRID_COLS * 31 + GRID_ROWS


func _geom() -> Array:
	var sz: Vector2 = _grid_area.size
	var cell: float = min(sz.x / float(GRID_COLS), sz.y / float(GRID_ROWS))
	var ox: float = (sz.x - cell * GRID_COLS) * 0.5
	var oy: float = (sz.y - cell * GRID_ROWS) * 0.5
	return [Vector2(ox, oy), cell]


# EIN Ort fuer "welche Zelle liegt unter diesem Bildpunkt". In 3D kann das
# keine Division sein: die Kamera steht schraeg, also wird ihr Strahl mit
# der Ebene y = 0 geschnitten (Scene3D.cell_at). Stuende die Umrechnung
# zweimal im Code, liefe sie beim naechsten Umbau auseinander - dieselbe
# Falle wie die nachgebaute Nachbarschaft im Durchspiel-Test (It. 42).
func _cell_at(p: Vector2) -> Vector2i:
	var cell: Vector2i
	if _field3d_on and _field3d != null:
		cell = _field3d.cell_at(p)
	else:
		var g: Array = _geom()
		var o: Vector2 = g[0]; var c: float = g[1]
		if c <= 0.0: return Vector2i(-1, -1)
		cell = Vector2i(int(floor((p.x - o.x) / c)), int(floor((p.y - o.y) / c)))
	if cell.x < 0 or cell.x >= GRID_COLS or cell.y < 0 or cell.y >= GRID_ROWS:
		return Vector2i(-1, -1)
	return cell


# Grundfarben je Terrain der Weltkarte (MapGen.TILE_*: 0=Gras, 1=Wald,
# 2=Wasser/Kueste, 3=Gebirge, 4=Sand, 5=Sumpf). Bis hierhin bestimmte das
# Terrain nur die Hindernis-Auswahl - der Boden war immer dasselbe
# Dunkelgrau, was jeden Kampf gleich aussehen liess.
const TERRAIN_GROUND := [
	Color(0.18, 0.28, 0.16),   # Gras
	Color(0.13, 0.22, 0.14),   # Wald
	Color(0.16, 0.23, 0.30),   # Wasser/Kueste
	Color(0.26, 0.25, 0.24),   # Gebirge
	Color(0.34, 0.30, 0.20),   # Sand
	Color(0.20, 0.23, 0.16),   # Sumpf
]


# --- Schlachtfeld-Grafik (It. 21) ----------------------------------------
# Vorher: Volltonfarbe je Gelaende mit Schachbrett-Nuance, Hindernisse im
# Code gezeichnet, und ueber/unter dem Gitter zusammen rund 40 % leere
# Flaeche (das Gitter ist breitenbegrenzt, die Flaeche auf dem Handy viel
# hoeher als breit). Jetzt Boden-Kacheln, Kulisse und Vordergrund aus
# tools/gen_battle_art.py. Fehlt eine Datei, greift ueberall der alte Weg.
const BATTLE_ART := "res://assets/battle/%s"
const TERRAIN_ART_NAMES := ["grass", "forest", "coast", "mountain", "sand", "swamp"]
# It. 36: von 4 auf 6. Bei 80 Zellen und 4 Varianten kam jede rund 20 Mal
# vor - genug, dass die Deko als Raster lesbar wurde. Muss zu
# tools/gen_battle_art.py GROUND_VARIANTS passen (test_battle prueft die
# Dateien).
const GROUND_VARIANTS := 6
# Hindernis-Art -> Sprite. Schluessel sind Integer-Literale wie in
# _dijkstra_for: cross-class class_name-Referenzen sind im Android-Export
# unzuverlaessig. 0=Stein, 1=Baumstamm, 2=Busch, 3=Sumpf, 4=Mauer.
const OBSTACLE_ART := {0: "stone", 1: "log", 2: "bush", 3: "swamp", 4: "wall"}
var _battle_tex_cache: Dictionary = {}


func _battle_texture(rel: String) -> Texture2D:
	if _battle_tex_cache.has(rel):
		return _battle_tex_cache[rel] as Texture2D
	var path: String = BATTLE_ART % rel
	var tex: Texture2D = load(path) as Texture2D if ResourceLoader.exists(path) else null
	_battle_tex_cache[rel] = tex
	return tex


func _terrain_art_name() -> String:
	if _terrain_id >= 0 and _terrain_id < TERRAIN_ART_NAMES.size():
		return String(TERRAIN_ART_NAMES[_terrain_id])
	return String(TERRAIN_ART_NAMES[0])


# Boden-Variante deterministisch aus Feld und Kampf-Seed. Bit-Mischung wie
# bei den Weltkarten-Kacheln: ohne sie koppelt die Paritaet an x und
# waagerechte Nachbarn bekommen nie dieselbe Variante (It. 19).
func _ground_variant(cx: int, cy: int) -> int:
	var h: int = (cx * 73856093) ^ (cy * 19349663) ^ (_art_seed * 83492791)
	h = (h ^ (h >> 13)) * 1274126177
	h = h ^ (h >> 16)
	return absi(h) % GROUND_VARIANTS


func _ground_color() -> Color:
	if _terrain_id >= 0 and _terrain_id < TERRAIN_GROUND.size():
		return TERRAIN_GROUND[_terrain_id]
	return TERRAIN_GROUND[0]


func _draw_grid() -> void:
	# EIN TRICHTER FUER BEIDE ANSICHTEN. Jeder Weg, der das Brett aendert,
	# ruft schon `_grid_area.queue_redraw()` - sonst waere auch die
	# 2D-Ansicht veraltet. Den Abgleich der raeumlichen hier anzuhaengen
	# heisst: es gibt keine Stelle, an der man ihn vergessen kann.
	_field3d_apply()
	if _field3d_on:
		# In 3D zeichnet die Ansicht das Brett. Was bleibt, sind die
		# ZAHLEN: eine Stapelgroesse ist Schrift, und Schrift im Raum waere
		# entweder schraeg gestellt oder ein Schild, das seine Zelle
		# verlaesst. Sie liegt deshalb flach darueber.
		_draw_counts_3d()
		# Der Effekt-Layer laeuft unveraendert darueber: er kennt nur
		# Zellmitten und die Zellgroesse, und beides liefert die
		# raeumliche Ansicht.
		_draw_effects(Vector2.ZERO, _field3d.cell_pixels())
		return
	var g: Array = _geom()
	var o: Vector2 = g[0]; var c: float = g[1]
	if c <= 0.0: return
	# Wackeln bei schweren Treffern. Nur der ZEICHEN-Ursprung wandert -
	# _geom() selbst bleibt sauber, sonst wuerde _cell_at die Taps
	# waehrend des Shakes auf die falschen Felder legen.
	o += _shake_offset()
	var gw := c * GRID_COLS; var gh := c * GRID_ROWS
	var ground: Color = _ground_color()

	# Schlachtfeld-Hintergrund ueber die GANZE Flaeche: das Gitter ist
	# breitenbegrenzt (10 Spalten), oben und unten blieb sonst schwarze
	# Leere stehen. Verlauf von dunkel (hinten) nach hell (vorne).
	var area := Vector2(_grid_area.size)
	var bands: int = 16
	for i in range(bands):
		var t: float = float(i) / float(bands - 1)
		_grid_area.draw_rect(Rect2(
			Vector2(0.0, area.y * float(i) / float(bands)),
			Vector2(area.x, area.y / float(bands) + 1.0)),
			ground.darkened(0.55).lerp(ground.darkened(0.25), t), true)

	# Kulisse OBERHALB und Bewuchs UNTERHALB des Gitters. Genau diese zwei
	# Baender standen leer.
	var art: String = _terrain_art_name()
	var back_tex: Texture2D = _battle_texture("backdrop/%s.svg" % art)
	if back_tex != null and o.y > 8.0:
		var bh: float = min(o.y, area.x * 0.34)
		_grid_area.draw_texture_rect(back_tex,
			Rect2(Vector2(0.0, o.y - bh), Vector2(area.x, bh)), false)
	var fore_tex: Texture2D = _battle_texture("fore/%s.svg" % art)
	var below: float = area.y - (o.y + gh)
	if fore_tex != null and below > 8.0:
		var fh: float = min(below, area.x * 0.22)
		_grid_area.draw_texture_rect(fore_tex,
			Rect2(Vector2(0.0, o.y + gh), Vector2(area.x, fh)), false)

	# Kampffeld-Boden: Kachel je Feld. Ohne Sprites bleibt die alte
	# Schachbrett-Nuance, damit Felder zaehlbar sind.
	# (Bei aktiver 3D-Ansicht ist hier schon zurueckgekehrt worden.)
	for cx in range(GRID_COLS):
		for cy in range(GRID_ROWS):
			var crect := Rect2(o + Vector2(float(cx) * c, float(cy) * c), Vector2(c, c))
			var gt: Texture2D = _battle_texture(
				"ground/%s_%d.svg" % [art, _ground_variant(cx, cy)])
			if gt != null:
				_grid_area.draw_texture_rect(gt, crect, false)
			else:
				var shade: float = 0.04 if (cx + cy) % 2 == 0 else 0.0
				_grid_area.draw_rect(crect, ground.lightened(shade), true)
	# Rahmen um das Feld.
	_grid_area.draw_rect(Rect2(o, Vector2(gw, gh)), ground.darkened(0.6), false, 4.0)

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

	# Aufstellungs-Zone (M7 Teil 2): waehrend der Taktik-Phase steht statt
	# der Reichweite die erlaubte Flaeche im Feld.
	if _tactics_phase:
		for tx in range(TACTICS_FIRST_COL, TACTICS_FIRST_COL + _tactics_cols + 1):
			for ty in range(GRID_ROWS):
				var tr := Rect2(o + Vector2(float(tx) * c, float(ty) * c),
					Vector2(c, c))
				_grid_area.draw_rect(tr, Color(0.25, 0.40, 0.60, 0.35), true)

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

	var r_active: float = c * TOKEN_DISC_FRAC
	for i in range(_p_stacks.size()):
		var s: Dictionary = _p_stacks[i]
		if int(s["count"]) <= 0: continue
		var sp: Vector2i = Vector2i(s["pos"])
		var ctr := _cell_center(sp, o, c) + _stack_offset(sp, c)
		# Seiten-Ring bleibt auch mit Sprite: er sagt auf einen Blick, wem
		# der Stack gehoert - die Silhouette allein tut das nicht.
		var col_fill := Color(0.95, 0.80, 0.25) if sp != active_pos else Color(1.0, 0.95, 0.4)
		_draw_token(ctr, c, r_active, s, col_fill, Color(0.5, 0.35, 0.05))
		if sp == active_pos:
			_grid_area.draw_arc(ctr, r_active + 4, 0, TAU, 32, Color(1,1,0.5,0.7), 2.5)
		if _tactics_phase and i == _tactics_pick:
			_grid_area.draw_arc(ctr, r_active + 6, 0, TAU, 32,
				Color(0.55, 0.85, 1.0, 0.9), 4.0)
		_draw_lbl(ctr, UnitType.short_of(String(s["type"])) + str(int(s["count"])), c)
		_draw_hp_bar(ctr, c, int(s["top_hp"]), UnitType.hp_of(String(s["type"])))
		_draw_status_marker(ctr, c, s)
		if bool(s.get("waited", false)):
			_draw_wait_marker(ctr, r_active)

	for i in range(_e_stacks.size()):
		var s: Dictionary = _e_stacks[i]
		if int(s["count"]) <= 0: continue
		var sp: Vector2i = Vector2i(s["pos"])
		var ctr := _cell_center(sp, o, c) + _stack_offset(sp, c)
		_draw_token(ctr, c, r_active, s, Color(0.5, 0.5, 0.55), Color(0.85, 0.25, 0.25))
		_draw_lbl(ctr, UnitType.short_of(String(s["type"])) + str(int(s["count"])), c)
		_draw_hp_bar(ctr, c, int(s["top_hp"]), UnitType.hp_of(String(s["type"])))
		_draw_status_marker(ctr, c, s)
		if bool(s.get("waited", false)):
			_draw_wait_marker(ctr, r_active)

	# Effekte zuletzt, damit sie ueber den Token liegen.
	_draw_effects(o, c)


# --- Zauber (M8) ---------------------------------------------------------

func _castable_spells() -> Array:
	var out: Array = []
	for sid in _p_spells:
		if Spl.cost_of(String(sid)) <= _p_mana:
			out.append(String(sid))
	return out


func _refresh_spell_button() -> void:
	if _spell_btn == null:
		return
	var can: Array = _castable_spells()
	_spell_btn.visible = not _p_spells.is_empty()
	_spell_btn.disabled = can.is_empty() or _casts_left <= 0 or _finished
	if _casts_left <= 0:
		_spell_btn.text = "Zauber verbraucht"
	elif can.is_empty():
		_spell_btn.text = "Mana %d" % _p_mana
	else:
		_spell_btn.text = "Zauber (%d Mana)" % _p_mana


func _on_spell_button() -> void:
	if _pending_spell != "":
		# Zweiter Druck bricht die Zielauswahl ab.
		_pending_spell = ""
		_set_action("Zauber abgebrochen.")
		return
	_open_spell_book()


func _open_spell_book() -> void:
	if _spell_panel == null:
		_build_spell_panel()
	var vb := _spell_panel.get_node("VB") as VBoxContainer
	for child in vb.get_children():
		child.queue_free()
	var head := Label.new()
	head.text = "Zauberbuch  -  %d Mana  -  Zauberkraft %d" % [_p_mana, _p_power]
	head.add_theme_font_size_override("font_size", 34)
	head.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(head)
	for sid in _castable_spells():
		var spell_id: String = String(sid)
		var btn := Button.new()
		btn.custom_minimum_size = Vector2(0, 110)
		btn.add_theme_font_size_override("font_size", 28)
		btn.text = Spl.book_line(spell_id, _p_power)
		btn.pressed.connect(_on_spell_chosen.bind(spell_id))
		vb.add_child(btn)
	var cancel := Button.new()
	cancel.custom_minimum_size = Vector2(0, 100)
	cancel.add_theme_font_size_override("font_size", 30)
	cancel.text = "Zurueck"
	cancel.pressed.connect(func(): _spell_panel.visible = false)
	vb.add_child(cancel)
	_spell_panel.visible = true


func _build_spell_panel() -> void:
	var panel := Panel.new()
	panel.visible = false
	panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(panel)
	var bg := ColorRect.new()
	bg.color = Color(0.05, 0.06, 0.09, 0.96)
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(bg)
	var vb := VBoxContainer.new()
	vb.name = "VB"
	vb.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	vb.offset_left = 40
	vb.offset_right = -40
	vb.offset_top = 140
	vb.offset_bottom = -140
	vb.add_theme_constant_override("separation", 18)
	panel.add_child(vb)
	_spell_panel = panel


func _on_spell_chosen(spell_id: String) -> void:
	_spell_panel.visible = false
	# Gebet und Flaechen-Zauber haben kein Einzelziel - sie wirken sofort,
	# statt auf ein Tippen zu warten, das nie kommen kann.
	if not Spl.needs_target(spell_id):
		_pending_spell = ""
		_cast_no_target(spell_id)
		return
	_pending_spell = spell_id
	var friendly: bool = Spl.is_friendly_target(spell_id)
	var what: String = "eigenen Stack"
	if Spl.undead_only(spell_id):
		what = "eigenen UNTOTEN Stack"
	elif not friendly:
		what = "Gegner-Stack"
	_set_action("%s: %s antippen." % [Spl.display_name(spell_id), what])


# Zauber, die die ganze eigene Seite treffen (Gebet).
func _cast_no_target(spell_id: String) -> void:
	var cost: int = Spl.cost_of(spell_id)
	if cost > _p_mana or _casts_left <= 0:
		_set_action("Nicht genug Mana.")
		return
	var st: Dictionary = Spl.status_of(spell_id)
	if st.is_empty():
		return
	_p_mana -= cost
	_casts_left -= 1
	Sound.play("spell_cast")
	var hit: int = 0
	for s in _p_stacks:
		if int(s["count"]) <= 0:
			continue
		Fx.add(s, String(st["status"]), int(st["rounds"]))
		Vfx.popup(_fx, Vector2i(s["pos"]), Spl.display_name(spell_id),
			Color(0.75, 0.70, 1.0))
		hit += 1
	_set_action("%s auf %d Stack(s), %d Rd.  [Mana %d]" % [
		Spl.display_name(spell_id), hit, int(st["rounds"]), _p_mana])
	_refresh_spell_button()
	_refresh()


# Tippt der Spieler im Zielmodus auf einen Stack, wird hier gewirkt.
# Rueckgabe true = Tap verbraucht.
func _try_cast_on(cell: Vector2i) -> bool:
	if _pending_spell == "":
		return false
	var spell_id: String = _pending_spell
	var friendly: bool = Spl.is_friendly_target(spell_id)
	var pool: Array = _p_stacks if friendly else _e_stacks
	var target: Dictionary = {}
	for s in pool:
		if int(s["count"]) > 0 and Vector2i(s["pos"]) == cell:
			target = s
			break
	if target.is_empty():
		_set_action("Kein gueltiges Ziel dort.")
		return true
	# Untote erwecken geht nur auf untote Stacks - so steht es in
	# spells.json, und ohne die Pruefung waere der Zauber auf jedem Stack
	# wirksam.
	if Spl.undead_only(spell_id) \
			and not UnitType.has_ability(String(target["type"]), "undead"):
		_set_action("%s wirkt nur auf Untote." % Spl.display_name(spell_id))
		return true
	_pending_spell = ""
	_cast(spell_id, target)
	return true


func _cast(spell_id: String, target: Dictionary) -> void:
	var cost: int = Spl.cost_of(spell_id)
	if cost > _p_mana or _casts_left <= 0:
		_set_action("Nicht genug Mana.")
		return
	_p_mana -= cost
	_casts_left -= 1
	Sound.play("spell_cast")
	var name: String = Spl.display_name(spell_id)
	var msg: String = ""
	var st: Dictionary = Spl.status_of(spell_id)
	if not st.is_empty():
		Fx.add(target, String(st["status"]), int(st["rounds"]))
		Vfx.popup(_fx, Vector2i(target["pos"]), name, Color(0.75, 0.70, 1.0))
		msg = "%s auf %s: %s fuer %d Runden" % [name,
			UnitType.name_of(String(target["type"])),
			String(st["status"]), int(st["rounds"])]
	elif Spl.damage_of(spell_id, _p_power) > 0:
		# Feuerschutz halbiert Feuer-Zauber (It. 43). Der Faktor kommt aus
		# StatusFx, damit die Zahl dort steht, wo alle Status-Zahlen stehen.
		var fire: bool = Spl.is_fire(spell_id)
		var dmg: int = int(round(float(Spl.damage_of(spell_id, _p_power))
			* Fx.spell_taken_factor(target, fire)))
		var killed: int = _apply_dmg(target, dmg)
		Sound.play("spell_hit")
		msg = "%s trifft %s: %d Schaden, %s" % [name,
			UnitType.name_of(String(target["type"])), dmg, _fallen(killed)]
		if fire and Fx.has(target, Fx.FIRE_WARD):
			msg += "  (halb: Feuerschutz)"
		if Spl.is_aoe(spell_id):
			# Umfeld wie die Lich-Todeswolke: halber Schaden auf die
			# Nachbarfelder derselben Seite.
			var side: int = int(target["side"])
			var splash: int = max(1, int(round(float(dmg) * Spl.AOE_FRACTION)))
			var hit: int = 0
			for s2 in (_e_stacks if side == 1 else _p_stacks):
				if s2 == target or int(s2["count"]) <= 0:
					continue
				if _adj(Vector2i(s2["pos"]), Vector2i(target["pos"])):
					# Auch im Umfeld schuetzt der Feuerschutz - sonst waere
					# er gegen den Feuerball, den einzigen Flaechenzauber
					# mit Feuer, halb wirkungslos.
					_apply_dmg(s2, maxi(1, int(round(float(splash)
						* Fx.spell_taken_factor(s2, fire)))))
					hit += 1
			if hit > 0:
				msg += "  (+%d Nachbar, je %d)" % [hit, splash]
	elif Spl.revive_of(spell_id, _p_power) > 0:
		# Wiederbeleben darf `count` wieder anheben (allow_revive), Heilen
		# nicht - das ist der ganze Unterschied zwischen den beiden.
		var rev: int = Spl.revive_of(spell_id, _p_power)
		var c_before: int = int(target["count"])
		CombatMath.heal(target, rev, true)
		var back: int = int(target["count"]) - c_before
		Vfx.healed(_fx, Vector2i(target["pos"]), rev)
		Sound.play("heal")
		msg = "%s auf %s: %d wiederbelebt" % [name,
			UnitType.name_of(String(target["type"])), back]
	else:
		var heal: int = Spl.heal_of(spell_id, _p_power)
		if heal > 0:
			var before: int = int(target["top_hp"])
			CombatMath.heal(target, heal, false)
			var gained: int = int(target["top_hp"]) - before
			Vfx.healed(_fx, Vector2i(target["pos"]), gained)
			Sound.play("heal")
			msg = "%s auf %s: %d Trefferpunkte geheilt" % [name,
				UnitType.name_of(String(target["type"])), gained]
	_set_action("%s  [Mana %d]" % [msg, _p_mana])
	_refresh_spell_button()
	_refresh()
	# Zaubern kostet KEINEN Zug - der aktive Stack darf danach noch
	# handeln (HoMM3-Regel). Deshalb hier kein _advance().
	if _check_end():
		return


# --- Effekt-Zeichnung (It. 17) --------------------------------------------

func _shake_offset() -> Vector2:
	var off := Vector2.ZERO
	for e in Vfx.of_kind(_fx, Vfx.SHAKE):
		if Vfx.pending(e):
			continue
		off += Vfx.shake_offset(Vfx.progress(e), float(e.get("amp", 5.0)))
	return off


# Versatz eines Stacks in PIXEL: Ausfallschritt beim Angriff, Gleiten
# beim Zug. Der Stack steht datenseitig schon auf dem Zielfeld - der
# Effekt zieht ihn optisch zurueck, bis er "angekommen" ist.
func _stack_offset(sp: Vector2i, c: float) -> Vector2:
	var off := Vector2.ZERO
	for e in _fx:
		if Vfx.pending(e):
			continue
		var kind: String = String(e.get("kind", ""))
		if kind == Vfx.LUNGE:
			if Vector2i(e.get("from", Vector2i.ZERO)) != sp:
				continue
			var dir: Vector2 = Vector2(Vector2i(e.get("to", sp)) - sp)
			off += dir * c * 0.34 * Vfx.ping_pong(Vfx.progress(e))
		elif kind == Vfx.MOVE:
			if Vector2i(e.get("to", Vector2i.ZERO)) != sp:
				continue
			var back: Vector2 = Vector2(Vector2i(e.get("from", sp)) - sp)
			off += back * c * (1.0 - Vfx.ease_in_out(Vfx.progress(e)))
	return off


# Letzter Durchgang, damit Effekte UEBER den Token liegen.
func _draw_effects(o: Vector2, c: float) -> void:
	var font: Font = ThemeDB.fallback_font
	for e in _fx:
		if Vfx.pending(e):
			continue
		var kind: String = String(e.get("kind", ""))
		var t: float = Vfx.progress(e)
		match kind:
			Vfx.PROJECTILE:
				var pa: Vector2 = _cell_center(Vector2i(e["from"]), o, c)
				var pb: Vector2 = _cell_center(Vector2i(e["to"]), o, c)
				var lift: float = float(e.get("lift", 0.45)) * c
				var p: Vector2 = Vfx.arc_point(pa, pb, t, lift)
				# Schweif: drei kleiner werdende Punkte hinter dem Geschoss.
				for k in range(3):
					var tt: float = max(0.0, t - 0.07 * float(k + 1))
					var q: Vector2 = Vfx.arc_point(pa, pb, tt, lift)
					_grid_area.draw_circle(q, c * (0.055 - 0.014 * float(k)),
						Color(1.0, 0.92, 0.65, 0.45 - 0.12 * float(k)))
				# Der Pfeil selbst als AUSGERICHTETER Schaft mit Spitze
				# (It. 36). Vorher war es ein Punkt: bei 104 px Zellgroesse
				# flog eine Murmel durchs Bild, und die Flugrichtung war nur
				# am Schweif zu erraten. Die Richtung kommt aus der Bahn
				# selbst (zwei Punkte kurz hintereinander), damit sie zur
				# Parabel passt und nicht zur Luftlinie.
				var ahead: Vector2 = Vfx.arc_point(pa, pb, min(1.0, t + 0.06), lift)
				var dir: Vector2 = (ahead - p)
				if dir.length() < 0.001:
					dir = (pb - pa)
				dir = dir.normalized()
				var side: Vector2 = Vector2(-dir.y, dir.x)
				var shaft: float = c * 0.30
				var tip: Vector2 = p + dir * shaft * 0.5
				var tail: Vector2 = p - dir * shaft * 0.5
				_grid_area.draw_line(tail, tip, Color(0.92, 0.86, 0.66),
					max(2.0, c * 0.030))
				_grid_area.draw_colored_polygon([
					tip + dir * c * 0.075,
					tip + side * c * 0.045,
					tip - side * c * 0.045,
				], Color(1.0, 0.97, 0.82))
				# Federn am Ende, damit der Pfeil eine Leserichtung hat.
				_grid_area.draw_line(tail + side * c * 0.03,
					tail - dir * c * 0.045, Color(0.95, 0.90, 0.72, 0.9),
					max(1.5, c * 0.018))
				_grid_area.draw_line(tail - side * c * 0.03,
					tail - dir * c * 0.045, Color(0.95, 0.90, 0.72, 0.9),
					max(1.5, c * 0.018))
			Vfx.IMPACT:
				var ctr: Vector2 = _cell_center(Vector2i(e["at"]), o, c)
				var col: Color = e.get("col", Color(1, 1, 1))
				var alpha: float = 1.0 - t
				# Ring + Splitter nach aussen: liest sich als Einschlag,
				# ein einfaches Aufblitzen sieht wie ein Fehler aus. Die
				# Radien kommen aus BattleVfx, damit die Vorschau dasselbe
				# zeichnet.
				_grid_area.draw_arc(ctr, c * Vfx.impact_radius(t), 0, TAU, 28,
					Color(col.r, col.g, col.b, alpha * 0.9), max(2.0, c * 0.05))
				var sp: Array = Vfx.impact_spoke(t)
				for k in range(Vfx.IMPACT_SPOKES):
					var a: float = float(k) * TAU / float(Vfx.IMPACT_SPOKES) + 0.3
					var dir := Vector2(cos(a), sin(a))
					_grid_area.draw_line(ctr + dir * c * float(sp[0]),
						ctr + dir * c * float(sp[1]),
						Color(1, 1, 1, alpha * 0.8), max(1.5, c * 0.035))
			Vfx.HEAL:
				var hc: Vector2 = _cell_center(Vector2i(e["at"]), o, c)
				for k in range(5):
					var ang: float = float(k) * TAU / 5.0
					var rise: float = c * 0.5 * Vfx.ease_out(t)
					var pt: Vector2 = hc + Vector2(cos(ang) * c * 0.28,
						sin(ang) * c * 0.16 - rise)
					_grid_area.draw_circle(pt, c * 0.06,
						Color(0.55, 1.0, 0.62, (1.0 - t) * 0.85))
			Vfx.DEATH:
				_draw_death(e, o, c, t)
			Vfx.WALL_BREAK:
				var wc: Vector2 = _cell_center(Vector2i(e["at"]), o, c)
				# Truemmer fallen auseinander und nach unten.
				for k in range(7):
					var ang2: float = float(k) * TAU / 7.0 + 0.5
					var d: Vector2 = Vector2(cos(ang2), sin(ang2) * 0.5)
					var pos: Vector2 = wc + d * c * 0.5 * Vfx.ease_out(t) \
						+ Vector2(0.0, c * 0.35 * t * t)
					var sz: float = c * 0.11 * (1.0 - t * 0.5)
					_grid_area.draw_rect(Rect2(pos - Vector2(sz, sz) * 0.5,
						Vector2(sz, sz)), Color(0.62, 0.60, 0.56, 1.0 - t), true)
			Vfx.NUMBER, Vfx.POPUP:
				var rf: Array = Vfx.rise_fade(t)
				var up: float = float(rf[0]) * c
				var a2: float = float(rf[1])
				var nc: Vector2 = _cell_center(Vector2i(e["at"]), o, c) \
					- Vector2(0.0, c * 0.42 + up)
				var txt: String = String(e.get("text", ""))
				var fsize: int = int(max(14.0, c * (0.30 if kind == Vfx.NUMBER else 0.24)))
				var col2: Color = e.get("col", Color(1, 1, 1))
				var w: float = font.get_string_size(txt,
					HORIZONTAL_ALIGNMENT_LEFT, -1, fsize).x
				var at: Vector2 = nc - Vector2(w * 0.5, 0.0)
				# Schlagschatten, sonst verschwindet die Zahl auf hellem Boden.
				_grid_area.draw_string(font, at + Vector2(2, 2), txt,
					HORIZONTAL_ALIGNMENT_LEFT, -1, fsize, Color(0, 0, 0, a2 * 0.8))
				_grid_area.draw_string(font, at, txt,
					HORIZONTAL_ALIGNMENT_LEFT, -1, fsize,
					Color(col2.r, col2.g, col2.b, a2))


# Zerfall eines gefallenen Stacks: das Sprite bleibt sichtbar, sinkt,
# schrumpft und blendet aus, dazu Staub. Position und Typ kommen aus dem
# Effekt, weil der Stack datenseitig schon leer ist.
func _draw_death(e: Dictionary, o: Vector2, c: float, t: float) -> void:
	var ctr: Vector2 = _cell_center(Vector2i(e["at"]), o, c)
	var fade: float = 1.0 - t
	var sink: float = c * 0.22 * Vfx.ease_out(t)
	var tex: Texture2D = _unit_texture(String(e.get("uid", "")))
	var size: float = c * 0.92 * (1.0 - 0.28 * t)
	var at: Vector2 = ctr + Vector2(0.0, sink) - Vector2(size, size) * 0.5
	_grid_area.draw_circle(ctr + Vector2(0.0, sink), c * 0.40 * (1.0 - 0.3 * t),
		Color(0.05, 0.05, 0.06, fade * 0.7))
	if tex != null:
		_grid_area.draw_texture_rect(tex, Rect2(at, Vector2(size, size)), false,
			Color(1, 1, 1, fade))
	# Staubwolke nach aussen.
	for k in range(5):
		var ang: float = float(k) * TAU / 5.0 + 0.9
		var d := Vector2(cos(ang), sin(ang) * 0.45)
		_grid_area.draw_circle(ctr + d * c * 0.44 * Vfx.ease_out(t),
			c * 0.09 * (1.0 - t * 0.4), Color(0.55, 0.50, 0.44, fade * 0.5))


# ZELLE -> BILDPUNKT, fuer beide Ansichten. Der ganze Effekt-Layer (Pfeile,
# Einschlaege, Heilung, Truemmer, Zahlen) rechnet nur ueber diese Funktion
# und ueber die Zellgroesse - beides gibt es in 3D genauso. Damit laeuft er
# unveraendert ueber der raeumlichen Ansicht, statt dort zu fehlen.
#
# `o` bleibt im Aufruf: in 2D ist es der Zeichen-Ursprung, in 3D das
# Ruetteln (SHAKE), das dort auf den Viewport selbst geht.
func _cell_center(cell: Vector2i, o: Vector2, c: float) -> Vector2:
	if _field3d_on and _field3d != null:
		return _field3d.project_cell(cell, 0.0)
	return o + Vector2((float(cell.x) + 0.5) * c, (float(cell.y) + 0.5) * c)


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
	var size: float = cell * TOKEN_SPRITE_FRAC
	_grid_area.draw_texture_rect(tex,
		Rect2(ctr - Vector2(size * 0.5, size * (0.5 + TOKEN_SPRITE_LIFT)),
			Vector2(size, size)), false)
	_grid_area.draw_arc(ctr, r, 0, TAU, 32, ring, 3.0)


# Sprite-Lookup mit Cache. Konvention: assets/units/<fraktion>/<id>.svg,
# Fraktions-Verzeichnis wie in CityScreen.FACTION_DIRS. Nicht gefundene
# Pfade werden als null gecacht, damit der Render-Loop nicht jeden Frame
# erneut sucht.
# Sprite-Zuordnung und Cache liegen seit It. 29 in core/UnitArt.gd - die
# Stadt-Panels brauchen dieselben Bilder, und zwei Kopien der
# Verzeichnis-Liste waeren zwei Gelegenheiten, `orkstaemme` statt `orks`
# zu schreiben.
func _unit_texture(uid: String) -> Texture2D:
	return UnitArt.texture_for(uid)


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
		# Sprite zuerst (It. 21). Die Mauer wechselt bei hp <= 1 auf die
		# gerissene Variante - der Spieler soll sehen, wo die naechste
		# Katapultkugel die Bresche schlaegt.
		var art_name: String = OBSTACLE_ART.get(kind, "")
		if kind == 4 and int(ob.get("hp", Obstacles.WALL_SEGMENT_HP)) <= 1:
			art_name = "wall_cracked"
		if art_name != "":
			var otex: Texture2D = _battle_texture("obstacles/%s.svg" % art_name)
			if otex != null:
				_grid_area.draw_texture_rect(otex,
					Rect2(o + Vector2(float(pos.x) * c, float(pos.y) * c),
						Vector2(c, c)), false)
				continue
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
	var top_left := Vector2(ctr.x - w * 0.5, ctr.y + cell * 0.28)
	_grid_area.draw_rect(Rect2(top_left, Vector2(w, h)), Color(0.15, 0.05, 0.05), true)
	var fill_col := Color(0.85, 0.25, 0.20)
	if frac > 0.66:
		fill_col = Color(0.35, 0.80, 0.35)
	elif frac > 0.33:
		fill_col = Color(0.95, 0.80, 0.25)
	_grid_area.draw_rect(Rect2(top_left, Vector2(w * frac, h)), fill_col, true)
	_grid_area.draw_rect(Rect2(top_left, Vector2(w, h)), Color(0.05, 0.05, 0.05), false, 1.0)


# Stapelgroessen ueber der raeumlichen Ansicht. Sie stehen an derselben
# Stelle wie in 2D (knapp unter der Figur) und tragen denselben Text -
# `_draw_lbl` ist fuer beide Ansichten dieselbe Funktion.
func _draw_counts_3d() -> void:
	if _field3d == null:
		return
	var c: float = _field3d.cell_pixels()
	if c <= 1.0:
		return
	for arr in [_p_stacks, _e_stacks]:
		for st in arr:
			var sd: Dictionary = st as Dictionary
			if int(sd["count"]) <= 0:
				continue
			var ctr: Vector2 = _field3d.project_cell(Vector2i(sd["pos"]), 0.0)
			_draw_lbl(ctr, UnitType.short_of(String(sd["type"]))
				+ str(int(sd["count"])), c)


func _draw_lbl(ctr: Vector2, txt: String, cell: float) -> void:
	var font: Font = get_theme_default_font()
	if font == null: return
	var fs: int = int(max(15.0, cell * 0.30))
	var sz: Vector2 = font.get_string_size(txt, HORIZONTAL_ALIGNMENT_CENTER, -1.0, fs)
	# Seit die Token-Scheibe dunkel ist (M10), braucht die Beschriftung
	# helle Schrift mit dunklem Schlagschatten - sonst verschwindet sie
	# auf der Scheibe. Sie sitzt leicht unterhalb der Mitte, damit Kopf
	# und Hoerner der Silhouette frei bleiben.
	# Unterhalb der Scheibe statt mitten auf dem Sprite - vorher lag der
	# Text ("Sk3") direkt auf der Silhouette und beide waren schlecht
	# lesbar. Der Token-Radius ist cell*0.40, also sitzt cell*0.52 knapp
	# darunter.
	var pos := Vector2(ctr.x - sz.x * 0.5, ctr.y + cell * 0.52)
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
	# Aufstellungsphase faengt den Tap ab, bevor irgendeine Zug-Logik
	# greift - es ist noch niemand am Zug.
	if _tactics_phase:
		var tc: Vector2i = _cell_at(mb.position)
		if tc.x >= 0:
			_tactics_tap(tc)
		return
	if _turn_order.is_empty() or _active_slot >= _turn_order.size(): return
	if int(_turn_order[_active_slot]["side"]) != 0: return

	var cell: Vector2i = _cell_at(mb.position)
	if cell.x < 0: return

	# Zauber-Zielmodus fangt den Tap ab, bevor Angriff oder Bewegung
	# ausgeloest werden.
	if _try_cast_on(cell):
		return

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
		Vfx.moved(_fx, Vector2i(active["pos"]), cell,
			String(active["type"]), 0)
		active["pos"] = cell
		_set_action("%s zieht weiter." % UnitType.name_of(String(active["type"])))
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
	_set_action("%s schlaegt gegen die Mauer: %s" % [UnitType.name_of(uid), res])
	_end_player_turn()
	return true


func _try_attack_enemy(e_idx: int) -> void:
	var active: Dictionary = _active_stack()
	var estack: Dictionary = _e_stacks[e_idx]
	var epos: Vector2i = Vector2i(estack["pos"])
	var apos: Vector2i = Vector2i(active["pos"])
	var uid: String = String(active["type"])

	var atk_s: String = UnitType.name_of(uid)
	var def_s: String = UnitType.name_of(String(estack["type"]))
	# Schiessen nur mit Munition - leergeschossene Schuetzen fallen in
	# die Nahkampf-Zweige unten (dort mit Fernkaempfer-Malus).
	if _can_shoot(active):
		var mod: Dictionary = Obstacles.line_modifier(_obstacles, apos, epos)
		if bool(mod["blocked"]):
			_set_action("Held %s: keine Schusslinie (Stein im Weg)." % atk_s)
			return
		var adjacent: bool = _adj(apos, epos)
		_fx_delay = Vfx.shot(_fx, apos, epos)
		Sound.play("arrow_shot")
		# Doppelschuss (Erz-Elfen) feuert zweimal - kostet 2 Munition.
		var volleys: int = Abil.attacks_per_turn(uid, true)
		var dmg: int = 0
		var killed: int = 0
		var fired: int = 0
		var extra: String = ""
		for _v in range(volleys):
			if int(estack["count"]) <= 0 or int(active["shots_left"]) <= 0:
				break
			var d1: int = _dmg(active, estack, adjacent, true)
			if bool(mod["halve"]):
				d1 = max(1, d1 / 2)
			dmg += d1
			killed += _apply_dmg(estack, d1)
			active["shots_left"] = int(active["shots_left"]) - 1
			fired += 1
			extra += _luck_suffix()
			extra += _roll_status(uid, estack)
			extra += _apply_aoe(uid, estack, d1)
		_fx_delay = 0.0
		var suffix: String = "  (halb: Baumstamm)" if bool(mod["halve"]) else ""
		var shot_txt: String = "%d Schaden, %s" % [dmg, _fallen(killed)]
		if fired > 1:
			shot_txt = "%d Schuesse, %s" % [fired, shot_txt]
		_set_action("%s beschiesst %s: %s%s%s  (noch %d Schuss)" % [
			atk_s, def_s, shot_txt, suffix, extra, int(active["shots_left"])])
		_end_player_turn()
		return

	if _adj(apos, epos):
		_set_action("%s greift %s an: %s" % [atk_s, def_s, _melee_exchange(active, estack)])
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
	Vfx.moved(_fx, Vector2i(active["pos"]), best, String(active["type"]), 0)
	active["pos"] = best
	_set_action("%s rueckt vor und greift %s an: %s"
		% [atk_s, def_s, _melee_exchange(active, estack)])
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
			Vfx.popup(_fx, Vector2i(s["pos"]), "Moral!", Color(0.55, 1.0, 0.65))
			_set_action("Gute Moral: %s %s zieht gleich nochmal." % [
				"dein" if side == 0 else "gegnerischer", UnitType.name_of(String(s["type"]))])
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

	var atk_s: String = UnitType.name_of(uid)
	var def_s: String = UnitType.name_of(String(best_target["type"]))
	if _can_shoot(estack):
		var mod: Dictionary = Obstacles.line_modifier(_obstacles, epos, tpos)
		if not bool(mod["blocked"]):
			var adjacent: bool = _adj(epos, tpos)
			_fx_delay = Vfx.time_left_of(_fx, Vfx.MOVE) \
				+ Vfx.shot(_fx, epos, tpos)
			Sound.play("arrow_shot")
			var volleys: int = Abil.attacks_per_turn(uid, true)
			var dmg: int = 0
			var killed: int = 0
			var fired: int = 0
			var extra: String = ""
			for _v in range(volleys):
				if int(best_target["count"]) <= 0 or int(estack["shots_left"]) <= 0:
					break
				var d1: int = _dmg(estack, best_target, adjacent, true)
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
			var shot_txt: String = "%d Schaden, %s" % [dmg, _fallen(killed)]
			if fired > 1:
				shot_txt = "%d Schuesse, %s" % [fired, shot_txt]
			_set_action("Gegnerischer %s beschiesst %s: %s%s%s"
				% [atk_s, def_s, shot_txt, suffix, extra])
			_rebuild_order()
			if _check_end(): return
			_advance()
			return
		# LOS blockiert (Stein) -> faellt durch auf Melee-Pathing unten.

	var spd: int = _reach_of(UnitType.speed_of(uid) + Fx.spd_mod(estack))
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
			Vfx.moved(_fx, epos, atk_cell, String(estack["type"]), 1)
			estack["pos"] = atk_cell
			epos = atk_cell
		var def_s2: String = UnitType.name_of(String(atk_target["type"]))
		# Fernkaempfer mit blockierter Schusslinie oder leerem Koecher
		# gleiten hier hinein und kassieren den korrekten Nahkampfabzug.
		_set_action("Gegnerischer %s greift %s an: %s"
			% [atk_s, def_s2, _melee_exchange(estack, atk_target)])
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
			Vfx.moved(_fx, epos, best_step, String(estack["type"]), 1)
			estack["pos"] = best_step
			_set_action("Gegnerischer %s zieht weiter." % atk_s)
		else:
			_set_action("Gegnerischer %s wartet ab." % atk_s)

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


func _dmg(attacker: Dictionary, defender: Dictionary, melee_penalty: bool,
		shooting: bool = false) -> int:
	var a_bonus: int = _p_att if int(attacker["side"]) == 0 else 0
	var d_bonus: int = _p_def if int(defender["side"]) == 0 else 0
	# Belagerung: die Stadt-Seite (1) steht hinter der Mauer und ist
	# schwerer zu treffen, solange kein Segment gefallen ist.
	if _siege and int(defender["side"]) == 1 and _walls_standing():
		d_bonus += SIEGE_DEF_BONUS
	# tiles_moved speist den Jousting-Bonus (Kavalier/Wolfsreiter).
	var opts: Dictionary = {"tiles_moved": int(attacker.get("tiles_moved", 0)),
		"shooting": shooting}
	var dmg: int = CombatMath.damage(attacker, defender, melee_penalty, a_bonus, d_bonus, _rng, opts)
	# Glueck wirkt auf den einzelnen Schlag (M6): Volltreffer x2, Pech x0.5.
	# Skill-Prozente (M7): Bogenkampf/Offensive auf den ausgeteilten,
	# Ruestungskunde auf den erlittenen Schaden - beide nur fuer die
	# Spielerseite, der Held steht auf keiner anderen.
	if int(attacker["side"]) == 0:
		var out_pct: int = _p_archery_pct if shooting else _p_offense_pct
		if out_pct != 0:
			dmg = max(1, int(round(float(dmg) * (1.0 + float(out_pct) / 100.0))))
	if int(defender["side"]) == 0 and _p_armorer_pct != 0:
		dmg = max(1, int(round(float(dmg) * (1.0 - float(_p_armorer_pct) / 100.0))))
	var luck: int = _p_luck if int(attacker["side"]) == 0 else _e_luck
	_last_luck = 1.0
	if luck != 0:
		_last_luck = Mor.luck_factor(luck, _rng)
		if _last_luck != 1.0:
			dmg = max(1, int(float(dmg) * _last_luck))
			# Einblendung am ZIEL, weil dort auch die Schadenszahl steht.
			if _last_luck > 1.0:
				Vfx.popup(_fx, Vector2i(defender["pos"]), "Glueck!",
					Color(1.0, 0.88, 0.35))
			else:
				Vfx.popup(_fx, Vector2i(defender["pos"]), "Pech!",
					Color(0.70, 0.72, 0.78))
	return dmg


# Log-Zusatz zum letzten Glueckswurf ("" wenn normal).
func _luck_suffix() -> String:
	if _last_luck > 1.0:
		return "  Volltreffer!"
	if _last_luck < 1.0:
		return "  Pech"
	return ""


# EINZIGER Trichter fuer Schaden an einem Stack - Nahkampf, Konter,
# Schuss, Todeswolke, Pfeilturm laufen alle hier durch. Deshalb sitzen die
# Treffer-Effekte hier und nicht an zehn Aufrufstellen: eine Quelle, kein
# vergessener Zweig.
func _apply_dmg(stack: Dictionary, dmg: int) -> int:
	var at: Vector2i = Vector2i(stack["pos"])
	var side: int = int(stack.get("side", 1))
	var before: int = int(stack["count"])
	var killed: int = CombatMath.apply(stack, dmg)
	var col: Color = FX_COL_PLAYER_HURT if side == 0 else FX_COL_ENEMY_HURT
	Vfx.hit(_fx, at, dmg, col, _fx_delay)
	# Stack ist gerade gefallen -> Zerfall. Der Effekt traegt Typ und Seite
	# selbst, damit _draw_effects die Einheit noch zeichnen kann, obwohl
	# ihr count schon 0 ist.
	if before > 0 and int(stack["count"]) <= 0:
		Vfx.died(_fx, at, String(stack["type"]), side, _fx_delay)
		Sound.play("death")
	return killed


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
	var cas: Dictionary = _own_casualties()
	# Ueberlebende BEIDER Seiten mitgeben: eine gescheiterte Belagerung
	# soll die Stadt-Garnison geschwaecht zuruecklassen, und bei einem
	# Verteidigungskampf um die eigene Stadt braucht der Aufrufer die
	# Reste der eigenen (Garnisons-)Truppe.
	# Gefallene Gegner - Grundlage der Totenerweckung (M7 Teil 2). Zwei
	# Zahlen: Koepfe fuer die Meldung, TREFFERPUNKTE fuer die Rechnung.
	# Ueber die HP, weil ein Feld voll Goblins sonst mehr Skelette bringt
	# als ein gefallener Drache (siehe HeroSkills.raised_skeletons).
	var e_killed: int = 0
	var e_killed_hp: int = 0
	for s in _e_stacks:
		var lost_e: int = int(s.get("count_start", 0)) - int(s["count"])
		if lost_e > 0:
			e_killed += lost_e
			e_killed_hp += lost_e * UnitType.hp_of(String(s["type"]))
	var res: Dictionary = {
		"outcome": "victory" if p_alive else "defeat",
		"casualties": cas,
		"enemy_killed": e_killed,
		"enemy_killed_hp": e_killed_hp,
		# M8: verbrauchtes Mana muss zurueck, sonst waere der Held nach
		# jedem Kampf wieder voll aufgeladen.
		"mana_left": _p_mana,
		"player_remaining": _remaining_of(_p_stacks),
		"enemy_remaining": _remaining_of(_e_stacks),
	}
	battle_finished.emit(res)
	return true


func _remaining_of(stacks: Array) -> Dictionary:
	var out: Dictionary = {}
	for s in stacks:
		var c: int = int(s["count"])
		if c > 0:
			var uid: String = String(s["type"])
			out[uid] = int(out.get(uid, 0)) + c
	return out


func _on_wait() -> void:
	if _finished: return
	if _turn_order.is_empty() or _active_slot >= _turn_order.size(): return
	if int(_turn_order[_active_slot]["side"]) != 0: return
	var active: Dictionary = _active_stack()
	if active.is_empty(): return
	if bool(active.get("waited", false)):
		# Doppelwarten nicht erlaubt (HoMM-Konvention): stattdessen Zug
		# einfach aussetzen, damit der Spieler weiterkommt.
		_set_action("%s pausiert." % UnitType.name_of(String(active["type"])))
		if _check_end(): return
		_advance()
		return
	active["waited"] = true
	_set_action("%s wartet und zieht spaeter in der Runde."
		% UnitType.name_of(String(active["type"])))
	_rebuild_order()
	if _check_end(): return
	# Kein _advance: rebuild hat den Warter ans Ende geschoben, der neue
	# Stack auf _active_slot ist der naechste Handler.
	_step()


# Der Preis steht auf dem Knopf - sonst ist Kapitulieren ein Blindkauf.
func _refresh_surrender_button() -> void:
	if _surrender_btn == null:
		return
	_surrender_btn.visible = _allow_surrender
	_surrender_btn.text = "Kapitulieren\n%d G" % _surrender_cost


func _on_flee() -> void:
	if _finished or not _allow_flee: return
	# Flucht KOSTET die Armee (HoMM3-Regel) - der Aufrufer setzt sie auf
	# leer. Die Verluste werden trotzdem mitgegeben, damit die Meldung auf
	# der Karte stimmt.
	_finished = true
	battle_finished.emit({"outcome": "flee", "casualties": _own_casualties(),
		"mana_left": _p_mana,
		"player_remaining": _remaining_of(_p_stacks),
		"enemy_remaining": _remaining_of(_e_stacks)})


# Kapitulieren: Gold gegen die UEBERLEBENDE Armee. Der Held behaelt sie,
# der Aufrufer zieht das Gold ab und schickt ihn in die naechste eigene
# Stadt. Anders als bei der Flucht ist das die teure, aber verlustfreie
# Tuer aus einem Kampf, den man nicht gewinnen kann.
func _on_surrender() -> void:
	if _finished or not _allow_surrender: return
	_finished = true
	battle_finished.emit({"outcome": "surrender", "casualties": _own_casualties(),
		"mana_left": _p_mana,
		"surrender_cost": _surrender_cost,
		"player_remaining": _remaining_of(_p_stacks),
		"enemy_remaining": _remaining_of(_e_stacks)})


# Eigene Verluste bis JETZT. _check_end rechnet dasselbe; herausgezogen,
# weil Flucht und Kapitulation es auch brauchen.
func _own_casualties() -> Dictionary:
	var cas: Dictionary = {}
	for st in _p_stacks:
		var uid: String = String(st["type"])
		var lost: int = int(st.get("count_start", 0)) - int(st["count"])
		if lost > 0:
			cas[uid] = int(cas.get(uid, 0)) + lost
	return cas
