"""Deduplication functions for search results."""

from typing import List, Dict, Any


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
        src = h.get("url")
        if src and src not in agg[key]["sources"]:
            agg[key]["sources"].append(src)
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
