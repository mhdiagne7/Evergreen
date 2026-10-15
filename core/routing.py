"""Plus court chemin pondéré par la distance, avec Dijkstra."""

from dataclasses import dataclass

import networkx as nx

from core.campus import building_distance


@dataclass(frozen=True)
class Route:
    nodes: list[str]
    distance_m: float | None
    distance_label: str

    @property
    def ranking_distance(self):
        """Même bâtiment prioritaire ; les mètres intérieurs restent inconnus."""
        return self.distance_m if self.distance_m is not None else 0


def shortest_route(graph, source, destination):
    if source not in graph or destination not in graph:
        raise ValueError("Point de départ ou d'arrivée inconnu")
    if graph.graph.get("distance_mode") == "geodesic":
        if source == destination:
            return Route([source], 0, "nulle (aucun déplacement)")
        origin = graph.nodes[source]["building"]
        target = graph.nodes[destination]["building"]
        if origin == target:
            return Route([source, destination], None, "intra-bâtiment non évaluée")
        walking = graph.graph.get("walking_routes", {}).get((origin, target))
        if walking:
            return Route(
                [source, destination],
                walking["distance_m"],
                "de marche renseignée manuellement",
            )
        distance = building_distance(origin, target)
        if distance is None:
            return None
        return Route(
            [source, destination],
            distance,
            "à vol d’oiseau entre bâtiments (trajet non mesuré)",
        )
    try:
        distance, nodes = nx.single_source_dijkstra(
            graph, source, destination, weight="distance_m"
        )
    except nx.NetworkXNoPath:
        return None
    kinds = {graph[a][b]["distance_type"] for a, b in zip(nodes, nodes[1:])}
    labels = {
        "simulated": "simulée",
        "estimated": "estimée",
        "measured": "mesurée (déclarée)",
    }
    if not kinds:
        label = "nulle (aucun déplacement)"
    elif len(kinds) == 1:
        label = labels[next(iter(kinds))]
    else:
        label = "mixte (" + " / ".join(labels[kind] for kind in sorted(kinds)) + ")"
    return Route(nodes, distance, label)
