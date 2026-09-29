---
name: "propstack-expose-workflow"
description: "Verarbeitet Immobilien-Exposés und legt Projekte/Einheiten in Propstack CRM an oder pflegt sie – über den Propstack-MCP-Server von Kromeich & Partner. Triggert bei: Exposé-PDFs (Upload oder #objekte), Anfragen wie \"lege dieses Exposé in Propstack an\", \"neues Objekt anlegen\", \"ergänze diese Fläche\", \"Objekt ist vermietet\", Links auf crm.propstack.de, Dealmeldungen und Newslettern von Eigentümern. Nutze diesen Skill IMMER, wenn es um Exposé-Verarbeitung oder Propstack-Objektpflege geht."
---

# Exposé → Propstack (über den MCP-Server)

Alle Zugriffe auf Propstack laufen über den MCP-Server **„Propstack Kromeich & Partner“**. Es gibt hier **keine API-Schlüssel** und keine curl-Aufrufe. Fehlen die Werkzeuge `einheit_lesen`, `einheit_anlegen` usw., ist der Server nicht verbunden: Den User bitten, ihn in Claude unter *Einstellungen → Connectors* hinzuzufügen und sich mit dem Firmenkonto anzumelden. Nicht auf anderem Weg an Propstack schreiben.

Der Server prüft die Hausregeln selbst und lehnt Verstöße mit **„REGELVERSTOSS – nichts geschrieben“** ab. Dann den Grund lesen und die Daten korrigieren. Die Prüfung nicht umgehen.

## Grundsätze

1. **Nichts ohne Rücksprache.** Strukturentscheidungen (Einheiten aufteilen, Dubletten stilllegen, Eigentümer ändern) erst vorschlagen, dann nach Freigabe umsetzen.
2. **Existenz vor Anlage.** Immer über **PLZ und Straße** suchen, dazu Ort, Eigentümer und Marketingname. Gefunden heißt: ergänzen und sanieren, nicht neu anlegen.
3. **Nichts erfinden.**
   - Keine Zahl im Exposé → Feld leer lassen und in der Prüfungsaufgabe benennen.
   - Nur eine Quote genannt (z. B. „1 Rampe je 1.000 m²“) → rechnen und als *abgeleitet* kennzeichnen.
   - E-Mail-Adressen nie raten.
4. **0 m² ist nie richtig.** In die Flächenfelder gehört die reale Größe, auch bei vermieteten Einheiten. Vermietung zeigen `rented` und der Status (`vermietet_setzen`).
5. **Provision auf jeder Einheit** (`provision: frei | pflichtig`). Die Regel kommt vom User oder aus dem Exposé. Im Zweifel fragen. Das Feld `provisionspflichtig` wird nie gesetzt; der Server sperrt es.
6. **Keine Eigentümer-, Entwickler- oder Markennamen** in Titel, Beschreibung, Lage und Ausstattung. Die Namen immer als `verbotene_namen` mitgeben. Der Eigentümer steht nur im Custom Field `eigentumer` und in der Verknüpfung.
7. **Mietpreise nur intern:** `intern_mietpreis_hallenflache`, `_buro`, `_mezzanine`, dazu `price_on_inquiry: true`. Nie in öffentliche Preisfelder, nie in Texte.
8. **Bemerkung nie überschreiben**, nur mit `bemerkung_ergaenzen` vorne anfügen. Dort gehören hin: Quelle, Widersprüche, abgeleitete Werte, offene Punkte.
9. **Löschen macht nur der User in der UI.** Dubletten werden gekennzeichnet: Titel-Präfix `[ZU LOESCHEN] `, Status Abgeschlossen, verfügbar „<reale m²> (Dublette stillgelegt)“, Vermerk am bleibenden Datensatz.
10. **Prüfungsaufgabe immer an Lena Klinnert** (`pruefaufgabe_anlegen` setzt sie automatisch).
11. **Portale:** Wir laden nichts auf Portale hoch.
12. **Newsletter:** Immer den Stand des aktuellsten Newsletters nehmen.

## Schritt 1 – Quelle lesen

- PDF: `pdftotext -layout`, Bilder mit `pdfimages -j`. Lagepläne und Grundrisse sind oft Vektorgrafik; diese Seiten mit `pdftoppm -r 150` rendern.
- PDF-Metadaten ansehen (Autor, Datum). KI-erzeugte oder aus Portalen kopierte Exposés gegen die Eigentümerquelle prüfen; bei Widersprüchen gilt die belastbarere Quelle (Bauakte vor Inserat).
- Summen nachrechnen (Halle + Büro + Mezzanine), Widersprüche notieren.
- Links auf `crm.propstack.de/app/portfolio/properties/<ID>` zeigen auf eine Einheit, `/projects/<ID>` auf ein Projekt. Zuerst mit `einheit_lesen` oder `projekt_lesen` den Ist-Zustand holen.

## Schritt 2 – Existenzprüfung

`einheiten_suchen` (Straße, dann PLZ, dann Ort) und `projekte_suchen`. `kontakte_suchen` für Eigentümer und Ansprechpartner.

Altdaten aus dem Import vom 13.01.2025 (IDs 2777xxx/2778xxx) sind oft kaputt:
- **Kategorie:** Wohnen/Apartment statt Industrie/Halle → `rs_type: INDUSTRY`, `rs_category: HALL`.
- **Baujahr** „2“.
- **Tausenderfehler:** Bruchteile unter 100 sind korrupt. Werte ab 100 nach Nachkommastellen beurteilen: 3 Nachkommastellen = Lesefehler, 1–2 = echter Wert. Werte ab 1.000 nie mit 1.000 multiplizieren.
- **Maklereinträge** im Eigentümerfeld.

## Schritt 3 – Struktur

- Mehrere unabhängig vermietbare Flächen → **Projekt + je Fläche eine Einheit**, auch die vermieteten.
- Werte, die nur für das Gesamtobjekt vorliegen (Tore, Stellplätze), nicht auf jede Einheit kopieren. Sie stehen im Text, die Aufteilung wird erfragt.
- Titelschema: `Logistikhalle in (<erste 2 PLZ-Ziffern>) <Ort> – <Straße>`, Einheiten mit `– Halle 1`, `– Unit 1.1` usw.
- `einheiten_gesamt`, `verm_einheiten` und `vermietungsstand_einheiten` sind an allen Einheiten eines Standorts gleich.

## Schritt 4 – Anlegen oder pflegen

1. `projekt_anlegen` (ohne Eigentümer), dann `eigentuemer_setzen`.
2. `einheit_anlegen` je Einheit, mit `felder`, `custom_fields`, `provision`, `provision_quelle`, `verbotene_namen` und `bemerkung`.
   - Flächen in allen Varianten: `lagerflache`, `_gesamt`, `_verfugbar` (Text), `_teilbar_ab`. Ebenso Büro und Mezzanine (`mezzanineflache_gesamt` / `_verfugbar`, **nie** `mezzanineflache`).
   - Tore: `ramepntore` = Rampen (Text), `anzahl_rampentore_2` = **ebenerdige** Tore (Zahl).
   - `floor_load` in kg/m² (5 t/m² = 5000), `bodentragkraft` als Text („5,0 t/m² (50 kN/m²)“).
   - Unbekannte Felder vorher mit `feld_nachschlagen` prüfen (Typ und Einheit).
3. Die Rückgabe `abweichungen: []` bedeutet: steht so in Propstack. Sonst die Abweichungen melden oder nachbessern.
4. Vermietet: `vermietet_setzen` mit Beleg. Andere Statuswechsel: `status_setzen`.
5. Bestehende Einheit: `einheit_aktualisieren`, dazu `bemerkung_ergaenzen` mit dem Warum.

## Schritt 5 – Bilder

- Das erste Bild wird Titelbild, das beste Außenbild zuerst.
- **Keine Firmenschriftzüge** (Wissensdatenbank 1.10). Logos an Fassaden, Bannern, LKW und Plan-Köpfen wegschneiden oder retuschieren. Luftbilder mit Beschriftungen des Eigentümers weglassen.
- Grundrisse mit `grundriss: true` hochladen, alle Bilder sinnvoll betiteln.
- Bilder an Projekt **und** Einheiten hängen. Je Einheit, wenn möglich, den eigenen Plan-Ausschnitt.
- `bild_hochladen` mit Base64 oder öffentlicher URL.

## Schritt 6 – Prüfungsaufgabe

`pruefaufgabe_anlegen` mit Absätzen zu:
- Quelle
- was angelegt oder geändert wurde
- Widersprüche
- **bewusst leer gelassene Felder**
- abgeleitete Werte
- offene Punkte
- manuell Nachzuholendes: Exposé in „Objektunterlagen“ ablegen, Landing-Page-Schalter setzen, Vorschau prüfen

Fällig ist die Aufgabe am nächsten Werktag. Recherche-Aufträge formulieren wir so, dass Lena selbst recherchiert, statt beim Eigentümer nachzufragen, wenn der User das so vorgibt.

## Schritt 7 – Zusammenfassung an den User

Projekt- und Einheiten-IDs mit Flächen und Status; was korrigiert wurde; was fehlt, um das Objekt kundenreif zu machen; welche Werte abgeleitet sind; offene Entscheidungen als Fragen.

## Nicht per MCP möglich (UI)

Löschen (Einheiten, Bilder, Deals), Landing-Page-Schalter, Dokumente in Ordner ablegen, Mails aus Propstack einsehen.
