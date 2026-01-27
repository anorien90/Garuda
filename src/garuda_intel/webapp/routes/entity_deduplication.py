"""Entity deduplication routes - merge and match entities."""
import logging
from flask import Blueprint, jsonify, request

from ..services.event_system import emit_event
from ...database import models as db_models


bp_dedup = Blueprint('entity_dedup', __name__, url_prefix='/api/entities')
logger = logging.getLogger(__name__)


def init_deduplication_routes(api_key_required, store):
    """Initialize deduplication routes."""
    
    @bp_dedup.post("/deduplicate")
    @api_key_required
    def api_deduplicate_entities():
        """Deduplicate entities based on similarity."""
        body = request.get_json(silent=True) or {}
        threshold = float(body.get("threshold", 0.85))
        
        emit_event("deduplication", f"deduplicating entities with threshold {threshold}")
        
        try:
            merge_map = store.deduplicate_entities(threshold=threshold)
            count = len(merge_map)
            emit_event("deduplication", f"merged {count} duplicate entities")
            return jsonify({
                "merged_count": count,
                "merge_map": {str(k): str(v) for k, v in merge_map.items()}
            })
        except Exception as e:
            emit_event("deduplication", f"failed: {e}", level="error")
            logger.exception("Entity deduplication failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_dedup.post("/<source_id>/merge/<target_id>")
    @api_key_required
    def api_merge_entities(source_id, target_id):
        """Manually merge two entities."""
        emit_event("merge_entities", f"merging {source_id} into {target_id}")
        
        try:
            success = store.merge_entities(source_id, target_id)
            if success:
                emit_event("merge_entities", "merge successful")
                return jsonify({"status": "ok", "message": "Entities merged successfully"})
            else:
                return jsonify({"error": "Merge failed"}), 500
        except Exception as e:
            emit_event("merge_entities", f"failed: {e}", level="error")
            logger.exception("Entity merge failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_dedup.get("/<entity_id>/similar")
    @api_key_required
    def api_similar_entities(entity_id):
        """Find similar entities."""
        threshold = float(request.args.get("threshold", 0.75))
        
        try:
            with store.Session() as session:
                entity = session.query(db_models.Entity).filter_by(id=entity_id).first()
                if not entity:
                    return jsonify({"error": "Entity not found"}), 404
                
                entity_name = entity.name
            
            similar = store.find_similar_entities(entity_name, threshold=threshold)
            
            return jsonify({
                "entity_name": entity_name,
                "similar_entities": [
                    {
                        "id": str(e.id),
                        "name": e.name,
                        "kind": e.kind,
                        "last_seen": e.last_seen.isoformat() if e.last_seen else None
                    }
                    for e in similar
                ]
            })
        except Exception as e:
            logger.exception("Similar entities lookup failed")
            return jsonify({"error": str(e)}), 500
    
    return bp_dedup
