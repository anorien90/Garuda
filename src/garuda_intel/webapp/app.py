from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS
from functools import wraps
import logging
from datetime import datetime, timezone
import json
import queue
import threading
from collections import deque
import itertools  # NEW
from typing import Generator
import re  # NEW
from collections import Counter  # NEW



from ..database import models as db_models
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

_EVENT_BUFFER_LIMIT = 1000
_event_buffer = deque(maxlen=_EVENT_BUFFER_LIMIT)
_event_listeners: list[queue.Queue] = []
_event_lock = threading.Lock()

def _publish_event(evt: dict):
    """Push an event to the in-memory buffer and live listeners."""
    with _event_lock:
        _event_buffer.append(evt)
        dead = []
        for q in _event_listeners:
            try:
                q.put_nowait(evt)
            except Exception:
                dead.append(q)
        for q in dead:
            if q in _event_listeners:
                _event_listeners.remove(q)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def emit_event(step: str, message: str, level: str = "info", payload=None, session_id=None):
    """Primary emitter used across the app when logging explicit steps."""
    evt = {
        "ts": _now_iso(),
        "level": level,
        "step": step,
        "message": message,
        "payload": payload or {},
        "session_id": session_id,
    }
    _publish_event(evt)
    logger.log(getattr(logging, level.upper(), logging.INFO), f"[{step}] {message}")


class EventQueueHandler(logging.Handler):
    """Logging handler that mirrors all log records into the UI event stream."""
    def emit(self, record: logging.LogRecord):
        try:
            evt = {
                "ts": _now_iso(),
                "level": record.levelname.lower(),
                "step": getattr(record, "step", record.name),
                "message": self.format(record),
                "payload": getattr(record, "payload", {}) or {},
                "session_id": getattr(record, "session_id", None),
            }
            _publish_event(evt)
        except Exception:
            # Never break app logging on handler errors
            pass


def init_event_logging():
    """Attach the event queue handler to the root logger so all modules funnel into UI logs."""
    handler = EventQueueHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    if root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)

    # Tone down noisy HTTP access logs but still capture warnings/errors
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


# Initialize central log funnel on import
init_event_logging()

def _event_stream():
    q: queue.Queue = queue.Queue()
    with _event_lock:
        _event_listeners.append(q)
    try:
        while True:
            evt = q.get()
            yield f"data: {json.dumps(evt)}\n\n"
    except GeneratorExit:
        with _event_lock:
            if q in _event_listeners:
                _event_listeners.remove(q)

# --- Auth helper ---
def api_key_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # If no key configured, allow open access (for local dev)
        if not settings.api_key:
            return fn(*args, **kwargs)
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if key != settings.api_key:
            return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)

    return wrapper


# --- Static / HTML ---
@app.get("/")
def home():
    return render_template("index.html")

def _canonical(name) -> str:
    # Accept any type, convert to string, then normalize
    if name is None:
        return ""
    try:
        s = str(name)
    except Exception:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()

def _best_label(variants_counter: Counter[str]) -> str:
    if not variants_counter:
        return ""
    return variants_counter.most_common(1)[0][0]

def _collect_entities_from_json(obj):
    """
    Recursively walk a JSON-like structure and collect entities.
    An entity is detected if:
      - dict has a name/entity/value key
      - or a string (treated as a name with unknown kind)
    Returns list of {"name": str, "kind": Optional[str]}
    """
    out = []
    if obj is None:
        return out
    if isinstance(obj, str):
        out.append({"name": obj, "kind": None})
        return out
    if isinstance(obj, dict):
        # If it looks like an entity object
        maybe_name = obj.get("name") or obj.get("entity") or obj.get("value")
        maybe_kind = obj.get("type") or obj.get("kind") or obj.get("entity_type")
        if maybe_name:
            out.append({"name": maybe_name, "kind": maybe_kind.lower() if maybe_kind else None})
        # Recurse into values
        for v in obj.values():
            out.extend(_collect_entities_from_json(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_collect_entities_from_json(v))
    return out


@app.get("/api/entities/graph")
@api_key_required
def api_entities_graph():
    """
    Build entity co-occurrence graph with combined semantic + SQL filtering:
    - Canonicalize variants into one node
    - Derive types from payload/entity table when possible
    - Edge weights = co-occurrence count across documents (intel rows, page_content)
    Query params:
      query: semantic filter (vector-backed) combined with SQL substring fallback
      type: optional type filter (matches derived node type)
      min_score: minimum confidence for an intel row (default 0)
      limit: max nodes returned (default 100, cap 500)
    """
    q = (request.args.get("query") or "").strip().lower()
    type_filter = (request.args.get("type") or "").strip().lower()
    min_score = float(request.args.get("min_score", 0) or 0)
    limit = min(int(request.args.get("limit", 100) or 100), 500)

    emit_event("entities_graph", "start", payload={"q": q, "type": type_filter, "min_score": min_score, "limit": limit})

    nodes: dict[str, dict] = {}
    variants: dict[str, Counter[str]] = {}
    links: dict[tuple[str, str], int] = {}
    canonical_type: dict[str, str] = {}

    def semantic_entity_hints(query: str, top_k: int = 200) -> set[str]:
        hints: set[str] = set()
        if not vector_store or not query:
            return hints
        vec = llm.embed_text(query)
        if not vec:
            return hints
        try:
            results = vector_store.search(vec, top_k=top_k)
        except Exception as e:
            logger.warning(f"entities graph semantic search failed: {e}")
            return hints
        for r in results:
            p = getattr(r, "payload", {}) or {}  # type: ignore[attr-defined]
            for key in ("entity", "entity_name", "name"):
                val = p.get(key)
                if val:
                    canon = _canonical(val)
                    if canon:
                        hints.add(canon)
        return hints

    def upsert_node(raw_name: str, kind: str | None, score: float | None):
        if not raw_name:
            return None
        canon = _canonical(raw_name)
        if not canon:
            return None
        variants.setdefault(canon, Counter()).update([raw_name])
        node = nodes.get(canon, {"id": canon, "label": raw_name, "type": "unknown", "score": 0, "count": 0})
        node["count"] += 1
        if score is not None:
            node["score"] = max(node.get("score") or 0, score)
        if kind:
            k = kind.lower()
            canonical_type[canon] = canonical_type.get(canon) or k
            node["type"] = canonical_type[canon]
        nodes[canon] = node
        return canon

    def add_edges(entity_keys: list[str]):
        unique_keys = sorted(set([e for e in entity_keys if e]))
        for a, b in itertools.combinations(unique_keys, 2):
            key = (a, b)
            links[key] = links.get(key, 0) + 1

    # Collect semantic hints (vector) early
    semantic_allow = semantic_entity_hints(q, top_k=200) if q else set()

    with store.Session() as session:
        intel_q = session.query(db_models.Intelligence)
        if q:
            intel_q = intel_q.filter(db_models.Intelligence.entity_name.ilike(f"%{q}%"))
        if min_score:
            intel_q = intel_q.filter(db_models.Intelligence.confidence >= min_score)
        intel_rows = intel_q.limit(5000).all()

        page_rows = session.query(db_models.PageContent).limit(5000).all()

        entity_kinds = {}
        for ent in session.query(db_models.Entity).limit(10000).all():
            canon = _canonical(ent.name)
            if canon and ent.kind:
                entity_kinds[canon] = ent.kind.lower()

    # Process intel rows as documents
    for row in intel_rows:
        try:
            payload = json.loads(row.data or "{}")
        except Exception:
            payload = {}
        doc_keys = []
        primary = upsert_node(row.entity_name, payload.get("entity_type") or payload.get("entity_kind"), row.confidence)
        if primary:
            doc_keys.append(primary)
        for ent in _collect_entities_from_json(payload):
            ck = upsert_node(ent["name"], ent.get("kind"), None)
            if ck:
                doc_keys.append(ck)
        add_edges(doc_keys)

    # Process page_content as documents
    for p in page_rows:
        doc_keys = []
        try:
            extracted = json.loads(p.extracted_json or "{}")
        except Exception:
            extracted = {}
        try:
            metadata = json.loads(p.metadata_json or "{}")
        except Exception:
            metadata = {}
        for ent in _collect_entities_from_json(extracted):
            ck = upsert_node(ent["name"], ent.get("kind"), None)
            if ck:
                doc_keys.append(ck)
        for ent in _collect_entities_from_json(metadata):
            ck = upsert_node(ent["name"], ent.get("kind"), None)
            if ck:
                doc_keys.append(ck)
        add_edges(doc_keys)

    # Apply type hints from entity table
    for canon, k in entity_kinds.items():
        if canon in nodes:
            canonical_type[canon] = canonical_type.get(canon) or k
            nodes[canon]["type"] = canonical_type[canon]

    # Finalize labels to most common variant
    for canon, node in nodes.items():
        node["label"] = _best_label(variants.get(canon, Counter())) or node["label"]

    # Combined filtering: type + semantic hints + substring fallback
    if type_filter:
        nodes = {k: v for k, v in nodes.items() if (v.get("type") or "").lower() == type_filter}

    allowed_keys: set[str] = set(nodes.keys()) if not q else set()
    if q:
        # semantic allow
        allowed_keys |= semantic_allow
        # substring fallback on label
        for k, v in nodes.items():
            lbl = v.get("label")
            try:
                lbl_norm = str(lbl).lower()
            except Exception:
                lbl_norm = ""
            if q in lbl_norm:
                allowed_keys.add(k)

    if q:
        nodes = {k: v for k, v in nodes.items() if (not allowed_keys) or (k in allowed_keys)}

    # Expand by links: include neighbors of matched nodes for better link discovery
    expanded_keys = set(nodes.keys())
    if q and allowed_keys:
        for (a, b) in links.keys():
            if a in allowed_keys or b in allowed_keys:
                expanded_keys.add(a)
                expanded_keys.add(b)
        nodes = {k: v for k, v in nodes.items() if k in expanded_keys}

    # Recompute node set after filters and prune/expand edges
    node_set = set(nodes.keys())
    filtered_links = []
    for (a, b), weight in links.items():
        if a in node_set or b in node_set:
            filtered_links.append({"source": a, "target": b, "weight": weight})

    # Limit nodes and drop edges to removed nodes
    top_nodes = dict(
        sorted(nodes.items(), key=lambda kv: (kv[1].get("count", 0), kv[1].get("score", 0)), reverse=True)[:limit]
    )
    node_set = set(top_nodes.keys())
    filtered_links = [l for l in filtered_links if l["source"] in node_set and l["target"] in node_set]

    emit_event(
        "entities_graph",
        "done",
        payload={"nodes": len(top_nodes), "links": len(filtered_links)},
    )
    return jsonify(
        {
            "nodes": list(top_nodes.values()),
            "links": filtered_links,
        }
    )

@app.get("/favicon.ico")
def favicon():
    return send_from_directory(
        app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon"
    )


@app.get("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


# --- Status ---
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


# --- Logging endpoints ---
@app.get("/api/logs/stream")
@api_key_required
def logs_stream():
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(_event_stream(), mimetype="text/event-stream", headers=headers)


@app.get("/api/logs/recent")
@api_key_required
def logs_recent():
    limit = min(int(request.args.get("limit", 200)), _EVENT_BUFFER_LIMIT)
    with _event_lock:
        data = list(_event_buffer)[-limit:]
    return jsonify({"events": data})


@app.post("/api/logs/clear")
@api_key_required
def logs_clear():
    with _event_lock:
        _event_buffer.clear()
    emit_event("logs_clear", "Log buffer cleared")
    return jsonify({"status": "cleared"})


# --- Intel APIs ---
@app.get("/api/intel")
@api_key_required
def api_intel():
    q = request.args.get("q", "")
    entity = request.args.get("entity")
    min_conf = float(request.args.get("min_conf", 0))
    limit = int(request.args.get("limit", 50))
    emit_event("intel", "intel request received", payload={"q": q, "entity": entity})
    if q:
        rows = store.search_intelligence_data(q)
    else:
        rows = store.get_intelligence(
            entity_name=entity, min_confidence=min_conf, limit=limit
        )
    emit_event("intel", f"intel response ready", payload={"count": len(rows)})
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
    emit_event("semantic_search", "start", payload={"q": query, "top_k": top_k})
    try:
        results = vector_store.search(vec, top_k=top_k)
    except Exception as e:
        emit_event("semantic_search", f"vector search failed: {e}", level="error")
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
    emit_event("semantic_search", "done", payload={"returned": len(hits)})
    return jsonify({"semantic": hits})


@app.get("/api/pages")
@api_key_required
def api_pages():
    limit = int(request.args.get("limit", 200))
    q = (request.args.get("q") or "").strip()
    entity_filter = (request.args.get("entity_type") or "").strip()
    page_type_filter = (request.args.get("page_type") or "").strip()
    min_score = request.args.get("min_score")
    sort_by = (request.args.get("sort") or "fresh").lower()

    try:
        min_score_val = float(min_score) if min_score not in (None, "",) else None
    except ValueError:
        min_score_val = None

    pages = store.get_all_pages(
        q=q,
        entity_type=entity_filter or None,
        page_type=page_type_filter or None,
        min_score=min_score_val,
        sort=sort_by,
        limit=limit,
    )

    data = [p.to_dict() for p in pages]
    emit_event(
        "pages",
        "pages listed",
        payload={
            "count": len(data),
            "filters": {
                "q": q,
                "entity_type": entity_filter,
                "page_type": page_type_filter,
                "min_score": min_score_val,
                "sort": sort_by,
                "limit": limit,
            },
        },
    )
    return jsonify(data)


@app.get("/api/page")
@api_key_required
def api_page():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "url required"}), 400
    emit_event("page", "page fetch", payload={"url": url})
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
    session_id = body.get("session_id") or request.args.get("session_id")
    if not question:
        return jsonify({"error": "question required"}), 400

    emit_event("chat", "chat request received", payload={"session_id": session_id})

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
                    emit_event("chat", f"vector search failed: {e}", level="warning")
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
                emit_event("chat", "starting crawl", payload={"urls": live_urls})
                if getattr(settings, "chat_use_selenium", False):
                    browser = SeleniumBrowser(headless=True)
                    browser._init_driver()
                explorer.explore(live_urls, browser)
                emit_event("chat", "crawl complete", payload={"urls": live_urls})
            except Exception as e:
                logger.warning(f"Chat crawl failed: {e}")
                emit_event("chat", f"crawl failed: {e}", level="warning")
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
        if _looks_like_refusal(answer):
            answer = "I searched online but still couldn't find a definitive answer."

    emit_event("chat", "chat completed", payload={"session_id": session_id})
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
    emit_event("recorder", "search", payload={"q": q, "limit": limit})
    results = store.search_intel(
        keyword=q, limit=limit, entity_type=entity_type, page_type=page_type
    )
    emit_event("recorder", "search done", payload={"count": len(results)})
    return jsonify({"results": results})


@app.get("/api/recorder/health")
@api_key_required
def api_recorder_health():
    emit_event("recorder", "health")
    return jsonify({"status": "ok"})


@app.get("/api/recorder/queue")
@api_key_required
def api_recorder_queue():
    emit_event("recorder", "queue")
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
    emit_event("recorder", "mark", payload={"url": url, "mode": mode, "session_id": session_id})
    logger.info(f"[recorder-mark] ({session_id}) mode={mode} url={url}")
    return jsonify({"status": "received", "url": url, "mode": mode, "session_id": session_id})


# --- Crawl: wired to search.py logic ---
@app.post("/api/crawl")
@api_key_required
def api_crawl():
    body = request.get_json(silent=True) or {}
    emit_event("crawl", "start", payload={"body": body})
    try:
        result = run_crawl_api(body)
        emit_event("crawl", "done", payload={"status": "ok"})
        return jsonify(result)
    except ValueError as e:
        emit_event("crawl", f"bad request: {e}", level="warning")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        emit_event("crawl", f"failed: {e}", level="error")
        logger.exception("Crawl failed")
        return jsonify({"error": f"crawl failed: {e}"}), 500

def main():
    app.run(host="0.0.0.0", port=8080, debug=settings.debug)


if __name__ == "__main__":
    main()
