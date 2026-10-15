"""Préparer des remplacements par bâtiment, puis les détailler salle par salle."""

from dataclasses import dataclass, replace

from core.graph import build_graph
from core.routing import shortest_route


@dataclass(frozen=True)
class Transfer:
    source: str
    destination: str
    model: str
    quantity: int = 1


def apply_transfers(data, transfers):
    """Vérifie chaque étape, y compris la capacité du lieu de transit."""
    updated = replace(data, inventory=data.inventory.copy())
    for move in transfers:
        if (
            isinstance(move.quantity, bool)
            or not isinstance(move.quantity, int)
            or move.quantity <= 0
        ):
            raise ValueError("Une quantité déplacée doit être un entier positif.")
        if (
            move.source == move.destination
            or move.source not in updated.rooms
            or move.destination not in updated.rooms
        ):
            raise ValueError("Source ou destination invalide.")
        if not updated.rooms[move.destination].accepts(move.model):
            raise ValueError(
                f"{move.destination} n'autorise pas le modèle {move.model}."
            )
        if updated.inventory.get((move.source, move.model), 0) < move.quantity:
            raise ValueError(f"Stock insuffisant dans {move.source} pour {move.model}.")
        if updated.available(move.destination) < move.quantity:
            raise ValueError(f"Place insuffisante dans {move.destination}.")
        updated.inventory[move.source, move.model] -= move.quantity
        key = move.destination, move.model
        updated.inventory[key] = updated.inventory.get(key, 0) + move.quantity
    return updated


def building_summary(data, models):
    rows = []
    for building in sorted({room.building for room in data.rooms.values()}):
        classes = [
            r
            for r, info in data.rooms.items()
            if info.building == building and info.room_type == "classroom"
        ]
        storage = [
            r
            for r, info in data.rooms.items()
            if info.building == building and info.room_type == "storage"
        ]
        rows.append(
            {
                "Bâtiment": building,
                "Salles de classe": len(classes),
                "Postes installés": sum(data.occupied(r) for r in classes),
                "En réserve": sum(data.occupied(r) for r in storage),
                "Total": sum(data.occupied(r) for r in classes + storage),
            }
        )
    details = []
    for building in sorted({room.building for room in data.rooms.values()}):
        for model in sorted(models):
            installed = sum(
                q
                for (r, m), q in data.inventory.items()
                if m == model
                and data.rooms[r].building == building
                and data.rooms[r].room_type == "classroom"
            )
            stock = sum(
                q
                for (r, m), q in data.inventory.items()
                if m == model
                and data.rooms[r].building == building
                and data.rooms[r].room_type == "storage"
            )
            details.append(
                {
                    "Bâtiment": building,
                    "Modèle": model,
                    "Installés": installed,
                    "Disponibles en réserve": stock,
                    "Total": installed + stock,
                }
            )
    return rows, details


def plan_building(data, building, goals, buffer, allow_swaps=False):
    """Objectifs = nombre total de classes à un poste par modèle, après le lot.

    Heuristique déterministe : modèles par nom, meilleure livraison disponible
    par distance. Préserve les classes déjà conformes à leur quota. Un échange
    de postes installés utilise une place de transit explicitement choisie.
    """
    if not goals or any(
        isinstance(q, bool) or not isinstance(q, int) or q <= 0 for q in goals.values()
    ):
        raise ValueError("Indiquer au moins un objectif entier positif.")
    if buffer not in data.rooms or data.rooms[buffer].room_type != "storage":
        raise ValueError(
            "Choisir un stock de retour existant, par exemple le stock central MRT."
        )
    classes = sorted(
        r
        for r, info in data.rooms.items()
        if info.building == building
        and info.room_type == "classroom"
        and info.capacity == 1
    )
    if not classes:
        raise ValueError("Aucune salle de classe à un poste dans ce bâtiment.")
    if sum(goals.values()) > len(classes):
        raise ValueError(
            f"Les objectifs dépassent les {len(classes)} classes à un poste du bâtiment."
        )
    graph = build_graph(data)
    route_cache = {}

    def route(a, b):
        if (a, b) not in route_cache:
            route_cache[a, b] = shortest_route(graph, a, b)
        return route_cache[a, b]

    work = replace(data, inventory=data.inventory.copy())
    assigned = set()
    for model, count in sorted(goals.items()):
        matches = [r for r in classes if work.inventory.get((r, model), 0) == 1]
        assigned.update(matches[:count])
    groups = []
    for model, goal in sorted(goals.items()):
        current = sum(work.inventory.get((r, model), 0) for r in assigned)
        for _ in range(max(0, goal - current)):
            candidates = []
            for destination in classes:
                if destination in assigned or not work.rooms[destination].accepts(
                    model
                ):
                    continue
                old = next(
                    (
                        m
                        for (r, m), q in work.inventory.items()
                        if r == destination and q
                    ),
                    None,
                )
                for (source, item_model), stock in sorted(work.inventory.items()):
                    if item_model != model or stock <= 0 or source == destination:
                        continue
                    source_info = work.rooms[source]
                    is_swap = source_info.room_type == "classroom"
                    if is_swap and (
                        not allow_swaps
                        or source_info.building == building
                        or source_info.capacity != 1
                        or old is None
                    ):
                        continue
                    delivery = route(source, destination)
                    if delivery is None:
                        continue
                    transfers = []
                    if old:
                        transfers.append(Transfer(destination, buffer, old))
                    transfers.append(Transfer(source, destination, model))
                    if is_swap:
                        transfers.append(Transfer(buffer, source, old))
                    if any(route(t.source, t.destination) is None for t in transfers):
                        continue
                    try:
                        after = apply_transfers(work, transfers)
                    except ValueError:
                        continue
                    # Réserves d'abord ; distance ensuite ; noms pour départager.
                    transport_distance = sum(
                        route(move.source, move.destination).ranking_distance
                        for move in transfers
                    )
                    candidates.append(
                        (
                            is_swap,
                            transport_distance,
                            source,
                            destination,
                            old,
                            transfers,
                            after,
                        )
                    )
            if not candidates:
                break
            _, _, source, destination, old, transfers, work = min(
                candidates, key=lambda c: c[:4]
            )
            assigned.add(destination)
            groups.append(
                {
                    "room": destination,
                    "old_model": old or "Aucun",
                    "new_model": model,
                    "source": source,
                    "delivery_m": route(source, destination).distance_m,
                    "distance_type": route(source, destination).distance_label,
                    "transfers": [vars(t) for t in transfers],
                }
            )
    result = []
    for model, goal in sorted(goals.items()):
        before = sum(data.inventory.get((r, model), 0) for r in classes)
        after = sum(work.inventory.get((r, model), 0) for r in classes)
        result.append(
            {
                "Modèle": model,
                "Avant": before,
                "Objectif": goal,
                "Après le lot": after,
                "Manque": max(0, goal - after),
            }
        )
    return {
        "building": building,
        "goals": goals,
        "buffer": buffer,
        "groups": groups,
        "summary": result,
        "allow_swaps": allow_swaps,
    }
