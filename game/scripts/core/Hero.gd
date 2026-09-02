class_name Hero
extends RefCounted

# Artefakt-Regeln per preload (Android-class_name-Falle wie ueberall
# sonst). Artifacts.gd laedt selbst nichts nach - kein Preload-Kreis.
const Art := preload("res://scripts/core/Artifacts.gd")

# Minimaler Helden-Zustand fuer die Weltkarte.
# Position in Kachel-Koordinaten, Bewegungspunkte pro Tag.
#
# army ist ein Dictionary { unit_id: count }. Rekrutierung, Verluste und
# Anzeige laufen ueber die Helfer add_units/remove_units/total_count.
#
# Stack-Limit: max 6 unterschiedliche Einheiten-Typen pro Held. Ein
# neuer Typ wird abgewiesen, wenn schon 6 Slots belegt sind - bestehende
# Stacks koennen unbegrenzt wachsen. Wert 6 (statt HoMM3-klassischer 7),
# damit auch auf schmalen Handy-Displays die Armee-Zeile lesbar bleibt.
const MAX_ARMY_SLOTS: int = 6

var position: Vector2i
var max_mp: int
var mp: int
# Mehr-Ressourcen-Boerse (M3). "gold" bleibt als Property erhalten,
# damit die ~24 bestehenden .gold-Zugriffe im Code unveraendert
# weiterlaufen - sie lesen/schreiben transparent ins Wallet.
var wallet: Wallet = Wallet.new()
var gold: int:
	get:
		return wallet.get_amount("gold")
	set(value):
		wallet.set_amount("gold", value)
var army: Dictionary = {}
# Progression: Level startet bei 1; XP sammelt sich monoton. Der
# WorldMapScreen bestimmt per LEVEL_THRESHOLDS, wann ein Level-Up faellt.
var xp: int = 0
var level: int = 1

# --- Primaerwerte und Skills (M7 Teil 1) ---------------------------------
# att/def gehen als getrennte Boni in die Kampfformel (CombatMath.damage
# nimmt att_bonus und def_bonus schon immer entgegen - vorher fuellte beide
# derselbe Pauschalwert, ein Angriffsbonus hob also auch die Verteidigung).
# spell_power/knowledge wachsen noch NICHT: sie wirken erst mit den Zaubern
# (M8). Die Felder stehen trotzdem hier, damit der Save schon passt.
# Rohwerte aus Stufenaufstiegen und Schreinen. Was der Rest des Spiels
# liest, ist die Summe aus Rohwert UND getragenen Artefakten (It. 51) -
# deshalb sind att/def/spell_power/knowledge Eigenschaften mit Getter.
#
# Dasselbe Muster wie `_hero` in M13a und aus demselben Grund: die Werte
# werden an rund neunzig Stellen GELESEN und nur an zwei geschrieben
# (add_primary und from_dict). Ein Getter laesst alle Lesestellen
# unveraendert. Der Setter schreibt den Rohwert, damit `hero.knowledge =
# 4` in den Tests weiter tut, was es soll.
var att_base: int = 0
var def_base: int = 0
var spell_power_base: int = 0
var knowledge_base: int = 0

# Getragene Artefakte, hoechstens Artifacts.MAX_SLOTS Stueck.
var artifacts: Array = []

# NIE NEGATIV. Die Klinge des Zorns gibt +3 Angriff fuer -1 Verteidigung;
# traegt ein Held sie ohne andere Verteidigungsquelle, kaeme -1 heraus und
# ginge so in die Kampfformel. In HoMM3 fallen Primaerwerte nicht unter
# null, und ein negativer Bonus, der den Gegner STAERKER macht als gar
# keine Ruestung, waere schwer zu erklaeren. Der Rohwert bleibt unberuehrt
# - legt der Held das Artefakt ab, ist der alte Wert wieder da.
# Und der ROHWERT wird beim Schreiben geklemmt: ein negativer Rohwert
# (kaputter Spielstand) wuerde durch die Summen-Klemme nur maskiert - ein
# +2-Artefakt laese sich dann als 0, ohne sichtbaren Grund.
var att: int:
	get: return _eff(att_base, "attack")
	set(value): att_base = maxi(0, value)
var def: int:
	get: return _eff(def_base, "defense")
	set(value): def_base = maxi(0, value)
var spell_power: int:
	get: return _eff(spell_power_base, "spell_power")
	set(value): spell_power_base = maxi(0, value)
var knowledge: int:
	get: return _eff(knowledge_base, "knowledge")
	set(value): knowledge_base = maxi(0, value)


# Wirksamer Wert: Rohwert plus Artefakte, nie unter null. EINE Stelle fuer
# die Regel statt vier Kopien.
#
# Bekannte Kante, bewusst so gelassen: traegt ein Held die Klinge des Zorns
# (-1 Verteidigung) bei Rohwert 0, zeigt Verteidigung 0 - und ein Schrein
# (+1 Rohwert) hebt die Anzeige nicht, weil 1 - 1 wieder 0 ist. Der Punkt
# ist da (legt er die Klinge ab, sind es 1), er ist nur solange nicht
# sichtbar. Das ist die Arithmetik eines Artefakts mit Minus, kein Fehler.
func _eff(base: int, stat: String) -> int:
	return maxi(0, base + Art.bonus(artifacts, stat))


# --- Artefakte anlegen und ablegen (It. 52) -------------------------------
#
# Die Regeln (bekannte ID, nicht doppelt, hoechstens MAX_SLOTS) stehen HIER
# und nicht an jeder Stelle, die die Liste anfasst. Die Code-Review zu It. 51
# fand sie in vier Kopien - und from_dict hatte die Obergrenze vergessen.
func can_equip(aid: String) -> bool:
	return Art.exists(aid) and not artifacts.has(aid) \
		and artifacts.size() < Art.MAX_SLOTS


func equip(aid: String) -> bool:
	if not can_equip(aid):
		return false
	artifacts.append(aid)
	return true


func unequip(aid: String) -> bool:
	if not artifacts.has(aid):
		return false
	artifacts.erase(aid)
	return true
# {skill_id: stufe 1..3}
var skills: Dictionary = {}
# Mana (M8). Der Hoechstwert leitet sich aus `knowledge` ab und wird
# deshalb NICHT gespeichert - nur der aktuelle Stand.
var mana: int = 0


func skill_tier(skill_id: String) -> int:
	return int(skills.get(skill_id, 0))


func raise_skill(skill_id: String, max_tier: int = 3) -> int:
	var t: int = min(max_tier, skill_tier(skill_id) + 1)
	skills[skill_id] = t
	return t


func add_primary(stat_id: String, amount: int = 1) -> void:
	match stat_id:
		# Auf den ROHWERT, nicht auf die Summe: `att += amount` waere
		# ueber den Getter gelaufen und haette den Artefakt-Bonus in den
		# Rohwert einbetoniert - beim Ablegen des Artefakts waere er
		# geblieben.
		"attack": att_base += amount
		"defense": def_base += amount
		"spell_power": spell_power_base += amount
		"knowledge": knowledge_base += amount

# Standard-Bewegung in PUNKTEN, nicht in Feldern: seit M7 Teil 2 kostet
# ein flaches Feld Movement.UNIT (4) Punkte. 48 sind also 12 Felder - der
# alte Vorgabewert, nur in der feineren Einheit.
func _init(start: Vector2i, max_movement: int = 48) -> void:
	position = start
	max_mp = max_movement
	mp = max_movement

func end_turn() -> void:
	mp = max_mp

func total_count() -> int:
	var t: int = 0
	for k in army.keys():
		t += int(army[k])
	return t

func can_add_unit(unit_id: String) -> bool:
	# Stack existiert schon -> Count-Erhoehung ist immer ok.
	# Stack neu -> nur wenn noch ein Slot frei ist.
	if army.has(unit_id):
		return true
	return army.size() < MAX_ARMY_SLOTS

func add_units(unit_id: String, count: int) -> void:
	if count <= 0:
		return
	if not can_add_unit(unit_id):
		return
	army[unit_id] = int(army.get(unit_id, 0)) + count

func remove_units(unit_id: String, count: int) -> void:
	if count <= 0 or not army.has(unit_id):
		return
	var c: int = int(army[unit_id]) - count
	if c <= 0:
		army.erase(unit_id)
	else:
		army[unit_id] = c

func count_of(unit_id: String) -> int:
	return int(army.get(unit_id, 0))

func apply_casualties(cas: Dictionary) -> void:
	for k in cas.keys():
		remove_units(String(k), int(cas[k]))

# Proportionaler Abzug (fuer Auto-Resolve-Kaempfe ohne Overlay, z.B.
# Gegner-KI nimmt Wache ein). Verteilt die Verluste gleichmaessig auf
# alle Stacks. Runden-Rest faellt auf den groessten Stack.
func apply_proportional_losses(total_loss: int) -> void:
	if total_loss <= 0 or army.is_empty():
		return
	var total: int = total_count()
	if total_loss >= total:
		army.clear()
		return
	var removed: int = 0
	var biggest_id: String = ""
	var biggest_count: int = -1
	var new_army: Dictionary = {}
	for k in army.keys():
		var c: int = int(army[k])
		var share: int = int(float(c) / float(total) * float(total_loss))
		removed += share
		var left: int = c - share
		new_army[k] = left
		if left > biggest_count:
			biggest_count = left
			biggest_id = String(k)
	var leftover: int = total_loss - removed
	if leftover > 0 and biggest_id != "":
		new_army[biggest_id] = max(0, int(new_army[biggest_id]) - leftover)
	for k in new_army.keys():
		if int(new_army[k]) <= 0:
			new_army.erase(k)
	army = new_army

# Kurzform fuer Anzeige, z.B. "5 Sw / 3 Bw / 2 Ri". Iteriert in
# Fraktions-Reihenfolge (UnitType.ORDER), damit die Anzeige stabil ist.
func army_summary() -> String:
	if army.is_empty():
		return "0"
	var parts: Array = []
	for uid in UnitType.all_ids():
		if army.has(uid) and int(army[uid]) > 0:
			parts.append("%d %s" % [int(army[uid]), UnitType.short_of(uid)])
	if parts.is_empty():
		for k in army.keys():
			parts.append("%d %s" % [int(army[k]), String(k).substr(0, 2)])
	return " / ".join(parts)

# --- Save/Load (M1) ---
# to_dict/from_dict sind bewusst tolerant: fehlende Keys -> Defaults,
# damit aeltere Saves nach Feld-Ergaenzungen ohne Migration laden.
func to_dict() -> Dictionary:
	return {
		"position": SaveCodec.v2i(position),
		"mp": mp,
		"max_mp": max_mp,
		"wallet": wallet.to_dict(),
		"army": army.duplicate(),
		"xp": xp,
		"level": level,
		# ROHWERTE speichern. Wuerde hier die Summe stehen, waechse der
		# Held bei jedem Speichern und Laden um seine Artefakte.
		"att": att_base,
		"def": def_base,
		"spell_power": spell_power_base,
		"knowledge": knowledge_base,
		"artifacts": artifacts.duplicate(),
		"skills": skills.duplicate(),
		"mana": mana,
	}

static func from_dict(d: Dictionary) -> Hero:
	var h := Hero.new(SaveCodec.to_v2i(d.get("position"), Vector2i.ZERO),
		int(d.get("max_mp", 48)))
	h.mp = int(d.get("mp", h.max_mp))
	if d.has("wallet"):
		h.wallet = Wallet.from_dict(d["wallet"])
	else:
		# v1-Saves (vor M3) kannten nur "gold" - tolerant mappen,
		# kein SAVE_VERSION-Bump noetig.
		h.gold = int(d.get("gold", 0))
	h.army = SaveCodec.int_dict(d.get("army", {}))
	h.xp = int(d.get("xp", 0))
	h.level = int(d.get("level", 1))
	# M7: reine Feld-Ergaenzung, also KEIN SAVE_VERSION-Bump - alte Saves
	# laden mit Nullwerten (siehe Kommentar oben bei to_dict).
	# Artefakte VOR den Werten: die Setter schreiben zwar nur den Rohwert,
	# aber die Reihenfolge macht die Absicht deutlich.
	# Tolerantes Feld, also KEIN SAVE_VERSION-Bump - ein Spielstand ohne
	# Artefakte laedt mit leerer Liste (dieselbe Begruendung wie bei den
	# Primaerwerten in M7).
	# Ueber equip(): unbekannte IDs (ausgemustertes Artefakt) und Doppelte
	# fallen raus, und mehr als MAX_SLOTS nimmt der Held nicht - ein
	# uebervoller Stand (von Hand oder aus einem alten Fehler) laedt sauber
	# statt mit vier Boni.
	for a in (d.get("artifacts", []) as Array):
		h.equip(String(a))
	h.att = int(d.get("att", 0))
	h.def = int(d.get("def", 0))
	h.spell_power = int(d.get("spell_power", 0))
	h.knowledge = int(d.get("knowledge", 0))
	h.skills = SaveCodec.int_dict(d.get("skills", {}))
	h.mana = int(d.get("mana", 0))
	return h
