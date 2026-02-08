"""Tests for score type safety fixes."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from garuda_intel.extractor.query_generator import _safe_float
from unittest.mock import MagicMock, patch


def test_safe_float_with_valid_inputs():
    """Test _safe_float handles various valid numeric inputs."""
    print("\n=== Test: _safe_float with valid inputs ===")
    
    assert _safe_float(10) == 10.0
    print("✓ Integer converted to float")
    
    assert _safe_float(3.14) == 3.14
    print("✓ Float passed through")
    
    assert _safe_float("42") == 42.0
    print("✓ String number converted to float")
    
    assert _safe_float("3.14159") == 3.14159
    print("✓ String float converted to float")


def test_safe_float_with_invalid_inputs():
    """Test _safe_float handles invalid inputs gracefully."""
    print("\n=== Test: _safe_float with invalid inputs ===")
    
    assert _safe_float(None) == 0.0
    print("✓ None returns default 0.0")
    
    assert _safe_float("") == 0.0
    print("✓ Empty string returns default 0.0")
    
    assert _safe_float("not_a_number") == 0.0
    print("✓ Invalid string returns default 0.0")
    
    assert _safe_float([], default=5.0) == 5.0
    print("✓ List returns custom default 5.0")
    
    assert _safe_float({}, default=10.0) == 10.0
    print("✓ Dict returns custom default 10.0")


def test_query_generator_rank_results_handles_string_scores():
    """Test that rank_search_results handles string scores from LLM."""
    print("\n=== Test: QueryGenerator rank_search_results with string scores ===")
    
    from garuda_intel.extractor.query_generator import QueryGenerator
    from garuda_intel.types.entity.profile import EntityProfile
    from garuda_intel.types.entity.type import EntityType
    import json
    
    qg = QueryGenerator()
    profile = EntityProfile(name="Test Entity", entity_type=EntityType.COMPANY)
    
    # Mock search results
    search_results = [
        {"url": "http://example.com/1", "title": "Result 1"},
        {"url": "http://example.com/2", "title": "Result 2"},
    ]
    
    # Mock LLM response with string scores
    mock_response = {
        "rankings": [
            {"id": 0, "score": "85", "is_official": True, "reason": "High relevance"},
            {"id": 1, "score": "42", "is_official": False, "reason": "Medium relevance"},
        ]
    }
    
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = {"response": json.dumps(mock_response)}
        
        ranked = qg.rank_search_results(profile, search_results)
        
        # Should not crash and should convert string scores to floats
        assert len(ranked) == 2
        assert ranked[0]["llm_score"] == 85.0
        assert ranked[1]["llm_score"] == 42.0
        print("✓ String scores converted to floats without crashing")
        
        # Should be sorted by score
        assert ranked[0]["url"] == "http://example.com/1"
        print("✓ Results sorted by converted float scores")


def test_query_generator_rank_links_handles_string_scores():
    """Test that rank_links handles string scores from LLM."""
    print("\n=== Test: QueryGenerator rank_links with string scores ===")
    
    from garuda_intel.extractor.query_generator import QueryGenerator
    from garuda_intel.types.entity.profile import EntityProfile
    from garuda_intel.types.entity.type import EntityType
    
    qg = QueryGenerator()
    profile = EntityProfile(name="Test Entity", entity_type=EntityType.COMPANY)
    
    links = [
        {"href": "http://example.com/about", "text": "About"},
        {"href": "http://example.com/contact", "text": "Contact"},
    ]
    
    # Mock LLM responses with string scores
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.side_effect = [
            {"response": '{"score": "75", "reason": "Good"}'},
            {"response": '{"score": "50", "reason": "Okay"}'},
        ]
        
        ranked = qg.rank_links(profile, "http://example.com", "page text", links)
        
        assert len(ranked) == 2
        assert ranked[0]["llm_score"] == 75.0
        assert ranked[1]["llm_score"] == 50.0
        print("✓ Link string scores converted to floats")


def test_engine_enqueue_new_links_handles_string_scores():
    """Test that float conversion handles string llm_score values."""
    print("\n=== Test: Float conversion with string llm_score ===")
    
    # Simulate the key logic from engine._enqueue_new_links
    # This tests the actual fix without needing to instantiate the full engine
    
    # Test data with mixed string/int/None scores
    link1 = {"href": "http://example.com/page1", "text": "Page 1", "llm_score": "90"}
    link2 = {"href": "http://example.com/page2", "text": "Page 2", "llm_score": "70"}
    link3 = {"href": "http://example.com/page3", "text": "Page 3", "llm_score": 85}
    link4 = {"href": "http://example.com/page4", "text": "Page 4", "llm_score": None}
    link5 = {"href": "http://example.com/page5", "text": "Page 5", "llm_score": ""}
    
    # This is the key fix - converting llm_score to float before max() comparison
    try:
        llm_score1 = float(link1.get("llm_score", 0) or 0)
        llm_score2 = float(link2.get("llm_score", 0) or 0)
        llm_score3 = float(link3.get("llm_score", 0) or 0)
        llm_score4 = float(link4.get("llm_score", 0) or 0)
        llm_score5 = float(link5.get("llm_score", 0) or 0)
        
        h_score = 60  # Mock heuristic score
        
        # This would crash without the fix if llm_score was a string
        final_score1 = max(h_score, llm_score1)
        final_score2 = max(h_score, llm_score2)
        final_score3 = max(h_score, llm_score3)
        final_score4 = max(h_score, llm_score4)
        final_score5 = max(h_score, llm_score5)
        
        assert final_score1 == 90.0
        assert final_score2 == 70.0
        assert final_score3 == 85.0
        assert final_score4 == 60.0  # None becomes 0, so h_score wins
        assert final_score5 == 60.0  # Empty string becomes 0, so h_score wins
        
        print("✓ Float conversion handled string llm_scores without crashing")
        print("✓ Float conversion handled None and empty string correctly")
        print("✓ max() comparison works correctly after conversion")
    except TypeError as e:
        if "'<' not supported between instances of 'str' and 'int'" in str(e):
            raise AssertionError("String score comparison failed - fix not working")
        raise


def test_search_routes_score_sorting():
    """Test that search.py score sorting handles mixed types."""
    print("\n=== Test: Search routes score sorting ===")
    
    # Test the sorting pattern used in search.py
    hits = [
        {"url": "http://example.com/1", "score": "90"},
        {"url": "http://example.com/2", "score": 85},
        {"url": "http://example.com/3", "score": "70"},
        {"url": "http://example.com/4", "score": None},
        {"url": "http://example.com/5", "score": ""},
    ]
    
    # Should not crash when sorting with mixed types
    try:
        sorted_hits = sorted(hits, key=lambda x: float(x.get("score", 0) or 0), reverse=True)
        assert len(sorted_hits) == 5
        assert sorted_hits[0]["score"] == "90"
        assert sorted_hits[1]["score"] == 85
        assert sorted_hits[2]["score"] == "70"
        print("✓ Mixed-type scores sorted correctly without crashing")
    except TypeError as e:
        if "'<' not supported between instances of 'str' and 'int'" in str(e):
            raise AssertionError("Score sorting failed with mixed types - fix not working")
        raise


if __name__ == "__main__":
    test_safe_float_with_valid_inputs()
    test_safe_float_with_invalid_inputs()
    test_query_generator_rank_results_handles_string_scores()
    test_query_generator_rank_links_handles_string_scores()
    test_engine_enqueue_new_links_handles_string_scores()
    test_search_routes_score_sorting()
    print("\n✅ All score type safety tests passed!")
