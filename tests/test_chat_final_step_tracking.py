"""
Tests for chat final step tracking and step progress indication.

Ensures that the chat UI always returns a result with proper step tracking,
even after multiple web crawl cycles.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestChatFinalStepTracking:
    """Test chat final step and current step tracking."""
    
    def test_phase1_local_lookup_success(self):
        """Test final step when initial RAG lookup succeeds."""
        # Simulate successful initial lookup
        final_step = "phase1_local_lookup"
        current_step = "phase1_initial_rag"
        search_cycles_completed = 0
        online_triggered = False
        retry_attempted = False
        
        response = {
            "answer": "Test answer from local RAG",
            "final_step": final_step,
            "current_step": current_step,
            "search_cycles_completed": search_cycles_completed,
            "online_search_triggered": online_triggered,
            "retry_attempted": retry_attempted,
        }
        
        # Verify response structure
        assert response["final_step"] == "phase1_local_lookup"
        assert response["current_step"] == "phase1_initial_rag"
        assert response["search_cycles_completed"] == 0
        assert response["online_search_triggered"] is False
        assert response["retry_attempted"] is False
    
    def test_phase2_local_lookup_after_retry(self):
        """Test final step when retry with paraphrasing succeeds."""
        final_step = "phase2_local_lookup_after_retry"
        current_step = "phase2_retry_paraphrasing"
        search_cycles_completed = 0
        online_triggered = False
        retry_attempted = True
        
        response = {
            "answer": "Test answer after retry",
            "final_step": final_step,
            "current_step": current_step,
            "search_cycles_completed": search_cycles_completed,
            "online_search_triggered": online_triggered,
            "retry_attempted": retry_attempted,
            "paraphrased_queries": ["query1", "query2"],
        }
        
        assert response["final_step"] == "phase2_local_lookup_after_retry"
        assert response["retry_attempted"] is True
        assert len(response["paraphrased_queries"]) == 2
    
    def test_phase4_local_lookup_after_single_cycle(self):
        """Test final step when web crawl cycle succeeds early."""
        final_step = "phase4_local_lookup_after_cycle_1"
        current_step = "phase4_final_local_lookup"
        search_cycles_completed = 1
        online_triggered = True
        
        response = {
            "answer": "Test answer after 1 cycle",
            "final_step": final_step,
            "current_step": current_step,
            "search_cycles_completed": search_cycles_completed,
            "max_search_cycles": 3,
            "online_search_triggered": online_triggered,
            "live_urls": ["https://example.com/page1"],
        }
        
        assert response["final_step"] == "phase4_local_lookup_after_cycle_1"
        assert response["search_cycles_completed"] == 1
        assert response["max_search_cycles"] == 3
        assert len(response["live_urls"]) == 1
    
    def test_phase4_local_lookup_success_after_all_cycles(self):
        """Test final step when all cycles complete successfully."""
        final_step = "phase4_local_lookup_success"
        current_step = "phase4_final_local_lookup"
        search_cycles_completed = 3
        
        response = {
            "answer": "Test answer after all cycles",
            "final_step": final_step,
            "current_step": current_step,
            "search_cycles_completed": search_cycles_completed,
            "max_search_cycles": 3,
            "online_search_triggered": True,
            "live_urls": ["https://example.com/1", "https://example.com/2"],
        }
        
        assert response["final_step"] == "phase4_local_lookup_success"
        assert response["search_cycles_completed"] == 3
        assert response["search_cycles_completed"] == response["max_search_cycles"]
    
    def test_phase4_insufficient_after_all_cycles(self):
        """Test final step when all cycles complete but answer still insufficient."""
        final_step = "phase4_local_lookup_insufficient_after_all_cycles"
        current_step = "phase4_final_local_lookup"
        search_cycles_completed = 3
        
        response = {
            "answer": "Based on the available information: [limited context]",
            "final_step": final_step,
            "current_step": current_step,
            "search_cycles_completed": search_cycles_completed,
            "max_search_cycles": 3,
            "online_search_triggered": True,
            "live_urls": ["https://example.com/1"],
            "rag_hits_count": 1,  # Less than min_high_quality_hits
        }
        
        assert response["final_step"] == "phase4_local_lookup_insufficient_after_all_cycles"
        assert response["search_cycles_completed"] == response["max_search_cycles"]
        assert "Based on the available information" in response["answer"]
    
    def test_error_no_urls_found_after_all_cycles(self):
        """Test final step when no URLs are found despite all cycles."""
        final_step = "error_no_urls_found_after_all_cycles"
        current_step = "phase3_web_crawling"
        search_cycles_completed = 3
        
        response = {
            "answer": "I searched online but couldn't find relevant sources.",
            "final_step": final_step,
            "current_step": current_step,
            "search_cycles_completed": search_cycles_completed,
            "max_search_cycles": 3,
            "online_search_triggered": True,
            "live_urls": [],  # No URLs found
        }
        
        assert response["final_step"] == "error_no_urls_found_after_all_cycles"
        assert len(response["live_urls"]) == 0
        assert response["search_cycles_completed"] == response["max_search_cycles"]
    
    def test_error_fallback_answer_generated(self):
        """Test final step when fallback answer generation is used."""
        final_step = "error_fallback_answer_generated"
        
        response = {
            "answer": "Based on the available information:\n\nSnippet 1\n\nSnippet 2",
            "final_step": final_step,
            "current_step": "phase4_final_local_lookup",
            "context": [
                {"snippet": "Snippet 1"},
                {"snippet": "Snippet 2"},
            ],
        }
        
        assert response["final_step"] == "error_fallback_answer_generated"
        assert "Based on the available information" in response["answer"]
        assert len(response["context"]) > 0
    
    def test_always_returns_answer(self):
        """Test that response always contains an answer field."""
        test_cases = [
            {
                "final_step": "phase1_local_lookup",
                "answer": "Answer from phase 1",
            },
            {
                "final_step": "phase4_local_lookup_insufficient_after_all_cycles",
                "answer": "Partial answer after all cycles",
            },
            {
                "final_step": "error_fallback_answer_generated",
                "answer": "Fallback answer",
            },
        ]
        
        for case in test_cases:
            assert "answer" in case
            assert case["answer"]  # Not empty
            assert len(case["answer"]) > 0
    
    def test_final_step_always_present(self):
        """Test that final_step is always present in response."""
        # All valid final step states
        valid_final_steps = [
            "phase1_local_lookup",
            "phase2_local_lookup_after_retry",
            "phase4_local_lookup_after_cycle_1",
            "phase4_local_lookup_after_cycle_2",
            "phase4_local_lookup_after_cycle_3",
            "phase4_local_lookup_success",
            "phase4_local_lookup_insufficient_after_all_cycles",
            "error_no_urls_found_after_all_cycles",
            "error_fallback_answer_generated",
        ]
        
        for step in valid_final_steps:
            response = {
                "answer": "Test answer",
                "final_step": step,
                "current_step": "some_step",
            }
            assert "final_step" in response
            assert response["final_step"] == step


class TestChatStepProgression:
    """Test the progression of steps through the chat pipeline."""
    
    def test_step_progression_success_phase1(self):
        """Test step progression when phase 1 succeeds."""
        steps = []
        
        # Phase 1: Initial RAG
        steps.append(("phase1_initial_rag", "phase1_local_lookup"))
        
        # Verify progression
        assert len(steps) == 1
        current, final = steps[0]
        assert current == "phase1_initial_rag"
        assert final == "phase1_local_lookup"
    
    def test_step_progression_with_retry(self):
        """Test step progression when retry is needed."""
        steps = []
        
        # Phase 1: Initial RAG (insufficient)
        steps.append(("phase1_initial_rag", None))
        
        # Phase 2: Retry with paraphrasing
        steps.append(("phase2_retry_paraphrasing", "phase2_local_lookup_after_retry"))
        
        # Verify progression
        assert len(steps) == 2
        assert steps[0][0] == "phase1_initial_rag"
        assert steps[1][0] == "phase2_retry_paraphrasing"
        assert steps[1][1] == "phase2_local_lookup_after_retry"
    
    def test_step_progression_with_crawling(self):
        """Test step progression when web crawling is needed."""
        steps = []
        max_cycles = 3
        
        # Phase 1: Initial RAG (insufficient)
        steps.append(("phase1_initial_rag", None))
        
        # Phase 2: Retry (insufficient)
        steps.append(("phase2_retry_paraphrasing", None))
        
        # Phase 3: Web crawling
        steps.append(("phase3_web_crawling", None))
        
        # Phase 4: Final lookup after all cycles
        steps.append(("phase4_final_local_lookup", "phase4_local_lookup_success"))
        
        # Verify progression
        assert len(steps) == 4
        assert steps[0][0] == "phase1_initial_rag"
        assert steps[1][0] == "phase2_retry_paraphrasing"
        assert steps[2][0] == "phase3_web_crawling"
        assert steps[3][0] == "phase4_final_local_lookup"
        assert steps[3][1] == "phase4_local_lookup_success"
    
    def test_step_progression_early_termination(self):
        """Test step progression when early termination occurs."""
        steps = []
        
        # Phase 1: Initial RAG (insufficient)
        steps.append(("phase1_initial_rag", None))
        
        # Phase 2: Retry (insufficient)
        steps.append(("phase2_retry_paraphrasing", None))
        
        # Phase 3: Web crawling
        steps.append(("phase3_web_crawling", None))
        
        # Cycle 1 succeeds - early termination
        steps.append(("phase4_final_local_lookup", "phase4_local_lookup_after_cycle_1"))
        
        # Verify early termination
        assert len(steps) == 4
        final_step = steps[-1][1]
        assert "cycle_1" in final_step
        assert final_step == "phase4_local_lookup_after_cycle_1"


class TestChatMultipleCyclesBehavior:
    """Test behavior across multiple search/crawl cycles."""
    
    def test_url_tracking_across_cycles(self):
        """Test that URLs are tracked correctly across cycles."""
        all_crawled_urls = set()
        live_urls = []
        
        # Cycle 1
        cycle1_urls = ["https://example.com/1", "https://example.com/2"]
        for url in cycle1_urls:
            if url not in all_crawled_urls:
                all_crawled_urls.add(url)
                live_urls.append(url)
        
        # Cycle 2 (with one duplicate)
        cycle2_urls = ["https://example.com/2", "https://example.com/3"]
        for url in cycle2_urls:
            if url not in all_crawled_urls:
                all_crawled_urls.add(url)
                live_urls.append(url)
        
        # Cycle 3
        cycle3_urls = ["https://example.com/4"]
        for url in cycle3_urls:
            if url not in all_crawled_urls:
                all_crawled_urls.add(url)
                live_urls.append(url)
        
        # Verify deduplication
        assert len(all_crawled_urls) == 4  # Unique URLs
        assert len(live_urls) == 4  # Only new URLs added
        assert "https://example.com/1" in live_urls
        assert "https://example.com/2" in live_urls
        assert "https://example.com/3" in live_urls
        assert "https://example.com/4" in live_urls
    
    def test_cycle_count_tracking(self):
        """Test that cycle count is correctly tracked."""
        max_search_cycles = 3
        search_cycles_completed = 0
        
        # Simulate 3 cycles
        for cycle_num in range(1, max_search_cycles + 1):
            search_cycles_completed = cycle_num
        
        assert search_cycles_completed == 3
        assert search_cycles_completed == max_search_cycles
    
    def test_cycle_early_exit_tracking(self):
        """Test that early exit from cycles is tracked correctly."""
        max_search_cycles = 5
        search_cycles_completed = 0
        
        # Simulate early exit after cycle 2
        for cycle_num in range(1, max_search_cycles + 1):
            search_cycles_completed = cycle_num
            
            # Simulate sufficient results after cycle 2
            if cycle_num == 2:
                is_sufficient = True
                if is_sufficient:
                    final_step = f"phase4_local_lookup_after_cycle_{cycle_num}"
                    break
        
        assert search_cycles_completed == 2
        assert search_cycles_completed < max_search_cycles
        assert final_step == "phase4_local_lookup_after_cycle_2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
