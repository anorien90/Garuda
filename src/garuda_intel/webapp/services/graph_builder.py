"""Graph building utilities for entities and relationships."""

import logging
from ..utils.helpers import _canonical, _as_list
from ...database import models as db_models


logger = logging.getLogger(__name__)


def _collect_entities_from_json(obj, path="root"):
    """Extract entities from JSON structure."""
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


def _collect_relationships_from_json(obj, path="root"):
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
                out.extend(_collect_relationships_from_json(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_collect_relationships_from_json(v, f"{path}[{i}]"))
    return out


def _add_semantic_relationship_edges(relationships_data, upsert_entity, add_edge, include_meta, context_meta=None):
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
    for rel in _collect_relationships_from_json(relationships_data):
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


def _collect_images_from_metadata(meta: dict):
    """Extract image information from page metadata."""
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


def _qdrant_semantic_page_hits(query: str, vector_store, llm, top_k: int = 200):
    """Return Qdrant page hits with payload; empty if vector store unavailable."""
    if not (vector_store and query):
        return []
    vec = llm.embed_text(query)
    if not vec:
        return []
    try:
        return vector_store.search(vec, top_k=top_k)
    except Exception as e:
        logger.warning(f"entities graph semantic page search failed: {e}")
        return []


def _qdrant_semantic_entity_hints(query: str, vector_store, llm, top_k: int = 200) -> set[str]:
    """Pull entity names from semantic hits payload."""
    hints: set[str] = set()
    for r in _qdrant_semantic_page_hits(query, vector_store, llm, top_k=top_k):
        p = getattr(r, "payload", {}) or {}
        for key in ("entity", "entity_name", "name"):
            val = p.get(key)
            if val:
                canon = _canonical(val)
                if canon:
                    hints.add(canon)
    return hints


def _add_relationship_edges(session, ensure_node, add_edge, entry_type_map: dict[str, str]):
    """
    Include explicit Entity->Entity (or other Entry) relationships as edges with metadata.
    
    Includes deduplication to ensure each unique relationship is only added once.
    Uses "relationship" as the edge kind for filtering, while preserving the specific
    relation_type in metadata for display.
    
    Note: Currently loads relationships in bulk (limit 20000) to maintain original behavior.
    TODO: For very large datasets (>20K relationships), implement pagination:
          - Process relationships in batches of 1000-5000
          - Use offset-based or cursor-based pagination
          - This will improve memory usage and prevent timeouts
    """
    seen_edges = set()  # Track (source, target, relation_type) to avoid duplicates
    
    # Pre-fetch nodes in bulk for better performance
    # Build lookup maps for getting proper labels
    node_labels = {}
    
    for rel in session.query(db_models.Relationship).limit(20000).all():
        sid = str(rel.source_id)
        tid = str(rel.target_id)
        relation_type = rel.relation_type or "related"
        
        # Create a normalized edge key for deduplication
        edge_key = (min(sid, tid), max(sid, tid), relation_type)
        
        # Skip if we've already added this relationship
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        
        # Get node types and labels
        s_type = entry_type_map.get(sid, "entity")
        t_type = entry_type_map.get(tid, "entity")
        
        # Try to get proper labels for nodes if not already fetched
        if sid not in node_labels:
            node_labels[sid] = _get_node_label(session, sid, s_type)
        if tid not in node_labels:
            node_labels[tid] = _get_node_label(session, tid, t_type)
        
        # Create nodes with proper labels
        ensure_node(sid, node_labels[sid], s_type, meta={"entity_id": sid, "source_id": sid})
        ensure_node(tid, node_labels[tid], t_type, meta={"entity_id": tid, "source_id": tid})
        
        # Use "relationship" as the kind for consistent edge filtering
        # Preserve the specific relation_type in metadata for tooltips/display
        add_edge(
            sid,
            tid,
            kind="relationship",
            weight=1,
            meta={"relation_type": relation_type, "metadata": rel.metadata_json or {}, "source_id": sid, "target_id": tid},
        )


def _get_node_label(session, node_id: str, node_type: str) -> str:
    """
    Get a human-readable label for a node based on its type and ID.
    
    Args:
        session: Database session
        node_id: UUID of the node
        node_type: Type of the node (entity, page, intel, seed, media)
    
    Returns:
        Human-readable label for the node
    """
    try:
        if node_type == "entity":
            entity = session.query(db_models.Entity).filter_by(id=node_id).first()
            if entity:
                return entity.name
        elif node_type == "page":
            page = session.query(db_models.Page).filter_by(id=node_id).first()
            if page:
                return page.title or page.url or node_id
        elif node_type == "intel":
            intel = session.query(db_models.Intelligence).filter_by(id=node_id).first()
            if intel:
                return f"Intel: {intel.entity_name or intel.entity_type or 'data'}"
        elif node_type == "seed":
            seed = session.query(db_models.Seed).filter_by(id=node_id).first()
            if seed:
                return seed.query or node_id
        elif node_type == "media":
            media = session.query(db_models.MediaItem).filter_by(id=node_id).first()
            if media:
                return media.url.split('/')[-1][:50] if media.url else "media"
    except Exception:
        pass
    
    # Fallback to node_id if we can't fetch the label
    return node_id
