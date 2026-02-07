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
    
    def __init__(self, session_maker, logger: Optional[logging.Logger] = None):
        """
        Initialize EntityMerger.
        
        Args:
            session_maker: SQLAlchemy session maker
            logger: Optional logger instance
        """
        self.Session = session_maker
        self.logger = logger or logging.getLogger(__name__)
    
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
            
            entity = session.execute(stmt).scalar_one_or_none()
            if entity:
                return self._entity_to_dict(entity)
            
            # 2. Try fuzzy match if enabled
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
        stmt = select(Entity).where(func.lower(Entity.name) == name_normalized)
        entity = session.execute(stmt).scalar_one_or_none()
        
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
