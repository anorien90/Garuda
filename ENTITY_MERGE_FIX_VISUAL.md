# Entity Merge Fix - Quick Reference

## The Problem (Before Fix)

```
BEFORE MERGE:
┌─────────────┐         ┌─────────────┐
│  Microsoft  │────────▶│ Bill Gates  │  Relationship: FOUNDED_BY
│  (source)   │         │             │
└─────────────┘         └─────────────┘
       ▲                       │
       └───────────────────────┘       Relationship: FOUNDED

┌──────────────────┐
│ Microsoft Corp   │  (target)
│                  │
└──────────────────┘

AFTER MERGE (BUGGY):
┌──────────────────┐
│ Microsoft Corp   │  ← Only survivor, but...
│                  │
└──────────────────┘

❌ ALL RELATIONSHIPS LOST! (CASCADE deleted)
❌ EntityFieldValue records lost!
❌ Intelligence records orphaned!
❌ Page references orphaned!
❌ MediaItem references orphaned!
```

## The Fix (After Fix)

```
BEFORE MERGE:
┌─────────────┐         ┌─────────────┐
│  Microsoft  │────────▶│ Bill Gates  │  Relationship: FOUNDED_BY
│  (source)   │         │             │
└─────────────┘         └─────────────┘
       ▲                       │
       └───────────────────────┘       Relationship: FOUNDED

┌──────────────────┐
│ Microsoft Corp   │  (target)
│                  │
└──────────────────┘

STEP 1: Transfer all references to target
- EntityFieldValue: entity_id → target
- Intelligence: entity_id → target
- Page: entity_id → target
- MediaItem: entity_id → target
- FieldDiscoveryLog: entity_id → target

STEP 2: Redirect relationships
- Microsoft → Bill Gates becomes Microsoft Corp → Bill Gates
- Bill Gates → Microsoft becomes Bill Gates → Microsoft Corp

STEP 3: ⚡ FLUSH (CRITICAL!)
session.flush()  ← Persists FK updates BEFORE delete

STEP 4: Delete source entity
- Now safe to delete Microsoft (no CASCADE issues)

STEP 5: Clean up
- Remove self-referential relationships (if any)
- Deduplicate relationships (if any)

AFTER MERGE (FIXED):
┌──────────────────┐         ┌─────────────┐
│ Microsoft Corp   │────────▶│ Bill Gates  │  Relationship: FOUNDED_BY
│  (survivor)      │         │             │
└──────────────────┘         └─────────────┘
       ▲                             │
       └─────────────────────────────┘       Relationship: FOUNDED

✅ ALL RELATIONSHIPS PRESERVED!
✅ EntityFieldValue records transferred!
✅ Intelligence records transferred!
✅ Page references transferred!
✅ MediaItem references transferred!
✅ Data merged (source fills gaps in target)!
✅ Metadata merged!
```

## Key Code Change

```python
# OLD CODE (BUGGY):
def _merge_entities(self, session, source_id, target_id):
    # ... redirect relationships ...
    for rel in relationships:
        rel.source_id = target_id  # FK update in memory
    
    session.delete(source)  # ❌ CASCADE deletes relationships!
    # FK updates never flushed to DB before CASCADE!

# NEW CODE (FIXED):
def _merge_entities(self, session, source_id, target_id):
    # ... transfer all references ...
    # ... redirect relationships ...
    for rel in relationships:
        rel.source_id = target_id  # FK update in memory
    
    session.flush()  # ✅ CRITICAL: Persist FK updates first!
    
    # ... remove self-loops ...
    # ... deduplicate relationships ...
    
    session.delete(source)  # ✅ Now safe! FKs already updated.
```

## Testing

Run verification:
```bash
python test_merge_fix_verification.py
```

Run all tests:
```bash
pytest tests/test_entity_merging.py::TestMergeTransfersAllReferences -v
```

## Order of Operations (Critical!)

1. Merge metadata_json
2. Transfer EntityFieldValue records
3. Transfer Intelligence records
4. Transfer Page references
5. Transfer MediaItem references
6. Transfer FieldDiscoveryLog records
7. Redirect relationships (FK updates)
8. **⚡ FLUSH** ← This is the critical fix!
9. Remove self-referential relationships
10. Deduplicate relationships
11. Record merge history
12. Delete source entity

## Why This Order Matters

- **Transfers before FK redirects**: Ensures all data points to correct entity
- **FK redirects before flush**: All FK updates in one batch
- **Flush before delete**: Ensures FK updates are in DB before CASCADE
- **Cleanup after flush**: Self-loops and duplicates only exist after redirect
- **Delete last**: Only after everything is safely transferred and persisted
