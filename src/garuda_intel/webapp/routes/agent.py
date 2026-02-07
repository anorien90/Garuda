"""
Agent API routes for intelligent data exploration and refinement.

Provides endpoints for:
- Reflect & Refine mode: Entity merging and data quality
- Explore & Prioritize mode: Entity graph exploration
- Multidimensional RAG search
- Async chat with agent capabilities
"""

import logging
from flask import Blueprint, jsonify, request
from typing import Optional

from ..services.event_system import emit_event

bp_agent = Blueprint('agent', __name__, url_prefix='/api/agent')
logger = logging.getLogger(__name__)


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
        
        Returns:
            Report of merge operations and data quality findings
        """
        body = request.get_json(silent=True) or {}
        
        target_entities = body.get("target_entities")
        dry_run = body.get("dry_run", True)  # Default to dry run for safety
        
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
        
        Returns:
            Exploration report with prioritized entities for further research
        """
        body = request.get_json(silent=True) or {}
        
        root_entities = body.get("root_entities", [])
        if not root_entities:
            return jsonify({"error": "root_entities required"}), 400
        
        max_depth = int(body.get("max_depth", 3))
        top_n = int(body.get("top_n", 20))
        
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
        
        Request body (JSON):
            question: User question (required)
            entity: Optional entity context
        
        Returns:
            Chat response with answer and context
        """
        import asyncio
        
        body = request.get_json(silent=True) or {}
        
        question = body.get("question", "").strip()
        if not question:
            return jsonify({"error": "question required"}), 400
        
        entity = body.get("entity")
        
        emit_event("agent", "chat started", payload={
            "mode": "deep_rag",
            "question": question[:100],
            "entity": entity,
        })
        
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
            "modes": ["deep_rag"],
            "config": {
                "max_exploration_depth": getattr(settings, 'agent_max_exploration_depth', 3),
                "entity_merge_threshold": getattr(settings, 'agent_entity_merge_threshold', 0.85),
                "priority_unknown_weight": getattr(settings, 'agent_priority_unknown_weight', 0.7),
                "priority_relation_weight": getattr(settings, 'agent_priority_relation_weight', 0.3),
            },
            "components": {
                "llm_available": llm is not None,
                "vector_store_available": vector_store is not None,
            },
        })
    
    return bp_agent
