from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_app_default_and_interactions():
    app = AppTest.from_file(str(APP)).run(timeout=20)
    assert not app.exception
    assert "195 m" in app.success[0].value
    app.selectbox(key="route_destination").select("MRT 1140").run()
    assert "0 m" in app.success[0].value
    app.selectbox(key="compat_source").select("CBY 210").run()
    assert not app.exception
    assert any("Aucune destination" in item.value for item in app.info)
    app.selectbox[4].select("HP EliteDesk 800").run()
    assert not app.exception
    assert any("Aucun déplacement" in item.value for item in app.info)
