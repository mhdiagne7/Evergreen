import pytest
from test_buildings import tiny

from core.buildings import plan_building
from core.store import Store


def setup_store(tmp_path):
    store = Store(tmp_path / "state.sqlite3")
    key = store.create_workspace("Test", tiny())
    plan = plan_building(tiny(), "A", {"New": 2}, "A stock")
    return store, key, plan


def test_partial_confirm_restart_double_confirmation_and_static_data(tmp_path):
    store, key, plan = setup_store(tmp_path)
    batch = store.save_batch(key, 0, "A — New", plan)
    assert store.load(key)[2] == 0
    store.confirm_batch(key, batch, [0], "Salle A1 terminée")
    reopened = Store(store.path)
    data, _, version, _ = reopened.load(key)
    assert data.inventory["A1", "New"] == 1 and version == 1
    assert data.inventory["A2", "Old"] == 1
    assert data.rooms == tiny().rooms
    assert data.connections == tiny().connections
    assert reopened.batches(key)[0]["status"] == "Partiel"
    with pytest.raises(ValueError):
        reopened.confirm_batch(key, batch, [0], "Doublon")
    reopened.confirm_batch(key, batch, [1], "Salle A2 terminée")
    assert reopened.batches(key)[0]["status"] == "Terminé"
    with pytest.raises(ValueError):
        reopened.confirm_batch(key, batch, [1], "Doublon")
    assert len(reopened.history(key)) == 2
    assert sum(reopened.load(key)[0].inventory.values()) == sum(
        tiny().inventory.values()
    )


def test_old_drafts_are_blocked_and_atomic(tmp_path):
    store, key, plan = setup_store(tmp_path)
    first = store.save_batch(key, 0, "Premier", plan)
    second = store.save_batch(key, 0, "Autre proposition", plan)
    store.confirm_batch(key, first, [0], "Fait")
    before = store.load(key)[0].inventory.copy()
    with pytest.raises(ValueError, match="inventaire a changé"):
        Store(store.path).confirm_batch(key, second, [0, 1], "Périmé")
    assert store.load(key)[0].inventory == before


def test_receipts_new_models_and_capacity(tmp_path):
    store, key, _ = setup_store(tmp_path)
    store.add_model(key, "PC 2030")
    store.receive(key, "A stock", "PC 2030", 3, 0, "Livraison 123")
    data, models, revision, _ = store.load(key)
    assert "PC 2030" in models and data.inventory["A stock", "PC 2030"] == 3
    with pytest.raises(ValueError):
        store.receive(key, "A stock", "PC 2030", 3, revision, "Pas assez de place")
    with pytest.raises(ValueError):
        store.receive(key, "A1", "PC 2030", 1, revision, "Pas une réserve")
    assert store.load(key)[2] == revision


def test_failure_rolls_back_entire_confirmation(tmp_path):
    store, key, plan = setup_store(tmp_path)
    batch = store.save_batch(key, 0, "A", plan)
    # Simule un lot stocké incohérent : la première salle doit aussi être annulée.
    import json

    with store.connect() as db:
        plan["groups"][1]["transfers"][1]["quantity"] = 999
        db.execute("UPDATE batches SET plan=? WHERE id=?", (json.dumps(plan), batch))
    with pytest.raises(ValueError):
        store.confirm_batch(key, batch, [0, 1], "Erreur")
    assert store.load(key)[2] == 0
    assert store.load(key)[0].inventory == tiny().inventory
    assert not store.history(key)


def test_cancel_partial_keeps_completed_moves(tmp_path):
    store, key, plan = setup_store(tmp_path)
    batch = store.save_batch(key, 0, "A", plan)
    store.confirm_batch(key, batch, [0], "Fait")
    store.cancel_batch(key, batch)
    assert store.load(key)[0].inventory["A1", "New"] == 1
    assert store.batches(key)[0]["status"] == "Annulé"
    with pytest.raises(ValueError):
        store.confirm_batch(key, batch, [1], "Annulé")


def test_workspaces_separated_and_backup_restorable(tmp_path):
    store, key, plan = setup_store(tmp_path)
    second = store.create_workspace("Autre", tiny())
    store.receive(key, "A stock", "New", 1, 0, "Entrée")
    assert store.load(second)[2] == 0
    destination = tmp_path / "restored.sqlite3"
    destination.write_bytes(store.backup())
    restored = Store(destination)
    assert restored.load(key)[0].inventory["A stock", "New"] == 1
    assert len(restored.list_workspaces()) == 2


def test_edit_generic_operation_revalidates_and_token_detects_new_lot(tmp_path):
    store, key, plan = setup_store(tmp_path)
    token = store.change_token(key)
    batch = store.save_batch(key, 0, "À modifier", plan)
    assert store.change_token(key) != token
    before = store.load(key)
    transfers = plan["groups"][0]["transfers"]
    store.edit_operation(key, batch, 0, 0, transfers=transfers)
    assert store.load(key) == before
    invalid = [dict(move) for move in transfers]
    invalid[0]["quantity"] = 1000
    with pytest.raises(ValueError):
        store.edit_operation(key, batch, 0, 1, transfers=invalid)
    assert store.batches(key)[0]["plan"]["edit_version"] == 1


@pytest.mark.parametrize("confirmed", [False, True])
def test_delete_lot_hides_card_and_preserves_confirmed_inventory(tmp_path, confirmed):
    store, key, plan = setup_store(tmp_path)
    batch = store.save_batch(key, 0, "À supprimer", plan)
    if confirmed:
        store.confirm_batch(key, batch, [0], "Premier déplacement effectué")
    before = store.load(key)
    store.delete_batch(key, batch)
    assert store.batches(key) == []
    archived = store.batches(key, include_hidden=True)[0]
    assert archived["status"] == "Annulé"
    assert archived["plan"]["hidden"]
    assert store.load(key)[0].inventory == before[0].inventory
    assert store.load(key)[2] == before[2]
    with pytest.raises(ValueError):
        store.confirm_batch(key, batch, [1], "Lot supprimé")
    with pytest.raises(ValueError):
        store.delete_batch(key, batch)
