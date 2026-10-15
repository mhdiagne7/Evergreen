"""Blocs compacts de petits parcs, avec un modèle commun par bloc."""

from collections import Counter
from itertools import combinations

from core.campus import CENTRAL_STOCK, building_distance
from core.homogeneity import building_models, plan_homogeneity, suggested_targets


def block_counts(data, buildings):
    counts = Counter()
    for building in buildings:
        counts.update(building_models(data, building))
    return +counts


def block_diameter(buildings):
    distances = [building_distance(a, b) for a, b in combinations(buildings, 2)]
    if any(distance is None for distance in distances):
        return None
    return max(distances, default=0)


def suggest_blocks(data, max_posts=5, max_distance=200, max_buildings=4):
    """Fusion gloutonne par proximité ; chaque paire respecte le seuil.

    Le diamètre empêche une chaîne de voisins de réunir des bâtiments éloignés.
    Les distances géographiques servent à définir le voisinage, pas un trajet.
    Un bâtiment ne peut appartenir qu'à un bloc proposé.
    """
    if max_posts < 1 or max_distance <= 0 or max_buildings < 2:
        raise ValueError("Les seuils de regroupement doivent être positifs.")
    codes = sorted(
        {r.building for r in data.rooms.values() if r.room_type == "classroom"}
    )
    candidates = [
        code
        for code in codes
        if 0 < sum(building_models(data, code).values()) <= max_posts
    ]
    groups = [
        (code,) for code in candidates if building_distance(code, code) is not None
    ]
    while True:
        merges = []
        for index, first in enumerate(groups):
            for second in groups[index + 1 :]:
                merged = tuple(sorted(first + second))
                if len(merged) > max_buildings:
                    continue
                diameter = block_diameter(merged)
                if diameter is not None and diameter <= max_distance:
                    merges.append((diameter, merged, first, second))
        if not merges:
            break
        _, merged, first, second = min(merges)
        groups.remove(first)
        groups.remove(second)
        groups.append(merged)
    return sorted(group for group in groups if len(group) >= 2)


def block_candidates(data, buildings):
    """Comparer les quantités sans assimiler taille, génération et performance."""
    counts = block_counts(data, buildings)
    total = sum(counts.values())
    return sorted(
        [
            {
                "Modèle": model,
                "Déjà dans le bloc": quantity,
                "À remplacer": total - quantity,
                "Disponible à Morisset": data.inventory.get((CENTRAL_STOCK, model), 0),
                "Manque hors bloc": max(
                    0, total - quantity - data.inventory.get((CENTRAL_STOCK, model), 0)
                ),
            }
            for model, quantity in counts.items()
        ],
        key=lambda row: (-row["Déjà dans le bloc"], row["Modèle"]),
    )


def plan_blocks(
    data, blocks, stock=CENTRAL_STOCK, protect_newer=True, include_other_buildings=True
):
    if not blocks:
        raise ValueError("Choisir au moins un bloc.")
    known = {
        room.building for room in data.rooms.values() if room.room_type == "classroom"
    }
    targets = suggested_targets(data) if include_other_buildings else {}
    used = set()
    normalized = []
    for block in blocks:
        buildings = tuple(sorted(set(block["buildings"])))
        model = block["model"]
        if len(buildings) < 2 or set(buildings) - known:
            raise ValueError("Un bloc doit contenir au moins deux bâtiments recensés.")
        if used.intersection(buildings):
            raise ValueError("Un bâtiment ne peut appartenir qu'à un seul bloc.")
        if not model or model == "*":
            raise ValueError("Choisir un modèle cible pour chaque bloc.")
        used.update(buildings)
        targets.update({building: model for building in buildings})
        normalized.append({"buildings": list(buildings), "model": model})
    plan = plan_homogeneity(data, targets, stock, protect_newer)
    plan["blocks"] = normalized
    plan["block_summary"] = []
    for block in normalized:
        rows = [row for row in plan["summary"] if row["Bâtiment"] in block["buildings"]]
        plan["block_summary"].append(
            {
                "Bloc": " + ".join(block["buildings"]),
                "Modèle commun": block["model"],
                "Postes": sum(row["Postes attendus"] for row in rows),
                "Conformes avant": sum(row["Conformes avant"] for row in rows),
                "Conformes après": sum(row["Conformes après"] for row in rows),
                "Manque": sum(row["Manque"] for row in rows),
            }
        )
    return plan
