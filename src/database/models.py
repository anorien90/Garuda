from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

Base = declarative_base()

class Intelligence(Base):
    __tablename__ = "intelligence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_name: Mapped[str] = mapped_column(String)
    data: Mapped[str] = mapped_column(Text)  # JSON string of the finding
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Seed(Base):
    __tablename__ = "seeds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String)
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Page(Base):
    __tablename__ = "pages"
    url: Mapped[str] = mapped_column(String, primary_key=True)
    page_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    domain_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_fetch_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    text_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def to_dict(self):
        return {
            "url": self.url,
            "entity_type": self.entity_type,
            "domain_key": self.domain_key,
            "depth": self.depth,
            "score": self.score,
            "page_type": self.page_type,
            "last_status": self.last_status,
            "last_fetch_at": self.last_fetch_at,
            "text_length": self.text_length,
        }

class PageContent(Base):
    __tablename__ = "page_content"
    page_url: Mapped[str] = mapped_column(String, primary_key=True)
    html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetch_ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Link(Base):
    __tablename__ = "links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_url: Mapped[str] = mapped_column(String)
    to_url: Mapped[str] = mapped_column(String)
    anchor_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Fingerprint(Base):
    __tablename__ = "fingerprints"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_url: Mapped[str] = mapped_column(String)
    selector: Mapped[str] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(String)
    sample_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Pattern(Base):
    __tablename__ = "patterns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pattern: Mapped[str] = mapped_column(String)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Domain(Base):
    __tablename__ = "domains"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    domain: Mapped[str] = mapped_column(String)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_official: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0/1
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)  # person, company, product, location, event, entity
    data: Mapped[str] = mapped_column(Text)   # JSON blob of merged attributes
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
