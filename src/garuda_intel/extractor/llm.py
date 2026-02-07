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
    6. Entity Merging & Type Hierarchy (Phase 5)
    
    Enhanced with entity merging capabilities to:
    - Find and update existing entities by name
    - Detect specialized entity types (e.g., address → headquarters)
    - Track field discovery for adaptive learning
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
        # Timeouts / retries (default 15 minutes for long operations)
        summarize_timeout: int = 900,
        summarize_retries: int = 3,
        extract_timeout: int = 900,
        reflect_timeout: int = 300,
        # Entity merging (Phase 5)
        enable_entity_merging: bool = True,
        session_maker=None,
        # Comprehensive extraction (Phase 6)
        enable_comprehensive_extraction: bool = True,
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
        self.enable_entity_merging = enable_entity_merging
        self.session_maker = session_maker
        self.enable_comprehensive_extraction = enable_comprehensive_extraction

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
            enable_entity_merging=enable_entity_merging,
            session_maker=session_maker,
            enable_comprehensive_extraction=enable_comprehensive_extraction,
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
        Summarize the full text using hierarchical summarization with overlapping windows.
        
        For large texts that exceed LLM context:
        1. Split into overlapping chunks for context preservation
        2. Summarize each chunk compactly
        3. Recursively summarize partial summaries
        4. Final merge produces coherent summary
        """
        if not text:
            return ""

        # Try direct summarization for small texts
        if len(text) < self.summary_chunk_chars * 0.8:
            return self._summarize_chunk(text)
        
        # Hierarchical summarization for large texts
        return self._hierarchical_summarize(text)
    
    def _hierarchical_summarize(self, text: str, max_summary_length: int = 2000) -> str:
        """
        Hierarchical summarization with overlapping windows for large texts.
        
        Uses overlapping partial reflection and summarization windows that get
        merged into increasingly compact summaries.
        """
        # Step 1: Create overlapping chunks with 25% overlap for context preservation
        chunk_size = self.summary_chunk_chars
        overlap = chunk_size // 4  # 25% overlap
        chunks = []
        
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - overlap
            if start >= len(text) - overlap:
                break
        
        if not chunks:
            return ""
        
        # Step 2: Summarize each chunk with compact output
        partial_summaries = []
        for i, chunk in enumerate(chunks):
            summary = self._summarize_chunk_compact(
                chunk, 
                context=f"Part {i+1} of {len(chunks)}"
            )
            if summary:
                partial_summaries.append(summary)
        
        if not partial_summaries:
            return ""
        
        # Step 3: If we have few enough summaries, combine directly
        if len(partial_summaries) <= 3:
            combined = "\n\n".join(partial_summaries)
            if len(combined) < max_summary_length:
                return self._final_merge_summary(combined)
            return self._summarize_chunk(combined)
        
        # Step 4: Recursive summarization for many partial summaries
        # Group partial summaries with overlap for coherence
        window_size = 3
        stride = 2  # Overlap of 1 summary between windows
        intermediate_summaries = []
        
        for i in range(0, len(partial_summaries), stride):
            window = partial_summaries[i:i + window_size]
            if len(window) > 1:
                window_text = "\n\n---\n\n".join(window)
                merged = self._summarize_chunk_compact(
                    window_text,
                    context="Merge partial summaries"
                )
                if merged:
                    intermediate_summaries.append(merged)
            elif window:
                intermediate_summaries.append(window[0])
        
        # Step 5: Final merge of intermediate summaries
        if len(intermediate_summaries) <= 3:
            final_text = "\n\n".join(intermediate_summaries)
            return self._final_merge_summary(final_text)
        
        # Recursively summarize if still too many
        return self._hierarchical_summarize(
            "\n\n---\n\n".join(intermediate_summaries),
            max_summary_length
        )
    
    def _summarize_chunk(self, text: str) -> str:
        """Summarize a single chunk with standard prompting."""
        prompt = (
            "Summarize the following text in 3-5 sentences, focusing on key facts and entities:\n\n"
            f"{text}"
        )
        return self._call_llm_with_retry(prompt)
    
    def _summarize_chunk_compact(self, text: str, context: str = "") -> str:
        """Summarize a chunk compactly for hierarchical summarization."""
        context_str = f" ({context})" if context else ""
        prompt = (
            f"Summarize this text{context_str} in 2-3 sentences, preserving key entities, "
            "facts, relationships, and numbers. Be concise but complete:\n\n"
            f"{text}"
        )
        return self._call_llm_with_retry(prompt)
    
    def _final_merge_summary(self, text: str) -> str:
        """Create final merged summary from partial summaries."""
        prompt = (
            "Combine these partial summaries into a single coherent 3-5 sentence summary. "
            "Preserve all key entities, facts, and relationships. Remove redundancy:\n\n"
            f"{text}"
        )
        return self._call_llm_with_retry(prompt)
    
    def _call_llm_with_retry(self, prompt: str) -> str:
        """Call LLM with retry logic and proper error handling."""
        for attempt in range(self.summarize_retries):
            try:
                payload = {"model": self.model, "prompt": prompt, "stream": False}
                resp = requests.post(self.ollama_url, json=payload, timeout=self.summarize_timeout)
                
                # Check for input length errors
                if resp.status_code == 400:
                    error_text = resp.text.lower()
                    if "context" in error_text or "length" in error_text or "token" in error_text:
                        self.logger.warning(f"Input too long for LLM, will segment: {resp.text[:200]}")
                        # Return empty to trigger segmentation in caller
                        return ""
                
                resp.raise_for_status()
                return resp.json().get("response", "").strip()
                
            except requests.exceptions.Timeout as e:
                if attempt == self.summarize_retries - 1:
                    self.logger.warning(f"Summarization timed out after {self.summarize_timeout}s: {e}")
                else:
                    self.logger.debug(f"Summarization timeout retry {attempt+1}")
            except Exception as e:
                if attempt == self.summarize_retries - 1:
                    self.logger.warning(f"Summarization failed after retries: {e}")
                else:
                    self.logger.debug(f"Summarization retry {attempt+1} due to {e}")
        
        return ""

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
    def extract_entities_from_finding(
        self, 
        finding: Dict[str, Any],
        primary_entity_name: Optional[str] = None,
        context_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract entity mentions from a finding with type hierarchy detection.
        
        Args:
            finding: The extracted finding dictionary
            primary_entity_name: Name of the primary entity for relationship context
            context_text: Original text for specialized type detection
            
        Returns:
            List of entity dictionaries with enhanced type information
        """
        return self.intel_extractor.extract_entities_from_finding(
            finding, 
            primary_entity_name=primary_entity_name,
            context_text=context_text,
        )
    
    def process_entities_with_merging(
        self,
        entities: List[Dict[str, Any]],
        page_id: Optional[str] = None,
        source_url: Optional[str] = None,
        confidence: float = 0.5,
    ) -> Dict[Tuple[str, str], str]:
        """
        Process extracted entities with intelligent merging.
        
        Args:
            entities: List of entity dictionaries from extract_entities_from_finding
            page_id: Source page ID for provenance
            source_url: Source URL for provenance
            confidence: Extraction confidence score
            
        Returns:
            Mapping of (name, kind) to entity_id
        """
        return self.intel_extractor.process_entities_with_merging(
            entities=entities,
            page_id=page_id,
            source_url=source_url,
            confidence=confidence,
        )

    def infer_relationships_from_entities(
        self,
        entities: List[Dict[str, Any]],
        context_text: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Infer implicit relationships between extracted entities based on context.
        
        This method analyzes the extracted entities and the surrounding text to
        discover relationships that may not have been explicitly stated.
        
        Args:
            entities: List of extracted entity dictionaries
            context_text: The original text from which entities were extracted
            
        Returns:
            List of inferred relationship dictionaries
        """
        return self.intel_extractor.infer_relationships_from_entities(
            entities=entities,
            context_text=context_text,
        )

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
    def generate_seed_queries(self, user_question: str, entity_name: str = "") -> List[str]:
        """Generates 3-4 specific search strings to find new data online."""
        return self.query_generator.generate_seed_queries(user_question, entity_name)
    
    def paraphrase_query(self, query: str) -> List[str]:
        """Generate paraphrased versions of a query for better retrieval."""
        return self.query_generator.paraphrase_query(query)

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
