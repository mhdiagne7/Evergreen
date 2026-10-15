"""Liens publics vers les trajets à pied, sans clé ni appel API."""

from urllib.parse import urlencode

from core.campus import building_position


def directions_url(origin, destination):
    first, last = building_position(origin), building_position(destination)
    if first is None or last is None:
        return None
    return "https://www.google.com/maps/dir/?" + urlencode(
        {
            "api": 1,
            "origin": f"{first[0]},{first[1]}",
            "destination": f"{last[0]},{last[1]}",
            "travelmode": "walking",
        }
    )
