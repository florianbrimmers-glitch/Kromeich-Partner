"""link_company: Die Zeile der Person heißt "Mitarbeiter" (erscheint an der Firma).
Mit "Firma" stand am Kontakt die Firma als "Mitarbeiter" (Oberfläche geprüft 13.11.2026)."""
from personalkarussell_handler import propstack


class _Resp:
    status_code = 201
    text = ""


def test_link_company_labels_person_row_as_mitarbeiter(monkeypatch):
    posts = []
    monkeypatch.setattr(propstack.config, "no_write", lambda: False)
    monkeypatch.setattr(propstack.config, "propstack_key_v2", lambda: "v2")
    monkeypatch.setattr(propstack.httpx, "post",
                        lambda url, json=None, **kw: posts.append((url, json)) or _Resp())
    propstack.link_company(111, 222)
    url, body = posts[0]
    assert url.endswith("/v2/relationships")
    assert body == {"internal_name": "associate", "name": "Mitarbeiter",
                    "client_id": 111, "related_client_id": 222}
