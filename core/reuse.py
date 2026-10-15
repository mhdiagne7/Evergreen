"""Réaffecter les retours Morisset vers des salles équipées de modèles plus anciens."""

from core.buildings import Transfer, apply_transfers
from core.graph import build_graph
from core.routing import shortest_route


def add_reuse_operations(data, plan):
    """Compléter un plan sans prélever de poste installé ni modifier ses objectifs.

    Les années sont déclarées par l'utilisateur. Une année manquante ne permet
    aucun classement automatique. Le bâtiment cible initial reste inchangé.
    """
    work = data
    for group in plan["groups"]:
        work = apply_transfers(work, [Transfer(**move) for move in group["transfers"]])
    graph = build_graph(data)
    stock = plan["buffer"]
    if work.rooms[stock].building != "MRT":
        raise ValueError("Les postes retirés doivent revenir à Morisset (MRT).")
    result = {**plan, "groups": list(plan["groups"]), "reuse_count": 0}
    visited = set()
    while True:
        candidates = []
        for (source, model), quantity in sorted(work.returned_stock.items()):
            if source != stock or quantity <= 0 or model not in work.model_years:
                continue
            for room, info in sorted(work.rooms.items()):
                if (
                    info.room_type != "classroom"
                    or info.capacity != 1
                    or info.building == plan["building"]
                    or room in visited
                    or not info.accepts(model)
                ):
                    continue
                installed = [
                    old
                    for (location, old), count in work.inventory.items()
                    if location == room and count > 0
                ]
                if len(installed) != 1:
                    continue
                old = installed[0]
                if (
                    old not in work.model_years
                    or work.model_years[model] <= work.model_years[old]
                ):
                    continue
                outbound = shortest_route(graph, stock, room)
                inbound = shortest_route(graph, room, stock)
                if outbound is None or inbound is None:
                    continue
                transfers = [
                    Transfer(room, stock, old),
                    Transfer(stock, room, model, stock_kind="returned"),
                ]
                try:
                    after = apply_transfers(work, transfers)
                except ValueError:
                    continue
                distance = outbound.ranking_distance + inbound.ranking_distance
                improvement = work.model_years[model] - work.model_years[old]
                candidates.append(
                    (
                        improvement,
                        distance,
                        room,
                        model,
                        old,
                        transfers,
                        after,
                        outbound,
                    )
                )
        if not candidates:
            break
        _, _, room, model, old, transfers, work, outbound = min(
            candidates, key=lambda candidate: candidate[:4]
        )
        visited.add(room)
        result["groups"].append(
            {
                "room": room,
                "old_model": old,
                "new_model": model,
                "source": stock,
                "delivery_m": outbound.distance_m,
                "distance_type": outbound.distance_label,
                "stock_kind": "returned",
                "reuse": True,
                "transfers": [vars(move) for move in transfers],
            }
        )
        result["reuse_count"] += 1
    return result
