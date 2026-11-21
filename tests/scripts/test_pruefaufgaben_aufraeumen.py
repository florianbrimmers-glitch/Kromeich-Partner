"""Auswahl der schließbaren Aufgaben in scripts/pruefaufgaben_aufraeumen.py (ohne Netz).

Die Zeilen sind so aufgebaut, wie GET /v1/activities und GET /v1/units?expand=1 sie am
19.11.2026 geliefert haben (gekürzt auf die genutzten Felder).
"""
import importlib.util
from pathlib import Path

_PFAD = Path(__file__).resolve().parents[2] / "scripts" / "pruefaufgaben_aufraeumen.py"
_spec = importlib.util.spec_from_file_location("pruefaufgaben_aufraeumen", _PFAD)
skript = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skript)

OFFEN = {"property_status": {"id": 163674, "name": "Vermarktung"}, "rented": {"label": "Vermietet", "value": False}, "archived": False}
ABGESCHLOSSEN = {"property_status": {"id": 163676, "name": "Abgeschlossen"}, "rented": {"label": "Vermietet", "value": False}, "archived": False}
VERMIETET = {"property_status": {"id": 163674, "name": "Vermarktung"}, "rented": {"label": "Vermietet", "value": True}, "archived": False}
OHNE_STATUS = {"property_status": None, "rented": {"label": "Vermietet", "value": False}, "archived": False}


def _aufgabe(task_id, titel, units, angelegt, done=None):
    return {"id": task_id + 1_000_000, "activatable_id": task_id, "title": titel, "done": done,
            "property_ids": units, "original_created_at": angelegt}


def _plan(aufgaben, einheiten):
    return {e["task_id"]: e for e in skript.plane(aufgaben, einheiten)}


def test_einheit_abgeschlossen():
    assert skript.einheit_abgeschlossen(ABGESCHLOSSEN)
    assert skript.einheit_abgeschlossen(VERMIETET)
    assert skript.einheit_abgeschlossen({**OFFEN, "archived": True})
    assert not skript.einheit_abgeschlossen(OFFEN)
    assert not skript.einheit_abgeschlossen(OHNE_STATUS)


def test_dublette_aelteste_bleibt_offen():
    aufgaben = [  # absteigend, wie die Schnittstelle liefert
        _aufgabe(3, "Newsletter-Vermietung prüfen: CTP", [5769426], "2026-10-28T10:27:31.732+01:00"),
        _aufgabe(2, "Newsletter-Vermietung prüfen: CTP", [5769426], "2026-10-06T11:54:19.470+02:00"),
        _aufgabe(1, "Newsletter-Vermietung prüfen: CTP", [5769426], "2026-09-30T10:00:00.000+02:00"),
    ]
    plan = _plan(aufgaben, {5769426: OFFEN})
    assert set(plan) == {2, 3}
    assert all(e["grund"] == skript.DUBLETTE and e["behalten"] == 1 for e in plan.values())


def test_gegenstandslos_auch_die_aelteste():
    """Ist die Einheit abgeschlossen, bleibt keine Aufgabe dazu offen – auch nicht die erste."""
    aufgaben = [
        _aufgabe(1, "Newsletter-Vermietung prüfen: Garbe Industrial", [5032898], "2026-10-16T09:59:46.949+02:00"),
        _aufgabe(2, "Newsletter-Vermietung prüfen: Garbe", [5032898], "2026-10-18T09:52:40.046+02:00"),
    ]
    plan = _plan(aufgaben, {5032898: ABGESCHLOSSEN})
    assert {t: e["grund"] for t, e in plan.items()} == {1: skript.GEGENSTANDSLOS, 2: skript.GEGENSTANDSLOS}


def test_mehrere_einheiten_nur_wenn_alle_zutreffen():
    aufgaben = [
        _aufgabe(1, "Newsletter-Vermietung prüfen: Park", [11], "2026-08-01T10:00:00.000+02:00"),
        _aufgabe(2, "Newsletter-Vermietung prüfen: Park", [11, 12], "2026-08-02T10:00:00.000+02:00"),  # 12 neu -> bleibt
        _aufgabe(3, "Newsletter-Vermietung prüfen: Park", [11, 12], "2026-08-03T10:00:00.000+02:00"),  # beide abgedeckt
        _aufgabe(4, "Newsletter-Vermietung prüfen: Halle", [21, 22], "2026-08-04T10:00:00.000+02:00"),  # nur 21 zu -> bleibt
    ]
    plan = _plan(aufgaben, {11: OFFEN, 12: OFFEN, 21: ABGESCHLOSSEN, 22: OFFEN})
    assert set(plan) == {3}
    assert plan[3]["grund"] == skript.DUBLETTE


def test_unangetastet_bleiben_andere_arten_erledigte_und_aufgaben_ohne_einheit():
    aufgaben = [
        _aufgabe(1, "Flächenupdate abgleichen: Panattoni", [11], "2026-08-01T10:00:00.000+02:00"),
        _aufgabe(2, "Flächenupdate abgleichen: Panattoni", [11], "2026-08-02T10:00:00.000+02:00"),
        _aufgabe(3, "Newsletter-Vermietung prüfen: erledigt", [11], "2026-08-03T10:00:00.000+02:00", done=True),
        _aufgabe(4, "Newsletter-Vermietung prüfen: ohne Objekt", [], "2026-08-04T10:00:00.000+02:00"),
        _aufgabe(5, "Newsletter-Vermietung prüfen: ohne Objekt", [], "2026-08-05T10:00:00.000+02:00"),
        _aufgabe(6, "Newsletter-Vermietung prüfen: erste offene", [11], "2026-08-06T10:00:00.000+02:00"),
    ]
    assert skript.plane(aufgaben, {11: OFFEN}) == []


def test_einheit_nicht_geladen_gilt_als_offen():
    aufgaben = [_aufgabe(1, "Newsletter-Vermietung prüfen: X", [99], "2026-08-01T10:00:00.000+02:00")]
    assert skript.plane(aufgaben, {}) == []


# --- Aufgaben des #objekte-Handlers, die auf eine Vollzugsmeldung antworten ------------

def _text(zitat):
    """So legt der Handler den Aufgabentext an (objekte_handler/main.py, _stufe_b)."""
    return (f"Slack-Nachricht vom 2026-11-09:<br><br><blockquote>{zitat}</blockquote><br><br>"
            "Permalink: https://example.invalid/p1<br><br>Einordnung: Objekt fehlt in Propstack – Anlage nur manuell")


def test_zitierte_nachricht():
    text = _text("neues Objekt angelegt<br> SEGRO - (32) Herford &amp; Umgebung")
    assert skript.zitierte_nachricht(text) == "neues Objekt angelegt\n SEGRO - (32) Herford & Umgebung"
    assert skript.zitierte_nachricht("ohne Zitat") == ""
    assert skript.zitierte_nachricht(None) == ""


def test_vollzugsmeldungen_koennen_zu_auftraege_bleiben():
    aufgaben = [
        _aufgabe(1, "Objekt fehlt in Propstack: SEGRO Herford", [], "2026-11-10T10:23:28.701+01:00"),
        _aufgabe(2, "Flächenupdate abgleichen: P3 Verfügbarkeiten 11/2026", [], "2026-11-03T10:07:04.325+01:00"),
        _aufgabe(3, "Objekt fehlt in Propstack: bitte anlegen", [], "2026-10-05T10:32:08.682+02:00"),       # echter Auftrag
        _aufgabe(4, "Flächenupdate abgleichen: Newsletter Hillwood", [], "2026-11-12T10:24:39.655+01:00"),  # echter Auftrag
        _aufgabe(5, "Slack #objekte prüfen: ohne lesbaren Text", [], "2026-11-12T10:24:39.655+01:00"),
        _aufgabe(6, "Objekt fehlt in Propstack: erledigt", [], "2026-11-10T10:23:28.701+01:00", done=True),
        _aufgabe(7, "Pruefung: Mileway Immo-Blitz 09.11. - 15 Objekte neu + Updates", [], "2026-11-09T16:07:18.646+01:00"),
    ]
    texte = {
        1: _text("neues Objekt angelegt<br> SEGRO - (32) Herford"),
        2: _text("_P3 Verfügbarkeiten 11/2026 – Abgleich mit Propstack_ …<br>_Gesendet mit_ Claude<br>*Gesendet mit* Claude"),
        3: _text("bitte anlegen"),
        4: _text("Newsletter Hillwood 11/26 INKLUSIVE Mietpreise"),
        5: None,
        6: _text("neues Objekt angelegt"),
        7: _text("neues Objekt angelegt"),   # andere Art von Aufgabe: nie angefasst
    }
    plan = {e["task_id"]: e for e in skript.plane_vollzug(aufgaben, texte)}
    assert set(plan) == {1, 2}
    assert all(e["grund"] == skript.VOLLZUG for e in plan.values())
    assert "vermerk" not in plan[1]       # ohne Datum wie bisher: schließen ohne Vermerk

    # 21.11.2026: mit Datum steht vorn im Text, warum die Aufgabe zu ist (--undo nimmt es wieder heraus)
    plan = {e["task_id"]: e for e in skript.plane_vollzug(aufgaben, texte, "21.11.2026")}
    assert plan[2]["vermerk"] == ("Aufgeräumt 21.11.2026: Antwort auf eine Vollzugsmeldung – kein Auftrag, "
                                  "das Gemeldete ist in Propstack schon erledigt.<br><br>")


# --- Nachträge aus dem Gegenlesen (19.11.2026) ----------------------------------------

def test_doppelt_gelieferte_zeile_ist_keine_dublette_ihrer_selbst():
    """Die Liste wird seitenweise gelesen, während Leute arbeiten – eine Zeile kann zweimal kommen.
    Die einzige offene Aufgabe zu einer Einheit darf dadurch nicht geschlossen werden."""
    zeile = _aufgabe(1, "Newsletter-Vermietung prüfen: CTP", [5769426], "2026-09-30T10:00:00.000+02:00")
    assert skript.plane([zeile, dict(zeile)], {5769426: OFFEN}) == []


class _FakePropstack:
    def __init__(self):
        self.geschrieben = []
        self.erledigt = {}

    def setze_erledigt(self, task_id, erledigt):
        self.geschrieben.append((task_id, erledigt))
        self.erledigt[task_id] = erledigt

    def ist_erledigt(self, task_id):
        return self.erledigt.get(task_id)


def test_undo_schreibt_nur_mit_apply(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(skript.time, "sleep", lambda s: None)
    protokoll = tmp_path / "protokoll.json"
    protokoll.write_text('{"geschlossen": [11, 12], "unklar": [13]}', encoding="utf-8")

    ps = _FakePropstack()
    assert skript._undo(ps, str(protokoll), apply=False) == 0
    assert ps.geschrieben == [] and "Nur gelesen" in capsys.readouterr().out

    assert skript._undo(ps, str(protokoll), apply=True) == 0
    assert ps.geschrieben == [(11, False), (12, False), (13, False)]


def test_undo_bricht_ab_wenn_die_probe_nicht_wirkt(tmp_path, monkeypatch):
    monkeypatch.setattr(skript.time, "sleep", lambda s: None)
    protokoll = tmp_path / "protokoll.json"
    protokoll.write_text('{"geschlossen": [11, 12]}', encoding="utf-8")

    class _Wirkungslos(_FakePropstack):
        def ist_erledigt(self, task_id):
            return True   # Propstack hat das Feld still verworfen

    ps = _Wirkungslos()
    assert skript._undo(ps, str(protokoll), apply=True) == 1
    assert ps.geschrieben == [(11, False)]   # nur die Probe


def test_andere_meldung_zur_selben_einheit_ist_keine_dublette():
    """Rückfrage Florian, 19.11.2026: „Die Dubletten klar, aber die Newsletter müssen doch noch
    geprüft werden?“ – Zwei verschiedene Meldungen, die die KI derselben Einheit zugeordnet hat,
    sind genau der Fall für einen Menschen. Echte Titel vom Review-Sitz."""
    aufgaben = [
        _aufgabe(1, "Newsletter-Vermietung prüfen: Ixocon", [5768805], "2026-10-20T10:19:13.812+02:00"),
        _aufgabe(2, "Newsletter-Vermietung prüfen: Prologis Park Hamburg-Steinwerder DC1", [5768805], "2026-10-23T10:22:05.358+02:00"),
        _aufgabe(3, "Newsletter-Vermietung prüfen: Prologis Park Hamburg-Steinwerder", [5768805], "2026-10-27T09:46:48.420+01:00"),
    ]
    plan = _plan(aufgaben, {5768805: OFFEN})
    assert set(plan) == {3} and plan[3]["behalten"] == 2   # Dublette der zweiten, nicht der ersten


def test_gleiche_meldung():
    g = skript.gleiche_meldung
    assert g("Newsletter-Vermietung prüfen: Garbe", "Newsletter-Vermietung prüfen: Garbe Industrial")
    assert g("Newsletter-Vermietung prüfen: CTP", "Newsletter-Vermietung prüfen: CTP")
    assert g("Newsletter-Vermietung prüfen: Flex City", "Newsletter-Vermietung prüfen: FlexCity")
    assert g("Newsletter-Vermietung prüfen: Panattoni-Park Herleshausen", "Newsletter-Vermietung prüfen: Panattoni Park Bad Hersfeld Ost")
    assert not g("Newsletter-Vermietung prüfen: Hamburger Triport", "Newsletter-Vermietung prüfen: Maersk Deutschland")
    assert not g("Newsletter-Vermietung prüfen: Log Plaza Colonia 3", "Newsletter-Vermietung prüfen: Unternehmerpark Köln-Porz")
    assert not g("Newsletter-Vermietung prüfen: Dream Advisors", "Newsletter-Vermietung prüfen: Garbe Gewerbepark Soest")


# ---------------------------------------------------------------- Schließen nach Vorprüfung (--urteile)

def _vorpruefung():
    """Drei Vorgänge aus scripts/radar_vorpruefung_2026-11-19.json, gekürzt."""
    return {"stand": "19.11.2026", "faelle": [
        {"gruppe": "erledigt", "ort": "Dissen, Westring 8", "urteil": "Einheit ist seit dem 12.10. geschlossen.",
         "aufgaben": [{"id": 156833017}, {"id": 156912622}], "einheiten": [{"id": 5032898, "rolle": "zu"}]},
        {"gruppe": "fremd", "ort": "Frickenhausen", "urteil": "Verlängerung, keine neue Vermietung.",
         "aufgaben": [{"id": 154753285}], "einheiten": [{"id": 5769426, "rolle": "finger_weg"}]},
        {"gruppe": "klaeren", "ort": "Nohra", "urteil": "Adresse stimmt.", "frage": "Rest frei?",
         "aufgaben": [{"id": 158058453}], "einheiten": [{"id": 2777841, "rolle": "offen"}]},
    ]}


def _offene_aufgaben():
    return [
        _aufgabe(156833017, "Newsletter-Vermietung prüfen: Garbe Industrial", [5032898], "2026-10-16T09:59:46.949+02:00"),
        _aufgabe(156912622, "Newsletter-Vermietung prüfen: Garbe Industrial", [5032898], "2026-10-17T09:51:00.000+02:00"),
        _aufgabe(154753285, "Newsletter-Vermietung prüfen: CTP", [5769426], "2026-09-30T10:00:00.000+02:00"),
        _aufgabe(158058453, "Newsletter-Vermietung prüfen: FOCUS Logistikpark", [2777841], "2026-10-28T10:00:00.000+01:00"),
    ]


def test_urteile_nur_gewaehlte_gruppen_und_nur_offene_aufgaben():
    aufgaben = _offene_aufgaben()
    aufgaben[1]["done"] = True  # inzwischen von Hand erledigt
    plan, hinweise = skript.plane_urteile(aufgaben, _vorpruefung(), {"erledigt", "fremd"}, {5032898: ABGESCHLOSSEN})
    assert [e["task_id"] for e in plan] == [156833017, 154753285]
    assert [e["grund"] for e in plan] == ["erledigt", "fremd"]
    assert any("156912622" in h and "nicht mehr offen" in h for h in hinweise)
    assert plan[0]["vermerk"].startswith("Vorprüfung 19.11.2026: erledigt – ")
    assert plan[0]["vermerk"].endswith("Einheit ist seit dem 12.10. geschlossen.<br><br>")


def test_urteil_erledigt_gilt_nicht_mehr_wenn_die_einheit_wieder_offen_ist():
    """Zwischen Vorprüfung und Schließen kann jemand die Einheit wieder in die Vermarktung
    nehmen – dann bleibt die Aufgabe offen. Ebenso, wenn sich die Einheit nicht lesen ließ."""
    for einheiten in ({5032898: OFFEN}, {}):
        plan, hinweise = skript.plane_urteile(_offene_aufgaben(), _vorpruefung(), {"erledigt", "fremd"}, einheiten)
        assert [e["task_id"] for e in plan] == [154753285]
        assert any("Dissen" in h and "ausgelassen" in h for h in hinweise)


def test_urteil_fremd_braucht_keine_geschlossene_einheit():
    plan, _ = skript.plane_urteile(_offene_aufgaben(), _vorpruefung(), {"fremd"}, {})
    assert [e["task_id"] for e in plan] == [154753285]


class _TextPropstack(skript.Propstack):
    """Nur die Logik um den Vermerk; die Schnittstelle ist ein Wörterbuch."""

    def __init__(self, texte):
        self.texte_ = dict(texte)
        self.geschrieben = []

    def text(self, task_id):
        return self.texte_[task_id]

    def _request(self, method, path, **kw):
        task_id = int(path.rsplit("/", 1)[1])
        self.geschrieben.append((method, task_id, kw["json"]["task"]))
        if "body" in kw["json"]["task"]:
            self.texte_[task_id] = kw["json"]["task"]["body"]


def test_vermerk_kommt_vor_den_text_und_laesst_sich_wieder_herausnehmen():
    vermerk = skript.vermerk_html("19.11.2026", "fremd", "Verlängerung, keine neue Vermietung.")
    alt = "Vermietung aus dem Logistik-Deal Radar vom 2026-09-29:<br><br><blockquote>…</blockquote>"
    ps = _TextPropstack({7: alt})
    ps.schliesse_mit_vermerk(7, vermerk)
    assert ps.geschrieben[-1] == ("PUT", 7, {"done": True, "body": vermerk + alt})
    ps.schliesse_mit_vermerk(7, vermerk)  # zweiter Lauf: der Vermerk steht nicht doppelt da
    assert ps.texte_[7] == vermerk + alt
    assert ps.oeffne_ohne_vermerk(7, vermerk) is True
    assert ps.geschrieben[-1] == ("PUT", 7, {"done": False, "body": alt})


def test_undo_laesst_einen_inzwischen_geaenderten_text_stehen():
    vermerk = skript.vermerk_html("19.11.2026", "erledigt", "Einheit ist geschlossen.")
    ps = _TextPropstack({7: "Lena: doch noch offen, siehe Mail.<br>" + vermerk + "alt"})
    assert ps.oeffne_ohne_vermerk(7, vermerk) is False
    assert ps.geschrieben[-1] == ("PUT", 7, {"done": False})  # nur geöffnet, Text unberührt


def test_vorpruefung_im_repo_deckt_jede_aufgabe_genau_einmal():
    """Die Datei vom 19.11.2026: 129 Aufgaben in 85 Vorgängen, keine doppelt."""
    import json
    daten = json.loads((_PFAD.parent / "radar_vorpruefung_2026-11-19.json").read_text(encoding="utf-8"))
    ids = [a["id"] for f in daten["faelle"] for a in f["aufgaben"]]
    assert len(ids) == len(set(ids)) == 129
    assert {f["gruppe"] for f in daten["faelle"]} == {"eintragen", "klaeren", "schwach", "erledigt", "fremd"}
    je_gruppe = {g: sum(len(f["aufgaben"]) for f in daten["faelle"] if f["gruppe"] == g) for g in ("erledigt", "fremd")}
    assert je_gruppe == {"erledigt": 49, "fremd": 28}
    for f in daten["faelle"]:
        if f["gruppe"] == "erledigt":
            assert any(e["rolle"] == "zu" for e in f["einheiten"]), f["ort"]


def test_eintragen_schliesst_erst_wenn_die_vermietung_eingetragen_ist():
    """Die Aufgabe zu einer Vermietung, die noch eingetragen werden soll, bleibt offen, solange
    die Einheit in Propstack offen ist (Stand 20.11.2026: erst Connector, dann Aufgabe)."""
    vor = {"stand": "19.11.2026", "faelle": [
        {"gruppe": "eintragen", "ort": "Wiesloch, Gutenbergring", "urteil": "Einheit 002 hat exakt 30.000 m².",
         "aufgaben": [{"id": 154405188}],
         "einheiten": [{"id": 3181692, "rolle": "eintragen"}, {"id": 3181688, "rolle": "offen"}]},
    ]}
    aufgaben = [_aufgabe(154405188, "Newsletter-Vermietung prüfen: VGP Park Wiesloch-Walldorf", [3181692], "2026-09-29T10:00:00.000+02:00")]
    plan, hinweise = skript.plane_urteile(aufgaben, vor, {"eintragen"}, {3181692: OFFEN})
    assert plan == [] and "Wiesloch" in hinweise[0]
    # eingetragen: die Nachbar-Einheit mit Rolle „offen“ darf offen bleiben
    plan, hinweise = skript.plane_urteile(aufgaben, vor, {"eintragen"}, {3181692: {**ABGESCHLOSSEN, "rented": {"label": "Vermietet", "value": True}}})
    assert [e["task_id"] for e in plan] == [154405188] and hinweise == []
    assert plan[0]["vermerk"].startswith("Vorprüfung 19.11.2026: eingetragen – ")


def test_nachpruefung_im_repo_deckt_genau_die_klaeren_aufgaben():
    """scripts/radar_nachpruefung_2026-11-20.json: dieselben 26 Aufgaben wie „klaeren“ am 19.11.,
    jede genau einmal; jede Gruppe hat einen Wortlaut für den Vermerk."""
    import json
    vor = json.loads((_PFAD.parent / "radar_vorpruefung_2026-11-19.json").read_text(encoding="utf-8"))
    nach = json.loads((_PFAD.parent / "radar_nachpruefung_2026-11-20.json").read_text(encoding="utf-8"))
    klaeren = sorted(a["id"] for f in vor["faelle"] if f["gruppe"] == "klaeren" for a in f["aufgaben"])
    ids = sorted(a["id"] for f in nach["faelle"] for a in f["aufgaben"])
    assert ids == klaeren and len(ids) == 26
    for f in nach["faelle"]:
        assert f["gruppe"] == "offen" or f["gruppe"] in skript.URTEIL_WORT, f["ort"]
        if f["gruppe"] == "eintragen":
            assert any(e["rolle"] == "eintragen" for e in f["einheiten"]), f["ort"]
