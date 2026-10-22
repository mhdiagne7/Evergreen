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
    assert not any("Contrôle conservé" in item.value for item in app.caption)
    app.switch_page("ui/pages/data.py").run()
    assert any("Contrôle conservé" in item.value for item in app.caption)


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
    assert any("Google Maps" in item.value for item in app.caption)


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


def test_routes_only_shows_google_maps_building_selection(application):
    app, store, key = application
    before = store.load(key)
    app.run().switch_page("ui/pages/routes.py").run()
    assert not app.exception
    assert {item.key for item in app.selectbox} == {"google_from", "google_to"}
    assert not app.number_input
    assert not any(
        "déplacer ces ordinateurs" in heading.value for heading in app.subheader
    )
    assert not any("planification" in expander.label for expander in app.expander)
    assert not app.dataframe
    assert store.load(key) == before


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
    app.switch_page("ui/pages/data.py").run()
    app.selectbox(key="workspace").select(key).run()
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


def test_home_displays_map_without_removed_sections_and_inventory_banner(application):
    app, _, _ = application
    app.run()
    assert not app.exception
    assert any(
        heading.value == "Carte du parc informatique" for heading in app.subheader
    )
    text = " ".join(item.value for item in app.caption)
    assert "Version de l’inventaire" not in text
    assert "Survole un bâtiment" not in text
    assert "Extraction du" not in text
    assert not any(
        heading.value in {"Que souhaitez-vous faire ?", "À préparer"}
        for heading in app.subheader
    )


def test_model_presence_navigation_filter_and_return(application):
    app, _, _ = application
    app.run().switch_page("ui/pages/computer_models.py").run()
    assert not app.exception
    assert not any(button.key == "presence_model_New" for button in app.button)
    app.text_input(key="presence_search").set_value("Old").run()
    app.button(key="presence_model_Old").click().run()
    assert app.session_state.selected_computer_model == "Old"
    app.switch_page("ui/pages/computer_model.py").run()
    assert app.main.title[0].value == "Old"
    assert app.metric[0].value == "5"
    assert app.metric[1].value == "5"
    app.selectbox(key="presence_building_filter").select("CBY").run()
    assert len(app.dataframe[-1].value) == 2
    app.text_input(key="presence_room_search").set_value("Absent").run()
    assert any("Aucune salle" in info.value for info in app.info)
    assert not app.exception


def test_sidebar_is_minimal_and_buildings_routes_button_navigates(application):
    app, _, _ = application
    app.run()
    assert not app.sidebar.selectbox
    assert not app.sidebar.expander
    assert not any(
        "Carte du campus" in link.label for link in app.sidebar.get("page_link")
    )
    app.switch_page("ui/pages/buildings.py").run()
    app.button(key="buildings_routes").click().run()
    app.switch_page("ui/pages/routes.py").run()
    assert app.main.title[0].value == "Salles et trajets"


def test_workspace_choice_survives_leaving_data_page(application):
    app, store, first = application
    store.create_workspace("Autre inventaire", import_owned_computers(OWNED))
    app.run().switch_page("ui/pages/data.py").run()
    app.selectbox(key="workspace").select(first).run()
    app.switch_page("ui/pages/home.py").run()
    app.switch_page("ui/pages/buildings.py").run()
    assert app.session_state.workspace == first
    assert not app.exception


def test_groups_manual_preview_save_edit_and_plan_do_not_move_inventory(application):
    from core.asset_groups import GroupStore

    app, store, workspace = application
    before = store.load(workspace)[0]
    app.run().switch_page("ui/pages/regroup.py").run()
    assert not app.exception
    assert not any(
        "Comment les propositions" in expander.label for expander in app.expander
    )
    app.button(key="ag_create").click().run()
    app.session_state["ag_map_buildings"] = ["CBY"]
    app.run()
    app.checkbox(key="ag_select_all").check().run()
    app.text_input(key="ag_create_name").set_value("CBY à vérifier")
    app.button(key="ag_preview").click().run()
    assert not app.exception
    app.button(key="ag_save").click().run()
    assert not app.exception
    groups = GroupStore(store).groups(workspace)
    assert len(groups) == 1 and len(groups[0]["members"]) == 2
    assert store.load(workspace)[0] == before
    assert app.metric[0].value == "2"
    app.radio(key="ag_move_mode").set_value("Une destination pour tout le groupe").run()
    app.selectbox(key="ag_destination_" + groups[0]["id"]).select(CENTRAL_STOCK).run()
    app.button(key="ag_plan_" + groups[0]["id"]).click().run()
    assert not app.exception
    assert app.button(key="ag_plan_save_" + groups[0]["id"]).disabled
    app.checkbox(key="ag_plan_confirm_" + groups[0]["id"]).check().run()
    app.button(key="ag_plan_save_" + groups[0]["id"]).click().run()
    assert not app.exception
    assert GroupStore(store).groups(workspace)[0]["status"] == "Planifié"
    assert store.load(workspace)[0] == before


def test_group_creation_is_simple_and_map_opens_in_dialog(application):
    app, store, workspace = application
    app.run().switch_page("ui/pages/regroup.py").run()
    app.button(key="ag_create").click().run()
    assert not app.radio
    assert {m.label for m in app.multiselect} == {"Salle", "Modèle"}
    labels = {c.label for c in app.checkbox}
    assert "Uniquement les ordinateurs disponibles" not in labels
    assert "Uniquement les postes installés en salle" not in labels
    app.button(key="ag_open_map").click().run()
    assert not app.exception
    assert app.selectbox(key="ag_picker_model")
    assert app.button(key="ag_confirm_map").disabled
    app.button(key="ag_close_map").click().run()
    assert not app.exception
    assert app.text_input(key="ag_create_name").value == "Nouveau groupe"


def test_group_defaults_include_every_model_and_multiple_buildings(application):
    from core.asset_groups import GroupStore

    app, store, workspace = application
    app.run().switch_page("ui/pages/regroup.py").run()
    app.button(key="ag_create").click().run()
    assert app.checkbox(key="ag_select_all").value
    assert app.multiselect(key="ag_filter_model").value == []
    assert app.multiselect(key="ag_filter_room").value == []
    assert not any("Renouvellement et uniformisation" in e.label for e in app.expander)
    app.session_state["ag_map_buildings"] = ["CBY", "MRT"]
    app.run()
    app.button(key="ag_preview").click().run()
    app.button(key="ag_save").click().run()
    assert not app.exception
    groups = GroupStore(store).groups(workspace)
    assets = {a["id"]: a for a in GroupStore(store).assets(workspace)}
    assert {assets[i]["building"] for i in groups[0]["members"]} == {"CBY", "MRT"}


def test_map_dialog_requires_confirmation_for_multiple_buildings():
    app = AppTest.from_string("""
import streamlit as st
import map_view
from ui.asset_groups import building_map_dialog
map_view.campus_map = lambda *args, **kwargs: ["CBY", "MRT"]
if "ag_map_buildings" not in st.session_state:
    building_map_dialog(None, [])
""")
    app.run()
    assert "ag_map_buildings" not in app.session_state
    app.button(key="ag_confirm_map").click().run()
    assert not app.exception
    assert app.session_state["ag_map_buildings"] == ["CBY", "MRT"]


def test_group_individual_swap_preview_save_and_list(application):
    from core.asset_groups import GroupStore

    app, store, workspace = application
    app.run().switch_page("ui/pages/regroup.py").run()
    app.button(key="ag_create").click().run()
    app.session_state["ag_map_buildings"] = ["CBY"]
    app.run()
    app.button(key="ag_preview").click().run()
    app.button(key="ag_save").click().run()
    groups = GroupStore(store)
    group = groups.groups(workspace)[0]
    asset = group["members"][0]
    partner = next(
        a
        for a in groups.assets(workspace)
        if a["room"] == "FTX-147" and a["model"] == "Other"
    )
    app.selectbox(key="ag_to_" + asset).select("FTX-147").run()
    app.selectbox(key="ag_swap_" + asset).select(partner["id"]).run()
    before = store.load(workspace)[0]
    app.button(key="ag_individual_preview").click().run()
    assert not app.exception
    assert app.button(key="ag_individual_save").disabled
    app.checkbox(key="ag_individual_confirm").check().run()
    app.button(key="ag_individual_save").click().run()
    assert not app.exception
    assert groups.groups(workspace)[0]["status"] == "Planifié"
    assert store.load(workspace)[0] == before
