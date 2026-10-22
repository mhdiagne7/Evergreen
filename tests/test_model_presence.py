from core.campus import CENTRAL_STOCK
from core.owned_import import import_owned_computers
from ui.model_presence import installed_models, installed_rooms


def test_presence_counts_multipost_rooms_and_excludes_stock_and_zeroes():
    data = import_owned_computers(
        b"room_id,model,quantity\nCBY-1,X,2\nCBY-1,Y,1\nBRS-1,X,1\n"
    )
    data.inventory[CENTRAL_STOCK, "StockOnly"] = 10
    data.inventory["CBY-1", "Empty"] = 0
    models = installed_models(data)
    assert set(models) == {"X", "Y"}
    assert models["X"] == {
        "postes": 3,
        "salles": {"CBY-1", "BRS-1"},
        "batiments": {"CBY", "BRS"},
    }
    assert len(installed_rooms(data, "X")) == 2
    assert installed_rooms(data, "Unknown") == []
