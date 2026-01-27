"""Entity management API routes."""

import logging
import itertools
from collections import Counter
from flask import Blueprint, jsonify, request
from ..services.event_system import emit_event
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
        min_score = float(request.args.get("min_score", 0) or 0)
        limit = min(int(request.args.get("limit", 100) or 100), 500)
        depth_limit = int(request.args.get("depth", 1) or 1)
        include_meta = (request.args.get("include_meta") or "1").strip() != "0"

        node_type_filters = _parse_list_param(
            request.args.get("node_types"),
            default={"entity", "person", "org", "organization", "corporation", "location", "product", "page", "intel", "image"},
        )
        edge_kind_filters = _parse_list_param(
            request.args.get("edge_kinds"),
            default={"cooccurrence", "page-mentions", "intel-mentions", "intel-primary", "page-image", "link", "relationship", "semantic-hit", "page-entity"},
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

            def ensure_node(node_id: str, label: str, node_type: str, score: float | None = None, count_inc: int = 1, meta: dict | None = None):
                if not node_id:
                    return None
                node_id = str(node_id)
                node = nodes.get(node_id, {"id": node_id, "label": label or node_id, "type": node_type, "score": 0, "count": 0, "meta": {}})
                node["count"] = (node.get("count") or 0) + (count_inc or 0)
                if score is not None:
                    node["score"] = max(node.get("score") or 0, score)
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
                node_key = str(ent_uuid) if ent_uuid else canon
                node_meta = {"entity_kind": norm_kind, "canonical": canon, "entity_id": ent_uuid, "source_id": node_key}
                if meta:
                    node_meta.update(meta)
                node_id = ensure_node(node_key, raw_name, node_type=norm_kind or "entity", score=score, meta=node_meta)
                if norm_kind:
                    canonical_type[canon] = canonical_type.get(canon) or norm_kind
                    nodes[node_id]["type"] = canonical_type[canon]
                return node_id

            entry_type_map: dict[str, str] = {}
            with store.Session() as session:
                # Note: Loading entities in bulk (limit 20000) maintains original behavior.
                # TODO: For very large datasets (>20K entities), implement pagination:
                #       - Process entities in batches of 1000-5000
                #       - Use offset-based or cursor-based pagination
                for row in session.query(db_models.Entity).limit(20000).all():
                    canon = _canonical(row.name)
                    ent_uuid = str(row.id)
                    norm_kind = _norm_kind(row.kind)  # Calculate once
                    entity_ids[canon] = ent_uuid
                    entity_kinds[canon] = norm_kind
                    if row.kind:
                        canonical_type[canon] = norm_kind
                    entry_type_map[ent_uuid] = "entity"

                semantic_entity_hints = _qdrant_semantic_entity_hints(q, vector_store, llm) if q else set()

                for row in session.query(db_models.IntelligenceData).limit(5000).all():
                    ents_from_json = _collect_entities_from_json(row.data_json or {})
                    rels_from_json = _collect_relationships_from_json(row.data_json or {})
                    
                    if ents_from_json and row.entity_name:
                        primary = upsert_entity(row.entity_name, row.entity_type, row.confidence)
                        if primary and rels_from_json:
                            _add_semantic_relationship_edges(
                                rels_from_json,
                                upsert_entity,
                                add_edge,
                                include_meta,
                                context_meta={"intel_id": str(row.id)} if include_meta else None
                            )

                    if row.entity_name and ents_from_json:
                        primary = upsert_entity(row.entity_name, row.entity_type, row.confidence)
                        for ent in ents_from_json:
                            other_id = upsert_entity(ent["name"], ent.get("kind"), None)
                            if primary and other_id and other_id != primary:
                                add_edge(primary, other_id, kind="intel-mentions", weight=1)

                        intel_id_str = str(row.id)
                        ensure_node(intel_id_str, f"Intel: {row.source_type or 'data'}", "intel", score=row.confidence,
                                    meta={"intel_id": intel_id_str, "source_id": intel_id_str})
                        entry_type_map[intel_id_str] = "intel"
                        if primary:
                            add_edge(intel_id_str, primary, kind="intel-primary", weight=1)
                        for ent in ents_from_json:
                            other_id = upsert_entity(ent["name"], ent.get("kind"), None)
                            if other_id:
                                add_edge(intel_id_str, other_id, kind="intel-mentions", weight=1)

                for row in session.query(db_models.Page).limit(3000).all():
                    page_id = _page_id_from_row(row)
                    page_id_to_url[page_id] = row.url
                    page_ents: list[str] = []

                    if row.entities:
                        for e_json in row.entities:
                            if isinstance(e_json, dict):
                                e_name = e_json.get("name") or e_json.get("entity")
                                e_kind = e_json.get("type") or e_json.get("entity_type")
                                if e_name:
                                    eid = upsert_entity(e_name, e_kind, None)
                                    if eid:
                                        page_ents.append(eid)

                    add_cooccurrence_edges(page_ents)

                    ensure_node(page_id, row.title or row.url, "page", score=row.intel_score,
                                meta={"url": row.url, "page_type": row.page_type, "source_id": page_id, "page_id": page_id})
                    entry_type_map[page_id] = "page"

                    for eid in page_ents:
                        add_edge(page_id, eid, kind="page-mentions", weight=1)

                    for img in _collect_images_from_metadata(row.metadata_json or {}):
                        img_url = img["url"]
                        img_id = f"img:{img_url}"
                        ensure_node(img_id, img.get("alt") or img_url, "image",
                                    meta={"source_url": img_url, "source_id": img_id})
                        add_edge(page_id, img_id, kind="page-image", weight=1)

                    for link in row.outlinks or []:
                        if isinstance(link, str):
                            link_id = f"link:{link}"
                            ensure_node(link_id, link, "link", meta={"url": link, "source_id": link_id})
                            add_edge(page_id, link_id, kind="link", weight=1)

                _add_relationship_edges(session, ensure_node, add_edge, entry_type_map)

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

        try:
            with store.Session() as session:
                entity = session.query(db_models.Entity).filter_by(id=node_id).first()
                if entity:
                    node_type = "entity"
                    label = entity.name
                    meta = {
                        "entity_id": str(entity.id),
                        "name": entity.name,
                        "kind": entity.kind,
                        "source_id": str(entity.id),
                    }

                intel = session.query(db_models.IntelligenceData).filter_by(id=node_id).first()
                if intel:
                    node_type = "intel"
                    label = f"Intel: {intel.source_type or 'data'}"
                    meta = {
                        "intel_id": str(intel.id),
                        "entity_name": intel.entity_name,
                        "entity_type": intel.entity_type,
                        "data": intel.data_json,
                        "confidence": intel.confidence,
                        "source_id": str(intel.id),
                    }

                page = session.query(db_models.Page).filter_by(id=node_id).first()
                if page:
                    node_type = "page"
                    label = page.title or page.url
                    meta = {
                        "page_id": str(page.id),
                        "url": page.url,
                        "title": page.title,
                        "page_type": page.page_type,
                        "intel_score": page.intel_score,
                        "source_id": str(page.id),
                    }

            if node_id.startswith("link:"):
                url = node_id[5:]
                return jsonify({"id": node_id, "type": "link", "meta": {"url": url, "source_id": node_id}})

            if node_id.startswith("img:"):
                img_url = node_id[4:]
                return jsonify({"id": node_id, "type": "image", "meta": {"source_url": img_url, "source_id": img_url}})

        except Exception as e:
            logger.exception(f"Node lookup failed for {node_id}")

        img_url = node_id[4:] if node_id.startswith("img:") else node_id
        return jsonify({"id": node_id, "type": "image", "meta": {"source_url": img_url, "source_id": img_url}})

    @bp.get("/<entity_id>/gaps")
    @api_key_required
    def api_entity_gaps(entity_id):
        """Analyze data gaps for a specific entity."""
        emit_event("entity_gaps", f"analyzing entity {entity_id}")
        try:
            gaps = entity_crawler.analyze_entity_gaps(entity_id)
            return jsonify(gaps)
        except Exception as e:
            emit_event("entity_gaps", f"failed: {e}", level="error")
            logger.exception("Entity gap analysis failed")
            return jsonify({"error": str(e)}), 500

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

    @bp.post("/deduplicate")
    @api_key_required
    def api_deduplicate_entities():
        """Deduplicate entities based on similarity."""
        body = request.get_json(silent=True) or {}
        threshold = float(body.get("threshold", 0.85))
        
        emit_event("deduplication", f"deduplicating entities with threshold {threshold}")
        
        try:
            merge_map = store.deduplicate_entities(threshold=threshold)
            count = len(merge_map)
            emit_event("deduplication", f"merged {count} duplicate entities")
            return jsonify({
                "merged_count": count,
                "merge_map": {str(k): str(v) for k, v in merge_map.items()}
            })
        except Exception as e:
            emit_event("deduplication", f"failed: {e}", level="error")
            logger.exception("Entity deduplication failed")
            return jsonify({"error": str(e)}), 500

    @bp.post("/<source_id>/merge/<target_id>")
    @api_key_required
    def api_merge_entities(source_id, target_id):
        """Manually merge two entities."""
        emit_event("merge_entities", f"merging {source_id} into {target_id}")
        
        try:
            success = store.merge_entities(source_id, target_id)
            if success:
                emit_event("merge_entities", "merge successful")
                return jsonify({"status": "ok", "message": "Entities merged successfully"})
            else:
                return jsonify({"error": "Merge failed"}), 500
        except Exception as e:
            emit_event("merge_entities", f"failed: {e}", level="error")
            logger.exception("Entity merge failed")
            return jsonify({"error": str(e)}), 500

    @bp.get("/<entity_id>/similar")
    @api_key_required
    def api_similar_entities(entity_id):
        """Find similar entities."""
        threshold = float(request.args.get("threshold", 0.75))
        
        try:
            with store.Session() as session:
                entity = session.query(db_models.Entity).filter_by(id=entity_id).first()
                if not entity:
                    return jsonify({"error": "Entity not found"}), 404
                
                entity_name = entity.name
            
            similar = store.find_similar_entities(entity_name, threshold=threshold)
            
            return jsonify({
                "entity_name": entity_name,
                "similar_entities": [
                    {
                        "id": str(e.id),
                        "name": e.name,
                        "kind": e.kind,
                        "last_seen": e.last_seen.isoformat() if e.last_seen else None
                    }
                    for e in similar
                ]
            })
        except Exception as e:
            logger.exception("Similar entities lookup failed")
            return jsonify({"error": str(e)}), 500

    @bp.get("/<entity_id>/relations")
    @api_key_required
    def api_entity_relations(entity_id):
        """Get all relationships for an entity."""
        direction = request.args.get("direction", "both")
        max_depth = int(request.args.get("max_depth", 1))
        
        try:
            relations = store.get_entity_relations(
                entity_id=entity_id,
                direction=direction,
                max_depth=max_depth
            )
            
            return jsonify(relations)
        except Exception as e:
            logger.exception("Entity relations lookup failed")
            return jsonify({"error": str(e)}), 500

    @bp.route("/<entity_id>/analyze_gaps", methods=["GET"])
    @api_key_required
    def api_entity_analyze_gaps(entity_id):
        """Analyze an entity to identify missing data fields."""
        emit_event("entity_gaps_analysis", f"Analyzing gaps for entity {entity_id}")
        
        try:
            analysis = gap_analyzer.analyze_entity_gaps(entity_id)
            
            emit_event(
                "entity_gaps_analysis",
                f"Analysis complete - {len(analysis.get('missing_fields', []))} gaps found",
                level="info",
                payload={"entity_id": entity_id, "completeness": analysis.get("completeness_score")}
            )
            
            return jsonify(analysis)
        except Exception as e:
            logger.exception(f"Gap analysis failed for entity {entity_id}")
            emit_event("entity_gaps_analysis", f"Error: {str(e)}", level="error")
            return jsonify({"error": str(e)}), 500

    @bp.route("/analyze_all_gaps", methods=["GET"])
    @api_key_required
    def api_entities_analyze_all_gaps():
        """Analyze all entities to find those with critical data gaps."""
        limit = min(int(request.args.get("limit", 50) or 50), 200)
        
        emit_event("bulk_gap_analysis", f"Analyzing gaps for up to {limit} entities")
        
        try:
            results = gap_analyzer.analyze_all_entities(limit=limit)
            
            emit_event(
                "bulk_gap_analysis",
                f"Analyzed {len(results)} entities",
                level="info",
                payload={"count": len(results)}
            )
            
            return jsonify({
                "count": len(results),
                "entities": results
            })
        except Exception as e:
            logger.exception("Bulk gap analysis failed")
            emit_event("bulk_gap_analysis", f"Error: {str(e)}", level="error")
            return jsonify({"error": str(e)}), 500

    @bp.route("/<entity_id>/infer_from_relationships", methods=["POST"])
    @api_key_required
    def api_entity_infer_from_relationships(entity_id):
        """Use related entities to infer missing data for target entity."""
        hops = int(request.args.get("hops", 1) or 1)
        
        emit_event(
            "cross_entity_inference",
            f"Inferring data for entity {entity_id} via relationships",
            payload={"entity_id": entity_id, "hops": hops}
        )
        
        try:
            inferences = adaptive_crawler.cross_entity_inference(
                entity_id=entity_id,
                relationship_hops=hops
            )
            
            emit_event(
                "cross_entity_inference",
                f"Found {len(inferences.get('inferred_fields', []))} possible inferences",
                level="info",
                payload=inferences
            )
            
            return jsonify(inferences)
        except Exception as e:
            logger.exception(f"Cross-entity inference failed for {entity_id}")
            emit_event("cross_entity_inference", f"Error: {str(e)}", level="error")
            return jsonify({"error": str(e)}), 500
    
    return bp
