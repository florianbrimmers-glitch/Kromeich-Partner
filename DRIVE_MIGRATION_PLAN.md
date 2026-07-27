# Drive-Migration: Unternehmensdaten aus dem Privatkonto lösen

**Stand:** 27.07.2026 · **Anlass:** Der Zugriff des Gesellschafters Felix Kern auf die
Unternehmensdaten im Google Drive soll beendet werden. Die Ordnerstruktur liegt auf seinem
privaten Google-Konto.

**Randbedingung:** Er wirkt nicht mit. Der Plan setzt durchgehend darauf, dass wir ohne seine
Beteiligung, seine Zustimmung und ohne Administratorzugriff auf sein Konto auskommen müssen.

---

## 1. Befund (per Drive-API erhoben)

### 1.1 Eigentümerschaft

Der Wurzelordner **„Kromeich & Partner"** (`1kriRg2pmh1H6J7XyfE_OtKQGs4M2HIH1`) gehört
`felix.kern2014@gmail.com`. Eigentümer der obersten Ebene:

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
`09. Knowledge Sharing`, `10. IT`. Inhaltlich betrifft das Gesellschafts- und
Anstellungsverträge, Kooperationsverträge, Finanzamtskorrespondenz, Ausgangsrechnungen 2025,
Mieter- und Investorenlisten, PPT-Master und Logos, HR-Unterlagen mit Ausweisdokumenten.

Nebenbefund: `Eigentümerliste_Updates.xlsx` gehört `kormeich@gmail.com` – ein **zweites**
privates Gmail-Konto. Ebenfalls ablösen.

### 1.2 Die Ablage ist per Link öffentlich

Der Wurzelordner trägt `{"role": "reader", "type": "anyone"}` – lesbar **ohne Google-Login**,
vererbt auf den gesamten Baum (bestätigt für `01. Allgemein`, `01. Gesellschaft`,
`03. Finanzen, Steuern`, `11. HR`). Betroffen sind damit auch Personalausweis-Scans, eine
Heiratsurkunde, Arbeitsverträge und die Steuerkorrespondenz.

Das ist unabhängig von Felix Kern zu behandeln und hat zwei unangenehme Seiten:

1. Wer je einen Link bekommen hat, liest bis heute mit (Art. 32 DSGVO, besondere Kategorien
   personenbezogener Daten in den HR-Unterlagen).
2. **Diese Freigabe ist gleichzeitig unser Zugangsweg.** Auf den Felix-eigenen Ordnern können
   wir sie nicht entfernen – und er kann sie jederzeit widerrufen. Mit dem Widerruf verlieren
   wir den Lesezugriff und damit die Möglichkeit, überhaupt noch zu migrieren.

Daraus folgt die zentrale Reihenfolge dieses Plans: **erst kopieren, dann kommunizieren.**

### 1.3 Warum der Zugriff nicht einfach entzogen werden kann

Dem **Eigentümer** einer Datei kann in Google Drive der Zugriff nicht genommen werden. Solange
`felix.kern2014@gmail.com` Eigentümer ist, kann er unsere Freigaben ändern, Inhalte löschen, den
öffentlichen Link weiter streuen – und mit seinem Konto verschwinden die Daten. Auf ein
privates Google-Konto hat unsere Workspace-Administration keinen Hebel: keine Datenübertragung,
keine Sperrung, keine Zwangsübertragung der Eigentümerschaft.

Ohne seine Mitwirkung bleibt genau ein Weg: **kopieren**. Eine Kopie gehört dem Konto, das sie
anlegt – bzw. direkt der geteilten Ablage, wenn dorthin kopiert wird.

### 1.4 Machbarkeit verifiziert

Am 27.07.2026 mit zwei Testkopien geprüft, weil der ganze Plan daran hängt: Hätte Felix
„Betrachter dürfen nicht kopieren" gesetzt, wäre auch der Kopierweg versperrt.

| Test | Quelle (Eigentümer felix.kern2014@gmail.com) | Ergebnis |
|---|---|---|
| Binärdatei | `Seriennummer Drucker.pdf` | Kopie angelegt, Eigentümer `florian.brimmers@kromeichpartner.de` |
| Google-Doc | `Fee Structure Asset Management` | Kopie angelegt, Eigentümer `florian.brimmers@kromeichpartner.de`, Inhalt vollständig |

**Der Kopierweg funktioniert.** Die beiden Testdateien liegen als
`MIGRATIONSTEST_1_bitte_loeschen.pdf` und `MIGRATIONSTEST_2_bitte_loeschen` in Florians „Meine
Ablage" und können gelöscht werden.

### 1.5 Gibt die Domain allein schon Zugriff?

Nein – aber die Frage trifft einen blinden Fleck, der vor Phase 1 geklärt sein muss.

Zugriff auf eine geteilte Ablage ist **explizite Mitgliedschaft**, Nutzer für Nutzer oder über
Gruppen. Ein Konto in `kromeichpartner.de` sieht eine Ablage nicht, nur weil es zur Domain
gehört. Am 27.07.2026 zusätzlich geprüft:

- Neu angelegte Dateien in der Domain tragen **keine** `domain`-Berechtigung, nur den
  Eigentümer. Die Voreinstellung „für alle in kromeichpartner.de freigeben" ist also aus.
- Eine Kopie erbt die Freigaben der Quelle **nicht** (Testkopie: nur Eigentümer). Die
  öffentliche Linkfreigabe aus 1.2 wandert damit nicht in die neue Ablage.

Vier Wege führen trotzdem hinein – in dieser Prioritätsreihenfolge:

1. **Administratorrollen.** Hat `kern@kromeichpartner.de` eine Super-Admin- oder delegierte
   Administratorrolle, ist die gesamte Migration wirkungslos: Ein Admin kann sich selbst zu
   jeder geteilten Ablage hinzufügen, per Datenexport oder Vault alles herausziehen, Passwörter
   zurücksetzen und Konten übernehmen. **Vor Phase 1 prüfen:** Admin-Konsole → Konto →
   Administratorrollen. Dabei mitklären, ob ein zweiter Super Admin existiert und wo
   Domainverwaltung und Abo-Inhaberschaft liegen – ein Super Admin kann die übrigen aussperren.
2. **Gruppen.** Wer in `team@` oder einer „alle Mitarbeiter"-Gruppe steht, erhält den Zugriff
   transitiv. Mitgliedschaften prüfen, bevor Gruppen die Ablagen freigeben.
3. **Domainweite Linkfreigabe.** Aktuell aus, aber pro Datei mit einem Klick setzbar
   („Jeder in kromeichpartner.de"). Auf Ablage-Ebene per Freigabebeschränkung verhindern.
4. **Bestehende Einzelfreigaben.** Alles, was ihm namentlich freigegeben wurde, funktioniert
   weiter, solange das Konto aktiv ist – siehe Phase 2b.

Das private Konto `felix.kern2014@gmail.com` ist gegenüber der neuen Ablage ein externes Konto
und durch „keine externen Mitglieder" (Phase 1.4) ausgeschlossen.

---

## 2. Zielbild: geteilte Ablage im bestehenden Workspace

Kein neues Werkzeug – nur, was in Google Workspace `kromeichpartner.de` schon enthalten ist:

- **Geteilte Ablage** (Shared Drive): Eigentümer ist die Organisation, nicht eine Person.
  Konto weg ≠ Daten weg. Das ist die eigentliche Reparatur des Grundfehlers.
- **Google-Gruppen** (`gf@`, `team@`, `finanzen@`, `hr@`) als Zugriffsschicht – Ein- und
  Austritt ist danach eine Gruppenmitgliedschaft, keine Freigabe-Archäologie.
- **Admin-Konsole** für das interne Konto `kern@kromeichpartner.de`.
- **Audit-Log** (Drive-Protokoll) für die Nachkontrolle.

**Vorab prüfen:** Geteilte Ablagen brauchen mindestens *Business Standard*. Auf *Business
Starter* ist ein Upgrade Voraussetzung – bringt zugleich Pool-Speicher, den die Kopien belegen
werden (Binärdateien zählen auf das Kontingent, Google-Docs nicht; die Meeting-Recordings mit
~1 GB je Datei sind der Treiber).

Zielstruktur – bewusst zweigeteilt, das ist die Lehre aus Abschnitt 1.2:

```
Geteilte Ablage „Kromeich & Partner"      → Gruppe team@
├── 01. Allgemein  (ohne HR/Finanzen)
├── 02. Investment
├── 03. Leasing
├── 04. Asset Management
├── 05. Consulting
├── 06. Project Management
├── 07. Logistik
└── 08. Research

Geteilte Ablage „KP Vertraulich"          → nur gf@
├── 01. Gesellschaft
├── 03. Finanzen, Steuern
└── 11. HR
```

---

## 3. Umsetzung

### Phase 0 — Vorbereitung, ohne Außenwirkung

1. **Nichts ankündigen.** Solange er Eigentümer ist und wir über seinen öffentlichen Link
   lesen, hat er die Oberhand. Jede Vorwarnung kann den Zugang kosten.
2. **Bestandsaufnahme sichern.** Datei-Liste mit Eigentümern als Nachweis des Ist-Zustands
   exportieren (Basis: die hier erhobenen API-Daten). Dient später als Belegkette.
3. **Öffentliche Freigaben dokumentieren**, wo wir sie nicht selbst schließen können. Das ist
   die Grundlage für das Lösch- und Schließverlangen in Abschnitt 5.
4. **Rechtliche Abstimmung anstoßen** (parallel, blockiert Phase 1–2 nicht).

### Phase 1 — Geteilte Ablagen aufsetzen (Admin, ~1 h)

0. **Administratorrollen prüfen (siehe 1.5).** Solange `kern@` Administrator sein könnte, ist
   jede weitere Maßnahme wirkungslos. Rolle entziehen, bevor die Ablagen entstehen.
1. Workspace-Edition prüfen, ggf. Upgrade.
2. Beide geteilten Ablagen anlegen, Zielordner-IDs notieren.
3. Google-Gruppen anlegen/befüllen und als Mitglieder eintragen.
4. Ablagen härten: Freigabe außerhalb der Organisation **aus**, bei „KP Vertraulich"
   Download/Kopieren für Betrachter **aus**, Strukturänderungen nur für Manager.
5. Admin-Konsole → Apps → Google Workspace → Drive und Docs → *Migrationseinstellungen*:
   „Nutzer dürfen Dateien in geteilte Ablagen verschieben" **ein** (nötig für den
   Verschiebe-Anteil in Phase 2).
6. Ausführendes Konto braucht mindestens *Inhaltsmanager* in der Zielablage.

### Phase 2 — Migration (Werkzeug: `scripts/drive_migrate_copy.py`)

Für die Migration liegt ein Skript im Repo, das auf denselben OAuth-Secrets läuft wie die
Kontakt-Pipeline (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`). Der
Token braucht zusätzlich den Scope `https://www.googleapis.com/auth/drive` – der vorhandene
Gmail-Token reicht nicht, er ist auf `gmail.readonly` beschränkt.

Es behandelt jedes Objekt nach Eigentümer, und das ist der Kern der Sache:

| Objekt | Aktion | Warum |
|---|---|---|
| Ordner | im Ziel neu angelegt | Ordner sind nicht kopierbar |
| Datei des ausführenden Kontos | **verschoben** | Historie, Kommentare, Zeitstempel bleiben erhalten |
| fremde Datei | **kopiert** | einziger Weg, das Eigentum zu lösen |
| Verknüpfung | im zweiten Durchlauf neu angelegt | Ziel-IDs existieren erst nach dem Hauptlauf |

**Damit ist der verlustbehaftete Anteil so klein wie möglich.** Alles, was uns schon gehört –
und das ist ein erheblicher Teil der jüngeren Ablage: `07. Logistik`, `08. Research`,
`08. Events`, `15. Dienstreisen`, sämtliche Meeting-Notizen und Recordings – wandert
verlustfrei per Verschieben. Kopiert wird nur, was den Privatkonten gehört.

Weil „eigene Datei" vom ausführenden Konto abhängt, lohnt der Lauf **pro Mitarbeiterkonto**.
Die fünf Refresh-Tokens aus der Kontakt-Pipeline (Florian, Denise, Marek, Lena, Oguzhan) sind
dafür schon vorhanden. Reihenfolge:

```bash
# 1. Trockenlauf – zeigt Aktionen und Datenmenge, ändert nichts
python3 scripts/drive_migrate_copy.py --source <ALT_WURZEL_ID> \
    --target <ZIEL_ORDNER_ID> --manifest migration.csv --dry-run

# 2. Ein Durchlauf je Mitarbeiterkonto: verschiebt dessen eigene Dateien verlustfrei.
#    Dasselbe Manifest für alle Läufe – bereits migrierte Objekte werden übersprungen.
GOOGLE_REFRESH_TOKEN=$TOKEN_FLORIAN python3 scripts/drive_migrate_copy.py \
    --source <ALT_WURZEL_ID> --target <ZIEL_ORDNER_ID> --manifest migration.csv
GOOGLE_REFRESH_TOKEN=$TOKEN_DENISE  python3 scripts/drive_migrate_copy.py ...   # usw.

# 3. Abschlusslauf mit einem beliebigen Konto: kopiert alles Übrige (Privatkonten).

# 4. Nachkontrolle – prüft jede Manifest-Zeile im Ziel, md5 bei Binärdateien
python3 scripts/drive_migrate_copy.py --manifest migration.csv --verify
```

Eigenschaften, die bei einem Lauf über mehrere tausend Dateien den Unterschied machen:

- **Wiederaufsetzbar.** Das Manifest wird zeilenweise geschrieben; nach Abbruch macht derselbe
  Aufruf dort weiter, wo er stand, ohne Dubletten.
- **Backoff mit Augenmaß.** Drive quittiert Ratenbegrenzung *und* fehlende Rechte mit HTTP 403.
  Nur die Ratenbegrenzung wird wiederholt – sonst kostet jede gesperrte Datei Minuten Leerlauf.
- **Keine stillen Verluste.** Nicht kopierbare Objekte landen als `fehler` im Manifest und
  lassen den Lauf mit Exit-Code 1 enden. Was nicht mitkommt, steht namentlich da.
- **Herkunftsnachweis.** Jede Kopie trägt Original-ID, -Eigentümer, -Zeitstempel und -Pfad in
  der Beschreibung; dieselben Daten stehen im Manifest. Das ist der Teilersatz für die
  Metadaten, die beim Kopieren verloren gehen – bei Vertrags- und Steuerunterlagen der
  nachweisrelevante Punkt.
- **alt→neu-ID-Mapping.** Das Manifest ist die Grundlage, um Links in Asana, Notion, Propstack
  und Mails nachzuziehen.

Getestet mit nachgebautem Drive-Dienst: `python3 -m pytest tests/test_drive_migrate_copy.py`
(12 Tests: Kopieren, Verschieben, Rückfall auf Kopieren ohne Schreibrecht, gesperrte Dateien,
Verknüpfungen, Wiederanlauf, Trockenlauf, 403-Unterscheidung, Nachkontrolle).

### Phase 2b — Das interne Konto `kern@kromeichpartner.de`

Hier sind wir Administrator, das ist unabhängig von seiner Mitwirkung:

1. Admin-Konsole → Nutzer → **Daten übertragen** (Drive + Docs) auf ein Zielkonto; die Dateien
   gehören danach uns und werden vom Migrationslauf **verschoben**, nicht kopiert.
2. Alle Sitzungen beenden, App-Passwörter und OAuth-Token widerrufen.
3. Konto **sperren, nicht löschen** (Beweis- und Aufbewahrungslage), ggf. Vault-Aufbewahrung.
4. Mailweiterleitung/Delegierung für laufende Vorgänge einrichten.

### Phase 3 — Umschalten und Nachkontrolle

1. `--verify` läuft ohne Abweichung durch. Erst dann weiter.
2. **Freigabe-Audit** über die neue Ablage: keine „Jeder mit dem Link"-Freigabe, keine externen
   Einzelfreigaben. Beim Kopieren werden Freigaben der Quelldateien nicht mitgenommen – bei
   verschobenen Dateien schon. Diese aktiv entfernen.
3. **Team umschalten:** neue Ablage ist ab Datum X die einzige Quelle. Verknüpfung „Kromeich &
   Partner" (`1wgl4XZeY-4q8RoRQ0K18muZfkXx5f5gh`) aus den „Meine Ablage"-Ordnern entfernen,
   damit niemand aus Gewohnheit in der Altstruktur weiterarbeitet.
4. **Links nachziehen** anhand des Manifests (Asana, Notion, Propstack, Mailvorlagen).
   Die Automatisierungen in diesem Repo enthalten keine fest verdrahteten Drive-IDs (geprüft),
   sind also nicht betroffen.
5. **Audit-Log** (Admin-Konsole → Berichte → Drive) auf Massendownloads prüfen und das Ergebnis
   dokumentieren.
6. Erst jetzt: Kommunikation und das Schreiben aus Abschnitt 5.

---

## 4. Was der Kopierweg kostet – und was davon bleibt

Ehrlich benannt, damit die Entscheidung bewusst fällt:

| Verlust | Umfang | Gegenmaßnahme |
|---|---|---|
| Versionshistorie, Kommentare | nur bei kopierten Dateien (Privatkonten) | Original-Metadaten in Beschreibung + Manifest |
| Erstellungs-/Änderungsdatum | dito | dito |
| Alte Links zeigen auf seine Originale | alle Verweise auf kopierte Dateien | ID-Mapping im Manifest, Phase 3.4 |
| Doppelte Bearbeitung während der Umstellung | Google-Docs, an denen aktiv gearbeitet wird | kurze Schreibpause, Umschalttermin kommunizieren |
| Speicherverbrauch | Binärkopien belegen das Kontingent doppelt | Edition/Pool prüfen (Phase 1.1) |

Was **nicht** verloren geht: alles, was Konten unserer Domain gehört – das wird verschoben.

---

## 5. Was Technik nicht löst

Nach Phase 3 hat er keinen Zugriff auf unsere Ablage. Aber: **die Originale bleiben sein
Eigentum, und die öffentliche Freigabe darauf können nur er oder Google schließen.** Wir
kopieren uns aus der Abhängigkeit heraus – nicht aus seinem Datenbesitz. Der Rest ist
organisatorisch und rechtlich:

- **Schriftliche Aufforderung**, (a) alle Unternehmensdaten aus privaten Konten und Endgeräten
  zu löschen und (b) die öffentliche Linkfreigabe auf dem Wurzelordner **unverzüglich** zu
  schließen. Mit Frist und Löschbestätigung. Punkt (b) ist der dringlichere – dort liegen
  Ausweisdokumente und Arbeitsverträge unserer Mitarbeiter offen.
- **Dokumentierter Befund als Grundlage:** Der Ist-Zustand aus Phase 0.3 belegt die Exposition.
  Falls die Freigabe nicht geschlossen wird, ist zu prüfen, ob eine Meldung nach Art. 33 DSGVO
  erforderlich ist – Verantwortlicher für diese Daten ist die Kromeich & Partner, nicht er.
- **Vertragliche Hebel** prüfen: Gesellschaftsvertrag, Geschäftsführeranstellungsvertrag, NDA –
  Herausgabe- und Löschpflichten, Vertragsstrafen.
- **Zwei Dinge auseinanderhalten:** Der operative Datenzugriff darf entzogen werden. Als
  Gesellschafter hat er unabhängig davon ein Auskunfts- und Einsichtsrecht nach § 51a GmbHG.
  Beides ist vereinbar – Auskunft erteilt die Geschäftsführung anlassbezogen, nicht per
  Dauerzugriff auf die Ablage. Diesen Punkt vor der Kommunikation mit der Rechtsberatung
  abstimmen; er ist der wahrscheinlichste Angriffspunkt gegen das Vorgehen.

---

## 6. Weitere Systeme

Gleiche Frage, anderes Tool – jeweils: eigenes Konto, private Adresse, Gastzugang, API-Token?

| System | Zu prüfen |
|---|---|
| Google Workspace | Konto `kern@`, Gruppen, Kalenderfreigaben, Weiterleitungen, geteilte Ablagen |
| Slack | Mitgliedschaft, Gastkonten, private Kanäle, Exporte |
| Propstack (CRM) | Nutzerkonto, API-Keys, Objekt- und Eigentümerdaten |
| Notion | Workspace-Mitgliedschaft, private Seiten, geteilte Links |
| Asana | Nutzerkonto, Projektmitgliedschaften, Gastzugänge |
| Apollo.io | Nutzerkonto, Kontaktexporte |
| Qonto | Mitgliedschaft, Kartenrechte, Freigabeberechtigungen |
| Canva | Team-Mitgliedschaft, Markendateien |
| GitHub | Collaborator-Rechte an diesem Repo, Deploy-Keys |
| Passwortmanager | Geteilte Tresore, Einzelzugänge |
| Sonstiges | Domain-Registrar, Steuerberater-Portal, DATEV/Lexware, Versicherungsportale |

Konten **deaktivieren, nicht löschen** – Zuordnungen und Historie bleiben so erhalten.

---

## 7. Reihenfolge und Aufwand

| # | Schritt | Wer | Aufwand |
|---|---|---|---|
| 0 | **Administratorrollen prüfen** (1.5) – entscheidet über alles Weitere | Admin | 0,5 h |
| 1 | Bestandsaufnahme und Exposition dokumentieren | IT | 1 h |
| 2 | Rechtliche Abstimmung anstoßen (§ 51a, Löschverlangen) | GF + Anwalt | parallel |
| 3 | Edition prüfen / Upgrade | Admin | 0,5 h |
| 4 | Geteilte Ablagen + Gruppen aufsetzen | Admin | 1 h |
| 5 | Drive-Scope für den OAuth-Token ergänzen | IT | 0,5 h |
| 6 | Trockenlauf, Datenmenge und Fehlerliste bewerten | IT | 1 h |
| 7 | Migrationsläufe je Konto + Abschlusslauf | IT | 2–6 h (Datenmenge) |
| 8 | `kern@` übertragen und sperren | Admin | 1 h |
| 9 | `--verify`, Freigabe-Audit, Audit-Log | IT | 2 h |
| 10 | Umschalten, Links nachziehen | Team | 2 h |
| 11 | Kommunikation und Schreiben (Löschung + Linkfreigabe) | GF | – |
| 12 | Restliche Systeme nach Checkliste | IT | 2–4 h |

Kritisch ist nicht die Technik, sondern die Reihenfolge: Schritt 11 kommt **nach** Schritt 9.
Wer vorher redet, verliert womöglich den Lesezugriff und damit die Migration.
