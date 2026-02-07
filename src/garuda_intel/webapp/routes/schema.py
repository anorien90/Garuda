"""Schema API routes for entity kinds and relation types.

This module provides API endpoints for the dynamic entity kind registry,
allowing the UI to fetch available kinds, relation types, and their metadata
without requiring code changes.
"""

import logging
from flask import Blueprint, jsonify, request
from ...types.entity.registry import get_registry


bp = Blueprint('schema', __name__, url_prefix='/api/schema')
logger = logging.getLogger(__name__)


def init_schema_routes(api_key_required, store):
    """Initialize schema routes with required dependencies."""
    
    @bp.get("/kinds")
    @api_key_required
    def api_get_kinds():
        """
        Get all registered entity kinds.
        
        This endpoint returns both builtin kinds and any dynamically
        discovered kinds from the database.
        
        Query params:
            sync: If "true", sync registry from database first
            
        Returns:
            JSON object with kinds and their metadata
        """
        try:
            # Optionally sync from database first
            if request.args.get("sync", "").lower() == "true":
                store.sync_registry_from_database()
            
            registry = get_registry()
            kinds = registry.get_all_kinds()
            
            # Also include database kinds that might not be registered yet
            db_kinds = store.get_unique_entity_kinds()
            for kind in db_kinds:
                if kind and kind not in kinds:
                    # Auto-register and return
                    registry.register_kind(kind)
            
            # Refresh kinds after potential registration
            kinds = registry.get_all_kinds()
            
            return jsonify({
                "success": True,
                "kinds": {name: info.to_dict() for name, info in kinds.items()},
                "names": sorted(kinds.keys()),
                "colors": registry.get_kind_colors(),
                "priorities": registry.get_kind_priority_map(),
            })
        except Exception as e:
            logger.error(f"Error getting kinds: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    
    @bp.get("/relations")
    @api_key_required
    def api_get_relations():
        """
        Get all registered relation types.
        
        Returns:
            JSON object with relation types and their metadata
        """
        try:
            # Sync from database first
            store.sync_registry_from_database()
            
            registry = get_registry()
            relations = registry.get_all_relations()
            
            return jsonify({
                "success": True,
                "relations": {name: info.to_dict() for name, info in relations.items()},
                "names": sorted(relations.keys()),
                "colors": registry.get_relation_colors(),
            })
        except Exception as e:
            logger.error(f"Error getting relations: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    
    @bp.get("/full")
    @api_key_required
    def api_get_full_schema():
        """
        Get the full schema including kinds, relations, and database stats.
        
        This endpoint provides everything the UI needs to render
        dynamic filters and understand the data model.
        
        Returns:
            JSON object with full schema information
        """
        try:
            # Sync registry from database
            store.sync_registry_from_database()
            
            registry = get_registry()
            
            # Get counts by kind
            db_kinds = store.get_unique_entity_kinds()
            db_relations = store.get_unique_relation_types()
            
            return jsonify({
                "success": True,
                "kinds": {name: info.to_dict() for name, info in registry.get_all_kinds().items()},
                "relations": {name: info.to_dict() for name, info in registry.get_all_relations().items()},
                "kind_names": sorted(registry.get_kind_names()),
                "relation_names": sorted(registry.get_relation_names()),
                "kind_colors": registry.get_kind_colors(),
                "relation_colors": registry.get_relation_colors(),
                "kind_priorities": registry.get_kind_priority_map(),
                "database_kinds": db_kinds,
                "database_relations": db_relations,
            })
        except Exception as e:
            logger.error(f"Error getting full schema: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    
    @bp.post("/kinds")
    @api_key_required
    def api_register_kind():
        """
        Register a new entity kind.
        
        Request body:
            name: Kind name (required)
            priority: Priority for deduplication (1-100)
            color: Hex color for UI
            description: Human-readable description
            parent_kind: Parent kind for hierarchical classification
            aliases: List of alternative names
            fields: Common fields for this kind
            
        Returns:
            JSON object with the registered kind info
        """
        try:
            data = request.get_json() or {}
            name = data.get("name", "").strip().lower()
            
            if not name:
                return jsonify({"success": False, "error": "Kind name is required"}), 400
            
            registry = get_registry()
            kind_info = registry.register_kind(
                name=name,
                priority=data.get("priority", 50),
                color=data.get("color", "#94a3b8"),
                description=data.get("description", ""),
                parent_kind=data.get("parent_kind"),
                aliases=data.get("aliases", []),
                fields=data.get("fields", []),
            )
            
            logger.info(f"Registered kind via API: {name}")
            
            return jsonify({
                "success": True,
                "kind": kind_info.to_dict(),
            })
        except Exception as e:
            logger.error(f"Error registering kind: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    
    @bp.post("/relations")
    @api_key_required
    def api_register_relation():
        """
        Register a new relation type.
        
        Request body:
            name: Relation name (required)
            source_kinds: Allowed source entity kinds
            target_kinds: Allowed target entity kinds
            color: Color for UI display
            description: Human-readable description
            inverse_relation: Name of the inverse relation
            
        Returns:
            JSON object with the registered relation info
        """
        try:
            data = request.get_json() or {}
            name = data.get("name", "").strip().lower()
            
            if not name:
                return jsonify({"success": False, "error": "Relation name is required"}), 400
            
            registry = get_registry()
            relation_info = registry.register_relation(
                name=name,
                source_kinds=data.get("source_kinds", []),
                target_kinds=data.get("target_kinds", []),
                color=data.get("color", "rgba(148,163,184,0.25)"),
                description=data.get("description", ""),
                inverse_relation=data.get("inverse_relation"),
            )
            
            logger.info(f"Registered relation via API: {name}")
            
            return jsonify({
                "success": True,
                "relation": relation_info.to_dict(),
            })
        except Exception as e:
            logger.error(f"Error registering relation: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    
    @bp.get("/kind/<name>")
    @api_key_required
    def api_get_kind(name: str):
        """
        Get info for a specific entity kind.
        
        Args:
            name: The kind name
            
        Returns:
            JSON object with kind info
        """
        try:
            registry = get_registry()
            kind_info = registry.get_kind(name)
            
            if not kind_info:
                return jsonify({"success": False, "error": f"Kind '{name}' not found"}), 404
            
            return jsonify({
                "success": True,
                "kind": kind_info.to_dict(),
            })
        except Exception as e:
            logger.error(f"Error getting kind {name}: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    
    @bp.get("/normalize/<kind>")
    @api_key_required
    def api_normalize_kind(kind: str):
        """
        Normalize a kind name to its canonical form.
        
        Args:
            kind: The kind name or alias
            
        Returns:
            JSON object with the normalized kind name
        """
        try:
            registry = get_registry()
            normalized = registry.normalize_kind(kind)
            
            return jsonify({
                "success": True,
                "input": kind,
                "normalized": normalized,
                "is_known": registry.is_known_kind(kind),
            })
        except Exception as e:
            logger.error(f"Error normalizing kind {kind}: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    
    return bp
