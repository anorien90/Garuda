# Entity Merge Soft-Delete Implementation - Change Summary

## Overview
Changed entity merge behavior from hard-delete to soft-merge in three files.

## File 1: src/garuda_intel/extractor/entity_merger.py

**Method**: `SemanticEntityDeduplicator._merge_entities`  
**Lines**: 1425-1459 (previously 1425-1428)

### REMOVED:
```python
        # Delete source
        session.delete(source)
```

### ADDED:
```python
        # Soft-merge: keep the source entity as a subordinate, not deleted
        # Mark source as merged into target
        merge_timestamp = datetime.now(timezone.utc).isoformat()
        if not source.metadata_json:
            source.metadata_json = {}
        source.metadata_json["merged_into"] = str(target_id)
        source.metadata_json["merged_at"] = merge_timestamp
        flag_modified(source, 'metadata_json')
        
        # Create "duplicate_of" relationship from source → target
        # Check it doesn't already exist
        existing_dup_rel = session.execute(
            select(Relationship).where(
                Relationship.source_id == source_id,
                Relationship.target_id == target_id,
                Relationship.relation_type == "duplicate_of",
            )
        ).scalar_one_or_none()
        if not existing_dup_rel:
            dup_rel = Relationship(
                id=uuid.uuid4(),
                source_id=source_id,
                target_id=target_id,
                relation_type="duplicate_of",
                source_type="entity",
                target_type="entity",
                metadata_json={
                    "merged_at": merge_timestamp,
                    "original_name": source.name,
                    "original_kind": source.kind,
                },
            )
            session.add(dup_rel)
```

---

## File 2: src/garuda_intel/services/agent_service.py

**Import Change** (Line 16):
```python
# BEFORE:
from datetime import datetime

# AFTER:
from datetime import datetime, timezone
```

**Method**: `AgentService._merge_entity_group`  
**Lines**: 489-518 (previously 489-490)

### REMOVED:
```python
            # Hard delete the secondary entity
            session.delete(secondary_entity)
```

### ADDED:
```python
            # Soft-merge: keep the secondary entity as a subordinate
            merge_timestamp = datetime.now(timezone.utc).isoformat()
            if not secondary_entity.metadata_json:
                secondary_entity.metadata_json = {}
            secondary_entity.metadata_json["merged_into"] = str(primary_id)
            secondary_entity.metadata_json["merged_at"] = merge_timestamp
            
            # Create "duplicate_of" relationship from secondary → primary
            existing_dup_rel = session.execute(
                select(Relationship).where(
                    Relationship.source_id == secondary_id,
                    Relationship.target_id == primary_id,
                    Relationship.relation_type == "duplicate_of",
                )
            ).scalar_one_or_none()
            if not existing_dup_rel:
                dup_rel = Relationship(
                    id=uuid.uuid4(),
                    source_id=secondary_id,
                    target_id=primary_id,
                    relation_type="duplicate_of",
                    source_type="entity",
                    target_type="entity",
                    metadata_json={
                        "merged_at": merge_timestamp,
                        "original_name": secondary_entity.name,
                        "original_kind": secondary_entity.kind,
                    },
                )
                session.add(dup_rel)
```

---

## File 3: src/garuda_intel/database/engine.py

**Method**: `SQLAlchemyStore.merge_entities`  
**Lines**: 865-895 (previously 865-867)

### REMOVED:
```python
                # Delete source entity
                s.delete(source)
```

### ADDED:
```python
                # Soft-merge: keep the source entity as a subordinate
                merge_timestamp = datetime.now(timezone.utc).isoformat()
                if not source.metadata_json:
                    source.metadata_json = {}
                source.metadata_json["merged_into"] = str(target_id)
                source.metadata_json["merged_at"] = merge_timestamp
                
                # Create "duplicate_of" relationship from source → target
                existing_dup_rel = s.execute(
                    select(Relationship).where(
                        Relationship.source_id == source_id,
                        Relationship.target_id == target_id,
                        Relationship.relation_type == "duplicate_of",
                    )
                ).scalar_one_or_none()
                if not existing_dup_rel:
                    dup_rel = Relationship(
                        id=uuid.uuid4(),
                        source_id=source_id,
                        target_id=target_id,
                        relation_type="duplicate_of",
                        source_type="entity",
                        target_type="entity",
                        metadata_json={
                            "merged_at": merge_timestamp,
                            "original_name": source.name,
                            "original_kind": source.kind,
                        },
                    )
                    s.add(dup_rel)
```

---

## Key Implementation Points

1. **Single Timestamp**: Each merge operation uses one timestamp for both entity metadata and relationship
2. **String IDs**: `merged_into` field stores entity ID as string for consistency
3. **UTC Timezone**: All timestamps use `datetime.now(timezone.utc).isoformat()`
4. **Idempotent**: Checks for existing "duplicate_of" relationship before creating
5. **Provenance**: Original entity name and kind preserved in relationship metadata

## Testing Performed

- ✅ Python syntax validation
- ✅ Code review (0 issues)
- ✅ CodeQL security scan (0 alerts)

## Status: COMPLETE ✅

All changes implemented, reviewed, and validated.
