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


def filters_view(assets, prefix, include_ids=()):
    filters = {}
    with st.expander("Filtrer les ordinateurs", expanded=True):
        columns = st.columns(2)
        for index, (label, field) in enumerate(FIELDS.items()):
            values = sorted({a[field] for a in assets if a[field] is not None}, key=str)
            key = prefix + field
            if key in st.session_state:
                st.session_state[key] = [
                    value for value in st.session_state[key] if value in values
                ]
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
        if (a["active"] and a["available"] and a["room_type"] == "classroom")
        or a["id"] in include_ids
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
        st.subheader("Nom du groupe")
        title = st.text_input(
            "Nom du groupe",
            value="Nouveau groupe",
            key="ag_create_name",
            label_visibility="collapsed",
        )
        description = st.text_area("Description", key="ag_create_description")
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
        scoped_assets = [
            a
            for a in assets
            if a["active"]
            and a["available"]
            and a["room_type"] == "classroom"
            and (not buildings or a["building"] in buildings)
        ]
        found = filters_view(scoped_assets, "ag_filter_")
        found.sort(key=lambda a: (a["model"].casefold(), a["room"], a["id"]))
        st.caption(f"{len(found)} ordinateur(s) correspondent aux filtres.")
        chosen = []
        drafts = []
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
            st.header(title)
            model_counts = Counter(by_id[item]["model"] for item in chosen)
            first, second = st.columns(2)
            first.metric("Modèles différents", len(model_counts))
            second.metric("Ordinateurs sélectionnés", len(chosen))
            table(
                [
                    {"Modèle": model, "Nombre d’ordinateurs": count}
                    for model, count in sorted(model_counts.items())
                ]
            )
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
                    "Service Tag": asset.get("service_tag") or "Non renseigné",
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


def close_swap_dialog():
    st.session_state.ag_swap_open = None


def selected_table_asset(event, assets):
    indices = event.selection.rows
    return (
        assets[indices[0]]
        if len(indices) == 1 and 0 <= indices[0] < len(assets)
        else None
    )


@st.dialog("Échanges entre ordinateurs", width="large", on_dismiss=close_swap_dialog)
def swaps_dialog(groups_store, workspace, data, revision, assets, members, group):
    from core.campus import building_distance

    groups = groups_store.groups(workspace)
    by_group = {item["id"]: item for item in groups}
    sources = [
        item["id"] for item in groups if item["status"] not in {"Planifié", "En cours"}
    ]
    if not sources:
        st.info("Aucun groupe disponible pour préparer de nouveaux échanges.")
        return
    if st.session_state.get("ag_swap_source_group") not in sources:
        st.session_state.ag_swap_source_group = (
            group["id"] if group["id"] in sources else sources[0]
        )
    first_selector, second_selector = st.columns(2)
    source_id = first_selector.selectbox(
        "Groupe de départ",
        sources,
        format_func=lambda value: by_group[value]["name"],
        key="ag_swap_source_group",
    )
    targets = [None] + [item["id"] for item in groups if item["id"] != source_id]
    if st.session_state.get("ag_swap_target_group") not in targets:
        st.session_state.ag_swap_target_group = None
    target_id = second_selector.selectbox(
        "Comparer avec",
        targets,
        format_func=lambda value: (
            "Reste des ordinateurs du campus"
            if value is None
            else by_group[value]["name"]
        ),
        key="ag_swap_target_group",
    )
    group = by_group[source_id]
    target = by_group[target_id] if target_id else None
    members = [a for a in assets if a["id"] in group["members"]]
    comparison = {"id": target["id"], "version": target["version"]} if target else None
    st.subheader(
        group["name"] + " ⇄ " + (target["name"] if target else "Reste du campus")
    )
    context = (
        workspace,
        group["id"],
        group["version"],
        revision,
        target_id,
        target["version"] if target else None,
    )
    queues = st.session_state.setdefault("ag_swap_queues", {})
    context_key = str(context)
    if context_key not in queues:
        queues[context_key] = {"context": context, "pairs": []}
    draft = queues[context_key]
    previous = st.session_state.get("ag_swap_queue")
    if previous and previous["context"] != context:
        st.session_state.ag_swap_left_search = ""
        st.session_state.ag_swap_right_search = ""
    st.session_state.ag_swap_queue = draft
    pairs = draft["pairs"]
    by_id = {a["id"]: a for a in assets}
    used = {item for pair in pairs for item in pair}
    member_ids = set(group["members"])
    eligible = [
        a
        for a in assets
        if a["active"]
        and a["available"]
        and a["room_type"] == "classroom"
        and a["id"] not in used
    ]
    left_assets = sorted(
        [a for a in eligible if a["id"] in member_ids],
        key=lambda a: (a["model"], a["room"], a.get("service_tag") or a["id"]),
    )
    left, right = st.columns(2)
    table_key = str(context) + str(pairs)
    with left:
        st.markdown("**" + group["name"] + "**")
        query = st.text_input("Rechercher dans le groupe", key="ag_swap_left_search")
        left_assets = [
            a for a in left_assets if query.casefold() in asset_label(a).casefold()
        ]
        left_event = st.dataframe(
            asset_rows(left_assets),
            hide_index=True,
            width="stretch",
            height=280,
            on_select="rerun",
            selection_mode="single-row",
            key="ag_swap_left_" + table_key + query,
            column_order=["Service Tag", "Modèle", "Salle actuelle"],
        )
        first = selected_table_asset(left_event, left_assets)
    with right:
        st.markdown(
            "**" + (target["name"] if target else "Autres ordinateurs du campus") + "**"
        )
        query = st.text_input("Rechercher hors du groupe", key="ag_swap_right_search")
        outside = [
            a
            for a in eligible
            if a["id"] not in member_ids
            and (target is None or a["id"] in target["members"])
            and (not first or a["room"] != first["room"])
        ]

        def proximity(asset):
            same_building = first and asset["building"] == first["building"]
            distance = (
                building_distance(first["building"], asset["building"])
                if first
                else None
            )
            return (
                not same_building,
                distance if distance is not None else float("inf"),
                asset["room"],
                asset["model"],
                asset["id"],
            )

        outside.sort(key=proximity)
        outside = [a for a in outside if query.casefold() in asset_label(a).casefold()]
        right_event = st.dataframe(
            asset_rows(outside),
            hide_index=True,
            width="stretch",
            height=280,
            on_select="rerun",
            selection_mode="single-row",
            key="ag_swap_right_"
            + table_key
            + str(first["id"] if first else None)
            + query,
            column_order=["Service Tag", "Modèle", "Salle actuelle"],
        )
        second = selected_table_asset(right_event, outside)
    st.caption(
        "Sélectionne une ligne dans chaque tableau. Les postes hors du groupe sont triés par bâtiment puis proximité à vol d’oiseau du poste choisi."
    )
    if first and second:
        st.write(asset_label(first) + " ⇄ " + asset_label(second))

    def assignments_for(items):
        return {
            one: {"destination": by_id[two]["room"], "swap": two} for one, two in items
        }

    if st.button(
        "Swap · ajouter à la liste",
        type="primary",
        disabled=not (first and second),
        key="ag_swap_add",
    ):
        proposed = pairs + [(first["id"], second["id"])]
        try:
            groups_store.plan(
                workspace,
                group["id"],
                group["version"],
                revision,
                assignments=assignments_for(proposed),
                comparison=comparison,
            )
            draft["pairs"] = proposed
            st.session_state.ag_swap_queue = draft
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    if pairs:
        st.subheader("Liste des échanges préparés")
        rows = []
        for index, (one, two) in enumerate(pairs, 1):
            for source, target in [(by_id[one], by_id[two]), (by_id[two], by_id[one])]:
                rows.append(
                    {
                        "Échange": index,
                        "Service Tag": source.get("service_tag") or "Non renseigné",
                        "Modèle": source["model"],
                        "Départ": source["room"],
                        "Destination": target["room"],
                    }
                )
        table(rows)
        st.download_button(
            "Exporter les échanges",
            csv_bytes(rows),
            "echanges.csv",
            "text/csv",
            key="ag_swap_export",
        )
        remove = st.selectbox(
            "Échange à retirer",
            range(len(pairs)),
            format_func=lambda i: (
                f"{i + 1} · {asset_label(by_id[pairs[i][0]])} ⇄ {asset_label(by_id[pairs[i][1]])}"
            ),
            key="ag_swap_remove_choice_" + str(pairs),
        )
        if st.button("Retirer de la liste", key="ag_swap_remove"):
            draft["pairs"] = [pair for i, pair in enumerate(pairs) if i != remove]
            st.session_state.ag_swap_queue = draft
            st.rerun()
        confirmed = st.checkbox(
            "Je confirme ces échanges à réaliser",
            key="ag_swap_confirm_" + str(context) + str(pairs),
        )
        if st.button(
            "Enregistrer la liste des échanges",
            type="primary",
            disabled=not confirmed,
            key="ag_swap_save",
        ):
            try:
                groups_store.plan(
                    workspace,
                    group["id"],
                    group["version"],
                    revision,
                    assignments=assignments_for(pairs),
                    comparison=comparison,
                    save=True,
                )
                close_swap_dialog()
                refresh(
                    "Échanges planifiés. Confirme leur réalisation dans Lots de déplacements pour mettre à jour l’inventaire."
                )
            except ValueError as error:
                st.error(str(error))
    if not pairs:
        with st.expander("Déplacer un poste sans échange"):
            individual_moves_view(
                groups_store, workspace, data, revision, assets, members, group
            )
    if st.button("Fermer", key="ag_swap_close"):
        close_swap_dialog()
        st.rerun()


def close_group_editor():
    st.session_state.ag_group_editor_open = None
    st.session_state.pop("ag_group_editor_draft", None)
    for key in list(st.session_state):
        if key.startswith("ag_editor_"):
            del st.session_state[key]


@st.dialog("Modifier le groupe", width="large", on_dismiss=close_group_editor)
def group_editor(groups_store, workspace, data, revision, assets, group):
    draft = st.session_state.get("ag_group_editor_draft")
    if not draft or draft["group"] != group["id"] or draft["workspace"] != workspace:
        draft = {
            "group": group["id"],
            "workspace": workspace,
            "version": group["version"],
            "name": group["name"],
            "description": group["description"],
            "members": list(group["members"]),
            "buildings": sorted(
                {a["building"] for a in assets if a["id"] in group["members"]}
            ),
            "map": False,
            "view": None,
            "nonce": 0,
        }
        st.session_state.ag_group_editor_draft = draft
    if draft["version"] != group["version"] or group["status"] in {
        "Planifié",
        "En cours",
    }:
        st.info(
            "Ce groupe a changé ou possède un lot actif. Ferme la fenêtre avant de reprendre."
        )
        if st.button("Fermer", key="ag_editor_stale_close"):
            close_group_editor()
            st.rerun()
        return
    if draft["map"]:
        from map_view import campus_map

        st.subheader("Choisir les bâtiments")
        selected = (
            campus_map(
                data,
                sorted({a["model"] for a in assets}),
                key_prefix="ag_editor_map",
                multiple=True,
            )
            or []
        )
        if selected:
            st.write("Bâtiments sélectionnés : " + ", ".join(selected))
        if st.button(
            "Confirmer les bâtiments",
            type="primary",
            disabled=not selected,
            key="ag_editor_map_confirm",
        ):
            draft["buildings"] = selected
            draft["map"] = False
            st.rerun()
        if st.button("Revenir au formulaire", key="ag_editor_map_cancel"):
            draft["map"] = False
            st.rerun()
        return
    st.subheader("Nom du groupe")
    draft["name"] = st.text_input(
        "Nom du groupe",
        value=draft["name"],
        label_visibility="collapsed",
        key="ag_editor_name",
    )
    draft["description"] = st.text_area(
        "Description", value=draft["description"], key="ag_editor_description"
    )
    if st.button(
        "Sélectionner des bâtiments sur la carte",
        type="primary",
        width="stretch",
        key="ag_editor_open_map",
    ):
        draft["map"] = True
        st.rerun()
    if draft["buildings"]:
        st.write("Bâtiments affichés : **" + ", ".join(draft["buildings"]) + "**")
        if st.button("Afficher tous les bâtiments", key="ag_editor_all_buildings"):
            draft["buildings"] = []
            st.rerun()
    existing = set(group["members"])
    eligible = [
        a
        for a in assets
        if (
            a["id"] in existing
            or (a["active"] and a["available"] and a["room_type"] == "classroom")
        )
        and (not draft["buildings"] or a["building"] in draft["buildings"])
    ]
    found = filters_view(eligible, "ag_editor_filter_", include_ids=existing)
    found.sort(key=lambda a: (a["model"], a["room"], a.get("service_tag") or a["id"]))
    visible = {a["id"] for a in found}
    view = tuple(a["id"] for a in found)
    if draft["view"] != view:
        draft["nonce"] += 1
        draft["view"] = view
    selected = set(draft["members"])
    first, second = st.columns(2)
    if first.button("Tout sélectionner dans cette vue", key="ag_editor_select_visible"):
        draft["members"] = sorted(selected | visible)
        draft["nonce"] += 1
        st.rerun()
    if second.button(
        "Tout désélectionner dans cette vue", key="ag_editor_clear_visible"
    ):
        draft["members"] = sorted(selected - visible)
        draft["nonce"] += 1
        st.rerun()
    chosen = selection_table(found, "ag_editor_table_" + str(draft["nonce"]), selected)
    selected = (selected - visible) | set(chosen)
    draft["members"] = sorted(selected)
    st.caption(
        "Les filtres limitent l’affichage ; les postes masqués restent sélectionnés dans le groupe."
    )
    by_id = {a["id"]: a for a in assets}
    counts = Counter(by_id[item]["model"] for item in selected if item in by_id)
    first, second = st.columns(2)
    first.metric("Ordinateurs sélectionnés", len(selected))
    second.metric("Modèles différents", len(counts))
    with st.expander("Prévisualiser les changements"):
        table(
            [
                {"Modèle": model, "Nombre d’ordinateurs": count}
                for model, count in sorted(counts.items())
            ]
        )
        table(asset_rows([by_id[item] for item in sorted(selected) if item in by_id]))
    if st.button("Enregistrer les modifications", type="primary", key="ag_editor_save"):
        try:
            groups_store.update(
                workspace,
                group["id"],
                draft["version"],
                draft["name"],
                draft["description"],
                draft["members"],
            )
            close_group_editor()
            refresh("Groupe mis à jour ; aucun ordinateur déplacé.")
        except ValueError as error:
            st.error(str(error))
    if st.button("Annuler", key="ag_editor_cancel"):
        close_group_editor()
        st.rerun()
    with st.expander("Supprimer le groupe"):
        confirmed = st.checkbox(
            "Supprimer uniquement ce groupe, sans supprimer les ordinateurs",
            key="ag_editor_delete_confirm",
        )
        if st.button(
            "Supprimer le groupe", disabled=not confirmed, key="ag_editor_delete"
        ):
            try:
                groups_store.delete(workspace, group["id"], draft["version"])
                close_group_editor()
                st.session_state.pop("ag_selected", None)
                refresh("Groupe supprimé ; ordinateurs conservés.")
            except ValueError as error:
                st.error(str(error))


def group_view(store, workspace, data, revision, groups_store, assets, group):
    by_id = {a["id"]: a for a in assets}
    members = [by_id[item] for item in group["members"] if item in by_id]
    overlaps = Counter(
        item for g in groups_store.groups(workspace) for item in g["members"]
    )
    st.header(group["name"])
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
    if st.button(
        "Modifier le groupe",
        key="ag_open_group_editor",
        width="stretch",
        disabled=locked,
    ):
        close_group_editor()
        close_swap_dialog()
        st.session_state.ag_group_editor_open = group["id"]
    if st.session_state.get("ag_group_editor_open") == group["id"]:
        group_editor(groups_store, workspace, data, revision, assets, group)
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
    if st.button(
        "Ouvrir la fenêtre des déplacements et swaps",
        type="primary",
        width="stretch",
        key="ag_open_swaps",
    ):
        close_group_editor()
        st.session_state.ag_swap_source_group = group["id"]
        st.session_state.ag_swap_target_group = None
        st.session_state.ag_swap_open = group["id"]
    if st.session_state.get("ag_swap_open") == group["id"]:
        swaps_dialog(groups_store, workspace, data, revision, assets, members, group)


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
        st.subheader("Groupes enregistrés")
        for index, group in enumerate(groups):
            if index % 3 == 0:
                cards = st.columns(3, gap="small")
            with cards[index % 3]:
                with st.container(border=True):
                    title, actions = st.columns([3, 1])
                    with title:
                        st.markdown(f"**{group['name']}**")
                    with actions:
                        with st.popover("⋮", help="Actions du groupe"):
                            locked = group["status"] in {"Planifié", "En cours"}
                            if st.button(
                                "Supprimer",
                                key="ag_delete_card_" + group["id"],
                                icon=":material/delete:",
                                disabled=locked,
                            ):
                                try:
                                    groups_store.delete(
                                        workspace, group["id"], group["version"]
                                    )
                                except ValueError as error:
                                    st.error(str(error))
                                else:
                                    close_group_editor()
                                    close_swap_dialog()
                                    if st.session_state.get("ag_selected") == group["id"]:
                                        st.session_state.pop("ag_selected", None)
                                    refresh("Groupe supprimé ; ordinateurs conservés.")
                            if locked:
                                st.caption(
                                    "Annule ou termine le lot actif avant de supprimer ce groupe."
                                )
                    model_count = len(
                        {a["model"] for a in assets if a["id"] in group["members"]}
                    )
                    st.caption(
                        f"{len(group['members'])} ordinateurs · {model_count} modèles"
                    )
                    if st.button("Ouvrir →", key="ag_open_card_" + group["id"]):
                        close_group_editor()
                        close_swap_dialog()
                        st.session_state.ag_selected = group["id"]
        selected = st.session_state.ag_selected
        st.divider()
        group_view(
            store, workspace, data, revision, groups_store, assets, by_id[selected]
        )
    else:
        st.info("Aucun groupe enregistré. Sélectionne des ordinateurs pour commencer.")
