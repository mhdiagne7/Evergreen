"""Consulter les modèles installés et les salles de classe qui les accueillent."""

from collections import Counter

import streamlit as st

from core.export import csv_bytes
from ui.common import table
from ui.navigation import go, heading


def installed_rooms(data, model=None):
    """Une ligne par salle et modèle installé ; le stock n'est jamais inclus."""
    return [
        {
            "Modèle": item,
            "Bâtiment": data.rooms[room].building,
            "Salle": room,
            "Postes": quantity,
        }
        for (room, item), quantity in sorted(data.inventory.items())
        if quantity > 0
        and data.rooms[room].room_type == "classroom"
        and (model is None or item == model)
    ]


def installed_models(data):
    models = {}
    for row in installed_rooms(data):
        item = models.setdefault(
            row["Modèle"], {"postes": 0, "salles": set(), "batiments": set()}
        )
        item["postes"] += row["Postes"]
        item["salles"].add(row["Salle"])
        item["batiments"].add(row["Bâtiment"])
    return models


def models_presence(data):
    heading("Modèles dans les salles", "home")
    query = st.text_input(
        "Rechercher un modèle",
        placeholder="Nom ou numéro du modèle",
        key="presence_search",
    )
    models = installed_models(data)
    matches = [
        model for model in sorted(models) if query.casefold() in model.casefold()
    ]
    if not matches:
        st.info("Aucun modèle installé ne correspond à cette recherche.")
        return
    columns = st.columns(3)
    for index, model in enumerate(matches):
        counts = models[model]
        with columns[index % 3], st.container(border=True):
            st.subheader(model)
            st.write(
                f"{counts['postes']} poste(s) · {len(counts['salles'])} salle(s) · {len(counts['batiments'])} bâtiment(s)"
            )
            if st.button("Ouvrir →", key="presence_model_" + model):
                go("computer_model", selected_computer_model=model)


def model_presence_detail(data):
    model = st.session_state.get("selected_computer_model")
    rows = installed_rooms(data, model) if model else []
    if not rows:
        heading("Choisir un modèle", "computer_models")
        st.info("Sélectionnez un modèle installé dans la liste.")
        return
    heading(model, "computer_models")
    buildings = sorted({row["Bâtiment"] for row in rows})
    first, second, third = st.columns(3)
    first.metric("Postes installés", sum(row["Postes"] for row in rows))
    second.metric("Salles de classe", len(rows))
    third.metric("Bâtiments", len(buildings))
    st.subheader("Présence par bâtiment")
    counts = Counter()
    classrooms = Counter()
    for row in rows:
        counts[row["Bâtiment"]] += row["Postes"]
        classrooms[row["Bâtiment"]] += 1
    table(
        [
            {
                "Bâtiment": building,
                "Postes": counts[building],
                "Salles de classe": classrooms[building],
            }
            for building in buildings
        ]
    )
    st.subheader("Salles équipées")
    query = st.text_input(
        "Rechercher une salle", placeholder="Code de salle", key="presence_room_search"
    )
    building = st.selectbox(
        "Filtrer par bâtiment",
        ["Tous les bâtiments"] + buildings,
        key="presence_building_filter",
    )
    filtered = [
        row
        for row in rows
        if query.casefold() in row["Salle"].casefold()
        and (building == "Tous les bâtiments" or row["Bâtiment"] == building)
    ]
    if filtered:
        table(
            [
                {key: value for key, value in row.items() if key != "Modèle"}
                for row in filtered
            ]
        )
        st.download_button(
            "Exporter les salles de ce modèle",
            csv_bytes(filtered),
            "evergreen-presence-modele.csv",
            "text/csv",
        )
    else:
        st.info("Aucune salle ne correspond aux filtres.")
