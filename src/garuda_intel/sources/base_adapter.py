"""Base adapter for multi-source intelligence aggregation.

This module provides the abstract base class for source adapters that enable
Garuda to fetch and normalize intelligence from diverse sources beyond web crawling.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum


class SourceType(Enum):
    """Type of intelligence source."""
    WEB = "web"
    PDF = "pdf"
    API = "api"
    DATABASE = "database"
    SOCIAL_MEDIA = "social_media"
    STRUCTURED_DATA = "structured_data"


@dataclass
class Document:
    """Normalized document from any source.
    
    Attributes:
        id: Unique document identifier
        source_type: Type of source (PDF, API, etc.)
        url: Source URL or identifier
        title: Document title
        content: Extracted text content
        metadata: Additional metadata (author, date, etc.)
        confidence: Extraction confidence score (0.0-1.0)
        timestamp: When the document was fetched
    """
    id: str
    source_type: SourceType
    url: str
    title: Optional[str]
    content: str
    metadata: Dict[str, Any]
    confidence: float = 1.0
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class SourceAdapter(ABC):
    """Abstract base class for source adapters.
    
    Each adapter implements methods to:
    1. Fetch raw data from a specific source type
    2. Normalize the data into a common Document format
    3. Validate and score the quality of extracted data
    
    This enables Garuda to aggregate intelligence from diverse sources
    with a unified interface.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the adapter with optional configuration.
        
        Args:
            config: Adapter-specific configuration (API keys, paths, etc.)
        """
        self.config = config or {}
        self._cache: Dict[str, Document] = {}
    
    @abstractmethod
    def fetch(self, query: str, **kwargs) -> List[Document]:
        """Fetch documents from the source based on a query.
        
        Args:
            query: Search query or identifier
            **kwargs: Additional source-specific parameters
            
        Returns:
            List of normalized Document objects
            
        Raises:
            SourceAdapterError: If fetching fails
        """
        pass
    
    @abstractmethod
    def normalize(self, raw_data: Any) -> Document:
        """Normalize raw source data into a Document.
        
        Args:
            raw_data: Source-specific raw data
            
        Returns:
            Normalized Document object
            
        Raises:
            NormalizationError: If normalization fails
        """
        pass
    
    def validate(self, document: Document) -> bool:
        """Validate document quality and completeness.
        
        Args:
            document: Document to validate
            
        Returns:
            True if document is valid and usable
        """
        if not document.content or len(document.content.strip()) < 10:
            return False
        if document.confidence < 0.3:
            return False
        return True
    
    def get_from_cache(self, key: str) -> Optional[Document]:
        """Get document from cache.
        
        Args:
            key: Cache key (usually URL or ID)
            
        Returns:
            Cached document or None
        """
        return self._cache.get(key)
    
    def add_to_cache(self, key: str, document: Document):
        """Add document to cache.
        
        Args:
            key: Cache key
            document: Document to cache
        """
        self._cache[key] = document
    
    def clear_cache(self):
        """Clear the adapter cache."""
        self._cache.clear()


class SourceAdapterError(Exception):
    """Base exception for source adapter errors."""
    pass


class NormalizationError(SourceAdapterError):
    """Exception raised when normalization fails."""
    pass


class FetchError(SourceAdapterError):
    """Exception raised when fetching fails."""
    pass
