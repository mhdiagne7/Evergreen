"""Point d'entrée Streamlit : données, navigation et vues de l'application."""

import os
from pathlib import Path

import streamlit as st

from core.graph import build_graph
from core.routing import shortest_route
from core.store import DEFAULT_DB, Store
from room_views import recommendations, show_route
from ui.batches import batches_view
from ui.dashboard import overview
from ui.distances import google_distances
from ui.imports import bootstrap_inventory, sidebar
from ui.planning import planning
from ui.stock import stock_view


def main():
    st.set_page_config(page_title="Evergreen", page_icon="🌿", layout="wide")
    store = Store(Path(os.environ.get("EVERGREEN_DB", str(DEFAULT_DB))))
    try:
        bootstrap_inventory(store)
    except (ValueError, OSError) as error:
        st.error(f"Impossible de charger l’inventaire local : {error}")
    identifier = sidebar(store)
    st.title("Evergreen · Bâtiments et inventaire")
    if identifier is None:
        st.info(
            "Importe ton CSV dans la barre latérale pour commencer. Aucun inventaire fictif n’est chargé."
        )
        return
    data, models, revision, label = store.load(identifier)
    context = identifier, revision
    if st.session_state.get("active_context") != context:
        for key in list(st.session_state):
            if key.startswith(("choice_", "goal_", "plan_", "overview_", "map_")):
                del st.session_state[key]
        st.session_state.pop("preview", None)
        st.session_state.pop("uniform_preview", None)
        st.session_state.active_context = context
    st.caption(f"{label} · Version de l’inventaire : {revision}")
    if data.import_notes:
        with st.expander("Détails du contrôle de l’import"):
            for note in data.import_notes:
                st.caption(note)
    if data.distance_mode == "geodesic":
        st.caption(
            "Stock central à MRT · Distances à vol d’oiseau entre bâtiments, "
            "sans estimation des déplacements intérieurs. "
            "Les capacités des salles sont limitées aux postes recensés à l’import."
        )
    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))
    pages = st.tabs(
        [
            "Vue par bâtiment",
            "Planifier Evergreen",
            "Lots et historique",
            "Stock et modèles",
            "Salles et trajets",
        ]
    )
    with pages[0]:
        overview(data, models)
    with pages[1]:
        planning(store, identifier, data, models, revision)
    with pages[2]:
        batches_view(store, identifier, data, revision)
    with pages[3]:
        stock_view(store, identifier, data, models, revision)
    with pages[4]:
        google_distances(data)
        st.divider()
        graph = build_graph(data)
        rooms = sorted(data.rooms)
        if not rooms:
            st.info("Aucune salle dans cet inventaire.")
            return
        recommendations(data, graph, rooms, label)
        st.divider()
        source = st.selectbox("Départ du trajet", rooms, key="choice_route_source")
        destination = st.selectbox(
            "Arrivée du trajet",
            rooms,
            index=min(1, len(rooms) - 1),
            key="choice_route_destination",
        )
        show_route(shortest_route(graph, source, destination))


if __name__ == "__main__":
    main()
