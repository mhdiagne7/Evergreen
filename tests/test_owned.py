"""Contrats d'import, géographie et stock central avec données de test minimales."""

from math import isclose

import pytest

from core.buildings import Transfer, apply_transfers, plan_building
from core.campus import CENTRAL_STOCK, building_distance, campus_catalog
from core.graph import build_graph
from core.owned_import import import_owned_computers
from core.routing import shortest_route
from core.store import Store, decode_data, encode_data
from map_view import map_rows

OWNED = (
    b"room_id,model,quantity\n"
    b"CBY-101,Old,1\nCBY-102,Old,1\n"
    b"MRT-101,Old,1\nFTX-147,Old,1\nFTX-147,Other,1\n"
    b"LEE-100,Old,1\n"
)


def test_import_keeps_every_computer_and_mixed_rooms():
    data = import_owned_computers(OWNED)
    assert sum(data.inventory.values()) == 6
    assert data.rooms["FTX-147"].capacity == 2
    assert data.rooms["FTX-147"].capacity_basis == "observed"
    assert data.inventory["FTX-147", "Other"] == 1
    assert data.occupied(CENTRAL_STOCK) == 0
    assert data.rooms[CENTRAL_STOCK].capacity is None
    assert [
        room for room, info in data.rooms.items() if info.room_type == "storage"
    ] == [CENTRAL_STOCK]
    assert decode_data(encode_data(data)) == data


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"room_id,model,quantity\n",
        b"room_id,model,quantity\nCBY-1,PC,-1\n",
        b"room_id,model,quantity\nCBY-1,PC,0\n",
        b"room_id,model,quantity\nCBY-1,PC,1.5\n",
        b"room_id,model,quantity\nUNKNOWN,PC,1\n",
        b"room_id,model,quantity\nMRT-STOCK,PC,1\n",
        b"room_id,model,quantity\nCBY-1,,1\n",
    ],
)
def test_invalid_owned_file_is_rejected(payload):
    with pytest.raises(ValueError):
        import_owned_computers(payload)


def test_semicolon_and_bom():
    data = import_owned_computers(
        "\ufeffmodel;quantity;room_id\nPC;2;CBY-101\n".encode()
    )
    assert data.inventory["CBY-101", "PC"] == 2


def test_repeated_export_rows_are_preserved_and_flagged():
    payload = b"room_id,model,quantity\nFTX-147,PC,1\nFTX-147,PC,1\n"
    data = import_owned_computers(payload)
    assert data.inventory["FTX-147", "PC"] == 2
    assert data.rooms["FTX-147"].capacity == 2
    assert len(data.import_notes) == 1
    assert "doublon" in data.import_notes[0]
    assert decode_data(encode_data(data)).import_notes == data.import_notes


def test_geography_is_symmetric_and_internal_distance_is_unknown():
    data = import_owned_computers(OWNED)
    graph = build_graph(data)
    route = shortest_route(graph, CENTRAL_STOCK, "CBY-101")
    assert 0 < route.distance_m < 2000
    assert "vol d’oiseau" in route.distance_label
    assert isclose(
        route.distance_m, shortest_route(graph, "CBY-101", CENTRAL_STOCK).distance_m
    )
    assert shortest_route(graph, "CBY-101", "CBY-102").distance_m is None
    assert shortest_route(graph, "CBY-101", "CBY-101").distance_m == 0
    assert building_distance("UNKNOWN", "CBY") is None
    assert campus_catalog()["LEE"]["properties"]["official_code"] == "LEES-FHS"


def test_stock_receipt_return_and_total_conservation(tmp_path):
    store = Store(tmp_path / "inventory.sqlite3")
    key = store.create_workspace("Test", import_owned_computers(OWNED))
    store.add_model(key, "New")
    # Aucun champ de provenance n'est nécessaire.
    store.receive(key, CENTRAL_STOCK, "New", 2, 0)
    data, _, revision, _ = store.load(key)
    plan = plan_building(data, "CBY", {"New": 2}, CENTRAL_STOCK)
    assert len(plan["groups"]) == 2
    assert not any(row["Manque"] for row in plan["summary"])
    assert all(
        group["transfers"][0]["destination"] == CENTRAL_STOCK
        for group in plan["groups"]
    )
    batch = store.save_batch(key, revision, "Test renouvellement", plan)
    store.confirm_batch(key, batch, [0], "Effectué")
    store.confirm_batch(key, batch, [1], "Effectué")
    after, _, _, _ = store.load(key)
    assert sum(after.inventory.values()) == sum(data.inventory.values())
    assert after.inventory[CENTRAL_STOCK, "Old"] == 2
    assert after.inventory[CENTRAL_STOCK, "New"] == 0
    assert after.inventory["CBY-101", "New"] == 1


def test_stock_limit_and_stale_plan(tmp_path):
    store = Store(tmp_path / "inventory.sqlite3")
    key = store.create_workspace("Test", import_owned_computers(OWNED))
    store.configure_stock_capacity(key, CENTRAL_STOCK, 1, 0)
    store.receive(key, CENTRAL_STOCK, "Old", 1, 1)
    with pytest.raises(ValueError, match="pas assez de places"):
        store.receive(key, CENTRAL_STOCK, "Old", 1, 2)
    with pytest.raises(ValueError, match="inférieure"):
        store.configure_stock_capacity(key, CENTRAL_STOCK, 0, 2)
    with pytest.raises(ValueError, match="inventaire a changé"):
        store.receive(key, CENTRAL_STOCK, "Old", 1, 0)


def test_map_only_contains_inventory_buildings_and_escapes_html():
    data = import_owned_computers(OWNED.replace(b"Other", b"<script>"))
    rows, missing, _ = map_rows(data, ["Old", "<script>"])
    assert missing == []
    assert {row["code"] for row in rows} == {"CBY", "MRT", "FTX", "LEE"}
    assert sum(row["installed"] for row in rows) == 6
    assert "<script>" not in next(
        row["details"] for row in rows if row["code"] == "FTX"
    )
    filtered, _, _ = map_rows(data, ["Old", "<script>"], "<script>")
    assert next(row["quantity"] for row in filtered if row["code"] == "FTX") == 1


def test_central_stock_without_same_building_reserve():
    data = import_owned_computers(OWNED)
    data.inventory[CENTRAL_STOCK, "New"] = 1
    plan = plan_building(data, "CBY", {"New": 1}, CENTRAL_STOCK)
    assert len(plan["groups"]) == 1
    transfers = [Transfer(**row) for row in plan["groups"][0]["transfers"]]
    result = apply_transfers(data, transfers)
    assert result.inventory[CENTRAL_STOCK, "Old"] == 1
    assert data.inventory.get((CENTRAL_STOCK, "Old"), 0) == 0
