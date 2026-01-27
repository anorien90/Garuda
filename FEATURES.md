# Dynamic Intelligence Gathering Features

This document describes the new dynamic intelligence gathering capabilities added to Garuda.

## Overview

Garuda now includes intelligent, adaptive crawling capabilities that analyze existing entity data, identify information gaps, and automatically generate targeted crawling strategies to fill those gaps. The system learns from past crawl results to continuously improve its effectiveness.

## Key Components

### 1. Entity Gap Analyzer

The `EntityGapAnalyzer` service analyzes entities to identify missing data fields and generate intelligent recommendations.

**Location:** `src/garuda_intel/services/entity_gap_analyzer.py`

**Key Features:**
- Identifies missing critical, important, and supplementary fields
- Calculates entity completeness score (0-100%)
- Prioritizes gaps by importance and findability
- Generates targeted search queries
- Suggests specific data sources
- Supports multiple entity types (company, person, organization, product, location, topic, news)

**API Endpoints:**
- `GET /api/entities/<id>/analyze_gaps` - Analyze single entity
- `GET /api/entities/analyze_all_gaps?limit=N` - Bulk analysis

**Example Usage:**
```bash
# Analyze a specific entity
curl -H "X-API-Key: YOUR_KEY" \
  http://localhost:8080/api/entities/123e4567-e89b-12d3-a456-426614174000/analyze_gaps

# Analyze top 20 entities with most gaps
curl -H "X-API-Key: YOUR_KEY" \
  http://localhost:8080/api/entities/analyze_all_gaps?limit=20
```

**Response Example:**
```json
{
  "entity_id": "123e4567-e89b-12d3-a456-426614174000",
  "entity_name": "Acme Corporation",
  "entity_type": "company",
  "completeness_score": 62.5,
  "missing_fields": [
    {"field": "ticker", "priority": "important", "category": "business"},
    {"field": "ceo", "priority": "supplementary", "category": "hierarchical"}
  ],
  "prioritized_gaps": [
    {"field": "ticker", "priority": "important", "score": 7.2, "findability": 0.6}
  ],
  "suggested_queries": [
    "\"Acme Corporation\" investor relations",
    "\"Acme Corporation\" company information"
  ],
  "suggested_sources": [
    {
      "name": "LinkedIn Company Page",
      "url_pattern": "site:linkedin.com/company Acme Corporation",
      "fields": ["industry", "employees", "description"]
    }
  ]
}
```

### 2. Adaptive Crawler Service

The `AdaptiveCrawlerService` orchestrates intelligent crawling based on entity analysis and learned patterns.

**Location:** `src/garuda_intel/services/adaptive_crawler.py`

**Key Features:**
- Two crawl modes: Discovery (new entities) vs Gap-Filling (existing entities)
- Real-time monitoring and adaptation
- Cross-entity data inference
- Integration with crawl learning system
- Dynamic depth/breadth adjustments

**API Endpoints:**
- `POST /api/crawl/intelligent` - Start intelligent crawl
- `POST /api/entities/<id>/infer_from_relationships` - Cross-entity inference
- `GET /api/crawl/adaptive/status` - System status and capabilities

**Example Usage:**
```bash
# Start an intelligent crawl for "Bill Gates"
curl -X POST -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_name": "Bill Gates",
    "entity_type": "person",
    "max_pages": 50,
    "max_depth": 2
  }' \
  http://localhost:8080/api/crawl/intelligent
```

**Response Example:**
```json
{
  "plan": {
    "mode": "gap_filling",
    "entity_id": "456...",
    "entity_name": "Bill Gates",
    "strategy": "targeted",
    "queries": [
      "\"Bill Gates\" biography",
      "\"Bill Gates\" profile linkedin",
      "\"Bill Gates\" about"
    ],
    "analysis": {
      "completeness_score": 45.0,
      "missing_fields": [...],
      "prioritized_gaps": [...]
    }
  },
  "results": {
    "crawl_mode": "gap_filling",
    "pages_discovered": 0,
    "intel_extracted": 0,
    "target_gaps": ["bio", "education", "email"],
    "learning_stats": {
      "total_domains": 15,
      "reliable_domains": 8,
      "high_confidence_patterns": 12
    }
  }
}
```

### 3. Crawl Learning System

Enhanced `CrawlLearner` tracks successful patterns and domain reliability.

**Location:** `src/garuda_intel/discover/crawl_learner.py`

**Key Features:**
- Tracks domain reliability scores
- Records page type extraction success rates
- Learns entity-specific patterns
- Suggests extraction strategies
- Adapts frontier scoring based on history

**API Endpoint:**
- `GET /api/crawl/learning/stats` - Learning statistics

## UI Features

### Intelligent Crawl Interface

**Location:** Crawler tab in web UI

**Features:**
- Entity name input with auto-type detection
- Displays generated crawl plan
- Shows gap analysis results
- Visualizes completeness scores
- Lists suggested queries and sources
- Shows learning statistics

**How to Use:**
1. Go to the "Crawler" tab
2. Find the "🧠 Intelligent Crawl" section (blue box)
3. Enter entity name (e.g., "Bill Gates")
4. Optionally select entity type
5. Click "🚀 Start Intelligent Crawl"
6. View results showing plan, gaps, queries, and learning stats

### Gap Analysis Interface

**Location:** Entity Tools tab in web UI

**Features:**
- Single entity gap analysis
- Bulk gap analysis (top N entities)
- Color-coded completeness scores
  - Green: 70%+ (good)
  - Amber: 40-69% (needs work)
  - Rose: <40% (critical gaps)
- Prioritized missing fields
- Field categorization (critical/important/supplementary)
- Suggested queries and sources
- Click-to-analyze functionality

**How to Use:**
1. Go to the "Entity Tools" tab
2. Find the "🎯 Entity Gap Analysis" section
3. Option A: Analyze specific entity
   - Enter entity UUID
   - Click "🔍 Analyze Gaps"
4. Option B: Bulk analysis
   - Click "📊 Analyze All (Top 20)"
   - Click any entity in results to analyze it in detail

## Crawl Modes

### Discovery Mode
- **When:** Entity doesn't exist in database
- **Strategy:** Comprehensive search to establish baseline
- **Queries:** Broad queries for entity discovery
- **Output:** New entity with foundational data

### Gap-Filling Mode
- **When:** Entity exists with incomplete data
- **Strategy:** Targeted search for missing fields
- **Queries:** Specific queries for identified gaps
- **Output:** Updated entity with filled gaps

### Expansion Mode
- **When:** Finding related entities
- **Strategy:** Relationship-based discovery
- **Queries:** Queries for partners, competitors, related entities

## Expected Fields by Entity Type

### Company
- **Critical:** official_name, industry, website
- **Important:** ticker, founded, description, headquarters
- **Supplementary:** revenue, employees, ceo, products

### Person
- **Critical:** full_name
- **Important:** title, organization, location
- **Supplementary:** bio, education, email, social_media

### Organization
- **Critical:** name, type
- **Important:** description, location, founded
- **Supplementary:** mission, leadership, size

### Product
- **Critical:** name, manufacturer
- **Important:** description, category, launch_date
- **Supplementary:** price, specifications, reviews

### Location
- **Critical:** name, country
- **Important:** coordinates, type
- **Supplementary:** population, area, timezone

## Cross-Entity Inference

The system can infer missing data from relationships:

**Examples:**
- If Person has "works_at" relationship to Company → infer organization field
- If Company has incoming "ceo_of" relationship from Person → infer CEO field
- If Entity has "located_in" relationship to Location → infer location field

**API Usage:**
```bash
curl -X POST -H "X-API-Key: YOUR_KEY" \
  http://localhost:8080/api/entities/123.../infer_from_relationships?hops=1
```

**Response:**
```json
{
  "entity_id": "123...",
  "inferred_fields": [
    {
      "field": "organization",
      "value": "Microsoft Corporation",
      "source": "relationship",
      "relation_type": "works_at",
      "confidence": 0.8
    }
  ]
}
```

## Learning System

The crawl learner tracks:
- **Domain Stats:** Success rates, quality scores, reliability
- **Page Patterns:** Which page types work best for entity types
- **Temporal Trends:** How patterns change over time

**Metrics:**
- `total_domains`: Domains seen
- `reliable_domains`: Domains with >70% reliability
- `high_confidence_patterns`: Patterns with >70% confidence
- `total_page_patterns`: Page type patterns learned

## Integration with Existing System

### Backward Compatibility
All existing crawl functionality remains available. The new features are additive:
- Standard crawl form still works
- All existing API endpoints unchanged
- New endpoints are opt-in

### Data Model
No database schema changes required. The services work with existing:
- `Entity` table
- `Intelligence` table
- `Relationship` table
- `Page` and `PageContent` tables

### Event System
All new operations emit events for monitoring:
- `entity_gaps_analysis` - Gap analysis started/completed
- `intelligent_crawl` - Intelligent crawl progress
- `cross_entity_inference` - Inference operations

## Configuration

The services use existing configuration from `.env`:
- `GARUDA_DB_URL` - Database connection
- `GARUDA_OLLAMA_URL` - LLM endpoint (for inference)
- `GARUDA_QDRANT_URL` - Vector store (for semantic search)

No additional configuration required.

## Best Practices

### When to Use Intelligent Crawl
- Researching a specific known entity
- Filling gaps in existing entity data
- Need adaptive strategy based on learned patterns

### When to Use Standard Crawl
- Exploratory crawling
- Topic-based research
- Custom crawl parameters needed

### Gap Analysis Workflow
1. Use bulk analysis to identify entities with critical gaps
2. For high-priority entities, run individual gap analysis
3. Use suggested queries to manually verify findability
4. Run intelligent crawl to fill gaps automatically

### Cross-Entity Inference
- Run after relationship inference/deduplication
- Useful when entity has many relationships but missing direct data
- Higher confidence (>0.7) inferences are generally reliable

## Performance Considerations

- Gap analysis scales to ~200 entities efficiently
- Intelligent crawl is more focused than standard crawl (fewer pages, higher quality)
- Learning system has minimal overhead (<1% of crawl time)
- Cross-entity inference is fast (graph traversal)

## Troubleshooting

### Gap Analysis Returns Empty
- Check entity has intelligence records
- Verify entity type is recognized
- Ensure entity.data or intelligence.data contains fields

### Intelligent Crawl Not Finding Gaps
- Entity may already be complete
- Check completeness score is <100%
- Try analyzing gaps first to see what's missing

### Inferences Return Nothing
- Entity needs relationships first
- Run relationship inference: `POST /api/relationships/infer`
- Check relationship types are recognized

## Future Enhancements

Potential additions:
- Automatic relationship inference after crawl
- Real-time entity deduplication during extraction
- Crawl progress monitoring dashboard
- Gap analysis export/reporting
- Custom field definitions per entity type
- ML-based findability prediction
