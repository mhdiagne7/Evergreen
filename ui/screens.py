"""Pages courtes, organisées autour des tâches du responsable du parc."""

import os
from pathlib import Path

import streamlit as st

from core.buildings import building_summary
from core.export import csv_bytes
from core.homogeneity import building_models, dominant_models
from core.store import DEFAULT_DB, Store
from map_view import campus_map
from ui.batches import batches_view, swap_undo_from_history
from ui.block_planning import block_planning
from ui.common import refresh, table
from ui.dashboard import building_detail
from ui.distances import google_distances
from ui.homogeneity import homogenization
from ui.imports import import_form
from ui.model_presence import model_presence_detail, models_presence
from ui.navigation import PAGES, go, heading
from ui.planning import manual_planning
from ui.stock import models_view, stock_view


def card(title, description, target, key=None, **selection):
    with st.container(border=True):
        st.subheader(title)
        st.write(description)
        if st.button("Ouvrir →", key=key or "open_" + target):
            go(target, **selection)


def render(name):
    store = Store(Path(os.environ.get("EVERGREEN_DB", str(DEFAULT_DB))))
    identifier = st.session_state.get("workspace")
    if not identifier or identifier not in {w["id"] for w in store.list_workspaces()}:
        heading("Bienvenue dans Evergreen")
        st.info("Importe ton CSV pour commencer. Aucun inventaire fictif n’est chargé.")
        st.caption(
            "Si votre inventaire existe sur un autre ordinateur, récupérez sa sauvegarde ou les CSV d’origine. Aucun inventaire de remplacement ne sera créé."
        )
        import_form(store)
        return
    data, models, revision, label = store.load(identifier)
    args = store, identifier, data, models, revision
    buildings = sorted({r.building for r in data.rooms.values()})
    batches = store.batches(identifier)
    active = [b for b in batches if b["status"] in {"Préparé", "Partiel"}]
    if name == "home":
        heading("Vue d’ensemble du parc")
        st.write(
            "Consultez les bâtiments, préparez les interventions et suivez ce qui a été réalisé."
        )
        installed = sum(
            q
            for (r, _), q in data.inventory.items()
            if data.rooms[r].room_type == "classroom"
        )
        for col, title, value in zip(
            st.columns(4),
            ["Bâtiments", "Postes installés", "En stock", "Lots à suivre"],
            [
                len(buildings),
                installed,
                sum(data.inventory.values()) - installed,
                len(active),
            ],
        ):
            col.metric(title, value)
        selected = campus_map(data, models)
        if selected in buildings:
            if st.button("Voir les salles de " + selected):
                go("building", selected_building=selected)
    elif name == "computer_models":
        models_presence(data)
    elif name == "computer_model":
        model_presence_detail(data)
    elif name == "buildings":
        heading("Bâtiments", "home")
        with st.container(border=True):
            st.subheader("Trajets entre bâtiments")
            if st.button(
                "Consulter les trajets et la carte →",
                key="buildings_routes",
                type="primary",
                width="stretch",
            ):
                go("routes")
        query = st.text_input("Rechercher un bâtiment", placeholder="Code du bâtiment")
        matches = [
            building
            for building in buildings
            if query.casefold() in building.casefold()
        ]
        if not matches:
            st.info("Aucun bâtiment ne correspond à cette recherche.")
        columns = st.columns(3)
        for index, building in enumerate(matches):
            counts = building_models(data, building)
            leaders = dominant_models(data, building)
            dominant = (
                leaders[0]
                if len(leaders) == 1
                else "à départager"
                if leaders
                else "aucun poste installé"
            )
            with columns[index % 3]:
                card(
                    building,
                    f"{sum(counts.values())} poste(s) installés · Modèle principal : {dominant}",
                    "building",
                    "building_" + building,
                    selected_building=building,
                )
        with st.expander("Synthèse et export du parc"):
            summary, breakdown = building_summary(data, models)
            table(summary)
            st.download_button(
                "Exporter la synthèse",
                csv_bytes(breakdown),
                "evergreen-batiments.csv",
                "text/csv",
            )

    elif name == "building":
        selected = st.session_state.get("selected_building")
        if selected not in buildings:
            heading("Choisir un bâtiment", "buildings")
            return
        heading(selected, "buildings")
        building_detail(data, selected)
        st.page_link(PAGES["regroup"], label="Préparer une intervention →")
    elif name == "regroup":
        heading("Regroupements", "home")
        from ui.asset_groups import groups_view

        groups_view(*args)
    elif name == "suggestions":
        heading("Regrouper par modèle", "regroup")
        homogenization(*args)
        st.page_link(PAGES["lots"], label="Voir les lots enregistrés →")
    elif name == "blocks":
        heading("Regrouper par blocs proches", "regroup")
        block_planning(*args)
        st.page_link(PAGES["lots"], label="Voir les lots enregistrés →")
    elif name == "manual":
        heading("Renouveler un bâtiment", "regroup")
        manual_planning(*args)
        st.page_link(PAGES["lots"], label="Voir les lots enregistrés →")
    elif name == "lots":
        heading("Lots de déplacements", "home")
        status = st.radio("Afficher", ["À réaliser", "Tous les lots"], horizontal=True)
        shown = active if status == "À réaliser" else batches
        if not shown:
            st.info(
                "Aucun lot dans cette vue. Préparez un regroupement pour commencer."
            )
        for batch in shown:
            with st.container(border=True):
                title, actions = st.columns([12, 1])
                with title:
                    st.subheader(batch["name"])
                with actions:
                    with st.popover("⋮", help="Actions du lot"):
                        if st.button(
                            "Supprimer",
                            key="delete_lot_" + batch["id"],
                            icon=":material/delete:",
                        ):
                            try:
                                store.delete_batch(identifier, batch["id"])
                            except ValueError as error:
                                st.error(str(error))
                            else:
                                refresh("Lot supprimé de la liste.")
                count = sum(
                    not operation.get("deleted")
                    for operation in batch["plan"]["groups"]
                )
                st.write(f"{batch['status']} · {count} opération(s)")
                if st.button("Ouvrir →", key="lot_" + batch["id"]):
                    go("lot", selected_lot=batch["id"])
        st.page_link(PAGES["regroup"], label="Préparer un regroupement →")
    elif name == "lot":
        heading("Détail du lot", "lots")
        selected = st.session_state.get("selected_lot")
        if selected not in {b["id"] for b in batches}:
            st.info("Sélectionnez un lot dans la liste.")
            return
        batches_view(store, identifier, data, revision, batch_id=selected)
    elif name == "stock":
        heading("Stock central", "home")
        if st.button(
            "Enregistrer une réception →",
            type="primary",
            width="stretch",
            key="stock_open_receipts",
        ):
            go("receipts")
        stock_view(*args)
    elif name == "receipts":
        heading("Recevoir du matériel", "stock")
        stock_view(*args, section="receive")
    elif name == "models":
        heading("Catalogue des modèles", "home")
        models_view(*args)
    elif name == "history":
        heading("Historique", "home")
        swap_undo_from_history(store, identifier, data, revision)
        events = store.history(identifier)
        table(
            [
                {"Date (UTC)": e["created"], "Action": e["kind"], "Note": e["note"]}
                for e in events
            ]
        )
        if events:
            st.download_button(
                "Exporter l’historique",
                csv_bytes(events),
                "evergreen-historique.csv",
                "text/csv",
            )
    elif name == "data":
        go("home")
    elif name == "assistant":
        heading("Assistant IA local", "home")
        from ui.assistant import assistant_view

        assistant_view(*args)
    elif name == "map":
        go("home")
    elif name == "routes":
        heading("Salles et trajets", "buildings")
        google_distances(data)
