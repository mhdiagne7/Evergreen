import copy
import shutil
import pytest
from core.data import DEMO_DIR, load_data
from core.graph import build_graph
from core.routing import shortest_route
from core.optimizer import compatible_destinations, prepare_grouping


@pytest.fixture
def data():
    return load_data()


def test_route_and_same_room(data):
    graph = build_graph(data)
    route = shortest_route(graph, "MRT 1140", "UCU 214")
    assert route.distance_m == 195
    assert route.nodes == ["MRT 1140", "MRT Hall", "MRT Exit", "UCU Entry", "UCU 214"]
    assert route.distance_label == "simulée"
    assert shortest_route(graph, "MRT 1140", "MRT 1140").distance_m == 0
    assert shortest_route(graph, "UCU 214", "MRT 1140").distance_m == 195


def test_dijkstra_uses_weights(data):
    graph = build_graph(data)
    graph.add_edge("MRT 1140", "UCU 214", distance_m=900, distance_type="simulated")
    assert shortest_route(graph, "MRT 1140", "UCU 214").distance_m == 195


def test_unreachable_unknown_and_estimated(data):
    graph = build_graph(data)
    graph.remove_edge("MRT 1140", "MRT Hall")
    assert shortest_route(graph, "MRT 1140", "UCU 214") is None
    with pytest.raises(ValueError):
        shortest_route(graph, "missing", "UCU 214")
    graph["UCU Entry"]["UCU 214"]["distance_type"] = "estimated"
    assert shortest_route(graph, "UCU Entry", "UCU 214").distance_label == "estimée"
    assert "mixte" in shortest_route(graph, "MRT 120", "UCU 214").distance_label


def test_compatibility_capacity_and_order(data):
    moves = compatible_destinations(data, build_graph(data), "MRT 1140", "Dell OptiPlex 7050", 10)
    assert [move.destination for move in moves] == ["MRT 120", "UCU 214", "STE 1030"]
    # MRT 1140 has 10 of this model plus 2 of another: only 8 free places.
    moves = compatible_destinations(data, build_graph(data), "MRT 120", "Dell OptiPlex 7050", 9)
    assert "MRT 1140" not in [move.destination for move in moves]
    with pytest.raises(ValueError):
        compatible_destinations(data, build_graph(data), "MRT 1140", "Dell OptiPlex 7050", 11)


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True])
def test_invalid_quantity(data, quantity):
    with pytest.raises(ValueError):
        prepare_grouping(data, build_graph(data), "MRT 120", "Dell OptiPlex 7050", quantity)


def test_grouping_respects_capacity_conservation_and_no_mutation(data):
    before = copy.deepcopy(data)
    plan = prepare_grouping(data, build_graph(data), "UCU 214", "Dell OptiPlex 7050", 25)
    assert plan.moved == 18 and plan.remaining == 7
    assert [(m.source, m.quantity) for m in plan.moves] == [("MRT 1140", 10), ("MRT 120", 8)]
    assert plan.effort == 10 * 195 + 8 * 205
    updated = dict(data.inventory)
    for move in plan.moves:
        updated[move.source, move.model] -= move.quantity
        key = (move.destination, move.model)
        updated[key] = updated.get(key, 0) + move.quantity
    assert sum(updated.values()) == sum(data.inventory.values())
    assert min(updated.values()) >= 0
    assert data == before


def test_insufficient_stock_and_disconnected(data):
    graph = build_graph(data)
    plan = prepare_grouping(data, graph, "CBY 210", "HP EliteDesk 800", 5)
    assert plan.moved == 0 and plan.remaining == 5
    graph.remove_edge("UCU Entry", "UCU 214")
    assert prepare_grouping(data, graph, "UCU 214", "Dell OptiPlex 7050", 5).moved == 0
    with pytest.raises(ValueError):
        prepare_grouping(data, graph, "CBY 210", "Dell OptiPlex 7050", 5)


@pytest.mark.parametrize("filename,old,new", [
    ("connections.csv", "20,simulated", "-20,simulated"),
    ("connections.csv", "20,simulated", "nan,simulated"),
    ("connections.csv", "20,simulated", "20,real"),
    ("inventory.csv", "7050,10", "7050,100"),
    ("inventory.csv", "7050,10", "7050,-1"),
    ("inventory.csv", "MRT 1140", "UNKNOWN"),
    ("rooms.csv", "room_id", "wrong_header"),
])
def test_invalid_csv(tmp_path, filename, old, new):
    for path in DEMO_DIR.glob("*.csv"):
        shutil.copy(path, tmp_path / path.name)
    path = tmp_path / filename
    path.write_text(path.read_text().replace(old, new), encoding="utf-8")
    with pytest.raises(ValueError):
        load_data(tmp_path)
