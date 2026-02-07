"""Graph search and traversal API routes.

Provides API endpoints for:
- Hybrid SQL + semantic entity search
- Depth-based graph traversal
- Path finding between entities
"""

import logging
from flask import Blueprint, jsonify, request

from ..services.event_system import emit_event
from ...extractor.entity_merger import GraphSearchEngine, SemanticEntityDeduplicator
from ...database import models as db_models

bp_graph = Blueprint('graph_search', __name__, url_prefix='/api/graph')
logger = logging.getLogger(__name__)


def init_graph_routes(api_key_required, store, semantic_engine=None):
    """Initialize graph search and traversal routes.
    
    Args:
        api_key_required: Auth decorator
        store: SQLAlchemy store instance
        semantic_engine: Optional semantic engine for embedding-based search
    """
    
    # Initialize engines
    graph_engine = GraphSearchEngine(store.Session, semantic_engine, logger)
    deduplicator = SemanticEntityDeduplicator(store.Session, semantic_engine, logger)
    
    @bp_graph.get("/search")
    @api_key_required
    def api_graph_search():
        """
        Search entities using hybrid SQL + semantic search.
        
        Query params:
            query: Search query string
            kind: Optional entity kind filter
            threshold: Semantic similarity threshold (default: 0.7)
            limit: Maximum results (default: 20)
        
        Returns:
            List of matching entities with match type and scores
        """
        query = request.args.get("query", "").strip()
        if not query:
            return jsonify({"error": "Query parameter required"}), 400
        
        kind = request.args.get("kind")
        threshold = float(request.args.get("threshold", 0.7))
        limit = min(int(request.args.get("limit", 20)), 100)
        
        emit_event("graph_search", "start", payload={
            "query": query,
            "kind": kind,
            "threshold": threshold,
            "limit": limit,
        })
        
        try:
            results = graph_engine.search_entities(
                query=query,
                kind=kind,
                semantic_threshold=threshold,
                limit=limit,
            )
            
            emit_event("graph_search", f"found {len(results)} results")
            
            return jsonify({
                "query": query,
                "total": len(results),
                "results": results,
            })
        except Exception as e:
            emit_event("graph_search", f"failed: {e}", level="error")
            logger.exception("Graph search failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_graph.post("/traverse")
    @api_key_required
    def api_graph_traverse():
        """
        Traverse the entity graph from starting entities.
        
        Request body (JSON):
            entity_ids: List of starting entity UUIDs
            max_depth: Maximum traversal depth (default: 2)
            top_n_per_depth: Top N entities per depth level (default: 10)
            relation_types: Optional list of relation types to filter
        
        Returns:
            Graph structure with entities and relationships at each depth
        """
        body = request.get_json(silent=True) or {}
        
        entity_ids = body.get("entity_ids", [])
        if not entity_ids:
            return jsonify({"error": "entity_ids required"}), 400
        
        max_depth = int(body.get("max_depth", 2))
        top_n = int(body.get("top_n_per_depth", 10))
        relation_types = body.get("relation_types")
        
        emit_event("graph_traverse", "start", payload={
            "entity_ids": entity_ids,
            "max_depth": max_depth,
            "top_n": top_n,
        })
        
        try:
            result = graph_engine.traverse_graph(
                entity_ids=entity_ids,
                max_depth=max_depth,
                top_n_per_depth=top_n,
                relation_types=relation_types,
            )
            
            total_entities = len(result.get("root_entities", []))
            for depth_data in result.get("depths", {}).values():
                total_entities += depth_data.get("entity_count", 0)
            
            emit_event("graph_traverse", f"found {total_entities} entities across {max_depth} depths")
            
            return jsonify(result)
        except Exception as e:
            emit_event("graph_traverse", f"failed: {e}", level="error")
            logger.exception("Graph traversal failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_graph.get("/path")
    @api_key_required
    def api_graph_path():
        """
        Find the shortest path between two entities.
        
        Query params:
            source_id: Source entity UUID
            target_id: Target entity UUID
            max_depth: Maximum path length (default: 5)
        
        Returns:
            List of path steps (entities and relationships)
        """
        source_id = request.args.get("source_id")
        target_id = request.args.get("target_id")
        
        if not source_id or not target_id:
            return jsonify({"error": "source_id and target_id required"}), 400
        
        max_depth = int(request.args.get("max_depth", 5))
        
        emit_event("graph_path", "start", payload={
            "source_id": source_id,
            "target_id": target_id,
            "max_depth": max_depth,
        })
        
        try:
            path = graph_engine.find_path(
                source_id=source_id,
                target_id=target_id,
                max_depth=max_depth,
            )
            
            if path is None:
                return jsonify({
                    "found": False,
                    "message": "No path found between entities",
                    "source_id": source_id,
                    "target_id": target_id,
                })
            
            emit_event("graph_path", f"found path with {len(path)} steps")
            
            return jsonify({
                "found": True,
                "path_length": len(path),
                "path": path,
            })
        except Exception as e:
            emit_event("graph_path", f"failed: {e}", level="error")
            logger.exception("Graph path finding failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_graph.get("/semantic-duplicates")
    @api_key_required
    def api_semantic_duplicates():
        """
        Find semantically similar entities (potential duplicates).
        
        Query params:
            name: Entity name to find duplicates for
            kind: Optional entity kind filter
            threshold: Similarity threshold (default: 0.85)
            limit: Maximum results (default: 10)
        
        Returns:
            List of similar entities with similarity scores
        """
        name = request.args.get("name", "").strip()
        if not name:
            return jsonify({"error": "name parameter required"}), 400
        
        kind = request.args.get("kind")
        threshold = float(request.args.get("threshold", 0.85))
        limit = min(int(request.args.get("limit", 10)), 50)
        
        emit_event("semantic_duplicates", "start", payload={
            "name": name,
            "kind": kind,
            "threshold": threshold,
        })
        
        try:
            results = deduplicator.find_semantic_duplicates(
                name=name,
                kind=kind,
                threshold=threshold,
                max_results=limit,
            )
            
            emit_event("semantic_duplicates", f"found {len(results)} potential duplicates")
            
            return jsonify({
                "query_name": name,
                "threshold": threshold,
                "total": len(results),
                "duplicates": results,
            })
        except Exception as e:
            emit_event("semantic_duplicates", f"failed: {e}", level="error")
            logger.exception("Semantic duplicate search failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_graph.post("/dedupe-scan")
    @api_key_required
    def api_dedupe_scan():
        """
        Scan database for duplicate entities.
        
        Request body (JSON):
            threshold: Similarity threshold (default: 0.9)
            kind: Optional entity kind to limit scan
            merge: If true, actually merge duplicates (default: false)
        
        Returns:
            Report with duplicate groups found and merge actions
        """
        body = request.get_json(silent=True) or {}
        
        threshold = float(body.get("threshold", 0.9))
        kind = body.get("kind")
        merge = bool(body.get("merge", False))
        
        emit_event("dedupe_scan", "start", payload={
            "threshold": threshold,
            "kind": kind,
            "merge": merge,
        })
        
        try:
            report = deduplicator.deduplicate_entities(
                dry_run=not merge,
                threshold=threshold,
                kind=kind,
            )
            
            dup_count = len(report.get("duplicates_found", []))
            merge_count = len(report.get("merged", []))
            
            emit_event("dedupe_scan", f"found {dup_count} duplicate groups, merged {merge_count}")
            
            return jsonify({
                "dry_run": not merge,
                "threshold": threshold,
                "kind": kind,
                "duplicates_found": dup_count,
                "merged_count": merge_count,
                "report": report,
            })
        except Exception as e:
            emit_event("dedupe_scan", f"failed: {e}", level="error")
            logger.exception("Deduplication scan failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_graph.post("/merge-entities")
    @api_key_required
    def api_merge_entities():
        """
        Merge two entities.
        
        Request body (JSON):
            source_id: Source entity UUID (to be deleted)
            target_id: Target entity UUID (to keep)
        
        Returns:
            Success status
        """
        body = request.get_json(silent=True) or {}
        
        source_id = body.get("source_id")
        target_id = body.get("target_id")
        
        if not source_id or not target_id:
            return jsonify({"error": "source_id and target_id required"}), 400
        
        emit_event("merge_entities", "start", payload={
            "source_id": source_id,
            "target_id": target_id,
        })
        
        try:
            success = deduplicator.merge_entities(source_id, target_id)
            
            if success:
                emit_event("merge_entities", "success")
                return jsonify({
                    "status": "ok",
                    "message": "Entities merged successfully",
                    "source_id": source_id,
                    "target_id": target_id,
                })
            else:
                emit_event("merge_entities", "failed", level="error")
                return jsonify({"error": "Merge failed"}), 500
        except Exception as e:
            emit_event("merge_entities", f"failed: {e}", level="error")
            logger.exception("Entity merge failed")
            return jsonify({"error": str(e)}), 500
    
    return bp_graph
