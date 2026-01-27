#!/usr/bin/env python3
"""
Real-World Integration Example for Phase 4

This example demonstrates how to integrate Phase 4 components into an actual
web intelligence gathering pipeline.
"""

from src.garuda_intel.discover.crawl_learner import CrawlLearner
from src.garuda_intel.explorer.scorer import URLScorer
from src.garuda_intel.extractor.iterative_refiner import IterativeRefiner
from src.garuda_intel.extractor.strategy_selector import StrategySelector
from src.garuda_intel.extractor.llm import LLMIntelExtractor
from src.garuda_intel.types.entity import EntityProfile, EntityType
from urllib.parse import urlparse


class IntelligentCrawler:
    """
    An intelligent web crawler that learns and adapts.
    
    Features:
    - Learns from crawl outcomes
    - Adapts URL scoring
    - Uses optimal extraction strategies
    - Refines intelligence with gap filling
    """
    
    def __init__(self, store, entity_name: str, entity_type: EntityType):
        """Initialize the intelligent crawler."""
        self.store = store
        self.entity_profile = EntityProfile(
            name=entity_name,
            entity_type=entity_type
        )
        
        # Initialize Phase 4 components
        self.learner = CrawlLearner(store, learning_rate=0.1, decay_days=30)
        self.scorer = URLScorer(entity_name, entity_type)
        self.llm_extractor = LLMIntelExtractor()
        self.refiner = IterativeRefiner(self.llm_extractor, store)
        self.selector = StrategySelector()
        
        print(f"Initialized intelligent crawler for: {entity_name} ({entity_type.value})")
    
    def score_url(self, url: str, link_text: str = "", depth: int = 0) -> tuple:
        """
        Score a URL with learning-enhanced scoring.
        
        Returns:
            Tuple of (score, reason)
        """
        # Get base score from URLScorer
        base_score, reason = self.scorer.score_url(url, link_text, depth)
        
        # Classify page type (simplified)
        page_type = self._classify_page_type(url)
        
        # Apply learned adjustments
        adjusted_score = self.learner.adapt_frontier_scoring(
            base_score=base_score,
            url=url,
            context={
                "page_type": page_type,
                "entity_type": self.entity_profile.entity_type.value
            }
        )
        
        # Combine reasons
        domain = urlparse(url).netloc
        reliability = self.learner.get_domain_reliability(domain)
        enhanced_reason = f"{reason} | Domain reliability: {reliability:.2f}"
        
        return adjusted_score, enhanced_reason
    
    def extract_intelligence(self, url: str, page_text: str, entity_id: str) -> dict:
        """
        Extract intelligence using optimal strategy and refinement.
        
        Args:
            url: Page URL
            page_text: Page text content
            entity_id: Entity ID for tracking
            
        Returns:
            Refined intelligence dictionary
        """
        page_type = self._classify_page_type(url)
        
        # Select optimal extraction strategy
        strategy = self.selector.select_strategy(
            self.entity_profile.entity_type,
            page_type
        )
        
        print(f"Using {strategy.__class__.__name__} for {page_type} page")
        
        # Get optimized extraction prompt
        optimized_prompt = strategy.get_extraction_prompt(
            profile=self.entity_profile,
            text=page_text[:4000],  # First 4K chars
            page_type=page_type,
            url=url
        )
        
        # Initial extraction
        initial_intel = self.llm_extractor.extract_intelligence(
            profile=self.entity_profile,
            text=page_text,
            page_type=page_type,
            url=url,
            existing_intel=None
        )
        
        print(f"Initial extraction: {self._count_fields(initial_intel)} fields populated")
        
        # Refine extraction to fill gaps
        refined_intel = self.refiner.refine_extraction(
            entity_id=entity_id,
            initial_intel=initial_intel,
            page_text=page_text,
            page_url=url,
            page_type=page_type
        )
        
        print(f"After refinement: {self._count_fields(refined_intel)} fields populated")
        
        # Validate consistency with existing data
        existing_intel = self._get_existing_intelligence(entity_id)
        if existing_intel:
            is_consistent, issues = self.refiner.validate_consistency(
                refined_intel,
                existing_intel
            )
            
            if not is_consistent:
                print(f"⚠️  Consistency issues detected: {len(issues)}")
                for issue in issues[:3]:  # Show first 3
                    print(f"    - {issue}")
        
        return refined_intel
    
    def record_outcome(self, url: str, page_type: str, intel: dict, success: bool):
        """
        Record crawl outcome for learning.
        
        Args:
            url: Crawled URL
            page_type: Classified page type
            intel: Extracted intelligence
            success: Whether extraction was successful
        """
        # Calculate intelligence quality
        quality = self._calculate_quality(intel)
        
        # Record for CrawlLearner
        self.learner.record_crawl_result(
            url=url,
            page_type=page_type,
            intel_quality=quality,
            extraction_success=success,
            entity_type=self.entity_profile.entity_type.value
        )
        
        # Update URLScorer
        domain = urlparse(url).netloc
        self.scorer.learn_domain_pattern(domain, success, quality)
        
        print(f"Recorded outcome: quality={quality:.2f}, success={success}")
    
    def get_learning_stats(self) -> dict:
        """Get learning statistics."""
        return self.learner.get_learning_stats()
    
    def get_domain_suggestions(self) -> list:
        """Get suggested domains based on learning."""
        patterns = self.learner.get_successful_patterns(
            self.entity_profile.entity_type.value
        )
        return patterns
    
    def _classify_page_type(self, url: str) -> str:
        """Classify page type from URL (simplified)."""
        url_lower = url.lower()
        
        if any(x in url_lower for x in ['about', 'company', 'who-we-are']):
            return 'official'
        elif any(x in url_lower for x in ['news', 'press', 'blog']):
            return 'news'
        elif any(x in url_lower for x in ['investor', 'ir', 'annual-report']):
            return 'official'
        elif any(x in url_lower for x in ['linkedin', 'facebook', 'twitter']):
            return 'social'
        elif any(x in url_lower for x in ['opencorporates', 'northdata', 'crunchbase']):
            return 'registry'
        else:
            return 'general'
    
    def _calculate_quality(self, intel: dict) -> float:
        """Calculate intelligence quality score (0-1)."""
        if not intel:
            return 0.0
        
        score = 0.0
        weights = {
            "basic_info": 0.3,
            "persons": 0.2,
            "locations": 0.1,
            "financials": 0.2,
            "products": 0.1,
            "events": 0.1
        }
        
        for field, weight in weights.items():
            if field == "basic_info":
                basic = intel.get(field, {})
                if basic:
                    filled = sum(1 for v in basic.values() if v)
                    score += weight * (filled / max(1, len(basic)))
            else:
                items = intel.get(field, [])
                if items:
                    score += weight
        
        return min(1.0, score)
    
    def _count_fields(self, intel: dict) -> int:
        """Count populated fields in intelligence."""
        if not intel:
            return 0
        
        count = 0
        
        # Count basic_info fields
        basic = intel.get("basic_info", {})
        count += sum(1 for v in basic.values() if v)
        
        # Count list fields
        for field in ["persons", "locations", "financials", "products", "events"]:
            items = intel.get(field, [])
            count += len(items)
        
        return count
    
    def _get_existing_intelligence(self, entity_id: str) -> list:
        """Get existing intelligence for entity (stub)."""
        # In real implementation, query from store
        # return self.store.get_intelligence(entity_id=entity_id)
        return []


def demo_intelligent_crawler():
    """Demonstrate the intelligent crawler in action."""
    print("=" * 70)
    print("INTELLIGENT CRAWLER DEMONSTRATION")
    print("=" * 70)
    
    # Mock store for demo
    class MockStore:
        pass
    
    store = MockStore()
    
    # Create crawler for Microsoft
    crawler = IntelligentCrawler(
        store=store,
        entity_name="Microsoft Corporation",
        entity_type=EntityType.COMPANY
    )
    
    print("\n" + "-" * 70)
    print("PHASE 1: URL SCORING WITH LEARNING")
    print("-" * 70)
    
    # Score some candidate URLs
    test_urls = [
        ("https://microsoft.com/en-us/about", "About Microsoft"),
        ("https://microsoft.com/investor", "Investor Relations"),
        ("https://news.microsoft.com/latest", "Latest News"),
        ("https://linkedin.com/company/microsoft", "LinkedIn Profile"),
    ]
    
    for url, link_text in test_urls:
        score, reason = crawler.score_url(url, link_text, depth=1)
        print(f"\nURL: {url}")
        print(f"  Score: {score:.1f}")
        print(f"  Reason: {reason[:80]}...")
    
    print("\n" + "-" * 70)
    print("PHASE 2: SIMULATED CRAWL CYCLE")
    print("-" * 70)
    
    # Simulate crawling top URL
    best_url = "https://microsoft.com/en-us/about"
    page_text = """
    Microsoft Corporation is an American multinational technology corporation.
    Founded in 1975 by Bill Gates and Paul Allen.
    Headquartered in Redmond, Washington.
    CEO: Satya Nadella
    Products: Windows, Office, Azure, Xbox
    """
    
    print(f"\n📄 Crawling: {best_url}")
    print("📝 Extracting intelligence...")
    
    # Extract intelligence (would be real extraction in production)
    # For demo, simulate with mock data
    mock_intel = {
        "basic_info": {
            "official_name": "Microsoft Corporation",
            "founded": "1975",
            "industry": "Technology"
        },
        "persons": [
            {"name": "Satya Nadella", "title": "CEO"}
        ],
        "locations": [
            {"city": "Redmond", "country": "USA"}
        ]
    }
    
    print(f"✓ Extracted {crawler._count_fields(mock_intel)} fields")
    
    print("\n" + "-" * 70)
    print("PHASE 3: RECORDING OUTCOME & LEARNING")
    print("-" * 70)
    
    # Record successful crawl
    crawler.record_outcome(
        url=best_url,
        page_type="official",
        intel=mock_intel,
        success=True
    )
    
    # Show learning stats
    stats = crawler.get_learning_stats()
    print(f"\n📊 Learning Statistics:")
    print(f"  Total domains tracked: {stats['total_domains']}")
    print(f"  Total page patterns: {stats['total_page_patterns']}")
    print(f"  High confidence patterns: {stats['high_confidence_patterns']}")
    
    # Get suggestions
    print(f"\n💡 Suggested patterns for company entities:")
    patterns = crawler.get_domain_suggestions()
    for pattern in patterns[:3]:
        print(f"  - {pattern['page_type']}: quality={pattern['avg_quality']:.2f}, confidence={pattern['confidence']:.2f}")
    
    print("\n" + "=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    print("\n✨ The crawler is now smarter:")
    print("  • Learned microsoft.com is reliable")
    print("  • Official pages give high-quality intelligence")
    print("  • Future microsoft.com URLs will get boosted scores")
    print("  • Extraction strategies are optimized per entity type")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    demo_intelligent_crawler()
