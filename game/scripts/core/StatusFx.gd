class_name StatusFx
extends RefCounted

# Status-Effekte mit Dauer (M6b Teil 2). Wie Abilities.gd rein statisch:
# der Zustand lebt im Stack-Dictionary unter "status" als
# { name: verbleibende_Runden }, die Regeln stehen hier.
#
# Einbindung per preload (Android-class_name-Falle, siehe
# TacticalBattleScreen.gd-Kopf).
#
# units.json nennt nur Flags mit Prozentzahl im Namen - Dauer und
# Wirkung sind die hier dokumentierte Interpretation (HoMM3-nah, aber
# fuer Handy-Runden abgemildert: nichts dauert laenger als 3 Runden,
# damit ein Stack nie eine ganze Schlacht handlungsunfaehig ist):
#
#   verwurzelt  (Treant, 20 %)      1 Runde  kann sich nicht bewegen
#   geblendet   (Einhorn, 15 %)     1 Runde  verliert den Zug; ein
#                                            Nahkampf-Treffer weckt es
#   betaeubt    (Oger, 10 %)        1 Runde  verliert den Zug
#   krank       (Zombie, immer)     3 Runden -2 Angriff, -2 Verteidigung
#   verflucht   (Schwarzritter,10%) 2 Runden richtet 25 % weniger an
#   gealtert    (Knochendrache,10%) 2 Runden erleidet 25 % mehr Schaden
#
# Dazu die kleine Todeswolke des Lichs (death_cloud_aoe_small): der
# Schuss trifft die Nachbar-Stacks des Ziels mit halbem Schaden.

const ROOTED := "verwurzelt"
const BLINDED := "geblendet"
const STUNNED := "betaeubt"
const DISEASED := "krank"
const CURSED := "verflucht"
const AGED := "gealtert"
# Zauber-Status (M8). Bewusst getrennt von den Treffer-Status oben: die
# kommen aus units.json-Flags, diese aus data/spells.json. Gleiche
# Mechanik, andere Quelle.
const HASTENED := "beschleunigt"
const SLOWED := "verlangsamt"
const STONE_SKIN := "steinhaut"
const WEAKENED := "geschwaecht"
# M8 Teil 2
const BLESSED := "gesegnet"       # richtet immer Hoechstschaden an
const SHIELDED := "geschirmt"     # weniger NAHKAMPF-Schaden erlitten
const PRAYED := "gebet"           # +2 Angriff, Verteidigung, Geschwindigkeit
const READY := "konterbereit"     # ein zusaetzlicher Konter pro Runde

# Ability-Flag -> Status, Trefferwahrscheinlichkeit, Dauer in Runden.
const ON_HIT := {
	"root_enemy_on_hit_20pct":  {"status": ROOTED,   "chance": 0.20, "rounds": 1},
	"blind_enemy_on_hit_15pct": {"status": BLINDED,  "chance": 0.15, "rounds": 1},
	"bash_stun_10pct":          {"status": STUNNED,  "chance": 0.10, "rounds": 1},
	"disease_on_hit":           {"status": DISEASED, "chance": 1.00, "rounds": 3},
	"curse_on_hit_10pct":       {"status": CURSED,   "chance": 0.10, "rounds": 2},
	"aging_on_hit_10pct":       {"status": AGED,     "chance": 0.10, "rounds": 2},
}

# Kurzmarker fuer die Kampf-Anzeige (ein Zeichen pro Status).
const MARKERS := {
	ROOTED: "W", BLINDED: "B", STUNNED: "S",
	DISEASED: "K", CURSED: "F", AGED: "A",
	# Zauber-Status (M8). Grossbuchstaben bleiben fuer Treffer-Status,
	# damit man im Gitter auf einen Blick sieht, woher etwas kommt.
	HASTENED: "h", SLOWED: "l", STONE_SKIN: "d", WEAKENED: "w",
	BLESSED: "+", SHIELDED: "s", PRAYED: "p", READY: "k",
}

const DISEASE_STAT_MALUS: int = 2
# Zauber-Werte. Quelle: data/spells.json (+3_spd, -3_spd, +3_def, -3_att).
const HASTE_SPD_BONUS: int = 3
const SLOW_SPD_MALUS: int = 3
const STONE_SKIN_DEF_BONUS: int = 3
const WEAKNESS_ATT_MALUS: int = 3
# M8 Teil 2. Quelle: data/spells.json.
const PRAYER_STAT_BONUS: int = 2
const SHIELD_MELEE_FACTOR: float = 0.85   # -15 % Nahkampf-Schaden
const READY_EXTRA_RETALIATIONS: int = 1
const CURSE_DEALT_FACTOR: float = 0.75
const AGED_TAKEN_FACTOR: float = 1.25

const AOE_FLAG := "death_cloud_aoe_small"
const AOE_FRACTION: float = 0.5


static func has(stack: Dictionary, name: String) -> bool:
	return int((stack.get("status", {}) as Dictionary).get(name, 0)) > 0


static func add(stack: Dictionary, name: String, rounds: int) -> void:
	var st: Dictionary = stack.get("status", {}) as Dictionary
	# Neuer Treffer verlaengert nur, verkuerzt nie.
	st[name] = max(int(st.get(name, 0)), rounds)
	stack["status"] = st


static func clear(stack: Dictionary, name: String) -> void:
	var st: Dictionary = stack.get("status", {}) as Dictionary
	st.erase(name)
	stack["status"] = st


# Rundenwechsel: alle Dauern um 1 runter, abgelaufene raus.
static func tick(stack: Dictionary) -> void:
	var st: Dictionary = stack.get("status", {}) as Dictionary
	for name in st.keys():
		var left: int = int(st[name]) - 1
		if left <= 0:
			st.erase(name)
		else:
			st[name] = left
	stack["status"] = st


# Wuerfelt die On-Hit-Effekte des Angreifers auf das Ziel. Rueckgabe:
# Namen der neu gesetzten Status (fuer das Kampf-Log), leer wenn nichts
# gegriffen hat. Der RNG kommt von aussen, damit Kaempfe deterministisch
# bleiben (gleicher Seed = gleicher Verlauf).
static func apply_on_hit(attacker_uid: String, target: Dictionary,
		rng: RandomNumberGenerator) -> Array:
	var applied: Array = []
	if int(target.get("count", 0)) <= 0:
		return applied
	for flag in ON_HIT.keys():
		if not UnitType.has_ability(attacker_uid, String(flag)):
			continue
		var rule: Dictionary = ON_HIT[flag]
		if rng.randf() < float(rule["chance"]):
			add(target, String(rule["status"]), int(rule["rounds"]))
			applied.append(String(rule["status"]))
	return applied


static func att_mod(stack: Dictionary) -> int:
	var m: int = 0
	if has(stack, DISEASED):
		m -= DISEASE_STAT_MALUS
	if has(stack, WEAKENED):
		m -= WEAKNESS_ATT_MALUS
	if has(stack, PRAYED):
		m += PRAYER_STAT_BONUS
	return m


static func def_mod(stack: Dictionary) -> int:
	var m: int = 0
	if has(stack, DISEASED):
		m -= DISEASE_STAT_MALUS
	if has(stack, STONE_SKIN):
		m += STONE_SKIN_DEF_BONUS
	if has(stack, PRAYED):
		m += PRAYER_STAT_BONUS
	return m


# Geschwindigkeits-Aenderung (M8). Beschleunigen und Verlangsamen heben
# sich gegenseitig auf, statt sich zu stapeln - so kann ein Zauberduell
# nicht in absurde Werte laufen.
static func spd_mod(stack: Dictionary) -> int:
	var m: int = 0
	if has(stack, HASTENED):
		m += HASTE_SPD_BONUS
	if has(stack, SLOWED):
		m -= SLOW_SPD_MALUS
	if has(stack, PRAYED):
		m += PRAYER_STAT_BONUS
	return m


# Faktor auf den Schaden, den dieser Stack ANRICHTET.
static func dealt_factor(stack: Dictionary) -> float:
	return CURSE_DEALT_FACTOR if has(stack, CURSED) else 1.0


# Faktor auf den Schaden, den dieser Stack ERLEIDET.
#
# `melee` unterscheidet Nahkampf von Fernkampf: der Schild-Zauber wirkt
# laut spells.json nur gegen Nahkampf. Standard true, damit bestehende
# Aufrufer (und der Balance-Simulator) unveraendert weiterlaufen.
static func taken_factor(stack: Dictionary, melee: bool = true) -> float:
	var f: float = AGED_TAKEN_FACTOR if has(stack, AGED) else 1.0
	if melee and has(stack, SHIELDED):
		f *= SHIELD_MELEE_FACTOR
	return f


# Verschiebung des Schadenswurfs: +1 = immer Hoechstwert, -1 = immer
# Mindestwert, 0 = normal wuerfeln.
#
# Der Fluch bleibt bewusst ein FAKTOR (CURSE_DEALT_FACTOR) und keine
# Wurf-Verschiebung, obwohl spells.json "dmg_min" sagt: derselbe Status
# kommt aus der Schwarzritter-Faehigkeit `curse_on_hit_10pct`, und ein
# Mechanik-Wechsel wuerde die in Balance-Pass 10 getunten Zahlen
# verschieben.
static func damage_bias(stack: Dictionary) -> int:
	return 1 if has(stack, BLESSED) else 0


# Zusaetzlich erlaubte Konter pro Runde (Konterschlag-Zauber).
static func extra_retaliations(stack: Dictionary) -> int:
	return READY_EXTRA_RETALIATIONS if has(stack, READY) else 0


# Verliert der Stack seinen Zug (und kontert nicht)?
static func blocks_turn(stack: Dictionary) -> bool:
	return has(stack, BLINDED) or has(stack, STUNNED)


static func blocks_move(stack: Dictionary) -> bool:
	return has(stack, ROOTED) or blocks_turn(stack)


# Nahkampf-Treffer weckt geblendete Stacks (HoMM3-Regel).
static func wake_on_melee(stack: Dictionary) -> bool:
	if has(stack, BLINDED):
		clear(stack, BLINDED)
		return true
	return false


static func aoe_fraction(uid: String) -> float:
	return AOE_FRACTION if UnitType.has_ability(uid, AOE_FLAG) else 0.0


# Kompakte Marker fuer die Kampf-Anzeige, z.B. "KF".
static func marker_text(stack: Dictionary) -> String:
	var st: Dictionary = stack.get("status", {}) as Dictionary
	var out: String = ""
	for name in MARKERS.keys():
		if int(st.get(name, 0)) > 0:
			out += String(MARKERS[name])
	return out


# Ausgeschriebene Liste fuer das Kampf-Log.
static func names_text(names: Array) -> String:
	return ", ".join(names)


# Name des Status, der dem Stack gerade den Zug nimmt (fuer Meldungen).
static func marker_name(stack: Dictionary) -> String:
	if has(stack, STUNNED):
		return STUNNED
	if has(stack, BLINDED):
		return BLINDED
	if has(stack, ROOTED):
		return ROOTED
	return ""
