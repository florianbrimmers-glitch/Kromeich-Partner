# Kromeich GmbH – Propstack Wissensdatenbank

Quelle: Notion-Seite `32d7b7e5627b81d3a471fbbd134fc8dd`, Stand 25.03.2026.

Diese Seite dokumentiert die internen Prozesse der Kromeich GmbH für die Anlage von Objekten und Projekten in Propstack.

---

## 1. Objekt anlegen (Einzelobjekte)

### 1.1 Stammdaten
- **Kategorie:** Kauf/Miete und Gewerbe unterscheiden
- **Objektart:** Halle/Produktion → Halle
- **Überschrift:** Einheitlich: *Logistikhalle in (2-stellige PLZ) Ort*
- **Aktiv:** Hinterlegen, wenn das Objekt angeboten werden kann

### 1.2 Interne Notizen
- Link zum Exposé oder Website
- Alleinmandat eines Maklers
- Mietpreise (**niemals** im Feld "Preise" hinterlegen!)
- Provisionsregelungen (Tischregel, Vereinbarungen, Höhe etc.)
- Projektname der Entwickler

### 1.3 Ansprechpartner
- Betreuer zieht sich i.d.R. automatisch
- Eigentümer ausfüllen
- Sofern vorhanden: Kontakt hinterlegen

### 1.4 Adresse
- Adresse ausfüllen und im Dropdown auswählen → Koordinaten werden automatisch gezogen

### 1.5 Provision

**Provisionspflichtig = Ja:**
Provisionsstaffel nach Mietvertragslaufzeit:
- < 5 Jahre: 2 Nettokaltmieten zzgl. MwSt.
- >= 5 bis < 7 Jahre: 3 Nettokaltmieten zzgl. MwSt.
- >= 7 bis < 10 Jahre: 3,5 Nettokaltmieten zzgl. MwSt.
- >= 10 Jahre: 4 Nettokaltmieten zzgl. MwSt.

**Provisionspflichtig = Nein:**
- Außenprovision für Exposé → "Provisionsfrei"
- Provisionshinweis: "Die Anmietung erfolgt provisionsfrei für den Mieter."

### 1.6 Flächen (aus Exposé)
Auszufüllen: Hallenfläche, Hallenfläche teilbar ab, Bürofläche, Bürofläche teilbar ab, Mezzaninefläche, Mezzaninefläche teilbar ab, Grundstücksfläche, Gesamtfläche (Halle + Mezzanine), PKW-Stellplätze, LKW-Stellplätze, Hallenhöhe (m UKB), Rampentore, Ebenerdige Tore, WGK, Beleuchtung, Bodentragkraft, Sprinkleranlage

### 1.7 Energie & Nachhaltigkeit
Auszufüllen: Heizungsart Halle, Wesentlicher Energieträger, Zertifizierung, Baujahr

### 1.8 Zusatzinformationen
- Verfügbar ab
- Button "Vermietet" standardmäßig auf "nicht vermietet"

### 1.9 Beschreibung
- **Lage:** Aus Exposé übernehmen. Falls nicht vorhanden → KI-Prompt: "Stichpunktartige Auflistung der Anbindung an Autobahnen, Häfen und Flughäfen ab der [Adresse]"
- **Ausstattung:** Beleuchtung, Besonderheiten (Regalierung, Gleisanschluss, WGK etc.)

### 1.10 Medien hinzufügen
- Bilder aus Exposé hochladen (oder Google Maps Screenshots)
- **Wichtig:** Keine Firmenschriftzüge auf Bildern!
- Bilder in Propstack benennen (z.B. "Außenansicht")
- Grundrisse in den Einstellungen als solche kennzeichnen
- Vorschau der Landing Page über die drei Punkte prüfen

---

## 2. Projekt anlegen (Projekte mit Einheiten)

### 2.1 Stammdaten
- **Name:** *Logistikhalle in (2-stellige PLZ) Ort*
- Interner und externer Name sollten gleich sein

### 2.2 Interne Notizen
Identisch mit Objektanlage (siehe 1.2)

### 2.3 Ansprechpartner
Identisch mit Objektanlage (siehe 1.3)

### 2.4 Adresse
Identisch mit Objektanlage (siehe 1.4)

### 2.5 Webseite & Landing-Page
- **Überschrift:** Name inkl. erste 2 Ziffern der PLZ (z.B. *Logistikparks in (50) Köln*)
- Aktivieren: "Mietprojekt", "Einheitenliste im Exposé anzeigen", "Auf der Landing Page auf die jeweiligen Einheiten verlinken"

### 2.6 Provision
Identisch mit Objektanlage (siehe 1.5)

### 2.7 Beschreibung
- **Projektbeschreibung:** Gesamtfläche, Abschnitte, Lagerfläche, Büro, Rampen etc.
- **Lage & Ausstattung:** Identisch mit Objektanlage (siehe 1.9)

### 2.8 Energieausweis
Heizungsart Halle, Wesentlicher Energieträger, Baujahr

### 2.9 Einheiten anlegen
Über die drei Punkte oben rechts → "Neue Einheit"

Der Prozess entspricht weitgehend der Objektanlage:
- **Stammdaten:** Kategorie, Objektart, Einheitennummer (Unit 1, Unit 2 etc.), Aktiv-Status
- **Ansprechpartner:** Wie Objekt
- **Provision:** Wie Objekt
- **Flächen:** Wie Objekt (siehe 1.6)
- **Energie & Nachhaltigkeit:** Wie Objekt (ohne Baujahr)
- **Zusatzinformationen:** Verfügbar ab

---

## Wichtige Regeln

- Mietpreise **niemals** im Feld "Preise" eintragen – immer in Interne Notizen!
- Medien dürfen **keine Firmenschriftzüge** enthalten
- Alle Änderungen immer **speichern**!
- Über die drei Punkte kann jederzeit eine Vorschau der Landing Page aufgerufen werden
