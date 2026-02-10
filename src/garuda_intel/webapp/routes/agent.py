"""
Agent API routes for intelligent data exploration and refinement.

Provides endpoints for:
- Reflect & Refine mode: Entity merging and data quality
- Explore & Prioritize mode: Entity graph exploration
- Multidimensional RAG search
- Async chat with agent capabilities

All long-running endpoints support `queued: true` in the request body
to submit the operation to the persistent task queue instead of executing
synchronously. This protects the Ollama instance and provides persistent
task tracking.
"""

import logging
from flask import Blueprint, jsonify, request, current_app
from typing import Optional

from ..services.event_system import emit_event

bp_agent = Blueprint('agent', __name__, url_prefix='/api/agent')
logger = logging.getLogger(__name__)


def _get_task_queue():
    """Get the task queue service from the app context."""
    try:
        from ..app import task_queue
        return task_queue
    except Exception:
        return None


def init_agent_routes(api_key_required, settings, store, llm, vector_store):
    """Initialize agent routes.
    
    Args:
        api_key_required: Auth decorator
        settings: Application settings
        store: SQLAlchemy store instance
        llm: LLM extractor instance
        vector_store: Vector store instance (optional)
    """
    # Initialize agent service
    from ...services.agent_service import AgentService
    
    agent = AgentService(
        store=store,
        llm=llm,
        vector_store=vector_store,
        entity_merge_threshold=getattr(settings, 'agent_entity_merge_threshold', 0.85),
        max_exploration_depth=getattr(settings, 'agent_max_exploration_depth', 3),
        priority_unknown_weight=getattr(settings, 'agent_priority_unknown_weight', 0.7),
        priority_relation_weight=getattr(settings, 'agent_priority_relation_weight', 0.3),
    )
    
    @bp_agent.post("/reflect")
    @api_key_required
    def api_agent_reflect():
        """
        Reflect & Refine mode: Analyze and merge entities, validate data quality.
        
        Request body (JSON):
            target_entities: Optional list of entity names to focus on
            dry_run: If true, only report without making changes (default: true)
            queued: If true, submit to task queue (default: false)
        
        Returns:
            Report of merge operations and data quality findings,
            or task submission confirmation if queued
        """
        body = request.get_json(silent=True) or {}
        
        target_entities = body.get("target_entities")
        dry_run = body.get("dry_run", True)  # Default to dry run for safety
        
        # Support queued execution
        if body.get("queued"):
            tq = _get_task_queue()
            if tq:
                from ...services.task_queue import TaskQueueService
                task_id = tq.submit(TaskQueueService.TASK_AGENT_REFLECT, {
                    "target_entities": target_entities,
                    "dry_run": dry_run,
                })
                return jsonify({"task_id": task_id, "status": "pending", "message": "Reflect task queued"}), 202
        
        emit_event("agent", "reflect mode started", payload={
            "target_entities": target_entities,
            "dry_run": dry_run,
        })
        
        try:
            report = agent.reflect_and_refine(
                target_entities=target_entities,
                dry_run=dry_run,
            )
            
            emit_event("agent", "reflect mode completed", payload={
                "merges": report["statistics"]["merges_performed"],
                "issues": report["statistics"]["quality_issues_found"],
            })
            
            return jsonify(report)
            
        except Exception as e:
            emit_event("agent", f"reflect mode failed: {e}", level="error")
            logger.exception("Reflect mode failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_agent.post("/explore")
    @api_key_required
    def api_agent_explore():
        """
        Explore & Prioritize mode: Analyze entity graph and find high-priority entities.
        
        Request body (JSON):
            root_entities: List of starting entity names (required)
            max_depth: Maximum relation depth to explore (default: 3)
            top_n: Number of top-priority entities to return (default: 20)
            queued: If true, submit to task queue (default: false)
        
        Returns:
            Exploration report with prioritized entities for further research,
            or task submission confirmation if queued
        """
        body = request.get_json(silent=True) or {}
        
        root_entities = body.get("root_entities", [])
        if not root_entities:
            return jsonify({"error": "root_entities required"}), 400
        
        max_depth = int(body.get("max_depth", 3))
        top_n = int(body.get("top_n", 20))
        
        # Support queued execution
        if body.get("queued"):
            tq = _get_task_queue()
            if tq:
                from ...services.task_queue import TaskQueueService
                task_id = tq.submit(TaskQueueService.TASK_AGENT_EXPLORE, {
                    "root_entities": root_entities,
                    "max_depth": max_depth,
                    "top_n": top_n,
                })
                return jsonify({"task_id": task_id, "status": "pending", "message": "Explore task queued"}), 202
        
        emit_event("agent", "explore mode started", payload={
            "root_entities": root_entities,
            "max_depth": max_depth,
            "top_n": top_n,
        })
        
        try:
            report = agent.explore_and_prioritize(
                root_entities=root_entities,
                max_depth=max_depth,
                top_n=top_n,
            )
            
            emit_event("agent", "explore mode completed", payload={
                "unique_entities": report["statistics"]["unique_entities"],
                "prioritized_count": len(report["prioritized_entities"]),
            })
            
            return jsonify(report)
            
        except Exception as e:
            emit_event("agent", f"explore mode failed: {e}", level="error")
            logger.exception("Explore mode failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_agent.post("/search")
    @api_key_required
    def api_agent_search():
        """
        Multidimensional RAG search combining embedding and graph-based search.
        
        Request body (JSON):
            query: Search query string (required)
            top_k: Number of results to return (default: 10)
            include_graph: Whether to include graph traversal (default: true)
            graph_depth: Depth for graph traversal (default: 2)
        
        Returns:
            Combined search results with source information
        """
        body = request.get_json(silent=True) or {}
        
        query = body.get("query", "").strip()
        if not query:
            return jsonify({"error": "query required"}), 400
        
        top_k = int(body.get("top_k", 10))
        include_graph = body.get("include_graph", True)
        graph_depth = int(body.get("graph_depth", 2))
        
        emit_event("agent", "multidimensional search started", payload={
            "query": query[:100],
            "top_k": top_k,
            "include_graph": include_graph,
        })
        
        try:
            result = agent.multidimensional_search(
                query=query,
                top_k=top_k,
                include_graph=include_graph,
                graph_depth=graph_depth,
            )
            
            emit_event("agent", "multidimensional search completed", payload={
                "embedding_hits": result["statistics"]["embedding_hits"],
                "graph_hits": result["statistics"]["graph_hits"],
                "unique_results": result["statistics"]["unique_results"],
            })
            
            return jsonify(result)
            
        except Exception as e:
            emit_event("agent", f"multidimensional search failed: {e}", level="error")
            logger.exception("Multidimensional search failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_agent.post("/chat")
    @api_key_required
    def api_agent_chat():
        """
        Async chat with deep RAG search (embedding + graph + SQL).
        
        Both embedding and graph search modes are always enabled automatically.
        When use_planner is true (default), uses the dynamic task planner.
        
        Request body (JSON):
            question: User question (required)
            entity: Optional entity context
            use_planner: Use dynamic task planner (default: true)
            queued: If true, submit to task queue (default: false)
        
        Returns:
            Chat response with answer and context,
            or task submission confirmation if queued
        """
        import asyncio
        
        body = request.get_json(silent=True) or {}
        
        question = body.get("question", "").strip()
        if not question:
            return jsonify({"error": "question required"}), 400
        
        entity = body.get("entity")
        use_planner = body.get("use_planner", True)
        
        # Support queued execution
        if body.get("queued"):
            tq = _get_task_queue()
            if tq:
                from ...services.task_queue import TaskQueueService
                task_id = tq.submit(TaskQueueService.TASK_AGENT_CHAT, {
                    "question": question,
                    "entity": entity,
                    "use_planner": use_planner,
                }, priority=5)  # Higher priority for chat
                return jsonify({"task_id": task_id, "status": "pending", "message": "Chat task queued"}), 202
        
        emit_event("agent", "chat started", payload={
            "mode": "task_planner" if use_planner else "deep_rag",
            "question": question[:100],
            "entity": entity,
        })
        
        # --- Dynamic task planner path ---
        if use_planner:
            try:
                from ...services.task_planner import TaskPlanner
                planner = TaskPlanner(
                    store=store,
                    llm=llm,
                    vector_store=vector_store,
                    settings=settings,
                )
                result = planner.run(
                    question=question,
                    entity=entity or "",
                )
                emit_event("agent", "task planner chat completed", payload={
                    "plan_id": result.get("plan_id"),
                    "steps": result.get("total_steps_executed"),
                })
                return jsonify(result)
            except Exception as e:
                logger.warning(f"Task planner failed, falling back to legacy: {e}")
                emit_event("agent", f"Task planner error – legacy fallback: {e}", level="warning")
        
        try:
            # Run async function in event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                response = loop.run_until_complete(
                    agent.chat_async(
                        question=question,
                        entity=entity,
                    )
                )
            finally:
                loop.close()
            
            emit_event("agent", "chat completed", payload={
                "mode": "deep_rag",
                "has_answer": bool(response.get("answer")),
                "context_count": len(response.get("context", [])),
            })
            
            return jsonify(response)
            
        except Exception as e:
            emit_event("agent", f"chat failed: {e}", level="error")
            logger.exception("Agent chat failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_agent.post("/autonomous")
    @api_key_required
    def api_agent_autonomous():
        """
        Run autonomous discovery cycle.

        Finds dead-end entities, knowledge gaps, generates crawl plans,
        and optionally triggers crawls.

        Request body (JSON):
            max_entities: Max entities to process (default: 10)
            priority_threshold: Min priority score (default: 0.3)
            max_depth: Max graph traversal depth (default: 3)
            auto_crawl: Whether to trigger crawls (default: false)
            max_pages: Max pages per crawl (default: 25)
            queued: If true, submit to task queue (default: false)

        Returns:
            Discovery report with dead-ends, gaps, plans, and results,
            or task submission confirmation if queued
        """
        body = request.get_json(silent=True) or {}

        max_entities = int(body.get("max_entities", 10))
        priority_threshold = float(body.get("priority_threshold", 0.3))
        max_depth = int(body.get("max_depth", 3))
        auto_crawl = body.get("auto_crawl", False)
        max_pages = int(body.get("max_pages", 25))

        # Support queued execution
        if body.get("queued"):
            tq = _get_task_queue()
            if tq:
                from ...services.task_queue import TaskQueueService
                task_id = tq.submit(TaskQueueService.TASK_AGENT_AUTONOMOUS, {
                    "max_entities": max_entities,
                    "priority_threshold": priority_threshold,
                    "max_depth": max_depth,
                    "auto_crawl": auto_crawl,
                    "max_pages": max_pages,
                })
                return jsonify({"task_id": task_id, "status": "pending", "message": "Autonomous task queued"}), 202

        emit_event("agent", "autonomous discovery started", payload={
            "max_entities": max_entities,
            "priority_threshold": priority_threshold,
            "auto_crawl": auto_crawl,
        })

        try:
            shutdown_mgr = current_app.config.get('shutdown_manager')
            if shutdown_mgr and shutdown_mgr.is_shutting_down():
                return jsonify({"error": "Server is shutting down", "shutdown": True}), 503
            
            report = agent.autonomous_discover(
                max_entities=max_entities,
                priority_threshold=priority_threshold,
                max_depth=max_depth,
                auto_crawl=auto_crawl,
                max_pages=max_pages,
            )

            emit_event("agent", "autonomous discovery completed", payload={
                "dead_ends": report["statistics"]["dead_ends_found"],
                "gaps": report["statistics"]["gaps_found"],
                "plans": report["statistics"]["crawl_plans_generated"],
                "crawls": report["statistics"]["crawls_executed"],
            })

            return jsonify(report)

        except Exception as e:
            emit_event("agent", f"autonomous discovery failed: {e}", level="error")
            logger.exception("Autonomous discovery failed")
            return jsonify({"error": str(e)}), 500

    @bp_agent.post("/autonomous/reflect-relate")
    @api_key_required
    def api_agent_reflect_relate():
        """
        Reflect & Relate: Find indirect connections and create investigation tasks.
        
        Request body (JSON):
            - target_entities (list, optional): Entity names to focus on
            - max_depth (int, optional): Maximum graph traversal depth (default: 2)
            - top_n (int, optional): Maximum potential relations to suggest (default: 20)
            - queued (bool, optional): Submit to task queue (default: false)
        
        Returns:
            Report with reflection results, potential relations, and investigation tasks,
            or task submission confirmation if queued
        """
        body = request.get_json(silent=True) or {}
        target_entities = body.get("target_entities")
        max_depth = int(body.get("max_depth", 2))
        top_n = int(body.get("top_n", 20))
        
        # Support queued execution
        if body.get("queued"):
            tq = _get_task_queue()
            if tq:
                from ...services.task_queue import TaskQueueService
                task_id = tq.submit(TaskQueueService.TASK_AGENT_REFLECT_RELATE, {
                    "target_entities": target_entities,
                    "max_depth": max_depth,
                    "top_n": top_n,
                })
                return jsonify({"task_id": task_id, "status": "pending", "message": "Reflect-relate task queued"}), 202
        
        emit_event("agent", "reflect-relate started", payload={"target_entities": target_entities})
        try:
            report = agent.reflect_relate(
                target_entities=target_entities,
                max_depth=max_depth,
                top_n=top_n
            )
            emit_event("agent", "reflect-relate completed", payload=report.get("statistics", {}))
            return jsonify(report)
        except Exception as e:
            emit_event("agent", f"reflect-relate failed: {e}", level="error")
            logger.exception("Reflect-relate failed")
            return jsonify({"error": str(e)}), 500

    @bp_agent.post("/autonomous/investigate-crawl")
    @api_key_required
    def api_agent_investigate_crawl():
        """
        Investigate Crawl: Execute crawls based on investigation tasks.
        
        Request body (JSON):
            - investigation_tasks (list, optional): List of investigation task dicts
            - max_entities (int, optional): Maximum entities to crawl (default: 10)
            - max_pages (int, optional): Maximum pages per crawl (default: 25)
            - max_depth (int, optional): Maximum crawl depth (default: 3)
            - priority_threshold (float, optional): Minimum task priority (default: 0.3)
            - queued (bool, optional): Submit to task queue (default: false)
        
        Returns:
            Report with crawl plans and results,
            or task submission confirmation if queued
        """
        body = request.get_json(silent=True) or {}
        investigation_tasks = body.get("investigation_tasks")
        max_entities = int(body.get("max_entities", 10))
        max_pages = int(body.get("max_pages", 25))
        max_depth = int(body.get("max_depth", 3))
        priority_threshold = float(body.get("priority_threshold", 0.3))
        
        # Support queued execution
        if body.get("queued"):
            tq = _get_task_queue()
            if tq:
                from ...services.task_queue import TaskQueueService
                task_id = tq.submit(TaskQueueService.TASK_AGENT_INVESTIGATE, {
                    "investigation_tasks": investigation_tasks,
                    "max_entities": max_entities,
                    "max_pages": max_pages,
                    "max_depth": max_depth,
                    "priority_threshold": priority_threshold,
                })
                return jsonify({"task_id": task_id, "status": "pending", "message": "Investigate task queued"}), 202
        
        emit_event("agent", "investigate-crawl started")
        try:
            report = agent.investigate_crawl(
                investigation_tasks=investigation_tasks,
                max_entities=max_entities,
                max_pages=max_pages,
                max_depth=max_depth,
                priority_threshold=priority_threshold
            )
            emit_event("agent", "investigate-crawl completed", payload=report.get("statistics", {}))
            return jsonify(report)
        except Exception as e:
            emit_event("agent", f"investigate-crawl failed: {e}", level="error")
            logger.exception("Investigate-crawl failed")
            return jsonify({"error": str(e)}), 500

    @bp_agent.post("/autonomous/combined")
    @api_key_required
    def api_agent_combined_autonomous():
        """
        Combined Autonomous: Run reflect_relate then investigate_crawl.
        
        Request body (JSON):
            - target_entities (list, optional): Entity names to focus on
            - max_entities (int, optional): Maximum entities to crawl (default: 10)
            - max_pages (int, optional): Maximum pages per crawl (default: 25)
            - max_depth (int, optional): Maximum crawl depth (default: 3)
            - priority_threshold (float, optional): Minimum task priority (default: 0.3)
            - queued (bool, optional): Submit to task queue (default: false)
        
        Returns:
            Combined report with both sub-reports,
            or task submission confirmation if queued
        """
        body = request.get_json(silent=True) or {}
        target_entities = body.get("target_entities")
        max_entities = int(body.get("max_entities", 10))
        max_pages = int(body.get("max_pages", 25))
        max_depth = int(body.get("max_depth", 3))
        priority_threshold = float(body.get("priority_threshold", 0.3))
        
        # Support queued execution
        if body.get("queued"):
            tq = _get_task_queue()
            if tq:
                from ...services.task_queue import TaskQueueService
                task_id = tq.submit(TaskQueueService.TASK_AGENT_COMBINED, {
                    "target_entities": target_entities,
                    "max_entities": max_entities,
                    "max_pages": max_pages,
                    "max_depth": max_depth,
                    "priority_threshold": priority_threshold,
                })
                return jsonify({"task_id": task_id, "status": "pending", "message": "Combined task queued"}), 202
        
        emit_event("agent", "combined-autonomous started")
        try:
            report = agent.combined_autonomous(
                target_entities=target_entities,
                max_entities=max_entities,
                max_pages=max_pages,
                max_depth=max_depth,
                priority_threshold=priority_threshold
            )
            emit_event("agent", "combined-autonomous completed", payload=report.get("statistics", {}))
            return jsonify(report)
        except Exception as e:
            emit_event("agent", f"combined-autonomous failed: {e}", level="error")
            logger.exception("Combined-autonomous failed")
            return jsonify({"error": str(e)}), 500

    @bp_agent.post("/autonomous/stop")
    @api_key_required
    def api_agent_stop_process():
        """
        Stop a running autonomous process.
        
        Request body (JSON):
            - process_id (str, required): ID of the process to stop
        
        Returns:
            Result dict with success or error
        """
        body = request.get_json(silent=True) or {}
        process_id = body.get("process_id")
        if not process_id:
            return jsonify({"error": "process_id required"}), 400
        
        emit_event("agent", f"stop-process requested: {process_id}")
        result = agent.stop_process(process_id)
        return jsonify(result)

    @bp_agent.get("/autonomous/processes")
    @api_key_required
    def api_agent_processes():
        """
        Get status of all running/completed processes.
        
        Returns:
            Dict with list of process statuses
        """
        return jsonify(agent.get_process_status())

    @bp_agent.get("/status")
    @api_key_required
    def api_agent_status():
        """
        Get agent service status and configuration.
        
        Returns:
            Agent configuration and availability status
        """
        return jsonify({
            "enabled": getattr(settings, 'agent_enabled', True),
            "modes": ["deep_rag", "reflect_relate", "investigate_crawl", "combined_autonomous", "autonomous_discover"],
            "config": {
                "max_exploration_depth": getattr(settings, 'agent_max_exploration_depth', 3),
                "entity_merge_threshold": getattr(settings, 'agent_entity_merge_threshold', 0.85),
                "priority_unknown_weight": getattr(settings, 'agent_priority_unknown_weight', 0.7),
                "priority_relation_weight": getattr(settings, 'agent_priority_relation_weight', 0.3),
            },
            "autonomous": {
                "enabled": getattr(settings, 'agent_autonomous_enabled', False),
                "interval": getattr(settings, 'agent_autonomous_interval', 300),
                "max_entities": getattr(settings, 'agent_autonomous_max_entities', 10),
                "priority_threshold": getattr(settings, 'agent_autonomous_priority_threshold', 0.3),
                "max_depth": getattr(settings, 'agent_autonomous_max_depth', 3),
                "auto_crawl": getattr(settings, 'agent_autonomous_auto_crawl', False),
                "max_pages": getattr(settings, 'agent_autonomous_max_pages', 25),
            },
            "components": {
                "llm_available": llm is not None,
                "vector_store_available": vector_store is not None,
            },
        })
    
    return bp_agent
