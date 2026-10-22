"""Créer, filtrer et déplacer des groupes d'ordinateurs dans les parcours existants."""

from collections import Counter

import streamlit as st

from core.asset_groups import (
    CONDITIONS,
    PRIORITIES,
    GroupStore,
    automatic_groups,
    filter_assets,
)
from core.export import csv_bytes
from ui.common import operation_rows, refresh, table, transfer_rows
from ui.navigation import PAGES, go

FIELDS = {
    "Catégorie": "category",
    "Bâtiment": "building",
    "Étage": "floor",
    "Salle": "room",
    "Modèle": "model",
    "État": "condition",
    "Priorité": "priority",
}


def asset_label(asset):
    return f"{asset['physical_id'] or asset['id'][:15]} · {asset['room']} · {asset['model']}"


def asset_rows(assets, origins=None):
    return [
        {
            "Identifiant Evergreen": a["id"],
            "Numéro d’inventaire réel": a["physical_id"] or "Non renseigné",
            "Modèle": a["model"],
            "Catégorie": a["category"],
            "Bâtiment": a["building"],
            "Étage": a["floor"] or "Non renseigné",
            "Salle actuelle": a["room"],
            "État": a["condition"],
            "Priorité": a["priority"],
            "Disponible": bool(a["available"]) and bool(a["active"]),
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
        available = st.checkbox(
            "Uniquement les ordinateurs disponibles",
            value=True,
            key=prefix + "available",
        )
        classes = st.checkbox(
            "Uniquement les postes installés en salle",
            value=True,
            key=prefix + "classes",
        )
    found = filter_assets(assets, filters)
    return [
        a
        for a in found
        if a["active"]
        and (not available or a["available"])
        and (not classes or a["room_type"] == "classroom")
    ]


def selection_table(assets, key, default=()):
    rows = [
        {
            "Choisir": a["id"] in default,
            "ID": a["id"],
            "Salle": a["room"],
            "Modèle": a["model"],
            "Catégorie": a["category"],
            "Étage": a["floor"] or "Non renseigné",
            "Disponible": bool(a["available"]),
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
        st.subheader("Créer un groupe")
        mode = st.radio(
            "Mode de création",
            ["Manuel", "Automatique"],
            horizontal=True,
            key="ag_mode",
        )
        st.caption(
            "Les identifiants Evergreen sont locaux. Les catégories, étages, états et priorités restent non renseignés tant qu’ils ne sont pas vérifiés."
        )
        found = filters_view(assets, "ag_filter_")
        source_map = st.checkbox(
            "Sélectionner un bâtiment sur la carte", key="ag_use_map"
        )
        if source_map:
            from map_view import campus_map

            selected = campus_map(data, sorted({a["model"] for a in assets}))
            if selected:
                st.session_state.ag_map_building = selected
            building = st.session_state.get("ag_map_building")
            if building:
                st.info("Sélection sur la carte : " + building)
                found = [a for a in found if a["building"] == building]
                if st.button("Effacer la sélection sur la carte", key="ag_clear_map"):
                    st.session_state.pop("ag_map_building", None)
                    st.rerun()
        st.caption(f"{len(found)} ordinateur(s) correspondent aux filtres.")
        chosen = []
        drafts = []
        title = st.text_input(
            "Nom du groupe" if mode == "Manuel" else "Préfixe des groupes",
            value="Nouveau groupe",
            key="ag_create_name",
        )
        description = st.text_area("Description", key="ag_create_description")
        by_id = {a["id"]: a for a in assets}
        if mode == "Manuel":
            all_selected = st.checkbox(
                "Sélectionner tous les résultats disponibles", key="ag_select_all"
            )
            eligible = [a for a in found if a["available"]]
            chosen = selection_table(
                eligible,
                "ag_selection_"
                + str(revision)
                + "_"
                + str(tuple(a["id"] for a in eligible))
                + str(all_selected),
                [a["id"] for a in eligible] if all_selected else [],
            )
            drafts = [{"name": title, "description": description, "members": chosen}]
        else:
            fields = st.multiselect(
                "Séparer les groupes selon",
                list(FIELDS),
                default=["Bâtiment", "Étage", "Modèle"],
                key="ag_auto_fields",
            )
            maximum = int(
                st.number_input(
                    "Nombre maximal d’ordinateurs par groupe",
                    1,
                    500,
                    10,
                    key="ag_maximum",
                )
            )
            partitions = automatic_groups(
                found, [FIELDS[field] for field in fields], maximum
            )
            drafts = [
                {
                    "name": f"{title} {i + 1}",
                    "description": description,
                    "members": members,
                }
                for i, members in enumerate(partitions)
            ]
            chosen = [item for partition in partitions for item in partition]
            st.caption(
                "Les mêmes salles et étages renseignés sont privilégiés, puis les bâtiments voisins. La proximité ne provoque aucun déplacement."
            )
        signature = (workspace, revision, mode, title, description, str(drafts))
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
                "Enregistrer le groupe"
                if mode == "Manuel"
                else "Enregistrer les groupes",
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
    destination = st.selectbox(
        "Salle de destination", sorted(data.rooms), key="ag_destination_" + group["id"]
    )
    info = data.rooms[destination]
    st.caption(
        "Places libres : "
        + (
            str(int(data.available(destination)))
            if info.capacity is not None
            else "capacité non configurée, à vérifier avant intervention"
        )
    )
    with st.expander("Renseigner la capacité réelle de la destination"):
        st.caption(
            "Les capacités issues du CSV sont les postes observés, pas une mesure des places physiques. Vérifie la salle avant de déclarer une autre capacité."
        )
        capacity = int(
            st.number_input(
                "Capacité totale vérifiée de la salle",
                min_value=data.occupied(destination),
                value=max(data.occupied(destination), info.capacity or 0),
                step=1,
                key="ag_capacity_" + destination,
            )
        )
        checked = st.checkbox(
            "J’ai vérifié cette capacité sur le terrain",
            key="ag_capacity_checked_" + destination,
        )
        if st.button(
            "Enregistrer la capacité de destination",
            disabled=not checked,
            key="ag_save_capacity_" + group["id"],
        ):
            try:
                groups_store.room_capacity(workspace, destination, revision, capacity)
                refresh("Capacité déclarée enregistrée. Recalcule le déplacement.")
            except ValueError as error:
                st.error(str(error))
    signature = (workspace, revision, group["id"], group["version"], destination)
    if st.button("Prévisualiser le déplacement", key="ag_plan_" + group["id"]):
        try:
            plan = groups_store.plan(
                workspace, group["id"], group["version"], revision, destination
            )
            st.session_state.ag_move_preview = (signature, plan)
        except ValueError as error:
            st.error(str(error))
    preview = st.session_state.get("ag_move_preview")
    if preview and preview[0] == signature:
        plan = preview[1]
        table(operation_rows(plan))
        table(transfer_rows(plan, data))
        st.caption(
            "Les ordinateurs déjà à destination restent en place. L’ordre regroupe les salles d’origine ; aucune tournée piétonne optimale n’est garantie."
        )
        confirmed = st.checkbox(
            "Je confirme cette planification ; les ordinateurs seront déplacés plus tard",
            key="ag_plan_confirm_" + group["id"],
        )
        if st.button(
            "Enregistrer le lot de déplacement",
            disabled=not confirmed,
            key="ag_plan_save_" + group["id"],
        ):
            try:
                groups_store.plan(
                    workspace,
                    group["id"],
                    group["version"],
                    revision,
                    destination,
                    save=True,
                )
                st.session_state.pop("ag_move_preview", None)
                refresh(
                    "Lot planifié. L’inventaire est inchangé jusqu’à la confirmation physique."
                )
            except ValueError as error:
                st.error(str(error))


def metadata_view(groups_store, workspace, revision, assets):
    with st.expander("Renseigner les caractéristiques manquantes"):
        st.caption(
            "Les catégories sont un classement interne à définir par l’équipe. Aucune note n’est déduite du nom commercial. L’étage renseigné concerne toute la salle."
        )
        active = [a for a in assets if a["active"]]
        if not active:
            return
        ids = [a["id"] for a in active]
        by_id = {a["id"]: a for a in active}
        selected = st.selectbox(
            "Ordinateur à renseigner",
            ids,
            format_func=lambda item: asset_label(by_id[item]),
            key="ag_metadata_asset",
        )
        asset = by_id[selected]
        with st.form("ag_metadata_" + selected + "_" + str(revision)):
            physical = st.text_input(
                "Numéro d’inventaire réel (si connu)", asset["physical_id"]
            )
            category = st.number_input(
                "Catégorie interne (non renseignée par défaut)",
                min_value=1,
                max_value=99,
                value=asset["category"],
                step=1,
            )
            floor = st.text_input("Étage de la salle", asset["floor"])
            condition = st.selectbox(
                "État du matériel",
                CONDITIONS,
                index=CONDITIONS.index(asset["condition"]),
            )
            priority = st.selectbox(
                "Priorité de remplacement",
                PRIORITIES,
                index=PRIORITIES.index(asset["priority"]),
            )
            available = st.checkbox(
                "Ordinateur disponible", value=bool(asset["available"])
            )
            submit = st.form_submit_button("Enregistrer les caractéristiques")
        if submit:
            try:
                groups_store.metadata(
                    workspace,
                    selected,
                    revision,
                    physical,
                    category,
                    condition,
                    priority,
                    available,
                    floor,
                )
                refresh("Caractéristiques enregistrées ; quantités inchangées.")
            except ValueError as error:
                st.error(str(error))


def groups_view(store, workspace, data, models, revision):
    groups_store = GroupStore(store)
    assets = groups_store.assets(workspace)
    groups = groups_store.groups(workspace)
    if st.button("Créer un groupe", type="primary", key="ag_create"):
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
        st.info(
            "Aucun groupe enregistré. Crée un groupe manuel ou automatique pour commencer."
        )
    metadata_view(groups_store, workspace, revision, assets)
    with st.expander("Renouvellement et uniformisation des modèles"):
        st.page_link(PAGES["suggestions"], label="Regrouper par modèle dominant →")
        st.page_link(PAGES["blocks"], label="Regrouper les blocs proches →")
        st.page_link(PAGES["manual"], label="Renouveler un bâtiment →")
