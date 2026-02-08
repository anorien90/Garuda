"""
Crawl Learning and Adaptation System.

This module tracks successful crawl patterns to improve future discovery strategies.
It learns from domain reliability, page types, and extraction success to optimize crawling.
"""

import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import json

from ..database.store import PersistenceStore


@dataclass
class CrawlOutcome:
    """Record of a single crawl outcome."""
    url: str
    domain: str
    page_type: str
    entity_type: str
    intel_quality: float
    extraction_success: bool
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DomainStats:
    """Aggregated statistics for a domain."""
    domain: str
    total_crawls: int = 0
    successful_crawls: int = 0
    avg_intel_quality: float = 0.0
    page_type_distribution: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    entity_type_distribution: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    
    def reliability_score(self, decay_days: float = 30.0) -> float:
        """Calculate reliability score with time decay."""
        if self.total_crawls == 0:
            return 0.0
        
        success_rate = self.successful_crawls / self.total_crawls
        quality_score = self.avg_intel_quality
        
        # Apply time decay - older data is less reliable
        age_days = (time.time() - self.last_seen) / 86400
        decay_factor = max(0.0, 1.0 - (age_days / decay_days))
        
        # Combined score: success rate (40%) + quality (40%) + recency (20%)
        return (success_rate * 0.4 + quality_score * 0.4) * (0.8 + decay_factor * 0.2)


@dataclass
class PageTypePattern:
    """Pattern learned for a specific page type."""
    page_type: str
    entity_type: str
    success_count: int = 0
    total_count: int = 0
    avg_quality: float = 0.0
    extraction_hints: List[str] = field(default_factory=list)
    confidence: float = 0.0
    
    def update_confidence(self):
        """Update confidence based on sample size and success rate."""
        if self.total_count == 0:
            self.confidence = 0.0
            return
        
        success_rate = self.success_count / self.total_count
        # Confidence increases with both success rate and sample size
        sample_factor = min(1.0, self.total_count / 10.0)  # Full confidence at 10+ samples
        self.confidence = success_rate * sample_factor


class CrawlLearner:
    """
    Learns from successful crawls to improve future strategies.
    
    Tracks:
    - Domain patterns and reliability
    - Page type extraction success
    - Entity-specific patterns
    - Temporal trends
    """
    
    def __init__(self, store: Optional[PersistenceStore] = None, learning_rate: float = 0.1, decay_days: float = 30.0):
        """
        Initialize the crawl learner.
        
        Args:
            store: Persistence store for saving/loading learned patterns
            learning_rate: How quickly to adapt to new information (0-1)
            decay_days: Days after which old patterns start to decay
        """
        self.store = store
        self.learning_rate = learning_rate
        self.decay_days = decay_days
        self.logger = logging.getLogger(__name__)
        
        if not store:
            self.logger.warning("CrawlLearner initialized without a persistence store; patterns will not be persisted")
        
        # In-memory caches
        self._domain_stats: Dict[str, DomainStats] = {}
        self._page_type_patterns: Dict[str, PageTypePattern] = {}
        self._entity_patterns: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._recent_outcomes: List[CrawlOutcome] = []
        self._max_recent = 1000
        
        # Load existing patterns from database
        if self.store:
            self._load_patterns()
    
    def record_crawl_result(
        self, 
        url: str, 
        page_type: str, 
        intel_quality: float,
        extraction_success: bool,
        entity_type: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record the outcome of a crawl for learning.
        
        Args:
            url: URL that was crawled
            page_type: Classified page type (e.g., 'official', 'news', 'registry')
            intel_quality: Quality score of extracted intelligence (0-1)
            extraction_success: Whether extraction succeeded
            entity_type: Type of entity being researched
            metadata: Additional context about the crawl
        """
        from urllib.parse import urlparse
        
        domain = urlparse(url).netloc.lower().replace("www.", "")
        
        outcome = CrawlOutcome(
            url=url,
            domain=domain,
            page_type=page_type,
            entity_type=entity_type,
            intel_quality=intel_quality,
            extraction_success=extraction_success,
            metadata=metadata or {}
        )
        
        # Update domain statistics
        self._update_domain_stats(outcome)
        
        # Update page type patterns
        self._update_page_type_patterns(outcome)
        
        # Update entity-specific patterns
        self._update_entity_patterns(outcome)
        
        # Keep recent outcomes for analysis
        self._recent_outcomes.append(outcome)
        if len(self._recent_outcomes) > self._max_recent:
            self._recent_outcomes.pop(0)
        
        # Periodically persist patterns
        if self.store and len(self._recent_outcomes) % 50 == 0:
            self._save_patterns()
        
        self.logger.debug(
            f"Recorded crawl: {domain} | {page_type} | quality={intel_quality:.2f} | success={extraction_success}"
        )
    
    def get_domain_reliability(self, domain: str) -> float:
        """
        Get reliability score for a domain based on past crawls.
        
        Args:
            domain: Domain name
            
        Returns:
            Reliability score (0-1), 0.5 if unknown
        """
        domain = domain.lower().replace("www.", "")
        stats = self._domain_stats.get(domain)
        
        if not stats:
            # Unknown domain - return neutral score
            return 0.5
        
        return stats.reliability_score(self.decay_days)
    
    def suggest_page_strategy(self, url: str, page_type: str, entity_type: str = "") -> Dict[str, Any]:
        """
        Suggest extraction strategy based on learned patterns.
        
        Args:
            url: Target URL
            page_type: Classified page type
            entity_type: Entity type being researched
            
        Returns:
            Dictionary with strategy suggestions including confidence, extraction hints
        """
        from urllib.parse import urlparse
        
        domain = urlparse(url).netloc.lower().replace("www.", "")
        
        # Get domain reliability
        domain_reliability = self.get_domain_reliability(domain)
        
        # Get page type pattern
        pattern_key = f"{entity_type}:{page_type}"
        pattern = self._page_type_patterns.get(pattern_key)
        
        # Build strategy
        strategy = {
            "domain_reliability": domain_reliability,
            "expected_quality": 0.5,  # default
            "extraction_hints": [],
            "confidence": 0.0,
            "recommended_timeout": 120,
            "chunk_size": 4000,
        }
        
        if pattern:
            strategy["expected_quality"] = pattern.avg_quality
            strategy["extraction_hints"] = pattern.extraction_hints
            strategy["confidence"] = pattern.confidence
            
            # Adjust based on pattern confidence
            if pattern.confidence > 0.8:
                strategy["recommended_timeout"] = 90  # faster for known patterns
            elif pattern.confidence < 0.3:
                strategy["recommended_timeout"] = 150  # slower for uncertain patterns
        
        # Domain-specific adjustments
        domain_stats = self._domain_stats.get(domain)
        if domain_stats and domain_stats.total_crawls >= 5:
            # For well-known domains, use historical quality
            strategy["expected_quality"] = domain_stats.avg_intel_quality
        
        return strategy
    
    def get_successful_patterns(self, entity_type: str) -> List[Dict]:
        """
        Get patterns that have been successful for an entity type.
        
        Args:
            entity_type: Entity type (e.g., 'company', 'person')
            
        Returns:
            List of successful patterns with domains, page types, quality scores
        """
        patterns = []
        
        # Find patterns with high success for this entity type
        for key, pattern in self._page_type_patterns.items():
            if pattern.entity_type == entity_type and pattern.confidence > 0.5:
                patterns.append({
                    "page_type": pattern.page_type,
                    "success_rate": pattern.success_count / max(1, pattern.total_count),
                    "avg_quality": pattern.avg_quality,
                    "confidence": pattern.confidence,
                    "sample_size": pattern.total_count,
                })
        
        # Sort by combined score
        patterns.sort(key=lambda x: x["confidence"] * x["avg_quality"], reverse=True)
        
        return patterns[:10]  # Top 10 patterns
    
    def adapt_frontier_scoring(self, base_score: float, url: str, context: Dict) -> float:
        """
        Adjust URL score based on learned patterns.
        
        Args:
            base_score: Initial score from URLScorer
            url: Target URL
            context: Additional context (page_type, entity_type, etc.)
            
        Returns:
            Adjusted score
        """
        from urllib.parse import urlparse
        
        domain = urlparse(url).netloc.lower().replace("www.", "")
        page_type = context.get("page_type", "")
        entity_type = context.get("entity_type", "")
        
        adjustment = 0.0
        
        # Domain reliability boost/penalty
        reliability = self.get_domain_reliability(domain)
        if reliability > 0.7:
            adjustment += 20.0  # Boost reliable domains
        elif reliability < 0.3:
            adjustment -= 15.0  # Penalize unreliable domains
        
        # Page type pattern boost
        if page_type and entity_type:
            pattern_key = f"{entity_type}:{page_type}"
            pattern = self._page_type_patterns.get(pattern_key)
            if pattern and pattern.confidence > 0.6:
                # Boost based on historical quality
                adjustment += pattern.avg_quality * 25.0
        
        # Apply learning rate to smooth adjustments
        adjustment *= self.learning_rate
        
        return base_score + adjustment
    
    def _update_domain_stats(self, outcome: CrawlOutcome) -> None:
        """Update domain statistics with new outcome."""
        stats = self._domain_stats.get(outcome.domain)
        
        if not stats:
            stats = DomainStats(domain=outcome.domain)
            self._domain_stats[outcome.domain] = stats
        
        # Update counts
        stats.total_crawls += 1
        if outcome.extraction_success:
            stats.successful_crawls += 1
        
        # Update running average of quality (exponential moving average)
        alpha = self.learning_rate
        stats.avg_intel_quality = (
            alpha * outcome.intel_quality + (1 - alpha) * stats.avg_intel_quality
        )
        
        # Update distributions
        stats.page_type_distribution[outcome.page_type] += 1
        stats.entity_type_distribution[outcome.entity_type] += 1
        stats.last_seen = outcome.timestamp
    
    def _update_page_type_patterns(self, outcome: CrawlOutcome) -> None:
        """Update page type patterns with new outcome."""
        if not outcome.page_type or not outcome.entity_type:
            return
        
        pattern_key = f"{outcome.entity_type}:{outcome.page_type}"
        pattern = self._page_type_patterns.get(pattern_key)
        
        if not pattern:
            pattern = PageTypePattern(
                page_type=outcome.page_type,
                entity_type=outcome.entity_type
            )
            self._page_type_patterns[pattern_key] = pattern
        
        # Update counts
        pattern.total_count += 1
        if outcome.extraction_success:
            pattern.success_count += 1
        
        # Update quality (exponential moving average)
        alpha = self.learning_rate
        pattern.avg_quality = (
            alpha * outcome.intel_quality + (1 - alpha) * pattern.avg_quality
        )
        
        # Update confidence
        pattern.update_confidence()
        
        # Extract hints from metadata
        if outcome.extraction_success and outcome.metadata:
            hints = outcome.metadata.get("extraction_hints", [])
            for hint in hints:
                if hint not in pattern.extraction_hints:
                    pattern.extraction_hints.append(hint)
    
    def _update_entity_patterns(self, outcome: CrawlOutcome) -> None:
        """Update entity-specific patterns."""
        if not outcome.entity_type:
            return
        
        entity_data = self._entity_patterns[outcome.entity_type]
        
        # Track successful domains for this entity type
        if "successful_domains" not in entity_data:
            entity_data["successful_domains"] = defaultdict(int)
        
        if outcome.extraction_success:
            entity_data["successful_domains"][outcome.domain] += 1
    
    def _load_patterns(self) -> None:
        """Load learned patterns from database."""
        try:
            # Try to load patterns from a dedicated patterns table
            # For now, use a simple approach - this can be enhanced later
            self.logger.info("Loading learned patterns from database...")
            
            # Load patterns using the store (if available)
            # This is a placeholder - actual implementation would query a dedicated table
            
        except Exception as e:
            self.logger.warning(f"Could not load patterns: {e}")
    
    def _save_patterns(self) -> None:
        """Save learned patterns to database."""
        try:
            # Serialize and save patterns
            # This is a placeholder for actual persistence
            # In production, this would save to dedicated learning tables
            
            self.logger.debug(
                f"Patterns snapshot: {len(self._domain_stats)} domains, "
                f"{len(self._page_type_patterns)} page patterns"
            )
            
        except Exception as e:
            self.logger.warning(f"Could not save patterns: {e}")
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """Get summary statistics about learned patterns."""
        return {
            "total_domains": len(self._domain_stats),
            "total_page_patterns": len(self._page_type_patterns),
            "total_crawls_recorded": len(self._recent_outcomes),
            "high_confidence_patterns": sum(
                1 for p in self._page_type_patterns.values() if p.confidence > 0.7
            ),
            "reliable_domains": sum(
                1 for d in self._domain_stats.values() 
                if d.reliability_score(self.decay_days) > 0.7
            ),
        }
