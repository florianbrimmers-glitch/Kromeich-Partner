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
# Dritte Welle (It. 79): Behausungen und Kreaturenbanken.
const DWELLING := 24       # bewacht; danach Kreaturen anwerben, Zuwachs je Woche
const CRYPT := 25          # Kreaturenbank: Untote, Gold + Artefakt
const DWARF_TREASURY := 26 # Kreaturenbank: Zwerge, Gold + Edelsteine
const DRAGON_HOARD := 27   # Kreaturenbank: Drache, viel Gold + Artefakt
# Vierte Welle (It. 80).
const PORTAL := 28         # Teleporter, immer paarweise
const SEER_HUT := 29       # Seherhuette: Auftrag "bring mir ..." gegen Lohn
# Fuenfte Welle (It. 82): Paesse.
const BORDER_GATE := 30    # Grenztor im Pass, offen nur mit dem Schluessel seiner Farbe
const KEYMASTER := 31      # Zelt des Schluesselmeisters, gibt den Schluessel

const FIRST := CAMPFIRE
const LAST := KEYMASTER

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
	DWELLING: {"name": "Behausung", "sprite": "dwelling", "model": "obj_dwelling", "count": 3},
	CRYPT: {"name": "Krypta", "sprite": "crypt", "model": "obj_crypt", "count": 1},
	DWARF_TREASURY: {"name": "Zwergenschatz", "sprite": "dwarf_treasury", "model": "obj_dwarf_treasury", "count": 1},
	DRAGON_HOARD: {"name": "Drachenhort", "sprite": "dragon_hoard", "model": "obj_dragon_hoard", "count": 1},
	PORTAL: {"name": "Portal", "sprite": "portal", "model": "obj_portal", "count": 4},
	SEER_HUT: {"name": "Seherhuette", "sprite": "seer_hut", "model": "obj_seer_hut", "count": 2},
	# Tore und Schluesselmeister setzt der Kartengenerator mit den Paessen,
	# nicht der Zufallsplan - "count" ist hier die Zahl der Riegel.
	BORDER_GATE: {"name": "Grenztor", "sprite": "border_gate", "model": "obj_gate_rot", "count": 2},
	KEYMASTER: {"name": "Schluesselmeister", "sprite": "keymaster", "model": "obj_keymaster_rot", "count": 2},
}

# --- Gebirgsriegel und Paesse (It. 82) ---------------------------------
#
# Zwei Gebirgsriegel quer ueber die Karte teilen sie in drei Zonen. Jeder
# Riegel ist zwei Felder dick und hat genau ZWEI Paesse: in einem steht
# ein Grenztor (offen mit dem Schluessel seiner Farbe), im anderen ein
# starker Passwaechter. Damit ist jede Zone erreichbar - kaempfend oder mit
# Schluessel -, und das Tor ist kein Hindernis zum Drumherumlaufen.
#
# Die KI hat keine Schluessel: fuer sie sind Tore immer zu, sie geht ueber
# den Waechter-Pass (Monster halten die KI-Wegsuche nicht auf).
const RIDGE_ROWS := [8, 17]      # Grundreihe je Riegel (Karte 26 hoch)
const RIDGE_JITTER := 1          # Riegel schlaengelt sich um +-1 Reihe
const PASS_MIN_GAP := 5          # Mindestabstand der zwei Paesse eines Riegels
const KEY_COLORS := ["rot", "blau"]
const KEY_TINT := {"rot": Color(0.85, 0.25, 0.2), "blau": Color(0.25, 0.45, 0.9)}
const PASS_GUARD_STRENGTH := 8
const KEYMASTER_MIN_DIST := 3


static func gate_model(color: String) -> String:
	return "obj_gate_%s" % color


static func keymaster_model(color: String) -> String:
	return "obj_keymaster_%s" % color


static func gate_sprite(color: String) -> String:
	return "border_gate_%s" % color


static func keymaster_sprite(color: String) -> String:
	return "keymaster_%s" % color

# Auftraege der Seherhuetten: was sie wollen, was sie geben. Die Auswahl
# je Huette steht beim Platzieren fest (Feld `quest`).
const SEER_QUESTS := [
	{"want": {"ore": 10}, "gold": 1500, "artifact": false},
	{"want": {"wood": 10}, "gold": 1500, "artifact": false},
	{"want": {"gems": 5}, "gold": 0, "artifact": true},
	{"want": {"crystal": 5}, "gold": 0, "artifact": true},
	{"want": {"mercury": 4, "sulfur": 4}, "gold": 2500, "artifact": false},
	{"want": {"gold": 3000}, "gold": 0, "artifact": true},
]

# Ein Modell je Minenart (It. 80) - vorher war jede Mine derselbe Stollen.
const MINE_MODELS := {
	"gold": "obj_mine",
	"wood": "obj_mine_wood",
	"ore": "obj_mine_ore",
	"mercury": "obj_mine_mercury",
	"sulfur": "obj_mine_sulfur",
	"crystal": "obj_mine_crystal",
	"gems": "obj_mine_gems",
}

# Kreaturenbanken: feste Wache (Armee, kein Staerke-Wert) und Beute. Die
# Wachen sind bewusst Mittel- bis Spaetspiel - gruen faerbt die Karte sie
# erst mit einer gewachsenen Armee.
const BANKS := {
	CRYPT: {"army": {"nec_skeleton": 10, "nec_zombie": 6, "nec_wight": 3},
		"gold": 1500, "res": {}, "artifact": true},
	DWARF_TREASURY: {"army": {"elf_dwarf": 16},
		"gold": 2000, "res": {"crystal": 4, "gems": 4}, "artifact": false},
	DRAGON_HOARD: {"army": {"elf_goldwyrm": 1, "ork_roc": 2},
		"gold": 5000, "res": {"gems": 6}, "artifact": true},
}

# Behausungen: welche Kreaturen dort wohnen koennen - Stufe 1 bis 4 aller
# Fraktionen, wie die Aussen-Behausungen in Heroes.
const DWELLING_MAX_TIER := 4
# Der Vorrat waechst je Woche um den Zuwachs der Kreatur, hoechstens bis
# zum Vierfachen - wer vier Wochen nicht kommt, verliert nichts, wer zehn
# nicht kommt, schon.
const DWELLING_CAP_WEEKS := 4
const DWELLING_GUARD := 3

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
	return kind == ARTIFACT or kind == DWELLING or BANKS.has(kind)


static func is_bank(kind: int) -> bool:
	return BANKS.has(kind)


# Gesamtzahl der Bank-Wache (fuer Erfahrung und die Zahl auf der Karte).
static func bank_guard_count(kind: int) -> int:
	var n: int = 0
	var army: Dictionary = (BANKS.get(kind, {}) as Dictionary).get("army", {}) as Dictionary
	for k in army.keys():
		n += int(army[k])
	return n


# Kreatur einer Behausung, deterministisch aus einem Hash.
static func dwelling_unit(unit_lib, h: int) -> String:
	var pool: Array = []
	for uid in unit_lib.all_ids():
		var t: int = int(unit_lib.tier_of(String(uid)))
		if t >= 1 and t <= DWELLING_MAX_TIER:
			pool.append(String(uid))
	pool.sort()
	if pool.is_empty():
		return "men_spearman"
	return String(pool[absi(h) % pool.size()])


# Vorrat einer Behausung in Woche `week`: der gespeicherte Stand plus der
# Zuwachs der Wochen seitdem, gedeckelt. Wird beim Besuch ausgerechnet,
# damit es keinen Wochen-Haken braucht.
static func dwelling_pool(obj: Dictionary, growth: int, week: int) -> int:
	var base: int = int(obj.get("pool", 0))
	var since: int = maxi(0, week - int(obj.get("pool_week", week)))
	return mini(base + growth * since, growth * DWELLING_CAP_WEEKS)


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


static func seer_quest(i: int) -> Dictionary:
	return SEER_QUESTS[clampi(i, 0, SEER_QUESTS.size() - 1)] as Dictionary


static func mine_model(resource: String) -> String:
	return String(MINE_MODELS.get(resource, "obj_mine"))
