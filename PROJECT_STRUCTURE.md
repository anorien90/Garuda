# Garuda Project Structure Guide

## Directory Overview

```
Garuda/
├── src/garuda_intel/           # Core application package
│   ├── browser/                # Web scraping & browser automation
│   ├── database/               # Data models & persistence
│   ├── discover/               # Intelligent crawling & learning
│   ├── docker/                 # Docker utilities
│   ├── explorer/               # Search & exploration
│   ├── extractor/              # Intelligence extraction & NLP
│   ├── recorder/               # Manual page recording
│   ├── search/                 # Search functionality & CLI
│   ├── services/               # High-level business logic
│   ├── templates/              # Extraction templates
│   ├── types/                  # Type definitions & data structures
│   ├── vector/                 # Vector database integration
│   └── webapp/                 # Web UI & REST API
│       ├── routes/             # API endpoints
│       ├── services/           # Web app services
│       ├── static/             # Frontend assets (JS/CSS)
│       ├── templates/          # HTML templates
│       └── utils/              # Web utilities
├── plugin/                     # Browser extensions
│   └── chrome/                 # Chrome extension
├── tests/                      # Test suite
├── build/                      # Build artifacts
├── docs/                       # Documentation (future)
├── .env                        # Environment configuration
├── requirements.txt            # Python dependencies
├── pyproject.toml             # Project metadata & build config
├── docker-compose.yml         # Docker Compose setup
├── Dockerfile                 # Docker image definition
└── README.md                  # Main documentation
```

---

## Module Details

### 1. Browser Module (`src/garuda_intel/browser/`)

**Purpose**: Web page acquisition and content capture

**Files**:
- `selenium.py`: Headless Chrome automation
  - `SeleniumBrowser`: Main browser class
  - `fetch_page()`: URL fetching with configurable timeouts
  - Supports custom wait conditions, screenshot capture
  
- `active.py`: Interactive browser sessions
  - `ActiveBrowser`: Recording browser with UI overlays
  - JavaScript injection for visual feedback
  - Keyboard shortcut handling

**Dependencies**: `selenium`, `beautifulsoup4`

**Usage Example**:
```python
from garuda_intel.browser.selenium import SeleniumBrowser

browser = SeleniumBrowser(headless=True)
html, metadata = browser.fetch_page("https://example.com")
```

---

### 2. Database Module (`src/garuda_intel/database/`)

**Purpose**: Data persistence, ORM, and relationship management

**Files**:
- `models.py`: SQLAlchemy ORM models
  - `Entity`: Core entity model (companies, people, locations)
  - `Intelligence`: Extracted intelligence facts
  - `Page`: Crawled web pages
  - `PageContent`: Full page HTML and metadata
  - `Relationship`: Entity-to-entity relationships
  
- `engine.py`: Database operations
  - `SQLAlchemyStore`: Main database interface
  - CRUD operations for all models
  - Aggregation and filtering
  
- `store.py`: Abstract persistence interface
  - `PersistenceStore`: Abstract base class
  - Defines standard operations for any storage backend
  
- `relationship_manager.py`: Graph operations
  - `RelationshipManager`: Relationship inference and management
  - LLM-powered relationship extraction
  - Clustering and deduplication
  
- `helpers.py`: Utility functions for database operations

**Dependencies**: `sqlalchemy`, `sqlite3/postgresql`

**Database Schema**:
```
Entity (entities table)
├── id: UUID (PK)
├── name: String (indexed)
├── kind: String (person, company, location, etc.)
├── data: JSON (aggregated intelligence)
├── metadata_json: JSON
└── created_at: DateTime

Intelligence (intelligence table)
├── id: UUID (PK)
├── entity_id: UUID (FK → entities)
├── page_id: UUID (FK → pages)
├── data: JSON (structured facts)
├── confidence: Float (0-1)
└── extracted_at: DateTime

Relationship (relationships table)
├── id: UUID (PK)
├── source_id: UUID (FK → entities)
├── target_id: UUID (FK → entities)
├── relationship_type: String
├── confidence: Float
└── metadata_json: JSON
```

---

### 3. Discover Module (`src/garuda_intel/discover/`)

**Purpose**: Intelligent crawling strategies and adaptive learning

**Files**:
- `crawl_modes.py`: Crawl mode implementations
  - `CrawlMode` enum: DISCOVERY, TARGETING, EXPANSION
  - `EntityAwareCrawler`: Main intelligent crawler
  - Gap-aware query generation
  
- `crawl_learner.py`: Adaptive learning system
  - `CrawlLearner`: Tracks crawl effectiveness
  - Domain authority scoring
  - Pattern decay (30-day default)
  
- `seeds.py`: Seed URL management
  - `SeedManager`: Seed source handling
  - DuckDuckGo integration
  
- `frontier.py`: URL frontier for crawling
  - `URLFrontier`: Priority queue for URLs
  - Domain-based deduplication
  
- `post_crawl_processor.py`: Post-processing pipeline
  - `PostCrawlProcessor`: 6-step processing
  - Entity deduplication, relationship validation, inference
  - Embedding regeneration

**Key Workflow**:
```
EntityAwareCrawler.crawl_for_entity()
    ↓
Analyze existing data (gap analysis)
    ↓
Generate targeted queries (LLM)
    ↓
DuckDuckGo search → URL candidates
    ↓
Browser fetch → Extract → Store
    ↓
PostCrawlProcessor.process()
    ↓
CrawlLearner.update_from_crawl()
```

---

### 4. Extractor Module (`src/garuda_intel/extractor/`)

**Purpose**: Intelligence extraction from raw content

**Files**:
- `intel_extractor.py`: LLM-based extraction
  - `IntelExtractor`: Main extraction class
  - Chunk-based processing (4000 chars/chunk)
  - Categories: basic_info, persons, locations, financials, products, events
  
- `llm.py`: LLM interface
  - `LLMIntelExtractor`: Ollama/OpenAI wrapper
  - `extract_intelligence()`: Main extraction method
  - `generate_search_queries()`: Query generation
  
- `semantic_engine.py`: Embedding generation
  - `SemanticEngine`: SentenceTransformers wrapper
  - `embed_text()`: Generate embeddings
  - `build_embeddings_for_page()`: Page-level embeddings
  - `build_embeddings_for_entities()`: Entity embeddings
  
- `text_processor.py`: Content preprocessing
  - `TextProcessor`: HTML cleaning and chunking
  - `clean_text()`: Noise removal
  - `split_sentences()`: Sentence segmentation
  
- `qa_validator.py`: Quality validation
- `iterative_refiner.py`: Multi-pass refinement
- `query_generator.py`: Search query generation
- `strategy_selector.py`: Extraction strategy selection
- `filter.py`: Content filtering

**Extraction Pipeline**:
```
Raw HTML
    ↓
TextProcessor.clean_text()
    ↓
Split into chunks (4000 chars)
    ↓
For each chunk:
    LLM.extract_intelligence()
    ↓
Aggregate results across chunks
    ↓
SemanticEngine.embed_text()
    ↓
Store to Database + Vector Store
```

---

### 5. Services Module (`src/garuda_intel/services/`)

**Purpose**: High-level business logic orchestration

**Files**:
- `entity_gap_analyzer.py`: Data completeness analysis
  - `EntityGapAnalyzer`: Gap detection
  - `EXPECTED_FIELDS`: Field definitions per entity type
  - Completeness scoring (0-1)
  - Priority-based recommendations
  
- `adaptive_crawler.py`: Crawl orchestration
  - `AdaptiveCrawlerService`: Gap-filling coordinator
  - Combines gap analysis + learning + crawling
  - Domain filtering (avoid marking Wikipedia as "official")
  
- `media_processor.py`: Media content extraction
  - `MediaProcessor`: Multi-format processing
  - Image: Tesseract OCR or AI Image2Text
  - Video: Audio extraction + speech-to-text or AI Video2Text
  - Audio: Speech recognition
  - Configurable processing methods
  
- `media_downloader.py`: Media file management
- `media_extractor.py`: Media content extraction

**Gap Analysis Workflow**:
```python
analyzer = EntityGapAnalyzer(store)
report = analyzer.analyze_entity_gaps(entity_id)
# Returns:
# {
#   "completeness_score": 0.45,
#   "missing_critical": ["headquarters", "founder"],
#   "missing_important": ["revenue", "employees"],
#   "priority_gaps": [...],
#   "suggested_queries": [...]
# }
```

---

### 6. Vector Module (`src/garuda_intel/vector/`)

**Purpose**: Semantic search via vector embeddings

**Files**:
- `base.py`: Abstract vector store interface
  - `VectorStore`: Abstract base class
  - `upsert()`, `search()`, `delete()` methods
  
- `engine.py`: Qdrant implementation
  - `QdrantVectorStore`: Qdrant integration
  - COSINE distance metric
  - Deterministic UUID-based point IDs

**Vector Storage**:
```
Each embedding stored as:
{
  "point_id": UUID5(url),  # Deterministic
  "vector": [0.1, 0.2, ...],  # 384-dim
  "payload": {
    "url": "...",
    "entity_ids": [...],
    "text": "...",
    "page_id": "...",
    "kind": "page|entity|finding"
  }
}
```

---

### 7. WebApp Module (`src/garuda_intel/webapp/`)

**Purpose**: Web UI and REST API

**Structure**:
```
webapp/
├── app.py                  # Flask application entry point
├── routes/                 # API endpoints
│   ├── search.py          # Search & chat endpoints
│   ├── crawling.py        # Crawl triggers
│   ├── entities.py        # Entity CRUD
│   ├── entity_gaps.py     # Gap analysis endpoints
│   ├── entity_relations.py # Relationship queries
│   ├── entity_deduplication.py # Deduplication
│   ├── recorder.py        # Manual recording (/mark_page)
│   ├── media.py           # Media processing
│   └── static.py          # Static files & status
├── services/
│   ├── event_system.py    # Crawl event logging
│   └── graph_builder.py   # Graph visualization builder
├── static/                 # Frontend assets
│   ├── app.js             # Main application logic
│   ├── api.js             # API client
│   ├── entities-graph.js  # Graph visualization
│   ├── render-*.js        # UI rendering modules
│   └── vendor/            # Third-party libraries
└── templates/
    ├── base.html          # Base template
    └── index.html         # Main UI
```

**Key API Endpoints**:
```
POST /api/chat                      # RAG-first Q&A
POST /api/crawl/intelligent         # Intelligent crawl
POST /api/crawl/adaptive/trigger    # Gap-filling crawl
GET  /api/entities                  # List entities
POST /api/entities/{id}/gaps        # Analyze gaps
GET  /api/entities/{id}/relationships # Get relationships
POST /api/mark_page                 # Record page (extension)
POST /api/media/process             # Process media
GET  /api/status                    # System status
```

---

### 8. Chrome Extension (`plugin/chrome/`)

**Purpose**: Browser-based page recording and search

**Files**:
- `manifest.json`: Extension configuration (v3)
- `popup.html`: Extension UI
- `popup.js`: UI logic (tabs: Record, Search, Settings)
- `content.js`: Injected into web pages
  - Page/element/image marking
  - Visual highlighting
- `background.js`: Service worker
  - Settings storage
  - Message routing

**Communication Flow**:
```
Web Page
    ↓ (inject)
Content Script
    ↓ (chrome.runtime.sendMessage)
Background Worker
    ↓ (chrome.tabs.sendMessage)
Popup UI
    ↓ (fetch with API key)
Backend API (/mark_page)
    ↓
Database Storage
```

---

## Configuration Files

### `.env`
Environment variables for runtime configuration:
```bash
# Core
GARUDA_DB_URL=sqlite:///crawler.db
GARUDA_OLLAMA_URL=http://localhost:11434/api/generate
GARUDA_OLLAMA_MODEL=granite3.1-dense:8b
GARUDA_QDRANT_URL=http://localhost:6333
GARUDA_QDRANT_COLLECTION=pages

# Security
GARUDA_UI_API_KEY=changeme
GARUDA_UI_CORS_ORIGINS=*

# Media
GARUDA_MEDIA_PROCESSING=true
GARUDA_MEDIA_IMAGE_METHOD=tesseract
GARUDA_MEDIA_VIDEO_METHOD=speech
```

### `pyproject.toml`
Project metadata and build configuration:
- Package name: `garuda-intel`
- Version: `0.1.0`
- Entry points: CLI scripts
- Dependencies
- Development tools (ruff, black, mypy)

### `requirements.txt`
Python dependencies:
- flask: Web framework
- sqlalchemy: ORM
- selenium: Browser automation
- qdrant-client: Vector database
- sentence-transformers: Embeddings
- pytesseract: OCR
- beautifulsoup4: HTML parsing
- ddgs: DuckDuckGo search

---

## Data Flow Summary

### 1. Crawl Flow
```
User Input → Gap Analysis → Query Generation → DuckDuckGo Search
    → Browser Fetch → HTML Extraction → LLM Intelligence Extraction
    → Entity Detection → Relationship Extraction → Storage (SQL + Vector)
    → Post-Processing → Learning Update
```

### 2. Search Flow
```
User Question → Embed Query → Vector Search (RAG)
    → Quality Filter (score >= 0.7)
    → SQL Supplement → Merge Results
    → [If insufficient] Auto-Crawl → Re-query
    → LLM Synthesis → Return Answer + Context
```

### 3. Media Flow
```
Page Crawl → Detect Media (images, videos, audio)
    → Score Information Potential → Select Processing Method
    → Extract Text (OCR/Speech-to-Text) → Link to Entities
    → Generate Embeddings → Store to Vector DB
```

---

## Key Design Patterns

### 1. Abstract Factory
- `PersistenceStore` → `SQLAlchemyStore`
- `VectorStore` → `QdrantVectorStore`
- Allows swapping backends without code changes

### 2. Strategy Pattern
- `CrawlMode`: DISCOVERY, TARGETING, EXPANSION
- `MediaProcessingMethod`: Tesseract, Image2Text, Speech
- Different strategies for different scenarios

### 3. Observer Pattern
- `CrawlLearner` observes crawl outcomes
- `EventSystem` logs crawl progress
- Updates based on events

### 4. Repository Pattern
- `PageRepository`, `EntityRepository` (planned)
- Encapsulate data access logic
- Clean separation from business logic

### 5. Composite Pattern
- Intelligence aggregation across multiple pages
- Entity relationship graphs
- Gap analysis across multiple fields

---

## Testing Strategy

### Current Tests
- `tests/`: Basic test suite
- Limited coverage (~20-30%)

### Recommended Test Structure
```
tests/
├── unit/
│   ├── test_browser.py
│   ├── test_extractor.py
│   ├── test_semantic_engine.py
│   ├── test_gap_analyzer.py
│   ├── test_crawler.py
│   └── test_media_processor.py
├── integration/
│   ├── test_crawl_workflow.py
│   ├── test_search_workflow.py
│   └── test_gap_filling_workflow.py
├── e2e/
│   ├── test_webapp_endpoints.py
│   └── test_extension_integration.py
└── fixtures/
    ├── sample_html.html
    ├── sample_entities.json
    └── mock_llm_responses.json
```

---

## Development Workflow

### 1. Adding a New Feature

**Example: Add Twitter/X Integration**

1. Create adapter in `src/garuda_intel/sources/adapters/twitter_adapter.py`
2. Implement `SourceAdapter` interface
3. Add to crawler in `discover/seeds.py`
4. Add configuration in `.env`
5. Write tests in `tests/unit/test_twitter_adapter.py`
6. Update documentation

### 2. Adding a New Entity Type

**Example: Add "Product" Entity Type**

1. Update `types/entity/type.py` with PRODUCT enum
2. Add expected fields in `services/entity_gap_analyzer.py`
3. Update LLM prompts in `extractor/llm.py` to recognize products
4. Add UI handling in `webapp/static/render-intel.js`
5. Test with sample product pages

### 3. Optimizing Performance

**Example: Add Caching Layer**

1. Create `src/garuda_intel/cache/manager.py`
2. Implement LRU cache for embeddings
3. Add Redis cache for LLM responses
4. Update `extractor/semantic_engine.py` to check cache first
5. Add cache metrics to monitoring
6. Document cache invalidation strategy

---

## Common Tasks

### Start Development Server
```bash
# Activate virtual environment
source .venv/bin/activate

# Set environment variables (or use .env)
export GARUDA_DB_URL=sqlite:///crawler.db
export GARUDA_UI_API_KEY=dev-key

# Start web UI
python -m src.garuda_intel.webapp.app

# Or use docker-compose
docker-compose up
```

### Run Tests
```bash
# All tests
pytest tests/

# Specific test file
pytest tests/test_post_crawl_scenario.py -v

# With coverage
pytest tests/ --cov=src/garuda_intel --cov-report=html
```

### Lint & Format
```bash
# Lint
ruff check src/

# Format
black src/

# Type check
mypy src/
```

### Database Operations
```bash
# Create fresh database
python -c "from src.garuda_intel.database.engine import create_tables; create_tables()"

# Export entities
python -m src.garuda_intel.search export --output entities.json

# Import entities
python -m src.garuda_intel.search import --input entities.json
```

### Crawl from CLI
```bash
# Basic crawl
python -m src.garuda_intel.search run --sqlite-path crawler.db

# Intelligent crawl for entity
python -m src.garuda_intel.search intelligent-crawl --entity "Microsoft" --mode targeting

# Gap-filling crawl
python -m src.garuda_intel.search fill-gaps --entity-id abc123
```

---

## Troubleshooting

### Common Issues

1. **"Embedding unavailable" error**
   - Check Qdrant is running: `docker ps | grep qdrant`
   - Verify URL in `.env`
   - Check embedding model loaded: `/api/status`

2. **Browser crashes during crawl**
   - Increase timeout in browser config
   - Check ChromeDriver version matches Chrome
   - Reduce concurrent requests

3. **Database locked errors**
   - SQLite doesn't handle concurrent writes well
   - Use PostgreSQL for production
   - Add connection pooling

4. **LLM extraction fails**
   - Check Ollama is running
   - Verify model is pulled: `ollama list`
   - Check prompt length (max 4096 tokens for some models)

---

## Performance Optimization Tips

1. **Embedding Generation**
   - Cache embeddings (avoid regenerating same text)
   - Use batch embedding when possible
   - Consider smaller model for speed (distilbert)

2. **Database Queries**
   - Add indexes on frequently queried columns
   - Use eager loading for relationships
   - Implement pagination for large result sets

3. **Crawling**
   - Use async/await for concurrent requests
   - Implement rate limiting per domain
   - Cache DNS lookups

4. **Search**
   - Cache frequent queries (TTL: 1 hour)
   - Precompute entity completeness scores
   - Use database views for complex aggregations

---

## Security Considerations

1. **API Security**
   - All endpoints require API key in header: `X-API-Key`
   - CORS configured via `GARUDA_UI_CORS_ORIGINS`
   - No authentication by default (add OAuth/JWT for production)

2. **Input Validation**
   - Sanitize all user inputs
   - Validate URLs before crawling
   - Limit file upload sizes (media)

3. **LLM Safety**
   - Don't send sensitive data to external LLMs
   - Use local Ollama for confidential data
   - Implement prompt injection detection

4. **Browser Security**
   - Run in sandboxed environment
   - Use domain allowlists for crawling
   - Disable JavaScript for untrusted domains

---

## Extending Garuda

### Add Custom Storage Backend

```python
# src/garuda_intel/database/custom_store.py
from garuda_intel.database.store import PersistenceStore

class MongoDBStore(PersistenceStore):
    def __init__(self, connection_string):
        self.client = MongoClient(connection_string)
        self.db = self.client.garuda
    
    def save_entity(self, entity):
        return self.db.entities.insert_one(entity.to_dict())
    
    # Implement other methods...
```

### Add Custom Extraction Strategy

```python
# src/garuda_intel/extractor/custom_extractor.py
from garuda_intel.extractor.intel_extractor import IntelExtractor

class ScientificPaperExtractor(IntelExtractor):
    def extract_intelligence(self, profile, text, ...):
        # Custom logic for scientific papers
        # Extract: authors, citations, methodology, results
        return custom_intel
```

### Add Custom Vector Backend

```python
# src/garuda_intel/vector/weaviate_store.py
from garuda_intel.vector.base import VectorStore

class WeaviateVectorStore(VectorStore):
    def upsert(self, point_id, vector, payload):
        # Weaviate-specific implementation
        pass
```

---

## Contributing

See main [README.md](README.md) for contribution guidelines.

Quick checklist:
- [ ] Code passes `ruff check`
- [ ] Code formatted with `black`
- [ ] Type hints added (passes `mypy`)
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] PR description explains changes

---

## Additional Resources

- **Main Documentation**: [README.md](README.md)
- **Architecture**: [README.md#architecture-overview](README.md#architecture-overview)
- **Optimization Plan**: [V2_OPTIMIZATION_PLAN.md](V2_OPTIMIZATION_PLAN.md)
- **RAG Integration**: [EMBEDDING_RAG_INTEGRATION.md](EMBEDDING_RAG_INTEGRATION.md)
- **Embedding Guide**: [EMBEDDING_LOGGING_GUIDE.md](EMBEDDING_LOGGING_GUIDE.md)
- **Entity Fixes**: [IMPLEMENTATION_SUMMARY_CHAT_ENTITY_FIXES.md](IMPLEMENTATION_SUMMARY_CHAT_ENTITY_FIXES.md)

---

**Last Updated**: 2024-01-28  
**Maintainer**: anorien90
