from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from functools import wraps
import logging
from datetime import datetime, timezone

from ..database.engine import SQLAlchemyStore
from ..vector.engine import QdrantVectorStore
from ..extractor.llm import LLMIntelExtractor
from .config import Settings

settings = Settings.from_env()

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/api/*": {"origins": settings.cors_origins}})

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

store = SQLAlchemyStore(settings.db_url)
llm = LLMIntelExtractor(
    ollama_url=settings.ollama_url,
    model=settings.ollama_model,
    embedding_model=settings.embedding_model,
)

vector_store = None
if settings.vector_enabled:
    try:
        vector_store = QdrantVectorStore(
            url=settings.qdrant_url, collection=settings.qdrant_collection
        )
    except Exception as e:
        logger.warning(f"Qdrant unavailable: {e}")
        vector_store = None


def api_key_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not settings.api_key:
            return fn(*args, **kwargs)
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if key != settings.api_key:
            return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)

    return wrapper


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/status")
@api_key_required
def status():
        db_ok = True
        qdrant_ok = bool(vector_store)
        embed_loaded = bool(getattr(llm, "_embedder", None))
        try:
            with store.Session() as s:
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


@app.get("/api/intel")
@api_key_required
def api_intel():
    q = request.args.get("q", "")
    entity = request.args.get("entity")
    min_conf = float(request.args.get("min_conf", 0))
    limit = int(request.args.get("limit", 50))
    if q:
        rows = store.search_intelligence_data(q)
    else:
        rows = store.get_intelligence(
            entity_name=entity, min_confidence=min_conf, limit=limit
        )
    return jsonify(rows)


@app.get("/api/intel/semantic")
@api_key_required
def api_intel_semantic():
    if not vector_store:
        return jsonify({"error": "semantic search unavailable"}), 503
    query = request.args.get("q", "").strip()
    top_k = int(request.args.get("top_k", 10))
    if not query:
        return jsonify({"error": "q required"}), 400
    vec = llm.embed_text(query)
    if not vec:
        return jsonify({"error": "embedding unavailable"}), 503
    try:
        results = vector_store.search(vec, top_k=top_k)
    except Exception as e:
        return jsonify({"error": f"vector search failed: {e}"}), 502
    hits = [
        {
            "score": r.score,
            "url": r.payload.get("url"),
            "kind": r.payload.get("kind"),
            "page_type": r.payload.get("page_type"),
            "entity": r.payload.get("entity"),
            "entity_type": r.payload.get("entity_type"),
            "text": r.payload.get("text"),
            "data": r.payload.get("data"),
        }
        for r in results
    ]
    return jsonify({"semantic": hits})


@app.get("/api/pages")
@api_key_required
def api_pages():
    limit = int(request.args.get("limit", 200))
    pages = store.get_all_pages() or []
    # Sort by last_fetch_at or created_at, fallback to epoch to avoid None comparisons
    def sort_key(p):
        ts = getattr(p, "last_fetch_at", None) or getattr(p, "created_at", None)
        if ts is None:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        if getattr(ts, "tzinfo", None) is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts

    pages = sorted(pages, key=sort_key, reverse=True)
    data = [p.to_dict() for p in pages[:limit]]
    return jsonify(data)


@app.get("/api/page")
@api_key_required
def api_page():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "url required"}), 400
    return jsonify(
        {
            "url": url,
            "content": store.get_page_content(url),
            "page": store.get_page(url),
        }
    )


@app.post("/api/chat")
@api_key_required
def api_chat():
    body = request.get_json(silent=True) or {}
    question = body.get("question") or request.args.get("q")
    entity = body.get("entity") or request.args.get("entity")
    top_k = int(body.get("top_k") or request.args.get("top_k") or 6)
    if not question:
        return jsonify({"error": "question required"}), 400

    context_hits = store.search_intel(keyword=question, limit=top_k)
    vector_hits = []
    if vector_store:
        vec = llm.embed_text(question)
        if vec:
            try:
                res = vector_store.search(vec, top_k=top_k)
                vector_hits = [
                    {
                        "url": r.payload.get("url"),
                        "snippet": r.payload.get("text"),
                        "score": r.score,
                        "source": "vector",
                    }
                    for r in res
                ]
            except Exception as e:
                logger.warning(f"Vector chat search failed: {e}")

    merged_hits = context_hits + vector_hits
    answer = llm.synthesize_answer(question=question, context_hits=merged_hits)
    return jsonify({"answer": answer, "context": merged_hits, "entity": entity})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=settings.debug)
