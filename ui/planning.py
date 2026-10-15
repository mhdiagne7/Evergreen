"""Préparer et enregistrer les propositions de renouvellement."""

import streamlit as st

from core.buildings import plan_building
from core.export import csv_bytes
from ui.common import operation_rows, refresh, table, transfer_rows, transport_summary


def planning(store, identifier, data, models, revision):
    st.subheader("Préparer un lot Evergreen pour un bâtiment")
    st.write(
        "L'objectif est le nombre total de classes à équiper avec chaque modèle après les déplacements. Les classes déjà équipées comptent dans cet objectif."
    )
    buildings = sorted({r.building for r in data.rooms.values()})
    building = st.selectbox("Bâtiment à équiper", buildings, key="plan_building")
    classes = [
        r
        for r, info in data.rooms.items()
        if info.building == building
        and info.room_type == "classroom"
        and info.capacity == 1
    ]
    reserves = sorted(
        r
        for r, info in data.rooms.items()
        if info.building == "MRT" and info.room_type == "storage"
    )
    st.caption(
        f"{len(classes)} classes à un poste dans ce bâtiment. Les salles de capacité différente restent visibles dans l'inventaire mais ne sont pas remplacées automatiquement."
    )
    if not reserves or not classes or not models:
        st.info(
            "Il faut des salles à un poste, au moins un modèle au catalogue et un stock de retour central à MRT."
        )
        return
    chosen = st.multiselect(
        "Modèles souhaités dans ce bâtiment",
        models,
        default=models[:1],
        key="plan_models",
    )
    goals = {
        model: int(
            st.number_input(
                f"Nombre total de classes en {model}",
                min_value=1,
                max_value=len(classes),
                value=min(10, len(classes)),
                key=f"goal_{building}_{model}",
            )
        )
        for model in chosen
    }
    buffer = st.selectbox("Stock central de retour à MRT", reserves, key="plan_buffer")
    swaps = st.checkbox(
        "Autoriser les échanges avec des classes d'autres bâtiments", key="plan_swaps"
    )
    st.caption(
        "Priorité au stock disponible, puis à la somme des distances des retraits, livraisons et retours. Les anciens postes reviennent à MRT. Un échange conserve un poste dans la salle source. Les distances à vol d’oiseau servent au classement, sans garantir une tournée optimale."
    )
    signature = (
        identifier,
        revision,
        building,
        tuple(sorted(goals.items())),
        buffer,
        swaps,
    )
    if st.button("Calculer les propositions", key="calculate"):
        try:
            st.session_state.preview = (
                signature,
                plan_building(data, building, goals, buffer, swaps),
            )
        except ValueError as error:
            st.session_state.pop("preview", None)
            st.error(str(error))
    preview = st.session_state.get("preview")
    if preview and preview[0] == signature:
        plan = preview[1]
        table(plan["summary"])
        if any(row["Manque"] for row in plan["summary"]):
            st.warning(
                "Objectif partiellement réalisable. Les propositions respectent le stock, les modèles autorisés, les chemins et la capacité de retour. Essaie un objectif plus petit, un arrivage ou les échanges entre classes. Un modèle ajouté au catalogue n'ajoute aucun ordinateur au stock."
            )
        if not plan["groups"]:
            st.info(
                "Aucun changement proposé : objectif déjà atteint ou aucun remplacement réalisable avec ces contraintes."
            )
            return
        st.write("**Transport entre bâtiments**")
        transports = transport_summary(plan, data)
        table(transports)
        if not transports:
            st.caption(
                "Ce lot ne comporte que des déplacements à l’intérieur du bâtiment."
            )
        st.write("**Interventions dans les salles**")
        table(operation_rows(plan))
        with st.expander("Feuille de route : retraits, livraisons et retours"):
            table(transfer_rows(plan, data))
        name = st.text_input(
            "Nom du lot", value=f"Evergreen {building}", key="batch_name"
        )
        st.download_button(
            "Exporter la feuille de route",
            csv_bytes(transfer_rows(plan, data)),
            "evergreen-feuille-de-route.csv",
            "text/csv",
        )
        if st.button("Enregistrer ce lot à réaliser", key="save_batch"):
            try:
                store.save_batch(identifier, revision, name, plan)
                st.session_state.pop("preview", None)
                refresh(
                    "Lot enregistré. L'inventaire reste inchangé jusqu'à confirmation dans « Lots et historique »."
                )
            except ValueError as error:
                st.error(str(error))
    elif preview:
        st.info(
            "Les paramètres ou l'inventaire ont changé. Recalcule les propositions avant d'enregistrer un lot."
        )
