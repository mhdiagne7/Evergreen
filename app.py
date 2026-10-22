"""Evergreen : un espace de travail, une page par tâche."""

import os
from pathlib import Path

import streamlit as st

from core.store import DEFAULT_DB, Store
from ui.imports import bootstrap_inventory
from ui.navigation import PAGES, TITLES


def main():
    st.set_page_config(page_title="Evergreen", page_icon="🌿", layout="wide")
    st.markdown(
        """<style>
    .stMainBlockContainer {max-width:1240px;padding-top:4rem;padding-bottom:3rem;}
    [data-testid="stSidebar"] {background:#f1f5f2;}
    [data-testid="stMetric"] {background:#f5f7f5;border:1px solid #e1e8e2;border-radius:12px;padding:16px;}
    [data-testid="stMetricValue"] {font-size:1.85rem;}
    h1 {letter-spacing:-0.03em;}
    </style>""",
        unsafe_allow_html=True,
    )
    store = Store(Path(os.environ.get("EVERGREEN_DB", str(DEFAULT_DB))))
    try:
        bootstrap_inventory(store)
    except (ValueError, OSError) as error:
        st.error(f"Impossible de charger l’inventaire local : {error}")
    workspaces = store.list_workspaces()
    ids = [w["id"] for w in workspaces]
    labels = {w["id"]: w["name"] for w in workspaces}
    with st.sidebar:
        st.title("Evergreen")
        st.caption("Organiser le parc. Suivre les interventions.")
        if ids:
            if st.session_state.get("workspace") not in ids:
                requested = st.query_params.get("workspace")
                st.session_state.workspace = requested if requested in ids else ids[-1]
            st.selectbox(
                "Inventaire actif", ids, format_func=labels.get, key="workspace"
            )
        st.divider()
    identifier = st.session_state.get("workspace") if ids else None
    if identifier:
        data, models, revision, label = store.load(identifier)
        previous = st.session_state.get("active_workspace")
        if previous != identifier:
            for key in list(st.session_state):
                if key.startswith(("selected_", "uniform_", "block_", "receipt_")):
                    del st.session_state[key]
            st.session_state.active_workspace = identifier
        context = identifier, revision
        if st.session_state.get("active_context") != context:
            for key in list(st.session_state):
                if key.startswith(("choice_", "goal_", "plan_", "overview_", "map_")):
                    del st.session_state[key]
            st.session_state.pop("preview", None)
            st.session_state.pop("uniform_preview", None)
            st.session_state.pop("block_preview", None)
            st.session_state.active_context = context
        st.caption(f"{label} · Version de l’inventaire : {revision}")
        if "notice" in st.session_state:
            st.success(st.session_state.pop("notice"))

    pages = [
        st.Page(path, title=TITLES[name], url_path=name, default=name == "home")
        for name, path in PAGES.items()
    ]
    page = st.navigation(pages, position="hidden")
    with st.sidebar:
        st.caption("PILOTER")
        for name in ("home", "buildings", "regroup", "lots"):
            st.page_link(PAGES[name], label=TITLES[name])
        st.caption("TENIR À JOUR")
        for name in ("stock", "models", "history", "data", "routes"):
            st.page_link(PAGES[name], label=TITLES[name])
        st.divider()
        st.caption(
            "Données enregistrées sur cet ordinateur. Aucun envoi automatique vers GitHub."
        )
    if identifier:
        with st.sidebar:
            if data.import_notes:
                with st.expander("Détails du contrôle de l’import"):
                    for note in data.import_notes:
                        st.caption(note)
            if data.distance_mode == "geodesic":
                st.caption(
                    "Stock central à Morisset · Préparation des interventions Evergreen"
                )
                with st.expander("Repères de planification et distances"):
                    st.caption(
                        "Stock central à Morisset · Distances de marche renseignées quand disponibles, sinon à vol d’oiseau, "
                        "sans estimation des déplacements intérieurs. "
                        "Les capacités des salles sont limitées aux postes recensés à l’import."
                    )
    page.run()


if __name__ == "__main__":
    main()
