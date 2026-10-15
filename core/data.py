"""Lecture des salles, du stock et des liaisons, depuis un dossier ou un import."""

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Room:
    building: str
    capacity: int | None
    allowed_models: frozenset[str]
    room_type: str = "classroom"
    capacity_basis: str = "declared"

    def accepts(self, model):
        return "*" in self.allowed_models or model in self.allowed_models


@dataclass
class Dataset:
    rooms: dict[str, Room]
    inventory: dict[tuple[str, str], int]
    connections: list[tuple[str, str, float, str]]
    distance_mode: str = "network"
    import_notes: tuple[str, ...] = ()

    def occupied(self, room):
        return sum(q for (r, _), q in self.inventory.items() if r == room)

    def available(self, room):
        capacity = self.rooms[room].capacity
        if capacity is None:
            return math.inf
        return capacity - self.occupied(room)


SCHEMAS = {
    "rooms.csv": ["room_id", "building", "capacity", "allowed_models"],
    "inventory.csv": ["room_id", "model", "quantity"],
    "connections.csv": ["source", "target", "distance_m", "distance_type"],
}


def read_csv(content, filename):
    """Accepte les CSV UTF-8 exportés avec des virgules ou points-virgules."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(
            f"{filename} : enregistrer le fichier en CSV UTF-8."
        ) from error
    header = text.splitlines()[0] if text.splitlines() else ""
    delimiter = ";" if ";" in header else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    columns = SCHEMAS[filename]
    if (
        filename == "rooms.csv"
        and reader.fieldnames
        and "room_type" in reader.fieldnames
    ):
        columns = columns + ["room_type"]
    if (
        reader.fieldnames is None
        or len(reader.fieldnames) != len(columns)
        or set(reader.fieldnames) != set(columns)
    ):
        raise ValueError(f"{filename} : colonnes attendues : {', '.join(columns)}.")
    rows = []
    for row in reader:
        if None in row or any(
            value is None or not value.strip() for value in row.values()
        ):
            raise ValueError(
                f"{filename}, ligne {reader.line_num} : cellule vide ou colonne en trop."
            )
        rows.append({key: value.strip() for key, value in row.items()})
    if not rows and filename == "rooms.csv":
        raise ValueError("rooms.csv : ajouter au moins une salle.")
    return rows


def whole_number(value, filename, field):
    try:
        number = int(value)
    except ValueError as error:
        raise ValueError(
            f"{filename} : {field} doit être un entier (valeur reçue : {value})."
        ) from error
    return number


def load_data(directory):
    directory = Path(directory)
    return load_csv_files({name: (directory / name).read_bytes() for name in SCHEMAS})


def load_csv_files(files):
    """Valide un jeu complet avant de le rendre disponible, sans écrire de fichier."""
    missing = set(SCHEMAS) - set(files)
    if missing:
        raise ValueError("Fichiers manquants : " + ", ".join(sorted(missing)))
    rooms = {}
    for row in read_csv(files["rooms.csv"], "rooms.csv"):
        key = row["room_id"]
        capacity = whole_number(row["capacity"], "rooms.csv", "capacity")
        models = frozenset(m.strip() for m in row["allowed_models"].split("|"))
        if key in rooms or capacity < 0 or "" in models:
            raise ValueError("Salle dupliquée, capacité négative ou modèle vide")
        room_type = row.get("room_type", "classroom")
        if room_type not in {"classroom", "storage"}:
            raise ValueError(f"{key} : room_type doit être classroom ou storage")
        rooms[key] = Room(row["building"], capacity, models, room_type)
    inventory = {}
    for row in read_csv(files["inventory.csv"], "inventory.csv"):
        room, model = row["room_id"], row["model"]
        quantity = whole_number(row["quantity"], "inventory.csv", "quantity")
        if room not in rooms or quantity < 0 or (room, model) in inventory:
            raise ValueError("Inventaire invalide : salle, quantité ou doublon")
        if not rooms[room].accepts(model):
            raise ValueError("Modèle présent mais non autorisé dans la salle")
        inventory[room, model] = quantity
    connections, seen = [], set()
    for row in read_csv(files["connections.csv"], "connections.csv"):
        source, target = row["source"], row["target"]
        try:
            distance = float(row["distance_m"].replace(",", "."))
        except ValueError as error:
            raise ValueError(
                "connections.csv : distance_m doit être un nombre en mètres."
            ) from error
        key = frozenset((source, target))
        if (
            source == target
            or key in seen
            or not math.isfinite(distance)
            or distance <= 0
        ):
            raise ValueError("Connexion dupliquée, boucle ou distance invalide")
        if row["distance_type"] not in {"simulated", "estimated", "measured"}:
            raise ValueError(
                "connections.csv : distance_type doit être simulated, estimated ou measured"
            )
        seen.add(key)
        connections.append((source, target, distance, row["distance_type"]))
    dataset = Dataset(rooms, inventory, connections)
    if any(dataset.available(room) < 0 for room in rooms):
        raise ValueError("Inventaire supérieur à la capacité totale")
    return dataset
