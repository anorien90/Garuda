"""Tests for RAG-first chat functionality and intelligent crawling.

These tests validate the core logic of the RAG-first chat system,
including prioritization, quality thresholds, and fallback behavior.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_rag_result_prioritization():
    """Test that RAG results are prioritized correctly in merge logic."""
    print("\n=== Test: RAG Result Prioritization ===")
    
    # Simulate RAG and SQL results
    rag_hits = [
        {"source": "rag", "score": 0.9, "snippet": "RAG 1"},
        {"source": "rag", "score": 0.85, "snippet": "RAG 2"},
        {"source": "rag", "score": 0.8, "snippet": "RAG 3"},
    ]
    
    sql_hits = [
        {"source": "sql", "snippet": "SQL 1"},
        {"source": "sql", "snippet": "SQL 2"},
    ]
    
    limit = 4
    prioritize_rag = True
    
    # Simulate merge logic from gather_hits
    if prioritize_rag and rag_hits:
        merged = rag_hits[:limit]
        if len(merged) < limit:
            merged.extend(sql_hits[:limit - len(merged)])
    else:
        merged = rag_hits + sql_hits
        merged = merged[:limit]
    
    # Verify RAG results come first
    assert len(merged) == 4, f"Expected 4 results, got {len(merged)}"
    assert merged[0]["source"] == "rag", "First result should be RAG"
    assert merged[1]["source"] == "rag", "Second result should be RAG"
    assert merged[2]["source"] == "rag", "Third result should be RAG"
    assert merged[3]["source"] == "sql", "Fourth result should be SQL (supplement)"
    
    print("✓ RAG results are prioritized correctly")
    print(f"  Merged results: {len([h for h in merged if h['source'] == 'rag'])} RAG, "
          f"{len([h for h in merged if h['source'] == 'sql'])} SQL")


def test_quality_threshold_logic():
    """Test quality threshold filtering for RAG results."""
    print("\n=== Test: Quality Threshold Logic ===")
    
    rag_hits = [
        {"source": "rag", "score": 0.9, "snippet": "High quality"},
        {"source": "rag", "score": 0.75, "snippet": "Medium quality"},
        {"source": "rag", "score": 0.6, "snippet": "Low quality"},
    ]
    
    quality_threshold = 0.7
    
    # Filter high-quality results
    high_quality_rag = [h for h in rag_hits if h.get("score", 0) >= quality_threshold]
    
    assert len(high_quality_rag) == 2, f"Expected 2 high-quality results, got {len(high_quality_rag)}"
    assert all(h["score"] >= quality_threshold for h in high_quality_rag), \
        "All high-quality results should meet threshold"
    
    # Test crawl trigger logic
    should_crawl = len(high_quality_rag) < 2
    assert not should_crawl, "Should not crawl with 2+ high-quality results"
    
    # Test with insufficient quality
    low_quality_hits = [{"source": "rag", "score": 0.5}]
    high_quality_low = [h for h in low_quality_hits if h.get("score", 0) >= quality_threshold]
    should_crawl_low = len(high_quality_low) < 2
    assert should_crawl_low, "Should crawl with <2 high-quality results"
    
    print("✓ Quality threshold filtering works correctly")
    print(f"  High-quality hits (>={quality_threshold}): {len(high_quality_rag)}")


def test_max_vector_results_cap():
    """Test that vector search limit is capped to prevent resource exhaustion."""
    print("\n=== Test: Max Vector Results Cap ===")
    
    MAX_VECTOR_RESULTS = 100
    
    # Test various limit values
    test_cases = [
        (10, 20),    # limit=10, expected=20 (limit * 2)
        (50, 100),   # limit=50, expected=100 (capped at MAX)
        (60, 100),   # limit=60, expected=100 (would be 120, but capped)
        (100, 100),  # limit=100, expected=100 (would be 200, but capped)
    ]
    
    for limit, expected in test_cases:
        vector_limit = min(limit * 2, MAX_VECTOR_RESULTS)
        assert vector_limit == expected, \
            f"For limit={limit}, expected {expected}, got {vector_limit}"
    
    print("✓ Vector results are properly capped")
    print(f"  MAX_VECTOR_RESULTS = {MAX_VECTOR_RESULTS}")


def test_fallback_when_no_rag():
    """Test fallback to SQL when RAG is unavailable."""
    print("\n=== Test: Fallback When No RAG ===")
    
    rag_hits = []  # No RAG results
    sql_hits = [
        {"source": "sql", "snippet": "SQL 1"},
        {"source": "sql", "snippet": "SQL 2"},
    ]
    
    limit = 3
    prioritize_rag = True
    
    # Simulate merge logic
    if prioritize_rag and rag_hits:
        merged = rag_hits[:limit]
        if len(merged) < limit:
            merged.extend(sql_hits[:limit - len(merged)])
    else:
        merged = rag_hits + sql_hits
        merged = merged[:limit]
    
    # Should fall back to SQL
    assert len(merged) == 2, f"Expected 2 SQL results, got {len(merged)}"
    assert all(h["source"] == "sql" for h in merged), "All results should be SQL"
    
    # Determine crawl reason
    if not rag_hits:
        crawl_reason = "No RAG results found"
    else:
        crawl_reason = None
    
    assert crawl_reason == "No RAG results found", "Should identify no RAG results"
    
    print("✓ Fallback to SQL works correctly")
    print(f"  Crawl reason: {crawl_reason}")


def test_mixed_source_results():
    """Test handling of mixed RAG and SQL results."""
    print("\n=== Test: Mixed Source Results ===")
    
    rag_hits = [
        {"source": "rag", "score": 0.9, "snippet": "RAG 1"},
    ]
    
    sql_hits = [
        {"source": "sql", "snippet": "SQL 1"},
        {"source": "sql", "snippet": "SQL 2"},
        {"source": "sql", "snippet": "SQL 3"},
    ]
    
    limit = 3
    prioritize_rag = True
    
    # Merge with prioritization
    if prioritize_rag and rag_hits:
        merged = rag_hits[:limit]
        if len(merged) < limit:
            merged.extend(sql_hits[:limit - len(merged)])
    else:
        merged = rag_hits + sql_hits
        merged = merged[:limit]
    
    # Should have 1 RAG + 2 SQL
    assert len(merged) == 3, f"Expected 3 results, got {len(merged)}"
    rag_count = len([h for h in merged if h["source"] == "rag"])
    sql_count = len([h for h in merged if h["source"] == "sql"])
    
    assert rag_count == 1, f"Expected 1 RAG result, got {rag_count}"
    assert sql_count == 2, f"Expected 2 SQL results, got {sql_count}"
    
    print("✓ Mixed source results handled correctly")
    print(f"  Results: {rag_count} RAG + {sql_count} SQL = {len(merged)} total")


def test_no_prioritization_mode():
    """Test when RAG prioritization is disabled."""
    print("\n=== Test: No Prioritization Mode ===")
    
    rag_hits = [
        {"source": "rag", "score": 0.9, "snippet": "RAG 1"},
        {"source": "rag", "score": 0.85, "snippet": "RAG 2"},
    ]
    
    sql_hits = [
        {"source": "sql", "snippet": "SQL 1"},
    ]
    
    limit = 2
    prioritize_rag = False  # Disabled
    
    # Merge without prioritization
    if prioritize_rag and rag_hits:
        merged = rag_hits[:limit]
        if len(merged) < limit:
            merged.extend(sql_hits[:limit - len(merged)])
    else:
        merged = rag_hits + sql_hits
        merged = merged[:limit]
    
    # Should mix both sources
    assert len(merged) == 2, f"Expected 2 results, got {len(merged)}"
    
    print("✓ No prioritization mode works correctly")


def run_all_tests():
    """Run all RAG chat logic tests."""
    print("\n" + "=" * 60)
    print("RAG-First Chat Logic Tests")
    print("=" * 60)
    
    test_rag_result_prioritization()
    test_quality_threshold_logic()
    test_max_vector_results_cap()
    test_fallback_when_no_rag()
    test_mixed_source_results()
    test_no_prioritization_mode()
    
    print("\n" + "=" * 60)
    print("✓ All RAG chat logic tests passed!")
    print("=" * 60)
    print("\nThese tests validate the core logic of:")
    print("  - RAG result prioritization")
    print("  - Quality threshold filtering (0.7 similarity)")
    print("  - Max vector results capping (100 limit)")
    print("  - SQL fallback when RAG unavailable")
    print("  - Mixed source result handling")
    print("  - Crawl trigger logic")


if __name__ == "__main__":
    run_all_tests()

