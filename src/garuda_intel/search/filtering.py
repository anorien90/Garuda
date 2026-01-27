"""Filtering functions for search results."""

from typing import List, Dict
from qdrant_client.http import models as qmodels


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
