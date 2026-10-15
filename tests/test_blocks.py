from copy import deepcopy

import pytest

from core.blocks import block_counts, plan_blocks, suggest_blocks
from core.campus import CENTRAL_STOCK
from core.owned_import import import_owned_computers
from core.store import Store


def campus():
    return import_owned_computers(
        b"room_id,model,quantity\nBRS-1,X,1\nCBY-1,Y,1\nFTX-1,Y,2\n"
    )


def test_block_compactness_no_neighbor_chain(monkeypatch):
    data = campus()
    distance = {
        frozenset({"BRS", "CBY"}): 100,
        frozenset({"CBY", "FTX"}): 100,
        frozenset({"BRS", "FTX"}): 200,
    }
    monkeypatch.setattr(
        "core.blocks.building_distance",
        lambda a, b: 0 if a == b else distance[frozenset({a, b})],
    )
    blocks = suggest_blocks(data, max_posts=2, max_distance=150)
    assert len(blocks) == 1
    assert len(blocks[0]) == 2
    assert len({code for group in blocks for code in group}) == sum(map(len, blocks))


def test_post_threshold_and_unknown_coordinates(monkeypatch):
    data = campus()
    monkeypatch.setattr(
        "core.blocks.building_distance", lambda a, b: None if "BRS" in (a, b) else 10
    )
    assert suggest_blocks(data, max_posts=1) == []
    assert suggest_blocks(data, max_posts=2) == [("CBY", "FTX")]


def test_blocks_use_one_target_without_merging_rooms(tmp_path):
    data = campus()
    data.inventory[CENTRAL_STOCK, "Y"] = 1
    before = deepcopy(data)
    plan = plan_blocks(
        data,
        [{"buildings": ["BRS", "CBY"], "model": "Y"}],
        include_other_buildings=False,
    )
    assert plan["targets"] == {"BRS": "Y", "CBY": "Y"}
    assert plan["block_summary"][0]["Manque"] == 0
    assert data == before
    store = Store(tmp_path / "blocks.sqlite3")
    identifier = store.create_workspace("Blocks", data)
    batch = store.save_batch(identifier, 0, "Bloc", plan)
    store.confirm_batch(identifier, batch, [0], "Terminé")
    after = store.load(identifier)[0]
    assert after.inventory["BRS-1", "Y"] == 1
    assert after.occupied("CBY-1") == 1
    assert sum(after.inventory.values()) == sum(data.inventory.values())
    assert block_counts(data, ["BRS", "CBY"]) == {"X": 1, "Y": 1}


def test_overlapping_blocks_are_rejected():
    with pytest.raises(ValueError, match="seul bloc"):
        plan_blocks(
            campus(),
            [
                {"buildings": ["BRS", "CBY"], "model": "X"},
                {"buildings": ["CBY", "FTX"], "model": "Y"},
            ],
        )


def test_no_stock_shortage_is_visible_and_no_machine_created():
    data = campus()
    plan = plan_blocks(
        data,
        [{"buildings": ["BRS", "CBY"], "model": "Y"}],
        include_other_buildings=False,
    )
    assert not plan["groups"]
    assert plan["block_summary"][0]["Manque"] == 1
