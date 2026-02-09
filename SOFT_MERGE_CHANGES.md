# Soft-Merge Implementation Summary

## Overview
Successfully modified entity merge/deduplication behavior from hard-delete to soft-merge across three core files. Duplicate entities are now preserved as subordinate entities linked to their master entity via a "duplicate_of" relationship, maintaining full provenance.

## Files Modified

### 1. `/src/garuda_intel/extractor/entity_merger.py`
**Method**: `SemanticEntityDeduplicator._merge_entities` (lines 1425-1459)

**Changes**:
- Removed `session.delete(source)` call
- Added metadata marking on source entity:
  - `merged_into`: Target entity ID
  - `merged_at`: Timestamp of merge
- Created "duplicate_of" relationship from source → target
- Preserved provenance: original_name, original_kind in relationship metadata

### 2. `/src/garuda_intel/services/agent_service.py`
**Method**: `AgentService._merge_entity_group` (lines 489-518)

**Changes**:
- Removed `session.delete(secondary_entity)` call
- Added metadata marking on secondary entity:
  - `merged_into`: Primary entity ID
  - `merged_at`: Timestamp of merge
- Created "duplicate_of" relationship from secondary → primary
- Preserved provenance: original_name, original_kind in relationship metadata

### 3. `/src/garuda_intel/database/engine.py`
**Method**: `IntelStore.merge_entities` (lines 865-895)

**Changes**:
- Removed `s.delete(source)` call
- Added metadata marking on source entity:
  - `merged_into`: Target entity ID
  - `merged_at`: Timestamp of merge
- Created "duplicate_of" relationship from source → target
- Preserved provenance: original_name, original_kind in relationship metadata

## Behavioral Changes

### Before (Hard-Delete)
```python
# Source entity deleted from database
session.delete(source)
```

### After (Soft-Merge)
```python
# Source entity kept as subordinate with metadata
source.metadata_json["merged_into"] = target_id
source.metadata_json["merged_at"] = timestamp

# Relationship created to track duplicates
duplicate_relationship = Relationship(
    source_id=source_id,
    target_id=target_id,
    relation_type="duplicate_of",
    metadata_json={
        "merged_at": timestamp,
        "original_name": source.name,
        "original_kind": source.kind,
    }
)
```

## Key Features

1. **Provenance Preservation**: Original entity data retained
2. **Relationship Tracking**: "duplicate_of" relationship links subordinate to master
3. **Metadata Enrichment**: Both entities marked with merge information
4. **Idempotency**: Checks for existing duplicate relationships before creating
5. **Audit Trail**: Timestamps and original names/kinds preserved

## Verification

- ✅ All three files modified successfully
- ✅ Python syntax validation passed
- ✅ No import dependencies added (all required imports already present)
- ✅ Code style consistent with existing patterns
- ✅ Minimal, surgical changes as requested

## Impact

- Entities are no longer lost during deduplication
- Full audit trail maintained for merged entities
- Subordinate entities can be queried via "duplicate_of" relationship
- Master entity retains "merged_from" history in metadata
- Data recovery possible by following relationship graph

