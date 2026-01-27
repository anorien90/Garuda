# Phase 4: Dynamic Discovery & Extraction - Quick Start

## What is Phase 4?

Phase 4 adds **intelligent learning and adaptation** to Garuda's web intelligence gathering system. The system now:
- 🧠 **Learns** from successful/unsuccessful crawls
- 📊 **Adapts** URL scoring based on domain reliability
- 🔍 **Refines** extractions by detecting gaps and contradictions
- 🎯 **Optimizes** extraction strategies per entity type

## Quick Start

### 1. Import Components

```python
from src.garuda_intel.discover.crawl_learner import CrawlLearner
from src.garuda_intel.explorer.scorer import URLScorer
from src.garuda_intel.extractor.iterative_refiner import IterativeRefiner
from src.garuda_intel.extractor.strategy_selector import StrategySelector
from src.garuda_intel.types.entity import EntityProfile, EntityType
```

### 2. Basic Usage

#### Enable Learning on URLScorer
```python
scorer = URLScorer("Microsoft", EntityType.COMPANY)

# After each crawl, teach the scorer
scorer.learn_domain_pattern("microsoft.com", success=True, intel_quality=0.9)

# Scoring now includes learned boosts
score, reason = scorer.score_url("https://microsoft.com/investor")
# Score includes learned boost for reliable domain
```

#### Use Entity-Specific Strategies
```python
selector = StrategySelector()
profile = EntityProfile(name="Microsoft", entity_type=EntityType.COMPANY)

# Get optimized strategy
strategy = selector.select_strategy(EntityType.COMPANY, page_type="official")

# Generate optimized extraction prompt
prompt = strategy.get_extraction_prompt(profile, page_text, "official", url)
# Prompt is optimized for company extraction from official pages
```

#### Refine Extractions
```python
refiner = IterativeRefiner(llm_extractor, store)

# Initial extraction may have gaps
initial_intel = extract_intelligence(...)

# Refine to fill gaps
refined_intel = refiner.refine_extraction(
    entity_id="entity-123",
    initial_intel=initial_intel,
    page_text=page_text,
    page_url=url,
    page_type="official"
)
# Gaps are now filled with targeted re-extraction
```

#### Full Learning System
```python
learner = CrawlLearner(store)

# Record crawl outcomes
learner.record_crawl_result(
    url="https://microsoft.com/about",
    page_type="official",
    intel_quality=0.92,
    extraction_success=True,
    entity_type="company"
)

# Get suggestions for new URLs
strategy = learner.suggest_page_strategy(
    url="https://microsoft.com/leadership",
    page_type="official",
    entity_type="company"
)
print(f"Expected quality: {strategy['expected_quality']:.2f}")
```

## Key Features

### 1. CrawlLearner - Intelligence System
- Tracks domain reliability over time
- Identifies successful page patterns
- Suggests optimal extraction strategies
- Adapts URL prioritization

### 2. Enhanced URLScorer - Adaptive Scoring
- Learns from domain success/failure
- Applies automatic boosts/penalties
- Updates pattern weights
- Fully backward compatible

### 3. IterativeRefiner - Smart Extraction
- Detects missing fields
- Identifies contradictions
- Generates targeted prompts
- Validates consistency

### 4. StrategySelector - Optimized Prompts
- Company-specific extraction
- Person-specific extraction
- News-specific extraction
- Topic-specific extraction

## Documentation

📖 **Full Documentation**: [PHASE4_DOCUMENTATION.md](PHASE4_DOCUMENTATION.md)
- Complete API reference
- Usage examples
- Integration guide
- Best practices

💡 **Examples**: [PHASE4_EXAMPLES.py](PHASE4_EXAMPLES.py)
- 5 working examples
- Full integration demo
- Executable code

📋 **Summary**: [PHASE4_SUMMARY.md](PHASE4_SUMMARY.md)
- Implementation details
- Design decisions
- Performance notes

✅ **Verification**: [PHASE4_VERIFICATION.md](PHASE4_VERIFICATION.md)
- Test results
- Security scan
- Code quality metrics

## Testing

Run the test suite:
```bash
python3 test_phase4_basic.py
```

Run the examples:
```bash
python3 PHASE4_EXAMPLES.py
```

## Integration with Existing Code

Phase 4 is **100% backward compatible**. You can:
1. Use existing code unchanged
2. Enable features gradually
3. Mix new and old APIs

### Minimal Integration
```python
# Just add to existing URLScorer
scorer.learn_domain_pattern(domain, success, quality)
```

### Full Integration
```python
# Complete adaptive crawling system
learner = CrawlLearner(store)
scorer = URLScorer("Entity", EntityType.COMPANY)
refiner = IterativeRefiner(llm_extractor, store)
selector = StrategySelector()

# Use in crawl pipeline
# See PHASE4_EXAMPLES.py for full example
```

## Performance

- **Memory**: ~1MB per 1000 crawl outcomes
- **Speed**: O(1) for domain lookups
- **Storage**: Periodic persistence to database
- **Scalability**: Handles 1000s of domains

## Configuration

### Learning Rate
```python
learner = CrawlLearner(store, learning_rate=0.1)
# 0.05 = slower, more stable
# 0.3 = faster, more reactive
```

### Decay Period
```python
learner = CrawlLearner(store, decay_days=30)
# 7-14 = fast-changing domains
# 60-90 = stable sources
```

## What's Next?

### Immediate Use
1. Add URLScorer learning to existing code
2. Use StrategySelector for better prompts
3. Monitor learning statistics

### Short Term
1. Enable IterativeRefiner for gap filling
2. Deploy full CrawlLearner system
3. Tune parameters for your domain

### Future Enhancements
- Active learning with human feedback
- Cross-entity pattern transfer
- Automatic pattern mining
- Reinforcement learning optimization

## Support

- See [PHASE4_DOCUMENTATION.md](PHASE4_DOCUMENTATION.md) for detailed API
- Run [PHASE4_EXAMPLES.py](PHASE4_EXAMPLES.py) for working demos
- Check [PHASE4_VERIFICATION.md](PHASE4_VERIFICATION.md) for test results

## Status

✅ **Implementation**: Complete  
✅ **Testing**: All tests pass  
✅ **Security**: 0 vulnerabilities  
✅ **Documentation**: Complete  
✅ **Ready**: Production deployment  

---

**Phase 4 adds intelligence to intelligence gathering. 🧠**
