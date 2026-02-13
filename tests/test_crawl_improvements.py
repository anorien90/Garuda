"""
Tests for crawling pipeline improvements:
- Semantic snippet generation (1-3 sentence chunks with prev/next context)
- Per-field entity embeddings (not single JSON blob)
- Reduced automatic seeds
- Multi-step reflect and verify for large findings
- SemanticSnippet database model
"""

import json
import uuid
import pytest
from unittest.mock import MagicMock, patch

from garuda_intel.extractor.semantic_chunker import SemanticChunker, TextChunk
from garuda_intel.extractor.qa_validator import QAValidator, _MAX_FINDING_CHARS


# ===========================================================================
# Semantic Snippet Tests
# ===========================================================================


class TestChunkIntoSnippets:
    """Test SemanticChunker.chunk_into_snippets for 1-3 sentence micro-chunks."""

    @pytest.fixture
    def chunker(self):
        return SemanticChunker()

    def test_empty_text_returns_empty(self, chunker):
        assert chunker.chunk_into_snippets("") == []
        assert chunker.chunk_into_snippets(None) == []

    def test_single_sentence(self, chunker):
        snippets = chunker.chunk_into_snippets("Hello world.")
        assert len(snippets) == 1
        assert snippets[0].text == "Hello world."
        assert snippets[0].chunk_index == 0
        assert snippets[0].prev_context is None
        assert snippets[0].next_context is None

    def test_three_sentences_yield_one_snippet(self, chunker):
        text = "First. Second. Third."
        snippets = chunker.chunk_into_snippets(text, max_sentences=3)
        assert len(snippets) == 1
        assert "First" in snippets[0].text
        assert "Third" in snippets[0].text

    def test_six_sentences_yield_two_snippets(self, chunker):
        text = "One. Two. Three. Four. Five. Six."
        snippets = chunker.chunk_into_snippets(text, max_sentences=3)
        assert len(snippets) == 2
        # First snippet: One, Two, Three
        assert "One" in snippets[0].text
        assert "Three" in snippets[0].text
        # Second snippet: Four, Five, Six
        assert "Four" in snippets[1].text
        assert "Six" in snippets[1].text

    def test_prev_next_context_populated(self, chunker):
        text = "A. B. C. D. E. F."
        snippets = chunker.chunk_into_snippets(text, max_sentences=3)
        assert len(snippets) == 2
        # First snippet should have no prev but a next
        assert snippets[0].prev_context is None
        assert snippets[0].next_context is not None
        # Second snippet should have a prev but no next
        assert snippets[1].prev_context is not None
        assert snippets[1].next_context is None

    def test_prev_context_matches_previous_snippet(self, chunker):
        text = "Alpha sentence. Beta sentence. Gamma sentence. Delta sentence. Epsilon sentence. Zeta sentence."
        snippets = chunker.chunk_into_snippets(text, max_sentences=3)
        if len(snippets) >= 2:
            # prev_context of snippet[1] should start with beginning of snippet[0]
            assert snippets[1].prev_context.startswith(snippets[0].text[:20])

    def test_source_url_attached(self, chunker):
        text = "Fact one. Fact two. Fact three."
        snippets = chunker.chunk_into_snippets(text, source_url="https://example.com")
        for s in snippets:
            assert s.source_url == "https://example.com"

    def test_chunk_index_sequential(self, chunker):
        text = ". ".join(f"Sentence {i}" for i in range(15)) + "."
        snippets = chunker.chunk_into_snippets(text, max_sentences=3)
        for idx, s in enumerate(snippets):
            assert s.chunk_index == idx

    def test_max_sentences_clamped(self, chunker):
        """max_sentences is clamped to 1-3."""
        text = "A. B. C. D. E."
        # Requesting more than 3 should still use 3
        snippets_high = chunker.chunk_into_snippets(text, max_sentences=10)
        snippets_normal = chunker.chunk_into_snippets(text, max_sentences=3)
        assert len(snippets_high) == len(snippets_normal)

    def test_max_sentences_one(self, chunker):
        text = "One. Two. Three."
        snippets = chunker.chunk_into_snippets(text, max_sentences=1)
        assert len(snippets) == 3

    def test_large_text_produces_many_snippets(self, chunker):
        text = ". ".join(f"Sentence number {i}" for i in range(100)) + "."
        snippets = chunker.chunk_into_snippets(text, max_sentences=3)
        # Should be roughly 100/3 ≈ 34 snippets
        assert 30 <= len(snippets) <= 40


class TestTextChunkNewFields:
    """Test that the extended TextChunk dataclass works correctly."""

    def test_new_fields_default_none(self):
        chunk = TextChunk(text="hello", start_index=0, end_index=5)
        assert chunk.chunk_index is None
        assert chunk.prev_context is None
        assert chunk.next_context is None
        assert chunk.source_url is None
        assert chunk.entity_refs is None

    def test_new_fields_set(self):
        chunk = TextChunk(
            text="hello",
            start_index=0,
            end_index=5,
            chunk_index=3,
            prev_context="prev...",
            next_context="next...",
            source_url="https://x.com",
            entity_refs=["Microsoft", "Google"],
        )
        assert chunk.chunk_index == 3
        assert chunk.prev_context == "prev..."
        assert chunk.next_context == "next..."
        assert chunk.source_url == "https://x.com"
        assert chunk.entity_refs == ["Microsoft", "Google"]


# ===========================================================================
# Per-field Entity Embedding Tests
# ===========================================================================


class TestPerFieldEntityEmbeddings:
    """Test that entity embeddings are per-field, not a single JSON blob."""

    @pytest.fixture
    def engine(self):
        from garuda_intel.extractor.semantic_engine import SemanticEngine
        engine = SemanticEngine.__new__(SemanticEngine)
        engine.logger = MagicMock()
        engine._embedder = None
        engine.min_text_length_for_embedding = 5
        engine.cache_manager = None
        engine.text_processor = MagicMock()
        # Mock embed_text to return deterministic vectors
        engine.embed_text = MagicMock(return_value=[0.1] * 384)
        return engine

    def test_entity_name_embedded_separately(self, engine):
        entities = [{"name": "Microsoft", "kind": "company", "attrs": {"industry": "Technology", "description": "Big tech company"}}]
        entries = engine.build_embeddings_for_entities(
            entities=entities,
            source_url="https://example.com",
            entity_type="company",
            entity_id_map={("Microsoft", "company"): "eid-1"},
        )
        # Should have: name + industry + description = 3 embeddings
        assert len(entries) >= 3
        # Check that the name embedding is present
        name_entries = [e for e in entries if e["payload"]["kind"] == "entity" and e["payload"]["text"] == "Microsoft"]
        assert len(name_entries) == 1

    def test_entity_field_embeddings_present(self, engine):
        entities = [{
            "name": "Acme Corp",
            "kind": "company",
            "attrs": {
                "industry": "Manufacturing",
                "description": "A large manufacturing company specialising in widgets.",
                "founded": "1985",
            },
        }]
        entries = engine.build_embeddings_for_entities(
            entities=entities,
            source_url="https://acme.com",
            entity_type="company",
            entity_id_map={("Acme Corp", "company"): "eid-2"},
        )
        # Should have field embeddings with kind "entity_field"
        field_entries = [e for e in entries if e["payload"]["kind"] == "entity_field"]
        assert len(field_entries) >= 2  # industry, description, possibly founded

    def test_empty_attrs_still_embeds_name(self, engine):
        entities = [{"name": "Tesla", "kind": "company", "attrs": {}}]
        entries = engine.build_embeddings_for_entities(
            entities=entities,
            source_url="https://tesla.com",
            entity_type="company",
            entity_id_map={("Tesla", "company"): "eid-3"},
        )
        assert len(entries) == 1  # Only the name embedding
        assert entries[0]["payload"]["text"] == "Tesla"


# ===========================================================================
# Snippet Embedding Tests
# ===========================================================================


class TestSnippetEmbeddings:
    """Test SemanticEngine.build_snippet_embeddings."""

    @pytest.fixture
    def engine(self):
        from garuda_intel.extractor.semantic_engine import SemanticEngine
        engine = SemanticEngine.__new__(SemanticEngine)
        engine.logger = MagicMock()
        engine._embedder = None
        engine.min_text_length_for_embedding = 5
        engine.cache_manager = None
        engine.text_processor = MagicMock()
        engine.embed_text = MagicMock(return_value=[0.1] * 384)
        return engine

    def test_snippet_embeddings_generated(self, engine):
        snippet1 = TextChunk(text="The sky is blue.", start_index=0, end_index=16, chunk_index=0)
        snippet2 = TextChunk(text="The grass is green.", start_index=17, end_index=36, chunk_index=1)

        entries = engine.build_snippet_embeddings(
            snippets=[snippet1, snippet2],
            source_url="https://example.com",
            page_type="article",
            entity_name="Nature",
            entity_type="topic",
            page_uuid="page-uuid-1",
        )
        assert len(entries) == 2
        for e in entries:
            assert e["payload"]["kind"] == "semantic-snippet"
            assert e["payload"]["url"] == "https://example.com"

    def test_snippet_too_short_skipped(self, engine):
        engine.min_text_length_for_embedding = 20
        snippet = TextChunk(text="Hi.", start_index=0, end_index=3, chunk_index=0)
        entries = engine.build_snippet_embeddings(
            snippets=[snippet],
            source_url="https://x.com",
            page_type="article",
            entity_name="Test",
            entity_type="topic",
        )
        assert len(entries) == 0


# ===========================================================================
# Reduced Seed Tests
# ===========================================================================


class TestReducedSeeds:
    """Test that seed generation produces fewer queries."""

    def test_company_single_base_query(self):
        from garuda_intel.discover.seeds import generate_seeds
        from garuda_intel.types.entity.profile import EntityProfile
        from garuda_intel.types.entity.type import EntityType

        profile = EntityProfile(name="TestCorp", entity_type=EntityType.COMPANY)

        # Mock LLM to return no additional queries
        mock_llm = MagicMock()
        mock_llm.generate_search_queries.return_value = []
        mock_llm.embed_text.return_value = []

        seeds = generate_seeds(profile, mock_llm)
        # Should have only the single base query
        assert len(seeds) == 1
        assert "official site" in seeds[0]

    def test_person_single_base_query(self):
        from garuda_intel.discover.seeds import generate_seeds
        from garuda_intel.types.entity.profile import EntityProfile
        from garuda_intel.types.entity.type import EntityType

        profile = EntityProfile(name="Jane Doe", entity_type=EntityType.PERSON)

        mock_llm = MagicMock()
        mock_llm.generate_search_queries.return_value = []
        mock_llm.embed_text.return_value = []

        seeds = generate_seeds(profile, mock_llm)
        assert len(seeds) == 1
        assert "biography" in seeds[0]

    def test_topic_single_base_query(self):
        from garuda_intel.discover.seeds import generate_seeds
        from garuda_intel.types.entity.profile import EntityProfile
        from garuda_intel.types.entity.type import EntityType

        profile = EntityProfile(name="Machine Learning", entity_type=EntityType.TOPIC)

        mock_llm = MagicMock()
        mock_llm.generate_search_queries.return_value = []
        mock_llm.embed_text.return_value = []

        seeds = generate_seeds(profile, mock_llm)
        assert len(seeds) == 1
        assert "wiki" in seeds[0]

    def test_seeds_capped_at_max(self):
        from garuda_intel.discover.seeds import generate_seeds
        from garuda_intel.types.entity.profile import EntityProfile
        from garuda_intel.types.entity.type import EntityType

        profile = EntityProfile(name="TestCorp", entity_type=EntityType.COMPANY)

        mock_llm = MagicMock()
        # LLM returns many queries
        mock_llm.generate_search_queries.return_value = [f"query {i}" for i in range(20)]
        mock_llm.embed_text.return_value = []  # Bypass similarity filtering

        seeds = generate_seeds(profile, mock_llm)
        assert len(seeds) <= 4  # MAX_SEED_QUERIES = 4


# ===========================================================================
# Multi-step Reflect and Verify Tests
# ===========================================================================


class TestMultiStepReflect:
    """Test QAValidator reflect_and_verify splitting for large findings."""

    def test_split_finding_basic(self):
        finding = {
            "basic_info": {"official_name": "TestCorp"},
            "persons": [{"name": "Alice"}, {"name": "Bob"}],
            "locations": [{"city": "Berlin"}],
        }
        subs = QAValidator._split_finding(finding)
        # basic_info alone + basic_info+persons + basic_info+locations = 3
        assert len(subs) == 3

    def test_split_finding_empty(self):
        finding = {}
        subs = QAValidator._split_finding(finding)
        assert len(subs) == 1  # Falls back to [finding]

    def test_split_finding_only_basic(self):
        finding = {"basic_info": {"official_name": "X"}}
        subs = QAValidator._split_finding(finding)
        assert len(subs) == 1  # Just the basic_info sub

    def test_small_finding_verified_in_single_pass(self):
        """A small finding should not be split."""
        validator = QAValidator()
        finding = {"basic_info": {"official_name": "X"}}
        assert len(json.dumps(finding)) < _MAX_FINDING_CHARS

        from garuda_intel.types.entity.profile import EntityProfile
        from garuda_intel.types.entity.type import EntityType

        profile = EntityProfile(name="X", entity_type=EntityType.COMPANY)

        # Mock the internal single-pass method
        with patch.object(validator, '_verify_single', return_value=(True, 85.0)) as mock_verify:
            is_ok, score = validator.reflect_and_verify(profile, finding)
            assert is_ok is True
            assert score == 85.0
            mock_verify.assert_called_once()

    def test_large_finding_splits_into_multiple(self):
        """A very large finding should be split into sub-findings."""
        validator = QAValidator()

        from garuda_intel.types.entity.profile import EntityProfile
        from garuda_intel.types.entity.type import EntityType

        profile = EntityProfile(name="BigCorp", entity_type=EntityType.COMPANY)

        # Build a finding that exceeds _MAX_FINDING_CHARS
        finding = {
            "basic_info": {"official_name": "BigCorp", "description": "x" * 3000},
            "persons": [{"name": f"Person {i}", "bio": "x" * 200} for i in range(20)],
            "products": [{"name": f"Product {i}", "description": "y" * 200} for i in range(20)],
        }
        assert len(json.dumps(finding)) > _MAX_FINDING_CHARS

        with patch.object(validator, '_verify_single', return_value=(True, 80.0)) as mock_verify:
            is_ok, score = validator.reflect_and_verify(profile, finding)
            assert is_ok is True
            # Should be called multiple times (once per sub-finding)
            assert mock_verify.call_count >= 2


# ===========================================================================
# SemanticSnippet Model Tests
# ===========================================================================


class TestSemanticSnippetModel:
    """Test the SemanticSnippet database model."""

    def test_model_exists_and_has_fields(self):
        from garuda_intel.database.models import SemanticSnippet
        # Verify the model has the expected fields
        columns = SemanticSnippet.__table__.columns
        col_names = {c.name for c in columns}
        assert "text" in col_names
        assert "chunk_index" in col_names
        assert "prev_context" in col_names
        assert "next_context" in col_names
        assert "source_url" in col_names
        assert "page_id" in col_names
        assert "entity_id" in col_names
        assert "entity_refs_json" in col_names

    def test_to_dict(self):
        from garuda_intel.database.models import SemanticSnippet
        snip = SemanticSnippet(
            id=uuid.uuid4(),
            text="Hello world.",
            chunk_index=0,
            prev_context=None,
            next_context="Next sentence.",
            source_url="https://example.com",
            entity_refs_json=["Microsoft"],
        )
        d = snip.to_dict()
        assert d["text"] == "Hello world."
        assert d["chunk_index"] == 0
        assert d["next_context"] == "Next sentence."
        assert d["entity_refs"] == ["Microsoft"]

    def test_model_in_exports(self):
        from garuda_intel.database import SemanticSnippet
        assert SemanticSnippet is not None

    def test_snippet_table_creation(self):
        """Verify the table can be created in an in-memory database."""
        from sqlalchemy import create_engine
        from garuda_intel.database.models import Base
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        # If we get here, the table was created successfully
        assert "semantic_snippets" in Base.metadata.tables
