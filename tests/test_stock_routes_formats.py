import pytest

from core.campus import CENTRAL_STOCK
from core.graph import build_graph
from core.model_catalog import model_profile, model_rows
from core.owned_import import import_owned_computers
from core.routing import shortest_route
from core.store import Store


@pytest.fixture
def workspace(tmp_path):
    data = import_owned_computers(
        b"room_id,model,quantity\nBRS-1,OptiPlex 3060,1\nCBY-1,OptiPlex SFF Plus 7020,1\n"
    )
    store = Store(tmp_path / "stock.sqlite3")
    identifier = store.create_workspace("Campus", data)
    return store, identifier


def test_multi_receipt_adds_models_and_aggregates_in_one_revision(workspace):
    store, key = workspace
    store.receive_many(
        key,
        [
            {"model": "New", "quantity": 2},
            {"model": "Other", "quantity": 3},
            {"model": "New", "quantity": 1},
        ],
        0,
    )
    data, models, revision, _ = store.load(key)
    assert data.inventory[CENTRAL_STOCK, "New"] == 3
    assert data.inventory[CENTRAL_STOCK, "Other"] == 3
    assert "Other" in models
    assert revision == 1
    assert data.returned_stock == {}


def test_receipt_invalid_row_and_capacity_roll_back_everything(workspace):
    store, key = workspace
    with pytest.raises(ValueError):
        store.receive_many(
            key, [{"model": "New", "quantity": 2}, {"model": "Other", "quantity": 0}], 0
        )
    assert "New" not in store.load(key)[1]
    store.configure_stock_capacity(key, CENTRAL_STOCK, 1, 0)
    with pytest.raises(ValueError, match="capacité"):
        store.receive_many(key, [{"model": "New", "quantity": 2}], 1)
    assert store.load(key)[0].occupied(CENTRAL_STOCK) == 0
    assert "New" not in store.load(key)[1]


def test_reset_is_audited_preserves_installed_and_rejects_stale_revision(workspace):
    store, key = workspace
    store.receive_many(key, [{"model": "New", "quantity": 4}], 0)
    store.reset_central_stock(key, 1, "Réinitialisation demandée")
    data = store.load(key)[0]
    assert data.occupied(CENTRAL_STOCK) == 0
    assert data.occupied("BRS-1") == 1
    assert store.history(key)[0]["kind"] == "Stock central remis à zéro"
    with pytest.raises(ValueError, match="inventaire a changé"):
        store.receive_many(key, [{"model": "New", "quantity": 1}], 1)


def test_walking_distance_directed_persistent_and_labelled(workspace):
    store, key = workspace
    store.set_walking_distance(key, "BRS", "CBY", 850, 0)
    data = Store(store.path).load(key)[0]
    outward = shortest_route(build_graph(data), "BRS-1", "CBY-1")
    inward = shortest_route(build_graph(data), "CBY-1", "BRS-1")
    assert outward.distance_m == 850
    assert "marche renseignée" in outward.distance_label
    assert "vol d’oiseau" in inward.distance_label
    store.set_walking_distance(key, "BRS", "CBY", 900, 1, True)
    assert store.load(key)[0].walking_routes["CBY", "BRS"]["distance_m"] == 900


@pytest.mark.parametrize("metres", [0, -1, float("nan"), float("inf"), True, 100001])
def test_invalid_walking_distance_is_rejected(workspace, metres):
    store, key = workspace
    with pytest.raises(ValueError):
        store.set_walking_distance(key, "BRS", "CBY", metres, 0)
    assert store.load(key)[2] == 0


def test_model_size_is_not_derived_from_number_and_confirmation_persists(workspace):
    store, key = workspace
    data = store.load(key)[0]
    assert model_profile("OptiPlex 3060")["format"] == "À confirmer"
    assert model_profile("OptiPlex SFF Plus 7020")["dimensions"] == [290, 92.6, 292.8]
    store.set_model_format(key, "OptiPlex 3060", "Micro", 0)
    data = store.load(key)[0]
    assert model_profile("OptiPlex 3060", data.model_formats)["format"] == "Micro"
    assert model_profile("OptiPlex 3060", data.model_formats)["dimensions"] is None
    rows = model_rows(["OptiPlex 3060", "OptiPlex SFF Plus 7020"], data)
    assert rows[0]["Format"] == "SFF / Slim"
    assert rows[1]["Format"] == "Micro"
