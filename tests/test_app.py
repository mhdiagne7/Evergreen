from pathlib import Path
from streamlit.testing.v1 import AppTest
from core.session import activate_import

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_recommendations_and_route():
    app = AppTest.from_file(str(APP)).run(timeout=20)
    assert not app.exception
    app.selectbox(key="choice_source").select("MRT 1140").run()
    assert any("Salle conseillée : MRT 120 · 50 m" in item.value for item in app.success)
    app.selectbox(key="choice_route_source").select("MRT 1140").run()
    app.selectbox(key="choice_route_destination").select("UCU 214").run()
    assert any("195 m" in item.value for item in app.success)
    app.selectbox(key="choice_route_destination").select("MRT 1140").run()
    assert any("0 m" in item.value for item in app.success)
    app.selectbox(key="choice_source").select("CBY 210").run()
    assert any("Aucune destination" in item.value for item in app.info)
    app.selectbox(key="choice_group_model").select("HP EliteDesk 800").run()
    assert not app.exception
    assert any("Aucun déplacement" in item.value for item in app.info)


def test_missing_import_keeps_demo():
    app = AppTest.from_file(str(APP)).run()
    app.button(key="apply_import").click().run()
    assert not app.exception
    assert any("Fichiers manquants" in item.value for item in app.error)
    assert app.session_state.dataset_label.startswith("Démonstration")


def test_single_room_empty_import_and_reset():
    script = f"""
import runpy
import streamlit as st
from core.session import activate_import
if "pending_files" in st.session_state:
    activate_import(st.session_state, st.session_state.pop("pending_files"))
runpy.run_path({str(APP)!r}, run_name="__main__")
"""
    app = AppTest.from_string(script).run()
    files = {
        "rooms.csv": b"room_id,building,capacity,allowed_models\nNEW,N,4,New PC\n",
        "inventory.csv": b"room_id,model,quantity\n",
        "connections.csv": b"source,target,distance_m,distance_type\n",
    }
    # Même fonction d'activation que le bouton d'import, sans simuler le navigateur.
    app.session_state["pending_files"] = files
    app.run()
    assert not app.exception
    assert app.selectbox(key="choice_source").options == ["NEW"]
    assert any("aucun ordinateur" in item.value for item in app.info)
    assert app.session_state.dataset_label.startswith("Données importées")
    app.button(key="reset_demo").click().run()
    assert not app.exception
    assert "MRT 1140" in app.selectbox(key="choice_source").options
