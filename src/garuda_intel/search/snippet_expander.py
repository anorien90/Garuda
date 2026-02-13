"""
Snippet window expansion for deep RAG search.

When a semantic-snippet hit doesn't contain enough information, this module
provides helpers to expand the snippet window in both directions by fetching
neighbouring snippets from the database until the combined text is sufficient
or no further snippets exist.
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Maximum number of expansion rounds to avoid runaway loops
_MAX_EXPANSION_ROUNDS = 4
# Characters per round of expansion (window grows by this each time)
_EXPANSION_WINDOW = 2
# Minimum combined text length below which we always try to expand
_MIN_SUFFICIENT_LENGTH = 200


def expand_snippet_window(
    hit: Dict[str, Any],
    store: Any,
    *,
    min_length: int = _MIN_SUFFICIENT_LENGTH,
    max_rounds: int = _MAX_EXPANSION_ROUNDS,
    window_step: int = _EXPANSION_WINDOW,
    sufficiency_fn: Any = None,
) -> Dict[str, Any]:
    """Expand a snippet hit by fetching neighbours in both directions.

    The function progressively widens the window around the original snippet
    until one of these conditions is met:

    * ``sufficiency_fn(combined_text)`` returns ``True``
    * The combined text has ``>= min_length`` characters **and** no new
      snippets were returned (boundary reached)
    * ``max_rounds`` iterations have been performed

    Args:
        hit: A search-result dict that should contain at least ``snippet``
             (the text) and ``data`` with ``page_id`` and ``chunk_index``.
        store: A :class:`PersistenceStore` (or compatible) providing
               ``get_neighbouring_snippets``.
        min_length: Minimum combined text length considered sufficient.
        max_rounds: Cap on expansion iterations.
        window_step: How many extra snippets to fetch per direction per round.
        sufficiency_fn: Optional callable ``(text) -> bool`` for custom
            sufficiency checks (e.g. LLM-based).

    Returns:
        A *new* dict based on ``hit`` with ``snippet`` replaced by the
        expanded text and an ``expanded`` flag set to ``True`` when
        expansion occurred.  The original ``hit`` is not mutated.
    """
    snippet_text = hit.get("snippet") or hit.get("text") or ""
    data = hit.get("data") or {}
    page_id = data.get("page_id") or hit.get("page_id") or hit.get("sql_page_id")
    chunk_index = data.get("chunk_index")

    # Cannot expand without page_id + chunk_index
    if page_id is None or chunk_index is None:
        return hit

    if not hasattr(store, "get_neighbouring_snippets"):
        return hit

    combined_parts_before: List[str] = []
    combined_parts_after: List[str] = []
    seen_indices = {chunk_index}
    current_window = 0
    expanded = False

    for _ in range(max_rounds):
        current_window += window_step

        neighbours = store.get_neighbouring_snippets(
            page_id=str(page_id),
            chunk_index=chunk_index,
            direction="both",
            window=current_window,
        )

        new_found = False
        for nb in neighbours:
            idx = nb.get("chunk_index")
            if idx is None or idx in seen_indices:
                continue
            seen_indices.add(idx)
            new_found = True
            expanded = True
            if idx < chunk_index:
                combined_parts_before.append(nb.get("text", ""))
            else:
                combined_parts_after.append(nb.get("text", ""))

        if not new_found:
            break  # no more snippets in either direction

        # Build combined text and check sufficiency
        combined_parts_before.sort(key=lambda _t: 0)  # keep insertion order
        combined_text = " ".join(
            combined_parts_before + [snippet_text] + combined_parts_after
        )

        if sufficiency_fn and sufficiency_fn(combined_text):
            snippet_text = combined_text
            break

        if len(combined_text) >= min_length:
            snippet_text = combined_text
            break

        snippet_text = combined_text

    if not expanded:
        return hit

    result = dict(hit)
    result["snippet"] = snippet_text
    result["text"] = snippet_text
    result["expanded"] = True
    result["expansion_window"] = current_window
    return result


def expand_snippet_hits(
    hits: List[Dict[str, Any]],
    store: Any,
    *,
    min_length: int = _MIN_SUFFICIENT_LENGTH,
    max_rounds: int = _MAX_EXPANSION_ROUNDS,
    sufficiency_fn: Any = None,
) -> List[Dict[str, Any]]:
    """Apply :func:`expand_snippet_window` to every snippet hit in a list.

    Non-snippet hits (those without ``chunk_index``) are returned unchanged.
    """
    expanded: List[Dict[str, Any]] = []
    for hit in hits:
        data = hit.get("data") or {}
        is_snippet = (
            hit.get("kind") in ("semantic-snippet", "semantic_snippet")
            or data.get("chunk_index") is not None
        )
        if is_snippet:
            expanded.append(
                expand_snippet_window(
                    hit, store,
                    min_length=min_length,
                    max_rounds=max_rounds,
                    sufficiency_fn=sufficiency_fn,
                )
            )
        else:
            expanded.append(hit)
    return expanded
