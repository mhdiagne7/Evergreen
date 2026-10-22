"""Groupes persistants et suivi d’unités locales, distincts des mouvements réels."""

import json
import sqlite3
import uuid
from collections import Counter
from itertools import groupby

from core.buildings import Transfer, apply_transfers
from core.campus import building_distance
from core.graph import build_graph
from core.routing import shortest_route
from core.store import now

CONDITIONS = ["Non renseigné", "Bon", "À vérifier", "À remplacer", "Hors service"]
PRIORITIES = ["Non renseignée", "Faible", "Normale", "Haute", "Urgente"]
SCHEMA = """
CREATE TABLE IF NOT EXISTS tracked_assets (
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, room TEXT NOT NULL, model TEXT NOT NULL,
 kind TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, physical_id TEXT NOT NULL DEFAULT '',
 category INTEGER, condition TEXT NOT NULL DEFAULT 'Non renseigné',
 priority TEXT NOT NULL DEFAULT 'Non renseignée', available INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS asset_location ON tracked_assets(workspace,room,model,active);
CREATE UNIQUE INDEX IF NOT EXISTS asset_physical_id ON tracked_assets(workspace,physical_id) WHERE physical_id != '' AND active=1;
CREATE TABLE IF NOT EXISTS room_attributes (
 workspace TEXT NOT NULL, room TEXT NOT NULL, floor TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(workspace,room));
CREATE TABLE IF NOT EXISTS asset_groups (
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL,
 members TEXT NOT NULL, origins TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
 batch_id TEXT, created TEXT NOT NULL);
"""


def registry_exists(db):
    return (
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tracked_assets'"
        ).fetchone()
        is not None
    )


def sync_assets(db, workspace, data):
    """Les unités sans numéro physique sont des identifiants locaux, jamais des numéros de série."""
    if not registry_exists(db):
        return
    expected = Counter()
    for (room, model), quantity in data.inventory.items():
        if data.rooms[room].room_type == "storage":
            returned = data.returned_stock.get((room, model), 0)
            expected[room, model, "returned"] += returned
            expected[room, model, "new"] += quantity - returned
        else:
            expected[room, model, "installed"] += quantity
    existing = {}
    for row in db.execute(
        "SELECT * FROM tracked_assets WHERE workspace=? AND active=1 ORDER BY id",
        (workspace,),
    ):
        existing.setdefault((row["room"], row["model"], row["kind"]), []).append(
            row["id"]
        )
    for key in set(expected) | set(existing):
        ids = existing.get(key, [])
        target = expected.get(key, 0)
        if target < len(ids):
            db.executemany(
                "UPDATE tracked_assets SET active=0 WHERE id=?",
                [(item,) for item in ids[target:]],
            )
        for _ in range(max(0, target - len(ids))):
            db.execute(
                "INSERT INTO tracked_assets(id,workspace,room,model,kind) VALUES (?,?,?,?,?)",
                ("EG-" + uuid.uuid4().hex, workspace, *key),
            )


def move_assets(db, workspace, data, operations):
    """Même transaction que les quantités, pour les lots nouveaux et préexistants."""
    if not registry_exists(db):
        return
    sync_assets(db, workspace, data)
    for operation in operations:
        specific = operation.get("asset_ids")
        if specific and (
            len(operation["transfers"]) != 1
            or len(specific) != operation["transfers"][0]["quantity"]
        ):
            raise ValueError(
                "Identifiants d’ordinateurs incohérents dans le déplacement."
            )
        for raw in operation["transfers"]:
            move = Transfer(**raw)
            rows = list(
                db.execute(
                    "SELECT * FROM tracked_assets WHERE workspace=? AND active=1 AND available=1 AND room=? AND model=? ORDER BY kind,id",
                    (workspace, move.source, move.model),
                )
            )
            if data.rooms[move.source].room_type == "storage":
                if move.stock_kind in {"new", "returned"}:
                    rows = [row for row in rows if row["kind"] == move.stock_kind]
                else:
                    rows.sort(key=lambda row: (row["kind"] != "new", row["id"]))
            if specific:
                rows = [row for row in rows if row["id"] in specific]
                if any(not row["available"] for row in rows):
                    raise ValueError(
                        "Un ordinateur du groupe est désormais indisponible."
                    )
            selected = rows[: move.quantity]
            if len(selected) != move.quantity:
                raise ValueError(
                    "Un ordinateur a changé d’emplacement ou n’est plus disponible dans ce lot."
                )
            for row in selected:
                kind = "installed"
                if data.rooms[move.destination].room_type == "storage":
                    kind = (
                        row["kind"]
                        if data.rooms[move.source].room_type == "storage"
                        else "returned"
                    )
                db.execute(
                    "UPDATE tracked_assets SET room=?,kind=? WHERE id=?",
                    (move.destination, kind, row["id"]),
                )


def filter_assets(assets, filters):
    return [
        asset
        for asset in assets
        if all(
            not values or asset.get(field) in values
            for field, values in filters.items()
        )
    ]


def automatic_groups(assets, fields, maximum=10):
    """Paquets sans déplacement, groupés par critères puis proximité déterministe."""
    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or not 1 <= maximum <= 500
    ):
        raise ValueError("Choisir entre 1 et 500 ordinateurs par groupe.")
    allowed = {
        "category",
        "building",
        "floor",
        "room",
        "model",
        "condition",
        "priority",
    }
    if set(fields) - allowed:
        raise ValueError("Critère de regroupement inconnu.")
    candidates = [asset for asset in assets if asset["active"] and asset["available"]]

    def key(asset):
        return tuple(str(asset.get(field) or "") for field in fields)

    result = []
    for _, bucket in groupby(
        sorted(candidates, key=lambda asset: (key(asset), asset["id"])), key
    ):
        remaining = list(bucket)
        while remaining:
            chosen = [remaining.pop(0)]
            while remaining and len(chosen) < maximum:
                anchor = chosen[-1]

                def proximity(asset):
                    same_room = asset["room"] == anchor["room"]
                    same_building = asset["building"] == anchor["building"]
                    same_floor = (
                        same_building
                        and bool(asset["floor"])
                        and asset["floor"] == anchor["floor"]
                    )
                    distance = building_distance(asset["building"], anchor["building"])
                    return (
                        not same_room,
                        not same_floor,
                        not same_building,
                        distance if distance is not None else float("inf"),
                        asset["id"],
                    )

                best = min(remaining, key=proximity)
                remaining.remove(best)
                chosen.append(best)
            result.append([asset["id"] for asset in chosen])
    return result


def movement_plan(data, assets, destination):
    if not assets:
        raise ValueError("Ce groupe est vide.")
    if destination not in data.rooms:
        raise ValueError("Choisir une salle de destination existante.")
    if any(not asset["active"] or not asset["available"] for asset in assets):
        raise ValueError("Un ordinateur est absent de l’inventaire ou indisponible.")
    graph = build_graph(data)
    work = data
    groups = []
    ordered = sorted(
        assets,
        key=lambda asset: (
            asset["building"] != data.rooms[destination].building,
            asset["building"],
            asset["floor"],
            asset["room"],
            asset["id"],
        ),
    )
    for asset in ordered:
        if asset["room"] == destination:
            continue
        route = shortest_route(graph, asset["room"], destination)
        if route is None:
            raise ValueError("Aucun trajet renseigné pour " + asset["room"])
        move = Transfer(
            asset["room"],
            destination,
            asset["model"],
            stock_kind=asset["kind"] if asset["kind"] in {"new", "returned"} else "any",
        )
        work = apply_transfers(work, [move])
        groups.append(
            {
                "room": destination,
                "old_model": asset["model"],
                "new_model": asset["model"],
                "source": asset["room"],
                "delivery_m": route.distance_m,
                "distance_type": route.distance_label,
                "stock_kind": "any",
                "asset_ids": [asset["id"]],
                "transfers": [vars(move)],
            }
        )
    if not groups:
        raise ValueError(
            "Tous les ordinateurs sont déjà dans la destination : aucun déplacement nécessaire."
        )
    return {
        "mode": "asset_group",
        "building": data.rooms[destination].building,
        "buffer": destination,
        "destination": destination,
        "groups": groups,
    }


class GroupStore:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript(SCHEMA)

    def assets(self, workspace):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            _, data = self.store._read(db, workspace)
            sync_assets(db, workspace, data)
            floors = {
                row["room"]: row["floor"]
                for row in db.execute(
                    "SELECT * FROM room_attributes WHERE workspace=?", (workspace,)
                )
            }
            result = []
            for row in db.execute(
                "SELECT * FROM tracked_assets WHERE workspace=? ORDER BY room,model,id",
                (workspace,),
            ):
                item = dict(row)
                item["building"] = (
                    data.rooms[item["room"]].building
                    if item["room"] in data.rooms
                    else ""
                )
                item["floor"] = floors.get(item["room"], "")
                item["room_type"] = (
                    data.rooms[item["room"]].room_type
                    if item["room"] in data.rooms
                    else ""
                )
                result.append(item)
            return result

    def groups(self, workspace):
        with self.store.connect() as db:
            result = []
            for row in db.execute(
                "SELECT * FROM asset_groups WHERE workspace=? ORDER BY created DESC,rowid DESC",
                (workspace,),
            ):
                item = dict(row)
                item["members"] = json.loads(item["members"])
                item["origins"] = json.loads(item["origins"])
                batch = db.execute(
                    "SELECT status,revision,plan FROM batches WHERE id=? AND workspace=?",
                    (item["batch_id"], workspace),
                ).fetchone()
                item["status"] = (
                    {
                        "Préparé": "Planifié",
                        "Partiel": "En cours",
                        "Terminé": "Terminé",
                    }.get(batch["status"], "Brouillon")
                    if batch
                    else "Brouillon"
                )
                item["destination"] = (
                    json.loads(batch["plan"]).get("destination") if batch else None
                )
                result.append(item)
            return result

    def save_many(self, workspace, revision, drafts):
        if not drafts:
            raise ValueError("Aucun groupe à enregistrer.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self.store._read(db, workspace)
            self.store._check_revision(row, revision)
            sync_assets(db, workspace, data)
            ids = []
            for draft in drafts:
                name = draft["name"].strip()
                members = draft["members"]
                if (
                    not name
                    or len(name) > 160
                    or not members
                    or len(set(members)) != len(members)
                ):
                    raise ValueError("Nom requis, groupe non vide et sans doublons.")
                assets = {
                    r["id"]: dict(r)
                    for r in db.execute(
                        "SELECT * FROM tracked_assets WHERE workspace=? AND active=1",
                        (workspace,),
                    )
                }
                if any(
                    item not in assets or not assets[item]["available"]
                    for item in members
                ):
                    raise ValueError(
                        "Un ordinateur sélectionné est absent ou indisponible."
                    )
                identifier = "group-" + uuid.uuid4().hex
                db.execute(
                    "INSERT INTO asset_groups(id,workspace,name,description,members,origins,created) VALUES (?,?,?,?,?,?,?)",
                    (
                        identifier,
                        workspace,
                        name,
                        draft.get("description", "").strip(),
                        json.dumps(members),
                        json.dumps({item: assets[item]["room"] for item in members}),
                        now(),
                    ),
                )
                ids.append(identifier)
            self.store._event(
                db,
                workspace,
                "Groupes créés",
                "Aucun déplacement d’inventaire",
                {"groups": ids},
            )
            return ids

    def update(self, workspace, identifier, version, name, description, members):
        if (
            not name.strip()
            or len(name.strip()) > 160
            or not members
            or len(set(members)) != len(members)
        ):
            raise ValueError("Nom requis, groupe non vide et sans doublons.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            group = self._editable(db, workspace, identifier, version)
            _, data = self.store._read(db, workspace)
            sync_assets(db, workspace, data)
            assets = {
                r["id"]: dict(r)
                for r in db.execute(
                    "SELECT * FROM tracked_assets WHERE workspace=? AND active=1",
                    (workspace,),
                )
            }
            original_members = json.loads(group["members"])
            if any(
                item not in assets
                or (not assets[item]["available"] and item not in original_members)
                for item in members
            ):
                raise ValueError(
                    "Un ordinateur sélectionné est absent ou indisponible."
                )
            origins = json.loads(group["origins"])
            origins = {
                item: origins.get(item, assets[item]["room"]) for item in members
            }
            db.execute(
                "UPDATE asset_groups SET name=?,description=?,members=?,origins=?,version=version+1,batch_id=? WHERE id=?",
                (
                    name.strip(),
                    description.strip(),
                    json.dumps(members),
                    json.dumps(origins),
                    group["batch_id"]
                    if set(original_members) == set(members)
                    else None,
                    identifier,
                ),
            )
            self.store._event(
                db, workspace, "Groupe modifié", name.strip(), {"group": identifier}
            )

    def _editable(self, db, workspace, identifier, version):
        group = db.execute(
            "SELECT * FROM asset_groups WHERE id=? AND workspace=?",
            (identifier, workspace),
        ).fetchone()
        if group is None or group["version"] != version:
            raise ValueError("Le groupe a changé. Actualiser avant de continuer.")
        batch = db.execute(
            "SELECT status FROM batches WHERE id=?", (group["batch_id"],)
        ).fetchone()
        if batch and batch["status"] in {"Préparé", "Partiel"}:
            raise ValueError(
                "Annuler ou terminer le lot actif avant de modifier ce groupe."
            )
        return group

    def delete(self, workspace, identifier, version):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            group = self._editable(db, workspace, identifier, version)
            db.execute("DELETE FROM asset_groups WHERE id=?", (identifier,))
            self.store._event(
                db,
                workspace,
                "Groupe supprimé",
                group["name"],
                {"group": identifier, "members": json.loads(group["members"])},
            )

    def metadata(
        self,
        workspace,
        asset_id,
        revision,
        physical_id,
        category,
        condition,
        priority,
        available,
        floor,
    ):
        if (
            condition not in CONDITIONS
            or priority not in PRIORITIES
            or (
                category is not None
                and (type(category) is not int or not 1 <= category <= 99)
            )
        ):
            raise ValueError("Catégorie, état ou priorité invalide.")
        if len(physical_id.strip()) > 160 or len(floor.strip()) > 80:
            raise ValueError("Identifiant ou étage trop long.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self.store._read(db, workspace)
            self.store._check_revision(row, revision)
            sync_assets(db, workspace, data)
            asset = db.execute(
                "SELECT * FROM tracked_assets WHERE id=? AND workspace=? AND active=1",
                (asset_id, workspace),
            ).fetchone()
            if asset is None:
                raise ValueError("Ordinateur absent de cet inventaire.")
            try:
                db.execute(
                    "UPDATE tracked_assets SET physical_id=?,category=?,condition=?,priority=?,available=? WHERE id=?",
                    (
                        physical_id.strip(),
                        category,
                        condition,
                        priority,
                        int(available and condition != "Hors service"),
                        asset_id,
                    ),
                )
            except sqlite3.IntegrityError:
                raise ValueError(
                    "Ce numéro d’inventaire réel est déjà associé à un autre ordinateur."
                ) from None
            db.execute(
                "INSERT INTO room_attributes VALUES (?,?,?) ON CONFLICT(workspace,room) DO UPDATE SET floor=excluded.floor",
                (workspace, asset["room"], floor.strip()),
            )
            self.store._save(db, workspace, data)
            self.store._event(
                db,
                workspace,
                "Caractéristiques d’ordinateur",
                physical_id.strip(),
                {"asset": asset_id},
            )

    def room_capacity(self, workspace, room, revision, capacity):
        from dataclasses import replace

        if type(capacity) is not int or capacity < 0:
            raise ValueError("La capacité doit être un entier positif ou nul.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self.store._read(db, workspace)
            self.store._check_revision(row, revision)
            if room not in data.rooms or capacity < data.occupied(room):
                raise ValueError(
                    "La capacité ne peut être inférieure aux postes présents."
                )
            data.rooms[room] = replace(
                data.rooms[room], capacity=capacity, capacity_basis="declared"
            )
            self.store._save(db, workspace, data)
            self.store._event(
                db,
                workspace,
                "Capacité déclarée",
                "Vérification explicite de la salle",
                {"room": room, "capacity": capacity},
            )

    def plan(self, workspace, identifier, version, revision, destination, save=False):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            group = self._editable(db, workspace, identifier, version)
            row, data = self.store._read(db, workspace)
            self.store._check_revision(row, revision)
            sync_assets(db, workspace, data)
            ids = json.loads(group["members"])
            assets = {
                r["id"]: dict(r)
                for r in db.execute(
                    "SELECT * FROM tracked_assets WHERE workspace=?", (workspace,)
                )
            }
            floors = {
                r["room"]: r["floor"]
                for r in db.execute(
                    "SELECT * FROM room_attributes WHERE workspace=?", (workspace,)
                )
            }
            selected = []
            for asset_id in ids:
                if asset_id not in assets:
                    raise ValueError("Un ordinateur du groupe est introuvable.")
                asset = assets[asset_id]
                asset["building"] = data.rooms[asset["room"]].building
                asset["floor"] = floors.get(asset["room"], "")
                selected.append(asset)
            plan = movement_plan(data, selected, destination)
            plan["asset_group_id"] = identifier
            self.store._validate_plan(data, plan["groups"], allow_asset_movement=True)
            if not save:
                return plan
            batch = "batch-" + uuid.uuid4().hex
            db.execute(
                "INSERT INTO batches VALUES (?,?,?,?,?,?,?)",
                (
                    batch,
                    workspace,
                    revision,
                    group["name"],
                    json.dumps(plan, ensure_ascii=False),
                    "Préparé",
                    now(),
                ),
            )
            db.execute(
                "UPDATE asset_groups SET batch_id=?,version=version+1 WHERE id=?",
                (batch, identifier),
            )
            self.store._event(
                db,
                workspace,
                "Déplacement de groupe planifié",
                "Aucun ordinateur déplacé",
                {"group": identifier, "batch": batch},
            )
            return batch
