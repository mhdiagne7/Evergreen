"""Créer, filtrer et déplacer des groupes d'ordinateurs dans les parcours existants."""

from collections import Counter

import streamlit as st

from core.asset_groups import (
    GroupStore,
    filter_assets,
)
from core.export import csv_bytes
from ui.common import refresh, table, transfer_rows
from ui.navigation import go

FIELDS = {"Salle": "room", "Modèle": "model"}


def asset_label(asset):
    return f"{asset.get('service_tag') or 'Service Tag non renseigné'} · {asset['room']} · {asset['model']}"


def asset_rows(assets, origins=None):
    return [
        {
            "Service Tag": a.get("service_tag") or "Non renseigné",
            "Modèle": a["model"],
            "Bâtiment": a["building"],
            "Salle actuelle": a["room"],
            **(
                {"Salle à la création": origins.get(a["id"])}
                if origins is not None
                else {}
            ),
        }
        for a in assets
    ]


def filters_view(assets, prefix):
    filters = {}
    with st.expander("Filtrer les ordinateurs", expanded=True):
        columns = st.columns(2)
        for index, (label, field) in enumerate(FIELDS.items()):
            values = sorted({a[field] for a in assets if a[field] is not None}, key=str)
            selected = columns[index % 2].multiselect(
                label,
                values,
                format_func=lambda v: str(v) if v != "" else "Non renseigné",
                key=prefix + field,
            )
            filters[field] = selected
    found = filter_assets(assets, filters)
    return [
        a
        for a in found
        if a["active"] and a["available"] and a["room_type"] == "classroom"
    ]


@st.dialog("Sélectionner des bâtiments sur la carte", width="large")
def building_map_dialog(data, models):
    from map_view import campus_map

    st.caption(
        "Maintiens Ctrl (ou Cmd) en cliquant pour sélectionner plusieurs bâtiments, puis confirme."
    )
    selected = campus_map(data, models, key_prefix="ag_picker", multiple=True) or []
    if selected:
        st.write("Sélection sur la carte : **" + ", ".join(selected) + "**")
    if st.button(
        "Confirmer les bâtiments",
        type="primary",
        key="ag_confirm_map",
        disabled=not selected,
    ):
        st.session_state.ag_map_buildings = selected
        st.rerun()
    if st.button("Annuler", key="ag_close_map"):
        st.rerun()


def selection_table(assets, key, default=()):
    rows = [
        {
            "Choisir": a["id"] in default,
            "ID": a["id"],
            "Service Tag": a.get("service_tag") or "Non renseigné",
            "Salle": a["room"],
            "Modèle": a["model"],
        }
        for a in assets
    ]
    if not rows:
        st.info("Aucun ordinateur ne correspond aux filtres.")
        return []
    edited = st.data_editor(
        rows,
        hide_index=True,
        width="stretch",
        disabled=[k for k in rows[0] if k != "Choisir"],
        column_config={
            "Choisir": st.column_config.CheckboxColumn("Choisir"),
            "ID": None,
        },
        key=key,
    )
    return [row["ID"] for row in edited if row["Choisir"]]


def create_view(store, workspace, data, revision, groups_store, assets):
    with st.container(border=True):
        if st.button(
            "Sélectionner des bâtiments sur la carte",
            type="primary",
            width="stretch",
            key="ag_open_map",
        ):
            building_map_dialog(data, sorted({a["model"] for a in assets}))
        buildings = st.session_state.get("ag_map_buildings", [])
        if buildings:
            st.write("Bâtiments sélectionnés : **" + ", ".join(buildings) + "**")
            if st.button("Effacer la sélection sur la carte", key="ag_clear_map"):
                st.session_state.pop("ag_map_buildings", None)
                st.rerun()
        found = filters_view(assets, "ag_filter_")
        if buildings:
            found = [a for a in found if a["building"] in buildings]
        found.sort(key=lambda a: (a["model"].casefold(), a["room"], a["id"]))
        st.caption(f"{len(found)} ordinateur(s) correspondent aux filtres.")
        chosen = []
        drafts = []
        title = st.text_input(
            "Nom du groupe",
            value="Nouveau groupe",
            key="ag_create_name",
        )
        description = st.text_area("Description", key="ag_create_description")
        by_id = {a["id"]: a for a in assets}
        all_selected = st.checkbox(
            "Sélectionner tous les résultats", value=True, key="ag_select_all"
        )
        chosen = selection_table(
            found,
            "ag_selection_"
            + str(revision)
            + "_"
            + str(tuple(a["id"] for a in found))
            + str(all_selected),
            [a["id"] for a in found] if all_selected else [],
        )
        drafts = [{"name": title, "description": description, "members": chosen}]
        signature = (workspace, revision, title, description, str(drafts))
        if st.button("Prévisualiser le regroupement", key="ag_preview"):
            if not chosen or not title.strip():
                st.error(
                    "Donne un nom au groupe et sélectionne au moins un ordinateur disponible."
                )
            else:
                st.session_state.ag_draft_preview = signature
        if st.session_state.get("ag_draft_preview") == signature:
            table(
                [
                    {
                        "Groupe": draft["name"],
                        "Ordinateurs": len(draft["members"]),
                        "Salles": len(
                            {by_id[item]["room"] for item in draft["members"]}
                        ),
                        "Bâtiments": ", ".join(
                            sorted(
                                {by_id[item]["building"] for item in draft["members"]}
                            )
                        ),
                    }
                    for draft in drafts
                ]
            )
            with st.expander("Ordinateurs sélectionnés"):
                table(asset_rows([by_id[item] for item in chosen]))
            if st.button(
                "Enregistrer le groupe",
                type="primary",
                key="ag_save",
            ):
                try:
                    groups_store.save_many(workspace, revision, drafts)
                    st.session_state.pop("ag_draft_preview", None)
                    st.session_state.ag_creating = False
                    refresh("Groupes enregistrés. Aucun ordinateur n’a été déplacé.")
                except ValueError as error:
                    st.error(str(error))
        if st.button("Annuler la création", key="ag_cancel_create"):
            st.session_state.ag_creating = False
            st.session_state.pop("ag_draft_preview", None)
            st.rerun()


def individual_moves_view(
    groups_store, workspace, data, revision, assets, members, group
):
    from core.campus import building_distance

    assignments = {}
    rows = []
    for asset in sorted(members, key=lambda a: (a["model"], a["room"], a["id"])):
        with st.container(border=True):
            st.write(
                "**"
                + asset["model"]
                + "** · "
                + asset["room"]
                + " · "
                + (asset.get("service_tag") or "Service Tag non renseigné")
            )
            origin = data.rooms[asset["room"]].building

            def nearby(room):
                building = data.rooms[room].building
                distance = building_distance(origin, building)
                return (
                    room != asset["room"],
                    building != origin,
                    distance if distance is not None else float("inf"),
                    room,
                )

            rooms = sorted(
                [
                    room
                    for room, info in data.rooms.items()
                    if info.room_type == "classroom" or room == "MRT-STOCK"
                ],
                key=nearby,
            )
            destination = st.selectbox("Destination", rooms, key="ag_to_" + asset["id"])
            if destination == asset["room"]:
                continue
            distance = building_distance(origin, data.rooms[destination].building)
            st.caption(
                "Même bâtiment : distance intérieure non mesurée."
                if origin == data.rooms[destination].building
                else (
                    f"Proximité : {distance:.0f} m à vol d’oiseau."
                    if distance is not None
                    else "Distance non renseignée."
                )
            )
            candidates = [
                a
                for a in assets
                if a["active"]
                and a["available"]
                and a["room"] == destination
                and a["id"] != asset["id"]
                and data.rooms[destination].room_type == "classroom"
                and data.rooms[asset["room"]].room_type == "classroom"
            ]
            by_id = {a["id"]: a for a in candidates}
            partner = st.selectbox(
                "Poste à échanger en retour",
                [None] + list(by_id),
                format_func=lambda value: (
                    "Aucun · déplacement simple"
                    if value is None
                    else asset_label(by_id[value])
                ),
                key="ag_swap_" + asset["id"],
            )
            assignments[asset["id"]] = {"destination": destination, "swap": partner}
            rows.append(
                {
                    "Référence carte mère": asset.get("motherboard_code")
                    or "Non renseignée",
                    "Modèle": asset["model"],
                    "Depuis": asset["room"],
                    "Vers": destination,
                    "Échange en retour": asset_label(by_id[partner])
                    if partner
                    else "—",
                }
            )
    if rows:
        st.subheader("Liste des mouvements et échanges")
        table(rows)
        st.download_button(
            "Exporter la liste",
            csv_bytes(rows),
            "echanges.csv",
            "text/csv",
            key="ag_moves_export_" + group["id"],
        )
    signature = (workspace, revision, group["id"], group["version"], str(assignments))
    if st.button("Vérifier les déplacements et échanges", key="ag_individual_preview"):
        try:
            plan = groups_store.plan(
                workspace,
                group["id"],
                group["version"],
                revision,
                assignments=assignments,
            )
            st.session_state.ag_individual_draft = (signature, plan)
        except ValueError as error:
            st.error(str(error))
    preview = st.session_state.get("ag_individual_draft")
    if preview and preview[0] == signature:
        table(transfer_rows(preview[1], data))
        confirmed = st.checkbox(
            "Je confirme cette liste à réaliser", key="ag_individual_confirm"
        )
        if st.button(
            "Enregistrer les échanges planifiés",
            disabled=not confirmed,
            key="ag_individual_save",
        ):
            try:
                groups_store.plan(
                    workspace,
                    group["id"],
                    group["version"],
                    revision,
                    assignments=assignments,
                    save=True,
                )
                refresh(
                    "Liste enregistrée. Confirme chaque opération après sa réalisation physique dans Lots de déplacements."
                )
            except ValueError as error:
                st.error(str(error))


def group_view(store, workspace, data, revision, groups_store, assets, group):
    by_id = {a["id"]: a for a in assets}
    members = [by_id[item] for item in group["members"] if item in by_id]
    overlaps = Counter(
        item for g in groups_store.groups(workspace) for item in g["members"]
    )
    st.subheader(group["name"])
    if group["description"]:
        st.write(group["description"])
    first, second, third = st.columns(3)
    first.metric("Ordinateurs", len(members))
    second.metric("Salles actuelles", len({a["room"] for a in members if a["active"]}))
    third.metric("Statut", group["status"])
    table(asset_rows(members, group["origins"]))
    if any(not a["active"] for a in members):
        st.info(
            "Certains ordinateurs ne sont plus dans l’inventaire actif. Retire-les du groupe avant de préparer un nouveau lot."
        )
    if any(overlaps[a["id"]] > 1 for a in members):
        st.info(
            "Certains ordinateurs appartiennent à plusieurs groupes. La création d’un groupe ne réserve pas le matériel ; les lots périmés doivent être recalculés."
        )
    st.download_button(
        "Exporter ce groupe",
        csv_bytes(asset_rows(members, group["origins"])),
        "evergreen-groupe.csv",
        "text/csv",
        key="ag_export_" + group["id"],
    )
    with st.expander("Voir ce groupe sur la carte"):
        from dataclasses import replace

        from map_view import campus_map

        inventory = Counter((a["room"], a["model"]) for a in members if a["active"])
        rooms = {room: data.rooms[room] for room, _ in inventory}
        if inventory:
            subset = replace(
                data,
                rooms=rooms,
                inventory=dict(inventory),
                returned_stock=dict(
                    Counter(
                        (a["room"], a["model"])
                        for a in members
                        if a["active"] and a["kind"] == "returned"
                    )
                ),
            )
            campus_map(
                subset,
                sorted({a["model"] for a in members}),
                key_prefix="group_" + group["id"],
                group_highlight=True,
            )
    locked = group["status"] in {"Planifié", "En cours"}
    with st.expander("Modifier ou supprimer le groupe"):
        if locked:
            st.info("Termine ou annule le lot actif avant de modifier la composition.")
        else:
            name = st.text_input(
                "Nom", group["name"], key="ag_edit_name_" + group["id"]
            )
            description = st.text_area(
                "Description du groupe",
                group["description"],
                key="ag_edit_description_" + group["id"],
            )
            eligible = [
                a
                for a in assets
                if a["active"] and (a["available"] or a["id"] in group["members"])
            ]
            st.caption(
                "Coche ou décoche les ordinateurs pour en ajouter ou en retirer."
            )
            selected = selection_table(
                eligible,
                "ag_edit_"
                + group["id"]
                + "_"
                + str(group["version"])
                + "_"
                + str(revision),
                group["members"],
            )
            if st.button(
                "Enregistrer les modifications", key="ag_update_" + group["id"]
            ):
                try:
                    groups_store.update(
                        workspace,
                        group["id"],
                        group["version"],
                        name,
                        description,
                        selected,
                    )
                    refresh("Groupe mis à jour ; inventaire inchangé.")
                except ValueError as error:
                    st.error(str(error))
            confirmed = st.checkbox(
                "Supprimer uniquement le groupe, sans supprimer les ordinateurs",
                key="ag_delete_confirm_" + group["id"],
            )
            if st.button(
                "Supprimer le groupe",
                disabled=not confirmed,
                key="ag_delete_" + group["id"],
            ):
                try:
                    groups_store.delete(workspace, group["id"], group["version"])
                    st.session_state.pop("ag_selected", None)
                    refresh("Groupe supprimé ; ordinateurs conservés.")
                except ValueError as error:
                    st.error(str(error))
    st.subheader("Déplacement groupé")
    if locked:
        st.info(
            "Un lot est déjà enregistré pour ce groupe. Confirme les opérations après leur réalisation physique dans Lots de déplacements."
        )
        if st.button("Ouvrir le lot du groupe", key="ag_open_batch_" + group["id"]):
            go("lot", selected_lot=group["batch_id"])
        if st.button(
            "Annuler les déplacements restants", key="ag_cancel_batch_" + group["id"]
        ):
            store.cancel_batch(workspace, group["batch_id"])
            refresh("Lot annulé. Les opérations déjà confirmées sont conservées.")
        return
    individual_moves_view(
        groups_store, workspace, data, revision, assets, members, group
    )


def groups_view(store, workspace, data, models, revision):
    groups_store = GroupStore(store)
    assets = groups_store.assets(workspace)
    groups = groups_store.groups(workspace)
    if not st.session_state.get("ag_creating") and st.button(
        "Nouveau groupe", type="primary", key="ag_create"
    ):
        st.session_state.ag_creating = True
        st.session_state.pop("ag_selected", None)
    if st.session_state.get("ag_creating"):
        create_view(store, workspace, data, revision, groups_store, assets)
    elif groups:
        choices = [g["id"] for g in groups]
        by_id = {g["id"]: g for g in groups}
        if st.session_state.get("ag_selected") not in choices:
            st.session_state.ag_selected = choices[0]
        selected = st.selectbox(
            "Groupes enregistrés",
            choices,
            format_func=lambda item: (
                by_id[item]["name"] + " · " + by_id[item]["status"]
            ),
            key="ag_selected",
        )
        group_view(
            store, workspace, data, revision, groups_store, assets, by_id[selected]
        )
    else:
        st.info("Aucun groupe enregistré. Sélectionne des ordinateurs pour commencer.")
