"""
Unit tests for seed discovery and candidate collection.

Tests various response formats from search providers:
- Dict responses (standard DuckDuckGo format)
- String responses (HTML/direct URLs)
- List responses
- Error responses (429, consent pages, etc.)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from garuda_intel.search.seed_discovery import collect_candidates_simple


class TestCollectCandidatesSimple:
    """Test collect_candidates_simple with various response types."""
    
    @patch('garuda_intel.search.seed_discovery.DDGS')
    def test_dict_response_standard(self, mock_ddgs_class):
        """Test standard dict response from DuckDuckGo."""
        # Setup mock
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = Mock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = Mock(return_value=False)
        mock_ddgs_class.return_value = mock_ddgs
        
        # Standard DuckDuckGo response format
        mock_ddgs.text.return_value = [
            {"href": "https://example.com", "title": "Example", "body": "Description"},
            {"href": "https://test.com", "title": "Test", "body": "Test description"}
        ]
        
        results = collect_candidates_simple(["test query"], limit=5)
        
        # Should return list of dicts
        assert len(results) == 2
        assert all(isinstance(r, dict) for r in results)
        assert results[0]["href"] == "https://example.com"
        assert results[1]["href"] == "https://test.com"
    
    @patch('garuda_intel.search.seed_discovery.DDGS')
    def test_string_response_handling(self, mock_ddgs_class):
        """Test handling when provider returns strings instead of dicts."""
        # Setup mock
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = Mock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = Mock(return_value=False)
        mock_ddgs_class.return_value = mock_ddgs
        
        # Some providers might return strings
        mock_ddgs.text.return_value = [
            "https://example.com",
            "https://test.com"
        ]
        
        results = collect_candidates_simple(["test query"], limit=5)
        
        # Should convert strings to dicts with 'href' key
        assert len(results) == 2
        assert all(isinstance(r, dict) for r in results)
        assert results[0]["href"] == "https://example.com"
        assert results[1]["href"] == "https://test.com"
    
    @patch('garuda_intel.search.seed_discovery.DDGS')
    def test_mixed_response_types(self, mock_ddgs_class):
        """Test handling mix of dicts and strings."""
        # Setup mock
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = Mock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = Mock(return_value=False)
        mock_ddgs_class.return_value = mock_ddgs
        
        # Mixed response
        mock_ddgs.text.return_value = [
            {"href": "https://example.com", "title": "Example"},
            "https://test.com",
            {"href": "https://another.com"}
        ]
        
        results = collect_candidates_simple(["test query"], limit=5)
        
        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)
        assert results[0]["href"] == "https://example.com"
        assert results[1]["href"] == "https://test.com"
        assert results[2]["href"] == "https://another.com"
    
    @patch('garuda_intel.search.seed_discovery.DDGS')
    def test_deduplication(self, mock_ddgs_class):
        """Test that duplicate URLs are removed."""
        # Setup mock
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = Mock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = Mock(return_value=False)
        mock_ddgs_class.return_value = mock_ddgs
        
        # Duplicate URLs
        mock_ddgs.text.return_value = [
            {"href": "https://example.com", "title": "Example 1"},
            {"href": "https://test.com", "title": "Test"},
            {"href": "https://example.com", "title": "Example 2"}  # Duplicate
        ]
        
        results = collect_candidates_simple(["test query"], limit=5)
        
        # Should deduplicate
        assert len(results) == 2
        assert results[0]["href"] == "https://example.com"
        assert results[1]["href"] == "https://test.com"
    
    @patch('garuda_intel.search.seed_discovery.DDGS')
    def test_limit_enforcement(self, mock_ddgs_class):
        """Test that limit parameter is enforced."""
        # Setup mock
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = Mock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = Mock(return_value=False)
        mock_ddgs_class.return_value = mock_ddgs
        
        # More results than limit
        mock_ddgs.text.return_value = [
            {"href": f"https://example{i}.com"} for i in range(10)
        ]
        
        results = collect_candidates_simple(["test query"], limit=3)
        
        # Should respect limit
        assert len(results) == 3
    
    @patch('garuda_intel.search.seed_discovery.DDGS')
    def test_empty_response(self, mock_ddgs_class):
        """Test handling of empty response."""
        # Setup mock
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = Mock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = Mock(return_value=False)
        mock_ddgs_class.return_value = mock_ddgs
        
        mock_ddgs.text.return_value = []
        
        results = collect_candidates_simple(["test query"], limit=5)
        
        assert results == []
    
    @patch('garuda_intel.search.seed_discovery.DDGS')
    def test_search_exception_handling(self, mock_ddgs_class):
        """Test graceful handling of search exceptions (e.g., 429 rate limit)."""
        # Setup mock
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = Mock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = Mock(return_value=False)
        mock_ddgs_class.return_value = mock_ddgs
        
        # First query fails (e.g., 429), second succeeds
        mock_ddgs.text.side_effect = [
            Exception("Rate limited"),
            [{"href": "https://example.com"}]
        ]
        
        results = collect_candidates_simple(["query1", "query2"], limit=5)
        
        # Should continue and return results from successful query
        assert len(results) == 1
        assert results[0]["href"] == "https://example.com"
    
    @patch('garuda_intel.search.seed_discovery.DDGS')
    def test_missing_href_key(self, mock_ddgs_class):
        """Test handling of results without href key."""
        # Setup mock
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = Mock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = Mock(return_value=False)
        mock_ddgs_class.return_value = mock_ddgs
        
        # Some results without href
        mock_ddgs.text.return_value = [
            {"href": "https://example.com"},
            {"title": "No URL"},  # Missing href
            {"href": "https://test.com"}
        ]
        
        results = collect_candidates_simple(["test query"], limit=5)
        
        # Should skip results without href
        assert len(results) == 2
        assert results[0]["href"] == "https://example.com"
        assert results[1]["href"] == "https://test.com"
    
    @patch('garuda_intel.search.seed_discovery.DDGS')
    def test_none_and_invalid_results(self, mock_ddgs_class):
        """Test handling of None and invalid result types."""
        # Setup mock
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = Mock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = Mock(return_value=False)
        mock_ddgs_class.return_value = mock_ddgs
        
        # Invalid result types
        mock_ddgs.text.return_value = [
            {"href": "https://example.com"},
            None,  # Invalid
            123,   # Invalid
            [],    # Invalid
            {"href": "https://test.com"}
        ]
        
        results = collect_candidates_simple(["test query"], limit=5)
        
        # Should skip invalid types
        assert len(results) == 2
        assert results[0]["href"] == "https://example.com"
        assert results[1]["href"] == "https://test.com"
    
    @patch('garuda_intel.search.seed_discovery.DDGS')
    def test_multiple_queries(self, mock_ddgs_class):
        """Test processing multiple queries."""
        # Setup mock
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = Mock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = Mock(return_value=False)
        mock_ddgs_class.return_value = mock_ddgs
        
        # Different results for different queries
        mock_ddgs.text.side_effect = [
            [{"href": "https://query1-result.com"}],
            [{"href": "https://query2-result.com"}]
        ]
        
        results = collect_candidates_simple(["query1", "query2"], limit=5)
        
        assert len(results) == 2
        assert results[0]["href"] == "https://query1-result.com"
        assert results[1]["href"] == "https://query2-result.com"
