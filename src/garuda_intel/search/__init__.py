"""Search module for Garuda Intel - entity-aware web crawling and intelligence gathering.

This module provides the main entry point and public API for the search functionality.
"""

# Re-export types that are used by other modules
from ..types.entity import EntityProfile, EntityType
from ..explorer.engine import IntelligentExplorer
from ..discover.crawl_modes import CrawlMode

# Import main functions
from .handlers import (
    handle_intel,
    handle_run,
    perform_rag_search,
    interactive_chat,
)
from .run_crawl_api import run_crawl_api
from .seed_discovery import collect_candidates_simple

# Export all public API
__all__ = [
    # Types
    "EntityProfile",
    "EntityType",
    "IntelligentExplorer",
    "CrawlMode",
    # Main handlers
    "handle_intel",
    "handle_run",
    "perform_rag_search",
    "interactive_chat",
    "run_crawl_api",
    # Helper functions
    "collect_candidates_simple",
]
