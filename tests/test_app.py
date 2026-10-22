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
    assert app.main.title[0].value == "Votre parc, en un coup d’œil"
    assert app.metric[1].value == "6"
    assert not any(workspace["id"] == "demo" for workspace in store.list_workspaces())
    app.switch_page("ui/pages/data.py").run()
    app.button(key="import_apply").click().run()
    assert any("Sélectionne un fichier" in error.value for error in app.error)
    assert not app.exception


def test_plan_save_confirm_and_restart(application):
    app, store, key = application
    app.run()
    app.switch_page("ui/pages/manual.py").run()
    app.selectbox(key="plan_building").select("CBY").run()
    app.multiselect(key="plan_models").set_value(["New"]).run()
    app.number_input(key="goal_CBY_New").set_value(2).run()
    app.button(key="calculate").click().run()
    assert not app.exception
    app.button(key="save_batch").click().run()
    assert not app.exception
    batch = store.batches(key)[0]
    app.session_state.selected_lot = batch["id"]
    app.switch_page("ui/pages/lot.py").run()
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
    app.switch_page("ui/pages/receipts.py").run()
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
    app.switch_page("ui/pages/models.py").run()
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


def test_default_homogeneity_can_save_a_campus_cycle(tmp_path, monkeypatch):
    from test_homogeneity import campus

    path = tmp_path / "uniform.sqlite3"
    monkeypatch.setenv("EVERGREEN_DB", str(path))
    monkeypatch.delenv("EVERGREEN_INVENTORY", raising=False)
    store = Store(path)
    identifier = store.create_workspace("Campus", campus())
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    app.switch_page("ui/pages/suggestions.py").run()
    app.button(key="uniform_calculate").click().run()
    assert not app.exception
    app.button(key="uniform_save").click().run()
    assert not app.exception
    batch = store.batches(identifier)[0]
    assert batch["plan"]["mode"] == "homogenization"
    assert store.load(identifier)[2] == 0
    store.confirm_batch(identifier, batch["id"], [0], "Cycle complet réalisé")
    assert store.load(identifier)[0].inventory["CBY-103", "X"] == 1


def test_google_routes_are_links_without_api_fields(application):
    app, _, _ = application
    app.run()
    assert not app.exception
    assert not any("API" in item.label for item in app.text_input)
    app.switch_page("ui/pages/routes.py").run()
    assert any("Aucune clé API nécessaire" in item.value for item in app.caption)


def test_block_planning_can_be_selected_and_requires_two_buildings(application):
    app, _, _ = application
    app.run()
    app.switch_page("ui/pages/blocks.py").run()
    assert not app.exception
    app.multiselect(key="block_suggestions").set_value([]).run()
    app.multiselect(key="block_manual").set_value(["CBY"]).run()
    app.button(key="block_calculate").click().run()
    assert not app.exception
    assert any("Choisis un modèle" in error.value for error in app.error)


def test_manual_walking_distance_requires_confirmation(application):
    app, store, key = application
    app.run()
    app.switch_page("ui/pages/routes.py").run()
    app.selectbox(key="google_from").select("CBY").run()
    app.selectbox(key="google_to").select("FTX").run()
    app.number_input(key="walking_metres_CBY_FTX").set_value(800)
    next(
        button
        for button in app.button
        if button.label == "Enregistrer la distance de marche"
    ).click().run()
    assert not store.load(key)[0].walking_routes
    app.checkbox(key="walking_confirm").check()
    next(
        button
        for button in app.button
        if button.label == "Enregistrer la distance de marche"
    ).click().run()
    assert not app.exception
    assert store.load(key)[0].walking_routes["CBY", "FTX"]["distance_m"] == 800


def test_every_page_and_building_navigation(application):
    from ui.navigation import PAGES

    app, store, identifier = application
    app.run()
    for name, path in PAGES.items():
        app.switch_page(path).run()
        assert not app.exception, name
    app.switch_page(PAGES["buildings"]).run()
    app.button(key="building_CBY").click().run()
    assert app.session_state.selected_building == "CBY"
    app.switch_page(PAGES["building"]).run()
    assert app.main.title[0].value == "CBY"
    assert not app.exception


def test_stale_lot_cannot_be_confirmed_in_ui(application):
    from core.buildings import plan_building

    app, store, identifier = application
    data, _, revision, _ = store.load(identifier)
    plan = plan_building(data, "CBY", {"New": 2}, CENTRAL_STOCK)
    batch = store.save_batch(identifier, revision, "Test", plan)
    store.receive(identifier, CENTRAL_STOCK, "New", 1, revision)
    app.run()
    app.session_state.selected_lot = batch
    app.switch_page("ui/pages/lot.py").run()
    assert not app.exception
    assert any("plus ancien" in info.value for info in app.info)
    assert not any(
        button.label == "Mettre à jour l'inventaire" for button in app.button
    )


def test_backup_available_without_central_stock(application):
    from sample_data import routing_data

    app, store, _ = application
    key = store.create_workspace("Réseau importé sans stock MRT", routing_data())
    app.run()
    app.selectbox(key="workspace").select(key).run()
    app.switch_page("ui/pages/data.py").run()
    app.button(key="prepare_backup").click().run()
    assert not app.exception
    assert app.session_state.backup_bytes.startswith(b"SQLite format 3")


def test_assistant_requires_review_and_never_updates_inventory(
    application, monkeypatch
):
    from ui import assistant

    app, store, key = application
    monkeypatch.setattr(
        assistant,
        "interpret",
        lambda *args: {"action": "inventaire", "buildings": ["CBY"], "model": ""},
    )
    before = store.load(key)
    app.run().switch_page("ui/pages/assistant.py").run()
    app.text_area[0].set_value("Quels modèles à CBY ?")
    next(b for b in app.button if b.label == "Comprendre ma demande").click().run()
    assert not app.exception
    assert not app.dataframe
    next(
        b for b in app.button if b.label == "Calculer avec ces paramètres"
    ).click().run()
    assert app.dataframe
    assert store.load(key) == before
    app.text_area[0].set_value("Autre question").run()
    assert not app.dataframe
