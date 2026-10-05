"""Wächter für Fallen im HTML, die kein Python-Test und kein API-Test sieht."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).parents[2] / "eigentuemer" / "static"
SEITEN = ["index.html", "status.html"]

# Werte, die im Logistikalltag vorkommen und das Formular passieren müssen
REALISTISCH = {"flaeche_qm": 5400, "hallenhoehe_m": 8.75, "miete_eur_qm": 5.25}


def felder(html: str) -> list[dict[str, str]]:
    gefunden = []
    for treffer in re.finditer(r"<input\b[^>]*>", html):
        tag = treffer.group(0)
        if 'type="number"' not in tag:
            continue
        gefunden.append({
            name: wert for name, wert in re.findall(r'(\w+)="([^"]*)"', tag)
        })
    return gefunden


@pytest.mark.parametrize("seite", SEITEN)
def test_zahlenfelder_akzeptieren_realistische_werte(seite):
    """step="10" bei min="1" heißt: gültig sind nur 1, 11, 21 … – eine Halle
    mit 5.400 m² wäre eine ungültige Eingabe, und der Browser blockiert das
    Absenden ohne sichtbare Meldung."""
    for feld in felder((STATIC / seite).read_text()):
        name = feld.get("name", "")
        if name not in REALISTISCH:
            continue
        schritt = feld.get("step", "any")
        if schritt == "any":
            continue
        minimum = float(feld.get("min", 0))
        rest = (REALISTISCH[name] - minimum) % float(schritt)
        assert abs(rest) < 1e-9, (
            f"{seite}: {name} mit step={schritt} und min={minimum} lehnt "
            f"{REALISTISCH[name]} ab"
        )


def test_bearbeiten_formular_prueft_ueber_javascript():
    """Ohne novalidate blockiert der Browser das Absenden still; unsere eigenen
    Meldungen erscheinen dann nie."""
    html = (STATIC / "status.html").read_text()
    treffer = re.search(r'<form id="bearbeiten"[^>]*>', html)
    assert treffer, "Bearbeiten-Formular nicht gefunden"
    assert "novalidate" in treffer.group(0)


@pytest.mark.parametrize("seite", SEITEN)
def test_pflichtfelder_sind_nicht_dauerhaft_versteckt(seite):
    """Ein required-Feld in einem versteckten Block macht das Formular
    unabsendbar, ohne dass jemand sieht, warum."""
    html = (STATIC / seite).read_text()
    for block in re.findall(r"<label[^>]*\bhidden\b[^>]*>.*?</label>", html, re.S):
        assert "required" not in block, f"{seite}: verstecktes Pflichtfeld"


def test_hidden_attribut_wird_global_durchgesetzt():
    """Jede Klassenregel mit display überstimmt sonst die Browser-Regel für
    [hidden] – versteckte Knöpfe und Felder blieben sichtbar. Genau dieser
    Fehler ist im Hallentinder schon einmal aufgetreten."""
    css = (STATIC / "styles.css").read_text()
    assert re.search(r"\[hidden\]\s*\{[^}]*display:\s*none\s*!important", css), \
        "Regel [hidden] { display: none !important } fehlt"
