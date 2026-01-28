# Embedding and RAG Integration Enhancement

## Overview

This document describes the enhancements made to fully integrate embeddings and RAG (Retrieval Augmented Generation) into the Garuda Intelligence Assistant's chat interface.

## Problem Statement

The original system had the following issues:
1. Embeddings were being generated but not prioritized in the chat interface
2. RAG (semantic search) was available but SQL keyword search was prioritized
3. No clear indication of when RAG vs SQL results were being used
4. Automatic crawling trigger wasn't clearly tied to RAG result quality
5. UI didn't show the source of context (RAG vs SQL)

## Solution Architecture

### 3-Phase Chat Flow

The enhanced chat system now uses a **RAG-first, 3-phase approach**:

#### Phase 1: RAG Lookup with Quality Assessment
1. **Prioritize Semantic Search**: Query vector store (Qdrant) first with user's question
2. **Quality Threshold**: Apply similarity score threshold (0.7) to identify high-quality RAG results
3. **Smart Fallback**: Supplement with SQL keyword search only if needed
4. **Detailed Logging**: Track RAG performance through event system

```python
# Example from search.py
def gather_hits(q: str, limit: int, prioritize_rag: bool = True):
    vec_hits = []  # RAG results
    sql_hits = []  # SQL keyword results
    
    # Try RAG first
    if vector_store:
        res = vector_store.search(vec, top_k=limit * 2)
        vec_hits = [...semantic results...]
    
    # Get SQL as fallback/supplement
    sql_hits = store.search_intel(keyword=q, limit=limit)
    
    # Prioritize RAG results
    if prioritize_rag and vec_hits:
        merged = vec_hits[:limit]
        if len(merged) < limit:
            merged.extend(sql_hits[:limit - len(merged)])
    
    return merged
```

#### Phase 2: Intelligent Crawling (When Needed)
Triggers automatic crawling when:
- No RAG results found at all
- Less than 2 high-quality RAG results (similarity < 0.7)
- Answer is insufficient despite RAG results

```python
# Crawl trigger logic
if not rag_hits:
    crawl_reason = "No RAG results found"
elif len(high_quality_rag) < 2:
    crawl_reason = f"Insufficient high-quality RAG results ({len(high_quality_rag)})"
else:
    crawl_reason = "Answer insufficient despite RAG results"
```

When triggered:
1. Generate targeted search queries using LLM
2. Find candidate URLs via DuckDuckGo
3. Crawl pages using IntelligentExplorer
4. **Automatically generate embeddings** during crawl (via PostCrawlProcessor)

#### Phase 3: Re-query with Fresh Data
After successful crawl:
1. Re-run RAG lookup with newly generated embeddings
2. Synthesize improved answer from enhanced context
3. Report new RAG hit count to user

### UI Enhancements

#### Color-Coded Badges
- 🧠 **Purple**: RAG/Semantic hits - "🧠 RAG: 5 semantic hits"
- 📊 **Blue**: SQL keyword hits - "📊 SQL: 3 keyword hits"  
- 🌐 **Green**: Live crawl triggered - "🌐 Live Crawl: Insufficient high-quality RAG results (1)"

#### Enhanced Context Display
Each context item now shows:
- Source type (RAG or SQL) with color coding
- Similarity score (for RAG results)
- Result kind (page, entity, finding, etc.)
- Entity name (if applicable)
- Snippet text

```javascript
// Example from render-chat.js
const sourceClass = ctx.source === 'rag' 
  ? 'border-purple-200 dark:border-purple-800/50 bg-purple-50/50'
  : 'border-slate-100 dark:border-slate-800 bg-white';
const sourceLabel = ctx.source === 'rag' ? '🧠 RAG' : '📊 SQL';
```

## Embedding Generation Flow

### During Crawl (Immediate)
```
Page Crawled → Extract Intelligence → Save to SQL → Generate Embeddings → Store in Qdrant
```

Location: `explorer/engine.py` lines 490-521

### Post-Crawl Processing (Comprehensive)
```
All Crawls Done → PostCrawlProcessor → 6-Step Pipeline:
  1. Entity deduplication
  2. Relationship validation
  3. Intelligence aggregation
  4. Cross-entity inference
  5. Data quality improvements
  6. Embedding regeneration ← Ensures all deduplicated data has embeddings
```

Location: `discover/post_crawl_processor.py` lines 377-502

## Configuration

### Required Services
- **Qdrant**: Vector database for embeddings (`GARUDA_QDRANT_URL`)
- **Ollama**: LLM for intelligence extraction (`GARUDA_OLLAMA_URL`)
- **Sentence Transformers**: Embedding model (loaded automatically)

### Environment Variables
```bash
# Vector Store
export GARUDA_QDRANT_URL=http://garuda-qdrant:6333
export GARUDA_QDRANT_COLLECTION=pages

# Embedding Model
export GARUDA_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2

# LLM
export GARUDA_OLLAMA_URL=http://garuda-ollama:11434/api/generate
export GARUDA_OLLAMA_MODEL=granite3.1-dense:8b
```

## API Response Format

### Chat Endpoint (`POST /api/chat`)

**Request:**
```json
{
  "question": "What is Microsoft's revenue?",
  "entity": "Microsoft",
  "top_k": 6
}
```

**Response:**
```json
{
  "answer": "According to the latest data...",
  "context": [
    {
      "url": "https://example.com/page",
      "snippet": "Microsoft reported...",
      "score": 0.87,
      "source": "rag",
      "kind": "page",
      "entity": "Microsoft"
    }
  ],
  "entity": "Microsoft",
  "online_search_triggered": true,
  "live_urls": ["https://example.com/..."],
  "crawl_reason": "Insufficient high-quality RAG results (1)",
  "rag_hits_count": 5,
  "sql_hits_count": 2
}
```

## Testing

### Manual Testing Steps

1. **Test RAG-first behavior**:
   ```bash
   curl -X POST http://localhost:8080/api/chat \
     -H "Content-Type: application/json" \
     -d '{"question": "What does Microsoft do?"}'
   ```
   - Should see `rag_hits_count` > 0 in response
   - Check logs for "RAG lookup starting" events

2. **Test automatic crawling**:
   ```bash
   curl -X POST http://localhost:8080/api/chat \
     -H "Content-Type: application/json" \
     -d '{"question": "What is XYZ123 company?"}'
   ```
   - For unknown entities, should trigger crawl
   - Response should have `online_search_triggered: true`
   - Should see `crawl_reason` explaining why

3. **Test UI indicators**:
   - Open http://localhost:8080
   - Go to Search tab, Chat section
   - Ask a question
   - Verify color-coded badges appear
   - Check context items show source type

### Automated Testing

The existing test suite covers embedding generation:
```bash
pytest tests/test_post_crawl_scenario.py -v
```

## Performance Considerations

### Embedding Generation
- **Immediate**: Generated during crawl for instant availability
- **Batch**: Regenerated in post-processing for deduplicated data
- **Optimization**: For datasets >10K items, consider adding tracking to skip already-embedded items

### RAG Query Performance
- Vector search is typically faster than SQL full-text search
- Qdrant uses HNSW index for efficient similarity search
- Default top_k=12 (limit * 2) provides good coverage without overhead

## Troubleshooting

### "Embedding unavailable" Error
**Cause**: Vector store (Qdrant) not running or unreachable

**Solutions**:
1. Check Qdrant is running: `docker ps | grep qdrant`
2. Verify connection: `curl http://localhost:6333/collections`
3. Check logs: `docker logs garuda-qdrant`

### No RAG Results
**Cause**: Embeddings not generated yet

**Solutions**:
1. Run a crawl to generate embeddings
2. Check embedding model is loaded: Check `/api/status` endpoint
3. Verify vector store has data: Check Qdrant dashboard

### Crawling Always Triggers
**Cause**: RAG quality threshold too high or embeddings not matching queries well

**Solutions**:
1. Lower quality threshold in `search.py` (currently 0.7)
2. Check embedding model matches data domain
3. Review generated embeddings in Qdrant

## Files Changed

### Backend
- `src/garuda_intel/webapp/routes/search.py`: Enhanced chat endpoint with RAG-first logic
  - New `gather_hits()` with RAG prioritization
  - Quality threshold checking
  - Detailed event logging
  - 3-phase approach implementation

### Frontend
- `src/garuda_intel/webapp/static/render-chat.js`: Enhanced UI display
  - Color-coded badges for source types
  - Detailed context item rendering
  - RAG/SQL hit count display
  
- `src/garuda_intel/webapp/static/ui.js`: Updated pill function
  - Support for custom CSS classes
  - Maintains backward compatibility

### Documentation
- `EMBEDDING_RAG_INTEGRATION.md`: This document

## Future Enhancements

1. **Adaptive Quality Threshold**: Automatically adjust based on query type
2. **Hybrid Ranking**: Combine RAG similarity scores with SQL relevance
3. **Feedback Loop**: Learn from user interactions to improve RAG ranking
4. **Embedding Cache**: Track which items have embeddings to avoid regeneration
5. **Multi-modal Embeddings**: Include image and video embeddings in RAG

## References

- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Sentence Transformers](https://www.sbert.net/)
- [RAG Pattern Guide](https://www.anthropic.com/research/retrieval-augmented-generation)
