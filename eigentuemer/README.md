# Hallenbörse – Eigentümer-Portal (Prototyp)

Eigentümer stellen ihre Hallenfläche selbst ein, ohne Provision. Einmalig wird geprüft, ob der Einsender über die Fläche verfügen darf; danach ist das Objekt für Suchende sichtbar. Entrypoint `python -m eigentuemer.main`, Standard-Port 8090.

Eigenständiges Paket – **kein Code-Sharing** mit `hallentinder/` oder den Slack-Handlern. Es ist ein anderes Produkt: der Hallentinder zeigt den **eigenen Propstack-Bestand**, dieses Portal sammelt **fremde Objekte** mit eigener Datenhaltung.

## Die drei Oberflächen

| Seite | Für wen | Zweck |
|---|---|---|
| `/` | Eigentümer und Makler | Objekt einstellen, Nachweis hochladen |
| `/status.html?t=…` | der Einsender | Stand des Vorgangs verfolgen |
| `/pruefung.html` | intern, passwortgeschützt | Nachweis prüfen, freigeben oder ablehnen |

## Ablauf

1. **Einstellen.** Rolle wählen (Eigentümer oder Vermarktungsmandat), Kontakt, Objektdaten, Fotos und den passenden Nachweis: Grundbuchauszug beim Eigentümer, Alleinvermarktungsauftrag beim Makler. Ohne Einwilligung passiert nichts.
2. **Bestätigung.** Der Vorgang bekommt eine Nummer im Format `KP-2026-0001` – die lässt sich am Telefon vorlesen – und einen Statuslink mit Zufallstoken.
3. **Prüfen.** Intern erscheint der Vorgang in der Liste. Der Nachweis wird über einen geschützten Endpunkt gestreamt, nie über einen statischen Pfad. Wer prüft, trägt seinen Namen ein; eine Ablehnung braucht einen Grund, den der Einsender zu sehen bekommt.
4. **Benachrichtigen.** Der Einsender bekommt die Eingangsbestätigung mit Vorgangsnummer und Statuslink, später die Entscheidung. Intern geht eine Meldung an die Adressen aus `EIGENTUEMER_INTERN_AN`.
5. **Veröffentlichen.** Nach der Freigabe liefert `GET /api/objekte` das Objekt aus – mit dem Hinweis „Direkt vom Eigentümer" oder „Über Vermarktungsmandat", aber **ohne jede Angabe zum Einsender**.

## Der Nachweis wird gelöscht

Ein Grundbuchauszug nennt Eigentümer und Belastungen. Für den Betrieb der Plattform wird er nach der Prüfung nicht mehr gebraucht, deshalb wird die Datei mit der Entscheidung gelöscht. Erhalten bleibt das Protokoll: **welche Art** von Nachweis **wer wann** geprüft hat. Der Abruf danach antwortet mit `410 Gone` und sagt das auch.

Das reduziert die Haftung erheblich: Was nicht gespeichert ist, kann nicht abfließen.

## Ändern durch den Einsender

Über den Statuslink verwaltet der Einsender sein Objekt selbst:

- **Angaben ändern** – Fläche, Miete, Ausstattung, Beschreibung, Fotos. Ohne erneute Prüfung: Der Nachweis belegte die Verfügungsbefugnis, nicht die Ausstattung.
- **Adresse ändern** – das ist ein anderes Objekt. Der Vorgang geht zurück in die Prüfung und verlangt einen neuen Nachweis; ohne ihn lehnt der Server die Änderung ab. Groß-/Kleinschreibung und doppelte Leerzeichen zählen nicht als Änderung.
- **Zurückziehen und wieder online stellen** – die häufigste Änderung überhaupt ist „Halle ist vermietet". Dafür darf niemand eine Mail schreiben müssen. Wieder online geht nur, wenn der Vorgang schon einmal geprüft war.

Jeder Schritt landet im Verlauf, den Einsender und Prüfung sehen.

**Der Statuslink ist der Zugang** – wer ihn hat, hat das Objekt eingereicht. Für einen Prototyp ist das angemessen; für den Echtbetrieb gehört an diese Stelle ein Bestätigungscode per Mail bei jeder Änderung.

## E-Mail

Ohne `EIGENTUEMER_SMTP_HOST` wird **nichts verschickt, sondern geloggt** – derselbe Gedanke wie `NO_WRITE` beim Hallentinder. Wer testet, schickt keine Post an echte Eigentümer.

Der Versand lässt einen Vorgang nie scheitern: Eine Einreichung, die an einem SMTP-Timeout stirbt, wäre schlimmer als eine Einreichung ohne Mail.

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `EIGENTUEMER_DATEN` | nein | `eigentuemer_daten` | Ablage für Datenbank und Dateien – **nicht** unter `static/` |
| `EIGENTUEMER_PRUEF_PASSWORT` | nein | wird erzeugt | Zugang zur Prüfansicht; ohne Angabe erzeugt der Start eines und schreibt es ins Log |
| `EIGENTUEMER_HOST` | nein | `0.0.0.0` | Bind-Adresse |
| `EIGENTUEMER_PORT` | nein | `8090` | Port |
| `EIGENTUEMER_BASIS_URL` | nein | `http://localhost:<port>` | Adresse für die Links in den E-Mails |
| `EIGENTUEMER_SMTP_HOST` | nein | – | Ohne Angabe wird keine Mail verschickt, sondern geloggt |
| `EIGENTUEMER_SMTP_PORT` | nein | `587` | 465 schaltet auf SSL statt STARTTLS |
| `EIGENTUEMER_SMTP_BENUTZER` | nein | – | Anmeldung am Mailserver |
| `EIGENTUEMER_SMTP_PASSWORT` | nein | – | Anmeldung am Mailserver |
| `EIGENTUEMER_ABSENDER` | nein | `noreply@kromeichpartner.de` | Absenderadresse |
| `EIGENTUEMER_INTERN_AN` | nein | – | Wer intern über neue Vorgänge informiert wird (kommagetrennt) |

## Lokal starten

```bash
pip install -r requirements.txt
python -m eigentuemer.main
```

Das Log nennt beide Adressen und – falls keins gesetzt wurde – das erzeugte Passwort für die Prüfansicht. Der Benutzername ist frei wählbar und landet im Protokoll.

Tests:

```bash
pytest tests/eigentuemer/ -v
```

## Was dieser Prototyp nicht ist

- **Keine Benutzerverwaltung.** Ein gemeinsames Passwort für die Prüfansicht, keine Rollen, keine Historie pro Prüfer über den Namen hinaus.
- **Keine Suche.** `GET /api/objekte` liefert alle freigegebenen Objekte; Filter, Umkreis und Ranking stecken im Hallentinder und sind hier noch nicht angeschlossen.
- **Keine Zugangssicherung über den Link hinaus.** Wer den Statuslink hat, kann das Objekt ändern.
- **Dateiablage lokal.** Für einen Server mit mehreren Instanzen bräuchte es einen Objektspeicher.
