#!/usr/bin/env python3
"""
Basic integration test for Phase 4 components.
Tests that all components work together correctly.
"""

import sys
from src.garuda_intel.discover.crawl_learner import CrawlLearner, CrawlOutcome, DomainStats
from src.garuda_intel.explorer.scorer import URLScorer
from src.garuda_intel.extractor.strategy_selector import StrategySelector
from src.garuda_intel.types.entity import EntityProfile, EntityType


def test_crawl_learner_basic():
    """Test CrawlLearner basic functionality."""
    print("Testing CrawlLearner...")
    
    # Create mock store (simplified)
    class MockStore:
        pass
    
    store = MockStore()
    learner = CrawlLearner(store, learning_rate=0.1, decay_days=30)
    
    # Record some crawl outcomes
    learner.record_crawl_result(
        url="https://example.com/about",
        page_type="official",
        intel_quality=0.9,
        extraction_success=True,
        entity_type="company"
    )
    
    learner.record_crawl_result(
        url="https://example.com/news",
        page_type="news",
        intel_quality=0.75,
        extraction_success=True,
        entity_type="company"
    )
    
    # Get domain reliability
    reliability = learner.get_domain_reliability("example.com")
    assert 0.0 <= reliability <= 1.0, "Reliability should be 0-1"
    print(f"  Domain reliability: {reliability:.3f}")
    
    # Get strategy suggestion
    strategy = learner.suggest_page_strategy(
        url="https://example.com/contact",
        page_type="official",
        entity_type="company"
    )
    assert "domain_reliability" in strategy
    assert "expected_quality" in strategy
    print(f"  Strategy confidence: {strategy['confidence']:.3f}")
    
    # Get learning stats
    stats = learner.get_learning_stats()
    assert stats["total_domains"] >= 1
    print(f"  Tracked domains: {stats['total_domains']}")
    
    print("  ✓ CrawlLearner tests passed")


def test_url_scorer_learning():
    """Test URLScorer learning capabilities."""
    print("\nTesting URLScorer learning...")
    
    scorer = URLScorer("Test Company", EntityType.COMPANY)
    
    # Learn from multiple crawls
    for i in range(5):
        scorer.learn_domain_pattern("example.com", True, 0.85)
    
    boost = scorer.get_learned_boost("example.com")
    assert boost > 0, "Should have positive boost for successful domain"
    print(f"  Learned boost: {boost:.1f}")
    
    # Test with unsuccessful domain
    for i in range(5):
        scorer.learn_domain_pattern("bad-site.com", False, 0.0)
    
    penalty = scorer.get_learned_boost("bad-site.com")
    assert penalty < 0, "Should have penalty for unsuccessful domain"
    print(f"  Learned penalty: {penalty:.1f}")
    
    # Update pattern weights
    patterns = [
        {"pattern": r"test", "weight": 10, "success_count": 8, "total_uses": 10}
    ]
    scorer.update_pattern_weights(patterns)
    
    print("  ✓ URLScorer learning tests passed")


def test_strategy_selector():
    """Test StrategySelector."""
    print("\nTesting StrategySelector...")
    
    selector = StrategySelector()
    
    # Test all entity types
    for entity_type in [EntityType.COMPANY, EntityType.PERSON, EntityType.NEWS, EntityType.TOPIC]:
        strategy = selector.select_strategy(entity_type, "official")
        assert strategy is not None
        
        # Test priority fields
        fields = strategy.get_priority_fields()
        assert len(fields) > 0
        print(f"  {entity_type.value}: {len(fields)} priority fields")
        
        # Test prompt generation
        profile = EntityProfile(
            name="Test Entity",
            entity_type=entity_type
        )
        prompt = strategy.get_extraction_prompt(profile, "test text", "official", "http://test.com")
        assert len(prompt) > 0
    
    print("  ✓ StrategySelector tests passed")


def test_integration():
    """Test integration of components."""
    print("\nTesting component integration...")
    
    # Create components
    class MockStore:
        pass
    
    learner = CrawlLearner(MockStore())
    scorer = URLScorer("Microsoft", EntityType.COMPANY)
    selector = StrategySelector()
    
    # Simulate crawl cycle
    url = "https://microsoft.com/about"
    
    # 1. Score with learning
    base_score, _ = scorer.score_url(url, "About", 0)
    adjusted_score = learner.adapt_frontier_scoring(
        base_score=base_score,
        url=url,
        context={"page_type": "official", "entity_type": "company"}
    )
    print(f"  Score: {base_score:.1f} -> {adjusted_score:.1f}")
    
    # 2. Select strategy
    strategy = selector.select_strategy(EntityType.COMPANY, "official")
    assert strategy is not None
    
    # 3. Record outcome
    learner.record_crawl_result(
        url=url,
        page_type="official",
        intel_quality=0.85,
        extraction_success=True,
        entity_type="company"
    )
    
    scorer.learn_domain_pattern("microsoft.com", True, 0.85)
    
    # 4. Verify learning applied
    reliability = learner.get_domain_reliability("microsoft.com")
    print(f"  Domain reliability after learning: {reliability:.3f}")
    
    print("  ✓ Integration tests passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 4 Basic Integration Tests")
    print("=" * 60)
    
    try:
        test_crawl_learner_basic()
        test_url_scorer_learning()
        test_strategy_selector()
        test_integration()
        
        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
