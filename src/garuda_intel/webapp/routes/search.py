"""Search and chat API routes."""

import logging
import re
from typing import Any

from flask import Blueprint, jsonify, request
from ..services.event_system import emit_event
from ..utils.request_helpers import safe_int, safe_float
from ...search import IntelligentExplorer, EntityProfile, EntityType, collect_candidates_simple
from ...browser.selenium import SeleniumBrowser


bp = Blueprint('search', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


def _looks_like_refusal(text: str) -> bool:
    """Check if LLM response looks like a refusal or gibberish."""
    if not text:
        return True
    t = text.lower()
    
    # Check for refusal patterns
    refusal_patterns = [
        "no information",
        "not have information",
        "unable to find",
        "does not contain",
        "cannot provide details",
        "i don't have enough",
        "no data",
        "insufficient context",
        "based solely on the given data",
        "insufficient_data",
    ]
    
    # Check for structural gibberish/artifact patterns (not specific words)
    gibberish_patterns = [
        "a user:",
        "document",
        "write a)",
        "name_congraining",  # Specific artifact from test case
        "beacon",
        "jsonleveraging",
    ]
    
    if any(p in t for p in refusal_patterns):
        return True
    
    if any(p in t for p in gibberish_patterns):
        logger.warning(f"Detected gibberish in answer: {text[:200]}")
        return True
    
    # Check for excessive special characters (sign of corruption)
    special_ratio = len(re.findall(r'[^a-zA-Z0-9\s.,!?;:()\-]', text)) / max(len(text), 1)
    if special_ratio > 0.25:
        logger.warning(f"Excessive special characters in answer: {special_ratio:.2%}")
        return True
    
    return False


def init_routes(api_key_required, settings, store, llm, vector_store):
    """Initialize routes with required dependencies."""
    
    @bp.get("/intel")
    @api_key_required
    def api_intel():
        q = request.args.get("q", "")
        entity = request.args.get("entity")
        min_conf = safe_float(request.args.get("min_conf"), 0)
        limit = safe_int(request.args.get("limit"), 50)
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
        """
        Combined semantic and SQL search with graceful degradation.
        Returns both semantic (vector) and SQL results for comprehensive coverage.
        """
        query = request.args.get("q", "").strip()
        top_k = safe_int(request.args.get("top_k"), 10)
        if not query:
            return jsonify({"error": "q required"}), 400
        
        emit_event("semantic_search", "start", payload={"q": query, "top_k": top_k})
        
        # Initialize result containers
        semantic_hits = []
        sql_hits = []
        
        # Try semantic/vector search if available
        if vector_store:
            try:
                vec = llm.embed_text(query)
                if vec:
                    results = vector_store.search(vec, top_k=top_k)
                    semantic_hits = [
                        {
                            "score": r.score,
                            "url": r.payload.get("url"),
                            "kind": r.payload.get("kind"),
                            "page_type": r.payload.get("page_type"),
                            "entity": r.payload.get("entity"),
                            "entity_type": r.payload.get("entity_type"),
                            "entity_kind": r.payload.get("entity_kind"),
                            "text": r.payload.get("text"),
                            "snippet": r.payload.get("text"),
                            "data": r.payload.get("data"),
                            "sql_page_id": r.payload.get("page_id"),
                            "sql_entity_id": r.payload.get("entity_id"),
                            "sql_intel_id": r.payload.get("intel_id"),
                        }
                        for r in results
                    ]
                    emit_event("semantic_search", f"vector search found {len(semantic_hits)} results")
                else:
                    emit_event("semantic_search", "embedding generation failed", level="warning")
            except Exception as e:
                emit_event("semantic_search", f"vector search failed: {e}", level="warning")
                logger.warning(f"Vector search failed: {e}")
        else:
            emit_event("semantic_search", "vector store not available", level="warning")
        
        # Always include SQL search results as fallback/supplement
        try:
            sql_results = store.search_intelligence_data(query)
            if sql_results:
                sql_hits = [
                    {
                        "score": r.get("confidence", r.get("score", 0)),
                        "url": r.get("url", ""),
                        "kind": "intel",
                        "page_type": r.get("page_type", ""),
                        "entity": r.get("entity", r.get("entity_name", "")),
                        "entity_type": r.get("entity_type", ""),
                        "entity_kind": r.get("entity_type", ""),
                        "text": str(r.get("data", "")),
                        "snippet": str(r.get("data", "")),
                        "data": r.get("data", {}),
                        "sql_intel_id": r.get("id", ""),
                        "sql_entity_id": r.get("entity_id", ""),
                    }
                    for r in sql_results[:top_k]
                ]
                emit_event("semantic_search", f"SQL search found {len(sql_hits)} results")
        except Exception as e:
            emit_event("semantic_search", f"SQL search failed: {e}", level="warning")
            logger.warning(f"SQL search failed: {e}")
        
        emit_event("semantic_search", "done", payload={
            "semantic_count": len(semantic_hits),
            "sql_count": len(sql_hits),
            "total": len(semantic_hits) + len(sql_hits)
        })
        
        # Return combined results with semantic results first
        return jsonify({
            "semantic": semantic_hits + sql_hits,
            "semantic_count": len(semantic_hits),
            "sql_count": len(sql_hits)
        })
    
    @bp.get("/pages")
    @api_key_required
    def api_pages():
        limit = safe_int(request.args.get("limit"), 200)
        q = (request.args.get("q") or "").strip()
        entity_filter = (request.args.get("entity_type") or "").strip()
        page_type_filter = (request.args.get("page_type") or "").strip()
        min_score = request.args.get("min_score")
        sort_by = (request.args.get("sort") or "fresh").lower()
    
        min_score_val = safe_float(min_score) if min_score not in (None, "",) else None
    
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
        top_k = safe_int(body.get("top_k") or request.args.get("top_k"), 6)
        session_id = body.get("session_id") or request.args.get("session_id")
        if not question:
            return jsonify({"error": "question required"}), 400
    
        emit_event("chat", "chat request received", payload={"session_id": session_id, "question": question})
    
        def gather_hits(q: str, limit: int, prioritize_rag: bool = True) -> list[dict[str, Any]]:
            """
            Gather context hits with RAG-first approach.
            
            Args:
                q: Query string
                limit: Maximum number of results per source
                prioritize_rag: If True, prioritize semantic (RAG) results over SQL
            
            Returns:
                List of context hits with source information
            """
            # Cap the maximum results to prevent resource exhaustion
            MAX_VECTOR_RESULTS = 100
            vec_hits = []
            sql_hits = []
            
            # Step 1: Try semantic/vector search first (RAG)
            if vector_store:
                emit_event("chat", "RAG lookup starting", payload={"query": q})
                vec = llm.embed_text(q)
                if vec:
                    try:
                        # Cap vector search to prevent excessive resource usage
                        vector_limit = min(limit * 2, MAX_VECTOR_RESULTS)
                        vector_results = vector_store.search(vec, top_k=vector_limit)
                        vec_hits = [
                            {
                                "url": r.payload.get("url"),
                                "snippet": r.payload.get("text", ""),
                                "score": r.score,
                                "source": "rag",
                                "kind": r.payload.get("kind", "unknown"),
                                "entity": r.payload.get("entity", ""),
                            }
                            for r in vector_results
                        ]
                        emit_event("chat", f"RAG found {len(vec_hits)} results", 
                                 payload={"count": len(vec_hits)})
                    except Exception as e:
                        logger.warning(f"Vector chat search failed: {e}")
                        emit_event("chat", f"RAG search failed: {e}", level="warning")
                else:
                    emit_event("chat", "RAG embedding generation failed", level="warning")
            else:
                emit_event("chat", "RAG unavailable - vector store not configured", level="warning")
            
            # Step 2: Get SQL/keyword results as fallback/supplement
            try:
                sql_hits = store.search_intel(keyword=q, limit=limit)
                for hit in sql_hits:
                    hit["source"] = "sql"
                emit_event("chat", f"SQL found {len(sql_hits)} results", 
                         payload={"count": len(sql_hits)})
            except Exception as e:
                logger.warning(f"SQL search failed: {e}")
                emit_event("chat", f"SQL search failed: {e}", level="warning")
            
            # Step 3: Merge and prioritize results
            if prioritize_rag and vec_hits:
                # RAG-first: Use semantic results primarily, SQL as supplement
                merged = vec_hits[:limit]
                # Add top SQL results if we need more context
                if len(merged) < limit:
                    merged.extend(sql_hits[:limit - len(merged)])
                emit_event("chat", "Using RAG-prioritized results", 
                         payload={"rag_count": len([h for h in merged if h.get("source") == "rag"]),
                                "sql_count": len([h for h in merged if h.get("source") == "sql"])})
            else:
                # Fallback: Mix both sources
                merged = vec_hits + sql_hits
                merged = merged[:limit]
            
            return merged
    
        # Phase 1: Initial RAG lookup with prioritization
        emit_event("chat", "Phase 1: Initial RAG lookup", payload={"question": question})
        merged_hits = gather_hits(question, top_k, prioritize_rag=True)
        
        # Check if we have enough high-quality RAG results
        rag_hits = [h for h in merged_hits if h.get("source") == "rag"]
        rag_quality_threshold = 0.7  # Minimum similarity score for RAG results
        high_quality_rag = [h for h in rag_hits if h.get("score", 0) >= rag_quality_threshold]
        
        emit_event("chat", f"RAG quality check: {len(high_quality_rag)}/{len(rag_hits)} high-quality hits",
                 payload={"high_quality": len(high_quality_rag), "total_rag": len(rag_hits)})
        
        answer = llm.synthesize_answer(question=question, context_hits=merged_hits)
        online_triggered = False
        live_urls = []
        crawl_reason = None
        retry_attempted = False
        paraphrased_queries = []
    
        # Evaluate answer quality and determine if retry is needed
        is_sufficient = llm.evaluate_sufficiency(answer) and not _looks_like_refusal(answer)
        quality_insufficient = len(high_quality_rag) == 0
        
        # Phase 2: Retry with paraphrasing and more hits if initial attempt insufficient
        if quality_insufficient or (not is_sufficient and len(high_quality_rag) < 2):
            emit_event("chat", "Phase 2: Retry with paraphrasing and more hits",
                     payload={"reason": "Insufficient initial results"})
            retry_attempted = True
            
            # Generate paraphrased queries
            paraphrased_queries = llm.paraphrase_query(question)
            emit_event("chat", f"Generated {len(paraphrased_queries)} paraphrased queries",
                     payload={"paraphrased": paraphrased_queries})
            
            # Gather results with increased limit and paraphrased queries
            increased_top_k = min(top_k * 2, 20)  # Double the hits, cap at 20
            all_retry_hits = []
            
            # Search with original query (increased hits)
            retry_hits = gather_hits(question, increased_top_k, prioritize_rag=True)
            all_retry_hits.extend(retry_hits)
            
            # Search with each paraphrased query
            for para_query in paraphrased_queries:
                para_hits = gather_hits(para_query, increased_top_k, prioritize_rag=True)
                all_retry_hits.extend(para_hits)
            
            # Deduplicate by URL and score, keep highest scoring versions
            # Preserve hits without URLs (e.g., SQL-only hits)
            unique_hits = {}
            hits_without_url = []
            
            for hit in all_retry_hits:
                url = hit.get("url", "")
                if url:
                    if url not in unique_hits or hit.get("score", 0) > unique_hits[url].get("score", 0):
                        unique_hits[url] = hit
                else:
                    # Preserve hits without URLs
                    hits_without_url.append(hit)
            
            # Sort by score descending and take top results
            deduplicated = list(unique_hits.values())
            deduplicated.sort(key=lambda x: x.get("score", 0), reverse=True)
            merged_hits = deduplicated[:increased_top_k] + hits_without_url[:increased_top_k // 4]
            
            # Re-check quality after retry
            rag_hits = [h for h in merged_hits if h.get("source") == "rag"]
            high_quality_rag = [h for h in rag_hits if h.get("score", 0) >= rag_quality_threshold]
            
            emit_event("chat", f"After retry: {len(high_quality_rag)}/{len(rag_hits)} high-quality RAG hits",
                     payload={"high_quality": len(high_quality_rag), "total_rag": len(rag_hits),
                            "total_results": len(merged_hits)})
            
            # Re-synthesize answer with new results
            answer = llm.synthesize_answer(question=question, context_hits=merged_hits)
            is_sufficient = llm.evaluate_sufficiency(answer) and not _looks_like_refusal(answer)
        
        # Phase 3: Intelligent crawling if still insufficient
        if not is_sufficient or quality_insufficient:
            # Determine crawl trigger reasons
            if not rag_hits:
                crawl_reason = "No RAG results found"
            elif len(high_quality_rag) < 2:
                if retry_attempted:
                    crawl_reason = f"Insufficient high-quality RAG results ({len(high_quality_rag)}) after retry"
                else:
                    crawl_reason = f"Insufficient high-quality RAG results ({len(high_quality_rag)})"
            else:
                if retry_attempted:
                    crawl_reason = "Answer insufficient despite RAG results and retry"
                else:
                    crawl_reason = "Answer insufficient despite RAG results"
            
            emit_event("chat", f"Phase 3: Intelligent crawling triggered - {crawl_reason}",
                     payload={"reason": crawl_reason})
            
            profile = EntityProfile(name=entity or "General Research", entity_type=EntityType.TOPIC)
            online_triggered = True
    
            # Generate targeted search queries (use paraphrased queries if available)
            search_queries = paraphrased_queries if paraphrased_queries else llm.generate_seed_queries(question, profile.name)
            emit_event("chat", f"Generated {len(search_queries)} search queries", 
                     payload={"queries": search_queries})
            
            candidates = collect_candidates_simple(search_queries, limit=5)
            live_urls = []
            seen_live = set()
            for cand in candidates:
                url = None
                if isinstance(cand, dict):
                    url = cand.get("href") or cand.get("url")
                elif isinstance(cand, str):
                    url = cand
                if url and url not in seen_live:
                    seen_live.add(url)
                    live_urls.append(url)
            
            emit_event("chat", f"Found {len(live_urls)} candidate URLs", 
                     payload={"urls": live_urls})
    
            if live_urls:
                # Initialize intelligent crawler with embeddings enabled
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
                    emit_event("chat", "Starting intelligent crawl with embedding generation",
                             payload={"urls": live_urls, "max_pages": getattr(settings, "chat_max_pages", 5)})
                    
                    if getattr(settings, "chat_use_selenium", False):
                        browser = SeleniumBrowser(headless=True)
                        browser._init_driver()
                    
                    # Execute crawl - this will generate embeddings automatically
                    explorer.explore(live_urls, browser)
                    
                    emit_event("chat", "Crawl complete - embeddings generated",
                             payload={"urls": live_urls})
                except Exception as e:
                    logger.warning(f"Chat crawl failed: {e}")
                    emit_event("chat", f"Crawl failed: {e}", level="warning")
                finally:
                    if browser:
                        try:
                            browser.close()
                        except Exception:
                            pass
    
                # Phase 4: Re-query with new embeddings
                emit_event("chat", "Phase 4: Re-querying with newly crawled data")
                merged_hits = gather_hits(question, top_k, prioritize_rag=True)
                answer = llm.synthesize_answer(question=question, context_hits=merged_hits)
                
                # Check improvement
                new_rag_hits = [h for h in merged_hits if h.get("source") == "rag"]
                emit_event("chat", f"After crawl: {len(new_rag_hits)} RAG results available",
                         payload={"new_rag_count": len(new_rag_hits)})
    
            # Improve error messages
            answer = answer.replace(
                "INSUFFICIENT_DATA",
                "I searched online but still couldn't find a definitive answer.",
            )
            if _looks_like_refusal(answer):
                answer = "I searched online but still couldn't find a definitive answer."
    
        emit_event("chat", "Chat completed successfully", 
                 payload={"session_id": session_id, "online_triggered": online_triggered, 
                         "retry_attempted": retry_attempted})
        
        return jsonify(
            {
                "answer": answer,
                "context": merged_hits,
                "entity": entity,
                "online_search_triggered": online_triggered,
                "retry_attempted": retry_attempted,
                "paraphrased_queries": paraphrased_queries,
                "live_urls": live_urls,
                "crawl_reason": crawl_reason,
                "rag_hits_count": len([h for h in merged_hits if h.get("source") == "rag"]),
                "sql_hits_count": len([h for h in merged_hits if h.get("source") == "sql"]),
            }
        )
    
    return bp
