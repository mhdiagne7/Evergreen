"""Confirmer les mouvements physiques et consulter leur historique."""

import streamlit as st

from core.export import csv_bytes
from ui.common import operation_rows, refresh, table, transfer_rows, transport_summary


def batches_view(store, identifier, data, revision):
    st.subheader("Lots de déplacements")
    batches = store.batches(identifier)
    if not batches:
        st.info("Aucun lot enregistré pour cet inventaire.")
    for batch in batches:
        with st.expander(f"{batch['name']} · {batch['status']} · {batch['id'][:8]}"):
            plan = batch["plan"]
            table(transport_summary(plan, data))
            table(operation_rows(plan))
            st.download_button(
                "Télécharger la feuille de route",
                csv_bytes(transfer_rows(plan, data)),
                f"lot-{batch['id'][:8]}.csv",
                "text/csv",
                key="download_" + batch["id"],
            )
            if batch["status"] in {"Préparé", "Partiel"}:
                if batch["revision"] != revision:
                    st.warning(
                        "Ce lot a été préparé sur un inventaire plus ancien. Il faut le recalculer pour éviter d'utiliser un stock déjà déplacé."
                    )
                else:
                    remaining = [
                        i
                        for i, g in enumerate(plan["groups"])
                        if not g.get("completed")
                    ]
                    with st.form("confirm_" + batch["id"]):
                        selected = st.multiselect(
                            "Salles dont le remplacement est entièrement terminé",
                            remaining,
                            format_func=lambda i: plan["groups"][i]["room"],
                            key="complete_" + batch["id"],
                        )
                        st.caption(
                            "Pour chaque salle cochée, le retrait, l'installation et le retour doivent tous être réalisés. Respecter l'ordre de la feuille de route ; certains stocks proviennent d'une étape précédente."
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
                                    identifier, batch["id"], selected, note
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
