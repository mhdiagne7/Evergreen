"""Synthèses par bâtiment, carte et détail des salles."""

import streamlit as st

from core.buildings import building_summary
from core.export import csv_bytes
from map_view import campus_map
from ui.common import finite_places, table


def overview(data, models):
    classes = [room for room in data.rooms.values() if room.room_type == "classroom"]
    installed = sum(
        quantity
        for (room, _), quantity in data.inventory.items()
        if data.rooms[room].room_type == "classroom"
    )
    stock = sum(data.inventory.values()) - installed
    first, second, third, fourth = st.columns(4)
    first.metric("Bâtiments", len({room.building for room in data.rooms.values()}))
    second.metric("Salles recensées", len(classes))
    third.metric("Postes installés", installed)
    fourth.metric("Stock central", stock)
    selected = campus_map(data, models)
    summary, breakdown = building_summary(data, models)
    st.subheader("Vue d'ensemble des bâtiments")
    table(summary)
    with st.expander("Répartition par modèle"):
        table([row for row in breakdown if row["Total"]])
    st.download_button(
        "Exporter la synthèse par bâtiment",
        csv_bytes(breakdown),
        "evergreen-batiments.csv",
        "text/csv",
    )
    buildings = sorted({room.building for room in data.rooms.values()})
    if selected in buildings and st.session_state.get("map_last_selection") != selected:
        st.session_state.overview_building = selected
        st.session_state.map_last_selection = selected
    building = st.selectbox(
        "Voir les salles du bâtiment", buildings, key="overview_building"
    )
    details = []
    for room, info in sorted(data.rooms.items()):
        if info.building != building:
            continue
        computers = (
            ", ".join(
                f"{model} × {quantity}"
                for (location, model), quantity in sorted(data.inventory.items())
                if location == room and quantity
            )
            or "Aucun ordinateur"
        )
        details.append(
            {
                "Salle": room,
                "Usage": "Stock central" if info.room_type == "storage" else "Salle",
                "Inventaire actuel": computers,
                "Capacité de travail": info.capacity,
                "Origine de la capacité": (
                    "Postes recensés à l’import"
                    if info.capacity_basis == "observed"
                    else "Non configurée"
                    if info.capacity is None
                    else "Déclarée"
                ),
                "Places libres configurées": finite_places(data.available(room)),
            }
        )
    table(details)
