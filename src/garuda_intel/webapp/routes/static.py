"""Static routes and status endpoints."""

from flask import Blueprint, render_template, send_from_directory, Response, jsonify, request, current_app
from ..services.event_system import _event_stream, emit_event, get_event_buffer, _EVENT_BUFFER_LIMIT, _event_lock


bp = Blueprint('static', __name__)


def init_routes(api_key_required, settings, store, llm, vector_store):
    """Initialize routes with required dependencies."""
    
    @bp.get("/")
    def home():
        return render_template("index.html")
    
    @bp.get("/favicon.ico")
    def favicon():
        return send_from_directory(current_app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon")
    
    @bp.get("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(current_app.static_folder, filename)
    
    @bp.get("/api/status")
    @api_key_required
    def status():
        db_ok = True
        qdrant_ok = bool(vector_store)
        embed_loaded = bool(getattr(llm, "_embedder", None))
        try:
            with store.Session() as _:
                db_ok = True
        except Exception:
            db_ok = False
    
        if vector_store:
            try:
                vector_store.client.get_collection(vector_store.collection)  # type: ignore[attr-defined]
            except Exception:
                qdrant_ok = False
        return jsonify(
            {
                "db_ok": db_ok,
                "qdrant_ok": qdrant_ok,
                "embedding_loaded": embed_loaded,
                "qdrant_url": settings.qdrant_url,
                "qdrant_collection": settings.qdrant_collection,
                "ollama_url": settings.ollama_url,
                "model": settings.ollama_model,
            }
        )
    
    @bp.get("/api/logs/stream")
    @api_key_required
    def logs_stream():
        headers = {
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
        return Response(_event_stream(), mimetype="text/event-stream", headers=headers)
    
    @bp.get("/api/logs/recent")
    @api_key_required
    def logs_recent():
        limit = min(int(request.args.get("limit", 200)), _EVENT_BUFFER_LIMIT)
        with _event_lock:
            data = list(get_event_buffer())[-limit:]
        return jsonify({"events": data})
    
    @bp.post("/api/logs/clear")
    @api_key_required
    def logs_clear():
        with _event_lock:
            get_event_buffer().clear()
        emit_event("logs_clear", "Log buffer cleared")
        return jsonify({"status": "cleared"})
    
    return bp
