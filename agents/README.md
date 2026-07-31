# Propstack-Objektpflege als Managed Agent

Die Definitionen hier gehören zur **Steuerungsebene**: Agent und Environment sind
statische, versionierte Ressourcen und werden aus diesem Repo per `ant`-CLI
ausgerollt. Sessions dagegen sind dynamisch und entstehen pro Lauf — entweder
durch ein geplantes Deployment oder von Hand zum Testen.

| Datei | Was |
|---|---|
| `propstack.agent.yaml` | Modell, System-Prompt, Tools, später Skill-Verweis |
| `propstack.environment.yaml` | Container mit eng gesetztem Egress |

## Reihenfolge

### 1. Environment und Agent anlegen

```sh
ENV_ID=$(ant beta:environments create < agents/propstack.environment.yaml --transform id -r)
AGENT_ID=$(ant beta:agents create   < agents/propstack.agent.yaml       --transform id -r)
```

Beide IDs festhalten (Secret, Config oder `.env` — sie sind keine Geheimnisse,
aber jeder Lauf braucht sie). **Nie `create` pro Lauf aufrufen** — das sammelt
verwaiste Agenten an und hebelt die Versionierung aus. Änderungen laufen über
`update`, das eine neue unveränderliche Version erzeugt.

### 2. Vault mit den Zugangsdaten

Der Container sieht nur Platzhalter; das echte Secret wird erst beim Ausgang
eingesetzt und ist damit auch bei Prompt-Injection nicht auslesbar.

```sh
VAULT_ID=$(ant beta:vaults create --name propstack-objekte --transform id -r)
```

Dann pro Zugang ein Credential vom Typ `environment_variable`:

| `secret_name` | `allowed_hosts` | `injection_location` |
|---|---|---|
| `PROPSTACK_API_KEY` | `api.propstack.de` | `{header: true}` |
| `PROPSTACK_KEY_TASKS` | `api.propstack.de` | `{header: true}` |
| `APIFY_TOKEN` | `api.apify.com` | `{header: true}` |
| `SLACK_BOT_TOKEN` | `slack.com`, `files.slack.com` | `{header: true}` |
| `GOOGLE_CLIENT_SECRET` | `oauth2.googleapis.com` | **`{body: true}`** |
| `GOOGLE_REFRESH_TOKEN_2` | `oauth2.googleapis.com` | **`{body: true}`** |

> ⚠️ **Der Fallstrick, der einen Abend kostet.** Über die Console angelegte
> Credentials sind **header-only**. Der Google-Token-Refresh schickt
> `client_secret` und `refresh_token` aber formularkodiert **im Body** — mit der
> Voreinstellung geht der Platzhalter wörtlich an Google und du bekommst einen
> Auth-Fehler, der wie ein falsches Secret aussieht. Für die beiden Google-Werte
> also ausdrücklich Body-Injection setzen (per API reicht
> `"injection_location": {"body": true}`, in der Console das entsprechende
> Häkchen).

> ⚠️ **Zwei Netzwerkschichten, beide nötig.** `allowed_hosts` am Credential
> steuert, *wofür* ein Secret eingesetzt wird. Die `allowed_hosts` im Environment
> steuern, *wohin* der Container überhaupt darf. Ein Host muss in **beiden**
> Listen stehen, sonst schlägt der Aufruf fehl.

Die Werte selbst liegen bereits als GitHub-Secrets — sie gehören nicht in dieses
Repo und nicht in einen Chat.

### 3. Wissensdatenbank als Skill

`propstack-expose-workflow` als Zip hochladen und die zurückgegebene `skill_id`
in `propstack.agent.yaml` eintragen (der Block ist dort auskommentiert
vorbereitet), dann `ant beta:agents update`. Damit lädt der Agent die
Feldwahrheiten bei Bedarf, statt sie in jedem System-Prompt mitzuschleppen.

### 4. Von Hand testen, bevor irgendein Cron läuft

```sh
SID=$(ant beta:sessions create --agent "$AGENT_ID" --environment-id "$ENV_ID" \
        --title "Test: Flächenupdate Mileway" --transform id -r)
echo "https://platform.claude.com/workspaces/default/sessions/$SID"
```

Den Link öffnen — dort laufen Tool-Aufrufe und Nachrichten live mit. Dann den
Testfall schicken:

```sh
ant beta:sessions:events send --session-id "$SID" <<'YAML'
events:
  - type: user.message
    content:
      - type: text
        text: |
          Flächenupdate Mileway 07/26. Gleiche den Bestand ab, aber SCHREIBE NICHTS —
          liefere nur ein Diff pro Einheit und deine Einordnung.
YAML
```

**Repo mounten** nicht vergessen: beim `sessions create` eine
`github_repository`-Resource mit `authorization_token` angeben, sonst fehlen die
Helfer aus `objekte_handler/`.

Gute erste Testfälle sind die zwei Fälle vom 31.07.2026, bei denen der alte Job
danebenlag:

- **Aconlog Viersen** — der Eigentümer besitzt 7 Einheiten an 4 Adressen. Bei
  „ca. 9.150 m²" darf nur `5050187` übrig bleiben. Wenn der Agent auf
  `2778052 Mackenstein 48` zeigt, greift die Eigentümer-Achse nicht.
- **Flächenupdate Mileway** — 23 Einheiten in 3 Projekten. Erwartet ist ein
  Portfolio-Abgleich, nicht „keine eindeutige Zuordnung".

#### Die Neuanlage getrennt testen

Der Agent legt Projekte und Einheiten selbstständig an. Das ist der Schreibpfad
mit den dauerhaftesten Folgen — `DELETE` gibt bei Einheiten 401, jede Fehlanlage
muss von Hand in der UI weg. Deshalb in dieser Reihenfolge:

1. **Erkennungstest.** Ein Objekt, das es **gibt**, als angebliche Neumeldung
   schicken. Der Agent muss es finden und darf **nichts** anlegen. Legt er trotzdem
   an, greift die Dublettenprüfung nicht — dann nicht scharf schalten.
2. **Trockenlauf.** Ein Objekt, das es wirklich nicht gibt, mit dem Zusatz
   `SCHREIBE NICHTS, zeige nur den geplanten Datensatz samt Pflichtfeldern`.
   Feldbelegung, Projekt-vs-Einheit-Entscheidung und Status prüfen.
3. **Ein einziger echter Fall.** Danach den Datensatz in der UI ansehen: Titel,
   `unit_id`, Betreuer, Status, `free_from`, Provision, Flächen, Koordinaten,
   Eigentümer-Verknüpfung. Und die JSONL aus `/mnt/session/outputs/` durchgehen.
4. **Wiederanlauf.** Dieselbe Meldung ein zweites Mal schicken. Es darf **keine**
   zweite Anlage entstehen — der `bemerkung`-Eintrag mit Quelle ist der Schutz.

Die Obergrenze steht bei **fünf neuen Projekten pro Lauf** (im System-Prompt,
Abschnitt „Obergrenze pro Lauf"). Das ist eine gesetzte Annahme, kein Naturgesetz
— dreh sie hoch, wenn die ersten Wochen sauber laufen.

Vor dem Scharfschalten `effort` einmal über echte Newsletter vergleichen
(`medium` / `high` / `xhigh`) — bei Opus 5 sind die niedrigen Stufen
ungewöhnlich stark, und ein übernommener Wert ist selten der richtige.

### 5. Deployment — und zwar parallel, nicht als Ersatz

```sh
ant beta:deployments create --transform id -r <<YAML
name: Propstack Objektpflege nachts
agent: $AGENT_ID
environment_id: $ENV_ID
initial_events:
  - type: user.message
    content:
      - type: text
        text: Prüfe die Eigentümer-Mails und Newsletter der letzten 24 Stunden.
schedule:
  type: cron
  expression: "0 4 * * *"
  timezone: Europe/Berlin
YAML
```

Die Antwort enthält `schedule.upcoming_runs_at` — daran prüfen, ob der
Cron-Ausdruck gemeint ist wie gedacht. **Die Ausführung wird gejittert**
(bis 15 % des Intervalls, maximal 9 Minuten), es darf also keine
Anschluss-Deadline daran hängen. Bei Sommerzeitwechsel entfallen Zeiten zwischen
1 und 3 Uhr oder feuern doppelt — 4 Uhr ist deshalb bewusst gewählt.

**Der GitHub-Job läuft weiter.** Erst wenn die Trefferquote über einige Wochen
steht, wird er abgeschaltet. Zum Testen ohne Warten auf die erste Feuerung:
`ant beta:deployments run --deployment-id <id>` — geht auch, während das
Deployment pausiert ist.

`pause` ist reversibel, `archive` nicht. Fehlgeschlagene Läufe stehen mit
Fehlertyp in `ant beta:deployment_runs list --deployment-id <id> --has-error true`.

## Was hier bewusst nicht drinsteht

**Keine Custom Tools.** Ein Custom Tool bedeutet: der Agent ruft es, die Session
geht auf `idle` und wartet, dass eine Client-Anwendung das Ergebnis zurückgibt.
Nachts hört niemand zu — die Session bliebe stehen. Alles läuft deshalb über
`bash` gegen die Repo-Skripte, mit Vault-Credentials.

**Keine Subagenten in Version 1.** Erst wenn Meldungen regelmäßig mehrere
Standorte gleichzeitig bringen. Opus 5 delegiert von sich aus eher zu viel,
deshalb steht die Obergrenze schon im System-Prompt.

**Managed Agents gibt es nur auf der Claude-API** — nicht über Bedrock, Vertex
oder Foundry. Falls einmal eine Cloud-Vorgabe im Raum steht, ist das der Punkt,
an dem sie kollidiert.
