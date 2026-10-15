"""Changement de jeu de données : tout valider avant de remplacer la session."""

from core.data import load_csv_files


def activate_import(state, files):
    dataset = load_csv_files(files)
    state["dataset"] = dataset
    state["dataset_label"] = "Données importées — non vérifiées indépendamment"
    reset_choices(state)


def reset_choices(state):
    for key in list(state):
        if key.startswith("choice_"):
            del state[key]
