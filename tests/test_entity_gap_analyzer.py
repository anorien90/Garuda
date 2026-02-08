"""
Tests for EntityGapAnalyzer, specifically the generate_crawl_plan signature changes
to support both legacy (entity_name) and new (entity object) calling patterns.
"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from garuda_intel.services.entity_gap_analyzer import EntityGapAnalyzer
from garuda_intel.database.store import PersistenceStore
from garuda_intel.database.models import Entity, Intelligence


class TestEntityGapAnalyzerCrawlPlan:
    """Test suite for generate_crawl_plan signature and behavior."""
    
    @pytest.fixture
    def mock_store(self):
        """Create a mock store for testing."""
        store = Mock(spec=PersistenceStore)
        session_mock = MagicMock()
        store.Session.return_value.__enter__.return_value = session_mock
        store.Session.return_value.__exit__.return_value = None
        return store, session_mock
    
    @pytest.fixture
    def sample_entity(self):
        """Create a sample entity for testing."""
        entity = Mock(spec=Entity)
        entity.id = uuid.uuid4()
        entity.name = "Bill Gates"
        entity.kind = "person"
        entity.data = {"title": "Co-founder", "organization": "Microsoft"}
        entity.metadata_json = {}
        entity.updated_at = datetime.now()
        return entity
    
    def test_legacy_call_with_entity_name_positional(self, mock_store):
        """Test backwards compatibility: positional args (entity_name, entity_type)."""
        store, session_mock = mock_store
        analyzer = EntityGapAnalyzer(store)
        
        # Mock entity found in DB
        mock_entity = Mock(spec=Entity)
        mock_entity.id = uuid.uuid4()
        mock_entity.name = "Microsoft"
        mock_entity.kind = "company"
        mock_entity.updated_at = datetime.now()
        
        session_mock.query.return_value.filter.return_value.first.return_value = mock_entity
        session_mock.query.return_value.filter.return_value.all.return_value = []
        
        # Legacy call: positional arguments
        plan = analyzer.generate_crawl_plan("Microsoft", "company")
        
        assert plan is not None
        assert plan["mode"] == "gap_filling"
        assert plan["entity_name"] == "Microsoft"
        assert plan["entity_id"] == str(mock_entity.id)
        assert "task_type" not in plan
        assert "context" not in plan
    
    def test_legacy_call_with_keyword_args(self, mock_store):
        """Test backwards compatibility: keyword args entity_name and entity_type."""
        store, session_mock = mock_store
        analyzer = EntityGapAnalyzer(store)
        
        # Mock entity found in DB
        mock_entity = Mock(spec=Entity)
        mock_entity.id = uuid.uuid4()
        mock_entity.name = "Apple Inc"
        mock_entity.kind = "company"
        mock_entity.updated_at = datetime.now()
        
        session_mock.query.return_value.filter.return_value.first.return_value = mock_entity
        session_mock.query.return_value.filter.return_value.all.return_value = []
        
        # Legacy call: keyword arguments
        plan = analyzer.generate_crawl_plan(entity_name="Apple Inc", entity_type="company")
        
        assert plan is not None
        assert plan["mode"] == "gap_filling"
        assert plan["entity_name"] == "Apple Inc"
    
    def test_new_call_with_entity_object(self, mock_store, sample_entity):
        """Test new signature: passing entity object directly."""
        store, session_mock = mock_store
        analyzer = EntityGapAnalyzer(store)
        
        # Mock the analyze_entity_gaps call
        with patch.object(analyzer, 'analyze_entity_gaps') as mock_analyze:
            mock_analyze.return_value = {
                "entity_id": str(sample_entity.id),
                "entity_name": sample_entity.name,
                "entity_type": sample_entity.kind,
                "completeness_score": 75.0,
                "missing_fields": ["email", "social_media"],
                "suggested_queries": ["Bill Gates contact", "Bill Gates social media"],
                "suggested_sources": ["linkedin.com", "twitter.com"]
            }
            
            # New call: entity object
            plan = analyzer.generate_crawl_plan(entity=sample_entity)
            
            assert plan is not None
            assert plan["mode"] == "gap_filling"
            assert plan["entity_name"] == "Bill Gates"
            assert plan["entity_id"] == str(sample_entity.id)
            assert "analysis" in plan
            mock_analyze.assert_called_once_with(str(sample_entity.id))
    
    def test_new_call_with_entity_and_task_context(self, mock_store, sample_entity):
        """Test new signature: entity object with task_type and context."""
        store, session_mock = mock_store
        analyzer = EntityGapAnalyzer(store)
        
        # Mock the analyze_entity_gaps call
        with patch.object(analyzer, 'analyze_entity_gaps') as mock_analyze:
            mock_analyze.return_value = {
                "entity_id": str(sample_entity.id),
                "entity_name": sample_entity.name,
                "suggested_queries": ["query1"],
                "suggested_sources": ["source1"]
            }
            
            # New call: entity object with task_type and context
            plan = analyzer.generate_crawl_plan(
                entity=sample_entity,
                task_type="investigate_crawl",
                context="High priority investigation"
            )
            
            assert plan is not None
            assert plan["mode"] == "gap_filling"
            assert plan["entity_name"] == "Bill Gates"
            assert plan["task_type"] == "investigate_crawl"
            assert plan["context"] == "High priority investigation"
    
    def test_new_call_entity_name_with_task_context(self, mock_store):
        """Test that entity_name lookup also supports task_type and context."""
        store, session_mock = mock_store
        analyzer = EntityGapAnalyzer(store)
        
        # Mock entity found in DB
        mock_entity = Mock(spec=Entity)
        mock_entity.id = uuid.uuid4()
        mock_entity.name = "Google"
        mock_entity.kind = "company"
        mock_entity.updated_at = datetime.now()
        
        session_mock.query.return_value.filter.return_value.first.return_value = mock_entity
        session_mock.query.return_value.filter.return_value.all.return_value = []
        
        # Call with entity_name and task context
        plan = analyzer.generate_crawl_plan(
            entity_name="Google",
            task_type="fill_gap",
            context="Missing revenue data"
        )
        
        assert plan is not None
        assert plan["mode"] == "gap_filling"
        assert plan["entity_name"] == "Google"
        assert plan["task_type"] == "fill_gap"
        assert plan["context"] == "Missing revenue data"
    
    def test_discovery_mode_with_task_context(self, mock_store):
        """Test discovery mode (entity not found) with task context."""
        store, session_mock = mock_store
        analyzer = EntityGapAnalyzer(store)
        
        # Mock entity NOT found in DB
        session_mock.query.return_value.filter.return_value.first.return_value = None
        
        # Call with entity_name that doesn't exist
        plan = analyzer.generate_crawl_plan(
            entity_name="NewStartup Inc",
            entity_type="company",
            task_type="discover",
            context="Initial discovery"
        )
        
        assert plan is not None
        assert plan["mode"] == "discovery"
        assert plan["entity_name"] == "NewStartup Inc"
        assert plan["entity_type"] == "company"
        assert plan["task_type"] == "discover"
        assert plan["context"] == "Initial discovery"
    
    def test_missing_both_entity_and_entity_name_raises_error(self, mock_store):
        """Test that missing both entity and entity_name raises ValueError."""
        store, session_mock = mock_store
        analyzer = EntityGapAnalyzer(store)
        
        # Call without entity or entity_name should raise ValueError
        with pytest.raises(ValueError, match="Must provide either 'entity' or 'entity_name'"):
            analyzer.generate_crawl_plan()
    
    def test_entity_takes_precedence_over_entity_name(self, mock_store, sample_entity):
        """Test that when both entity and entity_name are provided, entity is used."""
        store, session_mock = mock_store
        analyzer = EntityGapAnalyzer(store)
        
        # Mock the analyze_entity_gaps call
        with patch.object(analyzer, 'analyze_entity_gaps') as mock_analyze:
            mock_analyze.return_value = {
                "entity_id": str(sample_entity.id),
                "entity_name": sample_entity.name,
                "suggested_queries": [],
                "suggested_sources": []
            }
            
            # Call with both - entity should take precedence
            plan = analyzer.generate_crawl_plan(
                entity_name="SomeOtherName",
                entity=sample_entity
            )
            
            # Should use the entity object, not lookup by name
            assert plan["entity_name"] == "Bill Gates"
            assert plan["entity_id"] == str(sample_entity.id)
            # Session should not be used for lookup since entity was provided
            session_mock.query.assert_not_called()
    
    def test_optional_task_type_only(self, mock_store, sample_entity):
        """Test providing only task_type without context."""
        store, session_mock = mock_store
        analyzer = EntityGapAnalyzer(store)
        
        with patch.object(analyzer, 'analyze_entity_gaps') as mock_analyze:
            mock_analyze.return_value = {
                "entity_id": str(sample_entity.id),
                "entity_name": sample_entity.name,
                "suggested_queries": [],
                "suggested_sources": []
            }
            
            plan = analyzer.generate_crawl_plan(
                entity=sample_entity,
                task_type="urgent_fill"
            )
            
            assert plan["task_type"] == "urgent_fill"
            assert "context" not in plan
    
    def test_optional_context_only(self, mock_store, sample_entity):
        """Test providing only context without task_type."""
        store, session_mock = mock_store
        analyzer = EntityGapAnalyzer(store)
        
        with patch.object(analyzer, 'analyze_entity_gaps') as mock_analyze:
            mock_analyze.return_value = {
                "entity_id": str(sample_entity.id),
                "entity_name": sample_entity.name,
                "suggested_queries": [],
                "suggested_sources": []
            }
            
            plan = analyzer.generate_crawl_plan(
                entity=sample_entity,
                context="Background research"
            )
            
            assert plan["context"] == "Background research"
            assert "task_type" not in plan
    
    def test_plan_structure_consistency(self, mock_store, sample_entity):
        """Test that plan structure is consistent across different call patterns."""
        store, session_mock = mock_store
        analyzer = EntityGapAnalyzer(store)
        
        with patch.object(analyzer, 'analyze_entity_gaps') as mock_analyze:
            mock_analyze.return_value = {
                "entity_id": str(sample_entity.id),
                "entity_name": sample_entity.name,
                "suggested_queries": ["q1", "q2"],
                "suggested_sources": ["s1", "s2"]
            }
            
            plan = analyzer.generate_crawl_plan(entity=sample_entity)
            
            # Verify required keys
            assert "mode" in plan
            assert "entity_id" in plan
            assert "entity_name" in plan
            assert "analysis" in plan
            assert "strategy" in plan
            assert "queries" in plan
            assert "sources" in plan
            assert "priority" in plan
            
            # Verify values
            assert plan["mode"] == "gap_filling"
            assert plan["strategy"] == "targeted"
            assert plan["priority"] == "fill_critical_gaps"
            assert plan["queries"] == ["q1", "q2"]
            assert plan["sources"] == ["s1", "s2"]
