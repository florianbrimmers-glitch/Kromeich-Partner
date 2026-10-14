extends RefCounted

# Abenteuer-Objekte der Weltkarte, zweite Welle (It. 78).
#
# Die ersten zehn Arten (Mine, Truhe, Haufen, vier Schreine, Brunnen,
# Lehrmeister, Windmuehle) stehen als Konstanten in WorldMapScreen. Die
# neuen stehen HIER, mit allem, was sich ohne Spielzustand sagen laesst:
# Name, Sprite, Modell, wie oft sie besucht werden duerfen und die reinen
# Regeln (welcher Skill, welcher Zauber, welche Beute). Was sie mit dem
# Helden machen, entscheidet weiter der Weltkarten-Screen - dort liegen
# Held, Kasse und Nebel.
#
# Vorbild ist die Abenteuerkarte von Heroes 4: Lagerfeuer, Artefakte am
# Boden, Wassermuehle, Staelle, Oase, Aussichtsturm, Arena, Gluecksbrunnen,
# Tempel, Baum des Wissens, Hexenhuette, Schrein der Magie, Gefaengnis und
# Handelsposten.
#
# Per preload eingebunden, ohne class_name (Android-Export-Falle, siehe
# Kopf von TacticalBattleScreen.gd).

const CAMPFIRE := 10       # Gold + eine Ressource, einmalig, verschwindet
const ARTIFACT := 11       # Artefakt am Boden, bewacht, verschwindet
const WATERMILL := 12      # Gold, einmal pro Woche
const STABLES := 13        # mehr Bewegung bis Wochenende, je Held
const OASIS := 14          # Bewegung sofort, einmal pro Tag
const LOOKOUT := 15        # deckt einen weiten Umkreis dauerhaft auf
const ARENA := 16          # +2 Angriff ODER +2 Verteidigung (Wahl), einmalig
const FOUNTAIN := 17       # Glueck +1 bis zum naechsten Kampf
const TEMPLE := 18         # Moral +1 bis zum naechsten Kampf
const TREE := 19           # eine Stufe, einmalig
const WITCH_HUT := 20      # lehrt eine Faehigkeit, einmalig
const MAGIC_SHRINE := 21   # lehrt einen Zauber, einmalig
const PRISON := 22         # befreit einen Helden, verschwindet
const TRADING_POST := 23   # Tausch zu besseren Kursen als der Markt

const FIRST := CAMPFIRE
const LAST := TRADING_POST

# Name, Sprite (assets/world/objects/<sprite>.svg), 3D-Modell (mapobj.glb)
# und Anzahl auf der Karte.
const CATALOG := {
	CAMPFIRE: {"name": "Lagerfeuer", "sprite": "campfire", "model": "obj_campfire", "count": 3},
	ARTIFACT: {"name": "Artefakt", "sprite": "artifact", "model": "obj_artifact", "count": 3},
	WATERMILL: {"name": "Wassermuehle", "sprite": "watermill", "model": "obj_watermill", "count": 1},
	STABLES: {"name": "Stallungen", "sprite": "stables", "model": "obj_stables", "count": 1},
	OASIS: {"name": "Oase", "sprite": "oasis", "model": "obj_oasis", "count": 1},
	LOOKOUT: {"name": "Aussichtsturm", "sprite": "lookout", "model": "obj_lookout", "count": 1},
	ARENA: {"name": "Arena", "sprite": "arena", "model": "obj_arena", "count": 1},
	FOUNTAIN: {"name": "Gluecksbrunnen", "sprite": "fountain", "model": "obj_fountain", "count": 1},
	TEMPLE: {"name": "Tempel", "sprite": "temple", "model": "obj_temple", "count": 1},
	TREE: {"name": "Baum des Wissens", "sprite": "tree", "model": "obj_tree", "count": 1},
	WITCH_HUT: {"name": "Hexenhuette", "sprite": "witch_hut", "model": "obj_witch_hut", "count": 1},
	MAGIC_SHRINE: {"name": "Schrein der Magie", "sprite": "magic_shrine", "model": "obj_magic_shrine", "count": 1},
	PRISON: {"name": "Gefaengnis", "sprite": "prison", "model": "obj_prison", "count": 1},
	TRADING_POST: {"name": "Handelsposten", "sprite": "trading_post", "model": "obj_trading_post", "count": 1},
}

# Zahlen der Wirkungen.
const CAMPFIRE_GOLD_MIN := 200
const CAMPFIRE_GOLD_MAX := 500
const CAMPFIRE_RES_MIN := 3
const CAMPFIRE_RES_MAX := 6
const CAMPFIRE_RESOURCES := ["wood", "ore", "mercury", "sulfur", "crystal", "gems"]
const ARTIFACT_GUARD_MIN := 2
const ARTIFACT_GUARD_MAX := 4
const WATERMILL_GOLD := 500
const STABLES_MP := 12          # 3 Felder, bis Wochenende auf max_mp
const OASIS_MP := 8             # 2 Felder sofort
const LOOKOUT_SIGHT := 7
const ARENA_BONUS := 2
const FOUNTAIN_LUCK := 1
const TEMPLE_MORALE := 1
const MAGIC_SHRINE_MAX_LEVEL := 3
# Handelsposten: besser als der Markt in der Stadt (Kauf billiger,
# Verkauf teurer) - dafuer muss man hinlaufen.
const TRADE_BUY_PCT := 80
const TRADE_SELL_PCT := 130
# Ein befreiter Gefangener war schon unterwegs: etwas staerker als ein
# frisch angeworbener Held.
const PRISON_UNITS := 4
const PRISON_STATS := 1


static func is_new_kind(kind: int) -> bool:
	return kind >= FIRST and kind <= LAST


static func name_of(kind: int) -> String:
	return String((CATALOG.get(kind, {}) as Dictionary).get("name", "?"))


static func sprite_of(kind: int) -> String:
	return String((CATALOG.get(kind, {}) as Dictionary).get("sprite", ""))


static func model_of(kind: int) -> String:
	return String((CATALOG.get(kind, {}) as Dictionary).get("model", ""))


# Art -> Anzahl, fuer den Platzierungsplan.
static func plan() -> Dictionary:
	var out: Dictionary = {}
	for k in CATALOG.keys():
		out[int(k)] = int((CATALOG[k] as Dictionary).get("count", 1))
	return out


# Wird beim Betreten aufgehoben und verschwindet von der Karte.
static func is_pickup(kind: int) -> bool:
	return kind == CAMPFIRE or kind == ARTIFACT


# Steht eine Wache davor? Nur Artefakte - alles andere ist wie die
# Schreine frei zugaenglich.
static func is_guarded(kind: int) -> bool:
	return kind == ARTIFACT


# Beute eines Lagerfeuers, deterministisch aus einem Hash.
static func campfire_loot(h: int) -> Dictionary:
	var rng := RandomNumberGenerator.new()
	rng.seed = h
	return {
		"gold": rng.randi_range(CAMPFIRE_GOLD_MIN / 10, CAMPFIRE_GOLD_MAX / 10) * 10,
		"resource": String(CAMPFIRE_RESOURCES[rng.randi_range(0, CAMPFIRE_RESOURCES.size() - 1)]),
		"amount": rng.randi_range(CAMPFIRE_RES_MIN, CAMPFIRE_RES_MAX),
	}


# Welche Faehigkeit lehrt die Hexenhuette diesem Helden? Dieselbe Auswahl
# wie beim Stufenaufstieg (Slots, Konflikte, Hoechststufe), aber nur EIN
# Angebot und ohne Wahl. "" = nichts mehr zu lernen.
static func witch_skill(skills_lib, have: Dictionary, h: int) -> String:
	var rng := RandomNumberGenerator.new()
	rng.seed = h
	var offer: Array = skills_lib.offer(rng, have)
	return String(offer[0]) if not offer.is_empty() else ""


# Welchen Zauber lehrt der Schrein? Einer, den der Held noch NICHT kennt,
# bis Stufe MAGIC_SHRINE_MAX_LEVEL - auch aus fremden Schulen; genau das
# macht den Schrein wertvoll. "" = der Held kennt schon alles.
static func shrine_spell(spells_lib, known: Array, h: int) -> String:
	var pool: Array = []
	for sid in spells_lib.IMPLEMENTED:
		var s: String = String(sid)
		if known.has(s) or int(spells_lib.level_of(s)) > MAGIC_SHRINE_MAX_LEVEL:
			continue
		pool.append(s)
	if pool.is_empty():
		return ""
	return String(pool[absi(h) % pool.size()])


static func trade_buy_price(market_price: int) -> int:
	return maxi(1, market_price * TRADE_BUY_PCT / 100)


static func trade_sell_price(market_price: int) -> int:
	return maxi(1, market_price * TRADE_SELL_PCT / 100)
