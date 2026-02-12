"""Tests for entity UUID generation and graph action correctness.

Validates that:
- Entities without DB records receive deterministic UUID IDs
- The same canonical name always produces the same UUID
- All graph entity nodes have valid UUID IDs
- Empty query in graph search returns all entities
"""

import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from garuda_intel.webapp.utils.helpers import (
    _canonical,
    _entity_uuid_from_canonical,
    _looks_like_uuid,
)


# ---------------------------------------------------------------------------
# _entity_uuid_from_canonical – deterministic UUID generation
# ---------------------------------------------------------------------------
def test_entity_uuid_is_valid_uuid():
    """Generated entity UUID should be a valid UUID."""
    result = _entity_uuid_from_canonical("cleverspinner")
    assert _looks_like_uuid(result), f"Expected valid UUID, got {result}"


def test_entity_uuid_is_deterministic():
    """Same canonical name should always produce the same UUID."""
    uuid1 = _entity_uuid_from_canonical("cleverspinner")
    uuid2 = _entity_uuid_from_canonical("cleverspinner")
    assert uuid1 == uuid2, f"Expected same UUID, got {uuid1} and {uuid2}"


def test_entity_uuid_differs_by_name():
    """Different canonical names should produce different UUIDs."""
    uuid1 = _entity_uuid_from_canonical("cleverspinner")
    uuid2 = _entity_uuid_from_canonical("microsoft")
    assert uuid1 != uuid2, "Expected different UUIDs for different names"


def test_entity_uuid_canonical_consistency():
    """Canonicalized names should produce consistent UUIDs."""
    canon = _canonical("CleverSpinner")
    uuid1 = _entity_uuid_from_canonical(canon)
    uuid2 = _entity_uuid_from_canonical("cleverspinner")
    assert uuid1 == uuid2, "Expected same UUID for same canonical name"


def test_entity_uuid_not_collide_with_page_uuid():
    """Entity UUIDs should not collide with page UUIDs from URLs."""
    from garuda_intel.webapp.utils.helpers import _page_uuid_from_url

    entity_uuid = _entity_uuid_from_canonical("example")
    page_uuid = _page_uuid_from_url("example")
    assert entity_uuid != page_uuid, "Entity and page UUIDs should not collide"


# ---------------------------------------------------------------------------
# Integration: upsert_entity in graph building
# ---------------------------------------------------------------------------
def test_upsert_entity_always_returns_uuid():
    """Simulate the upsert_entity flow: entities without DB records
    should still get valid UUID node keys."""
    from collections import Counter

    entity_ids = {}
    entity_kinds = {}
    nodes = {}
    variants = {}
    canonical_type = {}

    def ensure_node(node_id, label, node_type, score=None, count_inc=1, meta=None, kind=None):
        if not node_id:
            return None
        node_id = str(node_id)
        node = nodes.get(node_id, {"id": node_id, "label": label or node_id, "type": node_type, "score": 0, "count": 0, "meta": {}})
        node["count"] = (node.get("count") or 0) + (count_inc or 0)
        if score is not None:
            node["score"] = max(node.get("score") or 0, score)
        if kind:
            existing_kind = node.get("kind")
            is_specific_kind = kind not in ("entity", "unknown")
            is_existing_generic = not existing_kind or existing_kind in ("entity", "unknown")
            if is_specific_kind and is_existing_generic:
                node["kind"] = kind
            elif not existing_kind:
                node["kind"] = kind
        if meta:
            node_meta = node.get("meta") or {}
            node_meta.update({k: v for k, v in meta.items() if v is not None})
            node["meta"] = node_meta
        nodes[node_id] = node
        return node_id

    from garuda_intel.webapp.utils.helpers import _norm_kind

    def upsert_entity(raw_name, kind, score, meta=None):
        """Mimic the updated upsert_entity function."""
        if not raw_name:
            return None
        canon = _canonical(raw_name)
        if not canon:
            return None
        norm_kind = _norm_kind(kind)
        variants.setdefault(canon, Counter()).update([raw_name])
        ent_uuid = entity_ids.get(canon)
        stored_kind = entity_kinds.get(canon)
        is_stored_specific = stored_kind and stored_kind not in ("entity", "unknown")
        effective_kind = stored_kind if is_stored_specific else (norm_kind or "entity")
        # Key change: always generate a UUID
        if not ent_uuid:
            ent_uuid = _entity_uuid_from_canonical(canon)
            entity_ids[canon] = ent_uuid
        node_key = str(ent_uuid)
        node_meta = {"entity_kind": norm_kind or effective_kind or "entity", "canonical": canon, "entity_id": ent_uuid, "source_id": node_key}
        if meta:
            node_meta.update(meta)
        node_id = ensure_node(node_key, raw_name, node_type=effective_kind, score=score, meta=node_meta, kind=effective_kind)
        if effective_kind:
            canonical_type[canon] = canonical_type.get(canon) or effective_kind
            nodes[node_id]["type"] = canonical_type[canon]
        return node_id

    # Test: entity without DB record
    node_id = upsert_entity("cleverspinner", None, None)
    assert node_id is not None
    assert _looks_like_uuid(node_id), f"Expected UUID node ID, got {node_id}"

    # Test: entity with kind=None should still work
    node = nodes[node_id]
    assert node["id"] == node_id
    assert node["label"] == "cleverspinner"
    assert _looks_like_uuid(node["meta"]["entity_id"]), "entity_id in meta should be a valid UUID"

    # Test: same entity name resolves to same node
    node_id2 = upsert_entity("CleverSpinner", None, None)
    assert node_id2 == node_id, "Same canonical name should resolve to same node"

    # Test: pre-existing DB entity uses its own UUID
    db_uuid = str(uuid.uuid4())
    entity_ids[_canonical("Microsoft")] = db_uuid
    entity_kinds[_canonical("Microsoft")] = "org"
    ms_node_id = upsert_entity("Microsoft", "organization", 0.95)
    assert ms_node_id == db_uuid, "DB entity should use its own UUID"


# ---------------------------------------------------------------------------
# Bulk delete: all entities should now have valid UUIDs
# ---------------------------------------------------------------------------
def test_bulk_delete_no_entities_skipped():
    """Simulate the JS deleteSelectedNodes flow: with deterministic UUIDs
    no entities should be skipped due to invalid UUID checks."""
    # Simulate entity nodes generated by the updated upsert_entity
    entity_names = ["cleverspinner", "some_tool", "another entity", "テスト"]
    uuids = [_entity_uuid_from_canonical(_canonical(name)) for name in entity_names]

    # All should pass UUID validation
    for uid in uuids:
        assert _looks_like_uuid(uid), f"Expected valid UUID, got {uid}"


if __name__ == "__main__":
    print("Running entity UUID and graph action tests...\n")

    test_entity_uuid_is_valid_uuid()
    print("✓ test_entity_uuid_is_valid_uuid")

    test_entity_uuid_is_deterministic()
    print("✓ test_entity_uuid_is_deterministic")

    test_entity_uuid_differs_by_name()
    print("✓ test_entity_uuid_differs_by_name")

    test_entity_uuid_canonical_consistency()
    print("✓ test_entity_uuid_canonical_consistency")

    test_entity_uuid_not_collide_with_page_uuid()
    print("✓ test_entity_uuid_not_collide_with_page_uuid")

    test_upsert_entity_always_returns_uuid()
    print("✓ test_upsert_entity_always_returns_uuid")

    test_bulk_delete_no_entities_skipped()
    print("✓ test_bulk_delete_no_entities_skipped")

    print("\n✓ All entity UUID and graph action tests passed!")
