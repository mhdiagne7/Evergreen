from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from core.store import Store

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def application(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("EVERGREEN_DB", str(path))
    return AppTest.from_file(str(APP)), Store(path)


def test_dashboard_and_import_validation(application):
    app, store = application
    app.run()
    assert not app.exception
    assert app.title[0].value == "Evergreen · Bâtiments et inventaire"
    assert len(store.load("demo")[0].rooms) == 53
    app.button(key="import_apply").click().run()
    assert any("Fichiers manquants" in e.value for e in app.error)
    assert not app.exception


def test_plan_save_confirm_and_restart(application):
    app, store = application
    app.run()
    app.multiselect(key="plan_models").set_value(["Dell OptiPlex 7060", "Dell OptiPlex 7090"]).run()
    app.number_input(key="goal_CBY_Dell OptiPlex 7060").set_value(15).run()
    app.button(key="calculate").click().run()
    assert not app.exception
    app.button(key="save_batch").click().run()
    assert not app.exception
    batch = store.batches("demo")[0]
    assert store.load("demo")[2] == 0
    app.multiselect(key="complete_" + batch["id"]).set_value([0])
    app.text_input(key="note_" + batch["id"]).set_value("Test de réalisation")
    # Le bouton seul ne doit pas valider le déplacement physique.
    submit = next(b for b in app.button if b.label == "Mettre à jour l'inventaire")
    submit.click().run()
    assert store.load("demo")[2] == 0
    app.multiselect(key="complete_" + batch["id"]).set_value([0])
    app.text_input(key="note_" + batch["id"]).set_value("Test de réalisation")
    app.checkbox(key="done_" + batch["id"]).check()
    next(b for b in app.button if b.label == "Mettre à jour l'inventaire").click().run()
    assert not app.exception
    assert store.load("demo")[2] == 1
    new_app = AppTest.from_file(str(APP)).run()
    assert not new_app.exception
    assert store.batches("demo")[0]["status"] == "Partiel"


def test_empty_workspace_and_old_format(application):
    from core.data import Dataset, Room
    app, store = application
    app.run()
    key = store.create_workspace("Une salle", Dataset({"Only": Room("New", 1, frozenset({"*"}))}, {}, []))
    app.run()
    app.selectbox(key="workspace").select(key).run()
    assert not app.exception
    assert any("au moins un modèle" in i.value for i in app.info)
