"""
Semantic chunking for intelligent text splitting.

Splits text into semantically coherent chunks that preserve context
and maintain topic boundaries, improving extraction quality.
"""

import logging
import re
from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class TextChunk:
    """Represents a semantically coherent chunk of text."""
    text: str
    start_index: int
    end_index: int
    topic_context: Optional[str] = None  # Heading or topic for this chunk
    

class SemanticChunker:
    """
    Splits text into semantically coherent chunks.
    
    Uses paragraph boundaries, heading detection, and topic coherence
    to create chunks that preserve context and meaning.
    """
    
    def __init__(self):
        """Initialize semantic chunker."""
        self.logger = logging.getLogger(__name__)
        
        # Patterns for detecting headings and section breaks
        self.heading_pattern = re.compile(
            r'^(?:#{1,6}\s+|[A-Z][^.!?]*:|\d+\.\s+[A-Z])',
            re.MULTILINE
        )
    
    def chunk_by_topic(
        self,
        text: str,
        max_chunk_size: int = 4000,
        min_chunk_size: int = 500,
        preserve_paragraphs: bool = True
    ) -> List[TextChunk]:
        """
        Split text into semantically coherent chunks based on topics.
        
        Args:
            text: Text to chunk
            max_chunk_size: Maximum characters per chunk
            min_chunk_size: Minimum characters per chunk (avoid tiny chunks)
            preserve_paragraphs: Whether to avoid breaking paragraphs
            
        Returns:
            List of text chunks with context
        """
        if not text or max_chunk_size <= 0:
            return []
        
        # If text is small enough, return as single chunk
        if len(text) <= max_chunk_size:
            return [TextChunk(text=text, start_index=0, end_index=len(text))]
        
        # Detect sections and headings
        sections = self._split_by_sections(text)
        
        # Build chunks respecting section boundaries
        chunks = []
        current_chunk = []
        current_size = 0
        current_context = None
        chunk_start = 0
        
        for section_heading, section_text in sections:
            section_len = len(section_text)
            
            # If adding this section would exceed max size, finalize current chunk
            if current_chunk and current_size + section_len > max_chunk_size:
                # Join current chunk
                chunk_text = "".join(current_chunk)
                if len(chunk_text.strip()) >= min_chunk_size:
                    chunks.append(TextChunk(
                        text=chunk_text,
                        start_index=chunk_start,
                        end_index=chunk_start + len(chunk_text),
                        topic_context=current_context
                    ))
                
                # Start new chunk
                current_chunk = []
                current_size = 0
                chunk_start = chunk_start + len(chunk_text) if chunk_text else 0
            
            # Add heading as context if present
            if section_heading and not current_context:
                current_context = section_heading
            
            # If section itself is larger than max size, split it further
            if section_len > max_chunk_size:
                # Finalize any pending chunk first
                if current_chunk:
                    chunk_text = "".join(current_chunk)
                    if len(chunk_text.strip()) >= min_chunk_size:
                        chunks.append(TextChunk(
                            text=chunk_text,
                            start_index=chunk_start,
                            end_index=chunk_start + len(chunk_text),
                            topic_context=current_context
                        ))
                    current_chunk = []
                    current_size = 0
                    chunk_start = chunk_start + len(chunk_text) if chunk_text else 0
                
                # Split large section by paragraphs
                subsections = self._split_large_section(
                    section_text,
                    max_chunk_size,
                    min_chunk_size,
                    preserve_paragraphs
                )
                
                for subsection in subsections:
                    chunks.append(TextChunk(
                        text=subsection,
                        start_index=chunk_start,
                        end_index=chunk_start + len(subsection),
                        topic_context=section_heading or current_context
                    ))
                    chunk_start += len(subsection)
                
                current_context = None
            else:
                # Add section to current chunk
                current_chunk.append(section_text)
                current_size += section_len
        
        # Finalize any remaining chunk
        if current_chunk:
            chunk_text = "".join(current_chunk)
            if len(chunk_text.strip()) >= min_chunk_size:
                chunks.append(TextChunk(
                    text=chunk_text,
                    start_index=chunk_start,
                    end_index=chunk_start + len(chunk_text),
                    topic_context=current_context
                ))
        
        self.logger.debug(f"Created {len(chunks)} semantic chunks from {len(text)} chars")
        return chunks
    
    def _split_by_sections(self, text: str) -> List[Tuple[Optional[str], str]]:
        """
        Split text by section headings.
        
        Args:
            text: Text to split
            
        Returns:
            List of (heading, section_text) tuples
        """
        sections = []
        lines = text.split('\n')
        
        current_heading = None
        current_section = []
        
        for line in lines:
            # Check if line is a heading
            if self._is_heading(line):
                # Save previous section
                if current_section:
                    section_text = '\n'.join(current_section)
                    sections.append((current_heading, section_text))
                
                # Start new section
                current_heading = line.strip()
                current_section = [line]
            else:
                current_section.append(line)
        
        # Add final section
        if current_section:
            section_text = '\n'.join(current_section)
            sections.append((current_heading, section_text))
        
        # If no sections found, return entire text
        if not sections:
            return [(None, text)]
        
        return sections
    
    def _is_heading(self, line: str) -> bool:
        """
        Check if a line is likely a heading.
        
        Args:
            line: Line to check
            
        Returns:
            True if line appears to be a heading
        """
        line = line.strip()
        
        if not line:
            return False
        
        # Markdown headings
        if line.startswith('#'):
            return True
        
        # Lines ending with colon (section labels)
        if line.endswith(':') and len(line) < 100:
            return True
        
        # Numbered headings (1. Introduction, etc.)
        if re.match(r'^\d+\.\s+[A-Z]', line):
            return True
        
        # All caps short lines
        if line.isupper() and len(line) < 80 and len(line.split()) <= 10:
            return True
        
        return False
    
    def _split_large_section(
        self,
        text: str,
        max_size: int,
        min_size: int,
        preserve_paragraphs: bool
    ) -> List[str]:
        """
        Split a large section into smaller chunks.
        
        Args:
            text: Section text to split
            max_size: Maximum chunk size
            min_size: Minimum chunk size
            preserve_paragraphs: Whether to preserve paragraph boundaries
            
        Returns:
            List of text chunks
        """
        if preserve_paragraphs:
            # Split by paragraphs (double newline)
            paragraphs = re.split(r'\n\s*\n', text)
            
            chunks = []
            current_chunk = []
            current_size = 0
            
            for para in paragraphs:
                para_len = len(para)
                
                # If paragraph itself is too large, split by sentences
                if para_len > max_size:
                    # Finalize current chunk
                    if current_chunk:
                        chunks.append('\n\n'.join(current_chunk))
                        current_chunk = []
                        current_size = 0
                    
                    # Split large paragraph
                    sentence_chunks = self._split_by_sentences(para, max_size)
                    chunks.extend(sentence_chunks)
                    continue
                
                # If adding this paragraph exceeds max size, finalize chunk
                if current_chunk and current_size + para_len + 2 > max_size:
                    if current_size >= min_size:
                        chunks.append('\n\n'.join(current_chunk))
                    current_chunk = [para]
                    current_size = para_len
                else:
                    current_chunk.append(para)
                    current_size += para_len + 2  # Account for separator
            
            # Add final chunk
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
            
            return chunks
        else:
            # Simple character-based splitting
            return [text[i:i + max_size] for i in range(0, len(text), max_size)]
    
    def _split_by_sentences(self, text: str, max_size: int) -> List[str]:
        """
        Split text by sentences.
        
        Args:
            text: Text to split
            max_size: Maximum chunk size
            
        Returns:
            List of chunks
        """
        # Split by sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = []
        current_size = 0
        
        for sentence in sentences:
            sent_len = len(sentence)
            
            # If sentence alone is too large, just add it
            if sent_len > max_size:
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = []
                    current_size = 0
                chunks.append(sentence)
                continue
            
            # If adding sentence exceeds max size, finalize chunk
            if current_chunk and current_size + sent_len + 1 > max_size:
                chunks.append(' '.join(current_chunk))
                current_chunk = [sentence]
                current_size = sent_len
            else:
                current_chunk.append(sentence)
                current_size += sent_len + 1
        
        # Add final chunk
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks
    
    def chunk_with_overlap(
        self,
        text: str,
        chunk_size: int = 4000,
        overlap: int = 200
    ) -> List[TextChunk]:
        """
        Create overlapping chunks using sliding window.
        
        Args:
            text: Text to chunk
            chunk_size: Size of each chunk
            overlap: Number of characters to overlap between chunks
            
        Returns:
            List of overlapping chunks
        """
        if not text or chunk_size <= 0:
            return []
        
        if len(text) <= chunk_size:
            return [TextChunk(text=text, start_index=0, end_index=len(text))]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + chunk_size, len(text))
            
            # Try to end at sentence boundary if possible
            if end < len(text):
                # Look for sentence end in last 100 chars
                last_segment = text[max(start, end - 100):end]
                sentence_end = max(
                    last_segment.rfind('. '),
                    last_segment.rfind('! '),
                    last_segment.rfind('? ')
                )
                if sentence_end > 0:
                    end = max(start, end - 100) + sentence_end + 2
            
            chunk_text = text[start:end]
            chunks.append(TextChunk(
                text=chunk_text,
                start_index=start,
                end_index=end
            ))
            
            # Move start forward by (chunk_size - overlap)
            start += chunk_size - overlap
            
            # Avoid tiny final chunks
            if len(text) - start < overlap:
                break
        
        self.logger.debug(f"Created {len(chunks)} overlapping chunks with {overlap} char overlap")
        return chunks
    
    def get_chunks_as_strings(self, chunks: List[TextChunk]) -> List[str]:
        """
        Convert TextChunk objects to plain strings.
        
        Args:
            chunks: List of TextChunk objects
            
        Returns:
            List of text strings
        """
        return [chunk.text for chunk in chunks]
