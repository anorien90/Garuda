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

from ..database.models import ChatMemoryEntry, ChatPlan, ChatPlanStep, StepPattern
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
    "search_memory",
    "create_plan",
    "store_step_to_plan",
    "eval_step_from_plan",
    "evaluate_plan",
]

DEFAULT_MAX_PLAN_CHANGES_PER_CYCLE = 15
DEFAULT_MAX_CYCLES = 2
DEFAULT_MAX_TOTAL_STEPS = 100
DEFAULT_PATTERN_REUSE_THRESHOLD = 0.75
DEFAULT_MAX_PROMPT_TOKENS = 13000
DEFAULT_MAX_CONSECUTIVE_INSUFFICIENT = 3
STEP_PATTERN_QDRANT_PREFIX = "step_pattern_"
# Rough chars-per-token factor (conservative for English text)
CHARS_PER_TOKEN = 4
# Minimum hits before query expansion kicks in for exhaustive queries
DEFAULT_QUERY_EXPANSION_THRESHOLD = 2
# Keywords that signal the user wants exhaustive / comprehensive results
EXHAUSTIVE_KEYWORDS = {"all", "every", "each", "complete", "full", "list", "entire"}
# Maximum number of query variants to generate
MAX_QUERY_VARIANTS = 6
# Maximum number of entities to extract from search results
MAX_EXTRACTED_ENTITIES = 20


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
        # Per-request overrides
        crawl_enabled: Optional[bool] = None,
        task_id: Optional[str] = None,
        progress_callback=None,
    ):
        self.store = store
        self.llm = llm
        self.vector_store = vector_store
        self.settings = settings
        self._collect_candidates = collect_candidates_fn
        self._explorer_factory = explorer_factory
        self._task_id = task_id
        self._progress_callback = progress_callback

        # Limits
        self.max_plan_changes_per_cycle = getattr(
            settings, "chat_max_plan_changes_per_cycle", DEFAULT_MAX_PLAN_CHANGES_PER_CYCLE
        )
        self.max_cycles = getattr(settings, "chat_max_cycles", DEFAULT_MAX_CYCLES)
        self.max_total_steps = getattr(settings, "chat_max_total_steps", DEFAULT_MAX_TOTAL_STEPS)
        self.pattern_reuse_threshold = getattr(
            settings, "chat_pattern_reuse_threshold", DEFAULT_PATTERN_REUSE_THRESHOLD
        )
        self.max_prompt_tokens = getattr(
            settings, "chat_max_prompt_tokens", DEFAULT_MAX_PROMPT_TOKENS
        )
        self.max_consecutive_insufficient = getattr(
            settings, "chat_max_consecutive_insufficient", DEFAULT_MAX_CONSECUTIVE_INSUFFICIENT
        )

        # Crawl enabled: per-request flag > settings > True
        if crawl_enabled is not None:
            self.crawl_enabled = crawl_enabled
        else:
            self.crawl_enabled = getattr(settings, "chat_crawl_enabled", True)

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
        cancelled = False

        # Persist the plan row
        self._create_plan_row(plan_id, question, session_id)
        self._emit("plan_created", f"Plan {plan_id} created for: {question[:80]}",
                    {"plan_id": plan_id, "question": question})
        self._report_progress(0.05, "Plan created, analysing question")

        total_plan_changes = 0
        total_steps = 0
        consecutive_insufficient = 0
        plan_steps_log: List[Dict[str, Any]] = []
        current_plan: Optional[List[Dict[str, Any]]] = None
        final_answer: Optional[str] = None
        last_cycle = 1

        # --- Look up past patterns for a head-start ---
        existing_pattern = self._find_matching_pattern(question)
        if existing_pattern:
            logger.info("Found matching step pattern – will try reuse")
            self._emit("pattern_match", "Reusing successful step pattern",
                        {"plan_id": plan_id})

        for cycle in range(1, self.max_cycles + 1):
            last_cycle = cycle
            plan_changes_this_cycle = 0

            while plan_changes_this_cycle < self.max_plan_changes_per_cycle:
                # --- Cancellation check ---
                if self._is_cancelled():
                    logger.info("Plan %s cancelled by user", plan_id)
                    self._emit("plan_cancelled", f"Plan {plan_id} cancelled",
                                {"plan_id": plan_id})
                    cancelled = True
                    break

                if total_steps >= self.max_total_steps:
                    logger.warning("Total step limit reached (%d)", self.max_total_steps)
                    self._emit("step_limit", "Total step limit reached",
                                {"plan_id": plan_id, "limit": self.max_total_steps})
                    break

                # -- 1. Create / recreate the plan --
                if current_plan is None or not self._has_pending_steps(current_plan):
                    plan_changes_this_cycle += 1
                    total_plan_changes += 1
                    self._emit("plan_creating", f"Creating plan (revision {total_plan_changes})",
                                {"plan_id": plan_id, "revision": total_plan_changes})
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
                tool_name = step.get("tool", "unknown")
                # Estimate progress: reserve 0.05-0.90 for step execution
                step_progress = 0.05 + (0.85 * total_steps / max(self.max_total_steps, total_steps + 1))
                self._report_progress(
                    min(step_progress, 0.90),
                    f"Step {total_steps}: {tool_name} – {step.get('description', '')[:60]}",
                )
                self._emit("step_executing",
                           f"Step {total_steps}: {tool_name}",
                           {"plan_id": plan_id, "step": total_steps,
                            "tool": tool_name,
                            "description": step.get("description", "")})

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

                # Persist memory snapshot to DB after every step
                self._persist_memory(plan_id, memory, total_steps, tool_name)

                self._emit("step_completed",
                           f"Step {total_steps} ({tool_name}): {step_result.get('status', 'unknown')}",
                           {"plan_id": plan_id, "step": total_steps,
                            "tool": tool_name,
                            "status": step_result.get("status")})

                # Collect sources / context
                step_sources = step_result.get("sources", [])
                sources.extend(s for s in step_sources if s not in sources)
                step_ctx = step_result.get("context", [])
                all_context.extend(step_ctx)

                # -- 3. Evaluate the step --
                eval_ok = self._tool_eval_step(step_result, question, memory)
                if not eval_ok:
                    consecutive_insufficient += 1

                    # Check if we've hit the consecutive insufficient limit
                    if consecutive_insufficient >= self.max_consecutive_insufficient:
                        logger.warning(
                            "Consecutive insufficient limit reached (%d) – "
                            "stopping re-plan loop and proceeding with available data",
                            consecutive_insufficient,
                        )
                        self._emit(
                            "insufficient_limit_reached",
                            f"Consecutive insufficient limit ({consecutive_insufficient}) reached – moving on",
                            {"plan_id": plan_id, "step": total_steps,
                             "consecutive_insufficient": consecutive_insufficient},
                        )
                        self._tool_store_memory(
                            memory, "_insufficient_limit_reached",
                            {"count": consecutive_insufficient,
                             "last_tool": tool_name,
                             "action": "proceeding_with_available_data"},
                        )
                        self._invalidate_remaining(current_plan)
                        break

                    # INSUFFICIENT_DATA escalation – force re-plan
                    self._emit("step_insufficient",
                               f"Step {total_steps} ({tool_name}) insufficient – re-planning",
                               {"plan_id": plan_id, "step": total_steps, "tool": tool_name})
                    self._tool_store_memory(memory, f"_insufficient_step_{total_steps}",
                                            {"tool": tool_name, "reason": "INSUFFICIENT_DATA"})
                    self._invalidate_remaining(current_plan)
                    continue

                # Step was sufficient – reset the consecutive counter
                consecutive_insufficient = 0

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

            if final_answer or cancelled:
                break

        # --- Final summarisation step ---
        if not final_answer and not cancelled:
            self._report_progress(0.90, "Generating final summary")
            self._emit("plan_summarizing", "Generating final summary",
                        {"plan_id": plan_id})
            final_answer = self._final_summary(question, memory, plan_steps_log, sources)

        if cancelled and not final_answer:
            final_answer = "Task was cancelled by the user."

        # --- Persist pattern if successful ---
        self._maybe_store_pattern(question, plan_steps_log, final_answer)

        # --- Persist completed plan ---
        status = "cancelled" if cancelled else "completed"
        self._complete_plan_row(plan_id, final_answer, sources, memory, total_steps, status=status)

        # --- Final memory persist ---
        self._persist_memory(plan_id, memory, total_steps, "_final")

        self._emit("plan_done", f"Plan finished: {status}",
                    {"plan_id": plan_id, "status": status,
                     "total_steps": total_steps})
        self._report_progress(1.0, f"Plan finished: {status}")

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
            cycle_count=min(last_cycle, self.max_cycles),
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
        crawl_note = "" if self.crawl_enabled else "\n  NOTE: Online crawling is DISABLED. Do NOT use crawl_external_data.\n"
        tools_desc = (
            "Available tools:\n"
            "- search_local_data(query): Search local RAG, graph, and SQL data\n"
            "- crawl_external_data(query, entity): Crawl the web for new data\n"
            "- reflect_findings(data_key): Reflect on data stored in memory\n"
            "- store_memory_data(key, value): Store a result to working memory\n"
            "- get_memory_data(key): Retrieve data from working memory\n"
            "- search_memory(query): Search through working memory for relevant entries\n"
            + crawl_note
        )

        memory_summary = self._truncate_for_prompt(
            json.dumps(
                {k: (str(v)[:200] if isinstance(v, str) else v) for k, v in memory.items()},
                ensure_ascii=False,
            )
            if memory
            else "{}",
            max_chars=2000,
        )

        history_summary = ""
        if history:
            recent = history[-5:]
            history_summary = "\n".join(
                f"  Step {h.get('step_index', '?')}: {h.get('tool_name', '?')} → {h.get('status', '?')}"
                for h in recent
            )

        # Build a summary of previously failed insufficient steps to avoid repeating them
        insufficient_note = ""
        insufficient_keys = [k for k in memory if k.startswith("_insufficient_step_")]
        if insufficient_keys:
            insufficient_note = (
                f"\nWARNING: {len(insufficient_keys)} previous steps returned INSUFFICIENT_DATA. "
                "Do NOT repeat the same search queries or reflect on the same data. "
                "Try a DIFFERENT approach: use different search terms, crawl for external data, "
                "or proceed with the data already available.\n"
            )

        pattern_hint = ""
        if existing_pattern:
            seq = existing_pattern.get("tool_sequence", [])
            pattern_hint = (
                f"\nA similar task was solved before with this tool sequence: "
                f"{json.dumps(seq, ensure_ascii=False)}\n"
                "Try this approach first, but adapt if needed.\n"
            )

        # Build a note about already-discovered entities so the planner
        # can generate individual look-up steps for each one.
        # Filter out entities that have already been searched to avoid
        # infinite follow-up loops.
        discovered_note = ""
        discovered = memory.get("_discovered_entities", [])
        searched = memory.get("_searched_entities", [])
        searched_lower = {s.lower() for s in searched} if searched else set()
        pending_entities = [
            e for e in discovered
            if e.lower() not in searched_lower
        ] if discovered else []
        if pending_entities:
            discovered_note = (
                f"\nDiscovered entities to look up individually: {json.dumps(pending_entities[:20], ensure_ascii=False)}\n"
                "Create a search_local_data step for EACH entity above to get its details "
                "(price, specs, role, etc.).\n"
            )

        prompt = f"""You are a task planner. Given the user request and context, create a step-by-step plan 
using ONLY the tools listed below. Return ONLY a JSON array of step objects.

{tools_desc}
{pattern_hint}
{insufficient_note}
{discovered_note}
User request: "{question}"
Entity context: "{entity}"
Current memory: {memory_summary}
Previous steps: {history_summary or 'None'}

Rules:
1. FIRST decompose the user request into distinct sub-tasks (e.g. "find all X", "get details for each", "sort by date")
2. Create search_local_data steps with SPECIFIC queries for each sub-task
3. If local data is insufficient, use crawl_external_data (if enabled) with targeted queries
4. Use store_memory_data to save intermediate results for each sub-task
5. Only use reflect_findings ONCE near the end, after gathering data for all sub-tasks
6. Keep the plan concise but THOROUGH (3-12 steps if needed for exhaustive queries)
7. Use search_memory when memory grows large and you need specific entries
8. Do NOT repeat queries that already failed – try different search terms or approaches
9. When the user asks for "all", "every", or a complete list of something:
   a. First search broadly to discover what items/entities exist
   b. Store the discovered list to memory
   c. Then search for EACH item individually to get details
   d. Do NOT stop after finding just 1-2 items – cover the full list
   e. Try different search angles (e.g. by name, by category, by related entity)
   f. Search with MULTIPLE query variations (e.g. search for "RTX 3000", then "RTX 3060", then "RTX 3070", etc.)
10. When a direct query finds nothing, ABSTRACT the request:
    e.g. "leaders of Nvidia" → search "Nvidia people", "Nvidia executives", "Nvidia board members",
    "Nvidia CTO", "Nvidia CEO", "Nvidia CFO", etc.
11. Correct likely typos in user queries (e.g. "RXT" → "RTX")
12. If memory contains _discovered_entities, create search steps for EACH entity in that list

Return JSON array:
[{{"tool": "<tool_name>", "input": {{"<param>": "<value>"}}, "description": "..."}}]
"""
        # Apply token budget
        prompt = self._truncate_for_prompt(prompt, self.max_prompt_tokens * CHARS_PER_TOKEN)
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
        fallback = [
            {
                "tool": "search_local_data",
                "input": {"query": question},
                "status": "pending",
                "step_index": 0,
                "description": "Search local knowledge base",
            },
        ]
        if self.crawl_enabled:
            fallback.append({
                "tool": "crawl_external_data",
                "input": {"query": question, "entity": entity},
                "status": "pending",
                "step_index": 1,
                "description": "Crawl web for data",
            })
        fallback.append({
            "tool": "reflect_findings",
            "input": {"data_key": "search_results"},
            "status": "pending",
            "step_index": len(fallback),
            "description": "Reflect on gathered data",
        })
        return fallback

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

        # Include info about discovered but not yet looked-up entities
        discovered = memory.get("_discovered_entities", [])
        searched = memory.get("_searched_entities", [])
        searched_lower = {s.lower() for s in searched} if searched else set()
        pending_entities = [
            e for e in discovered
            if e.lower() not in searched_lower
        ] if discovered else []
        entity_note = ""
        if pending_entities:
            entity_note = (
                f"\nDiscovered entities still needing individual look-up: "
                f"{json.dumps(pending_entities[:20], ensure_ascii=False)}\n"
                "If these have not all been searched for details yet, data is NOT sufficient.\n"
            )

        is_exhaustive = self._is_exhaustive_query(question)
        exhaustive_note = ""
        if is_exhaustive:
            exhaustive_note = (
                "\nIMPORTANT: The user asked for ALL/EVERY/COMPLETE data. "
                "Only mark as sufficient if the data covers a COMPREHENSIVE set of entities, "
                "not just 1-2 examples. If you see a partial list (e.g. only some GPU models "
                "or only one leader), mark as insufficient and suggest searching for the rest. "
                "Recommend SPECIFIC alternative search queries to fill gaps.\n"
            )

        prompt = f"""Analyse the following data gathered for the user question and determine:
1. Is there enough information to answer the question?
2. What is missing?
3. What should be done next?
{exhaustive_note}
{entity_note}
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

    # -- search_memory --
    @staticmethod
    def _tool_search_memory(memory: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Search through working memory for entries matching the query.

        Performs a simple keyword search across memory keys and values,
        useful when memory is too large to include fully in prompts.
        """
        query_lower = query.lower()
        matches: Dict[str, Any] = {}
        for key, value in memory.items():
            val_str = json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value
            if query_lower in key.lower() or query_lower in val_str.lower():
                matches[key] = value
        return {"matches": matches, "count": len(matches), "query": query}

    # -- eval_step_from_plan --
    def _tool_eval_step(
        self,
        step_result: Dict[str, Any],
        question: str,
        memory: Dict[str, Any],
    ) -> bool:
        """Evaluate a single step outcome – returns True if acceptable.

        Triggers INSUFFICIENT_DATA escalation (returns False) when a step
        yields no usable data, so the orchestrator can re-plan.
        """
        status = step_result.get("status", "failed")
        if status == "failed":
            return False
        tool = step_result.get("tool_name", "")
        output = step_result.get("output", {})

        if tool == "search_local_data":
            count = 0
            if isinstance(output, dict):
                count = output.get("count", 0)
            if count == 0:
                logger.info("INSUFFICIENT_DATA: search_local_data returned 0 hits")
            return count > 0

        if tool == "crawl_external_data":
            if isinstance(output, dict):
                if output.get("error") or output.get("skipped"):
                    return False
            return True

        if tool == "reflect_findings":
            if isinstance(output, dict):
                # If reflection says data is insufficient, escalate
                if output.get("sufficient") is False:
                    logger.info("INSUFFICIENT_DATA: reflect_findings says data insufficient")
                    return False
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
        # Budget: reserve half the token window for the evaluation prompt
        max_memory_chars = (self.max_prompt_tokens * CHARS_PER_TOKEN) // 2
        memory_str = self._truncate_for_prompt(
            json.dumps(memory, ensure_ascii=False, default=str), max_memory_chars
        )
        steps_done = [h for h in history if h.get("status") == "completed"]

        prompt = f"""You are evaluating whether enough data has been gathered to answer the user question.

User question: "{question}"
Memory (collected data):
{memory_str}
Steps completed: {len(steps_done)}

IMPORTANT evaluation rules:
- If the question asks for "all", "every", or "list" of something, you MUST verify that the
  data covers a COMPREHENSIVE set of entities, not just one or two examples.
- Finding only 1-2 items when the user asked for "all" is NOT sufficient.
  Return done=false and explain what categories or items are still missing.
- If the data contains a partial list (e.g. names without details), request
  detail-gathering for each listed item before declaring done.
- Only return done=true when the answer would satisfy someone who explicitly
  asked for comprehensive / exhaustive coverage.

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
                all_hits = list(result.get("hits", []))
                all_sources = list(result.get("sources", []))

                # --- Query expansion for exhaustive queries ---
                # When the user asks for "all/every/list" and initial results
                # are sparse, automatically search with variant queries to
                # gather data from multiple angles.
                is_exhaustive = self._is_exhaustive_query(question)
                hit_count = result.get("count", 0)
                if is_exhaustive and hit_count < DEFAULT_QUERY_EXPANSION_THRESHOLD:
                    variants = self._generate_query_variants(question, entity)
                    for vq in variants:
                        if vq.strip().lower() == q.strip().lower():
                            continue
                        vr = self._tool_search_local(vq, top_k, entity)
                        for h in vr.get("hits", []):
                            url = h.get("url", "")
                            if url and any(eh.get("url") == url for eh in all_hits):
                                continue
                            all_hits.append(h)
                        all_sources.extend(
                            s for s in vr.get("sources", []) if s not in all_sources
                        )
                    result = {"hits": all_hits, "sources": all_sources, "count": len(all_hits)}

                # --- Track searched entities ---
                # Record the query so we know which entities have already
                # been looked up.  This prevents the planner from
                # re-searching entities that are already in memory.
                searched: list = list(memory.get("_searched_entities", []))
                q_norm = q.strip().lower()
                if q_norm and q_norm not in [s.lower() for s in searched]:
                    searched.append(q.strip())
                    self._tool_store_memory(memory, "_searched_entities", searched)

                # --- Entity list extraction ---
                # When results contain a list of entities (e.g. GPU names,
                # person names), extract them so the planner can look up
                # details for each one individually.
                if is_exhaustive and all_hits:
                    entities_found = self._extract_entity_list_from_results(all_hits, question)
                    if entities_found:
                        # Merge with already-discovered entities and filter
                        # out any that have already been searched.
                        existing_discovered = set(memory.get("_discovered_entities", []))
                        searched_lower = {s.lower() for s in searched}
                        new_entities = [
                            e for e in entities_found
                            if e not in existing_discovered
                            and e.lower() not in searched_lower
                        ]
                        merged = list(existing_discovered | set(new_entities))
                        # Only keep entities that haven't been searched yet
                        pending = [
                            e for e in merged
                            if e.lower() not in searched_lower
                        ]
                        self._tool_store_memory(
                            memory, "_discovered_entities", pending
                        )
                        logger.info(
                            "Extracted %d entities for follow-up: %s",
                            len(pending),
                            pending[:5],
                        )

                output = result
                step_sources = result.get("sources", [])
                step_context = result.get("hits", [])
                # Auto-store to memory
                self._tool_store_memory(memory, "search_results", result.get("hits", []))

            elif tool == "crawl_external_data":
                if not self.crawl_enabled:
                    output = {"skipped": True, "reason": "Online crawling is disabled"}
                    error = "crawl_disabled"
                    logger.info("Crawl skipped – crawl_enabled=False")
                else:
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

            elif tool == "search_memory":
                q = tool_input.get("query", question)
                output = self._tool_search_memory(memory, q)

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
        max_memory_chars = (self.max_prompt_tokens * CHARS_PER_TOKEN) // 2
        memory_str = self._truncate_for_prompt(
            json.dumps(memory, ensure_ascii=False, default=str), max_memory_chars
        )
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
2. If data is insufficient, clearly state what is missing BUT still present
   every piece of relevant data you DO have – do not dismiss partial data.
3. Include references to sources where available.
4. Do NOT fabricate information.
5. When the user asked for "all" or a comprehensive list, present EVERY entity
   and detail found in memory, organized clearly (e.g. per item/person/model).
6. Combine and deduplicate information gathered from multiple search angles.
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
                        point_id,
                        vec,
                        {
                            "kind": "step_pattern",
                            "generalized_task": generalized,
                            "tool_sequence": tool_sequence,
                            "reward_score": 1.0,
                        },
                    )
        except Exception as e:
            logger.warning("Pattern storage failed (non-critical): %s", e)

    def _generalize_task(self, question: str) -> str:
        """Ask the LLM to produce a generalized reformulation of the task."""
        prompt = f"""Rewrite the following user question as a short, generalized task description 
that could match similar future questions. Remove specific names/dates but keep the intent.

Question: "{question}"
Return ONLY the generalized task description as a plain string (no JSON).
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

    def apply_reward(self, plan_id: str, reward: float) -> bool:
        """Apply user reward/debuff feedback to the plan's associated step pattern.

        Args:
            plan_id: The UUID of the completed plan.
            reward: Positive value (e.g. 1.0) to reward, negative (e.g. -1.0) to debuff.

        Returns:
            True if the pattern was updated, False otherwise.
        """
        if not hasattr(self.store, "Session"):
            return False
        try:
            with self.store.Session() as session:
                # Look up the plan to get the original question
                plan_row = session.get(ChatPlan, uuid.UUID(plan_id))
                if not plan_row:
                    logger.warning("apply_reward: plan %s not found", plan_id)
                    return False

                # Find the most recent StepPattern that was created around
                # the same time the plan completed
                from sqlalchemy import select, desc
                stmt = (
                    select(StepPattern)
                    .order_by(desc(StepPattern.last_used_at))
                    .limit(10)
                )
                patterns = session.execute(stmt).scalars().all()

                # Match by generalised task similarity (simple substring for now)
                question = plan_row.original_prompt or ""
                matched = None
                for pat in patterns:
                    gen_task = (pat.generalized_task or "").lower()
                    if gen_task and (
                        gen_task in question.lower()
                        or question.lower() in gen_task
                        or any(
                            word in gen_task
                            for word in question.lower().split()
                            if len(word) > 3
                        )
                    ):
                        matched = pat
                        break

                if not matched:
                    logger.info("apply_reward: no matching pattern for plan %s", plan_id)
                    return False

                # Apply reward / debuff
                matched.reward_score = max(0.0, matched.reward_score + reward)
                matched.times_used += 1
                if reward > 0:
                    matched.times_succeeded += 1
                matched.last_used_at = datetime.now(timezone.utc)
                session.commit()

                logger.info(
                    "apply_reward: pattern %s updated – reward_score=%.2f, "
                    "times_used=%d, times_succeeded=%d",
                    matched.id, matched.reward_score,
                    matched.times_used, matched.times_succeeded,
                )

                # Update Qdrant embedding payload if available
                if self.vector_store:
                    try:
                        vec = self.llm.embed_text(matched.generalized_task)
                        if vec:
                            self.vector_store.upsert(
                                str(matched.id),
                                vec,
                                {
                                    "kind": "step_pattern",
                                    "generalized_task": matched.generalized_task,
                                    "tool_sequence": matched.tool_sequence,
                                    "reward_score": matched.reward_score,
                                },
                            )
                    except Exception as e:
                        logger.debug("apply_reward: Qdrant update failed (non-critical): %s", e)

                return True
        except Exception as e:
            logger.warning("apply_reward failed: %s", e)
            return False

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
        status: str = "completed",
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
                        row.status = status
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
            "crawl_enabled": self.crawl_enabled,
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
            "memory_snapshot": self._safe_memory(memory),
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

    # -----------------------------------------------------------------------
    # Cancellation, persistence, event, and token-budget helpers
    # -----------------------------------------------------------------------
    def _is_cancelled(self) -> bool:
        """Check if the associated task has been cancelled by the user."""
        if not self._task_id:
            return False
        try:
            from .task_queue import TaskQueueService
            task_queue = getattr(self, "_task_queue", None)
            if task_queue and hasattr(task_queue, "is_cancelled"):
                return task_queue.is_cancelled(self._task_id)
            # Fallback: query DB directly
            if hasattr(self.store, "Session"):
                from ..database.models import Task
                with self.store.Session() as session:
                    task = session.get(Task, uuid.UUID(self._task_id))
                    return task is not None and task.status == "cancelled"
        except Exception:
            pass
        return False

    def _persist_memory(
        self,
        plan_id: str,
        memory: Dict[str, Any],
        step_index: int,
        tool_name: str,
    ) -> None:
        """Persist every memory key/value pair to the database."""
        try:
            if hasattr(self.store, "Session"):
                safe = self._safe_memory(memory)
                with self.store.Session() as session:
                    for key, value in safe.items():
                        # Upsert: delete old entry with same plan+key, then insert
                        from sqlalchemy import select, and_
                        existing = session.execute(
                            select(ChatMemoryEntry).where(
                                and_(
                                    ChatMemoryEntry.plan_id == uuid.UUID(plan_id),
                                    ChatMemoryEntry.key == key,
                                )
                            )
                        ).scalar_one_or_none()
                        if existing:
                            existing.value_json = self._safe_json(value)
                            existing.step_index = step_index
                            existing.tool_name = tool_name
                        else:
                            entry = ChatMemoryEntry(
                                plan_id=uuid.UUID(plan_id),
                                key=key,
                                value_json=self._safe_json(value),
                                step_index=step_index,
                                tool_name=tool_name,
                            )
                            session.add(entry)
                    session.commit()
        except Exception as e:
            logger.warning("Failed to persist memory entries: %s", e)

    def _emit(self, step: str, message: str, payload: Optional[Dict] = None):
        """Emit an event for UI observability."""
        try:
            from ..webapp.services.event_system import emit_event
            emit_event(step, message, payload=payload)
        except Exception:
            pass  # Event system may not be initialized

    def _report_progress(self, progress: float, message: str) -> None:
        """Report progress via the optional callback (used by task queue)."""
        if self._progress_callback:
            try:
                self._progress_callback(progress, message)
            except Exception:
                pass

    @staticmethod
    def _truncate_for_prompt(text: str, max_chars: int = 8000) -> str:
        """Truncate text to stay within token budget.

        Uses a simple char-based heuristic since exact tokenization is model-specific.
        """
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "… [truncated]"

    # -----------------------------------------------------------------------
    # Query expansion & exhaustive search helpers
    # -----------------------------------------------------------------------
    @staticmethod
    def _is_exhaustive_query(question: str) -> bool:
        """Return True when the user's question signals they want ALL results."""
        words = set(question.lower().split())
        return bool(words & EXHAUSTIVE_KEYWORDS)

    def _generate_query_variants(self, question: str, entity: str) -> List[str]:
        """Generate multiple rephrased / broadened search queries.

        This prevents early escape by ensuring the planner searches from
        several angles rather than relying on a single query.
        """
        prompt = f"""Generate 3-5 different search queries that could help answer the
following user question. Each query should approach the topic from a different
angle (e.g. broader category, specific sub-items, related terms, alternative
phrasing, corrected typos).

User question: "{question}"
Entity context: "{entity}"

Return ONLY a JSON array of query strings, for example:
["query 1", "query 2", "query 3"]
"""
        try:
            payload = {"model": self.llm.model, "prompt": prompt, "stream": False}
            resp = requests.post(self.llm.ollama_url, json=payload, timeout=30)
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            variants = self.llm.text_processor.safe_json_loads(raw, fallback=[])
            if isinstance(variants, list) and variants:
                # Deduplicate & always include original
                seen: set = set()
                unique: List[str] = []
                for v in [question] + variants:
                    vl = v.strip().lower() if isinstance(v, str) else ""
                    if vl and vl not in seen:
                        seen.add(vl)
                        unique.append(v.strip() if isinstance(v, str) else v)
                return unique[:MAX_QUERY_VARIANTS]
        except Exception as e:
            logger.debug("Query variant generation failed (non-critical): %s", e)
        return [question]

    def _extract_entity_list_from_results(
        self,
        hits: List[Dict[str, Any]],
        question: str,
    ) -> List[str]:
        """Ask the LLM to extract a list of entity names from search results.

        When the user asks for "all X", the first search often returns a page
        that *lists* many entities (e.g. GPU model names) but without details.
        This helper extracts those names so the planner can search for each one
        individually.
        """
        if not hits:
            return []

        snippets = "\n".join(
            h.get("snippet", "")[:300] for h in hits[:10] if h.get("snippet")
        )
        if not snippets.strip():
            return []

        prompt = f"""Extract a list of distinct entity names mentioned in the following search
results that are relevant to the user question. These could be product names,
person names, organization names, etc.

User question: "{question}"

Search result snippets:
{snippets}

Return ONLY a JSON array of entity name strings. If no entities are found, return [].
Example: ["RTX 3060", "RTX 3070", "RTX 3080", "RTX 3090"]
"""
        try:
            payload = {"model": self.llm.model, "prompt": prompt, "stream": False}
            resp = requests.post(self.llm.ollama_url, json=payload, timeout=30)
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            entities = self.llm.text_processor.safe_json_loads(raw, fallback=[])
            if isinstance(entities, list):
                return [e for e in entities if isinstance(e, str) and e.strip()][:MAX_EXTRACTED_ENTITIES]
        except Exception as e:
            logger.debug("Entity list extraction failed (non-critical): %s", e)
        return []
