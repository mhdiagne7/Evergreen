"""Plus court chemin pondéré par la distance, avec Dijkstra."""
from dataclasses import dataclass
import networkx as nx


@dataclass(frozen=True)
class Route:
    nodes: list[str]
    distance_m: float
    distance_label: str


def shortest_route(graph, source, destination):
    if source not in graph or destination not in graph:
        raise ValueError("Point de départ ou d'arrivée inconnu")
    try:
        distance, nodes = nx.single_source_dijkstra(graph, source, destination, weight="distance_m")
    except nx.NetworkXNoPath:
        return None
    kinds = {graph[a][b]["distance_type"] for a, b in zip(nodes, nodes[1:])}
    labels = {"simulated": "simulée", "estimated": "estimée", "measured": "mesurée (déclarée)"}
    if not kinds:
        label = "nulle (aucun déplacement)"
    elif len(kinds) == 1:
        label = labels[next(iter(kinds))]
    else:
        label = "mixte (" + " / ".join(labels[kind] for kind in sorted(kinds)) + ")"
    return Route(nodes, distance, label)
