"""Die K&P-Schriften müssen auch ohne den kp-design-Skill gefunden werden."""

import pytest  # noqa: F401  (von den Fixtures unten nicht gebraucht, aber üblich)


# --- Schriften -------------------------------------------------------------
def test_kp_schriften_liegen_im_repository(monkeypatch):
    """Ohne die TTFs im Repo rendert der Actions-Lauf still in Helvetica.

    Gemessen am 13.08.2026 (Lauf 31700073360): die nach Asana geladene Datei
    war byte-identisch mit einem Lauf ohne Schriften – 16.299 statt 53.615
    Bytes. Inhaltlich richtig, aber nicht CI-treu; und genau diese Datei geht
    ins Kundengespräch. Der Test hält den Fallback-Pfad fest.
    """
    from comparables_handler import report_pdf

    # kp-design-Skill wegkonfigurieren: der Runner hat ihn auch nicht
    monkeypatch.setenv("KP_DESIGN_DIR", "/gibt-es-nicht")
    for datei in report_pdf._FONT_DATEIEN.values():
        assert report_pdf._finde_font(datei), f"{datei} fehlt in assets/fonts"
