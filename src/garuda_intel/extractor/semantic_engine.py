"""
Semantic engine for text embeddings and similarity calculations.
Handles sentence transformers and vector operations.
"""

import json
import logging
import uuid
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from sentence_transformers import SentenceTransformer

from ..types.entity import EntityType
from .text_processor import TextProcessor


class SemanticEngine:
    """Handles embedding generation, similarity calculation, and embedding construction for pages and entities."""

    def __init__(
        self,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        sentence_window_size: int = 5,
        sentence_window_stride: int = 2,
        max_sentence_embeddings: int = 400,
        max_window_embeddings: int = 200,
        max_total_embeddings: int = 1200,
        min_text_length_for_embedding: int = 10,
    ):
        self.logger = logging.getLogger(__name__)
        self.embedding_model_name = embedding_model
        self._embedder = None
        self.sentence_window_size = sentence_window_size
        self.sentence_window_stride = sentence_window_stride
        self.max_sentence_embeddings = max_sentence_embeddings
        self.max_window_embeddings = max_window_embeddings
        self.max_total_embeddings = max_total_embeddings
        self.min_text_length_for_embedding = min_text_length_for_embedding
        self.text_processor = TextProcessor()

        if SentenceTransformer:
            try:
                self._embedder = SentenceTransformer(embedding_model)
                self.logger.info(f"Loaded embedding model: {embedding_model}")
            except Exception as e:
                self.logger.warning(f"Could not load embedding model {embedding_model}: {e}")
        else:
            self.logger.warning("sentence-transformers not installed; semantic features disabled.")

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding vector for text."""
        if not self._embedder or not text or len(text) < self.min_text_length_for_embedding:
            return []
        try:
            return self._embedder.encode(text, normalize_embeddings=True).tolist()
        except Exception as e:
            self.logger.error(f"Embedding generation failed: {e}")
            return []

    def calculate_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec_a or not vec_b:
            return 0.0
        try:
            a = np.array(vec_a)
            b = np.array(vec_b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(np.dot(a, b) / (norm_a * norm_b))
        except Exception as e:
            self.logger.warning(f"Similarity calculation error: {e}")
            return 0.0

    def build_embeddings_for_page(
        self,
        url: str,
        metadata: Dict,
        summary: str,
        text_content: str,
        findings_with_ids: List[Tuple[Dict, Any]],
        page_type: str,
        entity_name: str,
        entity_type: EntityType,
        max_sentences: int = 40,
        page_uuid: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Produce multiple semantic views:
          - page-level (title/description/summary/url)
          - sentence-level for full text (capped)
          - overlapping sentence windows (to preserve continuity)
          - findings with ids
        Uses page_uuid when provided to keep SQL/Qdrant alignment.
        """
        entries: List[Dict[str, Any]] = []
        total_embeddings = 0
        primary_id = page_uuid or url

        cleaned_text = self.text_processor.clean_text(text_content)

        # Page-level views
        views = [
            ("title", metadata.get("title", "")),
            ("description", metadata.get("description", "") or metadata.get("og_title", "")),
            ("summary", summary),
            ("url", url),
        ]

        for name, text in views:
            if total_embeddings >= self.max_total_embeddings:
                break
            if not text:
                continue
            vec = self.embed_text(text)
            if vec:
                entries.append(
                    self._make_entry(
                        base_id=primary_id,
                        suffix=f"page-{name}",
                        vector=vec,
                        kind="page",
                        url=url,
                        page_type=page_type,
                        entity_name=entity_name,
                        entity_type=entity_type,
                        text=text,
                        sql_page_id=page_uuid,
                    )
                )
                total_embeddings += 1

        # Sentence-level embeddings for the whole page
        sentences = self.text_processor.split_sentences(cleaned_text)
        if max_sentences:
            sentences = sentences[:max_sentences]

        sentence_limit = min(self.max_sentence_embeddings, len(sentences))
        for idx, sent in enumerate(sentences[:sentence_limit]):
            if total_embeddings >= self.max_total_embeddings:
                break
            vec = self.embed_text(sent)
            if vec:
                entries.append(
                    self._make_entry(
                        base_id=primary_id,
                        suffix=f"sentence-{idx}",
                        vector=vec,
                        kind="page_sentence",
                        url=url,
                        page_type=page_type,
                        entity_name=entity_name,
                        entity_type=entity_type,
                        text=sent,
                        sql_page_id=page_uuid,
                    )
                )
                total_embeddings += 1

        # Overlapping windows of sentences
        windows = self.text_processor.window_sentences(
            sentences=sentences,
            window_size=self.sentence_window_size,
            stride=self.sentence_window_stride,
            max_windows=self.max_window_embeddings,
        )
        for idx, win_text in enumerate(windows):
            if total_embeddings >= self.max_total_embeddings:
                break
            vec = self.embed_text(win_text)
            if vec:
                entries.append(
                    self._make_entry(
                        base_id=primary_id,
                        suffix=f"window-{idx}",
                        vector=vec,
                        kind="page_window",
                        url=url,
                        page_type=page_type,
                        entity_name=entity_name,
                        entity_type=entity_type,
                        text=win_text,
                        sql_page_id=page_uuid,
                    )
                )
                total_embeddings += 1

        # Findings (tuple may contain finding, sql_intel_id, optional sql_entity_id)
        for idx, tup in enumerate(findings_with_ids or []):
            if total_embeddings >= self.max_total_embeddings:
                break
            finding = tup[0] if len(tup) > 0 else {}
            sql_id = tup[1] if len(tup) > 1 else None
            sql_entity_id = tup[2] if len(tup) > 2 else None
            text = self._format_finding(finding)
            vec = self.embed_text(text)
            if vec:
                entries.append(
                    self._make_entry(
                        base_id=primary_id,
                        suffix=f"finding-{idx}",
                        vector=vec,
                        kind="finding",
                        url=url,
                        page_type=page_type,
                        entity_name=entity_name,
                        entity_type=entity_type,
                        text=text,
                        data=finding,
                        sql_id=sql_id,
                        sql_entity_id=sql_entity_id,
                        sql_page_id=page_uuid,
                    )
                )
                total_embeddings += 1

        self.logger.debug(
            f"Embedding stats for {url}: total={total_embeddings}, sentences={len(sentences)}, windows={len(windows)}, findings={len(findings_with_ids or [])}"
        )
        return entries

    def build_embeddings_for_entities(
        self,
        entities: List[Dict[str, Any]],
        source_url: str,
        entity_type: EntityType,
        entity_id_map: Dict[tuple, Any],
        page_uuid: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build embeddings for extracted entities."""
        entries: List[Dict[str, Any]] = []
        primary_id = page_uuid or source_url
        for ent in entities:
            text = json.dumps({"name": ent.get("name"), **(ent.get("attrs") or {})}, ensure_ascii=False)
            vec = self.embed_text(text)
            if not vec:
                continue
            ent_kind = ent.get("kind", "entity")
            suffix = f"entity-{ent_kind}-{ent.get('name','')}"
            sql_ent_id = entity_id_map.get((ent.get("name"), ent_kind))
            entries.append(
                self._make_entry(
                    base_id=primary_id,
                    suffix=suffix,
                    vector=vec,
                    kind="entity",
                    url=source_url,
                    page_type=ent_kind,
                    entity_name=ent.get("name", ""),
                    entity_type=ent_kind,
                    text=text,
                    data=ent,
                    sql_entity_id=sql_ent_id,
                    sql_page_id=page_uuid,
                )
            )
        return entries

    def _make_entry(
        self,
        base_id: str,
        suffix: str,
        vector: List[float],
        kind: str,
        url: str,
        page_type: str,
        entity_name: str,
        entity_type: Any,
        text: str,
        data: Any = None,
        sql_id: Any = None,
        sql_entity_id: Any = None,
        sql_page_id: Any = None,
    ) -> Dict[str, Any]:
        """Create a standardized embedding entry."""
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{base_id}#{suffix}"))
        payload = {
            "kind": kind,
            "url": url,
            "page_type": page_type if isinstance(page_type, str) else getattr(page_type, "value", str(page_type)),
            "entity": entity_name,
            "entity_type": getattr(entity_type, "value", str(entity_type)) if hasattr(entity_type, "value") else str(entity_type),
            "entity_kind": page_type,
            "text": text,
            "data": data,
        }
        if sql_id is not None:
            payload["sql_intel_id"] = sql_id
        if sql_entity_id is not None:
            payload["sql_entity_id"] = sql_entity_id
        if sql_page_id is not None:
            payload["sql_page_id"] = sql_page_id
        return {
            "id": pid,
            "vector": vector,
            "payload": payload,
        }

    def _format_finding(self, finding: Dict[str, Any]) -> str:
        """Format finding dictionary into a readable text representation."""
        try:
            parts = []
            bi = finding.get("basic_info", {}) if isinstance(finding, dict) else {}
            if bi:
                parts.append("basic_info: " + json.dumps(bi, ensure_ascii=False))
            for key in ["persons", "jobs", "metrics", "locations", "financials", "products", "events"]:
                if finding.get(key):
                    parts.append(f"{key}: " + json.dumps(finding[key], ensure_ascii=False))
            return " | ".join(parts) or json.dumps(finding, ensure_ascii=False)
        except Exception:
            return json.dumps(finding, ensure_ascii=False)
