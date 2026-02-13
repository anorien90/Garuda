"""Main handler functions for intel, run, and interactive chat."""

import json
import sys
import logging
from datetime import datetime
from urllib.parse import urlparse
import pandas as pd

from ..database.engine import SQLAlchemyStore
from ..database.models import Intelligence, Entity
from ..extractor.llm import LLMIntelExtractor
from ..vector.engine import QdrantVectorStore
from ..types.entity import EntityProfile, EntityType
from ..explorer.engine import IntelligentExplorer
from ..browser.selenium import SeleniumBrowser
from ..discover.seeds import generate_seeds
from ..discover.refresh import RefreshRunner
from ..explorer.scorer import URLScorer

from .utils import normalize_db_url, init_vector_store
from .filtering import _kind_filter, _filter_by_entity_name
from .deduplication import _dedupe_payload_hits, _aggregate_entities, _extract_entity_fields
from .hydration import _hydrate_intel, _hydrate_entities
from .seed_discovery import collect_candidates, collect_candidates_simple, load_seeds_from_db
from .active_mode import run_active_session
from .formatters import fetch_text

logger = logging.getLogger(__name__)


def handle_intel(args):
    """Integrated intel.py logic"""
    persistence_enabled = args.use_sqlite or bool(args.db_url)
    db_url = normalize_db_url(args.db_url, args.sqlite_path) if persistence_enabled else ""
    store = SQLAlchemyStore(db_url) if persistence_enabled else SQLAlchemyStore()

    # Deep semantic / hybrid search path
    if args.semantic_search or args.hybrid_search:
        llm = LLMIntelExtractor(args.ollama_url, args.model, embedding_model=args.embedding_model)
        vector_store = QdrantVectorStore(url=args.qdrant_url, collection=args.qdrant_collection)
        query_text = args.semantic_search or args.hybrid_search
        query_vec = llm.embed_text(query_text)
        if not query_vec:
            logging.error("Embedding model not available.")
            sys.exit(1)
        filt = _kind_filter(args.semantic_kind)
        results = vector_store.search(query_vec, top_k=args.top_k, filter_=filt)
        results = _dedupe_payload_hits(results)
        hits = [
            {
                "url": r.payload.get("url"),
                "score": r.score,
                "kind": r.payload.get("kind"),
                "page_type": r.payload.get("page_type"),
                "entity_type": r.payload.get("entity_type"),
                "entity_kind": r.payload.get("entity_kind") or r.payload.get("page_type"),
                "entity": r.payload.get("entity"),
                "title": r.payload.get("title"),
                "data": r.payload.get("data"),
                "text": r.payload.get("text"),
                "sql_intel_id": r.payload.get("sql_intel_id"),
                "sql_entity_id": r.payload.get("sql_entity_id"),
                "sql_page_id": r.payload.get("sql_page_id"),
                "source_url": r.payload.get("url"),
                "entity_refs": (r.payload.get("data") or {}).get("entity_refs"),
            }
            for r in results
        ]
        # Expand thin snippet windows
        try:
            from .snippet_expander import expand_snippet_hits
            hits = expand_snippet_hits(hits, store)
        except Exception:
            pass
        if args.semantic_kind == "entity" and args.entity_name:
            hits = _filter_by_entity_name(hits, args.entity_name)

        payload = {}
        if args.semantic_kind == "entity":
            aggregated = _aggregate_entities(hits, max_field_vals=args.top_k)
            if args.entity_name:
                aggregated = [a for a in aggregated if (a.get("entity") or "").lower().strip() == args.entity_name.lower().strip()]
            payload = {"semantic": hits, "aggregated": aggregated}
            if args.entity_field:
                payload["fields"] = _extract_entity_fields(aggregated, args.entity_field)
        else:
            payload = {"semantic": hits}

        # Optional SQL hydration
        if args.hydrate_sql and store:
            intel_ids = sorted({h.get("sql_intel_id") for h in hits if h.get("sql_intel_id")})
            entity_ids = sorted({h.get("sql_entity_id") for h in hits if h.get("sql_entity_id")})
            payload["sql"] = {
                "intelligence": _hydrate_intel(store, intel_ids),
                "entities": _hydrate_entities(store, entity_ids),
            }

        if args.hybrid_search:
            exact_hits = store.search_intelligence_data(query_text) if store else []
            payload["exact"] = exact_hits
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # Simple intel search/export
    if args.query:
        results = store.search_intelligence_data(args.query)
    else:
        results = store.get_intelligence(entity_name=args.entity, min_confidence=args.min_conf)

    if not results:
        print("[-] No intelligence entries found.")
        return

    flattened = []
    for r in results:
        row = {
            "entity": r["entity"],
            "confidence": r.get("confidence", 0),
            "date": r.get("created", ""),
        }
        if isinstance(r["data"], dict):
            for k, v in r["data"].items():
                row[k] = str(v)
        flattened.append(row)
    
    df = pd.DataFrame(flattened)

    if args.export:
        if args.export.endswith(".csv"):
            df.to_csv(args.export, index=False)
        else:
            df.to_json(args.export, orient="records", indent=2)
        print(f"[+] Exported {len(df)} entries to {args.export}")
    elif args.format == "table":
        print(df.to_string(index=False))
    else:
        print(json.dumps(results, indent=2))


def perform_rag_search(query, store, v_store, llm):
    """Gathers context from SQL and Vector DB for the LLM."""
    search_terms = llm.generate_seed_queries(query)
    context_hits = []
    
    # 1. Vector Search
    q_vec = llm.embed_text(query)
    if q_vec and v_store:
        try:
            hits = v_store.search(q_vec, top_k=5)
            context_hits.extend([{
                "url": h.payload.get("url"),
                "snippet": h.payload.get("text", ""),
                "kind": h.payload.get("kind", "unknown"),
                "data": h.payload.get("data") or {},
                "page_id": h.payload.get("sql_page_id"),
                "source_url": h.payload.get("url"),
            } for h in hits])
        except Exception as e:
            logging.debug(f"Vector search failed: {e}")

    # 2. SQL Keyword Search
    for term in search_terms:
        context_hits.extend(store.search_intel(term))

    # 3. Expand thin snippet windows
    try:
        from .snippet_expander import expand_snippet_hits
        context_hits = expand_snippet_hits(context_hits, store)
    except Exception:
        pass
    
    return llm.synthesize_answer(query, context_hits)


def interactive_chat(args):
    """The Autonomous Intel Loop with Live Web Search Integration."""
    store = SQLAlchemyStore(args.db_url if args.db_url else f"sqlite:///{args.sqlite_path}")
    llm = LLMIntelExtractor(ollama_url=args.ollama_url, model=args.model)
    v_store = None
    try:
        v_store = QdrantVectorStore(url=args.qdrant_url, collection=args.qdrant_collection)
    except Exception:
        logger.warning("Vector store unavailable. Chat will use SQL only.")
    
    entity_name = getattr(args, "entity_name", "General Research")
    profile = EntityProfile(name=entity_name, entity_type=EntityType.TOPIC)
    
    print(f"\n--- Intelligence Chat: {profile.name} ---")
    print("(Commands: 'exit' to quit)\n")
    
    while True:
        try:
            query = input(f"[{profile.name}]> ").strip()
            if query.lower() in ["exit", "quit"]:
                break
            if not query:
                continue

            print("[*] Searching existing knowledge base...")
            answer = perform_rag_search(query, store, v_store, llm)
            
            if llm.evaluate_sufficiency(answer):
                print(f"\n[AI]: {answer}\n")
                continue

            print("[!] Local data is insufficient. Resolving online search seeds...")
            
            search_queries = llm.generate_seed_queries(query, profile.name)
            print(f"[*] Generated Queries: {search_queries}")
            
            live_urls = collect_candidates_simple(search_queries, limit=5)
            
            if not live_urls:
                print("[!] No live URLs found from search queries.")
                print(f"\n[AI]: {answer.replace('INSUFFICIENT_DATA', 'I could not find information locally or online.')}\n")
                continue

            print(f"[*] Found {len(live_urls)} URLs. Starting autonomous crawl...")
            
            explorer = IntelligentExplorer(
                profile=profile, 
                persistence=store, 
                vector_store=v_store, 
                llm_extractor=llm,
                max_total_pages=args.max_pages if hasattr(args, "max_pages") else 5,
                score_threshold=5.0,
            )
            
            browser = None
            if args.use_selenium:
                browser = SeleniumBrowser(headless=True)
                browser._init_driver()
            
            try:
                explorer.explore(live_urls, browser)
            finally:
                if browser:
                    browser.close()

            print("[*] Re-evaluating with fresh intelligence...")
            answer = perform_rag_search(query, store, v_store, llm)
            final_text = answer.replace("INSUFFICIENT_DATA", "I searched online but still couldn't find a definitive answer.")
            print(f"\n[AI]: {final_text}\n")

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Chat Loop Error: {e}")


def handle_run(args, return_result: bool = False):
    persistence_enabled = args.use_sqlite or bool(args.db_url)
    db_url = normalize_db_url(args.db_url, args.sqlite_path) if persistence_enabled else ""
    store = SQLAlchemyStore(db_url) if persistence_enabled else None
    vector_store = init_vector_store(args)
    llm = LLMIntelExtractor(args.ollama_url, args.model, embedding_model=args.embedding_model)

    if args.active_mode and not return_result:
        run_active_session(store)
    elif args.active_mode and return_result:
        raise ValueError("active_mode is not supported via API")

    # Search-only paths
    if args.semantic_search or args.hybrid_search:
        if not vector_store:
            if return_result:
                raise ValueError("Semantic/hybrid search requires Qdrant.")
            logging.error("Semantic/hybrid search requires Qdrant.")
            sys.exit(1)
        query_vec = llm.embed_text(args.semantic_search or args.hybrid_search)
        if not query_vec:
            if return_result:
                raise ValueError("Embedding model not available.")
            logging.error("Embedding model not available.")
            sys.exit(1)
        filt = _kind_filter(args.semantic_kind)
        results = vector_store.search(query_vec, top_k=args.top_k, filter_=filt)
        results = _dedupe_payload_hits(results)
        hits = [
            {
                "url": r.payload.get("url"),
                "score": r.score,
                "kind": r.payload.get("kind"),
                "page_type": r.payload.get("page_type"),
                "entity_type": r.payload.get("entity_type"),
                "entity_kind": r.payload.get("entity_kind") or r.payload.get("page_type"),
                "entity": r.payload.get("entity"),
                "title": r.payload.get("title"),
                "data": r.payload.get("data"),
                "text": r.payload.get("text"),
                "sql_intel_id": r.payload.get("sql_intel_id"),
                "sql_entity_id": r.payload.get("sql_entity_id"),
                "sql_page_id": r.payload.get("sql_page_id"),
                "source_url": r.payload.get("url"),
                "entity_refs": (r.payload.get("data") or {}).get("entity_refs"),
            }
            for r in results
        ]
        # Expand thin snippet windows
        try:
            from .snippet_expander import expand_snippet_hits
            hits = expand_snippet_hits(hits, store)
        except Exception:
            pass
        if args.semantic_kind == "entity" and args.entity_name:
            hits = _filter_by_entity_name(hits, args.entity_name)
        if args.semantic_kind == "entity":
            aggregated = _aggregate_entities(hits, max_field_vals=args.top_k)
            if args.entity_name:
                aggregated = [a for a in aggregated if (a.get("entity") or "").lower().strip() == args.entity_name.lower().strip()]
            payload = {"semantic": hits, "aggregated": aggregated}
            if args.entity_field:
                payload["fields"] = _extract_entity_fields(aggregated, args.entity_field)
        else:
            payload = {"semantic": hits}
        if args.hybrid_search:
            keyword = args.hybrid_search.lower()
            exact_hits = store.search_intelligence_data(keyword) if store else []
            payload["exact"] = exact_hits
        if return_result:
            return payload
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.list_pages or args.fetch_text or args.refresh or args.search_intel:
        if not store:
            msg = "This operation requires a DB (use --use-sqlite or --db-url)."
            if return_result:
                raise ValueError(msg)
            logging.error(msg)
            sys.exit(1)
        if args.search_intel:
            results = store.search_intel(
                keyword=args.search_intel,
                limit=args.top_k,
                entity_type=args.search_entity_type or None,
                page_type=args.search_page_type or None,
            )
            if return_result:
                return {"results": results}
            print(json.dumps(results, ensure_ascii=False, indent=2))
            return
        if args.list_pages:
            pages = store.get_all_pages()
            data = [p.to_dict() for p in pages]
            if return_result:
                return {"pages": data}
            def serial(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError("Type not serializable")
            print(json.dumps(data, default=serial, indent=2))
            return
        if args.fetch_text:
            found = fetch_text(store, args.fetch_text)
            if found:
                if return_result:
                    return {"fetch_text": args.fetch_text, "status": "ok"}
                return
            logging.info("Text not found; refetching page...")
            rr = RefreshRunner(store=store, use_selenium=args.use_selenium, vector_store=vector_store, llm_extractor=llm)  # type: ignore
            rr.run(batch=1)
            found = fetch_text(store, args.fetch_text)
            if not found:
                msg = "Text still not available after refetch."
                if return_result:
                    return {"fetch_text": args.fetch_text, "status": "missing"}
                logging.error(msg)
            return
        if args.refresh:
            rr = RefreshRunner(store=store, use_selenium=args.use_selenium, vector_store=vector_store, llm_extractor=llm)  # type: ignore
            rr.run(batch=args.refresh_batch)
            if return_result:
                return {"refresh": "ok", "batch": args.refresh_batch}
            logging.info("Refresh complete.")
            return

    entity_name = args.entity
    if not entity_name and args.seed_url:
        try:
            entity_name = urlparse(args.seed_url[0]).netloc or "seeded-entity"
        except Exception:
            entity_name = "seeded-entity"
    if not entity_name:
        msg = "Entity name is required (or provide --seed-url/--seed-from-links/--seed-from-pages)."
        if return_result:
            raise ValueError(msg)
        logging.error(msg)
        sys.exit(1)
    profile = EntityProfile(
        name=entity_name,
        entity_type=EntityType(args.type),
        location_hint=args.location,
        official_domains=[],
    )

    seed_urls = []
    official_domains = []
    mode = "search"
    if (args.seed_from_links or args.seed_from_pages) and store:
        mode = "db-seeds"
        seed_urls = load_seeds_from_db(
            store=store,
            from_links=args.seed_from_links,
            from_pages=args.seed_from_pages,
            domains=args.seed_domain,
            patterns=args.seed_pattern,
            min_score=args.min_link_score,
            limit=args.seed_limit_db,
        )
        for u in seed_urls:
            try:
                domain = urlparse(u).netloc.lower().replace("www.", "")
                if not any(reg in domain for reg in URLScorer.REGISTRY_DOMAINS):
                    official_domains.append(domain)
            except Exception:
                continue
    elif args.seed_url:
        mode = "seed-url"
        seed_urls = args.seed_url
        for u in seed_urls:
            try:
                domain = urlparse(u).netloc.lower().replace("www.", "")
                if not any(reg in domain for reg in URLScorer.REGISTRY_DOMAINS):
                    official_domains.append(domain)
            except Exception:
                continue
    else:
        mode = "search"
        logging.info("Generating search queries...")
        queries = generate_seeds(profile, llm)
        logging.info("Collecting candidate URLs from SERP...")
        candidates = collect_candidates(queries, args.seed_limit)
        logging.info("Ranking candidates with LLM...")
        ranked = llm.rank_search_results(profile, candidates)
        seed_urls = [r.get("href") for r in ranked if r.get("href")]
        for r in ranked:
            if r.get("is_official") and r.get("href"):
                try:
                    domain = urlparse(r["href"]).netloc.lower().replace("www.", "")
                    if not any(reg in domain for reg in URLScorer.REGISTRY_DOMAINS):
                        official_domains.append(domain)
                except Exception:
                    continue
    profile.official_domains = official_domains
    explorer = IntelligentExplorer(
        profile=profile,
        use_selenium=args.use_selenium,
        max_pages_per_domain=args.max_pages,
        max_total_pages=args.total_pages or args.max_pages * 20,
        max_depth=args.max_depth,
        score_threshold=args.score_threshold,
        persistence=store,
        vector_store=vector_store,
        llm_extractor=llm,
        enable_llm_link_rank=args.enable_llm_link_rank,
    )
    browser = None
    if args.use_selenium:
        try:
            browser = SeleniumBrowser(headless=True, timeout=8)
            browser._init_driver()
        except Exception as e:
            logging.warning(f"Could not init Selenium: {e}")
            browser = None
    logging.info(f"Starting exploration (mode={mode}) with {len(seed_urls)} seeds...")
    try:
        explored = explorer.explore(seed_urls, browser)
    finally:
        if browser:
            browser.close()
    result = {
        "entity": entity_name,
        "entity_type": args.type,
        "mode": mode,
        "seed_query": args.seed_query if args.seed_query else "",
        "seeds": seed_urls,
        "official_domains": official_domains,
        "pages_explored": len(explored),
        "explored_data": explored,
    }
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logging.info(f"Wrote results to {args.output}")
    elif return_result:
        return result
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
