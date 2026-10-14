"""Lecture et validation stricte des trois CSV de démonstration."""
import csv
import math
from dataclasses import dataclass
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"


@dataclass(frozen=True)
class Room:
    building: str
    capacity: int
    allowed_models: frozenset[str]


@dataclass
class Dataset:
    rooms: dict[str, Room]
    inventory: dict[tuple[str, str], int]
    connections: list[tuple[str, str, float, str]]

    def occupied(self, room):
        return sum(q for (r, _), q in self.inventory.items() if r == room)

    def available(self, room):
        return self.rooms[room].capacity - self.occupied(room)


def read_csv(path, columns):
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != columns:
            raise ValueError(f"{path.name} : colonnes attendues {columns}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path.name} : fichier vide")
    if any(None in row or any(v is None or not v.strip() for v in row.values()) for row in rows):
        raise ValueError(f"{path.name} : ligne incomplète ou mal formée")
    return [{k: v.strip() for k, v in row.items()} for row in rows]


def load_data(directory=DEMO_DIR):
    directory = Path(directory)
    rooms = {}
    for row in read_csv(directory / "rooms.csv", ["room_id", "building", "capacity", "allowed_models"]):
        key = row["room_id"]
        capacity = int(row["capacity"])
        models = frozenset(m.strip() for m in row["allowed_models"].split("|"))
        if key in rooms or capacity < 0 or "" in models:
            raise ValueError("Salle dupliquée, capacité négative ou modèle vide")
        rooms[key] = Room(row["building"], capacity, models)
    inventory = {}
    for row in read_csv(directory / "inventory.csv", ["room_id", "model", "quantity"]):
        room, model = row["room_id"], row["model"]
        quantity = int(row["quantity"])
        if room not in rooms or quantity < 0 or (room, model) in inventory:
            raise ValueError("Inventaire invalide : salle, quantité ou doublon")
        if model not in rooms[room].allowed_models:
            raise ValueError("Modèle présent mais non autorisé dans la salle")
        inventory[room, model] = quantity
    connections, seen = [], set()
    for row in read_csv(directory / "connections.csv", ["source", "target", "distance_m", "distance_type"]):
        source, target = row["source"], row["target"]
        distance = float(row["distance_m"])
        key = frozenset((source, target))
        if source == target or key in seen or not math.isfinite(distance) or distance <= 0:
            raise ValueError("Connexion dupliquée, boucle ou distance invalide")
        if row["distance_type"] not in {"simulated", "estimated"}:
            raise ValueError("Type de distance attendu : simulated ou estimated")
        seen.add(key)
        connections.append((source, target, distance, row["distance_type"]))
    dataset = Dataset(rooms, inventory, connections)
    if any(dataset.available(room) < 0 for room in rooms):
        raise ValueError("Inventaire supérieur à la capacité totale")
    return dataset
