"""
Tests for the dynamic task planner engine.

Validates:
- Plan creation with tool sequence
- Step execution dispatch
- Memory store / get operations
- Plan evaluation logic
- Pattern storage and matching
- Response backward compatibility
- Configuration defaults
- Cycle and step limits
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from garuda_intel.config import Settings
from garuda_intel.services.task_planner import TaskPlanner, TOOL_NAMES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_planner(**overrides):
    """Create a TaskPlanner with mocked dependencies."""
    store = MagicMock()
    store.search_intel.return_value = []
    # Mock Session as context manager
    session_mock = MagicMock()
    session_mock.__enter__ = Mock(return_value=session_mock)
    session_mock.__exit__ = Mock(return_value=False)
    store.Session.return_value = session_mock

    llm = MagicMock()
    llm.model = "test-model"
    llm.ollama_url = "http://localhost:11434/api/generate"
    llm.embed_text.return_value = [0.1] * 384
    llm.text_processor = MagicMock()
    llm.text_processor.safe_json_loads = lambda raw, fallback: _safe_json(raw, fallback)
    llm.generate_seed_queries.return_value = ["test query"]

    vector_store = MagicMock()
    vector_store.search.return_value = []

    settings = Settings()
    defaults = {
        "store": store,
        "llm": llm,
        "vector_store": vector_store,
        "settings": settings,
    }
    defaults.update(overrides)
    return TaskPlanner(**defaults)


def _safe_json(raw, fallback):
    try:
        parsed = json.loads(raw)
        return parsed
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestPlannerConfig:
    """Test configuration defaults for the task planner."""

    def test_default_max_plan_changes_per_cycle(self):
        settings = Settings()
        assert settings.chat_max_plan_changes_per_cycle == 15

    def test_default_max_cycles(self):
        settings = Settings()
        assert settings.chat_max_cycles == 2

    def test_default_max_total_steps(self):
        settings = Settings()
        assert settings.chat_max_total_steps == 100

    def test_default_pattern_reuse_threshold(self):
        settings = Settings()
        assert settings.chat_pattern_reuse_threshold == 0.75

    @patch.dict("os.environ", {
        "GARUDA_CHAT_MAX_PLAN_CHANGES_PER_CYCLE": "20",
        "GARUDA_CHAT_MAX_CYCLES": "3",
        "GARUDA_CHAT_MAX_TOTAL_STEPS": "200",
        "GARUDA_CHAT_PATTERN_REUSE_THRESHOLD": "0.8",
    })
    def test_settings_from_env(self):
        settings = Settings.from_env()
        assert settings.chat_max_plan_changes_per_cycle == 20
        assert settings.chat_max_cycles == 3
        assert settings.chat_max_total_steps == 200
        assert settings.chat_pattern_reuse_threshold == 0.8


# ---------------------------------------------------------------------------
# Tool name registry
# ---------------------------------------------------------------------------

class TestToolNames:
    """Validate tool name registry."""

    def test_all_tools_present(self):
        expected = {
            "search_local_data",
            "crawl_external_data",
            "reflect_findings",
            "store_memory_data",
            "get_memory_data",
            "search_memory",
            "create_plan",
            "store_step_to_plan",
            "eval_step_from_plan",
            "evaluate_plan",
        }
        assert set(TOOL_NAMES) == expected


# ---------------------------------------------------------------------------
# Memory tool tests
# ---------------------------------------------------------------------------

class TestMemoryTools:
    """Test store_memory_data and get_memory_data."""

    def test_store_and_get(self):
        memory = {}
        TaskPlanner._tool_store_memory(memory, "key1", "value1")
        assert memory["key1"] == "value1"

        result = TaskPlanner._tool_get_memory(memory, "key1")
        assert result == "value1"

    def test_get_full_memory(self):
        memory = {"a": 1, "b": 2}
        result = TaskPlanner._tool_get_memory(memory)
        assert result == {"a": 1, "b": 2}

    def test_get_missing_key(self):
        memory = {"a": 1}
        result = TaskPlanner._tool_get_memory(memory, "nonexistent")
        assert result is None

    def test_overwrite_key(self):
        memory = {"key": "old"}
        TaskPlanner._tool_store_memory(memory, "key", "new")
        assert memory["key"] == "new"


# ---------------------------------------------------------------------------
# Plan step helpers
# ---------------------------------------------------------------------------

class TestPlanStepHelpers:
    """Test plan step utility methods."""

    def test_has_pending_steps_true(self):
        plan = [
            {"tool": "search_local_data", "status": "completed"},
            {"tool": "reflect_findings", "status": "pending"},
        ]
        assert TaskPlanner._has_pending_steps(plan) is True

    def test_has_pending_steps_false(self):
        plan = [
            {"tool": "search_local_data", "status": "completed"},
            {"tool": "reflect_findings", "status": "completed"},
        ]
        assert TaskPlanner._has_pending_steps(plan) is False

    def test_next_pending_step(self):
        plan = [
            {"tool": "search_local_data", "status": "completed"},
            {"tool": "reflect_findings", "status": "pending"},
            {"tool": "crawl_external_data", "status": "pending"},
        ]
        nxt = TaskPlanner._next_pending_step(plan)
        assert nxt["tool"] == "reflect_findings"

    def test_next_pending_step_none(self):
        plan = [{"tool": "x", "status": "completed"}]
        assert TaskPlanner._next_pending_step(plan) is None

    def test_invalidate_remaining(self):
        plan = [
            {"tool": "a", "status": "completed"},
            {"tool": "b", "status": "pending"},
            {"tool": "c", "status": "pending"},
        ]
        TaskPlanner._invalidate_remaining(plan)
        assert plan[0]["status"] == "completed"
        assert plan[1]["status"] == "skipped"
        assert plan[2]["status"] == "skipped"


# ---------------------------------------------------------------------------
# Step evaluation
# ---------------------------------------------------------------------------

class TestStepEvaluation:
    """Test eval_step_from_plan logic."""

    def test_failed_step_returns_false(self):
        planner = _make_planner()
        result = planner._tool_eval_step(
            {"status": "failed", "tool_name": "search_local_data"},
            "question", {},
        )
        assert result is False

    def test_search_with_results_returns_true(self):
        planner = _make_planner()
        result = planner._tool_eval_step(
            {"status": "completed", "tool_name": "search_local_data", "output": {"count": 3}},
            "question", {},
        )
        assert result is True

    def test_search_with_zero_results_returns_false(self):
        planner = _make_planner()
        result = planner._tool_eval_step(
            {"status": "completed", "tool_name": "search_local_data", "output": {"count": 0}},
            "question", {},
        )
        assert result is False

    def test_crawl_with_error_returns_false(self):
        planner = _make_planner()
        result = planner._tool_eval_step(
            {"status": "completed", "tool_name": "crawl_external_data", "output": {"error": "timeout"}},
            "question", {},
        )
        assert result is False

    def test_crawl_success_returns_true(self):
        planner = _make_planner()
        result = planner._tool_eval_step(
            {"status": "completed", "tool_name": "crawl_external_data", "output": {"urls_crawled": ["x"]}},
            "question", {},
        )
        assert result is True

    def test_reflect_with_dict_output_returns_true(self):
        planner = _make_planner()
        result = planner._tool_eval_step(
            {"status": "completed", "tool_name": "reflect_findings", "output": {"sufficient": True}},
            "question", {},
        )
        assert result is True


# ---------------------------------------------------------------------------
# Response backward compatibility
# ---------------------------------------------------------------------------

class TestResponseFormat:
    """Test that the planner produces backward-compatible response dicts."""

    def test_response_has_required_keys(self):
        planner = _make_planner()
        resp = planner._build_response(
            question="test",
            entity="TestEntity",
            answer="The answer is 42",
            context=[{"source": "rag", "score": 0.9, "snippet": "text"}],
            sources=["https://example.com"],
            plan_steps_log=[
                {"tool_name": "search_local_data", "status": "completed", "input": {"query": "test"}},
            ],
            memory={"search_results": []},
            total_plan_changes=2,
            total_steps=3,
            cycle_count=1,
            plan_id="test-plan-id",
        )

        # All legacy keys must be present
        for key in [
            "answer", "context", "entity", "online_search_triggered",
            "retry_attempted", "paraphrased_queries", "live_urls",
            "crawl_reason", "rag_hits_count", "graph_hits_count",
            "sql_hits_count", "search_cycles_completed", "max_search_cycles",
            "current_step", "final_step",
        ]:
            assert key in resp, f"Missing legacy key: {key}"

        # New planner keys
        assert "plan_id" in resp
        assert "total_plan_changes" in resp
        assert "total_steps_executed" in resp
        assert "plan_steps" in resp
        assert "memory_keys" in resp
        assert "sources" in resp

    def test_online_triggered_detection(self):
        planner = _make_planner()
        resp = planner._build_response(
            question="test", entity="", answer="a", context=[], sources=[],
            plan_steps_log=[
                {"tool_name": "crawl_external_data", "status": "completed",
                 "output": {"urls_crawled": ["http://x"]}, "input": {}},
            ],
            memory={}, total_plan_changes=1, total_steps=1, cycle_count=1,
            plan_id="x",
        )
        assert resp["online_search_triggered"] is True
        assert resp["live_urls"] == ["http://x"]


# ---------------------------------------------------------------------------
# Search local tool
# ---------------------------------------------------------------------------

class TestSearchLocalTool:
    """Test _tool_search_local."""

    def test_returns_empty_when_no_data(self):
        planner = _make_planner()
        result = planner._tool_search_local("test query", 6, "")
        assert isinstance(result, dict)
        assert "hits" in result
        assert "count" in result

    def test_deduplicates_by_url(self):
        planner = _make_planner()
        # Simulate vector results with duplicates
        mock_result = MagicMock()
        mock_result.score = 0.8
        mock_result.payload = {"url": "https://example.com/a", "text": "hit1", "kind": "page", "entity": "E"}
        mock_result2 = MagicMock()
        mock_result2.score = 0.9
        mock_result2.payload = {"url": "https://example.com/a", "text": "hit2", "kind": "page", "entity": "E"}

        planner.vector_store.search.return_value = [mock_result, mock_result2]
        result = planner._tool_search_local("test", 6, "")
        # Should keep only the higher-scored version
        urls = [h["url"] for h in result["hits"] if h.get("url")]
        assert urls.count("https://example.com/a") <= 1


# ---------------------------------------------------------------------------
# Safe JSON helpers
# ---------------------------------------------------------------------------

class TestSafeHelpers:
    """Test serialisation safety utilities."""

    def test_safe_json_passthrough(self):
        assert TaskPlanner._safe_json({"key": "val"}) == {"key": "val"}

    def test_safe_json_none(self):
        assert TaskPlanner._safe_json(None) is None

    def test_safe_memory_filters_bad(self):
        class FailingRepr:
            def __repr__(self):
                raise ValueError("cannot repr")
        mem = {"ok": [1, 2], "bad": FailingRepr()}
        safe = TaskPlanner._safe_memory(mem)
        assert "ok" in safe
        # The bad value should be converted to some string representation
        assert "bad" in safe


# ---------------------------------------------------------------------------
# Full run integration (mocked LLM)
# ---------------------------------------------------------------------------

class TestPlannerRun:
    """Test the full planner.run() flow with mocked LLM."""

    def _mock_llm_response(self, response_text):
        """Create a mock requests.post response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": response_text}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    @patch("garuda_intel.services.task_planner.requests.post")
    def test_run_returns_valid_response(self, mock_post):
        """Test that run() returns a valid response dict."""
        # Plan creation response
        plan_json = json.dumps([
            {"tool": "search_local_data", "input": {"query": "CEO of Microsoft"}, "description": "Search local data"},
            {"tool": "reflect_findings", "input": {"data_key": "search_results"}, "description": "Reflect on findings"},
        ])
        # Reflection response
        reflect_json = json.dumps({"sufficient": True, "summary": "Found data", "missing": [], "next_action": "none"})
        # Plan evaluation response
        eval_json = json.dumps({"done": True, "answer": "Satya Nadella is the CEO of Microsoft."})

        mock_post.side_effect = [
            self._mock_llm_response(plan_json),      # create_plan
            self._mock_llm_response(reflect_json),    # reflect_findings
            self._mock_llm_response(eval_json),       # evaluate_plan
            self._mock_llm_response('"Find leadership of an organization"'),  # generalize_task
        ]

        planner = _make_planner()
        result = planner.run("Who is the CEO of Microsoft?")

        assert "answer" in result
        assert "context" in result
        assert "plan_steps" in result
        assert result["total_steps_executed"] >= 1

    @patch("garuda_intel.services.task_planner.requests.post")
    def test_run_respects_step_limit(self, mock_post):
        """Test that total step limit is respected."""
        # Always return a plan with pending steps that never finish
        plan_json = json.dumps([
            {"tool": "search_local_data", "input": {"query": "test"}, "description": "Search"},
        ])
        eval_json = json.dumps({"done": False, "reason": "need more data"})
        summary_json = "Could not find sufficient data."

        mock_post.return_value = self._mock_llm_response(plan_json)

        planner = _make_planner()
        planner.max_total_steps = 3
        planner.max_plan_changes_per_cycle = 5
        planner.max_cycles = 1

        # Mock eval to always say "not done"
        with patch.object(planner, '_tool_evaluate_plan', return_value=(False, None)):
            with patch.object(planner, '_tool_eval_step', return_value=True):
                result = planner.run("test question")

        assert result["total_steps_executed"] <= 3


# ---------------------------------------------------------------------------
# Model import tests
# ---------------------------------------------------------------------------

class TestModels:
    """Test that new DB models are properly defined."""

    def test_chat_plan_import(self):
        from garuda_intel.database.models import ChatPlan
        assert ChatPlan.__tablename__ == "chat_plans"

    def test_chat_plan_step_import(self):
        from garuda_intel.database.models import ChatPlanStep
        assert ChatPlanStep.__tablename__ == "chat_plan_steps"

    def test_step_pattern_import(self):
        from garuda_intel.database.models import StepPattern
        assert StepPattern.__tablename__ == "step_patterns"

    def test_chat_plan_has_steps_relationship(self):
        from garuda_intel.database.models import ChatPlan
        assert hasattr(ChatPlan, "steps")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
