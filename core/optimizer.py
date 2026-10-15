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


@dataclass(frozen=True)
class Destination:
    room: str
    free_places: int
    route: Route | None
    reasons: tuple[str, ...]


def evaluate_destinations(data, graph, source, model, quantity):
    """Classe toutes les salles ; les exclusions restent explicables."""
    validate_quantity(quantity)
    if source not in data.rooms:
        raise ValueError("Salle source inconnue")
    if data.inventory.get((source, model), 0) < quantity:
        raise ValueError("Stock source insuffisant pour ce modèle")
    results = []
    for destination, room in data.rooms.items():
        if destination == source:
            continue
        route = shortest_route(graph, source, destination)
        free = data.available(destination)
        reasons = []
        if not room.accepts(model):
            reasons.append("Modèle non autorisé")
        if free < quantity:
            reasons.append(
                f"Place insuffisante : {free} libre(s) pour {quantity} demandé(s)"
            )
        if route is None:
            reasons.append("Aucun chemin renseigné")
        results.append(Destination(destination, free, route, tuple(reasons)))
    return sorted(
        results,
        key=lambda item: (
            item.route.ranking_distance if item.route else float("inf"),
            item.room,
        ),
    )


def compatible_destinations(data, graph, source, model, quantity):
    return [
        Move(source, item.room, model, quantity, item.route)
        for item in evaluate_destinations(data, graph, source, model, quantity)
        if not item.reasons
    ]


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
        if any(move.route.distance_m is None for move in self.moves):
            return None
        return sum(move.quantity * move.route.distance_m for move in self.moves)


def prepare_grouping(data, graph, destination, model, quantity):
    """Remplit une cible depuis les sources proches ; aucun inventaire modifié."""
    validate_quantity(quantity)
    if destination not in data.rooms or not data.rooms[destination].accepts(model):
        raise ValueError("Destination incompatible avec ce modèle")
    candidates = []
    for (source, item_model), stock in data.inventory.items():
        if source == destination or item_model != model or stock == 0:
            continue
        route = shortest_route(graph, source, destination)
        if route is not None:
            candidates.append((route.ranking_distance, source, stock, route))
    budget = min(quantity, data.available(destination))
    moves = []
    for _, source, stock, route in sorted(candidates):
        amount = min(stock, budget)
        if amount:
            moves.append(Move(source, destination, model, amount, route))
            budget -= amount
    return Plan(moves, quantity, sum(move.quantity for move in moves))
