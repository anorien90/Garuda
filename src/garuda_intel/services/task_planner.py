"""
Dynamic Task Planner for Chat Hybrid RAG.

Converts the chat process into an LLM-driven, tool-based planning loop.
The planner analyses the user question, creates a multi-step plan using
available tools, executes steps, reflects on findings, and adapts the plan
up to a configurable number of revisions before returning a final answer.

Tools available to the planner:
    search_local_data   – semantic / graph / SQL lookup
    crawl_external_data – web search + intelligent crawl pipeline
    reflect_findings    – LLM reflection on gathered data
    store_memory_data   – persist intermediate results in working memory
    get_memory_data     – retrieve (partial) working memory
    create_plan         – generate / regenerate a multi-step plan
    store_step_to_plan  – append a step to the current plan
    eval_step_from_plan – evaluate a single step's outcome
    evaluate_plan       – evaluate the whole plan against the original request
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from ..database.models import ChatPlan, ChatPlanStep, StepPattern
from ..database.store import PersistenceStore
from ..extractor.llm import LLMIntelExtractor
from ..vector.base import VectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TOOL_NAMES = [
    "search_local_data",
    "crawl_external_data",
    "reflect_findings",
    "store_memory_data",
    "get_memory_data",
    "create_plan",
    "store_step_to_plan",
    "eval_step_from_plan",
    "evaluate_plan",
]

DEFAULT_MAX_PLAN_CHANGES_PER_CYCLE = 15
DEFAULT_MAX_CYCLES = 2
DEFAULT_MAX_TOTAL_STEPS = 100
DEFAULT_PATTERN_REUSE_THRESHOLD = 0.75
STEP_PATTERN_QDRANT_PREFIX = "step_pattern_"


class TaskPlanner:
    """Orchestrates dynamic, multi-step chat plans using MCP-style tools."""

    def __init__(
        self,
        store: PersistenceStore,
        llm: LLMIntelExtractor,
        vector_store: Optional[VectorStore] = None,
        settings: Any = None,
        # Injected helpers for web crawling
        collect_candidates_fn=None,
        explorer_factory=None,
    ):
        self.store = store
        self.llm = llm
        self.vector_store = vector_store
        self.settings = settings
        self._collect_candidates = collect_candidates_fn
        self._explorer_factory = explorer_factory

        # Limits
        self.max_plan_changes_per_cycle = getattr(
            settings, "chat_max_plan_changes_per_cycle", DEFAULT_MAX_PLAN_CHANGES_PER_CYCLE
        )
        self.max_cycles = getattr(settings, "chat_max_cycles", DEFAULT_MAX_CYCLES)
        self.max_total_steps = getattr(settings, "chat_max_total_steps", DEFAULT_MAX_TOTAL_STEPS)
        self.pattern_reuse_threshold = getattr(
            settings, "chat_pattern_reuse_threshold", DEFAULT_PATTERN_REUSE_THRESHOLD
        )

    # -----------------------------------------------------------------------
    # Public entry-point
    # -----------------------------------------------------------------------
    def run(
        self,
        question: str,
        entity: str = "",
        top_k: int = 6,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute the dynamic task-based chat pipeline.

        Returns a dict compatible with the existing ``/api/chat`` response
        schema so the frontend can render the result unchanged.
        """
        plan_id = str(uuid.uuid4())
        memory: Dict[str, Any] = {}
        sources: List[str] = []
        all_context: List[Dict[str, Any]] = []

        # Persist the plan row
        self._create_plan_row(plan_id, question, session_id)

        total_plan_changes = 0
        total_steps = 0
        plan_steps_log: List[Dict[str, Any]] = []
        current_plan: Optional[List[Dict[str, Any]]] = None
        final_answer: Optional[str] = None

        # --- Look up past patterns for a head-start ---
        existing_pattern = self._find_matching_pattern(question)
        if existing_pattern:
            logger.info("Found matching step pattern – will try reuse")

        for cycle in range(1, self.max_cycles + 1):
            plan_changes_this_cycle = 0

            while plan_changes_this_cycle < self.max_plan_changes_per_cycle:
                if total_steps >= self.max_total_steps:
                    logger.warning("Total step limit reached (%d)", self.max_total_steps)
                    break

                # -- 1. Create / recreate the plan --
                if current_plan is None or not self._has_pending_steps(current_plan):
                    plan_changes_this_cycle += 1
                    total_plan_changes += 1
                    current_plan = self._tool_create_plan(
                        question,
                        entity,
                        memory,
                        plan_steps_log,
                        existing_pattern=existing_pattern if plan_changes_this_cycle == 1 else None,
                    )
                    self._update_plan_row(
                        plan_id,
                        current_plan,
                        memory,
                        plan_changes_this_cycle,
                        cycle,
                    )
                    if not current_plan:
                        break

                # -- 2. Execute next pending step --
                step = self._next_pending_step(current_plan)
                if step is None:
                    break

                total_steps += 1
                step_result = self._execute_step(
                    step,
                    question,
                    entity,
                    memory,
                    top_k,
                    plan_id,
                    total_steps,
                )
                plan_steps_log.append(step_result)

                # Collect sources / context
                step_sources = step_result.get("sources", [])
                sources.extend(s for s in step_sources if s not in sources)
                step_ctx = step_result.get("context", [])
                all_context.extend(step_ctx)

                # -- 3. Evaluate the step --
                eval_ok = self._tool_eval_step(step_result, question, memory)
                if not eval_ok:
                    # Mark remaining steps stale – force re-plan
                    self._invalidate_remaining(current_plan)
                    continue

                # -- 4. Evaluate entire plan --
                plan_done, answer_candidate = self._tool_evaluate_plan(
                    question,
                    memory,
                    plan_steps_log,
                    current_plan,
                )
                if plan_done and answer_candidate:
                    final_answer = answer_candidate
                    break

            if final_answer:
                break

        # --- Final summarisation step ---
        if not final_answer:
            final_answer = self._final_summary(question, memory, plan_steps_log, sources)

        # --- Persist pattern if successful ---
        self._maybe_store_pattern(question, plan_steps_log, final_answer)

        # --- Persist completed plan ---
        self._complete_plan_row(plan_id, final_answer, sources, memory, total_steps)

        # --- Build response ---
        return self._build_response(
            question=question,
            entity=entity,
            answer=final_answer,
            context=all_context,
            sources=sources,
            plan_steps_log=plan_steps_log,
            memory=memory,
            total_plan_changes=total_plan_changes,
            total_steps=total_steps,
            cycle_count=min(cycle, self.max_cycles) if "cycle" in dir() else 1,
            plan_id=plan_id,
        )

    # -----------------------------------------------------------------------
    # Tool implementations
    # -----------------------------------------------------------------------
    def _tool_create_plan(
        self,
        question: str,
        entity: str,
        memory: Dict[str, Any],
        history: List[Dict[str, Any]],
        existing_pattern: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Ask the LLM to create / regenerate a plan."""
        tools_desc = (
            "Available tools:\n"
            "- search_local_data(query): Search local RAG, graph, and SQL data\n"
            "- crawl_external_data(query, entity): Crawl the web for new data\n"
            "- reflect_findings(data_key): Reflect on data stored in memory\n"
            "- store_memory_data(key, value): Store a result to working memory\n"
            "- get_memory_data(key): Retrieve data from working memory\n"
        )

        memory_summary = (
            json.dumps(
                {k: (str(v)[:200] if isinstance(v, str) else v) for k, v in memory.items()},
                ensure_ascii=False,
            )
            if memory
            else "{}"
        )

        history_summary = ""
        if history:
            recent = history[-5:]
            history_summary = "\n".join(
                f"  Step {h.get('step_index', '?')}: {h.get('tool_name', '?')} → {h.get('status', '?')}"
                for h in recent
            )

        pattern_hint = ""
        if existing_pattern:
            seq = existing_pattern.get("tool_sequence", [])
            pattern_hint = (
                f"\nA similar task was solved before with this tool sequence: "
                f"{json.dumps(seq, ensure_ascii=False)}\n"
                "Try this approach first, but adapt if needed.\n"
            )

        prompt = f"""You are a task planner. Given the user request and context, create a step-by-step plan 
using ONLY the tools listed below. Return ONLY a JSON array of step objects.

{tools_desc}
{pattern_hint}
User request: "{question}"
Entity context: "{entity}"
Current memory: {memory_summary}
Previous steps: {history_summary or 'None'}

Rules:
1. Start with search_local_data to check existing knowledge
2. If local data is insufficient, use crawl_external_data
3. Always reflect_findings before finalising
4. Use store_memory_data to save intermediate results
5. Keep the plan concise (3-8 steps)
6. For multi-part questions, create steps for each sub-question

Return JSON array:
[{{"tool": "<tool_name>", "input": {{"<param>": "<value>"}}, "description": "..."}}]
"""
        try:
            payload = {"model": self.llm.model, "prompt": prompt, "stream": False}
            resp = requests.post(self.llm.ollama_url, json=payload, timeout=60)
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            plan = self.llm.text_processor.safe_json_loads(raw, fallback=[])
            if isinstance(plan, list):
                for i, step in enumerate(plan):
                    step["status"] = "pending"
                    step["step_index"] = i
                return plan
        except Exception as e:
            logger.warning("Plan creation failed: %s", e)

        # Fallback minimal plan
        return [
            {
                "tool": "search_local_data",
                "input": {"query": question},
                "status": "pending",
                "step_index": 0,
                "description": "Search local knowledge base",
            },
            {
                "tool": "crawl_external_data",
                "input": {"query": question, "entity": entity},
                "status": "pending",
                "step_index": 1,
                "description": "Crawl web for data",
            },
            {
                "tool": "reflect_findings",
                "input": {"data_key": "search_results"},
                "status": "pending",
                "step_index": 2,
                "description": "Reflect on gathered data",
            },
        ]

    # -- search_local_data --
    def _tool_search_local(
        self,
        query: str,
        top_k: int,
        entity: str,
    ) -> Dict[str, Any]:
        """Search local RAG + SQL + graph data."""
        hits: List[Dict[str, Any]] = []
        sources: List[str] = []

        # Vector / RAG search
        if self.vector_store:
            try:
                vec = self.llm.embed_text(query)
                if vec:
                    results = self.vector_store.search(vec, top_k=min(top_k * 2, 100))
                    for r in results:
                        hit = {
                            "url": r.payload.get("url", ""),
                            "snippet": r.payload.get("text", ""),
                            "score": r.score,
                            "source": "rag",
                            "kind": r.payload.get("kind", "unknown"),
                            "entity": r.payload.get("entity", ""),
                        }
                        hits.append(hit)
                        if hit["url"]:
                            sources.append(hit["url"])
            except Exception as e:
                logger.warning("Vector search failed: %s", e)

        # SQL search
        try:
            sql_results = self.store.search_intel(keyword=query, limit=top_k)
            for r in sql_results:
                r["source"] = "sql"
                hits.append(r)
        except Exception as e:
            logger.warning("SQL search failed: %s", e)

        # Deduplicate by URL
        seen: Dict[str, Dict] = {}
        no_url: List[Dict] = []
        for h in hits:
            url = h.get("url", "")
            if url:
                if url not in seen or float(h.get("score", 0) or 0) > float(
                    seen[url].get("score", 0) or 0
                ):
                    seen[url] = h
            else:
                no_url.append(h)
        merged = sorted(seen.values(), key=lambda x: float(x.get("score", 0) or 0), reverse=True)
        merged = merged[:top_k] + no_url[: top_k // 4]

        return {"hits": merged, "sources": sources, "count": len(merged)}

    # -- crawl_external_data --
    def _tool_crawl_external(
        self,
        query: str,
        entity: str,
    ) -> Dict[str, Any]:
        """Execute a web crawl cycle for the given query."""
        from ..search import (
            IntelligentExplorer,
            EntityProfile,
            EntityType,
            collect_candidates_simple,
        )

        collect_fn = self._collect_candidates or collect_candidates_simple
        search_queries = self.llm.generate_seed_queries(query, entity)
        if not search_queries:
            search_queries = [query]

        candidates = collect_fn(search_queries, limit=5)
        urls: List[str] = []
        for cand in candidates:
            url = None
            if isinstance(cand, dict):
                url = cand.get("href") or cand.get("url")
            elif isinstance(cand, str):
                url = cand
            if url:
                urls.append(url)

        if not urls:
            return {"urls_crawled": [], "error": "No candidate URLs found"}

        profile = EntityProfile(name=entity or "General Research", entity_type=EntityType.TOPIC)
        max_pages = getattr(self.settings, "chat_max_pages", 5)
        explorer = IntelligentExplorer(
            profile=profile,
            persistence=self.store,
            vector_store=self.vector_store,
            llm_extractor=self.llm,
            max_total_pages=max_pages,
            score_threshold=5.0,
        )

        try:
            explorer.explore(urls, None)
        except Exception as e:
            logger.warning("Crawl failed: %s", e)
            return {"urls_crawled": urls, "error": str(e)}

        return {"urls_crawled": urls, "count": len(urls)}

    # -- reflect_findings --
    def _tool_reflect(
        self,
        data_key: str,
        memory: Dict[str, Any],
        question: str,
    ) -> Dict[str, Any]:
        """Reflect on data in memory and evaluate quality."""
        data = memory.get(data_key, memory)
        data_str = json.dumps(data, ensure_ascii=False, default=str)[:4000]

        prompt = f"""Analyse the following data gathered for the user question and determine:
1. Is there enough information to answer the question?
2. What is missing?
3. What should be done next?

User question: "{question}"
Data:
{data_str}

Return JSON: {{"sufficient": true/false, "summary": "...", "missing": ["..."], "next_action": "..."}}
"""
        try:
            payload = {"model": self.llm.model, "prompt": prompt, "stream": False}
            resp = requests.post(self.llm.ollama_url, json=payload, timeout=60)
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            result = self.llm.text_processor.safe_json_loads(raw, fallback={})
            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.warning("Reflect failed: %s", e)
        return {
            "sufficient": False,
            "summary": "",
            "missing": [],
            "next_action": "crawl_external_data",
        }

    # -- store_memory_data / get_memory_data --
    @staticmethod
    def _tool_store_memory(memory: Dict[str, Any], key: str, value: Any) -> Dict[str, Any]:
        memory[key] = value
        return {"stored": key}

    @staticmethod
    def _tool_get_memory(memory: Dict[str, Any], key: Optional[str] = None) -> Any:
        if key:
            return memory.get(key)
        return memory

    # -- eval_step_from_plan --
    def _tool_eval_step(
        self,
        step_result: Dict[str, Any],
        question: str,
        memory: Dict[str, Any],
    ) -> bool:
        """Evaluate a single step outcome – returns True if acceptable."""
        status = step_result.get("status", "failed")
        if status == "failed":
            return False
        tool = step_result.get("tool_name", "")
        output = step_result.get("output", {})

        if tool == "search_local_data":
            count = 0
            if isinstance(output, dict):
                count = output.get("count", 0)
            return count > 0

        if tool == "crawl_external_data":
            if isinstance(output, dict) and output.get("error"):
                return False
            return True

        if tool == "reflect_findings":
            if isinstance(output, dict):
                return True
            return False

        return True

    # -- evaluate_plan --
    def _tool_evaluate_plan(
        self,
        question: str,
        memory: Dict[str, Any],
        history: List[Dict[str, Any]],
        plan: List[Dict[str, Any]],
    ) -> Tuple[bool, Optional[str]]:
        """Evaluate the overall plan progress. Return (done, answer_candidate)."""
        memory_str = json.dumps(memory, ensure_ascii=False, default=str)[:6000]
        steps_done = [h for h in history if h.get("status") == "completed"]

        prompt = f"""You are evaluating whether enough data has been gathered to answer the user question.

User question: "{question}"
Memory (collected data):
{memory_str}
Steps completed: {len(steps_done)}

If there is enough information to compose a final answer, return:
{{"done": true, "answer": "<your synthesized answer using the data in memory>"}}

If more data is needed, return:
{{"done": false, "reason": "..."}}
"""
        try:
            payload = {"model": self.llm.model, "prompt": prompt, "stream": False}
            resp = requests.post(self.llm.ollama_url, json=payload, timeout=90)
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            result = self.llm.text_processor.safe_json_loads(raw, fallback={})
            if isinstance(result, dict):
                if result.get("done"):
                    return True, result.get("answer", "")
                return False, None
        except Exception as e:
            logger.warning("Plan evaluation failed: %s", e)
        return False, None

    # -----------------------------------------------------------------------
    # Step execution dispatcher
    # -----------------------------------------------------------------------
    def _execute_step(
        self,
        step: Dict[str, Any],
        question: str,
        entity: str,
        memory: Dict[str, Any],
        top_k: int,
        plan_id: str,
        step_index: int,
    ) -> Dict[str, Any]:
        """Execute a single plan step and return the result."""
        tool = step.get("tool", "")
        tool_input = step.get("input", {})
        if not isinstance(tool_input, dict):
            tool_input = {}
        step["status"] = "running"
        started = datetime.now(timezone.utc)
        output: Any = None
        error: Optional[str] = None
        step_sources: List[str] = []
        step_context: List[Dict[str, Any]] = []

        try:
            if tool == "search_local_data":
                q = tool_input.get("query", question)
                result = self._tool_search_local(q, top_k, entity)
                output = result
                step_sources = result.get("sources", [])
                step_context = result.get("hits", [])
                # Auto-store to memory
                self._tool_store_memory(memory, "search_results", result.get("hits", []))

            elif tool == "crawl_external_data":
                q = tool_input.get("query", question)
                e = tool_input.get("entity", entity)
                result = self._tool_crawl_external(q, e)
                output = result
                step_sources.extend(result.get("urls_crawled", []))
                self._tool_store_memory(memory, "crawl_results", result)

            elif tool == "reflect_findings":
                dk = tool_input.get("data_key", "search_results")
                result = self._tool_reflect(dk, memory, question)
                output = result
                self._tool_store_memory(memory, "reflection", result)

            elif tool == "store_memory_data":
                key = tool_input.get("key", "data")
                val = tool_input.get("value", "")
                output = self._tool_store_memory(memory, key, val)

            elif tool == "get_memory_data":
                key = tool_input.get("key")
                output = self._tool_get_memory(memory, key)

            elif tool == "create_plan":
                # Handled externally – should not appear inside execution
                output = {"note": "Plan creation handled by orchestrator"}

            elif tool == "store_step_to_plan":
                output = {"note": "Dynamic step insertion handled by orchestrator"}

            elif tool == "eval_step_from_plan":
                output = {"note": "Step evaluation handled by orchestrator"}

            elif tool == "evaluate_plan":
                output = {"note": "Plan evaluation handled by orchestrator"}

            else:
                error = f"Unknown tool: {tool}"
                output = {"error": error}

            step["status"] = "completed" if not error else "failed"

        except Exception as exc:
            error = str(exc)
            step["status"] = "failed"
            logger.warning("Step execution failed (%s): %s", tool, exc)

        completed = datetime.now(timezone.utc)

        # Persist step row
        self._persist_step(
            plan_id, step_index, tool, tool_input, output, step["status"], error, started, completed
        )

        return {
            "step_index": step_index,
            "tool_name": tool,
            "input": tool_input,
            "output": output,
            "status": step["status"],
            "error": error,
            "sources": step_sources,
            "context": step_context,
        }

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    @staticmethod
    def _has_pending_steps(plan: List[Dict[str, Any]]) -> bool:
        return any(s.get("status") == "pending" for s in plan)

    @staticmethod
    def _next_pending_step(plan: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for s in plan:
            if s.get("status") == "pending":
                return s
        return None

    @staticmethod
    def _invalidate_remaining(plan: List[Dict[str, Any]]) -> None:
        for s in plan:
            if s.get("status") == "pending":
                s["status"] = "skipped"

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    def _final_summary(
        self,
        question: str,
        memory: Dict[str, Any],
        history: List[Dict[str, Any]],
        sources: List[str],
    ) -> str:
        """Produce a final answer by summarising memory and plan outcomes."""
        memory_str = json.dumps(memory, ensure_ascii=False, default=str)[:8000]
        src_str = "\n".join(f"- {s}" for s in sources[:20]) if sources else "No sources."

        prompt = f"""Synthesize a final answer to the user question using ALL collected data.

User question: "{question}"

Collected data (memory):
{memory_str}

Sources consulted:
{src_str}

Steps executed: {len(history)}

Instructions:
1. Answer the question as completely as possible using the data above.
2. If data is insufficient, clearly state what is missing.
3. Include references to sources where available.
4. Do NOT fabricate information.
"""
        try:
            payload = {"model": self.llm.model, "prompt": prompt, "stream": False}
            resp = requests.post(self.llm.ollama_url, json=payload, timeout=120)
            resp.raise_for_status()
            ans = resp.json().get("response", "").strip()
            if ans:
                return ans
        except Exception as e:
            logger.warning("Final summary failed: %s", e)

        # Fallback – assemble from memory
        parts = []
        for k, v in memory.items():
            if isinstance(v, str):
                parts.append(v[:500])
            elif isinstance(v, list):
                for item in v[:3]:
                    snippet = item.get("snippet", "") if isinstance(item, dict) else str(item)
                    if snippet:
                        parts.append(snippet[:300])
        if parts:
            return "Based on available data:\n\n" + "\n\n".join(parts)
        return "I could not gather enough information to answer your question."

    # -----------------------------------------------------------------------
    # Pattern matching and storage
    # -----------------------------------------------------------------------
    def _find_matching_pattern(self, question: str) -> Optional[Dict[str, Any]]:
        """Search Qdrant for a previously successful step pattern."""
        if not self.vector_store:
            return None
        try:
            vec = self.llm.embed_text(question)
            if not vec:
                return None
            results = self.vector_store.search(
                vec,
                top_k=3,
                query_filter=(
                    {"must": [{"key": "kind", "match": {"value": "step_pattern"}}]}
                    if hasattr(self.vector_store, "search")
                    else None
                ),
            )
            for r in results:
                if r.score >= self.pattern_reuse_threshold:
                    return {
                        "tool_sequence": r.payload.get("tool_sequence", []),
                        "generalized_task": r.payload.get("generalized_task", ""),
                        "reward_score": r.payload.get("reward_score", 0),
                        "score": r.score,
                    }
        except Exception as e:
            logger.debug("Pattern search failed (non-critical): %s", e)
        return None

    def _maybe_store_pattern(
        self,
        question: str,
        history: List[Dict[str, Any]],
        answer: str,
    ) -> None:
        """Store the tool sequence as a pattern if the result looks successful."""
        if not answer or "could not" in answer.lower() or "insufficient" in answer.lower():
            return
        completed_steps = [h for h in history if h.get("status") == "completed"]
        if len(completed_steps) < 2:
            return

        tool_sequence = [
            {"tool": h["tool_name"], "input_keys": list((h.get("input") or {}).keys())}
            for h in completed_steps
        ]

        # Generalize the task
        generalized = self._generalize_task(question)

        # Persist to DB
        try:
            if hasattr(self.store, "Session"):
                with self.store.Session() as session:
                    pattern = StepPattern(
                        generalized_task=generalized,
                        tool_sequence=tool_sequence,
                        reward_score=1.0,
                        times_used=1,
                        times_succeeded=1,
                        last_used_at=datetime.now(timezone.utc),
                    )
                    session.add(pattern)
                    session.commit()

            # Store embedding in Qdrant
            if self.vector_store:
                vec = self.llm.embed_text(generalized)
                if vec:
                    point_id = str(uuid.uuid4())
                    self.vector_store.upsert(
                        [
                            {
                                "id": point_id,
                                "vector": vec,
                                "payload": {
                                    "kind": "step_pattern",
                                    "generalized_task": generalized,
                                    "tool_sequence": tool_sequence,
                                    "reward_score": 1.0,
                                },
                            }
                        ]
                    )
        except Exception as e:
            logger.warning("Pattern storage failed (non-critical): %s", e)

    def _generalize_task(self, question: str) -> str:
        """Ask the LLM to produce a generalised reformulation of the task."""
        prompt = f"""Rewrite the following user question as a short, generalised task description 
that could match similar future questions. Remove specific names/dates but keep the intent.

Question: "{question}"
Return ONLY the generalised task description as a plain string (no JSON).
"""
        try:
            payload = {"model": self.llm.model, "prompt": prompt, "stream": False}
            resp = requests.post(self.llm.ollama_url, json=payload, timeout=30)
            resp.raise_for_status()
            result = resp.json().get("response", "").strip()
            if result and len(result) < 500:
                return result
        except Exception:
            pass
        return question

    # -----------------------------------------------------------------------
    # Persistence helpers
    # -----------------------------------------------------------------------
    def _create_plan_row(
        self,
        plan_id: str,
        question: str,
        session_id: Optional[str],
    ) -> Optional[ChatPlan]:
        try:
            if hasattr(self.store, "Session"):
                with self.store.Session() as session:
                    row = ChatPlan(
                        id=uuid.UUID(plan_id),
                        session_id=session_id,
                        original_prompt=question,
                        status="active",
                        memory_json={},
                        plan_json=[],
                        sources_json=[],
                    )
                    session.add(row)
                    session.commit()
                    return row
        except Exception as e:
            logger.warning("Failed to create plan row: %s", e)
        return None

    def _update_plan_row(
        self,
        plan_id: str,
        plan: List[Dict[str, Any]],
        memory: Dict[str, Any],
        plan_version: int,
        cycle: int,
    ) -> None:
        try:
            if hasattr(self.store, "Session"):
                with self.store.Session() as session:
                    row = session.get(ChatPlan, uuid.UUID(plan_id))
                    if row:
                        row.plan_json = plan
                        row.memory_json = self._safe_memory(memory)
                        row.plan_version = plan_version
                        row.cycle_number = cycle
                        session.commit()
        except Exception as e:
            logger.warning("Failed to update plan row: %s", e)

    def _complete_plan_row(
        self,
        plan_id: str,
        answer: str,
        sources: List[str],
        memory: Dict[str, Any],
        total_steps: int,
    ) -> None:
        try:
            if hasattr(self.store, "Session"):
                with self.store.Session() as session:
                    row = session.get(ChatPlan, uuid.UUID(plan_id))
                    if row:
                        row.final_answer = answer
                        row.sources_json = sources
                        row.memory_json = self._safe_memory(memory)
                        row.total_steps_executed = total_steps
                        row.status = "completed"
                        row.completed_at = datetime.now(timezone.utc)
                        session.commit()
        except Exception as e:
            logger.warning("Failed to complete plan row: %s", e)

    def _persist_step(
        self,
        plan_id: str,
        step_index: int,
        tool_name: str,
        tool_input: Any,
        tool_output: Any,
        status: str,
        error: Optional[str],
        started: datetime,
        completed: datetime,
    ) -> None:
        try:
            if hasattr(self.store, "Session"):
                with self.store.Session() as session:
                    step_row = ChatPlanStep(
                        plan_id=uuid.UUID(plan_id),
                        step_index=step_index,
                        tool_name=tool_name,
                        tool_input=self._safe_json(tool_input),
                        tool_output=self._safe_json(tool_output),
                        status=status,
                        error=error,
                        started_at=started,
                        completed_at=completed,
                    )
                    session.add(step_row)
                    session.commit()
        except Exception as e:
            logger.warning("Failed to persist step: %s", e)

    # -----------------------------------------------------------------------
    # Response builder
    # -----------------------------------------------------------------------
    def _build_response(
        self,
        question: str,
        entity: str,
        answer: str,
        context: List[Dict[str, Any]],
        sources: List[str],
        plan_steps_log: List[Dict[str, Any]],
        memory: Dict[str, Any],
        total_plan_changes: int,
        total_steps: int,
        cycle_count: int,
        plan_id: str,
    ) -> Dict[str, Any]:
        """Build the response dict, backward-compatible with existing /api/chat."""
        online_triggered = any(s.get("tool_name") == "crawl_external_data" for s in plan_steps_log)
        live_urls = []
        for s in plan_steps_log:
            if s.get("tool_name") == "crawl_external_data":
                out = s.get("output", {})
                if isinstance(out, dict):
                    live_urls.extend(out.get("urls_crawled", []))

        rag_hits = [c for c in context if c.get("source") == "rag"]
        graph_hits = [c for c in context if c.get("source") == "graph"]
        sql_hits = [c for c in context if c.get("source") == "sql"]

        # Determine final step label
        if not online_triggered:
            final_step = "phase1_local_lookup"
        elif answer and "could not" not in answer.lower():
            final_step = f"plan_completed_after_{total_steps}_steps"
        else:
            final_step = "plan_exhausted_insufficient_data"

        steps_summary = [
            {
                "step": s.get("step_index"),
                "tool": s.get("tool_name"),
                "status": s.get("status"),
                "description": s.get("input", {}).get(
                    "query", s.get("input", {}).get("data_key", "")
                ),
            }
            for s in plan_steps_log
        ]

        return {
            "answer": answer,
            "context": context[:50],
            "entity": entity,
            "online_search_triggered": online_triggered,
            "retry_attempted": total_plan_changes > 1,
            "paraphrased_queries": [],
            "live_urls": live_urls,
            "crawl_reason": "Task planner decided to crawl" if online_triggered else None,
            "rag_hits_count": len(rag_hits),
            "graph_hits_count": len(graph_hits),
            "sql_hits_count": len(sql_hits),
            "search_cycles_completed": cycle_count,
            "max_search_cycles": self.max_cycles,
            "current_step": "plan_execution",
            "final_step": final_step,
            # New fields for task planner
            "plan_id": plan_id,
            "total_plan_changes": total_plan_changes,
            "total_steps_executed": total_steps,
            "plan_steps": steps_summary,
            "memory_keys": list(memory.keys()),
            "sources": sources,
        }

    # -----------------------------------------------------------------------
    # Serialisation safety helpers
    # -----------------------------------------------------------------------
    @staticmethod
    def _safe_json(obj: Any) -> Any:
        """Ensure object is JSON-serialisable for DB storage."""
        if obj is None:
            return None
        try:
            json.dumps(obj, default=str)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    @staticmethod
    def _safe_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
        """Make memory dict safe for JSON column storage."""
        safe = {}
        for k, v in memory.items():
            try:
                json.dumps(v, default=str)
                safe[k] = v
            except (TypeError, ValueError):
                try:
                    safe[k] = str(v)
                except Exception:
                    safe[k] = "<unserializable>"
        return safe
