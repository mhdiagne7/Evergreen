"""Regrouper les modèles par bâtiment sans créer ni perdre d'ordinateurs."""

from collections import Counter

import networkx as nx

from core.buildings import Transfer, apply_transfers
from core.graph import build_graph
from core.routing import shortest_route


def building_models(data, building):
    return Counter(
        {
            model: sum(
                quantity
                for (room, item_model), quantity in data.inventory.items()
                if item_model == model
                and data.rooms[room].building == building
                and data.rooms[room].room_type == "classroom"
            )
            for model in sorted({model for _, model in data.inventory})
        }
    )


def dominant_models(data, building):
    counts = +building_models(data, building)
    if not counts:
        return []
    maximum = max(counts.values())
    return sorted(model for model, quantity in counts.items() if quantity == maximum)


def suggested_targets(data):
    """Une égalité reste un choix explicite ; aucune cible arbitraire."""
    result = {}
    for building in sorted({room.building for room in data.rooms.values()}):
        leaders = dominant_models(data, building)
        if len(leaders) == 1:
            result[building] = leaders[0]
    return result


def plan_homogeneity(data, targets, stock, protect_newer=True):
    """Stock MRT puis cycles de redistribution des seuls modèles minoritaires.

    Les objectifs sont fixés depuis l'inventaire initial. Chaque opération peut
    déplacer une unité : les salles multipostes sont prises en compte. Un cycle
    est indivisible à la confirmation, avec une place de transit à Morisset.
    """
    if not targets:
        raise ValueError("Choisir au moins un bâtiment et son modèle cible.")
    if (
        stock not in data.rooms
        or data.rooms[stock].building != "MRT"
        or data.rooms[stock].room_type != "storage"
    ):
        raise ValueError("Le stock et le transit doivent se trouver à Morisset (MRT).")
    rooms = {
        room: info
        for room, info in data.rooms.items()
        if info.room_type == "classroom" and info.building in targets
    }
    if set(targets) - {info.building for info in rooms.values()}:
        raise ValueError("Un bâtiment choisi ne contient aucune salle recensée.")
    if any(not model or model == "*" for model in targets.values()):
        raise ValueError("Choisir un modèle cible valide.")
    if any(info.capacity is None for info in rooms.values()):
        raise ValueError("Renseigner le nombre de postes attendu dans chaque salle.")

    graph = build_graph(data)
    cache = {}

    def route(source, destination):
        key = source, destination
        if key not in cache:
            cache[key] = shortest_route(graph, source, destination)
        return cache[key]

    def allowed(old, new):
        return not (
            protect_newer
            and old in data.model_years
            and new in data.model_years
            and data.model_years[new] < data.model_years[old]
        )

    desired = {room: targets[info.building] for room, info in rooms.items()}
    work = data
    groups = []

    def add_group(transfers, affected, old_label, new_label, source):
        nonlocal work
        if any(route(move.source, move.destination) is None for move in transfers):
            return False
        try:
            updated = apply_transfers(work, transfers)
        except ValueError:
            return False
        delivery = route(source, affected[0]) if len(affected) == 1 else None
        groups.append(
            {
                "room": " ↔ ".join(affected),
                "rooms": affected,
                "old_model": old_label,
                "new_model": new_label,
                "source": source,
                "delivery_m": delivery.distance_m if delivery else None,
                "distance_type": delivery.distance_label
                if delivery
                else "Selon les étapes du lot",
                "stock_kind": "regrouped",
                "transfers": [vars(move) for move in transfers],
            }
        )
        work = updated
        return True

    # Une opération augmente d'au moins un le nombre de postes conformes.
    limit = sum(info.capacity for info in rooms.values())
    for _ in range(limit):
        candidates = []
        for room, info in sorted(rooms.items()):
            model = desired[room]
            if (
                not info.accepts(model)
                or work.inventory.get((room, model), 0) >= info.capacity
            ):
                continue
            if work.inventory.get((stock, model), 0) <= 0:
                continue
            old_models = sorted(
                old
                for (location, old), quantity in work.inventory.items()
                if location == room
                and old != model
                and quantity > 0
                and allowed(old, model)
            )
            if not old_models and work.occupied(room) >= info.capacity:
                continue

            def recovery_priority(old):
                demand = sum(
                    max(0, rooms[other].capacity - work.inventory.get((other, old), 0))
                    for other in rooms
                    if desired[other] == old
                )
                available = work.inventory.get((stock, old), 0)
                return (-max(0, demand - available), old)

            old = min(old_models, key=recovery_priority) if old_models else None
            transfers = ([Transfer(room, stock, old)] if old else []) + [
                Transfer(stock, room, model, stock_kind="regrouped")
            ]
            paths = [route(move.source, move.destination) for move in transfers]
            if any(path is None for path in paths):
                continue
            try:
                apply_transfers(work, transfers)
            except ValueError:
                continue
            distance = sum(path.ranking_distance for path in paths)
            candidates.append((distance, room, old or "Aucun", model, transfers))
        if candidates:
            _, room, old, model, transfers = min(candidates, key=lambda item: item[:4])
            add_group(transfers, [room], old, model, stock)
            continue

        # Si Morisset ne possède pas le modèle demandé, rechercher un cycle
        # entre postes minoritaires. Aucun modèle déjà conforme n'est prélevé.
        dependencies = nx.DiGraph()
        for target, info in sorted(rooms.items()):
            wanted = desired[target]
            if (
                not info.accepts(wanted)
                or work.inventory.get((target, wanted), 0) >= info.capacity
            ):
                continue
            for donor in sorted(rooms):
                if donor == target or desired[donor] == wanted:
                    continue
                if (
                    work.inventory.get((donor, wanted), 0) > 0
                    and route(donor, target) is not None
                ):
                    dependencies.add_edge(target, donor)
        found = False
        while True:
            try:
                reciprocal = [
                    (
                        route(first, second).ranking_distance
                        + route(second, first).ranking_distance,
                        first,
                        second,
                    )
                    for first, second in dependencies.edges
                    if first < second and dependencies.has_edge(second, first)
                ]
                if reciprocal:
                    _, first, second = min(reciprocal)
                    edges = [(first, second), (second, first)]
                else:
                    edges = nx.find_cycle(dependencies)
            except nx.NetworkXNoCycle:
                break
            cycle = [source for source, _ in edges]
            removed = {
                cycle[index]: desired[cycle[index - 1]] for index in range(len(cycle))
            }
            blocked = [
                room for room in cycle if not allowed(removed[room], desired[room])
            ]
            if blocked:
                room = blocked[0]
                dependencies.remove_edge(
                    room, cycle[(cycle.index(room) + 1) % len(cycle)]
                )
                continue
            first = cycle[0]
            transfers = [Transfer(first, stock, removed[first])]
            for index in range(len(cycle) - 1):
                target, donor = cycle[index], cycle[index + 1]
                transfers.append(Transfer(donor, target, desired[target]))
            transfers.append(
                Transfer(stock, cycle[-1], desired[cycle[-1]], stock_kind="regrouped")
            )
            if add_group(
                transfers,
                cycle,
                " ; ".join(f"{room} : {removed[room]}" for room in cycle),
                " ; ".join(f"{room} : {desired[room]}" for room in cycle),
                stock,
            ):
                found = True
                break
            dependencies.remove_edge(*edges[0])
        if not found:
            break

    summary = []
    for building, model in sorted(targets.items()):
        locations = [room for room, info in rooms.items() if info.building == building]
        target = sum(rooms[room].capacity for room in locations)
        before = sum(data.inventory.get((room, model), 0) for room in locations)
        after = sum(work.inventory.get((room, model), 0) for room in locations)
        summary.append(
            {
                "Bâtiment": building,
                "Modèle cible": model,
                "Postes attendus": target,
                "Conformes avant": before,
                "Conformes après": after,
                "Manque": target - after,
            }
        )
    return {
        "mode": "homogenization",
        "building": "Campus",
        "buffer": stock,
        "targets": dict(targets),
        "protect_newer": protect_newer,
        "groups": groups,
        "summary": summary,
    }
