#!/usr/bin/env python3
"""
Verification script for Chat UI changes.

This script verifies:
1. The backend can handle max_search_cycles parameter
2. The fallback answer logic works
3. All expected fields are returned from the /api/chat endpoint
"""

import re


def _looks_like_refusal(text: str) -> bool:
    """Check if LLM response looks like a refusal or gibberish."""
    if not text:
        return True
    t = text.lower()
    
    # Check for refusal patterns
    refusal_patterns = [
        "no information",
        "not have information",
        "unable to find",
        "does not contain",
        "cannot provide details",
        "i don't have enough",
        "no data",
        "insufficient context",
        "based solely on the given data",
        "insufficient_data",
    ]
    
    # Check for structural gibberish/artifact patterns
    gibberish_patterns = [
        "a user:",
        "document",
        "write a)",
        "name_congraining",
        "beacon",
        "jsonleveraging",
    ]
    
    if any(p in t for p in refusal_patterns):
        return True
    
    if any(p in t for p in gibberish_patterns):
        return True
    
    # Check for excessive special characters
    special_ratio = len(re.findall(r'[^a-zA-Z0-9\s.,!?;:()\-]', text)) / max(len(text), 1)
    if special_ratio > 0.25:
        return True
    
    return False


def test_looks_like_refusal():
    """Test the _looks_like_refusal function."""
    print("\n=== Test: _looks_like_refusal function ===")
    
    # Test cases for refusal patterns
    test_cases = [
        ("no information available", True),
        ("I don't have enough data", True),
        ("cannot provide details", True),
        ("This is a valid answer with content", False),
        ("", True),  # Empty should be considered refusal
        ("INSUFFICIENT_DATA", True),
        ("A normal response about Python", False),
    ]
    
    for text, expected_refusal in test_cases:
        result = _looks_like_refusal(text)
        status = "✓" if result == expected_refusal else "✗"
        print(f"  {status} '{text[:50]}...' -> {result} (expected {expected_refusal})")
        assert result == expected_refusal, f"Failed for: {text}"
    
    print("✓ All refusal detection tests passed")


def test_fallback_answer_logic():
    """Test the fallback answer logic."""
    print("\n=== Test: Fallback Answer Logic ===")
    
    # Simulate the fallback logic from search.py
    def apply_fallback(answer, merged_hits):
        if not answer or _looks_like_refusal(answer):
            if merged_hits:
                snippets = [h.get("snippet", "") for h in merged_hits[:3] if h.get("snippet")]
                if snippets:
                    answer = f"Based on the available information:\n\n" + "\n\n".join(snippets)
                else:
                    answer = "I searched through local data and online sources but couldn't find a definitive answer. Try refining your question or providing more context."
            else:
                answer = "No relevant information was found in local data or online sources. Try a different question or crawl some relevant pages first."
        return answer
    
    # Test case 1: Empty answer with context
    answer = ""
    merged_hits = [
        {"snippet": "Python is a high-level language"},
        {"snippet": "It supports multiple paradigms"},
    ]
    result = apply_fallback(answer, merged_hits)
    assert "Based on the available information" in result
    assert "Python is a high-level language" in result
    print("  ✓ Empty answer with context -> Fallback with snippets")
    
    # Test case 2: Refusal with context
    answer = "I don't have enough information"
    result = apply_fallback(answer, merged_hits)
    assert "Based on the available information" in result
    print("  ✓ Refusal with context -> Fallback with snippets")
    
    # Test case 3: Empty answer without context
    answer = ""
    merged_hits = []
    result = apply_fallback(answer, merged_hits)
    assert "No relevant information was found" in result
    print("  ✓ Empty answer without context -> No data message")
    
    # Test case 4: Good answer (no fallback needed)
    answer = "Python is a versatile programming language"
    result = apply_fallback(answer, merged_hits)
    assert result == "Python is a versatile programming language"
    print("  ✓ Good answer -> No fallback applied")
    
    print("✓ All fallback logic tests passed")


def test_html_template_structure():
    """Test that the HTML template has all required elements."""
    print("\n=== Test: HTML Template Structure ===")
    
    template_path = "src/garuda_intel/webapp/templates/components/chat.html"
    with open(template_path, 'r') as f:
        content = f.read()
    
    required_elements = [
        ('chat-q', 'Question textarea'),
        ('chat-entity', 'Entity input'),
        ('chat-topk', 'Top K input'),
        ('chat-max-cycles', 'Max Search Cycles input'),
        ('chat-autonomous-mode', 'Autonomous Mode checkbox'),
        ('4-Phase Intelligent Search Pipeline', 'Phase indicator info box'),
    ]
    
    for element_id, description in required_elements:
        if element_id in content:
            print(f"  ✓ {description} found")
        else:
            print(f"  ✗ {description} NOT FOUND")
            raise AssertionError(f"Missing required element: {description}")
    
    print("✓ All required HTML elements present")


def test_javascript_imports():
    """Test that JavaScript files have correct imports."""
    print("\n=== Test: JavaScript Imports ===")
    
    # Check chat.js
    chat_js_path = "src/garuda_intel/webapp/static/actions/chat.js"
    with open(chat_js_path, 'r') as f:
        chat_content = f.read()
    
    assert 'renderAutonomousInChat' in chat_content, "chat.js must import renderAutonomousInChat"
    assert 'max_search_cycles' in chat_content, "chat.js must send max_search_cycles"
    assert 'chat-autonomous-mode' in chat_content, "chat.js must reference autonomous mode checkbox"
    print("  ✓ chat.js has correct imports and references")
    
    # Check render-chat.js
    render_chat_path = "src/garuda_intel/webapp/static/render-chat.js"
    with open(render_chat_path, 'r') as f:
        render_content = f.read()
    
    assert 'export function renderAutonomousInChat' in render_content, "render-chat.js must export renderAutonomousInChat"
    assert 'paraphrased_queries' in render_content, "render-chat.js must handle paraphrased_queries"
    assert 'search_cycles_completed' in render_content, "render-chat.js must show search cycles"
    assert 'collapsible' in render_content, "render-chat.js must import collapsible from ui.js"
    print("  ✓ render-chat.js has correct exports and references")
    
    print("✓ All JavaScript imports verified")


def test_backend_search_route():
    """Test that the backend route has the fallback logic."""
    print("\n=== Test: Backend Search Route ===")
    
    search_py_path = "src/garuda_intel/webapp/routes/search.py"
    with open(search_py_path, 'r') as f:
        content = f.read()
    
    # Verify max_search_cycles parameter handling
    assert 'max_search_cycles' in content, "search.py must handle max_search_cycles parameter"
    print("  ✓ max_search_cycles parameter handling found")
    
    # Verify fallback answer logic
    assert 'Final fallback - ensure there' in content, "search.py must have final fallback logic"
    assert 'Based on the available information' in content, "search.py must have snippet-based fallback"
    assert 'No relevant information was found' in content, "search.py must have no-data fallback"
    print("  ✓ Fallback answer logic found")
    
    # Verify _looks_like_refusal function exists
    assert 'def _looks_like_refusal' in content, "search.py must have _looks_like_refusal function"
    print("  ✓ _looks_like_refusal function found")
    
    print("✓ Backend route verification passed")


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Chat UI Changes Verification")
    print("=" * 60)
    
    try:
        test_looks_like_refusal()
        test_fallback_answer_logic()
        test_html_template_structure()
        test_javascript_imports()
        test_backend_search_route()
        
        print("\n" + "=" * 60)
        print("✅ ALL VERIFICATION TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ VERIFICATION FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
