extends RefCounted

# Effekt-Schicht fuer den Kampf (Iteration 17).
#
# Reine DATEN-Schicht: kein Node, keine Szene, kein Zeichnen. Ein Effekt
# ist ein Dictionary in einer Array-Queue; `advance()` laesst die Zeit
# laufen und raeumt abgelaufene Effekte weg. WO gezeichnet wird,
# entscheidet der TacticalBattleScreen - dieses Modul weiss nur, WIE WEIT
# ein Effekt fortgeschritten ist. Damit ist die ganze Schicht headless
# testbar, obwohl der echte Screen ohne Display nicht rendert.
#
# Eingebunden per `preload` (NICHT `class_name`) - dieselbe Android-
# Export-Falle wie bei Abilities/StatusFx/Morale/Garrison. Alias im
# Screen ist `Vfx`, weil `Fx` dort schon StatusFx belegt.
#
# Bremse fuer die Zugkette: solange `busy()` true ist, wartet
# `TacticalBattleScreen._advance()`. Tests setzen `fx_speed = 0.0`, dann
# ist jeder Effekt nach einem `advance()` abgelaufen und die Kette
# verhaelt sich exakt wie vor dieser Iteration.

# --- Effekt-Arten ---------------------------------------------------------
# Namen als Konstanten, damit ein Tippfehler beim Spawn nicht still
# einen Effekt erzeugt, den niemand zeichnet.
const LUNGE := "lunge"           # Angreifer macht einen Ausfallschritt
const PROJECTILE := "projectile" # Pfeil/Bolzen/Stein fliegt
const IMPACT := "impact"         # Treffer-Blitz am Ziel
const NUMBER := "number"         # Schadenszahl steigt auf
const DEATH := "death"           # Stack zerfaellt
const SHAKE := "shake"           # ganzes Schlachtfeld wackelt
const HEAL := "heal"             # Heilung/Regeneration
const POPUP := "popup"           # Wort-Einblendung (Moral!, Glueck!)
const WALL_BREAK := "wall_break" # Mauersegment zerbricht
const MOVE := "move"             # Token gleitet zum Zielfeld
# Unsichtbare Denkpause der KI (It. 38). WARUM als Effekt und nicht als
# Timer: die Zugkette hing an get_tree().create_timer() - einer ZWEITEN
# Uhr, die fx_speed ignoriert. Headless laeuft keine Echtzeit, der Timer
# feuerte also nie und der Kampf stand still (der Durchspiel-Test hielt
# das faelschlich fuer einen Patt). Als Effekt laeuft die Pause auf
# derselben Uhr wie alles andere: sie skaliert mit fx_speed und
# verschwindet bei fx_speed = 0 sofort.
const PAUSE := "pause"

# Dauer je Art in Sekunden. Alle an einer Stelle, damit sich das Tempo
# des Kampfes zentral drehen laesst.
const DUR := {
	LUNGE: 0.18,
	PROJECTILE: 0.28,
	IMPACT: 0.22,
	NUMBER: 0.70,
	DEATH: 0.45,
	SHAKE: 0.25,
	HEAL: 0.40,
	POPUP: 0.80,
	WALL_BREAK: 0.35,
	MOVE: 0.22,
	PAUSE: 0.30,
}

# Effekte, die die Zugkette AUFHALTEN. Schadenszahlen und Popups laufen
# nebenher aus - sonst steht der Kampf 0.8 s pro Schlag still.
const BLOCKING := [LUNGE, PROJECTILE, IMPACT, DEATH, WALL_BREAK, MOVE, PAUSE]

# Ab diesem Schaden wackelt der Bildschirm. Ohne Schwelle zappelt er bei
# jedem Goblin-Kratzer.
const SHAKE_MIN_DAMAGE := 40


static func new_queue() -> Array:
	return []


# Legt einen Effekt an. `cfg` traegt die Art-spezifischen Felder (Positionen
# in KACHEL-Koordinaten, Text, Farbe, ...); der Screen rechnet sie beim
# Zeichnen in Pixel um, damit ein Resize des Fensters nichts kaputt macht.
# `cfg["delay"]` staffelt den Start: t laeuft von -delay hoch, der Effekt
# gilt bis 0 als "pending" und wird nicht gezeichnet. Ohne das blitzt der
# Treffer, waehrend der Pfeil noch fliegt.
static func spawn(queue: Array, kind: String, cfg: Dictionary = {}) -> Dictionary:
	var e: Dictionary = cfg.duplicate()
	e.erase("delay")
	e["kind"] = kind
	e["t"] = -maxf(0.0, float(cfg.get("delay", 0.0)))
	e["dur"] = float(cfg.get("dur", DUR.get(kind, 0.25)))
	queue.append(e)
	return e


# Laesst die Zeit laufen. `speed` 0.0 = alles sofort fertig (Tests).
# Liefert true, wenn sich etwas geaendert hat - der Screen zeichnet dann
# neu, statt jeden Frame blind zu invalidieren.
static func advance(queue: Array, delta: float, speed: float = 1.0) -> bool:
	if queue.is_empty():
		return false
	if speed <= 0.0:
		queue.clear()
		return true
	var step: float = delta * speed
	var i: int = queue.size() - 1
	while i >= 0:
		var e: Dictionary = queue[i]
		e["t"] = float(e["t"]) + step
		if float(e["t"]) >= float(e["dur"]):
			queue.remove_at(i)
		i -= 1
	return true


# Fortschritt 0..1 eines Effekts.
static func progress(e: Dictionary) -> float:
	var d: float = float(e.get("dur", 0.25))
	if d <= 0.0:
		return 1.0
	return clampf(float(e.get("t", 0.0)) / d, 0.0, 1.0)


# Noch nicht gestartet (wartet auf seine Verzoegerung) - nicht zeichnen.
static func pending(e: Dictionary) -> bool:
	return float(e.get("t", 0.0)) < 0.0


# Bremse fuer die Zugkette: laeuft noch ein Effekt, der gesehen werden muss?
static func busy(queue: Array) -> bool:
	for e in queue:
		if BLOCKING.has(String(e.get("kind", ""))):
			return true
	return false


# Wie lange muss die Kette noch warten? Der Screen benutzt das als
# Timer-Dauer, statt jeden Frame nachzufragen.
static func busy_time_left(queue: Array) -> float:
	var worst: float = 0.0
	for e in queue:
		if not BLOCKING.has(String(e.get("kind", ""))):
			continue
		var left: float = float(e.get("dur", 0.0)) - float(e.get("t", 0.0))
		if left > worst:
			worst = left
	return worst


# Restzeit der laengsten laufenden Instanz EINER Art. Der Nahkampf
# benutzt das, um sich hinter einen noch laufenden Anmarsch zu staffeln -
# sonst gleitet die Einheit und schlaegt im selben Frame zu.
static func time_left_of(queue: Array, kind: String) -> float:
	var worst: float = 0.0
	for e in queue:
		if String(e.get("kind", "")) != kind:
			continue
		var left: float = float(e.get("dur", 0.0)) - float(e.get("t", 0.0))
		if left > worst:
			worst = left
	return worst


static func has_kind(queue: Array, kind: String) -> bool:
	for e in queue:
		if String(e.get("kind", "")) == kind:
			return true
	return false


static func of_kind(queue: Array, kind: String) -> Array:
	var out: Array = []
	for e in queue:
		if String(e.get("kind", "")) == kind:
			out.append(e)
	return out


# --- Kurven ---------------------------------------------------------------
# Reine Mathematik, damit der Screen keine Interpolation von Hand baut und
# die Tests die Bewegung ohne Display pruefen koennen.

static func ease_out(t: float) -> float:
	var x: float = clampf(t, 0.0, 1.0)
	return 1.0 - (1.0 - x) * (1.0 - x)


static func ease_in_out(t: float) -> float:
	var x: float = clampf(t, 0.0, 1.0)
	if x < 0.5:
		return 2.0 * x * x
	return 1.0 - 2.0 * (1.0 - x) * (1.0 - x)


# Hin und zurueck: 0 -> 1 -> 0. Fuer den Ausfallschritt, damit der
# Angreifer nicht auf dem Zielfeld stehen bleibt.
static func ping_pong(t: float) -> float:
	var x: float = clampf(t, 0.0, 1.0)
	return 1.0 - absf(x * 2.0 - 1.0)


# Parabel-Bogen von `from` nach `to`. `height` ist der Scheitel-Ausschlag
# senkrecht zur Verbindung (nach oben, weil y in Godot nach unten waechst).
# Bei t=0 exakt `from`, bei t=1 exakt `to` - darauf verlaesst sich der Test.
static func arc_point(from: Vector2, to: Vector2, t: float, height: float) -> Vector2:
	var x: float = clampf(t, 0.0, 1.0)
	var base: Vector2 = from.lerp(to, x)
	# 4*t*(1-t) ist 0 an beiden Enden, 1 in der Mitte.
	var lift: float = 4.0 * x * (1.0 - x) * height
	return base - Vector2(0.0, lift)


# Abklingendes Wackeln. Deterministisch aus t, damit zwei Frames mit
# gleichem t denselben Versatz liefern (wichtig fuer die Vorschau-Bilder).
static func shake_offset(t: float, amp: float) -> Vector2:
	var x: float = clampf(t, 0.0, 1.0)
	var decay: float = 1.0 - x
	return Vector2(
		sin(x * 54.0) * amp * decay,
		cos(x * 41.0) * amp * decay * 0.6)


# Einschlag-Geometrie in ZELLEN. Steht hier und nicht im Screen, weil
# preview_battle_fx.gd dieselben Werte zeichnet - zwei Zahlensaetze waeren
# nach der ersten Aenderung auseinandergelaufen. Der Ring startet ausserhalb
# der Token-Scheibe (0.40 Zellen), sonst liest er sich als Markierung auf
# der Einheit statt als Treffer.
const IMPACT_R0 := 0.34
const IMPACT_R1 := 0.88
const IMPACT_SPOKE_IN := 0.34
const IMPACT_SPOKE_OUT := 0.96
const IMPACT_SPOKES := 7


static func impact_radius(t: float) -> float:
	return IMPACT_R0 + (IMPACT_R1 - IMPACT_R0) * ease_out(t)


# [Innen-Radius, Aussen-Radius] eines Splitters, in Zellen.
static func impact_spoke(t: float) -> Array:
	var g: float = ease_out(t)
	return [IMPACT_SPOKE_IN + 0.26 * g, IMPACT_SPOKE_OUT * (0.34 + 0.66 * g)]


# Steigende, ausblendende Zahl: Versatz nach oben in ZELLEN und Alpha.
static func rise_fade(t: float) -> Array:
	var x: float = clampf(t, 0.0, 1.0)
	var up: float = ease_out(x) * 0.6
	# Erst die letzten 40 % blenden aus, sonst ist die Zahl nie lesbar.
	var a: float = 1.0 if x < 0.6 else 1.0 - (x - 0.6) / 0.4
	return [up, clampf(a, 0.0, 1.0)]


# --- Fertige Spawn-Helfer -------------------------------------------------
# Kapseln die Feld-Namen, damit der Screen nicht 12 mal dasselbe Dictionary
# von Hand baut und ein Tippfehler im Key nicht still einen Effekt
# unsichtbar macht.

static func hit(queue: Array, at: Vector2i, dmg: int, col: Color = Color(1, 1, 1),
		delay: float = 0.0) -> void:
	spawn(queue, IMPACT, {"at": at, "col": col, "delay": delay})
	spawn(queue, NUMBER, {"at": at, "text": str(dmg), "col": col, "delay": delay})
	if dmg >= SHAKE_MIN_DAMAGE:
		spawn(queue, SHAKE, {"amp": 6.0, "delay": delay})


# Rueckgabe: Flugdauer. Der Aufrufer benutzt sie als Verzoegerung fuer die
# Treffer-Effekte, damit der Einschlag ankommt, wenn das Geschoss da ist.
static func shot(queue: Array, from: Vector2i, to: Vector2i, high: bool = false) -> float:
	var d: float = DUR[PROJECTILE] * (1.6 if high else 1.0)
	spawn(queue, PROJECTILE, {
		"from": from, "to": to,
		"lift": 1.4 if high else 0.45,
		"dur": d,
	})
	return d


static func lunge(queue: Array, from: Vector2i, to: Vector2i) -> void:
	spawn(queue, LUNGE, {"from": from, "to": to})


static func died(queue: Array, at: Vector2i, uid: String, side: int,
		delay: float = 0.0) -> void:
	spawn(queue, DEATH, {"at": at, "uid": uid, "side": side, "delay": delay})


static func lunge_delay() -> float:
	# Treffer auf dem Scheitel des Ausfallschritts.
	return DUR[LUNGE] * 0.5


static func healed(queue: Array, at: Vector2i, amount: int) -> void:
	spawn(queue, HEAL, {"at": at})
	spawn(queue, NUMBER, {"at": at, "text": "+" + str(amount),
		"col": Color(0.55, 1.0, 0.60)})


static func popup(queue: Array, at: Vector2i, text: String, col: Color) -> void:
	spawn(queue, POPUP, {"at": at, "text": text, "col": col})


static func wall_break(queue: Array, at: Vector2i) -> void:
	spawn(queue, WALL_BREAK, {"at": at})
	spawn(queue, SHAKE, {"amp": 5.0})


static func moved(queue: Array, from: Vector2i, to: Vector2i, uid: String, side: int) -> void:
	spawn(queue, MOVE, {"from": from, "to": to, "uid": uid, "side": side})


# Unsichtbare Pause, die die Zugkette aufhaelt. Kein Zeichnen - der Screen
# kennt "pause" in _draw_effects gar nicht.
static func pause(queue: Array, seconds: float) -> Dictionary:
	return spawn(queue, PAUSE, {"dur": maxf(0.0, seconds)})
