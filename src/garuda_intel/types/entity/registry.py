"""
Dynamic Entity Kind Registry.

A thread-safe singleton registry for managing entity kinds with:
- Builtin kinds with predefined colors and priorities
- Runtime registration of new kinds discovered in database
- Kind normalization and alias support
- Priority-based deduplication (specific kinds override generic ones)
"""

import logging
import threading
from typing import Dict, Optional, List, Any, Set, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class EntityKindInfo:
    """Information about an entity kind."""
    name: str
    color: str
    priority: int  # Higher priority kinds override lower priority when deduplicating
    aliases: Set[str] = field(default_factory=set)
    parent_kind: Optional[str] = None  # For hierarchical kinds (e.g., 'ceo' -> 'person')
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "name": self.name,
            "color": self.color,
            "priority": self.priority,
            "aliases": list(self.aliases),
            "parent_kind": self.parent_kind,
            "description": self.description,
        }


@dataclass
class RelationTypeInfo:
    """Information about a relation type."""
    name: str
    color: str
    directed: bool = True
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "name": self.name,
            "color": self.color,
            "directed": self.directed,
            "description": self.description,
        }


class EntityKindRegistry:
    """
    Thread-safe singleton registry for entity kinds.
    
    Usage:
        registry = EntityKindRegistry.instance()
        registry.register_kind("custom_type", color="#ff0000", priority=50)
        info = registry.get_kind("person")
    """
    
    _instance: Optional["EntityKindRegistry"] = None
    _lock = threading.Lock()
    
    # Default builtin kinds with colors and priorities
    # Higher priority = more specific (should override generic)
    BUILTIN_KINDS: Dict[str, Dict[str, Any]] = {
        # Generic entity (lowest priority)
        "entity": {"color": "#14b8a6", "priority": 10, "description": "Generic entity"},
        "unknown": {"color": "#94a3b8", "priority": 5, "description": "Unknown entity type"},
        
        # Core entity types (medium priority)
        "person": {"color": "#0ea5e9", "priority": 50, "description": "Person/individual"},
        "org": {"color": "#22c55e", "priority": 50, "aliases": {"organization", "organisation"}, "description": "Organization"},
        "company": {"color": "#10b981", "priority": 55, "parent_kind": "org", "description": "Company/business"},
        "location": {"color": "#a855f7", "priority": 50, "aliases": {"place", "address"}, "description": "Geographic location"},
        "product": {"color": "#f97316", "priority": 50, "description": "Product or service"},
        "event": {"color": "#06b6d4", "priority": 50, "description": "Event or occurrence"},
        "technology": {"color": "#8b5cf6", "priority": 50, "aliases": {"tech", "software"}, "description": "Technology/software"},
        "document": {"color": "#64748b", "priority": 40, "aliases": {"doc", "file"}, "description": "Document or file"},
        "concept": {"color": "#cbd5e1", "priority": 30, "aliases": {"idea", "topic"}, "description": "Abstract concept"},
        "infrastructure": {"color": "#78716c", "priority": 45, "aliases": {"infra"}, "description": "Infrastructure"},
        "project": {"color": "#059669", "priority": 45, "description": "Project or initiative"},
        
        # Specialized person types (high priority - override 'person')
        "ceo": {"color": "#0284c7", "priority": 70, "parent_kind": "person", "description": "Chief Executive Officer"},
        "founder": {"color": "#0369a1", "priority": 70, "parent_kind": "person", "aliases": {"co-founder"}, "description": "Founder"},
        "executive": {"color": "#0891b2", "priority": 65, "parent_kind": "person", "description": "Executive/leadership"},
        "board_member": {"color": "#06b6d4", "priority": 65, "parent_kind": "person", "description": "Board member"},
        "employee": {"color": "#38bdf8", "priority": 55, "parent_kind": "person", "description": "Employee/staff member"},
        
        # Specialized location types (high priority - override 'location')
        "headquarters": {"color": "#9333ea", "priority": 60, "parent_kind": "location", "aliases": {"hq"}, "description": "Headquarters"},
        "office": {"color": "#7c3aed", "priority": 55, "parent_kind": "location", "description": "Office location"},
        "branch_office": {"color": "#6d28d9", "priority": 55, "parent_kind": "location", "description": "Branch office"},
        "registered_address": {"color": "#5b21b6", "priority": 55, "parent_kind": "location", "description": "Registered address"},
        "mailing_address": {"color": "#4c1d95", "priority": 55, "parent_kind": "location", "description": "Mailing address"},
        "billing_address": {"color": "#7e22ce", "priority": 55, "parent_kind": "location", "description": "Billing address"},
        "shipping_address": {"color": "#6b21a8", "priority": 55, "parent_kind": "location", "description": "Shipping address"},
        
        # Specialized organization types (high priority - override 'org'/'company')
        "subsidiary": {"color": "#059669", "priority": 60, "parent_kind": "company", "description": "Subsidiary company"},
        "parent_company": {"color": "#047857", "priority": 60, "parent_kind": "company", "description": "Parent company"},
        "division": {"color": "#065f46", "priority": 55, "parent_kind": "org", "description": "Organization division"},
        "department": {"color": "#064e3b", "priority": 55, "parent_kind": "org", "description": "Organization department"},
        
        # Content/media types
        "page": {"color": "#4366f1", "priority": 20, "description": "Web page"},
        "intel": {"color": "#f43f5e", "priority": 25, "description": "Intelligence data"},
        "image": {"color": "#facc15", "priority": 20, "description": "Image"},
        "media": {"color": "#ec4899", "priority": 20, "description": "Media content"},
        "seed": {"color": "#84cc16", "priority": 15, "description": "Search seed"},
        "semantic-snippet": {"color": "#fbbf24", "priority": 20, "description": "Semantic text snippet"},
    }
    
    # Default builtin relation types
    BUILTIN_RELATIONS: Dict[str, Dict[str, Any]] = {
        "cooccurrence": {"color": "rgba(148,163,184,0.22)", "directed": False, "description": "Co-occurrence"},
        "page-mentions": {"color": "rgba(34,197,94,0.28)", "directed": True, "description": "Page mentions entity"},
        "intel-mentions": {"color": "rgba(244,63,94,0.32)", "directed": True, "description": "Intel mentions entity"},
        "intel-primary": {"color": "rgba(244,63,94,0.38)", "directed": True, "description": "Primary intel link"},
        "page-image": {"color": "rgba(250,204,21,0.30)", "directed": True, "description": "Page contains image"},
        "page-media": {"color": "rgba(236,72,153,0.30)", "directed": True, "description": "Page contains media"},
        "entity-media": {"color": "rgba(236,72,153,0.35)", "directed": True, "description": "Entity has media"},
        "link": {"color": "rgba(99,102,241,0.28)", "directed": True, "description": "Generic link"},
        "relationship": {"color": "rgba(139,92,246,0.35)", "directed": True, "description": "Generic relationship"},
        "seed-entity": {"color": "rgba(132,204,22,0.30)", "directed": True, "description": "Seed discovered entity"},
        "semantic-hit": {"color": "rgba(251,191,36,0.30)", "directed": True, "description": "Semantic search hit"},
        "has-person": {"color": "rgba(14,165,233,0.35)", "directed": True, "description": "Has associated person"},
        "has-location": {"color": "rgba(168,85,247,0.35)", "directed": True, "description": "Has associated location"},
        "has-product": {"color": "rgba(249,115,22,0.35)", "directed": True, "description": "Has associated product"},
        "mentions_entity": {"color": "rgba(99,102,241,0.25)", "directed": True, "description": "Mentions entity"},
        "has_person": {"color": "rgba(14,165,233,0.30)", "directed": True, "description": "Has person relationship"},
    }
    
    def __new__(cls) -> "EntityKindRegistry":
        """Ensure singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the registry with builtin kinds."""
        if getattr(self, '_initialized', False):
            return
            
        self._kinds: Dict[str, EntityKindInfo] = {}
        self._relations: Dict[str, RelationTypeInfo] = {}
        self._alias_map: Dict[str, str] = {}  # Maps aliases to canonical names
        self._kind_lock = threading.RLock()
        self._relation_lock = threading.RLock()
        
        # Register builtin kinds
        for name, info in self.BUILTIN_KINDS.items():
            self._register_kind_internal(
                name=name,
                color=info["color"],
                priority=info["priority"],
                aliases=info.get("aliases", set()),
                parent_kind=info.get("parent_kind"),
                description=info.get("description", ""),
            )
        
        # Register builtin relations
        for name, info in self.BUILTIN_RELATIONS.items():
            self._register_relation_internal(
                name=name,
                color=info["color"],
                directed=info.get("directed", True),
                description=info.get("description", ""),
            )
        
        self._initialized = True
        logger.info(f"EntityKindRegistry initialized with {len(self._kinds)} kinds and {len(self._relations)} relations")
    
    @classmethod
    def instance(cls) -> "EntityKindRegistry":
        """Get the singleton instance."""
        return cls()
    
    def _register_kind_internal(
        self,
        name: str,
        color: str,
        priority: int,
        aliases: Set[str] = None,
        parent_kind: Optional[str] = None,
        description: str = "",
    ) -> EntityKindInfo:
        """Internal method to register a kind without locking."""
        name = name.lower().strip()
        aliases = aliases or set()
        
        kind_info = EntityKindInfo(
            name=name,
            color=color,
            priority=priority,
            aliases=aliases,
            parent_kind=parent_kind,
            description=description,
        )
        
        self._kinds[name] = kind_info
        
        # Register aliases
        for alias in aliases:
            self._alias_map[alias.lower().strip()] = name
        
        return kind_info
    
    def _register_relation_internal(
        self,
        name: str,
        color: str,
        directed: bool = True,
        description: str = "",
    ) -> RelationTypeInfo:
        """Internal method to register a relation without locking."""
        name = name.lower().strip()
        
        rel_info = RelationTypeInfo(
            name=name,
            color=color,
            directed=directed,
            description=description,
        )
        
        self._relations[name] = rel_info
        return rel_info
    
    def register_kind(
        self,
        name: str,
        color: Optional[str] = None,
        priority: Optional[int] = None,
        aliases: Optional[Set[str]] = None,
        parent_kind: Optional[str] = None,
        description: str = "",
    ) -> EntityKindInfo:
        """
        Register a new entity kind or update an existing one.
        
        Args:
            name: The canonical name for the kind
            color: Hex color for visualization (defaults to gray)
            priority: Priority for deduplication (defaults to 40)
            aliases: Alternative names that map to this kind
            parent_kind: Parent kind for hierarchical relationships
            description: Human-readable description
            
        Returns:
            The registered EntityKindInfo
        """
        name = name.lower().strip()
        
        with self._kind_lock:
            # If kind already exists, update it
            if name in self._kinds:
                existing = self._kinds[name]
                if color:
                    existing.color = color
                if priority is not None:
                    existing.priority = priority
                if aliases:
                    existing.aliases.update(aliases)
                    for alias in aliases:
                        self._alias_map[alias.lower().strip()] = name
                if parent_kind:
                    existing.parent_kind = parent_kind
                if description:
                    existing.description = description
                return existing
            
            # Create new kind
            return self._register_kind_internal(
                name=name,
                color=color or "#94a3b8",  # Default gray
                priority=priority if priority is not None else 40,
                aliases=aliases or set(),
                parent_kind=parent_kind,
                description=description,
            )
    
    def register_relation(
        self,
        name: str,
        color: Optional[str] = None,
        directed: bool = True,
        description: str = "",
    ) -> RelationTypeInfo:
        """
        Register a new relation type or update an existing one.
        
        Args:
            name: The canonical name for the relation
            color: RGBA color for visualization
            directed: Whether the relation is directed
            description: Human-readable description
            
        Returns:
            The registered RelationTypeInfo
        """
        name = name.lower().strip()
        
        with self._relation_lock:
            if name in self._relations:
                existing = self._relations[name]
                if color:
                    existing.color = color
                existing.directed = directed
                if description:
                    existing.description = description
                return existing
            
            return self._register_relation_internal(
                name=name,
                color=color or "rgba(148,163,184,0.20)",
                directed=directed,
                description=description,
            )
    
    def normalize_kind(self, kind: str) -> str:
        """
        Normalize a kind name, resolving aliases to canonical names.
        
        Args:
            kind: The kind name to normalize
            
        Returns:
            The canonical kind name
        """
        if not kind:
            return "entity"
        
        kind = kind.lower().strip()
        
        with self._kind_lock:
            # Check if it's an alias
            if kind in self._alias_map:
                return self._alias_map[kind]
            
            # Check if it's a known kind
            if kind in self._kinds:
                return kind
            
            # Unknown kind - auto-register and return
            self.register_kind(kind)
            return kind
    
    def get_kind(self, kind: str) -> Optional[EntityKindInfo]:
        """
        Get information about a kind.
        
        Args:
            kind: The kind name (will be normalized)
            
        Returns:
            EntityKindInfo or None if not found
        """
        normalized = self.normalize_kind(kind)
        with self._kind_lock:
            return self._kinds.get(normalized)
    
    def get_relation(self, name: str) -> Optional[RelationTypeInfo]:
        """
        Get information about a relation type.
        
        Args:
            name: The relation name
            
        Returns:
            RelationTypeInfo or None if not found
        """
        name = name.lower().strip()
        with self._relation_lock:
            return self._relations.get(name)
    
    def get_color(self, kind: str) -> str:
        """Get the color for a kind."""
        info = self.get_kind(kind)
        return info.color if info else "#94a3b8"
    
    def get_priority(self, kind: str) -> int:
        """Get the priority for a kind."""
        info = self.get_kind(kind)
        return info.priority if info else 10
    
    def get_parent_kind(self, kind: str) -> Optional[str]:
        """Get the parent kind if any."""
        info = self.get_kind(kind)
        return info.parent_kind if info else None
    
    def is_subtype_of(self, kind: str, parent: str) -> bool:
        """
        Check if kind is a subtype of parent.
        
        Args:
            kind: The kind to check
            parent: The potential parent kind
            
        Returns:
            True if kind is a subtype of parent
        """
        kind = self.normalize_kind(kind)
        parent = self.normalize_kind(parent)
        
        if kind == parent:
            return True
        
        info = self.get_kind(kind)
        if not info or not info.parent_kind:
            return False
        
        return self.is_subtype_of(info.parent_kind, parent)
    
    def should_merge_kinds(self, kind1: str, kind2: str) -> Tuple[bool, str]:
        """
        Determine if two kinds should be merged and which one to keep.
        
        Args:
            kind1: First kind
            kind2: Second kind
            
        Returns:
            Tuple of (should_merge, winning_kind)
        """
        kind1 = self.normalize_kind(kind1)
        kind2 = self.normalize_kind(kind2)
        
        if kind1 == kind2:
            return True, kind1
        
        # Check if one is a subtype of the other
        if self.is_subtype_of(kind1, kind2):
            return True, kind1  # More specific wins
        if self.is_subtype_of(kind2, kind1):
            return True, kind2  # More specific wins
        
        # Check priorities
        p1 = self.get_priority(kind1)
        p2 = self.get_priority(kind2)
        
        # Only merge if one is generic (entity/unknown) and the other is specific
        if kind1 in ("entity", "unknown") and kind2 not in ("entity", "unknown"):
            return True, kind2
        if kind2 in ("entity", "unknown") and kind1 not in ("entity", "unknown"):
            return True, kind1
        
        # Different specific types should not be merged
        return False, kind1
    
    def get_all_kinds(self) -> List[EntityKindInfo]:
        """Get all registered kinds."""
        with self._kind_lock:
            return list(self._kinds.values())
    
    def get_all_relations(self) -> List[RelationTypeInfo]:
        """Get all registered relation types."""
        with self._relation_lock:
            return list(self._relations.values())
    
    def get_kinds_dict(self) -> Dict[str, Dict[str, Any]]:
        """Get all kinds as a dictionary for API responses."""
        with self._kind_lock:
            return {name: info.to_dict() for name, info in self._kinds.items()}
    
    def get_relations_dict(self) -> Dict[str, Dict[str, Any]]:
        """Get all relations as a dictionary for API responses."""
        with self._relation_lock:
            return {name: info.to_dict() for name, info in self._relations.items()}
    
    def get_colors_map(self) -> Dict[str, str]:
        """Get a simple name -> color mapping for frontend."""
        with self._kind_lock:
            return {name: info.color for name, info in self._kinds.items()}
    
    def get_edge_colors_map(self) -> Dict[str, str]:
        """Get a simple relation name -> color mapping for frontend."""
        with self._relation_lock:
            return {name: info.color for name, info in self._relations.items()}
    
    def sync_from_database(self, session) -> int:
        """
        Discover and register new kinds from database entities.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            Number of new kinds discovered
        """
        try:
            from ...database.models import Entity
            
            # Get all unique kinds from the database
            result = session.query(Entity.kind).distinct().all()
            new_count = 0
            
            for (kind,) in result:
                if kind and kind.lower().strip() not in self._kinds:
                    self.register_kind(kind)
                    new_count += 1
                    logger.info(f"Discovered new entity kind from database: {kind}")
            
            return new_count
        except Exception as e:
            logger.warning(f"Failed to sync kinds from database: {e}")
            return 0


# Convenience function to get the registry instance
def get_registry() -> EntityKindRegistry:
    """Get the global EntityKindRegistry instance."""
    return EntityKindRegistry.instance()
