# -*- coding: utf-8 -*-
"""Schuetzt die Skill-Pflege: Korrekturen sind idempotent, und im Repo liegen keine Keys.

Hintergrund: die Skill-Dateien unter ~/.claude/skills/synced/ werden beim Container-Start
zurueckgesetzt. Das Repo haelt deshalb nur die Korrekturen (scripts/skill_korrekturen.py),
die ein SessionStart-Hook nach jedem Reset neu eintraegt. Die Skill-Dateien selbst duerfen
NICHT hier liegen - sie enthalten zwei Propstack-API-Keys und einen Slack-Bot-Token im
Klartext.
"""
import importlib.util
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SKRIPT = REPO / "scripts/skill_korrekturen.py"


def _laden():
    spec = importlib.util.spec_from_file_location("skill_korrekturen", SKRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_skript_existiert_und_laedt():
    assert SKRIPT.is_file(), "scripts/skill_korrekturen.py fehlt"
    assert _laden().KORREKTUREN, "keine Korrekturen definiert"


def test_korrekturen_sind_wohlgeformt():
    for datei, alt, neu, name in _laden().KORREKTUREN:
        assert datei.endswith(".md"), name
        assert alt.strip() and neu.strip(), name
        assert alt != neu, "%s: alter und neuer Text sind identisch" % name
        assert alt not in neu or "Früher stand hier" in neu or "KORRIGIERT" in neu, (
            "%s: der alte Text steckt unmarkiert im neuen - dann greift die Korrektur "
            "beim zweiten Lauf erneut" % name)


def test_anwendung_ist_idempotent(tmp_path):
    """Zweimal anwenden darf nichts weiter aendern."""
    modul = _laden()
    fixture = tmp_path / "propstack-expose-workflow"
    (fixture / "references").mkdir(parents=True)
    # Kunst-Skill, der genau die Anker enthaelt
    inhalt = {}
    for datei, alt, _neu, _name in modul.KORREKTUREN:
        inhalt.setdefault(datei, []).append(alt)
    for datei, anker in inhalt.items():
        (fixture / datei).write_text(
            "Kopf\n\n" + "\n\n".join(anker) + "\n\nFuss\n", encoding="utf-8")

    def lauf():
        return subprocess.run([sys.executable, str(SKRIPT), "--ziel", str(fixture)],
                              capture_output=True, text=True)

    assert lauf().returncode == 0
    erste = {d: (fixture / d).read_text(encoding="utf-8") for d in inhalt}
    assert lauf().returncode == 0
    zweite = {d: (fixture / d).read_text(encoding="utf-8") for d in inhalt}
    assert erste == zweite, "zweiter Lauf hat den Text noch einmal veraendert"

    pruef = subprocess.run([sys.executable, str(SKRIPT), "--ziel", str(fixture), "--pruefen"],
                           capture_output=True, text=True)
    assert pruef.returncode == 0, pruef.stdout


def test_pruefen_meldet_fehlende_korrekturen(tmp_path):
    """--pruefen muss mit Code 1 abbrechen, wenn eine Korrektur fehlt."""
    modul = _laden()
    fixture = tmp_path / "propstack-expose-workflow"
    (fixture / "references").mkdir(parents=True)
    for datei, alt, _neu, _name in modul.KORREKTUREN:
        p = fixture / datei
        p.write_text((p.read_text(encoding="utf-8") if p.exists() else "") + alt + "\n",
                     encoding="utf-8")
    r = subprocess.run([sys.executable, str(SKRIPT), "--ziel", str(fixture), "--pruefen"],
                       capture_output=True, text=True)
    assert r.returncode == 1, r.stdout


def test_hook_ist_ausfuehrbar_und_registriert():
    hook = REPO / ".claude/hooks/session-start.sh"
    assert hook.is_file(), "SessionStart-Hook fehlt"
    assert hook.stat().st_mode & 0o111, "Hook ist nicht ausfuehrbar"
    import json
    einstellungen = json.loads((REPO / ".claude/settings.json").read_text(encoding="utf-8"))
    befehle = [h["command"]
               for eintrag in einstellungen["hooks"]["SessionStart"]
               for h in eintrag["hooks"]]
    assert any("session-start.sh" in b for b in befehle), befehle


SLACK = re.compile(r"xox[bap]-\d")
# Form der beiden Propstack-Keys: langer Token mit Bindestrich in der Mitte
PROPSTACK = re.compile(r"\b[A-Za-z0-9]{20,}-[A-Za-z0-9_]{20,}\b")


def test_keine_secrets_im_repo():
    """Die Skill-Dateien tragen Keys im Klartext - sie duerfen nicht ins Git geraten."""
    dateien = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                             text=True, check=True).stdout.split()
    treffer = []
    for name in dateien:
        p = REPO / name
        if not p.is_file() or p.suffix in {".png", ".jpg", ".pdf", ".xlsx"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if name.endswith("tests/test_skill_korrekturen.py"):
            continue
        for regex, was in ((SLACK, "Slack-Token"), (PROPSTACK, "API-Key-Form")):
            for m in regex.finditer(text):
                treffer.append("%s: %s (%s...)" % (name, was, m.group(0)[:8]))
    assert not treffer, "moegliche Secrets im Repo:\n  " + "\n  ".join(treffer)
