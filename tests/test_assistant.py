"""Tests isolés : aucun inventaire de démonstration chargé dans l’application."""

from copy import deepcopy

import pytest
from test_homogeneity import campus

from core import assistant
from core.campus import CENTRAL_STOCK


def test_counts_and_stock_are_computed_without_changes():
    data = campus()
    data.inventory[CENTRAL_STOCK, "X"] = 3
    data.returned_stock[CENTRAL_STOCK, "X"] = 1
    original = deepcopy(data)
    result = assistant.calculate(
        data, ["X", "Y"], {"action": "inventaire", "buildings": ["CBY"], "model": "X"}
    )
    assert result["rows"] == [{"Bâtiment": "CBY", "Modèle": "X", "Installés": 2}]
    assert result["stock"] == [{"Modèle": "X", "Neufs à MRT": 2, "Retours à MRT": 1}]
    assert data == original


def test_plan_is_simulated_and_not_applied():
    data = campus()
    original = deepcopy(data)
    result = assistant.calculate(
        data, ["X", "Y"], {"action": "regroupement", "buildings": [], "model": ""}
    )
    assert result["plan"]["groups"]
    assert data == original


@pytest.mark.parametrize(
    "intent",
    [
        {"action": "delete", "buildings": [], "model": ""},
        {"action": "inventaire", "buildings": ["INCONNU"], "model": ""},
        {"action": "inventaire", "buildings": [], "model": "INVENTÉ"},
        {"action": "inventaire", "buildings": "CBY", "model": ""},
        {"action": "inventaire", "buildings": [], "model": "", "quantity": 999},
    ],
)
def test_untrusted_model_output_is_rejected(intent):
    with pytest.raises(ValueError):
        assistant.calculate(campus(), ["X", "Y"], intent)


def test_request_only_contains_catalogue_and_question(monkeypatch):
    def request(path, payload):
        assert path == "chat"
        assert payload["model"] == "qwen3:4b"
        assert "CBY-101" not in str(payload)
        return {
            "message": {
                "content": '{"action":"inventaire","buildings":["CBY"],"model":"X"}'
            }
        }

    monkeypatch.setattr(assistant, "local_request", request)
    assert assistant.interpret("Combien de X à CBY ?", ["CBY"], ["X"])["model"] == "X"


def test_malformed_response_is_explained(monkeypatch):
    monkeypatch.setattr(
        assistant,
        "local_request",
        lambda *args: {"message": {"content": "pas du JSON"}},
    )
    with pytest.raises(ValueError, match="illisible"):
        assistant.interpret("Inventaire ?", ["CBY"], ["X"])
