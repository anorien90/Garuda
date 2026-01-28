# Garuda v2 Optimization Plan

## Executive Summary

This document provides a comprehensive optimization plan for Garuda v2, focusing on universal intel gathering, enhanced content processing, automatic media detection, and architectural improvements. The plan is designed to guide the next development phase with precision and actionable strategies.

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Optimization Strategy 1: Universal Intel Gathering](#optimization-strategy-1-universal-intel-gathering)
3. [Optimization Strategy 2: Content Processing Enhancement](#optimization-strategy-2-content-processing-enhancement)
4. [Optimization Strategy 3: Auto Media Detection & Processing](#optimization-strategy-3-auto-media-detection--processing)
5. [Optimization Strategy 4: Performance & Scalability](#optimization-strategy-4-performance--scalability)
6. [Optimization Strategy 5: Testing & Quality Assurance](#optimization-strategy-5-testing--quality-assurance)
7. [Implementation Roadmap](#implementation-roadmap)
8. [Success Metrics](#success-metrics)

---

## Current State Analysis

### Strengths
✅ **Modular Architecture**: Well-organized components with clear separation of concerns  
✅ **RAG Integration**: Advanced semantic search with embedding-first approach  
✅ **Intelligent Crawling**: Gap-aware, adaptive learning system  
✅ **Multi-layer Extraction**: Heuristic + LLM-powered intelligence extraction  
✅ **Relationship Management**: Complete entity graph with persistent relationships  
✅ **Media Processing**: Optional OCR, speech-to-text, and video processing  
✅ **Chrome Extension**: Browser-based recording and search  

### Areas for Improvement
🔧 **Intel Coverage**: Limited to predefined categories, missing industry-specific fields  
🔧 **Content Processing**: Single embedding model, no content type adaptation  
🔧 **Media Detection**: Manual configuration, no automatic detection of processable media  
🔧 **Performance**: No caching layer, redundant embedding generation  
🔧 **Testing**: Limited test coverage, no integration tests for full workflows  
🔧 **Monitoring**: Basic logging, no metrics dashboard or crawl analytics  

---

## Optimization Strategy 1: Universal Intel Gathering

### Goal
Expand intelligence gathering to be domain-agnostic and self-adapting, automatically identifying and extracting relevant information regardless of entity type or industry.

### 1.1 Dynamic Schema Discovery

**Problem**: Current extraction uses hardcoded categories (basic_info, persons, locations, financials, products, events)

**Solution**: Implement schema-less extraction with LLM-driven field discovery

```python
# Proposed Enhancement: src/garuda_intel/extractor/schema_discovery.py
class DynamicSchemaDiscoverer:
    def discover_fields(self, entity_profile, sample_text):
        """
        Use LLM to identify relevant fields for this entity type
        Returns: {field_name: description, importance, example}
        """
        prompt = f"""
        Analyze this entity profile and sample text.
        Entity: {entity_profile.name} (Type: {entity_profile.kind})
        Sample: {sample_text[:1000]}
        
        Identify 10-15 most relevant data fields to extract for this entity.
        Return as JSON with field_name, description, importance (critical/important/supplementary)
        """
        # Parse LLM response into field schema
        # Cache schema by entity type for reuse
```

**Benefits**:
- Adapts to any entity type (government agencies, products, events, etc.)
- Discovers industry-specific fields automatically
- Reduces manual schema maintenance

**Implementation Priority**: HIGH  
**Estimated Effort**: 3-5 days  
**Dependencies**: Existing LLM infrastructure

### 1.2 Multi-Source Intelligence Aggregation

**Problem**: Limited source diversity - primarily web crawling

**Solution**: Plugin-based source adapters

```python
# Proposed: src/garuda_intel/sources/adapters/
class SourceAdapter(ABC):
    @abstractmethod
    def fetch(self, query: str) -> List[Document]: pass
    
    @abstractmethod
    def normalize(self, raw_data) -> Intelligence: pass

# Implementations:
- PDFAdapter (research papers, reports)
- APIAdapter (REST APIs, GraphQL)
- DatabaseAdapter (external DBs)
- SocialMediaAdapter (Twitter, LinkedIn)
- StructuredDataAdapter (JSON-LD, microdata)
```

**Benefits**:
- Unified interface for diverse sources
- Easy to add new sources without core changes
- Automatic normalization to common format

**Implementation Priority**: MEDIUM  
**Estimated Effort**: 5-7 days  
**Dependencies**: New module creation

### 1.3 Cross-Entity Knowledge Inference

**Problem**: Limited relationship inference, manual relationship definition

**Solution**: Graph-based inference engine

```python
# Enhancement: src/garuda_intel/services/inference_engine.py
class KnowledgeInferenceEngine:
    def infer_missing_data(self, entity_id: str):
        """
        Uses graph traversal and relationship patterns to infer missing data
        Example: If Person A works_at Company B, and Company B has_location City C,
                 infer Person A has probable location City C
        """
        # Get entity graph
        # Apply inference rules
        # Calculate confidence scores
        # Return inferred facts with provenance
```

**Benefits**:
- Fills gaps without additional crawling
- Leverages existing knowledge graph
- Provides confidence-scored inferences

**Implementation Priority**: MEDIUM  
**Estimated Effort**: 4-6 days  

### 1.4 Temporal Intelligence Tracking

**Problem**: No versioning or change tracking for entity data

**Solution**: Temporal database with snapshot capabilities

```python
# Enhancement: src/garuda_intel/database/temporal_store.py
class TemporalIntelligence(Base):
    __tablename__ = "intelligence_history"
    id = Column(String, primary_key=True)
    entity_id = Column(String, ForeignKey("entities.id"))
    data = Column(JSON)
    valid_from = Column(DateTime)
    valid_to = Column(DateTime, nullable=True)  # NULL = current
    change_type = Column(String)  # created, updated, deleted
    
def track_changes(old_intel, new_intel) -> ChangeSet:
    """Compare intelligence versions and create change record"""
```

**Benefits**:
- Track entity evolution over time
- Answer temporal queries ("What was Microsoft's CEO in 2020?")
- Detect anomalies and data drift

**Implementation Priority**: LOW  
**Estimated Effort**: 5-7 days  

---

## Optimization Strategy 2: Content Processing Enhancement

### Goal
Improve content extraction quality, speed, and adaptability through specialized processing pipelines and advanced NLP techniques.

### 2.1 Content Type Detection & Routing

**Problem**: Single processing pipeline for all content types

**Solution**: Classifier-based content routing

```python
# Proposed: src/garuda_intel/extractor/content_classifier.py
class ContentTypeClassifier:
    def classify(self, html: str, url: str) -> ContentType:
        """
        Determines content type: article, profile, listing, forum, product, etc.
        Returns: ContentType enum with confidence
        """
        # URL pattern analysis
        # HTML structure analysis
        # Meta tag inspection
        # ML classifier (lightweight)
        
class ContentRouter:
    def route_to_processor(self, content_type: ContentType):
        """Returns specialized processor for content type"""
        processors = {
            ContentType.ARTICLE: ArticleProcessor(),
            ContentType.PROFILE: ProfileProcessor(),
            ContentType.LISTING: ListingProcessor(),
            ContentType.FORUM: ForumProcessor(),
            ContentType.PRODUCT: ProductPageProcessor()
        }
```

**Benefits**:
- Specialized extraction per content type
- Higher quality results
- Faster processing (skip irrelevant extractors)

**Implementation Priority**: HIGH  
**Estimated Effort**: 4-6 days  

### 2.2 Advanced Text Chunking Strategies

**Problem**: Fixed-size chunking loses context

**Solution**: Semantic chunking with context preservation

```python
# Enhancement: src/garuda_intel/extractor/semantic_chunker.py
class SemanticChunker:
    def chunk_by_topic(self, text: str, max_chunk_size: int = 4000):
        """
        Split text into semantically coherent chunks
        - Preserve paragraph boundaries
        - Keep related sentences together
        - Maintain heading context
        """
        # Use sentence embeddings to detect topic shifts
        # Create chunks at topic boundaries
        # Add heading/context prefix to each chunk
        
    def chunk_with_overlap(self, text: str, chunk_size: int, overlap: int):
        """Sliding window with semantic overlap"""
```

**Benefits**:
- Better context for LLM extraction
- Reduced token waste
- Improved extraction accuracy

**Implementation Priority**: MEDIUM  
**Estimated Effort**: 3-4 days  

### 2.3 Multi-Model Embedding Strategy

**Problem**: Single embedding model (all-MiniLM-L6-v2) for all content

**Solution**: Model selection based on content type and domain

```python
# Enhancement: src/garuda_intel/extractor/embedding_selector.py
class EmbeddingModelSelector:
    models = {
        "general": "all-MiniLM-L6-v2",
        "technical": "allenai/specter",  # Scientific papers
        "legal": "nlpaueb/legal-bert-base-uncased",
        "biomedical": "microsoft/BiomedNLP-PubMedBERT-base",
        "multilingual": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    }
    
    def select_model(self, content_domain: str, entity_type: str):
        """Choose best embedding model for content"""
```

**Benefits**:
- Domain-specific embeddings improve search quality
- Multilingual support
- Better semantic matching

**Implementation Priority**: LOW  
**Estimated Effort**: 2-3 days  
**Trade-off**: Increased storage (multiple embedding sets)

### 2.4 Extraction Quality Validation

**Problem**: No automatic quality assessment of extracted data

**Solution**: Multi-stage validation pipeline

```python
# Enhancement: src/garuda_intel/extractor/quality_validator.py
class ExtractionQualityValidator:
    def validate(self, extracted_intel: Intelligence) -> QualityReport:
        """
        Validates extraction quality across dimensions:
        - Completeness: Are critical fields present?
        - Consistency: Do facts contradict each other?
        - Plausibility: Are values reasonable? (e.g., founding_year not in future)
        - Source reliability: Is source trustworthy?
        """
        
    def auto_correct(self, intel: Intelligence, issues: List[Issue]):
        """Attempt automatic correction of common issues"""
        # Date format normalization
        # Unit conversion (e.g., "5M employees" -> 5000000)
        # Deduplication of repeated facts
```

**Benefits**:
- Higher data quality
- Automatic error detection
- Reduced manual cleanup

**Implementation Priority**: MEDIUM  
**Estimated Effort**: 5-6 days  

---

## Optimization Strategy 3: Auto Media Detection & Processing

### Goal
Automatically identify, download, process, and integrate media content (images, videos, audio) without manual configuration.

### 3.1 Intelligent Media Detection

**Problem**: Media processing requires manual enabling/configuration

**Solution**: Automatic media discovery during crawling

```python
# Enhancement: src/garuda_intel/services/media_detector.py
class MediaDetector:
    def detect_media_on_page(self, html: str, url: str) -> List[MediaItem]:
        """
        Automatically identifies processable media:
        - Images with text (diagrams, infographics, screenshots)
        - Videos with speech
        - Audio files
        - PDFs with embedded images
        """
        # Parse HTML for media elements
        # Analyze media metadata (file size, dimensions, duration)
        # Score media by information potential
        # Return prioritized list
        
    def should_process(self, media: MediaItem) -> bool:
        """
        Decision logic:
        - Image >200px, contains text regions (via quick OCR check)
        - Video >30s with audio track
        - Whitelist domains (social media, news sites)
        """
```

**Benefits**:
- No manual configuration needed
- Processes valuable media automatically
- Reduces storage waste (skip decorative images)

**Implementation Priority**: HIGH  
**Estimated Effort**: 3-4 days  

### 3.2 Adaptive Media Processing

**Problem**: Fixed processing method per media type (tesseract vs image2text)

**Solution**: Automatic method selection based on media characteristics

```python
# Enhancement: src/garuda_intel/services/adaptive_media_processor.py
class AdaptiveMediaProcessor:
    def select_processing_method(self, media: MediaItem) -> ProcessingMethod:
        """
        Selects best method based on:
        - Media type (image/video/audio)
        - Content characteristics (handwritten vs printed, language)
        - Performance requirements (speed vs accuracy)
        - Available resources (GPU, API credits)
        """
        # For images:
        if is_printed_text(media):
            return TesseractOCR()  # Fast, accurate for printed text
        elif is_handwritten(media):
            return AIImage2Text()  # Better for handwriting
        
        # For videos:
        if has_clear_speech(media):
            return AudioTranscription()  # Cheaper than video2text
        else:
            return AIVideo2Text()  # Handle visual-only or poor audio
```

**Benefits**:
- Optimal quality/cost trade-off
- Faster processing
- Better accuracy

**Implementation Priority**: MEDIUM  
**Estimated Effort**: 4-5 days  

### 3.3 Media Content Linking

**Problem**: Extracted media text not linked to source pages/entities

**Solution**: Media-to-entity relationship tracking

```python
# Enhancement: src/garuda_intel/database/models.py
class MediaContent(Base):
    __tablename__ = "media_content"
    id = Column(String, primary_key=True)
    media_url = Column(String, index=True)
    media_type = Column(String)  # image, video, audio
    extracted_text = Column(Text)
    page_id = Column(String, ForeignKey("pages.id"))
    entities_mentioned = Column(JSON)  # List of entity IDs
    processing_method = Column(String)
    confidence = Column(Float)
    
# Enhancement: src/garuda_intel/services/media_linker.py
class MediaEntityLinker:
    def link_media_to_entities(self, media_text: str, page_id: str):
        """Extract entity mentions from media text and create relationships"""
```

**Benefits**:
- Media becomes searchable in knowledge graph
- Answer questions using media content
- Trace information to media sources

**Implementation Priority**: MEDIUM  
**Estimated Effort**: 3-4 days  

### 3.4 Media Processing Pipeline Optimization

**Problem**: Sequential processing, no parallel execution

**Solution**: Asynchronous media processing queue

```python
# Proposed: src/garuda_intel/services/media_queue.py
class MediaProcessingQueue:
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers)
        self.queue = deque()
        
    def enqueue(self, media_item: MediaItem):
        """Add media to processing queue"""
        future = self.executor.submit(self.process_media, media_item)
        future.add_done_callback(self.on_complete)
        
    def process_media(self, media: MediaItem):
        """Download → Process → Extract → Store → Embed"""
        # Runs in background thread
```

**Benefits**:
- Parallel processing of multiple media files
- Non-blocking crawl pipeline
- Better resource utilization

**Implementation Priority**: LOW  
**Estimated Effort**: 2-3 days  
**Dependencies**: Threading or async/await refactoring

---

## Optimization Strategy 4: Performance & Scalability

### Goal
Improve system performance, reduce redundant operations, and enable scaling to large datasets (100K+ entities, millions of pages).

### 4.1 Multi-Layer Caching Strategy

**Problem**: Redundant embedding generation, repeated LLM calls

**Solution**: Comprehensive caching layer

```python
# Proposed: src/garuda_intel/cache/
class CacheManager:
    def __init__(self):
        self.embedding_cache = LRUCache(maxsize=10000)
        self.llm_cache = Redis(host="localhost", port=6379, db=0)
        
    def get_embedding(self, text_hash: str) -> Optional[np.ndarray]:
        """Check cache before generating embedding"""
        
    def cache_llm_response(self, prompt_hash: str, response: str):
        """Cache LLM responses with TTL"""
        # Use Redis for persistence across restarts
        # Set TTL = 7 days for most prompts
```

**Caching Strategies**:
- **Embedding Cache**: LRU in-memory cache for recently used embeddings
- **LLM Response Cache**: Redis-based with TTL for prompt→response mapping
- **Page Content Cache**: Cache parsed HTML to avoid re-parsing
- **Search Result Cache**: Cache frequent queries for 1 hour

**Benefits**:
- 50-70% reduction in embedding generation time
- 80%+ reduction in LLM API costs for repeated queries
- Faster search response times

**Implementation Priority**: HIGH  
**Estimated Effort**: 5-7 days  
**Dependencies**: Redis (optional, can use SQLite for simple cache)

### 4.2 Database Query Optimization

**Problem**: N+1 query issues, full table scans

**Solution**: Optimized queries with proper indexing

```python
# Proposed enhancements to src/garuda_intel/database/models.py
class Entity(Base):
    # Add composite indexes
    __table_args__ = (
        Index('ix_entity_name_kind', 'name', 'kind'),
        Index('ix_entity_created_at', 'created_at'),
    )

# Proposed: Query optimization in repositories
class OptimizedEntityRepository:
    def get_entities_with_intel(self, entity_ids: List[str]):
        """Single query with eager loading instead of N queries"""
        return session.query(Entity).options(
            joinedload(Entity.intelligence),
            joinedload(Entity.outgoing_relationships)
        ).filter(Entity.id.in_(entity_ids)).all()
```

**Optimizations**:
- Add indexes on frequently queried columns (name, kind, url, created_at)
- Use eager loading for relationships (joinedload)
- Implement pagination for large result sets
- Add database connection pooling

**Benefits**:
- 10x faster queries on large datasets
- Reduced database load
- Better scalability

**Implementation Priority**: HIGH  
**Estimated Effort**: 3-4 days  

### 4.3 Asynchronous Crawling Architecture

**Problem**: Sequential crawling, blocking I/O

**Solution**: Async/await based crawler with concurrent execution

```python
# Proposed refactor: src/garuda_intel/browser/async_selenium.py
import asyncio
from playwright.async_api import async_playwright

class AsyncBrowser:
    async def fetch_pages(self, urls: List[str], max_concurrent: int = 5):
        """Fetch multiple pages concurrently"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_one(url):
            async with semaphore:
                return await self._fetch_page(url)
        
        tasks = [fetch_one(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

**Benefits**:
- 5-10x faster crawling with concurrent requests
- Better CPU utilization
- Easier to implement rate limiting

**Implementation Priority**: MEDIUM  
**Estimated Effort**: 7-10 days (significant refactoring)  
**Trade-off**: Requires async/await throughout stack

### 4.4 Monitoring & Observability

**Problem**: Limited visibility into system performance, no metrics

**Solution**: Comprehensive monitoring dashboard

```python
# Proposed: src/garuda_intel/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge

class MetricsCollector:
    crawl_requests = Counter('garuda_crawl_requests_total', 'Total crawl requests')
    crawl_duration = Histogram('garuda_crawl_duration_seconds', 'Crawl duration')
    embedding_generation_time = Histogram('garuda_embedding_time_seconds', 'Embedding time')
    entity_count = Gauge('garuda_entities_total', 'Total entities in DB')
    vector_search_latency = Histogram('garuda_vector_search_seconds', 'Vector search time')
```

**Metrics to Track**:
- Crawl performance (requests/sec, success rate, average duration)
- Extraction quality (fields extracted per page, confidence scores)
- Search performance (query latency, result relevance)
- System health (DB connections, memory usage, cache hit rate)

**Dashboard**: Grafana + Prometheus integration

**Benefits**:
- Identify performance bottlenecks
- Track system health in production
- Alert on anomalies

**Implementation Priority**: LOW  
**Estimated Effort**: 4-5 days  

---

## Optimization Strategy 5: Testing & Quality Assurance

### Goal
Increase test coverage, implement integration tests, and establish CI/CD pipelines for reliable deployments.

### 5.1 Comprehensive Unit Test Suite

**Problem**: Limited test coverage (~20-30% estimated)

**Solution**: Systematic unit testing for all modules

```python
# Proposed: tests/unit/
tests/
├── unit/
│   ├── test_extractor.py
│   ├── test_semantic_engine.py
│   ├── test_crawler.py
│   ├── test_gap_analyzer.py
│   ├── test_media_processor.py
│   ├── test_relationship_manager.py
│   └── test_vector_store.py
├── integration/
│   ├── test_crawl_workflow.py
│   ├── test_search_workflow.py
│   └── test_gap_filling_workflow.py
└── e2e/
    ├── test_webapp_endpoints.py
    └── test_extension_integration.py
```

**Target Coverage**: 80%+ for core modules

**Implementation Priority**: HIGH  
**Estimated Effort**: 10-15 days (ongoing)

### 5.2 Integration Testing

**Problem**: No tests for end-to-end workflows

**Solution**: Integration test suite with fixtures

```python
# Proposed: tests/integration/test_crawl_workflow.py
class TestCrawlWorkflow:
    @pytest.fixture
    def test_env(self):
        """Set up test database, vector store, LLM mock"""
        db = create_test_database()
        vector_store = MockVectorStore()
        llm = MockLLM()
        yield db, vector_store, llm
        cleanup_test_database(db)
    
    def test_full_crawl_pipeline(self, test_env):
        """Test: Query → Crawl → Extract → Store → Embed → Search"""
        db, vector_store, llm = test_env
        
        # 1. Start crawl
        crawler = EntityAwareCrawler(...)
        results = crawler.crawl_for_entity("Test Company", CrawlMode.DISCOVERY)
        
        # 2. Verify extraction
        assert len(results.intelligence) > 0
        
        # 3. Verify storage
        entity = db.get_entity_by_name("Test Company")
        assert entity is not None
        
        # 4. Verify embeddings
        embeddings = vector_store.search("Test Company", top_k=5)
        assert len(embeddings) > 0
```

**Benefits**:
- Catch integration bugs early
- Ensure workflows work end-to-end
- Regression prevention

**Implementation Priority**: HIGH  
**Estimated Effort**: 7-10 days  

### 5.3 CI/CD Pipeline

**Problem**: No automated testing or deployment

**Solution**: GitHub Actions workflow

```yaml
# Proposed: .github/workflows/ci.yml
name: CI/CD Pipeline

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      qdrant:
        image: qdrant/qdrant:latest
        ports:
          - 6333:6333
      
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov ruff black mypy
      
      - name: Lint
        run: |
          ruff check src/
          black --check src/
      
      - name: Type check
        run: mypy src/
      
      - name: Run tests
        run: pytest tests/ --cov=src --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
  
  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - name: Build Docker image
        run: docker build -t garuda:latest .
      
      - name: Push to registry
        if: github.ref == 'refs/heads/main'
        run: docker push garuda:latest
```

**Benefits**:
- Automated testing on every commit
- Catch bugs before merge
- Automated deployments

**Implementation Priority**: MEDIUM  
**Estimated Effort**: 2-3 days  

### 5.4 Data Quality Validation

**Problem**: No validation of extracted data quality

**Solution**: Automated data quality checks

```python
# Proposed: tests/data_quality/
class DataQualityValidator:
    def validate_entity_completeness(self):
        """Check that critical fields are populated"""
        entities = db.query(Entity).all()
        incomplete = []
        for e in entities:
            score = calculate_completeness(e)
            if score < 0.5:
                incomplete.append(e)
        
        assert len(incomplete) < len(entities) * 0.2  # <20% incomplete
    
    def validate_relationship_integrity(self):
        """Check that all relationships point to existing entities"""
        orphaned = db.query(Relationship).filter(
            ~exists().where(Entity.id == Relationship.target_id)
        ).all()
        
        assert len(orphaned) == 0
```

**Implementation Priority**: MEDIUM  
**Estimated Effort**: 4-5 days  

---

## Implementation Roadmap

### Phase 1: Quick Wins (Weeks 1-2)
**Focus**: High-impact, low-effort improvements

- [ ] **Caching Layer** (Strategy 4.1) - 5 days
  - Implement embedding cache
  - Add LLM response cache
  - Add search result cache
  
- [ ] **Content Type Detection** (Strategy 2.1) - 4 days
  - Build content classifier
  - Create specialized processors
  
- [ ] **Media Auto-Detection** (Strategy 3.1) - 3 days
  - Implement media detector
  - Add scoring logic
  
- [ ] **Database Optimization** (Strategy 4.2) - 3 days
  - Add indexes
  - Optimize queries

**Expected Impact**: 50% performance improvement, 30% cost reduction

### Phase 2: Core Enhancements (Weeks 3-5)
**Focus**: Fundamental improvements to extraction and processing

- [ ] **Dynamic Schema Discovery** (Strategy 1.1) - 5 days
  - Build schema discoverer
  - Integrate with extraction pipeline
  
- [ ] **Adaptive Media Processing** (Strategy 3.2) - 4 days
  - Method selection logic
  - Integration with existing processors
  
- [ ] **Semantic Chunking** (Strategy 2.2) - 4 days
  - Implement semantic chunker
  - Replace fixed-size chunking
  
- [ ] **Extraction Quality Validation** (Strategy 2.4) - 6 days
  - Build validator
  - Add auto-correction
  
- [ ] **Comprehensive Testing** (Strategy 5.1, 5.2) - 10 days
  - Unit tests for new modules
  - Integration test suite

**Expected Impact**: 40% extraction quality improvement, 80% test coverage

### Phase 3: Advanced Features (Weeks 6-8)
**Focus**: Advanced intelligence gathering and scalability

- [ ] **Multi-Source Adapters** (Strategy 1.2) - 7 days
  - Build adapter framework
  - Implement PDF and API adapters
  
- [ ] **Knowledge Inference Engine** (Strategy 1.3) - 6 days
  - Graph-based inference
  - Confidence scoring
  
- [ ] **Media-Entity Linking** (Strategy 3.3) - 4 days
  - Media content model
  - Entity linking
  
- [ ] **CI/CD Pipeline** (Strategy 5.3) - 3 days
  - GitHub Actions setup
  - Docker build automation

**Expected Impact**: 2x data coverage, 50% fewer gaps

### Phase 4: Optimization & Monitoring (Weeks 9-10)
**Focus**: Performance tuning and observability

- [ ] **Async Crawling** (Strategy 4.3) - 10 days
  - Refactor to async/await
  - Implement concurrent crawling
  
- [ ] **Multi-Model Embeddings** (Strategy 2.3) - 3 days
  - Model selector
  - Domain-specific models
  
- [ ] **Monitoring Dashboard** (Strategy 4.4) - 5 days
  - Prometheus metrics
  - Grafana dashboards
  
- [ ] **Data Quality Validation** (Strategy 5.4) - 5 days
  - Automated quality checks
  - Regular validation runs

**Expected Impact**: 5x crawling speed, full observability

### Phase 5: Advanced Features (Weeks 11-12)
**Focus**: Temporal tracking and advanced analytics

- [ ] **Temporal Intelligence** (Strategy 1.4) - 7 days
  - Temporal database schema
  - Change tracking
  
- [ ] **Media Processing Queue** (Strategy 3.4) - 3 days
  - Async queue
  - Background processing
  
- [ ] **Final Testing & Documentation** - 5 days
  - End-to-end testing
  - Performance benchmarking
  - Documentation updates

**Expected Impact**: Complete feature set, production-ready

---

## Success Metrics

### Performance Metrics
- **Crawl Speed**: Target 5-10x improvement (from ~5 pages/min to 25-50 pages/min)
- **Search Latency**: <200ms for hybrid search (RAG + SQL)
- **Embedding Generation**: <100ms per page with caching
- **Cache Hit Rate**: >60% for embeddings, >80% for LLM responses

### Quality Metrics
- **Extraction Completeness**: >70% average across all entities
- **Data Accuracy**: >90% precision on validation set
- **Relationship Quality**: >85% correct relationships
- **Media Processing Accuracy**: >80% OCR accuracy, >90% speech-to-text

### Coverage Metrics
- **Test Coverage**: >80% for core modules
- **Entity Field Coverage**: Average 15+ fields per entity (up from ~8)
- **Source Diversity**: >5 different source types
- **Media Coverage**: Process >50% of available media content

### Operational Metrics
- **System Uptime**: >99.5%
- **Error Rate**: <1% for API endpoints
- **Alert Response Time**: <15 minutes for critical issues
- **Deployment Frequency**: Daily deployments with CI/CD

### Business Metrics
- **User Satisfaction**: >4.5/5 on user surveys
- **Time to Insight**: <5 minutes from query to answer
- **Data Quality Score**: >8/10 on manual review
- **Cost Efficiency**: 50% reduction in LLM API costs via caching

---

## Risk Assessment & Mitigation

### Technical Risks

**Risk 1: Async Refactoring Complexity**  
- **Impact**: HIGH  
- **Probability**: MEDIUM  
- **Mitigation**: Incremental migration, extensive testing, fallback to sync mode

**Risk 2: Cache Consistency Issues**  
- **Impact**: MEDIUM  
- **Probability**: MEDIUM  
- **Mitigation**: Cache invalidation strategy, TTL management, monitoring

**Risk 3: Multi-Model Embedding Storage Costs**  
- **Impact**: MEDIUM  
- **Probability**: HIGH  
- **Mitigation**: Selective model usage, storage optimization, cost monitoring

### Operational Risks

**Risk 4: Breaking Changes in Dependencies**  
- **Impact**: MEDIUM  
- **Probability**: LOW  
- **Mitigation**: Version pinning, thorough testing, rollback procedures

**Risk 5: Scaling Database Performance**  
- **Impact**: HIGH  
- **Probability**: MEDIUM  
- **Mitigation**: Database optimization, indexing, consider PostgreSQL migration

---

## Conclusion

This optimization plan provides a comprehensive roadmap for Garuda v2, focusing on:

1. **Universal Intel Gathering**: Dynamic schema discovery, multi-source integration, inference engine
2. **Content Processing**: Content type routing, semantic chunking, quality validation
3. **Media Processing**: Auto-detection, adaptive processing, entity linking
4. **Performance**: Caching, async crawling, database optimization, monitoring
5. **Quality**: Comprehensive testing, CI/CD, data validation

**Key Priorities**:
- Phase 1 quick wins deliver immediate performance improvements
- Phases 2-3 build core capabilities for advanced intelligence gathering
- Phases 4-5 optimize and monitor for production deployment

**Expected Outcomes**:
- 5-10x performance improvement
- 40% better extraction quality
- 80% test coverage
- Production-ready scalability

The plan is designed to be executed incrementally, with each phase delivering measurable value while maintaining system stability.
