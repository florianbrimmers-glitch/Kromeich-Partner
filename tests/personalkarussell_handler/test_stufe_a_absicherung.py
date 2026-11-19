"""Stufe A: Die neue Verknüpfung wird gegengelesen, bevor die alte gelöscht wird.

link_company wertet HTTP 422 als „besteht bereits“. Das stimmt bei Propstack oft, aber
nicht immer (propstack-mcp/src/tools/company-tools.ts). Fehlte die neue Verknüpfung,
stünde die Person nach dem Löschen der alten ganz ohne Firma da – Slack meldete „umgestellt“.
"""
from types import SimpleNamespace

import pytest

from personalkarussell_handler import main


def _plan():
    person = SimpleNamespace(id=1, name=lambda: "Tim Hamacher")
    ziel = SimpleNamespace(id=20, name="Goodman Germany GmbH")
    alt = SimpleNamespace(relationship_id=900, company_id=10, company_name="Swiss Life Asset Managers")
    return SimpleNamespace(
        person=SimpleNamespace(person=person), firma=SimpleNamespace(company=ziel),
        wechsel=SimpleNamespace(alte_firma="Swiss Life", neue_position=None), alte_links=[alt],
    )


def test_fehlt_die_neue_verknuepfung_wird_nichts_geloescht(monkeypatch):
    monkeypatch.setenv("NO_WRITE", "false")
    alt = SimpleNamespace(relationship_id=900, company_id=10, company_name="Swiss Life Asset Managers")
    geloescht, geaendert = [], []
    monkeypatch.setattr(main, "get_company_links", lambda person_id: [alt])   # neue Firma 20 fehlt
    monkeypatch.setattr(main, "link_company", lambda person_id, company_id: None)  # 422 still geschluckt
    monkeypatch.setattr(main, "unlink", geloescht.append)
    monkeypatch.setattr(main, "update_contact", lambda *a: geaendert.append(a))

    with pytest.raises(RuntimeError, match="nicht vorhanden"):
        main._stufe_a({"ts": "1763550000.000100", "text": "Tim Hamacher ist jetzt bei Goodman"}, _plan(), "https://x")
    assert geloescht == [] and geaendert == []
