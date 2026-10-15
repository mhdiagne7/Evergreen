import pytest

from core.campus import campus_catalog
from core.google_routes import compute_walking_matrix, directions_url
from core.graph import build_graph
from core.owned_import import import_owned_computers
from core.routing import shortest_route
from core.store import decode_data, encode_data


def response_for(payload, key):
    assert payload["travelMode"] == "WALK"
    assert "model" not in str(payload) and "inventory" not in str(payload)
    return [
        {
            "originIndex": i,
            "destinationIndex": j,
            "condition": "ROUTE_EXISTS",
            "distanceMeters": 150 + 10 * i + j,
            "duration": "120.5s",
            "status": {},
        }
        for i in reversed(range(len(payload["origins"])))
        for j in reversed(range(len(payload["destinations"])))
    ]


def test_batches_respect_google_limits_and_keep_both_directions():
    codes = list(campus_catalog())
    calls = []

    def transport(payload, key):
        calls.append(payload)
        assert len(payload["origins"]) * len(payload["destinations"]) <= 625
        return response_for(payload, key)

    matrix = compute_walking_matrix(codes, "test-key-never-used-on-network", transport)
    assert len(calls) == 2
    assert len(matrix["routes"]) == 27 * 27
    assert (
        matrix["routes"]["BRS", "CBY"]["distance_m"]
        != matrix["routes"]["CBY", "BRS"]["distance_m"]
    )


def test_failed_pairs_do_not_become_geodesic_routes():
    data = import_owned_computers(b"room_id,model,quantity\nBRS-1,PC,1\nCBY-1,PC,1\n")
    data.building_routes = {
        ("BRS", "CBY"): {"status": "NON_DISPONIBLE", "distance_m": None}
    }
    assert shortest_route(build_graph(data), "BRS-1", "CBY-1") is None


def test_google_distances_are_runtime_only():
    data = import_owned_computers(b"room_id,model,quantity\nBRS-1,PC,1\nCBY-1,PC,1\n")
    data.building_routes = {("BRS", "CBY"): {"status": "OK", "distance_m": 765}}
    route = shortest_route(build_graph(data), "BRS-1", "CBY-1")
    assert route.distance_m == 765 and "Google Maps" in route.distance_label
    assert decode_data(encode_data(data)).building_routes == {}


def test_empty_key_and_unknown_building_fail_before_request():
    with pytest.raises(ValueError, match="clé"):
        compute_walking_matrix(["MRT"], "")
    with pytest.raises(ValueError, match="coordonnées"):
        compute_walking_matrix(["UNKNOWN"], "test-key")


@pytest.mark.parametrize(
    "response",
    [
        {},
        [{"originIndex": -1}],
        [{"originIndex": True}],
        [{"condition": "ROUTE_EXISTS", "distanceMeters": -1, "duration": "1s"}],
        [{"condition": "ROUTE_EXISTS", "distanceMeters": 1, "duration": "nans"}],
        [{"originIndex": 0}, {"originIndex": 0}],
    ],
)
def test_malformed_google_response_is_rejected(response):
    with pytest.raises(ValueError):
        compute_walking_matrix(["MRT"], "test-key", lambda payload, key: response)


def test_missing_pairs_are_reported_and_zero_indices_may_be_omitted():
    matrix = compute_walking_matrix(
        ["BRS", "CBY"],
        "test-key",
        lambda payload, key: [
            {"condition": "ROUTE_EXISTS", "distanceMeters": 0, "duration": "0s"},
        ],
    )
    assert matrix["routes"]["BRS", "BRS"]["status"] == "OK"
    assert matrix["routes"]["BRS", "CBY"]["status"] == "NON_DISPONIBLE"


def test_directions_link_needs_no_key_and_requests_walking():
    link = directions_url("MRT", "CBY")
    assert "travelmode=walking" in link
    assert "key=" not in link
    assert directions_url("UNKNOWN", "CBY") is None


def test_google_metrics_are_not_persisted_in_batches_or_exported(tmp_path):
    from core.homogeneity import plan_homogeneity
    from core.store import Store
    from ui.common import transfer_rows

    data = import_owned_computers(b"room_id,model,quantity\nCBY-1,Old,1\n")
    data.inventory["MRT-STOCK", "New"] = 1
    data.building_routes = {
        ("MRT", "CBY"): {"status": "OK", "distance_m": 432},
        ("CBY", "MRT"): {"status": "OK", "distance_m": 456},
    }
    plan = plan_homogeneity(data, {"CBY": "New"}, "MRT-STOCK")
    assert plan["groups"][0]["delivery_m"] == 432
    store = Store(tmp_path / "state.sqlite3")
    key = store.create_workspace("Campus", data)
    store.save_batch(key, 0, "Google preview", plan)
    assert store.batches(key)[0]["plan"]["groups"][0]["delivery_m"] is None
    assert plan["groups"][0]["delivery_m"] == 432
    assert all(
        row["Distance (m)"] is None
        for row in transfer_rows(plan, data, for_export=True)
    )
