# Deep RAG Graph Exploration Features

## Overview

The Garuda Intelligence platform now includes powerful Deep RAG (Retrieval-Augmented Generation) graph exploration features that enable advanced entity discovery, relationship traversal, and path finding within your knowledge graph.

## Features

### 1. Semantic Entity Search

Search for entities using hybrid SQL and semantic embedding similarity matching.

**How to use:**
1. Navigate to the **Graph** tab in the Web UI
2. Locate the **Deep RAG Graph Exploration** section (highlighted in blue)
3. Enter your search query in the "Semantic Entity Search" input
4. Adjust the similarity threshold (default: 0.7) if needed
5. Click **Search**

**What it does:**
- Performs both exact SQL matching and semantic similarity search
- Returns entities ranked by match type (exact vs. semantic) and similarity score
- Automatically highlights matching entities in the graph visualization

**Example queries:**
- "Microsoft Corporation"
- "tech companies"
- "software executives"

### 2. Graph Traversal

Explore entity relationships using depth-based breadth-first search from a selected entity.

**How to use:**
1. Click on any entity node in the graph to select it
2. The "Traverse from Selected" button becomes enabled
3. Set your desired parameters:
   - **Max Depth**: How many relationship hops to traverse (1-5)
   - **Top N**: Maximum entities to return per depth level (5-50)
4. Click **Traverse from Selected**

**What it does:**
- Starts from the selected entity
- Explores outgoing and incoming relationships
- Returns the most connected entities at each depth level
- Displays results in a modal with depth-organized entities
- Optionally adds discovered entities to the current graph view

**Use cases:**
- Discover companies related to a person
- Find products connected to an organization
- Explore multi-level supply chains
- Identify key players in a network

### 3. Path Finding

Find the shortest path between any two entities in the knowledge graph.

**How to use:**
1. Hold **Shift** and click on two different entity nodes
2. The "Find Path" button becomes enabled
3. Click **Find Path**

**What it does:**
- Uses breadth-first search to find the shortest path
- Returns the complete path with all intermediate entities and relationships
- Highlights the discovered path in the graph visualization
- Shows relationship types connecting each entity

**Use cases:**
- Discover how two companies are connected
- Find relationship chains between people
- Trace supply chain connections
- Identify hidden network connections

## API Endpoints

The Deep RAG features are powered by the following REST API endpoints:

### Semantic Search
```
GET /api/graph/search?query=<query>&threshold=<float>&limit=<int>
```

### Graph Traversal
```
POST /api/graph/traverse
Body: {
  "entity_ids": ["uuid1", "uuid2"],
  "max_depth": 2,
  "top_n_per_depth": 10,
  "relation_types": ["works_for", "owns"]  // optional
}
```

### Path Finding
```
GET /api/graph/path?source_id=<uuid>&target_id=<uuid>&max_depth=<int>
```

## Technical Details

### Graph Traversal Algorithm

The graph traversal uses a depth-limited breadth-first search (BFS):

1. **Initialization**: Start with root entity IDs
2. **Depth Iteration**: For each depth level (1 to max_depth):
   - Query all relationships (incoming + outgoing) for current level entities
   - Collect connected entities not yet visited
   - Rank by connection count
   - Select top N entities for next level
3. **Deduplication**: Track visited entities to avoid cycles
4. **Result Packaging**: Return entities organized by depth with relationship metadata

### Semantic Search Scoring

Hybrid search combines two approaches:

1. **SQL Exact Matching** (score: 1.0)
   - Case-insensitive LIKE search on entity names
   - Returns immediate exact matches

2. **Semantic Similarity** (score: 0.0-1.0)
   - Generates embeddings for query and entity names
   - Calculates cosine similarity
   - Filters by threshold (default: 0.7)
   - Sorts by similarity score

Results are merged and deduplicated, with exact matches prioritized.

### Path Finding Algorithm

Uses BFS to guarantee shortest path:

1. **Queue Initialization**: Start with source entity
2. **Level Expansion**: For each entity in queue:
   - Get all connected entities (both directions)
   - Mark as visited with parent reference
   - Check if target reached
3. **Path Reconstruction**: Backtrack from target to source using parent references
4. **Enrichment**: Fetch full entity details and relationship metadata

## Performance Considerations

- **Large Graphs**: Traversal is limited to top-N entities per depth to prevent performance issues
- **Caching**: Relationship queries benefit from database indexes
- **Timeouts**: Deep traversals may take several seconds for large graphs
- **Memory**: Path finding uses BFS which is memory-efficient for typical knowledge graphs

## Future Enhancements

Planned improvements for Deep RAG features:

- [ ] Relationship type filtering in UI
- [ ] Export traversal/path results as JSON/CSV
- [ ] Visual depth indicators with color coding
- [ ] Save and restore graph exploration sessions
- [ ] Collaborative path annotation
- [ ] Probabilistic path scoring
- [ ] Temporal relationship filtering

## Troubleshooting

### "No entities found"
- Check that entities exist in your database
- Try lowering the semantic similarity threshold
- Ensure embeddings are generated for entities

### "Traverse button stays disabled"
- Make sure you've clicked on a node in the graph
- The node must be loaded in the current graph view

### "Path finding returns no results"
- The two entities may not be connected
- Try increasing max_depth parameter
- Check that relationships exist in your database

### "Graph becomes cluttered after traversal"
- Use node/edge filters to focus on specific types
- Reload the graph to reset
- Adjust the Top N parameter to limit results

## Related Documentation

- [Graph API Routes](../src/garuda_intel/webapp/routes/graph_search.py)
- [Graph Search Engine](../src/garuda_intel/extractor/entity_merger.py)
- [Entity Relationships](../src/garuda_intel/database/relationship_manager.py)
