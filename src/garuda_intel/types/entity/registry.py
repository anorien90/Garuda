"""
Dynamic Entity Kind Registry.

This module provides a centralized registry for entity kinds, relation types,
and their associated metadata. The registry supports dynamic extension at runtime,
allowing new entity kinds to emerge as the system discovers them.

The registry is designed to be:
1. Dynamic - New kinds can be registered at runtime
2. Persistent - Registry state can be loaded from database
3. Extensible - Additional metadata can be associated with kinds
4. Backwards Compatible - Static kinds are pre-registered as defaults
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from enum import Enum


logger = logging.getLogger(__name__)


@dataclass
class EntityKindInfo:
    """Metadata about an entity kind."""
    name: str
    priority: int = 50  # Lower = higher priority for deduplication (1-100)
    color: str = "#94a3b8"  # Default slate gray
    description: str = ""
    parent_kind: Optional[str] = None  # For hierarchical kinds
    aliases: List[str] = field(default_factory=list)
    fields: List[str] = field(default_factory=list)  # Common fields for this kind
    is_builtin: bool = False  # True for predefined kinds
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "priority": self.priority,
            "color": self.color,
            "description": self.description,
            "parent_kind": self.parent_kind,
            "aliases": self.aliases,
            "fields": self.fields,
            "is_builtin": self.is_builtin,
        }


@dataclass
class RelationTypeInfo:
    """Metadata about a relation type."""
    name: str
    source_kinds: List[str] = field(default_factory=list)  # Allowed source entity kinds
    target_kinds: List[str] = field(default_factory=list)  # Allowed target entity kinds
    color: str = "rgba(148,163,184,0.25)"
    description: str = ""
    inverse_relation: Optional[str] = None  # e.g., "works-at" inverse is "employs"
    is_builtin: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source_kinds": self.source_kinds,
            "target_kinds": self.target_kinds,
            "color": self.color,
            "description": self.description,
            "inverse_relation": self.inverse_relation,
            "is_builtin": self.is_builtin,
        }


class EntityKindRegistry:
    """
    Centralized registry for entity kinds.
    
    This registry maintains all known entity kinds and their metadata.
    It supports dynamic registration of new kinds at runtime.
    """
    
    # Default builtin kinds with their properties
    BUILTIN_KINDS: Dict[str, EntityKindInfo] = {
        # Core entity kinds
        "person": EntityKindInfo(
            name="person",
            priority=1,
            color="#0ea5e9",  # Sky blue
            description="An individual human being",
            aliases=["individual", "human", "people"],
            fields=["name", "title", "role", "bio", "organization", "location"],
            is_builtin=True,
        ),
        "org": EntityKindInfo(
            name="org",
            priority=2,
            color="#22c55e",  # Green
            description="An organization or institution",
            aliases=["organization", "institution", "agency"],
            fields=["name", "type", "description", "location", "founded"],
            is_builtin=True,
        ),
        "company": EntityKindInfo(
            name="company",
            priority=3,
            color="#16a34a",  # Darker green
            description="A business or corporation",
            parent_kind="org",
            aliases=["corporation", "business", "enterprise", "firm"],
            fields=["name", "ticker", "industry", "description", "founded", "website", "employees"],
            is_builtin=True,
        ),
        "product": EntityKindInfo(
            name="product",
            priority=4,
            color="#f97316",  # Orange
            description="A product or service offering",
            aliases=["service", "offering", "solution"],
            fields=["name", "description", "status", "manufacturer", "category"],
            is_builtin=True,
        ),
        "location": EntityKindInfo(
            name="location",
            priority=5,
            color="#a855f7",  # Purple
            description="A geographical location or place",
            aliases=["place", "city", "country", "region", "address"],
            fields=["name", "address", "city", "country", "type", "coordinates"],
            is_builtin=True,
        ),
        "event": EntityKindInfo(
            name="event",
            priority=6,
            color="#06b6d4",  # Cyan
            description="An event or occurrence",
            aliases=["occurrence", "incident", "meeting", "conference"],
            fields=["name", "title", "date", "description", "location", "type"],
            is_builtin=True,
        ),
        # Additional common kinds
        "technology": EntityKindInfo(
            name="technology",
            priority=7,
            color="#8b5cf6",  # Violet
            description="A technology, framework, or technical concept",
            aliases=["tech", "framework", "platform", "tool"],
            fields=["name", "description", "category", "version", "vendor"],
            is_builtin=True,
        ),
        "document": EntityKindInfo(
            name="document",
            priority=8,
            color="#64748b",  # Slate
            description="A document, publication, or written content",
            aliases=["report", "publication", "article", "paper"],
            fields=["name", "title", "author", "date", "type", "summary"],
            is_builtin=True,
        ),
        "concept": EntityKindInfo(
            name="concept",
            priority=9,
            color="#fbbf24",  # Amber
            description="An abstract concept, topic, or idea",
            aliases=["topic", "idea", "theme", "subject"],
            fields=["name", "description", "category"],
            is_builtin=True,
        ),
        "infrastructure": EntityKindInfo(
            name="infrastructure",
            priority=10,
            color="#14b8a6",  # Teal
            description="Infrastructure or system component",
            aliases=["system", "component", "resource"],
            fields=["name", "type", "description", "location", "status"],
            is_builtin=True,
        ),
        "project": EntityKindInfo(
            name="project",
            priority=11,
            color="#ec4899",  # Pink
            description="A project or initiative",
            aliases=["initiative", "program", "effort"],
            fields=["name", "description", "status", "start_date", "end_date", "owner"],
            is_builtin=True,
        ),
        "entity": EntityKindInfo(
            name="entity",
            priority=99,  # Low priority - generic fallback
            color="#14b8a6",  # Teal
            description="A generic entity (will be reclassified when type is determined)",
            aliases=[],
            fields=["name", "description"],
            is_builtin=True,
        ),
    }
    
    # Default builtin relation types
    BUILTIN_RELATIONS: Dict[str, RelationTypeInfo] = {
        "has-person": RelationTypeInfo(
            name="has-person",
            source_kinds=["org", "company", "project"],
            target_kinds=["person"],
            color="rgba(14,165,233,0.35)",
            description="Organization has a person (employee, member, etc.)",
            inverse_relation="works-at",
            is_builtin=True,
        ),
        "works-at": RelationTypeInfo(
            name="works-at",
            source_kinds=["person"],
            target_kinds=["org", "company"],
            color="rgba(14,165,233,0.35)",
            description="Person works at an organization",
            inverse_relation="has-person",
            is_builtin=True,
        ),
        "has-location": RelationTypeInfo(
            name="has-location",
            source_kinds=["org", "company", "person", "event"],
            target_kinds=["location"],
            color="rgba(168,85,247,0.35)",
            description="Entity has a location",
            inverse_relation="location-of",
            is_builtin=True,
        ),
        "located-at": RelationTypeInfo(
            name="located-at",
            source_kinds=["org", "company", "person", "event", "infrastructure"],
            target_kinds=["location"],
            color="rgba(168,85,247,0.35)",
            description="Entity is located at a place",
            is_builtin=True,
        ),
        "has-product": RelationTypeInfo(
            name="has-product",
            source_kinds=["org", "company"],
            target_kinds=["product"],
            color="rgba(249,115,22,0.35)",
            description="Organization has a product",
            inverse_relation="produced-by",
            is_builtin=True,
        ),
        "produced-by": RelationTypeInfo(
            name="produced-by",
            source_kinds=["product"],
            target_kinds=["org", "company"],
            color="rgba(249,115,22,0.35)",
            description="Product is produced by an organization",
            inverse_relation="has-product",
            is_builtin=True,
        ),
        "participated-in-event": RelationTypeInfo(
            name="participated-in-event",
            source_kinds=["person", "org", "company"],
            target_kinds=["event"],
            color="rgba(6,182,212,0.35)",
            description="Entity participated in an event",
            is_builtin=True,
        ),
        "uses-technology": RelationTypeInfo(
            name="uses-technology",
            source_kinds=["org", "company", "project", "product"],
            target_kinds=["technology"],
            color="rgba(139,92,246,0.35)",
            description="Entity uses a technology",
            is_builtin=True,
        ),
        "related-entity": RelationTypeInfo(
            name="related-entity",
            source_kinds=[],  # Any kind
            target_kinds=[],  # Any kind
            color="rgba(139,92,246,0.25)",
            description="Generic relationship between entities",
            is_builtin=True,
        ),
        "associated-with": RelationTypeInfo(
            name="associated-with",
            source_kinds=[],
            target_kinds=[],
            color="rgba(148,163,184,0.25)",
            description="Generic association between entities",
            is_builtin=True,
        ),
        "part-of": RelationTypeInfo(
            name="part-of",
            source_kinds=[],
            target_kinds=[],
            color="rgba(34,197,94,0.30)",
            description="Entity is part of another entity",
            inverse_relation="contains",
            is_builtin=True,
        ),
        "contains": RelationTypeInfo(
            name="contains",
            source_kinds=[],
            target_kinds=[],
            color="rgba(34,197,94,0.30)",
            description="Entity contains another entity",
            inverse_relation="part-of",
            is_builtin=True,
        ),
    }
    
    _instance: Optional["EntityKindRegistry"] = None
    _lock = None  # Will be lazily initialized as a threading.Lock
    
    def __new__(cls):
        """Singleton pattern - ensure only one registry instance (thread-safe)."""
        # Use double-checked locking for thread safety
        if cls._instance is None:
            import threading
            if cls._lock is None:
                cls._lock = threading.Lock()
            with cls._lock:
                # Double-check inside lock
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # Initialize with builtin kinds
        self._kinds: Dict[str, EntityKindInfo] = dict(self.BUILTIN_KINDS)
        self._relations: Dict[str, RelationTypeInfo] = dict(self.BUILTIN_RELATIONS)
        
        # Build alias lookup
        self._alias_to_kind: Dict[str, str] = {}
        self._rebuild_alias_lookup()
        
        logger.info(f"Entity registry initialized with {len(self._kinds)} kinds and {len(self._relations)} relations")
    
    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance. Used for testing."""
        cls._instance = None
    
    def _rebuild_alias_lookup(self):
        """Rebuild the alias to kind lookup table."""
        self._alias_to_kind.clear()
        for kind_name, kind_info in self._kinds.items():
            for alias in kind_info.aliases:
                self._alias_to_kind[alias.lower()] = kind_name
    
    def register_kind(
        self,
        name: str,
        priority: int = 50,
        color: str = "#94a3b8",
        description: str = "",
        parent_kind: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        fields: Optional[List[str]] = None,
    ) -> EntityKindInfo:
        """
        Register a new entity kind.
        
        Args:
            name: The name of the kind (lowercase)
            priority: Deduplication priority (1-100, lower = higher priority)
            color: Hex color for UI display
            description: Human-readable description
            parent_kind: Parent kind for hierarchical classification
            aliases: List of alternative names for this kind
            fields: Common fields for entities of this kind
            
        Returns:
            The registered EntityKindInfo
        """
        name = name.lower().strip()
        if not name:
            raise ValueError("Kind name cannot be empty")
        
        # Check if already exists
        if name in self._kinds:
            existing = self._kinds[name]
            # Update non-builtin kinds, but don't modify builtins
            if not existing.is_builtin:
                existing.priority = priority
                existing.color = color
                existing.description = description or existing.description
                existing.parent_kind = parent_kind or existing.parent_kind
                if aliases:
                    existing.aliases = list(set(existing.aliases + aliases))
                if fields:
                    existing.fields = list(set(existing.fields + fields))
                self._rebuild_alias_lookup()
            return existing
        
        # Create new kind
        kind_info = EntityKindInfo(
            name=name,
            priority=priority,
            color=color,
            description=description,
            parent_kind=parent_kind,
            aliases=aliases or [],
            fields=fields or [],
            is_builtin=False,
        )
        self._kinds[name] = kind_info
        self._rebuild_alias_lookup()
        
        logger.info(f"Registered new entity kind: {name}")
        return kind_info
    
    def register_relation(
        self,
        name: str,
        source_kinds: Optional[List[str]] = None,
        target_kinds: Optional[List[str]] = None,
        color: str = "rgba(148,163,184,0.25)",
        description: str = "",
        inverse_relation: Optional[str] = None,
    ) -> RelationTypeInfo:
        """
        Register a new relation type.
        
        Args:
            name: The name of the relation type
            source_kinds: Allowed source entity kinds (empty = any)
            target_kinds: Allowed target entity kinds (empty = any)
            color: Color for UI display
            description: Human-readable description
            inverse_relation: Name of the inverse relation
            
        Returns:
            The registered RelationTypeInfo
        """
        name = name.lower().strip()
        if not name:
            raise ValueError("Relation name cannot be empty")
        
        if name in self._relations:
            existing = self._relations[name]
            if not existing.is_builtin:
                existing.source_kinds = source_kinds or existing.source_kinds
                existing.target_kinds = target_kinds or existing.target_kinds
                existing.color = color
                existing.description = description or existing.description
                existing.inverse_relation = inverse_relation or existing.inverse_relation
            return existing
        
        relation_info = RelationTypeInfo(
            name=name,
            source_kinds=source_kinds or [],
            target_kinds=target_kinds or [],
            color=color,
            description=description,
            inverse_relation=inverse_relation,
            is_builtin=False,
        )
        self._relations[name] = relation_info
        
        logger.info(f"Registered new relation type: {name}")
        return relation_info
    
    def get_kind(self, name: str) -> Optional[EntityKindInfo]:
        """Get kind info by name or alias."""
        name = name.lower().strip()
        if name in self._kinds:
            return self._kinds[name]
        # Check aliases
        if name in self._alias_to_kind:
            return self._kinds[self._alias_to_kind[name]]
        return None
    
    def get_relation(self, name: str) -> Optional[RelationTypeInfo]:
        """Get relation info by name."""
        return self._relations.get(name.lower().strip())
    
    def normalize_kind(self, name: str) -> str:
        """
        Normalize a kind name to its canonical form.
        
        Returns the canonical kind name if found, otherwise returns
        the input as-is (for dynamic kinds).
        """
        if not name:
            return "entity"
        name = name.lower().strip()
        
        # Direct match
        if name in self._kinds:
            return name
        
        # Alias match
        if name in self._alias_to_kind:
            return self._alias_to_kind[name]
        
        # Return as-is for dynamic kinds
        return name
    
    def get_priority(self, kind: str) -> int:
        """Get the priority for a kind (lower = higher priority)."""
        kind_info = self.get_kind(kind)
        if kind_info:
            return kind_info.priority
        return 50  # Default priority for unknown kinds
    
    def get_all_kinds(self) -> Dict[str, EntityKindInfo]:
        """Get all registered kinds."""
        return dict(self._kinds)
    
    def get_all_relations(self) -> Dict[str, RelationTypeInfo]:
        """Get all registered relations."""
        return dict(self._relations)
    
    def get_kind_names(self) -> List[str]:
        """Get all kind names."""
        return sorted(self._kinds.keys())
    
    def get_relation_names(self) -> List[str]:
        """Get all relation type names."""
        return sorted(self._relations.keys())
    
    def get_kind_priority_map(self) -> Dict[str, int]:
        """Get a map of kind name -> priority."""
        return {name: info.priority for name, info in self._kinds.items()}
    
    def get_kind_colors(self) -> Dict[str, str]:
        """Get a map of kind name -> color."""
        return {name: info.color for name, info in self._kinds.items()}
    
    def get_relation_colors(self) -> Dict[str, str]:
        """Get a map of relation name -> color."""
        return {name: info.color for name, info in self._relations.items()}
    
    def is_known_kind(self, name: str) -> bool:
        """Check if a kind is known (either direct or alias)."""
        name = name.lower().strip()
        return name in self._kinds or name in self._alias_to_kind
    
    def sync_from_database(self, db_kinds: List[str]):
        """
        Sync the registry with kinds discovered in the database.
        
        This registers any kinds found in the database that aren't
        already registered, ensuring the registry stays current.
        """
        for kind in db_kinds:
            if kind and not self.is_known_kind(kind):
                # Auto-register discovered kinds with default properties
                self.register_kind(
                    name=kind,
                    description=f"Dynamically discovered entity kind: {kind}",
                )
    
    def to_dict(self) -> Dict[str, Any]:
        """Export the registry as a dictionary."""
        return {
            "kinds": {name: info.to_dict() for name, info in self._kinds.items()},
            "relations": {name: info.to_dict() for name, info in self._relations.items()},
        }


# Global registry instance
_registry: Optional[EntityKindRegistry] = None


def get_registry() -> EntityKindRegistry:
    """Get the global entity kind registry."""
    global _registry
    if _registry is None:
        _registry = EntityKindRegistry()
    return _registry


def normalize_kind(name: str) -> str:
    """Convenience function to normalize a kind name."""
    return get_registry().normalize_kind(name)


def get_kind_priority(kind: str) -> int:
    """Convenience function to get kind priority."""
    return get_registry().get_priority(kind)
