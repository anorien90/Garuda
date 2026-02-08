# Entity Merge Fix - Summary

## Overview
Fixed critical bug in `_merge_entities` method where entity relationships and associated records were lost during entity deduplication.

## Problem Statement

After entity deduplication and merging in the `SemanticEntityDeduplicator` class, surviving entities became "orphans" with no relationships or associated records. This happened due to several root causes:

### Root Causes

1. **Database CASCADE Deletes Relationships**
   - `_merge_entities` redirected relationship FKs (`source_id`/`target_id`) from source to target entity
   - It then deleted the source entity WITHOUT flushing the FK updates first
   - Since `Relationship.source_id` and `Relationship.target_id` have `ForeignKey("entries.id", ondelete="CASCADE")`, the database CASCADE deleted all relationships before the Python-side FK updates were persisted
   - Result: ALL relationships lost

2. **Self-Referential Relationships After Redirect**
   - If source entity had a relationship TO target entity (or vice versa)
   - After redirecting FKs, we'd get `source_id == target_id` (self-loop)
   - These invalid self-loops were not removed

3. **Duplicate Relationships After Redirect**
   - Both source and target might have a relationship to entity C
   - After redirect, both become `target -> C` (duplicates)
   - These duplicates were not deduplicated

4. **EntityFieldValue Records Not Transferred**
   - `Entity.dynamic_field_values` has `cascade="all, delete-orphan"`
   - When source entity was deleted, its field values were cascade-deleted
   - Result: Lost all dynamically discovered field values

5. **Intelligence Records Not Transferred**
   - `Intelligence.entity_id` FK has `ondelete="SET NULL"`
   - Intelligence records lost their entity association
   - Result: Orphaned intelligence data

6. **Page References Not Transferred**
   - `Page.entity_id` FK has `ondelete="SET NULL"`
   - Page records lost their entity association
   - Result: Orphaned page data

7. **MediaItem References Not Transferred**
   - `MediaItem.entity_id` FK has `ondelete="SET NULL"`
   - Media items lost their entity association
   - Result: Orphaned media data

8. **FieldDiscoveryLog References Not Transferred**
   - `FieldDiscoveryLog.entity_id` FK has `ondelete="SET NULL"`
   - Discovery logs lost their entity association
   - Result: Lost field discovery tracking

9. **Source metadata_json Not Merged**
   - Only merge history was recorded
   - Source's metadata fields were not merged into target
   - Result: Lost metadata

## Solution

### Code Changes

#### File: `src/garuda_intel/extractor/entity_merger.py`

**Added imports:**
```python
from ..database.models import (
    Entity,
    Relationship,
    DynamicFieldDefinition,
    EntityFieldValue,
    FieldDiscoveryLog,
    Intelligence,      # NEW
    Page,              # NEW
    MediaItem,         # NEW
)
```

**Fixed `_merge_entities` method (lines ~1280-1430):**

1. **Merge metadata_json** (before any transfers)
   ```python
   source_metadata = source.metadata_json or {}
   target_metadata = target.metadata_json or {}
   for key, value in source_metadata.items():
       if key != "merged_from" and value and (key not in target_metadata or not target_metadata.get(key)):
           target_metadata[key] = value
   target.metadata_json = target_metadata
   flag_modified(target, 'metadata_json')
   ```

2. **Transfer EntityFieldValue records**
   ```python
   for field_value in session.execute(
       select(EntityFieldValue).where(EntityFieldValue.entity_id == source_id)
   ).scalars().all():
       field_value.entity_id = target_id
   ```

3. **Transfer Intelligence records**
   ```python
   for intel in session.execute(
       select(Intelligence).where(Intelligence.entity_id == source_id)
   ).scalars().all():
       intel.entity_id = target_id
   ```

4. **Transfer Page references**
   ```python
   for page in session.execute(
       select(Page).where(Page.entity_id == source_id)
   ).scalars().all():
       page.entity_id = target_id
   ```

5. **Transfer MediaItem references**
   ```python
   for media_item in session.execute(
       select(MediaItem).where(MediaItem.entity_id == source_id)
   ).scalars().all():
       media_item.entity_id = target_id
   ```

6. **Transfer FieldDiscoveryLog references**
   ```python
   for log in session.execute(
       select(FieldDiscoveryLog).where(FieldDiscoveryLog.entity_id == source_id)
   ).scalars().all():
       log.entity_id = target_id
   ```

7. **Redirect relationships** (existing logic, unchanged)

8. **CRITICAL FIX: Flush before delete**
   ```python
   # CRITICAL: Flush to persist relationship redirects BEFORE deleting source entity
   # This prevents CASCADE delete from wiping relationships
   session.flush()
   ```

9. **Remove self-referential relationships**
   ```python
   self_refs = session.execute(
       select(Relationship).where(
           Relationship.source_id == target_id,
           Relationship.target_id == target_id
       )
   ).scalars().all()
   for rel in self_refs:
       session.delete(rel)
   ```

10. **Deduplicate relationships**
    ```python
    all_rels = session.execute(
        select(Relationship).where(
            (Relationship.source_id == target_id) | (Relationship.target_id == target_id)
        )
    ).scalars().all()
    
    # Group by (source_id, target_id, relation_type)
    rel_groups: Dict[Tuple[str, str, str], List[Relationship]] = {}
    for rel in all_rels:
        key = (str(rel.source_id), str(rel.target_id), rel.relation_type or "")
        if key not in rel_groups:
            rel_groups[key] = []
        rel_groups[key].append(rel)
    
    # For each group with duplicates, keep only the first one
    for key, rels in rel_groups.items():
        if len(rels) > 1:
            rels_sorted = sorted(rels, key=lambda r: str(r.id))
            for rel in rels_sorted[1:]:
                session.delete(rel)
    ```

#### File: `tests/test_entity_merging.py`

**Added test class `TestMergeTransfersAllReferences`** with 8 comprehensive tests:

1. `test_merge_transfers_relationships_with_flush` - Verifies relationships survive merge
2. `test_merge_removes_self_referential_relationships` - Verifies self-loops are removed
3. `test_merge_deduplicates_relationships` - Verifies duplicates are removed
4. `test_merge_transfers_entity_field_values` - Verifies field values are transferred
5. `test_merge_transfers_intelligence_records` - Verifies intelligence is transferred
6. `test_merge_transfers_page_references` - Verifies pages are transferred
7. `test_merge_transfers_media_items` - Verifies media items are transferred
8. `test_merge_merges_metadata` - Verifies metadata is merged correctly

#### File: `test_merge_fix_verification.py`

Created standalone verification script that:
- Creates a realistic merge scenario
- Verifies relationships survive
- Verifies data is merged
- Provides visual confirmation of the fix

## Test Results

### All Tests Pass
```bash
tests/test_entity_merging.py::TestMergeTransfersAllReferences ........ [100%]
8 passed

tests/test_entity_merging.py (all tests) ................................ [100%]
46 passed
```

### No Regressions
- All 46 existing entity merging tests pass
- No regressions in related test suites
- No security issues (CodeQL clean)

## Verification

Run the standalone verification script:
```bash
cd /home/runner/work/Garuda/Garuda
python test_merge_fix_verification.py
```

Expected output:
```
✓ Created entities
✓ Created 2 relationships between Microsoft and Bill Gates
✓ Merge completed successfully
✓ Relationships remaining: 2 (expected: 2)
✓ Relationships correctly redirected to survivor entity
✓ ALL TESTS PASSED!
```

## Impact

### Before Fix
- Entity merging created orphan entities with no relationships
- Lost all EntityFieldValue records
- Lost Intelligence associations
- Lost Page associations  
- Lost MediaItem associations
- Lost FieldDiscoveryLog records
- Lost source metadata

### After Fix
- ✅ All relationships preserved and redirected to survivor
- ✅ Self-referential relationships removed
- ✅ Duplicate relationships deduplicated
- ✅ All EntityFieldValue records transferred
- ✅ All Intelligence records transferred
- ✅ All Page references transferred
- ✅ All MediaItem references transferred
- ✅ All FieldDiscoveryLog records transferred
- ✅ Metadata properly merged

## Files Modified

1. `src/garuda_intel/extractor/entity_merger.py` - Core fix
2. `tests/test_entity_merging.py` - Comprehensive tests
3. `test_merge_fix_verification.py` - Verification script (NEW)

## Security Review

- CodeQL scan: ✅ No alerts
- No SQL injection risks
- No data exposure risks
- Proper transaction handling with flush/commit

## Next Steps

This fix can be deployed immediately. It:
- Fixes a critical data loss bug
- Has comprehensive test coverage
- Maintains backward compatibility
- Introduces no security issues
- Has no performance impact (all operations are within same transaction)
