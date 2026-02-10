"""Database management API routes – create, switch, merge, delete, global search."""

import logging
from flask import Blueprint, jsonify, request

bp = Blueprint("databases", __name__, url_prefix="/api/databases")
logger = logging.getLogger(__name__)


def init_database_routes(api_key_required, db_manager, switch_callback):
    """Initialise routes.

    Parameters
    ----------
    api_key_required : decorator
        Auth decorator applied to every endpoint.
    db_manager : DatabaseManager
        The shared database manager instance.
    switch_callback : callable(store, collection) -> None
        Called after a successful database switch so the webapp can
        update its module-level ``store`` / ``vector_store`` references.
    """

    @bp.get("/")
    @api_key_required
    def list_databases():
        try:
            dbs = db_manager.list_databases()
            return jsonify({"databases": dbs})
        except Exception as exc:
            logger.error("list_databases error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @bp.get("/active")
    @api_key_required
    def active_database():
        try:
            info = db_manager.get_active_database()
            return jsonify(info)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @bp.post("/create")
    @api_key_required
    def create_database():
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name is required"}), 400
        description = body.get("description", "")
        set_active = bool(body.get("set_active", False))
        try:
            info = db_manager.create_database(name, description, set_active)
            if set_active:
                store, collection = db_manager.switch_database(name)
                switch_callback(store, collection)
            return jsonify(info), 201
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        except Exception as exc:
            logger.error("create_database error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @bp.post("/switch")
    @api_key_required
    def switch_database():
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name is required"}), 400
        try:
            store, collection = db_manager.switch_database(name)
            switch_callback(store, collection)
            info = db_manager.get_active_database()
            return jsonify({"status": "switched", "database": info})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
        except Exception as exc:
            logger.error("switch_database error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @bp.post("/merge")
    @api_key_required
    def merge_databases():
        body = request.get_json(silent=True) or {}
        source = (body.get("source") or "").strip()
        target = (body.get("target") or "").strip()
        if not source or not target:
            return jsonify({"error": "source and target are required"}), 400
        try:
            stats = db_manager.merge_databases(source, target)
            return jsonify({"status": "merged", "stats": stats})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logger.error("merge_databases error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @bp.delete("/<name>")
    @api_key_required
    def delete_database(name):
        delete_files = request.args.get("delete_files", "false").lower() in ("1", "true", "yes")
        try:
            db_manager.delete_database(name, delete_files=delete_files)
            return jsonify({"status": "deleted", "name": name})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logger.error("delete_database error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @bp.get("/search")
    @api_key_required
    def global_search():
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify({"error": "q parameter required"}), 400
        limit = min(int(request.args.get("limit", "10")), 100)
        try:
            results = db_manager.global_search(query=q, limit_per_db=limit)
            return jsonify({"query": q, "results": results})
        except Exception as exc:
            logger.error("global_search error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    return bp
