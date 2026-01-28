"""
Cache for LLM responses using SQLite backend with TTL.
Reduces API costs by caching prompt-response mappings.
"""

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional


class LLMCache:
    """
    SQLite-based cache for LLM responses with TTL support.
    Persists across restarts and reduces API costs for repeated queries.
    """

    def __init__(self, db_path: str = "data/llm_cache.db", ttl_seconds: int = 604800):
        """
        Initialize LLM response cache.
        
        Args:
            db_path: Path to SQLite database file
            ttl_seconds: Time-to-live in seconds (default: 7 days)
        """
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self.logger = logging.getLogger(__name__)
        
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_db()
        self.logger.info(f"LLMCache initialized: db_path={db_path}, ttl={ttl_seconds}s")

    def _init_db(self):
        """Create cache table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                prompt_hash TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )
        """)
        
        # Create index on expiration for efficient cleanup
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at ON llm_cache(expires_at)
        """)
        
        conn.commit()
        conn.close()

    def _hash_prompt(self, prompt: str) -> str:
        """Generate hash for prompt."""
        return hashlib.sha256(prompt.encode('utf-8')).hexdigest()

    def get(self, prompt: str) -> Optional[str]:
        """
        Get cached LLM response for prompt.
        
        Args:
            prompt: Input prompt
            
        Returns:
            Cached response or None if not found or expired
        """
        prompt_hash = self._hash_prompt(prompt)
        current_time = int(time.time())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT response FROM llm_cache 
            WHERE prompt_hash = ? AND expires_at > ?
        """, (prompt_hash, current_time))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            self.logger.debug(f"LLM cache hit for hash {prompt_hash[:8]}...")
            return result[0]
        
        self.logger.debug(f"LLM cache miss for hash {prompt_hash[:8]}...")
        return None

    def put(self, prompt: str, response: str) -> None:
        """
        Cache an LLM response.
        
        Args:
            prompt: Input prompt
            response: LLM response
        """
        prompt_hash = self._hash_prompt(prompt)
        current_time = int(time.time())
        expires_at = current_time + self.ttl_seconds
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Use INSERT OR REPLACE to update existing entries
        cursor.execute("""
            INSERT OR REPLACE INTO llm_cache 
            (prompt_hash, prompt, response, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (prompt_hash, prompt, response, current_time, expires_at))
        
        conn.commit()
        conn.close()
        
        self.logger.debug(f"Cached LLM response for hash {prompt_hash[:8]}...")

    def cleanup_expired(self) -> int:
        """
        Remove expired cache entries.
        
        Returns:
            Number of entries removed
        """
        current_time = int(time.time())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM llm_cache WHERE expires_at <= ?", (current_time,))
        deleted_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            self.logger.info(f"Cleaned up {deleted_count} expired LLM cache entries")
        
        return deleted_count

    def clear(self) -> None:
        """Clear all cached responses."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM llm_cache")
        
        conn.commit()
        conn.close()
        
        self.logger.info("LLM cache cleared")

    def get_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache size and other metrics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM llm_cache")
        total_count = cursor.fetchone()[0]
        
        current_time = int(time.time())
        cursor.execute("SELECT COUNT(*) FROM llm_cache WHERE expires_at > ?", (current_time,))
        valid_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_entries": total_count,
            "valid_entries": valid_count,
            "expired_entries": total_count - valid_count,
            "ttl_seconds": self.ttl_seconds,
        }
