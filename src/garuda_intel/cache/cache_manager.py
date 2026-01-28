"""
Unified cache manager that coordinates all caching layers.
"""

import logging
from typing import Optional, List

from .embedding_cache import EmbeddingCache
from .llm_cache import LLMCache


class CacheManager:
    """
    Centralized cache manager for all caching operations.
    Coordinates embedding cache, LLM response cache, and search result cache.
    """

    def __init__(
        self,
        embedding_cache_size: int = 10000,
        llm_cache_path: str = "data/llm_cache.db",
        llm_cache_ttl: int = 604800,  # 7 days
    ):
        """
        Initialize cache manager with all cache layers.
        
        Args:
            embedding_cache_size: Maximum embeddings to cache in memory
            llm_cache_path: Path to SQLite database for LLM cache
            llm_cache_ttl: Time-to-live for LLM responses in seconds
        """
        self.logger = logging.getLogger(__name__)
        
        # Initialize cache layers
        self.embedding_cache = EmbeddingCache(maxsize=embedding_cache_size)
        self.llm_cache = LLMCache(db_path=llm_cache_path, ttl_seconds=llm_cache_ttl)
        
        self.logger.info(
            f"CacheManager initialized: "
            f"embedding_maxsize={embedding_cache_size}, "
            f"llm_cache_path={llm_cache_path}, "
            f"llm_ttl={llm_cache_ttl}s"
        )

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get cached embedding for text.
        
        Args:
            text: Input text
            
        Returns:
            Cached embedding vector or None
        """
        return self.embedding_cache.get(text)

    def cache_embedding(self, text: str, embedding: List[float]) -> None:
        """
        Cache an embedding for text.
        
        Args:
            text: Input text
            embedding: Embedding vector
        """
        self.embedding_cache.put(text, embedding)

    def get_llm_response(self, prompt: str) -> Optional[str]:
        """
        Get cached LLM response for prompt.
        
        Args:
            prompt: Input prompt
            
        Returns:
            Cached response or None
        """
        return self.llm_cache.get(prompt)

    def cache_llm_response(self, prompt: str, response: str) -> None:
        """
        Cache an LLM response.
        
        Args:
            prompt: Input prompt
            response: LLM response
        """
        self.llm_cache.put(prompt, response)

    def cleanup_expired(self) -> None:
        """Clean up expired cache entries across all cache layers."""
        self.llm_cache.cleanup_expired()

    def clear_all(self) -> None:
        """Clear all caches."""
        self.embedding_cache.clear()
        self.llm_cache.clear()
        self.logger.info("All caches cleared")

    def get_stats(self) -> dict:
        """
        Get statistics for all cache layers.
        
        Returns:
            Dictionary with stats for each cache layer
        """
        return {
            "embedding_cache": self.embedding_cache.get_stats(),
            "llm_cache": self.llm_cache.get_stats(),
        }
