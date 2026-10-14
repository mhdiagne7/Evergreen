"""L'application se lance depuis son dossier avec Streamlit."""
import networkx as nx
import streamlit as st
from core.data import DEMO_DIR, SCHEMAS, load_data
from core.export import csv_bytes
from core.graph import build_graph
from core.optimizer import evaluate_destinations, prepare_grouping
from core.routing import shortest_route
from core.session import activate_import, reset_choices


def show_route(route):
    if route is None:
        st.info("Aucun chemin renseigné entre ces salles.")
    else:
        st.success(f"Distance {route.distance_label} : {route.distance_m:g} m")
        st.text(" → ".join(route.nodes))


def move_rows(moves, label):
    return [{"Source": move.source, "Destination": move.destination, "Modèle": move.model,
             "Quantité": move.quantity, "Distance (m)": move.route.distance_m,
             "Nature de la distance": move.route.distance_label,
             "Chemin": " → ".join(move.route.nodes), "Jeu de données": label}
            for move in moves]


def data_sidebar():
    with st.sidebar:
        st.header("Mes données")
        st.caption(st.session_state.dataset_label)
        with st.expander("Importer mes CSV"):
            st.write("Choisis les trois fichiers d'un même inventaire. Ils remplaceront ensemble les données actives après validation.")
            files = {name: st.file_uploader(name, type="csv", key="upload_" + name) for name in SCHEMAS}
            if st.button("Vérifier et utiliser ces données", key="apply_import"):
                try:
                    payload = {name: file.getvalue() for name, file in files.items() if file is not None}
                    activate_import(st.session_state, payload)
                except (ValueError, UnicodeError) as error:
                    st.error(str(error))
                    st.info("Les données actives n'ont pas changé.")
                else:
                    st.rerun()
            st.caption("L'import reste en mémoire dans cette session locale. Il n'est pas ajouté au dépôt ni conservé après fermeture de la session. Garde tes fichiers originaux.")
        if st.button("Revenir à la démonstration", key="reset_demo"):
            st.session_state.dataset = load_data()
            st.session_state.dataset_label = "Démonstration — données fictives"
            reset_choices(st.session_state)
            st.rerun()
        with st.expander("Télécharger les exemples CSV"):
            st.caption("Utilise ces fichiers comme modèles. Les lignes d'exemple sont fictives.")
            for name in SCHEMAS:
                st.download_button(name, (DEMO_DIR / name).read_bytes(), name, "text/csv", key="template_" + name)
        st.caption("CSV UTF-8, séparateur virgule ou point-virgule. Le README décrit les colonnes attendues.")


def recommendations(data, graph, rooms, label):
    st.subheader("Où déplacer ces ordinateurs ?")
    st.write("Choisis une salle, un modèle et une quantité. La première proposition sera la salle compatible la plus proche par les chemins renseignés.")
    source = st.selectbox("Salle source", rooms, key="choice_source")
    models = sorted(model for (room, model), stock in data.inventory.items() if room == source and stock > 0)
    if not models:
        st.info("Cette salle ne contient aucun ordinateur à déplacer.")
        return
    model = st.selectbox("Modèle à déplacer", models, key="choice_model_" + source)
    stock = data.inventory[source, model]
    quantity = int(st.number_input("Quantité à déplacer", 1, stock, min(5, stock), key=f"choice_qty_{source}_{model}"))
    st.caption(f"Stock disponible pour ce modèle : {stock}. La capacité libre des destinations tient compte de tous les modèles présents.")
    evaluated = evaluate_destinations(data, graph, source, model, quantity)
    candidates = [item for item in evaluated if not item.reasons]
    if candidates:
        best = candidates[0]
        st.success(f"Salle conseillée : {best.room} · {best.route.distance_m:g} m · {best.free_places} place(s) libre(s)")
        st.caption("Classement par distance croissante. En cas d'égalité, les salles sont présentées par ordre alphabétique ; elles sont équivalentes pour ce critère.")
        rows = [{"Rang": index, "Salle": item.room, "Distance (m)": item.route.distance_m,
                 "Distance": item.route.distance_label, "Places libres": item.free_places,
                 "Places après déplacement": item.free_places - quantity}
                for index, item in enumerate(candidates, 1)]
        st.dataframe(rows, hide_index=True, width="stretch")
        selected = st.selectbox("Voir le chemin vers", [item.room for item in candidates], key=f"choice_candidate_{source}_{model}_{quantity}")
        show_route(next(item.route for item in candidates if item.room == selected))
        export = [{**row, "Source": source, "Modèle": model, "Quantité": quantity, "Jeu de données": label} for row in rows]
        st.download_button("Exporter les propositions", csv_bytes(export), "evergreen-destinations.csv", "text/csv")
    else:
        st.info("Aucune destination ne peut recevoir tout le lot avec les données actuelles.")
    rejected = [item for item in evaluated if item.reasons]
    if rejected:
        with st.expander("Pourquoi les autres salles ne sont-elles pas proposées ?"):
            st.dataframe([{"Salle": item.room, "Distance (m)": item.route.distance_m if item.route else None,
                           "Motif": " ; ".join(item.reasons)} for item in rejected], hide_index=True, width="stretch")
    st.caption("Chaque proposition est une alternative. Rien n'est déplacé ou réservé dans l'inventaire.")


def grouping(data, graph, rooms, label):
    st.subheader("Rassembler un modèle dans une salle")
    st.write("Indique le nombre d'ordinateurs à ajouter à la cible. Le plan prend d'abord le stock des salles les plus proches, sans dépasser la capacité de la cible.")
    models = sorted({model for room in data.rooms.values() for model in room.allowed_models})
    model = st.selectbox("Modèle à regrouper", models, key="choice_group_model")
    targets = [room for room in rooms if model in data.rooms[room].allowed_models]
    target = st.selectbox("Salle cible", targets, key="choice_target_" + model)
    quantity = int(st.number_input("Nombre supplémentaire souhaité", min_value=1, value=10, step=1, key="choice_group_qty"))
    plan = prepare_grouping(data, graph, target, model, quantity)
    a, b, c = st.columns(3)
    a.metric("Places libres dans la cible", data.available(target))
    b.metric("Ordinateurs à ajouter", plan.moved)
    c.metric("Demande non satisfaite", plan.remaining)
    accessible_stock = sum(stock for (source, item_model), stock in data.inventory.items()
                           if source != target and item_model == model and shortest_route(graph, source, target) is not None)
    if plan.remaining:
        reasons = []
        if data.available(target) < quantity:
            reasons.append(f"La cible ne dispose que de {data.available(target)} place(s) libre(s).")
        if accessible_stock < quantity:
            reasons.append(f"Les autres salles accessibles ne contiennent que {accessible_stock} ordinateur(s) de ce modèle.")
        st.warning("Plan partiel. " + " ".join(reasons))
    if plan.moves:
        rows = move_rows(plan.moves, label)
        st.dataframe(rows, hide_index=True, width="stretch")
        st.download_button("Exporter ce plan", csv_bytes(rows), "evergreen-regroupement.csv", "text/csv")
        st.caption(f"Effort indicatif : {plan.effort:g} ordinateur·m (quantité × distance). Ce nombre ne représente ni une durée ni une tournée.")
    else:
        st.info("Aucun déplacement possible pour cette demande.")
    st.caption("Le plan est une proposition : il ne modifie pas les stocks et ne tient pas compte d'autres plans préparés auparavant.")


def main():
    st.set_page_config(page_title="Evergreen", page_icon="🌿", layout="wide")
    if "dataset" not in st.session_state:
        try:
            st.session_state.dataset = load_data()
            st.session_state.dataset_label = "Démonstration — données fictives"
        except (ValueError, OSError) as error:
            st.error(f"Impossible d'ouvrir les fichiers de démonstration : {error}")
            st.stop()
    data_sidebar()
    data = st.session_state.dataset
    label = st.session_state.dataset_label
    graph = build_graph(data)
    rooms = sorted(data.rooms)
    st.title("Evergreen")
    st.write("Trouver une salle disponible et préparer les déplacements de matériel.")
    if label.startswith("Démonstration"):
        st.info("Mode démonstration : salles, distances et inventaires fictifs, inspirés des noms de bâtiments de uOttawa. Ce n'est pas un plan du campus ni un outil officiel de l'université.")
    else:
        st.info("Données importées : les résultats dépendent des fichiers fournis. Les distances mesurées sont celles déclarées dans ces fichiers, sans vérification indépendante.")
    a, b, c = st.columns(3)
    a.metric("Salles", len(rooms))
    b.metric("Ordinateurs", sum(data.inventory.values()))
    c.metric("Places libres", sum(data.available(room) for room in rooms))
    recommend, route, group, inventory = st.tabs(["Trouver une salle", "Vérifier un trajet", "Préparer un regroupement", "Consulter les données"])
    with recommend:
        recommendations(data, graph, rooms, label)
    with route:
        st.subheader("Vérifier un trajet")
        source = st.selectbox("Départ", rooms, key="choice_route_source")
        destination = st.selectbox("Arrivée", rooms, index=min(1, len(rooms) - 1), key="choice_route_destination")
        show_route(shortest_route(graph, source, destination))
        st.caption("Distance du plus court chemin dans le réseau, pas une distance à vol d'oiseau. Toutes les liaisons sont utilisables dans les deux sens.")
    with group:
        grouping(data, graph, rooms, label)
    with inventory:
        st.caption(label)
        st.dataframe([{"Salle": room, "Bâtiment": info.building, "Capacité": info.capacity,
                       "Occupé": data.occupied(room), "Libre": data.available(room),
                       "Modèles autorisés": ", ".join(sorted(info.allowed_models))}
                      for room, info in sorted(data.rooms.items())], hide_index=True, width="stretch")
        st.subheader("Inventaire")
        if data.inventory:
            st.dataframe([{"Salle": room, "Modèle": model, "Quantité": quantity}
                          for (room, model), quantity in sorted(data.inventory.items())], hide_index=True, width="stretch")
        else:
            st.info("L'inventaire est vide.")
        st.subheader("Liaisons")
        if data.connections:
            st.dataframe([{"Départ": a, "Arrivée": b, "Distance (m)": distance, "Type": kind}
                          for a, b, distance, kind in data.connections], hide_index=True, width="stretch")
        components = nx.number_connected_components(graph)
        if components > 1:
            st.warning(f"Le réseau comporte {components} groupes non reliés. Aucun trajet n'est possible entre ces groupes.")
        transit = sorted(set(graph) - set(rooms))
        if transit:
            st.caption("Points de passage sans inventaire : " + ", ".join(transit))
            st.caption("Vérifie leur orthographe : un nom de salle mal saisi dans les liaisons sera interprété comme un point de passage.")
        st.caption("simulated : inventée · estimated : approximative · measured : mesurée selon le fichier fourni. Les salles isolées et les inventaires vides sont acceptés.")


if __name__ == "__main__":
    main()
