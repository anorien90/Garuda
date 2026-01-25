from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from functools import wraps
import logging
from datetime import datetime, timezone

from ..database.engine import SQLAlchemyStore
from ..vector.engine import QdrantVectorStore
from ..extractor.llm import LLMIntelExtractor
from ..config import Settings
from ..search import (
    run_crawl_api,
    perform_rag_search,
    collect_candidates_simple,
    IntelligentExplorer,
    EntityProfile,
    EntityType,
)
from ..browser.selenium import SeleniumBrowser

settings = Settings.from_env()

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/api/*": {"origins": settings.cors_origins}})

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

print(f"Starting Garuda Intel Webapp with DB: {settings.db_url}")
print(f"Qdrant Vector Store: {settings.qdrant_url} Collection: {settings.qdrant_collection}")
print(f"Ollama LLM: {settings.ollama_url} Model: {settings.ollama_model}")
print(f"Embedding Model: {settings.embedding_model}")


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


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(
        app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon"
    )


@app.get("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


@app.get("/api/status")
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


def _looks_like_refusal(text: str) -> bool:
    """Detect common LLM refusal/empty patterns even if not 'INSUFFICIENT_DATA'."""
    if not text:
        return True
    t = text.lower()
    patterns = [
        "no information",
        "not have information",
        "unable to find",
        "does not contain",
        "context provided does not contain",
        "cannot provide details",
        "i don't have enough",
        "no data",
        "insufficient context",
        "based solely on the given data",
    ]
    return any(p in t for p in patterns)


@app.post("/api/chat")
@api_key_required
def api_chat():
    """
    Align web chat behavior with CLI interactive_chat:
    - Try local RAG (SQL + vector).
    - If insufficient, generate seeds, resolve live URLs, run crawl, and re-run RAG.
    - Never return raw INSUFFICIENT_DATA to the client.
    - Also treat generic refusals as insufficient to force the crawl path.
    """
    body = request.get_json(silent=True) or {}
    question = body.get("question") or request.args.get("q")
    entity = body.get("entity") or request.args.get("entity")
    top_k = int(body.get("top_k") or request.args.get("top_k") or 6)
    if not question:
        return jsonify({"error": "question required"}), 400

    def gather_hits(q: str, limit: int):
        ctx = store.search_intel(keyword=q, limit=limit)
        vec_hits = []
        if vector_store:
            vec = llm.embed_text(q)
            if vec:
                try:
                    res = vector_store.search(vec, top_k=limit)
                    vec_hits = [
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
        return ctx + vec_hits

    merged_hits = gather_hits(question, top_k)
    answer = llm.synthesize_answer(question=question, context_hits=merged_hits)
    online_triggered = False
    live_urls = []

    is_sufficient = llm.evaluate_sufficiency(answer) and not _looks_like_refusal(answer)

    if not is_sufficient:
        profile = EntityProfile(
            name=entity or "General Research", entity_type=EntityType.TOPIC
        )
        online_triggered = True

        search_queries = llm.generate_seed_queries(question, profile.name)
        live_urls = collect_candidates_simple(search_queries, limit=5)

        if live_urls:
            explorer = IntelligentExplorer(
                profile=profile,
                persistence=store,
                vector_store=vector_store,
                llm_extractor=llm,
                max_total_pages=getattr(settings, "chat_max_pages", 5),
                score_threshold=5.0,
            )

            browser = None
            try:
                if getattr(settings, "chat_use_selenium", False):
                    browser = SeleniumBrowser(headless=True)
                    browser._init_driver()
                explorer.explore(live_urls, browser)
            except Exception as e:
                logger.warning(f"Chat crawl failed: {e}")
            finally:
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass

            merged_hits = gather_hits(question, top_k)
            answer = llm.synthesize_answer(question=question, context_hits=merged_hits)

        answer = answer.replace(
            "INSUFFICIENT_DATA",
            "I searched online but still couldn't find a definitive answer.",
        )
        # If it still sounds like a refusal, soften it.
        if _looks_like_refusal(answer):
            answer = "I searched online but still couldn't find a definitive answer."

    return jsonify(
        {
            "answer": answer,
            "context": merged_hits,
            "entity": entity,
            "online_search_triggered": online_triggered,
            "live_urls": live_urls,
        }
    )


# --- Recorder-like helpers exposed to UI (search, health, queue, mark)
@app.get("/api/recorder/search")
@api_key_required
def api_recorder_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "q required"}), 400
    limit = min(int(request.args.get("limit", 20)), 100)
    entity_type = request.args.get("entity_type")
    page_type = request.args.get("page_type")
    results = store.search_intel(
        keyword=q, limit=limit, entity_type=entity_type, page_type=page_type
    )
    return jsonify({"results": results})


@app.get("/api/recorder/health")
@api_key_required
def api_recorder_health():
    return jsonify({"status": "ok"})


@app.get("/api/recorder/queue")
@api_key_required
def api_recorder_queue():
    return jsonify({"length": 0, "status": "ok"})


@app.post("/api/recorder/mark")
@api_key_required
def api_recorder_mark():
    body = request.get_json(silent=True) or {}
    url = body.get("url")
    if not url:
        return jsonify({"error": "url required"}), 400
    mode = body.get("mode", "manual")
    session_id = body.get("session_id", "ui-session")
    logger.info(f"[recorder-mark] ({session_id}) mode={mode} url={url}")
    return jsonify({"status": "received", "url": url, "mode": mode, "session_id": session_id})


# --- Crawl: now wired to search.py logic instead of dummy stub
@app.post("/api/crawl")
@api_key_required
def api_crawl():
    body = request.get_json(silent=True) or {}
    try:
        result = run_crawl_api(body)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Crawl failed")
        return jsonify({"error": f"crawl failed: {e}"}), 500

def main():
    app.run(host="0.0.0.0", port=8080, debug=settings.debug)


if __name__ == "__main__":
    main()
