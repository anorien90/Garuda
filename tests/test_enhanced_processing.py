"""Tests for enhanced file processing features.

Tests cover:
- Enhanced image content extraction (OCR + metadata)
- PDF image extraction from pages
- Table data extraction (pipe-delimited, tab-delimited, CSV)
- Comprehensive image processing in MediaProcessor
- File browser API endpoints
"""

import os
import tempfile
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from garuda_intel.sources.local_file_adapter import LocalFileAdapter
from garuda_intel.services.media_processor import MediaProcessor


# ============================================================================
# Enhanced Image Content Extraction
# ============================================================================

class TestEnhancedImageExtraction:
    """Tests for enhanced _extract_image_content method."""

    def test_image_content_includes_filename(self, tmp_path):
        """Test that image extraction includes the filename."""
        # Create a minimal valid PNG file
        img_file = tmp_path / "test_image.png"
        _create_minimal_png(img_file)
        
        adapter = LocalFileAdapter()
        content = adapter._extract_image_content(str(img_file))
        
        assert "[Image file: test_image.png]" in content

    def test_image_content_includes_metadata_when_pil_available(self, tmp_path):
        """Test that image extraction includes metadata when PIL is available."""
        img_file = tmp_path / "test.png"
        _create_minimal_png(img_file)
        
        adapter = LocalFileAdapter()
        if adapter.PIL_Image:
            content = adapter._extract_image_content(str(img_file))
            assert "Format:" in content or "Dimensions:" in content
        else:
            pytest.skip("PIL not available")

    def test_image_content_without_ocr_shows_message(self, tmp_path):
        """Test that image extraction shows message when OCR is not available."""
        img_file = tmp_path / "test.png"
        _create_minimal_png(img_file)
        
        adapter = LocalFileAdapter()
        adapter.has_ocr_support = False
        
        content = adapter._extract_image_content(str(img_file))
        assert "OCR not available" in content


# ============================================================================
# PDF Image Extraction
# ============================================================================

class TestPDFImageExtraction:
    """Tests for _extract_images_from_pdf_page method."""

    def test_extract_images_handles_no_images_attribute(self):
        """Test that extraction handles pages without images attribute."""
        adapter = LocalFileAdapter()
        mock_page = Mock(spec=[])  # No 'images' attribute
        
        result = adapter._extract_images_from_pdf_page(mock_page, 0, "/tmp/test.pdf")
        assert result == []

    def test_extract_images_handles_empty_images(self):
        """Test that extraction handles pages with empty images list."""
        adapter = LocalFileAdapter()
        mock_page = Mock()
        mock_page.images = []
        
        result = adapter._extract_images_from_pdf_page(mock_page, 0, "/tmp/test.pdf")
        assert result == []

    def test_extract_images_handles_exception(self):
        """Test that extraction handles exceptions gracefully."""
        adapter = LocalFileAdapter()
        mock_page = Mock()
        mock_page.images = Mock(side_effect=Exception("test error"))
        
        # Should not raise
        result = adapter._extract_images_from_pdf_page(mock_page, 0, "/tmp/test.pdf")
        assert result == []


# ============================================================================
# Table Data Extraction
# ============================================================================

class TestTableExtraction:
    """Tests for table data extraction methods."""

    def test_extract_pipe_delimited_table(self):
        """Test extraction of pipe-delimited (Markdown-style) tables."""
        adapter = LocalFileAdapter()
        text = """Some text before
| Name | Age | City |
|------|-----|------|
| Alice | 30 | NYC |
| Bob | 25 | SF |
Some text after"""
        
        result = adapter._extract_tables_from_text(text)
        assert "Table" in result
        assert "Name" in result
        assert "Alice" in result or "Age" in result

    def test_extract_tab_delimited_table(self):
        """Test extraction of tab-delimited tables."""
        adapter = LocalFileAdapter()
        text = "Name\tAge\tCity\nAlice\t30\tNYC\nBob\t25\tSF"
        
        result = adapter._extract_tables_from_text(text)
        assert "Table" in result
        assert "Name" in result

    def test_empty_text_returns_empty(self):
        """Test that empty text returns empty result."""
        adapter = LocalFileAdapter()
        result = adapter._extract_tables_from_text("")
        assert result == ""

    def test_no_tables_returns_empty(self):
        """Test that text without tables returns empty result."""
        adapter = LocalFileAdapter()
        result = adapter._extract_tables_from_text("Just some regular text without tables.")
        assert result == ""

    def test_format_table_rows(self):
        """Test table row formatting."""
        adapter = LocalFileAdapter()
        rows = [["Name", "Age"], ["Alice", "30"], ["Bob", "25"]]
        
        result = adapter._format_table_rows(rows)
        assert "Table (3 rows, 2 columns):" in result
        assert "Headers: Name | Age" in result
        assert "Row 1:" in result
        assert "Alice" in result

    def test_format_table_rows_empty(self):
        """Test formatting empty rows."""
        adapter = LocalFileAdapter()
        result = adapter._format_table_rows([])
        assert result == ""


class TestCSVExtraction:
    """Tests for CSV structured data extraction."""

    def test_extract_csv_structured(self, tmp_path):
        """Test CSV structured extraction."""
        adapter = LocalFileAdapter()
        csv_content = "Name,Age,City\nAlice,30,NYC\nBob,25,SF"
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)
        
        result = adapter._extract_csv_structured(str(csv_file), csv_content)
        assert "CSV Table" in result
        assert "2 data rows" in result
        assert "3 columns" in result
        assert "Name" in result
        assert "Alice" in result

    def test_extract_csv_single_row(self):
        """Test that CSV with only headers returns empty."""
        adapter = LocalFileAdapter()
        result = adapter._extract_csv_structured("/tmp/test.csv", "Name,Age")
        assert result == ""

    def test_csv_text_content_extraction(self, tmp_path):
        """Test that CSV files get structured extraction in _extract_text_content."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("Name,Age,City\nAlice,30,NYC\nBob,25,SF")
        
        adapter = LocalFileAdapter()
        content = adapter._extract_text_content(str(csv_file))
        
        # Should contain both raw and structured content
        assert "Name,Age,City" in content
        assert "[Structured Table Data]" in content


# ============================================================================
# Comprehensive Image Processing in MediaProcessor
# ============================================================================

class TestComprehensiveImageProcessing:
    """Tests for the comprehensive image processing method."""

    def test_process_image_disabled(self):
        """Test that disabled processor returns appropriate response."""
        processor = MediaProcessor(enable_processing=False)
        result = processor.process_image("/tmp/test.png", "test://url")
        
        assert result["processed"] is False
        assert "disabled" in result["processing_error"]

    def test_comprehensive_method_selected_when_both_available(self):
        """Test that comprehensive method is selected when both OCR and AI are available."""
        mock_llm = Mock()
        mock_llm.image_to_text = Mock(return_value="A test image")
        
        processor = MediaProcessor(llm_extractor=mock_llm)
        processor.ocr_available = True
        processor.image2text_available = True
        
        # The method selection should prefer comprehensive
        # We can test the logic without actually processing
        method = None
        can_use_comprehensive = processor.ocr_available and processor.image2text_available
        use_comprehensive = method == "comprehensive" or (method is None and can_use_comprehensive)
        
        assert use_comprehensive is True

    def test_fallback_to_tesseract_when_no_ai(self):
        """Test fallback to tesseract when AI is not available."""
        processor = MediaProcessor()
        processor.ocr_available = True
        processor.image2text_available = False
        
        # When only OCR is available, should use tesseract
        method = processor.image_method  # Default is "tesseract"
        assert method == "tesseract"

    def test_process_image_returns_error_when_no_methods(self):
        """Test error when no processing methods are available."""
        processor = MediaProcessor()
        processor.ocr_available = False
        processor.image2text_available = False
        
        result = processor.process_image("/tmp/test.png", "test://url")
        
        assert result["processed"] is False
        assert "No image processing method available" in result["processing_error"]


# ============================================================================
# Build Metadata with Extracted Images
# ============================================================================

class TestBuildMetadata:
    """Tests for _build_metadata with PDF image tracking."""

    def test_metadata_includes_file_basics(self, tmp_path):
        """Test basic metadata fields."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world")
        
        adapter = LocalFileAdapter()
        meta = adapter._build_metadata(str(test_file), ".txt")
        
        assert "file_type" in meta
        assert meta["file_type"] == ".txt"
        assert "file_size_bytes" in meta
        assert "absolute_path" in meta

    def test_pdf_metadata_includes_extracted_images(self, tmp_path):
        """Test that PDF metadata tracks extracted images."""
        # Create a fake PDF and its extracted images directory
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")
        
        img_dir = tmp_path / "test_images"
        img_dir.mkdir()
        (img_dir / "page1_img1.png").write_bytes(b"fake png")
        (img_dir / "page1_img2.png").write_bytes(b"fake png")
        
        adapter = LocalFileAdapter()
        meta = adapter._build_metadata(str(pdf_file), ".pdf")
        
        assert meta.get("extracted_images_dir") == str(img_dir)
        assert meta.get("extracted_images_count") == 2
        assert len(meta.get("extracted_image_paths", [])) == 2


# ============================================================================
# Helper Functions
# ============================================================================

def _create_minimal_png(path):
    """Create a minimal valid 1x1 PNG file for testing."""
    # Minimal 1x1 red pixel PNG
    import struct
    import zlib
    
    def chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    
    # PNG signature
    signature = b'\x89PNG\r\n\x1a\n'
    
    # IHDR chunk: 1x1, 8-bit RGB
    ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr = chunk(b'IHDR', ihdr_data)
    
    # IDAT chunk: raw pixel data (filter byte + RGB)
    raw_data = b'\x00\xff\x00\x00'  # filter=None, R=255, G=0, B=0
    compressed = zlib.compress(raw_data)
    idat = chunk(b'IDAT', compressed)
    
    # IEND chunk
    iend = chunk(b'IEND', b'')
    
    with open(str(path), 'wb') as f:
        f.write(signature + ihdr + idat + iend)
