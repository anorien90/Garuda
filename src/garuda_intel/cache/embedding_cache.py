"""
LRU-based in-memory cache for embeddings to avoid redundant generation.
"""

import hashlib
import logging
from functools import lru_cache
from typing import Optional, List
import numpy as np


class EmbeddingCache:
    """
    LRU-based in-memory cache for text embeddings.
    Reduces redundant embedding generation for frequently accessed content.
    """

    def __init__(self, maxsize: int = 10000):
        """
        Initialize embedding cache with LRU eviction.
        
        Args:
            maxsize: Maximum number of embeddings to cache
        """
        self.maxsize = maxsize
        self.logger = logging.getLogger(__name__)
        # Use dict for simple cache implementation with hash-based lookup
        self._cache: dict[str, List[float]] = {}
        self._hits = 0
        self._misses = 0
        self.logger.info(f"EmbeddingCache initialized with maxsize={maxsize}")

    def _hash_text(self, text: str) -> str:
        """Generate hash for text content."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def get(self, text: str) -> Optional[List[float]]:
        """
        Get cached embedding for text.
        
        Args:
            text: Input text
            
        Returns:
            Cached embedding vector or None if not found
        """
        text_hash = self._hash_text(text)
        
        if text_hash in self._cache:
            self._hits += 1
            self.logger.debug(f"Embedding cache hit for hash {text_hash[:8]}...")
            return self._cache[text_hash]
        
        self._misses += 1
        self.logger.debug(f"Embedding cache miss for hash {text_hash[:8]}...")
        return None

    def put(self, text: str, embedding: List[float]) -> None:
        """
        Cache an embedding for text.
        
        Args:
            text: Input text
            embedding: Embedding vector
        """
        text_hash = self._hash_text(text)
        
        # Simple LRU: remove oldest if at capacity
        if len(self._cache) >= self.maxsize:
            # Remove first item (oldest in insertion order for Python 3.7+)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            
        self._cache[text_hash] = embedding
        self.logger.debug(f"Cached embedding for hash {text_hash[:8]}...")

    def clear(self) -> None:
        """Clear all cached embeddings."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        self.logger.info("Embedding cache cleared")

    def get_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache hits, misses, and hit rate
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "size": len(self._cache),
            "maxsize": self.maxsize,
        }
