from copy import deepcopy

import pytest

from core.buildings import Transfer, apply_transfers, plan_building
from core.campus import CENTRAL_STOCK
from core.data import Room
from core.owned_import import import_owned_computers
from core.reuse import add_reuse_operations
from core.store import Store, decode_data, encode_data


def inventory():
    data = import_owned_computers(
        b"room_id,model,quantity\nCBY-101,Middle,1\nBRS-101,Old,1\nDMS-101,Older,1\n"
    )
    data.inventory[CENTRAL_STOCK, "New"] = 1
    data.model_years = {"New": 2025, "Middle": 2020, "Old": 2015, "Older": 2010}
    return data


def execute(data, plan):
    for group in plan["groups"]:
        data = apply_transfers(data, [Transfer(**row) for row in group["transfers"]])
    return data


def test_replaced_computers_return_to_morisset_and_cascade():
    data = inventory()
    before = deepcopy(data)
    initial = plan_building(data, "CBY", {"New": 1}, CENTRAL_STOCK)
    result = add_reuse_operations(data, initial)
    assert result["reuse_count"] == 2
    assert [group["room"] for group in result["groups"]] == [
        "CBY-101",
        "BRS-101",
        "DMS-101",
    ]
    after = execute(data, result)
    assert after.inventory["CBY-101", "New"] == 1
    assert after.inventory["BRS-101", "Middle"] == 1
    assert after.inventory["DMS-101", "Old"] == 1
    assert sum(after.inventory.values()) == sum(data.inventory.values())
    assert sum(after.returned_stock.values()) == 1
    assert data == before
    assert initial.get("reuse_count") is None


def test_no_unknown_year_or_downgrade():
    data = inventory()
    data.model_years = {}
    initial = plan_building(data, "CBY", {"New": 1}, CENTRAL_STOCK)
    assert add_reuse_operations(data, initial)["reuse_count"] == 0
    returned = execute(data, initial)
    assert returned.returned_stock[CENTRAL_STOCK, "Middle"] == 1
    assert not plan_building(returned, "BRS", {"Middle": 1}, CENTRAL_STOCK)["groups"]


def test_receipt_does_not_turn_returned_stock_into_new(tmp_path):
    data = inventory()
    initial = plan_building(data, "CBY", {"New": 1}, CENTRAL_STOCK)
    after = execute(data, initial)
    store = Store(tmp_path / "inventory.sqlite3")
    key = store.create_workspace("Campus", after)
    store.receive(key, CENTRAL_STOCK, "Middle", 2, 0)
    saved = store.load(key)[0]
    assert saved.inventory[CENTRAL_STOCK, "Middle"] == 3
    assert saved.returned_stock[CENTRAL_STOCK, "Middle"] == 1
    assert decode_data(encode_data(saved)) == saved


def test_new_receipts_and_returns_only_at_morisset(tmp_path):
    data = inventory()
    data.rooms["BRS-STOCK"] = Room("BRS", None, frozenset({"*"}), "storage")
    store = Store(tmp_path / "inventory.sqlite3")
    key = store.create_workspace("Campus", data)
    with pytest.raises(ValueError, match="Morisset"):
        store.receive(key, "BRS-STOCK", "New", 1, 0)
    with pytest.raises(ValueError):
        plan_building(data, "CBY", {"New": 1}, "BRS-STOCK")


def test_reuse_confirmations_are_atomic_and_ordered(tmp_path):
    data = inventory()
    store = Store(tmp_path / "inventory.sqlite3")
    key = store.create_workspace("Campus", data)
    plan = add_reuse_operations(
        data, plan_building(data, "CBY", {"New": 1}, CENTRAL_STOCK)
    )
    batch = store.save_batch(key, 0, "Cascade", plan)
    with pytest.raises(ValueError, match="Stock insuffisant"):
        store.confirm_batch(key, batch, [1], "Pas encore disponible")
    assert store.load(key)[2] == 0
    store.confirm_batch(key, batch, [0], "Renouvellement effectué")
    assert store.load(key)[0].returned_stock[CENTRAL_STOCK, "Middle"] == 1
    store.confirm_batch(key, batch, [1, 2], "Réaffectations effectuées")
    assert store.batches(key)[0]["status"] == "Terminé"
    assert sum(store.load(key)[0].inventory.values()) == 4


def test_generation_year_persists_and_invalidates_old_plans(tmp_path):
    store = Store(tmp_path / "inventory.sqlite3")
    key = store.create_workspace("Campus", inventory())
    store.set_model_year(key, "New", 2026, 0)
    assert Store(store.path).load(key)[0].model_years["New"] == 2026
    with pytest.raises(ValueError):
        store.set_model_year(key, "Old", None, 1)


def test_downgrading_a_class_with_a_return_is_refused(tmp_path):
    data = inventory()
    data = execute(data, plan_building(data, "CBY", {"New": 1}, CENTRAL_STOCK))
    data.model_years["Middle"] = 2010
    empty_plan = {
        "building": "CBY",
        "buffer": CENTRAL_STOCK,
        "groups": [],
        "goals": {},
        "summary": [],
    }
    assert add_reuse_operations(data, empty_plan)["reuse_count"] == 0
    store = Store(tmp_path / "inventory.sqlite3")
    key = store.create_workspace("Campus", data)
    invalid = {
        **empty_plan,
        "groups": [
            {
                "room": "BRS-101",
                "transfers": [
                    vars(Transfer("BRS-101", CENTRAL_STOCK, "Old")),
                    vars(
                        Transfer(
                            CENTRAL_STOCK, "BRS-101", "Middle", stock_kind="returned"
                        )
                    ),
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="plus récent"):
        store.save_batch(key, 0, "Réaffectation refusée", invalid)
    assert store.load(key)[0] == data
