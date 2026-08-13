from __future__ import annotations

from . import config

# Umkehrindex PLZ-Leitregion -> Marktgebiet, einmal aufgebaut.
_NACH_PLZ: dict[str, str] = {}
for _name, _prefixe in config.MARKTGEBIETE_TOP:
    for _p in _prefixe:
        _NACH_PLZ[_p] = _name
for _p in config.MARKTGEBIET_RUHR[1]:
    _NACH_PLZ.setdefault(_p, config.MARKTGEBIET_RUHR[0])

TOP_NAMEN = tuple(name for name, _ in config.MARKTGEBIETE_TOP)
RUHR_NAME = config.MARKTGEBIET_RUHR[0]


def markt(region_key: str | None) -> str | None:
    """'44' -> 'Ruhrgebiet' · '40' -> 'Düsseldorf' · '99' -> None."""
    if not region_key:
        return None
    return _NACH_PLZ.get(region_key)


def gruppe(region_key: str | None) -> str:
    """Zuordnung zur Tabellen-Gruppe (Top-Märkte vs. sonstige Standorte)."""
    name = markt(region_key)
    if name and name in TOP_NAMEN:
        return config.GRUPPE_TOP
    return config.GRUPPE_SONSTIGE


def zeilen_label(region_key: str | None) -> str:
    """Beschriftung der Tabellenzeile für eine Leitregion.

    Top-Märkte und das Ruhrgebiet erscheinen namentlich, alles Übrige wird
    unter einer Sammelzeile geführt – wie in den Marktberichten.
    """
    name = markt(region_key)
    if name:
        return name
    return config.LABEL_UEBRIGE
