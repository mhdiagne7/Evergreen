"""Graphe non orienté : toutes les connexions sont bidirectionnelles."""
import networkx as nx


def build_graph(data):
    graph = nx.Graph()
    graph.add_nodes_from(data.rooms)
    for source, target, distance, kind in data.connections:
        graph.add_edge(source, target, distance_m=distance, distance_type=kind)
    return graph
