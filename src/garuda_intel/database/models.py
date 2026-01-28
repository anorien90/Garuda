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
        return str(uuid.UUID(str(value)))

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
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String, nullable=False)
    # Type information for source and target nodes (e.g., "entity", "page", "intelligence")
    # These are optional for backward compatibility with existing data
    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    source_entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[source_id], back_populates="outgoing_relationships"
    )
    target_entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[target_id], back_populates="incoming_relationships"
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
    page_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    domain_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_fetch_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    text_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )

    entity: Mapped["Entity"] = relationship(
        "Entity", back_populates="pages", foreign_keys=[entity_id]
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
        GUID(), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False
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
        GUID(), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[entity_id], back_populates="intelligence"
    )
    page: Mapped["Page"] = relationship(
        "Page", foreign_keys=[page_id], back_populates="intelligence"
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
