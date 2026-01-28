# Embedding and Qdrant Logging Guide

## Overview

This document explains the logging that has been added to track embedding generation and Qdrant vector store operations throughout the system.

## What to Expect in Logs

### 1. Startup Logs

When the application starts, you should see:

```
INFO - Starting Garuda Intel Webapp with DB: sqlite:///...
INFO - Qdrant Vector Store: http://qdrant:6333 Collection: pages
INFO - Ollama LLM: http://ollama:11434/api/generate Model: granite3.1-dense:8b
INFO - Embedding Model: sentence-transformers/all-MiniLM-L6-v2
INFO - Initializing Qdrant vector store at http://qdrant:6333
INFO - QdrantVectorStore initialized: url=http://qdrant:6333, collection=pages, vector_size=384
INFO - Using existing Qdrant collection: pages
INFO - ✓ Vector store initialized successfully
INFO - Loaded embedding model: sentence-transformers/all-MiniLM-L6-v2
```

### 2. During Crawling (Per Page)

For each page crawled, you should see:

```
INFO - Generating embeddings for page: https://example.com/page
INFO - Built 15 embeddings for page https://example.com/page
INFO - Upserting 15 embeddings to Qdrant for page: https://example.com/page
DEBUG - Upserted embedding to Qdrant: collection=pages, point_id=..., payload_type=page
DEBUG - Upserted embedding to Qdrant: collection=pages, point_id=..., payload_type=page_sentence
...
INFO - Successfully stored 15 embeddings in Qdrant
```

**Key Points:**
- "Generating embeddings" confirms the process started
- "Built X embeddings" shows how many were created
- "Upserting X embeddings" shows they're being sent to Qdrant
- Individual DEBUG logs for each upsert (only visible with DEBUG logging enabled)
- "Successfully stored" confirms all were saved

### 3. Post-Crawl Processing

After crawling completes, you should see:

```
INFO - Step 6/6: Generating embeddings for entities and intelligence...
INFO - Generated 42 embeddings
```

This is the batch processing phase where:
- Entity embeddings are generated/updated
- Intelligence item embeddings are generated
- Page embeddings are regenerated after deduplication

### 4. Error Scenarios

#### Qdrant Unavailable at Startup

```
INFO - Initializing Qdrant vector store at http://qdrant:6333
ERROR - ✗ Qdrant unavailable - embeddings will NOT be generated: ConnectionRefusedError: [Errno 111] Connection refused
```

**What this means:** Qdrant service is not running or not accessible. Embeddings will NOT be generated.

**How to fix:**
1. Check if Qdrant container is running: `docker ps | grep qdrant`
2. Check Qdrant URL in .env: `GARUDA_QDRANT_URL`
3. Start Qdrant if needed: `docker-compose up -d garuda-qdrant`

#### Vector Store Disabled

```
WARNING - ✗ Vector store disabled (vector_enabled=False) - embeddings will NOT be generated
```

**What this means:** Vector store is intentionally disabled in configuration.

**How to enable:**
1. Check .env file for `GARUDA_QDRANT_URL`
2. Ensure `GARUDA_QDRANT_URL` is set (not commented out)
3. Restart the application

#### Embedding Generation Failures

```
WARNING - Vector store not available - skipping embedding generation for https://example.com
```

This appears when vector store is unavailable during crawling.

```
WARNING - Failed to generate embedding for entity Microsoft (empty vector returned)
```

This means the embedding model returned an empty vector - possibly text was too short or empty.

```
ERROR - Failed to persist embeddings for https://example.com: KeyError: 'text'
Traceback (most recent call last):
  ...
```

This is a more serious error with full traceback for debugging.

## Troubleshooting

### Problem: No Embedding Logs Appear

**Check:**
1. **Logging Level**: Ensure logging is set to INFO or DEBUG
   ```python
   import logging
   logging.basicConfig(level=logging.INFO)
   ```

2. **Vector Store Status**: Look for startup messages
   - If you see "✓ Vector store initialized successfully" → embeddings should work
   - If you see "✗ Qdrant unavailable" → embeddings won't work
   - If you see "✗ Vector store disabled" → embeddings are turned off

3. **Qdrant Service**: Check if Qdrant is running
   ```bash
   docker ps | grep qdrant
   curl http://localhost:6333/collections
   ```

### Problem: "Vector store not available" During Crawling

**Possible Causes:**
1. Qdrant went down after startup
2. Network issue between app and Qdrant
3. Vector store initialization failed silently

**Solution:**
1. Check Qdrant logs: `docker logs garuda-qdrant`
2. Restart Qdrant: `docker-compose restart garuda-qdrant`
3. Check network connectivity from app container

### Problem: "Empty Vector Returned" Warnings

**This is normal if:**
- Entity has very short or empty name
- Page has no meaningful text content
- Text is below minimum length threshold (10 characters)

**Not a critical error** - just means that specific item couldn't be embedded.

### Problem: Seeing Logs but No PUT to Qdrant in Network Monitor

**This likely means:**
1. You're monitoring the wrong network interface
2. Qdrant is running in same container/network (traffic is internal)
3. Using Docker network - traffic doesn't go through host interface

**To verify Qdrant is actually receiving data:**
```bash
# Check Qdrant collection info
curl http://localhost:6333/collections/pages

# Should show:
# - "points_count": > 0 (means vectors are stored)
# - "vectors_count": > 0
```

## Log Levels

The system uses appropriate log levels:

| Level | Used For | Example |
|-------|----------|---------|
| DEBUG | Individual upserts, detailed stats | "Upserted embedding to Qdrant: point_id=..." |
| INFO | Normal operations, success messages | "Successfully stored 15 embeddings" |
| WARNING | Non-critical issues | "Failed to generate embedding (empty vector)" |
| ERROR | Critical failures | "Failed to persist embeddings: ConnectionError" |

## Expected Volume

For a typical crawl of 10 pages:

- **INFO logs**: ~40-60 messages (4-6 per page)
- **DEBUG logs**: ~150-300 messages (15-30 per page for upserts)

Post-crawl processing adds:
- **INFO logs**: 2-3 messages
- **WARNING logs**: 0-5 (if any items fail)

## Verification Checklist

To confirm embeddings are working:

1. ✅ **Startup**: See "✓ Vector store initialized successfully"
2. ✅ **Per Page**: See "Built X embeddings for page"
3. ✅ **Per Page**: See "Successfully stored X embeddings in Qdrant"
4. ✅ **Post-Crawl**: See "Generated X embeddings"
5. ✅ **Qdrant Check**: Run `curl http://localhost:6333/collections/pages` and see points_count > 0

If all 5 checks pass, embeddings are working correctly!

## Configuration Reference

Key environment variables:

```bash
# Required for embeddings
GARUDA_QDRANT_URL=http://garuda-qdrant:6333  # Must be set
GARUDA_QDRANT_COLLECTION=pages                # Collection name
GARUDA_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2  # Embedding model

# LLM (also required for embedding generation)
GARUDA_OLLAMA_URL=http://garuda-ollama:11434/api/generate
GARUDA_OLLAMA_MODEL=granite3.1-dense:8b
```

If `GARUDA_QDRANT_URL` is not set or empty, vector store is disabled and you'll see:
```
WARNING - ✗ Vector store disabled (vector_enabled=False) - embeddings will NOT be generated
```

## Summary

The logging system now provides complete visibility into:
- ✅ Whether embeddings are being generated
- ✅ How many embeddings are created per page
- ✅ When data is sent to Qdrant
- ✅ Any errors or issues that occur
- ✅ Why embeddings might not be working

No more silent failures - you'll know exactly what's happening with your embeddings!
