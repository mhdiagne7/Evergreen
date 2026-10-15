"""Créer un objectif commun pour un bloc de petits bâtiments proches."""

import streamlit as st

from core.blocks import block_candidates, block_diameter, plan_blocks, suggest_blocks
from core.campus import CENTRAL_STOCK
from core.export import csv_bytes
from ui.common import operation_rows, refresh, table, transfer_rows, transport_summary


def block_planning(store, identifier, data, models, revision):
    st.subheader("Un même modèle pour un bloc de bâtiments")
    st.caption(
        "Les ordinateurs restent dans leurs salles. Le bloc partage un modèle cible ; les interventions sont planifiées ensemble."
    )
    with st.expander("Définir les bâtiments voisins", expanded=True):
        left, right = st.columns(2)
        max_posts = int(
            left.number_input(
                "Postes maximum par bâtiment", 1, 30, 5, key="block_posts"
            )
        )
        max_distance = int(
            right.number_input(
                "Écart maximal entre bâtiments (m)",
                25,
                2000,
                200,
                25,
                key="block_radius",
            )
        )
        st.caption(
            "Proximité à vol d’oiseau entre chaque paire de bâtiments, distincte d’une distance de marche."
        )
    suggestions = suggest_blocks(data, max_posts, max_distance)
    options = {" + ".join(group): group for group in suggestions}
    if options:
        chosen = st.multiselect(
            "Blocs proposés",
            list(options),
            default=list(options),
            key="block_suggestions",
        )
    else:
        chosen = []
        st.info("Aucun bloc pour ces seuils. Ajuste-les ou crée un bloc manuellement.")
    all_codes = sorted(
        {r.building for r in data.rooms.values() if r.room_type == "classroom"}
    )
    with st.expander("Créer un bloc personnalisé"):
        manual = st.multiselect(
            "Bâtiments du bloc personnalisé", all_codes, key="block_manual"
        )
    groups = [options[name] for name in chosen]
    if manual:
        if len(manual) < 2:
            st.info("Choisis au moins deux bâtiments pour le bloc personnalisé.")
        else:
            groups.append(tuple(sorted(manual)))
    blocks = []
    for buildings in groups:
        label = " + ".join(buildings)
        with st.container(border=True):
            st.markdown(f"**Bloc · {label}**")
            diameter = block_diameter(buildings)
            st.caption(
                f"Écart maximal : {diameter:.0f} m à vol d’oiseau"
                if diameter is not None
                else "Coordonnées incomplètes"
            )
            candidates = block_candidates(data, buildings)
            leaders = (
                [
                    row["Modèle"]
                    for row in candidates
                    if row["Déjà dans le bloc"] == candidates[0]["Déjà dans le bloc"]
                ]
                if candidates
                else []
            )
            choices = ["Choisir un modèle"] + list(models)
            default = (
                choices.index(leaders[0])
                if len(leaders) == 1 and leaders[0] in choices
                else 0
            )
            model = st.selectbox(
                "Modèle commun du bloc",
                choices,
                index=default,
                key="block_target_" + label,
            )
            if model != choices[0]:
                counts = {row["Modèle"]: row["Déjà dans le bloc"] for row in candidates}
                total = sum(counts.values())
                st.caption(
                    f"{total} postes dans le bloc · {counts.get(model, 0)} déjà conformes · "
                    f"{total - counts.get(model, 0)} à regrouper"
                )
                blocks.append({"buildings": list(buildings), "model": model})
            with st.expander("Comparer les modèles du bloc · " + label):
                table(candidates)
    protect = st.checkbox(
        "Protéger les générations connues comme plus récentes",
        value=True,
        key="block_protect",
    )
    donors = st.checkbox(
        "Inclure les autres bâtiments à modèle dominant pour permettre les échanges",
        value=True,
        key="block_donors",
    )
    st.caption(
        "Seuls les postes non conformes à leur cible peuvent être échangés. Les salles restent équipées et Morisset reste l’unique stock."
    )
    signature = (identifier, revision, str(blocks), str(groups), protect, donors)
    if st.button("Préparer les blocs", key="block_calculate"):
        try:
            if not groups or len(blocks) != len(groups):
                raise ValueError("Choisis un modèle pour chaque bloc sélectionné.")
            plan = plan_blocks(data, blocks, CENTRAL_STOCK, protect, donors)
            st.session_state.block_preview = signature, plan
        except ValueError as error:
            st.error(str(error))
    preview = st.session_state.get("block_preview")
    if not preview or preview[0] != signature:
        return
    plan = preview[1]
    st.subheader("Résultat des blocs")
    table(plan["block_summary"])
    missing = sum(row["Manque"] for row in plan["block_summary"])
    if missing:
        st.info(
            f"{missing} poste(s) restent à regrouper dans les blocs. Consulte les besoins avant d’ajouter du stock."
        )
    with st.expander("Résultat par bâtiment et besoins restants"):
        table(plan["summary"])
    table(transport_summary(plan, data))
    table(operation_rows(plan))
    if not plan["groups"]:
        st.info("Aucun échange réalisable avec les stocks et contraintes actuels.")
        return
    with st.expander("Étapes des échanges"):
        table(transfer_rows(plan, data))
    name = st.text_input(
        "Nom du lot de blocs", "Regroupement par blocs", key="block_name"
    )
    st.download_button(
        "Exporter les interventions des blocs",
        csv_bytes(transfer_rows(plan, data, for_export=True)),
        "evergreen-blocs.csv",
        "text/csv",
    )
    if st.button("Enregistrer les blocs", key="block_save"):
        try:
            store.save_batch(identifier, revision, name, plan)
            st.session_state.pop("block_preview", None)
            refresh(
                "Lot de blocs enregistré. L’inventaire changera après confirmation des interventions réalisées."
            )
        except ValueError as error:
            st.error(str(error))
