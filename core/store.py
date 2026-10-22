"""Inventaire local durable. Chaque confirmation est une transaction SQLite."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from copy import deepcopy
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
            "returned_stock": [
                [room, model, quantity]
                for (room, model), quantity in sorted(data.returned_stock.items())
            ],
            "model_years": data.model_years,
            "model_formats": data.model_formats,
            "walking_routes": [
                [a, b, value] for (a, b), value in sorted(data.walking_routes.items())
            ],
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
        {
            (room, model): quantity
            for room, model, quantity in content.get("returned_stock", [])
        },
        content.get("model_years", {}),
        content.get("model_formats", {}),
        {(a, b): value for a, b, value in content.get("walking_routes", [])},
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
        from core.asset_groups import sync_assets

        sync_assets(db, identifier, data)
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
            if data.distance_mode == "geodesic" and data.rooms[room].building != "MRT":
                raise ValueError(
                    "Les nouveaux stocks sont reçus uniquement à Morisset (MRT)."
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

    def receive_many(self, identifier, items, revision, note=""):
        """Une réception, plusieurs modèles, une seule transaction et révision."""
        from core.campus import CENTRAL_STOCK

        if not items:
            raise ValueError("Ajouter au moins un modèle et une quantité.")
        quantities = {}
        for item in items:
            model = str(item.get("model", "")).strip()
            quantity = item.get("quantity")
            if not model or model == "*" or len(model) > 160:
                raise ValueError("Saisir un nom de modèle valide.")
            if (
                isinstance(quantity, bool)
                or not isinstance(quantity, int)
                or quantity <= 0
            ):
                raise ValueError("Chaque quantité doit être un entier positif.")
            quantities[model] = quantities.get(model, 0) + quantity
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self._read(db, identifier)
            self._check_revision(row, revision)
            stock = data.rooms.get(CENTRAL_STOCK)
            if stock is None or stock.room_type != "storage" or stock.building != "MRT":
                raise ValueError("Définir le stock central à Morisset.")
            if data.available(CENTRAL_STOCK) < sum(quantities.values()):
                raise ValueError("La capacité du stock central est insuffisante.")
            if any(not stock.accepts(model) for model in quantities):
                raise ValueError("Un modèle n’est pas autorisé au stock central.")
            models = set(json.loads(row["models"]))
            for model, quantity in quantities.items():
                data.inventory[CENTRAL_STOCK, model] = (
                    data.inventory.get((CENTRAL_STOCK, model), 0) + quantity
                )
                models.add(model)
            db.execute(
                "UPDATE workspaces SET models=? WHERE id=?",
                (json.dumps(sorted(models)), identifier),
            )
            self._save(db, identifier, data)
            self._event(
                db,
                identifier,
                "Réception multiple",
                note.strip(),
                {"room": CENTRAL_STOCK, "items": quantities},
            )

    def reset_central_stock(self, identifier, revision, note):
        """Correction explicite des quantités, sans toucher aux postes installés."""
        from core.campus import CENTRAL_STOCK

        if not note.strip():
            raise ValueError("Indiquer le motif de remise à zéro.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self._read(db, identifier)
            self._check_revision(row, revision)
            before = {
                model: quantity
                for (room, model), quantity in data.inventory.items()
                if room == CENTRAL_STOCK
            }
            data.inventory = {
                key: q for key, q in data.inventory.items() if key[0] != CENTRAL_STOCK
            }
            data.returned_stock = {
                key: q
                for key, q in data.returned_stock.items()
                if key[0] != CENTRAL_STOCK
            }
            self._save(db, identifier, data)
            self._event(
                db,
                identifier,
                "Stock central remis à zéro",
                note.strip(),
                {"before": before},
            )

    def set_model_format(self, identifier, model, form, revision):
        from core.model_catalog import FORMATS

        if form not in FORMATS:
            raise ValueError("Format physique inconnu.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self._read(db, identifier)
            self._check_revision(row, revision)
            if model not in json.loads(row["models"]):
                raise ValueError("Modèle inconnu dans le catalogue local.")
            if form == "À confirmer":
                data.model_formats.pop(model, None)
            else:
                data.model_formats[model] = form
            self._save(db, identifier, data)
            self._event(
                db,
                identifier,
                "Format physique",
                "Confirmation locale du boîtier",
                {"model": model, "format": form},
            )

    def set_walking_distance(
        self, identifier, source, target, metres, revision, both=False
    ):
        import math

        from core.campus import building_position

        if (
            source == target
            or building_position(source) is None
            or building_position(target) is None
        ):
            raise ValueError(
                "Choisir deux bâtiments distincts aux coordonnées connues."
            )
        if (
            isinstance(metres, bool)
            or not isinstance(metres, (int, float))
            or not math.isfinite(metres)
            or not 0 < metres <= 100_000
        ):
            raise ValueError(
                "La distance doit être positive et inférieure ou égale à 100 km."
            )
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self._read(db, identifier)
            self._check_revision(row, revision)
            known = {r.building for r in data.rooms.values()}
            if source not in known or target not in known:
                raise ValueError("Bâtiment absent de cet inventaire.")
            value = {
                "distance_m": float(metres),
                "recorded_at": now(),
                "source": "Distance de marche renseignée manuellement",
            }
            data.walking_routes[source, target] = value
            if both:
                data.walking_routes[target, source] = dict(value)
            self._save(db, identifier, data)
            self._event(
                db,
                identifier,
                "Distance de marche renseignée",
                "Saisie manuelle ; aucun appel Google API",
                {"source": source, "target": target, "metres": metres, "both": both},
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

    def set_model_year(self, identifier, model, year, revision):
        if (
            isinstance(year, bool)
            or not isinstance(year, int)
            or not 1980 <= year <= 2100
        ):
            raise ValueError("Renseigner une année de génération entre 1980 et 2100.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self._read(db, identifier)
            self._check_revision(row, revision)
            if model not in json.loads(row["models"]):
                raise ValueError("Modèle inconnu.")
            data.model_years[model] = year
            self._save(db, identifier, data)
            self._event(
                db, identifier, "Année du modèle", "", {"model": model, "year": year}
            )

    def save_batch(self, identifier, revision, name, plan):
        plan = deepcopy(plan)
        for group in plan["groups"]:
            if "Google Maps" in group.get("distance_type", ""):
                group["delivery_m"] = None
                group["distance_type"] = "Trajet à recalculer dans la session"
        if not plan["groups"] or not name.strip():
            raise ValueError("Le lot doit avoir un nom et au moins un déplacement.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self._read(db, identifier)
            self._check_revision(row, revision)
            self._validate_plan(
                data,
                plan["groups"],
                plan.get("mode") == "homogenization",
                plan.get("mode") == "asset_group",
            )
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

    def _validate_plan(
        self, data, groups, allow_regrouping=False, allow_asset_movement=False
    ):
        graph = build_graph(data)
        for group in groups:
            transfers = [Transfer(**move) for move in group["transfers"]]
            if not transfers:
                raise ValueError("Une opération doit contenir un déplacement.")
            for transfer in transfers:
                if transfer.stock_kind == "regrouped" and not allow_regrouping:
                    raise ValueError(
                        "Cette catégorie de déplacement exige un lot de regroupement."
                    )
                if transfer.stock_kind != "returned" or allow_asset_movement:
                    continue
                installed = [
                    model
                    for (room, model), quantity in data.inventory.items()
                    if room == transfer.destination and quantity > 0
                ]
                if (
                    len(installed) != 1
                    or installed[0] not in data.model_years
                    or transfer.model not in data.model_years
                    or data.model_years[transfer.model]
                    <= data.model_years[installed[0]]
                ):
                    raise ValueError(
                        "Un poste réaffecté doit être plus récent que le modèle installé, selon les années renseignées."
                    )
            for transfer in transfers:
                if shortest_route(graph, transfer.source, transfer.destination) is None:
                    raise ValueError("Un déplacement n'a pas de chemin renseigné.")
            if group.get("swap"):
                if not allow_asset_movement:
                    raise ValueError("Échange réservé aux déplacements de groupes.")
                from core.buildings import apply_classroom_swap

                data = apply_classroom_swap(data, transfers)
            else:
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
            updated = self._validate_plan(
                data,
                chosen,
                plan.get("mode") == "homogenization",
                plan.get("mode") == "asset_group",
            )
            from core.asset_groups import move_assets

            move_assets(db, identifier, data, chosen)
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
