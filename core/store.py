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

    def change_token(self, identifier):
        """Révision et dernière action persistée, pour rafraîchir les vues ouvertes."""
        with self.connect() as db:
            row = db.execute(
                "SELECT revision, (SELECT COALESCE(MAX(id),0) FROM events WHERE workspace=?) AS event_id, (SELECT COALESCE(MAX(rowid),0) FROM batches WHERE workspace=?) AS batch_id FROM workspaces WHERE id=?",
                (identifier, identifier, identifier),
            ).fetchone()
            if row is None:
                return None
            return row["revision"], row["event_id"], row["batch_id"]

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

    def batches(self, identifier, include_hidden=False):
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
        return (
            rows
            if include_hidden
            else [row for row in rows if not row["plan"].get("hidden")]
        )

    def confirm_batch(
        self, identifier, batch_id, completed, note, expected_version=None
    ):
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
            if (
                expected_version is not None
                and plan.get("edit_version", 0) != expected_version
            ):
                raise ValueError("Le lot a été modifié. Actualise avant de confirmer.")
            valid = [
                i
                for i, g in enumerate(plan["groups"])
                if not g.get("completed") and not g.get("deleted")
            ]
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
                if all(g.get("completed") or g.get("deleted") for g in plan["groups"])
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

    def undo_confirmed_swaps(
        self,
        identifier,
        batch_id,
        indices,
        revision,
        note="",
        expected_version=None,
        preview=False,
    ):
        """Annule les écritures d’échanges identifiés, sans restaurer toute la base."""
        from core.asset_groups import move_assets, registry_exists
        from core.buildings import apply_classroom_swap

        if (
            not indices
            or any(type(index) is not int for index in indices)
            or len(set(indices)) != len(indices)
        ):
            raise ValueError("Sélectionner des swaps confirmés distincts.")
        if not preview and not note.strip():
            raise ValueError("Renseigner le motif de l’annulation.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self._read(db, identifier)
            self._check_revision(row, revision)
            batch = db.execute(
                "SELECT * FROM batches WHERE id=? AND workspace=?",
                (batch_id, identifier),
            ).fetchone()
            if batch is None or not registry_exists(db):
                raise ValueError("Lot ou suivi individuel introuvable.")
            plan = json.loads(batch["plan"])
            if (
                expected_version is not None
                and plan.get("edit_version", 0) != expected_version
            ):
                raise ValueError("Le lot a été modifié. Actualise avant d’annuler.")
            locations = {
                asset["id"]: dict(asset)
                for asset in db.execute(
                    "SELECT * FROM tracked_assets WHERE workspace=?", (identifier,)
                )
            }
            inverse = []
            work = data
            for index in sorted(indices, reverse=True):
                if type(index) is not int or not 0 <= index < len(plan["groups"]):
                    raise ValueError("Swap introuvable.")
                operation = plan["groups"][index]
                ids = operation.get("asset_moves") or []
                transfers = operation.get("transfers", [])
                if (
                    not operation.get("swap")
                    or not operation.get("completed")
                    or operation.get("undone")
                    or operation.get("deleted")
                    or len(ids) != 2
                    or len(set(ids)) != 2
                    or len(transfers) != 2
                    or any(
                        t.get("quantity", 1) != 1 or t.get("stock_kind", "any") != "any"
                        for t in transfers
                    )
                ):
                    raise ValueError(
                        "Ce swap n’est pas confirmé, a déjà été annulé ou n’a pas d’identifiants fiables."
                    )
                reversed_moves = []
                for asset_id, original in zip(ids, transfers):
                    asset = locations.get(asset_id)
                    if (
                        asset is None
                        or not asset["active"]
                        or not asset["available"]
                        or asset["room"] != original["destination"]
                        or asset["model"] != original["model"]
                    ):
                        raise ValueError(
                            "Un poste a changé d’emplacement ou n’est plus disponible : annulation refusée."
                        )
                    reversed_moves.append(
                        Transfer(
                            original["destination"],
                            original["source"],
                            original["model"],
                        )
                    )
                work = apply_classroom_swap(work, reversed_moves)
                inverse.append(
                    {
                        "swap": True,
                        "asset_moves": ids,
                        "transfers": [asdict(move) for move in reversed_moves],
                        "original_operation": index,
                        "service_tags": [
                            locations[asset_id].get("service_tag", "")
                            for asset_id in ids
                        ],
                    }
                )
                for asset_id, move in zip(ids, reversed_moves):
                    locations[asset_id]["room"] = move.destination
            if preview:
                return inverse
            move_assets(db, identifier, data, inverse)
            self._save(db, identifier, work)
            for index in indices:
                plan["groups"][index]["undone"] = {"at": now(), "note": note.strip()}
            plan["edit_version"] = plan.get("edit_version", 0) + 1
            pending = any(
                not g.get("completed") and not g.get("deleted") for g in plan["groups"]
            )
            done = any(
                g.get("completed") and not g.get("undone") for g in plan["groups"]
            )
            status = (
                ("Partiel" if done else "Préparé")
                if pending
                else ("Terminé" if done else "Annulé")
            )
            if batch["status"] == "Annulé":
                status = "Annulé"
            db.execute(
                "UPDATE batches SET plan=?,revision=?,status=? WHERE id=?",
                (json.dumps(plan, ensure_ascii=False), revision + 1, status, batch_id),
            )
            self._event(
                db,
                identifier,
                "Swaps confirmés annulés",
                note.strip(),
                {
                    "batch": batch_id,
                    "name": batch["name"],
                    "operations": indices,
                    "inverse": inverse,
                },
            )
            return inverse

    def _operation_context(
        self, db, identifier, batch_id, index, version, restore=False
    ):
        row, data = self._read(db, identifier)
        batch = db.execute(
            "SELECT * FROM batches WHERE id=? AND workspace=?", (batch_id, identifier)
        ).fetchone()
        if not batch:
            raise ValueError("Lot introuvable.")
        plan = json.loads(batch["plan"])
        allowed = batch["status"] in {"Préparé", "Partiel"} or (
            restore
            and (
                batch["status"] == "Terminé"
                or (batch["status"] == "Annulé" and plan.get("empty_after_deletions"))
            )
        )
        if not allowed or plan.get("hidden"):
            raise ValueError("Ce lot n’est plus modifiable.")
        self._check_revision(row, batch["revision"])
        if plan.get("edit_version", 0) != version:
            raise ValueError("Le lot a été modifié. Actualise avant de continuer.")
        if type(index) is not int or not 0 <= index < len(plan["groups"]):
            raise ValueError("Opération introuvable.")
        operation = plan["groups"][index]
        if operation.get("completed"):
            raise ValueError(
                "Une opération déjà réalisée ne peut pas être modifiée ou supprimée."
            )
        if bool(operation.get("deleted")) != restore:
            raise ValueError("Cette opération est déjà supprimée ou restaurée.")
        return data, batch, plan, operation

    def _save_edited_plan(self, db, identifier, batch, plan, data, action, before):
        remaining = [
            g for g in plan["groups"] if not g.get("completed") and not g.get("deleted")
        ]
        used = set()
        for operation in remaining:
            ids = operation.get("asset_moves") or operation.get("asset_ids") or []
            if any(asset_id in used for asset_id in ids):
                raise ValueError(
                    "Un ordinateur ne peut pas participer à plusieurs opérations du lot."
                )
            used.update(ids)
        self._validate_plan(
            data,
            remaining,
            plan.get("mode") == "homogenization",
            plan.get("mode") == "asset_group",
        )
        plan["edit_version"] = plan.get("edit_version", 0) + 1
        done = any(g.get("completed") for g in plan["groups"])
        status = (
            ("Partiel" if done else "Préparé")
            if remaining
            else ("Terminé" if done else "Annulé")
        )
        plan["empty_after_deletions"] = not remaining and not done
        db.execute(
            "UPDATE batches SET plan=?,status=? WHERE id=?",
            (json.dumps(plan, ensure_ascii=False), status, batch["id"]),
        )
        self._event(
            db,
            identifier,
            action,
            "Inventaire inchangé",
            {
                "batch": batch["id"],
                "before": before,
                "edit_version": plan["edit_version"],
            },
        )

    def delete_operation(self, identifier, batch_id, index, version):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            data, batch, plan, operation = self._operation_context(
                db, identifier, batch_id, index, version
            )
            before = deepcopy(operation)
            operation["deleted"] = True
            self._save_edited_plan(
                db, identifier, batch, plan, data, "Opération supprimée du lot", before
            )

    def restore_operation(self, identifier, batch_id, index, version):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            data, batch, plan, operation = self._operation_context(
                db, identifier, batch_id, index, version, restore=True
            )
            before = deepcopy(operation)
            operation.pop("deleted", None)
            self._save_edited_plan(
                db,
                identifier,
                batch,
                plan,
                data,
                "Opération restaurée dans le lot",
                before,
            )

    def edit_operation(
        self,
        identifier,
        batch_id,
        index,
        version,
        destination=None,
        swap=None,
        transfers=None,
    ):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            data, batch, plan, operation = self._operation_context(
                db, identifier, batch_id, index, version
            )
            before = deepcopy(operation)
            if plan.get("mode") == "asset_group":
                from core.asset_groups import individual_plan

                ids = operation.get("asset_moves") or operation.get("asset_ids")
                if not ids:
                    raise ValueError(
                        "Identifiants manquants pour modifier ce déplacement."
                    )
                assets = [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM tracked_assets WHERE workspace=?", (identifier,)
                    )
                ]
                replacement = individual_plan(
                    data,
                    [ids[0]],
                    assets,
                    {ids[0]: {"destination": destination, "swap": swap}},
                )["groups"][0]
            else:
                if not transfers:
                    raise ValueError("L’opération doit contenir des déplacements.")
                parsed = [Transfer(**move) for move in transfers]
                if any(
                    t.source not in data.rooms or t.destination not in data.rooms
                    for t in parsed
                ):
                    raise ValueError("Source ou destination inconnue.")
                replacement = deepcopy(operation)
                replacement["transfers"] = [asdict(move) for move in parsed]
                destination = operation["room"]
                if destination not in {t.destination for t in parsed}:
                    destination = next(
                        (
                            t.destination
                            for t in parsed
                            if data.rooms.get(t.destination)
                            and data.rooms[t.destination].room_type == "classroom"
                        ),
                        parsed[-1].destination,
                    )
                replacement["room"] = destination
                incoming = next(
                    (t for t in parsed if t.destination == destination), parsed[-1]
                )
                replacement["source"] = incoming.source
                replacement["new_model"] = incoming.model
                outgoing = next((t for t in parsed if t.source == destination), None)
                if outgoing:
                    replacement["old_model"] = outgoing.model
                graph = build_graph(data)
                routes = [
                    shortest_route(graph, t.source, t.destination) for t in parsed
                ]
                if any(route is None for route in routes):
                    raise ValueError("Un déplacement n’a pas de trajet renseigné.")
                replacement["delivery_m"] = (
                    sum(route.distance_m for route in routes)
                    if all(route.distance_m is not None for route in routes)
                    else None
                )
                replacement["distance_type"] = " / ".join(
                    sorted({route.distance_label for route in routes})
                )
            plan["groups"][index] = replacement
            self._save_edited_plan(
                db,
                identifier,
                batch,
                plan,
                data,
                "Opération modifiée dans le lot",
                before,
            )

    def delete_batch(self, identifier, batch_id):
        """Retire un lot sans annuler les mouvements physiques déjà confirmés."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            batch = db.execute(
                "SELECT * FROM batches WHERE id=? AND workspace=?",
                (batch_id, identifier),
            ).fetchone()
            if not batch:
                raise ValueError("Ce lot n'existe plus.")
            plan = json.loads(batch["plan"])
            if plan.get("hidden"):
                raise ValueError("Ce lot a déjà été supprimé de la liste.")
            plan["hidden"] = True
            plan["edit_version"] = plan.get("edit_version", 0) + 1
            status = batch["status"]
            if status in {"Préparé", "Partiel"}:
                status = "Annulé"
            db.execute(
                "UPDATE batches SET plan=?, status=? WHERE id=? AND workspace=?",
                (json.dumps(plan, ensure_ascii=False), status, batch_id, identifier),
            )
            self._event(
                db,
                identifier,
                "Lot retiré de la liste",
                batch["name"],
                {"batch": batch_id},
            )

    def archive_batch(self, identifier, batch_id, hidden=True):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            batch = db.execute(
                "SELECT * FROM batches WHERE id=? AND workspace=?",
                (batch_id, identifier),
            ).fetchone()
            if not batch or batch["status"] not in {"Annulé", "Terminé"}:
                raise ValueError(
                    "Seul un lot annulé ou terminé peut être retiré de la liste."
                )
            plan = json.loads(batch["plan"])
            plan["hidden"] = bool(hidden)
            db.execute(
                "UPDATE batches SET plan=? WHERE id=?",
                (json.dumps(plan, ensure_ascii=False), batch_id),
            )
            self._event(
                db,
                identifier,
                "Lot retiré de la liste" if hidden else "Lot réaffiché",
                batch["name"],
                {"batch": batch_id},
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
