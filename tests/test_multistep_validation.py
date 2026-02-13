"""
Tests for multi-step task validation features.

Validates:
- Persistent memory (ChatMemoryEntry model + DB persist)
- Crawl disable gate (crawl_enabled flag)
- search_memory MCP tool
- Cancellation / interruption support
- INSUFFICIENT_DATA escalation in step evaluation
- Token budget management (truncation)
- Config new settings (chat_crawl_enabled, chat_max_prompt_tokens)
- Response includes memory_snapshot and crawl_enabled
- Reflect insufficient triggers re-plan
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
from garuda_intel.services.task_planner import (
    TaskPlanner,
    TOOL_NAMES,
    DEFAULT_MAX_PROMPT_TOKENS,
    DEFAULT_MAX_CONSECUTIVE_INSUFFICIENT,
    CHARS_PER_TOKEN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_planner(**overrides):
    """Create a TaskPlanner with mocked dependencies."""
    store = MagicMock()
    store.search_intel.return_value = []
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
        return json.loads(raw)
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestMultistepConfig:
    """Test new configuration defaults for multi-step validation."""

    def test_default_crawl_enabled(self):
        s = Settings()
        assert s.chat_crawl_enabled is True

    def test_default_max_prompt_tokens(self):
        s = Settings()
        assert s.chat_max_prompt_tokens == 13000

    @patch.dict("os.environ", {
        "GARUDA_CHAT_CRAWL_ENABLED": "false",
        "GARUDA_CHAT_MAX_PROMPT_TOKENS": "8000",
    })
    def test_config_from_env(self):
        s = Settings.from_env()
        assert s.chat_crawl_enabled is False
        assert s.chat_max_prompt_tokens == 8000


# ---------------------------------------------------------------------------
# Crawl disable gate
# ---------------------------------------------------------------------------

class TestCrawlDisableGate:
    """Test that crawl_enabled=False prevents external crawling."""

    def test_planner_respects_crawl_disabled(self):
        planner = _make_planner(crawl_enabled=False)
        assert planner.crawl_enabled is False

    def test_planner_crawl_enabled_default(self):
        planner = _make_planner()
        assert planner.crawl_enabled is True

    def test_fallback_plan_omits_crawl_when_disabled(self):
        planner = _make_planner(crawl_enabled=False)
        # Force fallback by making LLM request raise an exception
        with patch("garuda_intel.services.task_planner.requests.post", side_effect=Exception("timeout")):
            plan = planner._tool_create_plan("test question", "entity", {}, [])
            tool_names = [s["tool"] for s in plan]
            assert "crawl_external_data" not in tool_names
            assert "search_local_data" in tool_names
            assert "reflect_findings" in tool_names

    def test_fallback_plan_includes_crawl_when_enabled(self):
        planner = _make_planner(crawl_enabled=True)
        with patch("garuda_intel.services.task_planner.requests.post", side_effect=Exception("timeout")):
            plan = planner._tool_create_plan("test", "entity", {}, [])
            tool_names = [s["tool"] for s in plan]
            assert "crawl_external_data" in tool_names

    def test_execute_step_skips_crawl_when_disabled(self):
        planner = _make_planner(crawl_enabled=False)
        step = {"tool": "crawl_external_data", "input": {"query": "test"}, "status": "pending"}
        result = planner._execute_step(step, "test", "entity", {}, 6, str(uuid.uuid4()), 1)
        assert result["output"]["skipped"] is True
        assert "crawl_disabled" in (result.get("error") or "")

    def test_response_contains_crawl_enabled_flag(self):
        planner = _make_planner(crawl_enabled=False)
        resp = planner._build_response(
            question="test", entity="", answer="a", context=[], sources=[],
            plan_steps_log=[], memory={}, total_plan_changes=0,
            total_steps=0, cycle_count=1, plan_id="x",
        )
        assert resp["crawl_enabled"] is False


# ---------------------------------------------------------------------------
# search_memory MCP tool
# ---------------------------------------------------------------------------

class TestSearchMemoryTool:
    """Test the search_memory tool."""

    def test_search_finds_matching_key(self):
        memory = {"gpu_results": [{"name": "RTX 4090"}], "cpu_data": "Intel i9"}
        result = TaskPlanner._tool_search_memory(memory, "gpu")
        assert result["count"] == 1
        assert "gpu_results" in result["matches"]

    def test_search_finds_matching_value(self):
        memory = {"item1": "NVIDIA GeForce RTX", "item2": "AMD Radeon"}
        result = TaskPlanner._tool_search_memory(memory, "nvidia")
        assert result["count"] == 1
        assert "item1" in result["matches"]

    def test_search_returns_empty_on_no_match(self):
        memory = {"a": "hello", "b": "world"}
        result = TaskPlanner._tool_search_memory(memory, "nonexistent")
        assert result["count"] == 0
        assert result["matches"] == {}

    def test_search_case_insensitive(self):
        memory = {"Results": "Some Data"}
        result = TaskPlanner._tool_search_memory(memory, "results")
        assert result["count"] == 1

    def test_search_memory_in_execution(self):
        """Verify search_memory is dispatched in _execute_step."""
        planner = _make_planner()
        memory = {"gpu_list": ["RTX 4090", "RTX 4080"]}
        step = {
            "tool": "search_memory",
            "input": {"query": "gpu"},
            "status": "pending",
        }
        result = planner._execute_step(step, "test", "", memory, 6, str(uuid.uuid4()), 1)
        assert result["status"] == "completed"
        assert result["output"]["count"] == 1

    def test_search_memory_in_tool_names(self):
        assert "search_memory" in TOOL_NAMES


# ---------------------------------------------------------------------------
# INSUFFICIENT_DATA escalation
# ---------------------------------------------------------------------------

class TestInsufficientDataEscalation:
    """Test INSUFFICIENT_DATA triggers correct escalation."""

    def test_search_zero_hits_triggers_insufficient(self):
        planner = _make_planner()
        result = planner._tool_eval_step(
            {"status": "completed", "tool_name": "search_local_data", "output": {"count": 0}},
            "question", {},
        )
        assert result is False  # Should trigger INSUFFICIENT_DATA escalation

    def test_crawl_skipped_triggers_insufficient(self):
        planner = _make_planner()
        result = planner._tool_eval_step(
            {"status": "completed", "tool_name": "crawl_external_data",
             "output": {"skipped": True, "reason": "crawl_disabled"}},
            "question", {},
        )
        assert result is False

    def test_reflect_insufficient_triggers_escalation(self):
        """When reflect_findings says data is insufficient, step eval returns False."""
        planner = _make_planner()
        result = planner._tool_eval_step(
            {"status": "completed", "tool_name": "reflect_findings",
             "output": {"sufficient": False, "summary": "", "missing": ["more data"]}},
            "question", {},
        )
        assert result is False

    def test_reflect_sufficient_passes(self):
        planner = _make_planner()
        result = planner._tool_eval_step(
            {"status": "completed", "tool_name": "reflect_findings",
             "output": {"sufficient": True, "summary": "All data found"}},
            "question", {},
        )
        assert result is True


# ---------------------------------------------------------------------------
# Token budget / truncation
# ---------------------------------------------------------------------------

class TestTokenBudget:
    """Test prompt truncation for token budgets."""

    def test_truncate_short_text_unchanged(self):
        text = "Hello world"
        result = TaskPlanner._truncate_for_prompt(text, 1000)
        assert result == text

    def test_truncate_long_text(self):
        text = "A" * 10000
        result = TaskPlanner._truncate_for_prompt(text, 500)
        assert len(result) <= 520  # 500 + "… [truncated]"
        assert result.endswith("… [truncated]")

    def test_planner_uses_max_prompt_tokens(self):
        planner = _make_planner()
        assert planner.max_prompt_tokens == 13000

    def test_custom_max_prompt_tokens(self):
        settings = Settings()
        settings.chat_max_prompt_tokens = 8000
        planner = _make_planner(settings=settings)
        assert planner.max_prompt_tokens == 8000


# ---------------------------------------------------------------------------
# Cancellation support
# ---------------------------------------------------------------------------

class TestCancellationSupport:
    """Test task cancellation during plan execution."""

    def test_is_cancelled_with_no_task_id(self):
        planner = _make_planner()
        assert planner._is_cancelled() is False

    def test_is_cancelled_checks_db(self):
        """When task_id is set, _is_cancelled queries the DB."""
        store = MagicMock()
        session_mock = MagicMock()
        session_mock.__enter__ = Mock(return_value=session_mock)
        session_mock.__exit__ = Mock(return_value=False)

        # Simulate a cancelled task in DB
        mock_task = MagicMock()
        mock_task.status = "cancelled"
        session_mock.get.return_value = mock_task
        store.Session.return_value = session_mock

        planner = _make_planner(store=store, task_id=str(uuid.uuid4()))
        assert planner._is_cancelled() is True

    def test_is_cancelled_running_task(self):
        store = MagicMock()
        session_mock = MagicMock()
        session_mock.__enter__ = Mock(return_value=session_mock)
        session_mock.__exit__ = Mock(return_value=False)

        mock_task = MagicMock()
        mock_task.status = "running"
        session_mock.get.return_value = mock_task
        store.Session.return_value = session_mock

        planner = _make_planner(store=store, task_id=str(uuid.uuid4()))
        assert planner._is_cancelled() is False


# ---------------------------------------------------------------------------
# Persistent memory (ChatMemoryEntry)
# ---------------------------------------------------------------------------

class TestPersistentMemory:
    """Test that memory is persisted to the database via ChatMemoryEntry."""

    def test_chat_memory_entry_model_import(self):
        from garuda_intel.database.models import ChatMemoryEntry
        assert ChatMemoryEntry.__tablename__ == "chat_memory_entries"

    def test_chat_memory_entry_has_fields(self):
        from garuda_intel.database.models import ChatMemoryEntry
        assert hasattr(ChatMemoryEntry, "plan_id")
        assert hasattr(ChatMemoryEntry, "key")
        assert hasattr(ChatMemoryEntry, "value_json")
        assert hasattr(ChatMemoryEntry, "step_index")
        assert hasattr(ChatMemoryEntry, "tool_name")

    def test_chat_plan_has_memory_entries_relationship(self):
        from garuda_intel.database.models import ChatPlan
        assert hasattr(ChatPlan, "memory_entries")

    def test_persist_memory_calls_db(self):
        """Verify _persist_memory tries to write to DB."""
        store = MagicMock()
        session_mock = MagicMock()
        session_mock.__enter__ = Mock(return_value=session_mock)
        session_mock.__exit__ = Mock(return_value=False)
        # No existing entry
        session_mock.execute.return_value.scalar_one_or_none.return_value = None
        store.Session.return_value = session_mock

        planner = _make_planner(store=store)
        memory = {"key1": "value1", "key2": [1, 2, 3]}
        plan_id = str(uuid.uuid4())

        planner._persist_memory(plan_id, memory, 1, "search_local_data")

        # Should have committed
        assert session_mock.commit.called


# ---------------------------------------------------------------------------
# Response format
# ---------------------------------------------------------------------------

class TestResponseFormat:
    """Test that responses include new fields."""

    def test_response_has_memory_snapshot(self):
        planner = _make_planner()
        resp = planner._build_response(
            question="test", entity="", answer="answer",
            context=[], sources=[],
            plan_steps_log=[], memory={"k1": "v1", "k2": [1, 2]},
            total_plan_changes=1, total_steps=2, cycle_count=1,
            plan_id="test-id",
        )
        assert "memory_snapshot" in resp
        assert resp["memory_snapshot"]["k1"] == "v1"
        assert resp["memory_snapshot"]["k2"] == [1, 2]

    def test_response_has_crawl_enabled(self):
        planner = _make_planner(crawl_enabled=True)
        resp = planner._build_response(
            question="test", entity="", answer="a", context=[], sources=[],
            plan_steps_log=[], memory={}, total_plan_changes=0,
            total_steps=0, cycle_count=1, plan_id="x",
        )
        assert resp["crawl_enabled"] is True

    def test_response_backward_compatible(self):
        """All legacy keys must still be present."""
        planner = _make_planner()
        resp = planner._build_response(
            question="test", entity="", answer="a", context=[], sources=[],
            plan_steps_log=[], memory={}, total_plan_changes=0,
            total_steps=0, cycle_count=1, plan_id="x",
        )
        for key in [
            "answer", "context", "entity", "online_search_triggered",
            "retry_attempted", "paraphrased_queries", "live_urls",
            "crawl_reason", "rag_hits_count", "graph_hits_count",
            "sql_hits_count", "search_cycles_completed", "max_search_cycles",
            "current_step", "final_step",
            "plan_id", "total_plan_changes", "total_steps_executed",
            "plan_steps", "memory_keys", "memory_snapshot", "sources",
            "crawl_enabled",
        ]:
            assert key in resp, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Helper for mock LLM responses used by new tests
# ---------------------------------------------------------------------------

def _mock_llm_resp(text):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"response": text}
    mock.raise_for_status = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# Consecutive insufficient limit
# ---------------------------------------------------------------------------

class TestConsecutiveInsufficientLimit:
    """Test that consecutive INSUFFICIENT_DATA re-plans are capped."""

    def test_default_max_consecutive_insufficient(self):
        s = Settings()
        assert s.chat_max_consecutive_insufficient == 3

    @patch.dict("os.environ", {
        "GARUDA_CHAT_MAX_CONSECUTIVE_INSUFFICIENT": "5",
    })
    def test_config_from_env(self):
        s = Settings.from_env()
        assert s.chat_max_consecutive_insufficient == 5

    def test_planner_reads_config(self):
        planner = _make_planner()
        assert planner.max_consecutive_insufficient == 3

    def test_custom_max_consecutive_insufficient(self):
        settings = Settings()
        settings.chat_max_consecutive_insufficient = 5
        planner = _make_planner(settings=settings)
        assert planner.max_consecutive_insufficient == 5

    def test_default_constant_value(self):
        assert DEFAULT_MAX_CONSECUTIVE_INSUFFICIENT == 3

    @patch("garuda_intel.services.task_planner.requests.post")
    def test_run_stops_after_consecutive_insufficient_limit(self, mock_post):
        """After N consecutive INSUFFICIENT_DATA, the planner should stop re-planning."""
        plan_json = json.dumps([
            {"tool": "search_local_data", "input": {"query": "test"}, "description": "Search"},
            {"tool": "reflect_findings", "input": {"data_key": "search_results"}, "description": "Reflect"},
        ])
        reflect_json = json.dumps({
            "sufficient": False, "summary": "", "missing": ["data"], "next_action": "crawl"
        })
        summary_json = "Based on limited data available."

        # Return plan + reflect responses in a cycle, then a final summary
        mock_post.return_value = _mock_llm_resp(plan_json)

        planner = _make_planner()
        planner.max_consecutive_insufficient = 2
        planner.max_plan_changes_per_cycle = 10
        planner.max_cycles = 1

        # Mock reflect to always return insufficient
        with patch.object(planner, '_tool_reflect', return_value={"sufficient": False, "summary": "", "missing": ["data"]}):
            result = planner.run("test question")

        # Should have stopped after the consecutive insufficient limit
        # The key check: we should NOT see 10+ plan changes (the old behavior)
        assert result["total_plan_changes"] <= 3  # Should stop early
        assert "_insufficient_limit_reached" in result.get("memory_snapshot", {}) or \
               result["total_plan_changes"] <= 2 + 1  # max_consecutive_insufficient(2) + 1 initial plan

    @patch("garuda_intel.services.task_planner.requests.post")
    def test_consecutive_counter_resets_on_success(self, mock_post):
        """Counter should reset to 0 when a step succeeds."""
        # Plan: search → reflect(sufficient=true) → evaluate(done)
        plan_json = json.dumps([
            {"tool": "search_local_data", "input": {"query": "test"}, "description": "Search"},
            {"tool": "reflect_findings", "input": {"data_key": "search_results"}, "description": "Reflect"},
        ])
        reflect_json = json.dumps({
            "sufficient": True, "summary": "Found data", "missing": [], "next_action": "none"
        })
        eval_json = json.dumps({"done": True, "answer": "The answer."})

        mock_post.side_effect = [
            _mock_llm_resp(plan_json),
            _mock_llm_resp(reflect_json),
            _mock_llm_resp(eval_json),
            _mock_llm_resp('"Generalized task"'),
        ]

        planner = _make_planner()

        # Make vector store return results so search_local_data yields count > 0
        mock_result = MagicMock()
        mock_result.score = 0.8
        mock_result.payload = {"url": "https://example.com", "text": "data", "kind": "page", "entity": "E"}
        planner.vector_store.search.return_value = [mock_result]

        result = planner.run("test question")

        # Should complete normally without hitting insufficient limit
        assert "answer" in result
        assert "_insufficient_limit_reached" not in result.get("memory_snapshot", {})


# ---------------------------------------------------------------------------
# Task decomposition in plan creation
# ---------------------------------------------------------------------------

class TestTaskDecomposition:
    """Test that plan creation includes task decomposition guidance."""

    def test_plan_prompt_includes_decomposition_rule(self):
        """Verify the plan creation prompt includes task decomposition instructions."""
        planner = _make_planner()
        # Force fallback by making LLM request raise an exception and capture the prompt
        with patch("garuda_intel.services.task_planner.requests.post") as mock_post:
            mock_post.side_effect = Exception("timeout")
            plan = planner._tool_create_plan("Show me all RTX GPUs with details", "Nvidia", {}, [])
            # The fallback plan is returned, but we can verify the prompt was constructed
            # by checking the call args
            call_args = mock_post.call_args
            prompt_sent = call_args[1]["json"]["prompt"] if call_args else ""
            assert "decompose" in prompt_sent.lower() or "sub-task" in prompt_sent.lower()

    def test_plan_prompt_warns_about_insufficient_history(self):
        """When there are insufficient steps in memory, the prompt warns about them."""
        planner = _make_planner()
        memory = {
            "_insufficient_step_1": {"tool": "reflect_findings", "reason": "INSUFFICIENT_DATA"},
            "_insufficient_step_3": {"tool": "reflect_findings", "reason": "INSUFFICIENT_DATA"},
        }
        with patch("garuda_intel.services.task_planner.requests.post") as mock_post:
            mock_post.side_effect = Exception("timeout")
            plan = planner._tool_create_plan("test question", "", memory, [])
            call_args = mock_post.call_args
            prompt_sent = call_args[1]["json"]["prompt"] if call_args else ""
            assert "INSUFFICIENT_DATA" in prompt_sent or "WARNING" in prompt_sent

    def test_plan_prompt_no_warning_when_no_insufficient(self):
        """When there are no insufficient steps, no warning is included."""
        planner = _make_planner()
        memory = {"search_results": [{"score": 0.9}]}
        with patch("garuda_intel.services.task_planner.requests.post") as mock_post:
            mock_post.side_effect = Exception("timeout")
            plan = planner._tool_create_plan("test question", "", memory, [])
            call_args = mock_post.call_args
            prompt_sent = call_args[1]["json"]["prompt"] if call_args else ""
            assert "WARNING" not in prompt_sent


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------

class TestEventEmission:
    """Test that events are emitted correctly."""

    def test_emit_does_not_raise(self):
        """_emit should not crash even when event system is unavailable."""
        planner = _make_planner()
        # Should not raise
        planner._emit("test_step", "test message", {"key": "value"})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
