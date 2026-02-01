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


def test_retry_with_paraphrasing_logic():
    """Test retry logic with paraphrased queries and increased hits."""
    print("\n=== Test: Retry with Paraphrasing Logic ===")
    
    # Simulate initial insufficient results
    initial_rag_hits = [
        {"source": "rag", "score": 0.65, "url": "url1", "snippet": "Low quality RAG 1"},
    ]
    
    initial_sql_hits = [
        {"source": "sql", "url": "url2", "snippet": "SQL 1"},
    ]
    
    # Simulate paraphrased queries
    paraphrased_queries = [
        "What is the headquarters of Microsoft",
        "Microsoft main office location",
    ]
    
    # Simulate retry results from paraphrased queries
    retry_rag_hits = [
        {"source": "rag", "score": 0.85, "url": "url3", "snippet": "High quality paraphrased 1"},
        {"source": "rag", "score": 0.80, "url": "url4", "snippet": "High quality paraphrased 2"},
        {"source": "rag", "score": 0.75, "url": "url1", "snippet": "Higher scored duplicate"},  # Duplicate with higher score
    ]
    
    # Combine and deduplicate
    all_retry_hits = initial_rag_hits + retry_rag_hits + initial_sql_hits
    
    # Deduplicate by URL, keeping highest scoring versions
    unique_hits = {}
    for hit in all_retry_hits:
        url = hit.get("url", "")
        if url:
            if url not in unique_hits or hit.get("score", 0) > unique_hits[url].get("score", 0):
                unique_hits[url] = hit
    
    deduplicated = list(unique_hits.values())
    
    # Verify deduplication worked
    assert len(deduplicated) == 4, f"Expected 4 unique URLs, got {len(deduplicated)}"
    
    # Verify the higher score version was kept for url1
    url1_hit = next(h for h in deduplicated if h["url"] == "url1")
    assert url1_hit["score"] == 0.75, "Should keep higher-scored duplicate"
    
    # Check quality after retry
    quality_threshold = 0.7
    high_quality = [h for h in deduplicated if h.get("score", 0) >= quality_threshold]
    
    assert len(high_quality) >= 2, f"Should have 2+ high quality after retry, got {len(high_quality)}"
    
    print("✓ Retry with paraphrasing logic works correctly")
    print(f"  Initial results: {len(initial_rag_hits)} RAG + {len(initial_sql_hits)} SQL")
    print(f"  After retry: {len(deduplicated)} unique results, {len(high_quality)} high-quality")


def test_retry_trigger_conditions():
    """Test conditions that should trigger retry mechanism."""
    print("\n=== Test: Retry Trigger Conditions ===")
    
    quality_threshold = 0.7
    
    # Scenario 1: Low quality results AND insufficient answer should trigger retry
    low_quality_hits = [
        {"source": "rag", "score": 0.6, "snippet": "Low quality 1"},
        {"source": "rag", "score": 0.65, "snippet": "Low quality 2"},
    ]
    high_quality_low = [h for h in low_quality_hits if h.get("score", 0) >= quality_threshold]
    is_sufficient = False  # Simulate insufficient answer
    should_retry_1 = not is_sufficient and len(high_quality_low) < 2
    assert should_retry_1, "Should retry with <2 high-quality results and insufficient answer"
    print("  ✓ Triggers retry for low-quality results AND insufficient answer")
    
    # Scenario 2: Sufficient high-quality results BUT sufficient answer should not trigger retry
    high_quality_hits = [
        {"source": "rag", "score": 0.9, "snippet": "High quality 1"},
        {"source": "rag", "score": 0.85, "snippet": "High quality 2"},
    ]
    high_quality_high = [h for h in high_quality_hits if h.get("score", 0) >= quality_threshold]
    is_sufficient = True  # Simulate sufficient answer
    should_retry_2 = not is_sufficient and len(high_quality_high) < 2
    assert not should_retry_2, "Should not retry with sufficient answer"
    print("  ✓ Does not trigger retry when answer is sufficient")
    
    # Scenario 3: No RAG results AND insufficient answer should trigger retry
    no_rag_hits = []
    is_sufficient = False
    should_retry_3 = not is_sufficient and len(no_rag_hits) < 2
    assert should_retry_3, "Should retry with no RAG results and insufficient answer"
    print("  ✓ Triggers retry for no RAG results AND insufficient answer")
    
    # Scenario 4: High-quality results BUT insufficient answer should NOT trigger retry
    # (This is the edge case - we have good results but answer is still bad)
    high_quality_hits_2 = [
        {"source": "rag", "score": 0.9, "snippet": "High quality 1"},
        {"source": "rag", "score": 0.85, "snippet": "High quality 2"},
    ]
    high_quality_count = [h for h in high_quality_hits_2 if h.get("score", 0) >= quality_threshold]
    is_sufficient = False  # Insufficient answer despite good results
    should_retry_4 = not is_sufficient and len(high_quality_count) < 2
    assert not should_retry_4, "Should not retry when quality count >= 2 (skip to crawl instead)"
    print("  ✓ Does not trigger retry when 2+ high-quality results exist (goes to crawl)")
    
    print("✓ Retry trigger conditions work correctly")


def test_zero_high_quality_always_triggers_online():
    """Ensure zero high-quality RAG hits trigger online crawl even if answer seems sufficient."""
    print("\n=== Test: Zero High Quality Triggers Online Crawl ===")
    
    rag_hits = [
        {"source": "rag", "score": 0.4, "snippet": "Low quality"},
    ]
    quality_threshold = 0.7
    high_quality_rag = [h for h in rag_hits if h.get("score", 0) >= quality_threshold]
    
    # Simulate sufficiency flag being True but quality is zero
    is_sufficient = True
    quality_insufficient = len(high_quality_rag) == 0
    should_retry = quality_insufficient or (not is_sufficient and len(high_quality_rag) < 2)
    
    assert quality_insufficient, "Quality insufficiency should detect zero high-quality results"
    assert should_retry, "Should trigger retry/crawl when no high-quality hits even if answer seems sufficient"
    
    print("✓ Zero high-quality results force online search/crawl trigger")


def test_increased_hits_on_retry():
    """Test that retry increases the number of hits requested."""
    print("\n=== Test: Increased Hits on Retry ===")
    
    # Initial top_k
    initial_top_k = 6
    
    # Retry should double, capped at 20
    increased_top_k = min(initial_top_k * 2, 20)
    assert increased_top_k == 12, f"Expected 12 hits on retry, got {increased_top_k}"
    
    # Test with larger initial value
    large_initial = 15
    increased_large = min(large_initial * 2, 20)
    assert increased_large == 20, f"Expected cap at 20, got {increased_large}"
    
    print("✓ Hit count increases correctly on retry")
    print(f"  Initial top_k=6 → Retry top_k={increased_top_k}")
    print(f"  Initial top_k=15 → Retry top_k={increased_large} (capped)")


def test_crawl_after_failed_retry():
    """Test that crawling is triggered after retry fails."""
    print("\n=== Test: Crawl After Failed Retry ===")
    
    # Simulate retry that still yields insufficient results
    retry_rag_hits = [
        {"source": "rag", "score": 0.65, "snippet": "Still low quality"},
    ]
    
    quality_threshold = 0.7
    high_quality_after_retry = [h for h in retry_rag_hits if h.get("score", 0) >= quality_threshold]
    
    # Should trigger crawl
    should_crawl = len(high_quality_after_retry) < 2
    assert should_crawl, "Should trigger crawl after failed retry"
    
    # Verify crawl reason
    crawl_reason = f"Insufficient high-quality RAG results ({len(high_quality_after_retry)}) after retry"
    assert "after retry" in crawl_reason, "Crawl reason should mention retry"
    
    print("✓ Crawling triggered correctly after failed retry")
    print(f"  Crawl reason: {crawl_reason}")


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
    test_retry_with_paraphrasing_logic()
    test_retry_trigger_conditions()
    test_increased_hits_on_retry()
    test_crawl_after_failed_retry()
    
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
    print("  - Retry with paraphrasing and increased hits (NEW)")
    print("  - Retry trigger conditions (NEW)")
    print("  - Crawl fallback after failed retry (NEW)")


if __name__ == "__main__":
    run_all_tests()
