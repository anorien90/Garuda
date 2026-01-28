"""Recorder API routes."""

import logging
from flask import Blueprint, jsonify, request
from ..services.event_system import emit_event
from ..utils.request_helpers import safe_int


bp = Blueprint('recorder', __name__, url_prefix='/api/recorder')
logger = logging.getLogger(__name__)


def init_routes(api_key_required, store):
    """Initialize routes with required dependencies."""
    
    @bp.get("/search")
    @api_key_required
    def api_recorder_search():
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"error": "q required"}), 400
        limit = min(safe_int(request.args.get("limit"), 20), 100)
        entity_type = request.args.get("entity_type")
        page_type = request.args.get("page_type")
        emit_event("recorder", "search", payload={"q": q, "limit": limit})
        results = store.search_intel(keyword=q, limit=limit, entity_type=entity_type, page_type=page_type)
        emit_event("recorder", "search done", payload={"count": len(results)})
        return jsonify({"results": results})
    
    @bp.get("/health")
    @api_key_required
    def api_recorder_health():
        emit_event("recorder", "health")
        return jsonify({"status": "ok"})
    
    @bp.get("/queue")
    @api_key_required
    def api_recorder_queue():
        emit_event("recorder", "queue")
        return jsonify({"length": 0, "status": "ok"})
    
    @bp.post("/mark")
    @api_key_required
    def api_recorder_mark():
        body = request.get_json(silent=True) or {}
        url = body.get("url")
        if not url:
            return jsonify({"error": "url required"}), 400
        mode = body.get("mode", "manual")
        session_id = body.get("session_id", "ui-session")
        emit_event("recorder", "mark", payload={"url": url, "mode": mode, "session_id": session_id})
        logger.info(f"[recorder-mark] ({session_id}) mode={mode} url={url}")
        return jsonify({"status": "received", "url": url, "mode": mode, "session_id": session_id})
    
    return bp
