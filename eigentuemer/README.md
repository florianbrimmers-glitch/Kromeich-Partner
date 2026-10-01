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
4. **Veröffentlichen.** Nach der Freigabe liefert `GET /api/objekte` das Objekt aus – mit dem Hinweis „Direkt vom Eigentümer" oder „Über Vermarktungsmandat", aber **ohne jede Angabe zum Einsender**.

## Der Nachweis wird gelöscht

Ein Grundbuchauszug nennt Eigentümer und Belastungen. Für den Betrieb der Plattform wird er nach der Prüfung nicht mehr gebraucht, deshalb wird die Datei mit der Entscheidung gelöscht. Erhalten bleibt das Protokoll: **welche Art** von Nachweis **wer wann** geprüft hat. Der Abruf danach antwortet mit `410 Gone` und sagt das auch.

Das reduziert die Haftung erheblich: Was nicht gespeichert ist, kann nicht abfließen.

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `EIGENTUEMER_DATEN` | nein | `eigentuemer_daten` | Ablage für Datenbank und Dateien – **nicht** unter `static/` |
| `EIGENTUEMER_PRUEF_PASSWORT` | nein | wird erzeugt | Zugang zur Prüfansicht; ohne Angabe erzeugt der Start eines und schreibt es ins Log |
| `EIGENTUEMER_HOST` | nein | `0.0.0.0` | Bind-Adresse |
| `EIGENTUEMER_PORT` | nein | `8090` | Port |

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
- **Keine Benachrichtigungen.** Der Einsender erfährt die Entscheidung nur über seinen Statuslink – keine E-Mail. Das ist der erste Punkt, der für den Echtbetrieb fehlt.
- **Keine Suche.** `GET /api/objekte` liefert alle freigegebenen Objekte; Filter, Umkreis und Ranking stecken im Hallentinder und sind hier noch nicht angeschlossen.
- **Kein Bearbeiten.** Ein eingereichtes Objekt lässt sich nicht ändern oder zurückziehen.
- **Dateiablage lokal.** Für einen Server mit mehreren Instanzen bräuchte es einen Objektspeicher.
