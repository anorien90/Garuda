"""Seed collection and discovery functions."""

import logging
from urllib.parse import urlparse
from sqlalchemy import select
from ddgs import DDGS
from ..database.engine import SQLAlchemyStore
from ..database.models import Link, Page


# Maximum concurrent search queries
MAX_CONCURRENT_SEARCHES = 5


def collect_candidates(queries, seed_limit) -> list:
    """
    Fetch candidate URLs from DuckDuckGo with parallel queries.
    
    Returns:
        List of dicts with 'href' key and optional 'title'/'body' keys.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    candidates = []
    
    def _search_query(query):
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=seed_limit))
        except Exception as e:
            logging.warning(f"Search error for '{query}': {e}")
            return []
    
    # Parallelize searches
    with ThreadPoolExecutor(
        max_workers=min(len(queries), MAX_CONCURRENT_SEARCHES)
    ) as pool:
        futures = {pool.submit(_search_query, q): q for q in queries}
        for future in as_completed(futures):
            candidates.extend(future.result())
    
    # Deduplicate by href
    seen = set()
    deduped = []
    for c in candidates:
        href = c.get("href")
        if href and href not in seen:
            seen.add(href)
            deduped.append(c)
    return deduped


def collect_candidates_simple(queries, limit=5) -> list:
    """
    Fetch candidate URLs from DuckDuckGo with parallel queries.
    
    Returns:
        List of dicts with 'href' key and optional 'title'/'body' keys.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    logger = logging.getLogger(__name__)
    candidates = []
    
    def _search_query(q):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(q, max_results=3))
                # Return full result dicts, not just hrefs
                query_results = []
                for r in results:
                    if isinstance(r, dict) and "href" in r:
                        query_results.append(r)
                    elif isinstance(r, str):
                        # Handle case where result is a string (URL)
                        query_results.append({"href": r})
                    else:
                        logger.debug(
                            f"Skipping non-dict, non-string result: {type(r)}"
                        )
                return query_results
        except Exception as e:
            logger.warning(f"Search failed for query '{q}': {e}")
            return []
    
    # Parallelize searches
    with ThreadPoolExecutor(
        max_workers=min(len(queries), MAX_CONCURRENT_SEARCHES)
    ) as pool:
        futures = {pool.submit(_search_query, q): q for q in queries}
        for future in as_completed(futures):
            candidates.extend(future.result())
    
    # Deduplicate by href
    seen = set()
    deduped = []
    for c in candidates:
        href = c.get("href")
        if href and href not in seen:
            seen.add(href)
            deduped.append(c)
    
    return deduped[:limit]


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
