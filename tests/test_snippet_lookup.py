"""
Tests for snippet lookup, window expansion, and source detection.

Validates:
- SQLAlchemyStore.search_snippets() keyword search
- SQLAlchemyStore.get_neighbouring_snippets() directional expansion
- expand_snippet_window() progressive expansion logic
- expand_snippet_hits() batch expansion for snippet and non-snippet hits
- Source provenance fields on search results
"""

import uuid
import pytest
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from garuda_intel.database.models import Base, SemanticSnippet
from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.search.snippet_expander import (
    expand_snippet_window,
    expand_snippet_hits,
    _MIN_SUFFICIENT_LENGTH,
)


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

@pytest.fixture
def db_engine():
    """Create an in-memory SQLite database with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def store(db_engine):
    """SQLAlchemyStore backed by the in-memory engine."""
    s = SQLAlchemyStore.__new__(SQLAlchemyStore)
    s.Session = sessionmaker(bind=db_engine)
    s.logger = MagicMock()
    return s


@pytest.fixture
def page_id():
    return str(uuid.uuid4())


@pytest.fixture
def seed_snippets(store, page_id):
    """Insert a series of snippets for a single page."""
    texts = [
        "The quick brown fox jumps over the lazy dog.",  # 0
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",  # 1
        "Garuda is an intelligence platform for deep research.",  # 2
        "Semantic snippets improve RAG retrieval quality.",  # 3
        "Window expansion ensures sufficient context.",  # 4
    ]
    with store.Session() as s:
        for idx, text in enumerate(texts):
            snip = SemanticSnippet(
                id=uuid.uuid4(),
                text=text,
                chunk_index=idx,
                prev_context=texts[idx - 1][:80] if idx > 0 else None,
                next_context=texts[idx + 1][:80] if idx < len(texts) - 1 else None,
                source_url="https://example.com/article",
                page_id=uuid.UUID(page_id),
                entity_refs_json=["fox"] if idx == 0 else None,
            )
            s.add(snip)
        s.commit()
    return texts


# -----------------------------------------------------------------------
# search_snippets
# -----------------------------------------------------------------------


class TestSearchSnippets:
    def test_keyword_match(self, store, seed_snippets):
        results = store.search_snippets("Garuda")
        assert len(results) == 1
        assert "Garuda" in results[0]["text"]

    def test_case_insensitive(self, store, seed_snippets):
        results = store.search_snippets("garuda")
        assert len(results) >= 1

    def test_no_match(self, store, seed_snippets):
        results = store.search_snippets("xyznonexistent")
        assert results == []

    def test_limit(self, store, seed_snippets):
        results = store.search_snippets(".", limit=2)
        assert len(results) <= 2

    def test_result_has_expected_fields(self, store, seed_snippets):
        results = store.search_snippets("Garuda")
        r = results[0]
        assert "text" in r
        assert "chunk_index" in r
        assert "source_url" in r
        assert "page_id" in r


# -----------------------------------------------------------------------
# get_neighbouring_snippets
# -----------------------------------------------------------------------


class TestGetNeighbouringSnippets:
    def test_both_directions(self, store, seed_snippets, page_id):
        neighbours = store.get_neighbouring_snippets(page_id, chunk_index=2, direction="both", window=1)
        indices = sorted(n["chunk_index"] for n in neighbours)
        assert indices == [1, 3]

    def test_prev_direction(self, store, seed_snippets, page_id):
        neighbours = store.get_neighbouring_snippets(page_id, chunk_index=3, direction="prev", window=2)
        indices = sorted(n["chunk_index"] for n in neighbours)
        assert indices == [1, 2]

    def test_next_direction(self, store, seed_snippets, page_id):
        neighbours = store.get_neighbouring_snippets(page_id, chunk_index=1, direction="next", window=2)
        indices = sorted(n["chunk_index"] for n in neighbours)
        assert indices == [2, 3]

    def test_boundary_no_overflow(self, store, seed_snippets, page_id):
        """Requesting neighbours beyond the edge returns only what exists."""
        neighbours = store.get_neighbouring_snippets(page_id, chunk_index=0, direction="prev", window=5)
        assert neighbours == []

    def test_window_size(self, store, seed_snippets, page_id):
        neighbours = store.get_neighbouring_snippets(page_id, chunk_index=2, direction="both", window=10)
        # Should return all except index 2 itself (indices 0,1,3,4)
        assert len(neighbours) == 4


# -----------------------------------------------------------------------
# expand_snippet_window
# -----------------------------------------------------------------------


class TestExpandSnippetWindow:
    def test_no_expansion_without_page_id(self):
        hit = {"snippet": "short", "data": {}}
        result = expand_snippet_window(hit, MagicMock())
        assert result is hit  # unchanged

    def test_no_expansion_without_chunk_index(self):
        hit = {"snippet": "short", "data": {"page_id": "p1"}}
        result = expand_snippet_window(hit, MagicMock())
        assert result is hit

    def test_expansion_with_neighbours(self, store, seed_snippets, page_id):
        hit = {
            "snippet": seed_snippets[2],
            "text": seed_snippets[2],
            "data": {"page_id": page_id, "chunk_index": 2},
            "kind": "semantic-snippet",
        }
        result = expand_snippet_window(hit, store, min_length=50)
        assert result.get("expanded") is True
        # Should include neighbours
        assert len(result["snippet"]) > len(seed_snippets[2])

    def test_expansion_stops_at_boundary(self, store, seed_snippets, page_id):
        """Start at chunk 0 — only forward expansion possible."""
        hit = {
            "snippet": seed_snippets[0],
            "text": seed_snippets[0],
            "data": {"page_id": page_id, "chunk_index": 0},
            "kind": "semantic-snippet",
        }
        result = expand_snippet_window(hit, store, min_length=50)
        assert result.get("expanded") is True

    def test_custom_sufficiency_fn(self, store, seed_snippets, page_id):
        """Custom sufficiency function can stop expansion early."""
        hit = {
            "snippet": seed_snippets[2],
            "text": seed_snippets[2],
            "data": {"page_id": page_id, "chunk_index": 2},
            "kind": "semantic-snippet",
        }
        # Always sufficient
        result = expand_snippet_window(
            hit, store, sufficiency_fn=lambda t: True, min_length=99999
        )
        assert result.get("expanded") is True

    def test_no_mutation_of_original(self, store, seed_snippets, page_id):
        hit = {
            "snippet": seed_snippets[2],
            "text": seed_snippets[2],
            "data": {"page_id": page_id, "chunk_index": 2},
        }
        original_snippet = hit["snippet"]
        expand_snippet_window(hit, store, min_length=50)
        assert hit["snippet"] == original_snippet  # original not mutated


# -----------------------------------------------------------------------
# expand_snippet_hits (batch)
# -----------------------------------------------------------------------


class TestExpandSnippetHits:
    def test_non_snippet_hits_unchanged(self):
        hits = [
            {"snippet": "normal", "kind": "page", "data": {}},
        ]
        result = expand_snippet_hits(hits, MagicMock())
        assert result[0]["snippet"] == "normal"

    def test_snippet_hits_expanded(self, store, seed_snippets, page_id):
        hits = [
            {
                "snippet": seed_snippets[2],
                "text": seed_snippets[2],
                "kind": "semantic-snippet",
                "data": {"page_id": page_id, "chunk_index": 2},
            },
            {
                "snippet": "normal page hit",
                "kind": "page",
                "data": {},
            },
        ]
        result = expand_snippet_hits(hits, store, min_length=50)
        # First hit should be expanded
        assert result[0].get("expanded") is True
        # Second hit should be unchanged
        assert result[1]["snippet"] == "normal page hit"
        assert "expanded" not in result[1]


# -----------------------------------------------------------------------
# PersistenceStore defaults
# -----------------------------------------------------------------------


class TestPersistenceStoreDefaults:
    def test_search_snippets_default(self):
        from garuda_intel.database.store import PersistenceStore
        # Create a minimal concrete subclass
        class MinimalStore(PersistenceStore):
            def save_seed(self, *a, **kw): ...
            def save_page(self, *a, **kw): ...
            def save_links(self, *a, **kw): ...
            def save_fingerprint(self, *a, **kw): ...
            def save_patterns(self, *a, **kw): ...
            def save_domains(self, *a, **kw): ...
            def save_entities(self, *a, **kw): ...
            def get_all_pages(self, *a, **kw): ...
            def get_page_by_url(self, *a, **kw): ...
            def get_page_content_by_url(self, *a, **kw): ...
            def get_intelligence(self, *a, **kw): ...
            def search_intelligence_data(self, *a, **kw): ...
            def search_intel(self, *a, **kw): ...
            def get_aggregated_entity_data(self, *a, **kw): ...
            def get_entities(self, *a, **kw): ...
            def get_pending_refresh(self, *a, **kw): ...
            def mark_visited(self, *a, **kw): ...
            def has_visited(self, *a, **kw): ...

        s = MinimalStore()
        assert s.search_snippets("x") == []
        assert s.get_neighbouring_snippets("pid", 0) == []
