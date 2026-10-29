"""Confirmer les mouvements physiques et consulter leur historique."""

import streamlit as st

from core.export import csv_bytes
from ui.common import operation_rows, refresh, table, transfer_rows, transport_summary


def close_operation_editor():
    st.session_state.lot_operation_editor = None


@st.dialog("Modifier l’opération", width="large", on_dismiss=close_operation_editor)
def operation_editor(store, identifier, data, batch, index, version):
    plan = batch["plan"]
    if plan.get("edit_version", 0) != version:
        st.info("Ce lot a changé. Ferme la fenêtre puis rouvre l’opération.")
        return
    operation = plan["groups"][index]
    st.subheader(f"Opération {index + 1}")
    kwargs = {}
    prefix = f"lot_edit_{batch['id']}_{index}_{version}_"
    if plan.get("mode") == "asset_group":
        from core.asset_groups import GroupStore
        from ui.asset_groups import asset_label

        assets = GroupStore(store).assets(identifier)
        ids = operation.get("asset_moves") or operation.get("asset_ids") or []
        source = next((a for a in assets if ids and a["id"] == ids[0]), None)
        if source is None:
            st.error("Ordinateur introuvable.")
            return
        st.write(asset_label(source))
        rooms = sorted(data.rooms)
        original = operation["transfers"][0]["destination"]
        destination = st.selectbox(
            "Destination",
            rooms,
            index=rooms.index(original),
            key=prefix + "destination",
        )
        eligible = [
            a
            for a in assets
            if a["active"]
            and a["available"]
            and a["room"] == destination
            and a["id"] != source["id"]
            and a["room_type"] == source["room_type"] == "classroom"
        ]
        by_id = {a["id"]: a for a in eligible}
        choices = [None] + list(by_id)
        previous = ids[1] if operation.get("swap") and len(ids) > 1 else None
        partner = st.selectbox(
            "Poste à échanger en retour",
            choices,
            index=choices.index(previous) if previous in choices else 0,
            format_func=lambda value: (
                "Aucun · déplacement simple"
                if value is None
                else asset_label(by_id[value])
            ),
            key=prefix + "swap",
        )
        kwargs = {"destination": destination, "swap": partner}
    else:
        st.caption(
            "Les étapes de l’opération sont vérifiées ensemble avant enregistrement."
        )
        transfers = st.data_editor(
            operation["transfers"],
            hide_index=True,
            width="stretch",
            column_config={
                "source": st.column_config.SelectboxColumn(
                    "Source", options=sorted(data.rooms), required=True
                ),
                "destination": st.column_config.SelectboxColumn(
                    "Destination", options=sorted(data.rooms), required=True
                ),
                "model": st.column_config.TextColumn("Modèle", required=True),
                "quantity": st.column_config.NumberColumn(
                    "Quantité", min_value=1, step=1, required=True
                ),
            },
            disabled=["stock_kind"],
            key=prefix + "transfers",
        )
        kwargs = {"transfers": transfers}
    if st.button("Enregistrer les modifications", type="primary", key=prefix + "save"):
        try:
            store.edit_operation(identifier, batch["id"], index, version, **kwargs)
            close_operation_editor()
            refresh("Opération mise à jour. Aucun ordinateur déplacé.")
        except (ValueError, TypeError) as error:
            st.error(str(error))
    if st.button("Fermer", key=prefix + "close"):
        close_operation_editor()
        st.rerun()


def close_swap_undo():
    st.session_state.lot_swap_undo = None


@st.dialog("Annuler un swap confirmé", width="large", on_dismiss=close_swap_undo)
def swap_undo_dialog(store, identifier, data, revision, batch, index, version):
    st.subheader(batch["name"])
    st.write(f"Opération {index + 1}")
    st.caption(
        "Cette action rétablit les salles d’origine dans l’inventaire. Si les ordinateurs ont réellement été échangés, remets-les physiquement en place avant de confirmer."
    )
    try:
        inverse = store.undo_confirmed_swaps(
            identifier,
            batch["id"],
            [index],
            revision,
            expected_version=version,
            preview=True,
        )
        table(
            [
                {
                    "Service Tag": tag or "Non renseigné",
                    "Modèle": move["model"],
                    "Emplacement actuel": move["source"],
                    "Emplacement rétabli": move["destination"],
                }
                for tag, move in zip(
                    inverse[0]["service_tags"], inverse[0]["transfers"]
                )
            ]
        )
    except ValueError as error:
        st.error(str(error))
        return
    prefix = f"lot_undo_{batch['id']}_{index}_{revision}_{version}_"
    reason = st.radio(
        "Motif",
        [
            "Confirmation saisie par erreur · aucun déplacement physique",
            "Retour physique des deux postes effectué",
        ],
        key=prefix + "reason",
    )
    note = st.text_input(
        "Note d’annulation",
        placeholder="Ex. Swap de test confirmé par erreur",
        key=prefix + "note",
    )
    confirmed = st.checkbox(
        "Je confirme le rétablissement de ces emplacements dans l’inventaire",
        key=prefix + "confirm",
    )
    if st.button(
        "Annuler ce swap dans l’inventaire",
        type="primary",
        disabled=not confirmed or not note.strip(),
        key=prefix + "save",
    ):
        try:
            store.undo_confirmed_swaps(
                identifier,
                batch["id"],
                [index],
                revision,
                reason + " · " + note,
                expected_version=version,
            )
            close_swap_undo()
            refresh("Swap annulé. Inventaire rétabli et historique conservé.")
        except ValueError as error:
            st.error(str(error))


def swap_undo_from_history(store, identifier, data, revision):
    batches = store.batches(identifier)
    choices = [
        (batch, index)
        for batch in batches
        for index, g in enumerate(batch["plan"]["groups"])
        if g.get("completed")
        and g.get("swap")
        and g.get("asset_moves")
        and not g.get("undone")
        and not g.get("deleted")
    ]
    with st.popover("Revenir sur un swap confirmé"):
        if choices:
            selected = st.selectbox(
                "Swap à annuler",
                range(len(choices)),
                format_func=lambda i: (
                    f"{choices[i][0]['name']} · opération {choices[i][1] + 1}"
                ),
                key="history_swap_undo_choice",
            )
            batch, index = choices[selected]
            if st.button("Ouvrir l’annulation", key="history_swap_undo_open"):
                st.session_state.lot_swap_undo = (
                    batch["id"],
                    index,
                    batch["plan"].get("edit_version", 0),
                )
        else:
            st.info("Aucun swap confirmé à annuler.")
    pending = st.session_state.get("lot_swap_undo")
    if pending:
        batch = next((b for b in batches if b["id"] == pending[0]), None)
        if batch:
            swap_undo_dialog(
                store, identifier, data, revision, batch, pending[1], pending[2]
            )


def operation_actions(store, identifier, data, revision, batch):
    plan = batch["plan"]
    version = plan.get("edit_version", 0)
    for index, operation in enumerate(plan["groups"]):
        if operation.get("completed"):
            if (
                operation.get("swap")
                and operation.get("asset_moves")
                and not operation.get("undone")
                and not operation.get("deleted")
            ):
                text, menu = st.columns([12, 1])
                text.write(
                    f"**Opération {index + 1} confirmée** · {operation['source']} ⇄ {operation['room']}"
                )
                with menu.popover("⋮", help=f"Actions du swap confirmé {index + 1}"):
                    if st.button(
                        "Annuler ce swap confirmé",
                        key=f"lot_undo_open_{batch['id']}_{index}",
                    ):
                        st.session_state.lot_swap_undo = (batch["id"], index, version)
            continue
        if operation.get("deleted"):
            continue
        if batch["status"] not in {"Préparé", "Partiel"}:
            continue
        text, menu = st.columns([12, 1])
        text.write(
            f"**Opération {index + 1}** · {operation['source']} → {operation['room']}"
        )
        with menu.popover("⋮", help=f"Actions de l’opération {index + 1}"):
            stale = batch["revision"] != revision
            if st.button(
                "Modifier", key=f"lot_modify_{batch['id']}_{index}", disabled=stale
            ):
                st.session_state.lot_operation_editor = (batch["id"], index, version)
            if st.button(
                "Supprimer", key=f"lot_delete_{batch['id']}_{index}", disabled=stale
            ):
                try:
                    store.delete_operation(identifier, batch["id"], index, version)
                    refresh("Opération supprimée du lot ; inventaire inchangé.")
                except ValueError as error:
                    st.error(str(error))
    removed = [i for i, g in enumerate(plan["groups"]) if g.get("deleted")]
    if removed:
        with st.expander("Opérations supprimées"):
            for index in removed:
                if st.button(
                    f"Restaurer l’opération {index + 1}",
                    key=f"lot_restore_{batch['id']}_{index}",
                    disabled=batch["revision"] != revision,
                ):
                    try:
                        store.restore_operation(identifier, batch["id"], index, version)
                        refresh("Opération restaurée ; inventaire inchangé.")
                    except ValueError as error:
                        st.error(str(error))
    undo = st.session_state.get("lot_swap_undo")
    if undo and undo[0] == batch["id"]:
        swap_undo_dialog(store, identifier, data, revision, batch, undo[1], undo[2])
    editing = st.session_state.get("lot_operation_editor")
    if editing and editing[0] == batch["id"]:
        operation_editor(store, identifier, data, batch, editing[1], editing[2])


def batches_view(store, identifier, data, revision, batch_id=None):
    st.subheader("Lots de déplacements")
    batches = store.batches(identifier)
    if not batches:
        st.info("Aucun lot enregistré pour cet inventaire.")
    for batch in batches:
        if batch_id and batch["id"] != batch_id:
            continue
        with st.expander(
            f"{batch['name']} · {batch['status']} · {batch['id'][:8]}",
            expanded=bool(batch_id),
        ):
            plan = batch["plan"]
            table(transport_summary(plan, data))
            table(operation_rows(plan))
            operation_actions(store, identifier, data, revision, batch)
            context = (batch["revision"], plan.get("edit_version", 0))
            context_key = "lot_confirmation_context_" + batch["id"]
            if st.session_state.get(context_key) != context:
                st.session_state.pop("complete_" + batch["id"], None)
                st.session_state.pop("done_" + batch["id"], None)
                st.session_state[context_key] = context
            st.download_button(
                "Télécharger la feuille de route",
                csv_bytes(transfer_rows(plan, data, for_export=True)),
                f"lot-{batch['id'][:8]}.csv",
                "text/csv",
                key="download_" + batch["id"],
            )
            if batch["status"] in {"Préparé", "Partiel"}:
                if batch["revision"] != revision:
                    st.info(
                        "Ce lot a été préparé sur un inventaire plus ancien. Il faut le recalculer pour éviter d'utiliser un stock déjà déplacé."
                    )
                else:
                    remaining = [
                        i
                        for i, g in enumerate(plan["groups"])
                        if not g.get("completed") and not g.get("deleted")
                    ]
                    with st.form("confirm_" + batch["id"]):
                        selected = st.multiselect(
                            "Opérations entièrement réalisées",
                            remaining,
                            format_func=lambda i: (
                                f"{i + 1}. {plan['groups'][i]['room']}"
                            ),
                            key="complete_" + batch["id"],
                        )
                        st.caption(
                            "Chaque opération cochée doit être entièrement réalisée. "
                            "Une ligne avec ↔ concerne plusieurs salles : toutes ses étapes sont indivisibles. "
                            "Respecter l’ordre de la feuille de route ; certains stocks proviennent d’une étape précédente."
                        )
                        note = st.text_input(
                            "Note de réalisation (intervenant, date ou référence)",
                            key="note_" + batch["id"],
                        )
                        confirmed = st.checkbox(
                            "Je confirme que ces déplacements ont réellement été effectués",
                            key="done_" + batch["id"],
                        )
                        submit = st.form_submit_button("Mettre à jour l'inventaire")
                    if submit:
                        if not confirmed:
                            st.error(
                                "Confirme la réalisation physique avant de modifier l'inventaire."
                            )
                        else:
                            try:
                                store.confirm_batch(
                                    identifier,
                                    batch["id"],
                                    selected,
                                    note,
                                    expected_version=plan.get("edit_version", 0),
                                )
                                refresh(
                                    "Déplacements enregistrés. L'inventaire et les totaux par bâtiment sont à jour."
                                )
                            except ValueError as error:
                                st.error(str(error))
                if st.button("Annuler le reste de ce lot", key="cancel_" + batch["id"]):
                    store.cancel_batch(identifier, batch["id"])
                    refresh(
                        "Lot annulé. Les déplacements déjà confirmés sont conservés."
                    )
    if batch_id:
        return
    st.subheader("Historique des mises à jour")
    history = store.history(identifier)
    table(
        [
            {"Date (UTC)": e["created"], "Action": e["kind"], "Note": e["note"]}
            for e in history
        ]
    )
    if history:
        st.download_button(
            "Exporter l'historique détaillé",
            csv_bytes(history),
            "evergreen-historique.csv",
            "text/csv",
        )
