"""
Text processing utilities for cleaning, chunking, and sentence manipulation.
Handles HTML cleanup, text sanitization, and JSON parsing.
"""

import json
import logging
import re
from typing import List, Any
from bs4 import BeautifulSoup


class TextProcessor:
    """Handles text cleaning, chunking, sentence splitting, and JSON sanitization."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def clean_text(self, html_or_text: str) -> str:
        """
        Basic HTML boilerplate cleanup + prompt/instruction stripping; normalizes whitespace.
        Preserves paragraph boundaries (double newlines) for downstream semantic chunking.
        """
        if not html_or_text:
            return ""
        # Heuristic: if it contains HTML tags, parse; otherwise treat as text.
        if "<" in html_or_text and ">" in html_or_text:
            try:
                soup = BeautifulSoup(html_or_text, "html.parser")
                for tag in soup(["script", "style", "noscript"]):
                    tag.extract()
                # Drop common boilerplate containers
                for sel in ["nav", "footer", "header", "form"]:
                    for tag in soup.select(sel):
                        tag.extract()
                text = soup.get_text(separator="\n")
            except Exception:
                text = html_or_text
        else:
            text = html_or_text

        # Remove instruction/prompt-like content and metadata noise
        text = self.strip_prompty_lines(text)
        # Normalize paragraph breaks: 2+ newlines become double-newline
        text = re.sub(r"\n{2,}", "\n\n", text)
        # Collapse runs of whitespace within lines (spaces/tabs) but keep newlines
        text = re.sub(r"[^\S\n]+", " ", text)
        # Strip leading/trailing whitespace per line and remove blank-only lines
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines).strip()
        # Collapse 3+ consecutive newlines back to double-newline
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def split_sentences(self, text: str) -> List[str]:
        """Split text into sentences using basic punctuation heuristics."""
        if not text:
            return []
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def window_sentences(
        self,
        sentences: List[str],
        window_size: int,
        stride: int,
        max_windows: int,
    ) -> List[str]:
        """
        Create overlapping windows of sentences for better context preservation.
        
        Args:
            sentences: List of sentence strings
            window_size: Number of sentences per window
            stride: Step size between windows
            max_windows: Maximum number of windows to generate
            
        Returns:
            List of windowed text chunks
        """
        if window_size <= 1 or not sentences:
            return []
        windows: List[str] = []
        for start in range(0, len(sentences), stride):
            window = sentences[start : start + window_size]
            if len(window) < 2:  # skip tiny windows
                continue
            windows.append(" ".join(window))
            if len(windows) >= max_windows:
                break
        return windows

    def chunk_text(self, text: str, size: int, max_chunks: int) -> List[str]:
        """
        Split text into fixed-size chunks.
        
        Args:
            text: Text to chunk
            size: Character size per chunk
            max_chunks: Maximum number of chunks to create
            
        Returns:
            List of text chunks
        """
        if not text or size <= 0:
            return []
        chunks = []
        for i in range(0, len(text), size):
            chunks.append(text[i : i + size])
            if len(chunks) >= max_chunks:
                break
        return chunks

    def pretrim_irrelevant_sections(
        self, text: str, entity_name: str, max_no_entity_gap: int = 2
    ) -> str:
        """
        Stop at the first block of consecutive sentences that do NOT mention the entity,
        to cut off appended unrelated news/noise.
        
        Args:
            text: Text to trim
            entity_name: Entity name to look for
            max_no_entity_gap: Maximum consecutive sentences without entity before stopping
            
        Returns:
            Trimmed text
        """
        if not text or not entity_name:
            return text
        entity_l = entity_name.lower()
        sentences = self.split_sentences(text)
        kept = []
        gap = 0
        for s in sentences:
            if entity_l in s.lower():
                gap = 0
                kept.append(s)
            else:
                gap += 1
                if gap >= max_no_entity_gap:
                    break
                kept.append(s)
        return " ".join(kept).strip()

    def strip_code_fences(self, text: str) -> str:
        """Remove markdown code fences from text."""
        fenced = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE)
        fenced = re.sub(r"```$", "", fenced.strip())
        return fenced.strip()

    def sanitize_json_text(self, text: str) -> str:
        """Try to coerce near-JSON into valid JSON."""
        if not text:
            return ""
        t = self.strip_code_fences(text)
        # grab substring between first { and last }
        if "{" in t and "}" in t:
            t = t[t.find("{"): t.rfind("}") + 1]
        # replace single quotes with double quotes cautiously
        t = re.sub(r"(?<!\\)'", '"', t)
        # remove trailing commas before } or ]
        t = re.sub(r",\s*([}\]])", r"\1", t)
        return t.strip()

    def strip_prompty_lines(self, text: str) -> str:
        """
        Remove lines that look like injected prompts, instructions, or metadata noise.
        """
        if not text:
            return ""
        drop_patterns = re.compile(
            r"(?i)(^|\b)(instruction|prompt|assistant:|user:|###|score\s*\d+|uuid\s+[0-9a-f-]{8,}|No extracted intel|depth\s+\d+)\b"
        )
        kept = []
        for line in text.splitlines():
            if drop_patterns.search(line):
                continue
            kept.append(line)
        cleaned = "\n".join(kept).strip()
        cut_mark = re.search(r"(?i)(instruction:|###\s|assistant:|user:)", cleaned)
        if cut_mark:
            cleaned = cleaned[: cut_mark.start()].strip()
        return cleaned

    def safe_json_loads(self, text: str, fallback: Any):
        """Parse JSON defensively, returning fallback on failure."""
        if text is None:
            return fallback
        if isinstance(text, (dict, list)):
            return text
        if not isinstance(text, str):
            try:
                return json.loads(text)
            except Exception:
                return fallback
        # fast path
        try:
            return json.loads(text)
        except Exception:
            pass
        # sanitize and retry
        try:
            cleaned = self.sanitize_json_text(text)
            return json.loads(cleaned)
        except Exception:
            self.logger.debug("safe_json_loads: returning fallback after sanitize failure")
            return fallback
