"""Evergreen : un espace de travail, une page par tâche."""

import os
from pathlib import Path

import streamlit as st

from core.store import DEFAULT_DB, Store
from ui.common import watch_inventory_changes
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
    if ids:
        requested = st.session_state.get("workspace", st.query_params.get("workspace"))
        # Garder le choix d’inventaire même quand son widget n’est pas affiché.
        st.session_state.workspace = requested if requested in ids else ids[-1]
    with st.sidebar:
        st.title("Evergreen")
        st.divider()
    identifier = st.session_state.get("workspace") if ids else None
    if identifier:
        rendered_token = store.change_token(identifier)
        data, models, revision, label = store.load(identifier)
        previous = st.session_state.get("active_workspace")
        if previous != identifier:
            for key in list(st.session_state):
                if key.startswith(
                    ("selected_", "uniform_", "block_", "receipt_", "ag_")
                ):
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
        if "notice" in st.session_state:
            st.success(st.session_state.pop("notice"))

    pages = [
        st.Page(path, title=TITLES[name], url_path=name, default=name == "home")
        for name, path in PAGES.items()
    ]
    page = st.navigation(pages, position="hidden")
    with st.sidebar:
        st.caption("PILOTER")
        for name in (
            "home",
            "buildings",
            "computer_models",
            "models",
            "regroup",
            "lots",
        ):
            st.page_link(PAGES[name], label=TITLES[name])
        for name in ("stock", "history", "routes"):
            st.page_link(PAGES[name], label=TITLES[name])
    if identifier:
        watch_inventory_changes(store, identifier, rendered_token)
    page.run()


if __name__ == "__main__":
    main()
