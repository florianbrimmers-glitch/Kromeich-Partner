# Newsletter aus `newsletter@kromeichpartner.de` ziehen — Plan

Stand 06.08.2026. Ziel: die Eigentümer-Verteiler, die an das Sammelpostfach
`newsletter@kromeichpartner.de` gehen, automatisiert auswerten — **Text und Anhänge** —
und die Flächenstände gegen Propstack abgleichen.

Hintergrund: Die Newsletter sind oft aktueller als die Websites der Eigentümer. In
`eigentuemer.xlsx`, Spalte „Wie werden Updates versendet", ist vermerkt, wo wir schon
angemeldet sind; die fehlenden Anmeldungen sind am 05.08.2026 mit `newsletter@` nachgeholt
worden.

## Was gemessen wurde (06.08.2026)

| Befund | Ergebnis |
|---|---|
| claude.ai-Gmail-Connector | aktiv, gebunden an `florian.brimmers@kromeichpartner.de` |
| `newsletter@` über den Connector erreichbar? | **nein** — kein eigenes Postfach im Zugriff |
| Kopie von `newsletter@` im Postfach Florian? | **nein** — Suche über `to:` / `cc:` / `deliveredto:` inkl. Archiv und Trash: 0 Treffer |
| Microsoft-365-Connector | gebunden an `kromeich@kromeichpartner.de`; `newsletter@` → `ErrorInvalidUser` |
| Anhänge über den Connector | **nein** — `get_message` liefert `filename`, `mimeType`, `attachmentId`, **keine Bytes**; kein Download-Aufruf vorhanden (verifiziert an einem PDF-Anhang) |
| Google-Drive-Connector | aktiv, `download_file_content` funktioniert |
| Verteiler, die bereits bei Florian ankommen | u. a. P3 Logistic Parks `Availability MM/YYYY` (`watchdog.news@p3parks.com`, monatlich, Liste im Mailtext) und GARBE Flächenchancen (`newsletter@garbe-industrial.de`) |

Fazit: Für Anhänge reicht kein Connector. Es braucht den direkten Gmail-API-Zugriff auf das
Postfach.

## Weg A — Gmail-API mit eigenem Refresh Token (gewählt)

`newsletter@` ist ein **eigenes E-Mail-Konto** (Bestätigung des Users vom 06.08.2026), damit
ist der direkte Weg möglich. `gmail.readonly` deckt `users.messages.attachments.get` ab,
Anhänge kommen damit vollständig durch.

### Was zu beschaffen ist

Es fehlt **genau ein Wert**. `GOOGLE_CLIENT_ID` und `GOOGLE_CLIENT_SECRET` liegen bereits
als Repository Secrets und werden von `.github/workflows/contact-import.yml` mit fünf
Refresh Tokens (Florian, Denise, Marek, Lena, Oguzhan) produktiv genutzt; derselbe
OAuth-Client gilt für alle Konten der Domain.

- **Neu:** ein Refresh Token für `newsletter@`, unter **eigenem** Secret-Namen, z. B.
  `GOOGLE_REFRESH_TOKEN_NEWSLETTER`.
  **Nicht** `GOOGLE_REFRESH_TOKEN` überschreiben — das ist Florians Konto, der
  Kontakt-Import würde still auf das falsche Postfach umgelenkt.
- Erzeugung mit dem Verfahren aus `setup_guide.md`, **eingeloggt als `newsletter@`**
  (die Kontoauswahl ist die häufigste Fehlerquelle), Scope
  `https://www.googleapis.com/auth/gmail.readonly`.
- Voraussetzungen im Cloud-Projekt: Gmail API aktiv und OAuth-Consent-Screen als
  **Internal**. Bei Publishing-Status „Testing" verfallen Refresh Tokens nach 7 Tagen.
  Da der Kontakt-Import seit Monaten läuft, ist beides bereits erfüllt.
- Werte gehören ausschließlich in die Repository Secrets — nicht in Chat, Tickets, Notion
  oder Code.

### Was zu bauen ist

1. **Eigener Reader statt Wiederverwendung.** `src/gmail_client.py` würde genau die
   gesuchten Mails verwerfen: `SKIP_PREFIXES` enthält `newsletter`, `marketing`, `info`,
   `no-reply`, `notifications`; `SKIP_SUBJECT_PATTERNS` verwirft **jeden Betreff mit
   „newsletter"** sowie „unsubscribe". Das Modul ist für eingehende Mieteranfragen gebaut.
   Für `newsletter@` wird der Filter **umgekehrt**: Verteiler behalten, persönliche
   Korrespondenz ignorieren. Wiederverwendet werden `_build_credentials()` und
   `_decode_body()`.
2. **Anhang-Download ergänzen.** Im Repo existiert dafür nichts (`grep -i attachment`:
   0 Treffer). Nötig: `users().messages().attachments().get(userId="me", messageId=…, id=…)`,
   base64url-Dekodierung, Ablage als Datei, Filter auf `application/pdf`, Excel und
   Bilder, Unterdrückung von Signatur-Grafiken (`image00x.png/jpg`).
3. **Auswertung** je Verteiler-Mail: Standort, Flächen, Verfügbarkeit, Teilbarkeit,
   Bezugstermin — aus Mailtext **und** Anhang. PDF-Text über den bestehenden
   Exposé-Pfad, Excel-Anhänge tabellarisch.
4. **Abgleich gegen Propstack** nach dem Muster des `propstack-expose-workflow`-Skills:
   Objekt vorhanden → prüfen und vervollständigen; nicht vorhanden → nach Anleitung
   anlegen. Bestehende Regeln gelten unverändert, insbesondere:
   `provisionspflichtig` nie mit einem Wert schreiben, Mieten nur in
   `intern_mietpreis_*` plus `price_on_inquiry: true`, **keine automatische Freisetzung**
   von Flächen, Aufgaben immer an Lena.
5. **Workflow** analog `.github/workflows/newsletter-handler.yml`, mit `DRY_RUN` als
   Vorgabe und einem `NO_WRITE`-Lauf zur Abnahme.

### Verifikation

- Erster Lauf mit `DRY_RUN`: Anzahl gelesener Mails, erkannte Verteiler, geladene Anhänge
  mit Dateinamen und Größe — ohne einen einzigen Schreibzugriff.
- Gegenprobe, dass der umgekehrte Filter greift: eine Verteiler-Mail mit „Newsletter" im
  Betreff muss **durchkommen** (unter dem alten Filter wäre sie verworfen worden).
- Anhang-Nachweis an einem PDF: Datei liegt auf der Platte, Seitenzahl lesbar.
- Erst danach Schreibzugriffe, wie gewohnt mit Read-Back — HTTP 200 gilt nicht als Erfolg.

## Weg B — Rückfalloption ohne API-Zugriff

Falls der Refresh Token nicht zustande kommt:
Weiterleitungs- bzw. Filterregel von `newsletter@` in ein Postfach, das der Connector
lesen kann (Label „Verteiler"), plus ein Apps Script, das Anhänge eingehender
Verteiler-Mails in einen Drive-Ordner legt — der Drive-Connector kann Dateien
herunterladen. Deckt Text vollständig und Anhänge mit Zeitverzug ab, ist aber die
schwächere Lösung.

## Zwischenlösung, ohne neue Freigabe möglich

Die Verteiler, die schon heute bei `florian.brimmers@` ankommen, lassen sich sofort
auswerten — belegt an der monatlichen P3-Verfügbarkeitsliste und den GARBE
Flächenchancen.
