"""
Entity Merging and Type Hierarchy Support Module.

This module provides advanced entity management capabilities:
- Entity lookup and deduplication based on name similarity
- Entity type hierarchy (e.g., Address → Headquarters)
- Merging of new data into existing entities
- Dynamic field value tracking
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Tuple

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..database.models import (
    Entity,
    Relationship,
    DynamicFieldDefinition,
    EntityFieldValue,
    FieldDiscoveryLog,
    Intelligence,
    Page,
    MediaItem,
)


# Entity type hierarchy: maps specific types to their parent types
ENTITY_TYPE_HIERARCHY = {
    "headquarters": "address",
    "branch_office": "address",
    "registered_address": "address",
    "mailing_address": "address",
    "billing_address": "address",
    "shipping_address": "address",
    "ceo": "person",
    "founder": "person",
    "executive": "person",
    "employee": "person",
    "board_member": "person",
    "subsidiary": "company",
    "parent_company": "company",
    "division": "organization",
    "department": "organization",
}

# Additional mappings for flexible type handling
# These treat similar types as equivalent for parent/child relationships
EQUIVALENT_TYPES = {
    "address": ["location"],
    "location": ["address"],
}

# Reverse mapping: parent type to list of child types
ENTITY_TYPE_CHILDREN = {}
for child, parent in ENTITY_TYPE_HIERARCHY.items():
    if parent not in ENTITY_TYPE_CHILDREN:
        ENTITY_TYPE_CHILDREN[parent] = []
    ENTITY_TYPE_CHILDREN[parent].append(child)
    # Also add children to equivalent parent types
    for equiv in EQUIVALENT_TYPES.get(parent, []):
        if equiv not in ENTITY_TYPE_CHILDREN:
            ENTITY_TYPE_CHILDREN[equiv] = []
        ENTITY_TYPE_CHILDREN[equiv].append(child)


class EntityMerger:
    """
    Handles entity merging, lookup, and type hierarchy management.
    
    This class provides intelligent entity management to avoid duplicates
    and properly track specialized entity types.
    """
    
    def __init__(self, session_maker, logger: Optional[logging.Logger] = None, vector_store=None, llm=None):
        """
        Initialize EntityMerger.
        
        Args:
            session_maker: SQLAlchemy session maker
            logger: Optional logger instance
            vector_store: Optional VectorStore instance for deep RAG entity lookups
            llm: Optional LLMIntelExtractor instance for embedding generation
        """
        self.Session = session_maker
        self.logger = logger or logging.getLogger(__name__)
        self.vector_store = vector_store
        self.llm = llm
    
    def find_existing_entity(
        self,
        name: str,
        kind: Optional[str] = None,
        fuzzy_match: bool = True,
        threshold: float = 0.9,
    ) -> Optional[Dict[str, Any]]:
        """
        Find an existing entity by name, optionally with fuzzy matching.
        
        Searches for entities that:
        1. Have exactly the same name (case-insensitive)
        2. Have a similar name if fuzzy_match is True
        3. Optionally filters by entity kind/type
        
        Args:
            name: Entity name to search for
            kind: Optional entity kind filter
            fuzzy_match: Enable fuzzy name matching
            threshold: Similarity threshold for fuzzy matching (0.0-1.0)
            
        Returns:
            Entity dict if found, None otherwise
        """
        if not name or not name.strip():
            return None
        
        name_normalized = name.strip().lower()
        
        with self.Session() as session:
            # 1. Try exact match first
            stmt = select(Entity).where(func.lower(Entity.name) == name_normalized)
            if kind:
                # Allow matching parent or child types
                matching_kinds = self._get_compatible_kinds(kind)
                stmt = stmt.where(Entity.kind.in_(matching_kinds))
            stmt = stmt.order_by(Entity.created_at)
            
            entity = session.execute(stmt).scalars().first()
            if entity:
                return self._entity_to_dict(entity)
            
            # 2. Try vector/semantic search if available
            if self.vector_store and self.llm:
                try:
                    vec = self.llm.embed_text(name)
                    if vec:
                        vector_results = self.vector_store.search(vec, top_k=5)
                        for r in vector_results:
                            entity_name = r.payload.get("entity", "")
                            if entity_name and self._calculate_name_similarity(
                                name_normalized, entity_name.lower()
                            ) >= threshold:
                                # Found a semantic match - look up the actual entity
                                vec_entity = session.execute(
                                    select(Entity).where(
                                        func.lower(Entity.name) == entity_name.lower()
                                    ).order_by(Entity.created_at)
                                ).scalars().first()
                                if vec_entity:
                                    return self._entity_to_dict(vec_entity)
                except Exception as e:
                    self.logger.debug(f"Vector entity lookup failed: {e}")
            
            # 3. Try fuzzy match if enabled
            if fuzzy_match:
                stmt = select(Entity).where(
                    func.lower(Entity.name).like(f"%{name_normalized}%")
                )
                if kind:
                    matching_kinds = self._get_compatible_kinds(kind)
                    stmt = stmt.where(Entity.kind.in_(matching_kinds))
                
                candidates = session.execute(stmt).scalars().all()
                
                for candidate in candidates:
                    similarity = self._calculate_name_similarity(name_normalized, candidate.name.lower())
                    if similarity >= threshold:
                        return self._entity_to_dict(candidate)
            
            return None
    
    def get_or_create_entity(
        self,
        name: str,
        kind: str,
        data: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        page_id: Optional[str] = None,
        source_url: Optional[str] = None,
        confidence: float = 0.5,
    ) -> Tuple[str, bool]:
        """
        Get existing entity or create a new one, with intelligent merging.
        
        This is the main entry point for entity management. It:
        1. Searches for an existing entity with the same or similar name
        2. Updates existing entity's kind if the new kind is more specific
        3. Merges new data into the existing entity
        4. Creates a new entity if no match is found
        
        Args:
            name: Entity name
            kind: Entity kind/type
            data: Entity data fields
            metadata: Entity metadata
            page_id: Source page ID for field tracking
            source_url: Source URL for provenance
            confidence: Extraction confidence score
            
        Returns:
            Tuple of (entity_id, was_created) where was_created is True if new entity
        """
        if not name or not name.strip():
            raise ValueError("Entity name is required")
        
        name = name.strip()
        kind = (kind or "entity").strip().lower()
        data = data or {}
        metadata = metadata or {}
        
        with self.Session() as session:
            # Look for existing entity
            existing = self._find_entity_in_session(session, name, kind)
            
            if existing:
                # Update existing entity
                was_updated = self._update_existing_entity(
                    session, existing, kind, data, metadata, page_id, source_url, confidence
                )
                session.commit()
                
                if was_updated:
                    self.logger.debug(f"Updated existing entity: {name} ({existing.id})")
                
                return str(existing.id), False
            else:
                # Create new entity
                entity_id = uuid.uuid4()
                new_entity = Entity(
                    id=entity_id,
                    name=name,
                    kind=kind,
                    data=data,
                    metadata_json=metadata,
                    last_seen=datetime.now(timezone.utc),
                )
                session.add(new_entity)
                
                # Track field values if data provided
                if data and page_id:
                    self._track_field_values(
                        session, entity_id, data, page_id, source_url, confidence
                    )
                
                session.commit()
                self.logger.info(f"Created new entity: {name} ({entity_id})")
                
                return str(entity_id), True
    
    def upgrade_entity_type(
        self,
        entity_id: str,
        new_kind: str,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Upgrade an entity to a more specific type if applicable.
        
        For example:
        - "entity" → "organization" (more specific)
        - "address" → "headquarters" (more specific subtype)
        - "person" → "ceo" (more specific role)
        
        Args:
            entity_id: Entity UUID
            new_kind: New entity kind to upgrade to
            reason: Optional reason for upgrade
            
        Returns:
            True if upgrade was performed, False otherwise
        """
        new_kind = new_kind.strip().lower()
        
        with self.Session() as session:
            entity = session.execute(
                select(Entity).where(Entity.id == entity_id)
            ).scalar_one_or_none()
            
            if not entity:
                return False
            
            current_kind = (entity.kind or "entity").lower()
            
            # Check if upgrade is valid
            if self._is_more_specific_type(new_kind, current_kind):
                old_kind = entity.kind
                entity.kind = new_kind
                
                # Track the upgrade in metadata - create a new dict to force SQLAlchemy to track
                new_meta = dict(entity.metadata_json) if entity.metadata_json else {}
                type_history = new_meta.get("type_history", [])
                type_history.append({
                    "from": old_kind,
                    "to": new_kind,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": reason,
                })
                new_meta["type_history"] = type_history
                entity.metadata_json = new_meta
                flag_modified(entity, 'metadata_json')
                
                session.commit()
                self.logger.info(f"Upgraded entity {entity.name} from '{old_kind}' to '{new_kind}'")
                return True
            
            return False
    
    def create_specialized_entity(
        self,
        parent_entity_id: str,
        specialized_name: str,
        specialized_kind: str,
        relationship_type: str,
        data: Optional[Dict] = None,
        page_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create a specialized entity linked to a parent entity.
        
        For example:
        - Microsoft Corporation (organization) → Microsoft Headquarters (headquarters)
        - Apple Inc. (company) → Tim Cook (ceo)
        
        Args:
            parent_entity_id: Parent entity UUID
            specialized_name: Name for the specialized entity
            specialized_kind: Kind of the specialized entity
            relationship_type: Relationship type to parent
            data: Additional data for the specialized entity
            page_id: Source page ID
            
        Returns:
            Specialized entity ID if created, None otherwise
        """
        with self.Session() as session:
            # Verify parent exists
            parent = session.execute(
                select(Entity).where(Entity.id == parent_entity_id)
            ).scalar_one_or_none()
            
            if not parent:
                self.logger.warning(f"Parent entity not found: {parent_entity_id}")
                return None
            
            # Check for existing specialized entity
            existing = self._find_entity_in_session(session, specialized_name, specialized_kind)
            
            if existing:
                # Link existing entity if not already linked
                self._ensure_relationship(
                    session, parent_entity_id, str(existing.id), relationship_type
                )
                session.commit()
                return str(existing.id)
            
            # Create new specialized entity
            entity_id = uuid.uuid4()
            new_entity = Entity(
                id=entity_id,
                name=specialized_name,
                kind=specialized_kind.lower(),
                data=data or {},
                metadata_json={
                    "parent_entity_id": str(parent_entity_id),
                    "parent_entity_name": parent.name,
                    "specialized_from": parent.kind,
                },
                last_seen=datetime.now(timezone.utc),
            )
            session.add(new_entity)
            session.flush()
            
            # Create relationship
            self._create_relationship(
                session, parent_entity_id, entity_id, relationship_type,
                meta={"page_id": page_id} if page_id else None
            )
            
            session.commit()
            self.logger.info(
                f"Created specialized entity: {specialized_name} ({specialized_kind}) "
                f"linked to {parent.name}"
            )
            
            return str(entity_id)
    
    def detect_specialized_type(
        self,
        name: str,
        context: str,
        parent_kind: str,
    ) -> Optional[str]:
        """
        Detect if an entity name/context indicates a specialized type.
        
        Args:
            name: Entity name
            context: Surrounding context text
            parent_kind: Parent entity kind
            
        Returns:
            Specialized type if detected, None otherwise
        """
        name_lower = name.lower()
        context_lower = context.lower()
        
        # Detect address specializations
        if parent_kind == "address" or parent_kind == "location":
            if any(kw in name_lower or kw in context_lower for kw in 
                   ["headquarter", "hq", "head office", "main office", "corporate office"]):
                return "headquarters"
            if any(kw in name_lower or kw in context_lower for kw in 
                   ["branch", "regional office", "local office"]):
                return "branch_office"
            if any(kw in name_lower or kw in context_lower for kw in 
                   ["registered", "legal address"]):
                return "registered_address"
        
        # Detect person role specializations
        if parent_kind == "person":
            if any(kw in name_lower or kw in context_lower for kw in 
                   ["ceo", "chief executive"]):
                return "ceo"
            if any(kw in name_lower or kw in context_lower for kw in 
                   ["founder", "co-founder", "founded by"]):
                return "founder"
            if any(kw in name_lower or kw in context_lower for kw in 
                   ["cfo", "cto", "coo", "president", "vice president", "vp", "director"]):
                return "executive"
            if any(kw in name_lower or kw in context_lower for kw in 
                   ["board member", "board of directors", "chairman"]):
                return "board_member"
        
        # Detect company/organization specializations
        if parent_kind in ["company", "organization"]:
            if any(kw in name_lower or kw in context_lower for kw in 
                   ["subsidiary", "acquired", "owned by"]):
                return "subsidiary"
            if any(kw in name_lower or kw in context_lower for kw in 
                   ["division", "unit", "segment"]):
                return "division"
            if any(kw in name_lower or kw in context_lower for kw in 
                   ["department", "dept"]):
                return "department"
        
        return None
    
    def _find_entity_in_session(
        self, session: Session, name: str, kind: Optional[str]
    ) -> Optional[Entity]:
        """Find entity within an existing session."""
        name_normalized = name.strip().lower()
        
        # Try exact name match
        stmt = select(Entity).where(func.lower(Entity.name) == name_normalized).order_by(Entity.created_at)
        entity = session.execute(stmt).scalars().first()
        
        if entity:
            return entity
        
        # Try with compatible kinds
        if kind:
            matching_kinds = self._get_compatible_kinds(kind)
            stmt = select(Entity).where(
                func.lower(Entity.name) == name_normalized,
                Entity.kind.in_(matching_kinds)
            )
            return session.execute(stmt).scalar_one_or_none()
        
        return None
    
    def _update_existing_entity(
        self,
        session: Session,
        entity: Entity,
        new_kind: str,
        data: Dict,
        metadata: Dict,
        page_id: Optional[str],
        source_url: Optional[str],
        confidence: float,
    ) -> bool:
        """Update an existing entity with new information."""
        was_updated = False
        
        # Upgrade kind if more specific
        if self._is_more_specific_type(new_kind, entity.kind or "entity"):
            entity.kind = new_kind
            was_updated = True
        
        # Merge data - keep existing values, add new ones
        if data:
            existing_data = dict(entity.data) if entity.data else {}
            for key, value in data.items():
                if value and (key not in existing_data or not existing_data[key]):
                    existing_data[key] = value
                    was_updated = True
            entity.data = existing_data
            # Mark JSON column as modified for SQLAlchemy to track
            flag_modified(entity, 'data')
            
            # Track field values
            if page_id:
                self._track_field_values(
                    session, entity.id, data, page_id, source_url, confidence
                )
        
        # Merge metadata
        if metadata:
            existing_meta = dict(entity.metadata_json) if entity.metadata_json else {}
            for key, value in metadata.items():
                if value and key not in existing_meta:
                    existing_meta[key] = value
                    was_updated = True
            entity.metadata_json = existing_meta
            flag_modified(entity, 'metadata_json')
        
        # Update last_seen
        entity.last_seen = datetime.now(timezone.utc)
        
        return was_updated
    
    def _track_field_values(
        self,
        session: Session,
        entity_id: uuid.UUID,
        data: Dict,
        page_id: str,
        source_url: Optional[str],
        confidence: float,
    ) -> None:
        """Track field values for an entity using EntityFieldValue model."""
        for field_name, value in data.items():
            if value is None:
                continue
            
            # Create field value record
            field_value = EntityFieldValue(
                id=uuid.uuid4(),
                entity_id=entity_id,
                field_name=field_name,
                confidence=confidence,
                extraction_method="llm",
                source_page_id=page_id,
                source_url=source_url,
                is_current=True,
            )
            
            # Set appropriate value column based on type
            if isinstance(value, dict):
                field_value.value_json = value
            elif isinstance(value, (int, float)):
                field_value.value_number = float(value)
            elif isinstance(value, datetime):
                field_value.value_date = value
            else:
                field_value.value_text = str(value)
            
            session.add(field_value)
    
    def _get_compatible_kinds(self, kind: str) -> List[str]:
        """Get all compatible kinds including parent and child types."""
        kind = kind.lower()
        compatible = [kind]
        
        # Add parent type
        if kind in ENTITY_TYPE_HIERARCHY:
            compatible.append(ENTITY_TYPE_HIERARCHY[kind])
        
        # Add child types
        if kind in ENTITY_TYPE_CHILDREN:
            compatible.extend(ENTITY_TYPE_CHILDREN[kind])
        
        # Add equivalent types
        if kind in EQUIVALENT_TYPES:
            compatible.extend(EQUIVALENT_TYPES[kind])
        
        # Generic fallbacks
        if kind not in ["entity", "general"]:
            compatible.append("entity")
        
        return list(set(compatible))
    
    def _is_more_specific_type(self, new_kind: str, current_kind: str) -> bool:
        """Check if new_kind is more specific than current_kind."""
        new_kind = new_kind.lower()
        current_kind = current_kind.lower()
        
        # Generic to specific
        if current_kind in ["entity", "general", ""]:
            return new_kind not in ["entity", "general", ""]
        
        # Same type
        if new_kind == current_kind:
            return False
        
        # Check hierarchy: child is more specific than parent
        if new_kind in ENTITY_TYPE_HIERARCHY:
            parent = ENTITY_TYPE_HIERARCHY[new_kind]
            if current_kind == parent:
                return True
            # Also check equivalent types of the parent
            equiv_types = EQUIVALENT_TYPES.get(parent, [])
            if current_kind in equiv_types:
                return True
        
        return False
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate simple Levenshtein-like similarity between two names."""
        if name1 == name2:
            return 1.0
        
        # Simple overlap-based similarity
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def _entity_to_dict(self, entity: Entity) -> Dict[str, Any]:
        """Convert Entity model to dictionary."""
        return {
            "id": str(entity.id),
            "name": entity.name,
            "kind": entity.kind,
            "data": entity.data or {},
            "metadata": entity.metadata_json or {},
            "last_seen": entity.last_seen.isoformat() if entity.last_seen else None,
        }
    
    def _ensure_relationship(
        self,
        session: Session,
        source_id: str,
        target_id: str,
        relation_type: str,
    ) -> None:
        """Ensure a relationship exists, create if not."""
        existing = session.execute(
            select(Relationship).where(
                Relationship.source_id == source_id,
                Relationship.target_id == target_id,
                Relationship.relation_type == relation_type,
            )
        ).scalar_one_or_none()
        
        if not existing:
            self._create_relationship(session, source_id, target_id, relation_type)
    
    def _create_relationship(
        self,
        session: Session,
        source_id,
        target_id,
        relation_type: str,
        meta: Optional[Dict] = None,
    ) -> None:
        """Create a relationship between two entities."""
        rel = Relationship(
            id=uuid.uuid4(),
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            source_type="entity",
            target_type="entity",
            metadata_json=meta or {},
        )
        session.add(rel)


class FieldDiscoveryTracker:
    """
    Tracks field discovery outcomes for adaptive learning.
    
    This class logs extraction attempts and outcomes to improve
    future extraction accuracy.
    """
    
    def __init__(self, session_maker, logger: Optional[logging.Logger] = None):
        """
        Initialize FieldDiscoveryTracker.
        
        Args:
            session_maker: SQLAlchemy session maker
            logger: Optional logger instance
        """
        self.Session = session_maker
        self.logger = logger or logging.getLogger(__name__)
    
    def log_discovery(
        self,
        field_name: str,
        entity_type: str,
        was_successful: bool,
        extraction_confidence: Optional[float] = None,
        discovery_method: str = "llm",
        extraction_method: Optional[str] = None,
        context_snippet: Optional[str] = None,
        page_id: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> str:
        """
        Log a field discovery attempt.
        
        Args:
            field_name: Name of the field being extracted
            entity_type: Type of entity being extracted from
            was_successful: Whether extraction was successful
            extraction_confidence: Confidence score of extraction
            discovery_method: Method used for discovery (llm, pattern, user)
            extraction_method: Specific extraction method used
            context_snippet: Text context used for extraction
            page_id: Source page ID
            entity_id: Target entity ID
            
        Returns:
            Discovery log ID
        """
        with self.Session() as session:
            log = FieldDiscoveryLog(
                id=uuid.uuid4(),
                field_name=field_name,
                entity_type=entity_type,
                was_successful=was_successful,
                extraction_confidence=extraction_confidence,
                discovery_method=discovery_method,
                extraction_method=extraction_method,
                context_snippet=context_snippet[:500] if context_snippet else None,
                page_id=page_id,
                entity_id=entity_id,
            )
            session.add(log)
            session.commit()
            
            return str(log.id)
    
    def get_field_success_rate(
        self,
        field_name: str,
        entity_type: Optional[str] = None,
    ) -> float:
        """
        Get the success rate for extracting a specific field.
        
        Args:
            field_name: Field name to check
            entity_type: Optional entity type filter
            
        Returns:
            Success rate between 0.0 and 1.0
        """
        with self.Session() as session:
            stmt = select(FieldDiscoveryLog).where(
                FieldDiscoveryLog.field_name == field_name
            )
            if entity_type:
                stmt = stmt.where(FieldDiscoveryLog.entity_type == entity_type)
            
            logs = session.execute(stmt).scalars().all()
            
            if not logs:
                return 0.0
            
            successful = sum(1 for log in logs if log.was_successful)
            return successful / len(logs)
    
    def update_field_definition(
        self,
        field_name: str,
        entity_type: str,
    ) -> None:
        """
        Update DynamicFieldDefinition based on discovery logs.
        
        Args:
            field_name: Field name
            entity_type: Entity type
        """
        with self.Session() as session:
            # Get or create field definition
            field_def = session.execute(
                select(DynamicFieldDefinition).where(
                    DynamicFieldDefinition.field_name == field_name,
                    DynamicFieldDefinition.entity_type == entity_type,
                )
            ).scalar_one_or_none()
            
            # Calculate stats from logs
            success_rate = self.get_field_success_rate(field_name, entity_type)
            
            if field_def:
                field_def.discovery_count += 1
                field_def.success_rate = success_rate
                field_def.last_seen_at = datetime.now(timezone.utc)
            else:
                field_def = DynamicFieldDefinition(
                    id=uuid.uuid4(),
                    field_name=field_name,
                    entity_type=entity_type,
                    discovery_count=1,
                    success_rate=success_rate,
                    source="llm",
                    is_active=True,
                    last_seen_at=datetime.now(timezone.utc),
                )
                session.add(field_def)
            
            session.commit()


class SemanticEntityDeduplicator:
    """
    Handles semantic entity deduplication using embeddings.
    
    This class identifies and merges duplicate entities based on:
    1. Semantic name similarity (e.g., "Microsoft" vs "Microsoft Corporation")
    2. Shared relationship information (e.g., both linked to "Bill Gates")
    3. Overlapping intelligence data
    """
    
    def __init__(
        self,
        session_maker,
        semantic_engine=None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize SemanticEntityDeduplicator.
        
        Args:
            session_maker: SQLAlchemy session maker
            semantic_engine: SemanticEngine instance for embeddings (optional)
            logger: Optional logger instance
        """
        self.Session = session_maker
        self.semantic_engine = semantic_engine
        self.logger = logger or logging.getLogger(__name__)
    
    def find_semantic_duplicates(
        self,
        name: str,
        kind: Optional[str] = None,
        threshold: float = 0.85,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find entities that are semantically similar to the given name.
        
        Handles cases like:
        - "Microsoft" vs "Microsoft Corporation" vs "Microsoft Corp."
        - "Bill Gates" vs "William Gates" vs "Gates, Bill"
        
        Args:
            name: Entity name to find duplicates for
            kind: Optional entity kind filter
            threshold: Minimum semantic similarity (0.0-1.0)
            max_results: Maximum number of results
            
        Returns:
            List of similar entities with similarity scores
        """
        if not name or not name.strip():
            return []
        
        name = name.strip()
        results = []
        
        with self.Session() as session:
            # Get all entities of the same kind (or all if no kind specified)
            stmt = select(Entity)
            if kind:
                # Also include compatible kinds
                compatible_kinds = self._get_compatible_kinds(kind)
                stmt = stmt.where(Entity.kind.in_(compatible_kinds))
            
            entities = session.execute(stmt).scalars().all()
            
            # Calculate similarity for each entity
            for entity in entities:
                if entity.name.lower() == name.lower():
                    # Exact match
                    results.append({
                        "entity": self._entity_to_dict(entity),
                        "similarity": 1.0,
                        "match_type": "exact",
                    })
                    continue
                
                # Calculate semantic similarity
                similarity = self._calculate_similarity(name, entity.name)
                
                if similarity >= threshold:
                    results.append({
                        "entity": self._entity_to_dict(entity),
                        "similarity": similarity,
                        "match_type": "semantic",
                    })
            
            # Sort by similarity (highest first) and limit
            results.sort(key=lambda x: x["similarity"], reverse=True)
            return results[:max_results]
    
    def find_duplicates_by_shared_relationships(
        self,
        entity_id: str,
        min_shared: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Find entities that share relationships with the given entity.
        
        This helps identify potential duplicates like:
        - "Gates" entity linked to Microsoft via "founded Microsoft" context
        - "Bill Gates" entity also linked to Microsoft
        
        Args:
            entity_id: Entity UUID to find duplicates for
            min_shared: Minimum number of shared relationships
            
        Returns:
            List of entities sharing relationships
        """
        with self.Session() as session:
            # Get the entity's relationships
            entity = session.execute(
                select(Entity).where(Entity.id == entity_id)
            ).scalar_one_or_none()
            
            if not entity:
                return []
            
            # Get all entities this one is related to
            out_rels = session.execute(
                select(Relationship).where(Relationship.source_id == entity_id)
            ).scalars().all()
            
            in_rels = session.execute(
                select(Relationship).where(Relationship.target_id == entity_id)
            ).scalars().all()
            
            related_ids = set()
            for rel in out_rels:
                related_ids.add(str(rel.target_id))
            for rel in in_rels:
                related_ids.add(str(rel.source_id))
            
            if not related_ids:
                return []
            
            # Find other entities that share these relationships
            candidates = {}
            
            for related_id in related_ids:
                # Find other entities connected to this same related entity
                other_out = session.execute(
                    select(Relationship).where(
                        Relationship.target_id == related_id,
                        Relationship.source_id != entity_id,
                    )
                ).scalars().all()
                
                other_in = session.execute(
                    select(Relationship).where(
                        Relationship.source_id == related_id,
                        Relationship.target_id != entity_id,
                    )
                ).scalars().all()
                
                for rel in other_out:
                    src_id = str(rel.source_id)
                    if src_id not in candidates:
                        candidates[src_id] = {"shared_targets": set(), "shared_sources": set()}
                    candidates[src_id]["shared_targets"].add(related_id)
                
                for rel in other_in:
                    tgt_id = str(rel.target_id)
                    if tgt_id not in candidates:
                        candidates[tgt_id] = {"shared_targets": set(), "shared_sources": set()}
                    candidates[tgt_id]["shared_sources"].add(related_id)
            
            # Filter to entities with enough shared relationships
            results = []
            for cand_id, shared in candidates.items():
                total_shared = len(shared["shared_targets"]) + len(shared["shared_sources"])
                if total_shared >= min_shared:
                    cand_entity = session.execute(
                        select(Entity).where(Entity.id == cand_id)
                    ).scalar_one_or_none()
                    
                    if cand_entity:
                        # Also check name similarity
                        name_similarity = self._calculate_similarity(entity.name, cand_entity.name)
                        
                        results.append({
                            "entity": self._entity_to_dict(cand_entity),
                            "shared_relationships": total_shared,
                            "name_similarity": name_similarity,
                            "shared_targets": list(shared["shared_targets"]),
                            "shared_sources": list(shared["shared_sources"]),
                        })
            
            # Sort by shared relationships + name similarity
            results.sort(key=lambda x: (x["shared_relationships"], x["name_similarity"]), reverse=True)
            return results
    
    def deduplicate_entities(
        self,
        dry_run: bool = True,
        threshold: float = 0.9,
        kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Find and optionally merge duplicate entities across the database.
        
        Ensures that during deduplication:
        - No entities are lost: all data is merged into the canonical entity
        - The entity with the most specific kind wins (e.g., founder > person > entity)
        - The richest data and longest name are preserved
        
        Args:
            dry_run: If True, only report duplicates without merging
            threshold: Minimum similarity threshold for merging
            kind: Optional entity kind to limit deduplication
            
        Returns:
            Report with found duplicates and merge actions
        """
        report = {
            "duplicates_found": [],
            "merged": [],
            "errors": [],
        }
        
        with self.Session() as session:
            stmt = select(Entity)
            if kind:
                stmt = stmt.where(Entity.kind == kind)
            stmt = stmt.order_by(Entity.created_at)
            
            entities = session.execute(stmt).scalars().all()
            processed_ids = set()
            
            for entity in entities:
                if str(entity.id) in processed_ids:
                    continue
                
                # Find duplicates for this entity
                duplicates = self.find_semantic_duplicates(
                    entity.name,
                    kind=entity.kind,
                    threshold=threshold,
                )
                
                # Filter out self and already processed
                duplicates = [
                    d for d in duplicates
                    if d["entity"]["id"] != str(entity.id) and d["entity"]["id"] not in processed_ids
                ]
                
                if duplicates:
                    # Collect all entities in this duplicate group (current + duplicates)
                    all_group_ids = [str(entity.id)] + [d["entity"]["id"] for d in duplicates]
                    all_group_entities = [
                        e for e in entities if str(e.id) in all_group_ids
                    ]
                    
                    # Select the best canonical entity (highest kind, richest data, longest name)
                    canonical = self._select_canonical_entity(all_group_entities) if all_group_entities else entity
                    canonical_id = str(canonical.id)
                    
                    group = {
                        "canonical": self._entity_to_dict(canonical),
                        "duplicates": [
                            d for d in duplicates if d["entity"]["id"] != canonical_id
                        ],
                    }
                    # Include the original entity as a duplicate if it's not the canonical
                    if canonical_id != str(entity.id):
                        group["duplicates"].append({
                            "entity": self._entity_to_dict(entity),
                            "similarity": 1.0,
                            "match_type": "group_member",
                        })
                    report["duplicates_found"].append(group)
                    
                    # Mark all as processed
                    processed_ids.add(str(entity.id))
                    processed_ids.add(canonical_id)
                    for dup in duplicates:
                        processed_ids.add(dup["entity"]["id"])
                    
                    # Merge if not dry run
                    if not dry_run:
                        for dup in group["duplicates"]:
                            try:
                                self._merge_entities(session, dup["entity"]["id"], canonical_id)
                                report["merged"].append({
                                    "source": dup["entity"]["name"],
                                    "target": canonical.name,
                                    "similarity": dup["similarity"],
                                })
                            except Exception as e:
                                report["errors"].append({
                                    "source": dup["entity"]["name"],
                                    "error": str(e),
                                })
            
            if not dry_run:
                session.commit()
        
        return report
    
    def merge_entities(self, source_id: str, target_id: str) -> bool:
        """
        Merge source entity into target entity (public API).
        
        The source entity will be deleted and its data/relationships
        will be merged into the target entity.
        
        Args:
            source_id: Source entity UUID (will be deleted)
            target_id: Target entity UUID (will be kept)
            
        Returns:
            True if merge succeeded, False otherwise
        """
        with self.Session() as session:
            success = self._merge_entities(session, source_id, target_id)
            if success:
                session.commit()
            return success
    
    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two entity names."""
        if not name1 or not name2:
            return 0.0
        
        name1 = name1.lower().strip()
        name2 = name2.lower().strip()
        
        if name1 == name2:
            return 1.0
        
        # Try embedding similarity if semantic engine is available
        if self.semantic_engine:
            try:
                emb1 = self.semantic_engine.embed_text(name1)
                emb2 = self.semantic_engine.embed_text(name2)
                if emb1 and emb2:
                    return self.semantic_engine.calculate_similarity(emb1, emb2)
            except Exception as e:
                self.logger.debug(f"Embedding similarity failed: {e}")
        
        # Fall back to word-overlap similarity
        return self._word_overlap_similarity(name1, name2)
    
    def _word_overlap_similarity(self, name1: str, name2: str) -> float:
        """Calculate word-overlap (Jaccard) similarity."""
        # Normalize common abbreviations
        name1 = self._normalize_name(name1)
        name2 = self._normalize_name(name2)
        
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def _normalize_name(self, name: str) -> str:
        """Normalize entity name for comparison."""
        name = name.lower().strip()
        
        # Common abbreviation expansions
        replacements = {
            " corp.": " corporation",
            " corp": " corporation",
            " inc.": " incorporated",
            " inc": " incorporated",
            " ltd.": " limited",
            " ltd": " limited",
            " llc": " limited liability company",
            " co.": " company",
            " co": " company",
        }
        
        for abbrev, full in replacements.items():
            name = name.replace(abbrev, full)
        
        return name
    
    def _get_compatible_kinds(self, kind: str) -> List[str]:
        """Get compatible entity kinds including type hierarchy.
        
        Ensures that generic types (entity, general) can match any kind,
        and all types can match the generic fallbacks.
        """
        kind = kind.lower()
        compatible = [kind]
        
        # Add parent type
        if kind in ENTITY_TYPE_HIERARCHY:
            compatible.append(ENTITY_TYPE_HIERARCHY[kind])
        
        # Add child types
        if kind in ENTITY_TYPE_CHILDREN:
            compatible.extend(ENTITY_TYPE_CHILDREN[kind])
        
        # Add equivalent types
        if kind in EQUIVALENT_TYPES:
            compatible.extend(EQUIVALENT_TYPES[kind])
        
        # Generic fallbacks: "entity"/"general" should match any kind, 
        # and non-generic types should also match "entity"/"general"
        if kind not in ("entity", "general"):
            compatible.extend(["entity", "general"])
        else:
            # Generic types match all parent and child types
            compatible.extend(ENTITY_TYPE_HIERARCHY.keys())
            compatible.extend(ENTITY_TYPE_CHILDREN.keys())
        
        return list(set(compatible))
    
    def _entity_to_dict(self, entity: Entity) -> Dict[str, Any]:
        """Convert Entity model to dictionary."""
        return {
            "id": str(entity.id),
            "name": entity.name,
            "kind": entity.kind,
            "data": entity.data or {},
            "metadata": entity.metadata_json or {},
            "last_seen": entity.last_seen.isoformat() if entity.last_seen else None,
        }
    
    def _get_kind_specificity_rank(self, kind: str) -> int:
        """Return a numeric rank for entity kind specificity.
        
        Higher rank means more specific:
        - 0: generic types (entity, general, empty)
        - 1: parent types (person, address, company, organization)
        - 2: specialized child types (ceo, founder, headquarters, etc.)
        """
        kind = (kind or "").lower().strip()
        if kind in ("", "entity", "general"):
            return 0
        if kind in ENTITY_TYPE_HIERARCHY:
            return 2  # child/specialized types
        if kind in ENTITY_TYPE_CHILDREN:
            return 1  # parent types
        return 1  # any other concrete type
    
    def _select_canonical_entity(self, entities: List[Entity]) -> Entity:
        """Select the best canonical entity from a group of duplicates.
        
        Selection criteria (in priority order):
        1. Highest kind specificity (e.g., founder > person > entity)
        2. Richest data (most non-empty data fields)
        3. Longest name (more complete name likely contains more info)
        
        This ensures that no entity data is lost during deduplication:
        the entity with the most specific type and richest data wins.
        """
        def entity_score(e: Entity):
            kind_rank = self._get_kind_specificity_rank((e.kind or "").lower())
            data_count = len(e.data) if e.data else 0
            name_len = len(e.name.strip()) if e.name else 0
            return (kind_rank, data_count, name_len)
        
        return max(entities, key=entity_score)
    
    def _merge_entities(self, session: Session, source_id: str, target_id: str) -> bool:
        """Merge source entity into target entity.
        
        Ensures:
        - The most specific kind (highest in hierarchy) is preserved
        - The richest name (longest) is preserved
        - All data fields are merged (source fills gaps in target)
        - All relationships are transferred to target
        - All associated records (Intelligence, Page, MediaItem, etc.) are transferred
        - Self-referential relationships are removed
        - Duplicate relationships are deduplicated
        """
        source = session.execute(
            select(Entity).where(Entity.id == source_id)
        ).scalar_one_or_none()
        
        target = session.execute(
            select(Entity).where(Entity.id == target_id)
        ).scalar_one_or_none()
        
        if not source or not target:
            return False
        
        # Upgrade kind: keep the most specific type
        source_kind = (source.kind or "entity").lower()
        target_kind = (target.kind or "entity").lower()
        if self._get_kind_specificity_rank(source_kind) > self._get_kind_specificity_rank(target_kind):
            target.kind = source_kind
        
        # Pick the richest name (longest, as it likely contains the most info)
        if source.name and target.name and len(source.name.strip()) > len(target.name.strip()):
            target.name = source.name.strip()
        
        # Merge data
        source_data = source.data or {}
        target_data = target.data or {}
        for key, value in source_data.items():
            if value and (key not in target_data or not target_data.get(key)):
                target_data[key] = value
        target.data = target_data
        flag_modified(target, 'data')
        
        # Merge metadata_json (source fills gaps in target)
        source_metadata = source.metadata_json or {}
        target_metadata = target.metadata_json or {}
        for key, value in source_metadata.items():
            if key != "merged_from" and value and not target_metadata.get(key):
                target_metadata[key] = value
        target.metadata_json = target_metadata
        flag_modified(target, 'metadata_json')
        
        # Transfer EntityFieldValue records
        for field_value in session.execute(
            select(EntityFieldValue).where(EntityFieldValue.entity_id == source_id)
        ).scalars().all():
            field_value.entity_id = target_id
        
        # Transfer Intelligence records
        for intel in session.execute(
            select(Intelligence).where(Intelligence.entity_id == source_id)
        ).scalars().all():
            intel.entity_id = target_id
        
        # Transfer Page references
        for page in session.execute(
            select(Page).where(Page.entity_id == source_id)
        ).scalars().all():
            page.entity_id = target_id
        
        # Transfer MediaItem references
        for media_item in session.execute(
            select(MediaItem).where(MediaItem.entity_id == source_id)
        ).scalars().all():
            media_item.entity_id = target_id
        
        # Transfer FieldDiscoveryLog references
        for log in session.execute(
            select(FieldDiscoveryLog).where(FieldDiscoveryLog.entity_id == source_id)
        ).scalars().all():
            log.entity_id = target_id
        
        # Redirect relationships
        for rel in session.execute(
            select(Relationship).where(Relationship.source_id == source_id)
        ).scalars().all():
            rel.source_id = target_id
        
        for rel in session.execute(
            select(Relationship).where(Relationship.target_id == source_id)
        ).scalars().all():
            rel.target_id = target_id
        
        # CRITICAL: Flush to persist relationship redirects BEFORE deleting source entity
        # This prevents CASCADE delete from wiping relationships
        session.flush()
        
        # Remove self-referential relationships (where source == target after redirect)
        self_refs = session.execute(
            select(Relationship).where(
                Relationship.source_id == target_id,
                Relationship.target_id == target_id
            )
        ).scalars().all()
        for rel in self_refs:
            session.delete(rel)
        
        # Deduplicate relationships: keep only one for each (source_id, target_id, relation_type)
        all_rels = session.execute(
            select(Relationship).where(
                (Relationship.source_id == target_id) | (Relationship.target_id == target_id)
            )
        ).scalars().all()
        
        # Group by (source_id, target_id, relation_type)
        rel_groups: Dict[Tuple[str, str, str], List[Relationship]] = {}
        for rel in all_rels:
            key = (str(rel.source_id), str(rel.target_id), rel.relation_type or "")
            if key not in rel_groups:
                rel_groups[key] = []
            rel_groups[key].append(rel)
        
        # For each group with duplicates, keep only one (sorted by id for stability)
        for key, rels in rel_groups.items():
            if len(rels) > 1:
                rels_sorted = sorted(rels, key=lambda r: str(r.id))
                for rel in rels_sorted[1:]:
                    session.delete(rel)
        
        # Record merge in metadata
        merge_history = target.metadata_json.get("merged_from", []) if target.metadata_json else []
        merge_history.append({
            "id": source_id,
            "name": source.name,
            "kind": source_kind,
            "merged_at": datetime.now(timezone.utc).isoformat(),
        })
        if target.metadata_json is None:
            target.metadata_json = {}
        target.metadata_json["merged_from"] = merge_history
        flag_modified(target, 'metadata_json')
        
        # Delete source
        session.delete(source)
        
        self.logger.info(f"Merged entity '{source.name}' ({source_kind}) into '{target.name}' ({target.kind})")
        return True


class GraphSearchEngine:
    """
    Provides depth-based graph traversal with semantic and SQL hybrid search.
    
    Enables searching for entities with:
    1. SQL exact matches
    2. Semantic embedding similarity
    3. Depth-based relationship traversal (top X relations per depth)
    """
    
    def __init__(
        self,
        session_maker,
        semantic_engine=None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize GraphSearchEngine.
        
        Args:
            session_maker: SQLAlchemy session maker
            semantic_engine: SemanticEngine instance for embeddings (optional)
            logger: Optional logger instance
        """
        self.Session = session_maker
        self.semantic_engine = semantic_engine
        self.logger = logger or logging.getLogger(__name__)
    
    def search_entities(
        self,
        query: str,
        kind: Optional[str] = None,
        semantic_threshold: float = 0.7,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search for entities using hybrid SQL + semantic search.
        
        Args:
            query: Search query string
            kind: Optional entity kind filter
            semantic_threshold: Minimum semantic similarity for semantic matches
            limit: Maximum results
            
        Returns:
            List of matching entities with match type and scores
        """
        results = []
        seen_ids = set()
        
        with self.Session() as session:
            # 1. SQL exact matches (name contains query)
            stmt = select(Entity).where(
                func.lower(Entity.name).like(f"%{query.lower()}%")
            )
            if kind:
                stmt = stmt.where(Entity.kind == kind)
            
            sql_matches = session.execute(stmt.limit(limit)).scalars().all()
            
            for entity in sql_matches:
                if str(entity.id) not in seen_ids:
                    seen_ids.add(str(entity.id))
                    results.append({
                        "entity": self._entity_to_dict(entity),
                        "match_type": "sql_exact",
                        "score": 1.0,
                    })
            
            # 2. Semantic search (if semantic engine available)
            if self.semantic_engine and len(results) < limit:
                try:
                    query_embedding = self.semantic_engine.embed_text(query)
                    
                    if query_embedding:
                        # Get remaining entities for semantic comparison
                        remaining = limit - len(results)
                        stmt = select(Entity)
                        if kind:
                            stmt = stmt.where(Entity.kind == kind)
                        
                        all_entities = session.execute(stmt).scalars().all()
                        
                        semantic_matches = []
                        for entity in all_entities:
                            if str(entity.id) in seen_ids:
                                continue
                            
                            # Calculate semantic similarity
                            name_embedding = self.semantic_engine.embed_text(entity.name)
                            if name_embedding:
                                similarity = self.semantic_engine.calculate_similarity(
                                    query_embedding, name_embedding
                                )
                                if similarity >= semantic_threshold:
                                    semantic_matches.append((entity, similarity))
                        
                        # Sort by similarity and take top remaining
                        semantic_matches.sort(key=lambda x: x[1], reverse=True)
                        for entity, similarity in semantic_matches[:remaining]:
                            seen_ids.add(str(entity.id))
                            results.append({
                                "entity": self._entity_to_dict(entity),
                                "match_type": "semantic",
                                "score": similarity,
                            })
                
                except Exception as e:
                    self.logger.warning(f"Semantic search failed: {e}")
            
            return results
    
    def traverse_graph(
        self,
        entity_ids: List[str],
        max_depth: int = 2,
        top_n_per_depth: int = 10,
        relation_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Traverse the graph from starting entities with depth-limited BFS.
        
        At each depth level, returns the top N most connected entities.
        
        Args:
            entity_ids: Starting entity UUIDs
            max_depth: Maximum traversal depth
            top_n_per_depth: Number of top entities to return per depth level
            relation_types: Optional filter for relationship types
            
        Returns:
            Graph structure with entities and relationships at each depth
        """
        result = {
            "root_entities": [],
            "depths": {},
            "all_relationships": [],
        }
        
        with self.Session() as session:
            # Get root entities
            for eid in entity_ids:
                entity = session.execute(
                    select(Entity).where(Entity.id == eid)
                ).scalar_one_or_none()
                if entity:
                    result["root_entities"].append(self._entity_to_dict(entity))
            
            visited_ids = set(entity_ids)
            current_level_ids = set(entity_ids)
            
            for depth in range(1, max_depth + 1):
                next_level_entities = []
                depth_relationships = []
                
                for eid in current_level_ids:
                    # Get outgoing relationships
                    out_stmt = select(Relationship).where(Relationship.source_id == eid)
                    if relation_types:
                        out_stmt = out_stmt.where(Relationship.relation_type.in_(relation_types))
                    
                    out_rels = session.execute(out_stmt).scalars().all()
                    
                    for rel in out_rels:
                        target_id = str(rel.target_id)
                        if target_id not in visited_ids:
                            target = session.execute(
                                select(Entity).where(Entity.id == rel.target_id)
                            ).scalar_one_or_none()
                            
                            if target:
                                next_level_entities.append({
                                    "entity": self._entity_to_dict(target),
                                    "from_entity_id": eid,
                                    "relation_type": rel.relation_type,
                                    "direction": "outgoing",
                                })
                        
                        depth_relationships.append({
                            "source_id": eid,
                            "target_id": target_id,
                            "relation_type": rel.relation_type,
                            "metadata": rel.metadata_json,
                        })
                    
                    # Get incoming relationships
                    in_stmt = select(Relationship).where(Relationship.target_id == eid)
                    if relation_types:
                        in_stmt = in_stmt.where(Relationship.relation_type.in_(relation_types))
                    
                    in_rels = session.execute(in_stmt).scalars().all()
                    
                    for rel in in_rels:
                        source_id = str(rel.source_id)
                        if source_id not in visited_ids:
                            source = session.execute(
                                select(Entity).where(Entity.id == rel.source_id)
                            ).scalar_one_or_none()
                            
                            if source:
                                next_level_entities.append({
                                    "entity": self._entity_to_dict(source),
                                    "from_entity_id": eid,
                                    "relation_type": rel.relation_type,
                                    "direction": "incoming",
                                })
                        
                        depth_relationships.append({
                            "source_id": source_id,
                            "target_id": eid,
                            "relation_type": rel.relation_type,
                            "metadata": rel.metadata_json,
                        })
                
                # Deduplicate and rank entities by connection count
                entity_counts = {}
                for item in next_level_entities:
                    eid = item["entity"]["id"]
                    if eid not in entity_counts:
                        entity_counts[eid] = {"item": item, "count": 0}
                    entity_counts[eid]["count"] += 1
                
                # Take top N by connection count
                sorted_entities = sorted(
                    entity_counts.values(),
                    key=lambda x: x["count"],
                    reverse=True,
                )[:top_n_per_depth]
                
                # Update for next level
                current_level_ids = set()
                depth_entities = []
                for entry in sorted_entities:
                    eid = entry["item"]["entity"]["id"]
                    visited_ids.add(eid)
                    current_level_ids.add(eid)
                    depth_entities.append({
                        **entry["item"],
                        "connection_count": entry["count"],
                    })
                
                result["depths"][depth] = {
                    "entities": depth_entities,
                    "entity_count": len(depth_entities),
                }
                result["all_relationships"].extend(depth_relationships)
                
                if not current_level_ids:
                    break
        
        return result
    
    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Find the shortest path between two entities.
        
        Args:
            source_id: Source entity UUID
            target_id: Target entity UUID
            max_depth: Maximum path length
            
        Returns:
            List of path steps (entities and relationships), or None if no path
        """
        if source_id == target_id:
            with self.Session() as session:
                entity = session.execute(
                    select(Entity).where(Entity.id == source_id)
                ).scalar_one_or_none()
                if entity:
                    return [{"entity": self._entity_to_dict(entity), "relationship": None}]
            return None
        
        # BFS to find shortest path
        with self.Session() as session:
            visited = {source_id: None}  # Maps entity_id to (prev_id, relationship)
            queue = [source_id]
            
            for _ in range(max_depth):
                next_queue = []
                
                for current_id in queue:
                    # Get all connected entities
                    out_rels = session.execute(
                        select(Relationship).where(Relationship.source_id == current_id)
                    ).scalars().all()
                    
                    in_rels = session.execute(
                        select(Relationship).where(Relationship.target_id == current_id)
                    ).scalars().all()
                    
                    for rel in out_rels:
                        neighbor_id = str(rel.target_id)
                        if neighbor_id not in visited:
                            visited[neighbor_id] = (current_id, rel.relation_type, "outgoing")
                            next_queue.append(neighbor_id)
                            
                            if neighbor_id == target_id:
                                # Found path, reconstruct it
                                return self._reconstruct_path(session, visited, source_id, target_id)
                    
                    for rel in in_rels:
                        neighbor_id = str(rel.source_id)
                        if neighbor_id not in visited:
                            visited[neighbor_id] = (current_id, rel.relation_type, "incoming")
                            next_queue.append(neighbor_id)
                            
                            if neighbor_id == target_id:
                                return self._reconstruct_path(session, visited, source_id, target_id)
                
                queue = next_queue
                if not queue:
                    break
        
        return None
    
    def _reconstruct_path(
        self,
        session: Session,
        visited: Dict,
        source_id: str,
        target_id: str,
    ) -> List[Dict[str, Any]]:
        """Reconstruct path from visited dictionary."""
        path = []
        current = target_id
        
        while current != source_id:
            prev_id, rel_type, direction = visited[current]
            
            entity = session.execute(
                select(Entity).where(Entity.id == current)
            ).scalar_one_or_none()
            
            if entity:
                path.append({
                    "entity": self._entity_to_dict(entity),
                    "relationship": {
                        "type": rel_type,
                        "direction": direction,
                        "from_id": prev_id,
                    },
                })
            
            current = prev_id
        
        # Add source entity
        source_entity = session.execute(
            select(Entity).where(Entity.id == source_id)
        ).scalar_one_or_none()
        if source_entity:
            path.append({
                "entity": self._entity_to_dict(source_entity),
                "relationship": None,
            })
        
        path.reverse()
        return path
    
    def _entity_to_dict(self, entity: Entity) -> Dict[str, Any]:
        """Convert Entity model to dictionary."""
        return {
            "id": str(entity.id),
            "name": entity.name,
            "kind": entity.kind,
            "data": entity.data or {},
            "metadata": entity.metadata_json or {},
        }


class RelationshipConfidenceManager:
    """
    Manages relationship confidence scores.
    
    When a relationship is found multiple times, its confidence increases.
    """
    
    def __init__(self, session_maker, logger: Optional[logging.Logger] = None):
        """
        Initialize RelationshipConfidenceManager.
        
        Args:
            session_maker: SQLAlchemy session maker
            logger: Optional logger instance
        """
        self.Session = session_maker
        self.logger = logger or logging.getLogger(__name__)
    
    def record_relationship(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        source_url: Optional[str] = None,
        confidence_boost: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Record a relationship occurrence, boosting confidence if already exists.
        
        Args:
            source_id: Source entity UUID
            target_id: Target entity UUID
            relation_type: Type of relationship
            source_url: Source URL where relationship was found
            confidence_boost: How much to increase confidence per occurrence
            
        Returns:
            Relationship info with current confidence
        """
        with self.Session() as session:
            # Check if relationship exists
            existing = session.execute(
                select(Relationship).where(
                    Relationship.source_id == source_id,
                    Relationship.target_id == target_id,
                    Relationship.relation_type == relation_type,
                )
            ).scalar_one_or_none()
            
            if existing:
                # Boost confidence
                meta = dict(existing.metadata_json) if existing.metadata_json else {}
                current_confidence = meta.get("confidence", 0.5)
                occurrence_count = meta.get("occurrence_count", 1)
                
                # Apply diminishing returns: boost decreases as confidence approaches 1.0
                # This ensures repeated observations increase confidence but can never exceed 1.0
                new_confidence = min(1.0, current_confidence + confidence_boost * (1 - current_confidence))
                
                meta["confidence"] = new_confidence
                meta["occurrence_count"] = occurrence_count + 1
                meta["last_seen"] = datetime.now(timezone.utc).isoformat()
                
                # Track sources
                sources = meta.get("sources", [])
                if source_url and source_url not in sources:
                    sources.append(source_url)
                meta["sources"] = sources
                
                existing.metadata_json = meta
                flag_modified(existing, 'metadata_json')
                
                session.commit()
                
                self.logger.debug(
                    f"Boosted relationship confidence: {relation_type} "
                    f"({current_confidence:.2f} -> {new_confidence:.2f})"
                )
                
                return {
                    "id": str(existing.id),
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation_type": relation_type,
                    "confidence": new_confidence,
                    "occurrence_count": occurrence_count + 1,
                    "is_new": False,
                }
            else:
                # Create new relationship
                rel = Relationship(
                    id=uuid.uuid4(),
                    source_id=source_id,
                    target_id=target_id,
                    relation_type=relation_type,
                    source_type="entity",
                    target_type="entity",
                    metadata_json={
                        "confidence": 0.5,
                        "occurrence_count": 1,
                        "sources": [source_url] if source_url else [],
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                session.add(rel)
                session.commit()
                
                return {
                    "id": str(rel.id),
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation_type": relation_type,
                    "confidence": 0.5,
                    "occurrence_count": 1,
                    "is_new": True,
                }
    
    def get_high_confidence_relationships(
        self,
        min_confidence: float = 0.7,
        min_occurrences: int = 2,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get relationships with high confidence scores.
        
        Args:
            min_confidence: Minimum confidence threshold
            min_occurrences: Minimum occurrence count
            limit: Maximum results
            
        Returns:
            List of high-confidence relationships
        """
        results = []
        
        with self.Session() as session:
            # Get all relationships
            rels = session.execute(select(Relationship)).scalars().all()
            
            for rel in rels:
                meta = rel.metadata_json or {}
                confidence = meta.get("confidence", 0.5)
                occurrences = meta.get("occurrence_count", 1)
                
                if confidence >= min_confidence and occurrences >= min_occurrences:
                    results.append({
                        "id": str(rel.id),
                        "source_id": str(rel.source_id),
                        "target_id": str(rel.target_id),
                        "relation_type": rel.relation_type,
                        "confidence": confidence,
                        "occurrence_count": occurrences,
                        "sources": meta.get("sources", []),
                    })
            
            # Sort by confidence
            results.sort(key=lambda x: x["confidence"], reverse=True)
            return results[:limit]
