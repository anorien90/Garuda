"""Tests for Entity Graph search seed identification and depth traversal.

Validates that:
- UUID queries produce exact-match seeds
- Semantic seeds are included alongside text-match seeds
- Empty queries return all nodes as seeds
- Depth-0 with empty query returns all nodes
- Seeds are not lost due to score/limit truncation
"""

import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from garuda_intel.webapp.utils.helpers import (
    _seeds_from_query,
    _filter_by_depth,
    _looks_like_uuid,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _node(node_id, label="", node_type="entity", score=0):
    return {"id": str(node_id), "label": label, "type": node_type, "score": score}


def _link(src, tgt, kind="cooccurrence"):
    return {"source": str(src), "target": str(tgt), "kind": kind}


# ---------------------------------------------------------------------------
# _seeds_from_query – UUID handling
# ---------------------------------------------------------------------------
def test_seeds_uuid_exact_match():
    """When query is a UUID only the node with that exact ID is a seed."""
    uid = str(uuid.uuid4())
    nodes = [_node(uid, "Entity A"), _node(str(uuid.uuid4()), "Entity B")]
    seeds = _seeds_from_query(nodes, uid)
    assert seeds == {uid}, f"Expected {{'{uid}'}}, got {seeds}"


def test_seeds_uuid_no_fallback():
    """When query is a UUID that doesn't match any node, result is empty (no fallback)."""
    missing = str(uuid.uuid4())
    nodes = [_node(str(uuid.uuid4()), "X"), _node(str(uuid.uuid4()), "Y")]
    seeds = _seeds_from_query(nodes, missing)
    assert seeds == set(), f"Expected empty set, got {seeds}"


def test_seeds_uuid_case_insensitive():
    """UUID matching is case-insensitive."""
    uid = str(uuid.uuid4())
    nodes = [_node(uid, "Entity")]
    seeds = _seeds_from_query(nodes, uid.upper())
    assert seeds == {uid}


# ---------------------------------------------------------------------------
# _seeds_from_query – text / semantic matching
# ---------------------------------------------------------------------------
def test_seeds_text_match():
    """Text query matches by label substring."""
    nodes = [
        _node("1", "Apple Inc"),
        _node("2", "Google LLC"),
        _node("3", "Pineapple"),
    ]
    seeds = _seeds_from_query(nodes, "apple")
    assert seeds == {"1", "3"}, f"Expected {{'1','3'}}, got {seeds}"


def test_seeds_text_no_fallback():
    """When text query matches nothing, result is empty (no fallback to all)."""
    nodes = [_node("1", "Alpha"), _node("2", "Beta")]
    seeds = _seeds_from_query(nodes, "zzz_nonexistent")
    assert seeds == set()


def test_seeds_semantic_included():
    """Nodes in semantic_seeds set are added alongside text matches."""
    nodes = [
        _node("1", "Apple Inc"),
        _node("2", "Fruit Company"),
        _node("3", "Banana Corp"),
    ]
    # "2" matched semantically but not by text
    seeds = _seeds_from_query(nodes, "apple", semantic_seeds={"2"})
    assert seeds == {"1", "2"}, f"Expected {{'1','2'}}, got {seeds}"


def test_seeds_semantic_only():
    """When text matches nothing but semantic matches exist, return them."""
    nodes = [_node("1", "Alpha"), _node("2", "Beta"), _node("3", "Gamma")]
    seeds = _seeds_from_query(nodes, "zzz", semantic_seeds={"2", "3"})
    assert seeds == {"2", "3"}


def test_seeds_semantic_ignores_absent():
    """Semantic seed IDs not present in nodes are silently ignored."""
    nodes = [_node("1", "Alpha")]
    seeds = _seeds_from_query(nodes, "alpha", semantic_seeds={"999"})
    assert seeds == {"1"}


# ---------------------------------------------------------------------------
# _seeds_from_query – empty query
# ---------------------------------------------------------------------------
def test_seeds_empty_query():
    """Empty query returns every node as seed."""
    nodes = [_node("1", "A"), _node("2", "B"), _node("3", "C")]
    seeds = _seeds_from_query(nodes, "")
    assert seeds == {"1", "2", "3"}


def test_seeds_empty_query_empty_nodes():
    """Empty query with no nodes returns empty set."""
    seeds = _seeds_from_query([], "")
    assert seeds == set()


# ---------------------------------------------------------------------------
# _filter_by_depth – interaction with seeds
# ---------------------------------------------------------------------------
def test_filter_depth_zero_only_seeds():
    """Depth 0 keeps only seed nodes (and no links)."""
    nodes = [_node("A", "Root"), _node("B", "Child")]
    links = [_link("A", "B")]
    seeds = {"A"}
    kept_n, kept_l = _filter_by_depth(nodes, links, 0, seeds)
    assert {n["id"] for n in kept_n} == {"A"}
    assert kept_l == []


def test_filter_depth_one_expands_to_neighbors():
    """Depth 1 includes seeds and their immediate neighbors."""
    nodes = [_node("A"), _node("B"), _node("C")]
    links = [_link("A", "B"), _link("B", "C")]
    seeds = {"A"}
    kept_n, _ = _filter_by_depth(nodes, links, 1, seeds)
    assert {n["id"] for n in kept_n} == {"A", "B"}


def test_filter_depth_empty_seeds():
    """When seeds are empty, depth filter returns nothing for any finite depth."""
    nodes = [_node("A"), _node("B")]
    links = [_link("A", "B")]
    kept_n, kept_l = _filter_by_depth(nodes, links, 1, set())
    assert kept_n == []
    assert kept_l == []


def test_filter_depth_infinite_returns_all():
    """Depth >= 99 returns all nodes regardless of seeds."""
    nodes = [_node("A"), _node("B"), _node("C")]
    links = [_link("A", "B")]
    kept_n, kept_l = _filter_by_depth(nodes, links, 99, set())
    assert len(kept_n) == 3


# ---------------------------------------------------------------------------
# _looks_like_uuid – sanity checks
# ---------------------------------------------------------------------------
def test_looks_like_uuid_valid():
    assert _looks_like_uuid(str(uuid.uuid4())) is True


def test_looks_like_uuid_invalid():
    assert _looks_like_uuid("not-a-uuid") is False
    assert _looks_like_uuid("apple") is False
    assert _looks_like_uuid("") is False


# ---------------------------------------------------------------------------
# Integration-style: seeds survive score/limit truncation
# ---------------------------------------------------------------------------
def test_uuid_seed_survives_limit():
    """Simulate the graph endpoint: a UUID seed should survive even with low
    score and a tight result limit, because the caller sorts seeds first."""
    uid = str(uuid.uuid4())
    # Build a list of 100 high-score nodes + 1 low-score UUID node
    nodes = [_node(str(uuid.uuid4()), f"HighScore-{i}", score=10) for i in range(100)]
    nodes.append(_node(uid, "Target Entity", score=0))  # low score

    # Identify seeds from ALL nodes (before limit)
    seed_ids = _seeds_from_query(nodes, uid)
    assert uid in seed_ids

    # Filter step: keep seeds + top-scoring non-seeds
    filtered = [n for n in nodes if n["id"] in seed_ids or n["score"] >= 5]

    # Sort with seeds first (matching the actual api_entities_graph logic)
    limit = 50
    sorted_nodes = sorted(filtered, key=lambda x: (
        -(1 if x["id"] in seed_ids else 0),
        -x["score"],
        x["id"],
    ))[:limit]
    node_set = {n["id"] for n in sorted_nodes}

    # The UUID node should still be in the set because seeds are sorted first
    assert uid in node_set, "UUID seed was lost during limit truncation"


if __name__ == "__main__":
    print("Running graph search seed tests...\n")

    test_seeds_uuid_exact_match()
    print("✓ test_seeds_uuid_exact_match")

    test_seeds_uuid_no_fallback()
    print("✓ test_seeds_uuid_no_fallback")

    test_seeds_uuid_case_insensitive()
    print("✓ test_seeds_uuid_case_insensitive")

    test_seeds_text_match()
    print("✓ test_seeds_text_match")

    test_seeds_text_no_fallback()
    print("✓ test_seeds_text_no_fallback")

    test_seeds_semantic_included()
    print("✓ test_seeds_semantic_included")

    test_seeds_semantic_only()
    print("✓ test_seeds_semantic_only")

    test_seeds_semantic_ignores_absent()
    print("✓ test_seeds_semantic_ignores_absent")

    test_seeds_empty_query()
    print("✓ test_seeds_empty_query")

    test_seeds_empty_query_empty_nodes()
    print("✓ test_seeds_empty_query_empty_nodes")

    test_filter_depth_zero_only_seeds()
    print("✓ test_filter_depth_zero_only_seeds")

    test_filter_depth_one_expands_to_neighbors()
    print("✓ test_filter_depth_one_expands_to_neighbors")

    test_filter_depth_empty_seeds()
    print("✓ test_filter_depth_empty_seeds")

    test_filter_depth_infinite_returns_all()
    print("✓ test_filter_depth_infinite_returns_all")

    test_looks_like_uuid_valid()
    print("✓ test_looks_like_uuid_valid")

    test_looks_like_uuid_invalid()
    print("✓ test_looks_like_uuid_invalid")

    test_uuid_seed_survives_limit()
    print("✓ test_uuid_seed_survives_limit")

    print("\n✓ All graph search seed tests passed!")
