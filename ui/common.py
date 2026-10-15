"""Petits composants partagés par les vues."""

import math

import streamlit as st

from core.graph import build_graph
from core.routing import shortest_route


def table(rows):
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")


def refresh(message):
    st.session_state.notice = message
    st.rerun()


def finite_places(value):
    return int(value) if math.isfinite(value) else None


def operation_rows(plan):
    return [
        {
            "Opération": index,
            "Salle à équiper": group["room"],
            "Modèle actuel": group["old_model"],
            "Modèle à installer": group["new_model"],
            "Source du poste": group["source"],
            "Catégorie": (
                "Retour réaffecté"
                if group.get("stock_kind") == "returned"
                else "Regroupement de modèles"
                if group.get("stock_kind") == "regrouped"
                else "Stock neuf Morisset"
                if group.get("stock_kind") == "new"
                else "Stock disponible"
            ),
            "Livraison (m)": group["delivery_m"],
            "Distance": group["distance_type"],
            "État": "Fait" if group.get("completed") else "À faire",
        }
        for index, group in enumerate(plan["groups"], 1)
    ]


def transfer_rows(plan, data, for_export=False):
    graph = build_graph(data)
    rows = []
    for group in plan["groups"]:
        for index, move in enumerate(group["transfers"], 1):
            route = shortest_route(graph, move["source"], move["destination"])
            google_export = (
                for_export and route and "Google Maps" in route.distance_label
            )
            rows.append(
                {
                    "Salle concernée": group["room"],
                    "Étape": index,
                    "Bâtiment source": data.rooms[move["source"]].building,
                    "Source": move["source"],
                    "Bâtiment destination": data.rooms[move["destination"]].building,
                    "Destination": move["destination"],
                    "Modèle": move["model"],
                    "Quantité": move["quantity"],
                    "Distance (m)": route.distance_m
                    if route and not google_export
                    else None,
                    "Type de distance": "Consulter Google Maps dans l’application"
                    if google_export
                    else route.distance_label
                    if route
                    else "Non disponible",
                }
            )
    return rows


def transport_summary(plan, data):
    totals = {}
    for group in plan["groups"]:
        for move in group["transfers"]:
            origin = data.rooms[move["source"]].building
            destination = data.rooms[move["destination"]].building
            if origin != destination:
                key = origin, destination, move["model"]
                totals[key] = totals.get(key, 0) + move["quantity"]
    return [
        {"Depuis": origin, "Vers": target, "Modèle": model, "Ordinateurs": quantity}
        for (origin, target, model), quantity in sorted(totals.items())
    ]
