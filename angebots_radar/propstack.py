"""Propstack lesen – und nur lesen. Dieses Modul kennt ausschließlich GET.

Geprüft an Live-Antworten am 26.11.2026:
- `GET /v1/saved_queries` (Suchprofile): {data, meta.total_count}, `per` wirkt, 271 Zeilen.
  Gebiet in `lat`/`lng`/`radius` (Meter), `polygon` ([lng, lat]), `cities`, `regions`;
  Custom-Felder unter `custom_fields` als {value, pretty_value}.
- `GET /v1/client_properties` (Deals): {data, meta}, 1.945 Zeilen. `property_id` ist bei
  Projekt-Deals leer – dann steht `project_id`.
- `GET /v1/units?expand=1`: 26 Seiten zu 100, rund vier Minuten. Ohne feste Sortierung
  verschieben sich Einheiten zwischen den Seiten (scripts/gesuch_matching.py).
- `GET /v1/contacts/:id`: `name`, `company`.
"""
from __future__ import annotations

import time

import httpx

BASE = "https://api.propstack.de/v1"


class Propstack:
    def __init__(self, key: str):
        self._client = httpx.Client(timeout=90.0, headers={"X-API-KEY": key, "Accept": "application/json"})

    def _get(self, pfad: str, **params):
        for versuch in range(5):
            antwort = self._client.get(f"{BASE}{pfad}", params=params)
            if antwort.status_code == 429 or antwort.status_code >= 500:
                time.sleep(3 * (versuch + 1))
                continue
            antwort.raise_for_status()
            return antwort.json()
        antwort.raise_for_status()
        raise RuntimeError(f"Propstack antwortet nicht verwertbar auf {pfad}")

    def _alle(self, pfad: str, **params) -> list[dict]:
        """Alle Seiten; je ID nur einmal."""
        zeilen: dict[int, dict] = {}
        seite = 1
        while True:
            daten = self._get(pfad, per=100, page=seite, **params)
            rows = daten if isinstance(daten, list) else (daten or {}).get("data", [])
            for row in rows:
                if isinstance(row, dict) and row.get("id"):
                    zeilen[row["id"]] = row
            if len(rows) < 100:
                return list(zeilen.values())
            seite += 1
            time.sleep(0.2)

    def einheiten(self) -> list[dict]:
        return self._alle("/units", expand=1, sort_by="created_at", order="asc")

    def suchprofile(self) -> list[dict]:
        return self._alle("/saved_queries")

    def deals(self) -> list[dict]:
        return self._alle("/client_properties")

    def makler(self) -> dict[int, str]:
        daten = self._get("/brokers")
        rows = daten if isinstance(daten, list) else (daten or {}).get("data", [])
        return {int(b["id"]): str(b.get("name") or "").strip() for b in rows if isinstance(b, dict) and b.get("id")}

    def kontakte(self, ids: list[int]) -> dict[int, dict]:
        """Name und Firma je Kontakt. Ein Kontakt, der sich nicht lesen lässt, fehlt im Ergebnis –
        der Bericht nennt dann die Nummer."""
        out: dict[int, dict] = {}
        for kontakt_id in ids:
            try:
                daten = self._get(f"/contacts/{kontakt_id}")
            except httpx.HTTPStatusError:
                continue
            if isinstance(daten, dict):
                out[kontakt_id] = {"name": str(daten.get("name") or "").strip(), "firma": str(daten.get("company") or "").strip()}
            time.sleep(0.1)
        return out
