"""Graphe non orienté : toutes les connexions sont bidirectionnelles."""

import networkx as nx


def build_graph(data):
    graph = nx.Graph()
    graph.add_nodes_from(
        (room, {"building": info.building}) for room, info in data.rooms.items()
    )
    graph.graph["distance_mode"] = data.distance_mode
    graph.graph["building_routes"] = data.building_routes
    for source, target, distance, kind in data.connections:
        graph.add_edge(source, target, distance_m=distance, distance_type=kind)
    return graph
