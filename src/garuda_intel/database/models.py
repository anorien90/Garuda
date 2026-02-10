from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Any

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Text,
    ForeignKey,
    JSON,
    Boolean,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, CHAR

try:
    from sqlalchemy.dialects.postgresql import UUID as PGUUID
except ImportError:
    PGUUID = None


class GUID(TypeDecorator):
    """Platform-independent GUID/UUID type."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and PGUUID is not None:
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value if dialect.name == "postgresql" else str(value)
        # Validate that value is not empty or invalid before converting
        str_value = str(value).strip()
        if not str_value or str_value == '{}' or str_value == '[]':
            return None
        try:
            return str(uuid.UUID(str_value)) if dialect.name != "postgresql" else uuid.UUID(str_value)
        except (ValueError, AttributeError):
            # Log warning and return None for invalid UUIDs
            return None

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


Base = declarative_base()


class BasicDataEntry(Base):
    __tablename__ = "entries"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    entry_type: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __mapper_args__ = {
        "polymorphic_on": entry_type,
        "polymorphic_identity": "entry",
    }


class Entity(BasicDataEntry):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    kind: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    incoming_relationships: Mapped[list["Relationship"]] = relationship(
        "Relationship",
        foreign_keys="Relationship.target_id",
        back_populates="target_entity",
        cascade="all, delete-orphan",
    )
    outgoing_relationships: Mapped[list["Relationship"]] = relationship(
        "Relationship",
        foreign_keys="Relationship.source_id",
        back_populates="source_entity",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index('ix_entity_name_kind', 'name', 'kind'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "entity",
        "inherit_condition": id == BasicDataEntry.id,
    }


class Relationship(BasicDataEntry):
    __tablename__ = "relationships"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Type information for source and target nodes (e.g., "entity", "page", "intelligence")
    # These are optional for backward compatibility with existing data
    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Legacy Entity-specific relationship mappings for backward compatibility
    # These are maintained for existing code that expects Entity relationships,
    # but should not be used for non-Entity relationships (Page, Intelligence, etc.)
    # Use source_id/target_id directly for multi-node type relationships
    source_entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[source_id], back_populates="outgoing_relationships"
    )
    target_entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[target_id], back_populates="incoming_relationships"
    )

    __table_args__ = (
        Index('ix_relationship_source_target', 'source_id', 'target_id'),
        Index('ix_relationship_source_type', 'source_id', 'relation_type'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "relationship",
        "inherit_condition": id == BasicDataEntry.id,
    }


class Page(BasicDataEntry):
    __tablename__ = "pages"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    url: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    page_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    domain_key: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_fetch_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    text_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True
    )

    entity: Mapped["Entity"] = relationship(
        "Entity", back_populates="pages", foreign_keys=[entity_id]
    )

    __table_args__ = (
        Index('ix_page_entity_type', 'entity_id', 'page_type'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "page",
        "inherit_condition": id == BasicDataEntry.id,
    }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "url": self.url,
            "title": self.title,
            "page_type": self.page_type,
            "entity_type": self.entity_type,
            "domain_key": self.domain_key,
            "score": self.score,
            "last_status": self.last_status,
            "last_fetch_at": self.last_fetch_at.isoformat() if self.last_fetch_at else None,
            "text_length": self.text_length,
            "depth": self.depth,
            "entity_id": str(self.entity_id) if self.entity_id else None,
        }


Entity.pages = relationship(
    "Page",
    back_populates="entity",
    foreign_keys="Page.entity_id",
)


class PageContent(BasicDataEntry):
    __tablename__ = "page_content"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    page_url: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    extracted_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    fetch_ts: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    page: Mapped["Page"] = relationship(
        "Page", foreign_keys=[page_id], back_populates="content"
    )

    __mapper_args__ = {
        "polymorphic_identity": "page_content",
        "inherit_condition": id == BasicDataEntry.id,
    }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "page_id": str(self.page_id),
            "page_url": self.page_url,
            "html": self.html,
            "text": self.text,
            "metadata_json": self.metadata_json,
            "extracted_json": self.extracted_json,
            "fetch_ts": self.fetch_ts.isoformat() if self.fetch_ts else None,
        }


Page.content = relationship(
    "PageContent",
    uselist=False,
    back_populates="page",
    foreign_keys="PageContent.page_id",
)


class Seed(BasicDataEntry):
    __tablename__ = "seeds"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    query: Mapped[str] = mapped_column(String)
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __mapper_args__ = {"polymorphic_identity": "seed", "inherit_condition": id == BasicDataEntry.id}


class Intelligence(BasicDataEntry):
    __tablename__ = "intelligence"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entity_name: Mapped[Optional[str]] = mapped_column(String, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String, index=True)
    page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[entity_id], back_populates="intelligence"
    )
    page: Mapped["Page"] = relationship(
        "Page", foreign_keys=[page_id], back_populates="intelligence"
    )

    __table_args__ = (
        Index('ix_intelligence_entity_page', 'entity_id', 'page_id'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "intelligence",
        "inherit_condition": id == BasicDataEntry.id,
    }


Entity.intelligence = relationship(
    "Intelligence",
    back_populates="entity",
    foreign_keys="Intelligence.entity_id",
)
Page.intelligence = relationship(
    "Intelligence",
    back_populates="page",
    foreign_keys="Intelligence.page_id",
)


class Fingerprint(BasicDataEntry):
    __tablename__ = "fingerprints"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    kind: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Semantic/structural relation details
    selector: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    purpose: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sample_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    page: Mapped["Page"] = relationship(
        "Page", foreign_keys=[page_id], back_populates="fingerprints"
    )

    __mapper_args__ = {
        "polymorphic_identity": "fingerprint",
        "inherit_condition": id == BasicDataEntry.id,
    }


Page.fingerprints = relationship(
    "Fingerprint",
    back_populates="page",
    foreign_keys="Fingerprint.page_id",
    cascade="all, delete-orphan",
)


class Pattern(BasicDataEntry):
    __tablename__ = "patterns"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pattern: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "pattern",
        "inherit_condition": id == BasicDataEntry.id,
    }


class Domain(BasicDataEntry):
    __tablename__ = "domains"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_official: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "domain",
        "inherit_condition": id == BasicDataEntry.id,
    }


class Link(BasicDataEntry):
    """URL-to-URL link with optional Page relations."""
    __tablename__ = "links"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    from_url: Mapped[str] = mapped_column(String, nullable=False)
    to_url: Mapped[str] = mapped_column(String, nullable=False)
    from_page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    to_page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    anchor_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    relation_type: Mapped[str] = mapped_column(String, default="hyperlink")

    __table_args__ = (
        UniqueConstraint("from_url", "to_url", "relation_type", name="uq_link_from_to_type"),
    )

    from_page: Mapped[Optional["Page"]] = relationship("Page", foreign_keys=[from_page_id])
    to_page: Mapped[Optional["Page"]] = relationship("Page", foreign_keys=[to_page_id])

    __mapper_args__ = {
        "polymorphic_identity": "link",
        "inherit_condition": id == BasicDataEntry.id,
    }


class MediaItem(BasicDataEntry):
    """Base class for media items (images, videos, audio)."""
    __tablename__ = "media_items"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    url: Mapped[str] = mapped_column(String, nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String, nullable=False, index=True)  # image, video, audio
    source_page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    
    # Extracted content
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded embedding
    
    # Metadata
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # for video/audio
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Processing status
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    source_page: Mapped[Optional["Page"]] = relationship("Page", foreign_keys=[source_page_id])
    entity: Mapped[Optional["Entity"]] = relationship("Entity", foreign_keys=[entity_id])

    __mapper_args__ = {
        "polymorphic_identity": "media_item",
        "inherit_condition": id == BasicDataEntry.id,
    }


class MediaContent(BasicDataEntry):
    """Extracted content from processed media with entity linking.
    
    Tracks text/data extracted from media (images, videos, audio, PDFs)
    and links it to mentioned entities for searchable media intelligence.
    """
    __tablename__ = "media_content"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    media_url: Mapped[str] = mapped_column(String, index=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)  # image, video, audio, pdf
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Source tracking
    page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    
    # Entity mentions - list of entity IDs found in media content
    entities_mentioned: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Processing details
    processing_method: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    page: Mapped[Optional["Page"]] = relationship(
        "Page", foreign_keys=[page_id], back_populates="media_content"
    )

    __table_args__ = (
        Index('ix_media_content_page', 'page_id'),
        Index('ix_media_content_type', 'media_type'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "media_content",
        "inherit_condition": id == BasicDataEntry.id,
    }


# Add back-reference to Page
Page.media_content = relationship(
    "MediaContent",
    back_populates="page",
    foreign_keys="MediaContent.page_id",
)


class DynamicFieldDefinition(BasicDataEntry):
    """
    Stores dynamically discovered field definitions.
    
    This model tracks fields that are discovered through LLM analysis
    and trial-and-error learning. Fields can be associated with entity
    types (e.g., 'company', 'person') and evolve over time.
    
    Example: When analyzing a person, the system might discover that
    'address' is a useful field with sub-fields like postal_code, city, etc.
    """
    __tablename__ = "dynamic_field_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    # Field identification
    field_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Type classification
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    field_type: Mapped[str] = mapped_column(String(50), default="text")  # text, number, date, list, object
    
    # Discovery tracking
    importance: Mapped[str] = mapped_column(String(20), default="supplementary")  # critical, important, supplementary
    discovery_count: Mapped[int] = mapped_column(Integer, default=1)  # Times this field was discovered
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)  # Extraction success rate
    
    # Schema definition for complex fields
    schema_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Example values and validation
    example_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    validation_pattern: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Parent field for hierarchical structures (e.g., address.city)
    parent_field_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("dynamic_field_definitions.id", ondelete="SET NULL"), nullable=True
    )
    
    # Metadata
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # llm, heuristic, user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Self-referential relationship for hierarchical fields
    parent_field: Mapped[Optional["DynamicFieldDefinition"]] = relationship(
        "DynamicFieldDefinition",
        foreign_keys=[parent_field_id],
        remote_side="DynamicFieldDefinition.id",
        back_populates="sub_fields",
    )
    
    # Child fields (for hierarchical structures like address.city)
    sub_fields: Mapped[list["DynamicFieldDefinition"]] = relationship(
        "DynamicFieldDefinition",
        foreign_keys="DynamicFieldDefinition.parent_field_id",
        back_populates="parent_field",
    )

    __table_args__ = (
        UniqueConstraint("field_name", "entity_type", name="uq_field_name_entity_type"),
        Index('ix_dynamic_field_entity_importance', 'entity_type', 'importance'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "dynamic_field_definition",
        "inherit_condition": id == BasicDataEntry.id,
    }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": str(self.id),
            "field_name": self.field_name,
            "display_name": self.display_name,
            "description": self.description,
            "entity_type": self.entity_type,
            "field_type": self.field_type,
            "importance": self.importance,
            "discovery_count": self.discovery_count,
            "success_rate": self.success_rate,
            "schema_json": self.schema_json,
            "example_values": self.example_values,
            "validation_pattern": self.validation_pattern,
            "parent_field_id": str(self.parent_field_id) if self.parent_field_id else None,
            "source": self.source,
            "is_active": self.is_active,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EntityFieldValue(BasicDataEntry):
    """
    Stores discovered field values for entities.
    
    This model provides a flexible key-value store for entity attributes
    that were discovered dynamically rather than pre-defined.
    
    Supports:
    - Versioning/history tracking through timestamps
    - Confidence scoring for extracted values
    - Source tracking for provenance
    - Multiple values per field (through separate records)
    """
    __tablename__ = "entity_field_values"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    
    # Entity association
    entity_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Field definition association
    field_definition_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("dynamic_field_definitions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    
    # For backward compatibility and quick lookups
    field_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Value storage - supports different types
    value_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_number: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    value_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Quality metrics
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    extraction_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # llm, regex, heuristic
    
    # Provenance
    source_page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    
    # Version tracking
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    superseded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("entity_field_values.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[entity_id], back_populates="dynamic_field_values"
    )
    field_definition: Mapped[Optional["DynamicFieldDefinition"]] = relationship(
        "DynamicFieldDefinition", foreign_keys=[field_definition_id]
    )
    source_page: Mapped[Optional["Page"]] = relationship(
        "Page", foreign_keys=[source_page_id]
    )

    __table_args__ = (
        Index('ix_entity_field_current', 'entity_id', 'field_name', 'is_current'),
        Index('ix_entity_field_confidence', 'entity_id', 'confidence'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "entity_field_value",
        "inherit_condition": id == BasicDataEntry.id,
    }

    def get_value(self) -> Any:
        """Get the value in its appropriate type."""
        if self.value_json is not None:
            return self.value_json
        if self.value_number is not None:
            return self.value_number
        if self.value_date is not None:
            return self.value_date
        return self.value_text

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": str(self.id),
            "entity_id": str(self.entity_id),
            "field_definition_id": str(self.field_definition_id) if self.field_definition_id else None,
            "field_name": self.field_name,
            "value": self.get_value(),
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
            "source_page_id": str(self.source_page_id) if self.source_page_id else None,
            "source_url": self.source_url,
            "is_current": self.is_current,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FieldDiscoveryLog(BasicDataEntry):
    """
    Tracks field discovery attempts and outcomes for adaptive learning.
    
    This model enables the system to learn which fields are valuable
    for which entity types and which extraction methods work best.
    """
    __tablename__ = "field_discovery_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    
    # What was discovered
    field_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    
    # Discovery context
    page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True
    )
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    
    # Outcome tracking
    was_successful: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Method used
    discovery_method: Mapped[str] = mapped_column(String(50), default="llm")  # llm, pattern, user
    extraction_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Context for learning
    context_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index('ix_discovery_log_field_entity', 'field_name', 'entity_type'),
        Index('ix_discovery_log_success', 'was_successful', 'discovery_method'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "field_discovery_log",
        "inherit_condition": id == BasicDataEntry.id,
    }


# Add back-reference to Entity for dynamic field values
Entity.dynamic_field_values = relationship(
    "EntityFieldValue",
    back_populates="entity",
    foreign_keys="EntityFieldValue.entity_id",
    cascade="all, delete-orphan",
)


class Task(BasicDataEntry):
    """Persistent task queue entry for async operations.
    
    Tracks long-running tasks (LLM processing, crawling, agent operations)
    with status, progress, and results that survive server restarts.
    """
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )  # pending, running, completed, failed, cancelled
    priority: Mapped[int] = mapped_column(Integer, default=0)  # higher = more urgent
    
    # Task configuration
    params_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Results
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0 - 1.0
    progress_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_task_status_priority', 'status', 'priority'),
        Index('ix_task_type_status', 'task_type', 'status'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "task",
        "inherit_condition": id == BasicDataEntry.id,
    }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": str(self.id),
            "task_type": self.task_type,
            "status": self.status,
            "priority": self.priority,
            "params": self.params_json,
            "result": self.result_json,
            "error": self.error,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ChatPlan(BasicDataEntry):
    """Tracks a multi-step execution plan for a chat request.

    Each user question may spawn one or more plans.  A plan records the
    original prompt, a generalized task description (for pattern matching),
    and the working memory accumulated during execution.
    """
    __tablename__ = "chat_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    original_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    generalized_task: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    memory_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )  # active, completed, failed, exhausted
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    max_plan_changes: Mapped[int] = mapped_column(Integer, default=15)
    cycle_number: Mapped[int] = mapped_column(Integer, default=1)
    total_steps_executed: Mapped[int] = mapped_column(Integer, default=0)
    final_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sources_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_chat_plan_session', 'session_id'),
        Index('ix_chat_plan_status', 'status'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "chat_plan",
        "inherit_condition": id == BasicDataEntry.id,
    }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "original_prompt": self.original_prompt,
            "generalized_task": self.generalized_task,
            "plan": self.plan_json,
            "memory": self.memory_json,
            "status": self.status,
            "plan_version": self.plan_version,
            "max_plan_changes": self.max_plan_changes,
            "cycle_number": self.cycle_number,
            "total_steps_executed": self.total_steps_executed,
            "final_answer": self.final_answer,
            "sources": self.sources_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ChatPlanStep(BasicDataEntry):
    """A single step within a ChatPlan execution."""
    __tablename__ = "chat_plan_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("chat_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    tool_input: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tool_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, running, completed, failed, skipped
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    plan: Mapped["ChatPlan"] = relationship(
        "ChatPlan", foreign_keys=[plan_id], back_populates="steps"
    )

    __table_args__ = (
        Index('ix_chat_plan_step_plan', 'plan_id', 'step_index'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "chat_plan_step",
        "inherit_condition": id == BasicDataEntry.id,
    }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "plan_id": str(self.plan_id),
            "step_index": self.step_index,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            "status": self.status,
            "plan_version": self.plan_version,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


ChatPlan.steps = relationship(
    "ChatPlanStep",
    back_populates="plan",
    foreign_keys="ChatPlanStep.plan_id",
    cascade="all, delete-orphan",
    order_by="ChatPlanStep.step_index",
)


class StepPattern(BasicDataEntry):
    """Tracks successful step/plan patterns for reuse.

    A pattern captures a generalized task description with its embedding,
    the sequence of tool calls that led to a successful answer, and a
    reward score that increases when the pattern is reused successfully.
    """
    __tablename__ = "step_patterns"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    generalized_task: Mapped[str] = mapped_column(Text, nullable=False)
    tool_sequence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reward_score: Mapped[float] = mapped_column(Float, default=1.0)
    times_used: Mapped[int] = mapped_column(Integer, default=1)
    times_succeeded: Mapped[int] = mapped_column(Integer, default=1)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_step_pattern_reward', 'reward_score'),
    )

    __mapper_args__ = {
        "polymorphic_identity": "step_pattern",
        "inherit_condition": id == BasicDataEntry.id,
    }
