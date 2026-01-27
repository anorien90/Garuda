from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS
from functools import wraps
import logging
from datetime import datetime, timezone
import json
import queue
import threading
from collections import deque, Counter
import itertools
from typing import Generator
import re

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


def _collect_entities_from_json(obj, path="root"):
    """
    Recursively walk a JSON-like structure and collect entities.
    Returns list of {"name": str, "kind": Optional[str], "path": str}
    """
    out = []
    if obj is None:
        return out
    if isinstance(obj, str):
        out.append({"name": obj, "kind": None, "path": path})
        return out
    if isinstance(obj, dict):
        maybe_name = obj.get("name") or obj.get("entity") or obj.get("value")
        maybe_kind = obj.get("type") or obj.get("kind") or obj.get("entity_type")
        if maybe_name:
            out.append({"name": maybe_name, "kind": maybe_kind.lower() if maybe_kind else None, "path": path})
        for k, v in obj.items():
            out.extend(_collect_entities_from_json(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_collect_entities_from_json(v, f"{path}[{i}]"))
    return out


def _as_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def _collect_images_from_metadata(meta: dict):
    """
    Extract image-like references from metadata/structured data.
    Looks at common OpenGraph/Twitter and generic keys.
    """
    if not isinstance(meta, dict):
        return []
    candidates = []
    for key in ("image", "og_image", "og:image", "twitter:image", "images", "photos", "thumbnails"):
        for item in _as_list(meta.get(key)):
            url = None
            alt = None
            source = key
            if isinstance(item, dict):
                url = item.get("url") or item.get("src") or item.get("content")
                alt = item.get("alt") or item.get("title") or item.get("label")
            else:
                url = item
            if url:
                candidates.append({"url": url, "alt": alt, "source": source})
    return candidates


def _parse_list_param(val: str | None, default: set[str]) -> set[str]:
    if not val:
        return set(default)
    return {v.strip().lower() for v in val.split(",") if v.strip()}


def _seeds_from_query(nodes: list[dict], query: str) -> set[str]:
    if not query:
        return {n["id"] for n in nodes}
    q = query.lower()
    seeds = {n["id"] for n in nodes if q in str(n.get("label", "")).lower() or q in str(n.get("id", "")).lower()}
    return seeds or {n["id"] for n in nodes}


def _filter_by_depth(nodes: list[dict], links: list[dict], depth_limit: int, seeds: set[str]) -> tuple[list[dict], list[dict]]:
    if depth_limit is None or depth_limit < 0 or depth_limit >= 99:
        return nodes, links
    adj: dict[str, set[str]] = {}
    for l in links:
        a, b = l["source"], l["target"]
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    keep: set[str] = set(seeds)
    queue: list[tuple[str, int]] = [(s, 0) for s in seeds]
    while queue:
        node_id, d = queue.pop(0)
        if d >= depth_limit:
            continue
        for nb in adj.get(node_id, []):
            if nb not in keep:
                keep.add(nb)
                queue.append((nb, d + 1))
    kept_nodes = [n for n in nodes if n["id"] in keep]
    kept_set = {n["id"] for n in kept_nodes}
    kept_links = [l for l in links if l["source"] in kept_set and l["target"] in kept_set]
    return kept_nodes, kept_links

@app.get("/api/entities/graph")
@api_key_required
def api_entities_graph():
    """
    Build entity co-occurrence graph with combined semantic + SQL filtering.
    """
    q = (request.args.get("query") or "").strip().lower()
    type_filter = (request.args.get("type") or "").strip().lower()
    min_score = float(request.args.get("min_score", 0) or 0)
    limit = min(int(request.args.get("limit", 100) or 100), 500)
    depth_limit = int(request.args.get("depth", 1) or 1)

    node_type_filters = _parse_list_param(
        request.args.get("node_types"),
        default={"entity", "person", "org", "location", "product", "page", "intel", "image"},
    )
    edge_kind_filters = _parse_list_param(
        request.args.get("edge_kinds"),
        default={"cooccurrence", "page-mentions", "intel-mentions", "intel-primary", "page-image", "link"},
    )

    emit_event(
        "entities_graph",
        "start",
        payload={
            "q": q,
            "type": type_filter,
            "min_score": min_score,
            "limit": limit,
            "depth": depth_limit,
            "node_types": sorted(node_type_filters),
            "edge_kinds": sorted(edge_kind_filters),
        },
    )

    try:
        nodes: dict[str, dict] = {}
        variants: dict[str, Counter[str]] = {}
        links: dict[tuple[str, str], dict] = {}
        canonical_type: dict[str, str] = {}
        entity_ids: dict[str, int] = {}

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

        def ensure_node(node_id: str, label: str, node_type: str, score: float | None = None, count_inc: int = 1, meta: dict | None = None):
            if not node_id:
                return None
            node = nodes.get(node_id, {"id": node_id, "label": label or node_id, "type": node_type, "score": 0, "count": 0, "meta": {}})
            node["count"] = (node.get("count") or 0) + (count_inc or 0)
            if score is not None:
                node["score"] = max(node.get("score") or 0, score)
            if meta:
                node_meta = node.get("meta") or {}
                node_meta.update({k: v for k, v in meta.items() if v is not None})
                node["meta"] = node_meta
            nodes[node_id] = node
            return node_id

        def upsert_entity(raw_name: str, kind: str | None, score: float | None, meta: dict | None = None):
            if not raw_name:
                return None
            canon = _canonical(raw_name)
            if not canon:
                return None
            variants.setdefault(canon, Counter()).update([raw_name])
            node_id = ensure_node(canon, raw_name, node_type="entity", score=score, meta={"entity_kind": kind, **(meta or {})})
            if kind:
                k = kind.lower()
                canonical_type[canon] = canonical_type.get(canon) or k
                nodes[canon]["type"] = canonical_type[canon]
            if canon in entity_ids:
                nodes[canon]["meta"]["entity_id"] = entity_ids[canon]
                nodes[canon]["meta"]["source_id"] = entity_ids[canon]
            return node_id

        def add_edge(a: str, b: str, kind: str, weight: int = 1, meta: dict | None = None):
            if not a or not b:
                return
            key = tuple(sorted((a, b)))
            if key not in links:
                links[key] = {"weight": 0, "kind": kind, "meta": meta or {}}
            links[key]["weight"] += weight
            if kind and links[key].get("kind") != kind:
                links[key]["kind"] = kind
            if meta:
                edge_meta = links[key].get("meta") or {}
                edge_meta.update({k: v for k, v in meta.items() if v is not None})
                links[key]["meta"] = edge_meta

        def add_cooccurrence_edges(entity_keys: list[str]):
            unique_keys = sorted(set([e for e in entity_keys if e]))
            for a, b in itertools.combinations(unique_keys, 2):
                add_edge(a, b, kind="cooccurrence", weight=1)

        semantic_allow = semantic_entity_hints(q, top_k=200) if q else set()


        with store.Session() as session:
            intel_q = session.query(db_models.Intelligence)
            if q:
                intel_q = intel_q.filter(db_models.Intelligence.entity_name.ilike(f"%{q}%"))
            if min_score:
                intel_q = intel_q.filter(db_models.Intelligence.confidence >= min_score)
            intel_rows = intel_q.limit(5000).all()

            page_rows = session.query(db_models.PageContent).limit(5000).all()
            link_rows = session.query(db_models.Link).limit(10000).all()

            entity_kinds = {}
            for ent in session.query(db_models.Entity).limit(10000).all():
                canon = _canonical(ent.name)
                if canon:
                    if ent.kind:
                        entity_kinds[canon] = ent.kind.lower()
                    entity_ids[canon] = ent.id

        # Process intel rows
        for row in intel_rows:
            try:
                payload = json.loads(row.data or "{}")
            except Exception:
                payload = {}
            payload_preview = payload if isinstance(payload, dict) else {}
            if len(json.dumps(payload_preview)) > 4000:
                payload_preview = {"truncated": True, "keys": list(payload.keys())[:50]}
            primary = upsert_entity(
                row.entity_name,
                payload.get("entity_type") or payload.get("entity_kind") if isinstance(payload, dict) else None,
                row.confidence,
                meta={"source": "intel", "intel_id": row.id, "source_id": row.id},
            )
            intel_node_id = ensure_node(
                f"intel:{row.id}",
                label=f"Intel #{row.id}",
                node_type="intel",
                score=row.confidence,
                meta={
                    "entity": row.entity_name,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "payload_preview": payload_preview,
                    "source_url": payload.get("url") if isinstance(payload, dict) else None,
                    "intel_id": row.id,
                    "source_id": row.id,
                },
            )
            if primary and intel_node_id:
                add_edge(primary, intel_node_id, kind="intel-primary", meta={"source": "intel"})
            doc_entity_keys = []
            for ent in _collect_entities_from_json(payload):
                ck = upsert_entity(ent["name"], ent.get("kind"), None, meta={"path": ent.get("path")})
                if ck:
                    doc_entity_keys.append(ck)
                    if intel_node_id:
                        add_edge(intel_node_id, ck, kind="intel-mentions", meta={"path": ent.get("path"), "entity": ent.get("name")})
            add_cooccurrence_edges(doc_entity_keys + ([primary] if primary else []))

        # Process page_content
        for p in page_rows:
            try:
                extracted = json.loads(p.extracted_json or "{}")
            except Exception:
                extracted = {}
            try:
                metadata = json.loads(p.metadata_json or "{}")
            except Exception:
                metadata = {}

            page_meta = {
                "page_type": None,
                "entity_type": None,
                "domain_key": None,
                "score": None,
                "last_status": None,
                "last_fetch_at": None,
                "text_length": None,
                "depth": None,
            }
            page_row = store.get_page(p.page_url)
            if page_row:
                def _get(obj, key):
                    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)

                page_meta.update(
                    {
                        "page_type": _get(page_row, "page_type"),
                        "entity_type": _get(page_row, "entity_type"),
                        "domain_key": _get(page_row, "domain_key"),
                        "score": _get(page_row, "score"),
                        "last_status": _get(page_row, "last_status"),
                        "last_fetch_at": (_get(page_row, "last_fetch_at").isoformat() if _get(page_row, "last_fetch_at") else None),
                        "text_length": _get(page_row, "text_length"),
                        "depth": _get(page_row, "depth"),
                    }
                )

            page_meta.update(
                {
                    "content_type": metadata.get("content_type"),
                    "language": metadata.get("language"),
                    "site_name": metadata.get("site_name"),
                    "structured_data": metadata.get("structured_data"),
                }
            )

            content_preview = None
            try:
                content_text = p.text or ""
                if content_text:
                    content_preview = content_text[:1200]
            except Exception:
                content_preview = None

            page_node_id = ensure_node(
                p.page_url,
                label=p.page_url,
                node_type="page",
                score=page_meta.get("score"),
                meta={**page_meta, "content_preview": content_preview, "source_url": p.page_url, "page_url": p.page_url, "source_id": p.page_url},
            )
            doc_entity_keys = []
            for ent in _collect_entities_from_json(extracted):
                ck = upsert_entity(ent["name"], ent.get("kind"), None, meta={"path": ent.get("path")})
                if ck:
                    doc_entity_keys.append(ck)
                    add_edge(page_node_id, ck, kind="page-mentions", meta={"path": ent.get("path")})
            for ent in _collect_entities_from_json(metadata):
                ck = upsert_entity(ent["name"], ent.get("kind"), None, meta={"path": ent.get("path")})
                if ck:
                    doc_entity_keys.append(ck)
                    add_edge(page_node_id, ck, kind="page-mentions", meta={"path": ent.get("path"), "source": "metadata"})
            for img in _collect_images_from_metadata(metadata):
                img_id = f"img:{img['url']}"
                ensure_node(
                    img_id,
                    label=img["url"],
                    node_type="image",
                    meta={
                        "alt": img.get("alt"),
                        "source": img.get("source"),
                        "page": p.page_url,
                        "thumb": img.get("url"),
                        "source_url": img.get("url"),
                        "source_id": img.get("url"),
                    },
                )
                add_edge(page_node_id, img_id, kind="page-image", meta={"source": img.get("source"), "url": img["url"]})
            add_cooccurrence_edges(doc_entity_keys)

        # Process link graph
        for l in link_rows:
            from_id = ensure_node(l.from_url, l.from_url, node_type="page", meta={"depth": l.depth, "reason": l.reason, "source_url": l.from_url, "source_id": l.from_url})
            to_id = ensure_node(l.to_url, l.to_url, node_type="page", meta={"source_url": l.to_url, "source_id": l.to_url})
            add_edge(
                from_id,
                to_id,
                kind="link",
                weight=int(l.score or 1),
                meta={"anchor": l.anchor_text, "reason": l.reason, "score": l.score, "from_kind": "page", "to_kind": "page"},
            )

        for canon, k in entity_kinds.items():
            if canon in nodes:
                canonical_type[canon] = canonical_type.get(canon) or k
                nodes[canon]["type"] = canonical_type[canon]
                if canon in entity_ids:
                    nodes[canon]["meta"]["entity_id"] = entity_ids[canon]
                    nodes[canon]["meta"]["source_id"] = entity_ids[canon]

        for canon, node in nodes.items():
            node["label"] = _best_label(variants.get(canon, Counter())) or node["label"]

        if type_filter:
            nodes = {k: v for k, v in nodes.items() if (v.get("type") or "").lower() == type_filter}

        nodes = {
            k: v
            for k, v in nodes.items()
            if (v.get("type") or "").lower() in node_type_filters
            or (v.get("meta") or {}).get("entity_kind") in node_type_filters
        }

        filtered_links = []
        node_ids = set(nodes.keys())
        for (a, b), edge in links.items():
            if edge.get("kind") not in edge_kind_filters:
                continue
            if a in node_ids and b in node_ids:
                filtered_links.append(
                    {
                        "source": a,
                        "target": b,
                        "weight": edge.get("weight", 1),
                        "kind": edge.get("kind"),
                        "meta": edge.get("meta") or {},
                    }
                )

        allowed_keys: set[str] = set(nodes.keys()) if not q else set()
        if q:
            allowed_keys |= semantic_allow
            for k, v in nodes.items():
                lbl_norm = str(v.get("label") or "").lower()
                if q in lbl_norm or q in k.lower():
                    allowed_keys.add(k)
            nodes = {k: v for k, v in nodes.items() if (not allowed_keys) or (k in allowed_keys)}
            node_ids = set(nodes.keys())
            filtered_links = [l for l in filtered_links if l["source"] in node_ids and l["target"] in node_ids]

        if q and allowed_keys:
            expanded = set(nodes.keys())
            for l in filtered_links:
                if l["source"] in allowed_keys or l["target"] in allowed_keys:
                    expanded.add(l["source"])
                    expanded.add(l["target"])
            nodes = {k: v for k, v in nodes.items() if k in expanded}
            node_ids = set(nodes.keys())
            filtered_links = [l for l in filtered_links if l["source"] in node_ids and l["target"] in node_ids]

        seeds = _seeds_from_query(list(nodes.values()), q)
        depth_nodes, depth_links = _filter_by_depth(list(nodes.values()), filtered_links, depth_limit, seeds)

        sorted_nodes = sorted(depth_nodes, key=lambda n: (n.get("count", 0), n.get("score", 0)), reverse=True)
        top_nodes = {n["id"]: n for n in sorted_nodes[:limit]}
        if q and allowed_keys:
            for l in depth_links:
                if l["source"] in allowed_keys or l["target"] in allowed_keys:
                    if l["source"] in nodes:
                        top_nodes[l["source"]] = nodes[l["source"]]
                    if l["target"] in nodes:
                        top_nodes[l["target"]] = nodes[l["target"]]

        node_set = set(top_nodes.keys())
        depth_links = [l for l in depth_links if l["source"] in node_set and l["target"] in node_set]

        emit_event("entities_graph", "done", payload={"nodes": len(top_nodes), "links": len(depth_links)})
        return jsonify({"nodes": list(top_nodes.values()), "links": depth_links})
    except Exception as e:
        logger.exception("entities_graph failed")
        emit_event("entities_graph", f"failed: {e}", level="error")
        return jsonify({"error": "internal_error", "detail": str(e)}), 500


@app.get("/api/entities/graph/node")
@api_key_required
def api_entities_graph_node():
    """
    Fetch full detail for a graph node on demand to keep the main graph response small.
    Query params:
      id: node id (e.g., intel:123, page URL, img:<url>, or canonical entity id)
    """
    node_id = request.args.get("id")
    if not node_id:
        return jsonify({"error": "id required"}), 400

    if node_id.startswith("intel:"):
        try:
            intel_id = int(node_id.split(":", 1)[1])
        except ValueError:
            return jsonify({"error": "bad intel id"}), 400
        with store.Session() as s:
            row = s.get(db_models.Intelligence, intel_id)
            if not row:
                return jsonify({"error": "not found"}), 404
            try:
                payload = json.loads(row.data or "{}")
            except Exception:
                payload = {}
            return jsonify(
                {
                    "id": node_id,
                    "type": "intel",
                    "meta": {
                        "entity": row.entity_name,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "source_url": payload.get("url") if isinstance(payload, dict) else None,
                        "intel_id": row.id,
                        "source_id": row.id,
                    },
                    "payload": payload,
                }
            )

    with store.Session() as s:
        page_row = s.get(db_models.Page, node_id)
        pc_row = s.get(db_models.PageContent, node_id)
        if page_row or pc_row:
            try:
                metadata = json.loads(pc_row.metadata_json or "{}") if pc_row else {}
            except Exception:
                metadata = {}
            try:
                extracted = json.loads(pc_row.extracted_json or "{}") if pc_row else {}
            except Exception:
                extracted = {}
            return jsonify(
                {
                    "id": node_id,
                    "type": "page",
                    "meta": {
                        "source_url": node_id,
                        "source_id": node_id,
                    },
                    "page": page_row.to_dict() if page_row else None,
                    "content": {
                        "text": pc_row.text if pc_row else None,
                        "html": None,
                        "metadata": metadata,
                        "extracted": extracted,
                        "fetch_ts": pc_row.fetch_ts.isoformat() if pc_row and pc_row.fetch_ts else None,
                    },
                }
            )

    img_url = node_id[4:] if node_id.startswith("img:") else node_id
    return jsonify({"id": node_id, "type": "image", "meta": {"source_url": img_url, "source_id": img_url}})


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon")


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
        rows = store.get_intelligence(entity_name=entity, min_confidence=min_conf, limit=limit)
    emit_event("intel", "intel response ready", payload={"count": len(rows)})
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
        profile = EntityProfile(name=entity or "General Research", entity_type=EntityType.TOPIC)
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
    results = store.search_intel(keyword=q, limit=limit, entity_type=entity_type, page_type=page_type)
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
