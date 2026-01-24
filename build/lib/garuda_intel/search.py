import argparse
import pandas as pd
import json
import logging
import sys
import time
import queue
import os
from urllib.parse import urlparse
from datetime import datetime, date
from typing import List, Dict, Any



def try_load_dotenv():
    try:
        import dotenv
        dotenv.load_dotenv(override=True)
        print("[.env] Loaded environment from .env files.")
    except ImportError:
        pass

try_load_dotenv()

logger = logging.getLogger(__name__)

from ddgs import DDGS
from sqlalchemy import select
from qdrant_client.http import models as qmodels

from .recorder.app import start_server_thread
from .browser.active import RecordingBrowser, get_env_chrome_args, get_browser_start_url, get_session_id
from .recorder.ingest import RecorderIngestor
from .browser.selenium import SeleniumBrowser
from .discover.seeds import generate_seeds
from .extractor.llm import LLMIntelExtractor
from .explorer.engine import IntelligentExplorer
from .types.entity import EntityProfile, EntityType
from .database.engine import SQLAlchemyStore
from .database.models import Link, Page, PageContent, Intelligence, Entity
from .discover.refresh import RefreshRunner
from .explorer.scorer import URLScorer
from .vector.engine import QdrantVectorStore

def add_common_logging(parser: argparse.ArgumentParser):
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

def add_store_args(parser: argparse.ArgumentParser):
    parser.add_argument("--use-sqlite", action="store_true", help="Use SQLite DB at sqlite-path (default crawler.db)")
    parser.add_argument("--db-url", default="", help="SQLAlchemy DB URL (default sqlite:///crawler.db)")
    parser.add_argument("--sqlite-path", default="crawler.db", help="SQLite file path if db-url not set")


def add_llm_vector_args(parser: argparse.ArgumentParser, include_query_flags: bool = False):
    parser.add_argument("--ollama-url", default="http://localhost:11434/api/generate", help="Ollama endpoint")
    parser.add_argument("--model", default="granite3.1-dense:8b", help="LLM model name")
    parser.add_argument("--embedding-model", default="sentence-transformers/all-MiniLM-L6-v2", help="Embedding model name")
    parser.add_argument("--qdrant-url", default="http://localhost:6333", help="Qdrant URL")
    parser.add_argument("--qdrant-collection", default="pages", help="Qdrant collection name")
    parser.add_argument("--top-k", type=int, default=10, help="Number of search results to return")
    if include_query_flags:
        parser.add_argument("--semantic-search", default="", help="Semantic search query (Qdrant)")
        parser.add_argument("--hybrid-search", default="", help="Hybrid search query (exact + semantic)")
        parser.add_argument(
            "--semantic-kind",
            choices=["any", "page", "page_sentence", "finding", "entity", "page_raw"],
            default="any",
            help="Restrict semantic results to a payload kind",
        )
        parser.add_argument(
            "--entity-name",
            default="",
            help="Filter semantic entity results by exact entity name (case-insensitive)",
        )
        parser.add_argument(
            "--entity-field",
            action="append",
            default=[],
            help="When semantic-kind=entity, return only these fields (repeatable). Example: --entity-field bio",
        )
        parser.add_argument(
            "--hydrate-sql",
            action="store_true",
            help="If set, hydrate sql_intel_id/sql_entity_id from SQLite and include rows in output",
        )


def init_vector_store(args) -> QdrantVectorStore | None:
    try:
        return QdrantVectorStore(url=args.qdrant_url, collection=args.qdrant_collection)
    except Exception as e:
        logging.error(f"Failed to init Qdrant vector store: {e}")
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Entity-aware crawler CLI")
    subparsers = parser.add_subparsers(dest="command", required=False)

    run_parser = subparsers.add_parser("run", help="Run the intelligent crawler")
    add_common_logging(run_parser)
    add_store_args(run_parser)
    add_llm_vector_args(run_parser, include_query_flags=True)

    chat_p = subparsers.add_parser("chat")
    chat_p.add_argument("--entity-name", default="General Research")
    chat_p.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    chat_p.add_argument("--model", default="granite3.1-dense:8b")
    chat_p.add_argument("--sqlite-path", default="crawler.db")
    chat_p.add_argument("--db-url", default="")
    chat_p.add_argument("--qdrant-url", default="http://localhost:6333")
    chat_p.add_argument("--qdrant-collection", default="pages")
    chat_p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    chat_p.add_argument("--max-pages", type=int, default=10)
    chat_p.add_argument("--use-selenium", action="store_true", default=False, help="Enable Selenium (Chrome) fetching")
    chat_p.add_argument("--use-sqlite", action="store_true", help="Use SQLite DB at sqlite-path (default crawler.db)")

    run_parser.add_argument("entity", nargs="?", help="Entity name to search (company/person/topic)")
    run_parser.add_argument("--type", choices=[e.value for e in EntityType], default="company", help="Entity type")
    run_parser.add_argument("--location", default="", help="Location hint (optional)")
    run_parser.add_argument("--max-pages", type=int, default=10, help="Max pages per domain")
    run_parser.add_argument("--total-pages", type=int, default=50, help="Max total pages (default: max_pages*20)")
    run_parser.add_argument("--max-depth", type=int, default=2, help="Max crawl depth")
    run_parser.add_argument("--score-threshold", type=float, default=35.0, help="Scoring threshold for following links")
    run_parser.add_argument("--seed-limit", type=int, default=25, help="Max SERP results per query")
    run_parser.add_argument("--use-selenium", action="store_true", default=False, help="Enable Selenium (Chrome) fetching")
    run_parser.add_argument("--active-mode", action="store_true", help="Interactive browser: record your pageviews")
    run_parser.add_argument("--output", default="", help="Write crawl results JSON to this file")
    run_parser.add_argument("--list-pages", action="store_true", help="List stored page URLs (requires DB)")
    run_parser.add_argument("--fetch-text", default="", help="Fetch stored text_content for URL (requires DB). Refetch if missing.")
    run_parser.add_argument("--refresh", action="store_true", help="Run refresh on stored pages (requires DB)")
    run_parser.add_argument("--refresh-batch", type=int, default=50, help="Batch size for refresh")
    run_parser.add_argument("--seed-url", action="append", default=[], help="Seed URL(s) to start exploration from (bypass SERP)")
    run_parser.add_argument("--seed-query", default="", help="Optional query/context string when using --seed-url")
    run_parser.add_argument("--seed-from-links", action="store_true", help="Seed from stored links table (requires DB)")
    run_parser.add_argument("--seed-from-pages", action="store_true", help="Seed from stored pages table (requires DB)")
    run_parser.add_argument("--seed-domain", action="append", default=[], help="Only use seeds whose domain contains this (repeatable)")
    run_parser.add_argument("--seed-pattern", action="append", default=[], help="Only use seeds whose URL matches this regex (repeatable)")
    run_parser.add_argument("--min-link-score", type=float, default=0.0, help="Only use stored links with score >= this")
    run_parser.add_argument("--seed-limit-db", type=int, default=20, help="Max seeds pulled from DB for continuation")
    run_parser.add_argument("--search-intel", default="", help="Keyword to search within gathered text_content (requires DB)")
    run_parser.add_argument("--search-entity-type", default="", help="Filter search by entity_type")
    run_parser.add_argument("--search-page-type", default="", help="Filter search by page_type")
    run_parser.add_argument("--enable-llm-link-rank", action="store_true", help="Use LLM to rank sublinks before scoring")

    intel_parser = subparsers.add_parser("intel", help="Search and export gathered intelligence")
    add_common_logging(intel_parser)
    add_store_args(intel_parser)
    add_llm_vector_args(intel_parser, include_query_flags=True)

    intel_parser.add_argument("--query", help="Text search across all extracted data")
    intel_parser.add_argument("--entity", help="Filter by entity name")
    intel_parser.add_argument("--min-conf", type=float, default=0.0, help="Min confidence score")
    intel_parser.add_argument("--format", choices=["json", "csv", "table"], default="table")
    intel_parser.add_argument("--export", help="Filename for export (e.g. results.csv)")

    return parser.parse_args()

def _kind_filter(kind: str) -> qmodels.Filter | None:
    if kind == "any":
        return None
    return qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="kind",
                match=qmodels.MatchValue(value=kind),
            )
        ]
    )

def _dedupe_payload_hits(hits: List[Any]) -> List[Any]:
    seen = set()
    uniq = []
    for h in hits:
        pid = getattr(h, "id", None) or getattr(h, "point_id", None) or (str(h.payload.get("url")) + str(h.payload.get("kind")))
        if pid in seen:
            continue
        seen.add(pid)
        uniq.append(h)
    return uniq

def _filter_by_entity_name(hits: List[Dict], entity_name: str) -> List[Dict]:
    if not entity_name:
        return hits
    needle = entity_name.lower().strip()
    out = []
    for h in hits:
        name = (h.get("entity") or "").lower().strip()
        if name == needle:
            out.append(h)
    return out

def _aggregate_entities(hits: List[Dict], max_field_vals: int) -> List[Dict]:
    """
    Merge entity attrs by (entity, entity_kind).
    Keep up to max_field_vals unique values per attribute, preserving encounter order.
    """
    agg = {}
    for h in hits:
        name = h.get("entity") or h.get("payload", {}).get("entity")
        kind = h.get("entity_kind") or h.get("page_type") or h.get("payload", {}).get("entity_kind")
        data = h.get("data") or {}
        attrs = {}
        if isinstance(data, dict):
            attrs = data.get("attrs") or data
        key = (name, kind)
        if key not in agg:
            agg[key] = {
                "entity": name,
                "entity_kind": kind,
                "sources": [],
                "attrs": {},
            }
        # sources: preserve order, dedupe
        src = h.get("url")
        if src and src not in agg[key]["sources"]:
            agg[key]["sources"].append(src)
        # attrs: lists up to max_field_vals
        for k, v in (attrs or {}).items():
            if v in (None, ""):
                continue
            agg[key]["attrs"].setdefault(k, [])
            if v not in agg[key]["attrs"][k] and len(agg[key]["attrs"][k]) < max_field_vals:
                agg[key]["attrs"][k].append(v)
    out = []
    for (name, kind), val in agg.items():
        out.append({
            "entity": name,
            "entity_kind": kind,
            "attrs": val["attrs"],
            "sources": val["sources"],
        })
    return out

def _extract_entity_fields(aggregated: List[Dict], fields: List[str]) -> Dict[str, Dict[str, List[Any]]]:
    """
    Return per-entity selected fields with unique values (lists), up to the lengths already enforced in aggregation.
    """
    if not fields:
        return {}
    result = {}
    for row in aggregated:
        ent = row.get("entity")
        attrs = row.get("attrs", {})
        for f in fields:
            if f in attrs:
                result.setdefault(ent, {})
                result[ent][f] = attrs.get(f, [])
    return result

def _hydrate_intel(store: SQLAlchemyStore, ids: List[int]) -> List[Dict]:
    if not ids:
        return []
    with store.Session() as s:
        stmt = select(Intelligence).where(Intelligence.id.in_(ids))
        rows = s.execute(stmt).scalars().all()
        out = []
        for r in rows:
            try:
                data = json.loads(r.data)
            except Exception:
                data = r.data
            out.append({
                "id": r.id,
                "entity": r.entity_name,
                "confidence": r.confidence,
                "data": data,
                "created": r.created_at.isoformat(),
            })
        return out

def _hydrate_entities(store: SQLAlchemyStore, ids: List[int]) -> List[Dict]:
    if not ids:
        return []
    with store.Session() as s:
        stmt = select(Entity).where(Entity.id.in_(ids))
        rows = s.execute(stmt).scalars().all()
        out = []
        for r in rows:
            try:
                data = json.loads(r.data)
            except Exception:
                data = r.data
            out.append({
                "id": r.id,
                "name": r.name,
                "kind": r.kind,
                "data": data,
                "last_seen": r.last_seen.isoformat(),
            })
        return out

def handle_intel(args):
    """Integrated intel.py logic"""
    persistence_enabled = args.use_sqlite or bool(args.db_url)
    db_url = normalize_db_url(args.db_url, args.sqlite_path) if persistence_enabled else ""
    store = SQLAlchemyStore(db_url) if persistence_enabled else SQLAlchemyStore()

    # Deep semantic / hybrid search path (shared with run)
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
            }
            for r in results
        ]
        # entity-name filter (case-insensitive)
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
            "entity": r['entity'],
            "confidence": r.get('confidence', 0),
            "date": r.get('created', '')
        }
        if isinstance(r['data'], dict):
            for k, v in r['data'].items():
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

def normalize_db_url(db_url: str, sqlite_path: str) -> str:
    if db_url:
        if "://" not in db_url:
            return f"sqlite:///{db_url}"
        return db_url
    return f"sqlite:///{sqlite_path}"

def collect_candidates(queries, seed_limit) -> list:
    candidates = []
    with DDGS() as ddgs:
        for query in queries:
            try:
                results = list(ddgs.text(query, max_results=seed_limit))
                candidates.extend(results)
                time.sleep(0.5)
            except Exception as e:
                logging.warning(f"Search error for '{query}': {e}")
    seen = set()
    deduped = []
    for c in candidates:
        href = c.get("href")
        if href and href not in seen:
            seen.add(href)
            deduped.append(c)
    return deduped

def list_pages(store):
    try:
        pages = store.get_all_pages()
        def serial(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError("Type not serializable")
        data = [p.to_dict() for p in pages]
        print(json.dumps(data, default=serial, indent=2))
    except AttributeError as e:
        print(f"Error: The store implementation is missing a method: {e}")

def fetch_text(store: SQLAlchemyStore, url: str):
    with store.Session() as s:
        row = s.get(PageContent, url)
        if row and row.text:
            print(row.text)
            return True
    return False

def load_seeds_from_db(store: SQLAlchemyStore, from_links: bool, from_pages: bool, domains, patterns, min_score, limit):
    import re as _re
    seeds = []
    with store.Session() as s:
        if from_links:
            q = (
                select(Link.to_url, Link.score)
                .where(Link.score >= min_score)
                .order_by(Link.score.desc().nullslast())
                .limit(limit)
            )
            seeds.extend(s.execute(q).all())
        if from_pages:
            q = (
                select(Page.url, Page.score)
                .order_by(Page.last_fetch_at.desc().nullslast())
                .limit(limit)
            )
            seeds.extend(s.execute(q).all())
    filtered = []
    for url, score in seeds:
        if domains:
            try:
                d = urlparse(url).netloc.lower()
                if not any(dom.lower() in d for dom in domains):
                    continue
            except Exception:
                continue
        if patterns:
            pat_ok = False
            for pat in patterns:
                try:
                    if _re.search(pat, url):
                        pat_ok = True
                        break
                except Exception:
                    continue
            if not pat_ok:
                continue
        filtered.append(url)
    seen = set()
    uniq = []
    for u in filtered:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq[:limit]

def print_active_mode_instructions(session_id):
    msg = f"""
    ===============================================
    🟢 ACTIVE MODE (session: {session_id})
    -----------------------------------------------
    1. A Chrome browser window will open.
    2. Use the floating "Mark Recorder" panel to:
        - [Mark Page]: Save a snapshot of current page
            (shortcut: Shift+P)
        - [Element Select]: Click any text/element to save
            (shortcut: Shift+E)
        - [Image Select]: Click an image to save
            (shortcut: Shift+I)
        - You can drag the panel with its header.

    3. Status messages and session-id shown at bottom.
    4. All marks are saved into your database: inspection, search, and extractions are possible!

    [Tips]
    - Start URL for browser can be set via .env BROWSER_START_URL
    - To enable more Chrome features, set BROWSER_EXTRA_CHROME_ARGS in .env

    To exit: close the browser window or press [CTRL+C] in this terminal.
    ===============================================
    """
    print(msg)

def run_active_session(store):
    mark_queue = start_server_thread()
    ingestor = RecorderIngestor(store)
    session_id = get_session_id()
    print_active_mode_instructions(session_id)
    print(">> Launching Browser. Close the window to finish.")
    extra_chrome_args = get_env_chrome_args()
    start_url = get_browser_start_url()
    with RecordingBrowser(start_url=start_url, extra_chrome_args=extra_chrome_args, session_id=session_id) as browser:
        time.sleep(2)
        try:
            while browser.is_alive():
                try:
                    data = mark_queue.get(timeout=0.5)
                    if "session_id" not in data:
                        data["session_id"] = session_id
                    ingestor.ingest_marked_page(data)
                    logger.info(f">> Persisted: {data.get('url', '')[:50]}...")
                except queue.Empty:
                    continue
                except KeyboardInterrupt:
                    break
        finally:
            browser.close()
    print(">> Browser closed. Draining final items...")
    while not mark_queue.empty():
        d = mark_queue.get_nowait()
        if "session_id" not in d:
            d["session_id"] = session_id
        ingestor.ingest_marked_page(d)
    print(">> Session Complete.")
    sys.exit(0)

def collect_candidates_simple(queries, limit=5) -> list:
    """Helper to actually fetch URLs from DuckDuckGo."""
    candidates = []
    with DDGS() as ddgs:
        for q in queries:
            try:
                # Fetch a few results per query
                results = list(ddgs.text(q, max_results=3))
                candidates.extend([r['href'] for r in results if 'href' in r])
            except Exception as e:
                logger.warning(f"Search failed for '{q}': {e}")
    return list(set(candidates))[:limit]


def perform_rag_search(query, store, v_store, llm):
    """Gathers context from SQL and Vector DB for the LLM."""
    search_terms = llm.generate_search_queries(query)
    context_hits = []
    
    # 1. Vector Search
    q_vec = llm.embed_text(query)
    if q_vec and v_store:
        try:
            hits = v_store.search(q_vec, top_k=5)
            # Ensure snippet extraction
            context_hits.extend([{"url": h.payload.get("url"), "snippet": h.payload.get("text", "")} for h in hits])
        except Exception as e:
            logging.debug(f"Vector search failed: {e}")

    # 2. SQL Keyword Search
    for term in search_terms:
        context_hits.extend(store.search_intel(term))
    
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
            if query.lower() in ["exit", "quit"]: break
            if not query: continue

            print("[*] Searching existing knowledge base...")
            answer = perform_rag_search(query, store, v_store, llm)
            
            # If answer is good, print and continue
            if llm.evaluate_sufficiency(answer):
                print(f"\n[AI]: {answer}\n")
                continue

            # If answer is insufficient, trigger crawl
            print("[!] Local data is insufficient. Resolving online search seeds...")
            
            # 1. Generate search strings (e.g. "Bill Gates recent news")
            search_queries = llm.generate_seed_queries(query, profile.name)
            print(f"[*] Generated Queries: {search_queries}")
            
            # 2. RESOLVE to URLs using DuckDuckGo
            live_urls = collect_candidates_simple(search_queries, limit=5)
            
            if not live_urls:
                print("[!] No live URLs found from search queries.")
                print(f"\n[AI]: {answer.replace('INSUFFICIENT_DATA', 'I could not find information locally or online.')}\n")
                continue

            print(f"[*] Found {len(live_urls)} URLs. Starting autonomous crawl...")
            
            # 3. Execute Crawl
            # NOTE: We lower score_threshold to 5.0 to ensure these seeds are definitely processed.
            explorer = IntelligentExplorer(
                profile=profile, 
                persistence=store, 
                vector_store=v_store, 
                llm_extractor=llm,
                max_total_pages=args.max_pages if hasattr(args, 'max_pages') else 5,
                score_threshold=5.0 
            )
            
            browser = None
            if args.use_selenium:
                browser = SeleniumBrowser(headless=True)
                browser._init_driver()
            
            try:
                explorer.explore(live_urls, browser)
            finally:
                if browser: browser.close()

            print("[*] Re-evaluating with fresh intelligence...")
            answer = perform_rag_search(query, store, v_store, llm)
            final_text = answer.replace("INSUFFICIENT_DATA", "I searched online but still couldn't find a definitive answer.")
            print(f"\n[AI]: {final_text}\n")

        except KeyboardInterrupt: break
        except Exception as e:
            logger.error(f"Chat Loop Error: {e}")


# ... existing imports remain ...

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
            }
            for r in results
        ]
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
            rr = RefreshRunner(store=store, use_selenium=args.use_selenium, vector_store=vector_store, llm_extractor=llm)
            rr.run(batch=1)
            found = fetch_text(store, args.fetch_text)
            if not found:
                msg = "Text still not available after refetch."
                if return_result:
                    return {"fetch_text": args.fetch_text, "status": "missing"}
                logging.error(msg)
            return
        if args.refresh:
            rr = RefreshRunner(store=store, use_selenium=args.use_selenium, vector_store=vector_store, llm_extractor=llm)
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


def run_crawl_api(payload: dict) -> dict:
    """
    Entry point for web API: maps JSON payload to argparse-style Namespace
    and returns crawl/search results as a dict. Does not sys.exit.
    """
    # Defaults aligned with parse_args()
    args = argparse.Namespace(
        command="run",
        verbose=False,
        # persistence
        use_sqlite=bool(payload.get("use_sqlite", True)),
        db_url=payload.get("db_url", ""),
        sqlite_path=payload.get("sqlite_path", "crawler.db"),
        # llm/vector
        ollama_url=payload.get("ollama_url", "http://localhost:11434/api/generate"),
        model=payload.get("model", "granite3.1-dense:8b"),
        embedding_model=payload.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2"),
        qdrant_url=payload.get("qdrant_url", "http://localhost:6333"),
        qdrant_collection=payload.get("qdrant_collection", "pages"),
        top_k=int(payload.get("top_k", 10)),
        # crawl
        entity=payload.get("entity"),
        type=payload.get("type", "company"),
        location=payload.get("location", ""),
        max_pages=int(payload.get("max_pages", 10)),
        total_pages=int(payload.get("total_pages", 50)),
        max_depth=int(payload.get("max_depth", 2)),
        score_threshold=float(payload.get("score_threshold", 35.0)),
        seed_limit=int(payload.get("seed_limit", 25)),
        use_selenium=bool(payload.get("use_selenium", False)),
        active_mode=bool(payload.get("active_mode", False)),
        output=payload.get("output", ""),
        list_pages=bool(payload.get("list_pages", False)),
        fetch_text=payload.get("fetch_text", ""),
        refresh=bool(payload.get("refresh", False)),
        refresh_batch=int(payload.get("refresh_batch", 50)),
        seed_url=payload.get("seed_url", []) or [],
        seed_query=payload.get("seed_query", ""),
        seed_from_links=bool(payload.get("seed_from_links", False)),
        seed_from_pages=bool(payload.get("seed_from_pages", False)),
        seed_domain=payload.get("seed_domain", []) or [],
        seed_pattern=payload.get("seed_pattern", []) or [],
        min_link_score=float(payload.get("min_link_score", 0.0)),
        seed_limit_db=int(payload.get("seed_limit_db", 20)),
        search_intel=payload.get("search_intel", ""),
        search_entity_type=payload.get("search_entity_type", ""),
        search_page_type=payload.get("search_page_type", ""),
        enable_llm_link_rank=bool(payload.get("enable_llm_link_rank", False)),
        # semantic/hybrid (not used by current UI but kept)
        semantic_search=payload.get("semantic_search", ""),
        hybrid_search=payload.get("hybrid_search", ""),
        semantic_kind=payload.get("semantic_kind", "any"),
        entity_name=payload.get("entity_name", ""),
        entity_field=payload.get("entity_field", []) or [],
        hydrate_sql=bool(payload.get("hydrate_sql", False)),
    )
    return handle_run(args, return_result=True)


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.command == "chat":
        interactive_chat(args)

    if args.command == "intel":
        handle_intel(args)

    elif args.command == "run":
        handle_run(args)


if __name__ == "__main__":
    main()
