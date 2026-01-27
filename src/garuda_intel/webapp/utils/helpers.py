"""Helper utility functions for the webapp."""

import re
import uuid
from uuid import uuid5, NAMESPACE_URL
from collections import Counter


def _canonical(name) -> str:
    """Normalize entity names to canonical form."""
    if name is None:
        return ""
    try:
        s = str(name)
    except Exception:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def _best_label(variants_counter: Counter[str]) -> str:
    """Get the most common label variant from a Counter."""
    if not variants_counter:
        return ""
    return variants_counter.most_common(1)[0][0]


def _as_list(val):
    """Convert value to list if it isn't already."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def _parse_list_param(val: str | None, default: set[str]) -> set[str]:
    """Parse comma-separated parameter into set."""
    if not val:
        return set(default)
    return {v.strip().lower() for v in val.split(",") if v.strip()}


def _seeds_from_query(nodes: list[dict], query: str) -> set[str]:
    """Find seed nodes matching query string."""
    if not query:
        return {n["id"] for n in nodes}
    q = query.lower()
    seeds = {n["id"] for n in nodes if q in str(n.get("label", "")).lower() or q in str(n.get("id", "")).lower()}
    return seeds or {n["id"] for n in nodes}


def _filter_by_depth(nodes: list[dict], links: list[dict], depth_limit: int, seeds: set[str]) -> tuple[list[dict], list[dict]]:
    """Filter nodes and links by depth from seed nodes."""
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


ORG_KINDS = {"organization", "organisation", "corporation", "corp", "company", "business", "firm"}


def _norm_kind(k: str | None) -> str | None:
    """Normalize entity kind values."""
    if not k:
        return None
    k2 = k.strip().lower()
    if k2 in ORG_KINDS:
        return "org"
    if k2 == "person":
        return "person"
    return k2


def _looks_like_uuid(val: str) -> bool:
    """Check if value is a valid UUID."""
    try:
        uuid.UUID(str(val))
        return True
    except Exception:
        return False


def _page_uuid_from_url(url: str | None) -> str | None:
    """Generate deterministic UUID from URL."""
    if not url:
        return None
    return str(uuid5(NAMESPACE_URL, url))


def _page_id_from_row(row):
    """Extract page ID from database row."""
    if not row:
        return None
    for key in ("id", "page_id"):
        v = getattr(row, key, None) if not isinstance(row, dict) else row.get(key)
        if v:
            return v
    url = getattr(row, "page_url", None) or getattr(row, "url", None) if not isinstance(row, dict) else row.get("url") or row.get("page_url")
    if url:
        return _page_uuid_from_url(url)
    return None
