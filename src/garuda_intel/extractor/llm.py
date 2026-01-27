"""
LLM Intelligence Extractor - Main orchestrator.
Composes text processing, semantic analysis, intelligence extraction, QA validation, and query generation.

This module provides a simplified orchestrator that delegates to specialized modules while maintaining
100% backward compatibility with the original monolithic implementation.
"""

import logging
import requests
from typing import List, Dict, Any, Tuple, Optional

from ..types.entity import EntityProfile, EntityType
from .filter import SemanticFilter
from .text_processor import TextProcessor
from .semantic_engine import SemanticEngine
from .intel_extractor import IntelExtractor
from .qa_validator import QAValidator
from .query_generator import QueryGenerator


class LLMIntelExtractor:
    """
    The cognitive core of the crawler.
    Handles:
    1. Semantic Embedding (for redundancy checks)
    2. Search Query Generation & Result Ranking
    3. Link Prioritization (Navigation)
    4. Intelligence Extraction (Data Gathering)
    5. Reflection & Verification (Quality Control)
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434/api/generate",
        model: str = "granite3.1-dense:8b",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        # Chunking / embedding controls
        summary_chunk_chars: int = 4000,
        extraction_chunk_chars: int = 4000,
        max_chunks: int = 20,
        sentence_window_size: int = 5,
        sentence_window_stride: int = 2,
        max_sentence_embeddings: int = 400,
        max_window_embeddings: int = 200,
        max_total_embeddings: int = 1200,
        min_text_length_for_embedding: int = 10,
        # Timeouts / retries
        summarize_timeout: int = 60,
        summarize_retries: int = 2,
        extract_timeout: int = 120,
        reflect_timeout: int = 30,
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.logger = logging.getLogger(__name__)
        self.relevance_filter = SemanticFilter(ollama_url, model)
        
        # Store configuration
        self.summary_chunk_chars = summary_chunk_chars
        self.max_chunks = max_chunks
        self.summarize_timeout = summarize_timeout
        self.summarize_retries = summarize_retries

        # Initialize component modules
        self.text_processor = TextProcessor()
        
        self.semantic_engine = SemanticEngine(
            embedding_model=embedding_model,
            sentence_window_size=sentence_window_size,
            sentence_window_stride=sentence_window_stride,
            max_sentence_embeddings=max_sentence_embeddings,
            max_window_embeddings=max_window_embeddings,
            max_total_embeddings=max_total_embeddings,
            min_text_length_for_embedding=min_text_length_for_embedding,
        )
        
        self.intel_extractor = IntelExtractor(
            ollama_url=ollama_url,
            model=model,
            extraction_chunk_chars=extraction_chunk_chars,
            max_chunks=max_chunks,
            extract_timeout=extract_timeout,
        )
        
        self.qa_validator = QAValidator(
            ollama_url=ollama_url,
            model=model,
            reflect_timeout=reflect_timeout,
        )
        
        self.query_generator = QueryGenerator(
            ollama_url=ollama_url,
            model=model,
        )

        # Backwards compatibility - expose embedder and model name
        self.embedding_model_name = embedding_model
        self._embedder = self.semantic_engine._embedder

    # --------- Summaries & embeddings ---------
    def summarize_page(self, text: str) -> str:
        """
        Summarize the full text by processing it in chunks to avoid truncation.
        """
        if not text:
            return ""

        summaries: List[str] = []
        for chunk in self.text_processor.chunk_text(text, self.summary_chunk_chars, self.max_chunks):
            prompt = (
                "Summarize the following text in 3-5 sentences, focusing on key facts and entities:\n\n"
                f"{chunk}"
            )
            for attempt in range(self.summarize_retries):
                try:
                    payload = {"model": self.model, "prompt": prompt, "stream": False}
                    resp = requests.post(self.ollama_url, json=payload, timeout=self.summarize_timeout)
                    part = resp.json().get("response", "").strip()
                    if part:
                        summaries.append(part)
                    break
                except Exception as e:
                    if attempt == self.summarize_retries - 1:
                        self.logger.warning(f"Summarization failed after retries: {e}")
                    else:
                        self.logger.debug(f"Summarization retry {attempt+1} due to {e}")

        return "\n".join(summaries).strip()

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding vector for text."""
        return self.semantic_engine.embed_text(text)

    def calculate_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        return self.semantic_engine.calculate_similarity(vec_a, vec_b)

    # --------- Reflection / verification ---------
    def reflect_and_verify(self, profile: EntityProfile, finding: Dict[str, Any]) -> Tuple[bool, float]:
        """Validate extracted intelligence for quality and relevance."""
        return self.qa_validator.reflect_and_verify(profile, finding)

    # --------- Intelligence extraction ---------
    def extract_intelligence(
        self,
        profile: EntityProfile,
        text: str,
        page_type: str,
        url: str,
        existing_intel: Any,
    ) -> dict:
        """
        Process the full text by chunking so large pages are fully analyzed.
        Merges chunk-level findings into a single aggregated result.
        """
        return self.intel_extractor.extract_intelligence(profile, text, page_type, url, existing_intel)

    # --------- Ranking helpers ---------
    def rank_links(self, profile: EntityProfile, page_url: str, page_text: str, links: List[Dict]) -> List[Dict]:
        """Rank navigation links for relevance to entity research."""
        return self.query_generator.rank_links(profile, page_url, page_text, links)

    def generate_search_queries(self, name: str, known_location: str = "") -> List[str]:
        """Generate search queries for finding entity information."""
        return self.query_generator.generate_search_queries(name, known_location)

    def rank_search_results(self, profile: EntityProfile, search_results: List[dict]) -> List[dict]:
        """Rank search results by relevance and identify official sources."""
        return self.query_generator.rank_search_results(profile, search_results)

    # ---------- Entity helpers ----------
    def extract_entities_from_finding(self, finding: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract entity mentions from a finding."""
        return self.intel_extractor.extract_entities_from_finding(finding)

    # ---------- Embedding helpers ----------
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
        """Build embeddings for a page with multiple semantic views."""
        return self.semantic_engine.build_embeddings_for_page(
            url=url,
            metadata=metadata,
            summary=summary,
            text_content=text_content,
            findings_with_ids=findings_with_ids,
            page_type=page_type,
            entity_name=entity_name,
            entity_type=entity_type,
            max_sentences=max_sentences,
            page_uuid=page_uuid,
        )

    def build_embeddings_for_entities(
        self,
        entities: List[Dict[str, Any]],
        source_url: str,
        entity_type: EntityType,
        entity_id_map: Dict[tuple, Any],
        page_uuid: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build embeddings for extracted entities."""
        return self.semantic_engine.build_embeddings_for_entities(
            entities=entities,
            source_url=source_url,
            entity_type=entity_type,
            entity_id_map=entity_id_map,
            page_uuid=page_uuid,
        )

    # ---------- Query helpers ----------
    def generate_seed_queries(self, user_question: str, entity_name: str) -> List[str]:
        """Generates 3-4 specific search strings to find new data online."""
        return self.query_generator.generate_seed_queries(user_question, entity_name)

    def synthesize_answer(self, question: str, context_hits: List[Dict]) -> str:
        """Synthesize an answer from context snippets."""
        return self.query_generator.synthesize_answer(question, context_hits)

    def evaluate_sufficiency(self, answer: str) -> bool:
        """Checks if the LLM flagged the data as missing."""
        return self.query_generator.evaluate_sufficiency(answer)

    # ---------- Text helpers (delegated for backwards compatibility) ----------
    def _clean_text(self, html_or_text: str) -> str:
        """Basic HTML boilerplate cleanup + prompt/instruction stripping."""
        return self.text_processor.clean_text(html_or_text)

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        return self.text_processor.split_sentences(text)

    def _window_sentences(
        self,
        sentences: List[str],
        window_size: int,
        stride: int,
        max_windows: int,
    ) -> List[str]:
        """Create overlapping windows of sentences."""
        return self.text_processor.window_sentences(sentences, window_size, stride, max_windows)

    def _chunk_text(self, text: str, size: int, max_chunks: int) -> List[str]:
        """Split text into fixed-size chunks."""
        return self.text_processor.chunk_text(text, size, max_chunks)

    def _pretrim_irrelevant_sections(self, text: str, entity_name: str, max_no_entity_gap: int = 2) -> str:
        """Trim irrelevant sections from text."""
        return self.text_processor.pretrim_irrelevant_sections(text, entity_name, max_no_entity_gap)

    def _strip_code_fences(self, text: str) -> str:
        """Remove markdown code fences."""
        return self.text_processor.strip_code_fences(text)

    def _sanitize_json_text(self, text: str) -> str:
        """Try to coerce near-JSON into valid JSON."""
        return self.text_processor.sanitize_json_text(text)

    def _strip_prompty_lines(self, text: str) -> str:
        """Remove lines that look like prompts or instructions."""
        return self.text_processor.strip_prompty_lines(text)

    def _safe_json_loads(self, text: str, fallback: Any):
        """Parse JSON defensively."""
        return self.text_processor.safe_json_loads(text, fallback)

    # ---------- Internal helpers (delegated) ----------
    def _extract_chunk_intel(
        self,
        profile: EntityProfile,
        text_chunk: str,
        page_type: str,
        url: str,
        existing_intel: Any,
    ) -> dict:
        """Extract intelligence from a single text chunk."""
        return self.intel_extractor._extract_chunk_intel(profile, text_chunk, page_type, url, existing_intel)

    def _merge_intel(self, base: Dict[str, Any], new: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge new intelligence into base."""
        return self.intel_extractor._merge_intel(base, new)

    def _build_existing_context(self, intel: Any) -> str:
        """Build context string from existing intelligence."""
        return self.intel_extractor._build_existing_context(intel)

    def _rule_based_intel(self, profile: EntityProfile, text: str, url: str, page_type: str) -> dict:
        """Lightweight deterministic extraction fallback."""
        return self.intel_extractor._rule_based_intel(profile, text, url, page_type)

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
        return self.semantic_engine._make_entry(
            base_id=base_id,
            suffix=suffix,
            vector=vector,
            kind=kind,
            url=url,
            page_type=page_type,
            entity_name=entity_name,
            entity_type=entity_type,
            text=text,
            data=data,
            sql_id=sql_id,
            sql_entity_id=sql_entity_id,
            sql_page_id=sql_page_id,
        )

    def _format_finding(self, finding: Dict[str, Any]) -> str:
        """Format finding dictionary into readable text."""
        return self.semantic_engine._format_finding(finding)
