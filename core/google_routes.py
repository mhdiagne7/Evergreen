"""Client Routes API : coordonnées publiques uniquement, sans inventaire ni clé en URL."""

import hashlib
import json
import math
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.campus import building_position

ENDPOINT = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
FIELD_MASK = "originIndex,destinationIndex,status,condition,distanceMeters,duration"


def matrix_signature(codes):
    return hashlib.sha256(
        json.dumps([(code, building_position(code)) for code in sorted(codes)]).encode()
    ).hexdigest()


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


def post_matrix(payload, key):
    request = Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            content = response.read(4_000_001)
        if len(content) > 4_000_000:
            raise ValueError("Réponse Google Maps trop volumineuse.")
        return json.loads(content)
    except HTTPError as error:
        raise ValueError(
            f"Google Maps a refusé le calcul (HTTP {error.code}). Vérifie la clé, "
            "l’activation de Routes API, les restrictions et la facturation du projet."
        ) from None
    except (URLError, TimeoutError, json.JSONDecodeError):
        raise ValueError(
            "Google Maps ne répond pas ou a renvoyé une réponse illisible. Aucun nouvel essai automatique n’est effectué."
        ) from None


def compute_walking_matrix(codes, key, transport=None):
    codes = sorted(set(codes))
    if not key or not key.strip():
        raise ValueError("Configurer une clé Google Maps Routes API avant le calcul.")
    if not codes or any(building_position(code) is None for code in codes):
        raise ValueError(
            "Tous les bâtiments doivent posséder des coordonnées validées."
        )
    transport = transport or post_matrix
    result = {}
    # 625 éléments maximum par requête. Les directions restent indépendantes.
    destination_size = min(50, len(codes))
    for offset in range(0, len(codes), destination_size):
        destinations = codes[offset : offset + destination_size]
        origin_size = max(1, min(25, 625 // len(destinations)))
        for start in range(0, len(codes), origin_size):
            origins = codes[start : start + origin_size]

            def waypoint(code):
                latitude, longitude = building_position(code)
                return {
                    "waypoint": {
                        "location": {
                            "latLng": {
                                "latitude": latitude,
                                "longitude": longitude,
                            }
                        }
                    }
                }

            payload = {
                "origins": [waypoint(code) for code in origins],
                "destinations": [waypoint(code) for code in destinations],
                "travelMode": "WALK",
                "languageCode": "fr-CA",
                "units": "METRIC",
            }
            response = transport(payload, key)
            if not isinstance(response, list):
                raise ValueError(
                    "Réponse Google Maps inattendue : une liste de trajets est requise."
                )
            seen = set()
            for element in response:
                if not isinstance(element, dict):
                    raise ValueError(
                        "Un élément de la réponse Google Maps est invalide."
                    )
                origin_index = element.get("originIndex", 0)
                destination_index = element.get("destinationIndex", 0)
                if (
                    type(origin_index) is not int
                    or type(destination_index) is not int
                    or not 0 <= origin_index < len(origins)
                    or not 0 <= destination_index < len(destinations)
                    or (origin_index, destination_index) in seen
                ):
                    raise ValueError("Indices Google Maps incohérents ou dupliqués.")
                seen.add((origin_index, destination_index))
                pair = origins[origin_index], destinations[destination_index]
                status = element.get("status", {})
                if not isinstance(status, dict):
                    raise ValueError("Statut Google Maps invalide.")
                valid = (
                    element.get("condition") == "ROUTE_EXISTS"
                    and status.get("code", 0) == 0
                )
                distance = element.get("distanceMeters")
                duration = element.get("duration", "")
                if valid:
                    if (
                        type(distance) is not int
                        or distance < 0
                        or not isinstance(duration, str)
                        or not duration.endswith("s")
                    ):
                        raise ValueError("Distance ou durée Google Maps invalide.")
                    try:
                        seconds = float(duration[:-1])
                    except ValueError:
                        raise ValueError("Durée Google Maps invalide.") from None
                    if not math.isfinite(seconds) or seconds < 0:
                        raise ValueError("Durée Google Maps invalide.")
                    result[pair] = {
                        "distance_m": distance,
                        "duration_s": seconds,
                        "status": "OK",
                    }
                else:
                    result[pair] = {
                        "distance_m": None,
                        "duration_s": None,
                        "status": "NON_DISPONIBLE",
                    }
            for source in origins:
                for target in destinations:
                    result.setdefault(
                        (source, target),
                        {
                            "distance_m": None,
                            "duration_s": None,
                            "status": "NON_DISPONIBLE",
                        },
                    )
    return {
        "signature": matrix_signature(codes),
        "codes": codes,
        "calculated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "routes": result,
    }
