"""Interface locale ; lancer avec python -m streamlit run app.py."""
import csv
import io
import streamlit as st
from core.data import load_data
from core.graph import build_graph
from core.routing import shortest_route
from core.optimizer import compatible_destinations, prepare_grouping

st.set_page_config(page_title="Evergreen Optimizer", page_icon="🌿", layout="centered")
st.title("🌿 uOttawa Evergreen Optimizer")
st.caption("Prototype indépendant • Planification de déplacements de matériel")
st.warning("DÉMONSTRATION — Salles, connexions, distances, capacités et inventaires entièrement fictifs. Aucun plan réel du campus. Aucune affiliation officielle à uOttawa.")
try:
    data = load_data()
except (ValueError, OSError) as error:
    st.error(f"Impossible de charger les données : {error}")
    st.stop()
graph = build_graph(data)
rooms = list(data.rooms)
models = sorted({model for _, model in data.inventory})
a, b, c = st.columns(3)
a.metric("Salles fictives", len(rooms))
b.metric("Ordinateurs fictifs", sum(data.inventory.values()))
c.metric("Places disponibles", sum(data.available(room) for room in rooms))


def show_route(route):
    if route is None:
        st.info("Aucun chemin disponible entre ces salles.")
    else:
        st.success(f"Distance {route.distance_label} : {route.distance_m:g} m")
        st.write(" → ".join(route.nodes))


def move_rows(moves):
    return [{"Source": move.source, "Destination": move.destination, "Modèle": move.model,
             "Quantité": move.quantity, "Distance (m)": move.route.distance_m,
             "Nature de la distance": move.route.distance_label,
             "Chemin": " → ".join(move.route.nodes), "Données": "FICTIVES"} for move in moves]


routing, compatibility, grouping, inventory = st.tabs(["Trajet", "Destinations compatibles", "Regroupement Evergreen", "Données fictives"])
with routing:
    st.subheader("Calculer un trajet")
    source = st.selectbox("Salle de départ", rooms, key="route_source")
    destination = st.selectbox("Salle d'arrivée", rooms, index=2, key="route_destination")
    show_route(shortest_route(graph, source, destination))
    st.caption("Dijkstra minimise la somme des distances du graphe. Les liaisons sont bidirectionnelles et fictives.")
with compatibility:
    st.subheader("Déplacer un lot d'un même modèle")
    source = st.selectbox("Salle source", rooms, key="compat_source")
    available_models = sorted(model for (room, model), stock in data.inventory.items() if room == source and stock > 0)
    if available_models:
        model = st.selectbox("Modèle à déplacer", available_models)
        stock = data.inventory[source, model]
        quantity = int(st.number_input("Quantité à déplacer", min_value=1, max_value=stock, value=min(5, stock), key=f"quantity_{source}_{model}"))
        candidates = compatible_destinations(data, graph, source, model, quantity)
        if candidates:
            st.dataframe(move_rows(candidates), hide_index=True, use_container_width=True)
        else:
            st.info("Aucune destination accessible ne peut recevoir ce lot. Essayez une quantité plus petite.")
    else:
        st.info("Aucun ordinateur à déplacer depuis cette salle.")
    st.caption("Une salle doit autoriser le modèle et disposer d'assez de places, tous modèles présents confondus. Chaque ligne est une alternative indépendante.")
with grouping:
    st.subheader("Préparer un regroupement")
    st.write("Choisissez une cible et le nombre d'ordinateurs supplémentaires souhaité. Les sources accessibles les plus proches sont utilisées en premier.")
    model = st.selectbox("Modèle à regrouper", models)
    targets = [room for room in rooms if model in data.rooms[room].allowed_models]
    target = st.selectbox("Salle cible", targets)
    quantity = int(st.number_input("Nombre supplémentaire souhaité", min_value=1, max_value=10000, value=10))
    plan = prepare_grouping(data, graph, target, model, quantity)
    st.write(f"Places libres : **{data.available(target)}** · Prévu : **{plan.moved}** · Non satisfait : **{plan.remaining}**")
    if plan.remaining:
        st.warning("Proposition partielle : capacité ou stock accessible insuffisant.")
    if plan.moves:
        rows = move_rows(plan.moves)
        st.dataframe(rows, hide_index=True, use_container_width=True)
        st.caption(f"Effort indicatif : {plan.effort:g} ordinateur·m. Ce n'est ni une durée ni un nombre de voyages.")
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        st.download_button("Télécharger la proposition fictive (CSV)", output.getvalue().encode("utf-8-sig"), "evergreen-proposition-fictive.csv", "text/csv")
    else:
        st.info("Aucun déplacement possible avec ces paramètres.")
    st.caption("Proposition indépendante et sans réservation : l'inventaire n'est jamais modifié. Pas d'optimisation globale, de gestion des chariots, d'accessibilité ou de calendrier de renouvellement.")
with inventory:
    st.dataframe([{"Salle": room, "Bâtiment": info.building, "Capacité fictive": info.capacity,
                   "Occupé": data.occupied(room), "Libre": data.available(room),
                   "Modèles autorisés": ", ".join(sorted(info.allowed_models))} for room, info in data.rooms.items()], hide_index=True, use_container_width=True)
    st.dataframe([{"Salle": room, "Modèle": model, "Quantité": quantity} for (room, model), quantity in data.inventory.items()], hide_index=True, use_container_width=True)
    st.caption("MRT, UCU, STE et CBY servent uniquement d'inspiration nominale. Une distance simulée est inventée ; une distance estimée serait une approximation explicitement identifiée. Toutes les distances fournies ici sont simulées.")
