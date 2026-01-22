import json
from datetime import datetime
from typing import Dict, List, Optional
import logging

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from .models import Base, Domain, Fingerprint, Link, Page, PageContent, Pattern, Seed, Intelligence, Entity
from .store import PersistenceStore
from ..models.page_fingerprint import PageFingerprint


class SQLAlchemyStore(PersistenceStore):
    def __init__(self, url: str = "sqlite:///crawler.db"):
        self.engine = create_engine(url, future=True)
        self.logger = logging.getLogger(__name__)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False, future=True)
        self.PageContent = PageContent
        self.Page = Page

    def save_seed(self, query: str, entity_type: str, source: str):
        with self.Session() as s:
            s.add(Seed(query=query, entity_type=entity_type, source=source))
            s.commit()

    def get_all_pages(self) -> List[Page]:
        with self.Session() as s:
            stmt = select(Page)
            results = s.execute(stmt).scalars().all()
            return results

    def save_intelligence(self, finding: Dict, confidence: float) -> Optional[int]:
        """
        Saves verified extraction results to the database and returns the inserted row id.
        """
        try:
            with self.Session() as s:
                entity_name = finding.get("basic_info", {}).get("official_name", "Unknown Entity")
                intel_record = Intelligence(
                    entity_name=entity_name,
                    data=json.dumps(finding),
                    confidence=confidence
                )
                s.add(intel_record)
                s.commit()
                self.logger.info(f"Saved intelligence for {entity_name} (Confidence: {confidence})")
                return intel_record.id
        except Exception as e:
            self.logger.error(f"Failed to save intelligence: {e}")
            return None
    
    def get_intelligence(self, 
                           entity_name: Optional[str] = None, 
                           min_confidence: float = 0.0, 
                           limit: int = 100) -> List[Dict]:
        with self.Session() as s:
            stmt = select(Intelligence).where(Intelligence.confidence >= min_confidence)
            if entity_name:
                stmt = stmt.where(Intelligence.entity_name.ilike(f"%{entity_name}%"))
            stmt = stmt.order_by(Intelligence.confidence.desc()).limit(limit)
            results = s.execute(stmt).scalars().all()
            return [
                {
                    "id": r.id,
                    "entity": r.entity_name,
                    "confidence": r.confidence,
                    "data": json.loads(r.data),
                    "created": r.created_at.isoformat()
                } for r in results
            ]

    def search_intelligence_data(self, query: str) -> List[Dict]:
        with self.Session() as s:
            stmt = select(Intelligence).where(Intelligence.data.ilike(f"%{query}%"))
            results = s.execute(stmt).scalars().all()
            return [{"entity": r.entity_name, "data": json.loads(r.data)} for r in results]
    
    def save_page(self, page: Dict):
        with self.Session() as s:
            p = Page(
                url=page.get("url"),
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
                page_url=page.get("url"),
                html=page.get("html", ""),
                text=page.get("text_content", ""),
                metadata_json=json.dumps(page.get("metadata", {})),
                extracted_json=json.dumps(page.get("extracted", {})),
                fetch_ts=datetime.utcnow(),
            )
            s.merge(p)
            s.merge(pc)
            s.commit()

    def save_links(self, from_url: str, links: List[Dict]):
        if not links:
            return
        with self.Session() as s:
            for l in links:
                s.add(
                    Link(
                        from_url=from_url,
                        to_url=l.get("href"),
                        anchor_text=l.get("text", ""),
                        score=l.get("score", 0),
                        reason=l.get("reason", ""),
                        depth=l.get("depth", 0),
                    )
                )
            s.commit()

    def save_fingerprint(self, fp: PageFingerprint):
        with self.Session() as s:
            s.add(
                Fingerprint(
                    page_url=fp.page_url,
                    selector=fp.selector,
                    purpose=fp.purpose,
                    sample_text=fp.sample_text,
                )
            )
            s.commit()

    def save_patterns(self, patterns: List[Dict]):
        if not patterns:
            return
        with self.Session() as s:
            for p in patterns:
                s.add(
                    Pattern(
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
                        entity_type=d.get("entity_type"),
                        domain=d.get("domain"),
                        weight=d.get("weight", 0),
                        is_official=1 if d.get("is_official") else 0,
                        source=d.get("source", "code"),
                    )
                )
            s.commit()

    def save_entities(self, entities: List[Dict]) -> Dict[tuple, int]:
        """
        Merge/enrich entity nodes across pages. Entity identity: (name, kind).
        Returns mapping {(name, kind): id}.
        """
        ids = {}
        if not entities:
            return ids
        with self.Session() as s:
            for ent in entities:
                name = ent.get("name")
                kind = ent.get("kind", "entity")
                attrs = ent.get("attrs", {})
                row = (
                    s.query(Entity)
                    .filter(Entity.name == name)
                    .filter(Entity.kind == kind)
                    .one_or_none()
                )
                if row:
                    try:
                        existing = json.loads(row.data)
                    except Exception:
                        existing = {}
                    merged = {**existing, **attrs}
                    row.data = json.dumps(merged)
                    row.last_seen = datetime.utcnow()
                else:
                    row = Entity(name=name, kind=kind, data=json.dumps(attrs))
                    s.add(row)
                s.flush()
                ids[(name, kind)] = row.id
            s.commit()
        return ids

    def get_entities(self, name_like: Optional[str] = None, kind: Optional[str] = None, limit: int = 100) -> List[Dict]:
        with self.Session() as s:
            stmt = select(Entity)
            if name_like:
                stmt = stmt.where(Entity.name.ilike(f"%{name_like}%"))
            if kind:
                stmt = stmt.where(Entity.kind == kind)
            stmt = stmt.limit(limit)
            rows = s.execute(stmt).scalars().all()
            return [{"name": r.name, "kind": r.kind, "data": json.loads(r.data), "last_seen": r.last_seen.isoformat()} for r in rows]

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
            p = s.get(Page, url)
            if p:
                p.last_status = "visited"
                p.last_fetch_at = datetime.utcnow()
                s.commit()

    def has_visited(self, url: str) -> bool:
        with self.Session() as s:
            return s.get(Page, url) is not None

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
                .join(PageContent, Page.url == PageContent.page_url)
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
            stmt = select(Intelligence).where(Intelligence.entity_name.ilike(f"%{entity_name}%"))
            records = s.execute(stmt).scalars().all()
            
            aggregated = {
                "official_names": set(),
                "persons": [],
                "metrics": [],
                "financials": [],
                "products": [],
                "sources_count": len(records)
            }
            
            for r in records:
                data = json.loads(r.data)
                bi = data.get("basic_info", {})
                if bi.get("official_name"): aggregated["official_names"].add(bi["official_name"])
                
                # Deduplicate and merge lists
                for key in ["persons", "metrics", "financials", "products"]:
                    items = data.get(key, [])
                    if isinstance(items, list):
                        aggregated[key].extend(items)
            
            aggregated["official_names"] = list(aggregated["official_names"])
            return aggregated
