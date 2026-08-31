extends Control

# Save/Load: statische Funktionen ueber preload statt Autoload-Identifier,
# damit headless Tools-Skripte (starten ohne Autoloads) die Szene laden
# koennen. Das Autoload /root/SaveManager wird nur fuer pending_load
# (Menue-Uebergabe) per get_node_or_null angesprochen.
const SaveLib := preload("res://scripts/core/SaveManager.gd")
# Helden-Skills (M7 Teil 1) per preload und ohne class_name - dieselbe
# Android-Export-Vorsicht wie bei Abilities/StatusFx im Kampf-Screen.
# Diese Schicht rechnet Skill-Stufen in Zahlen um; der Kampf-Screen
# bekommt nur Prozentwerte im Kontext und kennt keine Skills.
const Skills := preload("res://scripts/core/HeroSkills.gd")
# Zauber (M8). Loest die Formeln aus spells.json in Zahlen auf.
const Spells := preload("res://scripts/core/HeroSpells.gd")
# Wochenereignisse (M12). Leiten sich aus Seed und Wochennummer ab, es wird
# also nichts gespeichert.
const WeekFx := preload("res://scripts/core/WeekEvents.gd")
# Geraeusche (M11) ueber die statische Fassade - der Sfx-Autoload
# fehlt bei "godot --script tools/x.gd", ein direkter Aufruf wuerde
# dort zur Laufzeit scheitern und die Testfunktion abbrechen.
const Sound := preload("res://scripts/core/SfxBus.gd")
# Bewegungskosten (M7 Teil 2). EINE Tabelle fuer Karte, Pathfinder und den
# Dijkstra hier drunter; der Skill Wegfindung greift genau dort den
# Gelaende-Aufschlag ab.
const Move := preload("res://scripts/core/Movement.gd")
# Kreatur-Sprites fuers Heldenblatt (It. 29) - dieselben 28 SVGs wie im
# Kampf, aufgeloest in core/UnitArt.gd.
const UnitArt := preload("res://scripts/core/UnitArt.gd")
const Abil := preload("res://scripts/core/Abilities.gd")

# Weltkarten-Screen. Rendert eine deterministische Zufallskarte per
# _draw() und erlaubt den Helden per Tap zu bewegen. Dijkstra berechnet
# die Kosten aller erreichbaren Felder; unerreichbare werden abgedunkelt.

const MAP_WIDTH := 18
const MAP_HEIGHT := 26

const CITY_COUNT := 8
# Mindestabstand jeder Stadt zum Kartenrand in Feldern. Eine Stadt IST der
# Startpunkt des Helden, deshalb ist das keine Kosmetik.
const CITY_BORDER_MARGIN := 2
# Schonfrist ohne eigene Stadt, in Tagen (HoMM3-Regel, It. 38).
const LOSS_GRACE_DAYS := 7

# --- Helden anwerben (M13b) ----------------------------------------------
# HoMM3 laesst acht Helden zu; auf einer Handy-Karte mit 18x26 Feldern sind
# drei genug und die Oberflaeche bleibt bedienbar (Wechsel-Zeile im
# Heldenblatt, kein eigener Verwaltungsbildschirm).
const MAX_HEROES := 3
# 2500 Gold wie in der HoMM3-Taverne.
const HERO_HIRE_COST := {"gold": 2500}
# Ein angeworbener Held kommt nicht nackt: zwei Einheiten der
# Stadt-Fraktion. Ohne Truppen koennte er nur laufen und Objekte
# einsammeln, was ihn zu einem 2500 Gold teuren Boten machen wuerde.
const HERO_HIRE_UNITS := 2
const CITY_MIN_DIST := 7
const CITY_INCOME := 500
const OWNER_NEUTRAL := -1
const OWNER_HERO := 0
# Historischer Alias: OWNER_ENEMY == erste KI. Generisch wird eine KI
# ueber OWNER_AI_MIN..OWNER_AI_MAX adressiert. _is_ai_owner()/_ai_index
# kapseln die Abfrage, damit wir spaeter nicht Alle Vergleiche suchen.
const OWNER_ENEMY := 1
const OWNER_AI_MIN := 1
const OWNER_AI_MAX := 3

# Gegner-Held: Start-Werte, bewegt sich automatisch am Ende des Spielerzugs.
# Er startet mit Armee 0 und Gold 0, exakt wie der Spieler - keine
# Gratis-Resourcen. Sein Fortschritt haengt allein davon ab, was er in
# seinen Staedten baut (siehe _enemy_economy).
const ENEMY_BASE_MP := 40

# Gebaeude-Effekte
const BASE_MAX_MP := 40      # 10 Felder Flachland (Movement.UNIT = 4)
const MP_BONUS_SPAEHER := 8     # pro Spaeher in eigener Stadt (2 Felder)
const INCOME_MARKT := 200       # zusaetzlich pro Markt in eigener Stadt
const UNIT_COST := 150          # pro Einheit, benoetigt Kaserne

# Kalender (HoMM-Stil): 1 Zug = 1 Tag, 7 Tage = 1 Woche, 4 Wochen = 1
# Monat (28 Tage), 12 Monate = 1 Jahr. Anzeige im Header: "T3 W2 M1 J1".
const DAYS_PER_WEEK := 7
const WEEKS_PER_MONTH := 4
const MONTHS_PER_YEAR := 12


# Startgold: Spieler und Gegner beginnen mit diesem Betrag, damit der
# erste Zug nicht zwangslaeufig "Enter druecken und warten" ist - reicht
# genau fuer eine Kaserne (500 G).
const STARTING_GOLD := 500
const STARTING_UNIT_COUNT := 3

# Monster
const MONSTER_COUNT := 8
# Wandernde Monster (It. 35). Vorher war ein Monster "Staerke 1-3" und im
# Kampf 1-3 MENSCHLICHE Speertraeger - auf der Karte ein grauer Kreis mit
# Zahl. Jetzt hat jedes Monster eine echte Kreatur, deren Sprite auf der
# Karte steht und die im Kampf auch antritt.
#
# KRAFT-BUDGET IN GOLD (It. 38, korrigiert): eine Staerke entspricht
# MONSTER_GOLD_PER_STRENGTH Gold, und die Stackgroesse ergibt sich aus dem
# Preis der Kreatur. Nur Kreaturen, die EINZELN ins Budget passen (mit
# etwas Spielraum), kommen in Frage.
#
# It. 35 hat dafuer TREFFERPUNKTE genommen - das war falsch, und der
# Durchspiel-Test (It. 38) hat es aufgedeckt: der Spieler verlor in Zug 1
# seine ganze Armee an einen Kampf, den die Karte als machbar anzeigte.
# 30 HP als EIN Greif (Tier 3, Angriff 8, fliegend) schlagen 30 HP als
# drei Speertraeger (Tier 1, Angriff 4) muehelos. HP sind ueber die Tiers
# hinweg nicht vergleichbar - GOLD ist es, denn genau darauf ist die
# Balance getunt (Balance-Pass 10, data/balance_notes.md).
#
# 60 Gold = ein Speertraeger. Staerke 3 = 180 Gold entspricht also der
# Startarmee des Spielers (3 Einheiten Tier 1) - ein knapper Kampf, kein
# aussichtsloser. Teure Kreaturen fallen automatisch aus: ein Greif kostet
# 200 und passt in kein Staerke-3-Budget.
const MONSTER_GOLD_PER_STRENGTH := 60
# Spielraum bei der Kreatur-Wahl. 1.0 heisst: die Kreatur muss EINZELN ins
# Budget passen. Der erste Anlauf stand auf 1.25 - damit war ein Greif
# (200 Gold) fuer Staerke 3 (180) zulaessig, also genau der Kampf, der die
# Startarmee ausloescht. Der Test in test_new_game haelt das jetzt fest.
const MONSTER_GOLD_TOLERANCE := 1.0
const MONSTER_MAX_COUNT := 20
# Ein REGENERIERENDER Gegner darf nie als Einzelgaenger dastehen (It. 42).
#
# Der Grund ist gemessen: ein einzelnes Gespenst fuer 170 Gold hat die
# 320-Gold-Startarmee 4 von 4 Mal ausgeloescht und erst gegen 480 Gold
# verloren. Abilities.regen_hp heilt einen Anteil der max-HP der OBERSTEN
# EINHEIT - das einzelne Gespenst holt 7 von 25 HP pro Runde zurueck (28
# %), und eine kleine Armee macht weniger Schaden als das. Sie kann es
# damit GAR NICHT toeten, egal wie lange sie draufschlaegt. Bei drei
# Gespenstern gilt dieselbe Heilung fuer 75 HP, also ein Drittel so viel,
# und der Kampf ist wieder eine Frage von Kraft statt von Unbesiegbarkeit.
#
# NUR fuer Regenerierer, nicht fuer alle: der erste Anlauf hat die
# Untergrenze auf JEDE Kreatur gelegt, und prompt kostete das schwaechste
# Monster (Staerke 1, Budget 60) drei Goblins = 120 Gold - doppeltes
# Budget, und test_new_game war zu Recht rot. Der Befund war die
# Regeneration, also gehoert die Regel auch dorthin.
const MONSTER_MIN_COUNT := 3
# Kandidaten fuer wandernde Monster: bewusst aus allen vier Fraktionen,
# aber nur Kreaturen, die als Wildnis-Begegnung taugen (keine Engel,
# keine Zitadellen-Einheiten).
const MONSTER_POOL := [
	"ork_goblin", "nec_skeleton", "men_spearman", "elf_dwarf",
	"ork_wolfrider", "nec_zombie", "ork_orc", "men_archer",
	"nec_wight", "men_griffin", "elf_pegasus", "elf_archer",
]
const MONSTER_MIN_DIST := 5
const MONSTER_VICTORY_GOLD := 120

# Karten-Objekte: Goldminen (dauerhaftes Einkommen) und Schatzkisten
# (Einmal-Belohnung). Beide haben eine Wache, die vor Einnahme besiegt
# werden muss (selbe Formel wie Stadt-Wache/Monster).
const OBJECT_MINE := 0
const OBJECT_TREASURE := 1
# Ressourcen-Haufen (M3): unbewachtes/leicht bewachtes Einmal-Pickup
# einer einzelnen Ressource.
const OBJECT_PILE := 2
# Bonus-Objekte (M5). Alle unbewacht - in HoMM3 sind die Stat-Schreine
# ebenfalls frei zugaenglich; die Kosten sind die Bewegungspunkte und der
# Umweg, nicht ein Kampf.
const OBJECT_SHRINE_ATT := 3      # Soeldnerlager   -> +1 Angriff
const OBJECT_SHRINE_DEF := 4      # Wehrturm        -> +1 Verteidigung
const OBJECT_SHRINE_POWER := 5    # Sternwarte      -> +1 Zauberkraft
const OBJECT_SHRINE_KNOW := 6     # Garten          -> +1 Wissen
const OBJECT_WELL := 7            # Brunnen         -> Mana voll, 1x/Tag
const OBJECT_LEARNING := 8        # Lehrmeister     -> XP, einmalig
const OBJECT_WINDMILL := 9        # Windmuehle      -> Ressource, 1x/Woche

const MINE_COUNT := 6
const TREASURE_COUNT := 4
const PILE_COUNT := 6

# Je Bonus-Art so viele Exemplare. Die Stat-Schreine bleiben einzeln,
# damit sie sich lohnen und nicht beliebig wiederholbar wirken.
const BONUS_PLAN := {
	OBJECT_SHRINE_ATT: 1,
	OBJECT_SHRINE_DEF: 1,
	OBJECT_SHRINE_POWER: 1,
	OBJECT_SHRINE_KNOW: 1,
	OBJECT_WELL: 2,
	OBJECT_LEARNING: 2,
	OBJECT_WINDMILL: 2,
}
# Einmalige Stat-Schreine: Art -> (Primaerwert, Anzeigename).
const SHRINE_STATS := {
	OBJECT_SHRINE_ATT: ["attack", "Soeldnerlager"],
	OBJECT_SHRINE_DEF: ["defense", "Wehrturm"],
	OBJECT_SHRINE_POWER: ["spell_power", "Sternwarte"],
	OBJECT_SHRINE_KNOW: ["knowledge", "Garten der Erkenntnis"],
}
# Art -> Sprite-Name unter assets/world/objects/.
const OBJECT_SPRITES := {
	OBJECT_SHRINE_ATT: "shrine_att",
	OBJECT_SHRINE_DEF: "shrine_def",
	OBJECT_SHRINE_POWER: "shrine_power",
	OBJECT_SHRINE_KNOW: "shrine_know",
	OBJECT_WELL: "well",
	OBJECT_LEARNING: "learning",
	OBJECT_WINDMILL: "windmill",
}
const LEARNING_XP := 120
const WINDMILL_MIN := 3
const WINDMILL_MAX := 6
const MINE_GOLD_PER_TURN := 150
const TREASURE_GOLD_MIN := 300
const TREASURE_GOLD_MAX := 700
const OBJECT_GUARD_MIN := 2
const OBJECT_GUARD_MAX := 5
const OBJECT_MIN_DIST := 3
# Minen-Verteilung (M3): Index in dieser Liste = wievielte platzierte
# Mine. 2x Gold, je 1x Holz/Erz, 2 zufaellige Edel-Minen (Slot "rare").
const MINE_KINDS := ["gold", "gold", "wood", "ore", "rare", "rare"]
const RARE_RESOURCES := ["mercury", "sulfur", "crystal", "gems"]
# Tagesertrag je Minen-Ressource.
const MINE_YIELD := {"gold": MINE_GOLD_PER_TURN, "wood": 2, "ore": 2,
	"mercury": 1, "sulfur": 1, "crystal": 1, "gems": 1}
# Tint-Farben fuer Haufen-Sprites und UI-Akzente je Ressource.
const RESOURCE_COLORS := {
	"gold": Color(1.0, 0.85, 0.3), "wood": Color(0.65, 0.45, 0.25),
	"ore": Color(0.62, 0.62, 0.66), "mercury": Color(0.75, 0.85, 0.95),
	"sulfur": Color(0.9, 0.85, 0.4), "crystal": Color(0.6, 0.85, 0.95),
	"gems": Color(0.85, 0.5, 0.85),
}

# Belohnung fuer Sieg ueber den Gegner-Helden (Auto-Resolve auf der Karte).
# Bewusst hoeher als ein Monster, weil er sich bewegt und zurueckschlaegt.
const ENEMY_DEFEAT_GOLD := 300
const ENEMY_DEFEAT_XP := 50

# Flucht und Kapitulation (It. 42) - die HoMM3-Tuer aus einem Kampf, den
# man nicht gewinnen kann. Der Durchspiel-Test hat gezeigt, warum sie
# fehlte: in 3 von 6 Seeds war das Spiel in Woche 1-2 vorbei, immer im
# gleichen Muster - ein KI-Held stellt den Startheld mit drei Einheiten und
# der Pflichtkampf war nicht ausschlagbar.
#
# FLUCHT ist kostenlos, kostet aber die GANZE Armee (HoMM3: der Held
# landet in der Taverne, seine Truppen sind weg). KAPITULATION kostet Gold
# in Hoehe des Armeewerts, dafuer behaelt der Held seine Truppen. Beides
# setzt eine eigene Stadt voraus - ohne Ziel gibt es kein Entkommen, und
# das ist die letzte Schlacht.
#
# Der Faktor auf den Armeewert ist die Stellschraube: 1.0 heisst "die
# Rettung kostet so viel wie die Armee neu zu kaufen".
const SURRENDER_COST_FACTOR := 1.0
const SURRENDER_COST_MIN := 250

# Stadt-Wachen: jede neutrale Stadt hat eine zufaellige Wache. Sie muss
# vor der Einnahme besiegt werden (selbe Combat-Formel wie Monster).
# Die Start-Stadt des Helden hat Garrison 0.
const GARRISON_MIN := 2
const GARRISON_MAX := 5

# Held-Progression. XP_PER_STRENGTH * Monster-Staerke = XP pro Kill.
# LEVEL_THRESHOLDS[i] ist die XP-Schwelle, um von Level i auf i+1 zu
# springen (Level 1 = Startlevel, Index 0 ungenutzt zur Klarheit).
const XP_PER_STRENGTH := 15
const LEVEL_THRESHOLDS := [0, 50, 150, 350, 700, 1200, 2000]
const LEVEL_BONUS_ARMY := 1   # sofort +1 Armee bei Level-Up
const LEVEL_BONUS_MP := 4     # +1 Feld pro Level-Up (additiv zur Basis)
# Kampfkraft-Bonus pro Level (level-1): zaehlt zur Armee im Kampf UND
# reduziert Verluste. Macht XP endlich nuetzlich: Level 3 mit 1 Armee
# schlaegt Staerke-3-Monster ohne einen einzigen Verlust.
const LEVEL_COMBAT_BONUS := 1

# Wachturm: pro eigener Stadt +1 Kampfkraft-Bonus (stapelt mit Level-Bonus).
const WACHTURM_COMBAT_BONUS := 1
# Kapelle: +XP pro Tag pro Stadt mit Kapelle.
const KAPELLE_XP_PER_TURN := 10
# Glueck im Kampf pro Kapelle (M6), gedeckelt wie in Morale.LUCK_LIMIT.
const LUCK_PER_KAPELLE := 1
const LUCK_MAX := 3
# Belagerung (M9): Pfeilturm-Schaden pro Runde, solange die Mauer steht,
# und der Faktor, mit dem eine Mauer die Garnison in der Auto-Abrechnung
# staerkt (KI-Angriffe auf Spielerstaedte laufen ohne Overlay).
const SIEGE_TOWER_DMG := 12
const SIEGE_TOWER_WACHTURM_BONUS := 8

# Monster-Aufklaerung: exakte Staerke nur sichtbar, wenn der Held in
# Manhattan-Reichweite ist. Weiter weg erscheint "?" (Info-Vorteil fuer
# Erkundung).
const MONSTER_VIEW_RANGE := 5

# Kriegsnebel: drei Stufen. HIDDEN = nie gesehen (schwarz), EXPLORED =
# schon einmal gesehen aber aktuell nicht in Sicht (gedimmt, Gelaende
# bleibt, bewegliche Einheiten nicht mehr), VISIBLE = aktuell in Sicht
# (volle Information). Sichtquellen sind Held, eigene Staedte und eigene
# Minen/Schatzfelder mit jeweils eigenem Radius (Manhattan). Der
# Ghost-Marker fuer gegnerische Helden verblasst ueber FOG_ROT_TURNS
# Zuege nach der letzten Sichtung ("Info rottet").
const FOG_HIDDEN := 0
const FOG_EXPLORED := 1
const FOG_VISIBLE := 2
const HERO_SIGHT := 6
const CITY_SIGHT := 4
const OBJECT_SIGHT := 2
const FOG_ROT_TURNS := 4

# Adaptive-KI-Parameter:
# AI_THREAT_RADIUS: Manhattan-Distanz eines feindlichen Helden zur
#   eigenen Stadt, unter der die KI defensiv umschaltet.
# AI_HUNT_SAFETY_PCT: prozentualer Armee-Vorsprung, den die KI haben
#   muss, bevor sie einen fremden Helden jagt (vermeidet Suizid-
#   Angriffe gegen sichtbar staerkere Gegner).
# AI_RAID_SAFETY_PCT: gleiche Logik fuer fixe Garnisonen/Objekt-Wachen.
const AI_THREAT_RADIUS := 5
const AI_HUNT_SAFETY_PCT := 10
const AI_RAID_SAFETY_PCT := 10

# Fraktionen. Bewusst generische Namen (nicht HoMM3-IP), passt zur
# Plan-Phase 1 ("Waldvolk"/"Menschen"/"Totenreich"/"Orks").
const FACTION_NAMES := ["Waldvolk", "Menschen", "Totenreich", "Orks"]
# Verzeichnis-Slugs fuer assets/city und assets/world/cities. Muss zu
# CityScreen.FACTION_DIRS passen (selbe Reihenfolge wie FACTION_NAMES).
const FACTION_DIRS := ["waldvolk", "menschen", "totenreich", "orks"]
const FACTION_COLORS := [
	Color(0.45, 0.85, 0.45),   # Waldvolk - gruen
	Color(0.95, 0.85, 0.35),   # Menschen - gold
	Color(0.70, 0.45, 0.90),   # Totenreich - violett
	Color(0.95, 0.35, 0.30),   # Orks - rot
]

# Gebaeude: id/Name/Kosten/effect-Text. Optional "requires" = id ODER
# Liste von ids anderer Gebaeude, die vorher gebaut sein muessen (selbe
# Stadt, siehe _requires_list). Pro Stadt als Liste von ids in
# city["buildings"].
# Gebaeude-Kosten als Ressourcen-Dictionaries (M3 Teil 2). HoMM3-angelehnt,
# mild fuer Mobile. Die 4 Militaergebaeude decken die 7 Einheiten-Tiers
# ab (M4 Teil 2): kaserne T1+2, schmiede T3+4, reiterei T5+6, zitadelle T7.
const BUILDINGS := [
	{"id": "kaserne",  "name": "Kaserne",  "cost": {"gold": 500, "wood": 5}, "effect": "Rekruten Tier 1-2"},
	{"id": "spaeher",  "name": "Spaeher",  "cost": {"gold": 300, "wood": 2}, "effect": "+2 max Schritte/Tag"},
	{"id": "markt",    "name": "Markt",    "cost": {"gold": 800, "wood": 5, "ore": 2}, "effect": "+200 Gold/Tag, Markt-Tausch"},
	{"id": "schmiede", "name": "Schmiede", "cost": {"gold": 700, "ore": 5}, "effect": "Rekruten Tier 3-4", "requires": "kaserne"},
	{"id": "reiterei", "name": "Reiterei", "cost": {"gold": 1000, "wood": 5, "ore": 5}, "effect": "Rekruten Tier 5-6", "requires": "schmiede"},
	{"id": "wachturm", "name": "Wachturm", "cost": {"gold": 400, "ore": 5}, "effect": "+1 Kampfkraft (dauerhaft)"},
	{"id": "kapelle",  "name": "Kapelle",  "cost": {"gold": 500, "wood": 2, "ore": 2, "crystal": 1}, "effect": "+10 XP/Tag, +1 Glueck im Kampf"},
	{"id": "mauer",    "name": "Stadtmauer", "cost": {"gold": 1200, "ore": 10, "wood": 5}, "effect": "Belagerung: +2 Verteidigung, Pfeilturm, Angreifer braucht Bresche"},
	{"id": "zitadelle", "name": "Zitadelle", "cost": {"gold": 2500, "wood": 10, "ore": 10, "crystal": 1}, "effect": "Rekruten Tier 7", "requires": ["reiterei", "mauer"]},
]
# Startvorrat (Spieler UND KI), damit Tag-1-Bauten nicht an fehlendem
# Holz scheitern, bevor die erste Mine erobert ist.
const STARTING_RESOURCES := {"wood": 20, "ore": 10}
# Markt-Tauschkurse (M3 Teil 2): Kaufpreis in Gold je 1 Ressource und
# Verkaufserloes. Bewusst ungleich (Spread), wie beim HoMM3-Marktplatz.
const MARKET_BUY := {"wood": 200, "ore": 200, "mercury": 600, "sulfur": 600, "crystal": 600, "gems": 600}
const MARKET_SELL := {"wood": 50, "ore": 50, "mercury": 150, "sulfur": 150, "crystal": 150, "gems": 150}

@export var status_label_path: NodePath    = ^"TopBar/StatusLabel"
@export var mp_label_path: NodePath        = ^"TopBar/MPLabel"
@export var end_turn_button_path: NodePath = ^"BottomBar/EndTurnBtn"
@export var reroll_button_path: NodePath   = ^"BottomBar/RerollBtn"
@export var back_button_path: NodePath     = ^"BottomBar/BackBtn"
@export var map_area_path: NodePath        = ^"MapArea"
@export var minimap_path: NodePath         = ^"Minimap"
@export var minimap_toggle_path: NodePath  = ^"TopBar/MinimapToggleBtn"
@export var sound_toggle_path: NodePath    = ^"TopBar/SoundToggleBtn"
@export var hero_button_path: NodePath     = ^"TopBar/HeroBtn"

var _map: Dictionary

# --- Helden (M13a) --------------------------------------------------------
# Der Spieler hat eine LISTE von Helden; `_active_hero` zeigt auf den, den
# er gerade steuert. `_hero` ist nur noch ein GETTER darauf.
#
# Warum so: `_hero` kommt in dieser Datei rund 160 Mal vor, aber es gab nur
# ZWEI Schreibzugriffe auf die Variable selbst. Als Getter bleiben damit
# alle Lesestellen (position, mp, army, xp, skills, mana, ...) unveraendert
# gueltig, und der Umbau beruehrt nur die Stellen, die es wirklich angeht.
#
# In dieser Iteration existiert genau EIN Held - das Spiel muss sich
# verhalten wie vorher. Anwerben, Wechsel-Knopf und Armee-Tausch kommen in
# M13b.
var _heroes: Array = []
var _active_hero: int = 0

# ACHTUNG: In Kampf-Callbacks (die Lambdas in `_open_battle`) NICHT `_hero`
# lesen, sondern den beim Oeffnen gemerkten Helden. Der aktive Held kann
# zwischen Kampfbeginn und Callback wechseln - mit einem Helden ist das
# harmlos, ab zwei ein Fehler, der nur manchmal auftritt.
var _hero: Hero:
	get:
		if _active_hero < 0 or _active_hero >= _heroes.size():
			return null   # 16 null-Pruefungen im Code verlassen sich darauf
		return _heroes[_active_hero] as Hero

# Geldbeutel des SPIELERS, nicht des Helden (M13a). Vorher lag er in
# `Hero.wallet` - mit zwei Helden waere "welcher Held haelt das Gold" sofort
# ein Fehler. Die KI behaelt ihren Beutel im Helden: jede KI hat genau einen.
var _purse: Wallet = Wallet.new()

var _seed: int = 42
var _costs: Dictionary = {}
var _tile_size: float = 64.0
var _map_area: Control
# Minimap: vollstaendig sichtbare Uebersichtskarte oben rechts. Zeichnet
# pro Kachel ein Farb-Pixel, das aktuelle Viewport-Rechteck und
# Helden-Positionen. Tap springt zum entsprechenden Feld.
var _minimap: Panel

# Scroll/Pan-State: die Karte ist potentiell groesser als _map_area.
# _view_offset ist die Pixel-Verschiebung des Karten-Origins relativ
# zu _map_area. Drag verschiebt den Offset, Tap (ohne Bewegung ueber
# DRAG_THRESHOLD) bewegt den Helden wie vorher.
const TILE_PX: float = 64.0
const DRAG_THRESHOLD: float = 12.0
var _view_offset: Vector2 = Vector2.ZERO
var _pan_active: bool = false
var _pan_start_pos: Vector2 = Vector2.ZERO
var _pan_start_offset: Vector2 = Vector2.ZERO
var _pan_moved: bool = false
# Staedte: Array aus { "pos": Vector2i, "faction": int, "owner": int,
# "buildings": Array[String] }. Faction-ID indiziert FACTION_NAMES/_COLORS.
var _cities: Array = []
# Spieler-Fraktion: Fraktion der Start-Stadt (0..3). Steuert, welche
# Boni-Einheiten der Spieler durch Level-Up und Schmiede bekommt.
var _player_faction: int = 1
var _selected_city: int = -1
# Isometrischer Stadt-Screen. Bau-/Rekrut-Logik laeuft per Signal an die
# bestehenden _buy_building/_recruit_unit zurueck (siehe _city_screen-Setup),
# damit Oekonomie an einer Stelle bleibt.
var _city_screen: CityScreen
# Monster: Array aus { "pos": Vector2i, "strength": int }.
var _monsters: Array = []
# Karten-Objekte: Array aus { "pos": Vector2i, "kind": int, "owner": int,
# "guard": int, "gold": int }. kind=OBJECT_MINE gibt Gold/Zug solange im
# Besitz; kind=OBJECT_TREASURE gibt einmalig Gold und wird entfernt.
var _objects: Array = []
# Dauerhafte Kampf-Anzeige zwischen TopBar und MapArea. Wird NIE von
# Tap-Status ueberschrieben - bleibt stehen, bis ein neuer Kampf passiert.
var _combat_label: Label
var _victory_panel: Panel
var _victory_title: Label
var _game_won: bool = false
var _game_lost: bool = false
# Zugnummer, ab der der Spieler keine Stadt mehr hat. -1 = alles in
# Ordnung. Wird gespeichert (reine Feld-Ergaenzung, kein Versions-Bump).
var _no_city_since: int = -1
# Gegner-KIs. Jede KI ist ein Dictionary mit:
#   "hero": Hero (null wenn im Kampf gefallen)
#   "owner_id": int (1..3) - wird in city/object["owner"] gespiegelt
#   "primary_faction": int (0..3) - Heimat-Fraktion der Start-Stadt
#   "recruit_idx": int - Rotations-Index ueber
#       UnitType.recruitable_ids_for_faction(primary_faction), T1..T7
#   "fog": Array (MAP_WIDTH*MAP_HEIGHT) - eigene Sichtbarkeit
#   "player_last_seen_pos": Vector2i - wo diese KI den Spieler-Held
#       zuletzt gesehen hat (-1,-1 wenn nie)
#   "player_last_seen_turn": int
# Fuer Step 1 wird genau eine KI angelegt (owner_id = OWNER_ENEMY = 1),
# die Logik ist aber schon arrayfoermig - Schritt 3 aktiviert drei KIs.
var _enemies: Array = []
# Parallel zu _enemies: wo der SPIELER jede KI zuletzt gesichtet hat.
# {pos: Vector2i, turn: int}. pos.x < 0 = nie gesehen.
var _ai_seen_by_player: Array = []
# RNG bleibt nach _start() aktiv, damit Enemy-Turn deterministische
# Wuerfe fuer Garrison machen kann.
var _rng: DeterministicRng

# Kriegsnebel-Spielerseite. Je KI liegt ihr eigenes Fog-Array in
# _enemies[i]["fog"]. Werte aus FOG_HIDDEN/EXPLORED/VISIBLE.
# _turn_number zaehlt abgeschlossene Spielerzuege, damit der
# Ghost-Marker "Info rottet" linear verblassen kann.
var _fog_player: Array = []
var _turn_number: int = 0
# Snapshot der Spieler-Oekonomie-Werte dieser Runde, damit die Status-
# Zeile auch dann korrekt bleibt, wenn die KI-Phase durch ein
# Pflicht-Kampf-Overlay (KI greift Spieler an) suspendiert wird und
# erst nach Kampfabschluss weiterlaeuft.
var _turn_income: int = 0
var _turn_xp_gain: int = 0
var _turn_owned: int = 0


func _set_status(s: String) -> void:
	var lbl := get_node_or_null(status_label_path) as Label
	if lbl != null:
		lbl.text = s
	# Liegt der Stadt-Screen drueber, dieselbe Meldung dort spiegeln -
	# sonst landet Feedback wie "Kein Nachschub" unsichtbar dahinter.
	if _city_screen != null and _city_screen.visible:
		_city_screen.set_status(s)
	print("[WorldMap] " + s)


func _ready() -> void:
	_set_status("STEP 1: _ready")
	_map_area = get_node(map_area_path) as Control
	_map_area.gui_input.connect(_on_map_input)
	_map_area.draw.connect(_draw_map)
	_map_area.resized.connect(_on_map_resized)
	_minimap = get_node_or_null(minimap_path) as Panel
	if _minimap != null:
		_minimap.gui_input.connect(_on_minimap_input)
		_minimap.draw.connect(_draw_minimap)
	var mm_toggle := get_node_or_null(minimap_toggle_path) as Button
	if mm_toggle != null:
		mm_toggle.pressed.connect(_toggle_minimap)
	# Stumm-Knopf (M11). Auf dem Handy will man Ton abschalten koennen, ohne
	# das Spiel zu verlassen. Ohne Autoload (Tools-Skript) bleibt er
	# unsichtbar, statt einen toten Knopf anzubieten.
	var snd_toggle := get_node_or_null(sound_toggle_path) as Button
	if snd_toggle != null:
		if Sound.available():
			snd_toggle.pressed.connect(_toggle_sound)
		else:
			snd_toggle.visible = false
	# Heldenblatt (It. 29). get_node_or_null, damit eine aeltere Szene ohne
	# den Knopf weiter laedt - dasselbe Muster wie beim Ton-Knopf.
	var hero_btn := get_node_or_null(hero_button_path) as Button
	if hero_btn != null:
		hero_btn.pressed.connect(_open_hero_panel)
	_build_combat_label()
	_build_city_screen()
	_build_victory_panel()

	(get_node(end_turn_button_path) as Button).pressed.connect(_on_end_turn)
	(get_node(reroll_button_path) as Button).pressed.connect(_on_reroll)
	(get_node(back_button_path) as Button).pressed.connect(_on_back)
	_set_status("STEP 2: Buttons verdrahtet")

	# Vom Hauptmenue angefordertes Laden? Das Autoload-Singleton traegt
	# den Save-Inhalt (get_node_or_null, damit headless Tools-Skripte ohne
	# Autoloads nicht crashen).
	var sm := get_node_or_null(^"/root/SaveManager")
	if sm != null and not (sm.pending_load as Dictionary).is_empty():
		var save: Dictionary = sm.pending_load
		sm.pending_load = {}
		if _restore_state(save):
			return
		# Korruptes Save: normal starten statt crashen.
		_set_status("Laden fehlgeschlagen - neues Spiel")
	# Neues Spiel mit Wunsch-Fraktion/-Seed aus dem Hauptmenue (M2)?
	if sm != null and not (sm.pending_new_game as Dictionary).is_empty():
		var ng: Dictionary = sm.pending_new_game
		sm.pending_new_game = {}
		_start(int(ng.get("seed", _seed)), int(ng.get("faction", -1)))
		return
	_start(_seed)


func _start(seed_value: int, requested_faction: int = -1) -> void:
	_set_status("STEP 3: generiere seed=%d" % seed_value)
	_seed = seed_value
	_game_won = false
	_game_lost = false
	_no_city_since = -1
	_enemies.clear()
	_ai_seen_by_player.clear()
	if _victory_panel != null:
		_victory_panel.visible = false
	_rng = DeterministicRng.new(seed_value)
	var rng := _rng
	_set_status("STEP 3a1: Array init")
	var tiles: Array = []
	_set_status("STEP 3a2: resize %d" % (MAP_WIDTH * MAP_HEIGHT))
	tiles.resize(MAP_WIDTH * MAP_HEIGHT)
	_set_status("STEP 3a3: fill grass")
	for i in range(tiles.size()):
		tiles[i] = MapGen.TILE_GRASS
	var water_clusters: int = max(2, int(float(MAP_WIDTH * MAP_HEIGHT) / 80.0))
	_set_status("STEP 3b: place_water (%d Cluster)" % water_clusters)
	for ci in range(water_clusters):
		_set_status("STEP 3b.%d.a: cx/cy" % (ci + 1))
		var cx := rng.next_int(0, MAP_WIDTH - 1)
		var cy := rng.next_int(0, MAP_HEIGHT - 1)
		_set_status("STEP 3b.%d.b: target_size" % (ci + 1))
		var target_size := rng.next_int(8, 18)
		_set_status("STEP 3b.%d.c: loop start (%d,%d) tgt=%d" % [ci + 1, cx, cy, target_size])
		var frontier: Array = [Vector2i(cx, cy)]
		var placed := 0
		var it := 0
		while placed < target_size and frontier.size() > 0 and it < 500:
			it += 1
			var idx := rng.next_int(0, frontier.size() - 1)
			var cell: Vector2i = frontier[idx]
			frontier.remove_at(idx)
			if cell.x < 0 or cell.x >= MAP_WIDTH or cell.y < 0 or cell.y >= MAP_HEIGHT:
				continue
			var ti: int = cell.y * MAP_WIDTH + cell.x
			if int(tiles[ti]) != MapGen.TILE_GRASS:
				continue
			tiles[ti] = MapGen.TILE_WATER
			placed += 1
			frontier.append(Vector2i(cell.x + 1, cell.y))
			frontier.append(Vector2i(cell.x - 1, cell.y))
			frontier.append(Vector2i(cell.x, cell.y + 1))
			frontier.append(Vector2i(cell.x, cell.y - 1))
		_set_status("STEP 3b.%d.d: loop done it=%d placed=%d" % [ci + 1, it, placed])
	var mountain_clusters: int = max(3, int(float(MAP_WIDTH * MAP_HEIGHT) / 50.0))
	_set_status("STEP 3c: place_mountains (%d Cluster)" % mountain_clusters)
	for ci in range(mountain_clusters):
		var cx := rng.next_int(0, MAP_WIDTH - 1)
		var cy := rng.next_int(0, MAP_HEIGHT - 1)
		var target_size := rng.next_int(4, 10)
		var frontier: Array = [Vector2i(cx, cy)]
		var placed := 0
		var it := 0
		while placed < target_size and frontier.size() > 0 and it < 500:
			it += 1
			var idx := rng.next_int(0, frontier.size() - 1)
			var cell: Vector2i = frontier[idx]
			frontier.remove_at(idx)
			if cell.x < 0 or cell.x >= MAP_WIDTH or cell.y < 0 or cell.y >= MAP_HEIGHT:
				continue
			var ti: int = cell.y * MAP_WIDTH + cell.x
			if int(tiles[ti]) != MapGen.TILE_GRASS:
				continue
			tiles[ti] = MapGen.TILE_MOUNTAIN
			placed += 1
			frontier.append(Vector2i(cell.x + 1, cell.y))
			frontier.append(Vector2i(cell.x - 1, cell.y))
			frontier.append(Vector2i(cell.x, cell.y + 1))
			frontier.append(Vector2i(cell.x, cell.y - 1))
	_set_status("STEP 3d: coat_with_sand")
	var sand_changes: Array = []
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			var ti := y * MAP_WIDTH + x
			if int(tiles[ti]) != MapGen.TILE_GRASS:
				continue
			var has_water := false
			if x + 1 < MAP_WIDTH and int(tiles[y * MAP_WIDTH + x + 1]) == MapGen.TILE_WATER:
				has_water = true
			elif x - 1 >= 0 and int(tiles[y * MAP_WIDTH + x - 1]) == MapGen.TILE_WATER:
				has_water = true
			elif y + 1 < MAP_HEIGHT and int(tiles[(y + 1) * MAP_WIDTH + x]) == MapGen.TILE_WATER:
				has_water = true
			elif y - 1 >= 0 and int(tiles[(y - 1) * MAP_WIDTH + x]) == MapGen.TILE_WATER:
				has_water = true
			if has_water:
				sand_changes.append(ti)
	for ti in sand_changes:
		tiles[ti] = MapGen.TILE_SAND

	_set_status("STEP 3d2: place_swamps")
	# Sumpf: 2-3 Inland-Cluster plus zufaellige Umwandlung von Sandfeldern
	# zu Kuesten-Sumpf. Cluster laufen wie Wasser/Gebirge (BFS-Wachstum).
	var swamp_clusters: int = max(2, int(float(MAP_WIDTH * MAP_HEIGHT) / 120.0))
	for ci in range(swamp_clusters):
		var scx := rng.next_int(0, MAP_WIDTH - 1)
		var scy := rng.next_int(0, MAP_HEIGHT - 1)
		var s_target := rng.next_int(3, 8)
		var s_frontier: Array = [Vector2i(scx, scy)]
		var s_placed := 0
		var s_it := 0
		while s_placed < s_target and s_frontier.size() > 0 and s_it < 500:
			s_it += 1
			var sidx := rng.next_int(0, s_frontier.size() - 1)
			var scell: Vector2i = s_frontier[sidx]
			s_frontier.remove_at(sidx)
			if scell.x < 0 or scell.x >= MAP_WIDTH or scell.y < 0 or scell.y >= MAP_HEIGHT:
				continue
			var sti: int = scell.y * MAP_WIDTH + scell.x
			if int(tiles[sti]) != MapGen.TILE_GRASS:
				continue
			tiles[sti] = MapGen.TILE_SWAMP
			s_placed += 1
			s_frontier.append(Vector2i(scell.x + 1, scell.y))
			s_frontier.append(Vector2i(scell.x - 1, scell.y))
			s_frontier.append(Vector2i(scell.x, scell.y + 1))
			s_frontier.append(Vector2i(scell.x, scell.y - 1))
	for ti in range(tiles.size()):
		if int(tiles[ti]) == MapGen.TILE_SAND and rng.next_int(0, 99) < 22:
			tiles[ti] = MapGen.TILE_SWAMP

	_set_status("STEP 3e: place_forests")
	for i in range(tiles.size()):
		if int(tiles[i]) == MapGen.TILE_GRASS and rng.next_int(0, 99) < 20:
			tiles[i] = MapGen.TILE_FOREST

	_set_status("STEP 3f: find_spawn")
	var spawn := Vector2i(int(MAP_WIDTH / 2), int(MAP_HEIGHT / 2))
	var found := false
	var max_r: int = max(MAP_WIDTH, MAP_HEIGHT)
	for r in range(max_r):
		if found:
			break
		for dy in range(-r, r + 1):
			if found:
				break
			for dx in range(-r, r + 1):
				var sx: int = int(MAP_WIDTH / 2) + dx
				var sy: int = int(MAP_HEIGHT / 2) + dy
				if sx < 0 or sx >= MAP_WIDTH or sy < 0 or sy >= MAP_HEIGHT:
					continue
				if int(tiles[sy * MAP_WIDTH + sx]) == MapGen.TILE_GRASS:
					spawn = Vector2i(sx, sy)
					found = true
					break
	_map = {
		"width": MAP_WIDTH,
		"height": MAP_HEIGHT,
		"tiles": tiles,
		"hero_spawn": spawn,
	}
	_set_status("STEP 4: MapGen fertig, spawn %s" % str(spawn))
	_heroes = [Hero.new(spawn, BASE_MAX_MP)]
	_active_hero = 0
	# Mana startet voll (M8). Der Deckel leitet sich aus dem Wissen ab,
	# bei Stufe 1 ist das der Grundstock.
	_hero.mana = Spells.max_mana(int(_hero.knowledge))
	# Der Beutel gehoert dem Spieler (M13a), nicht dem Helden.
	_purse = Wallet.new()
	_purse.set_amount("gold", STARTING_GOLD)
	_purse.add_all(STARTING_RESOURCES)
	# Start-Einheiten haengen an der Fraktion - die ergibt sich erst,
	# wenn die Start-Stadt gewaehlt ist. Siehe player_start_idx unten.
	_set_status("STEP 5: Hero erstellt")

	# Staedte platzieren: deterministisch, nur Gras-Felder, Mindestabstand
	# untereinander. Spawn-Abstand wird NICHT geprueft, weil eine der
	# Staedte selbst zum Start-Ort des Helden wird.
	_set_status("STEP 5a: Staedte platzieren")
	_cities.clear()
	var city_attempts := 0
	while _cities.size() < CITY_COUNT and city_attempts < 400:
		city_attempts += 1
		# Rand-Abstand (It. 34): vorher durfte eine Stadt in Reihe 0
		# liegen. Da eine der Staedte der START des Helden ist, begann ein
		# Spiel dann in der Kartenecke - der erste Bildschirm war zu rund
		# 85 % Nebel, und die halbe Sichtweite lag ausserhalb der Karte.
		var cx: int = rng.next_int(CITY_BORDER_MARGIN,
			MAP_WIDTH - 1 - CITY_BORDER_MARGIN)
		var cy: int = rng.next_int(CITY_BORDER_MARGIN,
			MAP_HEIGHT - 1 - CITY_BORDER_MARGIN)
		if int(tiles[cy * MAP_WIDTH + cx]) != 0:  # 0 = GRASS
			continue
		var candidate := Vector2i(cx, cy)
		var too_close := false
		for existing in _cities:
			var ep: Vector2i = existing["pos"]
			if abs(candidate.x - ep.x) + abs(candidate.y - ep.y) < CITY_MIN_DIST:
				too_close = true
				break
		if too_close:
			continue
		_cities.append({
			"pos": candidate,
			"faction": _cities.size() % FACTION_NAMES.size(),
			"owner": OWNER_NEUTRAL,
			"buildings": [],
			# Echte Verteidiger statt einer Staerke-Zahl: die Einheiten
			# der Stadt-Fraktion, die man beim Erobern auch besiegt.
			"garrison_army": Garrison.synth(
				_cities.size() % FACTION_NAMES.size(),
				rng.next_int(GARRISON_MIN, GARRISON_MAX)),
			"pools": {} as Dictionary,
		})

	# Start-Stadt waehlen: eine der platzierten Staedte wird dem Helden
	# zugewiesen, Garrison auf 0, Spawn-Position = Stadt-Position. So
	# sieht man vom ersten Zug an seine eigene Stadt auf der Karte.
	# _hero wurde oben schon mit Mitten-Spawn erzeugt - Position hier
	# ueberschreiben.
	var player_start_idx: int = -1
	_player_faction = 1
	if _cities.size() > 0:
		# Fraktionswahl (M2): requested_faction 0..3 bevorzugt eine Stadt
		# dieser Fraktion (Staedte rotieren i % 4, es gibt also immer
		# welche). -1 = Zufall (bisheriges Verhalten). Der RNG wird in
		# beiden Zweigen konsumiert, damit der Rest der Generierung
		# fuer denselben Seed deterministisch bleibt, egal ob/was
		# gewaehlt wurde.
		var roll: int = rng.next_int(0, _cities.size() - 1)
		if requested_faction >= 0:
			var candidates: Array = []
			for ci in range(_cities.size()):
				if int(_cities[ci]["faction"]) == requested_faction:
					candidates.append(ci)
			if candidates.is_empty():
				player_start_idx = roll
			else:
				player_start_idx = candidates[roll % candidates.size()]
		else:
			player_start_idx = roll
		_cities[player_start_idx]["owner"] = OWNER_HERO
		_cities[player_start_idx]["garrison_army"] = {}
		spawn = _cities[player_start_idx]["pos"]
		_map["hero_spawn"] = spawn
		_hero.position = spawn
		_player_faction = int(_cities[player_start_idx]["faction"])
	# Start-Armee kommt in der Fraktion der Start-Stadt - Menschen-Schwert
	# ist nur noch der Fallback, wenn keine Stadt gesetzt werden konnte.
	var player_starter: String = UnitType.starter_id_for_faction(_player_faction)
	_hero.add_units(player_starter, STARTING_UNIT_COUNT)

	# Drei KIs: jede bekommt ihre eigene Start-Stadt. Pro KI wird die
	# Stadt gewaehlt, deren minimale Manhattan-Distanz zu allen bereits
	# vergebenen Start-Staedten (Spieler + schon gesetzte KIs) maximal
	# ist. So sitzen alle vier Fraktionen in moeglichst weit
	# auseinanderliegenden Ecken, der Rest bleibt neutral zum Erobern.
	if player_start_idx >= 0:
		var taken_idx: Array = [player_start_idx]
		var taken_pos: Array = [_cities[player_start_idx]["pos"]]
		var ai_slots: int = min(OWNER_AI_MAX - OWNER_AI_MIN + 1, _cities.size() - 1)
		for slot in range(ai_slots):
			var best_idx: int = -1
			var best_min_d: int = -1
			for i in range(_cities.size()):
				if taken_idx.has(i):
					continue
				var cp: Vector2i = _cities[i]["pos"]
				var min_d: int = -1
				for tp in taken_pos:
					var tpv: Vector2i = tp
					var d: int = abs(cp.x - tpv.x) + abs(cp.y - tpv.y)
					if min_d < 0 or d < min_d:
						min_d = d
				if min_d > best_min_d:
					best_min_d = min_d
					best_idx = i
			if best_idx < 0:
				break
			var owner_id: int = OWNER_AI_MIN + slot
			_cities[best_idx]["owner"] = owner_id
			_cities[best_idx]["garrison_army"] = {}
			var ai_faction: int = int(_cities[best_idx]["faction"])
			var ai_starter: String = UnitType.starter_id_for_faction(ai_faction)
			var ai_hero := Hero.new(_cities[best_idx]["pos"], ENEMY_BASE_MP)
			ai_hero.gold = STARTING_GOLD
			ai_hero.wallet.add_all(STARTING_RESOURCES)
			ai_hero.add_units(ai_starter, STARTING_UNIT_COUNT)
			_enemies.append({
				"hero": ai_hero,
				"owner_id": owner_id,
				"primary_faction": ai_faction,
				"recruit_idx": 0,
				"fog": [] as Array,
				"player_last_seen_pos": Vector2i(-1, -1),
				"player_last_seen_turn": -1,
				"rivals_seen": {} as Dictionary,
			})
			_ai_seen_by_player.append({"pos": Vector2i(-1, -1), "turn": -1})
			taken_idx.append(best_idx)
			taken_pos.append(_cities[best_idx]["pos"])

	# Monster platzieren: nur Gras/Wald, Mindestabstand zu Held, Staedten
	# und anderen Monstern, Staerke 1-3.
	_set_status("STEP 5b: Monster platzieren")
	_monsters.clear()
	var m_attempts := 0
	while _monsters.size() < MONSTER_COUNT and m_attempts < 600:
		m_attempts += 1
		var mx: int = rng.next_int(0, MAP_WIDTH - 1)
		var my: int = rng.next_int(0, MAP_HEIGHT - 1)
		var tt: int = int(tiles[my * MAP_WIDTH + mx])
		if tt != 0 and tt != 1:  # 0 GRASS, 1 FOREST
			continue
		var mpos := Vector2i(mx, my)
		if abs(mpos.x - spawn.x) + abs(mpos.y - spawn.y) < MONSTER_MIN_DIST:
			continue
		var blocked := false
		for c in _cities:
			if c["pos"] == mpos:
				blocked = true
				break
		if blocked:
			continue
		for m in _monsters:
			if abs((m["pos"] as Vector2i).x - mpos.x) + abs((m["pos"] as Vector2i).y - mpos.y) < 2:
				blocked = true
				break
		if blocked:
			continue
		var m_str: int = rng.next_int(1, 3)
		_monsters.append({
			"pos": mpos,
			"strength": m_str,
			# Kreatur gleich festlegen und mitspeichern - so zeigt die
			# Karte dieselbe Einheit, die im Kampf antritt.
			"unit": _pick_monster_unit(m_str, rng.next_int(0, 1 << 20)),
		})

	# Karten-Objekte platzieren: erst Minen, dann Schatzkisten. Gras/Wald
	# wie Monster, Mindestabstand zu Spawn/Staedten/Monstern/anderen
	# Objekten. Jedes Objekt hat eine zufaellige Wache (OBJECT_GUARD_*).
	_set_status("STEP 5c: Objekte platzieren")
	_objects.clear()
	var o_attempts: int = 0
	# Plan statt Index-Arithmetik: die alte Form ("if idx >= MINE_COUNT +
	# TREASURE_COUNT") traegt sieben zusaetzliche Arten nicht mehr.
	var kind_plan: Array = []
	for _i in range(MINE_COUNT):
		kind_plan.append(OBJECT_MINE)
	for _i in range(TREASURE_COUNT):
		kind_plan.append(OBJECT_TREASURE)
	for _i in range(PILE_COUNT):
		kind_plan.append(OBJECT_PILE)
	for bk in BONUS_PLAN.keys():
		for _i in range(int(BONUS_PLAN[bk])):
			kind_plan.append(int(bk))
	var o_target: int = kind_plan.size()
	while _objects.size() < o_target and o_attempts < 800:
		o_attempts += 1
		var ox: int = rng.next_int(0, MAP_WIDTH - 1)
		var oy: int = rng.next_int(0, MAP_HEIGHT - 1)
		var ot: int = int(tiles[oy * MAP_WIDTH + ox])
		if ot != 0 and ot != 1:
			continue
		var opos := Vector2i(ox, oy)
		if abs(opos.x - spawn.x) + abs(opos.y - spawn.y) < OBJECT_MIN_DIST:
			continue
		var oblocked: bool = false
		for c in _cities:
			var cpp: Vector2i = c["pos"]
			if abs(cpp.x - opos.x) + abs(cpp.y - opos.y) < OBJECT_MIN_DIST:
				oblocked = true
				break
		if oblocked:
			continue
		for m in _monsters:
			if (m["pos"] as Vector2i) == opos:
				oblocked = true
				break
		if oblocked:
			continue
		for eo in _objects:
			if abs((eo["pos"] as Vector2i).x - opos.x) + abs((eo["pos"] as Vector2i).y - opos.y) < 2:
				oblocked = true
				break
		if oblocked:
			continue
		var idx: int = _objects.size()
		var kind: int = int(kind_plan[idx]) if idx < kind_plan.size() else OBJECT_PILE
		var resource: String = "gold"
		var gold_amt: int = MINE_GOLD_PER_TURN
		var guard_amt: int = rng.next_int(OBJECT_GUARD_MIN, OBJECT_GUARD_MAX)
		if kind == OBJECT_MINE:
			resource = String(MINE_KINDS[idx % MINE_KINDS.size()])
			if resource == "rare":
				resource = String(RARE_RESOURCES[rng.next_int(0, RARE_RESOURCES.size() - 1)])
			gold_amt = int(MINE_YIELD.get(resource, 1))
		elif kind == OBJECT_TREASURE:
			gold_amt = rng.next_int(TREASURE_GOLD_MIN, TREASURE_GOLD_MAX)
		elif kind >= OBJECT_SHRINE_ATT:
			# Bonus-Objekte: unbewacht, kein Gold-Ertrag. Was sie geben,
			# entscheidet _visit_bonus_object beim Betreten.
			guard_amt = 0
			gold_amt = 0
		else:
			# Ressourcen-Haufen: Rotation Holz/Erz/Edel, kleine Mengen,
			# hoechstens Mini-Wache (0-1) - fruehes "Einsammel-Futter".
			var pile_cycle: int = (idx - MINE_COUNT - TREASURE_COUNT) % 3
			match pile_cycle:
				0: resource = "wood"
				1: resource = "ore"
				_: resource = String(RARE_RESOURCES[rng.next_int(0, RARE_RESOURCES.size() - 1)])
			gold_amt = rng.next_int(5, 10) if pile_cycle < 2 else rng.next_int(2, 4)
			guard_amt = rng.next_int(0, 1)
		_objects.append({
			"pos": opos,
			"kind": kind,
			"owner": OWNER_NEUTRAL,
			"guard": guard_amt,
			# Wach-Kreatur gleich festlegen (It. 35), damit Karte und Kampf
			# dasselbe zeigen. Alte Spielstaende ohne das Feld leiten sie
			# aus Position und Wachstaerke ab (_object_guard_army).
			"guard_unit": _pick_monster_unit(max(1, guard_amt),
				rng.next_int(0, 1 << 20)) if guard_amt > 0 else "",
			"gold": gold_amt,
			"resource": resource,
		})

	_turn_number = 0
	_init_fog_arrays()
	_recompute_fog_player()
	for i in range(_enemies.size()):
		_recompute_fog_ai(i)

	_recompute_costs()
	_on_map_resized()
	_center_view_on(_hero.position)
	_update_labels()
	_set_combat("Kampf: noch keiner")
	_set_status("Seed %d  Reach %d  Tile %.1f" % [_seed, _costs.size(), _tile_size])


func _recompute_costs() -> void:
	# Ohne Helden gibt es keine Reichweite (M13b: der letzte kann fallen).
	if _hero == null:
		_costs = {}
		return
	_costs = _dijkstra(_hero.position, true, Skills.pathfinding_tier(_hero.skills))


func _init_fog_arrays() -> void:
	# Spieler-Fog + je ein Fog-Array pro KI auf HIDDEN setzen. Wird am
	# Start einer neuen Karte aufgerufen, danach nur noch per
	# _recompute_fog_player / _recompute_fog_ai gepflegt (setzt VISIBLE
	# zurueck auf EXPLORED und markiert neue Sichtfelder).
	var total: int = MAP_WIDTH * MAP_HEIGHT
	_fog_player.resize(total)
	for i in range(total):
		_fog_player[i] = FOG_HIDDEN
	for e in _enemies:
		var efog: Array = []
		efog.resize(total)
		for i in range(total):
			efog[i] = FOG_HIDDEN
		e["fog"] = efog


func _fog_mark(arr: Array, center: Vector2i, radius: int) -> void:
	# Manhattan-Scheibe um center auf VISIBLE. Randfelder (EXPLORED) bleiben
	# erst durch _recompute_fog erhalten, wenn diese Funktion vorher alles
	# VISIBLE -> EXPLORED demoted hat.
	for dy in range(-radius, radius + 1):
		var ay: int = center.y + dy
		if ay < 0 or ay >= MAP_HEIGHT:
			continue
		var remain: int = radius - abs(dy)
		for dx in range(-remain, remain + 1):
			var ax: int = center.x + dx
			if ax < 0 or ax >= MAP_WIDTH:
				continue
			arr[ay * MAP_WIDTH + ax] = FOG_VISIBLE


func _recompute_fog_player() -> void:
	# Wird nach Heldenbewegung und nach jedem KI-Zug aufgerufen. Setzt
	# erst VISIBLE zurueck auf EXPLORED, markiert dann alle aktuellen
	# Sichtquellen des Spielers (Held + eigene Staedte + eigene Minen/
	# Schatzfelder) und aktualisiert zum Schluss die Sichtungen der
	# KI-Helden (Ghost-Marker "Info rottet" im Draw).
	var arr: Array = _fog_player
	var total: int = MAP_WIDTH * MAP_HEIGHT
	for i in range(total):
		if int(arr[i]) == FOG_VISIBLE:
			arr[i] = FOG_EXPLORED
	# JEDER eigene Held deckt auf (M13a) - nicht nur der aktive. Sonst
	# sieht der Spieler beim Umschalten die Umgebung seines anderen Helden
	# nicht mehr, und der Nebel wechselt bei jedem Wechsel das Bild. Das
	# ist der Fehler, den der Save-Roundtrip-Test gefunden hat: einmal
	# aufgezeichnet mit Held A als aktivem, einmal mit B - zwei
	# verschiedene Nebelbilder.
	for h in _heroes:
		var ph: Hero = h as Hero
		if ph != null:
			_fog_mark(arr, ph.position, _hero_sight_of(ph))
	for city in _cities:
		if int(city["owner"]) == OWNER_HERO:
			_fog_mark(arr, Vector2i(city["pos"]), CITY_SIGHT)
	for obj in _objects:
		if int(obj.get("owner", OWNER_NEUTRAL)) == OWNER_HERO:
			_fog_mark(arr, Vector2i(obj["pos"]), OBJECT_SIGHT)
	for i in range(_enemies.size()):
		var eh: Hero = _enemies[i]["hero"] as Hero
		if eh == null:
			continue
		if _fog_get(arr, eh.position) == FOG_VISIBLE:
			_ai_seen_by_player[i]["pos"] = eh.position
			_ai_seen_by_player[i]["turn"] = _turn_number


func _recompute_fog_ai(idx: int) -> void:
	# Spiegel-Funktion zu _recompute_fog_player aus Sicht einer KI. Jede
	# KI pflegt ihr eigenes Fog-Array und ihre eigene Sichtung des
	# Spieler-Helden (relevant fuer Ziel-Auswahl "Hero jagen").
	if idx < 0 or idx >= _enemies.size():
		return
	var e: Dictionary = _enemies[idx]
	var arr: Array = e["fog"]
	var oid: int = int(e["owner_id"])
	var total: int = MAP_WIDTH * MAP_HEIGHT
	for j in range(total):
		if int(arr[j]) == FOG_VISIBLE:
			arr[j] = FOG_EXPLORED
	var eh: Hero = e["hero"] as Hero
	if eh != null:
		_fog_mark(arr, eh.position, HERO_SIGHT)
	for city in _cities:
		if int(city["owner"]) == oid:
			_fog_mark(arr, Vector2i(city["pos"]), CITY_SIGHT)
	for obj in _objects:
		if int(obj.get("owner", OWNER_NEUTRAL)) == oid:
			_fog_mark(arr, Vector2i(obj["pos"]), OBJECT_SIGHT)
	if _hero != null:
		if _fog_get(arr, _hero.position) == FOG_VISIBLE:
			e["player_last_seen_pos"] = _hero.position
			e["player_last_seen_turn"] = _turn_number
	# Rivalisierende KI-Helden: wenn aktuell im Sichtfeld, deren Position
	# und Runde merken. Target-Auswahl nutzt die Sichtungen genau wie
	# beim Spieler-Helden - damit greifen sich KIs im Free-for-All auch
	# untereinander an und bilden nicht automatisch eine 3v1-Front gegen
	# den Spieler.
	var rs: Dictionary = e.get("rivals_seen", {})
	for j in range(_enemies.size()):
		if j == idx:
			continue
		var rh: Hero = _enemies[j]["hero"] as Hero
		if rh == null:
			continue
		if _fog_get(arr, rh.position) == FOG_VISIBLE:
			var rid: int = int(_enemies[j]["owner_id"])
			rs[rid] = {"pos": rh.position, "turn": _turn_number}
	e["rivals_seen"] = rs


func _fog_get(arr: Array, p: Vector2i) -> int:
	if p.x < 0 or p.x >= MAP_WIDTH or p.y < 0 or p.y >= MAP_HEIGHT:
		return FOG_HIDDEN
	return int(arr[p.y * MAP_WIDTH + p.x])


func _is_ai_owner(owner: int) -> bool:
	return owner >= OWNER_AI_MIN and owner <= OWNER_AI_MAX


func _ai_index_for_owner(owner: int) -> int:
	for i in range(_enemies.size()):
		if int(_enemies[i]["owner_id"]) == owner:
			return i
	return -1


func _ai_index_at(pos: Vector2i) -> int:
	# Erste KI mit Held auf pos. Kollisionen koennen im Free-for-All
	# entstehen, wenn zwei KIs dasselbe Ziel nehmen - dann gewinnt die
	# mit niedrigerem Index (deterministisch).
	for i in range(_enemies.size()):
		var eh: Hero = _enemies[i]["hero"] as Hero
		if eh != null and eh.position == pos:
			return i
	return -1


# EINE Regel fuer alle drei Prognosen (Monster, Objekt-Wache, Garnison).
# Vorher stand die Dreifach-Abfrage dreimal im Zeichencode, jedes Mal mit
# eigenen Vergleichen - und alle drei verglichen Stueckzahlen.
#   rot  = die Verteidigung ist wertvoller als die eigene Armee
#   gelb = knapp: Sieg wahrscheinlich, aber mit Verlusten
#   gruen = mindestens doppelt so stark
const THREAT_SAFE_FACTOR := 2.0

func _threat_color(own_gold: int, threat_gold: int) -> Color:
	if threat_gold <= 0:
		return Color(0.45, 1.0, 0.45)
	if own_gold < threat_gold:
		return Color(1.0, 0.35, 0.35)
	if float(own_gold) >= float(threat_gold) * THREAT_SAFE_FACTOR:
		return Color(0.45, 1.0, 0.45)
	return Color(1.0, 0.92, 0.35)


func _ai_ring_color(owner_id: int) -> Color:
	# Ring-/Hero-Farbe pro KI-owner_id. Rot fuer die klassische "Gegner"-
	# Rolle (owner_id 1), violett und orange als Reserve fuer 2 und 3.
	match owner_id:
		1: return Color(0.85, 0.15, 0.15)
		2: return Color(0.70, 0.30, 0.85)
		3: return Color(0.95, 0.55, 0.15)
	return Color(0.85, 0.15, 0.15)


func _dijkstra(start: Vector2i, monsters_block: bool,
		pathfinding_tier: int = 0) -> Dictionary:
	# Dijkstra inline: static-Calls auf class_name Pathfinder liefern
	# im Android-Export leere Dicts zurueck (gleiches Problem wie bei
	# MapGen). Also hier direkt gerechnet.
	# monsters_block: wenn true (Spielerheld), blockieren Monster das
	# Durchlaufen. Fuer die Gegner-KI lassen wir das weg, damit der
	# Gegner nicht von Monstern eingekesselt wird (vereinfachtes AI).
	var tiles: Array = _map["tiles"]
	var costs: Dictionary = {}
	costs[start] = 0
	# 4 Richtungen als feste Vector2i-Variablen (statt Array-Literal
	# im for-Loop), damit GDScript keine Variant-Konvertierung braucht.
	var dir_e := Vector2i(1, 0)
	var dir_w := Vector2i(-1, 0)
	var dir_s := Vector2i(0, 1)
	var dir_n := Vector2i(0, -1)
	var open: Array = [start]
	var guard := 0
	var cap: int = MAP_WIDTH * MAP_HEIGHT * 4 + 10
	while open.size() > 0 and guard < cap:
		guard += 1
		var best_idx := 0
		var best_cost: int = int(costs[open[0]])
		for i in range(1, open.size()):
			var c: int = int(costs[open[i]])
			if c < best_cost:
				best_cost = c
				best_idx = i
		var cur: Vector2i = open[best_idx]
		open.remove_at(best_idx)
		var cur_cost: int = int(costs[cur])
		# Monster blockieren Durchlaufen: Feld ist erreichbar (bereits in
		# costs eingetragen), aber wir expandieren die Nachbarn nicht.
		# Start hat nie ein Monster drauf. Gegner-KI ignoriert Monster,
		# damit sie nicht eingekesselt wird.
		if monsters_block and cur != start and _monster_at(cur) >= 0:
			continue
		for di in range(4):
			var d: Vector2i = dir_e
			if di == 1: d = dir_w
			elif di == 2: d = dir_s
			elif di == 3: d = dir_n
			var nx: int = cur.x + d.x
			var ny: int = cur.y + d.y
			if nx < 0 or nx >= MAP_WIDTH or ny < 0 or ny >= MAP_HEIGHT:
				continue
			var t: int = int(tiles[ny * MAP_WIDTH + nx])
			# Kosten aus dem preload-Modul Movement: Cross-File-Aufrufe
			# ueber class_name (MapGen.terrain_cost) koennen im
			# Android-Export 0 liefern - dann waere das ganze Grid
			# unpassierbar und Held wie KI stehen fest. preload-Module
			# haben dieses Problem nicht (gleiches Muster wie Abilities
			# im Kampf-Screen), deshalb stehen die Zahlen jetzt EINMAL
			# im Baum statt dreimal.
			var step: int = Move.step_cost(t, pathfinding_tier)
			if step <= 0:
				continue
			var next_cost: int = cur_cost + step
			var key := Vector2i(nx, ny)
			if not costs.has(key) or next_cost < int(costs[key]):
				costs[key] = next_cost
				open.append(key)
	return costs


func _on_map_resized() -> void:
	if _map.is_empty():
		return
	# Feste Kachelgroesse - Karte darf groesser als der Viewport sein und
	# muss dann gescrollt werden. Falls die Karte trotzdem reinpasst,
	# zentriert _clamp_view_offset sie im Viewport.
	_tile_size = TILE_PX
	_clamp_view_offset()
	_request_redraw()


func _clamp_view_offset() -> void:
	# _view_offset ist die Pixel-Verschiebung des Karten-Origins (oben
	# links, Feld (0,0)). Bei Karte groesser als Viewport muss er
	# zwischen (viewport - map) und 0 liegen. Bei kleinerer Karte
	# zentrieren wir fest.
	var area: Vector2 = _map_area.size
	var map_px: Vector2 = Vector2(MAP_WIDTH, MAP_HEIGHT) * _tile_size
	if map_px.x <= area.x:
		_view_offset.x = (area.x - map_px.x) * 0.5
	else:
		_view_offset.x = clamp(_view_offset.x, area.x - map_px.x, 0.0)
	if map_px.y <= area.y:
		_view_offset.y = (area.y - map_px.y) * 0.5
	else:
		_view_offset.y = clamp(_view_offset.y, area.y - map_px.y, 0.0)


func _center_view_on(tile: Vector2i) -> void:
	# Viewport so verschieben, dass die Mitte der Kachel im Zentrum des
	# MapArea liegt. Danach clamp, damit wir nicht ins Leere scrollen.
	var area: Vector2 = _map_area.size
	var tile_center: Vector2 = Vector2(tile.x, tile.y) * _tile_size + Vector2(_tile_size, _tile_size) * 0.5
	_view_offset = area * 0.5 - tile_center
	_clamp_view_offset()
	_request_redraw()


# Kopfzeile. Vorher stand ALLES in einem rechtsbuendigen Label:
# "T4 W1 M1 J1 L2 0/10 G872 H15 E5 K3 1 Sk / 2 Zo / 1 Ge / 1 Va (+1) XP140".
# Auf dem Geraet war das ein Code-Streifen, den niemand lesen kann. Jetzt
# ZWEI gruppierte Zeilen, und die Armee ist ganz raus - die steht schon im
# Helden-Panel, wo Platz dafuer ist.
const TOPBAR_FONT_SIZE := 21


func _update_labels() -> void:
	var ml := get_node_or_null(mp_label_path) as Label
	if ml == null:
		return
	# Ohne Helden nur den Kalender zeigen (M13b: der letzte kann fallen,
	# und die Niederlage-Anzeige laeuft danach noch durch diese Funktion).
	if _hero == null:
		ml.text = "%s\nkein Held" % _calendar_long()
		return
	if ml.get_theme_font_size("font_size") != TOPBAR_FONT_SIZE:
		ml.add_theme_font_size_override("font_size", TOPBAR_FONT_SIZE)
	var bonus: int = _combat_bonus()
	var line1: Array = [
		_calendar_long(),
		"Stufe %d" % int(_hero.level),
		# In FELDERN, nicht in Punkten: die Punkte-Einheit ist seit M7
		# Teil 2 vierfach feiner (Movement.UNIT), und "Zug 40/40" liest
		# sich auf dem Handy wie ein Fehler.
		"Zug %d/%d" % [Move.tiles_of(int(_hero.mp)), Move.tiles_of(int(_hero.max_mp))],
	]
	# Wochenereignis (M12) nur nennen, wenn es eines gibt - "Ruhige Woche"
	# in jeder Zeile waere Rauschen.
	var wev: Dictionary = _week_event()
	if not WeekFx.is_quiet(wev):
		line1.append(String(wev.get("title", "")))
	if bonus > 0:
		line1.append("Kampf +%d" % bonus)
	# Laufende Schonfrist ohne Stadt (It. 38) - das ist die wichtigste
	# Information auf dem Bildschirm, solange sie laeuft.
	var grace: int = _grace_left()
	if grace >= 0:
		line1.append("OHNE STADT: %d Tage" % grace)
	# Ressourcen: nur Bestaende ungleich null, sonst wird die Zeile auf
	# schmalen Displays zu lang.
	var line2: Array = ["%d Gold" % _purse.get_amount("gold")]
	for rid in Wallet.RESOURCE_IDS:
		if rid == "gold":
			continue
		var amt: int = _purse.get_amount(rid)
		if amt > 0:
			line2.append("%d %s" % [amt, Wallet.short_name(rid)])
	line2.append("%d XP" % int(_hero.xp))
	ml.text = "  ".join(line1) + "\n" + "  ".join(line2)


# --- Kalender-Helper: duenne Delegates auf GameCalendar (core/), wo die
# Mathematik headless getestet wird (tools/test_core_logic.gd). ---
func _day_num() -> int:
	return GameCalendar.day_num(_turn_number)

func _day_of_week() -> int:
	return GameCalendar.day_of_week(_turn_number)

func _calendar_text() -> String:
	return GameCalendar.calendar_text(_turn_number)

func _calendar_long() -> String:
	return GameCalendar.calendar_long(_turn_number)


# --- Pool-Helper ---
# Wochen-Wachstum wird via Bresenham ueber 7 Tage verteilt (Mathe in
# GameCalendar.day_delta), Summe pro Woche entspricht WEEKLY_GROWTH[req].
# Pools stapeln sich - nichts verfaellt. Cap ist nur der Wochen-Durchsatz,
# kein Vorrats-Deckel.
# Ereignis der laufenden Woche. Deterministisch aus Seed und Wochennummer,
# deshalb ohne Zwischenspeicher - der Aufruf ist billig.
func _week_event() -> Dictionary:
	return WeekFx.for_week(_seed, GameCalendar.week_total(_turn_number),
		UnitType.all_ids())


# Einmalige Wirkungen zum Wochenstart. Wachstums-Faktoren laufen NICHT
# hier durch, die holt _pool_cap_for jeden Tag frisch aus _week_event().
func _apply_week_event_start() -> void:
	var ev: Dictionary = _week_event()
	if String(ev.get("kind", "")) != WeekFx.KIND_HARVEST:
		return
	var own: int = 0
	for c in _cities:
		if int(c["owner"]) == OWNER_HERO:
			own += 1
	if own <= 0:
		return
	var gold: int = own * WeekFx.HARVEST_GOLD_PER_CITY
	_purse.add("gold", gold)
	_turn_income += gold


func _pool_cap_for(uid: String) -> int:
	# M4: Wochenrate kommt aus units.json (designte Balance, z.B. 22
	# Speertraeger/Woche), nicht mehr pauschal pro Gebaeude.
	# M12: das Wochenereignis skaliert sie - EIN Ort, damit Tages-Tick und
	# Catch-up beim Neubau automatisch dasselbe rechnen.
	return WeekFx.apply_growth(_week_event(), uid, UnitType.growth_of(uid))


func _day_delta(cap: int, dow: int) -> int:
	return GameCalendar.day_delta(cap, dow)


# Alle Staedte bekommen die Tagesration fuer jedes ihrer produzierenden
# Gebaeude. Auch Neutrale/KI-Staedte ticken mit, damit Eroberung keinen
# Rueckstand auslaesst.
func _daily_pool_tick(dow: int) -> void:
	for c in _cities:
		var pools: Dictionary = c.get("pools", {}) as Dictionary
		var fid: int = int(c["faction"])
		for bid in c["buildings"]:
			for uid in UnitType.units_for_building(fid, String(bid)):
				var delta: int = _day_delta(_pool_cap_for(String(uid)), dow)
				if delta > 0:
					pools[uid] = int(pools.get(uid, 0)) + delta
		c["pools"] = pools


# Frisch gebautes Gebaeude bekommt den Catch-up dieser Woche: was waere
# bis heute geliefert worden, wenn das Gebaeude schon am Montag gestanden
# haette. So ist "Bau am Tag X" gleichwertig zu "stand schon" fuer die
# laufende Woche, ohne dass Tage nachtraeglich doppelt zaehlen.
func _prime_pool_for_building(city: Dictionary, bid: String) -> void:
	var fid: int = int(city["faction"])
	var dow: int = _day_of_week()
	var pools: Dictionary = city.get("pools", {}) as Dictionary
	for uid in UnitType.units_for_building(fid, bid):
		var catch_up: int = GameCalendar.catch_up(_pool_cap_for(String(uid)), dow)
		if catch_up > 0:
			pools[uid] = int(pools.get(uid, 0)) + catch_up
	city["pools"] = pools


func _build_combat_label() -> void:
	var lbl := Label.new()
	# Zwischen TopBar (y=32..96) und MapArea (y=120..). Volle Breite,
	# zentriert, damit die Sieg-Meldung nicht uebersehen wird.
	lbl.anchor_left = 0.0
	lbl.anchor_right = 1.0
	lbl.anchor_top = 0.0
	lbl.anchor_bottom = 0.0
	lbl.offset_left = 24
	lbl.offset_top = 100
	lbl.offset_right = -24
	lbl.offset_bottom = 170
	lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	lbl.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	lbl.add_theme_font_size_override("font_size", 34)
	lbl.add_theme_color_override("font_color", Color(1.0, 0.85, 0.35))
	lbl.mouse_filter = Control.MOUSE_FILTER_IGNORE
	lbl.text = "Kampf: noch keiner"
	add_child(lbl)
	_combat_label = lbl


func _set_combat(msg: String) -> void:
	if _combat_label != null:
		_combat_label.text = msg


func _draw_map() -> void:
	var tiles: Array = _map["tiles"]
	var origin := _map_origin()
	# Kampf-Prognose-Werte einmal vor den Schleifen, damit Staedte UND
	# Monster die gleiche Bonus-Logik fuer ihre Zahlen verwenden.
	var cbonus: int = _combat_bonus()
	var eff: int = _hero.total_count() + cbonus
	# Prognose-Farbe seit It. 38 ueber GOLD, nicht ueber Stueckzahlen. Der
	# Durchspiel-Test hat gezeigt, dass die alte Regel luegt: sie verglich
	# die ANZAHL eigener Einheiten mit der Monster-Staerke, und seit die
	# Monster echte Kreaturen sind, entspricht eine Staerke nicht mehr
	# einer vergleichbaren Einheit. Der Spieler verlor seine Armee an
	# einen Kampf, den die Karte gelb (= Sieg mit Verlusten) anzeigte.
	var eff_gold: int = _player_gold_power()
	var mfont: Font = ThemeDB.fallback_font
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			var ti: int = int(tiles[y * MAP_WIDTH + x])
			var pos := origin + Vector2(x * _tile_size, y * _tile_size)
			var rect := Rect2(pos, Vector2(_tile_size - 1.0, _tile_size - 1.0))
			var key := Vector2i(x, y)
			var fog: int = _fog_get(_fog_player, key)
			if fog == FOG_HIDDEN:
				# Gewolkte Nebelkachel statt Volltonschwarz - das schwarze
				# Raster nahm im Screenshot die halbe Karte ein.
				var ftex: Texture2D = _fog_texture(x, y)
				if ftex != null:
					_map_area.draw_texture_rect(ftex, rect, false)
				else:
					_map_area.draw_rect(rect, Color(0.04, 0.04, 0.06), true)
				continue
			var reachable: bool = _costs.has(key) and int(_costs[key]) <= _hero.mp
			# Terrain: zuerst Textur, sonst Color-Fallback. Fog-/Reachability-
			# Dim laeuft als schwarzes Alpha-Overlay, damit das Texturen-Bild
			# nicht doppelt eingefaerbt wird.
			var tex: Texture2D = _terrain_texture(ti, _tile_variant(x, y, TERRAIN_VARIANTS))
			if tex != null:
				_map_area.draw_texture_rect(tex, rect, false)
				_draw_fringes(x, y, ti, rect, tiles)
				if fog == FOG_EXPLORED:
					_map_area.draw_rect(rect, Color(0, 0, 0, 0.55), true)
				elif not reachable:
					_map_area.draw_rect(rect, Color(0, 0, 0, 0.30), true)
			else:
				var col := _terrain_color(ti)
				if fog == FOG_EXPLORED:
					col = col.darkened(0.55)
				elif not reachable:
					col = col.darkened(0.3)
				_map_area.draw_rect(rect, col, true)
			if fog == FOG_VISIBLE and reachable and key != _hero.position:
				_map_area.draw_rect(rect, Color(1.0, 1.0, 1.0, 0.25), false, 2.0)

	# Staedte: farbiges Viereck pro Fraktion. Neutraler Rand dunkel,
	# eigene Stadt bekommt dicken goldenen Rand. Wache-Staerke in der
	# Mitte, farbig nach Kampf-Prognose wie bei Monstern.
	for city in _cities:
		var cp: Vector2i = city["pos"]
		var cfog: int = _fog_get(_fog_player, cp)
		if cfog == FOG_HIDDEN:
			continue
		var fid: int = int(city["faction"])
		var owner: int = int(city["owner"])
		var cpos := origin + Vector2(cp.x * _tile_size, cp.y * _tile_size)
		# Sprite-Rect deckt das ganze Tile (mit minimalem Inset, damit der
		# Owner-Ring sauber sitzt). Faellt zurueck auf Farb-Rechteck wenn
		# kein Stadt-Sprite fuer die Fraktion existiert.
		var inset: float = _tile_size * 0.06
		var crect := Rect2(
			cpos + Vector2(inset, inset),
			Vector2(_tile_size - 1.0 - 2.0 * inset, _tile_size - 1.0 - 2.0 * inset)
		)
		var city_sprite_name: String = ""
		if fid >= 0 and fid < FACTION_DIRS.size():
			city_sprite_name = "cities/%s.svg" % String(FACTION_DIRS[fid])
		var city_tex: Texture2D = _world_texture(city_sprite_name) if city_sprite_name != "" else null
		if city_tex != null:
			_map_area.draw_texture_rect(city_tex, crect, false)
			if cfog == FOG_EXPLORED:
				_map_area.draw_rect(crect, Color(0, 0, 0, 0.55), true)
		else:
			# Fallback: alte farbige Box (wenn Asset fehlt).
			var fc: Color = FACTION_COLORS[fid] if fid >= 0 and fid < FACTION_COLORS.size() else Color.WHITE
			if cfog == FOG_EXPLORED:
				fc = fc.darkened(0.45)
			_map_area.draw_rect(crect, fc, true)
		# Owner-Ring (immer, ob Sprite oder Fallback)
		if owner == OWNER_HERO:
			_map_area.draw_rect(crect, Color(1.0, 0.85, 0.2), false, 4.0)
		elif owner >= OWNER_AI_MIN:
			_map_area.draw_rect(crect, _ai_ring_color(owner), false, 4.0)
		else:
			_map_area.draw_rect(crect, Color(0.1, 0.1, 0.12), false, 2.0)
		var garrison: int = Garrison.total(city.get("garrison_army", {}))
		if owner != OWNER_HERO and garrison > 0 and cfog == FOG_VISIBLE:
			var cdist: int = abs(cp.x - _hero.position.x) + abs(cp.y - _hero.position.y)
			var gtxt: String
			var gcol: Color
			if cdist <= MONSTER_VIEW_RANGE:
				gtxt = str(garrison)
				gcol = _threat_color(eff_gold,
					_threat_gold(city.get("garrison_army", {}) as Dictionary))
			else:
				gtxt = "?"
				gcol = Color(0.75, 0.75, 0.75)
			var gsize: int = int(_tile_size * 0.45)
			var gs := mfont.get_string_size(gtxt, HORIZONTAL_ALIGNMENT_CENTER, -1, gsize)
			var gcenter := cpos + Vector2(_tile_size * 0.5, _tile_size * 0.5)
			var gp := gcenter + Vector2(-gs.x * 0.5, gs.y * 0.3)
			# Dunkler Schatten fuer Lesbarkeit auf bunten Fraktions-Farben.
			_map_area.draw_string(mfont, gp + Vector2(2, 2), gtxt, HORIZONTAL_ALIGNMENT_CENTER, -1, gsize, Color(0, 0, 0, 0.8))
			_map_area.draw_string(mfont, gp, gtxt, HORIZONTAL_ALIGNMENT_CENTER, -1, gsize, gcol)

	# Monster: grauer Kreis mit Staerke-Zahl. Zahl UND Ring sind farbig
	# nach Kampf-Prognose:
	#   gruen = kein Verlust (Kampfkraft-Bonus deckt Schaden)
	#   gelb  = Sieg mit Verlusten
	#   rot   = Niederlage (Kampfkraft < Monster-Staerke)
	# Ausserhalb MONSTER_VIEW_RANGE erscheint "?" mit grauem Ring.
	var mfsize: int = int(_tile_size * 0.55)
	for m in _monsters:
		var mp: Vector2i = m["pos"]
		var mfog: int = _fog_get(_fog_player, mp)
		if mfog == FOG_HIDDEN:
			continue
		var mstr: int = int(m["strength"])
		var mpx := origin + Vector2(mp.x * _tile_size + _tile_size * 0.5, mp.y * _tile_size + _tile_size * 0.5)
		var mrad := _tile_size * 0.36
		var dist: int = abs(mp.x - _hero.position.x) + abs(mp.y - _hero.position.y)
		var txt: String
		var tcol: Color
		# Staerke steht erst unter halber Held-Sichtweite fest (Nahaufklae-
		# rung). Darueber hinaus bleibt das Monster sichtbar, aber mit "?".
		if mfog == FOG_VISIBLE and dist <= (HERO_SIGHT / 2):
			# Angezeigt wird die ANZAHL der Kreaturen (das sieht man auf
			# dem Feld), die FARBE kommt aus dem Gold-Vergleich.
			txt = str(_monster_count(m))
			tcol = _threat_color(eff_gold, _threat_gold_of_monster(m))
		else:
			txt = "?"
			tcol = Color(0.75, 0.75, 0.75)
		# Kreatur-Sprite statt abstrakter Scheibe (It. 35). Die Scheibe
		# bleibt als Untergrund - sie traegt den Prognose-Ring und hebt die
		# Figur vom Gelaende ab. Fehlt ein Sprite, bleibt es beim alten Bild.
		_map_area.draw_circle(mpx, mrad, Color(0.20, 0.20, 0.22))
		var mon_tex: Texture2D = UnitArt.texture_for(_monster_unit(m))
		if mon_tex != null:
			var msz: float = mrad * 1.72
			_map_area.draw_texture_rect(mon_tex,
				Rect2(mpx - Vector2(msz * 0.5, msz * 0.5), Vector2(msz, msz)),
				false)
			if mfog == FOG_EXPLORED:
				_map_area.draw_circle(mpx, mrad, Color(0, 0, 0, 0.5))
		_map_area.draw_arc(mpx, mrad, 0.0, TAU, 20, tcol, 4.0)
		var ts := mfont.get_string_size(txt, HORIZONTAL_ALIGNMENT_CENTER, -1, mfsize)
		var tp := mpx + Vector2(-ts.x * 0.5, ts.y * 0.35)
		_map_area.draw_string(mfont, tp, txt, HORIZONTAL_ALIGNMENT_CENTER, -1, mfsize, tcol)

	# Karten-Objekte: Goldmine (gold gefuelltes Quadrat) und Schatzkiste
	# (oranges Quadrat). Besitz wird ueber Rand-Farbe markiert: neutral
	# dunkel, HERO goldener Rand, ENEMY roter Rand. Wache-Zahl in der
	# Mitte mit Kampf-Prognose-Farbe (nur sichtbar in MONSTER_VIEW_RANGE).
	for obj in _objects:
		var op: Vector2i = obj["pos"]
		var ofog: int = _fog_get(_fog_player, op)
		if ofog == FOG_HIDDEN:
			continue
		var okind: int = int(obj["kind"])
		var oowner: int = int(obj.get("owner", OWNER_NEUTRAL))
		var opos := origin + Vector2(op.x * _tile_size, op.y * _tile_size)
		var oinset: float = _tile_size * 0.10
		var orect := Rect2(
			opos + Vector2(oinset, oinset),
			Vector2(_tile_size - 1.0 - 2.0 * oinset, _tile_size - 1.0 - 2.0 * oinset)
		)
		# Sprite-basiert: Mine/Truhe/Haufen als SVG. Fallback auf alte
		# Strich-Symbole wenn das Asset fehlt. Haufen werden per Modulate
		# in der Ressourcen-Farbe getoent.
		var obj_sprite: String = "objects/chest.svg"
		var obj_tint: Color = Color.WHITE
		if okind == OBJECT_MINE:
			obj_sprite = "objects/mine.svg"
		elif okind == OBJECT_PILE:
			obj_sprite = "objects/pile.svg"
			obj_tint = RESOURCE_COLORS.get(String(obj.get("resource", "gold")), Color.WHITE)
		elif OBJECT_SPRITES.has(okind):
			obj_sprite = "objects/%s.svg" % String(OBJECT_SPRITES[okind])
			# Verbrauchte Bonus-Objekte bleiben stehen, aber blass - der
			# Spieler soll sehen, wo er schon war, ohne hinzulaufen.
			if _bonus_spent(obj):
				obj_tint = Color(0.55, 0.55, 0.58)
		var obj_tex: Texture2D = _world_texture(obj_sprite)
		if obj_tex != null:
			_map_area.draw_texture_rect(obj_tex, orect, false, obj_tint)
			if ofog == FOG_EXPLORED:
				_map_area.draw_rect(orect, Color(0, 0, 0, 0.55), true)
		else:
			# Alte Fallback-Variante.
			var ofill: Color = Color(0.95, 0.80, 0.20) if okind == OBJECT_MINE else Color(0.85, 0.50, 0.20)
			if ofog == FOG_EXPLORED:
				ofill = ofill.darkened(0.45)
			_map_area.draw_rect(orect, ofill, true)
			var sym_col := Color(0.25, 0.15, 0.05)
			if okind == OBJECT_MINE:
				var sw: float = max(2.0, _tile_size * 0.06)
				var sr1 := orect.position
				var sr2 := orect.position + orect.size
				_map_area.draw_line(sr1, sr2, sym_col, sw)
				_map_area.draw_line(Vector2(sr1.x, sr2.y), Vector2(sr2.x, sr1.y), sym_col, sw)
			else:
				var lid_y: float = orect.position.y + orect.size.y * 0.38
				_map_area.draw_line(
					Vector2(orect.position.x, lid_y),
					Vector2(orect.position.x + orect.size.x, lid_y),
					sym_col,
					max(2.0, _tile_size * 0.05)
				)
				var lock_c := Vector2(
					orect.position.x + orect.size.x * 0.5,
					lid_y + orect.size.y * 0.18
				)
				_map_area.draw_circle(lock_c, max(2.0, _tile_size * 0.07), sym_col)
		if oowner == OWNER_HERO:
			_map_area.draw_rect(orect, Color(1.0, 0.85, 0.2), false, 4.0)
		elif oowner >= OWNER_AI_MIN:
			_map_area.draw_rect(orect, _ai_ring_color(oowner), false, 4.0)
		else:
			_map_area.draw_rect(orect, Color(0.1, 0.1, 0.12), false, 2.0)
		var ogd: int = int(obj.get("guard", 0))
		if ogd > 0 and ofog == FOG_VISIBLE:
			var odist: int = abs(op.x - _hero.position.x) + abs(op.y - _hero.position.y)
			var otxt: String
			var ocol: Color
			if odist <= MONSTER_VIEW_RANGE:
				# Zahl = Kreaturen der Wache, Farbe = Gold-Vergleich.
				var g_army: Dictionary = _object_guard_army(obj)
				var g_cnt: int = 0
				for gk in g_army.keys():
					g_cnt += int(g_army[gk])
				otxt = str(maxi(1, g_cnt))
				ocol = _threat_color(eff_gold, _threat_gold(g_army))
			else:
				otxt = "?"
				ocol = Color(0.75, 0.75, 0.75)
			var osize: int = int(_tile_size * 0.4)
			var oss := mfont.get_string_size(otxt, HORIZONTAL_ALIGNMENT_CENTER, -1, osize)
			var ocenter := opos + Vector2(_tile_size * 0.5, _tile_size * 0.5)
			var op2 := ocenter + Vector2(-oss.x * 0.5, oss.y * 0.3)
			_map_area.draw_string(mfont, op2 + Vector2(2, 2), otxt, HORIZONTAL_ALIGNMENT_CENTER, -1, osize, Color(0, 0, 0, 0.8))
			_map_area.draw_string(mfont, op2, otxt, HORIZONTAL_ALIGNMENT_CENTER, -1, osize, ocol)

	# ALLE eigenen Helden zeichnen (M13a). Der aktive bekommt den gelben
	# Ring - ohne ihn waere bei mehreren Helden nicht zu sehen, wen ein Tap
	# bewegt. Die inaktiven werden leicht abgedunkelt.
	var hero_tex: Texture2D = _world_texture("units/hero.svg")
	# EIN Radius fuer alle Helden-Marker (Spieler UND KI). Er stand vor dem
	# Umbau als `radius` vor dem Spieler-Block und wurde vom KI-Block
	# mitbenutzt; in der Schleife waere er lokal und der KI-Block saehe ihn
	# nicht mehr.
	var marker_radius: float = _tile_size * 0.35
	for hi in range(_heroes.size()):
		var ph: Hero = _heroes[hi] as Hero
		if ph == null:
			continue
		var active: bool = (hi == _active_hero)
		var hero_px := origin + Vector2(ph.position.x * _tile_size,
			ph.position.y * _tile_size)
		var center := hero_px + Vector2(_tile_size * 0.5, _tile_size * 0.5)
		if hero_tex != null:
			var hrect := Rect2(hero_px, Vector2(_tile_size - 1.0, _tile_size - 1.0))
			_map_area.draw_texture_rect(hero_tex, hrect, false,
				Color.WHITE if active else Color(0.72, 0.72, 0.76))
		else:
			_map_area.draw_circle(center, marker_radius, Color(1.0, 0.85, 0.2))
			_map_area.draw_arc(center, marker_radius, 0.0, TAU, 24,
				Color(0.2, 0.15, 0.05), 2.0)
		if active and _heroes.size() > 1:
			_map_area.draw_arc(center, marker_radius + 4.0, 0.0, TAU, 28,
				Color(1.0, 0.9, 0.3), 4.0)

	# KI-Helden: pro KI entweder voller Marker (in Sicht) oder Ghost an
	# zuletzt bekannter Position (Alpha ueber FOG_ROT_TURNS verblassend).
	# KIs tragen Ring-Farbe nach owner_id (1/2/3 -> rot/violett/orange),
	# damit man sie im Free-for-All unterscheiden kann.
	for i in range(_enemies.size()):
		var eh: Hero = _enemies[i]["hero"] as Hero
		var eoid: int = int(_enemies[i]["owner_id"])
		var efill: Color = _ai_ring_color(eoid)
		var ering: Color = efill.darkened(0.55)
		if eh != null:
			var ex := eh.position
			var efog: int = _fog_get(_fog_player, ex)
			if efog == FOG_VISIBLE:
				var epx := origin + Vector2(ex.x * _tile_size, ex.y * _tile_size)
				var ecenter := epx + Vector2(_tile_size * 0.5, _tile_size * 0.5)
				# Gegner als Sprite mit Fraktions-Modulate.
				var enemy_tex: Texture2D = _world_texture("units/enemy.svg")
				if enemy_tex != null:
					var erect := Rect2(epx, Vector2(_tile_size - 1.0, _tile_size - 1.0))
					_map_area.draw_texture_rect(enemy_tex, erect, false, efill)
				else:
					_map_area.draw_circle(ecenter, marker_radius, efill)
					_map_area.draw_arc(ecenter, marker_radius, 0.0, TAU, 24, ering, 2.0)
				var earmy: int = eh.total_count()
				var etxt: String = str(earmy)
				var ecol: Color
				if eff < earmy:
					ecol = Color(1.0, 0.35, 0.35)
				elif earmy - cbonus <= 0:
					ecol = Color(0.45, 1.0, 0.45)
				else:
					ecol = Color(1.0, 0.92, 0.35)
				var esize: int = int(_tile_size * 0.5)
				var es := mfont.get_string_size(etxt, HORIZONTAL_ALIGNMENT_CENTER, -1, esize)
				var epos := ecenter + Vector2(-es.x * 0.5, es.y * 0.35)
				_map_area.draw_string(mfont, epos + Vector2(2, 2), etxt, HORIZONTAL_ALIGNMENT_CENTER, -1, esize, Color(0, 0, 0, 0.8))
				_map_area.draw_string(mfont, epos, etxt, HORIZONTAL_ALIGNMENT_CENTER, -1, esize, ecol)
				continue
		# Held ist tot ODER aktuell nicht in Sicht: Ghost an letzter
		# Sichtungs-Position zeichnen, solange Info nicht verrottet ist.
		var seen: Dictionary = _ai_seen_by_player[i]
		var lpos: Vector2i = seen["pos"]
		if lpos.x < 0:
			continue
		var since: int = _turn_number - int(seen["turn"])
		if since >= FOG_ROT_TURNS:
			continue
		var alpha: float = 1.0 - float(since) / float(FOG_ROT_TURNS)
		var gpx := origin + Vector2(lpos.x * _tile_size, lpos.y * _tile_size)
		var gcenter := gpx + Vector2(_tile_size * 0.5, _tile_size * 0.5)
		_map_area.draw_circle(gcenter, marker_radius, Color(efill.r, efill.g, efill.b, 0.35 * alpha))
		_map_area.draw_arc(gcenter, marker_radius, 0.0, TAU, 24, Color(efill.r, efill.g, efill.b, alpha), 2.0)
		var qsize: int = int(_tile_size * 0.5)
		var qs := mfont.get_string_size("?", HORIZONTAL_ALIGNMENT_CENTER, -1, qsize)
		var qpos := gcenter + Vector2(-qs.x * 0.5, qs.y * 0.35)
		_map_area.draw_string(mfont, qpos, "?", HORIZONTAL_ALIGNMENT_CENTER, -1, qsize, Color(1.0, 0.6, 0.6, alpha))


func _terrain_color(t: int) -> Color:
	match t:
		MapGen.TILE_GRASS:    return Color(0.30, 0.55, 0.25)
		MapGen.TILE_FOREST:   return Color(0.15, 0.35, 0.18)
		MapGen.TILE_WATER:    return Color(0.18, 0.35, 0.65)
		MapGen.TILE_MOUNTAIN: return Color(0.45, 0.42, 0.40)
		MapGen.TILE_SAND:     return Color(0.85, 0.78, 0.48)
		MapGen.TILE_SWAMP:    return Color(0.35, 0.40, 0.22)
	return Color(0.5, 0.5, 0.5)


# Terrain-Texturen aus assets/world/terrain/<name>.svg. Liegt eine Datei,
# wird sie statt der flachen _terrain_color-Farbe gerendert. Negativ-Cache
# (null) wird gemerkt, sodass leere Slots null Kosten haben.
const TERRAIN_ASSET_PATH := "res://assets/world/terrain/%s.svg"
const TERRAIN_NAMES := {
	MapGen.TILE_GRASS:    "grass",
	MapGen.TILE_FOREST:   "forest",
	MapGen.TILE_WATER:    "water",
	MapGen.TILE_MOUNTAIN: "mountain",
	MapGen.TILE_SAND:     "sand",
	MapGen.TILE_SWAMP:    "swamp",
}
# Je Gelaendeart mehrere Kachel-Varianten (tools/gen_world_tiles.py).
# Vorher lag EINE Datei je Art - dieselbe Bluete an derselben Pixelposition
# auf jeder Wiese der Karte, auf dem Geraet ein Tapetenmuster.
const TERRAIN_VARIANTS := 6
const FOG_VARIANTS := 6
const FRINGE_SIDES := ["top", "right", "bottom", "left"]
# Deckkraft der Uebergangs-Franse. Hoeher wirkt wie ein Farbrand, niedriger
# ist auf dem Handy nicht mehr zu sehen.
# It. 34: von 0.40 auf 0.62. Die Franse selbst liegt bei 0.30/0.52
# Deckkraft in der SVG; mit 0.40 kam effektiv 0.12/0.21 heraus und die
# Gelaendegrenzen blieben in der komponierten Ansicht harte Treppen.
const FRINGE_ALPHA := 0.62
var _terrain_tex_cache: Dictionary = {}


# Variante deterministisch aus Feldkoordinate UND Karten-Seed: dieselbe
# Karte sieht nach Save/Load identisch aus, verschiedene Seeds streuen
# anders. Ganzzahl-Hash, damit kein RNG-Objekt pro Frame entsteht.
func _tile_variant(x: int, y: int, count: int) -> int:
	# Bit-Mischung ist noetig, nicht Kosmetik: mit dem rohen
	# "x*A ^ y*B ^ seed*C" wechselt die PARITAET des Hashs bei jedem Schritt
	# in x, weil A ungerade ist. Modulo 6 heisst das: waagerechte Nachbarn
	# bekamen NIE dieselbe Variante (der Test misst 0 % statt der erwarteten
	# ~17 %) - also ein verstecktes Schachbrett aus geraden und ungeraden
	# Varianten. Die zwei Shift-Multiply-Runden ziehen die hohen Bits nach
	# unten und loesen das auf.
	return absi(_mix_hash((x * 73856093) ^ (y * 19349663) ^ (_seed * 83492791))) % count


# Bit-Mischung als EIGENE Funktion (It. 35), weil sie jetzt zweimal
# gebraucht wird: fuer die Kachel-Variante und fuer die Monster-Kreatur.
# Zwei Shift-Multiply-Runden ziehen die hohen Bits nach unten.
func _mix_hash(h_in: int) -> int:
	var h: int = (h_in ^ (h_in >> 13)) * 1274126177
	return h ^ (h >> 16)


func _terrain_texture(t: int, variant: int = -1) -> Texture2D:
	var key: String = "%d:%d" % [t, variant]
	if _terrain_tex_cache.has(key):
		return _terrain_tex_cache[key] as Texture2D
	var name: String = String(TERRAIN_NAMES.get(t, ""))
	var tex: Texture2D = null
	if name != "":
		# Erst die Variante, dann die alte Datei ohne Suffix als Fallback -
		# so bleibt der Screen lauffaehig, falls der Generator nicht lief.
		var candidates: Array = []
		if variant >= 0:
			candidates.append(TERRAIN_ASSET_PATH % ("%s_%d" % [name, variant]))
		candidates.append(TERRAIN_ASSET_PATH % name)
		for path in candidates:
			if ResourceLoader.exists(String(path)):
				tex = load(String(path)) as Texture2D
				break
	_terrain_tex_cache[key] = tex
	return tex


func _fog_texture(x: int, y: int) -> Texture2D:
	var v: int = _tile_variant(x, y, FOG_VARIANTS)
	var key: String = "fog:%d" % v
	if _terrain_tex_cache.has(key):
		return _terrain_tex_cache[key] as Texture2D
	var path: String = TERRAIN_ASSET_PATH % ("fog_%d" % v)
	var tex: Texture2D = load(path) as Texture2D if ResourceLoader.exists(path) else null
	_terrain_tex_cache[key] = tex
	return tex


func _fringe_texture(side: String) -> Texture2D:
	var key: String = "fringe:%s" % side
	if _terrain_tex_cache.has(key):
		return _terrain_tex_cache[key] as Texture2D
	var path: String = TERRAIN_ASSET_PATH % ("fringe_%s" % side)
	var tex: Texture2D = load(path) as Texture2D if ResourceLoader.exists(path) else null
	_terrain_tex_cache[key] = tex
	return tex


# Weiche Uebergaenge: laeuft an einer Kante ein anderes Gelaende, wird die
# Franse in der Farbe des Nachbarn darueber gezeichnet - das Material des
# Nachbarn laeuft in die Kachel hinein. Vorher stiessen Gelaendearten mit
# kerzengeraden Kanten aneinander, die Karte las sich als Farbschachbrett.
func _draw_fringes(x: int, y: int, own: int, rect: Rect2, tiles: Array) -> void:
	var neighbours := [Vector2i(0, -1), Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0)]
	for i in range(4):
		var nx: int = x + neighbours[i].x
		var ny: int = y + neighbours[i].y
		if nx < 0 or ny < 0 or nx >= MAP_WIDTH or ny >= MAP_HEIGHT:
			continue
		var other: int = int(tiles[ny * MAP_WIDTH + nx])
		if other == own:
			continue
		var tex: Texture2D = _fringe_texture(String(FRINGE_SIDES[i]))
		if tex == null:
			continue
		var col: Color = _terrain_color(other)
		col.a = FRINGE_ALPHA
		_map_area.draw_texture_rect(tex, rect, false, col)


# Welt-Sprite-Cache (Staedte, Helden, Objekte). Schluessel = beliebiger
# Kurzname, Wert = Texture2D oder null wenn nicht gefunden.
var _world_tex_cache: Dictionary = {}
const WORLD_ASSET_BASE := "res://assets/world/"


func _world_texture(rel_path: String) -> Texture2D:
	if _world_tex_cache.has(rel_path):
		return _world_tex_cache[rel_path] as Texture2D
	var path: String = WORLD_ASSET_BASE + rel_path
	var tex: Texture2D = null
	if ResourceLoader.exists(path):
		tex = load(path) as Texture2D
	_world_tex_cache[rel_path] = tex
	return tex


func _terrain_name(t: int) -> String:
	match t:
		MapGen.TILE_GRASS:    return "Gras"
		MapGen.TILE_FOREST:   return "Wald"
		MapGen.TILE_WATER:    return "Wasser"
		MapGen.TILE_MOUNTAIN: return "Gebirge"
		MapGen.TILE_SAND:     return "Sand"
		MapGen.TILE_SWAMP:    return "Sumpf"
	return "Unbekannt"


func _map_origin() -> Vector2:
	# _clamp_view_offset haelt _view_offset bereits in gueltigen Grenzen
	# (zentriert oder geklemmt an Kartenrand). Draw und Tap-Transform
	# nutzen ausschliesslich diesen Wert, damit beides konsistent bleibt.
	return _view_offset


func _request_redraw() -> void:
	# Haupt-Karte und Minimap zusammen neu zeichnen. Einmal an allen
	# Aenderungspunkten (Bewegung, Fog, Stadt einnehmen, Viewport-Pan)
	# aufrufen, statt beide manuell zu koordinieren.
	if _map_area != null:
		_map_area.queue_redraw()
	if _minimap != null:
		_minimap.queue_redraw()


func _toggle_sound() -> void:
	var on: bool = Sound.toggle()
	var btn := get_node_or_null(sound_toggle_path) as Button
	if btn != null:
		btn.text = "Ton" if on else "Stumm"
	_set_status("Geraeusche %s" % ("an" if on else "aus"))


func _toggle_minimap() -> void:
	# Die Minimap liegt als Overlay oben rechts auf der Karte und fing
	# vorher Taps auf Staedte/Helden in dieser Region ab - das Panel
	# landete dann beim Minimap-Handler (Viewport zentrieren), nicht beim
	# Map-Handler. Der Umschalter blendet sie aus, damit Spieler Objekte
	# in der rechten oberen Ecke erreichen, ohne vorher panen zu muessen.
	if _minimap == null:
		return
	_minimap.visible = not _minimap.visible


func _on_minimap_input(event: InputEvent) -> void:
	# Tap auf Minimap springt mit dem Viewport zum entsprechenden Feld.
	# Drag auf der Minimap wird (noch) nicht unterstuetzt - einfacher
	# Tap-to-Jump reicht fuer Navigation.
	var pos := Vector2.ZERO
	var pressed: bool = false
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index != MOUSE_BUTTON_LEFT:
			return
		pressed = mb.pressed
		pos = mb.position
	elif event is InputEventScreenTouch:
		var st := event as InputEventScreenTouch
		pressed = st.pressed
		pos = st.position
	else:
		return
	if not pressed:
		return
	if _minimap == null:
		return
	var size: Vector2 = _minimap.size
	if size.x <= 0.0 or size.y <= 0.0:
		return
	var cell_w: float = size.x / float(MAP_WIDTH)
	var cell_h: float = size.y / float(MAP_HEIGHT)
	var tx: int = clamp(int(pos.x / cell_w), 0, MAP_WIDTH - 1)
	var ty: int = clamp(int(pos.y / cell_h), 0, MAP_HEIGHT - 1)
	_center_view_on(Vector2i(tx, ty))


func _draw_minimap() -> void:
	# Mini-Uebersicht: pro Kachel ein Farb-Rechteck (Fog dimmt EXPLORED,
	# versteckt HIDDEN), Helden-Positionen als farbige Punkte, Viewport-
	# Rechteck als heller Rahmen. Staedte bekommen einen duennen
	# Owner-farbigen Ring, damit man Machtverhaeltnisse sofort sieht.
	if _minimap == null or _map.is_empty():
		return
	var size: Vector2 = _minimap.size
	if size.x <= 0.0 or size.y <= 0.0:
		return
	var cw: float = size.x / float(MAP_WIDTH)
	var ch: float = size.y / float(MAP_HEIGHT)
	_minimap.draw_rect(Rect2(Vector2.ZERO, size), Color(0.05, 0.06, 0.08), true)
	var tiles: Array = _map["tiles"]
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			var fog: int = _fog_get(_fog_player, Vector2i(x, y))
			if fog == FOG_HIDDEN:
				continue
			var t: int = int(tiles[y * MAP_WIDTH + x])
			var col: Color = _terrain_color(t)
			if fog == FOG_EXPLORED:
				col = col.darkened(0.45)
			_minimap.draw_rect(Rect2(Vector2(x * cw, y * ch), Vector2(cw + 0.5, ch + 0.5)), col, true)
	# Staedte als kleine farbige Quadrate nach Besitzer (bzw. Faktion
	# bei neutral), damit man Konsolidierung auf einen Blick sieht.
	for city in _cities:
		var cp: Vector2i = city["pos"]
		if _fog_get(_fog_player, cp) == FOG_HIDDEN:
			continue
		var owner: int = int(city["owner"])
		var ccol: Color
		if owner == OWNER_HERO:
			ccol = Color(1.0, 0.85, 0.2)
		elif owner >= OWNER_AI_MIN:
			ccol = _ai_ring_color(owner)
		else:
			var fid: int = int(city["faction"])
			ccol = FACTION_COLORS[fid] if fid >= 0 and fid < FACTION_COLORS.size() else Color(0.6, 0.6, 0.6)
		var crect := Rect2(Vector2(cp.x * cw, cp.y * ch), Vector2(cw, ch))
		_minimap.draw_rect(crect, ccol, false, max(1.0, cw * 0.3))
	# Held als heller Punkt.
	if _hero != null:
		var hp: Vector2i = _hero.position
		var hpx := Vector2(hp.x * cw + cw * 0.5, hp.y * ch + ch * 0.5)
		_minimap.draw_circle(hpx, max(1.5, min(cw, ch) * 0.45), Color(1.0, 0.95, 0.4))
	# KI-Helden nur, wenn aktuell sichtbar (sonst waere Minimap ein
	# Aimbot). Ghost-Marker waeren overkill auf der kleinen Flaeche.
	for i in range(_enemies.size()):
		var eh: Hero = _enemies[i]["hero"] as Hero
		if eh == null:
			continue
		if _fog_get(_fog_player, eh.position) != FOG_VISIBLE:
			continue
		var ep := Vector2(eh.position.x * cw + cw * 0.5, eh.position.y * ch + ch * 0.5)
		_minimap.draw_circle(ep, max(1.5, min(cw, ch) * 0.45), _ai_ring_color(int(_enemies[i]["owner_id"])))
	# Viewport-Rahmen: Ausschnitt, der aktuell in MapArea sichtbar ist.
	var area: Vector2 = _map_area.size
	var vx: float = -_view_offset.x / _tile_size
	var vy: float = -_view_offset.y / _tile_size
	var vw: float = area.x / _tile_size
	var vh: float = area.y / _tile_size
	var vr := Rect2(Vector2(vx * cw, vy * ch), Vector2(vw * cw, vh * ch))
	_minimap.draw_rect(vr, Color(1.0, 1.0, 1.0, 0.85), false, 2.0)


func _on_map_input(event: InputEvent) -> void:
	# Nur Mouse-Events verarbeiten. Auf Android erzeugt Godot per Default
	# aus jedem Touch zusaetzlich ein emuliertes MouseButton-Event
	# (emulate_mouse_from_touch=true) - wenn wir beide Pfade behandeln,
	# feuert jeder Tap doppelt und Kaempfe triggerten zweimal. Das
	# Projekt-Default bleibt bewusst an, damit Standard-Buttons im
	# Hauptmenue auf Touch reagieren; hier verwerfen wir den Touch-Pfad.
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index != MOUSE_BUTTON_LEFT:
			return
		if mb.pressed:
			_begin_pan(mb.position)
		else:
			_end_pan(mb.position)
		return
	if event is InputEventMouseMotion:
		var mm := event as InputEventMouseMotion
		if _pan_active:
			_update_pan(mm.position)
		return


func _begin_pan(pos: Vector2) -> void:
	_pan_active = true
	_pan_moved = false
	_pan_start_pos = pos
	_pan_start_offset = _view_offset


func _update_pan(pos: Vector2) -> void:
	if not _pan_active:
		return
	var delta: Vector2 = pos - _pan_start_pos
	if not _pan_moved and delta.length() > DRAG_THRESHOLD:
		_pan_moved = true
	if _pan_moved:
		_view_offset = _pan_start_offset + delta
		_clamp_view_offset()
		_request_redraw()


func _end_pan(pos: Vector2) -> void:
	var was_drag: bool = _pan_moved
	_pan_active = false
	_pan_moved = false
	if was_drag:
		return
	_handle_tap(pos)


func _handle_tap(pos: Vector2) -> void:
	var origin := _map_origin()
	var local := pos - origin
	if _tile_size <= 0.0:
		_set_status("Tap ignoriert: tile_size=0")
		return
	var tx := int(local.x / _tile_size)
	var ty := int(local.y / _tile_size)
	if tx < 0 or tx >= MAP_WIDTH or ty < 0 or ty >= MAP_HEIGHT:
		_set_status("Tap ausserhalb (%d,%d)" % [tx, ty])
		return
	var target := Vector2i(tx, ty)

	# Tap auf einen ANDEREN eigenen Helden: umschalten statt hinlaufen
	# (M13a). Steht dort der aktive Held selbst, faellt der Tap durch - er
	# kann auf einer eigenen Stadt stehen, und dann soll das Stadt-Panel
	# aufgehen.
	var tapped_hero: int = _hero_index_at(target)
	if tapped_hero >= 0 and tapped_hero != _active_hero:
		_switch_hero(tapped_hero)
		return

	var target_city_idx: int = _city_at(target)
	# Eigene Stadt:
	#   - Held steht drauf            -> Panel oeffnen
	#   - Stadt ausser MP-Reichweite  -> Panel oeffnen (Remote-Management)
	#   - Stadt in MP-Reichweite      -> unten normale Lauf-Logik
	# So blockiert das Panel nicht das Hinlaufen, wenn eine eigene Stadt
	# gerade erreichbar ist (HoMM3-Flow: erst hinlaufen, naechster Tap
	# oeffnet dann die Stadt).
	if target_city_idx >= 0 and int(_cities[target_city_idx]["owner"]) == OWNER_HERO:
		if target == _hero.position:
			_show_city(target_city_idx)
			return
		var reachable: bool = _costs.has(target) and int(_costs[target]) <= _hero.mp
		if not reachable:
			_show_city(target_city_idx)
			return
		# Reachable: Laufen lassen, nicht aufschnappen.
	if target == _hero.position:
		_set_status("Tap auf Held (%d,%d)" % [tx, ty])
		return
	if not _costs.has(target):
		if target_city_idx >= 0:
			var fid0: int = int(_cities[target_city_idx]["faction"])
			_set_status("Stadt %s (%d,%d)" % [FACTION_NAMES[fid0], tx, ty])
		else:
			var tiles: Array = _map["tiles"]
			var tt: int = int(tiles[ty * MAP_WIDTH + tx])
			_set_status("Tap %s (%d,%d)" % [_terrain_name(tt), tx, ty])
		return
	var cost: int = int(_costs[target])
	if cost > _hero.mp:
		_set_status("Tap zu teuer: %d > %d Punkte" % [cost, _hero.mp])
		return

	# Terrain-Id des Zielfelds bestimmt Obstacle-Generierung im Taktikkampf
	# (Wald -> Baumstamm/Busch, Berg -> Stein, Sumpf -> Sumpf, etc.).
	var battle_terrain: int = int((_map["tiles"] as Array)[target.y * MAP_WIDTH + target.x])

	# Monster auf Zielfeld: Taktik-Kampf-Overlay (Flucht erlaubt).
	var mon_idx: int = _monster_at(target)
	if mon_idx >= 0:
		var mstr_m: int = int(_monsters[mon_idx]["strength"])
		var mon_pos: Vector2i = _monsters[mon_idx]["pos"]
		# Echte Kreatur in den Kampf geben statt der Menschen-Synthese.
		# "enemy_army" gibt es schon fuer Belagerungen - derselbe Weg.
		var mon_ctx: Dictionary = {
			"enemy_army": _monster_army(_monsters[mon_idx]),
		}
		_open_battle("Monster", mstr_m, true, battle_terrain, func(r: Dictionary) -> void:
			_on_monster_result(r, mon_pos, target, cost)
		, mon_ctx)
		return

	# Gegner-Held auf Zielfeld: Pflichtkampf (keine Flucht), bevor wir
	# eine evtl. dort stehende Stadt einnehmen. Bei Sieg: Held tot, Stadt
	# wird im Callback direkt geclaimt (ohne zusaetzliche Garnison).
	var ai_at_target: int = _ai_index_at(target)
	if ai_at_target >= 0:
		var eh_t: Hero = _enemies[ai_at_target]["hero"] as Hero
		var ai_idx_cap: int = ai_at_target
		# allow_flee=true seit It. 42: auch der Angreifer darf abbrechen.
		_open_battle("Gegner-Held", eh_t.total_count(), true, battle_terrain, func(r: Dictionary) -> void:
			_on_enemy_hero_result(r, target, cost, target_city_idx, ai_idx_cap)
		)
		return

	# Karten-Objekt auf Zielfeld: Wache (falls > 0) via Overlay, Einnahme
	# bzw. Einsammeln danach im Callback. Eigene Mine wird einfach betreten.
	var obj_idx: int = _object_at(target)
	if obj_idx >= 0:
		var obj: Dictionary = _objects[obj_idx]
		var okind: int = int(obj["kind"])
		var is_own_mine: bool = (okind == OBJECT_MINE and int(obj.get("owner", OWNER_NEUTRAL)) == OWNER_HERO)
		if not is_own_mine:
			var ogd: int = int(obj.get("guard", 0))
			if ogd > 0:
				var opos: Vector2i = target
				var guard_ctx: Dictionary = {
					"enemy_army": _object_guard_army(obj),
				}
				_open_battle("Wache", ogd, true, battle_terrain, func(r: Dictionary) -> void:
					_on_object_result(r, opos, target, cost)
				, guard_ctx)
				return
			# guard == 0: direktes Betreten / Einsammeln (siehe unten)

	# Stadt-Wache: Overlay-Kampf. Bei Sieg claimt Callback die Stadt.
	if target_city_idx >= 0 and int(_cities[target_city_idx]["owner"]) != OWNER_HERO:
		var tc: Dictionary = _cities[target_city_idx]
		var gar: Dictionary = tc.get("garrison_army", {}) as Dictionary
		if not Garrison.is_empty(gar):
			var cidx: int = target_city_idx
			var sctx: Dictionary = _siege_ctx_for(tc)
			sctx["enemy_army"] = gar
			_open_battle("Stadtwache", Garrison.total(gar), true, battle_terrain,
				func(r: Dictionary) -> void:
					_on_city_result(r, cidx, target, cost)
			, sctx)
			return

	# Kein Kampf noetig: Mine/Schatz/Stadt ohne Wache oder leeres Feld.
	# Objekt-Einnahme bzw. Schatz einsammeln, falls vorhanden.
	if obj_idx >= 0:
		var obj2: Dictionary = _objects[obj_idx]
		var okind2: int = int(obj2["kind"])
		if okind2 == OBJECT_MINE and int(obj2.get("owner", OWNER_NEUTRAL)) != OWNER_HERO:
			obj2["owner"] = OWNER_HERO
		elif okind2 == OBJECT_TREASURE:
			var reward: int = int(obj2["gold"])
			_purse.add("gold", reward)
			_objects.remove_at(obj_idx)
			Sound.play("coin")
			_set_combat("Schatz gefunden: +%d G" % reward)
		elif okind2 == OBJECT_PILE:
			var pres: String = String(obj2.get("resource", "gold"))
			var pamt: int = int(obj2["gold"])
			_purse.add(pres, pamt)
			_objects.remove_at(obj_idx)
			Sound.play("resource")
			_set_combat("Gefunden: +%d %s" % [pamt, Wallet.display_name(pres)])
		elif okind2 >= OBJECT_SHRINE_ATT:
			var bmsg: String = _visit_bonus_object(obj2)
			if bmsg != "":
				# "schon besucht" ist kein Erfolg - dann nur der Tap-Klick.
				Sound.play("ui_tap" if bmsg.contains("schon") else "recruit")
				_set_combat(bmsg)

	_hero.mp -= cost
	_hero.position = target
	var claimed := false
	if target_city_idx >= 0 and int(_cities[target_city_idx]["owner"]) != OWNER_HERO:
		_cities[target_city_idx]["owner"] = OWNER_HERO
		claimed = true
	_recompute_fog_player()
	_recompute_costs()
	_request_redraw()
	_update_labels()
	if claimed:
		var fid1: int = int(_cities[target_city_idx]["faction"])
		_set_status("Stadt %s eingenommen (%d Punkte)" % [FACTION_NAMES[fid1], cost])
		_check_victory()
	elif target_city_idx >= 0:
		var fid2: int = int(_cities[target_city_idx]["faction"])
		_set_status("Stadt %s (%d Punkte)" % [FACTION_NAMES[fid2], cost])
	else:
		_set_status("Zug -> (%d,%d) fuer %d Punkte" % [tx, ty, cost])


func _city_at(p: Vector2i) -> int:
	# Liefert Index in _cities oder -1.
	for i in range(_cities.size()):
		if _cities[i]["pos"] == p:
			return i
	return -1


# --- Helden anwerben (M13b) -----------------------------------------------

# Neuer Held in der gerade offenen eigenen Stadt. Kosten, Obergrenze und
# Startarmee entscheidet diese Funktion - der Stadtbildschirm zeigt nur
# einen Knopf.
func _on_hire_hero() -> void:
	if _selected_city < 0 or _selected_city >= _cities.size():
		return
	var city: Dictionary = _cities[_selected_city]
	if int(city.get("owner", OWNER_NEUTRAL)) != OWNER_HERO:
		_set_status("Anwerben nur in einer eigenen Stadt")
		return
	if _heroes.size() >= MAX_HEROES:
		_set_status("Maximal %d Helden" % MAX_HEROES)
		return
	if not _purse.can_afford(HERO_HIRE_COST):
		_set_status("Zu teuer: braucht %s" % Wallet.cost_text(HERO_HIRE_COST))
		return
	_purse.pay(HERO_HIRE_COST)
	var h := Hero.new(Vector2i(city["pos"]), BASE_MAX_MP)
	# Startarmee in der Fraktion DER STADT - nicht in der des Spielers:
	# eine erobere Ork-Stadt wirbt Orks an, und die Moral-Regel aus M6
	# (Fraktions-Mix kostet) wird damit zu einer echten Entscheidung.
	var fid: int = int(city.get("faction", _player_faction))
	h.add_units(UnitType.starter_id_for_faction(fid), HERO_HIRE_UNITS)
	h.mana = Spells.max_mana(int(h.knowledge))
	_heroes.append(h)
	_recalc_max_mp()
	h.mp = h.max_mp
	# PFLICHT bei jedem "Held dazu"-Pfad: Nebel und Reichweite neu rechnen.
	# Ohne das deckt der neue Held nichts auf und ein Save-Roundtrip
	# liefert ein anderes Nebelbild als der Zustand davor (Lehrgeld aus
	# M13a, festgehalten in test_multi_hero._add_hero).
	_recompute_fog_player()
	_recompute_costs()
	_update_labels()
	_request_redraw()
	Sound.play("recruit")
	_set_combat("Held angeworben (%d von %d) - %s" % [
		_heroes.size(), MAX_HEROES,
		Garrison.summary(h.army)])
	if _city_screen != null and _city_screen.visible:
		_city_screen.call("refresh", _city_ctx(_selected_city))


# --- Helden-Wechsel (M13a) ------------------------------------------------

# Index des eigenen Helden auf diesem Feld, oder -1.
func _hero_index_at(p: Vector2i) -> int:
	for i in range(_heroes.size()):
		var h: Hero = _heroes[i] as Hero
		if h != null and h.position == p:
			return i
	return -1


# Aktiven Helden wechseln. Die Reichweite MUSS neu gerechnet werden: sie
# haengt an Position, Bewegungspunkten und Wegfindung des Helden.
func _switch_hero(idx: int) -> void:
	if idx < 0 or idx >= _heroes.size() or idx == _active_hero:
		return
	_active_hero = idx
	_recompute_costs()
	_update_labels()
	_request_redraw()
	Sound.play("ui_tap")
	_set_status("Held %d von %d gewaehlt" % [idx + 1, _heroes.size()])


# --- Wandernde Monster (It. 35) -------------------------------------------

# Welche Kreatur steht auf diesem Monster-Feld, und wie viele?
#
# Die Kreatur steht im Monster-Dictionary ("unit"), sobald das Monster
# platziert wurde. ALTE SPIELSTAENDE haben das Feld nicht - dann wird es
# deterministisch aus Position und Staerke abgeleitet, damit kein
# SAVE_VERSION-Bump noetig ist und dasselbe Monster nach dem Laden dieselbe
# Kreatur zeigt.
func _monster_unit(m: Dictionary) -> String:
	var stored: String = String(m.get("unit", ""))
	if stored != "" and UnitType.hp_of(stored) > 0:
		return stored
	var mp: Vector2i = m.get("pos", Vector2i.ZERO)
	return _pick_monster_unit(int(m.get("strength", 1)),
		_mix_hash(mp.x * 73856093 + mp.y * 19349663 + _seed))


# Deterministische Wahl aus MONSTER_POOL: nur Kreaturen, die einzeln ins
# HP-Budget passen. Der Hash wird gemischt (gleiche Begruendung wie bei
# _tile_variant), sonst koppelt die Auswahl an die Feld-Paritaet.
func _pick_monster_unit(strength: int, h: int) -> String:
	var budget: float = float(max(1, strength) * MONSTER_GOLD_PER_STRENGTH)
	var fits: Array = []
	for uid in MONSTER_POOL:
		var price: int = UnitType.cost_of(String(uid))
		# Ein Regenerierer muss MONSTER_MIN_COUNT Mal ins Budget passen,
		# alle anderen wie bisher einmal.
		var need: int = MONSTER_MIN_COUNT if Abil.regenerates(String(uid)) else 1
		if price > 0 and float(price * need) <= budget * MONSTER_GOLD_TOLERANCE:
			fits.append(String(uid))
	if fits.is_empty():
		return "ork_goblin"
	return String(fits[abs(h) % fits.size()])


# Stackgroesse aus dem Gold-Budget. Mindestens 1, gedeckelt.
func _monster_count(m: Dictionary) -> int:
	var uid: String = _monster_unit(m)
	var price: int = max(1, UnitType.cost_of(uid))
	var budget: int = max(1, int(m.get("strength", 1))) * MONSTER_GOLD_PER_STRENGTH
	# ABRUNDEN, nicht runden: mit round() ergaben 60 Gold Budget bei einem
	# 40-Gold-Goblin zwei Goblins (80 Gold) - ein Drittel ueber Budget.
	# Aufgerundet wird nur die Untergrenze von einer Kreatur.
	# Untergrenze 1 wie bisher - ausser bei Regenerierern, die durch die
	# Auswahl oben ohnehin nur mit genug Budget vorkommen.
	var floor_n: int = MONSTER_MIN_COUNT if Abil.regenerates(uid) else 1
	return clampi(int(floor(float(budget) / float(price))),
		floor_n, MONSTER_MAX_COUNT)


# Gold-Wert einer Armee - das Kraftmass des Spiels (die Preise sind
# balanciert, siehe data/balance_notes.md). Basis fuer die Prognose-Farbe.
# Fuehrt Flucht oder Kapitulation aus. EIN Ort fuer alle Kampf-Ausgaenge,
# aufgerufen aus dem battle_finished-Trichter in _open_battle.
func _apply_retreat(h: Hero, result: Dictionary) -> void:
	var surrendered: bool = String(result.get("outcome", "")) == "surrender"
	var survivors: Dictionary = SaveCodec.int_dict(result.get("player_remaining", {}))
	if surrendered:
		var cost: Dictionary = {"gold": int(result.get("surrender_cost", 0))}
		if _purse.can_afford(cost):
			_purse.pay(cost)
		else:
			# Der Knopf war gesperrt, das darf nicht vorkommen. Wenn doch,
			# wird daraus eine Flucht - besser als eine Gratis-Rettung.
			surrendered = false
	if not _retreat_hero(h, surrendered, survivors):
		# Kein Rueckzugsziel. Der Knopf war dann unsichtbar, also
		# unerreichbar; die Armee ist trotzdem verloren.
		if h != null:
			h.army = {}
		_set_combat("Rueckzug ohne Ziel - Armee verloren")
		_update_labels()
		_request_redraw()
		return
	if surrendered:
		_set_combat("KAPITULIERT: -%d G, Armee gerettet, Rueckzug in die Stadt"
			% int(result.get("surrender_cost", 0)))
		_set_status("Kapituliert - Rueckzug in die Stadt")
	else:
		_set_combat("GEFLOHEN: Armee verloren, Held in Sicherheit")
		_set_status("Geflohen - die Armee ist verloren")
	Sound.play("ui_tap")


# Preis einer Kapitulation: der Wert der Armee, die dabei gerettet wird.
# Mindestpreis, damit ein Held mit zwei Goblins nicht fuer 80 Gold aus
# jedem Kampf spazieren kann.
func _surrender_cost_of(h: Hero) -> int:
	if h == null:
		return SURRENDER_COST_MIN
	return maxi(SURRENDER_COST_MIN,
		int(round(float(_army_gold(h.army)) * SURRENDER_COST_FACTOR)))


# Index der eigenen Stadt, die dem Punkt am naechsten liegt, oder -1.
# Chebyshev-Abstand und nicht der echte Weg: die Flucht ist kein Marsch,
# der Held taucht dort wieder auf.
func _nearest_own_city(from: Vector2i) -> int:
	var best: int = -1
	var best_d: int = 1 << 30
	for i in range(_cities.size()):
		if int(_cities[i]["owner"]) != OWNER_HERO:
			continue
		var cp: Vector2i = Vector2i(_cities[i]["pos"])
		var d: int = maxi(absi(cp.x - from.x), absi(cp.y - from.y))
		if d < best_d:
			best_d = d
			best = i
	return best


# Kann dieser Held ueberhaupt fliehen? Ohne eigene Stadt gibt es kein Ziel.
func _can_retreat(h: Hero) -> bool:
	return h != null and _nearest_own_city(h.position) >= 0


# EIN Ort fuer Flucht und Kapitulation. Der Held taucht in der naechsten
# eigenen Stadt auf, sein Tag ist zu Ende (mp = 0). `keep_army` trennt die
# beiden Faelle: Flucht verliert die Truppen, Kapitulation bezahlt sie.
#
# Reihenfolge ist wichtig: erst die Stadt suchen (sie haengt an der ALTEN
# Position), dann versetzen.
func _retreat_hero(h: Hero, keep_army: bool, survivors: Dictionary) -> bool:
	if h == null:
		return false
	var ci: int = _nearest_own_city(h.position)
	if ci < 0:
		return false
	h.army = survivors.duplicate() if keep_army else {}
	h.position = Vector2i(_cities[ci]["pos"])
	h.mp = 0
	# PFLICHT nach jeder Positionsaenderung eines eigenen Helden: Nebel und
	# Reichweite. Der Held steht jetzt woanders, und ohne das zeigt die
	# Karte die Reichweite von seinem alten Feld aus.
	_recompute_fog_player()
	_recompute_costs()
	_update_labels()
	_request_redraw()
	return true


func _army_gold(army: Dictionary) -> int:
	var total: int = 0
	for uid in army.keys():
		total += UnitType.cost_of(String(uid)) * int(army[uid])
	return total


# Kampfkraft des Spielers in Gold: Armee plus Kampfkraft-Bonus, wobei ein
# Bonuspunkt wie eine Tier-1-Einheit zaehlt.
func _player_gold_power() -> int:
	if _hero == null:
		return 0
	return _army_gold(_hero.army) \
		+ _combat_bonus() * MONSTER_GOLD_PER_STRENGTH


# Verteidigungswert eines Feldes in Gold. Monster und Objekt-Wachen
# rechnen ueber ihre Kreatur, Staedte ueber ihre echte Garnison.
# Bedrohung einer fremden Armee in Gold - das ist NICHT einfach ihr
# Kaufpreis. Ein regenerierender Stack ist deutlich mehr wert, als er
# kostet, weil er pro Runde einen Teil seiner Trefferpunkte zurueckholt:
# eine Armee, die weniger Schaden pro Runde macht als die Heilung, kann ihn
# GAR NICHT toeten, egal wie lange sie draufschlaegt.
#
# GEMESSEN, nicht geschaetzt (It. 42): ein EINZELNES Gespenst (170 Gold,
# regeneration_if_half_hp) hat 4 von 4 Kaempfen gegen 320 Gold Startarmee
# gewonnen und 0 von 4 gegen 480 Gold. Der Umschlagpunkt liegt bei etwa
# 2,4 - deshalb der Zuschlag 1 + 1,5 = 2,5 bei Stackgroesse 1. Ohne ihn hat
# die Karte genau diesen Kampf GRUEN gefaerbt, der Durchspiel-Test hat ihn
# genommen und das ganze Heer verloren: dieselbe Fehlerart wie It. 38, nur
# eine Ebene tiefer.
#
# WARUM DER ZUSCHLAG MIT DER STACKGROESSE FAELLT: Abilities.regen_hp heilt
# einen Anteil der max-HP der OBERSTEN EINHEIT, nicht des ganzen Stacks.
# Ein einzelnes Gespenst holt damit 7 von 25 HP pro Runde zurueck (28 %),
# zehn Gespenster dieselben 7 von 250 (3 %). Die Regeneration verduennt
# sich also - und der Zuschlag muss das mitmachen, sonst ueberschaetzt die
# Karte einen grossen Stack genauso stark wie den einzelnen.
const THREAT_REGEN_BONUS := 1.5

func _threat_gold(army: Dictionary) -> int:
	var total: int = 0
	for uid in army.keys():
		var u: String = String(uid)
		var cnt: int = int(army[uid])
		var price: int = UnitType.cost_of(u) * cnt
		if cnt > 0 and Abil.regenerates(u):
			price = int(round(float(price)
				* (1.0 + THREAT_REGEN_BONUS / float(cnt))))
		total += price
	return total


func _threat_gold_of_monster(m: Dictionary) -> int:
	return _threat_gold(_monster_army(m))


func _monster_army(m: Dictionary) -> Dictionary:
	return {_monster_unit(m): _monster_count(m)}


# Wachen an Karten-Objekten (It. 35): dieselbe Herleitung wie beim
# wandernden Monster. Vorher waren ALLE Wachen menschliche Speertraeger -
# eine Truhe im Ork-Gebiet wurde von drei Menschen gehuetet.
func _object_guard_army(obj: Dictionary) -> Dictionary:
	var g: int = int(obj.get("guard", 0))
	if g <= 0:
		return {}
	var fake: Dictionary = {
		"pos": obj.get("pos", Vector2i.ZERO),
		"strength": g,
		"unit": String(obj.get("guard_unit", "")),
	}
	return _monster_army(fake)


func _monster_at(p: Vector2i) -> int:
	for i in range(_monsters.size()):
		if (_monsters[i]["pos"] as Vector2i) == p:
			return i
	return -1


# Generisches Taktik-Kampf-Overlay. Host ruft _open_battle mit Gegner-
# Infos und einem Callback auf; der Callback bekommt das Ergebnis-
# Dictionary (outcome: "victory"/"defeat"/"flee", casualties: int) und
# ist fuer Belohnung und Bewegung verantwortlich. Der Level/Wachturm-
# Bonus fliesst in Att UND Def des Spieler-Stacks ein.
func _open_battle(opp_name: String, opp_army: int, allow_flee: bool, terrain_id: int,
		on_result: Callable, siege_ctx: Dictionary = {}) -> void:
	var bonus: int = _combat_bonus()
	var scene: PackedScene = load("res://scenes/TacticalBattle.tscn") as PackedScene
	if scene == null:
		push_error("TacticalBattle.tscn fehlt")
		return
	var overlay = scene.instantiate()
	add_child(overlay)
	# ZUERST verbinden, DANN set_battle (It. 38). Ein Kampf kann schon in
	# set_battle entschieden sein: der Screen ruft dort _step(), die
	# schnellere Gegnerseite zieht sofort, und faellt dabei der einzige
	# Verteidiger-Stack, feuert battle_finished noch INNERHALB von
	# set_battle. War der Empfaenger da noch nicht verbunden, ging das
	# Signal ins Leere: das Overlay blieb fuer immer im Baum stehen und der
	# Callback lief nie. Bei einem Verteidigungskampf setzt genau dieser
	# Callback die KI-Phase fort - die KI war ab da eingefroren, ohne
	# Absturz und ohne Meldung. Der Durchspiel-Test hat es gefunden: ab
	# Zug 3 fand er 14 Mal dasselbe tote Overlay.
	#
	# Kaempfte die Armee des HELDEN mit? Bei einem Verteidigungskampf um die
	# eigene Stadt steuert der Spieler die Garnison; Skelette gehoeren dann
	# nur dem Helden, wenn er selbst in der Stadt stand.
	var hero_fought: bool = (not siege_ctx.has("player_army")) \
		or bool(siege_ctx.get("hero_present", false))
	# DER Held, der jetzt kaempft - nicht `_hero` im Callback. Mit mehreren
	# Helden kann der aktive zwischen Kampfbeginn und Callback wechseln
	# (M13a-Falle, hier zum ersten Mal wirklich noetig: der Rueckzug
	# versetzt einen bestimmten Helden).
	var fighting_hero: Hero = _hero
	overlay.connect("battle_finished", func(result: Dictionary) -> void:
		# Verbrauchtes Mana zuerst uebernehmen - EIN Ort fuer alle
		# Kampf-Ausgaenge (Sieg, Niederlage, Flucht), statt in jedem der
		# fuenf Callbacks daran zu denken.
		if result.has("mana_left"):
			_hero.mana = clampi(int(result["mana_left"]), 0, _hero_max_mana())
		# Flucht und Kapitulation an EINEM Ort (It. 42): Held versetzen,
		# Armee bzw. Gold verrechnen. Der Callback laeuft danach TROTZDEM -
		# er muss die KI-Phase fortsetzen, sonst friert sie ein (die Falle
		# aus It. 38).
		var oc: String = String(result.get("outcome", ""))
		if oc == "flee" or oc == "surrender":
			_apply_retreat(fighting_hero, result)
		on_result.call(result)
		# Totenerweckung NACH dem Callback: der Verteidigungskampf verteilt
		# dort die Ueberlebenden neu und SETZT _hero.army komplett neu -
		# vorher eingehaengte Skelette waeren wieder verschwunden.
		if hero_fought and String(result.get("outcome", "")) == "victory":
			_apply_necromancy(int(result.get("enemy_killed_hp", 0)))
		overlay.queue_free()
	)
	if overlay.has_method("set_battle"):
		# Spieler-Seite: normalerweise die Heldenarmee. Bei einem
		# Verteidigungskampf um die eigene Stadt steuert der Spieler
		# stattdessen die Garnison (plus Held, falls er dort steht).
		var p_stacks: Array = _army_to_stacks(_hero.army)
		if siege_ctx.has("player_army"):
			p_stacks = Garrison.to_stacks(siege_ctx["player_army"] as Dictionary)
		# Gegner-Seite: echte Garnison-Einheiten, wenn vorhanden
		# (Stadt-Angriff), sonst die Groessen-Synthese fuer Monster und
		# Objektwachen. Fraktion aus dem Kontext, damit eine
		# Totenreich-Stadt sich mit Untoten verteidigt (M9).
		var e_stacks: Array
		if siege_ctx.has("enemy_army"):
			e_stacks = Garrison.to_stacks(siege_ctx["enemy_army"] as Dictionary)
		else:
			e_stacks = _build_enemy_stacks(opp_name, opp_army,
				int(siege_ctx.get("faction", -1)))
		overlay.call("set_battle", {
			"player_name": "Held",
			"player_stacks": p_stacks,
			# player_bonus bleibt fuer Alt-Aufrufer und Tests. NEU sind die
			# getrennten Werte: vorher hob derselbe Pauschalwert Angriff UND
			# Verteidigung, ein Angriffsbonus machte den Helden also auch
			# zaeher. Die Skill-Prozente rechnet der Weltkarten-Screen aus,
			# der Kampf-Screen sieht nie einen Skill.
			"player_bonus": bonus,
			"player_att": bonus + int(_hero.att),
			"player_def": bonus + int(_hero.def),
			"player_morale_bonus": Skills.morale_bonus(_hero.skills),
			"player_archery_pct": Skills.archery_pct(_hero.skills),
			"player_offense_pct": Skills.offense_pct(_hero.skills),
			"player_armorer_pct": Skills.armorer_pct(_hero.skills),
			# Taktik (M7 Teil 2): Spalten fuer die Aufstellungsphase. 0 =
			# keine Phase, der Kampf startet wie bisher sofort.
			"player_tactics": Skills.tactics_cols(_hero.skills),
			"player_mana": int(_hero.mana),
			"player_spell_power": int(_hero.spell_power),
			"player_spells": Spells.known(
				Spells.schools_for_faction(_player_faction),
				Skills.wisdom_tier(_hero.skills)),
			"enemy_name": opp_name,
			"enemy_stacks": e_stacks,
			# Flucht/Kapitulation nur mit einer eigenen Stadt als Ziel
			# (It. 42). Beim Verteidigungskampf um die eigene Stadt gibt
			# der Aufrufer allow_flee=false - man kann nicht aus der
			# eigenen Mauer fliehen (HoMM3-Regel).
			"allow_flee": allow_flee and _can_retreat(_hero),
			"allow_surrender": allow_flee and _can_retreat(_hero) \
				and _purse.get_amount("gold") >= _surrender_cost_of(_hero),
			"surrender_cost": _surrender_cost_of(_hero),
			"seed": _seed,
			"terrain_id": terrain_id,
			"player_luck": _player_luck(),
			"siege": bool(siege_ctx.get("siege", false)),
			"tower_dmg": int(siege_ctx.get("tower_dmg", 0)),
		})


# Zerlegt eine Gegner-Armee-Groesse in gemischte Stacks, abhaengig von
# der Quelle des Kampfes. Wachen bleiben reine Schwerter (einfache
# Verteidiger), Monster werden ab mittlerer Groesse gemischt (Bogen,
# Reiter), der Feind-Held erbt seine tatsaechliche Rekrutierungs-
# zusammensetzung. Keine RNG noetig - rein deterministisch aus der
# Gesamtzahl, damit zwei Spieler mit gleichem Seed das gleiche Matchup
# sehen.
func _build_enemy_stacks(opp_name: String, total: int, faction: int = -1) -> Array:
	# Fraktion gesetzt (Stadt-Wache, Belagerung): aus den ersten drei
	# Tiers DIESER Fraktion mischen statt pauschal Menschen zu nehmen.
	if faction >= 0:
		return _faction_guard_stacks(faction, total)
	if total <= 0:
		return [{"type": "men_spearman", "count": 1}]
	# Der Feind-Held erbt seine tatsaechliche Rekrutierung direkt aus der
	# KI-Stadt. Alle anderen Gegner (Monster, Stadt-/Objektwachen) werden
	# nach Groesse gemischt - klein reine Schwert-Truppe, ab mittlerer
	# Groesse Bogen dazu, ab grosser Groesse auch Reiter.
	if opp_name == "Gegner-Held":
		# Spieler greift eine KI direkt an: Stacks aus deren Hero-Armee
		# ableiten. Finde die KI am Zielfeld - _enemies[i]["hero"].position
		# ist deterministisch; falls mehrere KIs kollidieren sollten,
		# nimmt _ai_index_at die erste.
		for e_i in _enemies:
			var he: Hero = e_i["hero"] as Hero
			if he != null and he.total_count() == total:
				return _army_to_stacks(he.army)
	if total <= 2:
		return [{"type": "men_spearman", "count": total}]
	if total <= 5:
		var bows: int = max(1, int(round(float(total) * 0.4)))
		var swords: int = total - bows
		return [{"type": "men_spearman", "count": swords}, {"type": "men_archer", "count": bows}]
	var riders: int = max(1, int(round(float(total) * 0.2)))
	var bows2: int = max(1, int(round(float(total) * 0.3)))
	var swords2: int = max(1, total - bows2 - riders)
	return [
		{"type": "men_spearman", "count": swords2},
		{"type": "men_archer", "count": bows2},
		{"type": "men_griffin", "count": riders},
	]


# Belagerungs-Kontext einer Zielstadt (M9): Fraktion immer, Mauer nur
# wenn gebaut. Der Pfeilturm wird von Wachtuermen der Stadt verstaerkt -
# so zahlt sich Ausbauen bei der Verteidigung aus.
func _siege_ctx_for(city: Dictionary) -> Dictionary:
	var built: Array = city.get("buildings", []) as Array
	var walled: bool = built.has("mauer")
	var tower: int = 0
	if walled:
		tower = SIEGE_TOWER_DMG
		if built.has("wachturm"):
			tower += SIEGE_TOWER_WACHTURM_BONUS
	return {
		"faction": int(city.get("faction", -1)),
		"siege": walled,
		"tower_dmg": tower,
	}


# Stadt-Wache einer Fraktion: gleiche Groessen-Staffelung wie die
# generische Synthese, aber mit den Einheiten der Stadt selbst (Tier 1-3).
func _faction_guard_stacks(fid: int, total: int) -> Array:
	var ids: Array = UnitType.recruitable_ids_for_faction(fid)
	if ids.is_empty():
		return [{"type": "men_spearman", "count": max(1, total)}]
	var t1: String = String(ids[0])
	var t2: String = String(ids[1]) if ids.size() > 1 else t1
	var t3: String = String(ids[2]) if ids.size() > 2 else t2
	if total <= 2:
		return [{"type": t1, "count": max(1, total)}]
	if total <= 5:
		var mid: int = max(1, int(round(float(total) * 0.4)))
		return [{"type": t1, "count": total - mid}, {"type": t2, "count": mid}]
	var high: int = max(1, int(round(float(total) * 0.2)))
	var mid2: int = max(1, int(round(float(total) * 0.3)))
	return [
		{"type": t1, "count": max(1, total - mid2 - high)},
		{"type": t2, "count": mid2},
		{"type": t3, "count": high},
	]


func _army_to_stacks(army: Dictionary) -> Array:
	var out: Array = []
	for uid in UnitType.all_ids():
		var cnt: int = int(army.get(uid, 0))
		if cnt > 0:
			out.append({"type": uid, "count": cnt})
	if out.is_empty():
		out.append({"type": "men_spearman", "count": 1})
	return out


func _apply_casualties(result: Dictionary) -> void:
	var cas = result.get("casualties", {})
	if cas is Dictionary:
		_hero.apply_casualties(cas)
	elif cas is int:
		_hero.apply_proportional_losses(int(cas))


func _count_casualties(result: Dictionary) -> int:
	var cas = result.get("casualties", {})
	if cas is Dictionary:
		var t := 0
		for v in (cas as Dictionary).values():
			t += int(v)
		return t
	return int(cas)


func _finish_move_to(target: Vector2i, cost: int) -> void:
	_hero.mp -= cost
	_hero.position = target
	_recompute_fog_player()
	_recompute_costs()
	_ensure_hero_in_view()
	_request_redraw()
	_update_labels()


func _ensure_hero_in_view() -> void:
	# Wenn der Held nach der Bewegung nicht mehr im Viewport ist (z.B.
	# weil der Spieler vorher frei gepannt hat), sanft nachfuehren. Ist
	# er noch sichtbar, wird der Pan-Zustand des Spielers respektiert.
	if _hero == null or _map_area == null:
		return
	var area: Vector2 = _map_area.size
	var hero_world: Vector2 = Vector2(_hero.position.x, _hero.position.y) * _tile_size + Vector2(_tile_size, _tile_size) * 0.5
	var on_screen: Vector2 = hero_world + _view_offset
	var margin: float = _tile_size
	var off: bool = (on_screen.x < margin or on_screen.x > area.x - margin
		or on_screen.y < margin or on_screen.y > area.y - margin)
	if off:
		_center_view_on(_hero.position)


# Ein Held ist gefallen (M13b). `fallen_idx` = -1 heisst "der aktive" - das
# ist der Normalfall, denn wer kaempft, ist der aktive Held. Der
# Verteidigungskampf um eine Stadt uebergibt den Index des Helden, der dort
# stand; das muss NICHT der aktive sein.
#
# Vorher endete hier IMMER das Spiel. Mit mehreren Helden waere das die
# Regel "verliere einen Helden, verliere alles" gewesen - dann waere ein
# zweiter Held nur ein Risiko und kein Gewinn.
func _on_battle_defeat(fallen_idx: int = -1) -> void:
	var idx: int = fallen_idx if fallen_idx >= 0 else _active_hero
	var fallen_name: String = "Held"
	# WICHTIG: der LETZTE Held bleibt in der Liste stehen.
	#
	# Vor M13b gab es immer genau einen Helden, und `_on_battle_defeat`
	# liess ihn stehen - der ganze Code darf sich also darauf verlassen,
	# dass `_hero` nie null ist. Wer ihn beim Spielende entfernt, bricht
	# diese Invariante an Dutzenden Stellen gleichzeitig: die
	# Niederlage-Anzeige, die Kopfzeile, die Reichweite und drei Suiten
	# liefen sofort in Nil-Zugriffe. Das Spiel ist dann ohnehin vorbei -
	# es gibt keinen Grund, dafuer einen Weltzustand zu erfinden, den es
	# nie gab.
	if _heroes.size() <= 1:
		_game_lost = true
		SaveLib.delete_autosave()
		_set_status("NIEDERLAGE")
		_set_combat("NIEDERLAGE: letzter Held gefallen")
		_show_defeat_panel()
		return
	if idx >= 0 and idx < _heroes.size():
		fallen_name = "Held %d" % (idx + 1)
		_heroes.remove_at(idx)
	if not _heroes.is_empty():
		# Weiterspielen mit den uebrigen Helden.
		_active_hero = clampi(_active_hero if _active_hero < idx else _active_hero - 1,
			0, _heroes.size() - 1)
		_set_combat("%s gefallen - %d Held(en) bleiben" % [fallen_name, _heroes.size()])
		Sound.play("defeat")
		_recompute_fog_player()
		_recompute_costs()
		_update_labels()
		_request_redraw()
		# Ohne Stadt laeuft ab jetzt die Schonfrist (It. 38) - der Verlust
		# eines Helden kann also mittelbar doch das Spiel beenden.
		_check_defeat()


func _on_monster_result(result: Dictionary, mon_pos: Vector2i, target: Vector2i, cost: int) -> void:
	var outcome: String = String(result.get("outcome", "flee"))
	if outcome == "flee" or outcome == "surrender":
		# Rueckzug ist im Trichter (_apply_retreat) schon erledigt: der Held
		# steht in seiner Stadt. Hier bleibt nichts zu tun - kein Zug, kein
		# Gold, kein XP, und das Monster bleibt stehen.
		return
	if outcome == "defeat":
		_apply_casualties(result)
		_update_labels()
		_on_battle_defeat()
		return
	var mon_idx: int = _monster_at(mon_pos)
	if mon_idx < 0:
		return
	var mstr: int = int(_monsters[mon_idx]["strength"])
	var cas: int = _count_casualties(result)
	_apply_casualties(result)
	_purse.add("gold", MONSTER_VICTORY_GOLD)
	var xp_gain: int = mstr * XP_PER_STRENGTH
	_hero.xp += xp_gain
	var leveled: bool = _check_level_up()
	_monsters.remove_at(mon_idx)
	_finish_move_to(target, cost)
	var msg_win: String
	if leveled:
		msg_win = "SIEG! -%d A  +%d G  +%d XP  -->  LEVEL %d!" % [cas, MONSTER_VICTORY_GOLD, xp_gain, _hero.level]
	else:
		msg_win = "SIEG! -%d A  +%d G  +%d XP" % [cas, MONSTER_VICTORY_GOLD, xp_gain]
	_set_status(msg_win)
	_set_combat(msg_win)


func _on_enemy_hero_result(result: Dictionary, target: Vector2i, cost: int, target_city_idx: int, ai_idx: int = 0) -> void:
	var outcome: String = String(result.get("outcome", "flee"))
	if outcome == "flee" or outcome == "surrender":
		# Seit It. 42 ausschlagbar: der Rueckzug ist im Trichter erledigt,
		# der Gegner-Held bleibt stehen und behaelt seine Armee.
		return
	if outcome == "defeat":
		_apply_casualties(result)
		_update_labels()
		_on_battle_defeat()
		return
	var cas: int = _count_casualties(result)
	_apply_casualties(result)
	_purse.add("gold", ENEMY_DEFEAT_GOLD)
	_hero.xp += ENEMY_DEFEAT_XP
	var leveled: bool = _check_level_up()
	if ai_idx >= 0 and ai_idx < _enemies.size():
		_enemies[ai_idx]["hero"] = null
	_finish_move_to(target, cost)
	# Stadt auf dem Zielfeld direkt einnehmen (Gegner-Held war der Verteidiger).
	var claimed: bool = false
	if target_city_idx >= 0 and int(_cities[target_city_idx]["owner"]) != OWNER_HERO:
		_cities[target_city_idx]["owner"] = OWNER_HERO
		_cities[target_city_idx]["garrison_army"] = {}
		claimed = true
	var msg_h_win: String
	if leveled:
		msg_h_win = "Gegner besiegt: -%d A +%d G +%d XP -> LEVEL %d!" % [cas, ENEMY_DEFEAT_GOLD, ENEMY_DEFEAT_XP, _hero.level]
	else:
		msg_h_win = "Gegner besiegt: -%d A +%d G +%d XP" % [cas, ENEMY_DEFEAT_GOLD, ENEMY_DEFEAT_XP]
	_set_status(msg_h_win)
	_set_combat(msg_h_win)
	if claimed:
		_check_victory()


func _on_object_result(result: Dictionary, obj_pos: Vector2i, target: Vector2i, cost: int) -> void:
	var outcome: String = String(result.get("outcome", "flee"))
	if outcome == "flee" or outcome == "surrender":
		# Rueckzug im Trichter erledigt; die Wache bleibt stehen und das
		# Objekt bleibt unangetastet.
		return
	if outcome == "defeat":
		_apply_casualties(result)
		_update_labels()
		_on_battle_defeat()
		return
	var obj_idx: int = _object_at(obj_pos)
	if obj_idx < 0:
		return
	var obj: Dictionary = _objects[obj_idx]
	var okind: int = int(obj["kind"])
	var ogd: int = int(obj.get("guard", 0))
	var cas: int = _count_casualties(result)
	_apply_casualties(result)
	var xp_o: int = ogd * XP_PER_STRENGTH
	_hero.xp += xp_o
	var lvl_o: bool = _check_level_up()
	obj["guard"] = 0
	var msg_og: String
	if lvl_o:
		msg_og = "Wache besiegt: -%d A +%d XP -> LEVEL %d!" % [cas, xp_o, _hero.level]
	else:
		msg_og = "Wache besiegt: -%d A +%d XP" % [cas, xp_o]
	_set_combat(msg_og)
	if okind == OBJECT_MINE:
		obj["owner"] = OWNER_HERO
	elif okind == OBJECT_TREASURE:
		var reward: int = int(obj["gold"])
		_purse.add("gold", reward)
		_objects.remove_at(obj_idx)
		_set_combat("Schatz gefunden: +%d G (Wache -%d A)" % [reward, cas])
	elif okind == OBJECT_PILE:
		var pres: String = String(obj.get("resource", "gold"))
		var pamt: int = int(obj["gold"])
		_purse.add(pres, pamt)
		_objects.remove_at(obj_idx)
		_set_combat("Gefunden: +%d %s (Wache -%d A)" % [pamt, Wallet.display_name(pres), cas])
	_finish_move_to(target, cost)


func _on_city_result(result: Dictionary, city_idx: int, target: Vector2i, cost: int) -> void:
	var outcome: String = String(result.get("outcome", "flee"))
	if outcome == "flee" or outcome == "surrender":
		# Abgebrochene Belagerung. Der Rueckzug ist im Trichter erledigt;
		# die Garnison bleibt ungeschwaecht stehen, denn ihre Verluste
		# gehoeren zum Kampf, den der Spieler nicht durchgezogen hat.
		return
	if outcome == "defeat":
		_apply_casualties(result)
		# Gescheiterte Belagerung: die Verteidiger haben Verluste und
		# bleiben in dieser Staerke stehen - der naechste Versuch ist
		# leichter. Vorher blieb die Garnison unversehrt.
		if city_idx >= 0 and city_idx < _cities.size():
			var lost_city: Dictionary = _cities[city_idx]
			lost_city["garrison_army"] = SaveCodec.int_dict(
				result.get("enemy_remaining", lost_city.get("garrison_army", {})))
		_update_labels()
		_on_battle_defeat()
		return
	if city_idx < 0 or city_idx >= _cities.size():
		return
	var tc: Dictionary = _cities[city_idx]
	var garrison: int = Garrison.total(tc.get("garrison_army", {}))
	var cas: int = _count_casualties(result)
	_apply_casualties(result)
	var xp_c: int = garrison * XP_PER_STRENGTH
	_hero.xp += xp_c
	var leveled_c: bool = _check_level_up()
	tc["garrison_army"] = {}
	tc["owner"] = OWNER_HERO
	_finish_move_to(target, cost)
	var fid: int = int(tc["faction"])
	var msg_c: String
	if leveled_c:
		msg_c = "Stadt %s: Wache besiegt (-%d A, +%d XP) -> LEVEL %d" % [FACTION_NAMES[fid], cas, xp_c, _hero.level]
	else:
		msg_c = "Stadt %s: Wache besiegt (-%d A, +%d XP)" % [FACTION_NAMES[fid], cas, xp_c]
	_set_status(msg_c)
	_set_combat(msg_c)
	_check_victory()


func _object_at(p: Vector2i) -> int:
	for i in range(_objects.size()):
		if (_objects[i]["pos"] as Vector2i) == p:
			return i
	return -1


func _check_victory() -> void:
	# Free-for-All-Sieg: alle anderen Fraktionen sind eliminiert - d.h.
	# keine KI besitzt mehr eine Stadt, und keine KI hat noch einen
	# lebenden Helden. Neutrale Staedte/Minen zaehlen nicht als Gegner;
	# der Spieler muss sie nicht einnehmen, um zu gewinnen.
	if _cities.size() == 0:
		return
	for c in _cities:
		var ow: int = int(c["owner"])
		if _is_ai_owner(ow):
			return
	for e in _enemies:
		var eh: Hero = e["hero"] as Hero
		if eh != null:
			return
	_game_won = true
	SaveLib.delete_autosave()
	_show_victory_panel()


func _show_victory_panel() -> void:
	Sound.play("victory")
	if _victory_panel == null:
		return
	if _victory_title != null:
		_victory_title.text = "GEWONNEN!"
		_victory_title.add_theme_color_override("font_color", Color(1.0, 0.85, 0.25))
	var vb := _victory_panel.get_node_or_null("VB") as VBoxContainer
	if vb != null:
		var stats := vb.get_node_or_null("Stats") as Label
		if stats != null:
			stats.text = _hero_stats_text()
	_victory_panel.visible = true


func _combat_bonus() -> int:
	# Kampfkraft-Bonus: Level-Bonus plus Wachturm-Bonus pro eigener Stadt.
	var b: int = LEVEL_COMBAT_BONUS * max(0, _hero.level - 1)
	b += WACHTURM_COMBAT_BONUS * _count_own_buildings("wachturm")
	return b


# Wie viele eigene Staedte haben dieses Gebaeude? (Einkommen, Boni.)
func _count_own_buildings(bid: String) -> int:
	var n: int = 0
	for c in _cities:
		if int(c["owner"]) == OWNER_HERO and (c["buildings"] as Array).has(bid):
			n += 1
	return n


# Glueck im Kampf (M6): +1 je Kapelle in eigenen Staedten, max +3.
# Damit hat die Kapelle neben den XP endlich eine Kampfwirkung.
func _player_luck() -> int:
	return min(LUCK_MAX, LUCK_PER_KAPELLE * _count_own_buildings("kapelle"))


func _check_level_up() -> bool:
	# Schleife, falls sehr viele XP auf einmal (z.B. spaeter aus Quests).
	# Jeder Aufstieg gibt Armee, hebt max_mp um LEVEL_BONUS_MP (wirksam beim
	# naechsten Ende-Zug) und - seit M7 - EINEN Primaerwert plus EINE
	# Skill-Wahl. Die Wahl kann nicht sofort erledigt werden (mehrere
	# Aufstiege auf einmal, und der Kampf-Overlay liegt evtl. noch oben),
	# deshalb landet sie in einer Warteschlange, die _drain_skill_queue
	# nacheinander abarbeitet.
	var leveled := false
	while _hero.level < LEVEL_THRESHOLDS.size() and _hero.xp >= int(LEVEL_THRESHOLDS[_hero.level]):
		_hero.level += 1
		_hero.add_units(UnitType.starter_id_for_faction(_player_faction), LEVEL_BONUS_ARMY)
		# Primaerwert fraktionsgewichtet. Eigener RNG aus Seed UND Stufe,
		# damit derselbe Spielstand denselben Aufstieg liefert und _rng
		# (Kartenlogik) unberuehrt bleibt.
		var lrng := RandomNumberGenerator.new()
		lrng.seed = _seed * 7919 + _hero.level * 104729
		var stat: String = Skills.roll_primary(lrng, _player_faction)
		_hero.add_primary(stat, 1)
		_last_level_stat = stat
		var offer: Array = Skills.offer(lrng, _hero.skills)
		if not offer.is_empty():
			_skill_queue.append(offer)
		leveled = true
	# Deferred: _check_level_up laeuft mitten in Kampf-Callbacks und im
	# Tageswechsel. Erst wenn der aktuelle Frame fertig ist (Kampf-Overlay
	# abgeraeumt, Statuszeilen gesetzt), darf die Wahl aufgehen.
	if leveled:
		Sound.play("level_up")
	if leveled and not _skill_queue.is_empty():
		call_deferred("_drain_skill_queue")
	return leveled


# Warteschlange der offenen Skill-Wahlen. Jeder Eintrag ist ein Array mit
# bis zu zwei Skill-IDs.
var _skill_queue: Array = []
var _last_level_stat: String = ""
var _skill_panel: Panel = null



# --- Heldenblatt (It. 29) -------------------------------------------------
# Die Kopfzeile hat in It. 19 die Armee-Liste abgegeben ("steht schon im
# Helden-Panel, wo Platz dafuer ist") - nur gab es dieses Panel nicht. Die
# eigene Armee war auf der Weltkarte damit NIRGENDS zu sehen, nur im
# Garnisons-Panel der Stadt und im Kampf. Das hier ist das fehlende Blatt:
# Werte, Skills und die Armee mit den Kreatur-Bildern.
const HERO_PANEL_ICON_PX := 96

var _hero_panel: Panel = null
var _hero_panel_stats: Label = null
var _hero_panel_switch: HBoxContainer = null
var _hero_panel_title: Label = null
var _hero_panel_army: VBoxContainer = null
var _hero_panel_spells: HBoxContainer = null


func _open_hero_panel() -> void:
	if _hero_panel == null:
		_build_hero_panel()
	_fill_hero_panel()
	_hero_panel.visible = true
	Sound.play("ui_tap")


func _build_hero_panel() -> void:
	var panel := Panel.new()
	panel.visible = false
	panel.anchor_left = 0.5
	panel.anchor_top = 0.5
	panel.anchor_right = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -470
	panel.offset_top = -620
	panel.offset_right = 470
	panel.offset_bottom = 620
	add_child(panel)
	_hero_panel = panel

	var bg := ColorRect.new()
	bg.color = Color(0.07, 0.08, 0.11, 1.0)
	bg.anchor_right = 1.0
	bg.anchor_bottom = 1.0
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(bg)

	var vb := VBoxContainer.new()
	vb.anchor_right = 1.0
	vb.anchor_bottom = 1.0
	vb.offset_left = 30
	vb.offset_top = 30
	vb.offset_right = -30
	vb.offset_bottom = -30
	vb.add_theme_constant_override("separation", 16)
	panel.add_child(vb)

	var title := Label.new()
	title.text = "Heldenblatt"
	_hero_panel_title = title
	title.add_theme_font_size_override("font_size", 40)
	title.add_theme_color_override("font_color", Color(0.95, 0.85, 0.40))
	vb.add_child(title)

	# Wechsel-Zeile (M13b): ein Knopf je Held. Kein neuer Platz in der
	# Kopfzeile noetig - das Blatt gibt es schon, und wer den Helden
	# wechseln will, schaut ohnehin auf seine Werte.
	_hero_panel_switch = HBoxContainer.new()
	_hero_panel_switch.add_theme_constant_override("separation", 12)
	vb.add_child(_hero_panel_switch)

	# Abenteuer-Zauber (It. 43). Eigene Zeile unter den Werten, ein Knopf je
	# Zauber - dieselbe Bauart wie die Wechsel-Zeile. Kein neuer Platz in
	# der Kopfzeile: wer zaubern will, schaut auf sein Mana, und das steht
	# hier.
	_hero_panel_spells = HBoxContainer.new()
	_hero_panel_spells.add_theme_constant_override("separation", 12)
	vb.add_child(_hero_panel_spells)

	_hero_panel_stats = Label.new()
	_hero_panel_stats.add_theme_font_size_override("font_size", 26)
	_hero_panel_stats.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(_hero_panel_stats)

	var army_title := Label.new()
	army_title.text = "Armee"
	army_title.add_theme_font_size_override("font_size", 32)
	vb.add_child(army_title)

	# Scrollbar, weil sechs Stacks mit 96-px-Bildern das Panel auf einem
	# schmalen Geraet sonst sprengen.
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	vb.add_child(scroll)

	_hero_panel_army = VBoxContainer.new()
	_hero_panel_army.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_hero_panel_army.add_theme_constant_override("separation", 10)
	scroll.add_child(_hero_panel_army)

	var close_btn := Button.new()
	close_btn.text = "Schliessen"
	close_btn.custom_minimum_size = Vector2(0, 96)
	close_btn.add_theme_font_size_override("font_size", 30)
	close_btn.pressed.connect(func() -> void:
		_hero_panel.visible = false
		Sound.play("ui_back"))
	vb.add_child(close_btn)


func _fill_hero_panel() -> void:
	if _hero_panel_stats == null or _hero_panel_army == null:
		return
	# Wechsel-Knoepfe neu aufbauen: die Zahl der Helden aendert sich
	# (anwerben, fallen).
	if _hero_panel_switch != null:
		for c in _hero_panel_switch.get_children():
			c.queue_free()
		if _heroes.size() > 1:
			for i in range(_heroes.size()):
				var b := Button.new()
				var hh: Hero = _heroes[i] as Hero
				b.text = "Held %d (%d)" % [i + 1, hh.total_count() if hh != null else 0]
				b.add_theme_font_size_override("font_size", 26)
				b.custom_minimum_size = Vector2(0, 78)
				b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
				b.disabled = (i == _active_hero)
				var idx: int = i
				b.pressed.connect(func() -> void:
					_switch_hero(idx)
					_fill_hero_panel())
				_hero_panel_switch.add_child(b)
	_fill_adventure_spells()
	if _hero_panel_title != null:
		_hero_panel_title.text = "Heldenblatt" if _heroes.size() <= 1 \
			else "Heldenblatt - Held %d von %d" % [_active_hero + 1, _heroes.size()]
	_hero_panel_stats.text = _hero_stats_text()
	for c in _hero_panel_army.get_children():
		c.queue_free()
	if _hero == null or _hero.army.is_empty():
		var empty := Label.new()
		empty.text = "Keine Einheiten - in der Stadt rekrutieren."
		empty.add_theme_font_size_override("font_size", 26)
		_hero_panel_army.add_child(empty)
		return
	# Reihenfolge stabil nach Tier, damit die Liste nicht bei jedem Oeffnen
	# springt (Dictionary-Reihenfolge folgt der Einfuegereihenfolge).
	var ids: Array = []
	for k in _hero.army.keys():
		ids.append(String(k))
	ids.sort_custom(func(a, b): return UnitType.tier_of(a) < UnitType.tier_of(b))
	for uid in ids:
		var u: String = String(uid)
		var cnt: int = int(_hero.army[u])
		if cnt <= 0:
			continue
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 14)
		_hero_panel_army.add_child(row)
		var icon: TextureRect = UnitArt.icon(u, HERO_PANEL_ICON_PX)
		if icon != null:
			row.add_child(icon)
		var lbl := Label.new()
		lbl.text = "%d x %s (T%d)\n%s" % [cnt, UnitType.name_of(u),
			UnitType.tier_of(u), UnitArt.stat_line(u)]
		lbl.add_theme_font_size_override("font_size", 24)
		lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(lbl)


# Abenteuer-Zauber des aktiven Helden (It. 43). HoMM3 hat diese Kategorie
# von Anfang an; bei uns war sie leer - der Spieler konnte Weisheit III
# lernen, und Stadttor stand trotzdem nirgends.
func _fill_adventure_spells() -> void:
	if _hero_panel_spells == null:
		return
	for c in _hero_panel_spells.get_children():
		c.queue_free()
	if _hero == null:
		return
	var known: Array = Spells.known_adventure(
		Spells.schools_for_faction(_player_faction),
		Skills.wisdom_tier(_hero.skills))
	for sid in known:
		var spell: String = String(sid)
		var cost: int = Spells.cost_of(spell)
		var b := Button.new()
		b.text = "%s (%d Mana)" % [Spells.display_name(spell), cost]
		b.add_theme_font_size_override("font_size", 26)
		b.custom_minimum_size = Vector2(0, 78)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.disabled = not _can_cast_adventure(spell)
		b.pressed.connect(func() -> void: _cast_adventure(spell))
		_hero_panel_spells.add_child(b)


# Darf der aktive Held diesen Abenteuer-Zauber JETZT wirken? Mana, und was
# der Zauber selbst braucht.
func _can_cast_adventure(spell: String) -> bool:
	if _hero == null or _game_lost or _game_won:
		return false
	if int(_hero.mana) < Spells.cost_of(spell):
		return false
	if spell == "town_gate":
		# Ziel muss es geben, und auf der eigenen Stadt zu stehen waere
		# sinnlos. Beides hier pruefen, damit der Knopf die Wahrheit sagt
		# statt erst beim Druecken zu meckern.
		var ci: int = _nearest_own_city(_hero.position)
		return ci >= 0 and Vector2i(_cities[ci]["pos"]) != _hero.position
	return true


func _cast_adventure(spell: String) -> void:
	if not _can_cast_adventure(spell):
		return
	var cost: int = Spells.cost_of(spell)
	if spell == "town_gate":
		# Stadttor: der Held UND seine Armee gehen zur naechsten eigenen
		# Stadt. Genau der Weg, den _retreat_hero schon geht (It. 42) -
		# mit keep_army und seiner eigenen Armee als "Ueberlebende".
		#
		# Der Tag ist danach zu Ende (mp = 0, setzt _retreat_hero). HoMM3
		# macht es genauso: das Tor kostet die Restbewegung, sonst waere
		# jeder Zug ein Sprung hin und zurueck.
		if not _retreat_hero(_hero, true, _hero.army.duplicate()):
			return
		_hero.mana = maxi(0, int(_hero.mana) - cost)
		_set_combat("STADTTOR: Rueckkehr in die Stadt (-%d Mana)" % cost)
		_set_status("Stadttor - der Tag ist zu Ende")
		Sound.play("spell_hit")
		_fill_hero_panel()
		return


# EIN Ort fuer die Heldenwerte.# EIN Ort fuer die Heldenwerte. Der String stand vorher zweimal wortgleich
# im Code; mit Primaerwerten und Skills waere er auseinandergelaufen.
func _hero_stats_text() -> String:
	# Nach dem Tod des LETZTEN Helden gibt es keinen mehr - und genau dann
	# ruft `_show_defeat_panel` diese Funktion (M13b). Vorher lief das in
	# einen Nil-Zugriff auf `_hero.level`; der Test war trotzdem gruen, der
	# Fehler stand nur im Protokoll.
	if _hero == null:
		return "Kein Held mehr.\n%d Gold" % _purse.get_amount("gold")
	var lines: Array = [
		"Stufe %d   %d XP" % [int(_hero.level), int(_hero.xp)],
		"Angriff %d   Verteidigung %d" % [int(_hero.att), int(_hero.def)],
		"Zauberkraft %d   Wissen %d   Mana %d/%d" % [
			int(_hero.spell_power), int(_hero.knowledge),
			int(_hero.mana), _hero_max_mana()],
		"%d Gold   Armee %d" % [_purse.get_amount("gold"), _hero.total_count()],
	]
	if not _hero.skills.is_empty():
		var parts: Array = []
		for sid in _hero.skills.keys():
			parts.append(Skills.summary_line(String(sid), int(_hero.skills[sid])))
		lines.append("  ".join(parts))
	return "\n".join(lines)


func _drain_skill_queue() -> void:
	if _skill_queue.is_empty():
		if _skill_panel != null:
			_skill_panel.visible = false
		return
	_show_skill_choice(_skill_queue[0] as Array)


func _show_skill_choice(offer: Array) -> void:
	if _skill_panel == null:
		_build_skill_panel()
	var vb := _skill_panel.get_node("VB") as VBoxContainer
	for child in vb.get_children():
		child.queue_free()
	var title := Label.new()
	title.text = "Stufe %d erreicht" % int(_hero.level)
	title.add_theme_font_size_override("font_size", 46)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(title)
	var sub := Label.new()
	sub.text = "%s +1 - jetzt eine Faehigkeit waehlen:" % Skills.PRIMARY_NAMES.get(
		_last_level_stat, _last_level_stat)
	sub.add_theme_font_size_override("font_size", 28)
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(sub)
	for sid in offer:
		var skill_id: String = String(sid)
		var cur: int = _hero.skill_tier(skill_id)
		var btn := Button.new()
		btn.custom_minimum_size = Vector2(0, 150)
		btn.add_theme_font_size_override("font_size", 30)
		btn.text = "%s %s\n%s" % [
			Skills.display_name(skill_id),
			"(neu)" if cur == 0 else "-> Stufe %d" % (cur + 1),
			Skills.next_tier_text(skill_id, _hero.skills)]
		btn.pressed.connect(_on_skill_picked.bind(skill_id))
		vb.add_child(btn)
	_skill_panel.visible = true


func _build_skill_panel() -> void:
	var panel := Panel.new()
	panel.visible = false
	panel.anchor_right = 1.0
	panel.anchor_bottom = 1.0
	add_child(panel)
	var bg := ColorRect.new()
	bg.color = Color(0.05, 0.06, 0.09, 0.96)
	bg.anchor_right = 1.0
	bg.anchor_bottom = 1.0
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(bg)
	var vb := VBoxContainer.new()
	vb.name = "VB"
	vb.anchor_right = 1.0
	vb.anchor_bottom = 1.0
	vb.offset_left = 50
	vb.offset_right = -50
	vb.offset_top = 240
	vb.offset_bottom = -240
	vb.add_theme_constant_override("separation", 28)
	panel.add_child(vb)
	_skill_panel = panel


func _on_skill_picked(skill_id: String) -> void:
	_hero.raise_skill(skill_id, Skills.MAX_TIER)
	if not _skill_queue.is_empty():
		_skill_queue.remove_at(0)
	_set_combat("%s gelernt: %s" % [
		Skills.display_name(skill_id),
		Skills.summary_line(skill_id, _hero.skill_tier(skill_id))])
	_recalc_max_mp()
	_update_labels()
	_request_redraw()
	# Naechste offene Wahl (mehrere Aufstiege auf einmal).
	_drain_skill_queue()


# EINE Stelle fuer max_mp: Basis + Spaeher-Gebaeude + Stufen-Bonus, darauf
# der Prozentaufschlag aus Logistik. Vorher stand die Formel nur im
# Tageswechsel; mit dem Skill muss sie auch nach einer Wahl neu laufen,
# sonst wirkt Logistik erst am naechsten Tag.
func _recalc_max_mp() -> void:
	# Alle Helden (M13a): Spaeher-Gebaeude gelten fuer den ganzen Spieler,
	# Stufe und Logistik sind pro Held verschieden.
	for h in _heroes:
		_recalc_max_mp_of(h as Hero)


func _recalc_max_mp_of(h: Hero) -> void:
	if h == null:
		return
	var base_mp: int = BASE_MAX_MP \
		+ MP_BONUS_SPAEHER * _count_own_buildings("spaeher") \
		+ LEVEL_BONUS_MP * max(0, h.level - 1)
	var pct: int = Skills.move_pct(h.skills)
	h.max_mp = base_mp + int(round(float(base_mp) * float(pct) / 100.0))



# --- Totenerweckung (M7 Teil 2) ------------------------------------------
# Nach einem gewonnenen Kampf steigt ein Teil der gefallenen Gegner als
# Skelette in die Heldenarmee. Gerechnet wird ueber die gefallenen
# TREFFERPUNKTE (HeroSkills.raised_skeletons), nicht ueber Koepfe.
#
# Skelette gibt es fuer JEDE Fraktion, nicht nur fuer das Totenreich - so
# ist es in HoMM3, und es hat einen Preis: Lebende und Untote in einer
# Armee kosten Moral (Morale.gd). Der Skill schliesst ausserdem Fuehrung
# aus (conflicts_with in skills.json), also entscheidet der Spieler
# zwischen Moral und Nachschub.
const NECRO_UNIT := "nec_skeleton"

func _apply_necromancy(killed_hp: int) -> String:
	if _hero == null:
		return ""
	var pct: int = Skills.necromancy_pct(_hero.skills)
	if pct <= 0 or killed_hp <= 0:
		return ""
	var raised: int = Skills.raised_skeletons(_hero.skills, killed_hp,
		UnitType.hp_of(NECRO_UNIT))
	if raised <= 0:
		return ""
	if not _hero.can_add_unit(NECRO_UNIT):
		# Armee voll und kein Skelett-Stack da: der Skill greift nicht
		# still ins Leere, der Spieler soll den Grund sehen.
		var full: String = "Totenerweckung: kein Platz fuer %d Skelette" % raised
		_set_combat(full)
		return full
	_hero.add_units(NECRO_UNIT, raised)
	var msg: String = "Totenerweckung: %d Skelette erhoben" % raised
	_set_combat(msg)
	_update_labels()
	_request_redraw()
	return msg


# --- Bonus-Objekte (M5) --------------------------------------------------
# Wirkung beim Betreten. Rueckgabe ist die Statusmeldung ("" = nichts
# passiert). Der Zustand steckt im Objekt selbst, damit er ohne
# Save-Migration mitgespeichert wird:
#   "used"      -> einmalige Objekte (Stat-Schreine, Lehrmeister)
#   "used_turn" -> Brunnen, einmal pro Tag
#   "used_week" -> Windmuehle, einmal pro Woche
# Verbraucht = jetzt nichts zu holen. Einmalige sind endgueltig durch,
# Brunnen und Windmuehle nur fuer heute bzw. diese Woche.
func _bonus_spent(obj: Dictionary) -> bool:
	var kind: int = int(obj["kind"])
	if kind == OBJECT_WELL:
		return int(obj.get("used_turn", -1)) == _turn_number
	if kind == OBJECT_WINDMILL:
		return int(obj.get("used_week", -1)) == GameCalendar.week_total(_turn_number)
	return bool(obj.get("used", false))


func _visit_bonus_object(obj: Dictionary) -> String:
	var kind: int = int(obj["kind"])

	if SHRINE_STATS.has(kind):
		var spec: Array = SHRINE_STATS[kind] as Array
		var stat_id: String = String(spec[0])
		var label: String = String(spec[1])
		if bool(obj.get("used", false)):
			return "%s: schon besucht." % label
		obj["used"] = true
		_hero.add_primary(stat_id, 1)
		# Wissen hebt den Mana-Deckel - das Mana soll sofort mitwachsen,
		# sonst wirkt der Garten erst am naechsten Tag.
		if stat_id == "knowledge":
			_hero.mana = min(_hero_max_mana(), int(_hero.mana) + Spells.MANA_PER_KNOWLEDGE)
		_recalc_max_mp()
		_update_labels()
		return "%s: %s +1" % [label, Skills.PRIMARY_NAMES.get(stat_id, stat_id)]

	if kind == OBJECT_WELL:
		if int(obj.get("used_turn", -1)) == _turn_number:
			return "Brunnen: heute schon genutzt."
		var cap: int = _hero_max_mana()
		if int(_hero.mana) >= cap:
			return "Brunnen: Mana ist voll."
		obj["used_turn"] = _turn_number
		var gained: int = cap - int(_hero.mana)
		_hero.mana = cap
		_update_labels()
		return "Brunnen: +%d Mana (%d/%d)" % [gained, cap, cap]

	if kind == OBJECT_LEARNING:
		if bool(obj.get("used", false)):
			return "Lehrmeister: schon gelernt."
		obj["used"] = true
		_hero.xp += LEARNING_XP
		var leveled: bool = _check_level_up()
		_update_labels()
		if leveled:
			return "Lehrmeister: +%d XP - Stufe %d!" % [LEARNING_XP, int(_hero.level)]
		return "Lehrmeister: +%d XP" % LEARNING_XP

	if kind == OBJECT_WINDMILL:
		var week: int = GameCalendar.week_total(_turn_number)
		if int(obj.get("used_week", -1)) == week:
			return "Windmuehle: diese Woche schon geleert."
		obj["used_week"] = week
		# Deterministisch aus Seed, Feld und Woche: derselbe Spielstand gibt
		# denselben Ertrag, aber jede Woche etwas anderes.
		var wrng := RandomNumberGenerator.new()
		var wp: Vector2i = obj["pos"]
		wrng.seed = _seed * 31 + wp.x * 7919 + wp.y * 104729 + week * 1299709
		var res: String = String(RARE_RESOURCES[wrng.randi_range(0, RARE_RESOURCES.size() - 1)])
		var amt: int = wrng.randi_range(WINDMILL_MIN, WINDMILL_MAX)
		_purse.add(res, amt)
		_update_labels()
		return "Windmuehle: +%d %s" % [amt, Wallet.display_name(res)]

	return ""


# Mana-Maximum aus Wissen (M8). Nicht gespeichert, immer abgeleitet -
# steigt das Wissen, steigt der Deckel sofort mit.
func _hero_max_mana() -> int:
	return Spells.max_mana(int(_hero.knowledge))


# Mana pro Tag: Grundregeneration plus Mystizismus.
const MANA_REGEN_PER_DAY := 1


func _regen_mana() -> void:
	# Jeder Held regeneriert sein eigenes Mana (M13a): Deckel und Zuwachs
	# haengen an Wissen und Mystizismus, also am einzelnen Helden.
	for h in _heroes:
		var hero: Hero = h as Hero
		if hero == null:
			continue
		var cap: int = Spells.max_mana(int(hero.knowledge))
		var gain: int = MANA_REGEN_PER_DAY + Skills.mana_regen(hero.skills)
		hero.mana = clampi(int(hero.mana) + gain, 0, cap)


# Sichtweite des AKTIVEN Helden: Grundwert plus Aufklaeren.
func _hero_sight() -> int:
	if _hero == null:
		return HERO_SIGHT
	return _hero_sight_of(_hero)


# Sichtweite eines bestimmten Helden (M13a): Aufklaeren ist ein Skill, also
# pro Held verschieden.
func _hero_sight_of(h: Hero) -> int:
	if h == null:
		return HERO_SIGHT
	return HERO_SIGHT + Skills.sight_bonus(h.skills)


func _build_victory_panel() -> void:
	# Vollbild-Overlay. Wird sichtbar, sobald alle Staedte dem Helden
	# gehoeren. "Neue Karte" startet per _on_reroll einen neuen Seed.
	var panel := Panel.new()
	panel.visible = false
	panel.anchor_right = 1.0
	panel.anchor_bottom = 1.0
	add_child(panel)
	_victory_panel = panel

	var bg := ColorRect.new()
	bg.color = Color(0.06, 0.08, 0.05, 0.96)
	bg.anchor_right = 1.0
	bg.anchor_bottom = 1.0
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(bg)

	var vb := VBoxContainer.new()
	vb.name = "VB"
	vb.anchor_right = 1.0
	vb.anchor_bottom = 1.0
	vb.offset_left = 60
	vb.offset_top = 400
	vb.offset_right = -60
	vb.offset_bottom = -400
	vb.add_theme_constant_override("separation", 40)
	vb.alignment = BoxContainer.ALIGNMENT_CENTER
	panel.add_child(vb)

	var title := Label.new()
	title.text = "GEWONNEN!"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 96)
	title.add_theme_color_override("font_color", Color(1.0, 0.85, 0.25))
	vb.add_child(title)
	_victory_title = title

	var sub := Label.new()
	sub.text = "Alle Staedte erobert"
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sub.add_theme_font_size_override("font_size", 40)
	vb.add_child(sub)

	var stats := Label.new()
	stats.name = "Stats"
	stats.text = ""
	stats.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	stats.add_theme_font_size_override("font_size", 36)
	vb.add_child(stats)

	var new_btn := Button.new()
	new_btn.text = "Neue Karte"
	new_btn.custom_minimum_size = Vector2(0, 140)
	new_btn.add_theme_font_size_override("font_size", 40)
	new_btn.pressed.connect(_on_victory_new_map)
	vb.add_child(new_btn)

	var back_btn := Button.new()
	back_btn.text = "Zurueck zum Menue"
	back_btn.custom_minimum_size = Vector2(0, 140)
	back_btn.add_theme_font_size_override("font_size", 40)
	back_btn.pressed.connect(_on_back)
	vb.add_child(back_btn)


func _on_victory_new_map() -> void:
	_victory_panel.visible = false
	_game_won = false
	_start(_seed + 1, _player_faction)


func _build_city_screen() -> void:
	var cs := CityScreen.new()
	cs.anchor_right = 1.0
	cs.anchor_bottom = 1.0
	add_child(cs)
	cs.build_requested.connect(_on_city_build)
	cs.recruit_requested.connect(_on_city_recruit)
	cs.plaza_tapped.connect(_set_status)
	cs.market_trade_requested.connect(_on_market_trade)
	cs.garrison_move_requested.connect(_on_garrison_move)
	cs.hire_hero_requested.connect(_on_hire_hero)
	cs.closed.connect(_on_city_closed)
	_city_screen = cs


# Baut das Kontext-Buendel, das die View zum Rendern braucht. Die View
# enthaelt keine Logik - alle Werte kommen von hier und werden bei jedem
# open()/refresh() neu gereicht.
func _city_ctx(city_idx: int) -> Dictionary:
	var city: Dictionary = _cities[city_idx]
	return {
		"city": city,
		# "hero" bleibt fuer die ARMEE (Garnisons-Panel). Der Geldbeutel
		# kommt seit M13a getrennt: er gehoert dem Spieler, nicht dem
		# Helden, und der CityScreen darf ihn nicht mehr aus dem Helden
		# lesen.
		"hero": _hero,
		"wallet": _purse,
		# Anwerben (M13b): der Screen zeigt nur an, gerechnet wird hier.
		"hire_cost": HERO_HIRE_COST,
		"hire_slots_left": max(0, MAX_HEROES - _heroes.size()),
		"own_city": int(city.get("owner", OWNER_NEUTRAL)) == OWNER_HERO,
		"buildings": BUILDINGS,
		"faction_names": FACTION_NAMES,
		"faction_colors": FACTION_COLORS,
		"market_buy": MARKET_BUY,
		"market_sell": MARKET_SELL,
		"calendar": _calendar_long(),
		# Wochenereignis (M12) gehoert in die Stadt: hier wird rekrutiert,
		# und "Woche des Greifs" aendert genau das.
		"week_event": String(_week_event().get("title", "")),
		"week_quiet": WeekFx.is_quiet(_week_event()),
		"hero_here": _hero != null and _hero.position == Vector2i(city["pos"]),
	}


# Einstieg fuer "Stadt oeffnen": gibt der CityScreen-Overlay den
# aktuellen Kontext. Wird auch von _buy_building/_recruit_unit am Ende
# aufgerufen und dient damit zugleich als Refresh nach Aktionen.
func _show_city(city_idx: int) -> void:
	_selected_city = city_idx
	if _city_screen != null:
		_city_screen.open(_city_ctx(city_idx))


func _on_city_build(building_id: String) -> void:
	if _selected_city < 0:
		return
	for i in range(BUILDINGS.size()):
		if String(BUILDINGS[i]["id"]) == building_id:
			_buy_building(_selected_city, i)
			return


func _on_city_recruit(unit_id: String) -> void:
	if _selected_city < 0:
		return
	_recruit_unit(_selected_city, unit_id)


func _on_garrison_move(unit_id: String, to_city: bool, all: bool) -> void:
	if _selected_city < 0:
		return
	_move_garrison(_selected_city, unit_id, to_city, all)


func _on_market_trade(res: String, buy: bool) -> void:
	# Markt-Tausch (nur Spieler; die KI tauscht nicht). Kurse siehe
	# MARKET_BUY/MARKET_SELL. Der CityScreen zeigt nur an - Mathe hier.
	if _selected_city < 0:
		return
	if buy:
		var price: int = int(MARKET_BUY.get(res, 0))
		if price <= 0 or not _purse.pay({"gold": price}):
			_set_status("Zu wenig Gold (%d G noetig)" % price)
			return
		_purse.add(res, 1)
		_set_status("Gekauft: +1 %s fuer %d G" % [Wallet.display_name(res), price])
	else:
		var gain: int = int(MARKET_SELL.get(res, 0))
		if gain <= 0 or _purse.get_amount(res) < 1:
			_set_status("Kein %s zum Verkaufen" % Wallet.display_name(res))
			return
		_purse.add(res, -1)
		_purse.add("gold", gain)
		_set_status("Verkauft: 1 %s fuer %d G" % [Wallet.display_name(res), gain])
	_update_labels()
	_show_city(_selected_city)


func _on_city_closed() -> void:
	_hide_city()


func _hide_city() -> void:
	if _city_screen != null:
		_city_screen.visible = false
	_selected_city = -1


func _buy_building(city_idx: int, bld_idx: int) -> void:
	var b: Dictionary = BUILDINGS[bld_idx]
	var bid: String = b["id"]
	var cost: Dictionary = b["cost"]
	if not _purse.can_afford(cost):
		_set_status("Zu teuer: braucht %s" % Wallet.cost_text(cost))
		return
	var city: Dictionary = _cities[city_idx]
	var built: Array = city["buildings"]
	if built.has(bid):
		return
	# Voraussetzungen pruefen (z.B. Zitadelle braucht Reiterei UND Mauer).
	for req in _requires_list(b):
		if not built.has(req):
			return
	built.append(bid)
	_prime_pool_for_building(city, bid)
	Sound.play("build")
	_purse.pay(cost)
	_update_labels()
	_set_status("Gebaut: " + str(b["name"]))
	_show_city(city_idx)


# "requires" eines Gebaeude-Eintrags tolerant lesen: String ODER Array
# von Gebaeude-ids (z.B. Zitadelle braucht Reiterei UND Mauer).
func _requires_list(def: Dictionary) -> Array:
	var raw: Variant = def.get("requires", null)
	if raw == null:
		return []
	if raw is Array:
		var out: Array = []
		for r in raw:
			out.append(String(r))
		return out
	return [String(raw)]


func _recruit_unit(city_idx: int, unit_id: String) -> void:
	# Voller Ressourcen-Preis aus units.json (M4 Teil 2): T6/T7 kosten
	# neben Gold auch Edel-Ressourcen (z.B. Engel 3500G + 1 Edelstein).
	var cost: Dictionary = UnitType.cost_dict_of(unit_id)
	if not _purse.can_afford(cost):
		_set_status("Zu teuer: braucht %s" % Wallet.cost_text(cost))
		return
	var city: Dictionary = _cities[city_idx]
	# Sicherheit: nur Einheiten der Stadt-Fraktion erlaubt. Falls ein
	# alter Button-Bind auf eine fremde Einheit verweist, abbrechen.
	if int(UnitType.faction_of(unit_id)) != int(city["faction"]):
		return
	var built: Array = city["buildings"]
	var req: String = UnitType.building_for(unit_id)
	if not built.has(req):
		return
	# Pool: leer = abwarten bis die Tagesration den naechsten Stack liefert.
	var pools: Dictionary = city.get("pools", {}) as Dictionary
	if int(pools.get(unit_id, 0)) <= 0:
		_set_status("Kein Nachschub")
		return
	# Steht der Held in der Stadt, bekommt er die Einheit. Sonst wandert
	# sie in die Garnison und verteidigt die Stadt - Fernverwaltung gibt
	# es ja schon (eigene Stadt aus der Ferne antippen).
	var hero_here: bool = _hero.position == Vector2i(city["pos"])
	if hero_here:
		# Stack-Limit: neuen Typ nur rein, wenn noch Slot frei ist.
		# Bestehende Stacks koennen immer aufstocken.
		if not _hero.can_add_unit(unit_id):
			_set_status("Armee voll - max %d Stacks" % Hero.MAX_ARMY_SLOTS)
			return
		_purse.pay(cost)
		_hero.add_units(unit_id, 1)
		_set_status("Rekrutiert: +1 %s" % UnitType.name_of(unit_id))
	else:
		_purse.pay(cost)
		var gar: Dictionary = city.get("garrison_army", {}) as Dictionary
		Garrison.add(gar, unit_id, 1)
		city["garrison_army"] = gar
		_set_status("In die Garnison: +1 %s" % UnitType.name_of(unit_id))
	Sound.play("recruit")
	pools[unit_id] = int(pools[unit_id]) - 1
	city["pools"] = pools
	_update_labels()
	_show_city(city_idx)


# Einheiten zwischen Held und Stadt-Garnison verschieben (CityScreen-
# Panel). to_city = true: vom Helden in die Stadt.
func _move_garrison(city_idx: int, unit_id: String, to_city: bool, all: bool) -> void:
	if city_idx < 0 or city_idx >= _cities.size():
		return
	var city: Dictionary = _cities[city_idx]
	if _hero == null or _hero.position != Vector2i(city["pos"]):
		_set_status("Held muss in der Stadt stehen")
		return
	var gar: Dictionary = city.get("garrison_army", {}) as Dictionary
	if to_city:
		var have: int = _hero.count_of(unit_id)
		if have <= 0:
			return
		var n: int = have if all else 1
		_hero.remove_units(unit_id, n)
		Garrison.add(gar, unit_id, n)
		_set_status("%d %s -> Garnison" % [n, UnitType.short_of(unit_id)])
	else:
		var in_city: int = int(gar.get(unit_id, 0))
		if in_city <= 0:
			return
		# Slot-Limit des Helden respektieren (max 6 Typen).
		if not _hero.can_add_unit(unit_id):
			_set_status("Armee voll - max %d Stacks" % Hero.MAX_ARMY_SLOTS)
			return
		var n2: int = in_city if all else 1
		Garrison.remove(gar, unit_id, n2)
		_hero.add_units(unit_id, n2)
		_set_status("%d %s -> Held" % [n2, UnitType.short_of(unit_id)])
	city["garrison_army"] = gar
	_update_labels()
	_show_city(city_idx)


func _building_by_id(bid: String) -> Dictionary:
	for b in BUILDINGS:
		if String(b["id"]) == bid:
			return b
	return {}


func _enemy_economy_for(idx: int) -> void:
	# Gegner spielt nach den gleichen Regeln wie der Spieler: Einkommen pro
	# eigener Stadt (+Markt), max_mp mit Spaeher. Danach Ausgaben nach
	# Prioritaet: Militaergebaeude -> Markt/Spaeher -> Mauer -> Zitadelle.
	# Sobald keine Prioritaets-Gebaeude mehr affordable sind, wird Ueberschuss
	# in Rekruten gesteckt - aus dem Pool der Stadt, auf der die KI steht.
	# Wachturm/Kapelle bringen dem Gegner (noch) nichts, daher ignoriert.
	if idx < 0 or idx >= _enemies.size():
		return
	var e: Dictionary = _enemies[idx]
	var eh: Hero = e["hero"] as Hero
	if eh == null:
		return
	var oid: int = int(e["owner_id"])
	var owned: int = 0
	var markt: int = 0
	var spaeher: int = 0
	for c in _cities:
		if int(c["owner"]) != oid:
			continue
		owned += 1
		var bl: Array = c["buildings"]
		if bl.has("markt"):
			markt += 1
		if bl.has("spaeher"):
			spaeher += 1
	eh.max_mp = ENEMY_BASE_MP + MP_BONUS_SPAEHER * spaeher
	var e_mine_income: int = 0
	for obj in _objects:
		if int(obj["kind"]) == OBJECT_MINE and int(obj.get("owner", OWNER_NEUTRAL)) == oid:
			var eres: String = String(obj.get("resource", "gold"))
			if eres == "gold":
				e_mine_income += int(obj["gold"])
			else:
				eh.wallet.add(eres, int(obj["gold"]))
	eh.gold += owned * CITY_INCOME + markt * INCOME_MARKT + e_mine_income
	# Symmetrie zum Spieler: Gebaeude bauen und Rekruten kaufen nur,
	# wenn der KI-Held aktuell auf einer eigenen Stadt steht. Sonst
	# waechst die Armee auf der Jagd durch Gratis-Einheiten und der
	# Spieler hat keine Chance. Gold stapelt sich und wird bei der
	# Rueckkehr in die Stadt ausgegeben - genau wie beim Spieler.
	var current_city: Dictionary = {}
	for c in _cities:
		if int(c["owner"]) == oid and Vector2i(c["pos"]) == eh.position:
			current_city = c
			break
	if current_city.is_empty():
		return
	var priority: Array = ["kaserne", "schmiede", "reiterei", "markt", "spaeher", "mauer", "zitadelle"]
	var guard: int = 0
	var spent: bool = true
	while spent and guard < 24:
		guard += 1
		spent = false
		for bid in priority:
			var bdef: Dictionary = _building_by_id(bid)
			if bdef.is_empty():
				continue
			var bcost: Dictionary = bdef["cost"]
			if not eh.wallet.can_afford(bcost):
				continue
			var reqs: Array = _requires_list(bdef)
			for c in _cities:
				if int(c["owner"]) != oid:
					continue
				var bl: Array = c["buildings"]
				if bl.has(bid):
					continue
				var reqs_ok: bool = true
				for req in reqs:
					if not bl.has(req):
						reqs_ok = false
						break
				if not reqs_ok:
					continue
				bl.append(bid)
				_prime_pool_for_building(c, bid)
				eh.wallet.pay(bcost)
				spent = true
				break
			if spent:
				break
		if spent:
			continue
		# Keine Prioritaets-Gebaeude mehr affordable: Ueberschuss in Rekruten
		# stecken. Ab recruit_idx wird vorwaerts der ERSTE kaufbare Slot
		# gesucht (Gebaeude gebaut, Pool > 0, Ressourcen im Wallet, Slot in
		# der Armee frei) - Index wandert hinter den Kauf. Frueher blieb die
		# Rotation auf einem blockierten Slot stehen; seit T6/T7 Edel-
		# Ressourcen kosten (die die KI mangels Markt-Tausch evtl. nie
		# bekommt), waere das ein dauerhafter Rekrutierungs-Stopp.
		var pfid: int = int(e.get("primary_faction", 1))
		var f_order: Array = UnitType.recruitable_ids_for_faction(pfid)
		if f_order.is_empty():
			continue
		if int(current_city["faction"]) != pfid:
			continue
		var ri: int = int(e["recruit_idx"])
		var bl_here: Array = current_city["buildings"]
		var cpools: Dictionary = current_city.get("pools", {}) as Dictionary
		for off in range(f_order.size()):
			var slot: int = (ri + off) % f_order.size()
			var next_uid: String = String(f_order[slot])
			if not bl_here.has(UnitType.building_for(next_uid)):
				continue
			if int(cpools.get(next_uid, 0)) <= 0:
				continue
			var next_cost: Dictionary = UnitType.cost_dict_of(next_uid)
			if not eh.wallet.can_afford(next_cost):
				continue
			if not eh.can_add_unit(next_uid):
				continue
			eh.wallet.pay(next_cost)
			eh.add_units(next_uid, 1)
			cpools[next_uid] = int(cpools[next_uid]) - 1
			current_city["pools"] = cpools
			e["recruit_idx"] = (slot + 1) % f_order.size()
			spent = true
			break


func _run_enemy_turn_for(idx: int) -> bool:
	# Einfache Gegner-KI: waehlt die naechstgelegene Nicht-eigene-Stadt
	# (neutral, Spieler oder andere KI) per Dijkstra, laeuft mit
	# Gradienten-Abstieg so weit wie MP reichen. Monster werden ignoriert
	# (monsters_block=false), damit die KI nicht eingekesselt wird.
	# Rueckgabe: true wenn der Zug abgeschlossen ist, false wenn ein
	# Pflicht-Kampf-Overlay geoeffnet wurde und die AI-Phase suspendiert
	# auf den Callback wartet.
	if idx < 0 or idx >= _enemies.size():
		return true
	var e: Dictionary = _enemies[idx]
	var eh: Hero = e["hero"] as Hero
	if eh == null:
		return true
	var oid: int = int(e["owner_id"])
	var fog_e: Array = e["fog"]
	var pls_pos: Vector2i = e["player_last_seen_pos"]
	var pls_turn: int = int(e["player_last_seen_turn"])
	eh.end_turn()
	# Vor der Zielauswahl Fog aktualisieren, damit die KI ihre eigene Sicht
	# kennt (sonst wuerde sie mit stale Fog aus der letzten Runde arbeiten).
	_recompute_fog_ai(idx)
	fog_e = e["fog"]
	pls_pos = e["player_last_seen_pos"]
	pls_turn = int(e["player_last_seen_turn"])
	var ecosts: Dictionary = _dijkstra(eh.position, false)
	# Ziel-Auswahl: naechste nicht-eigene Stadt, fremde/neutrale Goldmine
	# oder Schatzkiste - aber nur, wenn die KI das Feld schonmal gesehen
	# hat (Fog-Symmetrie). Spieler-Held-Ziel ist moeglich, solange die
	# letzte Sichtung noch nicht "verrottet" ist (FOG_ROT_TURNS).
	var target_kind: String = ""
	var target_idx: int = -1
	var target_cost: int = -1
	var target_pos: Vector2i = eh.position
	# Nur Ziele anpeilen, die die KI auch nehmen kann. Sonst sitzt sie
	# endlos auf einer zu starken Wache und das Heimweg-Fallback greift
	# nie, weil target_cost immer 0 bleibt. Armee ist der einzige Wert,
	# der Kaempfe entscheidet (KI hat keinen Kampfkraft-Bonus).
	var army: int = eh.total_count()
	for i in range(_cities.size()):
		if int(_cities[i]["owner"]) == oid:
			continue
		var cp: Vector2i = _cities[i]["pos"]
		if _fog_get(fog_e, cp) == FOG_HIDDEN:
			continue
		if not ecosts.has(cp):
			continue
		var garrison_c: int = Garrison.total(_cities[i].get("garrison_army", {}))
		# Safety-Margin: KI greift nicht mit knapper Armee an, sondern
		# braucht AI_RAID_SAFETY_PCT Prozent mehr. Verhindert 1:1-Pyrrhus-
		# Eroberungen, bei denen die KI nach Sieg handlungsunfaehig ist.
		if garrison_c > 0 and army * 100 < garrison_c * (100 + AI_RAID_SAFETY_PCT):
			continue
		var c: int = int(ecosts[cp])
		if target_cost < 0 or c < target_cost:
			target_kind = "city"
			target_idx = i
			target_cost = c
			target_pos = cp
	for i in range(_objects.size()):
		var obj: Dictionary = _objects[i]
		var okind: int = int(obj["kind"])
		if okind == OBJECT_MINE and int(obj.get("owner", OWNER_NEUTRAL)) == oid:
			continue
		var op: Vector2i = obj["pos"]
		if _fog_get(fog_e, op) == FOG_HIDDEN:
			continue
		if not ecosts.has(op):
			continue
		var guard_o: int = int(obj.get("guard", 0))
		if guard_o > 0 and army * 100 < guard_o * (100 + AI_RAID_SAFETY_PCT):
			continue
		var c2: int = int(ecosts[op])
		if target_cost < 0 or c2 < target_cost:
			target_kind = "mine" if okind == OBJECT_MINE else "treasure"
			target_idx = i
			target_cost = c2
			target_pos = op
	# Helden-Jagd: sowohl der Spieler als auch rivalisierende KIs sind
	# Kandidaten, solange die letzte Sichtung nicht verrottet ist. Pro
	# Kandidat AI_HUNT_SAFETY_PCT Prozent Armee-Vorsprung verlangen,
	# sonst verzichtet die KI auf den Angriff (Suizid-Vermeidung). Ohne
	# Filter joggt die KI stur auf jeden gesehenen Helden zu, egal wie
	# stark der ist - und verliert alles in einem Kampf.
	var hunt_candidates: Array = []
	if _hero != null and pls_pos.x >= 0 and (_turn_number - pls_turn) < FOG_ROT_TURNS:
		hunt_candidates.append({"pos": pls_pos, "strength": _hero.total_count()})
	var rs_hunt: Dictionary = e.get("rivals_seen", {})
	for rid_key in rs_hunt.keys():
		var entry: Dictionary = rs_hunt[rid_key]
		var rturn: int = int(entry["turn"])
		if (_turn_number - rturn) >= FOG_ROT_TURNS:
			continue
		# Rival muss noch leben, um ueberhaupt angreifbar zu sein.
		var rh_live: Hero = null
		for oi in range(_enemies.size()):
			if int(_enemies[oi]["owner_id"]) == int(rid_key):
				rh_live = _enemies[oi]["hero"] as Hero
				break
		if rh_live == null:
			continue
		hunt_candidates.append({"pos": Vector2i(entry["pos"]), "strength": rh_live.total_count()})
	for hc_entry in hunt_candidates:
		var hp: Vector2i = hc_entry["pos"]
		var hstr: int = int(hc_entry["strength"])
		if not ecosts.has(hp):
			continue
		if army * 100 < hstr * (100 + AI_HUNT_SAFETY_PCT):
			continue
		var hc: int = int(ecosts[hp])
		if target_cost < 0 or hc <= target_cost:
			target_kind = "hero"
			target_idx = -1
			target_cost = hc
			target_pos = hp
	# Heimweg: wenn die KI genug Gold fuer eine billige Ausgabe hat, aber
	# nicht auf einer eigenen Stadt steht, ist die naechste eigene Stadt ein
	# valides Ziel. Grund: _enemy_economy_for gibt nur aus, wenn der Held
	# auf einer eigenen Stadt steht (gleiche Regel wie beim Spieler). Ohne
	# diesen Anker wuerde sich Gold endlos stapeln. Hero-Jagd hat Vorrang,
	# sonst gewinnt das naeher gelegene Ziel (home vs. Loot).
	var cheapest_spend: int = 300 # Spaeher ist das billigste Gebaeude
	var pfid_home: int = int(e.get("primary_faction", 1))
	for uid in UnitType.ids_for_faction(pfid_home):
		var uc: int = UnitType.cost_of(uid)
		if uc < cheapest_spend:
			cheapest_spend = uc
	if eh.gold >= cheapest_spend and target_kind != "hero":
		var on_own_city: bool = false
		for i in range(_cities.size()):
			if int(_cities[i]["owner"]) == oid and Vector2i(_cities[i]["pos"]) == eh.position:
				on_own_city = true
				break
		if not on_own_city:
			var best_home_i: int = -1
			var best_home_cost: int = -1
			var best_home_pos: Vector2i = eh.position
			for i in range(_cities.size()):
				if int(_cities[i]["owner"]) != oid:
					continue
				var cp2: Vector2i = _cities[i]["pos"]
				if not ecosts.has(cp2):
					continue
				var cc: int = int(ecosts[cp2])
				if best_home_cost < 0 or cc < best_home_cost:
					best_home_i = i
					best_home_cost = cc
					best_home_pos = cp2
			if best_home_i >= 0 and (target_cost < 0 or best_home_cost < target_cost):
				target_kind = "home"
				target_idx = best_home_i
				target_cost = best_home_cost
				target_pos = best_home_pos
	# Defensives Override: jede eigene Stadt in Manhattan-Reichweite
	# AI_THREAT_RADIUS eines aktuell sichtbaren feindlichen Helden
	# (Spieler oder rivalisierende KI) zaehlt als bedroht. Reagiert die
	# KI, laeuft ihr Held zur naechstgelegenen bedrohten Stadt, statt
	# weiter zu looten. Hat Vorrang vor Raid, Hunt und Home - defensive
	# Entscheidungen sind im Free-for-All die teuersten Fehler (Stadt
	# verloren = oft Spielentscheidung).
	var defend_i: int = -1
	var defend_cost: int = -1
	var defend_pos: Vector2i = eh.position
	for i in range(_cities.size()):
		if int(_cities[i]["owner"]) != oid:
			continue
		var cp_d: Vector2i = _cities[i]["pos"]
		if not ecosts.has(cp_d):
			continue
		var is_threatened: bool = false
		if _hero != null and _fog_get(fog_e, _hero.position) == FOG_VISIBLE:
			var dph: int = abs(_hero.position.x - cp_d.x) + abs(_hero.position.y - cp_d.y)
			if dph <= AI_THREAT_RADIUS:
				is_threatened = true
		if not is_threatened:
			for oi in range(_enemies.size()):
				if oi == idx:
					continue
				var ohd: Hero = _enemies[oi]["hero"] as Hero
				if ohd == null:
					continue
				if _fog_get(fog_e, ohd.position) != FOG_VISIBLE:
					continue
				var dpo: int = abs(ohd.position.x - cp_d.x) + abs(ohd.position.y - cp_d.y)
				if dpo <= AI_THREAT_RADIUS:
					is_threatened = true
					break
		if not is_threatened:
			continue
		var cd: int = int(ecosts[cp_d])
		if defend_cost < 0 or cd < defend_cost:
			defend_i = i
			defend_cost = cd
			defend_pos = cp_d
	if defend_i >= 0:
		target_kind = "defend"
		target_idx = defend_i
		target_cost = defend_cost
		target_pos = defend_pos
	# Fallback-Exploration: nichts bekannt -> naechstgelegenes Hidden-Feld
	# ansteuern, damit die KI aktiv erkundet und nicht passiv in der
	# Startzone bleibt.
	if target_cost < 0:
		var best_ex: int = -1
		var best_ep: Vector2i = eh.position
		for p in ecosts.keys():
			var pv: Vector2i = p
			if _fog_get(fog_e, pv) != FOG_HIDDEN:
				continue
			var pc: int = int(ecosts[pv])
			if best_ex < 0 or pc < best_ex:
				best_ex = pc
				best_ep = pv
		if best_ex < 0:
			return true
		target_kind = "explore"
		target_idx = -1
		target_cost = best_ex
		target_pos = best_ep
	if target_cost < 0:
		return true
	# Zweite Dijkstra vom Ziel aus, um Schritt-fuer-Schritt den Gradienten
	# absteigen zu koennen. Einfacher als Pfad-Rekonstruktion.
	var tcosts: Dictionary = _dijkstra(target_pos, false)
	if not tcosts.has(eh.position):
		return true
	var tiles: Array = _map["tiles"]
	var guard: int = 0
	var cap: int = MAP_WIDTH + MAP_HEIGHT + 10
	while eh.mp > 0 and eh.position != target_pos and guard < cap:
		guard += 1
		var cur_val: int = int(tcosts[eh.position])
		var best_next: Vector2i = eh.position
		var best_val: int = cur_val
		var best_step: int = -1
		var d_e := Vector2i(1, 0)
		var d_w := Vector2i(-1, 0)
		var d_s := Vector2i(0, 1)
		var d_n := Vector2i(0, -1)
		for di in range(4):
			var d: Vector2i = d_e
			if di == 1: d = d_w
			elif di == 2: d = d_s
			elif di == 3: d = d_n
			var np: Vector2i = eh.position + d
			if not tcosts.has(np):
				continue
			var v: int = int(tcosts[np])
			if v >= cur_val:
				continue
			if np.x < 0 or np.x >= MAP_WIDTH or np.y < 0 or np.y >= MAP_HEIGHT:
				continue
			var t: int = int(tiles[np.y * MAP_WIDTH + np.x])
			var step_cost: int = 1
			if t == 1:
				step_cost = 2
			if step_cost > eh.mp:
				continue
			if v < best_val:
				best_val = v
				best_next = np
				best_step = step_cost
		if best_step < 0:
			break
		# Spieler-Held auf dem naechsten Schritt: Pflicht-Kampf via
		# Taktik-Overlay. Der Aufruf oeffnet ein modales Overlay, das der
		# Spieler selbst ausspielt. Wir suspendieren die KI-Phase bis
		# zum Callback (return false -> _advance_ai_phase legt eine
		# Pause ein und wird von _on_ai_attack_result fortgesetzt).
		if _hero != null and best_next == _hero.position:
			var battle_terrain: int = int(tiles[best_next.y * MAP_WIDTH + best_next.x])
			var ai_total: int = eh.total_count()
			var next_idx: int = idx + 1
			# allow_flee=true seit It. 42 - DER Kampf, der vorher Pflicht war.
			_open_battle("Gegner-Held", ai_total, true, battle_terrain, func(r: Dictionary) -> void:
				_on_ai_attack_result(r, idx, next_idx)
			)
			return false
		# Gegner-Held einer anderen KI auf dem naechsten Schritt: Auto-
		# Resolve-Kampf (kein Overlay, Spieler ist nicht beteiligt).
		# Sieger = hoehere Gesamtarmee; Sieger nimmt proportionale
		# Verluste in Hoehe der Verliererarmee hin, Verlierer ist weg.
		# Gleichstand: Angreifer (diese KI) verliert (deterministischer
		# Tiebreaker, damit der Verteidiger einen Vorteil hat).
		var other_idx: int = -1
		for oi in range(_enemies.size()):
			if oi == idx:
				continue
			var oh: Hero = _enemies[oi]["hero"] as Hero
			if oh != null and oh.position == best_next:
				other_idx = oi
				break
		if other_idx >= 0:
			var other_hero: Hero = _enemies[other_idx]["hero"] as Hero
			var att_total: int = eh.total_count()
			var def_total: int = other_hero.total_count()
			if att_total > def_total:
				eh.apply_proportional_losses(def_total)
				_enemies[other_idx]["hero"] = null
				eh.position = best_next
				eh.mp -= best_step
			else:
				other_hero.apply_proportional_losses(att_total)
				e["hero"] = null
				return true
			continue
		eh.position = best_next
		eh.mp -= best_step
	# Ziel erreicht? Einnehmen/Einsammeln je nach Ziel-Art. KI hat keinen
	# Kampfkraft-Bonus, nur ihre Armee zaehlt. Wenn die Wache zu stark ist,
	# bleibt die KI einfach stehen und versucht es spaeter nochmal.
	if eh.position == target_pos:
		if target_kind == "city":
			var tc: Dictionary = _cities[target_idx]
			var gar: Dictionary = tc.get("garrison_army", {}) as Dictionary
			# Eigene Stadt MIT Verteidigern: der SPIELER spielt den
			# Verteidigungskampf selbst aus - hinter seiner Mauer, mit
			# Pfeilturm und Verteidiger-Bonus. Gleiches Muster wie der
			# Pflicht-Kampf gegen den Spieler-Helden: Overlay auf,
			# return false suspendiert die KI-Phase, der Callback setzt
			# sie fort.
			if int(tc.get("owner", OWNER_NEUTRAL)) == OWNER_HERO \
					and not Garrison.is_empty(gar):
				var terr_def: int = int(tiles[target_pos.y * MAP_WIDTH + target_pos.x])
				var sctx_def: Dictionary = _siege_ctx_for(tc)
				# Verteidiger = Garnison, plus Held wenn er in der Stadt steht.
				var def_army: Dictionary = gar.duplicate()
				# JEDER eigene Held in der Stadt verteidigt mit (M13b) -
				# vorher wurde nur der AKTIVE geprueft, ein zweiter Held in
				# derselben Stadt haette tatenlos zugesehen und waere bei
				# Verlust der Stadt trotzdem verschont geblieben.
				var def_hero_idx: int = _hero_index_at(target_pos)
				var hero_in_city: bool = def_hero_idx >= 0
				if hero_in_city:
					var dh: Hero = _heroes[def_hero_idx] as Hero
					for hk in dh.army.keys():
						Garrison.add(def_army, String(hk), int(dh.army[hk]))
				sctx_def["player_army"] = def_army
				# Fuer die Totenerweckung: nur wenn der Held selbst
				# mitkaempft, bekommt er die Skelette.
				sctx_def["hero_present"] = hero_in_city
				# Der Belagerer kaempft mit seinen ECHTEN Einheiten, nicht
				# mit einer aus der Kopfzahl synthetisierten Truppe.
				sctx_def["enemy_army"] = eh.army.duplicate()
				var c_idx: int = target_idx
				var ai_idx: int = idx
				var nxt: int = idx + 1
				_open_battle("Belagerer", eh.total_count(), false, terr_def,
					func(r: Dictionary) -> void:
						_on_city_defense_result(r, c_idx, ai_idx, nxt, def_hero_idx)
				, sctx_def)
				return false
			# Fremde/neutrale Stadt oder leere eigene Stadt: wie bisher ohne
			# Overlay (der Spieler ist nicht beteiligt).
			var garrison: int = Garrison.total(gar)
			if garrison > 0:
				if eh.total_count() < garrison:
					return true
				eh.apply_proportional_losses(garrison)
			tc["owner"] = oid
			tc["garrison_army"] = {}
		elif target_kind == "mine":
			var obj: Dictionary = _objects[target_idx]
			var g: int = int(obj.get("guard", 0))
			if g > 0:
				if eh.total_count() < g:
					return true
				eh.apply_proportional_losses(g)
				obj["guard"] = 0
			obj["owner"] = oid
		elif target_kind == "treasure":
			# Deckt Schatzkisten UND Ressourcen-Haufen ab (target_kind ist
			# fuer alles ausser Minen "treasure").
			var obj2: Dictionary = _objects[target_idx]
			var g2: int = int(obj2.get("guard", 0))
			if g2 > 0:
				if eh.total_count() < g2:
					return true
				eh.apply_proportional_losses(g2)
			var tres: String = String(obj2.get("resource", "gold"))
			if int(obj2["kind"]) == OBJECT_PILE and tres != "gold":
				eh.wallet.add(tres, int(obj2["gold"]))
			else:
				eh.gold += int(obj2["gold"])
			_objects.remove_at(target_idx)
	return true


func _check_defeat() -> void:
	# Niederlage bei Stadtverlust - aber MIT SCHONFRIST (It. 38).
	#
	# Vorher war der Verlust der letzten Stadt sofortiges Spielende, auch
	# mit lebendem Helden und voller Armee. Der Durchspiel-Test hat genau
	# das produziert: die KI lief in die leere Startstadt (der Spieler hatte
	# alle Truppen beim Helden), und das Spiel war in Zug 13 vorbei, obwohl
	# der Held unversehrt daneben stand und eine Stadt zurueckerobern
	# konnte.
	#
	# HoMM3 macht es anders und das ist die Vorlage: ohne Stadt laeuft eine
	# Frist von sieben Tagen. Erobert man in der Zeit eine Stadt, geht es
	# weiter. Ist der Held gefallen, gilt weiterhin sofortige Niederlage -
	# das entscheidet _on_battle_defeat.
	if _cities.size() == 0:
		return
	var player_cities: int = 0
	var ai_cities: int = 0
	for c in _cities:
		var ow: int = int(c["owner"])
		if ow == OWNER_HERO:
			player_cities += 1
		elif ow >= OWNER_AI_MIN:
			ai_cities += 1
	if player_cities > 0 or ai_cities <= 0:
		# Stadt (wieder) da: Frist zurueck auf Anfang.
		_no_city_since = -1
		return
	# Kein Held mehr UND keine Stadt: das ist endgueltig. Ein Held ohne
	# Truppen zaehlt weiter - er kann eine leere Stadt einnehmen, und genau
	# dafuer ist die Schonfrist da (M13b; vorher galt `total_count() <= 0`
	# als "kein Held", was einen Helden ohne Armee sofort verloren gab).
	if _heroes.is_empty():
		_lose_now()
		return
	if _no_city_since < 0:
		_no_city_since = _turn_number
		_set_combat("Letzte Stadt verloren! %d Tage, um eine zu erobern."
			% LOSS_GRACE_DAYS)
		return
	if _turn_number - _no_city_since >= LOSS_GRACE_DAYS:
		_lose_now()


func _lose_now() -> void:
	if _game_lost:
		return
	_game_lost = true
	SaveLib.delete_autosave()
	_show_defeat_panel()


# Restliche Schonfrist in Tagen, oder -1 wenn keine laeuft. Fuer die
# Kopfzeile - eine laufende Frist MUSS sichtbar sein.
func _grace_left() -> int:
	if _no_city_since < 0:
		return -1
	return maxi(0, LOSS_GRACE_DAYS - (_turn_number - _no_city_since))


func _show_defeat_panel() -> void:
	Sound.play("defeat")
	if _victory_panel == null:
		return
	if _victory_title != null:
		_victory_title.text = "NIEDERLAGE"
		_victory_title.add_theme_color_override("font_color", Color(1.0, 0.4, 0.35))
	var vb := _victory_panel.get_node_or_null("VB") as VBoxContainer
	if vb != null:
		var stats := vb.get_node_or_null("Stats") as Label
		if stats != null:
			stats.text = _hero_stats_text()
	_victory_panel.visible = true


func _on_end_turn() -> void:
	# Gebaeude-Effekte pro eigener Stadt:
	#   Spaeher  -> max_mp hoch
	#   Markt    -> Gold-Einkommen hoch
	#   Kaserne/Schmiede/Reiterei -> taeglich Pool auffuellen (Bresenham)
	#   Wachturm -> +1 Kampfkraft (via _combat_bonus() dauerhaft)
	#   Kapelle  -> +10 XP pro Tag, kann Level-Up ausloesen
	# Level-Up-Bonus: pro Level (ueber 1) zusaetzlich +1 max_mp.
	var owned := 0
	var markt_count := 0
	var kapelle_count := 0
	for city in _cities:
		if int(city["owner"]) == OWNER_HERO:
			owned += 1
			var bl: Array = city["buildings"]
			if bl.has("markt"):
				markt_count += 1
			if bl.has("kapelle"):
				kapelle_count += 1
	_recalc_max_mp()
	_regen_mana()
	# Bewegungspunkte aller Helden zuruecksetzen (M13a).
	for h in _heroes:
		(h as Hero).end_turn()
	# Goldminen im Besitz: +MINE_GOLD_PER_TURN pro Mine (bereits als
	# obj["gold"] hinterlegt, damit spaeter Minen unterschiedlichen
	# Ertrag haben koennen, ohne dass sich die Rechnung aendert).
	var mine_income: int = 0
	for obj in _objects:
		if int(obj["kind"]) == OBJECT_MINE and int(obj.get("owner", OWNER_NEUTRAL)) == OWNER_HERO:
			var mres: String = String(obj.get("resource", "gold"))
			if mres == "gold":
				mine_income += int(obj["gold"])
			else:
				# Nicht-Gold-Minen zahlen ihre Ressource direkt ins Wallet.
				_purse.add(mres, int(obj["gold"]))
	var income: int = owned * CITY_INCOME + markt_count * INCOME_MARKT + mine_income \
		+ Skills.estates_gold(_hero.skills)
	_purse.add("gold", income)
	var xp_gain: int = kapelle_count * KAPELLE_XP_PER_TURN
	if xp_gain > 0:
		_hero.xp += xp_gain
		if _check_level_up():
			_set_combat("Level-Up durch Kapelle! -> LEVEL %d" % _hero.level)
	# Oekonomie-Snapshot fuer die Status-Zeile, falls die KI-Phase durch
	# einen Pflicht-Kampf suspendiert und erst im Callback finalisiert wird.
	_turn_income = income
	_turn_xp_gain = xp_gain
	_turn_owned = owned
	# Gegner-Zuege: pro KI erst Oekonomie (Einkommen, Gebaeude, Rekruten),
	# dann Bewegung. Reihenfolge entspricht dem Spieler-Flow. Die KIs
	# spielen in Reihenfolge ihrer Indizes, damit die Runden-Logik
	# deterministisch ist. Greift eine KI den Spieler an, suspendiert
	# _advance_ai_phase und wird vom Overlay-Callback fortgesetzt.
	_advance_ai_phase(0)


func _advance_ai_phase(start_idx: int) -> void:
	for ai_idx in range(start_idx, _enemies.size()):
		_enemy_economy_for(ai_idx)
		var done: bool = _run_enemy_turn_for(ai_idx)
		if not done:
			return
		if _game_lost:
			break
	_finalize_turn()


func _finalize_turn() -> void:
	var week_before: int = GameCalendar.week_total(_turn_number)
	_turn_number += 1
	# Wochenwechsel (M12): das Ereignis der NEUEN Woche gilt schon fuer den
	# Tagestick unten - _pool_cap_for zieht es aus _week_event(). Einmalige
	# Wirkungen (Ernte) muessen hier vorher laufen.
	var new_week: bool = GameCalendar.week_total(_turn_number) != week_before
	if new_week:
		_apply_week_event_start()
	# Tagestick: Pools aller Staedte bekommen ihre Tagesration (Bresenham
	# ueber 7 Tage). Pools stapeln sich, nichts verfaellt. _day_of_week()
	# bezieht sich auf den gerade begonnenen neuen Tag.
	_daily_pool_tick(_day_of_week())
	_recompute_fog_player()
	for i in range(_enemies.size()):
		_recompute_fog_ai(i)
	_recompute_costs()
	_request_redraw()
	_update_labels()
	# _turn_number wurde gerade erhoeht, entspricht also der Nummer des
	# gerade beendeten Tages (Tag 1 = erster Zug). _day_num() zeigt auf
	# den neuen, aktuellen Tag.
	if new_week:
		# Der Wochenwechsel ist die wichtigere Nachricht als die
		# Tagesbilanz - er bestimmt, was diese Woche wachsen wird.
		Sound.play("week_event")
		var ev: Dictionary = _week_event()
		_set_status("Neue Woche: %s" % String(ev.get("title", "")))
		_set_combat(String(ev.get("detail", "")))
	else:
		Sound.play("day_end")
		_set_status("Tag %d beendet: +%d G, +%d XP (%d Staedte)"
			% [_turn_number, _turn_income, _turn_xp_gain, _turn_owned])
	_check_defeat()
	# Nach der kompletten KI-Phase pruefen, ob die KIs sich gegenseitig
	# ausradiert haben und der Spieler dadurch schon gewonnen hat. Ohne
	# diesen Aufruf wird der Sieg nur getriggert, wenn der Spieler selbst
	# eine Stadt einnimmt oder einen KI-Held besiegt.
	_check_victory()
	# Autosave am Tagesende - der wichtigste Persistenz-Punkt. Nach Sieg/
	# Niederlage nicht mehr speichern (das Autosave wurde dort geloescht).
	if not _game_won and not _game_lost:
		SaveLib.write_save(_capture_state())


func _on_ai_attack_result(result: Dictionary, ai_idx: int, next_idx: int) -> void:
	# Callback nach Pflicht-Kampf KI-greift-Spieler-an.
	# outcome == "defeat": Spieler gefallen, Spiel verloren.
	# outcome == "victory": Spieler gewinnt, die angreifende KI ist weg.
	# outcome == "flee"/"surrender": seit It. 42 moeglich - genau dieser
	# Kampf war vorher nicht ausschlagbar und hat in 3 von 6 Seeds des
	# Durchspiel-Tests das Spiel in Woche 1 beendet.
	var outcome: String = String(result.get("outcome", "flee"))
	if outcome == "flee" or outcome == "surrender":
		# Rueckzug schon erledigt. Die angreifende KI lebt weiter und
		# behaelt ihre Armee - aber die KI-PHASE MUSS WEITERLAUFEN, sonst
		# friert sie ein (It. 38).
		_advance_ai_phase(next_idx)
		return
	if outcome == "defeat":
		_apply_casualties(result)
		_update_labels()
		_on_battle_defeat()
		return
	# Sieg: Spieler nimmt Verluste hin, angreifende KI ist vernichtet.
	_apply_casualties(result)
	if ai_idx >= 0 and ai_idx < _enemies.size():
		_enemies[ai_idx]["hero"] = null
	_set_combat("Gegner-Held hat dich angegriffen und verloren")
	_update_labels()
	# Restliche KIs noch abarbeiten, dann normale Rundenfinalisierung.
	_advance_ai_phase(next_idx)


# Callback nach dem Verteidigungskampf um eine eigene Stadt.
# Der Spieler hat Garnison (+ Held, falls anwesend) gesteuert; die
# Ueberlebenden kommen aus result.player_remaining zurueck.
# hero_joined = der Held stand in der Stadt und hat mitgekaempft.
# `def_hero_idx` ist der Index des verteidigenden Helden in `_heroes`, oder
# -1 wenn nur die Garnison gekaempft hat (M13b). Vorher war das ein Bool und
# der Code griff auf `_hero` zu - mit mehreren Helden waere das der falsche.
func _on_city_defense_result(result: Dictionary, city_idx: int, ai_idx: int,
		next_idx: int, def_hero_idx: int) -> void:
	# Aus der eigenen Mauer flieht man nicht (HoMM3-Regel, allow_flee=false
	# an der Aufrufstelle). Der Riegel steht hier trotzdem: ein
	# durchgereichtes "flee" wuerde unten in den else-Zweig laufen und die
	# Stadt verlieren lassen.
	var oc_def: String = String(result.get("outcome", "defeat"))
	if oc_def == "flee" or oc_def == "surrender":
		_set_combat("Aus der eigenen Stadt gibt es keinen Rueckzug")
		_advance_ai_phase(next_idx)
		return
	var hero_joined: bool = def_hero_idx >= 0 and def_hero_idx < _heroes.size()
	var def_hero: Hero = _heroes[def_hero_idx] as Hero if hero_joined else null
	var outcome: String = String(result.get("outcome", "defeat"))
	var remaining: Dictionary = SaveCodec.int_dict(result.get("player_remaining", {}))
	if city_idx < 0 or city_idx >= _cities.size():
		_advance_ai_phase(next_idx)
		return
	var city: Dictionary = _cities[city_idx]
	if outcome == "victory":
		# Stadt gehalten. Reste zurueckverteilen: der Held bekommt
		# zuerst, was er beigesteuert hatte, der Rest bleibt Garnison.
		var left: Dictionary = remaining.duplicate()
		if def_hero != null:
			var new_hero_army: Dictionary = {}
			for k in def_hero.army.keys():
				var uid: String = String(k)
				var take: int = min(int(def_hero.army[uid]), int(left.get(uid, 0)))
				if take > 0:
					new_hero_army[uid] = take
					Garrison.remove(left, uid, take)
			def_hero.army = new_hero_army
		city["garrison_army"] = left
		if ai_idx >= 0 and ai_idx < _enemies.size():
			# Der Belagerer verliert genau, was im Kampf gefallen ist -
			# ueberlebt etwas, zieht er geschwaecht ab.
			var att_left: Dictionary = SaveCodec.int_dict(result.get("enemy_remaining", {}))
			var ah: Hero = _enemies[ai_idx]["hero"] as Hero
			if ah == null or Garrison.is_empty(att_left):
				_enemies[ai_idx]["hero"] = null
			else:
				ah.army = att_left
		_set_combat("Stadt verteidigt! Garnison: %s" % Garrison.summary(left))
	else:
		# Stadt gefallen: Angreifer uebernimmt, Verteidiger sind weg.
		# Stand der Held mit in der Stadt, ist er ebenfalls gefallen -
		# dann ist das Spiel verloren (gleiche Regel wie im Feldkampf).
		city["garrison_army"] = {}
		if ai_idx >= 0 and ai_idx < _enemies.size():
			var att: Hero = _enemies[ai_idx]["hero"] as Hero
			if att != null:
				city["owner"] = int(_enemies[ai_idx]["owner_id"])
				# Der Angreifer behaelt genau seine Ueberlebenden.
				var left_att: Dictionary = SaveCodec.int_dict(
					result.get("enemy_remaining", {}))
				if Garrison.is_empty(left_att):
					_enemies[ai_idx]["hero"] = null
				else:
					att.army = left_att
		if hero_joined:
			_update_labels()
			# GENAU der Held, der in der Stadt stand, ist gefallen - nicht
			# zwangslaeufig der aktive (M13b).
			_on_battle_defeat(def_hero_idx)
			return
		_set_combat("Stadt verloren - Garnison gefallen")
	_update_labels()
	_request_redraw()
	_advance_ai_phase(next_idx)


func _on_reroll() -> void:
	_start(_seed + 1, _player_faction)


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/Main.tscn")


# ====================== Save/Load (M1) ======================
# Snapshot-Pattern: die Karte selbst wird NICHT gespeichert - sie ist
# deterministische Funktion von _seed (MapGen). Save = Seed + Deltas.
# _restore_state nutzt _start(seed) als "Konstruktor" (baut Karte, UI,
# Fog-Arrays) und ueberschreibt danach die Zustands-Variablen.

func _capture_state() -> Dictionary:
	var cities_out: Array = []
	for c in _cities:
		var cd: Dictionary = c.duplicate(true)
		cd["pos"] = SaveCodec.v2i(c["pos"])
		cities_out.append(cd)
	var objects_out: Array = []
	for o in _objects:
		var od: Dictionary = o.duplicate(true)
		od["pos"] = SaveCodec.v2i(o["pos"])
		objects_out.append(od)
	var monsters_out: Array = []
	for m in _monsters:
		var md: Dictionary = m.duplicate(true)
		md["pos"] = SaveCodec.v2i(m["pos"])
		monsters_out.append(md)
	var enemies_out: Array = []
	for e in _enemies:
		var eh: Hero = e["hero"] as Hero
		var rivals_out: Dictionary = {}
		for rid in (e.get("rivals_seen", {}) as Dictionary).keys():
			var rv: Dictionary = e["rivals_seen"][rid]
			rivals_out[str(rid)] = {
				"pos": SaveCodec.v2i(rv["pos"]),
				"turn": int(rv["turn"]),
			}
		enemies_out.append({
			"hero": eh.to_dict() if eh != null else null,
			"owner_id": int(e["owner_id"]),
			"primary_faction": int(e.get("primary_faction", 1)),
			"recruit_idx": int(e.get("recruit_idx", 0)),
			"fog": (e["fog"] as Array).duplicate(),
			"player_last_seen_pos": SaveCodec.v2i(e["player_last_seen_pos"]),
			"player_last_seen_turn": int(e["player_last_seen_turn"]),
			"rivals_seen": rivals_out,
		})
	var seen_out: Array = []
	for s in _ai_seen_by_player:
		seen_out.append({"pos": SaveCodec.v2i(s["pos"]), "turn": int(s["turn"])})
	# Helden als LISTE plus aktiver Index und Spieler-Beutel (v5, M13a).
	# Der alte Schluessel "hero" wird nicht mehr geschrieben; alte
	# Spielstaende setzt SaveManager._migrate_4_to_5 um.
	var heroes_out: Array = []
	for h in _heroes:
		heroes_out.append((h as Hero).to_dict())
	return {
		"seed": _seed,
		"turn_number": _turn_number,
		"no_city_since": _no_city_since,
		"player_faction": _player_faction,
		"heroes": heroes_out,
		"active_hero": _active_hero,
		"purse": _purse.to_dict(),
		"cities": cities_out,
		"objects": objects_out,
		"monsters": monsters_out,
		"enemies": enemies_out,
		"ai_seen_by_player": seen_out,
		"fog_player": _fog_player.duplicate(),
		"rng_state": _rng.get_state_string(),
	}


func _restore_state(d: Dictionary) -> bool:
	# "heroes" ist die Form ab v5 (M13a); SaveManager.migrate hat einen
	# aelteren Spielstand vorher umgesetzt, hier kommt also immer die neue
	# Form an.
	if d.is_empty() or not d.has("seed") or not d.has("heroes"):
		return false
	# 1) Welt deterministisch neu bauen - danach stimmen Karte/UI/Arrays.
	_start(int(d["seed"]))
	# 2) Zustand ueberschreiben.
	_turn_number = int(d.get("turn_number", 0))
	_no_city_since = int(d.get("no_city_since", -1))
	_player_faction = int(d.get("player_faction", 1))
	_heroes.clear()
	for hd in (d["heroes"] as Array):
		_heroes.append(Hero.from_dict(hd as Dictionary))
	if _heroes.is_empty():
		return false
	_active_hero = clampi(int(d.get("active_hero", 0)), 0, _heroes.size() - 1)
	_purse = Wallet.from_dict(d.get("purse", {}))
	_cities.clear()
	for cd in d.get("cities", []):
		var c: Dictionary = (cd as Dictionary).duplicate(true)
		c["pos"] = SaveCodec.to_v2i(c["pos"])
		# JSON-Floats -> ints fuer bekannte Zahlfelder.
		c["faction"] = int(c.get("faction", 0))
		c["owner"] = int(c.get("owner", -1))
		c["garrison_army"] = SaveCodec.int_dict(c.get("garrison_army", {}))
		c.erase("garrison")   # v2-Rest, migrate() hat ihn schon umgesetzt
		c["pools"] = SaveCodec.int_dict(c.get("pools", {}))
		_cities.append(c)
	_objects.clear()
	for od in d.get("objects", []):
		var o: Dictionary = (od as Dictionary).duplicate(true)
		o["pos"] = SaveCodec.to_v2i(o["pos"])
		o["kind"] = int(o.get("kind", 0))
		o["owner"] = int(o.get("owner", -1))
		o["guard"] = int(o.get("guard", 0))
		o["gold"] = int(o.get("gold", 0))
		_objects.append(o)
	_monsters.clear()
	for md in d.get("monsters", []):
		var m: Dictionary = (md as Dictionary).duplicate(true)
		m["pos"] = SaveCodec.to_v2i(m["pos"])
		m["strength"] = int(m.get("strength", 1))
		_monsters.append(m)
	_enemies.clear()
	for ed in d.get("enemies", []):
		var e: Dictionary = ed as Dictionary
		var rivals_in: Dictionary = {}
		for rk in (e.get("rivals_seen", {}) as Dictionary).keys():
			var rv: Dictionary = e["rivals_seen"][rk]
			rivals_in[int(rk)] = {
				"pos": SaveCodec.to_v2i(rv["pos"]),
				"turn": int(rv["turn"]),
			}
		_enemies.append({
			"hero": Hero.from_dict(e["hero"]) if e.get("hero") != null else null,
			"owner_id": int(e["owner_id"]),
			"primary_faction": int(e.get("primary_faction", 1)),
			"recruit_idx": int(e.get("recruit_idx", 0)),
			"fog": SaveCodec.int_array(e.get("fog", [])),
			"player_last_seen_pos": SaveCodec.to_v2i(e.get("player_last_seen_pos")),
			"player_last_seen_turn": int(e.get("player_last_seen_turn", -1)),
			"rivals_seen": rivals_in,
		})
	_ai_seen_by_player.clear()
	for sd in d.get("ai_seen_by_player", []):
		_ai_seen_by_player.append({
			"pos": SaveCodec.to_v2i((sd as Dictionary).get("pos")),
			"turn": int((sd as Dictionary).get("turn", -1)),
		})
	_fog_player = SaveCodec.int_array(d.get("fog_player", []))
	_rng.set_state_string(String(d.get("rng_state", "")))
	_game_won = false
	_game_lost = false
	# 3) Abgeleitetes neu berechnen + zeichnen.
	_recompute_fog_player()
	for i in range(_enemies.size()):
		_recompute_fog_ai(i)
	_recompute_costs()
	_update_labels()
	_request_redraw()
	_set_status("Spielstand geladen - Tag %d" % _day_num())
	return true


# Android/iOS: App wird pausiert oder geschlossen -> sofort sichern.
# NOTIFICATION_APPLICATION_PAUSED kommt beim Backgrounding (Home-Button),
# WM_CLOSE_REQUEST beim regulaeren Beenden.
func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_PAUSED or what == NOTIFICATION_WM_CLOSE_REQUEST:
		if _hero != null and not _game_won and not _game_lost:
			SaveLib.write_save(_capture_state())
