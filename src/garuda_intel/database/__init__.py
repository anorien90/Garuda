"""
Database layer for Garuda Intel.

Provides:
- SQLAlchemy models for entities, relationships, pages, intelligence
- Dynamic field discovery models for adaptive learning
- Database engine and storage abstraction
- CLI tool for database management
"""

from .models import (
    Base,
    Entity,
    Relationship,
    Page,
    PageContent,
    Intelligence,
    Seed,
    Fingerprint,
    Pattern,
    Domain,
    Link,
    MediaItem,
    MediaContent,
    DynamicFieldDefinition,
    EntityFieldValue,
    FieldDiscoveryLog,
    Task,
    ChatMemoryEntry,
    SemanticSnippet,
)
from .engine import SQLAlchemyStore
from .store import PersistenceStore

__all__ = [
    # Base
    "Base",
    # Core models
    "Entity",
    "Relationship",
    "Page",
    "PageContent",
    "Intelligence",
    "Seed",
    "Fingerprint",
    "Pattern",
    "Domain",
    "Link",
    "MediaItem",
    "MediaContent",
    # Dynamic field models
    "DynamicFieldDefinition",
    "EntityFieldValue",
    "FieldDiscoveryLog",
    # Task model
    "Task",
    # Chat memory model
    "ChatMemoryEntry",
    # Semantic snippet model
    "SemanticSnippet",
    # Storage
    "SQLAlchemyStore",
    "PersistenceStore",
]
