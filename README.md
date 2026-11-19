# Kromeich & Partner – Automatisierung rund um Propstack

Kromeich & Partner ist Makler und Projektpartner für Logistik-Immobilien. Dieses Repo hält alles, was
automatisch in Propstack, Slack und Asana liest und schreibt.

| Ordner | Was | README |
|---|---|---|
| `src/` | Kontakt-Import aus E-Mail-Signaturen und Visitenkarten | [setup_guide.md](setup_guide.md) |
| `objekte_handler/` | Slack `#ver-objekte` → Propstack | [README](objekte_handler/README.md) |
| `newsletter_handler/` | Logistik-Deal Radar → Review-Aufgaben | [README](newsletter_handler/README.md) |
| `events_handler/` | Slack `#events` → Asana | [README](events_handler/README.md) |
| `personalkarussell_handler/` | Arbeitgeberwechsel → Propstack | [README](personalkarussell_handler/README.md) |
| `weekly_report/` | Wochenreport und Dashboard-Daten | [README](weekly_report/README.md) |
| `propstack-mcp/` | Propstack-Connector für Claude (Cloudflare Worker) | [README](propstack-mcp/README.md) |
| `scripts/` | Prüf- und Einmalskripte, lesen standardmäßig nur | Kopf der jeweiligen Datei |

Regeln, geprüfte Eigenheiten der Propstack-Schnittstelle und der Einstieg für neue Sitzungen: [CLAUDE.md](CLAUDE.md).
Stand der Prüfung vom 19.11.2026 und offene Entscheidungen: [docs/stresstest-2026-11-19.md](docs/stresstest-2026-11-19.md).

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -q
```
