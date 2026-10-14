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
    label = "simulée" if not kinds or kinds == {"simulated"} else "estimée" if kinds == {"estimated"} else "mixte (simulée / estimée)"
    return Route(nodes, distance, label)
