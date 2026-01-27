# Phase 4: Dynamic Discovery & Extraction - Documentation

## Overview

Phase 4 introduces intelligent learning and adaptation to Garuda's intelligence gathering system. The system now learns from successful crawls, adapts extraction strategies, and refines intelligence gathering over time.

## Components

### 1. CrawlLearner (`discover/crawl_learner.py`)

The `CrawlLearner` tracks and learns from crawl outcomes to improve future discovery strategies.

#### Features
- **Domain Reliability Tracking**: Learns which domains consistently provide quality intelligence
- **Page Type Patterns**: Identifies successful extraction patterns for different page types
- **Entity-Specific Learning**: Adapts to entity-specific crawl patterns
- **Temporal Decay**: Old patterns decay over time to stay relevant
- **Frontier Score Adaptation**: Adjusts URL prioritization based on learned patterns

#### Usage Example

```python
from garuda_intel.discover.crawl_learner import CrawlLearner
from garuda_intel.database.engine import SQLAlchemyStore

# Initialize
store = SQLAlchemyStore("sqlite:///crawler.db")
learner = CrawlLearner(store, learning_rate=0.1, decay_days=30)

# Record crawl outcomes
learner.record_crawl_result(
    url="https://example.com/company",
    page_type="official",
    intel_quality=0.85,
    extraction_success=True,
    entity_type="company",
    metadata={"extraction_hints": ["detailed_financials"]}
)

# Get domain reliability
reliability = learner.get_domain_reliability("example.com")
print(f"Domain reliability: {reliability:.2f}")

# Get strategy suggestions
strategy = learner.suggest_page_strategy(
    url="https://example.com/about",
    page_type="official",
    entity_type="company"
)
print(f"Expected quality: {strategy['expected_quality']:.2f}")
print(f"Confidence: {strategy['confidence']:.2f}")

# Get successful patterns for entity type
patterns = learner.get_successful_patterns("company")
for pattern in patterns:
    print(f"Page type: {pattern['page_type']}, Quality: {pattern['avg_quality']:.2f}")

# Adapt frontier scoring
adjusted_score = learner.adapt_frontier_scoring(
    base_score=75.0,
    url="https://example.com/news",
    context={"page_type": "news", "entity_type": "company"}
)
print(f"Adjusted score: {adjusted_score:.1f}")

# Get learning statistics
stats = learner.get_learning_stats()
print(f"Total domains tracked: {stats['total_domains']}")
print(f"High confidence patterns: {stats['high_confidence_patterns']}")
```

#### Key Methods

- `record_crawl_result()`: Record outcome of a crawl for learning
- `get_domain_reliability()`: Get reliability score for a domain (0-1)
- `suggest_page_strategy()`: Get extraction strategy suggestions based on learned patterns
- `get_successful_patterns()`: Get patterns that work well for an entity type
- `adapt_frontier_scoring()`: Adjust URL scores based on learned patterns
- `get_learning_stats()`: Get summary of learning progress

### 2. Enhanced URLScorer (`explorer/scorer.py`)

The `URLScorer` now includes learning capabilities to adapt URL scoring based on crawl outcomes.

#### New Methods

```python
from garuda_intel.explorer.scorer import URLScorer
from garuda_intel.types.entity.type import EntityType

scorer = URLScorer("Microsoft", EntityType.COMPANY)

# Learn from domain outcomes
scorer.learn_domain_pattern(
    domain="microsoft.com",
    success=True,
    intel_quality=0.9
)

# Get learned boost for a domain
boost = scorer.get_learned_boost("microsoft.com")
print(f"Learned boost: {boost:.1f}")

# Update pattern weights based on success
patterns = [
    {"pattern": r"investor", "weight": 50, "success_count": 8, "total_uses": 10},
    {"pattern": r"careers", "weight": 20, "success_count": 2, "total_uses": 10}
]
scorer.update_pattern_weights(patterns)

# Score URL (now includes learned adjustments)
score, reason = scorer.score_url("https://microsoft.com/investor")
print(f"Score: {score:.1f} - {reason}")
```

#### Learning Integration

The scorer automatically applies learned boosts when scoring URLs:
- Domains with high success rates get +30 boost
- Domains with low success rates get -20 penalty
- Requires at least 3 crawls before learning applies

### 3. IterativeRefiner (`extractor/iterative_refiner.py`)

The `IterativeRefiner` improves extraction quality by detecting gaps and contradictions.

#### Features
- **Gap Detection**: Identifies missing priority fields in extracted intelligence
- **Contradiction Detection**: Finds conflicts across multiple sources
- **Targeted Re-extraction**: Generates focused prompts for missing data
- **Consistency Validation**: Validates new intelligence against existing data

#### Usage Example

```python
from garuda_intel.extractor.iterative_refiner import IterativeRefiner
from garuda_intel.extractor.llm import LLMIntelExtractor
from garuda_intel.types.entity import EntityProfile, EntityType

# Initialize
llm_extractor = LLMIntelExtractor()
refiner = IterativeRefiner(llm_extractor, store)

profile = EntityProfile(
    name="Microsoft",
    entity_type=EntityType.COMPANY
)

# Initial extraction (may have gaps)
initial_intel = {
    "basic_info": {"official_name": "Microsoft Corporation"},
    "persons": [{"name": "Satya Nadella", "title": "CEO"}],
    "locations": [],  # Gap: missing locations
    "financials": []  # Gap: missing financials
}

# Refine extraction to fill gaps
refined_intel = refiner.refine_extraction(
    entity_id="entity-123",
    initial_intel=initial_intel,
    page_text=page_text,
    page_url="https://microsoft.com/about",
    page_type="official"
)

print(f"Filled gaps: {len(refined_intel['locations'])} locations added")

# Detect contradictions across sources
intel_records = [
    {"basic_info": {"founded": "1975"}},
    {"basic_info": {"founded": "April 4, 1975"}},  # Compatible
    {"basic_info": {"founded": "1976"}}  # Contradiction!
]

contradictions = refiner.detect_contradictions(intel_records)
for contradiction in contradictions:
    print(f"Field: {contradiction['field']}")
    print(f"Values: {contradiction['values']}")
    print(f"Severity: {contradiction['severity']}")

# Validate consistency of new intelligence
new_intel = {"basic_info": {"ticker": "MSFT"}}
existing = [{"basic_info": {"ticker": "MSFT"}}]

is_consistent, issues = refiner.validate_consistency(new_intel, existing)
print(f"Consistent: {is_consistent}")
for issue in issues:
    print(f"Issue: {issue}")

# Generate targeted extraction prompt for gap
prompt = refiner.request_additional_context(
    entity_id="entity-123",
    gap_field="basic_info.founded",
    page_text=page_text
)
print(f"Targeted prompt: {prompt[:100]}...")
```

#### Priority Fields by Entity Type

- **Company**: official_name, industry, founded, website, persons, locations, financials
- **Person**: official_name, title, bio, persons, events, relationships
- **News**: events, persons, relationships, description
- **Topic**: description, events, relationships

### 4. StrategySelector (`extractor/strategy_selector.py`)

The `StrategySelector` provides entity-specific extraction strategies optimized for different contexts.

#### Extraction Strategies

1. **CompanyExtractionStrategy**: Optimized for companies/organizations
2. **PersonExtractionStrategy**: Optimized for individuals
3. **NewsExtractionStrategy**: Optimized for news articles
4. **TopicExtractionStrategy**: Optimized for topics/concepts

#### Usage Example

```python
from garuda_intel.extractor.strategy_selector import StrategySelector
from garuda_intel.types.entity import EntityProfile, EntityType

selector = StrategySelector()

# Select strategy for entity type and page type
strategy = selector.select_strategy(
    entity_type=EntityType.COMPANY,
    page_type="official"
)

# Get optimized extraction prompt
profile = EntityProfile(
    name="Microsoft",
    entity_type=EntityType.COMPANY,
    location_hint="Redmond, WA"
)

prompt = strategy.get_extraction_prompt(
    profile=profile,
    text=page_text,
    page_type="official",
    url="https://microsoft.com/about"
)

# Get priority fields for this strategy
priority_fields = strategy.get_priority_fields()
print(f"Priority fields: {priority_fields}")

# Get validation rules
validation_rules = strategy.get_validation_rules()
print(f"Required fields: {validation_rules.get('required_fields', [])}")

# Register custom strategy
from garuda_intel.extractor.strategy_selector import ExtractionStrategy

class CustomStrategy(ExtractionStrategy):
    def get_extraction_prompt(self, profile, text, page_type, url):
        return "Custom prompt..."
    
    def get_priority_fields(self):
        return ["custom_field"]

selector.register_strategy(EntityType.COMPANY, CustomStrategy())
```

#### Strategy Customization by Page Type

Each strategy adjusts its focus based on page type:

**Company Strategy**:
- **official**: Focus on legal name, leadership, products, structure
- **news**: Focus on announcements, events, executive changes
- **registry**: Focus on legal details, registration numbers, directors

**Person Strategy**:
- **official**: Focus on biography, current position, qualifications
- **news**: Focus on recent activities, achievements, quotes

**News Strategy**: Focus on events, people, impact, timeline

**Topic Strategy**: Focus on definition, concepts, history, contributors

## Integration Guide

### Integrating Learning into Crawler

```python
from garuda_intel.discover.crawl_learner import CrawlLearner
from garuda_intel.explorer.scorer import URLScorer
from garuda_intel.types.entity import EntityProfile, EntityType

# Initialize components
learner = CrawlLearner(store)
scorer = URLScorer("Microsoft", EntityType.COMPANY)

# After each successful crawl
def on_crawl_complete(url, page_type, intel, extraction_success):
    # Calculate quality score
    intel_quality = calculate_quality(intel)
    
    # Record for learning
    learner.record_crawl_result(
        url=url,
        page_type=page_type,
        intel_quality=intel_quality,
        extraction_success=extraction_success,
        entity_type="company"
    )
    
    # Update scorer
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    scorer.learn_domain_pattern(domain, extraction_success, intel_quality)

# When scoring new URLs
def score_url_with_learning(url, link_text, depth):
    # Get base score
    base_score, reason = scorer.score_url(url, link_text, depth)
    
    # Apply learned adjustments
    adjusted_score = learner.adapt_frontier_scoring(
        base_score=base_score,
        url=url,
        context={"page_type": classify_page_type(url), "entity_type": "company"}
    )
    
    return adjusted_score, reason
```

### Integrating Strategy-Based Extraction

```python
from garuda_intel.extractor.strategy_selector import StrategySelector
from garuda_intel.extractor.llm import LLMIntelExtractor

selector = StrategySelector()
llm_extractor = LLMIntelExtractor()

def extract_with_strategy(profile, text, page_type, url):
    # Select optimal strategy
    strategy = selector.select_strategy(profile.entity_type, page_type)
    
    # Get optimized prompt
    prompt = strategy.get_extraction_prompt(profile, text, page_type, url)
    
    # Extract (use the custom prompt with LLM)
    # Note: This is a simplified example
    result = llm_extractor.extract_intelligence(profile, text, page_type, url, None)
    
    # Post-process with strategy
    processed = strategy.post_process(result)
    
    return processed
```

### Integrating Iterative Refinement

```python
from garuda_intel.extractor.iterative_refiner import IterativeRefiner

refiner = IterativeRefiner(llm_extractor, store)

def extract_and_refine(entity_id, profile, page_text, page_url, page_type):
    # Initial extraction
    initial_intel = llm_extractor.extract_intelligence(
        profile, page_text, page_type, page_url, None
    )
    
    # Refine to fill gaps
    refined_intel = refiner.refine_extraction(
        entity_id=entity_id,
        initial_intel=initial_intel,
        page_text=page_text,
        page_url=page_url,
        page_type=page_type
    )
    
    # Validate against existing intelligence
    existing = store.get_intelligence(entity_id=entity_id)
    is_consistent, issues = refiner.validate_consistency(refined_intel, existing)
    
    if not is_consistent:
        print(f"Consistency issues: {issues}")
    
    return refined_intel
```

## Performance Considerations

### Learning Rate

The learning rate (default: 0.1) controls how quickly the system adapts:
- **Higher (0.3-0.5)**: Fast adaptation, more reactive to recent data
- **Lower (0.05-0.1)**: Slower adaptation, more stable over time

### Decay Period

The decay period (default: 30 days) controls how long patterns remain relevant:
- **Shorter (7-14 days)**: For rapidly changing domains
- **Longer (60-90 days)**: For stable, authoritative sources

### Memory Management

- Recent outcomes are limited to 1000 entries
- Patterns are periodically persisted to database
- Domain statistics use exponential moving averages

## Best Practices

1. **Record All Crawls**: Record both successes and failures for accurate learning
2. **Use Quality Scores**: Assign meaningful quality scores (0-1) based on extraction completeness
3. **Monitor Learning Stats**: Regularly check learning statistics to ensure healthy adaptation
4. **Validate Refinements**: Always validate refined intelligence for consistency
5. **Choose Appropriate Strategy**: Use the correct extraction strategy for entity type
6. **Handle Contradictions**: Investigate contradictions before accepting new intelligence

## Configuration Examples

### Conservative Learning
```python
learner = CrawlLearner(store, learning_rate=0.05, decay_days=60)
```

### Aggressive Learning
```python
learner = CrawlLearner(store, learning_rate=0.3, decay_days=14)
```

### Custom Extraction Strategy
```python
from garuda_intel.extractor.strategy_selector import ExtractionStrategy, StrategySelector

class TechnologyCompanyStrategy(ExtractionStrategy):
    def get_extraction_prompt(self, profile, text, page_type, url):
        return f"""
        Extract technical details about {profile.name}:
        - Technology stack
        - Developer tools
        - API offerings
        - Open source projects
        {text[:4000]}
        """
    
    def get_priority_fields(self):
        return ["products", "metrics", "relationships"]

selector = StrategySelector()
selector.register_strategy(EntityType.COMPANY, TechnologyCompanyStrategy())
```

## Troubleshooting

### Learning Not Improving Scores

- Check if enough data has been recorded (need 3+ crawls per domain)
- Verify quality scores are being calculated correctly
- Ensure learning_rate is not too low

### Too Many Contradictions Detected

- Review validation rules in IterativeRefiner
- Check if date/name matching is too strict
- Consider adjusting compatibility thresholds

### Strategy Prompts Too Generic

- Customize extraction strategies for your use case
- Register domain-specific strategies
- Adjust page type modifiers in StrategySelector

## Future Enhancements

Potential areas for expansion:
- **Active Learning**: Request human feedback for ambiguous extractions
- **Multi-Source Fusion**: Intelligent merging of intelligence from multiple sources
- **Pattern Mining**: Automatic discovery of new extraction patterns
- **Cross-Entity Learning**: Apply patterns learned from one entity to similar entities
- **Confidence Calibration**: Automatic tuning of confidence thresholds
