from collections import Counter
from copy import deepcopy

import pytest

from core.asset_groups import GroupStore, automatic_groups, filter_assets
from core.buildings import Transfer
from core.campus import CENTRAL_STOCK
from core.owned_import import import_owned_computers
from core.store import Store


@pytest.fixture
def campus(tmp_path):
    store = Store(tmp_path / "groups.sqlite3")
    data = import_owned_computers(
        b"room_id,model,quantity\nCBY-101,X,2\nCBY-102,Y,1\nBRS-1,X,1\n"
    )
    workspace = store.create_workspace("Campus", data)
    groups = GroupStore(store)
    return store, workspace, groups


def save_group(groups, workspace, members, name="Groupe"):
    return groups.save_many(
        workspace, 0, [{"name": name, "description": "Test", "members": members}]
    )[0]


def test_local_identity_is_unique_stable_and_never_invents_physical_serial(campus):
    store, w, groups = campus
    assets = groups.assets(w)
    assert len(assets) == 4
    assert len({a["id"] for a in assets}) == 4
    assert all(
        a["physical_id"] == "" and a["category"] is None and a["floor"] == ""
        for a in assets
    )
    assert assets == GroupStore(Store(store.path)).assets(w)
    assert store.load(w)[2] == 0


def test_manual_crud_preserves_inventory_and_supports_overlapping_members(campus):
    store, w, groups = campus
    before = store.load(w)
    assets = groups.assets(w)
    ids = [a["id"] for a in assets]
    one = save_group(groups, w, ids[:2])
    two = save_group(groups, w, ids[:1], "Autre groupe")
    groups.update(w, one, 0, "Renommé", "Description", ids[1:])
    row = next(g for g in groups.groups(w) if g["id"] == one)
    assert row["name"] == "Renommé" and row["status"] == "Brouillon"
    assert row["members"] == ids[1:]
    groups.delete(w, one, 1)
    assert len(groups.groups(w)) == 1
    assert groups.groups(w)[0]["id"] == two
    assert store.load(w) == before


@pytest.mark.parametrize("members_kind", ["empty", "duplicate", "unknown"])
def test_invalid_groups_are_rejected_atomically(campus, members_kind):
    _, w, groups = campus
    asset = groups.assets(w)[0]["id"]
    members = {"empty": [], "duplicate": [asset, asset], "unknown": ["absent"]}[
        members_kind
    ]
    with pytest.raises(ValueError):
        groups.save_many(
            w,
            0,
            [
                {"name": "Valid", "members": [asset]},
                {"name": "Invalid", "members": members},
            ],
        )
    assert not groups.groups(w)


def test_metadata_and_floor_are_explicit_persistent_and_physical_ids_unique(campus):
    store, w, groups = campus
    assets = [a for a in groups.assets(w) if a["room"] == "CBY-101"]
    groups.metadata(
        w, assets[0]["id"], 0, "ASSET-001", 5, "À remplacer", "Urgente", True, "Étage 1"
    )
    updated = {a["id"]: a for a in groups.assets(w)}
    assert updated[assets[0]["id"]]["category"] == 5
    assert updated[assets[1]["id"]]["floor"] == "Étage 1"
    with pytest.raises(ValueError, match="déjà associé"):
        groups.metadata(
            w, assets[1]["id"], 1, "ASSET-001", 1, "Bon", "Normale", True, "Étage 1"
        )
    assert store.load(w)[2] == 1
    assert (
        len(filter_assets(groups.assets(w), {"category": [5], "building": ["CBY"]}))
        == 1
    )


def test_automatic_groups_respect_combined_keys_maximum_and_availability(campus):
    _, w, groups = campus
    assets = groups.assets(w)
    assets[0]["available"] = False
    buckets = automatic_groups(assets, ["building", "model"], 2)
    by_id = {a["id"]: a for a in assets}
    flattened = [item for b in buckets for item in b]
    assert len(flattened) == 3 and len(set(flattened)) == 3
    assert all(len(b) <= 2 for b in buckets)
    assert all(
        len({(by_id[item]["building"], by_id[item]["model"]) for item in b}) == 1
        for b in buckets
    )
    assert automatic_groups([], [], 5) == []
    for maximum in [0, True, 501]:
        with pytest.raises(ValueError):
            automatic_groups(assets, [], maximum)


def test_plan_confirmation_tracks_exact_units_and_status_without_early_movement(campus):
    store, w, groups = campus
    assets = groups.assets(w)
    members = [a["id"] for a in assets if a["model"] == "X"]
    group = save_group(groups, w, members)
    before = deepcopy(store.load(w)[0])
    plan = groups.plan(w, group, 0, 0, CENTRAL_STOCK)
    assert len(plan["groups"]) == 3
    assert store.load(w)[0] == before
    batch = groups.plan(w, group, 0, 0, CENTRAL_STOCK, save=True)
    assert groups.groups(w)[0]["status"] == "Planifié"
    assert store.load(w)[0] == before
    with pytest.raises(ValueError, match="lot actif"):
        groups.delete(w, group, 1)
    store.confirm_batch(w, batch, [0], "Premier ordinateur déplacé")
    assert groups.groups(w)[0]["status"] == "En cours"
    moved_id = plan["groups"][0]["asset_ids"][0]
    current = {a["id"]: a for a in groups.assets(w)}
    assert current[moved_id]["room"] == CENTRAL_STOCK
    assert current[moved_id]["kind"] == "returned"
    store.confirm_batch(w, batch, [1, 2], "Suite du groupe déplacée")
    assert groups.groups(w)[0]["status"] == "Terminé"
    assert all(
        a["room"] == CENTRAL_STOCK for a in groups.assets(w) if a["id"] in members
    )
    assert sum(store.load(w)[0].inventory.values()) == 4
    with pytest.raises(ValueError):
        store.confirm_batch(w, batch, [0], "Doublon")


def test_capacity_conflict_noop_and_stale_revision_do_not_change_inventory(campus):
    store, w, groups = campus
    assets = groups.assets(w)
    chosen = next(a for a in assets if a["room"] == "BRS-1")
    group = save_group(groups, w, [chosen["id"]])
    with pytest.raises(ValueError, match="Place insuffisante"):
        groups.plan(w, group, 0, 0, "CBY-102")
    with pytest.raises(ValueError, match="déjà dans la destination"):
        groups.plan(w, group, 0, 0, "BRS-1")
    groups.room_capacity(w, "CBY-102", 0, 2)
    batch = groups.plan(w, group, 0, 1, "CBY-102", save=True)
    store.receive_many(w, [{"model": "New", "quantity": 1}], 1)
    with pytest.raises(ValueError, match="inventaire a changé"):
        store.confirm_batch(w, batch, [0], "Tentative périmée")
    assert store.load(w)[0].inventory["BRS-1", "X"] == 1
    store.cancel_batch(w, batch)
    assert groups.groups(w)[0]["status"] == "Brouillon"


def test_legacy_batches_keep_identity_and_groups_follow_moved_computers(campus):
    store, w, groups = campus
    asset = next(a for a in groups.assets(w) if a["room"] == "BRS-1")
    save_group(groups, w, [asset["id"]])
    move = Transfer("BRS-1", CENTRAL_STOCK, "X")
    plan = {
        "groups": [
            {
                "room": "BRS-1",
                "old_model": "X",
                "new_model": "X",
                "source": "BRS-1",
                "delivery_m": None,
                "distance_type": "Test",
                "transfers": [vars(move)],
            }
        ]
    }
    batch = store.save_batch(w, 0, "Ancien lot", plan)
    store.confirm_batch(w, batch, [0], "Déplacement réel")
    current = next(a for a in groups.assets(w) if a["id"] == asset["id"])
    assert current["room"] == CENTRAL_STOCK
    assert groups.groups(w)[0]["origins"][asset["id"]] == "BRS-1"


def test_unavailable_members_block_plan_and_preserve_identity(campus):
    store, w, groups = campus
    asset = groups.assets(w)[0]
    group = save_group(groups, w, [asset["id"]])
    groups.metadata(w, asset["id"], 0, "", None, "Hors service", "Haute", True, "")
    assert not next(a for a in groups.assets(w) if a["id"] == asset["id"])["available"]
    with pytest.raises(ValueError, match="indisponible"):
        groups.plan(w, group, 0, 1, CENTRAL_STOCK)
    assert store.load(w)[0].occupied(asset["room"]) >= 1


def test_reset_retires_units_but_does_not_erase_group_history(campus):
    store, w, groups = campus
    store.receive_many(w, [{"model": "New", "quantity": 1}], 0)
    asset = next(a for a in groups.assets(w) if a["room"] == CENTRAL_STOCK)
    group = groups.save_many(w, 1, [{"name": "Stock", "members": [asset["id"]]}])[0]
    store.reset_central_stock(w, 1, "Remise à zéro explicite")
    assert not next(a for a in groups.assets(w) if a["id"] == asset["id"])["active"]
    assert groups.groups(w)[0]["members"] == [asset["id"]]
    with pytest.raises(ValueError):
        groups.plan(w, group, 0, 2, "CBY-101")


def test_returned_stock_group_moves_exact_returned_unit_without_consuming_new_stock(
    campus,
):
    store, w, groups = campus
    old = next(a for a in groups.assets(w) if a["room"] == "BRS-1")
    group = save_group(groups, w, [old["id"]])
    batch = groups.plan(w, group, 0, 0, CENTRAL_STOCK, save=True)
    store.confirm_batch(w, batch, [0], "Retour effectif")
    store.receive_many(w, [{"model": "X", "quantity": 1}], 1)
    groups.room_capacity(w, "BRS-1", 2, 1)
    batch2 = groups.plan(w, group, 1, 3, "BRS-1", save=True)
    store.confirm_batch(w, batch2, [0], "Réinstallation du retour")
    assets = groups.assets(w)
    assert next(a for a in assets if a["id"] == old["id"])["room"] == "BRS-1"
    stock = [a for a in assets if a["room"] == CENTRAL_STOCK and a["active"]]
    assert len(stock) == 1 and stock[0]["kind"] == "new"
    assert store.load(w)[0].returned_stock.get((CENTRAL_STOCK, "X"), 0) == 0


def test_multi_room_cycle_keeps_all_registered_identities(tmp_path):
    from test_homogeneity import campus as cycle_data

    from core.homogeneity import plan_homogeneity, suggested_targets

    store = Store(tmp_path / "cycle.sqlite3")
    data = cycle_data()
    w = store.create_workspace("Cycle", data)
    groups = GroupStore(store)
    before = groups.assets(w)
    plan = plan_homogeneity(data, suggested_targets(data), CENTRAL_STOCK)
    batch = store.save_batch(w, 0, "Cycle", plan)
    store.confirm_batch(w, batch, [0], "Cycle physique terminé")
    after = groups.assets(w)
    assert {a["id"] for a in after if a["active"]} == {a["id"] for a in before}
    assert Counter((a["room"], a["model"]) for a in after if a["active"]) == Counter(
        {key: value for key, value in store.load(w)[0].inventory.items() if value}
    )


def test_individual_swap_full_rooms_preserves_exact_ids_and_counts(campus):
    store, w, groups = campus
    assets = groups.assets(w)
    first = next(a for a in assets if a["room"] == "CBY-101")
    second = next(a for a in assets if a["room"] == "CBY-102")
    group = save_group(groups, w, [first["id"]])
    before, _, revision, _ = store.load(w)
    assignments = {first["id"]: {"destination": second["room"], "swap": second["id"]}}
    plan = groups.plan(w, group, 0, revision, assignments=assignments)
    assert len(plan["groups"]) == 1 and len(plan["groups"][0]["transfers"]) == 2
    batch = groups.plan(w, group, 0, revision, assignments=assignments, save=True)
    assert store.load(w)[0] == before
    store.confirm_batch(w, batch, [0], "Échange réalisé")
    after = {a["id"]: a for a in groups.assets(w)}
    assert after[first["id"]]["room"] == second["room"]
    assert after[second["id"]]["room"] == first["room"]
    assert sum(store.load(w)[0].inventory.values()) == sum(before.inventory.values())
    assert set(after) == {a["id"] for a in assets}


def test_individual_swap_rejects_duplicate_partner_and_simple_full_destination(campus):
    store, w, groups = campus
    assets = groups.assets(w)
    first = [a for a in assets if a["room"] == "CBY-101"]
    second = next(a for a in assets if a["room"] == "CBY-102")
    group = save_group(groups, w, [a["id"] for a in first])
    with pytest.raises(ValueError, match="Place insuffisante"):
        groups.plan(
            w,
            group,
            0,
            0,
            assignments={first[0]["id"]: {"destination": second["room"]}},
        )
    assignments = {
        a["id"]: {"destination": second["room"], "swap": second["id"]} for a in first
    }
    with pytest.raises(ValueError, match="deux opérations"):
        groups.plan(w, group, 0, 0, assignments=assignments)
    assert not store.batches(w)


def test_hostname_import_matches_room_model_and_preserves_counts_and_moves(campus):
    store, w, groups = campus
    before = store.load(w)[0]
    assigned, pending = groups.import_hostnames(
        w,
        b"Hostname,Model\n4299-CBY101-1,X\n4299-CBY101-2,X\n4299-CBY102,Y\n4299-BRS1,X\n",
    )
    assert assigned == 4 and not pending
    assert store.load(w)[0] == before
    assets = groups.assets(w)
    source = next(a for a in assets if a["hostname"] == "4299-CBY102")
    target = next(a for a in assets if a["hostname"] == "4299-BRS1")
    group = save_group(groups, w, [source["id"]])
    batch = groups.plan(
        w,
        group,
        0,
        0,
        assignments={
            source["id"]: {"destination": target["room"], "swap": target["id"]}
        },
        save=True,
    )
    store.confirm_batch(w, batch, [0], "Échange réalisé")
    moved = next(a for a in groups.assets(w) if a["id"] == source["id"])
    assert moved["hostname"] == "4299-CBY102" and moved["room"] == "BRS-1"
    from ui.asset_groups import asset_label, asset_rows

    row = asset_rows([moved])[0]
    assert row["Service Tag"] == "Non renseigné"
    assert "Identifiant Evergreen" not in row and "Numéro d’inventaire réel" not in row
    assert source["id"] not in asset_label(moved)


def test_hostname_import_rejects_duplicate_and_skips_ambiguous_or_wrong_model(campus):
    _, w, groups = campus
    with pytest.raises(ValueError, match="double"):
        groups.import_hostnames(w, b"Hostname,Model\n4299-CBY102,Y\n4299-cby102,Y\n")
    count, pending = groups.import_hostnames(
        w, b"Hostname,Model\n4299-CBY102,Y\n4299-CBY102-1,Y\n4299-BRS1,Z\n"
    )
    assert count == 0 and pending
    count, pending = groups.import_hostnames(
        w, b"Hostname,Model\n4299-CBY102,Y\n4299-CBY102-1,Y\n", prefer_unsuffixed=True
    )
    assert count == 1


def test_consolidate_lee_preserves_computers_hostnames_groups_and_total(tmp_path):
    from dataclasses import replace

    s = Store(tmp_path / "lee.sqlite3")
    data = import_owned_computers(b"room_id,model,quantity\nLEE-105,X,5\n")
    data.rooms["LEE-105"] = replace(data.rooms["LEE-105"], capacity=1)
    data.inventory["LEE-105", "X"] = 1
    for index in range(1, 5):
        data.rooms[f"LEE-105-{index}"] = data.rooms["LEE-105"]
        data.inventory[f"LEE-105-{index}", "X"] = 1
    w = s.create_workspace("Ancien import", data)
    groups = GroupStore(s)
    csv = (
        "Hostname,Model\n4299-LEE105,X\n"
        + "".join(f"4299-LEE105-{i},X\n" for i in range(1, 5))
    ).encode()
    groups.import_hostnames(w, csv)
    assets = groups.assets(w)
    identifier = groups.save_many(
        w, 0, [{"name": "LEE", "description": "", "members": [a["id"] for a in assets]}]
    )[0]
    assert groups.consolidate_confirmed_lee_rooms(w) == 4
    count, pending = groups.import_hostnames(w, csv)
    assert count in {0, 1} and not pending
    after = groups.assets(w)
    assert {a["id"] for a in after} == {a["id"] for a in assets}
    assert {a["room"] for a in after} == {"LEE-105"}
    assert {a["hostname"] for a in after} == {"4299-LEE105"} | {
        f"4299-LEE105-{i}" for i in range(1, 5)
    }
    assert groups.groups(w)[0]["id"] == identifier
    assert s.load(w)[0].inventory["LEE-105", "X"] == 5
    assert sum(s.load(w)[0].inventory.values()) == 5
    revision = s.load(w)[2]
    assert groups.consolidate_confirmed_lee_rooms(w) == 0
    assert s.load(w)[2] == revision


def test_motherboard_codes_only_update_existing_hosts_and_allow_duplicates(campus):
    store, w, groups = campus
    groups.import_hostnames(
        w,
        b"Hostname,Model\n4299-CBY101-1,X\n4299-CBY101-2,X\n4299-CBY102,Y\n4299-BRS1,X\n",
    )
    before = store.load(w)
    ids = {a["id"] for a in groups.assets(w)}
    content = b'Hostname, Model, Motherboard\n4299-CBY101-1, "X", "Dell Inc. 0YGWFV"\n4299-CBY101-2, "X", "Dell Inc. 0YGWFV"\n4299-CBY102, "Wrong", "Dell Inc. WRONG"\n4299-OTHER, "X", "Dell Inc. UNUSED"\n'
    assert groups.import_motherboard_codes(w, content) == 2
    assets = groups.assets(w)
    assert store.load(w) == before
    assert {a["id"] for a in assets} == ids
    assert sum(a["motherboard_code"] == "0YGWFV" for a in assets) == 2
    assert not any(a["motherboard_code"] in {"WRONG", "UNUSED"} for a in assets)
    from ui.asset_groups import asset_rows

    rows = asset_rows(assets)
    assert "Hostname" not in rows[0] and "Numéro d’inventaire réel" not in rows[0]


def test_service_tags_match_existing_hosts_only_and_survive_swap(campus):
    store, w, groups = campus
    groups.import_hostnames(
        w,
        b"Hostname,Model\n4299-CBY101-1,X\n4299-CBY101-2,X\n4299-CBY102,Y\n4299-BRS1,X\n",
    )
    before = store.load(w)
    payload = b'Hostname, Service Tag, Model\n4299-CBY102, "ABC1234", "Y"\n4299-BRS1, "DEF5678", "X"\n4299-OUTSIDE, "OUT1234", "X"\n'
    assert groups.import_service_tags(w, payload) == 2
    assert store.load(w) == before
    assets = groups.assets(w)
    first = next(a for a in assets if a["service_tag"] == "ABC1234")
    second = next(a for a in assets if a["service_tag"] == "DEF5678")
    group = save_group(groups, w, [first["id"]])
    batch = groups.plan(
        w,
        group,
        0,
        0,
        assignments={
            first["id"]: {"destination": second["room"], "swap": second["id"]}
        },
        save=True,
    )
    store.confirm_batch(w, batch, [0], "Échange réalisé")
    moved = next(a for a in groups.assets(w) if a["id"] == first["id"])
    assert moved["service_tag"] == "ABC1234" and moved["room"] == second["room"]
    from ui.asset_groups import asset_label, asset_rows

    assert "ABC1234" in asset_label(moved)
    row = asset_rows([moved])[0]
    assert row["Service Tag"] == "ABC1234" and "Référence carte mère" not in row
    with pytest.raises(ValueError, match="double"):
        groups.import_service_tags(
            w, b"Hostname,Service Tag,Model\nH1,ABC1234,X\nH2,ABC1234,X\n"
        )


def test_catalog_uses_only_inventory_hardware_and_preserves_variants(campus):
    from core.model_catalog import inventory_catalog_rows

    store, w, groups = campus
    groups.import_hostnames(w, b"Hostname,Model\n4299-CBY101-1,X\n4299-CBY101-2,X\n")
    payload = b"Hostname,Service Tag,Model,CPU,RAM Slots,Motherboard,Disks,Optical Drive\n4299-CBY101-1,TAG0001,X,CPU A,8GB,Board A,SSD A,None\n4299-CBY101-2,TAG0002,X,CPU B,16GB,Board B,SSD B,None\n4299-OUTSIDE,TAG0003,X,CPU OUTSIDE,99GB,Board Z,Disk Z,None\n"
    groups.import_service_tags(w, payload)
    before = store.load(w)
    rows = inventory_catalog_rows(before[0], groups.assets(w))
    row = next(row for row in rows if row["Modèle"] == "X")
    assert row["Postes"] == 3 and row["Fiches techniques"] == 2
    assert row["Processeurs observés"] == "CPU A | CPU B"
    assert "OUTSIDE" not in str(rows) and "99GB" not in str(rows)
    assert (
        next(row for row in rows if row["Modèle"] == "Y")["Processeurs observés"]
        == "Non renseigné"
    )
    groups.import_service_tags(
        w, b"Hostname,Service Tag,Model\n4299-CBY101-1,TAG0001,X\n"
    )
    assert (
        next(a for a in groups.assets(w) if a["service_tag"] == "TAG0001")[
            "hardware_json"
        ]
        != "{}"
    )
    assert before == store.load(w)
