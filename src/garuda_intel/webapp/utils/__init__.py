"""
Helper utilities for webapp.
"""

import re
import uuid
from collections import Counter
from typing import Any, Dict, List, Set, Tuple, Optional
from uuid import uuid5, NAMESPACE_URL


def canonical_name(name) -> str:
    """Canonicalize an entity name for comparison."""
    if name is None:
        return ""
    try:
        s = str(name)
    except Exception:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def best_label(variants_counter: Counter[str]) -> str:
    """Select best label from counter of variants."""
    if not variants_counter:
        return ""
    return variants_counter.most_common(1)[0][0]


def looks_like_uuid(val: str) -> bool:
    """Check if string looks like a UUID."""
    try:
        uuid.UUID(str(val))
        return True
    except Exception:
        return False


def page_uuid_from_url(url: str | None) -> str | None:
    """Generate deterministic UUID for a URL."""
    if not url:
        return None
    return str(uuid5(NAMESPACE_URL, url.strip()))


def as_list(val):
    """Convert value to list."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def parse_list_param(val: str | None, default: set[str]) -> set[str]:
    """Parse comma-separated string into set."""
    if not val:
        return set(default)
    return {v.strip().lower() for v in val.split(",") if v.strip()}


ORG_KINDS = {"organization", "organisation", "corporation", "corp", "company", "business", "firm"}


def normalize_kind(k: str | None) -> str | None:
    """Normalize entity kind to standard values."""
    if not k:
        return None
    k2 = k.strip().lower()
    if k2 in ORG_KINDS:
        return "org"
    if k2 == "person":
        return "person"
    return k2


def collect_entities_from_json(obj, path="root") -> List[Dict[str, Any]]:
    """Extract entity mentions from JSON structure."""
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
            out.extend(collect_entities_from_json(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(collect_entities_from_json(v, f"{path}[{i}]"))
    return out


def collect_relationships_from_json(obj, path="root") -> List[Dict[str, Any]]:
    """Extract relationships from JSON structure (e.g., from LLM findings)."""
    out = []
    if obj is None:
        return out
    if isinstance(obj, dict):
        # Check if this dict looks like a relationship
        if "source" in obj and "target" in obj:
            relation_type = obj.get("relation_type") or obj.get("type") or "related"
            out.append({
                "source": obj["source"],
                "target": obj["target"],
                "relation_type": relation_type,
                "description": obj.get("description", ""),
                "path": path
            })
        # Check for a "relationships" key
        if "relationships" in obj and isinstance(obj["relationships"], list):
            for i, rel in enumerate(obj["relationships"]):
                if isinstance(rel, dict) and "source" in rel and "target" in rel:
                    relation_type = rel.get("relation_type") or rel.get("type") or "related"
                    out.append({
                        "source": rel["source"],
                        "target": rel["target"],
                        "relation_type": relation_type,
                        "description": rel.get("description", ""),
                        "path": f"{path}.relationships[{i}]"
                    })
        # Recursively search nested structures
        for k, v in obj.items():
            if k != "relationships":  # Avoid double-processing
                out.extend(collect_relationships_from_json(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(collect_relationships_from_json(v, f"{path}[{i}]"))
    return out


def collect_images_from_metadata(meta: dict) -> List[Dict[str, str]]:
    """Extract image URLs from metadata."""
    if not isinstance(meta, dict):
        return []
    candidates = []
    for key in ("image", "og_image", "og:image", "twitter:image", "images", "photos", "thumbnails"):
        for item in as_list(meta.get(key)):
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


def seeds_from_query(nodes: list[dict], query: str) -> set[str]:
    """Extract seed nodes from query string."""
    if not query:
        return {n["id"] for n in nodes}
    q = query.lower()
    seeds = {n["id"] for n in nodes if q in str(n.get("label", "")).lower() or q in str(n.get("id", "")).lower()}
    return seeds or {n["id"] for n in nodes}


def filter_by_depth(
    nodes: list[dict], 
    links: list[dict], 
    depth_limit: int, 
    seeds: set[str]
) -> Tuple[list[dict], list[dict]]:
    """Filter graph nodes/links by depth from seed nodes."""
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


def page_id_from_row(row):
    """Extract page ID from database row."""
    if not row:
        return None
    for key in ("id", "page_id"):
        v = getattr(row, key, None) if not isinstance(row, dict) else row.get(key)
        if v:
            return v
    url = getattr(row, "page_url", None) or getattr(row, "url", None) if not isinstance(row, dict) else row.get("url") or row.get("page_url")
    if url:
        return page_uuid_from_url(url)
    return None


def add_semantic_relationship_edges(relationships_data, upsert_entity, add_edge, include_meta, context_meta=None):
    """
    Extract and add semantic relationship edges from JSON data.
    
    Args:
        relationships_data: JSON object to extract relationships from
        upsert_entity: Function to create/get entity nodes
        add_edge: Function to add edges to the graph
        include_meta: Whether to include metadata in edges
        context_meta: Additional metadata to include (e.g., page_id, intel_id)
    """
    context_meta = context_meta or {}
    for rel in collect_relationships_from_json(relationships_data):
        source_name = rel.get("source")
        target_name = rel.get("target")
        relation_type = rel.get("relation_type", "related")
        rel_path = rel.get("path")
        
        if source_name and target_name:
            source_node = upsert_entity(source_name, None, None, meta={"path": rel_path})
            target_node = upsert_entity(target_name, None, None, meta={"path": rel_path})
            
            if source_node and target_node:
                edge_meta = {
                    "relation_type": relation_type,
                    "description": rel.get("description", ""),
                    "path": rel_path,
                    **context_meta
                } if include_meta else None
                
                add_edge(
                    source_node,
                    target_node,
                    kind=f"semantic-{relation_type}",
                    weight=1,
                    meta=edge_meta,
                )
