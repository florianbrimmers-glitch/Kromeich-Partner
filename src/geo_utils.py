from __future__ import annotations

from functools import lru_cache

from pyproj import Transformer

# ETRS89 / UTM Zone 32N — passt für Bayern und liefert metrische Koordinaten,
# auf denen die Shoelace-Formel direkt qm zurückgibt.
_UTM32N_EPSG = 25832
_WGS84_EPSG = 4326


@lru_cache(maxsize=1)
def _wgs84_to_utm32n() -> Transformer:
    return Transformer.from_crs(_WGS84_EPSG, _UTM32N_EPSG, always_xy=True)


def polygon_area_sqm(coords_lonlat: list[tuple[float, float]]) -> float:
    """Berechnet Polygon-Grundfläche in Quadratmetern.

    coords_lonlat: Liste (lon, lat) — wird automatisch geschlossen falls nötig.
    """
    if len(coords_lonlat) < 3:
        return 0.0

    transformer = _wgs84_to_utm32n()
    projected: list[tuple[float, float]] = [
        transformer.transform(lon, lat) for lon, lat in coords_lonlat
    ]

    if projected[0] != projected[-1]:
        projected.append(projected[0])

    area = 0.0
    for i in range(len(projected) - 1):
        x1, y1 = projected[i]
        x2, y2 = projected[i + 1]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def polygon_centroid(coords_lonlat: list[tuple[float, float]]) -> tuple[float, float]:
    """Naive Zentroid-Berechnung im WGS84-Mittelwert (für Anzeige reicht das)."""
    if not coords_lonlat:
        return (0.0, 0.0)
    lons = [lon for lon, _ in coords_lonlat]
    lats = [lat for _, lat in coords_lonlat]
    return (sum(lats) / len(lats), sum(lons) / len(lons))
