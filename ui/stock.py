"""Réceptions à Morisset, stock disponible et formats des modèles."""

import streamlit as st

from core.export import csv_bytes
from core.model_catalog import catalog, inventory_catalog_rows
from ui.common import refresh, table


def receive_form(store, identifier, data, models, revision):
    if st.session_state.pop("receipt_reset", False):
        for key in list(st.session_state):
            if key.startswith("receipt_"):
                del st.session_state[key]
    choices = sorted(set(models) | set(catalog())) + ["Autre modèle…"]
    st.markdown("**Réception rapide**")
    with st.form("receipt"):
        left, right = st.columns([3, 1])
        model = left.selectbox("Modèle reçu", choices, key="receipt_model")
        quantity = int(
            right.number_input(
                "Quantité reçue", min_value=1, value=1, step=1, key="receipt_quantity"
            )
        )
        new_name = st.text_input(
            "Nom du modèle si « Autre modèle… »", key="receipt_new_name"
        )
        note = st.text_input(
            "Note de réception (facultative)",
            placeholder="Ex. Réception du lot d’octobre",
            key="receipt_note",
        )
        confirmed = st.checkbox(
            "Ces ordinateurs ont bien été reçus", key="receipt_confirm"
        )
        submit = st.form_submit_button("Enregistrer l'arrivage", type="primary")
    if submit:
        if not confirmed:
            st.error("Confirme la réception avant d’ajouter le stock.")
        else:
            try:
                selected = new_name if model == "Autre modèle…" else model
                store.receive_many(
                    identifier,
                    [{"model": selected, "quantity": quantity}],
                    revision,
                    note,
                )
                st.session_state.receipt_reset = True
                refresh(
                    f"{quantity} ordinateur(s) ajouté(s) au stock neuf de Morisset."
                )
            except ValueError as error:
                st.error(str(error))
    with st.expander("Recevoir plusieurs modèles en une seule opération"):
        st.caption(
            "Ajoute une ligne par modèle. Le catalogue et les quantités sont enregistrés ensemble après validation du lot complet."
        )
        with st.form("receipt_many"):
            items = st.data_editor(
                [{"Modèle": "", "Quantité": 1}],
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                column_config={
                    "Modèle": st.column_config.TextColumn(required=True),
                    "Quantité": st.column_config.NumberColumn(
                        min_value=1, step=1, required=True
                    ),
                },
                key="receipt_many_items",
            )
            note = st.text_input("Note du lot (facultative)", key="receipt_many_note")
            confirmed = st.checkbox(
                "Tous ces ordinateurs sont physiquement à Morisset",
                key="receipt_many_confirm",
            )
            submit = st.form_submit_button("Enregistrer la réception complète")
        if submit:
            if not confirmed:
                st.error("Confirme la présence de tous les ordinateurs du lot.")
            else:
                try:
                    parsed = []
                    for item in items:
                        name, amount = (
                            str(item.get("Modèle") or "").strip(),
                            item.get("Quantité"),
                        )
                        if not name:
                            raise ValueError(
                                "Complète chaque ligne ou supprime les lignes vides."
                            )
                        if (
                            isinstance(amount, bool)
                            or not isinstance(amount, (int, float))
                            or not float(amount).is_integer()
                        ):
                            raise ValueError(
                                "Chaque quantité doit être un entier positif."
                            )
                        parsed.append({"model": name, "quantity": int(amount)})
                    store.receive_many(identifier, parsed, revision, note)
                    st.session_state.receipt_reset = True
                    refresh("Réception complète enregistrée au stock neuf de Morisset.")
                except ValueError as error:
                    st.error(str(error))


def models_view(store, identifier, data, models, revision):
    st.caption(
        "Classement des boîtiers de bureau du plus grand au plus petit : Tour → SFF / Slim → Micro. Les portables sont séparés ; les noms incomplets restent à confirmer. La taille n’indique ni l’âge ni la puissance."
    )
    from core.asset_groups import GroupStore

    assets = GroupStore(store).assets(identifier)
    rows = inventory_catalog_rows(data, assets)
    if not rows:
        st.info("Aucun modèle présent dans cet inventaire.")
        return
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_order=[
            "Modèle",
            "Format",
            "Postes",
            "Fiches techniques",
            "Processeurs observés",
            "RAM observée",
            "Stockage observé",
            "Fiche constructeur",
        ],
        column_config={
            "Fiche constructeur": st.column_config.LinkColumn(
                display_text="Consulter Dell"
            )
        },
    )
    st.download_button(
        "Exporter le catalogue",
        csv_bytes(rows),
        "catalogue-modeles.csv",
        "text/csv",
        key="catalog_export",
    )


def stock_view(store, identifier, data, models, revision, section="available"):
    st.subheader("Morisset · Stock central")
    reserves = sorted(
        room
        for room, info in data.rooms.items()
        if info.room_type == "storage" and info.building == "MRT"
    )
    if not reserves:
        st.info(
            "Définis le stock central à Morisset avant d’enregistrer une réception."
        )
        return
    room = reserves[0] if len(reserves) == 1 else st.selectbox("Stock MRT", reserves)
    st.caption(
        "Tous les nouveaux ordinateurs arrivent à Morisset. Les retours de salles sont suivis séparément."
    )
    rows = [
        {
            "Modèle": model,
            "Stock neuf": data.inventory.get((room, model), 0)
            - data.returned_stock.get((room, model), 0),
            "Retours de salles": data.returned_stock.get((room, model), 0),
            "Total disponible": data.inventory.get((room, model), 0),
        }
        for model in models
    ]
    first, second, third = st.columns(3)
    first.metric("Neufs disponibles", sum(row["Stock neuf"] for row in rows))
    second.metric("Retours disponibles", sum(row["Retours de salles"] for row in rows))
    third.metric("Modèles en stock", sum(row["Total disponible"] > 0 for row in rows))
    if section == "receive":
        with st.container(border=True):
            receive_form(store, identifier, data, models, revision)
    if section == "available":
        show_zero = st.checkbox("Afficher les modèles à zéro", key="stock_zero")
        available = (
            rows if show_zero else [row for row in rows if row["Total disponible"]]
        )
        if available:
            table(available)
        else:
            st.info(
                "Le stock central est vide. Enregistre une réception quand le matériel est arrivé."
            )
    if section == "models":
        if models:
            models_view(store, identifier, data, models, revision)
    if section == "settings":
        info = data.rooms[room]
        with st.expander("Capacité du stock central"):
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


def backup_view(store, data):
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
    if st.button("Préparer une sauvegarde complète", key="prepare_backup"):
        st.session_state.backup_bytes = store.backup()
    if "backup_bytes" in st.session_state:
        st.download_button(
            "Télécharger la sauvegarde locale",
            st.session_state.backup_bytes,
            "evergreen-sauvegarde.sqlite3",
            "application/octet-stream",
        )
    st.caption("Les inventaires et leur historique restent sur cet ordinateur.")
