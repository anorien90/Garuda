"""Knowledge inference engine for cross-entity intelligence.

This module provides graph-based inference to fill knowledge gaps by traversing
entity relationships and applying inference rules with confidence scoring.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime
from enum import Enum
import uuid


class InferenceConfidence(Enum):
    """Confidence levels for inferred facts."""
    HIGH = 0.9  # Strong evidence from multiple sources
    MEDIUM = 0.7  # Moderate evidence
    LOW = 0.5  # Weak evidence, speculative


@dataclass
class InferredFact:
    """An inferred piece of intelligence.
    
    Attributes:
        entity_id: Target entity ID
        field_name: Name of inferred field
        value: Inferred value
        confidence: Confidence score (0.0-1.0)
        inference_type: Type of inference used
        provenance: List of source entity IDs used
        reasoning: Human-readable explanation
        timestamp: When inference was made
    """
    entity_id: str
    field_name: str
    value: Any
    confidence: float
    inference_type: str
    provenance: List[str]
    reasoning: str
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class InferenceRule:
    """Base class for inference rules.
    
    Each rule defines a pattern to match in the knowledge graph
    and how to derive new facts from matched patterns.
    """
    
    def __init__(self, name: str, confidence: float = 0.7):
        """Initialize inference rule.
        
        Args:
            name: Rule name/identifier
            confidence: Base confidence for this rule
        """
        self.name = name
        self.base_confidence = confidence
    
    def matches(self, entity: Any, graph_data: Dict) -> bool:
        """Check if rule applies to entity.
        
        Args:
            entity: Entity to check
            graph_data: Graph data with relationships
            
        Returns:
            True if rule can be applied
        """
        raise NotImplementedError
    
    def infer(self, entity: Any, graph_data: Dict) -> List[InferredFact]:
        """Apply rule to infer new facts.
        
        Args:
            entity: Entity to infer facts for
            graph_data: Graph data with relationships
            
        Returns:
            List of inferred facts
        """
        raise NotImplementedError


class TransitiveLocationRule(InferenceRule):
    """Infer person location from employer location.
    
    Pattern: Person --works_at--> Company --located_in--> Location
    Inference: Person probably located near Location
    """
    
    def __init__(self):
        super().__init__("transitive_location", confidence=0.75)
    
    def matches(self, entity: Any, graph_data: Dict) -> bool:
        """Check if person has employer with known location."""
        if entity.get("kind") != "person":
            return False
        
        entity_id = str(entity.get("id"))
        relationships = graph_data.get("relationships", {})
        
        # Check for works_at relationship
        for rel in relationships.get(entity_id, []):
            if rel.get("type") == "works_at":
                target_id = rel.get("target_id")
                target = graph_data.get("entities", {}).get(target_id)
                if target and target.get("data", {}).get("location"):
                    return True
        
        return False
    
    def infer(self, entity: Any, graph_data: Dict) -> List[InferredFact]:
        """Infer person location from employer."""
        facts = []
        entity_id = str(entity.get("id"))
        relationships = graph_data.get("relationships", {})
        
        for rel in relationships.get(entity_id, []):
            if rel.get("type") == "works_at":
                target_id = rel.get("target_id")
                target = graph_data.get("entities", {}).get(target_id)
                
                if target:
                    location = target.get("data", {}).get("location")
                    if location:
                        facts.append(InferredFact(
                            entity_id=entity_id,
                            field_name="probable_location",
                            value=location,
                            confidence=self.base_confidence,
                            inference_type=self.name,
                            provenance=[target_id],
                            reasoning=(
                                f"Person works at {target.get('name')}, "
                                f"which is located in {location}"
                            )
                        ))
        
        return facts


class IndustryFromCompanyRule(InferenceRule):
    """Infer person's industry from employer industry.
    
    Pattern: Person --works_at--> Company (with industry)
    Inference: Person works in that industry
    """
    
    def __init__(self):
        super().__init__("industry_from_company", confidence=0.85)
    
    def matches(self, entity: Any, graph_data: Dict) -> bool:
        """Check if person has employer with known industry."""
        if entity.get("kind") != "person":
            return False
        
        entity_id = str(entity.get("id"))
        relationships = graph_data.get("relationships", {})
        
        for rel in relationships.get(entity_id, []):
            if rel.get("type") == "works_at":
                target_id = rel.get("target_id")
                target = graph_data.get("entities", {}).get(target_id)
                if target and target.get("data", {}).get("industry"):
                    return True
        
        return False
    
    def infer(self, entity: Any, graph_data: Dict) -> List[InferredFact]:
        """Infer person's industry from employer."""
        facts = []
        entity_id = str(entity.get("id"))
        relationships = graph_data.get("relationships", {})
        
        for rel in relationships.get(entity_id, []):
            if rel.get("type") == "works_at":
                target_id = rel.get("target_id")
                target = graph_data.get("entities", {}).get(target_id)
                
                if target:
                    industry = target.get("data", {}).get("industry")
                    if industry:
                        facts.append(InferredFact(
                            entity_id=entity_id,
                            field_name="industry",
                            value=industry,
                            confidence=self.base_confidence,
                            inference_type=self.name,
                            provenance=[target_id],
                            reasoning=(
                                f"Person works at {target.get('name')}, "
                                f"which operates in {industry} industry"
                            )
                        ))
        
        return facts


class KnowledgeInferenceEngine:
    """Graph-based inference engine for entity intelligence.
    
    The engine:
    1. Loads entity graph with relationships
    2. Applies inference rules to discover implicit facts
    3. Scores confidence based on evidence strength
    4. Tracks provenance for explainability
    
    Features:
    - Multiple inference rules
    - Confidence scoring
    - Provenance tracking
    - Cycle detection
    - Configurable confidence thresholds
    """
    
    def __init__(self, min_confidence: float = 0.5):
        """Initialize inference engine.
        
        Args:
            min_confidence: Minimum confidence to accept inferences
        """
        self.min_confidence = min_confidence
        self.rules: List[InferenceRule] = []
        self._register_default_rules()
    
    def _register_default_rules(self):
        """Register default inference rules."""
        self.rules.append(TransitiveLocationRule())
        self.rules.append(IndustryFromCompanyRule())
    
    def register_rule(self, rule: InferenceRule):
        """Register a custom inference rule.
        
        Args:
            rule: InferenceRule instance
        """
        self.rules.append(rule)
    
    def infer_missing_data(
        self,
        entity: Any,
        graph_data: Dict,
        fields: Optional[List[str]] = None
    ) -> List[InferredFact]:
        """Infer missing data for an entity.
        
        Args:
            entity: Entity dict with id, kind, data, etc.
            graph_data: Graph data with entities and relationships
            fields: Optional list of specific fields to infer
            
        Returns:
            List of inferred facts above confidence threshold
        """
        inferred_facts = []
        
        # Apply each matching rule
        for rule in self.rules:
            if rule.matches(entity, graph_data):
                facts = rule.infer(entity, graph_data)
                
                # Filter by confidence and requested fields
                for fact in facts:
                    if fact.confidence >= self.min_confidence:
                        if fields is None or fact.field_name in fields:
                            inferred_facts.append(fact)
        
        return inferred_facts
    
    def infer_for_all_entities(
        self,
        graph_data: Dict
    ) -> Dict[str, List[InferredFact]]:
        """Run inference for all entities in graph.
        
        Args:
            graph_data: Graph data with entities and relationships
            
        Returns:
            Dict mapping entity_id -> list of inferred facts
        """
        results = {}
        
        entities = graph_data.get("entities", {})
        for entity_id, entity in entities.items():
            facts = self.infer_missing_data(entity, graph_data)
            if facts:
                results[entity_id] = facts
        
        return results
    
    def build_graph_data(self, db_session) -> Dict:
        """Build graph data structure from database.
        
        Args:
            db_session: SQLAlchemy session
            
        Returns:
            Dict with entities and relationships
        """
        from ..database.models import Entity, Relationship
        
        # Load all entities
        entities = {}
        for entity in db_session.query(Entity).all():
            entities[str(entity.id)] = {
                "id": entity.id,
                "name": entity.name,
                "kind": entity.kind,
                "data": entity.data or {}
            }
        
        # Load relationships grouped by source
        relationships = {}
        for rel in db_session.query(Relationship).all():
            source_id = str(rel.source_id)
            if source_id not in relationships:
                relationships[source_id] = []
            
            relationships[source_id].append({
                "type": rel.relation_type,
                "target_id": str(rel.target_id),
                "metadata": rel.metadata_json or {}
            })
        
        return {
            "entities": entities,
            "relationships": relationships
        }
    
    def apply_inferences(
        self,
        entity_id: str,
        facts: List[InferredFact],
        db_session,
        store_in_db: bool = True
    ) -> Dict[str, Any]:
        """Apply inferred facts to entity.
        
        Args:
            entity_id: Target entity ID
            facts: List of inferred facts
            db_session: Database session
            store_in_db: Whether to persist to database
            
        Returns:
            Updated entity data dict
        """
        from ..database.models import Entity
        import uuid as uuid_lib
        
        # Get entity
        entity = db_session.query(Entity).filter(
            Entity.id == uuid_lib.UUID(entity_id)
        ).first()
        
        if not entity:
            return {}
        
        # Update entity data
        if entity.data is None:
            entity.data = {}
        
        updated_data = entity.data.copy()
        
        for fact in facts:
            # Add field with metadata
            field_key = fact.field_name
            updated_data[field_key] = {
                "value": fact.value,
                "inferred": True,
                "confidence": fact.confidence,
                "inference_type": fact.inference_type,
                "reasoning": fact.reasoning,
                "provenance": fact.provenance,
                "timestamp": fact.timestamp.isoformat()
            }
        
        if store_in_db:
            entity.data = updated_data
            db_session.commit()
        
        return updated_data
