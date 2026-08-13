# K&P-Schriften für die PDF-Erzeugung

Diese TTFs liegen **im Repository**, weil die PDFs in GitHub Actions entstehen und
dort der `kp-design`-Skill nicht existiert.

Gemessen am 13.08.2026 (Lauf 31700073360): ohne diese Dateien fiel das
Comparables-PDF auf Helvetica/Times zurück – die in Asana hochgeladene Datei war
byte-identisch mit einem lokalen Lauf ohne Schriften (16.299 statt 53.615 Bytes).
Das Dokument war also vollständig und richtig, aber nicht CI-treu, und genau
diese Datei geht ins Kundengespräch.

Gesucht wird in dieser Reihenfolge (siehe `comparables_handler/report_pdf.py`):

1. `KP_DESIGN_DIR/assets/fonts` – der `kp-design`-Skill, wenn vorhanden.
   Er bleibt die **Single Source of Truth** für das Corporate Design.
2. dieses Verzeichnis – der Fallback für Actions.
3. reportlab-Standardschriften – nur noch Notnagel, mit Warnung im Log.

Wird das Design im `kp-design`-Skill geändert, gehören die Dateien hier
nachgezogen.

## Lizenz

Beide Familien stehen unter der **SIL Open Font License 1.1**, die Weitergabe
erlaubt. Die Lizenztexte liegen daneben und müssen mitgeführt werden:

| Datei | Familie | Lizenz |
|---|---|---|
| `Jomolhari-Regular.ttf` | Jomolhari (Headlines) | `Jomolhari-OFL.txt` |
| `Poppins-Regular.ttf`, `Poppins-Bold.ttf` | Poppins (Fließtext) | `Poppins-OFL.txt` |

Nur die drei tatsächlich benutzten Schnitte liegen hier; Poppins-Medium und
-SemiBold verwendet der Report nicht.
