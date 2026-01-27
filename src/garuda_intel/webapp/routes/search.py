"""Search and chat API routes."""

import logging
from flask import Blueprint, jsonify, request
from ..services.event_system import emit_event
from ...search import IntelligentExplorer, EntityProfile, EntityType, collect_candidates_simple
from ...browser.selenium import SeleniumBrowser


bp = Blueprint('search', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


def _looks_like_refusal(text: str) -> bool:
    """Check if LLM response looks like a refusal."""
    if not text:
        return True
    t = text.lower()
    patterns = [
        "no information",
        "not have information",
        "unable to find",
        "does not contain",
        "cannot provide details",
        "i don't have enough",
        "no data",
        "insufficient context",
        "based solely on the given data",
    ]
    return any(p in t for p in patterns)


def init_routes(api_key_required, settings, store, llm, vector_store):
    """Initialize routes with required dependencies."""
    
    @bp.get("/intel")
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
    
    @bp.get("/intel/semantic")
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
    
    @bp.get("/pages")
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
    
    @bp.get("/page")
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
    
    @bp.post("/chat")
    @api_key_required
    def api_chat():
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
                                "snippet": r.payload.get("text", ""),
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
    
    return bp
