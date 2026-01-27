"""Database hydration functions."""

from typing import List, Dict
from sqlalchemy import select
from ..database.engine import SQLAlchemyStore
from ..database.models import Intelligence, Entity


def _hydrate_intel(store: SQLAlchemyStore, ids: List[str]) -> List[Dict]:
    if not ids:
        return []
    with store.Session() as s:
        stmt = select(Intelligence).where(Intelligence.id.in_(ids))
        rows = s.execute(stmt).scalars().all()
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "entity_id": r.entity_id,
                "entity_name": r.entity_name,
                "page_id": r.page_id,
                "url": r.url,
                "confidence": r.confidence,
                "data": r.data,
                "created": r.created.isoformat() if r.created else None,
            })
        return out


def _hydrate_entities(store: SQLAlchemyStore, ids: List[str]) -> List[Dict]:
    if not ids:
        return []
    with store.Session() as s:
        stmt = select(Entity).where(Entity.id.in_(ids))
        rows = s.execute(stmt).scalars().all()
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "name": r.name,
                "entity_type": r.entity_type,
                "page_type": r.page_type,
                "description": r.description,
                "confidence": r.confidence,
                "data": r.data,
                "created": r.created.isoformat() if r.created else None,
            })
        return out
