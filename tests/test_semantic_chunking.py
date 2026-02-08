"""
Unit tests for semantic chunking.

Tests the SemanticChunker class and text chunking strategies.
"""

import pytest

from garuda_intel.extractor.semantic_chunker import SemanticChunker, TextChunk


class TestTextChunk:
    """Test TextChunk dataclass."""
    
    def test_chunk_creation(self):
        """Test creating a text chunk."""
        chunk = TextChunk(
            text="This is a test chunk",
            start_index=0,
            end_index=20,
            topic_context="Introduction"
        )
        
        assert chunk.text == "This is a test chunk"
        assert chunk.start_index == 0
        assert chunk.end_index == 20
        assert chunk.topic_context == "Introduction"


class TestSemanticChunker:
    """Test SemanticChunker class."""
    
    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker instance."""
        return SemanticChunker()
    
    def test_initialization(self, chunker):
        """Test chunker initialization."""
        assert chunker is not None
        assert chunker.heading_pattern is not None
    
    def test_chunk_small_text(self, chunker):
        """Test chunking text smaller than max size."""
        text = "This is a small text that fits in one chunk."
        
        chunks = chunker.chunk_by_topic(text, max_chunk_size=1000)
        
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].start_index == 0
        assert chunks[0].end_index == len(text)
    
    def test_chunk_by_topic_with_headings(self, chunker):
        """Test topic-based chunking with markdown headings."""
        text = """# Introduction
This is the introduction section with some content.
It has multiple sentences.

# Background
This is the background section.
It contains relevant information.

# Conclusion
This is the conclusion.
"""
        
        chunks = chunker.chunk_by_topic(text, max_chunk_size=200, min_chunk_size=10)
        
        # Should create chunks (may be 1 or more depending on size)
        assert len(chunks) >= 1
        # Check that some content is preserved
        assert any("Introduction" in chunk.text or "Background" in chunk.text for chunk in chunks)
    
    def test_chunk_preserves_paragraphs(self, chunker):
        """Test that chunking preserves paragraph boundaries."""
        text = """First paragraph here.
This is still the first paragraph.

Second paragraph starts here.
Second paragraph continues.

Third paragraph is here.
"""
        
        chunks = chunker.chunk_by_topic(
            text,
            max_chunk_size=100,
            min_chunk_size=10,
            preserve_paragraphs=True
        )
        
        assert len(chunks) >= 1
        # Each chunk should be non-empty
        assert all(len(chunk.text) > 0 for chunk in chunks)
    
    def test_chunk_respects_max_size(self, chunker):
        """Test that chunks don't exceed max size (approximately)."""
        text = "This is a sentence. " * 200  # Long text
        
        max_size = 500
        chunks = chunker.chunk_by_topic(text, max_chunk_size=max_size)
        
        # Most chunks should be around max_size or less
        # (some may be slightly larger due to paragraph preservation)
        for chunk in chunks:
            assert len(chunk.text) <= max_size * 1.2  # Allow 20% overflow
    
    def test_chunk_respects_min_size(self, chunker):
        """Test that chunks respect minimum size."""
        text = """Short para.

Another short para.

Medium length paragraph here.

Yet another.
"""
        
        chunks = chunker.chunk_by_topic(
            text,
            max_chunk_size=200,
            min_chunk_size=30
        )
        
        # All chunks should be >= min_size
        for chunk in chunks:
            assert len(chunk.text.strip()) >= 30 or chunk == chunks[-1]  # Last chunk may be smaller
    
    def test_is_heading_detection(self, chunker):
        """Test heading detection."""
        # Markdown headings
        assert chunker._is_heading("# Main Heading")
        assert chunker._is_heading("## Subheading")
        
        # Colon-ending lines
        assert chunker._is_heading("Section Name:")
        
        # Numbered headings
        assert chunker._is_heading("1. Introduction")
        
        # All caps (short)
        assert chunker._is_heading("IMPORTANT SECTION")
        
        # Not headings
        assert not chunker._is_heading("This is regular text.")
        assert not chunker._is_heading("A very long line that is not a heading because it's too long and contains multiple ideas")
        assert not chunker._is_heading("")
    
    def test_split_by_sections(self, chunker):
        """Test splitting text by sections."""
        text = """# Introduction
Content for introduction.

# Background
Content for background.

Regular paragraph.
"""
        
        sections = chunker._split_by_sections(text)
        
        assert len(sections) >= 2
        # Each section should be a tuple of (heading, content)
        assert all(isinstance(s, tuple) and len(s) == 2 for s in sections)
    
    def test_chunk_with_overlap(self, chunker):
        """Test creating overlapping chunks."""
        text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five. " * 20
        
        chunks = chunker.chunk_with_overlap(
            text,
            chunk_size=200,
            overlap=50
        )
        
        # Should have multiple chunks
        assert len(chunks) > 1
        
        # Check overlap by comparing end of one chunk with start of next
        for i in range(len(chunks) - 1):
            # There should be some content overlap (simplified check)
            assert len(chunks[i].text) > 0
            assert len(chunks[i + 1].text) > 0
    
    def test_chunk_with_overlap_small_text(self, chunker):
        """Test overlapping chunks with small text."""
        text = "Short text here."
        
        chunks = chunker.chunk_with_overlap(text, chunk_size=1000, overlap=100)
        
        # Should return single chunk for small text
        assert len(chunks) == 1
        assert chunks[0].text == text
    
    def test_chunk_with_overlap_respects_chunk_size(self, chunker):
        """Test that overlapping chunks respect size limits."""
        text = "Word " * 500  # Long text
        
        chunk_size = 300
        chunks = chunker.chunk_with_overlap(text, chunk_size=chunk_size, overlap=50)
        
        # Each chunk should be approximately chunk_size
        for chunk in chunks:
            # Allow some variance for sentence boundary detection
            assert len(chunk.text) <= chunk_size * 1.1
    
    def test_get_chunks_as_strings(self, chunker):
        """Test converting chunks to strings."""
        text = "Text " * 100
        
        chunks = chunker.chunk_by_topic(text, max_chunk_size=200)
        strings = chunker.get_chunks_as_strings(chunks)
        
        assert isinstance(strings, list)
        assert all(isinstance(s, str) for s in strings)
        assert len(strings) == len(chunks)
        assert strings[0] == chunks[0].text
    
    def test_split_large_section_by_paragraphs(self, chunker):
        """Test splitting a large section by paragraphs."""
        text = """First paragraph with content.

Second paragraph with more content.

Third paragraph here.

Fourth paragraph continues.
"""
        
        chunks = chunker._split_large_section(
            text,
            max_size=100,
            min_size=20,
            preserve_paragraphs=True
        )
        
        assert len(chunks) >= 2
        assert all(isinstance(c, str) for c in chunks)
    
    def test_split_by_sentences(self, chunker):
        """Test splitting text by sentences."""
        text = "First sentence here. Second sentence follows. Third one too. Fourth sentence."
        
        chunks = chunker._split_by_sentences(text, max_size=40)
        
        # Should split into multiple chunks
        assert len(chunks) >= 2
        assert all(isinstance(c, str) for c in chunks)
        
        # Each chunk should be reasonably sized
        for chunk in chunks:
            assert len(chunk) <= 60  # Allow some overflow
    
    def test_empty_text_handling(self, chunker):
        """Test handling of empty text."""
        chunks = chunker.chunk_by_topic("", max_chunk_size=1000)
        assert chunks == []
        
        chunks = chunker.chunk_with_overlap("", chunk_size=1000, overlap=100)
        assert chunks == []
    
    def test_chunk_maintains_indices(self, chunker):
        """Test that chunk indices are maintained correctly."""
        text = "A" * 1000
        
        chunks = chunker.chunk_by_topic(text, max_chunk_size=200)
        
        # Check that indices make sense
        for i, chunk in enumerate(chunks):
            assert chunk.start_index >= 0
            assert chunk.end_index <= len(text)
            assert chunk.end_index > chunk.start_index
            
            # Indices should be sequential (approximately)
            if i > 0:
                assert chunk.start_index >= chunks[i-1].start_index
    
    def test_unstructured_web_content_chunking(self, chunker):
        """Test chunking of continuous web-scraped text without newlines."""
        # Simulate web-scraped content - one continuous block
        text = (
            "Microsoft Headquarters Address Skip to content "
            "Microsoft Headquarters Address If you are looking for the official "
            "Microsoft headquarters location or want to speak with someone at "
            "the company's main office, you'll find everything you need below. "
            "The official Microsoft headquarters address is 15010 NE 36th Street, "
            "Redmond, WA 98052, USA. This location serves as the global headquarters "
            "of Microsoft Corporation, one of the largest and most influential "
            "technology companies in the world. The Redmond campus is the central hub "
            "for Microsoft's executive leadership, innovation departments, strategic "
            "operations, and major corporate decisions. If you need to contact "
            "Microsoft headquarters by phone, your call will be routed through their "
            "main office support center during standard business hours, Monday "
            "through Friday. This is the best way to reach out for corporate "
            "inquiries, investor relations, partnership opportunities, media requests, "
            "and other official business matters. "
            "Microsoft Headquarters Phone Number Microsoft headquarters phone number "
            "is 425-882-8080. You can communicate directly with Microsoft headquarters. "
            "If you're looking to speak directly with Microsoft's corporate office, "
            "the official Microsoft headquarters phone number is 425-882-8080. "
            "This is the primary contact number for Microsoft's global headquarters "
            "located in Redmond, Washington."
        )
        
        chunks = chunker.chunk_by_topic(text, max_chunk_size=1500, min_chunk_size=100)
        
        # Should produce multiple chunks, not just 1
        assert len(chunks) >= 2, f"Expected multiple chunks but got {len(chunks)}"
        
        # No chunk should be excessively large
        for chunk in chunks:
            assert len(chunk.text) <= 1500 * 1.2, (
                f"Chunk too large: {len(chunk.text)} chars"
            )

    def test_heading_detection_not_too_aggressive(self, chunker):
        """Test that heading detection doesn't match sentences ending with colons."""
        # These should NOT be detected as headings
        assert not chunker._is_heading(
            "The official Microsoft headquarters address is as follows:"
        )
        assert not chunker._is_heading(
            "If you are looking for the official Microsoft headquarters location:"
        )
        
        # These SHOULD still be detected as headings
        assert chunker._is_heading("Contact Information:")
        assert chunker._is_heading("Phone Number:")
        assert chunker._is_heading("# Main Heading")
        assert chunker._is_heading("COMPANY ADDRESS")

    def test_small_chunks_not_dropped(self, chunker):
        """Test that reasonably small chunks are not dropped."""
        text = "First section content here. " * 10 + "\n\n" + "Second section. " * 5
        
        chunks = chunker.chunk_by_topic(
            text, max_chunk_size=300, min_chunk_size=50
        )
        
        # Small but meaningful chunks should be preserved
        assert len(chunks) >= 1
        for chunk in chunks:
            assert len(chunk.text.strip()) >= 50 or chunk == chunks[-1]
    
    def test_topic_context_preserved(self, chunker):
        """Test that topic context is preserved in chunks."""
        text = """# Technology Section
This section discusses technology.
It has multiple paragraphs.

# Business Section
This section covers business topics.
""" * 5  # Repeat to make it larger
        
        chunks = chunker.chunk_by_topic(text, max_chunk_size=300, min_chunk_size=50)
        
        # Check that chunks were created
        assert len(chunks) >= 1
        
        # At least check that content is properly chunked
        combined_text = " ".join([c.text for c in chunks])
        assert "Technology" in combined_text or "Business" in combined_text
    
    def test_large_text_performance(self, chunker):
        """Test chunking performance with large text."""
        # Generate large text
        text = "This is a test sentence. " * 10000  # ~250KB
        
        # Should complete in reasonable time
        chunks = chunker.chunk_by_topic(text, max_chunk_size=4000)
        
        assert len(chunks) > 0
        assert len(chunks) < 500  # Should create reasonable number of chunks
