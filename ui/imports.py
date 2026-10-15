"""Création d'espaces réels et initialisation locale, sans démonstration."""

import hashlib
import os
from pathlib import Path

import streamlit as st

from core.data import SCHEMAS, load_csv_files
from core.owned_import import import_owned_computers
from core.store import DEFAULT_DB
from ui.common import refresh


def bootstrap_inventory(store):
    default = DEFAULT_DB.parent / "computers_owned.csv"
    path = Path(os.environ.get("EVERGREEN_INVENTORY", str(default)))
    # Un DB explicitement choisi doit rester indépendant de l'inventaire local.
    if "EVERGREEN_DB" in os.environ and "EVERGREEN_INVENTORY" not in os.environ:
        return
    if not path.is_file():
        return
    payload = path.read_bytes()
    identifier = "owned-" + hashlib.sha256(payload).hexdigest()[:20]
    existing = {workspace["id"] for workspace in store.list_workspaces()}
    if identifier not in existing:
        data = import_owned_computers(payload)
        store.create_workspace(
            "Inventaire des ordinateurs · " + path.stem, data, identifier
        )


def import_form(store):
    with st.expander("Importer un inventaire", expanded=not store.list_workspaces()):
        name = st.text_input(
            "Nom du nouvel inventaire", value="Inventaire du campus", key="import_name"
        )
        kind = st.radio(
            "Format des fichiers",
            ["Ordinateurs recensés (un CSV)", "Référentiel complet (trois CSV)"],
            key="import_kind",
        )
        if kind == "Ordinateurs recensés (un CSV)":
            upload = st.file_uploader(
                "Inventaire · room_id, model, quantity",
                type="csv",
                key="import_owned",
            )
            st.caption(
                "Les salles sont recensées depuis leurs identifiants. Les quantités sont préservées. "
                "MRT-STOCK est créé vide, sans limite de capacité configurée. "
                "Les distances sont à vol d’oiseau entre bâtiments ; les distances intérieures sont inconnues."
            )
            st.caption(
                "La capacité de travail d’une salle correspond aux postes recensés à l’import. "
                "Tous les modèles sont autorisés par défaut, sans évaluation de compatibilité matérielle. "
                "Les salles absentes de l’export ne sont pas créées."
            )
            uploads = None
        else:
            uploads = {
                filename: st.file_uploader(
                    filename, type="csv", key="import_" + filename
                )
                for filename in SCHEMAS
            }
            upload = None
        if st.button("Créer cet espace", key="import_apply"):
            try:
                if uploads is None:
                    if upload is None:
                        raise ValueError("Sélectionne un fichier CSV d’inventaire.")
                    data = import_owned_computers(upload.getvalue())
                else:
                    data = load_csv_files(
                        {
                            filename: file.getvalue()
                            for filename, file in uploads.items()
                            if file is not None
                        }
                    )
                store.create_workspace(name, data)
                st.session_state.pop("workspace", None)
                refresh("Inventaire créé dans un espace indépendant.")
            except ValueError as error:
                st.error(str(error))


def sidebar(store):
    with st.sidebar:
        st.header("Espace de travail")
        workspaces = store.list_workspaces()
        identifiers = [workspace["id"] for workspace in workspaces]
        names = {workspace["id"]: workspace["name"] for workspace in workspaces}
        identifier = None
        if identifiers:
            if st.session_state.get("workspace") not in identifiers:
                st.session_state.workspace = identifiers[-1]
            identifier = st.selectbox(
                "Inventaire actif",
                identifiers,
                format_func=names.get,
                key="workspace",
            )
        import_form(store)
        st.caption(
            "Inventaires et historique conservés sur cet ordinateur. Aucun envoi automatique vers GitHub."
        )
    return identifier
