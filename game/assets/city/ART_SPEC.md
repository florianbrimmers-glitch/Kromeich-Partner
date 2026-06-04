# Stadt-Screen — Art-Spezifikation (KI-Sprites)

Ziel: konsistente, isometrische Gebäude-Sprites für den Stadt-Screen. Erst die
**Menschen**-Fraktion komplett, dann dieselbe Pipeline für die anderen drei.
Generierung extern (Midjourney / SDXL / DALL·E o.ä.) — die Engine kann keine
Bilder erzeugen.

## Wichtiger rechtlicher Rahmen
Keine Heroes-/Ubisoft-Assets, -Namen oder -Stile kopieren. Eigene, generische
Fantasy-Motive. Mechaniken dürfen übernommen werden, Grafik/Marken nicht.

## Fester Stil-Block (an JEDEN Prompt anhängen)
> isometric, 2:1 dimetric projection, ~30° top-down angle, orthographic,
> single building centered, soft light from top-left, subtle ambient shadow,
> clean transparent background, no ground plane, hand-painted fantasy game
> art, crisp edges, cohesive color palette, mobile game asset

Konsistenz ist der ganze Trick: gleicher Winkel, gleiche Lichtrichtung, gleicher
Maßstab. KI driftet — viele Varianten erzeugen, kuratieren, ggf. denselben
Seed/Style-Reference wiederverwenden.

## Palette pro Fraktion
- **Menschen** (zuerst): warmer Sandstein, schiefer-blaue Dächer, Goldakzente,
  rote Banner.
- Waldvolk: Holz/Moosgrün, helle Blätter. — später
- Totenreich: Knochen-Grau, kaltes Violett, grünes Geisterlicht. — später
- Orks: dunkles Eisen, Leder, Rost-Rot. — später

## Ausgabe-Format
- Quadratisch, transparent PNG. Generieren auf **1024×1024**, später auf
  Ziel-Footprint herunterskalieren (Engine skaliert auch zur Laufzeit).
- Ein Motiv mittig, gleiche relative Höhe über alle Gebäude, damit sie auf den
  Hotspots gleich groß wirken.
- Falls das Tool keinen sauberen Alpha-Kanal liefert: Hintergrund nachträglich
  entfernen (remove.bg, SD-Matting o.ä.).

## Ablage (Drop-in — Dateinamen sind verbindlich)
```
game/assets/city/menschen/bg.png          # Stadt-Hintergrund (Vollbild, opak)
game/assets/city/menschen/kaserne.png
game/assets/city/menschen/spaeher.png
game/assets/city/menschen/markt.png
game/assets/city/menschen/schmiede.png
game/assets/city/menschen/reiterei.png
game/assets/city/menschen/wachturm.png
game/assets/city/menschen/kapelle.png
game/assets/city/_shared/construction.png # generische Baustelle (alle Fraktionen)
```
Die 7 Gebäude-IDs sind exakt die aus `BUILDINGS` (WorldMapScreen.gd). Andere
Fraktionen analog unter `city/<fraktion>/` (waldvolk, totenreich, orks).

## Motiv-Prompts (Menschen)
Jeweils + Stil-Block + Palette anhängen.

- **bg**: *medieval human town panorama, hilltop castle backdrop, sky and
  distant fields, painterly background plate* (opak, kein Alpha nötig).
- **kaserne** (Nahkampf-Ausbildung): *stone barracks with wooden training yard,
  weapon racks, palisade*.
- **schmiede** (Name = Schmiede): *blacksmith forge building, chimney with
  embers, anvil at entrance*.
- **reiterei** (schwere Reiter): *timber stables with hay, horse paddock,
  banners*.
- **markt**: *market hall with striped awnings, stalls of goods, barrels and
  crates*.
- **spaeher** (Späher/Bewegung): *ranger's outpost, wooden lookout lodge,
  signal flags, rope bridge*.
- **wachturm** (Kampfkraft): *tall fortified stone watchtower with battlements
  and arrow slits*.
- **kapelle** (XP): *small stone chapel with arched stained-glass window and
  bell*.

## So kommt die Art ins Spiel (nächster Code-Schritt)
Aktuell zeichnet `CityScreen.gd` Platzhalter-Iso-Blöcke. Geplanter Schritt:
Textur-Laden mit Fallback — liegt unter dem o.g. Pfad ein PNG, wird es am
Hotspot gerendert, sonst der Platzhalter-Block. Dadurch erscheinen Sprites
**ohne weitere Code-Änderung**, sobald die Dateien liegen; jedes Gebäude
upgradet einzeln. Hotspot-Positionen danach in `data/city_layout.json`
feinjustieren (an `bg.png` ausrichten).
