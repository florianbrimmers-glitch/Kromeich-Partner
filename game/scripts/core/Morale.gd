class_name Morale
extends RefCounted

# Moral und Glueck (M6). Wie Abilities/StatusFx rein statisch, Einbindung
# per preload (Android-class_name-Falle, siehe TacticalBattleScreen-Kopf).
#
# MORAL kommt aus der Armee-Zusammenstellung und gilt fuer eine ganze
# Seite. Nutzer-Entscheidung: HoMM3-streng, jede zusaetzliche Fraktion
# kostet.
#
#   1 Fraktion   +1     reine Armee kaempft geschlossen
#   2 Fraktionen  0
#   3 Fraktionen -1
#   4 Fraktionen -2
#   Lebende + Untote in derselben Armee: zusaetzlich -1
#   morale_aura (Engel): +1 fuer seine Seite
#   Ergebnis auf +-3 begrenzt
#
# Wirkung pro Zug (HoMM3-Muster, 10 % je Moralpunkt):
#   Moral > 0  Chance auf eine zweite Aktion ("Moral!")
#   Moral < 0  Chance den Zug zu verlieren ("keine Moral")
#   undead-Stacks sind immun - weder Bonus noch Malus.
#
# GLUECK wirkt auf den einzelnen Schlag: Volltreffer x2, Pechschlag x0.5,
# ebenfalls 10 % je Punkt. Quelle im Spiel ist die Kapelle
# (WorldMapScreen._player_luck, +1 je Kapelle, max +3); Helden-Skills
# kommen mit M7 dazu.

const MORALE_BY_FACTION_COUNT := {1: 1, 2: 0, 3: -1, 4: -2}
const UNDEAD_MIX_MALUS: int = -1
const AURA_BONUS: int = 1
const LIMIT: int = 3
const CHANCE_PER_POINT: float = 0.10

const LUCKY_FACTOR: float = 2.0
const UNLUCKY_FACTOR: float = 0.5
const LUCK_LIMIT: int = 3


# Untote ignorieren Moral komplett (kein Extrazug, kein Zugverlust).
static func is_immune(uid: String) -> bool:
	return UnitType.has_ability(uid, "undead")


# Moral einer Seite aus ihren Stacks. Erwartet Stack-Dicts mit "type"
# und "count"; tote Stacks zaehlen nicht mehr mit.
static func morale_for(stacks: Array) -> int:
	var factions: Dictionary = {}
	var has_undead: bool = false
	var has_living: bool = false
	var aura: int = 0
	for s in stacks:
		if int((s as Dictionary).get("count", 0)) <= 0:
			continue
		var uid: String = String((s as Dictionary)["type"])
		factions[UnitType.faction_of(uid)] = true
		if is_immune(uid):
			has_undead = true
		else:
			has_living = true
		if UnitType.has_ability(uid, "morale_aura"):
			aura = AURA_BONUS
	if factions.is_empty():
		return 0
	var m: int = int(MORALE_BY_FACTION_COUNT.get(factions.size(), -2))
	if has_undead and has_living:
		m += UNDEAD_MIX_MALUS
	m += aura
	return clampi(m, -LIMIT, LIMIT)


static func extra_turn_chance(morale: int) -> float:
	return float(max(0, morale)) * CHANCE_PER_POINT


static func freeze_chance(morale: int) -> float:
	return float(max(0, -morale)) * CHANCE_PER_POINT


# Wuerfelt einen Extrazug (nur bei positiver Moral).
static func rolls_extra_turn(morale: int, rng: RandomNumberGenerator) -> bool:
	var c: float = extra_turn_chance(morale)
	return c > 0.0 and rng.randf() < c


# Wuerfelt den Zugverlust (nur bei negativer Moral).
static func rolls_freeze(morale: int, rng: RandomNumberGenerator) -> bool:
	var c: float = freeze_chance(morale)
	return c > 0.0 and rng.randf() < c


# Schadensfaktor durch Glueck: x2 bei Volltreffer, x0.5 bei Pech, sonst 1.
static func luck_factor(luck: int, rng: RandomNumberGenerator) -> float:
	var l: int = clampi(luck, -LUCK_LIMIT, LUCK_LIMIT)
	if l == 0:
		return 1.0
	var c: float = float(abs(l)) * CHANCE_PER_POINT
	if rng.randf() >= c:
		return 1.0
	return LUCKY_FACTOR if l > 0 else UNLUCKY_FACTOR


# Anzeigetext fuer die Kampf-Kopfzeile, z.B. "Moral +1 Glueck +2".
static func status_text(morale: int, luck: int) -> String:
	return "Moral %+d Glueck %+d" % [morale, luck]
