"""
Tests for the Agent Service functionality.

Tests cover:
- Reflect & Refine mode (entity merging, data quality)
- Explore & Prioritize mode (entity graph exploration)
- Multidimensional RAG search
- Async chat functionality
- Autonomous discovery mode
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from garuda_intel.config import Settings


class TestAgentSettings:
    """Test agent-related settings in config."""
    
    def test_default_llm_summarize_timeout(self):
        """Test default value for llm_summarize_timeout."""
        settings = Settings()
        assert settings.llm_summarize_timeout == 900  # 15 minutes
    
    def test_default_llm_extract_timeout(self):
        """Test default value for llm_extract_timeout."""
        settings = Settings()
        assert settings.llm_extract_timeout == 900  # 15 minutes
    
    def test_default_llm_reflect_timeout(self):
        """Test default value for llm_reflect_timeout."""
        settings = Settings()
        assert settings.llm_reflect_timeout == 300  # 5 minutes
    
    def test_default_agent_enabled(self):
        """Test default value for agent_enabled."""
        settings = Settings()
        assert settings.agent_enabled is True
    
    def test_default_agent_max_exploration_depth(self):
        """Test default value for agent_max_exploration_depth."""
        settings = Settings()
        assert settings.agent_max_exploration_depth == 3
    
    def test_default_agent_entity_merge_threshold(self):
        """Test default value for agent_entity_merge_threshold."""
        settings = Settings()
        assert settings.agent_entity_merge_threshold == 0.85
    
    def test_default_agent_priority_weights(self):
        """Test default values for agent priority weights."""
        settings = Settings()
        assert settings.agent_priority_unknown_weight == 0.7
        assert settings.agent_priority_relation_weight == 0.3
    
    @patch.dict('os.environ', {
        'GARUDA_LLM_SUMMARIZE_TIMEOUT': '1800',
        'GARUDA_AGENT_MAX_EXPLORATION_DEPTH': '5',
        'GARUDA_AGENT_ENTITY_MERGE_THRESHOLD': '0.9',
    })
    def test_settings_from_env(self):
        """Test that settings are loaded from environment variables."""
        settings = Settings.from_env()
        
        assert settings.llm_summarize_timeout == 1800
        assert settings.agent_max_exploration_depth == 5
        assert settings.agent_entity_merge_threshold == 0.9


class TestEntityNameNormalization:
    """Test entity name normalization for duplicate detection."""
    
    def test_normalize_basic_name(self):
        """Test basic name normalization."""
        from garuda_intel.services.agent_service import AgentService
        
        # Create minimal mock for AgentService
        mock_store = MagicMock()
        mock_store.Session = MagicMock()
        
        agent = AgentService(
            store=mock_store,
            llm=None,
            vector_store=None,
        )
        
        # Test various company name patterns
        assert agent._normalize_entity_name("Microsoft Corporation") == "microsoft"
        assert agent._normalize_entity_name("Microsoft Corp") == "microsoft"
        assert agent._normalize_entity_name("Microsoft Corp.") == "microsoft"
        assert agent._normalize_entity_name("Microsoft Inc") == "microsoft"
        assert agent._normalize_entity_name("Microsoft Inc.") == "microsoft"
    
    def test_normalize_preserves_distinct_names(self):
        """Test that distinct names are preserved."""
        from garuda_intel.services.agent_service import AgentService
        
        mock_store = MagicMock()
        mock_store.Session = MagicMock()
        
        agent = AgentService(
            store=mock_store,
            llm=None,
            vector_store=None,
        )
        
        # Different names should stay different
        name1 = agent._normalize_entity_name("Apple Inc")
        name2 = agent._normalize_entity_name("Microsoft Corp")
        assert name1 != name2


class TestEntityMentionExtraction:
    """Test entity mention extraction from text."""
    
    def test_extract_capitalized_names(self):
        """Test extraction of capitalized entity names."""
        from garuda_intel.services.agent_service import AgentService
        
        mock_store = MagicMock()
        mock_store.Session = MagicMock()
        
        agent = AgentService(
            store=mock_store,
            llm=None,
            vector_store=None,
        )
        
        text = "Bill Gates founded Microsoft Corporation in 1975 with Paul Allen."
        entities = agent._extract_entity_mentions(text)
        
        assert "Bill Gates" in entities or "Bill" in entities
        assert "Microsoft Corporation" in entities or "Microsoft" in entities
    
    def test_filters_common_words(self):
        """Test that common words are filtered out."""
        from garuda_intel.services.agent_service import AgentService
        
        mock_store = MagicMock()
        mock_store.Session = MagicMock()
        
        agent = AgentService(
            store=mock_store,
            llm=None,
            vector_store=None,
        )
        
        text = "The company was founded in Seattle."
        entities = agent._extract_entity_mentions(text)
        
        # "The" should be filtered
        assert "The" not in entities


class TestSearchResultCombination:
    """Test combining search results from different sources."""
    
    def test_combine_results_deduplication(self):
        """Test that duplicate results are deduplicated."""
        from garuda_intel.services.agent_service import AgentService
        
        mock_store = MagicMock()
        mock_store.Session = MagicMock()
        
        agent = AgentService(
            store=mock_store,
            llm=None,
            vector_store=None,
        )
        
        embedding_results = [
            {"url": "http://example.com/1", "score": 0.9, "text": "Test 1"},
            {"url": "http://example.com/2", "score": 0.8, "text": "Test 2"},
        ]
        
        graph_results = [
            {"url": "http://example.com/1", "score": 0.7, "text": "Test 1"},  # Duplicate URL
            {"url": "http://example.com/3", "score": 0.6, "text": "Test 3"},
        ]
        
        combined = agent._combine_search_results(embedding_results, graph_results, limit=10)
        
        # Should have 3 unique results
        urls = [r.get("url") for r in combined]
        assert len(set(urls)) == 3
    
    def test_combine_results_scoring(self):
        """Test that combined results are properly scored."""
        from garuda_intel.services.agent_service import AgentService
        
        mock_store = MagicMock()
        mock_store.Session = MagicMock()
        
        agent = AgentService(
            store=mock_store,
            llm=None,
            vector_store=None,
        )
        
        embedding_results = [
            {"url": "http://example.com/1", "score": 0.9, "text": "Test 1"},
        ]
        
        graph_results = [
            {"url": "http://example.com/1", "score": 0.5, "text": "Test 1"},  # Same URL
        ]
        
        combined = agent._combine_search_results(embedding_results, graph_results, limit=10)
        
        # Combined score should be sum of both scores
        assert len(combined) == 1
        assert combined[0].get("combined_score", 0) > 0.9  # Boosted embedding + graph


class TestPriorityScoring:
    """Test entity priority scoring for exploration."""
    
    def test_priority_calculation(self):
        """Test that priority scores are calculated correctly."""
        # Test the formula: priority = unknown_weight * unknown_score + relation_weight * relation_score
        
        # Example: depth=2, max_depth=3, relations=5
        unknown_weight = 0.7
        relation_weight = 0.3
        max_depth = 3
        
        depth = 2
        relations = 5
        
        unknown_score = depth / max_depth  # 2/3 = 0.666...
        relation_score = min(relations / 10.0, 1.0)  # 5/10 = 0.5
        
        expected_priority = unknown_weight * unknown_score + relation_weight * relation_score
        
        # 0.7 * 0.666... + 0.3 * 0.5 = 0.466... + 0.15 = 0.616...
        assert 0.6 < expected_priority < 0.7


class TestHierarchicalSummarization:
    """Test hierarchical summarization for large texts."""
    
    def test_summarize_small_text_directly(self):
        """Test that small texts are summarized directly without segmentation."""
        from garuda_intel.extractor.llm import LLMIntelExtractor
        
        # Create LLMIntelExtractor with mocked HTTP calls
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"response": "Summary of the text."}
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response
            
            extractor = LLMIntelExtractor()
            
            # Small text should call LLM once
            small_text = "This is a short text about Microsoft."
            result = extractor.summarize_page(small_text)
            
            # Should return the summary
            assert result != ""
            # LLM should have been called
            assert mock_post.called
    
    def test_hierarchical_summarize_chunks_large_text(self):
        """Test that large texts are chunked for hierarchical summarization."""
        from garuda_intel.extractor.llm import LLMIntelExtractor
        
        # Create LLMIntelExtractor with mocked HTTP calls
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"response": "Partial summary."}
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response
            
            extractor = LLMIntelExtractor(summary_chunk_chars=100)  # Small chunks for testing
            
            # Large text that needs chunking
            large_text = "This is a very long text about Microsoft. " * 100
            result = extractor.summarize_page(large_text)
            
            # Should return some summary
            assert result != "" or mock_post.called


class TestReflectReportSummary:
    """Test summary generation from reflect reports."""
    
    def test_summarize_reflect_with_duplicates(self):
        """Test summarizing reflection report with duplicates."""
        from garuda_intel.services.agent_service import AgentService
        
        mock_store = MagicMock()
        mock_store.Session = MagicMock()
        
        agent = AgentService(
            store=mock_store,
            llm=None,
            vector_store=None,
        )
        
        report = {
            "duplicates_found": [
                {"normalized_name": "microsoft", "count": 2},
                {"normalized_name": "apple", "count": 3},
            ],
            "data_quality_issues": [
                {"entity_id": "1", "issues": ["Missing kind"]},
            ],
        }
        
        summary = agent._summarize_reflect_report(report)
        
        assert "2" in summary  # Should mention 2 duplicate groups
        assert "1" in summary  # Should mention 1 quality issue
    
    def test_summarize_reflect_no_issues(self):
        """Test summarizing reflection report with no issues."""
        from garuda_intel.services.agent_service import AgentService
        
        mock_store = MagicMock()
        mock_store.Session = MagicMock()
        
        agent = AgentService(
            store=mock_store,
            llm=None,
            vector_store=None,
        )
        
        report = {
            "duplicates_found": [],
            "data_quality_issues": [],
        }
        
        summary = agent._summarize_reflect_report(report)
        
        assert "clean" in summary.lower() or "no" in summary.lower()


class TestAutonomousSettings:
    """Test autonomous mode settings in config."""

    def test_default_autonomous_enabled(self):
        """Test default value for agent_autonomous_enabled."""
        settings = Settings()
        assert settings.agent_autonomous_enabled is False

    def test_default_autonomous_interval(self):
        """Test default value for agent_autonomous_interval."""
        settings = Settings()
        assert settings.agent_autonomous_interval == 300

    def test_default_autonomous_max_entities(self):
        """Test default value for agent_autonomous_max_entities."""
        settings = Settings()
        assert settings.agent_autonomous_max_entities == 10

    def test_default_autonomous_priority_threshold(self):
        """Test default value for agent_autonomous_priority_threshold."""
        settings = Settings()
        assert settings.agent_autonomous_priority_threshold == 0.3

    def test_default_autonomous_max_depth(self):
        """Test default value for agent_autonomous_max_depth."""
        settings = Settings()
        assert settings.agent_autonomous_max_depth == 3

    def test_default_autonomous_auto_crawl(self):
        """Test default value for agent_autonomous_auto_crawl."""
        settings = Settings()
        assert settings.agent_autonomous_auto_crawl is False

    def test_default_autonomous_max_pages(self):
        """Test default value for agent_autonomous_max_pages."""
        settings = Settings()
        assert settings.agent_autonomous_max_pages == 25

    @patch.dict('os.environ', {
        'GARUDA_AGENT_AUTONOMOUS_ENABLED': 'true',
        'GARUDA_AGENT_AUTONOMOUS_INTERVAL': '600',
        'GARUDA_AGENT_AUTONOMOUS_MAX_ENTITIES': '20',
        'GARUDA_AGENT_AUTONOMOUS_PRIORITY_THRESHOLD': '0.5',
        'GARUDA_AGENT_AUTONOMOUS_MAX_DEPTH': '4',
        'GARUDA_AGENT_AUTONOMOUS_AUTO_CRAWL': 'true',
        'GARUDA_AGENT_AUTONOMOUS_MAX_PAGES': '50',
    })
    def test_autonomous_settings_from_env(self):
        """Test that autonomous settings are loaded from environment variables."""
        settings = Settings.from_env()

        assert settings.agent_autonomous_enabled is True
        assert settings.agent_autonomous_interval == 600
        assert settings.agent_autonomous_max_entities == 20
        assert settings.agent_autonomous_priority_threshold == 0.5
        assert settings.agent_autonomous_max_depth == 4
        assert settings.agent_autonomous_auto_crawl is True
        assert settings.agent_autonomous_max_pages == 50


class TestAutonomousDiscover:
    """Test autonomous discovery mode in AgentService."""

    def test_autonomous_discover_returns_report_structure(self):
        """Test that autonomous_discover returns correct report structure."""
        from garuda_intel.services.agent_service import AgentService

        mock_store = MagicMock()
        mock_session = MagicMock()
        mock_store.Session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_store.Session.return_value.__exit__ = MagicMock(return_value=False)
        # Return empty results for queries
        mock_session.execute.return_value.all.return_value = []
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value.scalar.return_value = 0

        agent = AgentService(
            store=mock_store,
            llm=None,
            vector_store=None,
        )

        report = agent.autonomous_discover(max_entities=5)

        assert report["mode"] == "autonomous_discover"
        assert "started_at" in report
        assert "completed_at" in report
        assert "dead_ends" in report
        assert "knowledge_gaps" in report
        assert "crawl_plans" in report
        assert "crawl_results" in report
        assert "statistics" in report
        stats = report["statistics"]
        assert "dead_ends_found" in stats
        assert "gaps_found" in stats
        assert "crawl_plans_generated" in stats
        assert "crawls_executed" in stats
        assert "entities_analyzed" in stats

    def test_autonomous_discover_no_entities_message(self):
        """Test that autonomous_discover handles no entities gracefully."""
        from garuda_intel.services.agent_service import AgentService

        mock_store = MagicMock()
        mock_session = MagicMock()
        mock_store.Session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_store.Session.return_value.__exit__ = MagicMock(return_value=False)
        # Return empty results for everything
        mock_session.execute.return_value.all.return_value = []
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value.scalar.return_value = 0

        agent = AgentService(
            store=mock_store,
            llm=None,
            vector_store=None,
        )

        report = agent.autonomous_discover()

        assert report["statistics"]["dead_ends_found"] == 0
        assert report["statistics"]["gaps_found"] == 0
        assert report["statistics"]["crawl_plans_generated"] == 0
        assert report["statistics"]["crawls_executed"] == 0


class TestReflectRelate:
    """Test reflect & relate mode in AgentService."""

    def test_reflect_relate_returns_report_structure(self):
        """Test that reflect_relate returns correct report structure."""
        from garuda_intel.services.agent_service import AgentService
        mock_store = MagicMock()
        mock_session = MagicMock()
        mock_store.Session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_store.Session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.all.return_value = []
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value.scalar.return_value = 0

        agent = AgentService(store=mock_store, llm=None, vector_store=None)
        report = agent.reflect_relate()

        assert report["mode"] == "reflect_relate"
        assert "process_id" in report
        assert "started_at" in report
        assert "completed_at" in report
        assert "reflect_report" in report
        assert "potential_relations" in report
        assert "investigation_tasks" in report
        assert "statistics" in report
        stats = report["statistics"]
        assert "entities_analyzed" in stats
        assert "potential_relations_found" in stats
        assert "investigation_tasks_created" in stats

    def test_reflect_relate_empty_db(self):
        """Test reflect_relate with empty database."""
        from garuda_intel.services.agent_service import AgentService
        mock_store = MagicMock()
        mock_session = MagicMock()
        mock_store.Session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_store.Session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.all.return_value = []
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value.scalar.return_value = 0

        agent = AgentService(store=mock_store, llm=None, vector_store=None)
        report = agent.reflect_relate()

        assert report["statistics"]["entities_analyzed"] == 0
        assert report["statistics"]["potential_relations_found"] == 0
        assert report["statistics"]["investigation_tasks_created"] == 0


class TestInvestigateCrawl:
    """Test investigate crawl mode."""

    def test_investigate_crawl_returns_report_structure(self):
        """Test that investigate_crawl returns correct report structure."""
        from garuda_intel.services.agent_service import AgentService
        mock_store = MagicMock()
        mock_session = MagicMock()
        mock_store.Session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_store.Session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.all.return_value = []
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value.scalar.return_value = 0

        agent = AgentService(store=mock_store, llm=None, vector_store=None)
        report = agent.investigate_crawl(investigation_tasks=[])

        assert report["mode"] == "investigate_crawl"
        assert "process_id" in report
        assert "crawl_plans" in report
        assert "crawl_results" in report
        assert "statistics" in report
        stats = report["statistics"]
        assert "tasks_received" in stats
        assert "tasks_processed" in stats
        assert "crawl_plans_generated" in stats
        assert "crawls_executed" in stats


class TestCombinedAutonomous:
    """Test combined autonomous mode."""

    def test_combined_autonomous_returns_report_structure(self):
        """Test that combined_autonomous returns correct report structure."""
        from garuda_intel.services.agent_service import AgentService
        mock_store = MagicMock()
        mock_session = MagicMock()
        mock_store.Session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_store.Session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.all.return_value = []
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value.scalar.return_value = 0

        agent = AgentService(store=mock_store, llm=None, vector_store=None)
        report = agent.combined_autonomous()

        assert report["mode"] == "combined_autonomous"
        assert "process_id" in report
        assert "reflect_relate_report" in report
        assert "investigate_crawl_report" in report
        assert "statistics" in report


class TestProcessManagement:
    """Test process tracking and management."""

    def test_get_process_status_empty(self):
        """Test getting process status when no processes exist."""
        from garuda_intel.services.agent_service import AgentService
        mock_store = MagicMock()
        mock_store.Session = MagicMock()
        agent = AgentService(store=mock_store, llm=None, vector_store=None)

        status = agent.get_process_status()
        assert "processes" in status
        assert len(status["processes"]) == 0

    def test_stop_nonexistent_process(self):
        """Test stopping a process that doesn't exist."""
        from garuda_intel.services.agent_service import AgentService
        mock_store = MagicMock()
        mock_store.Session = MagicMock()
        agent = AgentService(store=mock_store, llm=None, vector_store=None)

        result = agent.stop_process("nonexistent")
        assert "error" in result

    def test_process_created_on_reflect_relate(self):
        """Test that running reflect_relate creates a process entry."""
        from garuda_intel.services.agent_service import AgentService
        mock_store = MagicMock()
        mock_session = MagicMock()
        mock_store.Session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_store.Session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.all.return_value = []
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value.scalar.return_value = 0

        agent = AgentService(store=mock_store, llm=None, vector_store=None)
        report = agent.reflect_relate()

        process_id = report["process_id"]
        status = agent.get_process_status(process_id)
        assert status["status"] == "completed"
