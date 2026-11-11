class_name Garrison
extends RefCounted

# Stadt-Garnison: echte Einheiten statt einer Staerke-Zahl.
#
# Eine Garnison ist dasselbe Format wie `Hero.army` - ein Dictionary
# { unit_id: count }. Damit passen Held und Stadt zusammen: Einheiten
# lassen sich hin- und herschieben, ohne umzurechnen, und der Kampf
# bekommt in beiden Faellen dieselben Stacks.
#
# Vorher hielt jede Stadt nur `garrison: int` (2-5), aus dem beim Angriff
# Stacks synthetisiert wurden - Phantom-Truppen, die niemand rekrutiert
# hatte. Die Spielerstadt startete sogar mit 0 und war damit voellig
# unverteidigt (die Stadtmauer aus M9 schuetzte niemanden).
#
# Rein statisch wie Abilities/Morale/StatusFx, Einbindung per preload
# (Android-class_name-Falle, siehe TacticalBattleScreen-Kopf).


# Neutrale Stadt bestuecken: die ersten drei Tiers der Stadt-Fraktion
# nach derselben Staffelung, die vorher die Wachen-Synthese benutzte -
# klein = nur T1, mittel + T2, gross + T3.
static func synth(fid: int, strength: int) -> Dictionary:
	var out: Dictionary = {}
	if strength <= 0:
		return out
	var ids: Array = UnitType.recruitable_ids_for_faction(fid)
	if ids.is_empty():
		return {"men_spearman": strength}
	var t1: String = String(ids[0])
	var t2: String = String(ids[1]) if ids.size() > 1 else t1
	var t3: String = String(ids[2]) if ids.size() > 2 else t2
	if strength <= 2:
		out[t1] = strength
		return out
	if strength <= 5:
		var mid: int = max(1, int(round(float(strength) * 0.4)))
		out[t1] = strength - mid
		add(out, t2, mid)
		return out
	var high: int = max(1, int(round(float(strength) * 0.2)))
	var mid2: int = max(1, int(round(float(strength) * 0.3)))
	out[t1] = max(1, strength - mid2 - high)
	add(out, t2, mid2)
	add(out, t3, high)
	return out


static func total(army: Dictionary) -> int:
	var t: int = 0
	for k in army.keys():
		t += int(army[k])
	return t


static func is_empty(army: Dictionary) -> bool:
	return total(army) <= 0


static func add(army: Dictionary, uid: String, n: int) -> void:
	if n <= 0:
		return
	army[uid] = int(army.get(uid, 0)) + n


static func remove(army: Dictionary, uid: String, n: int) -> void:
	if n <= 0 or not army.has(uid):
		return
	var left: int = int(army[uid]) - n
	if left <= 0:
		army.erase(uid)
	else:
		army[uid] = left


# Einheiten von einer Armee in eine andere schieben (It. 44).
#
# EINE Funktion fuer alle Umschlagstellen: Held <-> Held im Feld, Held <->
# Garnison in der Stadt. Rueckgabe ist die Zahl, die WIRKLICH gewandert
# ist - sie kann kleiner sein als gewuenscht, denn `to` hat ein
# Slot-Limit (Hero.MAX_ARMY_SLOTS) und `from` hat vielleicht weniger.
#
# `max_slots` <= 0 heisst "kein Limit" (die Stadt-Garnison kennt keins).
static func transfer(from: Dictionary, to: Dictionary, uid: String,
		n: int, max_slots: int = 0) -> int:
	if n <= 0 or not from.has(uid):
		return 0
	var have: int = int(from[uid])
	if have <= 0:
		return 0
	# Ein NEUER Stack braucht einen freien Slot; ein bestehender waechst
	# ohne Grenze. Genau die Regel aus Hero.can_add_unit - hier, damit
	# jede Umschlagstelle sie bekommt und nicht nur der Held.
	if max_slots > 0 and not to.has(uid) and to.size() >= max_slots:
		return 0
	var moved: int = mini(n, have)
	remove(from, uid, moved)
	add(to, uid, moved)
	return moved


static func apply_casualties(army: Dictionary, cas: Dictionary) -> void:
	for k in cas.keys():
		remove(army, String(k), int(cas[k]))


# Stacks fuer den Kampf-Screen, in stabiler Fraktions-/Tier-Reihenfolge.
static func to_stacks(army: Dictionary) -> Array:
	var out: Array = []
	for uid in UnitType.all_ids():
		var c: int = int(army.get(uid, 0))
		if c > 0:
			out.append({"type": String(uid), "count": c})
	# Unbekannte Ids (z.B. aus einem fremden Save) nicht verlieren.
	for k in army.keys():
		if not UnitType.all_ids().has(String(k)) and int(army[k]) > 0:
			out.append({"type": String(k), "count": int(army[k])})
	return out


# Aus dem Kampf zurueckkommende Restbestaende (aus stacks) wieder als
# Garnison-Dictionary. Wird nach Verteidigungskaempfen gebraucht.
static func from_stacks(stacks: Array) -> Dictionary:
	var out: Dictionary = {}
	for s in stacks:
		var d: Dictionary = s as Dictionary
		add(out, String(d.get("type", "")), int(d.get("count", 0)))
	return out


# Kurzform fuer die Anzeige, z.B. "5 Sp / 3 Ar".
static func summary(army: Dictionary) -> String:
	if is_empty(army):
		return "leer"
	var parts: Array = []
	for uid in UnitType.all_ids():
		var c: int = int(army.get(uid, 0))
		if c > 0:
			parts.append("%d %s" % [c, UnitType.short_of(String(uid))])
	return " / ".join(parts)
