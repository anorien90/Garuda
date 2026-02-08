"""Entity management API routes."""

import logging
import itertools
import uuid as uuid_module
from collections import Counter
from flask import Blueprint, jsonify, request
from sqlalchemy.orm import joinedload
from ..services.event_system import emit_event
from ..utils.request_helpers import safe_int, safe_float
from ..services.graph_builder import (
    _collect_entities_from_json,
    _collect_relationships_from_json,
    _add_semantic_relationship_edges,
    _collect_images_from_metadata,
    _qdrant_semantic_page_hits,
    _qdrant_semantic_entity_hints,
    _add_relationship_edges,
)
from ..utils.helpers import (
    _canonical,
    _best_label,
    _parse_list_param,
    _seeds_from_query,
    _filter_by_depth,
    _norm_kind,
    _page_id_from_row,
)
from ...database import models as db_models
from ...search import EntityProfile, EntityType, CrawlMode


bp = Blueprint('entities', __name__, url_prefix='/api/entities')
logger = logging.getLogger(__name__)


def init_routes(api_key_required, settings, store, llm, vector_store, entity_crawler, gap_analyzer, adaptive_crawler):
    """Initialize routes with required dependencies."""
    
    @bp.get("/graph")
    @api_key_required
    def api_entities_graph():
        q = (request.args.get("query") or "").strip().lower()
        type_filter_raw = request.args.get("type")
        type_filter = _norm_kind(type_filter_raw) or ""
        min_score = safe_float(request.args.get("min_score"), 0)
        limit = min(safe_int(request.args.get("limit"), 100), 500)
        depth_limit = safe_int(request.args.get("depth"), 1)
        include_meta = (request.args.get("include_meta") or "1").strip() != "0"

        node_type_filters = _parse_list_param(
            request.args.get("node_types"),
            default={"entity", "person", "org", "organization", "corporation", "location", "product", "event", "page", "intel", "image", "media", "semantic-snippet", "seed"},
        )
        edge_kind_filters = _parse_list_param(
            request.args.get("edge_kinds"),
            default={"cooccurrence", "page-mentions", "intel-mentions", "intel-primary", "page-image", "link", "relationship", "semantic-hit", "page-entity", "page-media", "entity-media", "semantic-snippet", "seed-entity", "has-person", "has-location", "has-product", "participated-in-event", "works-at", "located-at", "produced-by", "associated-with-person", "related-entity"},
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
                "include_meta": include_meta,
            },
        )

        try:
            nodes: dict[str, dict] = {}
            variants: dict[str, Counter[str]] = {}
            links: dict[tuple[str, str], dict] = {}
            canonical_type: dict[str, str] = {}
            entity_ids: dict[str, str] = {}
            entity_kinds: dict[str, str] = {}
            page_id_to_url: dict[str, str] = {}

            def add_edge(a: str, b: str, kind: str, weight: int = 1, meta: dict | None = None):
                if not a or not b:
                    return
                a_str, b_str = str(a), str(b)
                key = tuple(sorted((a_str, b_str)))
                if key not in links:
                    links[key] = {"weight": 0, "kind": kind, "meta": meta or {}}
                links[key]["weight"] += weight
                if kind and links[key].get("kind") != kind:
                    links[key]["kind"] = kind
                if meta is not None:
                    edge_meta = links[key].get("meta") or {}
                    edge_meta.update({k: v for k, v in meta.items() if v is not None})
                    links[key]["meta"] = edge_meta

            def add_cooccurrence_edges(entity_keys: list[str]):
                unique_keys = sorted(set([e for e in entity_keys if e]))
                for a, b in itertools.combinations(unique_keys, 2):
                    add_edge(a, b, kind="cooccurrence", weight=1)

            def ensure_node(node_id: str, label: str, node_type: str, score: float | None = None, count_inc: int = 1, meta: dict | None = None, kind: str | None = None):
                if not node_id:
                    return None
                node_id = str(node_id)
                # Initialize node with defaults
                node = nodes.get(node_id, {"id": node_id, "label": label or node_id, "type": node_type, "score": 0, "count": 0, "meta": {}})
                node["count"] = (node.get("count") or 0) + (count_inc or 0)
                if score is not None:
                    node["score"] = max(node.get("score") or 0, score)
                # Set kind field: prefer specific kinds over generic ones
                if kind:
                    existing_kind = node.get("kind")
                    is_specific_kind = kind not in ("entity", "unknown")
                    is_existing_generic = not existing_kind or existing_kind in ("entity", "unknown")
                    # Update kind if new kind is more specific, or if no kind exists yet
                    if is_specific_kind and is_existing_generic:
                        node["kind"] = kind
                    elif not existing_kind:
                        node["kind"] = kind
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
                norm_kind = _norm_kind(kind)
                variants.setdefault(canon, Counter()).update([raw_name])
                ent_uuid = entity_ids.get(canon)
                # Get stored kind from database if available (may have more specific kind like "founder")
                stored_kind = entity_kinds.get(canon)
                # Priority: stored_kind (if specific) > norm_kind (if specific) > norm_kind (generic) > "entity"
                is_stored_specific = stored_kind and stored_kind not in ("entity", "unknown")
                effective_kind = stored_kind if is_stored_specific else (norm_kind or "entity")
                node_key = str(ent_uuid) if ent_uuid else canon
                # entity_kind in meta stores normalized kind for filtering; falls back to effective_kind
                node_meta = {"entity_kind": norm_kind or effective_kind or "entity", "canonical": canon, "entity_id": ent_uuid, "source_id": node_key}
                if meta:
                    node_meta.update(meta)
                node_id = ensure_node(node_key, raw_name, node_type=effective_kind, score=score, meta=node_meta, kind=effective_kind)
                if effective_kind:
                    canonical_type[canon] = canonical_type.get(canon) or effective_kind
                    # type may be updated here for canonical consistency across merged nodes;
                    # kind is already set in ensure_node with smart update logic
                    nodes[node_id]["type"] = canonical_type[canon]
                return node_id

            entry_type_map: dict[str, str] = {}
            with store.Session() as session:
                # UNIQUENESS GUARANTEE: The graph ensures only unique entities through:
                # 1. Canonical name normalization (_canonical function)
                # 2. UUID-based deduplication (entity_ids dict maps canonical -> UUID)
                # 3. Variant tracking (multiple spellings map to same canonical entity)
                # This guarantees the graph displays only unique entities with full relations.
                
                # Note: Loading entities in bulk (limit 20000) maintains original behavior.
                # TODO: For very large datasets (>20K entities), implement pagination:
                #       - Process entities in batches of 1000-5000
                #       - Use offset-based or cursor-based pagination
                for row in session.query(db_models.Entity).limit(20000).all():
                    # Skip entities that have been soft-merged into another entity
                    if row.metadata_json and row.metadata_json.get("merged_into"):
                        continue
                    canon = _canonical(row.name)
                    ent_uuid = str(row.id)
                    norm_kind = _norm_kind(row.kind)  # Calculate once
                    entity_ids[canon] = ent_uuid
                    entity_kinds[canon] = norm_kind
                    if row.kind:
                        canonical_type[canon] = norm_kind
                    entry_type_map[ent_uuid] = "entity"

                semantic_entity_hints = _qdrant_semantic_entity_hints(q, vector_store, llm) if q else set()

                for row in session.query(db_models.Intelligence).limit(5000).all():
                    intel_data = row.data or {}
                    intel_id_str = str(row.id)
                    
                    # Create primary entity node once
                    primary = upsert_entity(row.entity_name, row.entity_type, row.confidence) if row.entity_name else None
                    
                    # Extract entities and relationships from JSON
                    ents_from_json = _collect_entities_from_json(intel_data)
                    rels_from_json = _collect_relationships_from_json(intel_data)
                    
                    # Process semantic relationships
                    if primary and rels_from_json:
                        _add_semantic_relationship_edges(
                            rels_from_json,
                            upsert_entity,
                            add_edge,
                            include_meta,
                            context_meta={"intel_id": intel_id_str} if include_meta else None
                        )
                    
                    # Extract and persist Persons as unique entities
                    persons = intel_data.get("persons", [])
                    if isinstance(persons, list):
                        for person in persons:
                            if isinstance(person, dict):
                                person_name = person.get("name")
                                if person_name:
                                    person_node = upsert_entity(person_name, "person", None, meta={
                                        "role": person.get("role"),
                                        "title": person.get("title"),
                                        "bio": person.get("bio")
                                    })
                                    if person_node and primary:
                                        add_edge(primary, person_node, kind="has-person", weight=1,
                                                meta={"role": person.get("role"), "title": person.get("title")} if include_meta else None)
                                    if person_node:
                                        add_edge(intel_id_str, person_node, kind="intel-mentions", weight=1)
                    
                    # Extract Locations as unique entities
                    locations = intel_data.get("locations", [])
                    if isinstance(locations, list):
                        for location in locations:
                            if isinstance(location, dict):
                                # Use same priority order as intel_extractor.py for consistency
                                location_name = location.get("address") or location.get("city") or location.get("country")
                                if location_name:
                                    location_node = upsert_entity(location_name, "location", None, meta={
                                        "type": location.get("type"),
                                        "city": location.get("city"),
                                        "country": location.get("country"),
                                        "address": location.get("address")
                                    })
                                    if location_node and primary:
                                        add_edge(primary, location_node, kind="has-location", weight=1,
                                                meta={"type": location.get("type")} if include_meta else None)
                                    if location_node:
                                        add_edge(intel_id_str, location_node, kind="intel-mentions", weight=1)
                    
                    # Extract Products as unique entities
                    products = intel_data.get("products", [])
                    if isinstance(products, list):
                        for product in products:
                            if isinstance(product, dict):
                                product_name = product.get("name")
                                if product_name:
                                    product_node = upsert_entity(product_name, "product", None, meta={
                                        "status": product.get("status"),
                                        "description": product.get("description")
                                    })
                                    if product_node and primary:
                                        add_edge(primary, product_node, kind="has-product", weight=1,
                                                meta={"status": product.get("status")} if include_meta else None)
                                    if product_node:
                                        add_edge(intel_id_str, product_node, kind="intel-mentions", weight=1)
                    
                    # Extract Events as unique entities
                    events = intel_data.get("events", [])
                    if isinstance(events, list):
                        for event in events:
                            if isinstance(event, dict):
                                event_name = event.get("title")
                                if event_name:
                                    event_node = upsert_entity(event_name, "event", None, meta={
                                        "date": event.get("date"),
                                        "description": event.get("description"),
                                        "type": event.get("type")
                                    })
                                    if event_node and primary:
                                        add_edge(primary, event_node, kind="participated-in-event", weight=1,
                                                meta={"date": event.get("date"), "type": event.get("type")} if include_meta else None)
                                    if event_node:
                                        add_edge(intel_id_str, event_node, kind="intel-mentions", weight=1)
                    
                    # Process entities from JSON structure
                    if row.entity_name and ents_from_json:
                        for ent in ents_from_json:
                            other_id = upsert_entity(ent["name"], ent.get("kind"), None)
                            if primary and other_id and other_id != primary:
                                add_edge(primary, other_id, kind="intel-mentions", weight=1)
                    
                    # Create Intel node
                    ensure_node(intel_id_str, f"Intel: {row.entity_type or 'data'}", "intel", score=row.confidence,
                                meta={"intel_id": intel_id_str, "source_id": intel_id_str, "confidence": row.confidence,
                                      "entity_name": row.entity_name, "entity_type": row.entity_type, "data": intel_data})
                    entry_type_map[intel_id_str] = "intel"
                    
                    # Link Intel node to primary entity
                    if primary:
                        add_edge(intel_id_str, primary, kind="intel-primary", weight=1)
                    
                    # Link Intel node to all extracted entities
                    for ent in ents_from_json:
                        other_id = upsert_entity(ent["name"], ent.get("kind"), None)
                        if other_id:
                            add_edge(intel_id_str, other_id, kind="intel-mentions", weight=1)

                for row in session.query(db_models.Page).options(joinedload(db_models.Page.content)).limit(3000).all():
                    page_id = _page_id_from_row(row)
                    page_id_to_url[page_id] = row.url
                    page_ents: list[str] = []

                    # Access extracted data from PageContent if available
                    extracted_data = {}
                    metadata = {}
                    if row.content:
                        # Defensive check: ensure extracted_json is a dict to prevent AttributeError
                        raw_extracted = row.content.extracted_json or {}
                        extracted_data = raw_extracted if isinstance(raw_extracted, dict) else {}
                        
                        raw_metadata = row.content.metadata_json or {}
                        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
                    
                    entities_list = extracted_data.get("entities", [])
                    if entities_list:
                        for e_json in entities_list:
                            if isinstance(e_json, dict):
                                e_name = e_json.get("name") or e_json.get("entity")
                                e_kind = e_json.get("type") or e_json.get("entity_type")
                                if e_name:
                                    eid = upsert_entity(e_name, e_kind, None)
                                    if eid:
                                        page_ents.append(eid)

                    add_cooccurrence_edges(page_ents)

                    ensure_node(page_id, row.title or row.url, "page", score=row.score,
                                meta={"url": row.url, "page_type": row.page_type, "source_id": page_id, "page_id": page_id})
                    entry_type_map[page_id] = "page"

                    for eid in page_ents:
                        add_edge(page_id, eid, kind="page-mentions", weight=1)

                    for img in _collect_images_from_metadata(metadata):
                        img_url = img["url"]
                        img_id = f"img:{img_url}"
                        ensure_node(img_id, img.get("alt") or img_url, "image",
                                    meta={"source_url": img_url, "source_id": img_id})
                        add_edge(page_id, img_id, kind="page-image", weight=1)

                    outlinks_list = extracted_data.get("outlinks", [])
                    for link in outlinks_list:
                        if isinstance(link, str):
                            link_id = f"link:{link}"
                            ensure_node(link_id, link, "link", meta={"url": link, "source_id": link_id})
                            add_edge(page_id, link_id, kind="link", weight=1)

                _add_relationship_edges(session, ensure_node, add_edge, entry_type_map)
                
                # Add media items to the graph (if MediaItem model exists)
                if hasattr(db_models, 'MediaItem'):
                    for media_row in session.query(db_models.MediaItem).limit(1000).all():
                        media_id = str(media_row.id)
                        media_label = media_row.url.split('/')[-1][:50] if media_row.url else "media"
                        media_meta = {
                            "url": media_row.url,
                            "media_type": media_row.media_type,
                            "processed": media_row.processed,
                            "source_id": media_id
                        }
                        ensure_node(media_id, media_label, "media", meta=media_meta)
                        entry_type_map[media_id] = "media"
                        
                        # Link to source page
                        if media_row.source_page_id:
                            page_id = str(media_row.source_page_id)
                            add_edge(page_id, media_id, kind="page-media", weight=1)
                        
                        # Link to associated entity
                        if media_row.entity_id:
                            entity_id = str(media_row.entity_id)
                            add_edge(entity_id, media_id, kind="entity-media", weight=1)
                
                # Add seed nodes to the graph (if Seed model exists)
                if hasattr(db_models, 'Seed'):
                    for seed_row in session.query(db_models.Seed).limit(500).all():
                        seed_id = str(seed_row.id)
                        seed_label = seed_row.query[:50] if seed_row.query else "seed"
                        seed_meta = {
                            "query": seed_row.query,
                            "entity_type": seed_row.entity_type,
                            "source": seed_row.source,
                            "source_id": seed_id
                        }
                        ensure_node(seed_id, seed_label, "seed", meta=seed_meta)
                        entry_type_map[seed_id] = "seed"
                        
                        # If the seed has an associated entity_type, try to link to matching entities
                        if seed_row.entity_type and seed_row.query:
                            # Look for entities that match the seed query
                            seed_canon = _canonical(seed_row.query)
                            if seed_canon in entity_ids:
                                entity_id = entity_ids[seed_canon]
                                add_edge(seed_id, entity_id, kind="seed-entity", weight=1)

                for r in _qdrant_semantic_page_hits(q, vector_store, llm):
                    p = r.payload or {}
                    ent_name = p.get("entity") or p.get("entity_name")
                    if not ent_name:
                        continue
                    canon = _canonical(ent_name)
                    if q and canon not in semantic_entity_hints:
                        continue
                    page_url = p.get("url")
                    ent_id = upsert_entity(ent_name, p.get("entity_type"), r.score)
                    pid = _page_id_from_row(p)
                    ensure_node(pid, page_url, "page", score=r.score, meta={"url": page_url, "page_id": pid, "source_id": pid})
                    add_edge(pid, ent_id, kind="semantic-hit", weight=1, meta={"score": r.score})
                    page_id_to_url[pid] = page_url

            for node_id in list(nodes.keys()):
                node = nodes[node_id]
                if node.get("type") == "entity" or node.get("type") in {"person", "org"}:
                    canon = node.get("meta", {}).get("canonical")
                    if canon and canon in variants:
                        best_variant = _best_label(variants[canon])
                        node["label"] = best_variant

            filtered_nodes = [
                n for n in nodes.values()
                if (
                    (not n.get("type") or n["type"] in node_type_filters)
                    and (not type_filter or n.get("type") == type_filter)
                    and (n.get("score", 0) >= min_score)
                )
            ]

            sorted_nodes = sorted(filtered_nodes, key=lambda x: (-x.get("score", 0), -x.get("count", 0), x["id"]))[:limit]
            node_set = {n["id"] for n in sorted_nodes}

            filtered_links = [
                {"source": k[0], "target": k[1], "weight": v["weight"], "kind": v["kind"], "meta": v.get("meta")}
                for k, v in links.items()
                if k[0] in node_set and k[1] in node_set and (not v.get("kind") or v["kind"] in edge_kind_filters)
            ]

            seeds = _seeds_from_query(sorted_nodes, q)
            final_nodes, final_links = _filter_by_depth(sorted_nodes, filtered_links, depth_limit, seeds)

            for n in final_nodes:
                meta = n.get("meta") or {}
                page_id = meta.get("page_id")
                if page_id and page_id in page_id_to_url:
                    meta["url"] = page_id_to_url[page_id]
                if not include_meta:
                    meta = {k: v for k, v in meta.items() if k in ("url", "page_id", "entity_id", "source_id", "page_type")}
                    n["meta"] = meta

            emit_event(
                "entities_graph",
                "done",
                payload={
                    "nodes": len(final_nodes),
                    "links": len(final_links),
                    "query": q,
                    "type_filter": type_filter,
                    "min_score": min_score,
                },
            )

            return jsonify({"nodes": final_nodes, "links": final_links})

        except Exception as e:
            emit_event("entities_graph", f"failed: {e}", level="error")
            logger.exception("Entities graph failed")
            return jsonify({"error": f"graph generation failed: {e}"}), 500

    @bp.get("/graph/node")
    @api_key_required
    def api_entities_graph_node():
        node_id = (request.args.get("id") or "").strip()
        if not node_id:
            return jsonify({"error": "id required"}), 400

        meta = {}
        node_type = "unknown"
        label = node_id

        # Handle special node types first
        if node_id.startswith("link:"):
            url = node_id[5:]
            return jsonify({"id": node_id, "type": "link", "meta": {"url": url, "source_id": node_id}})

        if node_id.startswith("img:"):
            img_url = node_id[4:]
            return jsonify({"id": node_id, "type": "image", "meta": {"source_url": img_url, "source_id": img_url}})

        # Check if node_id is a valid UUID before querying database
        is_valid_uuid = False
        try:
            uuid_module.UUID(node_id)
            is_valid_uuid = True
        except (ValueError, AttributeError):
            # Not a valid UUID, might be a canonical name or other identifier
            pass

        try:
            if is_valid_uuid:
                # Only query by ID if it's a valid UUID
                with store.Session() as session:
                    entity = session.query(db_models.Entity).filter_by(id=node_id).first()
                    if entity:
                        node_type = entity.kind or "entity"  # Use entity kind as type
                        entity_kind = entity.kind  # Separate kind field for more specific categorization
                        label = entity.name
                        
                        # Get entity data and metadata
                        entity_data = entity.data or {}
                        entity_meta = entity.metadata_json or {}
                        
                        meta = {
                            "name": entity.name,
                            "kind": entity.kind,
                            "last_seen": entity.last_seen.isoformat() if entity.last_seen else None,
                        }
                        
                        # Add entity data fields (excluding internal fields)
                        for key, value in entity_data.items():
                            if key not in meta and value:
                                meta[key] = value
                        
                        # Add metadata fields
                        for key, value in entity_meta.items():
                            if key not in meta and value:
                                meta[key] = value
                        
                        # Get related entities through relationships
                        relationships = []
                        for rel in entity.outgoing_relationships:
                            target = session.query(db_models.Entity).filter_by(id=rel.target_id).first()
                            if target:
                                # Get confidence from metadata_json since Relationship doesn't have a confidence attribute
                                rel_meta = rel.metadata_json or {}
                                relationships.append({
                                    "direction": "outgoing",
                                    "type": rel.relation_type,
                                    "target_name": target.name,
                                    "target_kind": target.kind,
                                    "confidence": rel_meta.get("confidence"),
                                })
                        for rel in entity.incoming_relationships:
                            source = session.query(db_models.Entity).filter_by(id=rel.source_id).first()
                            if source:
                                # Get confidence from metadata_json since Relationship doesn't have a confidence attribute
                                rel_meta = rel.metadata_json or {}
                                relationships.append({
                                    "direction": "incoming",
                                    "type": rel.relation_type,
                                    "source_name": source.name,
                                    "source_kind": source.kind,
                                    "confidence": rel_meta.get("confidence"),
                                })
                        
                        return jsonify({
                            "id": node_id, 
                            "type": node_type, 
                            "kind": entity_kind,  # Include kind at top level
                            "label": label, 
                            "meta": meta,
                            "relationships": relationships,
                        })

                    intel = session.query(db_models.Intelligence).filter_by(id=node_id).first()
                    if intel:
                        node_type = "intel"
                        label = intel.entity_name or f"Intel: {intel.entity_type or 'data'}"
                        meta = {
                            "entity_name": intel.entity_name,
                            "entity_type": intel.entity_type,
                            "confidence": intel.confidence,
                            "created_at": intel.created_at.isoformat() if intel.created_at else None,
                        }
                        # Include intel data in a readable format
                        data = intel.data or {}
                        return jsonify({
                            "id": node_id, 
                            "type": node_type, 
                            "label": label, 
                            "meta": meta,
                            "data": data,
                        })

                    page = session.query(db_models.Page).filter_by(id=node_id).first()
                    if page:
                        node_type = "page"
                        label = page.title or page.url
                        meta = {
                            "url": page.url,
                            "title": page.title,
                            "page_type": page.page_type,
                            "intel_score": page.score,
                        }
                        return jsonify({"id": node_id, "type": node_type, "label": label, "meta": meta})
                    
                    # Check for Seed
                    if hasattr(db_models, 'Seed'):
                        seed = session.query(db_models.Seed).filter_by(id=node_id).first()
                        if seed:
                            node_type = "seed"
                            label = seed.query
                            meta = {
                                "query": seed.query,
                                "entity_type": seed.entity_type,
                                "source": seed.source,
                            }
                            return jsonify({"id": node_id, "type": node_type, "label": label, "meta": meta})
                    
                    # Check for MediaItem
                    if hasattr(db_models, 'MediaItem'):
                        media = session.query(db_models.MediaItem).filter_by(id=node_id).first()
                        if media:
                            node_type = "media"
                            label = media.url.split('/')[-1][:50] if media.url else "media"
                            meta = {
                                "url": media.url,
                                "media_type": media.media_type,
                                "processed": media.processed,
                                "extracted_text": media.extracted_text[:200] if media.extracted_text else None,
                            }
                            return jsonify({"id": node_id, "type": node_type, "label": label, "meta": meta})
            
            # If not a valid UUID or not found in database, treat as canonical name or other node type
            # Return a generic entity node
            node_type = "entity"
            meta = {
                "canonical": node_id,
                "source_id": node_id,
            }
            return jsonify({"id": node_id, "type": node_type, "label": label, "meta": meta})

        except Exception as e:
            logger.exception(f"Node lookup failed for {node_id}")
            # Return a generic node on error
            return jsonify({"id": node_id, "type": "entity", "label": node_id, "meta": {"source_id": node_id, "error": str(e)}})

    @bp.post("/crawl")
    @api_key_required
    def api_entity_crawl():
        """Execute entity-aware crawl to fill data gaps."""
        body = request.get_json(silent=True) or {}
        entity_name = body.get("entity_name")
        entity_type_str = body.get("entity_type", "PERSON")
        mode_str = body.get("mode", "TARGETING")
        location_hint = body.get("location_hint", "")
        aliases = body.get("aliases", [])
        official_domains = body.get("official_domains", [])
        
        if not entity_name:
            return jsonify({"error": "entity_name required"}), 400
        
        emit_event("entity_crawl", f"starting entity-aware crawl for {entity_name}")
        
        try:
            try:
                entity_type = EntityType[entity_type_str.upper()]
            except KeyError:
                entity_type = EntityType.PERSON
            
            try:
                mode = CrawlMode[mode_str.upper()]
            except KeyError:
                mode = CrawlMode.TARGETING
            
            profile = EntityProfile(
                name=entity_name,
                entity_type=entity_type,
                location_hint=location_hint,
                aliases=aliases,
                official_domains=official_domains
            )
            
            result = entity_crawler.crawl_for_entity(profile, mode=mode)
            
            emit_event("entity_crawl", f"completed crawl for {entity_name}", payload=result)
            return jsonify(result)
        except Exception as e:
            emit_event("entity_crawl", f"failed: {e}", level="error")
            logger.exception("Entity crawl failed")
            return jsonify({"error": str(e)}), 500
    
    return bp
