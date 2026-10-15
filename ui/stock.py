"""Catalogue, arrivages au stock central MRT et sauvegardes."""

import streamlit as st

from core.export import csv_bytes
from ui.common import refresh, table


def stock_view(store, identifier, data, models, revision):
    st.subheader("Catalogue et arrivages")
    reserves = sorted(
        room
        for room, info in data.rooms.items()
        if info.room_type == "storage" and info.building == "MRT"
    )
    if not reserves:
        st.info(
            "Le référentiel doit définir le stock central à MRT pour enregistrer les arrivages."
        )
        return
    room = reserves[0] if len(reserves) == 1 else st.selectbox("Stock MRT", reserves)
    st.caption(
        "Les nouveaux ordinateurs sont reçus à MRT. Aucun champ de provenance n’est demandé."
    )
    table(
        [
            {
                "Modèle": model,
                "Quantité en stock à MRT": data.inventory.get((room, model), 0),
            }
            for model in models
        ]
    )
    with st.form("new_model"):
        model = st.text_input("Nouveau modèle", key="new_model_name")
        submit = st.form_submit_button("Ajouter au catalogue")
    if submit:
        try:
            store.add_model(identifier, model)
            refresh("Modèle ajouté. Tu peux maintenant enregistrer sa quantité reçue.")
        except ValueError as error:
            st.error(str(error))
    if models:
        with st.form("receipt"):
            model = st.selectbox("Modèle reçu", models, key="receipt_model")
            quantity = int(
                st.number_input(
                    "Quantité reçue",
                    min_value=1,
                    value=1,
                    step=1,
                    key="receipt_quantity",
                )
            )
            confirmed = st.checkbox(
                "Ces ordinateurs ont bien été reçus", key="receipt_confirm"
            )
            submit = st.form_submit_button("Enregistrer l'arrivage")
        if submit:
            if not confirmed:
                st.error("Confirme la réception avant d’ajouter le stock.")
            else:
                try:
                    store.receive(identifier, room, model, quantity, revision)
                    refresh("Arrivage enregistré dans le stock central MRT.")
                except ValueError as error:
                    st.error(str(error))
    info = data.rooms[room]
    st.caption(
        "Capacité maximale du stock MRT : "
        + (
            str(info.capacity)
            if info.capacity is not None
            else "aucune limite configurée, capacité physique inconnue"
        )
        + "."
    )
    with st.expander("Configurer la capacité du stock MRT"):
        with st.form("stock_capacity"):
            limited = st.checkbox(
                "Définir une capacité maximale", value=info.capacity is not None
            )
            capacity = int(
                st.number_input(
                    "Nombre maximal d’ordinateurs",
                    min_value=0,
                    value=info.capacity
                    if info.capacity is not None
                    else data.occupied(room),
                )
            )
            submit = st.form_submit_button("Enregistrer la capacité")
        if submit:
            try:
                store.configure_stock_capacity(
                    identifier, room, capacity if limited else None, revision
                )
                refresh("Capacité du stock mise à jour.")
            except ValueError as error:
                st.error(str(error))
    current = [
        {"room_id": location, "model": model, "quantity": quantity}
        for (location, model), quantity in sorted(data.inventory.items())
        if quantity
    ]
    st.download_button(
        "Exporter l'inventaire actuel",
        csv_bytes(current) if current else b"room_id,model,quantity\n",
        "inventory.csv",
        "text/csv",
    )
    st.caption(
        "Les quantités et les lots sont conservés en base locale ; le CSV initial reste intact."
    )
    if st.button("Préparer une sauvegarde complète", key="prepare_backup"):
        st.session_state.backup_bytes = store.backup()
    if "backup_bytes" in st.session_state:
        st.download_button(
            "Télécharger la sauvegarde locale",
            st.session_state.backup_bytes,
            "evergreen-sauvegarde.sqlite3",
            "application/octet-stream",
        )
        st.caption(
            "La sauvegarde contient tous les espaces et leurs historiques au moment de sa préparation."
        )
