"""
Unit tests for caching functionality.

Tests the embedding cache, LLM cache, and cache manager.
"""

import pytest
import tempfile
import os
from pathlib import Path

from garuda_intel.cache import CacheManager, EmbeddingCache, LLMCache


class TestEmbeddingCache:
    """Test in-memory embedding cache."""
    
    def test_cache_initialization(self):
        """Test cache initializes correctly."""
        cache = EmbeddingCache(maxsize=100)
        assert cache.maxsize == 100
        stats = cache.get_stats()
        assert stats['size'] == 0
        assert stats['hits'] == 0
        assert stats['misses'] == 0
    
    def test_cache_put_and_get(self):
        """Test putting and getting embeddings."""
        cache = EmbeddingCache(maxsize=10)
        
        text = "test document"
        embedding = [0.1, 0.2, 0.3, 0.4]
        
        # Cache the embedding
        cache.put(text, embedding)
        
        # Retrieve it
        cached = cache.get(text)
        assert cached == embedding
        
        # Check stats
        stats = cache.get_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 0
        assert stats['size'] == 1
    
    def test_cache_miss(self):
        """Test cache miss."""
        cache = EmbeddingCache(maxsize=10)
        
        # Try to get non-existent embedding
        cached = cache.get("nonexistent text")
        assert cached is None
        
        # Check stats
        stats = cache.get_stats()
        assert stats['hits'] == 0
        assert stats['misses'] == 1
    
    def test_cache_hit_rate(self):
        """Test cache hit rate calculation."""
        cache = EmbeddingCache(maxsize=10)
        
        # Add some embeddings
        cache.put("text1", [0.1, 0.2])
        cache.put("text2", [0.3, 0.4])
        
        # Hit and miss
        cache.get("text1")  # hit
        cache.get("text2")  # hit
        cache.get("text3")  # miss
        
        stats = cache.get_stats()
        assert stats['hits'] == 2
        assert stats['misses'] == 1
        assert abs(stats['hit_rate'] - 0.667) < 0.01
    
    def test_cache_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = EmbeddingCache(maxsize=3)
        
        # Fill cache
        cache.put("text1", [0.1])
        cache.put("text2", [0.2])
        cache.put("text3", [0.3])
        
        assert cache.get_stats()['size'] == 3
        
        # Add one more (should evict oldest)
        cache.put("text4", [0.4])
        
        # Cache should still be at max size
        assert cache.get_stats()['size'] == 3
        
        # Oldest entry should be evicted
        assert cache.get("text1") is None  # Should be evicted
        assert cache.get("text4") is not None  # Should exist
    
    def test_cache_clear(self):
        """Test clearing the cache."""
        cache = EmbeddingCache(maxsize=10)
        
        cache.put("text1", [0.1])
        cache.put("text2", [0.2])
        
        assert cache.get_stats()['size'] == 2
        
        cache.clear()
        
        stats = cache.get_stats()
        assert stats['size'] == 0
        assert stats['hits'] == 0
        assert stats['misses'] == 0


class TestLLMCache:
    """Test SQLite-based LLM response cache."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_cache.db")
            yield db_path
    
    def test_cache_initialization(self, temp_db):
        """Test cache initializes and creates database."""
        cache = LLMCache(db_path=temp_db, ttl_seconds=3600)
        
        # Database file should exist
        assert os.path.exists(temp_db)
        
        stats = cache.get_stats()
        assert stats['total_entries'] == 0
        assert stats['valid_entries'] == 0
    
    def test_cache_put_and_get(self, temp_db):
        """Test caching and retrieving LLM responses."""
        cache = LLMCache(db_path=temp_db, ttl_seconds=3600)
        
        prompt = "What is the capital of France?"
        response = "The capital of France is Paris."
        
        # Cache the response
        cache.put(prompt, response)
        
        # Retrieve it
        cached = cache.get(prompt)
        assert cached == response
        
        stats = cache.get_stats()
        assert stats['total_entries'] == 1
        assert stats['valid_entries'] == 1
    
    def test_cache_miss(self, temp_db):
        """Test cache miss."""
        cache = LLMCache(db_path=temp_db, ttl_seconds=3600)
        
        cached = cache.get("nonexistent prompt")
        assert cached is None
    
    def test_cache_expiration(self, temp_db):
        """Test that expired entries are not returned."""
        # Create cache with 0 second TTL (immediately expires)
        cache = LLMCache(db_path=temp_db, ttl_seconds=0)
        
        prompt = "Test prompt"
        response = "Test response"
        
        cache.put(prompt, response)
        
        # Should be expired immediately
        cached = cache.get(prompt)
        assert cached is None
        
        # Stats should show expired entry
        stats = cache.get_stats()
        assert stats['total_entries'] == 1
        assert stats['valid_entries'] == 0
        assert stats['expired_entries'] == 1
    
    def test_cache_cleanup(self, temp_db):
        """Test cleaning up expired entries."""
        cache = LLMCache(db_path=temp_db, ttl_seconds=0)
        
        # Add entries that expire immediately
        cache.put("prompt1", "response1")
        cache.put("prompt2", "response2")
        
        stats = cache.get_stats()
        assert stats['total_entries'] == 2
        
        # Clean up expired entries
        deleted = cache.cleanup_expired()
        assert deleted == 2
        
        stats = cache.get_stats()
        assert stats['total_entries'] == 0
    
    def test_cache_update(self, temp_db):
        """Test updating an existing cache entry."""
        cache = LLMCache(db_path=temp_db, ttl_seconds=3600)
        
        prompt = "Test prompt"
        
        # Add initial response
        cache.put(prompt, "response1")
        assert cache.get(prompt) == "response1"
        
        # Update with new response
        cache.put(prompt, "response2")
        assert cache.get(prompt) == "response2"
        
        # Should still be only one entry
        stats = cache.get_stats()
        assert stats['total_entries'] == 1
    
    def test_cache_persistence(self, temp_db):
        """Test that cache persists across instances."""
        # Create cache and add entry
        cache1 = LLMCache(db_path=temp_db, ttl_seconds=3600)
        cache1.put("prompt", "response")
        
        # Create new cache instance with same db
        cache2 = LLMCache(db_path=temp_db, ttl_seconds=3600)
        
        # Should retrieve cached value
        assert cache2.get("prompt") == "response"
    
    def test_cache_clear(self, temp_db):
        """Test clearing all cache entries."""
        cache = LLMCache(db_path=temp_db, ttl_seconds=3600)
        
        cache.put("prompt1", "response1")
        cache.put("prompt2", "response2")
        
        assert cache.get_stats()['total_entries'] == 2
        
        cache.clear()
        
        assert cache.get_stats()['total_entries'] == 0


class TestCacheManager:
    """Test unified cache manager."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_cache.db")
            yield db_path
    
    def test_cache_manager_initialization(self, temp_db):
        """Test cache manager initializes all caches."""
        manager = CacheManager(
            embedding_cache_size=100,
            llm_cache_path=temp_db,
            llm_cache_ttl=3600
        )
        
        assert manager.embedding_cache is not None
        assert manager.llm_cache is not None
    
    def test_embedding_cache_operations(self, temp_db):
        """Test embedding cache operations through manager."""
        manager = CacheManager(
            embedding_cache_size=10,
            llm_cache_path=temp_db
        )
        
        text = "test text"
        embedding = [0.1, 0.2, 0.3]
        
        # Should be cache miss initially
        assert manager.get_embedding(text) is None
        
        # Cache the embedding
        manager.cache_embedding(text, embedding)
        
        # Should be cache hit now
        assert manager.get_embedding(text) == embedding
    
    def test_llm_cache_operations(self, temp_db):
        """Test LLM cache operations through manager."""
        manager = CacheManager(
            llm_cache_path=temp_db,
            llm_cache_ttl=3600
        )
        
        prompt = "test prompt"
        response = "test response"
        
        # Should be cache miss initially
        assert manager.get_llm_response(prompt) is None
        
        # Cache the response
        manager.cache_llm_response(prompt, response)
        
        # Should be cache hit now
        assert manager.get_llm_response(prompt) == response
    
    def test_get_stats(self, temp_db):
        """Test getting statistics for all caches."""
        manager = CacheManager(
            embedding_cache_size=10,
            llm_cache_path=temp_db
        )
        
        # Add some data
        manager.cache_embedding("text", [0.1, 0.2])
        manager.cache_llm_response("prompt", "response")
        
        stats = manager.get_stats()
        
        assert 'embedding_cache' in stats
        assert 'llm_cache' in stats
        assert stats['embedding_cache']['size'] == 1
        assert stats['llm_cache']['total_entries'] == 1
    
    def test_clear_all(self, temp_db):
        """Test clearing all caches."""
        manager = CacheManager(
            embedding_cache_size=10,
            llm_cache_path=temp_db
        )
        
        # Add some data
        manager.cache_embedding("text", [0.1, 0.2])
        manager.cache_llm_response("prompt", "response")
        
        # Clear all caches
        manager.clear_all()
        
        # All caches should be empty
        stats = manager.get_stats()
        assert stats['embedding_cache']['size'] == 0
        assert stats['llm_cache']['total_entries'] == 0
    
    def test_cleanup_expired(self, temp_db):
        """Test cleanup of expired entries."""
        manager = CacheManager(
            llm_cache_path=temp_db,
            llm_cache_ttl=0  # Expire immediately
        )
        
        # Add entry that expires immediately
        manager.cache_llm_response("prompt", "response")
        
        # Run cleanup
        manager.cleanup_expired()
        
        # Entry should be removed
        stats = manager.get_stats()
        assert stats['llm_cache']['total_entries'] == 0
