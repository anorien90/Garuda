"""Relationship management API routes."""

import logging
from flask import Blueprint, jsonify, request
from ..services.event_system import emit_event


bp = Blueprint('relationships', __name__, url_prefix='/api/relationships')
logger = logging.getLogger(__name__)


def init_routes(api_key_required, relationship_manager):
    """Initialize routes with required dependencies."""
    
    @bp.get("/graph")
    @api_key_required
    def api_relationship_graph():
        """Get relationship graph for entities."""
        entity_ids_raw = request.args.get("entity_ids", "")
        min_confidence = float(request.args.get("min_confidence", 0.0))
        
        entity_ids = [eid.strip() for eid in entity_ids_raw.split(",") if eid.strip()]
        
        if not entity_ids:
            return jsonify({"error": "entity_ids parameter required"}), 400
        
        try:
            graph_data = relationship_manager.get_relationship_graph(
                entity_ids=entity_ids,
                min_confidence=min_confidence
            )
            return jsonify(graph_data)
        except Exception as e:
            logger.exception("Relationship graph generation failed")
            return jsonify({"error": str(e)}), 500
    
    @bp.post("/infer")
    @api_key_required
    def api_infer_relationships():
        """Infer relationships between entities."""
        body = request.get_json(silent=True) or {}
        entity_ids = body.get("entity_ids", [])
        context = body.get("context")
        
        if not entity_ids:
            return jsonify({"error": "entity_ids required"}), 400
        
        emit_event("infer_relationships", f"inferring relationships for {len(entity_ids)} entities")
        
        try:
            inferred = relationship_manager.infer_relationships(entity_ids, context=context)
            emit_event("infer_relationships", f"inferred {len(inferred)} relationships")
            
            return jsonify({
                "inferred_count": len(inferred),
                "relationships": [
                    {
                        "source_id": str(r[0]),
                        "target_id": str(r[1]),
                        "relation_type": r[2],
                        "confidence": r[3]
                    }
                    for r in inferred
                ]
            })
        except Exception as e:
            emit_event("infer_relationships", f"failed: {e}", level="error")
            logger.exception("Relationship inference failed")
            return jsonify({"error": str(e)}), 500
    
    @bp.post("/validate")
    @api_key_required
    def api_validate_relationships():
        """Validate and fix relationship integrity."""
        body = request.get_json(silent=True) or {}
        fix_invalid = body.get("fix_invalid", True)
        
        emit_event("validate_relationships", "validating relationships")
        
        try:
            report = relationship_manager.validate_relationships(fix_invalid=fix_invalid)
            emit_event("validate_relationships", f"validation complete: {report['valid']}/{report['total']} valid")
            return jsonify(report)
        except Exception as e:
            emit_event("validate_relationships", f"failed: {e}", level="error")
            logger.exception("Relationship validation failed")
            return jsonify({"error": str(e)}), 500
    
    @bp.post("/deduplicate")
    @api_key_required
    def api_deduplicate_relationships():
        """Deduplicate relationships."""
        emit_event("deduplicate_relationships", "deduplicating relationships")
        
        try:
            removed = relationship_manager.deduplicate_relationships()
            emit_event("deduplicate_relationships", f"removed {removed} duplicates")
            return jsonify({"removed_count": removed})
        except Exception as e:
            emit_event("deduplicate_relationships", f"failed: {e}", level="error")
            logger.exception("Relationship deduplication failed")
            return jsonify({"error": str(e)}), 500
    
    @bp.post("/backfill-types")
    @api_key_required
    def api_backfill_relationship_types():
        """Backfill source_type and target_type for existing relationships.
        
        This endpoint is useful for migrating old relationships that were created
        before the type tracking feature was added. It queries the entries table
        to determine the actual type of each source/target node and updates the
        relationship records.
        """
        emit_event("backfill_relationship_types", "backfilling relationship types")
        
        try:
            updated = relationship_manager.backfill_relationship_types()
            emit_event("backfill_relationship_types", f"updated {updated} relationships")
            return jsonify({
                "updated_count": updated,
                "message": f"Successfully backfilled types for {updated} relationships"
            })
        except Exception as e:
            emit_event("backfill_relationship_types", f"failed: {e}", level="error")
            logger.exception("Relationship type backfill failed")
            return jsonify({"error": str(e)}), 500
    
    @bp.get("/clusters")
    @api_key_required
    def api_relationship_clusters():
        """Get entity clusters by relationship type."""
        relation_types_raw = request.args.get("relation_types", "")
        relation_types = [rt.strip() for rt in relation_types_raw.split(",") if rt.strip()] or None
        
        try:
            clusters = relationship_manager.cluster_entities_by_relation(relation_types=relation_types)
            
            return jsonify({
                "clusters": {
                    rel_type: [{"source": str(a), "target": str(b)} for a, b in pairs]
                    for rel_type, pairs in clusters.items()
                }
            })
        except Exception as e:
            logger.exception("Relationship clustering failed")
            return jsonify({"error": str(e)}), 500
    
    return bp
