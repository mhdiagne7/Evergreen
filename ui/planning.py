"""Préparer et enregistrer les propositions de renouvellement."""

import streamlit as st

from core.buildings import plan_building
from core.export import csv_bytes
from core.reuse import add_reuse_operations
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
    reuse = st.checkbox(
        "Réaffecter les retours plus récents à d’autres bâtiments",
        value=True,
        key="plan_reuse",
    )
    st.caption(
        "Les nouveaux postes partent de Morisset et les anciens y reviennent. "
        "Les retours peuvent ensuite améliorer une autre salle, uniquement si leur année de génération "
        "est plus récente que celle du poste à remplacer. Renseigne ces années dans Stock et modèles."
    )
    signature = (
        identifier,
        revision,
        building,
        tuple(sorted(goals.items())),
        buffer,
        reuse,
    )
    if st.button("Calculer les propositions", key="calculate"):
        try:
            plan = plan_building(data, building, goals, buffer)
            if reuse:
                plan = add_reuse_operations(data, plan)
            st.session_state.preview = (signature, plan)
        except ValueError as error:
            st.session_state.pop("preview", None)
            st.error(str(error))
    preview = st.session_state.get("preview")
    if preview and preview[0] == signature:
        plan = preview[1]
        table(plan["summary"])
        if any(row["Manque"] for row in plan["summary"]):
            st.info(
                "Objectif partiellement réalisable avec le stock et les contraintes actuels. "
                "Un modèle ajouté au catalogue n’ajoute aucun ordinateur au stock."
            )
        if plan.get("reuse_count"):
            st.caption(
                f"{plan['reuse_count']} réaffectation(s) de retours proposées dans d’autres bâtiments."
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
