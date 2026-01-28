"""
Unit tests for AdaptiveCrawlerService candidate processing.

Tests the defensive handling of various candidate formats in adaptive_crawler.py.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from garuda_intel.services.adaptive_crawler import AdaptiveCrawlerService


class TestAdaptiveCrawlerCandidateProcessing:
    """Test adaptive crawler's handling of various candidate formats."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for AdaptiveCrawlerService."""
        store = Mock()
        llm = Mock()
        crawl_learner = Mock()
        
        # Mock store.Session() context manager
        session_mock = MagicMock()
        session_mock.__enter__ = Mock(return_value=session_mock)
        session_mock.__exit__ = Mock(return_value=False)
        store.Session = Mock(return_value=session_mock)
        
        # Mock crawl learner methods
        crawl_learner.get_successful_patterns.return_value = []
        crawl_learner.get_learning_stats.return_value = {}
        
        return store, llm, crawl_learner
    
    @pytest.fixture
    def service(self, mock_dependencies):
        """Create AdaptiveCrawlerService instance."""
        store, llm, crawl_learner = mock_dependencies
        return AdaptiveCrawlerService(store, llm, crawl_learner)
    
    @patch('garuda_intel.search.collect_candidates_simple')
    def test_dict_candidates(self, mock_collect, service, mock_dependencies):
        """Test processing dict candidates (expected format)."""
        store, llm, _ = mock_dependencies
        
        # Mock gap analyzer
        service.gap_analyzer.generate_crawl_plan = Mock(return_value={
            'mode': 'discovery',
            'strategy': 'comprehensive',
            'queries': ['"Test Company" headquarters']
        })
        
        # Mock collect_candidates_simple to return dicts
        mock_collect.return_value = [
            {"href": "https://example.com", "title": "Example"},
            {"href": "https://test.com", "title": "Test"}
        ]
        
        result = service.intelligent_crawl("Test Company", max_pages=5, max_depth=1)
        
        # Should extract URLs from dicts
        assert len(result['seed_urls']) > 0
        assert "https://example.com" in result['seed_urls']
        assert "https://test.com" in result['seed_urls']
    
    @patch('garuda_intel.search.collect_candidates_simple')
    def test_string_candidates(self, mock_collect, service, mock_dependencies):
        """Test processing string candidates (defensive handling)."""
        store, llm, _ = mock_dependencies
        
        service.gap_analyzer.generate_crawl_plan = Mock(return_value={
            'mode': 'discovery',
            'strategy': 'comprehensive',
            'queries': ['"Test Company" headquarters']
        })
        
        # Mock collect_candidates_simple to return strings (old behavior)
        mock_collect.return_value = [
            "https://example.com",
            "https://test.com"
        ]
        
        result = service.intelligent_crawl("Test Company", max_pages=5, max_depth=1)
        
        # Should handle strings gracefully
        assert len(result['seed_urls']) > 0
        assert "https://example.com" in result['seed_urls']
        assert "https://test.com" in result['seed_urls']
    
    @patch('garuda_intel.search.collect_candidates_simple')
    def test_mixed_candidates(self, mock_collect, service, mock_dependencies):
        """Test processing mix of dicts and strings."""
        store, llm, _ = mock_dependencies
        
        service.gap_analyzer.generate_crawl_plan = Mock(return_value={
            'mode': 'discovery',
            'strategy': 'comprehensive',
            'queries': ['"Test Company" headquarters']
        })
        
        # Mix of dicts and strings
        mock_collect.return_value = [
            {"href": "https://example.com"},
            "https://test.com",
            {"href": "https://another.com"}
        ]
        
        result = service.intelligent_crawl("Test Company", max_pages=5, max_depth=1)
        
        # Should handle both formats
        assert len(result['seed_urls']) == 3
        assert "https://example.com" in result['seed_urls']
        assert "https://test.com" in result['seed_urls']
        assert "https://another.com" in result['seed_urls']
    
    @patch('garuda_intel.search.collect_candidates_simple')
    def test_invalid_candidates(self, mock_collect, service, mock_dependencies):
        """Test skipping invalid candidate types."""
        store, llm, _ = mock_dependencies
        
        service.gap_analyzer.generate_crawl_plan = Mock(return_value={
            'mode': 'discovery',
            'strategy': 'comprehensive',
            'queries': ['"Test Company" headquarters']
        })
        
        # Mix with invalid types
        mock_collect.return_value = [
            {"href": "https://example.com"},
            None,  # Invalid
            123,   # Invalid
            [],    # Invalid
            "https://test.com"
        ]
        
        result = service.intelligent_crawl("Test Company", max_pages=5, max_depth=1)
        
        # Should skip invalid types
        assert len(result['seed_urls']) == 2
        assert "https://example.com" in result['seed_urls']
        assert "https://test.com" in result['seed_urls']
    
    @patch('garuda_intel.search.collect_candidates_simple')
    def test_empty_candidates(self, mock_collect, service, mock_dependencies):
        """Test handling when no candidates are found."""
        store, llm, _ = mock_dependencies
        
        service.gap_analyzer.generate_crawl_plan = Mock(return_value={
            'mode': 'discovery',
            'strategy': 'comprehensive',
            'queries': ['"Test Company" headquarters']
        })
        
        # Empty response
        mock_collect.return_value = []
        
        result = service.intelligent_crawl("Test Company", max_pages=5, max_depth=1)
        
        # Should handle gracefully
        assert len(result['seed_urls']) == 0
        # Should not proceed with crawl
        assert 'pages_discovered' in result
        assert result['pages_discovered'] == 0
    
    @patch('garuda_intel.search.collect_candidates_simple')
    def test_provider_exception_handling(self, mock_collect, service, mock_dependencies):
        """Test handling provider exceptions (e.g., 429 rate limit)."""
        store, llm, _ = mock_dependencies
        
        service.gap_analyzer.generate_crawl_plan = Mock(return_value={
            'mode': 'discovery',
            'strategy': 'comprehensive',
            'queries': [
                '"Test Company" headquarters',
                '"Test Company" about'
            ]
        })
        
        # First query fails, second succeeds
        mock_collect.side_effect = [
            Exception("Rate limited (429)"),
            [{"href": "https://example.com"}]
        ]
        
        result = service.intelligent_crawl("Test Company", max_pages=5, max_depth=1)
        
        # Should continue with successful query
        assert len(result['seed_urls']) > 0
        assert "https://example.com" in result['seed_urls']
    
    @patch('garuda_intel.search.collect_candidates_simple')
    def test_duplicate_url_filtering(self, mock_collect, service, mock_dependencies):
        """Test that duplicate URLs are filtered out."""
        store, llm, _ = mock_dependencies
        
        service.gap_analyzer.generate_crawl_plan = Mock(return_value={
            'mode': 'discovery',
            'strategy': 'comprehensive',
            'queries': [
                '"Test Company" headquarters',
                '"Test Company" about'
            ]
        })
        
        # Multiple queries returning same URL
        mock_collect.side_effect = [
            [{"href": "https://example.com"}, {"href": "https://test.com"}],
            [{"href": "https://example.com"}, {"href": "https://another.com"}]
        ]
        
        result = service.intelligent_crawl("Test Company", max_pages=5, max_depth=1)
        
        # Should deduplicate
        assert len(result['seed_urls']) == 3
        assert result['seed_urls'].count("https://example.com") == 1
