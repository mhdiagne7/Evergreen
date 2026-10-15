from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from test_owned import OWNED

from core.campus import CENTRAL_STOCK
from core.owned_import import import_owned_computers
from core.store import Store

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def application(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("EVERGREEN_DB", str(path))
    monkeypatch.delenv("EVERGREEN_INVENTORY", raising=False)
    store = Store(path)
    key = store.create_workspace("Test campus", import_owned_computers(OWNED))
    store.add_model(key, "New")
    store.receive(key, CENTRAL_STOCK, "New", 2, 0)
    return AppTest.from_file(str(APP)), store, key


def test_dashboard_and_import_validation(application):
    app, store, key = application
    app.run()
    assert not app.exception
    assert app.title[0].value == "Evergreen · Bâtiments et inventaire"
    assert app.metric[2].value == "6"
    assert not any(workspace["id"] == "demo" for workspace in store.list_workspaces())
    app.button(key="import_apply").click().run()
    assert any("Sélectionne un fichier" in error.value for error in app.error)
    assert not app.exception


def test_plan_save_confirm_and_restart(application):
    app, store, key = application
    app.run()
    app.selectbox(key="plan_building").select("CBY").run()
    app.multiselect(key="plan_models").set_value(["New"]).run()
    app.number_input(key="goal_CBY_New").set_value(2).run()
    app.button(key="calculate").click().run()
    assert not app.exception
    app.button(key="save_batch").click().run()
    assert not app.exception
    batch = store.batches(key)[0]
    app.multiselect(key="complete_" + batch["id"]).set_value([0])
    app.text_input(key="note_" + batch["id"]).set_value("Test de réalisation")
    next(
        button for button in app.button if button.label == "Mettre à jour l'inventaire"
    ).click().run()
    assert store.load(key)[2] == 1
    app.multiselect(key="complete_" + batch["id"]).set_value([0])
    app.text_input(key="note_" + batch["id"]).set_value("Test de réalisation")
    app.checkbox(key="done_" + batch["id"]).check()
    next(
        button for button in app.button if button.label == "Mettre à jour l'inventaire"
    ).click().run()
    assert not app.exception
    assert store.load(key)[2] == 2
    reopened = AppTest.from_file(str(APP)).run()
    assert not reopened.exception
    assert store.batches(key)[0]["status"] == "Partiel"


def test_receipt_needs_no_origin_and_persists(application):
    app, store, key = application
    app.run()
    app.selectbox(key="receipt_model").select("New")
    app.number_input(key="receipt_quantity").set_value(3)
    next(
        button for button in app.button if button.label == "Enregistrer l'arrivage"
    ).click().run()
    assert store.load(key)[0].inventory[CENTRAL_STOCK, "New"] == 2
    app.checkbox(key="receipt_confirm").check()
    next(
        button for button in app.button if button.label == "Enregistrer l'arrivage"
    ).click().run()
    assert not app.exception
    assert store.load(key)[0].inventory[CENTRAL_STOCK, "New"] == 5
    assert not any("Provenance" in widget.label for widget in app.text_input)


def test_new_database_has_no_demo(tmp_path, monkeypatch):
    path = tmp_path / "empty.sqlite3"
    monkeypatch.setenv("EVERGREEN_DB", str(path))
    monkeypatch.delenv("EVERGREEN_INVENTORY", raising=False)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert Store(path).list_workspaces() == []
    assert any("Importe ton CSV" in item.value for item in app.info)


def test_generation_year_can_be_saved_in_interface(application):
    app, store, key = application
    app.run()
    app.selectbox(key="model_to_date").select("New").run()
    app.number_input(key="model_year_New").set_value(2025)
    next(
        button
        for button in app.button
        if button.label == "Enregistrer l’année du modèle"
    ).click().run()
    assert not app.exception
    assert store.load(key)[0].model_years["New"] == 2025


def test_import_diagnostics_are_collapsed_without_yellow_banner(application):
    app, store, key = application
    data, _, _, _ = store.load(key)
    data.import_notes = ("Contrôle conservé dans le détail",)
    with store.connect() as db:
        from core.store import encode_data

        db.execute("UPDATE workspaces SET data=? WHERE id=?", (encode_data(data), key))
    app.run()
    assert not app.exception
    assert not app.warning
    assert any(
        expander.label == "Détails du contrôle de l’import" for expander in app.expander
    )
