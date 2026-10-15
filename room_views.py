"""Recherche ponctuelle de salles libres, complément de la planification bâtiment."""

import streamlit as st

from core.export import csv_bytes
from core.optimizer import evaluate_destinations
from ui.common import finite_places


def show_route(route):
    if route is None:
        st.info("Aucun chemin renseigné entre ces salles.")
    else:
        if route.distance_m is None:
            st.info("Même bâtiment : distance intérieure non évaluée.")
        else:
            st.success(f"Distance {route.distance_label} : {route.distance_m:.0f} m")
        st.text(" → ".join(route.nodes))


def recommendations(data, graph, rooms, label):
    st.subheader("Où déplacer ces ordinateurs ?")
    st.write(
        "Choisis une salle, un modèle et une quantité. La première proposition sera la salle compatible la plus proche par les chemins renseignés."
    )
    source = st.selectbox("Salle source", rooms, key="choice_source")
    models = sorted(
        model
        for (room, model), stock in data.inventory.items()
        if room == source and stock > 0
    )
    if not models:
        st.info("Cette salle ne contient aucun ordinateur à déplacer.")
        return
    model = st.selectbox("Modèle à déplacer", models, key="choice_model_" + source)
    stock = data.inventory[source, model]
    quantity = int(
        st.number_input(
            "Quantité à déplacer",
            1,
            stock,
            min(5, stock),
            key=f"choice_qty_{source}_{model}",
        )
    )
    st.caption(
        f"Stock disponible pour ce modèle : {stock}. La capacité libre des destinations tient compte de tous les modèles présents."
    )
    evaluated = evaluate_destinations(data, graph, source, model, quantity)
    candidates = [item for item in evaluated if not item.reasons]
    if candidates:
        best = candidates[0]
        distance = (
            f"{best.route.distance_m:.0f} m ({best.route.distance_label})"
            if best.route.distance_m is not None
            else "distance intérieure inconnue"
        )
        places = finite_places(best.free_places)
        capacity = (
            f"{places} place(s) libre(s)"
            if places is not None
            else "capacité sans limite configurée"
        )
        st.success(f"Destination conseillée : {best.room} · {distance} · {capacity}")
        st.caption(
            "Classement par distance croissante. En cas d'égalité, les salles sont présentées par ordre alphabétique ; elles sont équivalentes pour ce critère."
        )
        rows = [
            {
                "Rang": index,
                "Salle": item.room,
                "Distance (m)": item.route.distance_m,
                "Distance": item.route.distance_label,
                "Places libres": finite_places(item.free_places),
                "Places après déplacement": finite_places(item.free_places - quantity),
            }
            for index, item in enumerate(candidates, 1)
        ]
        st.dataframe(rows, hide_index=True, width="stretch")
        selected = st.selectbox(
            "Voir le chemin vers",
            [item.room for item in candidates],
            key=f"choice_candidate_{source}_{model}_{quantity}",
        )
        show_route(next(item.route for item in candidates if item.room == selected))
        export = [
            {
                **row,
                "Source": source,
                "Modèle": model,
                "Quantité": quantity,
                "Jeu de données": label,
            }
            for row in rows
        ]
        st.download_button(
            "Exporter les propositions",
            csv_bytes(export),
            "evergreen-destinations.csv",
            "text/csv",
        )
    else:
        st.info(
            "Aucune destination ne peut recevoir tout le lot avec les données actuelles."
        )
    rejected = [item for item in evaluated if item.reasons]
    if rejected:
        with st.expander("Pourquoi les autres salles ne sont-elles pas proposées ?"):
            st.dataframe(
                [
                    {
                        "Salle": item.room,
                        "Distance (m)": item.route.distance_m if item.route else None,
                        "Motif": " ; ".join(item.reasons),
                    }
                    for item in rejected
                ],
                hide_index=True,
                width="stretch",
            )
    st.caption(
        "Chaque proposition est une alternative. Rien n'est déplacé ou réservé dans l'inventaire."
    )
