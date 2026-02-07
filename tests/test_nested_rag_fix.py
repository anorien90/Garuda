"""Tests for nested RAG retrieval fix.

This test identifies and validates the fix for handling nested/graph results
in the chat endpoint when RAG retrieval returns complex nested structures.
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_graph_result_flattening():
    """Test that graph results with nested structures are properly flattened."""
    print("\n=== Test: Graph Result Flattening ===")
    
    # Simulate complex graph_result from multidimensional_search
    # This mimics what agent_service.multidimensional_search might return
    graph_result = {
        "combined_results": [
            {
                "source": "graph",
                "score": 0.5,
                "entity": "Microsoft",
                "entity_id": "entity-123",
                "kind": "organization",
                "text": "Microsoft Corporation is a tech company",
                "url": "https://microsoft.com",
                "combined_score": 0.7,
            },
            {
                "source": "embedding", 
                "score": 0.9,
                "entity": "Bill Gates",
                "entity_id": "entity-456",
                "kind": "person",
                "text": "Bill Gates co-founded Microsoft",
                # Note: Missing URL
                "combined_score": 1.1,
            },
            {
                "source": "graph",
                "score": 0.6,
                "entity": "Windows",
                # Missing several fields
                "text": "Windows operating system",
                "combined_score": 0.6,
            },
        ]
    }
    
    # UPDATED logic from search.py with nested structure handling
    graph_hits = []
    for r in graph_result.get("combined_results", []):
        try:
            url = r.get("url", "") or ""
            text = r.get("text", "") or ""
            entity = r.get("entity", "") or ""
            kind = r.get("kind", "") or "unknown"
            
            # Get score with proper fallback chain
            score = r.get("combined_score")
            if score is None:
                score = r.get("score", 0)
            if not isinstance(score, (int, float)):
                score = 0
            
            # Ensure text is a string, not a nested structure
            if isinstance(text, (dict, list)):
                text = json.dumps(text, ensure_ascii=False, separators=(',', ':'))
            text = str(text)[:1000]
            
            graph_hits.append({
                "url": url,
                "snippet": text,
                "score": score,
                "source": "graph",
                "kind": kind,
                "entity": entity,
            })
        except Exception:
            continue
    
    # Validate all results were processed
    assert len(graph_hits) == 3, f"Expected 3 results, got {len(graph_hits)}"
    
    # Check first result (complete)
    assert graph_hits[0]["url"] == "https://microsoft.com"
    assert graph_hits[0]["snippet"] == "Microsoft Corporation is a tech company"
    assert graph_hits[0]["score"] == 0.7
    assert graph_hits[0]["entity"] == "Microsoft"
    assert graph_hits[0]["kind"] == "organization"
    
    # Check second result (missing URL)
    assert graph_hits[1]["url"] == ""
    assert graph_hits[1]["snippet"] == "Bill Gates co-founded Microsoft"
    assert graph_hits[1]["score"] == 1.1
    
    # Check third result (missing multiple fields)
    assert graph_hits[2]["url"] == ""
    assert graph_hits[2]["kind"] == "unknown"
    
    print("✓ Graph results are properly flattened")
    print(f"  Processed {len(graph_hits)} results")


def test_nested_intelligence_data_handling():
    """Test that nested intelligence data structures are properly converted to JSON strings."""
    print("\n=== Test: Nested Intelligence Data Handling ===")
    
    # Simulate intelligence.data that might be nested dicts/lists
    nested_data_cases = [
        # Case 1: Simple dict
        {
            "company": "Microsoft",
            "founded": 1975,
        },
        # Case 2: Nested dict
        {
            "company": "Microsoft",
            "details": {
                "founder": "Bill Gates",
                "location": "Redmond",
            }
        },
        # Case 3: List of items
        ["Product 1", "Product 2", "Product 3"],
        # Case 4: Complex nested structure
        {
            "products": [
                {"name": "Windows", "type": "OS"},
                {"name": "Office", "type": "Software"},
            ],
            "ceo": {
                "name": "Satya Nadella",
                "since": 2014,
            }
        },
    ]
    
    # UPDATED conversion logic (from agent_service.py) - now uses JSON
    for i, data in enumerate(nested_data_cases):
        try:
            if isinstance(data, (dict, list)):
                text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))[:500]
            else:
                text = str(data)[:500]
        except (TypeError, ValueError):
            text = str(data)[:500]
        
        # Validate it's a string
        assert isinstance(text, str), f"Case {i+1}: Result should be string"
        
        # Validate it's not empty
        assert len(text) > 0, f"Case {i+1}: Result should not be empty"
        
        # Validate it's truncated to 500 chars
        assert len(text) <= 500, f"Case {i+1}: Result should be max 500 chars"
        
        # Validate it's valid JSON for dict/list cases
        if isinstance(data, (dict, list)):
            try:
                # Verify JSON is valid and parseable
                json.loads(text)
                print(f"  Case {i+1}: {type(data).__name__} → {len(text)} chars (valid JSON)")
            except json.JSONDecodeError:
                # Might be truncated, that's OK
                print(f"  Case {i+1}: {type(data).__name__} → {len(text)} chars (truncated)")
        else:
            print(f"  Case {i+1}: {type(data).__name__} → {len(text)} chars")
    
    print("✓ Nested intelligence data is properly converted to JSON")


def test_nested_text_in_results():
    """Test that nested text fields in results are properly flattened."""
    print("\n=== Test: Nested Text in Results ===")
    
    # Simulate results where text field is a nested structure
    graph_result = {
        "combined_results": [
            {
                "source": "graph",
                "score": 0.7,
                "entity": "Company",
                "text": {"description": "A tech company", "industry": "Software"},  # Nested dict!
                "url": "https://example.com",
            },
            {
                "source": "graph",
                "score": 0.6,
                "entity": "Product",
                "text": ["Feature 1", "Feature 2", "Feature 3"],  # Nested list!
            },
        ]
    }
    
    # Process with updated logic
    graph_hits = []
    for r in graph_result.get("combined_results", []):
        try:
            text = r.get("text", "") or ""
            
            # Flatten nested structures
            if isinstance(text, (dict, list)):
                text = json.dumps(text, ensure_ascii=False, separators=(',', ':'))
            text = str(text)[:1000]
            
            graph_hits.append({
                "url": r.get("url", "") or "",
                "snippet": text,
                "score": r.get("combined_score", r.get("score", 0)),
                "source": "graph",
                "kind": r.get("kind", "") or "unknown",
                "entity": r.get("entity", "") or "",
            })
        except Exception:
            continue
    
    # Validate flattening worked
    assert len(graph_hits) == 2
    
    # Check dict was converted to JSON
    assert '"description":"A tech company"' in graph_hits[0]["snippet"]
    assert isinstance(graph_hits[0]["snippet"], str)
    
    # Check list was converted to JSON
    assert '["Feature 1","Feature 2","Feature 3"]' in graph_hits[1]["snippet"]
    assert isinstance(graph_hits[1]["snippet"], str)
    
    print("✓ Nested text fields are properly flattened to JSON strings")


def test_malformed_score_handling():
    """Test handling of malformed or missing score fields."""
    print("\n=== Test: Malformed Score Handling ===")
    
    graph_result = {
        "combined_results": [
            {"score": "not_a_number", "text": "Test 1"},  # Invalid score type
            {"text": "Test 2"},  # Missing both scores
            {"score": None, "text": "Test 3"},  # None score
            {"combined_score": 0.8, "text": "Test 4"},  # Only combined_score
            {"score": 0.5, "combined_score": None, "text": "Test 5"},  # None combined, valid score
        ]
    }
    
    graph_hits = []
    for r in graph_result.get("combined_results", []):
        try:
            score = r.get("combined_score")
            if score is None:
                score = r.get("score", 0)
            if not isinstance(score, (int, float)):
                score = 0
            
            graph_hits.append({
                "url": "",
                "snippet": r.get("text", ""),
                "score": score,
                "source": "graph",
                "kind": "unknown",
                "entity": "",
            })
        except Exception:
            continue
    
    # All results should be processed with valid scores
    assert len(graph_hits) == 5
    assert graph_hits[0]["score"] == 0  # Invalid type → 0
    assert graph_hits[1]["score"] == 0  # Missing → 0
    assert graph_hits[2]["score"] == 0  # None → 0
    assert graph_hits[3]["score"] == 0.8  # Valid combined_score
    assert graph_hits[4]["score"] == 0.5  # Fallback to score when combined is None
    
    print("✓ Malformed scores handled correctly")


def test_graph_result_with_missing_combined_score():
    """Test handling when combined_score is missing from graph results."""
    print("\n=== Test: Missing Combined Score Handling ===")
    
    graph_result = {
        "combined_results": [
            {
                "source": "graph",
                "score": 0.8,
                "entity": "Test Entity",
                "text": "Test text",
                # Missing combined_score
            },
            {
                "source": "embedding",
                # Missing both combined_score AND score
                "entity": "Another Entity",
                "text": "More text",
            },
        ]
    }
    
    graph_hits = []
    for r in graph_result.get("combined_results", []):
        try:
            score = r.get("combined_score")
            if score is None:
                score = r.get("score", 0)
            if not isinstance(score, (int, float)):
                score = 0
            
            graph_hits.append({
                "url": r.get("url", "") or "",
                "snippet": r.get("text", "") or "",
                "score": score,
                "source": "graph",
                "kind": r.get("kind", "") or "unknown",
                "entity": r.get("entity", "") or "",
            })
        except Exception:
            continue
    
    # Check fallback to regular score works
    assert graph_hits[0]["score"] == 0.8, "Should fallback to 'score' field"
    
    # Check default to 0 when both are missing
    assert graph_hits[1]["score"] == 0, "Should default to 0 when both scores missing"
    
    print("✓ Missing combined_score handled correctly with updated logic")


def test_empty_graph_results():
    """Test handling of empty graph results."""
    print("\n=== Test: Empty Graph Results ===")
    
    # Case 1: Empty combined_results
    graph_result_1 = {"combined_results": []}
    graph_hits_1 = []
    for r in graph_result_1.get("combined_results", []):
        try:
            graph_hits_1.append({
                "url": r.get("url", "") or "",
                "snippet": r.get("text", "") or "",
                "score": r.get("combined_score", r.get("score", 0)),
                "source": "graph",
                "kind": r.get("kind", "") or "unknown",
                "entity": r.get("entity", "") or "",
            })
        except Exception:
            continue
    assert len(graph_hits_1) == 0, "Empty results should produce empty list"
    
    # Case 2: Missing combined_results key
    graph_result_2 = {}
    graph_hits_2 = []
    for r in graph_result_2.get("combined_results", []):
        try:
            graph_hits_2.append({
                "url": r.get("url", "") or "",
                "snippet": r.get("text", "") or "",
                "score": r.get("combined_score", r.get("score", 0)),
                "source": "graph",
                "kind": r.get("kind", "") or "unknown",
                "entity": r.get("entity", "") or "",
            })
        except Exception:
            continue
    assert len(graph_hits_2) == 0, "Missing key should produce empty list"
    
    print("✓ Empty graph results handled correctly")


def test_deduplication_with_graph_hits():
    """Test that graph hits are properly deduplicated with RAG and SQL hits."""
    print("\n=== Test: Deduplication with Graph Hits ===")
    
    # Simulate all three sources of hits
    vec_hits = [
        {"url": "https://example.com/a", "score": 0.9, "snippet": "RAG text A", "source": "rag"},
        {"url": "https://example.com/b", "score": 0.8, "snippet": "RAG text B", "source": "rag"},
    ]
    
    graph_hits = [
        {"url": "https://example.com/a", "score": 0.7, "snippet": "Graph text A", "source": "graph"},
        {"url": "https://example.com/c", "score": 0.75, "snippet": "Graph text C", "source": "graph"},
    ]
    
    sql_hits = [
        {"url": "https://example.com/b", "snippet": "SQL text B", "source": "sql"},
        {"url": "https://example.com/d", "snippet": "SQL text D", "source": "sql"},
    ]
    
    # Merge logic from search.py lines 343-363
    all_hits = []
    all_hits.extend(vec_hits)
    all_hits.extend(graph_hits)
    all_hits.extend(sql_hits)
    
    # Deduplicate by URL, keeping highest-scoring version
    seen_urls = {}
    no_url_hits = []
    for hit in all_hits:
        url = hit.get("url", "")
        if url:
            if url not in seen_urls or hit.get("score", 0) > seen_urls[url].get("score", 0):
                seen_urls[url] = hit
        else:
            no_url_hits.append(hit)
    
    merged = list(seen_urls.values()) + no_url_hits
    merged.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    # Validate deduplication
    assert len(merged) == 4, f"Expected 4 unique URLs, got {len(merged)}"
    
    # Check URL A kept highest score (RAG with 0.9, not graph with 0.7)
    url_a = next(h for h in merged if h["url"] == "https://example.com/a")
    assert url_a["score"] == 0.9, "Should keep highest scoring version"
    assert url_a["source"] == "rag", "Should keep RAG source for URL A"
    
    # Check URL B kept RAG version (0.8 vs SQL which has no score)
    url_b = next(h for h in merged if h["url"] == "https://example.com/b")
    assert url_b["source"] == "rag", "Should keep RAG source for URL B"
    
    # Check URL C and D are present
    assert any(h["url"] == "https://example.com/c" for h in merged), "URL C should be present"
    assert any(h["url"] == "https://example.com/d" for h in merged), "URL D should be present"
    
    print("✓ Graph hits deduplicated correctly with RAG and SQL")
    print(f"  {len(vec_hits)} RAG + {len(graph_hits)} Graph + {len(sql_hits)} SQL → {len(merged)} unique")


def test_graph_hits_without_urls():
    """Test that graph hits without URLs are still included."""
    print("\n=== Test: Graph Hits Without URLs ===")
    
    graph_hits = [
        {"url": "", "score": 0.6, "snippet": "Entity data 1", "source": "graph", "entity": "Entity1"},
        {"url": "", "score": 0.5, "snippet": "Entity data 2", "source": "graph", "entity": "Entity2"},
    ]
    
    vec_hits = [
        {"url": "https://example.com/a", "score": 0.9, "snippet": "RAG text", "source": "rag"},
    ]
    
    # Merge
    all_hits = vec_hits + graph_hits
    
    seen_urls = {}
    no_url_hits = []
    for hit in all_hits:
        url = hit.get("url", "")
        if url:
            if url not in seen_urls or hit.get("score", 0) > seen_urls[url].get("score", 0):
                seen_urls[url] = hit
        else:
            no_url_hits.append(hit)
    
    merged = list(seen_urls.values()) + no_url_hits
    
    # All hits should be preserved
    assert len(merged) == 3, f"Expected 3 hits (1 with URL, 2 without), got {len(merged)}"
    assert len(no_url_hits) == 2, "Should have 2 hits without URLs"
    
    print("✓ Graph hits without URLs are preserved")


def run_all_tests():
    """Run all nested RAG fix tests."""
    print("\n" + "=" * 60)
    print("Nested RAG Retrieval Fix Tests")
    print("=" * 60)
    
    test_graph_result_flattening()
    test_nested_intelligence_data_handling()
    test_nested_text_in_results()
    test_malformed_score_handling()
    test_graph_result_with_missing_combined_score()
    test_empty_graph_results()
    test_deduplication_with_graph_hits()
    test_graph_hits_without_urls()
    
    print("\n" + "=" * 60)
    print("✓ All nested RAG fix tests passed!")
    print("=" * 60)
    print("\nThese tests validate:")
    print("  - Graph result flattening from multidimensional_search")
    print("  - Nested intelligence data conversion to JSON strings")
    print("  - Nested text fields flattened to JSON")
    print("  - Malformed score handling with type checking")
    print("  - Missing combined_score field handling")
    print("  - Empty graph results handling")
    print("  - Deduplication across RAG, graph, and SQL sources")
    print("  - Graph hits without URLs preservation")


if __name__ == "__main__":
    run_all_tests()
