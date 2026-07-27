"""Tests für die Drive-Migration mit einem nachgebauten Drive-Dienst.

Prüft die vier Entscheidungen, auf die es bei der Migration ankommt: eigene Dateien
verschieben (Historie bleibt), fremde kopieren (Eigentum wechselt), gesperrte Dateien
als Fehler melden statt still zu verlieren, und ein abgebrochener Lauf muss
wiederaufsetzbar sein.
"""
import csv
import importlib.util
from pathlib import Path

import pytest

SKRIPT = Path(__file__).resolve().parents[1] / "scripts" / "drive_migrate_copy.py"
_spec = importlib.util.spec_from_file_location("drive_migrate_copy", SKRIPT)
dmc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dmc)

ICH = "florian.brimmers@kromeichpartner.de"
FREMD = "felix.kern2014@gmail.com"


# --------------------------------------------------------------- Drive-Attrappe

class _Antwort:
    def __init__(self, nutzlast):
        self._nutzlast = nutzlast

    def execute(self):
        return self._nutzlast


class FakeFiles:
    def __init__(self, baum):
        self.baum = baum          # parent_id -> Liste von Objekten
        self.angelegt = []
        self.kopiert = []
        self.verschoben = []
        self._zaehler = 0

    def _neue_id(self, praefix):
        self._zaehler += 1
        return f"{praefix}-{self._zaehler}"

    def list(self, q, **_kwargs):
        parent = q.split("'")[1]
        return _Antwort({"files": list(self.baum.get(parent, []))})

    def create(self, body, **_kwargs):
        neu_id = self._neue_id("neu")
        self.angelegt.append({**body, "id": neu_id})
        return _Antwort({"id": neu_id})

    def copy(self, fileId, body, **_kwargs):
        neu_id = self._neue_id("kopie")
        self.kopiert.append({"quelle": fileId, **body, "id": neu_id})
        return _Antwort({"id": neu_id})

    def update(self, fileId, addParents, removeParents, **_kwargs):
        self.verschoben.append({"id": fileId, "nach": addParents, "von": removeParents})
        return _Antwort({"id": fileId})


class FakeService:
    def __init__(self, baum):
        self._files = FakeFiles(baum)

    def files(self):
        return self._files


def datei(id_, name, eigentuemer, mime="application/pdf", can_copy=True, groesse="1024"):
    return {
        "id": id_, "name": name, "mimeType": mime, "size": groesse,
        "md5Checksum": f"md5-{id_}", "createdTime": "2025-01-01T00:00:00Z",
        "modifiedTime": "2025-06-01T00:00:00Z",
        "owners": [{"emailAddress": eigentuemer}],
        "capabilities": {"canCopy": can_copy, "canDownload": True},
    }


def ordner(id_, name, eigentuemer=FREMD):
    return {"id": id_, "name": name, "mimeType": dmc.FOLDER_MIME,
            "owners": [{"emailAddress": eigentuemer}]}


def verknuepfung(id_, name, ziel_id):
    return {"id": id_, "name": name, "mimeType": dmc.SHORTCUT_MIME,
            "owners": [{"emailAddress": FREMD}], "shortcutDetails": {"targetId": ziel_id}}


BAUM = {
    # Wurzel: ein Unterordner, eine fremde und eine eigene Datei
    "quelle": [
        ordner("o1", "03. Finanzen, Steuern"),
        datei("f1", "Steuerbescheid.pdf", FREMD),
        datei("f2", "Liquiditaetsplanung.xlsx", ICH),
    ],
    # Unterordner: gesperrte Datei und eine Verknüpfung auf f1
    "o1": [
        datei("f3", "Gesperrt.pdf", FREMD, can_copy=False),
        verknuepfung("v1", "Verweis auf Steuerbescheid", "f1"),
    ],
}


def lauf(tmp_path, baum=BAUM, dry_run=False):
    service = FakeService({k: list(v) for k, v in baum.items()})
    manifest_pfad = str(tmp_path / "migration.csv")
    manifest = dmc.Manifest(manifest_pfad, dry_run)
    migration = dmc.Migration(service, manifest, ICH, dry_run, move_own=True)
    migration.baum_durchlaufen("quelle", "ziel")
    migration.verknuepfungen_nachziehen()
    manifest.close()
    return service.files(), migration, manifest_pfad


def manifest_zeilen(pfad):
    with open(pfad, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------------ Tests

def test_fremde_datei_wird_kopiert_und_traegt_den_herkunftsvermerk(tmp_path):
    """Nur das Kopieren löst das Eigentum vom Privatkonto – der Nachweis muss mit."""
    files, _, _ = lauf(tmp_path)

    kopie = next(k for k in files.kopiert if k["quelle"] == "f1")
    assert kopie["parents"] == ["ziel"]
    assert "Original-ID: f1" in kopie["description"]
    assert f"Original-Eigentümer: {FREMD}" in kopie["description"]
    assert "Original erstellt: 2025-01-01T00:00:00Z" in kopie["description"]
    assert "Original-Pfad: /Steuerbescheid.pdf" in kopie["description"]


def test_eigene_datei_wird_verschoben_nicht_kopiert(tmp_path):
    """Was uns gehört, behält beim Verschieben Historie und Zeitstempel."""
    files, migration, _ = lauf(tmp_path)

    assert files.verschoben == [{"id": "f2", "nach": "ziel", "von": "quelle"}]
    assert "f2" not in [k["quelle"] for k in files.kopiert]
    assert migration.zaehler["verschoben"] == 1


def test_gesperrte_datei_wird_als_fehler_gemeldet(tmp_path):
    """'Betrachter dürfen nicht kopieren' darf nicht still durchrutschen."""
    files, migration, manifest_pfad = lauf(tmp_path)

    assert "f3" not in [k["quelle"] for k in files.kopiert]
    assert migration.zaehler["fehler"] == 1
    zeile = next(z for z in manifest_zeilen(manifest_pfad) if z["alt_id"] == "f3")
    assert zeile["status"] == "fehler"
    assert zeile["fehler"] == "canCopy=false"


def test_verknuepfung_zeigt_auf_die_neue_kopie(tmp_path):
    """Verweise müssen ins Ziel zeigen, sonst hängt der neue Baum am alten."""
    files, _, _ = lauf(tmp_path)

    kopie_von_f1 = next(k for k in files.kopiert if k["quelle"] == "f1")["id"]
    shortcut = next(a for a in files.angelegt if a["mimeType"] == dmc.SHORTCUT_MIME)
    assert shortcut["shortcutDetails"]["targetId"] == kopie_von_f1


def test_ordnerstruktur_wird_nachgebaut(tmp_path):
    files, migration, _ = lauf(tmp_path)

    ordner_angelegt = [a for a in files.angelegt if a["mimeType"] == dmc.FOLDER_MIME]
    assert [o["name"] for o in ordner_angelegt] == ["03. Finanzen, Steuern"]
    assert ordner_angelegt[0]["parents"] == ["ziel"]
    assert migration.zaehler["ordner"] == 1


def test_zweiter_lauf_wiederholt_nichts(tmp_path):
    """Nach Abbruch muss der Wiederanlauf keine Dubletten erzeugen."""
    _, _, manifest_pfad = lauf(tmp_path)
    vorher = len(manifest_zeilen(manifest_pfad))

    service = FakeService({k: list(v) for k, v in BAUM.items()})
    manifest = dmc.Manifest(manifest_pfad, dry_run=False)
    migration = dmc.Migration(service, manifest, ICH, False, move_own=True)
    migration.baum_durchlaufen("quelle", "ziel")
    manifest.close()

    assert service.files().kopiert == []          # nichts erneut kopiert
    assert service.files().verschoben == []       # nichts erneut verschoben
    assert service.files().angelegt == []         # Ordner nicht doppelt angelegt
    assert migration.zaehler["uebersprungen"] == 2
    # Nur das gesperrte Objekt wird erneut versucht und erzeugt eine neue Zeile.
    assert len(manifest_zeilen(manifest_pfad)) == vorher + 1
    # Ordner, zwei Dateien, gesperrte Datei, Verknüpfung – jedes Objekt genau einmal.
    assert len(dmc.letzter_stand(manifest_pfad)) == 5


def test_spaeterer_erfolg_ueberschreibt_frueheren_fehler(tmp_path):
    """Sonst meldet die Nachkontrolle eine im zweiten Lauf geglückte Datei als offen."""
    pfad = tmp_path / "m.csv"
    with open(pfad, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=dmc.MANIFEST_COLUMNS)
        w.writeheader()
        w.writerow({"aktion": "kopieren", "status": "fehler", "pfad": "/a.pdf",
                    "alt_id": "f1", "fehler": "rateLimitExceeded"})
        w.writerow({"aktion": "kopieren", "status": "ok", "pfad": "/a.pdf",
                    "alt_id": "f1", "neu_id": "kopie-1"})

    stand = dmc.letzter_stand(str(pfad))
    assert len(stand) == 1
    assert stand[0]["status"] == "ok"


def test_trockenlauf_veraendert_nichts(tmp_path):
    files, migration, manifest_pfad = lauf(tmp_path, dry_run=True)

    assert files.kopiert == [] and files.verschoben == [] and files.angelegt == []
    assert not Path(manifest_pfad).exists()
    assert migration.bytes_gesamt == 2048        # zwei Dateien à 1 KB eingeplant


def test_verschieben_faellt_bei_fehlendem_schreibrecht_auf_kopieren_zurueck(tmp_path, caplog):
    """Ohne Schreibrecht im Quellordner lässt sich der Elternteil nicht entfernen."""
    class Sperrig(FakeFiles):
        def update(self, **_kwargs):
            raise dmc.HttpError(type("R", (), {"status": 403, "reason": "insufficientPermissions"})(),
                                b"insufficientFilePermissions")

    service = FakeService({k: list(v) for k, v in BAUM.items()})
    service._files = Sperrig({k: list(v) for k, v in BAUM.items()})
    manifest = dmc.Manifest(str(tmp_path / "m.csv"), dry_run=False)
    migration = dmc.Migration(service, manifest, ICH, False, move_own=True)
    migration.baum_durchlaufen("quelle", "ziel")
    manifest.close()

    assert "f2" in [k["quelle"] for k in service.files().kopiert]
    assert migration.zaehler["kopiert"] == 2     # fremde + eigene (als Rückfall)
    assert migration.zaehler["verschoben"] == 0


def _http_error(status, inhalt):
    return dmc.HttpError(type("R", (), {"status": status, "reason": ""})(), inhalt)


def test_ratenbegrenzung_wird_wiederholt_rechtefehler_nicht():
    """Drive nutzt 403 für beides. Ein Rechtefehler darf keinen Backoff auslösen."""
    assert dmc.ist_wiederholbar(_http_error(403, b'{"error":{"errors":[{"reason":"rateLimitExceeded"}]}}'))
    assert dmc.ist_wiederholbar(_http_error(429, b"tooManyRequests"))
    assert dmc.ist_wiederholbar(_http_error(503, b"backendError"))
    assert not dmc.ist_wiederholbar(_http_error(403, b'{"error":{"errors":[{"reason":"insufficientFilePermissions"}]}}'))
    assert not dmc.ist_wiederholbar(_http_error(404, b"notFound"))


def test_rechtefehler_bricht_ohne_wartezeit_ab(monkeypatch):
    """Sonst kostet jede nicht verschiebbare Datei Minuten Leerlauf."""
    schlaefe = []
    monkeypatch.setattr(dmc.time, "sleep", schlaefe.append)
    versuche = []

    def factory():
        versuche.append(1)
        raise _http_error(403, b"insufficientFilePermissions")

    with pytest.raises(dmc.HttpError):
        dmc.with_retry(lambda: type("Q", (), {"execute": staticmethod(factory)})(), "Test")

    assert len(versuche) == 1
    assert schlaefe == []


def test_verify_meldet_fehlende_und_abweichende_dateien(tmp_path, capsys):
    class PruefFiles(FakeFiles):
        def get(self, fileId, **_kwargs):
            if fileId == "kopie-fehlt":
                raise dmc.HttpError(type("R", (), {"status": 404, "reason": "notFound"})(), b"notFound")
            if fileId == "kopie-abweichend":
                return _Antwort({"id": fileId, "md5Checksum": "anders", "trashed": False})
            return _Antwort({"id": fileId, "md5Checksum": "md5-f1", "trashed": False})

    pfad = tmp_path / "m.csv"
    with open(pfad, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=dmc.MANIFEST_COLUMNS)
        w.writeheader()
        w.writerow({"aktion": "kopieren", "status": "ok", "pfad": "/a.pdf",
                    "alt_id": "f1", "neu_id": "kopie-ok", "md5": "md5-f1"})
        w.writerow({"aktion": "kopieren", "status": "ok", "pfad": "/b.pdf",
                    "alt_id": "f2", "neu_id": "kopie-fehlt", "md5": "md5-f2"})
        w.writerow({"aktion": "kopieren", "status": "ok", "pfad": "/c.pdf",
                    "alt_id": "f3", "neu_id": "kopie-abweichend", "md5": "md5-f3"})
        w.writerow({"aktion": "kopieren", "status": "fehler", "pfad": "/d.pdf",
                    "alt_id": "f4", "fehler": "canCopy=false"})

    service = FakeService({})
    service._files = PruefFiles({})
    abweichungen = dmc.verify(service, str(pfad))
    ausgabe = capsys.readouterr().out

    assert abweichungen == 3
    assert "FEHLT     /b.pdf" in ausgabe
    assert "MD5 ABWEICHUNG /c.pdf" in ausgabe
    assert "OFFEN     /d.pdf" in ausgabe


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
