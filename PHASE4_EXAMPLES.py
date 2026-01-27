#!/usr/bin/env python3
"""
Phase 4 Examples: Dynamic Discovery & Extraction

This file demonstrates the key features of Phase 4:
- Crawl learning and adaptation
- Enhanced URL scoring with learning
- Iterative extraction refinement
- Entity-specific extraction strategies
"""

from src.garuda_intel.discover.crawl_learner import CrawlLearner
from src.garuda_intel.explorer.scorer import URLScorer
from src.garuda_intel.extractor.iterative_refiner import IterativeRefiner
from src.garuda_intel.extractor.strategy_selector import StrategySelector
from src.garuda_intel.types.entity import EntityProfile, EntityType


def example_1_crawl_learning():
    """Example 1: Learning from crawl outcomes"""
    print("=" * 60)
    print("Example 1: Crawl Learning and Adaptation")
    print("=" * 60)
    
    # Note: In production, pass actual PersistenceStore
    # learner = CrawlLearner(store)
    print("\n# Initialize CrawlLearner")
    print("learner = CrawlLearner(store, learning_rate=0.1, decay_days=30)")
    
    print("\n# Record successful crawls")
    print("learner.record_crawl_result(")
    print("    url='https://microsoft.com/about',")
    print("    page_type='official',")
    print("    intel_quality=0.92,")
    print("    extraction_success=True,")
    print("    entity_type='company'")
    print(")")
    
    print("\n# Record multiple outcomes to build patterns")
    crawl_examples = [
        ("microsoft.com/investor", "official", 0.88, True),
        ("microsoft.com/news", "news", 0.75, True),
        ("linkedin.com/company/microsoft", "social", 0.65, True),
        ("crunchbase.com/microsoft", "registry", 0.45, False),
    ]
    
    for url, page_type, quality, success in crawl_examples:
        print(f"    - {url}: quality={quality}, success={success}")
    
    print("\n# Get domain reliability")
    print("reliability = learner.get_domain_reliability('microsoft.com')")
    print("# Expected: ~0.85 (high reliability from successful crawls)")
    
    print("\n# Get extraction strategy suggestion")
    print("strategy = learner.suggest_page_strategy(")
    print("    url='https://microsoft.com/leadership',")
    print("    page_type='official',")
    print("    entity_type='company'")
    print(")")
    print("# Returns: {")
    print("#   'domain_reliability': 0.85,")
    print("#   'expected_quality': 0.90,")
    print("#   'confidence': 0.75,")
    print("#   'extraction_hints': ['detailed_leadership', 'executive_bios']")
    print("# }")
    
    print("\n# Get successful patterns for company entities")
    print("patterns = learner.get_successful_patterns('company')")
    print("# Returns top patterns like:")
    print("# [")
    print("#   {'page_type': 'official', 'avg_quality': 0.90, 'confidence': 0.85},")
    print("#   {'page_type': 'news', 'avg_quality': 0.75, 'confidence': 0.72}")
    print("# ]")
    
    print("\n# Adapt frontier scoring")
    print("adjusted_score = learner.adapt_frontier_scoring(")
    print("    base_score=75.0,")
    print("    url='https://microsoft.com/careers',")
    print("    context={'page_type': 'careers', 'entity_type': 'company'}")
    print(")")
    print("# Expected: ~75-95 (base + learned boost)")
    
    print("\n# Get learning statistics")
    print("stats = learner.get_learning_stats()")
    print("# Returns: {")
    print("#   'total_domains': 4,")
    print("#   'total_page_patterns': 3,")
    print("#   'high_confidence_patterns': 2,")
    print("#   'reliable_domains': 1")
    print("# }")


def example_2_enhanced_scoring():
    """Example 2: Enhanced URL scoring with learning"""
    print("\n\n" + "=" * 60)
    print("Example 2: Enhanced URL Scoring with Learning")
    print("=" * 60)
    
    print("\n# Initialize URLScorer")
    print("scorer = URLScorer('Microsoft', EntityType.COMPANY)")
    
    print("\n# Learn from domain outcomes")
    print("scorer.learn_domain_pattern('microsoft.com', success=True, intel_quality=0.9)")
    print("scorer.learn_domain_pattern('microsoft.com', success=True, intel_quality=0.85)")
    print("scorer.learn_domain_pattern('microsoft.com', success=True, intel_quality=0.88)")
    
    print("\n# Learn from unsuccessful domain")
    print("scorer.learn_domain_pattern('spam-site.com', success=False, intel_quality=0.0)")
    print("scorer.learn_domain_pattern('spam-site.com', success=False, intel_quality=0.0)")
    print("scorer.learn_domain_pattern('spam-site.com', success=False, intel_quality=0.0)")
    
    print("\n# Get learned boost for domains")
    print("boost_good = scorer.get_learned_boost('microsoft.com')")
    print("# Expected: ~25-30 (high success rate, high quality)")
    print("boost_bad = scorer.get_learned_boost('spam-site.com')")
    print("# Expected: -20 (low success rate)")
    
    print("\n# Update pattern weights based on success")
    print("patterns = [")
    print("    {'pattern': r'investor', 'weight': 50, 'success_count': 9, 'total_uses': 10},")
    print("    {'pattern': r'careers', 'weight': 20, 'success_count': 2, 'total_uses': 10}")
    print("]")
    print("scorer.update_pattern_weights(patterns)")
    
    print("\n# Score URLs with learning applied")
    print("score1, reason1 = scorer.score_url('https://microsoft.com/investor')")
    print("# Expected: ~120-140 (high base + learned boost + pattern match)")
    print("score2, reason2 = scorer.score_url('https://spam-site.com/microsoft-info')")
    print("# Expected: ~20-40 (low base + learned penalty)")


def example_3_iterative_refinement():
    """Example 3: Iterative extraction refinement"""
    print("\n\n" + "=" * 60)
    print("Example 3: Iterative Extraction Refinement")
    print("=" * 60)
    
    print("\n# Initialize IterativeRefiner")
    print("# refiner = IterativeRefiner(llm_extractor, store)")
    
    print("\n# Initial extraction with gaps")
    initial_intel = {
        "basic_info": {
            "official_name": "Microsoft Corporation",
            "industry": "Software & Cloud"
            # Missing: founded, website
        },
        "persons": [
            {"name": "Satya Nadella", "title": "CEO"}
            # Missing other executives
        ],
        "locations": [],  # Gap: missing locations
        "financials": []  # Gap: missing financials
    }
    
    print("initial_intel = {")
    print("  'basic_info': {'official_name': 'Microsoft Corporation', 'industry': 'Software & Cloud'},")
    print("  'persons': [{'name': 'Satya Nadella', 'title': 'CEO'}],")
    print("  'locations': [],  # GAP")
    print("  'financials': []  # GAP")
    print("}")
    
    print("\n# Refine extraction to fill gaps")
    print("refined_intel = refiner.refine_extraction(")
    print("    entity_id='entity-123',")
    print("    initial_intel=initial_intel,")
    print("    page_text=full_page_text,")
    print("    page_url='https://microsoft.com/about',")
    print("    page_type='official'")
    print(")")
    
    print("\n# Refined result now includes:")
    print("# - basic_info.founded: '1975-04-04'")
    print("# - basic_info.website: 'https://microsoft.com'")
    print("# - locations: [{'address': 'One Microsoft Way', 'city': 'Redmond', 'country': 'USA'}]")
    print("# - financials: [{'year': '2023', 'revenue': '$211.9B', 'currency': 'USD'}]")
    
    print("\n# Detect contradictions across sources")
    intel_records = [
        {"basic_info": {"founded": "1975"}},
        {"basic_info": {"founded": "April 4, 1975"}},
        {"basic_info": {"founded": "1976"}},  # Contradiction!
    ]
    
    print("intel_records = [")
    print("    {'basic_info': {'founded': '1975'}},")
    print("    {'basic_info': {'founded': 'April 4, 1975'}},")
    print("    {'basic_info': {'founded': '1976'}}  # CONTRADICTION")
    print("]")
    
    print("\ncontradictions = refiner.detect_contradictions(intel_records)")
    print("# Returns: [")
    print("#   {")
    print("#     'field': 'basic_info.founded',")
    print("#     'values': ['1975', 'April 4, 1975', '1976'],")
    print("#     'severity': 'medium'")
    print("#   }")
    print("# ]")
    
    print("\n# Validate consistency")
    new_intel = {"basic_info": {"ticker": "MSFT"}}
    existing = [{"basic_info": {"ticker": "GOOGL"}}]  # Inconsistent!
    
    print("new_intel = {'basic_info': {'ticker': 'MSFT'}}")
    print("existing = [{'basic_info': {'ticker': 'GOOGL'}}]")
    print("is_consistent, issues = refiner.validate_consistency(new_intel, existing)")
    print("# Returns: (False, ['Inconsistent ticker: new=MSFT vs existing=GOOGL'])")
    
    print("\n# Generate targeted extraction prompt")
    print("prompt = refiner.request_additional_context(")
    print("    entity_id='entity-123',")
    print("    gap_field='basic_info.founded',")
    print("    page_text=page_text")
    print(")")
    print("# Returns focused prompt: 'Extract the founding date or year...'")


def example_4_extraction_strategies():
    """Example 4: Entity-specific extraction strategies"""
    print("\n\n" + "=" * 60)
    print("Example 4: Entity-Specific Extraction Strategies")
    print("=" * 60)
    
    print("\n# Initialize StrategySelector")
    print("selector = StrategySelector()")
    
    print("\n# Select strategy for company entity")
    print("company_strategy = selector.select_strategy(")
    print("    entity_type=EntityType.COMPANY,")
    print("    page_type='official'")
    print(")")
    
    print("\n# Get priority fields for company extraction")
    print("priority = company_strategy.get_priority_fields()")
    print("# Returns: [")
    print("#   'basic_info.official_name',")
    print("#   'basic_info.industry',")
    print("#   'persons',")
    print("#   'locations',")
    print("#   'financials'")
    print("# ]")
    
    print("\n# Generate optimized extraction prompt")
    profile = EntityProfile(
        name="Microsoft",
        entity_type=EntityType.COMPANY,
        location_hint="Redmond, WA"
    )
    
    print("profile = EntityProfile(name='Microsoft', entity_type=EntityType.COMPANY)")
    print("prompt = company_strategy.get_extraction_prompt(")
    print("    profile=profile,")
    print("    text=page_text,")
    print("    page_type='official',")
    print("    url='https://microsoft.com/about'")
    print(")")
    print("# Returns optimized prompt focusing on:")
    print("# - Official legal name and branding")
    print("# - Leadership team and executives")
    print("# - Products and services")
    print("# - Corporate structure")
    
    print("\n# Select strategy for person entity")
    print("person_strategy = selector.select_strategy(EntityType.PERSON, 'official')")
    print("# Focus changes to: biography, current position, qualifications")
    
    print("\n# Select strategy for news entity")
    print("news_strategy = selector.select_strategy(EntityType.NEWS, 'news')")
    print("# Focus changes to: events, people, timeline, quotes")
    
    print("\n# Register custom strategy")
    print("class CustomStrategy(ExtractionStrategy):")
    print("    def get_extraction_prompt(self, profile, text, page_type, url):")
    print("        return 'Custom prompt for specialized extraction...'")
    print("")
    print("selector.register_strategy(EntityType.COMPANY, CustomStrategy())")


def example_5_integration():
    """Example 5: Full integration example"""
    print("\n\n" + "=" * 60)
    print("Example 5: Full Integration - Learning-Enhanced Crawling")
    print("=" * 60)
    
    print("""
# Complete workflow integrating all Phase 4 components

from garuda_intel.discover.crawl_learner import CrawlLearner
from garuda_intel.explorer.scorer import URLScorer
from garuda_intel.extractor.iterative_refiner import IterativeRefiner
from garuda_intel.extractor.strategy_selector import StrategySelector
from garuda_intel.extractor.llm import LLMIntelExtractor

# Initialize all components
learner = CrawlLearner(store)
scorer = URLScorer("Microsoft", EntityType.COMPANY)
llm_extractor = LLMIntelExtractor()
refiner = IterativeRefiner(llm_extractor, store)
selector = StrategySelector()

# Phase 1: Score URLs with learning
def score_url_with_learning(url, link_text, depth):
    # Base score
    base_score, reason = scorer.score_url(url, link_text, depth)
    
    # Apply learned adjustments
    adjusted_score = learner.adapt_frontier_scoring(
        base_score=base_score,
        url=url,
        context={"page_type": "official", "entity_type": "company"}
    )
    
    return adjusted_score, reason

# Phase 2: Extract with optimal strategy
def extract_with_strategy(profile, page_text, page_type, url):
    # Select strategy
    strategy = selector.select_strategy(profile.entity_type, page_type)
    
    # Get optimized prompt
    prompt = strategy.get_extraction_prompt(profile, page_text, page_type, url)
    
    # Extract (simplified - use custom prompt in actual implementation)
    intel = llm_extractor.extract_intelligence(profile, page_text, page_type, url, None)
    
    return intel

# Phase 3: Refine extraction
def extract_and_refine(entity_id, profile, page_text, page_url, page_type):
    # Initial extraction
    initial = extract_with_strategy(profile, page_text, page_type, page_url)
    
    # Refine to fill gaps
    refined = refiner.refine_extraction(
        entity_id=entity_id,
        initial_intel=initial,
        page_text=page_text,
        page_url=page_url,
        page_type=page_type
    )
    
    return refined

# Phase 4: Record outcome for learning
def record_crawl_outcome(url, page_type, intel, success):
    # Calculate quality
    quality = calculate_intelligence_quality(intel)
    
    # Record for learning
    learner.record_crawl_result(
        url=url,
        page_type=page_type,
        intel_quality=quality,
        extraction_success=success,
        entity_type="company"
    )
    
    # Update scorer
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    scorer.learn_domain_pattern(domain, success, quality)

# Complete crawl cycle
profile = EntityProfile(name="Microsoft", entity_type=EntityType.COMPANY)

# 1. Score candidate URLs
url = "https://microsoft.com/investor"
score, reason = score_url_with_learning(url, "Investor Relations", depth=1)
print(f"URL score: {score:.1f} - {reason}")

# 2. If score is high, crawl and extract
if score > 50:
    page_text = fetch_page(url)  # Your fetch logic
    intel = extract_and_refine("entity-123", profile, page_text, url, "official")
    
    # 3. Record outcome
    success = bool(intel.get("basic_info") or intel.get("persons"))
    record_crawl_outcome(url, "official", intel, success)
    
    # 4. System learns and improves future scoring/extraction
    stats = learner.get_learning_stats()
    print(f"Learning progress: {stats}")
""")


def calculate_intelligence_quality(intel: dict) -> float:
    """Helper to calculate intelligence quality score."""
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


def main():
    """Run all examples"""
    print("\n" + "#" * 60)
    print("# PHASE 4: DYNAMIC DISCOVERY & EXTRACTION")
    print("# Code Examples and Demonstrations")
    print("#" * 60)
    
    example_1_crawl_learning()
    example_2_enhanced_scoring()
    example_3_iterative_refinement()
    example_4_extraction_strategies()
    example_5_integration()
    
    print("\n\n" + "=" * 60)
    print("Examples completed!")
    print("See PHASE4_DOCUMENTATION.md for full API reference")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
