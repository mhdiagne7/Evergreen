"""Géographie publique du campus et distances géodésiques explicites."""

import json
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

MAP_SOURCE = (
    "https://www.uottawa.ca/about-us/administration-services/facilities/campus-maps"
)
CATALOG_PATH = Path(__file__).resolve().parents[1] / "data/public/buildings.geojson"
CENTRAL_STOCK = "MRT-STOCK"


@lru_cache(maxsize=1)
def campus_catalog():
    """Lire les contours publics, sans requête réseau ni données d'inventaire."""
    content = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {feature["properties"]["code"]: feature for feature in content["features"]}


def building_position(code):
    feature = campus_catalog().get(code)
    if feature is None:
        return None
    properties = feature["properties"]
    return properties["latitude"], properties["longitude"]


def geodesic_metres(first, second):
    """Haversine sur une sphère de rayon moyen terrestre, en mètres."""
    lat_a, lon_a = map(radians, first)
    lat_b, lon_b = map(radians, second)
    haversine = (
        sin((lat_b - lat_a) / 2) ** 2
        + cos(lat_a) * cos(lat_b) * sin((lon_b - lon_a) / 2) ** 2
    )
    return 2 * 6_371_008.8 * asin(sqrt(min(1, max(0, haversine))))


def building_distance(source, destination):
    first = building_position(source)
    second = building_position(destination)
    if first is None or second is None:
        return None
    return geodesic_metres(first, second)
