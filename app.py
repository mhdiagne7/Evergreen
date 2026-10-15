"""Evergreen : préparer, réaliser puis enregistrer les déplacements par bâtiment."""
import os
from pathlib import Path
import streamlit as st
from core.data import DEMO_DIR, SCHEMAS, load_data, load_csv_files
from core.buildings import building_summary, plan_building
from core.export import csv_bytes
from core.graph import build_graph
from core.routing import shortest_route
from core.store import Store, DEFAULT_DB
from room_views import recommendations, show_route

CAMPUS_DEMO = DEMO_DIR / "campus"


def table(rows):
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")


def refresh(message):
    st.session_state.notice = message
    st.rerun()


def operation_rows(plan):
    return [{"Salle à équiper": g["room"], "Modèle actuel": g["old_model"],
             "Modèle à installer": g["new_model"], "Provenance": g["source"],
             "Livraison (m)": g["delivery_m"], "Distance": g["distance_type"],
             "État": "Fait" if g.get("completed") else "À faire"} for g in plan["groups"]]


def transfer_rows(plan, data):
    graph = build_graph(data)
    rows = []
    for group in plan["groups"]:
        for index, move in enumerate(group["transfers"], 1):
            route = shortest_route(graph, move["source"], move["destination"])
            rows.append({"Salle concernée": group["room"], "Étape": index,
                         "Bâtiment source": data.rooms[move["source"]].building,
                         "Source": move["source"], "Bâtiment destination": data.rooms[move["destination"]].building,
                         "Destination": move["destination"], "Modèle": move["model"], "Quantité": move["quantity"],
                         "Distance (m)": route.distance_m, "Type de distance": route.distance_label,
                         "Chemin": " → ".join(route.nodes)})
    return rows


def transport_summary(plan, data):
    totals = {}
    for group in plan["groups"]:
        for move in group["transfers"]:
            origin = data.rooms[move["source"]].building
            destination = data.rooms[move["destination"]].building
            if origin != destination:
                key = (origin, destination, move["model"])
                totals[key] = totals.get(key, 0) + move["quantity"]
    return [{"Depuis": a, "Vers": b, "Modèle": model, "Ordinateurs à transporter": q}
            for (a, b, model), q in sorted(totals.items())]


def sidebar(store):
    with st.sidebar:
        st.header("Espace de travail")
        workspaces = store.list_workspaces()
        ids = [w["id"] for w in workspaces]
        names = {w["id"]: w["name"] for w in workspaces}
        if "workspace" not in st.session_state:
            st.session_state.workspace = ids[-1]
        identifier = st.selectbox("Inventaire actif", ids, format_func=lambda key: names[key], key="workspace")
        st.caption("Les stocks et les lots sont enregistrés sur cet ordinateur, même après fermeture de l'application.")
        with st.expander("Créer un inventaire depuis des CSV"):
            st.write("Les salles et les liaisons deviennent le référentiel fixe de ce nouvel espace. L'inventaire CSV sert de point de départ. Les espaces existants sont conservés.")
            name = st.text_input("Nom du nouvel inventaire", key="import_name")
            uploads = {name: st.file_uploader(name, type="csv", key="import_" + name) for name in SCHEMAS}
            if st.button("Créer cet espace", key="import_apply"):
                try:
                    payload = {name: file.getvalue() for name, file in uploads.items() if file is not None}
                    data = load_csv_files(payload)
                    store.create_workspace(name, data)
                    refresh("Inventaire créé. Choisis-le dans la liste des espaces de travail.")
                except ValueError as error:
                    st.error(str(error))
            st.caption("Dans rooms.csv : room_type = classroom ou storage ; capacity = 1 pour une classe à un poste. allowed_models = * accepte les nouveaux modèles du catalogue.")
        with st.expander("Modèles CSV fictifs"):
            for name in SCHEMAS:
                st.download_button(name, (CAMPUS_DEMO / name).read_bytes(), name, "text/csv", key="example_" + name)
        st.caption("Base locale : Documents/Evergreen/private/evergreen.sqlite3. Aucun envoi automatique vers GitHub.")
    return identifier


def overview(data, models):
    summary, breakdown = building_summary(data, models)
    st.subheader("Vue d'ensemble des bâtiments")
    table(summary)
    st.subheader("Répartition par modèle")
    table(breakdown)
    st.download_button("Exporter la synthèse par bâtiment", csv_bytes(breakdown), "evergreen-batiments.csv", "text/csv")
    building = st.selectbox("Voir les salles du bâtiment", sorted({r.building for r in data.rooms.values()}), key="overview_building")
    details = []
    for room, info in sorted(data.rooms.items()):
        if info.building == building:
            stock = ", ".join(f"{m} × {q}" for (r, m), q in sorted(data.inventory.items()) if r == room and q) or "Aucun ordinateur"
            details.append({"Salle": room, "Usage": "Réserve" if info.room_type == "storage" else "Classe",
                            "Inventaire actuel": stock, "Capacité": info.capacity, "Places libres": data.available(room)})
    table(details)


def planning(store, identifier, data, models, revision):
    st.subheader("Préparer un lot Evergreen pour un bâtiment")
    st.write("L'objectif est le nombre total de classes à équiper avec chaque modèle après les déplacements. Les classes déjà équipées comptent dans cet objectif.")
    buildings = sorted({r.building for r in data.rooms.values()})
    building = st.selectbox("Bâtiment à équiper", buildings, key="plan_building")
    classes = [r for r, info in data.rooms.items() if info.building == building and info.room_type == "classroom" and info.capacity == 1]
    reserves = sorted(r for r, info in data.rooms.items() if info.building == building and info.room_type == "storage")
    st.caption(f"{len(classes)} classes à un poste dans ce bâtiment. Les salles de capacité différente restent visibles dans l'inventaire mais ne sont pas remplacées automatiquement.")
    if not reserves or not classes or not models:
        st.info("Il faut des classes à un poste, au moins un modèle au catalogue et une réserve de retour dans le bâtiment. Décris ces lieux dans les CSV de référence.")
        return
    chosen = st.multiselect("Modèles souhaités dans ce bâtiment", models, default=models[:1], key="plan_models")
    goals = {model: int(st.number_input(f"Nombre total de classes en {model}", min_value=1, max_value=len(classes), value=min(10, len(classes)), key=f"goal_{building}_{model}")) for model in chosen}
    buffer = st.selectbox("Réserve pour les anciens postes et le transit", reserves, key="plan_buffer")
    swaps = st.checkbox("Autoriser les échanges avec des classes d'autres bâtiments", key="plan_swaps")
    st.caption("Priorité au stock en réserve, puis aux plus courtes livraisons. En échange entre classes, l'ancien poste est remis dans la classe source : elle ne reste pas vide. Une place libre de transit est nécessaire pour retirer l'ancien poste avant d'installer le nouveau.")
    signature = (identifier, revision, building, tuple(sorted(goals.items())), buffer, swaps)
    if st.button("Calculer les propositions", key="calculate"):
        try:
            st.session_state.preview = (signature, plan_building(data, building, goals, buffer, swaps))
        except ValueError as error:
            st.session_state.pop("preview", None)
            st.error(str(error))
    preview = st.session_state.get("preview")
    if preview and preview[0] == signature:
        plan = preview[1]
        table(plan["summary"])
        if any(row["Manque"] for row in plan["summary"]):
            st.warning("Objectif partiellement réalisable. Les propositions respectent le stock, les modèles autorisés, les chemins et la capacité de retour. Essaie un objectif plus petit, un arrivage ou les échanges entre classes. Un modèle ajouté au catalogue n'ajoute aucun ordinateur au stock.")
        if not plan["groups"]:
            st.info("Aucun changement proposé : objectif déjà atteint ou aucun remplacement réalisable avec ces contraintes.")
            return
        st.write("**Transport entre bâtiments**")
        transports = transport_summary(plan, data)
        table(transports)
        if not transports:
            st.caption("Ce lot ne comporte que des déplacements à l’intérieur du bâtiment.")
        st.write("**Interventions dans les salles**")
        table(operation_rows(plan))
        with st.expander("Feuille de route : retraits, livraisons et retours"):
            table(transfer_rows(plan, data))
        name = st.text_input("Nom du lot", value=f"Evergreen {building}", key="batch_name")
        st.download_button("Exporter la feuille de route", csv_bytes(transfer_rows(plan, data)), "evergreen-feuille-de-route.csv", "text/csv")
        if st.button("Enregistrer ce lot à réaliser", key="save_batch"):
            try:
                store.save_batch(identifier, revision, name, plan)
                st.session_state.pop("preview", None)
                refresh("Lot enregistré. L'inventaire reste inchangé jusqu'à confirmation dans « Lots et historique ».")
            except ValueError as error:
                st.error(str(error))
    elif preview:
        st.info("Les paramètres ou l'inventaire ont changé. Recalcule les propositions avant d'enregistrer un lot.")


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
            st.download_button("Télécharger la feuille de route", csv_bytes(transfer_rows(plan, data)), f"lot-{batch['id'][:8]}.csv", "text/csv", key="download_" + batch["id"])
            if batch["status"] in {"Préparé", "Partiel"}:
                if batch["revision"] != revision:
                    st.warning("Ce lot a été préparé sur un inventaire plus ancien. Il faut le recalculer pour éviter d'utiliser un stock déjà déplacé.")
                else:
                    remaining = [i for i, g in enumerate(plan["groups"]) if not g.get("completed")]
                    with st.form("confirm_" + batch["id"]):
                        selected = st.multiselect("Salles dont le remplacement est entièrement terminé", remaining,
                                                  format_func=lambda i: plan["groups"][i]["room"], key="complete_" + batch["id"])
                        st.caption("Pour chaque salle cochée, le retrait, l'installation et le retour doivent tous être réalisés. Respecter l'ordre de la feuille de route ; certains stocks proviennent d'une étape précédente.")
                        note = st.text_input("Note de réalisation (intervenant, date ou référence)", key="note_" + batch["id"])
                        confirmed = st.checkbox("Je confirme que ces déplacements ont réellement été effectués", key="done_" + batch["id"])
                        submit = st.form_submit_button("Mettre à jour l'inventaire")
                    if submit:
                        if not confirmed:
                            st.error("Confirme la réalisation physique avant de modifier l'inventaire.")
                        else:
                            try:
                                store.confirm_batch(identifier, batch["id"], selected, note)
                                refresh("Déplacements enregistrés. L'inventaire et les totaux par bâtiment sont à jour.")
                            except ValueError as error:
                                st.error(str(error))
                if st.button("Annuler le reste de ce lot", key="cancel_" + batch["id"]):
                    store.cancel_batch(identifier, batch["id"])
                    refresh("Lot annulé. Les déplacements déjà confirmés sont conservés.")
    st.subheader("Historique des mises à jour")
    history = store.history(identifier)
    table([{"Date (UTC)": e["created"], "Action": e["kind"], "Note": e["note"]} for e in history])
    if history:
        st.download_button("Exporter l'historique détaillé", csv_bytes(history), "evergreen-historique.csv", "text/csv")


def stock_view(store, identifier, data, models, revision):
    st.subheader("Catalogue et arrivages")
    st.write("Ajouter un modèle le rend sélectionnable. Pour augmenter le stock, enregistre ensuite un arrivage dans une réserve.")
    with st.form("new_model"):
        model = st.text_input("Nouveau modèle")
        submit = st.form_submit_button("Ajouter au catalogue")
    if submit:
        try:
            store.add_model(identifier, model)
            refresh("Modèle ajouté au catalogue, sans changement de quantité.")
        except ValueError as error:
            st.error(str(error))
    reserves = sorted(r for r, info in data.rooms.items() if info.room_type == "storage")
    if reserves and models:
        with st.form("receipt"):
            room = st.selectbox("Réserve de réception", reserves)
            model = st.selectbox("Modèle reçu", models)
            quantity = int(st.number_input("Quantité reçue", min_value=1, value=1, step=1))
            note = st.text_input("Provenance ou motif de l'entrée")
            confirm = st.checkbox("Ces ordinateurs ont bien été reçus")
            submit = st.form_submit_button("Enregistrer l'arrivage")
        if submit:
            if not confirm:
                st.error("Confirme la réception avant d'ajouter le stock.")
            else:
                try:
                    store.receive(identifier, room, model, quantity, revision, note)
                    refresh("Arrivage enregistré dans l'inventaire.")
                except ValueError as error:
                    st.error(str(error))
    else:
        st.info("Ajoute un modèle et définis une réserve dans le référentiel pour enregistrer un arrivage.")
    current = [{"room_id": room, "model": model, "quantity": q} for (room, model), q in sorted(data.inventory.items()) if q]
    st.download_button("Exporter l'inventaire actuel", csv_bytes(current) if current else b"room_id,model,quantity\n", "inventory.csv", "text/csv")
    st.caption("Les CSV de référence ne sont jamais écrasés. L'état courant et l'historique sont enregistrés dans la base locale.")
    if st.button("Préparer une sauvegarde complète", key="prepare_backup"):
        st.session_state.backup_bytes = store.backup()
    if "backup_bytes" in st.session_state:
        st.download_button("Télécharger la sauvegarde locale", st.session_state.backup_bytes, "evergreen-sauvegarde.sqlite3", "application/octet-stream")
        st.caption("Cette sauvegarde contient tous les espaces et leur historique au moment de sa préparation. Conserve-la dans un emplacement autorisé.")


def main():
    st.set_page_config(page_title="Evergreen", page_icon="🌿", layout="wide")
    store = Store(Path(os.environ.get("EVERGREEN_DB", str(DEFAULT_DB))))
    store.ensure_demo(load_data(CAMPUS_DEMO))
    identifier = sidebar(store)
    data, models, revision, label = store.load(identifier)
    if st.session_state.get("active_context") != (identifier, revision):
        for key in list(st.session_state):
            if key.startswith(("choice_", "goal_", "plan_", "overview_")):
                del st.session_state[key]
        st.session_state.active_context = (identifier, revision)
    st.title("Evergreen · Bâtiments et inventaire")
    st.caption(label + f" · Version de l'inventaire : {revision}")
    if identifier == "demo":
        st.info("Démonstration entièrement fictive : CBY compte 25 classes à un poste. Les noms, salles, stocks et distances ne représentent pas les données réelles de l'université.")
    else:
        st.info("Inventaire importé. Les distances et les informations proviennent de tes fichiers ; elles ne sont pas vérifiées indépendamment.")
    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))
    pages = st.tabs(["Vue par bâtiment", "Planifier Evergreen", "Lots et historique", "Stock et modèles", "Salles et trajets"])
    with pages[0]:
        overview(data, models)
    with pages[1]:
        planning(store, identifier, data, models, revision)
    with pages[2]:
        batches_view(store, identifier, data, revision)
    with pages[3]:
        stock_view(store, identifier, data, models, revision)
    with pages[4]:
        graph = build_graph(data)
        rooms = sorted(data.rooms)
        recommendations(data, graph, rooms, label)
        st.divider()
        source = st.selectbox("Départ du trajet", rooms, key="choice_route_source")
        destination = st.selectbox("Arrivée du trajet", rooms, index=min(1, len(rooms) - 1), key="choice_route_destination")
        show_route(shortest_route(graph, source, destination))


if __name__ == "__main__":
    main()
