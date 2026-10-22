"""Question libre, interprétation vérifiée, puis proposition sans effet sur le stock."""

import streamlit as st

from core.assistant import calculate, interpret
from ui.common import operation_rows, table, transfer_rows
from ui.navigation import PAGES


def assistant_view(store, identifier, data, models, revision):
    st.write(
        "Posez une question sur les modèles présents ou un regroupement. Les nombres et les interventions seront calculés par Evergreen."
    )
    st.caption(
        "IA locale : qwen3:4b via Ollama. Elle reçoit votre question et les noms des bâtiments/modèles, sans les quantités ni les identifiants de salle. Aucun service externe n’est configuré."
    )
    with st.expander("Mise en route de l’IA locale"):
        st.write(
            "Installer Ollama sur cet ordinateur, télécharger qwen3:4b puis démarrer le service local. Voir le README pour Mac, Windows et Linux."
        )
        st.code("ollama pull qwen3:4b\nollama serve", language="sh")
    question = st.text_area(
        "Votre question",
        placeholder="Quels modèles sont installés à CBY ? Ou : propose un regroupement par modèle dominant.",
        max_chars=2000,
    )
    context = identifier, revision, question
    if st.button("Comprendre ma demande", type="primary"):
        st.session_state.pop("assistant_result", None)
        st.session_state.pop("assistant_intent", None)
        try:
            buildings = sorted(
                {r.building for r in data.rooms.values() if r.room_type == "classroom"}
            )
            with st.spinner("Lecture de la question par le modèle local…"):
                intent = interpret(question, buildings, models)
            st.session_state.assistant_intent = context, intent
        except ValueError as error:
            st.error(str(error))
    parsed = st.session_state.get("assistant_intent")
    if not parsed or parsed[0] != context:
        return
    intent = parsed[1]
    if intent["action"] == "clarifier":
        st.info(
            "La demande nécessite une précision. Indiquez les bâtiments, le modèle et l’objectif. Cette version sait consulter l’inventaire et préparer des regroupements ; elle ne réalise pas les déplacements."
        )
        return
    st.subheader("Vérifier la demande comprise")
    st.write(
        {
            "Opération": intent["action"],
            "Bâtiments": intent["buildings"] or "Tous",
            "Modèle": intent["model"] or "Tous / cible dominante",
        }
    )
    st.caption(
        "Vérifiez ces paramètres avant de calculer : une IA peut mal interpréter une question. Les générations connues comme plus récentes restent protégées."
    )
    if st.button("Calculer avec ces paramètres"):
        try:
            st.session_state.assistant_result = context, calculate(data, models, intent)
        except ValueError as error:
            st.error(str(error))
    result = st.session_state.get("assistant_result")
    if not result or result[0] != context:
        return
    result = result[1]
    st.subheader("Résultat calculé depuis l’inventaire")
    table(result["rows"])
    if result["stock"]:
        st.write("Stock central, présenté séparément des ordinateurs installés")
        table(result["stock"])
    plan = result["plan"]
    if plan:
        st.info(
            "Proposition réalisable selon les données disponibles, sans garantie d’optimum global. Les distances inconnues restent inconnues. Aucun ordinateur n’a été déplacé."
        )
        table(operation_rows(plan))
        with st.expander("Détail des étapes"):
            table(transfer_rows(plan, data))
        if plan["groups"] and st.button("Enregistrer cette proposition comme lot"):
            try:
                store.save_batch(
                    identifier, revision, "Proposition de regroupement", plan
                )
                st.session_state.pop("assistant_result", None)
                st.session_state.pop("assistant_intent", None)
                st.success(
                    "Lot enregistré. Confirmez sa réalisation uniquement après les interventions."
                )
            except ValueError as error:
                st.error(str(error))
        st.page_link(PAGES["lots"], label="Consulter les lots →")
