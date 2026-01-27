# Garuda Intelligence Gathering - Feature Documentation

This document describes the advanced intelligence gathering and adaptive crawling features in Garuda.

## Table of Contents

- [Overview](#overview)
- [Intelligent Crawling System](#intelligent-crawling-system)
- [Entity Gap Analysis](#entity-gap-analysis)
- [Adaptive Learning](#adaptive-learning)
- [API Endpoints](#api-endpoints)
- [UI Components](#ui-components)
- [Workflows](#workflows)
- [Examples](#examples)

---

## Overview

Garuda's intelligence gathering system uses a multi-layered approach to automatically discover, analyze, and fill information gaps about any entity (companies, people, products, etc.). The system learns from each crawl to improve future discovery strategies.

**Key Capabilities:**
- 🧠 **Intelligent Gap-Aware Crawling** - Automatically identifies missing information and generates targeted queries
- 🎯 **Adaptive Strategy Selection** - Chooses between discovery and gap-filling modes based on existing data
- 📊 **Learning System** - Tracks successful patterns and domain reliability to optimize crawls
- 🔗 **Cross-Entity Inference** - Uses relationship data to infer missing fields
- 📈 **Completeness Tracking** - Scores entity data completeness and tracks improvements

---

## Intelligent Crawling System

### Architecture

The intelligent crawling system consists of four main components:

1. **EntityGapAnalyzer** - Identifies missing data fields and generates targeted crawl strategies
2. **AdaptiveCrawlerService** - Orchestrates intelligent, gap-aware crawling
3. **EntityAwareCrawler** - Executes entity-specific crawl modes
4. **CrawlLearner** - Learns from successful crawls to improve future strategies

### Crawl Modes

#### 1. Discovery Mode
Used for **new entities** not yet in the database.

**Flow:**
1. Auto-detect entity type from name patterns
2. Generate comprehensive discovery queries
3. Collect seed URLs from search results
4. Extract and store baseline information
5. Establish entity profile and relationships

**Example Queries Generated:**
- `"Microsoft" official`
- `"Microsoft" company`
- `"Microsoft" investor relations`
- `"Microsoft" about us`

#### 2. Gap-Filling Mode
Used for **existing entities** with incomplete data.

**Flow:**
1. Analyze current entity data completeness
2. Identify missing critical/important fields
3. Generate targeted queries for specific gaps
4. Prioritize high-value, findable fields
5. Re-analyze post-crawl to verify gaps filled

**Example for Company Entity:**
- Missing: `ticker`, `founded`, `headquarters`
- Generates: `"Microsoft" revenue employees industry`
- Sources: LinkedIn, Crunchbase, Wikipedia

#### 3. Relationship Expansion Mode
Used for **discovering related entities** from known seeds.

**Flow:**
1. Start from entity with good data coverage
2. Extract mentions of related entities
3. Create relationship links
4. Queue related entities for discovery

---

## Entity Gap Analysis

### Completeness Scoring

Each entity is scored 0-100% based on expected fields for its type:

**Field Priority Levels:**
- **Critical** (3x weight): `official_name`, `industry`, `website`, `full_name`
- **Important** (2x weight): `ticker`, `founded`, `description`, `title`, `organization`
- **Supplementary** (1x weight): `revenue`, `employees`, `bio`, `products`

**Formula:**
```
Completeness = (Σ filled_fields × priority_weight) / (Σ total_expected_fields × priority_weight) × 100
```

### Expected Fields by Entity Type

#### Company
- **Critical:** official_name, industry, website
- **Important:** ticker, founded, description, headquarters
- **Supplementary:** revenue, employees, ceo, products

#### Person
- **Critical:** full_name
- **Important:** title, organization, location
- **Supplementary:** bio, education, email, social_media

#### Product
- **Critical:** name, manufacturer
- **Important:** description, category, launch_date
- **Supplementary:** price, specifications, reviews

#### Organization
- **Critical:** name, type
- **Important:** description, location, founded
- **Supplementary:** mission, leadership, size

### Gap Prioritization

Gaps are scored by:
1. **Priority Level** (critical > important > supplementary)
2. **Findability Score** (0.0-1.0) - how likely the field is to be found online
3. **Combined Score** = priority_score × findability_score

**High Findability Fields:**
- website, official_name, industry, description, location (0.9)

**Medium Findability Fields:**
- ticker, founded, ceo, headquarters, title (0.6)

**Low Findability Fields:**
- revenue, employees, email, phone (0.3)

---

## Adaptive Learning

### Domain Reliability Tracking

The system tracks domain performance over time:

**Metrics:**
- Success rate (successful extractions / total attempts)
- Average intelligence quality (0.0-1.0)
- Recency factor (time decay over 30 days)

**Reliability Score:**
```
reliability = (success_rate × 0.4 + quality × 0.4) × (0.8 + recency × 0.2)
```

**Actions:**
- **High reliability (>0.8):** Increase crawl depth, prioritize domain
- **Low reliability (<0.3):** Decrease crawl depth, deprioritize domain

### Page Type Patterns

Tracks which page types yield good intel for each entity type:

**Pattern Attributes:**
- page_type (e.g., "company_about", "person_bio")
- entity_type (e.g., "company", "person")
- success_count / total_count
- avg_quality
- confidence (increases with sample size)

**Usage:**
- Suggest extraction strategies for similar pages
- Prioritize high-confidence patterns in frontier
- Adapt query generation based on successful patterns

### Query Refinement

Based on learning stats:
- If extraction rate is low (<25%), refine queries
- Use successful patterns from similar entity types
- Adjust depth based on domain reliability
- Suggest new queries based on gap analysis

---

## API Endpoints

### 1. Intelligent Crawl
**POST** `/api/crawl/intelligent`

Performs gap-aware intelligent crawl for an entity.

**Request:**
```json
{
  "entity_name": "Microsoft",
  "entity_type": "company",
  "max_pages": 50,
  "max_depth": 2
}
```

**Response:**
```json
{
  "plan": {
    "mode": "gap_filling",
    "strategy": "targeted",
    "entity_name": "Microsoft",
    "queries": ["Microsoft revenue employees industry", ...],
    "analysis": {
      "completeness_score": 65.5,
      "missing_fields": [...],
      "prioritized_gaps": [...]
    }
  },
  "results": {
    "pages_discovered": 23,
    "intel_extracted": 15,
    "relationships_found": 8,
    "gaps_filled": ["ticker", "founded"],
    "completeness_improvement": 12.5
  }
}
```

### 2. Entity Gap Analysis
**GET** `/api/entities/<entity_id>/gaps`

Analyzes data gaps for a specific entity.

**Response:**
```json
{
  "entity_id": "uuid",
  "entity_name": "Microsoft",
  "entity_type": "company",
  "completeness_score": 67.5,
  "missing_fields": [
    {"field": "ticker", "priority": "important", "category": "business"},
    {"field": "founded", "priority": "important", "category": "temporal"}
  ],
  "suggested_queries": [
    "Microsoft revenue employees industry",
    "Microsoft investor relations"
  ],
  "suggested_sources": [
    {
      "name": "LinkedIn Company Page",
      "url_pattern": "site:linkedin.com/company Microsoft",
      "fields": ["industry", "employees", "description"]
    }
  ]
}
```

### 3. Unified Crawl (Auto-Detection)
**POST** `/api/crawl/unified`

Automatically detects and uses appropriate crawl mode.

**Request:**
```json
{
  "entity": "Microsoft",
  "type": "company",
  "use_intelligent": false,  // Auto-detect if entity exists
  "max_pages": 50,
  "max_depth": 2
}
```

**Behavior:**
- If entity exists in database → Uses intelligent gap-filling mode
- If entity is new → Uses standard discovery mode
- Returns mode in response: `{"mode": "intelligent" | "standard", ...}`

### 4. Cross-Entity Inference
**POST** `/api/entities/<entity_id>/infer_from_relationships`

Uses related entities to infer missing data.

**Example:**
- Person entity missing "organization" field
- Has "works_at" relationship to company entity
- Infers organization from relationship

**Response:**
```json
{
  "entity_id": "uuid",
  "inferred_fields": [
    {
      "field": "organization",
      "value": "Microsoft",
      "source": "relationship",
      "relation_type": "works_at",
      "confidence": 0.8
    }
  ]
}
```

### 5. Adaptive Crawl Status
**GET** `/api/crawl/adaptive/status`

Get system capabilities and learning statistics.

**Response:**
```json
{
  "features": {
    "gap_aware_crawling": true,
    "cross_entity_inference": true,
    "real_time_adaptation": true,
    "domain_learning": true
  },
  "learning_stats": {
    "total_domains": 156,
    "total_page_patterns": 89,
    "high_confidence_patterns": 34,
    "reliable_domains": 67
  },
  "capabilities": {
    "modes": ["discovery", "gap_filling", "relationship_expansion"],
    "strategies": ["comprehensive", "targeted", "adaptive"]
  }
}
```

---

## UI Components

### 1. Intelligent Crawl Section (Blue Box)

Located at the top of the Crawler tab.

**Features:**
- Entity name input with auto-complete
- Entity type selector (auto-detect option)
- One-click intelligent crawl launch
- Real-time plan generation feedback

**Visual Indicators:**
- 🧠 Icon for intelligent mode
- Blue color scheme
- "Analyzing entity..." loading state

### 2. Smart Crawl Button (Auto-Detection)

Purple button in the Advanced Crawl section.

**Features:**
- Uses entity field from advanced form
- Auto-detects if entity exists
- Switches between standard/intelligent modes automatically
- Shows which mode was used in results

**Use Case:**
"I want to crawl an entity but don't know if it's new or existing"

### 3. Crawl Results Display

Enhanced results panel with:

**Crawl Plan Section (Blue):**
- Mode (discovery/gap_filling)
- Strategy (comprehensive/targeted)
- Entity name and type

**Gap Analysis Section (Amber):**
- Completeness percentage with progress bar
- Missing fields count
- Top priority gaps as pills

**Generated Queries Section (Green):**
- List of targeted queries
- Truncated with "X more..." indicator

**Crawl Results Section (Emerald/Rose):**
- Pages discovered count
- Intel extracted count
- Relationships found count
- Official domains (clickable pills)
- Completeness improvement (±%)
- Gaps filled (checkmarks)

**Learning Stats Section (Purple):**
- Known domains count
- Page patterns count
- High confidence patterns
- Reliable domains count

---

## Workflows

### Workflow 1: Discover New Company

**Goal:** Gather comprehensive information about a new company.

**Steps:**
1. Open Web UI → Crawler tab
2. Find "🧠 Intelligent Crawl" section (blue box)
3. Enter: `Microsoft`
4. Type: `company` (or leave auto-detect)
5. Click "🚀 Start Intelligent Crawl"

**System Actions:**
1. Detects entity is new → Discovery mode
2. Infers type: company
3. Generates queries:
   - `"Microsoft" official`
   - `"Microsoft" company`
   - `"Microsoft" investor relations`
   - `"Microsoft" about us`
4. Collects seed URLs from search
5. Crawls official domains
6. Extracts baseline intel
7. Creates entity profile

**Expected Results:**
- 20-30 pages discovered
- 10-15 intel records extracted
- 60-75% completeness
- Official domains: microsoft.com, linkedin.com/company/microsoft

### Workflow 2: Fill Information Gaps

**Goal:** Complete missing information for an existing entity.

**Steps:**
1. Web UI → Entity Tools tab
2. Enter entity UUID or name
3. Click "🔍 Analyze Gaps"
4. Review gap analysis modal
5. Click "Fill Gaps with Targeted Crawl"

**System Actions:**
1. Loads entity data
2. Identifies missing fields:
   - ticker (important)
   - founded (important)
   - employees (supplementary)
3. Generates targeted queries:
   - `"Microsoft" revenue employees industry`
   - `"Microsoft" investor relations`
4. Suggests sources: LinkedIn, Crunchbase
5. Executes focused crawl
6. Re-analyzes completeness

**Expected Results:**
- 10-15 pages discovered (fewer, more targeted)
- 5-8 new intel records
- +10-20% completeness improvement
- 2-4 gaps filled

### Workflow 3: Automatic Smart Crawl

**Goal:** Let the system decide the best crawl approach.

**Steps:**
1. Web UI → Crawler tab → Advanced section
2. Enter entity name: `Tesla`
3. Leave settings at defaults
4. Click "🎯 Smart Crawl (Auto-detect)"

**System Actions:**
1. Checks if "Tesla" exists in database
2. If exists → Intelligent gap-filling mode
3. If new → Standard discovery mode
4. Executes appropriate workflow
5. Returns results with mode indicator

**Expected Results:**
- Auto-selected mode shown in results
- Appropriate number of pages crawled
- Relevant intel extracted
- Mode-specific metrics displayed

### Workflow 4: Cross-Entity Discovery

**Goal:** Discover related entities from a well-known seed.

**Steps:**
1. Start with complete entity (e.g., "Microsoft")
2. System extracts relationships during crawl:
   - Mentions of "Satya Nadella" (CEO)
   - Mentions of "Azure" (product)
   - Mentions of "LinkedIn" (subsidiary)
3. Creates relationship links
4. Queues related entities for discovery

**System Actions:**
1. LLM extraction identifies entities in text
2. Creates relationship records:
   - `Microsoft --[ceo_of]--> Satya Nadella`
   - `Microsoft --[offers]--> Azure`
   - `Microsoft --[owns]--> LinkedIn`
3. Triggers discovery crawls for new entities
4. Uses inference to fill gaps:
   - Nadella's organization ← Microsoft
   - Azure's manufacturer ← Microsoft

**Expected Results:**
- Network of 5-10 related entities
- 20-30 relationships discovered
- Inferred fields: 3-5 per entity
- Knowledge graph expansion

---

## Examples

### Example 1: Company Discovery

**Input:**
```bash
curl -X POST http://localhost:8080/api/crawl/intelligent \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_name": "Anthropic",
    "entity_type": "company",
    "max_pages": 30
  }'
```

**Output:**
```json
{
  "plan": {
    "mode": "discovery",
    "strategy": "comprehensive",
    "entity_name": "Anthropic",
    "entity_type": "company",
    "queries": [
      "\"Anthropic\" official",
      "\"Anthropic\" company",
      "\"Anthropic\" about us",
      "\"Anthropic\" investor relations"
    ],
    "sources": [
      {"name": "Official Website", "url_pattern": "site:anthropic.com about"},
      {"name": "LinkedIn", "url_pattern": "site:linkedin.com/company Anthropic"}
    ]
  },
  "results": {
    "entity_name": "Anthropic",
    "crawl_mode": "discovery",
    "pages_discovered": 18,
    "intel_extracted": 12,
    "relationships_found": 5,
    "seed_urls": [
      "https://www.anthropic.com",
      "https://www.anthropic.com/company",
      "https://www.linkedin.com/company/anthropicai"
    ],
    "official_domains": ["anthropic.com"],
    "learning_stats": {
      "total_domains": 157,
      "total_page_patterns": 90
    }
  }
}
```

### Example 2: Person Gap Filling

**Input:**
```bash
curl -X POST http://localhost:8080/api/crawl/intelligent \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_name": "Satya Nadella",
    "entity_type": "person",
    "max_pages": 20
  }'
```

**Output:**
```json
{
  "plan": {
    "mode": "gap_filling",
    "strategy": "targeted",
    "entity_id": "uuid-here",
    "entity_name": "Satya Nadella",
    "analysis": {
      "completeness_score": 55.0,
      "missing_fields": [
        {"field": "bio", "priority": "supplementary"},
        {"field": "education", "priority": "supplementary"}
      ],
      "suggested_queries": [
        "\"Satya Nadella\" biography",
        "\"Satya Nadella\" linkedin profile",
        "\"Satya Nadella\" education background"
      ]
    }
  },
  "results": {
    "crawl_mode": "gap_filling",
    "pages_discovered": 12,
    "intel_extracted": 8,
    "target_gaps": ["bio", "education"],
    "gaps_filled": ["bio", "education"],
    "completeness_improvement": 18.5
  }
}
```

---

## Best Practices

### When to Use Intelligent Crawl

✅ **Use Intelligent Crawl When:**
- You want gap-aware, adaptive crawling
- Entity might already exist in database
- You need targeted information gathering
- You want to track completeness improvements
- You want automatic query generation

❌ **Use Standard Crawl When:**
- You have specific seed URLs to crawl
- You need fine-grained control over parameters
- You're doing specialized research (e.g., specific domains only)
- You're testing or debugging crawl behavior

### Optimizing Completeness

1. **Start with Discovery Mode** - Let the system build baseline
2. **Review Gap Analysis** - Understand what's missing
3. **Run Targeted Gap-Filling** - Focus on high-value fields
4. **Use Cross-Entity Inference** - Leverage relationships
5. **Iterate** - Re-analyze and fill remaining gaps

### Performance Tuning

**For Fast Discovery:**
- max_pages: 20-30
- max_depth: 1-2
- Focus on official domains

**For Comprehensive Coverage:**
- max_pages: 50-100
- max_depth: 2-3
- Allow broader domain discovery

**For Gap Filling:**
- max_pages: 15-25
- max_depth: 1-2
- Use suggested sources from gap analysis

---

## Troubleshooting

### No Seed URLs Found

**Cause:** Queries didn't return results or search failed

**Solutions:**
1. Check entity name spelling
2. Try simpler, more common queries
3. Manually add seed URLs in advanced mode
4. Check if DuckDuckGo is accessible

### Low Completeness Score

**Cause:** Entity type has many expected fields, few filled

**Solutions:**
1. Run multiple targeted crawls for different field categories
2. Use cross-entity inference if relationships exist
3. Manually add known data via API
4. Adjust expected fields for entity type (custom config)

### Crawl Finds No Intel

**Cause:** Pages don't match extraction patterns

**Solutions:**
1. Check if pages are JavaScript-heavy (enable Selenium)
2. Review page types in results
3. Verify LLM is running and accessible
4. Check extraction confidence thresholds

### Learning Stats Not Updating

**Cause:** CrawlLearner not persisting patterns

**Solutions:**
1. Verify database write permissions
2. Check for errors in crawl_learner logs
3. Ensure store is properly initialized
4. Re-run crawls to generate new patterns

---

## Future Enhancements

**Planned Features:**
- [ ] Real-time progress streaming via WebSockets
- [ ] Crawl cancellation and pause/resume
- [ ] Custom entity type definitions
- [ ] Multi-entity batch crawling
- [ ] Scheduled re-crawls for freshness
- [ ] Export gap analysis reports
- [ ] Visual knowledge graph explorer
- [ ] A/B testing different crawl strategies
- [ ] Confidence-based field merging
- [ ] Historical completeness tracking

---

## License

GPL-3.0 © [anorien90](https://github.com/anorien90)
