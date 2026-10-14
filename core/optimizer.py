"""Recherche de destinations et proposition gloutonne de regroupement."""
from dataclasses import dataclass
from core.routing import Route, shortest_route


@dataclass(frozen=True)
class Move:
    source: str
    destination: str
    model: str
    quantity: int
    route: Route


def validate_quantity(quantity):
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("La quantité doit être un entier strictement positif")


def compatible_destinations(data, graph, source, model, quantity):
    validate_quantity(quantity)
    if source not in data.rooms:
        raise ValueError("Salle source inconnue")
    if data.inventory.get((source, model), 0) < quantity:
        raise ValueError("Stock source insuffisant pour ce modèle")
    results = []
    for destination, room in data.rooms.items():
        if destination == source or model not in room.allowed_models or data.available(destination) < quantity:
            continue
        route = shortest_route(graph, source, destination)
        if route is not None:
            results.append(Move(source, destination, model, quantity, route))
    return sorted(results, key=lambda move: (move.route.distance_m, move.destination))


@dataclass(frozen=True)
class Plan:
    moves: list[Move]
    requested: int
    moved: int

    @property
    def remaining(self):
        return self.requested - self.moved

    @property
    def effort(self):
        return sum(move.quantity * move.route.distance_m for move in self.moves)


def prepare_grouping(data, graph, destination, model, quantity):
    """Remplit une cible depuis les sources proches ; aucun inventaire modifié."""
    validate_quantity(quantity)
    if destination not in data.rooms or model not in data.rooms[destination].allowed_models:
        raise ValueError("Destination incompatible avec ce modèle")
    candidates = []
    for (source, item_model), stock in data.inventory.items():
        if source == destination or item_model != model or stock == 0:
            continue
        route = shortest_route(graph, source, destination)
        if route is not None:
            candidates.append((route.distance_m, source, stock, route))
    budget = min(quantity, data.available(destination))
    moves = []
    for _, source, stock, route in sorted(candidates):
        amount = min(stock, budget)
        if amount:
            moves.append(Move(source, destination, model, amount, route))
            budget -= amount
    return Plan(moves, quantity, sum(move.quantity for move in moves))
