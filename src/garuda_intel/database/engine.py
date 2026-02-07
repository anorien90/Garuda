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
from .helpers import uuid5_url as _uuid5_url, uuid4 as _uuid4, as_dict as _as_dict
from .repositories.page_repository import PageRepository


class SQLAlchemyStore(PersistenceStore):
    # Constants for graph traversal
    MAX_RECURSION_DEPTH = 10  # Maximum depth to prevent infinite loops in graph traversal
    
    def __init__(self, url: str = "sqlite:///crawler.db"):
        self.engine = create_engine(url, future=True)
        self.logger = logging.getLogger(__name__)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False, future=True)
        self.PageContent = PageContent
        self.Page = Page
        
        # Initialize repositories
        self._page_repo = PageRepository(self.Session)

    def get_session(self):
        """
        Create and return a new database session.
        
        Note: Caller is responsible for closing the session.
        Consider using 'with self.Session() as session:' context manager instead.
        
        Returns:
            SQLAlchemy session object
        """
        return self.Session()

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
        return self._page_repo.get_all_pages(q, entity_type, page_type, min_score, sort, limit)

    def get_page_by_url(self, url: str) -> Optional[Dict]:
        return self._page_repo.get_page_by_url(url)

    def get_page_content_by_url(self, url: str) -> Optional[Dict]:
        return self._page_repo.get_page_content_by_url(url)

    # Convenience for legacy callers
    def get_page_content(self, url: str) -> Optional[Dict]:
        return self._page_repo.get_page_content_by_url(url)

    def get_page(self, url: str) -> Optional[Dict]:
        return self._page_repo.get_page_by_url(url)

    def save_page(self, page: Dict) -> str:
        return self._page_repo.save_page(page)

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
        Also creates Page→Page relationships for links that have both pages resolved.
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
                
                # Create Page→Page relationship if both pages exist
                if from_pid and to_pid:
                    try:
                        link_meta = {
                            "anchor_text": l.get("text", ""),
                            "score": l.get("score", 0),
                            "depth": l.get("depth", 0),
                        }
                        self._upsert_relationship(s, from_pid, to_pid, "page_link", link_meta)
                    except Exception as e:
                        self.logger.debug(f"Failed to create page link relationship: {e}")
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
        self._page_repo.mark_visited(url)

    def has_visited(self, url: str) -> bool:
        return self._page_repo.has_visited(url)

    # -------- Text search across intel --------
    def search_intel(
        self,
        keyword: str,
        limit: int = 50,
        entity_type: Optional[str] = None,
        page_type: Optional[str] = None,
    ) -> List[Dict]:
        with self.Session() as s:
            # Use explicit alias to avoid automatic aliasing warning for overlapping tables
            # Both Page and PageContent inherit from BasicDataEntry (polymorphic inheritance)
            page_content_alias = aliased(PageContent)
            
            kw_like = f"%{keyword}%"
            stmt = (
                select(
                    Page.url,
                    Page.entity_type,
                    Page.page_type,
                    Page.score,
                    func.substr(
                        page_content_alias.text,
                        func.max(1, func.instr(func.lower(page_content_alias.text), keyword.lower()) - 60),
                        200,
                    ).label("snippet"),
                )
                .join(page_content_alias, Page.id == page_content_alias.page_id)
                .where(page_content_alias.text.ilike(kw_like))
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
        """
        Aggregates all Intelligence records for an entity into one comprehensive JSON structure.
        
        This method:
        1. Finds all entities matching the name (case-insensitive)
        2. Merges all intelligence data from all matching entities
        3. Returns a consolidated view of the entity with all information
        
        Args:
            entity_name: Name of the entity to aggregate
            
        Returns:
            Dictionary with aggregated entity information including:
            - entities: List of matching entity records
            - official_names: Set of all official names found
            - persons: Merged list of all persons
            - metrics: Merged list of all metrics
            - financials: Merged list of all financials
            - products: Merged list of all products
            - locations: Merged list of all locations
            - events: Merged list of all events
            - relationships: Merged list of all relationships
            - sources_count: Number of intelligence sources
            - pages: List of pages mentioning this entity
        """
        with self.Session() as s:
            # Find all entities matching the name (case-insensitive)
            entities = s.execute(
                select(Entity).where(
                    func.lower(Entity.name).like(f"%{entity_name.lower()}%")
                )
            ).scalars().all()
            
            if not entities:
                return {
                    "entities": [],
                    "official_names": [],
                    "persons": [],
                    "metrics": [],
                    "financials": [],
                    "products": [],
                    "locations": [],
                    "events": [],
                    "relationships": [],
                    "sources_count": 0,
                    "pages": [],
                }
            
            entity_ids = [str(e.id) for e in entities]
            
            # Get all intelligence for these entities
            stmt = select(Intelligence).where(Intelligence.entity_id.in_(entity_ids))
            records = s.execute(stmt).scalars().all()

            aggregated = {
                "entities": [
                    {
                        "id": str(e.id),
                        "name": e.name,
                        "kind": e.kind,
                        "metadata": _as_dict(e.metadata) if hasattr(e, 'metadata') else {},
                    }
                    for e in entities
                ],
                "official_names": set(),
                "persons": [],
                "metrics": [],
                "financials": [],
                "products": [],
                "locations": [],
                "events": [],
                "relationships": [],
                "sources_count": len(records),
                "pages": [],
            }

            # Track unique items by key to avoid duplicates
            seen_persons = set()
            seen_products = set()
            seen_locations = set()
            seen_events = set()
            seen_metrics = set()
            seen_financials = set()
            seen_relationships = set()
            seen_pages = set()

            for r in records:
                data = _as_dict(r.data)
                
                # Extract basic info
                bi = data.get("basic_info", {})
                if bi.get("official_name"):
                    aggregated["official_names"].add(bi["official_name"])

                # Merge persons (deduplicate by name)
                for person in data.get("persons", []):
                    if isinstance(person, dict) and person.get("name"):
                        person_key = person["name"].lower()
                        if person_key not in seen_persons:
                            seen_persons.add(person_key)
                            aggregated["persons"].append(person)

                # Merge products (deduplicate by name)
                for product in data.get("products", []):
                    if isinstance(product, dict) and product.get("name"):
                        product_key = product["name"].lower()
                        if product_key not in seen_products:
                            seen_products.add(product_key)
                            aggregated["products"].append(product)

                # Merge locations (deduplicate by address/city/country combination)
                for location in data.get("locations", []):
                    if isinstance(location, dict):
                        location_key = f"{location.get('address', '')}-{location.get('city', '')}-{location.get('country', '')}".lower()
                        if location_key not in seen_locations and location_key != "--":
                            seen_locations.add(location_key)
                            aggregated["locations"].append(location)

                # Merge events (deduplicate by title+date)
                for event in data.get("events", []):
                    if isinstance(event, dict) and event.get("title"):
                        event_key = f"{event.get('title', '')}-{event.get('date', '')}".lower()
                        if event_key not in seen_events:
                            seen_events.add(event_key)
                            aggregated["events"].append(event)

                # Merge metrics (deduplicate by metric+value)
                for metric in data.get("metrics", []):
                    if isinstance(metric, dict):
                        metric_key = f"{metric.get('metric', '')}-{metric.get('value', '')}".lower()
                        if metric_key not in seen_metrics and metric_key != "-":
                            seen_metrics.add(metric_key)
                            aggregated["metrics"].append(metric)

                # Merge financials (deduplicate by year+type)
                for financial in data.get("financials", []):
                    if isinstance(financial, dict):
                        financial_key = f"{financial.get('year', '')}-{financial.get('type', '')}".lower()
                        if financial_key not in seen_financials and financial_key != "-":
                            seen_financials.add(financial_key)
                            aggregated["financials"].append(financial)

                # Merge relationships
                for relationship in data.get("relationships", []):
                    if isinstance(relationship, dict):
                        rel_key = f"{relationship.get('entity', '')}-{relationship.get('relation', '')}".lower()
                        if rel_key not in seen_relationships and rel_key != "-":
                            seen_relationships.add(rel_key)
                            aggregated["relationships"].append(relationship)

                # Get page information
                if r.page_id:
                    page_id = str(r.page_id)
                    if page_id not in seen_pages:
                        seen_pages.add(page_id)
                        page = s.execute(select(Page).where(Page.id == r.page_id)).scalar_one_or_none()
                        if page:
                            aggregated["pages"].append({
                                "id": str(page.id),
                                "url": page.url,
                                "title": page.title if hasattr(page, 'title') else None,
                                "page_type": page.page_type if hasattr(page, 'page_type') else None,
                                "score": page.score if hasattr(page, 'score') else None,
                            })

            aggregated["official_names"] = list(aggregated["official_names"])
            return aggregated

    # -------- Internal helpers --------
    def _resolve_page_id(self, session, url: Optional[str]) -> Optional[str]:
        return self._page_repo.resolve_page_id(session, url)

    def _upsert_relationship(self, session, from_id: str, to_id: str, relation_type: str, meta: Optional[Dict] = None) -> Optional[Relationship]:
        if not from_id or not to_id or not relation_type:
            return None
        
        # Determine source and target types by querying the entries table
        from .models import BasicDataEntry
        source_type = None
        target_type = None
        
        try:
            source_entry = session.execute(
                select(BasicDataEntry.entry_type).where(BasicDataEntry.id == from_id)
            ).scalar_one_or_none()
            if source_entry:
                source_type = source_entry
                
            target_entry = session.execute(
                select(BasicDataEntry.entry_type).where(BasicDataEntry.id == to_id)
            ).scalar_one_or_none()
            if target_entry:
                target_type = target_entry
        except Exception as e:
            # If we can't determine the type, continue without it for backward compatibility
            # This allows relationships to be created even if type lookup fails
            import logging
            logging.getLogger(__name__).debug(f"Could not determine relationship types: {e}")
        
        rel = Relationship(
            id=_uuid4(),
            source_id=from_id,
            target_id=to_id,
            relation_type=relation_type,
            source_type=source_type,
            target_type=target_type,
            metadata_json=meta or {},
        )
        session.merge(rel)
        return rel

    # -------- Entity Deduplication --------
    def find_similar_entities(
        self, 
        name: str, 
        threshold: float = 0.8,
        kind: Optional[str] = None,
        embedder=None,
    ) -> List[Entity]:
        """
        Find entities similar to given name using embeddings.
        
        Args:
            name: Entity name to search for
            threshold: Similarity threshold (0-1), default 0.8
            kind: Optional entity kind filter
            embedder: Optional LLMIntelExtractor instance for embedding generation
            
        Returns:
            List of similar Entity objects
        """
        if not name:
            return []
        
        # First try exact and fuzzy matches
        with self.Session() as s:
            stmt = select(Entity).where(func.lower(Entity.name).like(f"%{name.lower()}%"))
            if kind:
                stmt = stmt.where(Entity.kind == kind)
            
            # Get potential candidates
            candidates = s.execute(stmt).scalars().all()
            
            if not embedder or not candidates:
                # Return exact/fuzzy matches if no embedder or no candidates
                # Use lower threshold (0.6) for string-based matching
                string_threshold = max(0.6, threshold - 0.2)
                return [c for c in candidates if self._name_similarity(name, c.name) >= string_threshold]
            
            # Use embedding similarity for better matching
            try:
                target_embedding = embedder.embed_text(name)
                similar = []
                
                for candidate in candidates:
                    candidate_embedding = embedder.embed_text(candidate.name)
                    similarity = embedder.calculate_similarity(target_embedding, candidate_embedding)
                    
                    if similarity >= threshold:
                        similar.append(candidate)
                
                return similar
            except Exception as e:
                self.logger.warning(f"Embedding similarity failed, using fuzzy match: {e}")
                return [c for c in candidates if self._name_similarity(name, c.name) >= threshold]

    def merge_entities(self, source_id: str, target_id: str) -> bool:
        """
        Merge source entity into target, redirecting all relationships.
        
        Args:
            source_id: Source entity UUID to merge (will be deleted)
            target_id: Target entity UUID to merge into (will be kept)
            
        Returns:
            True if merge succeeded, False otherwise
        """
        if not source_id or not target_id or source_id == target_id:
            self.logger.warning("Invalid merge: source and target must be different")
            return False
        
        try:
            with self.Session() as s:
                # Get both entities
                source = s.execute(select(Entity).where(Entity.id == source_id)).scalar_one_or_none()
                target = s.execute(select(Entity).where(Entity.id == target_id)).scalar_one_or_none()
                
                if not source or not target:
                    self.logger.error(f"Entity not found: source={source_id}, target={target_id}")
                    return False
                
                # Merge data fields - preserve non-empty values from both entities
                source_data = _as_dict(source.data)
                target_data = _as_dict(target.data)
                merged_data = {}
                
                # Field-level merging: keep non-empty values from both
                all_keys = set(source_data.keys()) | set(target_data.keys())
                for key in all_keys:
                    source_val = source_data.get(key)
                    target_val = target_data.get(key)
                    
                    # Keep non-empty value, prefer target if both non-empty
                    if target_val:
                        merged_data[key] = target_val
                    elif source_val:
                        merged_data[key] = source_val
                
                target.data = merged_data
                
                # Merge metadata
                source_meta = _as_dict(source.metadata_json)
                target_meta = _as_dict(target.metadata_json)
                merged_meta = {**source_meta, **target_meta}
                target.metadata_json = merged_meta
                
                # Update last_seen to most recent
                if source.last_seen and target.last_seen:
                    target.last_seen = max(source.last_seen, target.last_seen)
                elif source.last_seen:
                    target.last_seen = source.last_seen
                
                # Update incoming relationships (where source is target)
                for rel in s.execute(select(Relationship).where(Relationship.target_id == source_id)).scalars().all():
                    # Avoid creating duplicate relationships
                    existing = s.execute(
                        select(Relationship)
                        .where(
                            Relationship.source_id == rel.source_id,
                            Relationship.target_id == target_id,
                            Relationship.relation_type == rel.relation_type,
                        )
                    ).scalar_one_or_none()
                    
                    if not existing:
                        rel.target_id = target_id
                
                # Update outgoing relationships (where source is source)
                for rel in s.execute(select(Relationship).where(Relationship.source_id == source_id)).scalars().all():
                    existing = s.execute(
                        select(Relationship)
                        .where(
                            Relationship.source_id == target_id,
                            Relationship.target_id == rel.target_id,
                            Relationship.relation_type == rel.relation_type,
                        )
                    ).scalar_one_or_none()
                    
                    if not existing:
                        rel.source_id = target_id
                
                # Redirect Intelligence records
                for intel in s.execute(select(Intelligence).where(Intelligence.entity_id == source_id)).scalars().all():
                    intel.entity_id = target_id
                
                # Redirect Page references
                for page in s.execute(select(Page).where(Page.entity_id == source_id)).scalars().all():
                    page.entity_id = target_id
                
                # Delete source entity
                s.delete(source)
                s.commit()
                
                self.logger.info(f"Merged entity {source.name} ({source_id}) into {target.name} ({target_id})")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to merge entities: {e}")
            return False

    def resolve_entity_aliases(self, name: str, aliases: List[str], kind: Optional[str] = None) -> Optional[str]:
        """
        Match entities by aliases and return the entity ID if found.
        
        Args:
            name: Primary entity name
            aliases: List of alternative names/aliases
            kind: Optional entity kind filter
            
        Returns:
            Entity UUID if found, None otherwise
        """
        all_names = [name] + aliases
        
        with self.Session() as s:
            for alias in all_names:
                stmt = select(Entity).where(func.lower(Entity.name) == alias.lower())
                if kind:
                    stmt = stmt.where(Entity.kind == kind)
                
                entity = s.execute(stmt).scalar_one_or_none()
                if entity:
                    return str(entity.id)
        
        return None

    def get_entity_relations(
        self, 
        entity_id: str, 
        direction: str = "both", 
        max_depth: int = 1,
        include_pages: bool = True,
        include_intel: bool = True,
    ) -> Dict:
        """
        Traverse relationship graph bidirectionally with full context.
        
        This method builds a complete picture showing:
        - Entity → Pages (where entity is mentioned)
        - Page → Intel (intelligence extracted from pages)
        - Intel → Sub-Entities (persons, locations, products mentioned in intel)
        - Entity → Entity relationships (direct connections)
        
        Args:
            entity_id: Starting entity UUID
            direction: "outgoing", "incoming", or "both"
            max_depth: Maximum traversal depth (default 1)
            include_pages: Include pages connected to entities
            include_intel: Include intelligence items connected to entities/pages
            
        Returns:
            Dictionary containing:
            - entity: The root entity info
            - outgoing: List of outgoing relationships
            - incoming: List of incoming relationships
            - pages: List of pages mentioning this entity
            - intelligence: List of intelligence items about this entity
            - depth: Current depth
        """
        def _traverse(eid: str, eid_type: str, current_depth: int, visited: set) -> Dict:
            """
            Traverse from any entry (Entity, Page, or Intelligence).
            
            Args:
                eid: Entity/Page/Intelligence ID
                eid_type: Type of entry ("entity", "page", "intel")
                current_depth: Current traversal depth
                visited: Set of visited (id, type) tuples
            """
            visit_key = (eid, eid_type)
            if current_depth > max_depth or visit_key in visited:
                return {"id": eid, "type": eid_type, "depth": current_depth}
            
            visited.add(visit_key)
            
            with self.Session() as s:
                if eid_type == "entity":
                    return self._traverse_entity(s, eid, current_depth, visited, direction, include_pages, include_intel)
                elif eid_type == "page":
                    return self._traverse_page(s, eid, current_depth, visited, include_intel)
                elif eid_type == "intel":
                    return self._traverse_intel(s, eid, current_depth, visited)
                else:
                    return {"id": eid, "type": eid_type, "depth": current_depth}
        
        return _traverse(entity_id, "entity", 0, set())
    
    def _traverse_entity(self, session, entity_id: str, current_depth: int, visited: set, 
                        direction: str, include_pages: bool, include_intel: bool) -> Dict:
        """Traverse from an Entity node."""
        entity = session.execute(select(Entity).where(Entity.id == entity_id)).scalar_one_or_none()
        if not entity:
            return {"id": entity_id, "type": "entity", "depth": current_depth}
        
        result = {
            "id": str(entity.id),
            "type": "entity",
            "name": entity.name,
            "kind": entity.kind,
            "metadata": _as_dict(entity.metadata) if hasattr(entity, 'metadata') else {},
            "depth": current_depth,
            "outgoing": [],
            "incoming": [],
            "pages": [],
            "intelligence": [],
        }
        
        # Get Entity → Entity relationships
        if direction in ["outgoing", "both"]:
            outgoing = session.execute(
                select(Relationship).where(Relationship.source_id == entity_id)
            ).scalars().all()
            
            for rel in outgoing:
                target = session.execute(
                    select(Entity).where(Entity.id == rel.target_id)
                ).scalar_one_or_none()
                
                if target:
                    rel_info = {
                        "relation_type": rel.relation_type,
                        "target_id": str(rel.target_id),
                        "target_name": target.name,
                        "target_kind": target.kind,
                        "metadata": _as_dict(rel.metadata_json) if hasattr(rel, 'metadata_json') else {},
                    }
                    
                    # Recursive traversal if depth allows
                    if current_depth < max_depth:
                        visit_key = (str(rel.target_id), "entity")
                        if visit_key not in visited:
                            rel_info["nested"] = self._traverse_entity(
                                session, str(rel.target_id), current_depth + 1, visited,
                                direction, include_pages, include_intel
                            )
                    
                    result["outgoing"].append(rel_info)
        
        if direction in ["incoming", "both"]:
            incoming = session.execute(
                select(Relationship).where(Relationship.target_id == entity_id)
            ).scalars().all()
            
            for rel in incoming:
                source = session.execute(
                    select(Entity).where(Entity.id == rel.source_id)
                ).scalar_one_or_none()
                
                if source:
                    rel_info = {
                        "relation_type": rel.relation_type,
                        "source_id": str(rel.source_id),
                        "source_name": source.name,
                        "source_kind": source.kind,
                        "metadata": _as_dict(rel.metadata_json) if hasattr(rel, 'metadata_json') else {},
                    }
                    
                    # Recursive traversal if depth allows
                    if current_depth < max_depth:
                        visit_key = (str(rel.source_id), "entity")
                        if visit_key not in visited:
                            rel_info["nested"] = self._traverse_entity(
                                session, str(rel.source_id), current_depth + 1, visited,
                                direction, include_pages, include_intel
                            )
                    
                    result["incoming"].append(rel_info)
        
        # Get pages mentioning this entity
        if include_pages and current_depth < max_depth:
            # Find relationships where Page → Entity
            page_rels = session.execute(
                select(Relationship).where(
                    Relationship.target_id == entity_id,
                    Relationship.relation_type.in_(['page_mentions_entity', 'page-entity'])
                )
            ).scalars().all()
            
            for rel in page_rels:
                page = session.execute(select(Page).where(Page.id == rel.source_id)).scalar_one_or_none()
                if page:
                    page_info = {
                        "id": str(page.id),
                        "type": "page",
                        "url": page.url,
                        "title": page.title if hasattr(page, 'title') else None,
                        "page_type": page.page_type if hasattr(page, 'page_type') else None,
                        "score": page.score if hasattr(page, 'score') else None,
                    }
                    
                    # Traverse page to get its intel
                    if include_intel:
                        visit_key = (str(page.id), "page")
                        if visit_key not in visited:
                            page_info["details"] = self._traverse_page(
                                session, str(page.id), current_depth + 1, visited, include_intel
                            )
                    
                    result["pages"].append(page_info)
        
        # Get intelligence about this entity
        if include_intel:
            intel_items = session.execute(
                select(Intelligence).where(Intelligence.entity_id == entity_id)
            ).scalars().all()
            
            for intel in intel_items:
                intel_info = {
                    "id": str(intel.id),
                    "type": "intel",
                    "confidence": intel.confidence if hasattr(intel, 'confidence') else None,
                    "data": _as_dict(intel.data) if intel.data else {},
                    "page_id": str(intel.page_id) if intel.page_id else None,
                }
                
                # Extract sub-entities from intel if depth allows
                if current_depth < max_depth:
                    visit_key = (str(intel.id), "intel")
                    if visit_key not in visited:
                        intel_info["sub_entities"] = self._extract_sub_entities_from_intel(
                            session, intel, current_depth + 1, visited
                        )
                
                result["intelligence"].append(intel_info)
        
        return result
    
    def _traverse_page(self, session, page_id: str, current_depth: int, visited: set, include_intel: bool) -> Dict:
        """Traverse from a Page node."""
        page = session.execute(select(Page).where(Page.id == page_id)).scalar_one_or_none()
        if not page:
            return {"id": page_id, "type": "page", "depth": current_depth}
        
        result = {
            "id": str(page.id),
            "type": "page",
            "url": page.url,
            "title": page.title if hasattr(page, 'title') else None,
            "page_type": page.page_type if hasattr(page, 'page_type') else None,
            "depth": current_depth,
            "intelligence": [],
            "linked_pages": [],
        }
        
        # Get intelligence extracted from this page
        if include_intel:
            intel_items = session.execute(
                select(Intelligence).where(Intelligence.page_id == page_id)
            ).scalars().all()
            
            for intel in intel_items:
                intel_info = {
                    "id": str(intel.id),
                    "type": "intel",
                    "confidence": intel.confidence if hasattr(intel, 'confidence') else None,
                    "data": _as_dict(intel.data) if intel.data else {},
                }
                
                # Extract sub-entities from intel if depth allows
                if current_depth < max_depth:
                    visit_key = (str(intel.id), "intel")
                    if visit_key not in visited:
                        intel_info["sub_entities"] = self._extract_sub_entities_from_intel(
                            session, intel, current_depth + 1, visited
                        )
                
                result["intelligence"].append(intel_info)
        
        # Get links from this page to other pages
        if current_depth < max_depth:
            links = session.execute(
                select(Link).where(Link.from_page == page.url).limit(10)
            ).scalars().all()
            
            for link in links:
                linked_page = session.execute(
                    select(Page).where(Page.url == link.to_url)
                ).scalar_one_or_none()
                
                if linked_page:
                    result["linked_pages"].append({
                        "id": str(linked_page.id),
                        "url": linked_page.url,
                        "title": linked_page.title if hasattr(linked_page, 'title') else None,
                    })
        
        return result
    
    def _traverse_intel(self, session, intel_id: str, current_depth: int, visited: set) -> Dict:
        """Traverse from an Intelligence node."""
        intel = session.execute(select(Intelligence).where(Intelligence.id == intel_id)).scalar_one_or_none()
        if not intel:
            return {"id": intel_id, "type": "intel", "depth": current_depth}
        
        result = {
            "id": str(intel.id),
            "type": "intel",
            "confidence": intel.confidence if hasattr(intel, 'confidence') else None,
            "data": _as_dict(intel.data) if intel.data else {},
            "page_id": str(intel.page_id) if intel.page_id else None,
            "entity_id": str(intel.entity_id) if intel.entity_id else None,
            "depth": current_depth,
            "sub_entities": [],
        }
        
        # Extract sub-entities from intel
        if current_depth < max_depth:
            result["sub_entities"] = self._extract_sub_entities_from_intel(
                session, intel, current_depth + 1, visited
            )
        
        return result
    
    def _extract_sub_entities_from_intel(self, session, intel: Intelligence, current_depth: int, visited: set) -> List[Dict]:
        """Extract and traverse sub-entities mentioned in intelligence data."""
        sub_entities = []
        
        if not intel.data:
            return sub_entities
        
        # Process persons, products, locations, events
        for entity_type in ['persons', 'products', 'locations', 'events']:
            items = intel.data.get(entity_type, [])
            if not isinstance(items, list):
                continue
            
            for item in items:
                if not isinstance(item, dict):
                    continue
                
                # Get entity name
                entity_name = None
                if entity_type == 'persons':
                    entity_name = item.get('name')
                elif entity_type == 'products':
                    entity_name = item.get('name')
                elif entity_type == 'locations':
                    entity_name = item.get('address') or item.get('city') or item.get('country')
                elif entity_type == 'events':
                    entity_name = item.get('title')
                
                if not entity_name:
                    continue
                
                # Look up entity
                entity_kind = entity_type.rstrip('s')  # persons -> person, etc.
                entity = session.execute(
                    select(Entity).where(
                        func.lower(Entity.name) == entity_name.lower(),
                        Entity.kind == entity_kind
                    )
                ).scalar_one_or_none()
                
                if entity:
                    visit_key = (str(entity.id), "entity")
                    if visit_key not in visited and current_depth < self.MAX_RECURSION_DEPTH:
                        entity_info = {
                            "id": str(entity.id),
                            "type": "entity",
                            "name": entity.name,
                            "kind": entity.kind,
                            "data_from_intel": item,
                        }
                        sub_entities.append(entity_info)
        
        return sub_entities

    def deduplicate_entities(self, threshold: float = 0.85, embedder=None) -> Dict[str, str]:
        """
        Automatically find and merge duplicate entities.
        
        This method performs two levels of deduplication:
        1. Within-kind deduplication: Merges entities with similar names within the same kind
        2. Cross-kind deduplication: Merges generic 'entity' kind entities into more specific
           kinds (person, org, company, etc.) when they have the same name
        
        Note: This implementation has O(n²) complexity within each entity kind.
        For large datasets (>1000 entities per kind), consider implementing
        clustering-based deduplication using embeddings.
        
        Args:
            threshold: Similarity threshold for considering duplicates (0-1)
            embedder: Optional LLMIntelExtractor for embedding-based matching
            
        Returns:
            Dictionary mapping source_id -> target_id for all merged entities
        """
        merged_map = {}
        
        with self.Session() as s:
            # Get all entities grouped by kind
            entities_by_kind = {}
            all_entities = s.execute(select(Entity)).scalars().all()
            
            for entity in all_entities:
                kind = entity.kind or "unknown"
                if kind not in entities_by_kind:
                    entities_by_kind[kind] = []
                entities_by_kind[kind].append(entity)
        
        # Track which entities have been merged globally
        global_merged_ids = set()
        
        # Process each kind separately (within-kind deduplication)
        for kind, entities in entities_by_kind.items():
            self.logger.info(f"Deduplicating {len(entities)} entities of kind '{kind}'")
            
            for i, entity in enumerate(entities):
                if str(entity.id) in global_merged_ids:
                    continue
                
                # Find similar entities
                similar = self.find_similar_entities(
                    entity.name, 
                    threshold=threshold, 
                    kind=kind,
                    embedder=embedder,
                )
                
                # Merge duplicates into this entity (keep first occurrence)
                for sim_entity in similar:
                    if str(sim_entity.id) == str(entity.id):
                        continue
                    if str(sim_entity.id) in global_merged_ids:
                        continue
                    
                    # Merge sim_entity into entity
                    if self.merge_entities(str(sim_entity.id), str(entity.id)):
                        merged_map[str(sim_entity.id)] = str(entity.id)
                        global_merged_ids.add(str(sim_entity.id))
                        self.logger.info(f"Merged duplicate: {sim_entity.name} -> {entity.name}")
        
        # Cross-kind deduplication: merge generic 'entity' kind into specific kinds
        # Specific kinds that should absorb generic 'entity' duplicates
        specific_kinds = {'person', 'org', 'company', 'organization', 'product', 'location', 'event'}
        
        # Refresh entities after within-kind deduplication
        with self.Session() as s:
            all_entities = s.execute(select(Entity)).scalars().all()
            entities_by_kind = {}
            for entity in all_entities:
                kind = entity.kind or "unknown"
                if kind not in entities_by_kind:
                    entities_by_kind[kind] = []
                entities_by_kind[kind].append(entity)
        
        # Get generic entities to potentially merge
        generic_entities = entities_by_kind.get('entity', [])
        
        if generic_entities:
            self.logger.info(f"Cross-kind deduplication: checking {len(generic_entities)} generic 'entity' entities")
            
            # Build a name -> (entity, kind) lookup for specific entities
            specific_entity_by_name = {}
            for kind in specific_kinds:
                for entity in entities_by_kind.get(kind, []):
                    if str(entity.id) not in global_merged_ids:
                        name_key = entity.name.lower().strip() if entity.name else ''
                        if name_key:
                            # Prefer more specific kinds; if same name exists in multiple specific kinds,
                            # prefer person > org > company > others
                            kind_priority = {'person': 1, 'org': 2, 'organization': 2, 'company': 3, 
                                           'product': 4, 'location': 5, 'event': 6}
                            current_priority = kind_priority.get(kind, 99)
                            existing_entry = specific_entity_by_name.get(name_key)
                            if not existing_entry or kind_priority.get(existing_entry[1], 99) > current_priority:
                                specific_entity_by_name[name_key] = (entity, kind)
            
            # Merge generic entities into specific ones
            for generic_entity in generic_entities:
                if str(generic_entity.id) in global_merged_ids:
                    continue
                
                name_key = generic_entity.name.lower().strip() if generic_entity.name else ''
                if name_key and name_key in specific_entity_by_name:
                    specific_entity, specific_kind = specific_entity_by_name[name_key]
                    
                    # Merge generic into specific
                    if self.merge_entities(str(generic_entity.id), str(specific_entity.id)):
                        merged_map[str(generic_entity.id)] = str(specific_entity.id)
                        global_merged_ids.add(str(generic_entity.id))
                        self.logger.info(
                            f"Cross-kind merge: '{generic_entity.name}' (entity) -> "
                            f"'{specific_entity.name}' ({specific_kind})"
                        )
        
        self.logger.info(f"Deduplication complete: {len(merged_map)} entities merged")
        return merged_map

    def _name_similarity(self, name1: str, name2: str) -> float:
        """
        Calculate simple string similarity between two names.
        Uses basic edit distance / character overlap.
        
        Args:
            name1: First name
            name2: Second name
            
        Returns:
            Similarity score (0-1)
        """
        if not name1 or not name2:
            return 0.0
        
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()
        
        if n1 == n2:
            return 1.0
        
        # Check if one is substring of other
        if n1 in n2 or n2 in n1:
            return 0.85
        
        # Simple character overlap
        set1 = set(n1.replace(" ", ""))
        set2 = set(n2.replace(" ", ""))
        
        if not set1 or not set2:
            return 0.0
        
        overlap = len(set1 & set2)
        total = len(set1 | set2)
        
        return overlap / total if total > 0 else 0.0

    # -------- Relationship Queries (Phase 3) --------
    def get_relationship_by_entities(
        self, 
        source_id: str, 
        target_id: str, 
        relation_type: Optional[str] = None
    ) -> Optional[Relationship]:
        """
        Get relationship between two entities.
        
        Args:
            source_id: Source entity UUID
            target_id: Target entity UUID
            relation_type: Optional relation type filter
            
        Returns:
            Relationship object if found, None otherwise
        """
        try:
            with self.Session() as s:
                stmt = select(Relationship).where(
                    Relationship.source_id == source_id,
                    Relationship.target_id == target_id
                )
                if relation_type:
                    stmt = stmt.where(Relationship.relation_type == relation_type)
                
                return s.execute(stmt).scalar_one_or_none()
        except Exception as e:
            self.logger.error(f"get_relationship_by_entities failed: {e}")
            return None
    
    def get_all_relationships_for_entity(self, entity_id: str) -> List[Relationship]:
        """
        Get all relationships (incoming and outgoing) for an entity.
        
        Args:
            entity_id: Entity UUID
            
        Returns:
            List of Relationship objects
        """
        try:
            with self.Session() as s:
                outgoing = s.execute(
                    select(Relationship).where(Relationship.source_id == entity_id)
                ).scalars().all()
                
                incoming = s.execute(
                    select(Relationship).where(Relationship.target_id == entity_id)
                ).scalars().all()
                
                # Combine and deduplicate
                all_rels = list(outgoing) + list(incoming)
                seen = set()
                unique_rels = []
                for rel in all_rels:
                    if rel.id not in seen:
                        seen.add(rel.id)
                        unique_rels.append(rel)
                
                return unique_rels
        except Exception as e:
            self.logger.error(f"get_all_relationships_for_entity failed: {e}")
            return []
    
    def update_relationship_metadata(
        self, 
        relationship_id: str, 
        metadata: Dict
    ) -> bool:
        """
        Update relationship metadata including confidence score.
        
        Args:
            relationship_id: Relationship UUID
            metadata: Dictionary of metadata to merge with existing
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.Session() as s:
                rel = s.execute(
                    select(Relationship).where(Relationship.id == relationship_id)
                ).scalar_one_or_none()
                
                if not rel:
                    self.logger.warning(f"Relationship not found: {relationship_id}")
                    return False
                
                # Merge metadata
                current_meta = _as_dict(rel.metadata_json)
                updated_meta = {**current_meta, **metadata}
                rel.metadata_json = updated_meta
                
                s.commit()
                return True
        except Exception as e:
            self.logger.error(f"update_relationship_metadata failed: {e}")
            return False
    
    def delete_relationship(self, relationship_id: str) -> bool:
        """
        Delete a relationship.
        
        Args:
            relationship_id: Relationship UUID to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.Session() as s:
                rel = s.execute(
                    select(Relationship).where(Relationship.id == relationship_id)
                ).scalar_one_or_none()
                
                if not rel:
                    self.logger.warning(f"Relationship not found: {relationship_id}")
                    return False
                
                s.delete(rel)
                s.commit()
                return True
        except Exception as e:
            self.logger.error(f"delete_relationship failed: {e}")
            return False
    
    def get_entity_clusters(
        self, 
        relation_type: Optional[str] = None,
        min_cluster_size: int = 2
    ) -> List[List[str]]:
        """
        Find clusters of connected entities.
        
        Args:
            relation_type: Optional filter for specific relationship type
            min_cluster_size: Minimum number of entities in a cluster
            
        Returns:
            List of clusters, where each cluster is a list of entity UUIDs
        """
        try:
            from collections import defaultdict
            
            with self.Session() as s:
                stmt = select(Relationship)
                if relation_type:
                    stmt = stmt.where(Relationship.relation_type == relation_type)
                
                relationships = s.execute(stmt).scalars().all()
                
                # Build adjacency list (undirected graph)
                adjacency = defaultdict(set)
                all_entities = set()
                
                for rel in relationships:
                    source = str(rel.source_id)
                    target = str(rel.target_id)
                    adjacency[source].add(target)
                    adjacency[target].add(source)
                    all_entities.add(source)
                    all_entities.add(target)
                
                # Find connected components using DFS
                visited = set()
                clusters = []
                
                def dfs(node, component):
                    visited.add(node)
                    component.append(node)
                    for neighbor in adjacency.get(node, []):
                        if neighbor not in visited:
                            dfs(neighbor, component)
                
                for entity in all_entities:
                    if entity not in visited:
                        component = []
                        dfs(entity, component)
                        if len(component) >= min_cluster_size:
                            clusters.append(component)
                
                return clusters
        except Exception as e:
            self.logger.error(f"get_entity_clusters failed: {e}")
            return []
