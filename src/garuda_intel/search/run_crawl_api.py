"""API entry point for web application crawl requests."""

import argparse
from .handlers import handle_run


def run_crawl_api(payload: dict) -> dict:
    """
    Entry point for web API: maps JSON payload to argparse-style Namespace
    and returns crawl/search results as a dict. Does not sys.exit.
    """
    from ..config import Settings
    settings = Settings.from_env()
    args = argparse.Namespace(
        command="run",
        verbose=False,
        # persistence
        use_sqlite=bool(payload.get("use_sqlite", True)),
        db_url=payload.get("db_url", settings.db_url),
        sqlite_path=payload.get("sqlite_path", settings.db_url.replace("sqlite:///", "") if settings.db_url else "crawler,db"),
        # llm/vector
        ollama_url=payload.get("ollama_url", settings.ollama_url),
        model=payload.get("model", settings.ollama_model),
        embedding_model=payload.get("embedding_model", settings.embedding_model),
        qdrant_url=payload.get("qdrant_url", settings.qdrant_url),
        qdrant_collection=payload.get("qdrant_collection", settings.qdrant_collection),
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
