from copy import deepcopy
import pytest
from core.data import Dataset, Room, load_data, DEMO_DIR
from core.buildings import Transfer, apply_transfers, plan_building, building_summary


def campus():
    return load_data(DEMO_DIR / "campus")


def tiny(storage_qty=2, buffer_capacity=5):
    rooms = {"A1": Room("A", 1, frozenset({"*"})), "A2": Room("A", 1, frozenset({"*"})),
             "A stock": Room("A", buffer_capacity, frozenset({"*"}), "storage"),
             "B1": Room("B", 1, frozenset({"*"})), "B stock": Room("B", 10, frozenset({"*"}), "storage")}
    stock = {("A1", "Old"): 1, ("A2", "Old"): 1, ("B1", "New"): 1, ("B stock", "New"): storage_qty}
    edges = [("A1", "A stock", 1, "simulated"), ("A2", "A stock", 2, "simulated"),
             ("B1", "A stock", 4, "simulated"), ("B stock", "A stock", 10, "simulated")]
    return Dataset(rooms, stock, edges)


def execute(data, plan):
    for group in plan["groups"]:
        data = apply_transfers(data, [Transfer(**m) for m in group["transfers"]])
    return data


def test_building_goals_and_conservation():
    data = campus()
    original = deepcopy(data)
    goals = {"Dell OptiPlex 7060": 15, "Dell OptiPlex 7090": 10}
    plan = plan_building(data, "CBY", goals, "CBY Réserve")
    assert all(row["Manque"] == 0 for row in plan["summary"])
    after = execute(data, plan)
    for model, count in goals.items():
        assert sum(q for (r, m), q in after.inventory.items() if m == model and after.rooms[r].building == "CBY" and after.rooms[r].room_type == "classroom") == count
    assert sum(after.inventory.values()) == sum(data.inventory.values())
    assert all(after.occupied(r) == 1 for r, room in after.rooms.items() if room.room_type == "classroom")
    assert data == original


def test_storage_priority_and_distance():
    data = tiny()
    plan = plan_building(data, "A", {"New": 1}, "A stock", allow_swaps=True)
    assert plan["groups"][0]["source"] == "B stock"  # B1 est plus près, mais installé.
    assert plan["groups"][0]["room"] == "A1"
    assert plan["groups"][0]["transfers"][0]["model"] == "Old"


def test_swaps_do_not_empty_donor_classes():
    data = tiny(storage_qty=0)
    assert not plan_building(data, "A", {"New": 1}, "A stock")["groups"]
    plan = plan_building(data, "A", {"New": 1}, "A stock", True)
    after = execute(data, plan)
    assert after.inventory["B1", "Old"] == 1
    assert after.inventory["A1", "New"] == 1
    assert after.occupied("A stock") == 0
    assert len(plan["groups"][0]["transfers"]) == 3


def test_full_transit_and_unreachable():
    data = tiny(buffer_capacity=0)
    assert not plan_building(data, "A", {"New": 2}, "A stock", True)["groups"]
    data = tiny()
    data.connections = []
    assert not plan_building(data, "A", {"New": 2}, "A stock", True)["groups"]


def test_already_equipped_and_missing_stock():
    data = tiny(storage_qty=1)
    plan = plan_building(data, "A", {"New": 2}, "A stock")
    assert plan["summary"][0]["Manque"] == 1
    data = execute(data, plan)
    assert not plan_building(data, "A", {"New": 1}, "A stock")["groups"]


def test_forbidden_return_model_blocks_swap():
    data = tiny(storage_qty=0)
    data.rooms["B1"] = Room("B", 1, frozenset({"New"}))
    assert not plan_building(data, "A", {"New": 1}, "A stock", True)["groups"]


@pytest.mark.parametrize("goals", [{"New": 3}, {"New": 0}, {"New": True}, {}])
def test_invalid_goals(goals):
    with pytest.raises(ValueError):
        plan_building(tiny(), "A", goals, "A stock")


def test_dashboard_separates_installed_from_stock():
    summary, details = building_summary(tiny(), ["Old", "New"])
    assert summary[0]["Postes installés"] == 2
    assert summary[1]["En réserve"] == 2
    assert next(r for r in details if r["Bâtiment"] == "B" and r["Modèle"] == "New")["Total"] == 3


def test_transfer_rejects_negative_stock_and_over_capacity():
    data = tiny()
    with pytest.raises(ValueError):
        apply_transfers(data, [Transfer("B stock", "A1", "New")])
    with pytest.raises(ValueError):
        apply_transfers(data, [Transfer("A stock", "A1", "Missing")])
