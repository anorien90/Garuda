# Quick Reference: EntityGapAnalyzer.generate_crawl_plan()

## Usage Patterns

### Pattern 1: Legacy - Entity Name Lookup (Still Supported)
```python
from garuda_intel.services.entity_gap_analyzer import EntityGapAnalyzer

analyzer = EntityGapAnalyzer(store)

# Positional arguments (most common legacy pattern)
plan = analyzer.generate_crawl_plan("Microsoft", "company")

# Keyword arguments (alternative legacy pattern)
plan = analyzer.generate_crawl_plan(
    entity_name="Apple Inc", 
    entity_type="company"
)
```

### Pattern 2: New - Direct Entity Object (Now Supported)
```python
from garuda_intel.services.entity_gap_analyzer import EntityGapAnalyzer
from garuda_intel.database.models import Entity

analyzer = EntityGapAnalyzer(store)

# Get entity from database
with store.Session() as session:
    entity = session.query(Entity).filter(Entity.name == "Microsoft").first()
    
    # Use entity object directly - no additional DB lookup!
    plan = analyzer.generate_crawl_plan(entity=entity)
```

### Pattern 3: New - With Task Context (Now Supported)
```python
# With entity object and task context
plan = analyzer.generate_crawl_plan(
    entity=entity,
    task_type="investigate_crawl",
    context="High priority security investigation"
)

# With entity name and task context
plan = analyzer.generate_crawl_plan(
    entity_name="Google",
    task_type="fill_gap",
    context="Missing revenue data from Q4"
)

# Discovery mode with task context
plan = analyzer.generate_crawl_plan(
    entity_name="NewStartup Inc",
    entity_type="company",
    task_type="initial_discovery",
    context="New market entrant analysis"
)
```

## Return Value Structure

### Gap Filling Mode (Entity Found)
```python
{
    "mode": "gap_filling",
    "entity_id": "uuid-string",
    "entity_name": "Entity Name",
    "analysis": {
        "entity_id": "uuid-string",
        "entity_name": "Entity Name",
        "completeness_score": 75.0,
        "missing_fields": ["field1", "field2"],
        "suggested_queries": ["query1", "query2"],
        "suggested_sources": ["source1.com", "source2.com"]
    },
    "strategy": "targeted",
    "queries": ["query1", "query2"],
    "sources": ["source1.com", "source2.com"],
    "priority": "fill_critical_gaps",
    
    # Optional fields (if provided)
    "task_type": "investigate_crawl",
    "context": "High priority investigation"
}
```

### Discovery Mode (Entity Not Found)
```python
{
    "mode": "discovery",
    "entity_name": "New Entity",
    "entity_type": "company",
    "strategy": "comprehensive",
    "queries": ["discovery query1", "discovery query2"],
    "sources": ["source1.com", "source2.com"],
    "priority": "establish_baseline",
    
    # Optional fields (if provided)
    "task_type": "initial_discovery",
    "context": "New market analysis"
}
```

## Parameter Reference

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `entity_name` | `Optional[str]` | Conditional* | `None` | Name of entity to research |
| `entity_type` | `Optional[str]` | No | `None` | Entity type hint (e.g., "company", "person") |
| `entity` | `Optional[Entity]` | Conditional* | `None` | Entity model instance |
| `task_type` | `Optional[str]` | No | `None` | Task categorization |
| `context` | `Optional[str]` | No | `None` | Additional context/reason |

\* Either `entity` or `entity_name` must be provided

## Common Use Cases

### Use Case 1: Agent Service Investigation
```python
# agent_service.py pattern (the fixed use case)
with store.Session() as session:
    entity = session.query(Entity).filter(Entity.name == name).first()
    
    if entity:
        plan = gap_analyzer.generate_crawl_plan(
            entity=entity,
            task_type=task.get("task_type", "fill_gap"),
            context=task.get("reason", "")
        )
```

### Use Case 2: Adaptive Crawler
```python
# adaptive_crawler.py pattern (existing, still works)
plan = gap_analyzer.generate_crawl_plan(entity_name, entity_type)
```

### Use Case 3: Batch Processing
```python
# Process multiple entities efficiently
entities = session.query(Entity).filter(...).all()

for entity in entities:
    plan = gap_analyzer.generate_crawl_plan(
        entity=entity,  # No DB lookup needed!
        task_type="batch_analysis",
        context=f"Batch {batch_id}"
    )
    # Process plan...
```

## Error Handling

### ValueError: Missing Parameters
```python
# This will raise ValueError
try:
    plan = analyzer.generate_crawl_plan()
except ValueError as e:
    print(e)  # "Must provide either 'entity' or 'entity_name' parameter"
```

### Proper Error Handling
```python
def safe_generate_plan(analyzer, entity=None, entity_name=None):
    if entity is None and entity_name is None:
        raise ValueError("Must provide entity or entity_name")
    
    try:
        return analyzer.generate_crawl_plan(
            entity=entity,
            entity_name=entity_name
        )
    except Exception as e:
        logger.error(f"Failed to generate crawl plan: {e}")
        return None
```

## Performance Tips

### ✅ Efficient: Direct Entity Object
```python
# Already have entity? Use it directly!
plan = analyzer.generate_crawl_plan(entity=entity)
# Skips DB lookup - faster!
```

### ⚠️ Less Efficient: Entity Name Lookup
```python
# Forces DB lookup even if you already have the entity
plan = analyzer.generate_crawl_plan(entity_name=entity.name)
# Unnecessary DB query
```

## Migration Guide

### Before (Old Code)
```python
# Only supported entity name
plan = gap_analyzer.generate_crawl_plan("Microsoft", "company")
```

### After (New Code - Both Work)
```python
# Option 1: Still works exactly as before
plan = gap_analyzer.generate_crawl_plan("Microsoft", "company")

# Option 2: New, more efficient if you have entity
plan = gap_analyzer.generate_crawl_plan(entity=entity_obj)

# Option 3: With additional context
plan = gap_analyzer.generate_crawl_plan(
    entity=entity_obj,
    task_type="investigation",
    context="Security audit"
)
```

## Testing Examples

```python
import pytest
from unittest.mock import Mock

def test_generate_plan_with_entity():
    """Test new entity parameter."""
    mock_store = Mock()
    analyzer = EntityGapAnalyzer(mock_store)
    
    mock_entity = Mock()
    mock_entity.id = uuid.uuid4()
    mock_entity.name = "Test Company"
    
    # Mock the analyze_entity_gaps method
    analyzer.analyze_entity_gaps = Mock(return_value={
        "suggested_queries": ["q1"],
        "suggested_sources": ["s1"]
    })
    
    # Test new signature
    plan = analyzer.generate_crawl_plan(entity=mock_entity)
    
    assert plan["entity_name"] == "Test Company"
    assert plan["mode"] == "gap_filling"
```

## Best Practices

1. **Use entity object when available**
   - More efficient (no DB lookup)
   - Guaranteed consistency (same object used throughout)

2. **Use entity_name for discovery**
   - When entity might not exist yet
   - When you only have a name string

3. **Always include task context in workflows**
   - Helps with debugging
   - Enables better tracking
   - Improves observability

4. **Handle errors gracefully**
   - Check for ValueError on missing parameters
   - Validate plan structure before use
   - Log failures for debugging

## Quick Comparison

| Aspect | Legacy (entity_name) | New (entity) |
|--------|---------------------|--------------|
| DB Lookup | Always | Never |
| Performance | Standard | Faster |
| Use Case | Name-based search | Object-based |
| Discovery Support | Yes | No (assumes exists) |
| Task Context | Supported | Supported |

---

**Last Updated:** 2024  
**Version:** Post-fix  
**Status:** Production Ready
