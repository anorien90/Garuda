"""Relationship confidence management API routes.

Provides API endpoints for:
- Recording relationships (boosting confidence if exists)
- Getting high-confidence relationships
- Managing relationship provenance
"""

import logging
from flask import Blueprint, jsonify, request

from ..services.event_system import emit_event
from ...extractor.entity_merger import RelationshipConfidenceManager

bp_rel_confidence = Blueprint('relationship_confidence', __name__, url_prefix='/api/relationships')
logger = logging.getLogger(__name__)


def init_relationship_confidence_routes(api_key_required, store):
    """Initialize relationship confidence management routes.
    
    Args:
        api_key_required: Auth decorator
        store: SQLAlchemy store instance
    """
    
    def _manager():
        """Create a manager bound to the *current* store.Session."""
        return RelationshipConfidenceManager(store.Session, logger)
    
    @bp_rel_confidence.post("/record")
    @api_key_required
    def api_record_relationship():
        """
        Record a relationship, boosting confidence if it already exists.
        
        Request body (JSON):
            source_id: Source entity UUID
            target_id: Target entity UUID
            relation_type: Type of relationship
            source_url: Optional source URL where relationship was found
            confidence_boost: How much to increase confidence (default: 0.1)
        
        Returns:
            Relationship info with current confidence and occurrence count
        """
        body = request.get_json(silent=True) or {}
        
        source_id = body.get("source_id")
        target_id = body.get("target_id")
        relation_type = body.get("relation_type")
        
        if not source_id or not target_id or not relation_type:
            return jsonify({"error": "source_id, target_id, and relation_type required"}), 400
        
        source_url = body.get("source_url")
        confidence_boost = float(body.get("confidence_boost", 0.1))
        
        emit_event("record_relationship", "start", payload={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
        })
        
        try:
            result = _manager().record_relationship(
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                source_url=source_url,
                confidence_boost=confidence_boost,
            )
            
            status = "created" if result["is_new"] else "boosted"
            emit_event("record_relationship", f"{status}: confidence={result['confidence']:.2f}")
            
            return jsonify({
                "status": status,
                "relationship": result,
            })
        except Exception as e:
            emit_event("record_relationship", f"failed: {e}", level="error")
            logger.exception("Record relationship failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_rel_confidence.get("/high-confidence")
    @api_key_required
    def api_high_confidence_relationships():
        """
        Get relationships with high confidence scores.
        
        Query params:
            min_confidence: Minimum confidence threshold (default: 0.7)
            min_occurrences: Minimum occurrence count (default: 2)
            limit: Maximum results (default: 100)
        
        Returns:
            List of high-confidence relationships
        """
        min_confidence = float(request.args.get("min_confidence", 0.7))
        min_occurrences = int(request.args.get("min_occurrences", 2))
        limit = min(int(request.args.get("limit", 100)), 500)
        
        emit_event("high_confidence_relationships", "start", payload={
            "min_confidence": min_confidence,
            "min_occurrences": min_occurrences,
            "limit": limit,
        })
        
        try:
            results = _manager().get_high_confidence_relationships(
                min_confidence=min_confidence,
                min_occurrences=min_occurrences,
                limit=limit,
            )
            
            emit_event("high_confidence_relationships", f"found {len(results)} relationships")
            
            return jsonify({
                "min_confidence": min_confidence,
                "min_occurrences": min_occurrences,
                "total": len(results),
                "relationships": results,
            })
        except Exception as e:
            emit_event("high_confidence_relationships", f"failed: {e}", level="error")
            logger.exception("High confidence relationships query failed")
            return jsonify({"error": str(e)}), 500
    
    @bp_rel_confidence.get("/confidence-stats")
    @api_key_required
    def api_relationship_confidence_stats():
        """
        Get statistics about relationship confidence in the database.
        
        Returns:
            Statistics including confidence distribution, top relation types, etc.
        """
        emit_event("confidence_stats", "start")
        
        try:
            from sqlalchemy import select, func
            from ...database.models import Relationship
            
            with store.Session() as session:
                # Count total relationships
                total = session.execute(
                    select(func.count(Relationship.id))
                ).scalar() or 0
                
                # Count by relation type
                type_counts = session.execute(
                    select(Relationship.relation_type, func.count(Relationship.id))
                    .group_by(Relationship.relation_type)
                    .order_by(func.count(Relationship.id).desc())
                    .limit(20)
                ).all()
                
                # Get confidence distribution
                all_rels = session.execute(select(Relationship)).scalars().all()
                
                confidence_buckets = {
                    "very_high": 0,   # >= 0.9
                    "high": 0,        # >= 0.7
                    "medium": 0,      # >= 0.5
                    "low": 0,         # < 0.5
                }
                
                multi_occurrence = 0
                
                for rel in all_rels:
                    meta = rel.metadata_json or {}
                    conf = meta.get("confidence", 0.5)
                    occurrences = meta.get("occurrence_count", 1)
                    
                    if occurrences > 1:
                        multi_occurrence += 1
                    
                    if conf >= 0.9:
                        confidence_buckets["very_high"] += 1
                    elif conf >= 0.7:
                        confidence_buckets["high"] += 1
                    elif conf >= 0.5:
                        confidence_buckets["medium"] += 1
                    else:
                        confidence_buckets["low"] += 1
            
            emit_event("confidence_stats", f"stats for {total} relationships")
            
            return jsonify({
                "total_relationships": total,
                "multi_occurrence_count": multi_occurrence,
                "confidence_distribution": confidence_buckets,
                "top_relation_types": [
                    {"type": t, "count": c}
                    for t, c in type_counts
                ],
            })
        except Exception as e:
            emit_event("confidence_stats", f"failed: {e}", level="error")
            logger.exception("Confidence stats query failed")
            return jsonify({"error": str(e)}), 500
    
    return bp_rel_confidence
