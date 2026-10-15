"""Inventaire local durable. Chaque confirmation est une transaction SQLite."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from core.buildings import Transfer, apply_transfers
from core.data import Dataset, Room
from core.graph import build_graph
from core.routing import shortest_route

DEFAULT_DB = Path(__file__).resolve().parents[1] / "private" / "evergreen.sqlite3"


def encode_data(data):
    return json.dumps(
        {
            "rooms": {
                r: {**asdict(info), "allowed_models": sorted(info.allowed_models)}
                for r, info in data.rooms.items()
            },
            "inventory": [[r, m, q] for (r, m), q in sorted(data.inventory.items())],
            "connections": data.connections,
            "distance_mode": data.distance_mode,
            "import_notes": list(data.import_notes),
        },
        ensure_ascii=False,
    )


def decode_data(raw):
    content = json.loads(raw)
    rooms = {
        r: Room(**{**info, "allowed_models": frozenset(info["allowed_models"])})
        for r, info in content["rooms"].items()
    }
    return Dataset(
        rooms,
        {(r, m): q for r, m, q in content["inventory"]},
        [tuple(edge) for edge in content["connections"]],
        content.get("distance_mode", "network"),
        tuple(content.get("import_notes", [])),
    )


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, data TEXT NOT NULL,
                    models TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, workspace TEXT NOT NULL, revision INTEGER NOT NULL,
                    name TEXT NOT NULL, plan TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, workspace TEXT NOT NULL, created TEXT NOT NULL,
                    kind TEXT NOT NULL, note TEXT NOT NULL, details TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def list_workspaces(self, include_archived=False):
        with self.connect() as db:
            query = "SELECT id,name,revision FROM workspaces"
            if not include_archived:
                query += " WHERE id != 'demo'"
            return [dict(row) for row in db.execute(query + " ORDER BY rowid")]

    def create_workspace(self, name, data, identifier=None):
        name = name.strip()
        if not name:
            raise ValueError("Donner un nom au jeu de données.")
        identifier = identifier or uuid.uuid4().hex
        models = {m for _, m in data.inventory} | {
            m for room in data.rooms.values() for m in room.allowed_models if m != "*"
        }
        with self.connect() as db:
            db.execute(
                "INSERT INTO workspaces(id,name,data,models) VALUES (?,?,?,?)",
                (identifier, name, encode_data(data), json.dumps(sorted(models))),
            )
        return identifier

    def _read(self, db, identifier):
        row = db.execute(
            "SELECT * FROM workspaces WHERE id=?", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError("Jeu de données introuvable.")
        return row, decode_data(row["data"])

    def load(self, identifier):
        with self.connect() as db:
            row, data = self._read(db, identifier)
            return data, json.loads(row["models"]), row["revision"], row["name"]

    def _check_revision(self, row, revision):
        if row["revision"] != revision:
            raise ValueError(
                "L'inventaire a changé depuis la préparation. Actualiser et préparer un nouveau lot."
            )

    def _save(self, db, identifier, data):
        db.execute(
            "UPDATE workspaces SET data=?,revision=revision+1 WHERE id=?",
            (encode_data(data), identifier),
        )

    def _event(self, db, workspace, kind, note, details):
        db.execute(
            "INSERT INTO events(workspace,created,kind,note,details) VALUES (?,?,?,?,?)",
            (workspace, now(), kind, note, json.dumps(details, ensure_ascii=False)),
        )

    def add_model(self, identifier, model):
        model = model.strip()
        if not model or model == "*":
            raise ValueError("Saisir un nom de modèle, par exemple Dell OptiPlex 7090.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, _ = self._read(db, identifier)
            models = set(json.loads(row["models"]))
            if model in models:
                raise ValueError("Ce modèle existe déjà.")
            models.add(model)
            db.execute(
                "UPDATE workspaces SET models=? WHERE id=?",
                (json.dumps(sorted(models)), identifier),
            )
            self._event(db, identifier, "Modèle ajouté", model, {})

    def receive(self, identifier, room, model, quantity, revision, note=""):
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("La quantité reçue doit être un entier positif.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self._read(db, identifier)
            self._check_revision(row, revision)
            if room not in data.rooms or data.rooms[room].room_type != "storage":
                raise ValueError(
                    "Les arrivages doivent être enregistrés dans une réserve."
                )
            if model not in json.loads(row["models"]) or not data.rooms[room].accepts(
                model
            ):
                raise ValueError("Modèle inconnu ou non autorisé dans cette réserve.")
            if data.available(room) < quantity:
                raise ValueError("La réserve n'a pas assez de places.")
            data.inventory[room, model] = (
                data.inventory.get((room, model), 0) + quantity
            )
            self._save(db, identifier, data)
            self._event(
                db,
                identifier,
                "Entrée de stock",
                note.strip(),
                {"room": room, "model": model, "quantity": quantity},
            )

    def configure_stock_capacity(self, identifier, room, capacity, revision):
        if capacity is not None and (
            isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 0
        ):
            raise ValueError(
                "Capacité attendue : un entier positif ou nul, ou aucune limite configurée."
            )
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self._read(db, identifier)
            self._check_revision(row, revision)
            if room not in data.rooms or data.rooms[room].room_type != "storage":
                raise ValueError("Stock introuvable.")
            if capacity is not None and capacity < data.occupied(room):
                raise ValueError(
                    "La capacité ne peut pas être inférieure au stock présent."
                )
            data.rooms[room] = replace(data.rooms[room], capacity=capacity)
            self._save(db, identifier, data)
            self._event(
                db,
                identifier,
                "Capacité du stock",
                "",
                {"room": room, "capacity": capacity},
            )

    def save_batch(self, identifier, revision, name, plan):
        if not plan["groups"] or not name.strip():
            raise ValueError("Le lot doit avoir un nom et au moins un déplacement.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self._read(db, identifier)
            self._check_revision(row, revision)
            self._validate_plan(data, plan["groups"])
            batch_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO batches VALUES (?,?,?,?,?,?,?)",
                (
                    batch_id,
                    identifier,
                    revision,
                    name.strip(),
                    json.dumps(plan, ensure_ascii=False),
                    "Préparé",
                    now(),
                ),
            )
        return batch_id

    def _validate_plan(self, data, groups):
        graph = build_graph(data)
        for group in groups:
            transfers = [Transfer(**move) for move in group["transfers"]]
            if not transfers:
                raise ValueError("Une opération doit contenir un déplacement.")
            for transfer in transfers:
                if shortest_route(graph, transfer.source, transfer.destination) is None:
                    raise ValueError("Un déplacement n'a pas de chemin renseigné.")
            data = apply_transfers(data, transfers)
        return data

    def batches(self, identifier):
        with self.connect() as db:
            rows = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM batches WHERE workspace=? ORDER BY created DESC,rowid DESC",
                    (identifier,),
                )
            ]
        for row in rows:
            row["plan"] = json.loads(row["plan"])
        return rows

    def confirm_batch(self, identifier, batch_id, completed, note):
        """Une opération de salle est indivisible : retrait, pose et retour ensemble."""
        if not note.strip() or not completed or len(set(completed)) != len(completed):
            raise ValueError(
                "Sélectionner les salles terminées et renseigner une note de réalisation."
            )
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self._read(db, identifier)
            batch = db.execute(
                "SELECT * FROM batches WHERE id=? AND workspace=?",
                (batch_id, identifier),
            ).fetchone()
            if batch is None or batch["status"] not in {"Préparé", "Partiel"}:
                raise ValueError("Ce lot est déjà terminé, annulé ou introuvable.")
            self._check_revision(row, batch["revision"])
            plan = json.loads(batch["plan"])
            valid = [i for i, g in enumerate(plan["groups"]) if not g.get("completed")]
            if any(
                isinstance(i, bool) or not isinstance(i, int) or i not in valid
                for i in completed
            ):
                raise ValueError(
                    "Cette opération a déjà été confirmée ou n'existe pas."
                )
            # L'ordre du plan est conservé, même si la sélection est différente.
            chosen = [plan["groups"][i] for i in sorted(completed)]
            updated = self._validate_plan(data, chosen)
            self._save(db, identifier, updated)
            for i in completed:
                plan["groups"][i]["completed"] = True
            status = (
                "Terminé"
                if all(g.get("completed") for g in plan["groups"])
                else "Partiel"
            )
            db.execute(
                "UPDATE batches SET revision=?,plan=?,status=? WHERE id=?",
                (
                    row["revision"] + 1,
                    json.dumps(plan, ensure_ascii=False),
                    status,
                    batch_id,
                ),
            )
            self._event(
                db,
                identifier,
                "Déplacements confirmés",
                note.strip(),
                {"batch": batch_id, "name": batch["name"], "groups": chosen},
            )

    def cancel_batch(self, identifier, batch_id):
        with self.connect() as db:
            changed = db.execute(
                "UPDATE batches SET status='Annulé' WHERE id=? AND workspace=? AND status IN ('Préparé','Partiel')",
                (batch_id, identifier),
            ).rowcount
            if changed != 1:
                raise ValueError("Ce lot ne peut plus être annulé.")
            self._event(
                db,
                identifier,
                "Lot annulé",
                "Les déplacements déjà confirmés sont conservés.",
                {"batch": batch_id},
            )

    def history(self, identifier):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT created,kind,note,details FROM events WHERE workspace=? ORDER BY id DESC",
                    (identifier,),
                )
            ]

    def backup(self):
        # serialize() n'est pas présent sur toutes les distributions Python.
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "backup.sqlite3"
            with self.connect() as db:
                target = sqlite3.connect(path)
                try:
                    db.backup(target)
                finally:
                    target.close()
            return path.read_bytes()
