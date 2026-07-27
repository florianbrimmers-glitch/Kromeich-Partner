# Drive-Migration: Unternehmensdaten aus dem Privatkonto lösen

**Stand:** 27.07.2026 · **Anlass:** Zugriff des Gesellschafters Felix Kern auf die Unternehmensdaten
im Google Drive soll beendet werden. Die Ordnerstruktur liegt aktuell auf seinem privaten
Google-Konto.

---

## 1. Befund (per Drive-API erhoben)

### 1.1 Eigentümerschaft

Der Wurzelordner **„Kromeich & Partner"** (`1kriRg2pmh1H6J7XyfE_OtKQGs4M2HIH1`) gehört
`felix.kern2014@gmail.com` – einem privaten Gmail-Konto außerhalb unseres Workspace.
Damit hängt die komplette Ablage an einem Konto, auf das wir administrativ keinen Zugriff haben.

Eigentümer der obersten Ebene:

| Ordner | Eigentümer |
|---|---|
| **Kromeich & Partner** (Wurzel) | felix.kern2014@gmail.com |
| 01. Allgemein | felix.kern2014@gmail.com |
| 02. Investment | felix.kern2014@gmail.com |
| 03. Leasing | felix.kern2014@gmail.com |
| 04. Asset Management | felix.kern2014@gmail.com |
| 05. Consulting | felix.kern2014@gmail.com |
| 06. Project Management | felix.kern2014@gmail.com |
| 07. Logistik | kromeich@kromeichpartner.de |
| 08. Research | kromeich@kromeichpartner.de |

In `01. Allgemein` gehören 10 von 15 Unterordnern demselben Privatkonto – darunter
`01. Gesellschaft`, `02. Marketing`, `03. Finanzen, Steuern`, `04. Vorlagen`,
`09. Knowledge Sharing`, `10. IT`. Die restlichen gehören `kern@kromeichpartner.de` (11. HR,
12. Versicherungen, 13. Diverses, 14. Partner) bzw. `kromeich@` / `florian.brimmers@`.

Auch inhaltlich liegt Substanz auf dem Privatkonto: Gesellschafts- und Anstellungsverträge
(`Anstellungsvertrag_GesGF_DK.docx`, `Arbeitsvertrag OS.docx`), Kooperationsverträge (Derricks,
Omnia Real Estate), Finanzamt-/Steuerkorrespondenz, Ausgangsrechnungen 2025, Mieter- und
Investorenlisten, PPT-Master und Logo-Dateien, HR-Unterlagen mit Ausweisdokumenten.

Nebenbefund: `Eigentümerliste_Updates.xlsx` gehört `kormeich@gmail.com` – ein **zweites**
privates Gmail-Konto in der Ablage. Ebenfalls ablösen.

### 1.2 Akuter Zusatzbefund: die Ablage ist per Link öffentlich

Der Wurzelordner trägt die Freigabe `{"role": "reader", "type": "anyone"}` – „Jeder, der den Link
hat" **ohne Google-Login**. Diese Freigabe vererbt sich auf den gesamten Baum; stichprobenartig
bestätigt für `01. Allgemein`, `01. Gesellschaft`, `03. Finanzen, Steuern` und `11. HR`.

Betroffen sind damit u. a. HR-Dokumente mit Personalausweis-Scans, Heiratsurkunde und
Arbeitsverträgen sowie die komplette Steuer- und Finanzkorrespondenz. Das ist unabhängig von
Felix Kern zu behandeln: Wer je einen Link erhalten oder weitergeleitet hat – Kandidat, Makler,
Dienstleister – kann bis heute lesen. Datenschutzrechtlich (Art. 32 DSGVO, besondere Kategorien
in den HR-Unterlagen) ist das der dringlichste Punkt des ganzen Vorgangs.

> Hinweis zur Methode: Die Berechtigungsliste zeigt nur, was das abfragende Konto sehen darf.
> Die vollständige Mitgliederliste je Ordner bitte zusätzlich in der Drive-UI prüfen.

### 1.3 Warum „Felix einfach entfernen" nicht funktioniert

In Google Drive kann dem **Eigentümer** einer Datei der Zugriff nicht entzogen werden. Solange
`felix.kern2014@gmail.com` Eigentümer ist, gilt:

- Wir können ihn nicht aus den eigenen Ordnern entfernen.
- Er kann jederzeit unsere Freigaben ändern, Inhalte löschen oder in den eigenen Papierkorb
  verschieben.
- Er könnte den öffentlichen Link jederzeit weiter streuen.
- Wenn er sein Google-Konto löscht oder das Speicherlimit reißt, sind die Daten für uns weg.

Der Zugriff endet also erst, wenn die **Eigentümerschaft** bei der Kromeich & Partner
Organisation liegt. Genau das leistet eine geteilte Ablage.

---

## 2. Zielbild: geteilte Ablage im bestehenden Workspace

Wir bauen nichts Neues auf, sondern nutzen, was in Google Workspace `kromeichpartner.de`
bereits enthalten ist:

- **Geteilte Ablage** (Shared Drive) statt „My Drive" einer Person. Eigentümer ist die
  Organisation, nicht ein Nutzer. Konto weg ≠ Daten weg.
- **Google-Gruppen** als Zugriffsschicht (`gf@`, `team@`, `finanzen@`, `hr@`). Zugriff wird über
  Gruppenmitgliedschaft gesteuert, nicht per Einzelfreigabe – Onboarding/Offboarding ist danach
  ein Klick.
- **Admin-Konsole** für Datenübertragung und Konto-Sperrung bei internen Konten.
- **Audit-Log** (Drive-Protokoll) für die Nachkontrolle, wer wann was geöffnet oder
  heruntergeladen hat.

**Vorab zu prüfen:** Geteilte Ablagen setzen mindestens *Business Standard* voraus. Läuft der
Tenant auf *Business Starter*, ist ein Upgrade Voraussetzung (bringt zugleich 2 TB Pool-Speicher
pro Nutzer, was für die Videoaufzeichnungen der Co-Working-Sessions ohnehin sinnvoll ist).

Zielstruktur – 1:1 wie heute, damit sich für das Team nichts ändert:

```
Geteilte Ablage „Kromeich & Partner"
├── 01. Allgemein            → Gruppe team@       (Unterordner HR/Finanzen eingeschränkt)
├── 02. Investment           → Gruppe team@
├── 03. Leasing              → Gruppe team@
├── 04. Asset Management     → Gruppe team@
├── 05. Consulting           → Gruppe team@
├── 06. Project Management   → Gruppe team@
├── 07. Logistik             → Gruppe team@
└── 08. Research             → Gruppe team@

Geteilte Ablage „KP Vertraulich"   → nur gf@
├── Gesellschaft / Beteiligungen
├── Finanzen, Steuern
└── HR / Personalakten
```

Die Trennung in zwei Ablagen ist die eigentliche Lehre aus dem Befund: Personalakten und
Gesellschaftsunterlagen haben in einem Baum, der breit geteilt wird, nichts zu suchen.

---

## 3. Umsetzung

### Phase 0 — Sofortmaßnahmen (heute, ohne Felix)

1. **Öffentliche Links kappen.** Bei jedem Ordner, auf dem wir Bearbeiter mit Freigaberecht sind,
   „Jeder mit dem Link" → „Eingeschränkt" setzen. Auf den Felix-eigenen Ordnern geht das nur
   durch ihn oder mit der Migration – umso mehr Grund, Phase 2 nicht liegen zu lassen.
2. **Backup ziehen.** Vollständige Kopie des Baums über Google Drive für Desktop (oder `rclone
   copy`) auf einen von uns kontrollierten Speicher. Vor jeder Verschiebeaktion. Nicht
   verhandelbar.
3. **Inventar sichern.** Datei-Liste inkl. Eigentümer als Nachweis des Ist-Zustands exportieren
   (Basis: die hier erhobenen API-Daten).
4. **Kein Ankündigungseffekt.** Solange Felix Eigentümer ist, hat er technisch die Oberhand.
   Erst Backup, dann Kommunikation.

### Phase 1 — Geteilte Ablagen aufsetzen (Admin, ~1 h)

1. Workspace-Edition prüfen, ggf. auf Business Standard upgraden.
2. Geteilte Ablagen „Kromeich & Partner" und „KP Vertraulich" anlegen.
3. Google-Gruppen anlegen/befüllen, als Mitglieder der Ablagen hinzufügen.
4. Ablage-Einstellungen härten: Freigabe außerhalb der Organisation **aus**, Download/Kopieren für
   Betrachter **aus** (bei „KP Vertraulich"), nur Manager dürfen Struktur ändern.
5. In der Admin-Konsole → Apps → Google Workspace → Drive und Docs vorübergehend freischalten:
   - *Migrationseinstellungen:* „Nutzer dürfen Dateien in geteilte Ablagen verschieben" **ein**
   - *Freigabeeinstellungen:* externe Mitglieder in geteilten Ablagen zulassen (nur temporär)

### Phase 2a — Migration **mit** Mitwirkung von Felix (empfohlener Weg)

Der technisch saubere Weg. Verschieben in eine geteilte Ablage überträgt die Eigentümerschaft an
die Organisation – **inklusive** Versionshistorie, Kommentaren, Erstellungsdaten und bestehenden
Links. Nichts bricht, keine Dubletten.

1. `felix.kern2014@gmail.com` **temporär** als *Inhaltsmanager* der Zielablage hinzufügen.
2. Felix verschiebt die sechs ihm gehörenden Top-Ordner sowie die zehn Unterordner in
   `01. Allgemein` in die geteilte Ablage (Drive-Web: Ordner markieren → „Verschieben nach" →
   geteilte Ablage). In Chargen, nicht alles auf einmal – Ordnerverschiebungen mit vielen tausend
   Dateien laufen sonst in Teilfehler.
3. Nach jeder Charge prüfen: Eigentümer aller Objekte ist jetzt die geteilte Ablage.
4. Wenn alles drin ist: Felix als Mitglied **entfernen**. Ab diesem Moment hat er keinen Zugriff
   mehr – auf keine Datei, auch nicht auf die von ihm erstellten.
5. Dasselbe für `kormeich@gmail.com` (Eigentümerliste).
6. Admin-Toggles aus Phase 1.5 wieder zurückdrehen (externe Mitglieder aus).

Falls Felix nur zur *Herausgabe*, nicht zur Mitarbeit bereit ist: Er kann alternativ
`admin@kromeichpartner.de` zum Eigentümer der Ordner machen (Freigabe → Rolle „Inhaber"). Danach
verschieben wir selbst. Etwas mehr Handarbeit, gleiches Ergebnis.

### Phase 2b — Migration **ohne** Mitwirkung von Felix (Rückfallebene)

Ohne ihn lässt sich Eigentum nicht übertragen – Google gibt uns keinen administrativen Hebel auf
ein fremdes Privatkonto. Bleibt: **kopieren.**

1. Kompletten Baum über Drive für Desktop / `rclone` lokal spiegeln.
2. Inhalte in die geteilte Ablage hochladen → Eigentümer ist damit die Organisation.
3. Team auf die neue Ablage umstellen, alte Struktur nicht mehr benutzen.
4. Freigaben zur Altstruktur von unserer Seite entfernen.

Preis dieses Wegs, bitte bewusst entscheiden:

- Versionshistorie, Kommentare und Original-Zeitstempel gehen verloren (relevant bei
  Vertrags- und Steuerunterlagen mit Nachweisbedarf).
- Alle bestehenden Links in Mails, Asana, Notion und Propstack zeigen weiter auf die alten
  Dateien.
- Google-Docs/Sheets/Slides werden zu Kopien; wer aktiv im Original weiterarbeitet, arbeitet an
  der falschen Datei. Kurze Schreibsperre-Phase einplanen.
- **Die Originale bleiben in seinem Besitz.** Technisch endet unsere Abhängigkeit, sein
  Datenbesitz nicht. Deshalb Abschnitt 4.

### Phase 2c — Das interne Konto `kern@kromeichpartner.de`

Hier sind wir Administrator, das ist trivial:

1. Admin-Konsole → Nutzer → `kern@…` → **Daten übertragen** (Drive + Docs) auf
   `admin@kromeichpartner.de`, dann in die geteilte Ablage verschieben.
2. Alle Sitzungen beenden, App-Passwörter und OAuth-Token widerrufen.
3. Konto **sperren** (nicht löschen – Beweis- und Aufbewahrungslage). Löschen erst nach
   Ablauf der Aufbewahrungsfristen, ggf. mit Vault-Aufbewahrung.
4. Mailweiterleitung und Delegierung für laufende Vorgänge einrichten.

### Phase 3 — Nachkontrolle

1. **Freigabe-Audit** über den gesamten neuen Baum: keine „Jeder mit dem Link"-Freigabe mehr,
   keine externen Einzelfreigaben. Bestehende Link-Freigaben auf Einzeldateien überleben die
   Verschiebung und müssen aktiv entfernt werden.
2. **Audit-Log** (Admin-Konsole → Berichte → Drive) auf Massendownloads in den Tagen vor dem
   Entzug prüfen und das Ergebnis dokumentieren.
3. **Zugriffstest:** Bestätigen, dass der alte Wurzel-Link ohne Login nichts mehr liefert.
4. **Automatisierungen prüfen:** Skripte und Connectors in diesem Repo, die auf Drive-IDs
   zeigen, laufen nach der Verschiebung weiter (IDs bleiben stabil) – bei Weg 2b **nicht**.
   Dann müssen die IDs nachgezogen werden.

---

## 4. Was Technik nicht löst

Nach Phase 2 hat Felix keinen *Zugriff* mehr. Was er bereits heruntergeladen, synchronisiert oder
– bei Weg 2b – als Original behalten hat, bleibt bei ihm. Das ist ein organisatorischer und
rechtlicher Vorgang, kein IT-Vorgang:

- Schriftliche Aufforderung zur Löschung aller Unternehmensdaten aus privaten Konten und
  Endgeräten, mit Frist und Löschbestätigung.
- Prüfen, was Gesellschaftsvertrag, Geschäftsführeranstellungsvertrag und NDA zu Herausgabe und
  Löschung hergeben.
- Soweit personenbezogene Daten Dritter betroffen sind (HR-Unterlagen, Eigentümer- und
  Mieterlisten), ist die Kromeich & Partner Verantwortlicher im Sinne der DSGVO – die
  Verarbeitung auf einem privaten Gmail-Konto ohne Grundlage ist ein eigenständiges Thema und
  stützt das Löschverlangen.
- Zwei Dinge auseinanderhalten: Der **operative Datenzugriff** darf entzogen werden. Als
  Gesellschafter hat er unabhängig davon ein Auskunfts- und Einsichtsrecht nach § 51a GmbHG.
  Beides ist vereinbar – Auskunft erteilt die Geschäftsführung anlassbezogen, nicht per
  Dauerzugriff auf die Ablage. Diesen Punkt bitte mit der Rechtsberatung abstimmen, bevor der
  Entzug kommuniziert wird.

---

## 5. Weitere Systeme (gleiche Frage, anderes Tool)

Der Drive ist der größte Brocken, aber nicht der einzige Ort mit Daten. Checkliste für dieselbe
Prüfung – jeweils: eigenes Konto, private Adresse, Gastzugang, API-Token?

| System | Zu prüfen |
|---|---|
| Google Workspace | Konto `kern@`, Gruppen-Mitgliedschaften, Kalenderfreigaben, Weiterleitungen, geteilte Ablagen |
| Slack | Mitgliedschaft, Gastkonten, private Kanäle, exportierte Daten |
| Propstack (CRM) | Nutzerkonto, API-Keys, Objekt- und Eigentümerdaten |
| Notion | Workspace-Mitgliedschaft, private Seiten, geteilte Links |
| Asana | Nutzerkonto, Projektmitgliedschaften, Gastzugänge |
| Apollo.io | Nutzerkonto, Kontaktexporte |
| Qonto | Mitgliedschaft, Kartenrechte, Freigabeberechtigungen |
| Canva | Team-Mitgliedschaft, Markendateien |
| GitHub | Collaborator-Rechte an diesem Repo, Deploy-Keys |
| Passwortmanager | Geteilte Tresore, Einzelzugänge |
| Sonstiges | Domain-Registrar, Steuerberater-Portal, DATEV/Lexware, Versicherungsportale |

Bei allen SaaS-Tools gilt: Konto **deaktivieren, nicht löschen**, damit Zuordnungen und Historie
erhalten bleiben.

---

## 6. Reihenfolge und Aufwand

| # | Schritt | Wer | Aufwand |
|---|---|---|---|
| 1 | Backup des gesamten Baums | IT | 2–4 h (Datenvolumen) |
| 2 | Öffentliche Links kappen, soweit möglich | IT | 1 h |
| 3 | Rechtliche Abstimmung (§ 51a, Löschverlangen, Kommunikation) | GF + Anwalt | – |
| 4 | Edition prüfen / Upgrade | Admin | 0,5 h |
| 5 | Geteilte Ablagen + Gruppen aufsetzen | Admin | 1 h |
| 6 | Migration Weg 2a (bzw. 2b) | Admin + Felix | 2–6 h |
| 7 | `kern@` übertragen und sperren | Admin | 1 h |
| 8 | Freigabe-Audit, Audit-Log, Zugriffstest | IT | 2 h |
| 9 | Restliche Systeme nach Checkliste | IT | 2–4 h |

Kritischer Pfad ist Schritt 3, nicht die Technik: Sobald der Entzug angekündigt ist, ist der
Zeitraum bis zur abgeschlossenen Migration der riskante. Backup steht deshalb an Position 1.
