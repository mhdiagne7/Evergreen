"""Importer un inventaire réel sans inventer de salles ni de stock disponible."""

import csv
import io
import re
from collections import Counter

from core.campus import CENTRAL_STOCK
from core.data import Dataset, Room

# Suffixes de postes confirmés par l’utilisateur, pas des numéros de salles.
CONFIRMED_LEE_ROOMS = ("LEE-105", "LEE-107", "LEE-109")


def canonical_owned_room(room):
    for base in CONFIRMED_LEE_ROOMS:
        if room in {base + "-" + str(index) for index in range(1, 5)}:
            return base
    return room


def import_owned_computers(content, stock_capacity=None):
    """Chaque ligne ajoute sa quantité ; les répétitions sont signalées.

    Les salles distinctes sont recensées depuis leur identifiant. Leur capacité
    de travail est le nombre de postes observés, pas une capacité immobilière.
    Le stock MRT démarre vide : l'export fourni recense les postes installés.
    """
    if stock_capacity is not None and (
        isinstance(stock_capacity, bool)
        or not isinstance(stock_capacity, int)
        or stock_capacity < 0
    ):
        raise ValueError("La capacité du stock doit être un entier positif ou nul.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Enregistrer l'inventaire en CSV UTF-8.") from error
    header = text.splitlines()[0] if text.splitlines() else ""
    delimiter = ";" if ";" in header else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    expected = {"room_id", "model", "quantity"}
    if (
        reader.fieldnames is None
        or len(reader.fieldnames) != 3
        or set(reader.fieldnames) != expected
    ):
        raise ValueError("Colonnes attendues : room_id, model, quantity.")

    inventory = {}
    totals = Counter()
    repeated = set()
    for row in reader:
        prefix = f"Ligne {reader.line_num} : "
        if None in row or any(
            value is None or not value.strip() for value in row.values()
        ):
            raise ValueError(prefix + "cellule vide ou colonne en trop.")
        room = canonical_owned_room(row["room_id"].strip())
        model = row["model"].strip()
        if not re.fullmatch(r"[A-Z0-9]+-[A-Za-z0-9][A-Za-z0-9 ._/-]*", room):
            raise ValueError(
                prefix + "identifiant attendu sous la forme BATIMENT-SALLE."
            )
        if room == CENTRAL_STOCK:
            raise ValueError(
                prefix
                + "MRT-STOCK est réservé au stock central ; utiliser les arrivages."
            )
        if len(model) > 160 or model == "*":
            raise ValueError(prefix + "nom de modèle invalide.")
        try:
            quantity = int(row["quantity"])
        except ValueError as error:
            raise ValueError(prefix + "la quantité doit être entière.") from error
        if quantity <= 0:
            raise ValueError(prefix + "la quantité doit être strictement positive.")
        key = room, model
        if key in inventory:
            repeated.add(key)
        inventory[key] = inventory.get(key, 0) + quantity
        totals[room] += quantity
    if not inventory:
        raise ValueError("L'inventaire ne contient aucun ordinateur.")

    rooms = {
        room: Room(
            building=room.split("-", 1)[0],
            capacity=quantity,
            allowed_models=frozenset({"*"}),
            capacity_basis="observed",
        )
        for room, quantity in sorted(totals.items())
    }
    rooms[CENTRAL_STOCK] = Room(
        building="MRT",
        capacity=stock_capacity,
        allowed_models=frozenset({"*"}),
        room_type="storage",
    )
    notes = tuple(
        f"{room} · {model} : lignes répétées additionnées ({inventory[room, model]} postes). "
        "Vérifier qu’il ne s’agit pas d’un doublon d’export ; aucun numéro de série ne permet de le déduire."
        for room, model in sorted(repeated)
    )
    return Dataset(rooms, inventory, [], distance_mode="geodesic", import_notes=notes)
