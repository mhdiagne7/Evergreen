import pytest
from core.data import DEMO_DIR, SCHEMAS, load_csv_files
from core.graph import build_graph
from core.routing import shortest_route
from core.optimizer import evaluate_destinations
from core.session import activate_import
from core.export import csv_bytes


def demo_files():
    return {name: (DEMO_DIR / name).read_bytes() for name in SCHEMAS}


def test_new_buildings_models_and_nearest_by_weight():
    files = {
        "rooms.csv": b"capacity;room_id;building;allowed_models\n10;A;New;PC\n10;B;New;PC\n10;C;New;PC\n10;D;New;Other\n",
        "inventory.csv": b"room_id;model;quantity\nA;PC;5\nB;PC;9\n",
        "connections.csv": b"source;target;distance_m;distance_type\nA;C;100;measured\nA;Hall;10,5;estimated\nHall;C;5;estimated\nA;B;2;measured\n",
    }
    data = load_csv_files(files)
    graph = build_graph(data)
    evaluated = evaluate_destinations(data, graph, "A", "PC", 3)
    assert [item.room for item in evaluated if not item.reasons] == ["C"]
    assert evaluated[0].room == "B" and "Place insuffisante" in evaluated[0].reasons[0]
    assert shortest_route(graph, "A", "C").distance_m == 15.5
    assert shortest_route(graph, "A", "B").distance_label == "mesurée (déclarée)"
    assert evaluated[-1].room == "D"
    assert len(evaluated[-1].reasons) == 2


def test_import_is_atomic_and_resets_choices():
    state = {"dataset": "previous", "dataset_label": "previous", "choice_source": "old"}
    invalid = demo_files()
    invalid["inventory.csv"] = b"room_id,model,quantity\nMissing,PC,5\n"
    with pytest.raises(ValueError):
        activate_import(state, invalid)
    assert state == {"dataset": "previous", "dataset_label": "previous", "choice_source": "old"}
    activate_import(state, demo_files())
    assert "choice_source" not in state
    assert state["dataset_label"].startswith("Données importées")


@pytest.mark.parametrize("content", [b"\xff", b"", b"room_id,building,capacity,allowed_models\nA,B,no,PC\n", b"room_id,building,capacity,allowed_models\nA,B,2,PC,extra\n"])
def test_invalid_upload(content):
    files = demo_files()
    files["rooms.csv"] = content
    with pytest.raises(ValueError):
        load_csv_files(files)


def test_ties_are_alphabetical():
    data = load_csv_files(demo_files())
    graph = build_graph(data)
    graph.add_edge("MRT 1140", "STE 1030", distance_m=50, distance_type="simulated")
    results = [item.room for item in evaluate_destinations(data, graph, "MRT 1140", "Dell OptiPlex 7050", 5) if not item.reasons]
    assert results[:2] == ["MRT 120", "STE 1030"]


def test_export_protects_formula_and_preserves_label():
    exported = csv_bytes([{"Salle": "=HYPERLINK(1)", "Quantité": 2, "Jeu": "Import"}]).decode("utf-8-sig")
    assert "'=HYPERLINK(1)" in exported
    assert "Import" in exported
