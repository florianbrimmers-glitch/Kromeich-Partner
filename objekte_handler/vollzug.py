from __future__ import annotations

import re

# Slack-Formatierung (*fett*, _kursiv_, ~durch~, `code`, > Zitat) für den Vergleich entfernen
_FORMAT = re.compile(r"[*_~`>]")
_CLAUDE_SIGNATUR = re.compile(r"gesendet\s+mit\s+claude", re.IGNORECASE)
_ANGELEGT = re.compile(r"^(neues\s+objekt\s+angelegt|neu\s+angelegt|objekt\s+angelegt)\b", re.IGNORECASE)
# Steht so etwas in einer „angelegt“-Meldung, ist sie (auch) ein Auftrag oder eine Frage
_BITTE = re.compile(
    r"\?|\bbitte\b|\bmuss\b|\bm(?:ü|ue)ss(?:en|te|ten)\b|\bsoll(?:en|te|ten)?\b|\bfehl(?:t|en)\b"
    r"|\bnoch\s+(?:zu|nicht)\b|\bvermietet\b|\bwerden\b",
    re.IGNORECASE,
)


def vollzugsmeldung(text: str | None) -> str | None:
    """Ist die Nachricht eine Vollzugsmeldung – also ein Bericht über etwas, das in
    Propstack schon erledigt ist – und kein Auftrag? Rückgabe: der Grund, sonst None.

    Stand 19.11.2026 (nur gelesen): 47 der 82 offenen Aufgaben dieses Handlers waren
    Antworten auf solche Meldungen. 25 von 30 „Objekt fehlt in Propstack: bitte
    anlegen“ betrafen Objekte, die gerade angelegt worden waren.

    Zwei Formen, beide an echten Nachrichten des Kanals geprüft:
    - Berichte aus Claude-Sitzungen („Update: …“, „… – Abgleich mit Propstack“). Sie
      tragen die Signatur „Gesendet mit Claude“ des Slack-Connectors; 27 von 27 so
      signierten Nachrichten waren Berichte.
    - „neues Objekt angelegt …“ – so melden Kollegen eine fertige Anlage (26 Nachrichten
      begannen so; 25 davon erkennt die Regel).
      Steht darin eine Bitte, eine Frage oder ein „vermietet“ („Neu angelegt werden muss
      bitte …“, „Objekt angelegt? …“, „… Halle 1 ist aber schon vermietet“), ist es
      keine reine Vollzugsmeldung – dann entscheidet wie bisher die Klassifikation.

    Grenze: Ein echter Auftrag, der über Claude gepostet wird und die Signatur trägt,
    wird nicht verarbeitet. Wer den Handler ansprechen will, schreibt ohne Signatur.
    """
    klar = _FORMAT.sub("", text or "").strip()
    if not klar:
        return None
    if _CLAUDE_SIGNATUR.search(klar):
        return "Bericht einer Claude-Sitzung (Signatur „Gesendet mit Claude“) – kein Auftrag"
    if _ANGELEGT.match(klar) and not _BITTE.search(klar):
        return "Vollzugsmeldung „neues Objekt angelegt“ – kein Auftrag"
    return None
