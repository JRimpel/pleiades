"""Geometry helpers: bbox parsing, cell polygons, GeoJSON."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .errors import bad_request

# Western New York bounding box (Architecture §4).
WNY_BBOX = (-79.8, 42.0, -77.0, 43.4)  # west, south, east, north


@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.west, self.south, self.east, self.north)


def parse_bbox(value: str | None, *, default: tuple[float, float, float, float] | None = WNY_BBOX) -> BBox | None:
    """Parse 'w,s,e,n'. Returns the default bbox if value is empty."""
    if not value:
        return BBox(*default) if default else None
    parts = value.split(",")
    if len(parts) != 4:
        raise bad_request("bbox must be 'west,south,east,north'")
    try:
        w, s, e, n = (float(p) for p in parts)
    except ValueError as err:
        raise bad_request("bbox values must be numbers") from err
    if not (-180 <= w <= 180 and -180 <= e <= 180 and -90 <= s <= 90 and -90 <= n <= 90):
        raise bad_request("bbox out of range")
    if w >= e or s >= n:
        raise bad_request("bbox must satisfy west < east and south < north")
    return BBox(w, s, e, n)


def parse_latlon(value: str | None, *, field: str = "near") -> tuple[float, float] | None:
    """Parse 'lat,lon'."""
    if not value:
        return None
    parts = value.split(",")
    if len(parts) != 2:
        raise bad_request(f"{field} must be 'lat,lon'")
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError as err:
        raise bad_request(f"{field} values must be numbers") from err
    validate_latlon(lat, lon)
    return lat, lon


def validate_latlon(lat: float, lon: float) -> None:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise bad_request("lat/lon out of range")


def cell_polygon(lat: float, lon: float, step: float) -> dict[str, Any]:
    """Square GeoJSON polygon of side `step` degrees centred on (lat, lon)."""
    h = step / 2.0
    w, e, s, n = round(lon - h, 6), round(lon + h, 6), round(lat - h, 6), round(lat + h, 6)
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def point(lat: float, lon: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}


def feature(geometry: dict[str, Any], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def feature_collection(features: Iterable[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    fc: dict[str, Any] = {"type": "FeatureCollection", "features": list(features)}
    fc.update(extra)
    return fc
