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
    assert app.main.title[0].value == "Vue d’ensemble du parc"
    assert app.metric[1].value == "6"
    assert not any(workspace["id"] == "demo" for workspace in store.list_workspaces())
    app.switch_page("ui/pages/data.py").run()
    assert app.main.title[0].value == "Vue d’ensemble du parc"
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


def test_catalog_is_read_only_and_lists_only_present_models(application):
    app, store, key = application
    app.run().switch_page("ui/pages/models.py").run()
    assert not app.exception
    assert not app.selectbox
    assert not app.number_input
    assert not any(
        "Confirmer le format" in e.label
        or "Ajouter un modèle" in e.label
        or "Années des modèles" in e.label
        for e in app.expander
    )
    table = app.dataframe[0].value
    assert set(table["Modèle"]) == {"Old", "Other", "New"}
    assert sum(table["Postes"]) == 8


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
    assert not any("Contrôle conservé" in item.value for item in app.caption)


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


def test_backup_backend_remains_available_without_data_tab(application):
    from sample_data import routing_data

    app, store, _ = application
    key = store.create_workspace("Sans stock MRT", routing_data())
    app.run()
    assert not any(
        "Données et sauvegardes" in link.label for link in app.sidebar.get("page_link")
    )
    assert store.backup().startswith(b"SQLite format 3")
    assert Store(store.path).load(key)[0] == store.load(key)[0]


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
    app.session_state.workspace = first
    app.run().switch_page("ui/pages/data.py").run()
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
    assert not app.radio
    app.button(key="ag_open_swaps").click().run()
    for identifier in groups[0]["members"]:
        app.selectbox(key="ag_to_" + identifier).select(CENTRAL_STOCK).run()
    app.button(key="ag_individual_preview").click().run()
    assert not app.exception
    assert app.button(key="ag_individual_save").disabled
    app.checkbox(key="ag_individual_confirm").check().run()
    app.button(key="ag_individual_save").click().run()
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
    app.button(key="ag_open_swaps").click().run()
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


def test_assistant_tab_is_not_in_sidebar(application):
    app, _, _ = application
    app.run()
    assert not any(
        "Assistant IA" in link.label for link in app.sidebar.get("page_link")
    )


def test_group_room_options_follow_buildings_and_preview_counts_models(application):
    app, _, _ = application
    app.run().switch_page("ui/pages/regroup.py").run()
    app.button(key="ag_create").click().run()
    app.multiselect(key="ag_filter_room").set_value(["MRT-101"]).run()
    app.session_state["ag_map_buildings"] = ["CBY"]
    app.run()
    assert set(app.multiselect(key="ag_filter_room").options) == {"CBY-101", "CBY-102"}
    assert app.multiselect(key="ag_filter_room").value == []
    app.button(key="ag_preview").click().run()
    assert not app.exception
    assert any(
        metric.label == "Modèles différents" and metric.value == "1"
        for metric in app.metric
    )
    distribution = next(
        frame.value
        for frame in app.dataframe
        if "Nombre d’ordinateurs" in frame.value.columns
    )
    assert list(distribution.columns) == ["Modèle", "Nombre d’ordinateurs"]
    assert distribution.iloc[0]["Nombre d’ordinateurs"] == 2


def test_two_table_swap_dialog_queues_removes_and_saves_without_moving_inventory(
    application,
):
    from core.asset_groups import GroupStore

    _, store, workspace = application
    groups = GroupStore(store)
    assets = groups.assets(workspace)
    source = next(a for a in assets if a["room"] == "CBY-101")
    revision = store.load(workspace)[2]
    identifier = groups.save_many(
        workspace,
        revision,
        [{"name": "Mon groupe", "description": "", "members": [source["id"]]}],
    )[0]
    before = store.load(workspace)[0]
    script = (
        """
import streamlit as st
from types import SimpleNamespace
from core.store import Store
from core.asset_groups import GroupStore
from ui.asset_groups import swaps_dialog
store=Store(DB_PATH)
groups=GroupStore(store)
workspace=WORKSPACE
original=st.dataframe
def selectable(rows,*args,**kwargs):
    key=kwargs.get('key','')
    if key.startswith('ag_swap_left_') or key.startswith('ag_swap_right_'):
        st.session_state['seen_left' if key.startswith('ag_swap_left_') else 'seen_right']=rows
        return SimpleNamespace(selection=SimpleNamespace(rows=[0] if rows else []))
    return original(rows,*args,**kwargs)
st.dataframe=selectable
group=next(g for g in groups.groups(workspace) if g['id']==GROUP_ID)
if group['status']=='Brouillon':
    assets=groups.assets(workspace)
    members=[a for a in assets if a['id'] in group['members']]
    data,_,revision,_=store.load(workspace)
    swaps_dialog(groups,workspace,data,revision,assets,members,group)
""".replace("DB_PATH", repr(str(store.path)))
        .replace("WORKSPACE", repr(workspace))
        .replace("GROUP_ID", repr(identifier))
    )
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert len(app.session_state["seen_left"]) == 1
    assert all(
        row["Salle actuelle"] != "CBY-101" for row in app.session_state["seen_right"]
    )
    app.button(key="ag_swap_add").click().run()
    assert not app.exception
    assert len(app.session_state["ag_swap_queue"]["pairs"]) == 1
    assert app.button(key="ag_swap_add").disabled
    assert app.button(key="ag_swap_save").disabled
    app.button(key="ag_swap_remove").click().run()
    assert app.session_state["ag_swap_queue"]["pairs"] == []
    app.button(key="ag_swap_add").click().run()
    next(
        box
        for box in app.checkbox
        if box.label == "Je confirme ces échanges à réaliser"
    ).check().run()
    app.button(key="ag_swap_save").click().run()
    assert not app.exception
    assert groups.groups(workspace)[0]["status"] == "Planifié"
    assert store.load(workspace)[0] == before


def test_saved_changes_survive_restart_and_refresh_all_inventory_views(application):
    from core.asset_groups import GroupStore
    from core.model_catalog import inventory_catalog_rows
    from ui.model_presence import installed_rooms

    app, store, workspace = application
    groups = GroupStore(store)
    initial = store.change_token(workspace)
    source = next(a for a in groups.assets(workspace) if a["room"] == "CBY-101")
    revision = store.load(workspace)[2]
    identifier = groups.save_many(
        workspace,
        revision,
        [{"name": "Groupe enregistré", "description": "", "members": [source["id"]]}],
    )[0]
    created = store.change_token(workspace)
    assert created != initial and created[0] == initial[0]
    groups.update(workspace, identifier, 0, "Groupe renommé", "", [source["id"]])
    assert store.change_token(workspace) != created
    store.receive_many(
        workspace, [{"model": "Nouveau modèle réel", "quantity": 3}], revision
    )
    received = store.change_token(workspace)
    batch = groups.plan(
        workspace, identifier, 1, store.load(workspace)[2], CENTRAL_STOCK, save=True
    )
    before = store.load(workspace)[0]
    assert before.inventory["CBY-101", "Old"] == 1
    store.confirm_batch(workspace, batch, [0], "Déplacement physique confirmé")
    reopened = Store(store.path)
    data, models, _, _ = reopened.load(workspace)
    assert reopened.change_token(workspace) != received
    assert "Nouveau modèle réel" in models
    assert data.inventory[CENTRAL_STOCK, "Nouveau modèle réel"] == 3
    assert not any(row["Salle"] == "CBY-101" for row in installed_rooms(data))
    assets = GroupStore(reopened).assets(workspace)
    assert next(a for a in assets if a["id"] == source["id"])["room"] == CENTRAL_STOCK
    assert any(
        row["Modèle"] == "Nouveau modèle réel" and row["Postes"] == 3
        for row in inventory_catalog_rows(data, assets)
    )
    assert GroupStore(reopened).groups(workspace)[0]["name"] == "Groupe renommé"
    app.run().switch_page("ui/pages/models.py").run()
    assert not app.exception
    assert "Nouveau modèle réel" in set(app.dataframe[0].value["Modèle"])


def test_lot_operation_menu_edits_deletes_and_restores_without_inventory_change(
    application,
):
    from core.asset_groups import GroupStore

    app, store, workspace = application
    groups = GroupStore(store)
    assets = groups.assets(workspace)
    first = next(a for a in assets if a["room"] == "CBY-101")
    partner = next(
        a for a in assets if a["room"] == "FTX-147" and a["model"] == "Other"
    )
    rev = store.load(workspace)[2]
    group = groups.save_many(
        workspace,
        rev,
        [{"name": "Lot à gérer", "description": "", "members": [first["id"]]}],
    )[0]
    batch = groups.plan(workspace, group, 0, rev, CENTRAL_STOCK, save=True)
    before = store.load(workspace)[0]
    app.run()
    app.session_state.selected_lot = batch
    app.switch_page("ui/pages/lot.py").run()
    app.button(key=f"lot_modify_{batch}_0").click().run()
    assert not app.exception
    prefix = f"lot_edit_{batch}_0_0_"
    app.selectbox(key=prefix + "destination").select("FTX-147").run()
    app.selectbox(key=prefix + "swap").select(partner["id"]).run()
    app.button(key=prefix + "save").click().run()
    assert not app.exception
    assert store.batches(workspace)[0]["plan"]["groups"][0]["swap"]
    app.button(key=f"lot_delete_{batch}_0").click().run()
    assert not app.exception
    assert store.batches(workspace)[0]["status"] == "Annulé"
    app.button(key=f"lot_restore_{batch}_0").click().run()
    assert not app.exception
    assert store.batches(workspace)[0]["status"] == "Préparé"
    assert store.load(workspace)[0] == before


def test_group_editor_dialog_preserves_hidden_members_and_cancelled_changes(
    application,
):
    from core.asset_groups import GroupStore

    app, store, workspace = application
    groups = GroupStore(store)
    ids = [a["id"] for a in groups.assets(workspace) if a["room"].startswith("CBY-")]
    identifier = groups.save_many(
        workspace,
        store.load(workspace)[2],
        [
            {
                "name": "Nom initial",
                "description": "Description initiale",
                "members": ids,
            }
        ],
    )[0]
    before = store.load(workspace)[0]
    app.run().switch_page("ui/pages/regroup.py").run()
    assert not any(e.label == "Modifier ou supprimer le groupe" for e in app.expander)
    app.button(key="ag_open_group_editor").click().run()
    app.text_input(key="ag_editor_name").set_value("Nom modifié").run()
    app.text_area(key="ag_editor_description").set_value("Description modifiée").run()
    app.button(key="ag_editor_open_map").click().run()
    assert not app.exception
    app.button(key="ag_editor_map_cancel").click().run()
    assert app.text_input(key="ag_editor_name").value == "Nom modifié"
    app.button(key="ag_editor_cancel").click().run()
    assert groups.groups(workspace)[0]["name"] == "Nom initial"
    app.button(key="ag_open_group_editor").click().run()
    assert app.text_input(key="ag_editor_name").value == "Nom initial"
    app.multiselect(key="ag_editor_filter_room").set_value(["CBY-101"]).run()
    app.text_input(key="ag_editor_name").set_value("Groupe renommé").run()
    app.button(key="ag_editor_save").click().run()
    assert not app.exception
    saved = next(g for g in groups.groups(workspace) if g["id"] == identifier)
    assert saved["name"] == "Groupe renommé" and set(saved["members"]) == set(ids)
    assert store.load(workspace)[0] == before


def test_group_editor_can_remove_filtered_members_and_reject_empty_group(application):
    from core.asset_groups import GroupStore

    app, store, workspace = application
    groups = GroupStore(store)
    assets = [a for a in groups.assets(workspace) if a["room"].startswith("CBY-")]
    identifier = groups.save_many(
        workspace,
        store.load(workspace)[2],
        [{"name": "Groupe", "description": "", "members": [a["id"] for a in assets]}],
    )[0]
    before = store.load(workspace)[0]
    app.run().switch_page("ui/pages/regroup.py").run()
    app.button(key="ag_open_group_editor").click().run()
    app.multiselect(key="ag_editor_filter_room").set_value(["CBY-101"]).run()
    app.button(key="ag_editor_clear_visible").click().run()
    app.button(key="ag_editor_save").click().run()
    assert not app.exception
    saved = next(g for g in groups.groups(workspace) if g["id"] == identifier)
    assert len(saved["members"]) == 1
    assert (
        next(a for a in assets if a["id"] == saved["members"][0])["room"] == "CBY-102"
    )
    app.button(key="ag_open_group_editor").click().run()
    app.button(key="ag_editor_clear_visible").click().run()
    app.button(key="ag_editor_save").click().run()
    assert not app.exception and app.error
    assert len(groups.groups(workspace)[0]["members"]) == 1
    assert store.load(workspace)[0] == before


def test_swap_dialog_selects_either_group_or_rest_of_campus_and_keeps_separate_queues(
    application,
):
    from core.asset_groups import GroupStore

    _, store, workspace = application
    groups = GroupStore(store)
    assets = groups.assets(workspace)
    first = next(a for a in assets if a["room"] == "CBY-101")
    second = next(a for a in assets if a["room"] == "CBY-102")
    rev = store.load(workspace)[2]
    source, target = groups.save_many(
        workspace,
        rev,
        [
            {"name": "Groupe 1", "description": "", "members": [first["id"]]},
            {
                "name": "Groupe 2",
                "description": "",
                "members": [first["id"], second["id"]],
            },
        ],
    )
    before = store.load(workspace)[0]
    script = (
        """
import streamlit as st
from types import SimpleNamespace
from core.store import Store
from core.asset_groups import GroupStore
from ui.asset_groups import swaps_dialog
store=Store(DB_PATH)
groups=GroupStore(store)
workspace=WORKSPACE
original=st.dataframe
def selectable(rows,*args,**kwargs):
    key=kwargs.get('key','')
    if key.startswith('ag_swap_left_') or key.startswith('ag_swap_right_'):
        st.session_state['observed_left' if key.startswith('ag_swap_left_') else 'observed_right']=rows
        return SimpleNamespace(selection=SimpleNamespace(rows=[0] if rows else []))
    return original(rows,*args,**kwargs)
st.dataframe=selectable
group=next(g for g in groups.groups(workspace) if g['id']==GROUP_ID)
if group['status']=='Brouillon':
    assets=groups.assets(workspace)
    data,_,revision,_=store.load(workspace)
    swaps_dialog(groups,workspace,data,revision,assets,[],group)
""".replace("DB_PATH", repr(str(store.path)))
        .replace("WORKSPACE", repr(workspace))
        .replace("GROUP_ID", repr(source))
    )
    app = AppTest.from_string(script).run()
    assert app.selectbox(key="ag_swap_source_group").value == source
    assert app.selectbox(key="ag_swap_target_group").value is None
    app.button(key="ag_swap_add").click().run()
    assert len(app.session_state["ag_swap_queue"]["pairs"]) == 1
    app.selectbox(key="ag_swap_target_group").select(target).run()
    assert not app.exception
    assert app.session_state["ag_swap_queue"]["pairs"] == []
    assert {row["Salle actuelle"] for row in app.session_state["observed_right"]} == {
        "CBY-102"
    }
    app.selectbox(key="ag_swap_target_group").select(None).run()
    assert len(app.session_state["ag_swap_queue"]["pairs"]) == 1
    app.selectbox(key="ag_swap_target_group").select(target).run()
    app.selectbox(key="ag_swap_source_group").select(target).run()
    assert app.selectbox(key="ag_swap_target_group").value is None
    assert all(
        row["Salle actuelle"] not in {"CBY-101", "CBY-102"}
        for row in app.session_state["observed_right"]
    )
    app.selectbox(key="ag_swap_source_group").select(source).run()
    app.selectbox(key="ag_swap_target_group").select(target).run()
    app.button(key="ag_swap_add").click().run()
    next(
        box
        for box in app.checkbox
        if box.label == "Je confirme ces échanges à réaliser"
    ).check().run()
    app.button(key="ag_swap_save").click().run()
    assert not app.exception
    assert store.batches(workspace)[0]["name"] == "Groupe 1 ⇄ Groupe 2"
    assert store.load(workspace)[0] == before


def test_history_can_undo_a_confirmed_swap_with_explicit_reason(application):
    from core.asset_groups import GroupStore

    app, store, workspace = application
    groups = GroupStore(store)
    assets = groups.assets(workspace)
    first = next(a for a in assets if a["room"] == "CBY-101")
    second = next(a for a in assets if a["room"] == "FTX-147" and a["model"] == "Other")
    before = store.load(workspace)[0]
    rev = store.load(workspace)[2]
    group = groups.save_many(
        workspace,
        rev,
        [{"name": "Test annulable", "description": "", "members": [first["id"]]}],
    )[0]
    batch = groups.plan(
        workspace,
        group,
        0,
        rev,
        assignments={
            first["id"]: {"destination": second["room"], "swap": second["id"]}
        },
        save=True,
    )
    store.confirm_batch(workspace, batch, [0], "Swap de test")
    app.run().switch_page("ui/pages/history.py").run()
    app.button(key="history_swap_undo_open").click().run()
    assert not app.exception
    rev = store.load(workspace)[2]
    prefix = f"lot_undo_{batch}_0_{rev}_0_"
    assert app.button(key=prefix + "save").disabled
    app.text_input(key=prefix + "note").set_value(
        "Confirmation de test saisie par erreur"
    ).run()
    app.checkbox(key=prefix + "confirm").check().run()
    app.button(key=prefix + "save").click().run()
    assert not app.exception
    assert store.batches(workspace)[0]["status"] == "Annulé"
    assert {key: q for key, q in store.load(workspace)[0].inventory.items() if q} == {
        key: q for key, q in before.inventory.items() if q
    }
    assert any(
        event["kind"] == "Swaps confirmés annulés" for event in store.history(workspace)
    )
