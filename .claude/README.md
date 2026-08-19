# Skill-Pflege für den Propstack-Workflow

## Das Problem

Der Skill `propstack-expose-workflow` liegt zur Laufzeit unter
`~/.claude/skills/synced/propstack-expose-workflow/`. Dieses Verzeichnis wird beim
Container-Start aus der Skill-Quelle **neu geschrieben**. Korrekturen, die dort von Hand
eingetragen werden, sind nach dem nächsten Start weg — am 19.08.2026 zweimal an einem Tag
passiert. In der Zwischenzeit stand die widerlegte Aussage „`mezzanineflache` direkt setzen
wirkungslos" wieder im Skill; genau die hatte am 13.08.2026 dazu geführt, dass auf
664 Einheiten eine Fläche in ein Euro-Feld geschrieben wurde.

## Die Lösung

Versioniert werden **nicht die Skill-Dateien, sondern die Korrekturen**:

| Datei | Zweck |
|---|---|
| `scripts/skill_korrekturen.py` | die Korrekturen als Suchen-Ersetzen-Paare, idempotent |
| `.claude/hooks/session-start.sh` | trägt sie bei jedem Sessionstart wieder ein |
| `.claude/settings.json` | registriert den Hook |
| `tests/test_skill_korrekturen.py` | prüft Idempotenz und dass keine Keys im Repo landen |
| `.claude/hooks/letzte-spiegelung.log` | Bericht des letzten Lauf (nicht versioniert) |

**Warum nicht die Skill-Dateien selbst?** Sie enthalten zwei Propstack-API-Keys und einen
Slack-Bot-Token im Klartext. Die gehören nicht in ein Git-Repository. `test_keine_secrets_im_repo`
schlägt fehl, falls doch einmal etwas in dieser Form hier landet.

## Bedienung

```bash
python3 scripts/skill_korrekturen.py            # Korrekturen anwenden
python3 scripts/skill_korrekturen.py --pruefen  # nur berichten (Exit 1 = etwas fehlt)
python3 scripts/skill_korrekturen.py --ziel /pfad/zum/skill
CLAUDE_PROJECT_DIR="$PWD" ./.claude/hooks/session-start.sh   # Hook manuell testen
```

Exit-Codes von `--pruefen`: `0` alles vorhanden · `1` mindestens eine Korrektur fehlt ·
`2` ein Anker ist nicht mehr auffindbar, die Skill-Quelle hat sich also geändert und die
Korrektur muss neu formuliert werden.

## Wo die Wahrheit steht

Maßgeblich für alle API-Funde ist die Notion-Seite
`32d7b7e5627b810db8bfdfcb9f477ee2` („Propstack API – Feld-Mapping"), Korrekturen 1–39.
Dieses Repo trägt nur die Teilmenge nach, die sonst bei jedem Reset verloren geht:

1. `mezzanineflache` ist das **Preisfeld** der Sektion Preise, nicht das Flächenfeld —
   und es wird nicht automatisch aus `mezzanineflache_verfugbar` befüllt.
2. Vor dem ersten Schreibzugriff die `unit` eines Custom Fields prüfen.
3. „Ebenerdige Tore" heißt in der API `anzahl_rampentore_2`; alles was keine Rampe ist,
   ist ein ebenerdiges Tor.
4. Zahlen, die nur für das Gesamtobjekt vorliegen: 1 Rampe pro 1.000 m², 1 ebenerdiges
   Tor pro Einheit — oder aus den Bildern auszählen.
5. UI-Beschriftungen weichen von `pretty_name` ab (`lagerflache` = „Hallenfläche").
6. Read-Back nur über `GET /v1/units?expand=1&per=100&property_ids[]=…`;
   `required_fields`/`optional_fields` taugen nicht, und ohne `per` liefert der Endpunkt
   trotz ID-Filter nur 20 Datensätze.
7. `q=` durchsucht `name`, nicht `title` — Existenzprüfung über PLZ **und** Straße.
