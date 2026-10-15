"""Objectifs automatiques par modèle dominant et aperçu des regroupements."""

import streamlit as st

from core.export import csv_bytes
from core.homogeneity import (
    building_models,
    plan_homogeneity,
    suggested_targets,
)
from ui.common import operation_rows, refresh, table, transfer_rows, transport_summary


def homogenization(store, identifier, data, models, revision):
    st.subheader("Un modèle principal par bâtiment")
    st.write(
        "Le modèle le plus présent devient la cible du bâtiment. "
        "Les postes déjà conformes restent en place ; les autres sont remplacés "
        "à partir de Morisset ou redistribués entre bâtiments."
    )
    buildings = sorted(
        {info.building for info in data.rooms.values() if info.room_type == "classroom"}
    )
    selected = st.multiselect(
        "Bâtiments à regrouper", buildings, default=buildings, key="uniform_buildings"
    )
    targets = suggested_targets(data)
    configured = {
        building: targets[building] for building in selected if building in targets
    }
    ties = [building for building in selected if building not in targets]
    if ties:
        with st.expander(
            f"Choisir les cibles de {len(ties)} bâtiment(s) à égalité", expanded=True
        ):
            for building in ties:
                options = ["Choisir un modèle"] + list(models)
                selected_model = st.selectbox(
                    f"{building} · modèle cible",
                    options,
                    key="uniform_tie_" + building,
                )
                if selected_model != options[0]:
                    configured[building] = selected_model
    with st.expander("Modifier un modèle cible"):
        override = st.selectbox(
            "Bâtiment à ajuster", ["Aucun"] + selected, key="uniform_override_building"
        )
        if override != "Aucun":
            target = configured.get(override)
            replacement = st.selectbox(
                "Modèle cible choisi",
                models,
                index=models.index(target) if target in models else 0,
                key="uniform_override_model_" + override,
            )
            configured[override] = replacement
    rows = []
    for building in selected:
        counts = +building_models(data, building)
        target = configured.get(building)
        total = sum(
            info.capacity or 0
            for info in data.rooms.values()
            if info.building == building and info.room_type == "classroom"
        )
        present = counts.get(target, 0)
        rows.append(
            {
                "Bâtiment": building,
                "Modèle cible": target or "À choisir",
                "Postes attendus": total,
                "Déjà conformes": present,
                "À regrouper": total - present,
                "Part actuelle (%)": round(100 * present / total, 1) if total else 0,
            }
        )
    table(rows)
    stocks = sorted(
        room
        for room, info in data.rooms.items()
        if info.building == "MRT" and info.room_type == "storage"
    )
    if not stocks or not models:
        st.info(
            "Définis le stock central à Morisset et au moins un modèle avant de préparer un regroupement."
        )
        return
    stock = st.selectbox("Stock et transit à Morisset", stocks, key="uniform_stock")
    protect = st.checkbox(
        "Conserver les modèles connus comme plus récents",
        value=True,
        key="uniform_protect",
    )
    st.caption(
        "Le regroupement redistribue les modèles existants ; il ne constitue pas une promesse de matériel plus récent. "
        "Les générations inconnues ne sont pas classées. Les échanges liés sont confirmés ensemble, "
        "et aucun poste déjà conforme n’est prélevé."
    )
    signature = (
        identifier,
        revision,
        tuple(sorted(configured.items())),
        tuple(selected),
        stock,
        protect,
    )
    if st.button("Préparer le regroupement", key="uniform_calculate"):
        if set(configured) != set(selected):
            st.error(
                "Choisis le modèle cible des bâtiments en égalité avant de continuer."
            )
        else:
            try:
                result = plan_homogeneity(data, configured, stock, protect)
                st.session_state.uniform_preview = signature, result
            except ValueError as error:
                st.error(str(error))
    preview = st.session_state.get("uniform_preview")
    if not preview or preview[0] != signature:
        return
    plan = preview[1]
    st.write("**Résultat proposé par bâtiment**")
    table(plan["summary"])
    missing = sum(row["Manque"] for row in plan["summary"])
    if missing:
        st.info(
            f"{missing} poste(s) restent à regrouper : les quantités disponibles, la capacité "
            "de transit, les générations protégées ou les trajets empêchent un regroupement complet."
        )
    table(transport_summary(plan, data))
    table(operation_rows(plan))
    if not plan["groups"]:
        return
    with st.expander("Ordre des interventions et échanges liés"):
        table(transfer_rows(plan, data))
    name = st.text_input(
        "Nom du regroupement",
        value="Regroupement des modèles par bâtiment",
        key="uniform_name",
    )
    st.download_button(
        "Exporter les interventions",
        csv_bytes(transfer_rows(plan, data, for_export=True)),
        "evergreen-regroupement.csv",
        "text/csv",
    )
    if st.button("Enregistrer le regroupement", key="uniform_save"):
        try:
            store.save_batch(identifier, revision, name, plan)
            st.session_state.pop("uniform_preview", None)
            refresh(
                "Regroupement enregistré. Les stocks changeront après confirmation physique du lot."
            )
        except ValueError as error:
            st.error(str(error))
