from copy import deepcopy

import pytest

from core.buildings import Transfer, apply_transfers
from core.campus import CENTRAL_STOCK
from core.homogeneity import dominant_models, plan_homogeneity, suggested_targets
from core.owned_import import import_owned_computers
from core.store import Store


def campus():
    return import_owned_computers(
        b"room_id,model,quantity\n"
        b"CBY-101,X,1\nCBY-102,X,1\nCBY-103,Y,1\n"
        b"BRS-101,Y,1\nBRS-102,Y,1\nBRS-103,X,1\n"
    )


def execute(data, plan):
    for group in plan["groups"]:
        data = apply_transfers(data, [Transfer(**move) for move in group["transfers"]])
    return data


def test_majority_cycle_without_new_stock_preserves_every_class():
    data = campus()
    original = deepcopy(data)
    targets = suggested_targets(data)
    assert targets == {"BRS": "Y", "CBY": "X"}
    plan = plan_homogeneity(data, targets, CENTRAL_STOCK)
    assert len(plan["groups"]) == 1
    assert len(plan["groups"][0]["rooms"]) == 2
    after = execute(data, plan)
    assert sum(after.inventory.values()) == 6
    assert all(row["Manque"] == 0 for row in plan["summary"])
    assert all(
        after.occupied(room) == 1
        for room, info in after.rooms.items()
        if info.room_type == "classroom"
    )
    assert after.occupied(CENTRAL_STOCK) == 0
    assert data == original


def test_shortage_remains_visible_without_emptying_a_donor():
    data = campus()
    plan = plan_homogeneity(data, {"CBY": "X"}, CENTRAL_STOCK)
    assert not plan["groups"]
    assert plan["summary"][0]["Manque"] == 1


def test_ties_are_not_chosen_silently():
    data = import_owned_computers(b"room_id,model,quantity\nCBY-1,X,1\nCBY-2,Y,1\n")
    assert dominant_models(data, "CBY") == ["X", "Y"]
    assert suggested_targets(data) == {}


def test_multi_post_room_is_fully_regrouped():
    data = import_owned_computers(b"room_id,model,quantity\nCBY-1,X,3\nCBY-2,Y,2\n")
    data.inventory[CENTRAL_STOCK, "X"] = 2
    plan = plan_homogeneity(data, {"CBY": "X"}, CENTRAL_STOCK)
    after = execute(data, plan)
    assert plan["summary"][0]["Conformes après"] == 5
    assert after.inventory["CBY-2", "X"] == 2
    assert after.inventory[CENTRAL_STOCK, "Y"] == 2
    assert sum(after.inventory.values()) == 7


def test_known_newer_models_can_be_protected():
    data = campus()
    data.model_years = {"X": 2020, "Y": 2025}
    plan = plan_homogeneity(data, suggested_targets(data), CENTRAL_STOCK)
    assert not plan["groups"]
    assert sum(row["Manque"] for row in plan["summary"]) == 2
    relaxed = plan_homogeneity(
        data, suggested_targets(data), CENTRAL_STOCK, protect_newer=False
    )
    assert all(row["Manque"] == 0 for row in relaxed["summary"])


def test_cycle_confirmation_is_indivisible_and_persistent(tmp_path):
    data = campus()
    store = Store(tmp_path / "state.sqlite3")
    identifier = store.create_workspace("Campus", data)
    plan = plan_homogeneity(data, suggested_targets(data), CENTRAL_STOCK)
    batch = store.save_batch(identifier, 0, "Uniformiser", plan)
    assert store.load(identifier)[0] == data
    store.confirm_batch(
        identifier, batch, [0], "Toutes les étapes du cycle sont réalisées"
    )
    assert store.batches(identifier)[0]["status"] == "Terminé"
    assert Store(store.path).load(identifier)[0].inventory["CBY-103", "X"] == 1
    with pytest.raises(ValueError):
        store.confirm_batch(identifier, batch, [0], "Doublon")


def test_zero_transit_capacity_blocks_cycle():
    data = campus()
    from dataclasses import replace

    data.rooms[CENTRAL_STOCK] = replace(data.rooms[CENTRAL_STOCK], capacity=0)
    plan = plan_homogeneity(data, suggested_targets(data), CENTRAL_STOCK)
    assert not plan["groups"]


def test_recovered_model_supplies_other_building_before_unused_model():
    data = import_owned_computers(
        b"room_id,model,quantity\nCBY-1,A,1\nCBY-1,Z,1\nBRS-1,Q,1\n"
    )
    data.inventory[CENTRAL_STOCK, "X"] = 1
    plan = plan_homogeneity(data, {"CBY": "X", "BRS": "Z"}, CENTRAL_STOCK)
    after = execute(data, plan)
    assert after.inventory["BRS-1", "Z"] == 1
    assert plan["groups"][0]["old_model"] == "Z"
