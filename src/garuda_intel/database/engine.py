import json
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any

from sqlalchemy import create_engine, select, func, or_, String
from sqlalchemy.orm import sessionmaker, aliased

from .store import PersistenceStore
from .models import (
    Base,
    Page,
    PageContent,
    Seed,
    Intelligence,
    Link,
    Fingerprint,
    Pattern,
    Domain,
    Entity,
    Relationship,
)
from ..types.page.fingerprint import PageFingerprint


def _uuid5_url(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


def _uuid4() -> str:
    return str(uuid.uuid4())


def _as_dict(obj):
    if obj is None:
        return {}
    if isinstance(obj, str):
        try:
            return json.loads(obj)
        except Exception:
            return {}
    if isinstance(obj, dict):
        return obj
    return {}


class SQLAlchemyStore(PersistenceStore):
    def __init__(self, url: str = "sqlite:///crawler.db"):
        self.engine = create_engine(url, future=True)
        self.logger = logging.getLogger(__name__)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False, future=True)
        self.PageContent = PageContent
        self.Page = Page

    # -------- Seeds --------
    def save_seed(self, query: str, entity_type: str, source: str) -> str:
        with self.Session() as s:
            seed = Seed(id=_uuid4(), query=query, entity_type=entity_type, source=source)
            s.merge(seed)
            s.commit()
            return seed.id

    # -------- Pages / Content --------
    def get_all_pages(
        self,
        q: Optional[str] = None,
        entity_type: Optional[str] = None,
        page_type: Optional[str] = None,
        min_score: Optional[float] = None,
        sort: str = "fresh",
        limit: int = 200,
    ) -> List[Page]:
        q_norm = (q or "").strip().lower()
        pc = aliased(PageContent, flat=True)
        try:
            with self.Session() as s:
                stmt = select(Page).outerjoin(pc, Page.id == pc.page_id)

                conditions = []
                if q_norm:
                    like = f"%{q_norm}%"
                    conditions.append(
                        or_(
                            func.lower(Page.url).ilike(like),
                            func.lower(Page.page_type).ilike(like),
                            func.lower(Page.entity_type).ilike(like),
                            func.lower(Page.domain_key).ilike(like),
                            func.lower(Page.last_status).ilike(like),
                            func.lower(pc.text).ilike(like),
                        )
                    )
                if entity_type:
                    conditions.append(Page.entity_type == entity_type)
                if page_type:
                    conditions.append(Page.page_type == page_type)
                if min_score is not None:
                    conditions.append(Page.score >= min_score)

                if conditions:
                    stmt = stmt.where(*conditions)

                if sort == "score":
                    stmt = stmt.order_by(Page.score.desc().nullslast(), Page.last_fetch_at.desc().nullslast())
                else:
                    stmt = stmt.order_by(Page.last_fetch_at.desc().nullslast())

                stmt = stmt.limit(limit)
                results = s.execute(stmt).scalars().all()
                return results or []
        except Exception as e:
            self.logger.error(f"get_all_pages failed: {e}")
            return []

    def get_page_by_url(self, url: str) -> Optional[Dict]:
        with self.Session() as s:
            p = s.execute(select(Page).where(Page.url == url)).scalar_one_or_none()
            if not p:
                return None
            return p.to_dict()

    def get_page_content_by_url(self, url: str) -> Optional[Dict]:
        with self.Session() as s:
            page_id = s.execute(select(Page.id).where(Page.url == url)).scalar_one_or_none()
            if not page_id:
                return None
            pc = s.execute(select(PageContent).where(PageContent.page_id == page_id)).scalar_one_or_none()
            if pc:
                return {
                    "html": pc.html,
                    "text": pc.text,
                    "metadata": _as_dict(pc.metadata_json),
                    "extracted": _as_dict(pc.extracted_json),
                    "fetch_ts": pc.fetch_ts.isoformat(),
                }
            return None

    # Convenience for legacy callers
    def get_page_content(self, url: str) -> Optional[Dict]:
        return self.get_page_content_by_url(url)

    def get_page(self, url: str) -> Optional[Dict]:
        return self.get_page_by_url(url)

    def save_page(self, page: Dict) -> str:
        """
        Upsert page + content. Returns the page UUID.
        If no id is provided, a deterministic UUID5 is derived from the URL to keep Qdrant alignment stable.
        """
        url = page.get("url")
        if not url:
            raise ValueError("page url is required")
        page_id = page.get("id") or _uuid5_url(url)

        with self.Session() as s:
            p = Page(
                id=page_id,
                url=url,
                entity_type=page.get("entity_type"),
                domain_key=page.get("domain_key"),
                depth=page.get("depth"),
                score=page.get("score"),
                page_type=page.get("page_type"),
                last_status=page.get("last_status"),
                last_fetch_at=page.get("last_fetch_at"),
                text_length=page.get("text_length"),
            )
            pc = PageContent(
                id=_uuid4(),
                page_id=page_id,
                html=page.get("html", ""),
                text=page.get("text_content", ""),
                metadata_json=page.get("metadata", {}) or {},
                extracted_json=page.get("extracted", {}) or {},
                fetch_ts=page.get("last_fetch_at") or datetime.utcnow(),
            )
            s.merge(p)
            s.merge(pc)
            s.commit()
            return page_id

    # -------- Intelligence --------
    def save_intelligence(
        self,
        finding: Dict,
        confidence: float,
        page_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        Persist an intel record with optional page/entity context.
        Also wires relationships to the entity and page when present.
        """
        entity_name = entity_name or finding.get("basic_info", {}).get("official_name") or "Unknown Entity"
        entity_type = entity_type or finding.get("basic_info", {}).get("entity_type")
        data = finding.get("data", finding)  # fallback to whole finding
        with self.Session() as s:
            intel = Intelligence(
                id=_uuid4(),
                entity_id=entity_id,
                entity_name=entity_name,
                entity_type=entity_type,
                page_id=page_id,
                data=_as_dict(data),
                confidence=confidence,
            )
            s.add(intel)
            s.flush()

            # Relationships for provenance
            if entity_id:
                self._upsert_relationship(s, entity_id, intel.id, "has_intel")
            if page_id:
                self._upsert_relationship(s, page_id, intel.id, "has_intel_source")

            s.commit()
            return intel.id

    def get_intelligence(
        self,
        entity_name: Optional[str] = None,
        entity_id: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> List[Dict]:
        with self.Session() as s:
            stmt = select(Intelligence).where(Intelligence.confidence >= min_confidence)
            if entity_id:
                stmt = stmt.where(Intelligence.entity_id == entity_id)
            if entity_name:
                stmt = stmt.where(Intelligence.entity_name.ilike(f"%{entity_name}%"))
            stmt = stmt.order_by(Intelligence.created_at.desc()).limit(limit)
            rows = s.execute(stmt).scalars().all()
            return [
                {
                    "id": r.id,
                    "entity_id": r.entity_id,
                    "entity_name": r.entity_name,
                    "entity_type": r.entity_type,
                    "confidence": r.confidence,
                    "data": _as_dict(r.data),
                    "created": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    def search_intelligence_data(self, query: str) -> List[Dict]:
        with self.Session() as s:
            stmt = select(Intelligence).where(
                func.cast(Intelligence.data, String).ilike(f"%{query}%")
            )
            rows = s.execute(stmt).scalars().all()
            return [{"id": r.id, "entity_id": r.entity_id, "data": _as_dict(r.data)} for r in rows]

    # -------- Links / Relationships --------
    def save_links(self, from_url: str, links: List[Dict]):
        """
        Persist links with optional Page resolution, and avoid duplicates via DB constraint.
        """
        if not links:
            return
        with self.Session() as s:
            from_pid = self._resolve_page_id(s, from_url)
            for l in links:
                to_url = l.get("href")
                to_pid = self._resolve_page_id(s, to_url) if to_url else None
                link = Link(
                    id=_uuid4(),
                    from_url=from_url,
                    to_url=to_url,
                    from_page_id=from_pid,
                    to_page_id=to_pid,
                    anchor_text=l.get("text", ""),
                    score=l.get("score", 0),
                    reason=l.get("reason", ""),
                    depth=l.get("depth", 0),
                    relation_type="hyperlink",
                )
                s.merge(link)
            s.commit()

    def save_relationship(self, from_id: str, to_id: str, relation_type: str, meta: Optional[Dict] = None) -> Optional[str]:
        """
        Persist an explicit relationship between two entries (entities, pages, intel, etc.).
        Uses correct columns: source_id / target_id / metadata_json.
        """
        if not from_id or not to_id or not relation_type:
            return None
        with self.Session() as s:
            rel = self._upsert_relationship(s, from_id, to_id, relation_type, meta)
            s.commit()
            return str(rel.id) if rel else None

    # -------- Fingerprints --------
    def save_fingerprint(self, fp: PageFingerprint):
        page_id = fp.page_id or (fp.page_url and _uuid5_url(fp.page_url))
        if not page_id:
            raise ValueError("page_id or page_url is required for fingerprint")
        with self.Session() as s:
            s.add(
                Fingerprint(
                    id=_uuid4(),
                    page_id=page_id,
                    hash=fp.hash,
                    kind=getattr(fp, "kind", None),
                    selector=getattr(fp, "selector", None),
                    purpose=getattr(fp, "purpose", None),
                    sample_text=getattr(fp, "sample_text", None),
                    metadata_json=getattr(fp, "meta", {}) or {},
                )
            )
            s.commit()

    # -------- Patterns / Domains --------
    def save_patterns(self, patterns: List[Dict]):
        if not patterns:
            return
        with self.Session() as s:
            for p in patterns:
                s.add(
                    Pattern(
                        id=_uuid4(),
                        entity_type=p.get("entity_type"),
                        pattern=p.get("pattern"),
                        weight=p.get("weight", 0),
                        source=p.get("source", "code"),
                    )
                )
            s.commit()

    def save_domains(self, domains: List[Dict]):
        if not domains:
            return
        with self.Session() as s:
            for d in domains:
                s.add(
                    Domain(
                        id=_uuid4(),
                        entity_type=d.get("entity_type"),
                        domain=d.get("domain"),
                        weight=d.get("weight", 0),
                        is_official=1 if d.get("is_official") else 0,
                        source=d.get("source", "code"),
                    )
                )
            s.commit()

    # -------- Entities --------
    def save_entities(self, entities: List[Dict]) -> Dict[tuple, str]:
        """
        Merge/enrich entity nodes across pages. Entity identity: (name, kind).
        Returns mapping {(name, kind): id}.
        If the entity dict carries contextual ids, persist relationships:
          - page_id -> entity (relation_type="mentions_entity")
          - primary_entity_id -> entity (relation_type="related_entity" or override via entity['relation_type'])
        """
        if not entities:
            return {}
        mapping: Dict[tuple, str] = {}
        with self.Session() as s:
            for e in entities:
                name = e.get("name")
                kind = (e.get("kind") or "entity").strip().lower()
                data = _as_dict(e.get("data") or e.get("attrs"))
                meta = _as_dict(e.get("meta"))
                page_id = e.get("page_id") or e.get("source_page_id")
                primary_entity_id = e.get("primary_entity_id") or e.get("parent_entity_id")
                rel_type = e.get("relation_type") or "related_entity"

                key = (name, kind)
                existing = (
                    s.execute(select(Entity).where(Entity.name == name, Entity.kind == kind))
                    .scalar_one_or_none()
                )
                if existing:
                    existing.data = {**existing.data, **data}
                    existing.metadata_json = {**_as_dict(existing.metadata_json), **meta}
                    existing.last_seen = datetime.utcnow()
                    eid = existing.id
                else:
                    eid = _uuid4()
                    s.add(
                        Entity(
                            id=eid,
                            name=name,
                            kind=kind,
                            data=data,
                            metadata_json=meta,
                            last_seen=datetime.utcnow(),
                        )
                    )
                mapping[key] = eid

                # Wire contextual relationships if context provided
                if page_id:
                    self._upsert_relationship(s, page_id, eid, "mentions_entity")
                if primary_entity_id:
                    self._upsert_relationship(s, primary_entity_id, eid, rel_type)

            s.commit()
        return mapping

    def get_entities(self, name_like: Optional[str] = None, kind: Optional[str] = None, limit: int = 100) -> List[Dict]:
        with self.Session() as s:
            stmt = select(Entity)
            if name_like:
                stmt = stmt.where(Entity.name.ilike(f"%{name_like}%"))
            if kind:
                stmt = stmt.where(Entity.kind == kind)
            stmt = stmt.limit(limit)
            rows = s.execute(stmt).scalars().all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "kind": r.kind,
                    "data": _as_dict(r.data),
                    "meta": _as_dict(r.metadata_json),
                    "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                }
                for r in rows
            ]

    # -------- Refresh helpers --------
    def get_pending_refresh(self, limit: int = 50) -> List[Dict]:
        with self.Session() as s:
            stmt = (
                select(Page.url, Page.entity_type, Page.page_type)
                .order_by(func.coalesce(Page.last_fetch_at, datetime(1970, 1, 1)))
                .limit(limit)
            )
            rows = s.execute(stmt).all()
            return [{"url": r[0], "entity_type": r[1], "page_type": r[2]} for r in rows]

    def mark_visited(self, url: str):
        with self.Session() as s:
            p = s.execute(select(Page).where(Page.url == url)).scalar_one_or_none()
            if p:
                p.last_status = "visited"
                p.last_fetch_at = datetime.utcnow()
                s.commit()

    def has_visited(self, url: str) -> bool:
        with self.Session() as s:
            return s.execute(select(Page.id).where(Page.url == url)).scalar_one_or_none() is not None

    # -------- Text search across intel --------
    def search_intel(
        self,
        keyword: str,
        limit: int = 50,
        entity_type: Optional[str] = None,
        page_type: Optional[str] = None,
    ) -> List[Dict]:
        with self.Session() as s:
            kw_like = f"%{keyword}%"
            stmt = (
                select(
                    Page.url,
                    Page.entity_type,
                    Page.page_type,
                    Page.score,
                    func.substr(
                        PageContent.text,
                        func.max(1, func.instr(func.lower(PageContent.text), keyword.lower()) - 60),
                        200,
                    ).label("snippet"),
                )
                .join(PageContent, Page.id == PageContent.page_id)
                .where(PageContent.text.ilike(kw_like))
                .order_by(Page.score.desc().nullslast(), Page.last_fetch_at.desc().nullslast())
                .limit(limit)
            )
            if entity_type:
                stmt = stmt.where(Page.entity_type == entity_type)
            if page_type:
                stmt = stmt.where(Page.page_type == page_type)
            rows = s.execute(stmt).all()
            return [
                {
                    "url": r[0],
                    "entity_type": r[1],
                    "page_type": r[2],
                    "score": r[3],
                    "snippet": r[4],
                }
                for r in rows
            ]

    def get_aggregated_entity_data(self, entity_name: str) -> Dict[str, Any]:
        """Aggregates all Intelligence records for an entity into one JSON structure."""
        with self.Session() as s:
            stmt = select(Intelligence).where(
                func.cast(Intelligence.data, String).ilike(f"%{entity_name}%")
            )
            records = s.execute(stmt).scalars().all()

            aggregated = {
                "official_names": set(),
                "persons": [],
                "metrics": [],
                "financials": [],
                "products": [],
                "sources_count": len(records),
            }

            for r in records:
                data = _as_dict(r.data)
                bi = data.get("basic_info", {})
                if bi.get("official_name"):
                    aggregated["official_names"].add(bi["official_name"])

                for key in ["persons", "metrics", "financials", "products"]:
                    items = data.get(key, [])
                    if isinstance(items, list):
                        aggregated[key].extend(items)

            aggregated["official_names"] = list(aggregated["official_names"])
            return aggregated

    # -------- Internal helpers --------
    def _resolve_page_id(self, session, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        return session.execute(select(Page.id).where(Page.url == url)).scalar_one_or_none()

    def _upsert_relationship(self, session, from_id: str, to_id: str, relation_type: str, meta: Optional[Dict] = None) -> Optional[Relationship]:
        if not from_id or not to_id or not relation_type:
            return None
        rel = Relationship(
            id=_uuid4(),
            source_id=from_id,
            target_id=to_id,
            relation_type=relation_type,
            metadata_json=meta or {},
        )
        session.merge(rel)
        return rel
