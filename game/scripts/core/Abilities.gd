class_name Abilities
extends RefCounted

# Kampf-Faehigkeiten (M6b Teil 1). Reine statische Funktionen ueber den
# abilities-Flags aus data/units.json - kein State, kein RNG. Dadurch
# bleibt der Kampf-Screen duenn und die Tests koennen jede Regel
# deterministisch pruefen (tools/test_battle.gd).
#
# Einbindung im Spiel per preload (nicht ueber class_name), weil
# Cross-File-class_name-Aufrufe im Android-Export historisch
# unzuverlaessig waren - siehe Kopf von TacticalBattleScreen.gd.
#
# units.json definiert die Flag-Semantik nicht formal; die hier
# gewaehlten Zahlen sind die dokumentierte Interpretation (HoMM3-nah):
#
#   flying                    Bewegung ignoriert Stein/Baum + Gelaende-Aufschlag
#   double_attack             2 Nahkampf-Angriffe pro Zug
#   double_shot               2 Schuesse pro Zug (kostet 2 Munition)
#   unlimited_retaliations    kontert jeden Angriff, nicht nur den ersten
#   no_retaliation            das Opfer dieses Angreifers kontert nicht
#   defense_ignore_25pct      Verteidigung des Ziels zaehlt nur zu 75 %
#   jousting_bonus            +5 % Schaden je gelaufenem Feld
#   jousting_bonus_light      +2,5 % Schaden je gelaufenem Feld
#   polearm_bonus_vs_cavalry  +50 % gegen Kavallerie (= Jousting-Traeger)
#   life_drain_50pct          heilt 50 % des zugefuegten Schadens
#   regeneration_per_turn     Rundenstart: oberste Einheit heilt voll
#   regeneration_if_half_hp   dito, aber nur unter 50 % Rest-HP
#
# Noch NICHT hier (Whitelist im Kampf-Screen loggt sie):
# Status-Effekte (root/blind/stun/disease/curse/aging) + death_cloud_aoe
# -> M6b Teil 2; Magie-Flags -> M8; attack_wall -> M9 Belagerung;
# morale_aura/hates:*/undead -> M6 Moral.

const JOUSTING_PCT_PER_TILE: int = 5
const JOUSTING_LIGHT_PCT_PER_TILE: int = 2
const POLEARM_BONUS_PCT: int = 50
const DEFENSE_IGNORE_FACTOR: float = 0.75
const LIFE_DRAIN_FRACTION: float = 0.5


static func ignores_obstacles(uid: String) -> bool:
	return UnitType.has_ability(uid, "flying")


# Angriffe bzw. Schuesse pro Zug. shooting=true fuer den Fernkampf-Pfad,
# damit Doppelangriff (Nahkampf) und Doppelschuss getrennt bleiben.
static func attacks_per_turn(uid: String, shooting: bool) -> int:
	if shooting:
		return 2 if UnitType.has_ability(uid, "double_shot") else 1
	return 2 if UnitType.has_ability(uid, "double_attack") else 1


# Darf der Verteidiger (defender_uid) diesen Nahkampf-Angriff kontern?
# times_retaliated = wie oft er in dieser Runde schon gekontert hat.
static func retaliation_allowed(defender_uid: String, attacker_uid: String,
		times_retaliated: int) -> bool:
	if UnitType.has_ability(attacker_uid, "no_retaliation"):
		return false
	if UnitType.has_ability(defender_uid, "unlimited_retaliations"):
		return true
	return times_retaliated <= 0


static func def_after_ignore(attacker_uid: String, def_val: int) -> int:
	if UnitType.has_ability(attacker_uid, "defense_ignore_25pct"):
		return int(float(def_val) * DEFENSE_IGNORE_FACTOR)
	return def_val


# Kavallerie = Einheiten mit Jousting-Flag. Datengetrieben, damit die
# Speertraeger-Regel keine zweite Liste braucht.
static func is_cavalry(uid: String) -> bool:
	return UnitType.has_ability(uid, "jousting_bonus") \
		or UnitType.has_ability(uid, "jousting_bonus_light")


# Prozentualer Nahkampf-Schadensbonus des Angreifers. tiles_moved =
# Felder, die er in diesem Zug bis zum Ziel gelaufen ist (Jousting).
static func melee_bonus_pct(attacker_uid: String, defender_uid: String,
		tiles_moved: int) -> int:
	var pct: int = 0
	var moved: int = max(0, tiles_moved)
	if UnitType.has_ability(attacker_uid, "jousting_bonus"):
		pct += moved * JOUSTING_PCT_PER_TILE
	elif UnitType.has_ability(attacker_uid, "jousting_bonus_light"):
		pct += moved * JOUSTING_LIGHT_PCT_PER_TILE
	if UnitType.has_ability(attacker_uid, "polearm_bonus_vs_cavalry") \
			and is_cavalry(defender_uid):
		pct += POLEARM_BONUS_PCT
	return pct


static func drain_fraction(uid: String) -> float:
	return LIFE_DRAIN_FRACTION if UnitType.has_ability(uid, "life_drain_50pct") else 0.0


# HP, die der Stack zum Rundenstart regeneriert (0 = keine Regeneration).
# hp_now/hp_max beziehen sich auf die oberste Einheit (top_hp).
static func regen_hp(uid: String, hp_now: int, hp_max: int) -> int:
	if hp_now >= hp_max or hp_max <= 0:
		return 0
	if UnitType.has_ability(uid, "regeneration_per_turn"):
		return hp_max - hp_now
	if UnitType.has_ability(uid, "regeneration_if_half_hp"):
		# Nur der schwer angeschlagene Stack regeneriert (Gespenst).
		if hp_now * 2 < hp_max:
			return hp_max - hp_now
	return 0
