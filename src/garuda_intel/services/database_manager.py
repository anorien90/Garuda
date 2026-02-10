"""
Database Manager for Garuda Intel Multi-Database Support.

Handles multiple SQLite databases and their associated Qdrant vector collections:
- Database registry management (JSON-backed)
- Switching between databases
- Merging databases (SQL + Qdrant)
- Global search across all databases
- Database lifecycle (create, delete, list)
"""

import json
import os
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

from sqlalchemy import select, inspect as sa_inspect

from ..database.engine import SQLAlchemyStore
from ..database.models import (
    Base,
    BasicDataEntry,
    Entity,
    Relationship,
    Page,
    PageContent,
    Intelligence,
    Seed,
    Link,
    Fingerprint,
    Pattern,
    Domain,
    MediaItem,
    MediaContent,
)


logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manage multiple databases for the Garuda Intel application."""

    REGISTRY_FILE = "databases.json"
    DEFAULT_DB_NAME = "default"
    DEFAULT_DB_FILE = "crawler.db"
    DEFAULT_COLLECTION = "pages"

    def __init__(
        self,
        data_dir: str = "/app/data",
        qdrant_url: Optional[str] = None,
        vector_size: int = 384,
    ):
        self.data_dir = data_dir
        self.qdrant_url = qdrant_url
        self.vector_size = vector_size
        self.registry_path = os.path.join(data_dir, self.REGISTRY_FILE)

        os.makedirs(data_dir, exist_ok=True)
        self._initialize_registry()

        self.qdrant_client = None
        if qdrant_url:
            try:
                from qdrant_client import QdrantClient
                self.qdrant_client = QdrantClient(url=qdrant_url)
                logger.info("Connected to Qdrant at %s", qdrant_url)
            except Exception as exc:
                logger.warning("Could not connect to Qdrant: %s", exc)

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    def _initialize_registry(self):
        if os.path.exists(self.registry_path):
            logger.info("Loaded database registry from %s", self.registry_path)
            return
        default_db_path = os.path.join(self.data_dir, self.DEFAULT_DB_FILE)
        registry = {
            "active": self.DEFAULT_DB_NAME,
            "databases": {
                self.DEFAULT_DB_NAME: {
                    "name": self.DEFAULT_DB_NAME,
                    "db_path": default_db_path,
                    "qdrant_collection": self.DEFAULT_COLLECTION,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "description": "Default database",
                }
            },
        }
        self._save_registry(registry)
        logger.info("Created database registry at %s", self.registry_path)

    def _load_registry(self) -> Dict[str, Any]:
        with open(self.registry_path, "r") as fh:
            return json.load(fh)

    def _save_registry(self, registry: Dict[str, Any]):
        with open(self.registry_path, "w") as fh:
            json.dump(registry, fh, indent=2)

    @staticmethod
    def _sanitize_name(name: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        sanitized = re.sub(r"_+", "_", sanitized).strip("_").lower()
        return sanitized or f"db_{uuid.uuid4().hex[:8]}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_databases(self) -> List[Dict[str, Any]]:
        """Return all registered databases."""
        registry = self._load_registry()
        result = []
        for name, info in registry["databases"].items():
            entry = info.copy()
            entry["is_active"] = name == registry["active"]
            result.append(entry)
        return result

    def get_active_database(self) -> Dict[str, Any]:
        """Return the currently active database info."""
        registry = self._load_registry()
        active = registry["active"]
        if active not in registry["databases"]:
            raise ValueError(f"Active database '{active}' not in registry")
        info = registry["databases"][active].copy()
        info["is_active"] = True
        return info

    def create_database(
        self,
        name: str,
        description: str = "",
        set_active: bool = False,
    ) -> Dict[str, Any]:
        """Create a new SQLite database (and Qdrant collection) and register it."""
        sname = self._sanitize_name(name)
        registry = self._load_registry()
        if sname in registry["databases"]:
            raise ValueError(f"Database '{sname}' already exists")

        db_path = os.path.join(self.data_dir, f"{sname}.db")
        qdrant_collection = f"garuda_{sname}"

        # Create SQLite db (tables auto-created by SQLAlchemyStore)
        db_url = f"sqlite:///{db_path}"
        SQLAlchemyStore(url=db_url)
        logger.info("Created SQLite database at %s", db_path)

        # Create Qdrant collection
        if self.qdrant_client:
            try:
                from qdrant_client.http import models as qmodels
                self.qdrant_client.recreate_collection(
                    collection_name=qdrant_collection,
                    vectors_config=qmodels.VectorParams(
                        size=self.vector_size,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
                logger.info("Created Qdrant collection: %s", qdrant_collection)
            except Exception as exc:
                logger.warning("Qdrant collection creation failed: %s", exc)

        db_info: Dict[str, Any] = {
            "name": sname,
            "db_path": db_path,
            "qdrant_collection": qdrant_collection,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "description": description,
        }
        registry["databases"][sname] = db_info
        if set_active:
            registry["active"] = sname
        self._save_registry(registry)
        logger.info("Database '%s' registered (active=%s)", sname, set_active)
        return db_info

    def switch_database(self, name: str) -> Tuple[SQLAlchemyStore, str]:
        """Switch to *name* and return ``(store, qdrant_collection)``."""
        sname = self._sanitize_name(name)
        registry = self._load_registry()
        if sname not in registry["databases"]:
            raise ValueError(f"Database '{sname}' not found")
        info = registry["databases"][sname]
        store = SQLAlchemyStore(url=f"sqlite:///{info['db_path']}")
        registry["active"] = sname
        self._save_registry(registry)
        logger.info("Switched to database '%s'", sname)
        return store, info["qdrant_collection"]

    def delete_database(self, name: str, delete_files: bool = False) -> bool:
        """Remove a database from the registry (never the default or active one)."""
        sname = self._sanitize_name(name)
        registry = self._load_registry()
        if sname == self.DEFAULT_DB_NAME:
            raise ValueError("Cannot delete the default database")
        if sname not in registry["databases"]:
            raise ValueError(f"Database '{sname}' not found")
        if registry["active"] == sname:
            raise ValueError("Cannot delete the active database – switch first")

        info = registry["databases"][sname]
        if delete_files:
            path = info["db_path"]
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info("Deleted database file: %s", path)
                except OSError as exc:
                    logger.error("Failed to delete file: %s", exc)
            if self.qdrant_client:
                try:
                    self.qdrant_client.delete_collection(info["qdrant_collection"])
                    logger.info("Deleted Qdrant collection: %s", info["qdrant_collection"])
                except Exception as exc:
                    logger.error("Failed to delete Qdrant collection: %s", exc)

        del registry["databases"][sname]
        self._save_registry(registry)
        logger.info("Database '%s' deleted from registry", sname)
        return True

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def merge_databases(self, source_name: str, target_name: str) -> Dict[str, int]:
        """Merge *source_name* into *target_name* (SQL rows + Qdrant vectors)."""
        src = self._sanitize_name(source_name)
        tgt = self._sanitize_name(target_name)
        registry = self._load_registry()

        if src not in registry["databases"]:
            raise ValueError(f"Source database '{src}' not found")
        if tgt not in registry["databases"]:
            raise ValueError(f"Target database '{tgt}' not found")
        if src == tgt:
            raise ValueError("Source and target must differ")

        src_info = registry["databases"][src]
        tgt_info = registry["databases"][tgt]

        src_store = SQLAlchemyStore(url=f"sqlite:///{src_info['db_path']}")
        tgt_store = SQLAlchemyStore(url=f"sqlite:///{tgt_info['db_path']}")

        stats: Dict[str, int] = {}

        # Merge tables in dependency order (parent → child).
        tables_ordered = [
            Entity, Page, Seed, Pattern, Domain,
            Relationship, PageContent, Intelligence, Fingerprint, Link,
            MediaItem, MediaContent,
        ]

        try:
            with src_store.Session() as src_s:
                for model_cls in tables_ordered:
                    tbl = model_cls.__tablename__
                    rows = src_s.execute(select(model_cls)).scalars().all()
                    if not rows:
                        stats[tbl] = 0
                        continue

                    with tgt_store.Session() as tgt_s:
                        count = 0
                        for row in rows:
                            # Collect column values from both the child and parent mapper
                            col_vals: Dict[str, Any] = {}
                            for col in sa_inspect(model_cls).columns:
                                col_vals[col.key] = getattr(row, col.key)
                            for col in sa_inspect(BasicDataEntry).columns:
                                if col.key not in col_vals:
                                    col_vals[col.key] = getattr(row, col.key)
                            tgt_s.merge(model_cls(**col_vals))
                            count += 1
                        tgt_s.commit()
                        stats[tbl] = count
                        logger.info("Merged %d %s rows", count, tbl)

            # Merge Qdrant vectors
            stats["vector_points"] = 0
            if self.qdrant_client:
                try:
                    from qdrant_client.http import models as qmodels
                    src_col = src_info["qdrant_collection"]
                    tgt_col = tgt_info["qdrant_collection"]
                    offset = None
                    while True:
                        points, next_offset = self.qdrant_client.scroll(
                            collection_name=src_col,
                            limit=100,
                            offset=offset,
                            with_vectors=True,
                            with_payload=True,
                        )
                        if not points:
                            break
                        self.qdrant_client.upsert(
                            collection_name=tgt_col,
                            points=[
                                qmodels.PointStruct(
                                    id=str(p.id), vector=p.vector, payload=p.payload
                                )
                                for p in points
                            ],
                        )
                        stats["vector_points"] += len(points)
                        if next_offset is None:
                            break
                        offset = next_offset
                    logger.info("Merged %d vector points", stats["vector_points"])
                except Exception as exc:
                    logger.error("Error merging Qdrant vectors: %s", exc)

        except Exception as exc:
            logger.error("Merge failed: %s", exc)
            raise

        logger.info("Merge %s → %s complete: %s", src, tgt, stats)
        return stats

    # ------------------------------------------------------------------
    # Global search
    # ------------------------------------------------------------------

    def global_search(
        self,
        query: str,
        search_entities: bool = True,
        search_intelligence: bool = True,
        limit_per_db: int = 10,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Search entities / intelligence across **all** registered databases."""
        registry = self._load_registry()
        results: Dict[str, List[Dict[str, Any]]] = {}

        for db_name, db_info in registry["databases"].items():
            hits: List[Dict[str, Any]] = []
            try:
                store = SQLAlchemyStore(url=f"sqlite:///{db_info['db_path']}")
                with store.Session() as session:
                    if search_entities:
                        rows = (
                            session.execute(
                                select(Entity)
                                .where(Entity.name.ilike(f"%{query}%"))
                                .limit(limit_per_db)
                            )
                            .scalars()
                            .all()
                        )
                        for e in rows:
                            hits.append({
                                "type": "entity",
                                "database": db_name,
                                "id": str(e.id),
                                "name": e.name,
                                "kind": e.kind,
                                "data": e.data,
                                "created_at": e.created_at.isoformat() if e.created_at else None,
                            })
                    if search_intelligence:
                        rows = (
                            session.execute(
                                select(Intelligence)
                                .where(Intelligence.entity_name.ilike(f"%{query}%"))
                                .limit(limit_per_db)
                            )
                            .scalars()
                            .all()
                        )
                        for i in rows:
                            hits.append({
                                "type": "intelligence",
                                "database": db_name,
                                "id": str(i.id),
                                "entity_name": i.entity_name,
                                "entity_type": i.entity_type,
                                "confidence": i.confidence,
                                "data": i.data,
                                "created_at": i.created_at.isoformat() if i.created_at else None,
                            })
                if hits:
                    results[db_name] = hits
            except Exception as exc:
                logger.error("Error searching database '%s': %s", db_name, exc)

        return results
