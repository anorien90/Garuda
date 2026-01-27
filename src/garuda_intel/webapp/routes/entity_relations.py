"""Entity relationship routes - query and traverse entity relationships."""
import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

bp_relations = Blueprint('entity_relations', __name__, url_prefix='/api/entities')


def init_relations_routes(api_key_required, store):
    """Initialize entity relationship routes."""
    
    @bp_relations.get("/<entity_id>/relations")
    @api_key_required
    def api_entity_relations(entity_id):
        """Get all relationships for an entity."""
        direction = request.args.get("direction", "both")
        max_depth = int(request.args.get("max_depth", 1))
        
        try:
            relations = store.get_entity_relations(
                entity_id=entity_id,
                direction=direction,
                max_depth=max_depth
            )
            
            return jsonify(relations)
        except Exception as e:
            logger.exception("Entity relations lookup failed")
            return jsonify({"error": str(e)}), 500
    
    return bp_relations
