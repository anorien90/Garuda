"""
Schema API routes for dynamic entity kinds and relation types.

Provides endpoints for:
- GET /api/schema/kinds - All registered entity kinds with colors/priorities
- GET /api/schema/relations - All registered relation types
- GET /api/schema/full - Complete schema with database sync
- POST /api/schema/kinds - Register new kinds at runtime
- POST /api/schema/relations - Register new relations at runtime
"""

import logging
from flask import Blueprint, request, jsonify

from ...types.entity import get_registry

logger = logging.getLogger(__name__)


def init_schema_routes(api_key_required, store):
    """Initialize schema API routes."""
    bp = Blueprint("schema", __name__, url_prefix="/api/schema")
    
    @bp.get("/kinds")
    @api_key_required
    def get_kinds():
        """
        Get all registered entity kinds with their colors and priorities.
        
        Returns:
            JSON object with kind names as keys and kind info as values
        """
        try:
            registry = get_registry()
            return jsonify({
                "kinds": registry.get_kinds_dict(),
                "colors": registry.get_colors_map(),
            })
        except Exception as e:
            logger.exception("Failed to get kinds")
            return jsonify({"error": str(e)}), 500
    
    @bp.get("/relations")
    @api_key_required
    def get_relations():
        """
        Get all registered relation types with their colors.
        
        Returns:
            JSON object with relation names as keys and relation info as values
        """
        try:
            registry = get_registry()
            return jsonify({
                "relations": registry.get_relations_dict(),
                "colors": registry.get_edge_colors_map(),
            })
        except Exception as e:
            logger.exception("Failed to get relations")
            return jsonify({"error": str(e)}), 500
    
    @bp.get("/full")
    @api_key_required
    def get_full_schema():
        """
        Get complete schema including database sync.
        
        This endpoint loads persisted structure learnings from the database,
        then syncs to discover any new kinds that were added by crawlers
        or extractors, and finally persists the updated state back.
        
        Returns:
            JSON object with kinds, relations, and sync stats
        """
        try:
            registry = get_registry()
            
            new_kinds_count = 0
            load_stats = {}
            save_stats = {}
            try:
                with store.Session() as session:
                    # Load persisted structure learnings
                    load_stats = registry.load_from_database(session)
                    # Discover new kinds from entity table
                    new_kinds_count = registry.sync_from_database(session)
                    # Persist everything back so new discoveries are saved
                    save_stats = registry.save_to_database(session)
                    session.commit()
            except Exception as e:
                logger.warning(f"Database sync failed: {e}")
            
            return jsonify({
                "kinds": registry.get_kinds_dict(),
                "relations": registry.get_relations_dict(),
                "colors": {
                    "nodes": registry.get_colors_map(),
                    "edges": registry.get_edge_colors_map(),
                },
                "stats": {
                    "total_kinds": len(registry.get_all_kinds()),
                    "total_relations": len(registry.get_all_relations()),
                    "new_kinds_synced": new_kinds_count,
                    "loaded": load_stats,
                    "saved": save_stats,
                },
            })
        except Exception as e:
            logger.exception("Failed to get full schema")
            return jsonify({"error": str(e)}), 500
    
    @bp.post("/kinds")
    @api_key_required
    def register_kind():
        """
        Register a new entity kind at runtime.
        
        Request body:
            {
                "name": "custom_kind",
                "color": "#ff0000",
                "priority": 50,
                "aliases": ["alias1", "alias2"],
                "parent_kind": "entity",
                "description": "Description"
            }
        
        Returns:
            The registered kind info
        """
        try:
            body = request.get_json(silent=True) or {}
            name = body.get("name")
            
            if not name:
                return jsonify({"error": "name is required"}), 400
            
            registry = get_registry()
            kind_info = registry.register_kind(
                name=name,
                color=body.get("color"),
                priority=body.get("priority"),
                aliases=set(body.get("aliases", [])),
                parent_kind=body.get("parent_kind"),
                description=body.get("description", ""),
            )
            
            # Persist to database
            try:
                with store.Session() as session:
                    registry.save_to_database(session)
                    session.commit()
            except Exception as e:
                logger.warning(f"Failed to persist kind to database: {e}")
            
            return jsonify({
                "success": True,
                "kind": kind_info.to_dict(),
            })
        except Exception as e:
            logger.exception("Failed to register kind")
            return jsonify({"error": str(e)}), 500
    
    @bp.post("/relations")
    @api_key_required
    def register_relation():
        """
        Register a new relation type at runtime.
        
        Request body:
            {
                "name": "custom_relation",
                "color": "rgba(100,100,100,0.5)",
                "directed": true,
                "description": "Description"
            }
        
        Returns:
            The registered relation info
        """
        try:
            body = request.get_json(silent=True) or {}
            name = body.get("name")
            
            if not name:
                return jsonify({"error": "name is required"}), 400
            
            registry = get_registry()
            rel_info = registry.register_relation(
                name=name,
                color=body.get("color"),
                directed=body.get("directed", True),
                description=body.get("description", ""),
            )
            
            # Persist to database
            try:
                with store.Session() as session:
                    registry.save_to_database(session)
                    session.commit()
            except Exception as e:
                logger.warning(f"Failed to persist relation to database: {e}")
            
            return jsonify({
                "success": True,
                "relation": rel_info.to_dict(),
            })
        except Exception as e:
            logger.exception("Failed to register relation")
            return jsonify({"error": str(e)}), 500
    
    @bp.get("/normalize/<kind>")
    @api_key_required
    def normalize_kind(kind: str):
        """
        Normalize a kind name to its canonical form.
        
        Args:
            kind: The kind name to normalize
            
        Returns:
            The canonical kind name and its info
        """
        try:
            registry = get_registry()
            normalized = registry.normalize_kind(kind)
            kind_info = registry.get_kind(normalized)
            
            return jsonify({
                "original": kind,
                "normalized": normalized,
                "kind": kind_info.to_dict() if kind_info else None,
            })
        except Exception as e:
            logger.exception("Failed to normalize kind")
            return jsonify({"error": str(e)}), 500
    
    # ---- User Settings ----

    @bp.get("/settings")
    @api_key_required
    def get_settings():
        """Get all user settings."""
        from ...database.models import UserSetting
        try:
            with store.Session() as session:
                rows = session.query(UserSetting).all()
                return jsonify({
                    "settings": {r.key: r.to_dict() for r in rows},
                })
        except Exception as e:
            logger.exception("Failed to get settings")
            return jsonify({"error": str(e)}), 500

    @bp.get("/settings/<key>")
    @api_key_required
    def get_setting(key: str):
        """Get a single user setting by key."""
        from ...database.models import UserSetting
        try:
            with store.Session() as session:
                row = session.query(UserSetting).filter_by(key=key).first()
                if not row:
                    return jsonify({"error": "Setting not found"}), 404
                return jsonify(row.to_dict())
        except Exception as e:
            logger.exception("Failed to get setting")
            return jsonify({"error": str(e)}), 500

    @bp.put("/settings/<key>")
    @api_key_required
    def put_setting(key: str):
        """Create or update a user setting."""
        import uuid as _uuid
        from ...database.models import UserSetting
        try:
            body = request.get_json(silent=True) or {}
            with store.Session() as session:
                row = session.query(UserSetting).filter_by(key=key).first()
                if row:
                    row.value_json = body.get("value")
                    if "description" in body:
                        row.description = body["description"]
                else:
                    row = UserSetting(
                        id=_uuid.uuid4(),
                        key=key,
                        value_json=body.get("value"),
                        description=body.get("description"),
                    )
                    session.add(row)
                session.commit()
                return jsonify(row.to_dict())
        except Exception as e:
            logger.exception("Failed to save setting")
            return jsonify({"error": str(e)}), 500

    return bp
