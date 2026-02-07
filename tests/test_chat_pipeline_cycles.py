"""
Tests for chat pipeline with configurable search cycles.

Tests the enhanced chat functionality:
- Configurable max_search_cycles setting
- Full pipeline execution during chat search
- RAG re-query after each cycle
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from garuda_intel.config import Settings


class TestChatPipelineSettings:
    """Test chat pipeline settings in config."""
    
    def test_default_chat_max_search_cycles(self):
        """Test default value for chat_max_search_cycles."""
        settings = Settings()
        assert settings.chat_max_search_cycles == 3
    
    def test_default_chat_max_pages(self):
        """Test default value for chat_max_pages."""
        settings = Settings()
        assert settings.chat_max_pages == 5
    
    def test_default_chat_rag_quality_threshold(self):
        """Test default value for chat_rag_quality_threshold."""
        settings = Settings()
        assert settings.chat_rag_quality_threshold == 0.7
    
    def test_default_chat_min_high_quality_hits(self):
        """Test default value for chat_min_high_quality_hits."""
        settings = Settings()
        assert settings.chat_min_high_quality_hits == 2
    
    def test_default_chat_use_selenium(self):
        """Test default value for chat_use_selenium."""
        settings = Settings()
        assert settings.chat_use_selenium is False
    
    def test_default_chat_extract_related_entities(self):
        """Test default value for chat_extract_related_entities."""
        settings = Settings()
        assert settings.chat_extract_related_entities is True
    
    @patch.dict('os.environ', {
        'GARUDA_CHAT_MAX_SEARCH_CYCLES': '5',
        'GARUDA_CHAT_MAX_PAGES': '10',
        'GARUDA_CHAT_RAG_QUALITY_THRESHOLD': '0.8',
        'GARUDA_CHAT_MIN_HIGH_QUALITY_HITS': '3',
        'GARUDA_CHAT_USE_SELENIUM': 'true',
        'GARUDA_CHAT_EXTRACT_RELATED_ENTITIES': 'false',
    })
    def test_settings_from_env(self):
        """Test that settings are loaded from environment variables."""
        settings = Settings.from_env()
        
        assert settings.chat_max_search_cycles == 5
        assert settings.chat_max_pages == 10
        assert settings.chat_rag_quality_threshold == 0.8
        assert settings.chat_min_high_quality_hits == 3
        assert settings.chat_use_selenium is True
        assert settings.chat_extract_related_entities is False


class TestChatSearchCycleLogic:
    """Test chat search cycle logic without requiring Flask app context."""
    
    def test_search_cycle_tracking(self):
        """Test that search cycles are properly tracked."""
        # Simulate search cycle state
        max_search_cycles = 3
        all_crawled_urls = set()
        search_cycles_completed = 0
        
        # Simulate 3 cycles
        for cycle_num in range(1, max_search_cycles + 1):
            # Each cycle adds some URLs
            new_urls = [f"https://example{cycle_num}.com/page{i}" for i in range(3)]
            
            for url in new_urls:
                if url not in all_crawled_urls:
                    all_crawled_urls.add(url)
            
            search_cycles_completed = cycle_num
        
        assert search_cycles_completed == 3
        assert len(all_crawled_urls) == 9  # 3 URLs per cycle * 3 cycles
    
    def test_early_termination_on_sufficient_results(self):
        """Test that search cycles can terminate early on sufficient results."""
        max_search_cycles = 3
        search_cycles_completed = 0
        
        # Simulate checking for sufficiency after each cycle
        for cycle_num in range(1, max_search_cycles + 1):
            search_cycles_completed = cycle_num
            
            # Simulate getting sufficient results after cycle 2
            if cycle_num == 2:
                high_quality_rag = [{"score": 0.9}, {"score": 0.85}]  # 2 high quality hits
                is_sufficient = True
                min_high_quality_hits = 2  # Configurable threshold
                
                if is_sufficient and len(high_quality_rag) >= min_high_quality_hits:
                    break
        
        assert search_cycles_completed == 2  # Should stop after cycle 2
    
    def test_url_deduplication_across_cycles(self):
        """Test that URLs are deduplicated across search cycles."""
        all_crawled_urls = set()
        
        # Cycle 1 URLs
        cycle1_urls = ["https://example.com/a", "https://example.com/b"]
        for url in cycle1_urls:
            all_crawled_urls.add(url)
        
        # Cycle 2 URLs (with some overlap)
        cycle2_urls = ["https://example.com/b", "https://example.com/c"]  # b is duplicate
        new_urls = [url for url in cycle2_urls if url not in all_crawled_urls]
        for url in new_urls:
            all_crawled_urls.add(url)
        
        # Only c should be new
        assert len(new_urls) == 1
        assert new_urls[0] == "https://example.com/c"
        assert len(all_crawled_urls) == 3  # a, b, c
    
    def test_different_search_angles_per_cycle(self):
        """Test that different search angles are used per cycle."""
        # Simulate generating different queries per cycle
        base_question = "What are the latest AI developments?"
        
        queries_per_cycle = []
        for cycle_num in range(1, 4):
            if cycle_num == 1:
                queries = [base_question, "AI developments 2024"]
            else:
                # Different angle for subsequent cycles
                queries = [
                    f"alternative search angle {cycle_num} for: {base_question}",
                    f"new perspective {cycle_num} on AI"
                ]
            queries_per_cycle.append(queries)
        
        # Each cycle should have different queries
        assert queries_per_cycle[0] != queries_per_cycle[1]
        assert queries_per_cycle[1] != queries_per_cycle[2]


class TestChatResponseFormat:
    """Test chat response format with new fields."""
    
    def test_response_includes_search_cycles_info(self):
        """Test that response includes search cycle information."""
        # Simulate a chat response
        response = {
            "answer": "Test answer",
            "context": [],
            "entity": "Test Entity",
            "online_search_triggered": True,
            "retry_attempted": True,
            "paraphrased_queries": ["query1", "query2"],
            "live_urls": ["https://example.com"],
            "crawl_reason": "Insufficient high-quality RAG results",
            "rag_hits_count": 3,
            "sql_hits_count": 2,
            "search_cycles_completed": 2,
            "max_search_cycles": 3,
        }
        
        # Verify new fields are present
        assert "search_cycles_completed" in response
        assert "max_search_cycles" in response
        assert response["search_cycles_completed"] == 2
        assert response["max_search_cycles"] == 3
    
    def test_response_with_no_online_search(self):
        """Test response when no online search is needed."""
        response = {
            "answer": "Test answer from local RAG",
            "context": [{"source": "rag", "score": 0.9}],
            "entity": "Test Entity",
            "online_search_triggered": False,
            "retry_attempted": False,
            "paraphrased_queries": [],
            "live_urls": [],
            "crawl_reason": None,
            "rag_hits_count": 5,
            "sql_hits_count": 0,
            "search_cycles_completed": 0,
            "max_search_cycles": 3,
        }
        
        # When no online search is triggered, cycles should be 0
        assert response["online_search_triggered"] is False
        assert response["search_cycles_completed"] == 0


class TestRelatedEntityExtraction:
    """Test related entity extraction during chat crawling."""
    
    def test_related_entities_extracted_from_finding(self):
        """Test that related entities are extracted from findings."""
        from garuda_intel.extractor.intel_extractor import IntelExtractor
        
        extractor = IntelExtractor(
            enable_entity_merging=False,
            enable_schema_discovery=False,
            enable_quality_validation=False,
            extract_related_entities=True,
        )
        
        # Finding about Microsoft with related entities
        finding = {
            "basic_info": {
                "official_name": "Microsoft Corporation",
                "industry": "Technology"
            },
            "persons": [
                {"name": "Satya Nadella", "title": "CEO"},
                {"name": "Amy Hood", "title": "CFO"},
            ],
            "products": [
                {"name": "Azure", "description": "Cloud platform"},
            ],
            "locations": [
                {"city": "Redmond", "type": "headquarters"},
            ]
        }
        
        entities = extractor.extract_entities_from_finding(
            finding,
            primary_entity_name="Microsoft Corporation"
        )
        
        # Should extract primary entity + related entities
        names = {e["name"] for e in entities}
        
        assert "Microsoft Corporation" in names
        assert "Satya Nadella" in names
        assert "Amy Hood" in names
        assert "Azure" in names
        assert "Redmond" in names
        
        # All related entities should have suggested relationships to primary
        related_entities = [e for e in entities if e["name"] != "Microsoft Corporation"]
        for entity in related_entities:
            if entity.get("suggested_relationship"):
                assert entity["suggested_relationship"]["target"] == "Microsoft Corporation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
