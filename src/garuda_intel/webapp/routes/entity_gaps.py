"""Entity gap analysis routes - identify missing data fields."""
import logging
from flask import Blueprint, jsonify, request

from ..services.event_system import emit_event


bp_gaps = Blueprint('entity_gaps', __name__, url_prefix='/api/entities')
logger = logging.getLogger(__name__)


def init_gaps_routes(api_key_required, gap_analyzer, adaptive_crawler):
    """Initialize gap analysis routes."""
    
    @bp_gaps.route("/<entity_id>/gaps", methods=["GET"])
    @api_key_required
    def api_entity_gaps(entity_id):
        """Analyze data gaps for a specific entity (legacy endpoint)."""
        emit_event("entity_gaps", f"analyzing entity {entity_id}")
        try:
            # Note: This delegates to entity_crawler which may not be gap_analyzer
            # Keeping for backward compatibility
            from ...search import entity_crawler
            gaps = entity_crawler.analyze_entity_gaps(entity_id)
            return jsonify(gaps)
        except Exception as e:
            emit_event("entity_gaps", f"failed: {e}", level="error")
            logger.exception("Entity gap analysis failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_gaps.route("/<entity_id>/analyze_gaps", methods=["GET"])
    @api_key_required
    def api_entity_analyze_gaps(entity_id):
        """Analyze an entity to identify missing data fields."""
        emit_event("entity_gaps_analysis", f"Analyzing gaps for entity {entity_id}")
        
        try:
            analysis = gap_analyzer.analyze_entity_gaps(entity_id)
            
            emit_event(
                "entity_gaps_analysis",
                f"Analysis complete - {len(analysis.get('missing_fields', []))} gaps found",
                level="info",
                payload={"entity_id": entity_id, "completeness": analysis.get("completeness_score")}
            )
            
            return jsonify(analysis)
        except Exception as e:
            logger.exception(f"Gap analysis failed for entity {entity_id}")
            emit_event("entity_gaps_analysis", f"Error: {str(e)}", level="error")
            return jsonify({"error": str(e)}), 500
    
    @bp_gaps.route("/analyze_all_gaps", methods=["GET"])
    @api_key_required
    def api_entities_analyze_all_gaps():
        """Analyze all entities to find those with critical data gaps."""
        limit = min(int(request.args.get("limit", 50) or 50), 200)
        
        emit_event("bulk_gap_analysis", f"Analyzing gaps for up to {limit} entities")
        
        try:
            results = gap_analyzer.analyze_all_entities(limit=limit)
            
            emit_event(
                "bulk_gap_analysis",
                f"Analyzed {len(results)} entities",
                level="info",
                payload={"count": len(results)}
            )
            
            return jsonify({
                "count": len(results),
                "entities": results
            })
        except Exception as e:
            logger.exception("Bulk gap analysis failed")
            emit_event("bulk_gap_analysis", f"Error: {str(e)}", level="error")
            return jsonify({"error": str(e)}), 500
    
    @bp_gaps.route("/<entity_id>/infer_from_relationships", methods=["POST"])
    @api_key_required
    def api_entity_infer_from_relationships(entity_id):
        """Use related entities to infer missing data for target entity."""
        hops = int(request.args.get("hops", 1) or 1)
        
        emit_event(
            "cross_entity_inference",
            f"Inferring data for entity {entity_id} via relationships",
            payload={"entity_id": entity_id, "hops": hops}
        )
        
        try:
            inferences = adaptive_crawler.cross_entity_inference(
                entity_id=entity_id,
                relationship_hops=hops
            )
            
            emit_event(
                "cross_entity_inference",
                f"Found {len(inferences.get('inferred_fields', []))} possible inferences",
                level="info",
                payload=inferences
            )
            
            return jsonify(inferences)
        except Exception as e:
            logger.exception(f"Cross-entity inference failed for {entity_id}")
            emit_event("cross_entity_inference", f"Error: {str(e)}", level="error")
            return jsonify({"error": str(e)}), 500
    
    return bp_gaps
