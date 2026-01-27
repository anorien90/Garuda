# Phase 3: Relationship Graph Enhancement - Implementation Guide

## Overview

Phase 3 introduces advanced relationship management capabilities to the Garuda intelligence gathering system. This enhancement provides AI-powered relationship inference, validation, clustering, and graph analysis.

## Components

### 1. RelationshipManager (`database/relationship_manager.py`)

The core component for relationship graph operations.

#### Key Features

- **Relationship Inference**: Use LLM to discover implicit relationships from context
- **Deduplication**: Automatically find and merge duplicate relationships
- **Entity Clustering**: Group entities by relationship patterns
- **Validation**: Ensure relationship integrity (no circular refs, valid entities)
- **Confidence Scoring**: Track and use confidence scores for relationships
- **Graph Export**: Export relationship data in networkx-compatible format

#### Basic Usage

```python
from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.extractor.llm import LLMIntelExtractor
from garuda_intel.database.relationship_manager import RelationshipManager

# Initialize
store = SQLAlchemyStore("sqlite:///garuda.db")
llm = LLMIntelExtractor(
    ollama_url="http://localhost:11434/api/generate",
    model="granite3.1-dense:8b"
)

manager = RelationshipManager(store, llm)
```

#### Example: Infer Relationships

```python
# Given entities and context, infer missing relationships
entity_ids = ["apple-id", "tim-cook-id", "cupertino-id"]
context = """
Tim Cook is the CEO of Apple Inc., which is headquartered 
in Cupertino, California. He has led the company since 2011.
"""

relationships = manager.infer_relationships(
    entity_ids=entity_ids,
    context=context,
    min_confidence=0.7
)

# Returns: [
#   ("tim-cook-id", "apple-id", "ceo_of", 0.85),
#   ("apple-id", "cupertino-id", "headquartered_in", 0.90),
#   ("tim-cook-id", "apple-id", "works_at", 0.88)
# ]

# Save inferred relationships
for source_id, target_id, rel_type, confidence in relationships:
    store.save_relationship(
        from_id=source_id,
        to_id=target_id,
        relation_type=rel_type,
        meta={"confidence": confidence, "inferred": True}
    )
```

#### Example: Deduplicate Relationships

```python
# Remove duplicate relationships, keeping highest confidence
removed = manager.deduplicate_relationships(auto_fix=True)
print(f"Removed {removed} duplicate relationships")
```

#### Example: Validate Relationships

```python
# Check for issues and fix them
report = manager.validate_relationships(fix_invalid=True)

print(f"Total: {report['total']}")
print(f"Valid: {report['valid']}")
print(f"Circular: {report['circular']}")
print(f"Orphaned: {report['orphaned']}")
print(f"Fixed: {report['fixed']}")

# Review issues
for issue in report['issues']:
    print(f"{issue['type']}: {issue['message']}")
```

#### Example: Cluster Entities

```python
# Find all entities connected by specific relationship types
clusters = manager.cluster_entities_by_relation(
    relation_types=["works_at", "ceo_of", "founded_by"]
)

for rel_type, pairs in clusters.items():
    print(f"\n{rel_type}: {len(pairs)} relationships")
    for source_id, target_id in pairs:
        print(f"  {source_id} -> {target_id}")
```

#### Example: Get Relationship Graph

```python
# Export graph for visualization
graph = manager.get_relationship_graph(
    entity_ids=["apple-id", "tim-cook-id"],
    min_confidence=0.7,
    include_metadata=True
)

# Convert to networkx
import networkx as nx

G = nx.DiGraph()
for node in graph['nodes']:
    G.add_node(node['id'], **node)

for edge in graph['edges']:
    G.add_edge(edge['source'], edge['target'], **edge)

# Visualize or analyze
print(f"Nodes: {G.number_of_nodes()}")
print(f"Edges: {G.number_of_edges()}")
```

#### Example: Find Entity Clusters

```python
# Find connected components in the graph
clusters = manager.find_entity_clusters(
    min_cluster_size=3,
    relation_types=["works_at", "subsidiary_of"]
)

for i, cluster in enumerate(clusters):
    print(f"Cluster {i}: {len(cluster)} entities")
    # cluster is a list of entity IDs
```

### 2. Enhanced Database Queries (`database/engine.py`)

New methods added to `SQLAlchemyStore`:

#### `get_relationship_by_entities(source_id, target_id, relation_type=None)`

Get a specific relationship between two entities.

```python
rel = store.get_relationship_by_entities(
    source_id="apple-id",
    target_id="tim-cook-id",
    relation_type="employs"
)
```

#### `get_all_relationships_for_entity(entity_id)`

Get all incoming and outgoing relationships for an entity.

```python
relationships = store.get_all_relationships_for_entity("apple-id")
for rel in relationships:
    print(f"{rel.source_id} --[{rel.relation_type}]--> {rel.target_id}")
```

#### `update_relationship_metadata(relationship_id, metadata)`

Update metadata for a relationship (e.g., confidence score).

```python
store.update_relationship_metadata(
    relationship_id="rel-123",
    metadata={
        "confidence": 0.95,
        "verified": True,
        "source": "manual"
    }
)
```

#### `delete_relationship(relationship_id)`

Delete a relationship.

```python
success = store.delete_relationship("rel-123")
```

#### `get_entity_clusters(relation_type=None, min_cluster_size=2)`

Find clusters of connected entities.

```python
clusters = store.get_entity_clusters(
    relation_type="works_at",
    min_cluster_size=3
)
```

### 3. Explorer Integration

The `IntelligentExplorer` now automatically:

1. **Adds confidence scores** when creating relationships from LLM findings
2. **Validates relationships** after each crawl
3. **Deduplicates relationships** automatically
4. **Logs relationship quality metrics**

#### Automatic Post-Crawl Cleanup

After each crawl, the explorer:

```python
# In IntelligentExplorer.explore():
# ...crawling happens...

# Automatic cleanup (runs in finally block)
if self.relationship_manager:
    # Remove duplicates
    duplicates_removed = self.relationship_manager.deduplicate_relationships()
    
    # Validate and fix issues
    report = self.relationship_manager.validate_relationships(fix_invalid=True)
    
    logger.info(
        f"Relationships: {report['valid']}/{report['total']} valid, "
        f"{report['fixed']} fixed, {duplicates_removed} duplicates removed"
    )
```

## Advanced Patterns

### Pattern 1: Relationship Confidence Tracking

Track and update confidence scores over time:

```python
# When creating relationship
store.save_relationship(
    from_id=source_id,
    to_id=target_id,
    relation_type="works_at",
    meta={
        "confidence": 0.75,
        "source": "llm_inference",
        "created_by": "crawler_v3"
    }
)

# Later, update confidence based on additional evidence
manager.add_relationship_confidence(rel_id, 0.90)
```

### Pattern 2: Incremental Relationship Building

Build relationships incrementally as you discover entities:

```python
# During crawl
page_entities = []  # Entities found on current page

for entity_dict in extracted_entities:
    entity_id = store.save_entities([entity_dict])
    page_entities.append(entity_id)

# Infer relationships among page entities
if len(page_entities) >= 2:
    inferred = manager.infer_relationships(
        entity_ids=page_entities,
        context=page_text[:2000],  # Use page text as context
        min_confidence=0.6
    )
    
    # Save inferred relationships
    for src, tgt, rel_type, conf in inferred:
        store.save_relationship(src, tgt, rel_type, {"confidence": conf})
```

### Pattern 3: Graph Analysis

Analyze the relationship graph to find insights:

```python
# Get full graph
graph = manager.get_relationship_graph(min_confidence=0.7)

# Convert to networkx for analysis
import networkx as nx

G = nx.DiGraph()
for node in graph['nodes']:
    G.add_node(node['id'], **node)
for edge in graph['edges']:
    G.add_edge(edge['source'], edge['target'], **edge)

# Find central entities
centrality = nx.degree_centrality(G)
top_entities = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:10]

print("Most connected entities:")
for entity_id, score in top_entities:
    entity = next(n for n in graph['nodes'] if n['id'] == entity_id)
    print(f"  {entity['name']}: {score:.2f}")

# Find relationship paths
if nx.has_path(G, "entity-a", "entity-b"):
    path = nx.shortest_path(G, "entity-a", "entity-b")
    print(f"Path: {' -> '.join(path)}")
```

### Pattern 4: Relationship Quality Monitoring

Monitor and maintain relationship quality:

```python
def monitor_relationship_quality(manager):
    """Run periodic relationship quality checks."""
    
    # Validate all relationships
    report = manager.validate_relationships(fix_invalid=True)
    
    # Log metrics
    metrics = {
        "total": report['total'],
        "valid_pct": report['valid'] / report['total'] * 100 if report['total'] > 0 else 0,
        "circular": report['circular'],
        "orphaned": report['orphaned'],
        "fixed": report['fixed']
    }
    
    print(f"Relationship Quality Report:")
    print(f"  Total: {metrics['total']}")
    print(f"  Valid: {metrics['valid_pct']:.1f}%")
    print(f"  Issues Fixed: {metrics['fixed']}")
    
    # Alert if quality is poor
    if metrics['valid_pct'] < 90:
        print("WARNING: Relationship quality below threshold!")
    
    return metrics

# Run monthly
metrics = monitor_relationship_quality(manager)
```

## API Reference

### RelationshipManager

#### Methods

- `infer_relationships(entity_ids, context=None, min_confidence=0.5)` → List[Tuple]
- `deduplicate_relationships(auto_fix=True)` → int
- `cluster_entities_by_relation(relation_types=None)` → Dict[str, List[Tuple]]
- `validate_relationships(fix_invalid=False)` → Dict[str, Any]
- `add_relationship_confidence(relationship_id, confidence)` → bool
- `get_relationship_graph(entity_ids=None, min_confidence=0.0, include_metadata=True)` → Dict
- `find_entity_clusters(min_cluster_size=2, relation_types=None)` → List[List[str]]

### SQLAlchemyStore (New Methods)

- `get_relationship_by_entities(source_id, target_id, relation_type=None)` → Optional[Relationship]
- `get_all_relationships_for_entity(entity_id)` → List[Relationship]
- `update_relationship_metadata(relationship_id, metadata)` → bool
- `delete_relationship(relationship_id)` → bool
- `get_entity_clusters(relation_type=None, min_cluster_size=2)` → List[List[str]]

## Configuration

### Confidence Thresholds

Recommended confidence thresholds for different use cases:

- **High precision** (0.8-1.0): Only very confident relationships
- **Balanced** (0.6-0.8): Good mix of precision and recall
- **High recall** (0.4-0.6): Capture more relationships, may have noise
- **Exploratory** (0.0-0.4): Capture everything for manual review

### Performance Considerations

- **Relationship inference** can be slow for large entity sets (O(n²) comparisons)
- **Clustering** uses DFS, efficient for sparse graphs
- **Validation** scans all relationships, run periodically not on every query
- **Deduplication** groups by key, scales well

### Best Practices

1. **Run validation periodically**, not on every operation
2. **Set appropriate confidence thresholds** for your domain
3. **Use relationship types consistently** (e.g., always "works_at" not "employed_by")
4. **Monitor relationship quality** over time
5. **Batch relationship creation** when possible
6. **Clean up orphaned relationships** regularly

## Troubleshooting

### Common Issues

**Issue**: Relationship inference returns no results

**Solutions**:
- Check that LLM is running and accessible
- Verify entity_ids are valid
- Lower min_confidence threshold
- Provide better context text

**Issue**: Too many duplicate relationships

**Solutions**:
- Run `deduplicate_relationships()` more frequently
- Check confidence scoring logic
- Ensure unique constraints are working

**Issue**: Validation finds many orphaned relationships

**Solutions**:
- Entity deletion cascades may not be working
- Run validation with `fix_invalid=True`
- Check entity lifecycle management

## Migration Guide

If upgrading from Phase 2:

1. **No schema changes required** - uses existing Relationship model
2. **Import new module**: `from garuda_intel.database.relationship_manager import RelationshipManager`
3. **Initialize in code**: `manager = RelationshipManager(store, llm)`
4. **Optional**: Run initial cleanup: `manager.validate_relationships(fix_invalid=True)`

## Testing

Example test cases:

```python
def test_relationship_inference():
    """Test relationship inference from context."""
    manager = RelationshipManager(store, llm)
    
    # Create test entities
    apple_id = store.save_entities([{"name": "Apple Inc.", "kind": "company"}])
    tim_id = store.save_entities([{"name": "Tim Cook", "kind": "person"}])
    
    # Infer relationships
    rels = manager.infer_relationships(
        entity_ids=[apple_id, tim_id],
        context="Tim Cook is the CEO of Apple Inc."
    )
    
    assert len(rels) > 0
    assert any(r[2] in ["ceo_of", "works_at"] for r in rels)

def test_deduplication():
    """Test duplicate removal."""
    manager = RelationshipManager(store, llm)
    
    # Create duplicates
    for i in range(3):
        store.save_relationship(
            from_id=entity1_id,
            to_id=entity2_id,
            relation_type="works_at",
            meta={"confidence": 0.5 + i * 0.1}
        )
    
    # Deduplicate
    removed = manager.deduplicate_relationships()
    assert removed == 2  # Kept highest confidence, removed 2
```

## Future Enhancements

Potential improvements for Phase 4:

1. **Temporal relationships**: Track when relationships were active
2. **Relationship strength**: Beyond confidence, track "importance"
3. **Automatic relationship typing**: Use LLM to suggest relation types
4. **Graph embeddings**: Use GNN for better relationship inference
5. **Provenance tracking**: Track source of each relationship
6. **Relationship versioning**: Keep history of relationship changes

## Support

For issues or questions:
- Check logs for detailed error messages
- Verify LLM is running: `curl http://localhost:11434/api/generate`
- Review validation report for specific issues
- Enable debug logging: `logging.getLogger('garuda_intel.database.relationship_manager').setLevel(logging.DEBUG)`
