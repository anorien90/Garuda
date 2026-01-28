#!/usr/bin/env python3
"""
Demonstration script showing the seed URL collection fix.

This script demonstrates that the code now handles various response formats
from search providers without crashing with "'str' object has no attribute 'get'".
"""

import sys
import os
import logging
from unittest.mock import Mock, MagicMock, patch

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Add src to path for direct execution (relative to script location)
script_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(script_dir, 'src')
if os.path.exists(src_path):
    sys.path.insert(0, src_path)

from garuda_intel.services.adaptive_crawler import AdaptiveCrawlerService


def demo_with_dict_responses():
    """Demo with standard dict responses (expected format)."""
    print("\n" + "="*80)
    print("DEMO 1: Standard dict responses from search provider")
    print("="*80)
    
    # Mock dependencies
    store = Mock()
    llm = Mock()
    crawl_learner = Mock()
    
    # Mock store.Session() context manager
    session_mock = MagicMock()
    session_mock.__enter__ = Mock(return_value=session_mock)
    session_mock.__exit__ = Mock(return_value=False)
    store.Session = Mock(return_value=session_mock)
    
    crawl_learner.get_successful_patterns.return_value = []
    crawl_learner.get_learning_stats.return_value = {}
    
    service = AdaptiveCrawlerService(store, llm, crawl_learner)
    
    # Mock gap analyzer
    service.gap_analyzer.generate_crawl_plan = Mock(return_value={
        'mode': 'discovery',
        'strategy': 'comprehensive',
        'queries': ['"Microsoft Corporation" headquarters']
    })
    
    # Mock collect_candidates_simple to return dicts
    with patch('garuda_intel.search.collect_candidates_simple') as mock_collect:
        mock_collect.return_value = [
            {"href": "https://www.microsoft.com", "title": "Microsoft"},
            {"href": "https://en.wikipedia.org/wiki/Microsoft", "title": "Microsoft - Wikipedia"}
        ]
        
        result = service.intelligent_crawl("Microsoft Corporation", max_pages=5, max_depth=1)
    
    print(f"✓ Seed URLs collected: {len(result['seed_urls'])}")
    for url in result['seed_urls']:
        print(f"  - {url}")
    print(f"✓ Official domains: {result['official_domains']}")
    print("✓ No errors - dict responses handled correctly!")


def demo_with_string_responses():
    """Demo with string responses (defensive handling)."""
    print("\n" + "="*80)
    print("DEMO 2: String responses from search provider (old behavior)")
    print("="*80)
    
    # Mock dependencies
    store = Mock()
    llm = Mock()
    crawl_learner = Mock()
    
    session_mock = MagicMock()
    session_mock.__enter__ = Mock(return_value=session_mock)
    session_mock.__exit__ = Mock(return_value=False)
    store.Session = Mock(return_value=session_mock)
    
    crawl_learner.get_successful_patterns.return_value = []
    crawl_learner.get_learning_stats.return_value = {}
    
    service = AdaptiveCrawlerService(store, llm, crawl_learner)
    
    service.gap_analyzer.generate_crawl_plan = Mock(return_value={
        'mode': 'discovery',
        'strategy': 'comprehensive',
        'queries': ['"Microsoft Corporation" headquarters']
    })
    
    # Mock collect_candidates_simple to return strings (OLD PROBLEMATIC FORMAT)
    with patch('garuda_intel.search.collect_candidates_simple') as mock_collect:
        mock_collect.return_value = [
            "https://www.microsoft.com",
            "https://en.wikipedia.org/wiki/Microsoft"
        ]
        
        result = service.intelligent_crawl("Microsoft Corporation", max_pages=5, max_depth=1)
    
    print(f"✓ Seed URLs collected: {len(result['seed_urls'])}")
    for url in result['seed_urls']:
        print(f"  - {url}")
    print("✓ No errors - string responses handled correctly with defensive code!")


def demo_with_mixed_responses():
    """Demo with mix of dicts and strings."""
    print("\n" + "="*80)
    print("DEMO 3: Mixed dict and string responses")
    print("="*80)
    
    # Mock dependencies
    store = Mock()
    llm = Mock()
    crawl_learner = Mock()
    
    session_mock = MagicMock()
    session_mock.__enter__ = Mock(return_value=session_mock)
    session_mock.__exit__ = Mock(return_value=False)
    store.Session = Mock(return_value=session_mock)
    
    crawl_learner.get_successful_patterns.return_value = []
    crawl_learner.get_learning_stats.return_value = {}
    
    service = AdaptiveCrawlerService(store, llm, crawl_learner)
    
    service.gap_analyzer.generate_crawl_plan = Mock(return_value={
        'mode': 'discovery',
        'strategy': 'comprehensive',
        'queries': ['"Microsoft Corporation" headquarters']
    })
    
    # Mock with mixed formats
    with patch('garuda_intel.search.collect_candidates_simple') as mock_collect:
        mock_collect.return_value = [
            {"href": "https://www.microsoft.com", "title": "Microsoft"},
            "https://en.wikipedia.org/wiki/Microsoft",  # String
            {"href": "https://www.linkedin.com/company/microsoft"}  # Dict
        ]
        
        result = service.intelligent_crawl("Microsoft Corporation", max_pages=5, max_depth=1)
    
    print(f"✓ Seed URLs collected: {len(result['seed_urls'])}")
    for url in result['seed_urls']:
        print(f"  - {url}")
    print("✓ No errors - mixed format responses handled correctly!")


def demo_with_invalid_types():
    """Demo with invalid response types that should be skipped."""
    print("\n" + "="*80)
    print("DEMO 4: Invalid response types (None, numbers, lists)")
    print("="*80)
    
    # Mock dependencies
    store = Mock()
    llm = Mock()
    crawl_learner = Mock()
    
    session_mock = MagicMock()
    session_mock.__enter__ = Mock(return_value=session_mock)
    session_mock.__exit__ = Mock(return_value=False)
    store.Session = Mock(return_value=session_mock)
    
    crawl_learner.get_successful_patterns.return_value = []
    crawl_learner.get_learning_stats.return_value = {}
    
    service = AdaptiveCrawlerService(store, llm, crawl_learner)
    
    service.gap_analyzer.generate_crawl_plan = Mock(return_value={
        'mode': 'discovery',
        'strategy': 'comprehensive',
        'queries': ['"Microsoft Corporation" headquarters']
    })
    
    # Mock with invalid types that should be gracefully skipped
    with patch('garuda_intel.search.collect_candidates_simple') as mock_collect:
        mock_collect.return_value = [
            {"href": "https://www.microsoft.com"},
            None,  # Invalid - should skip
            123,   # Invalid - should skip
            [],    # Invalid - should skip
            "https://en.wikipedia.org/wiki/Microsoft"
        ]
        
        result = service.intelligent_crawl("Microsoft Corporation", max_pages=5, max_depth=1)
    
    print(f"✓ Seed URLs collected: {len(result['seed_urls'])} (invalid types skipped)")
    for url in result['seed_urls']:
        print(f"  - {url}")
    print("✓ No errors - invalid types skipped gracefully!")


def demo_provider_exception():
    """Demo with provider exception (e.g., 429 rate limit)."""
    print("\n" + "="*80)
    print("DEMO 5: Provider exception handling (e.g., 429 rate limit)")
    print("="*80)
    
    # Mock dependencies
    store = Mock()
    llm = Mock()
    crawl_learner = Mock()
    
    session_mock = MagicMock()
    session_mock.__enter__ = Mock(return_value=session_mock)
    session_mock.__exit__ = Mock(return_value=False)
    store.Session = Mock(return_value=session_mock)
    
    crawl_learner.get_successful_patterns.return_value = []
    crawl_learner.get_learning_stats.return_value = {}
    
    service = AdaptiveCrawlerService(store, llm, crawl_learner)
    
    service.gap_analyzer.generate_crawl_plan = Mock(return_value={
        'mode': 'discovery',
        'strategy': 'comprehensive',
        'queries': [
            '"Microsoft Corporation" headquarters',
            '"Microsoft Corporation" about'
        ]
    })
    
    # First query fails with exception, second succeeds
    with patch('garuda_intel.search.collect_candidates_simple') as mock_collect:
        mock_collect.side_effect = [
            Exception("Rate limited (429)"),
            [{"href": "https://www.microsoft.com"}]
        ]
        
        result = service.intelligent_crawl("Microsoft Corporation", max_pages=5, max_depth=1)
    
    print(f"✓ Seed URLs collected: {len(result['seed_urls'])} (despite first query failure)")
    for url in result['seed_urls']:
        print(f"  - {url}")
    print("✓ No errors - provider exceptions handled gracefully!")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("SEED URL COLLECTION FIX DEMONSTRATION")
    print("="*80)
    print("\nThis demonstrates that the fix prevents the error:")
    print("  'str' object has no attribute 'get'")
    print("\nThe code now handles:")
    print("  ✓ Dict responses (standard format)")
    print("  ✓ String responses (old problematic format)")
    print("  ✓ Mixed format responses")
    print("  ✓ Invalid response types")
    print("  ✓ Provider exceptions (429, etc.)")
    
    try:
        demo_with_dict_responses()
        demo_with_string_responses()
        demo_with_mixed_responses()
        demo_with_invalid_types()
        demo_provider_exception()
        
        print("\n" + "="*80)
        print("ALL DEMOS COMPLETED SUCCESSFULLY! ✓")
        print("="*80)
        print("\nThe seed URL collection is now robust and handles all response formats.")
        print("The intelligent crawl will no longer crash with 'str has no attribute get'.")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
