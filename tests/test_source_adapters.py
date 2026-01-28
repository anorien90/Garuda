"""Tests for multi-source adapters."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from io import BytesIO

from garuda_intel.sources.base_adapter import (
    SourceAdapter,
    Document,
    SourceType,
    SourceAdapterError,
    NormalizationError,
)
from garuda_intel.sources.pdf_adapter import PDFAdapter
from garuda_intel.sources.api_adapter import APIAdapter, APIType


class TestBaseAdapter:
    """Tests for SourceAdapter base class."""
    
    def test_document_creation(self):
        """Test Document dataclass creation."""
        doc = Document(
            id="test-123",
            source_type=SourceType.PDF,
            url="http://example.com/doc.pdf",
            title="Test Document",
            content="Test content",
            metadata={"author": "Test Author"},
            confidence=0.9
        )
        
        assert doc.id == "test-123"
        assert doc.source_type == SourceType.PDF
        assert doc.title == "Test Document"
        assert doc.confidence == 0.9
        assert isinstance(doc.timestamp, datetime)
    
    def test_validate_document(self):
        """Test document validation."""
        adapter = Mock(spec=SourceAdapter)
        adapter.validate = SourceAdapter.validate.__get__(adapter)
        
        # Valid document
        valid_doc = Document(
            id="1", source_type=SourceType.PDF, url="test.pdf",
            title="Test", content="This is valid content",
            metadata={}, confidence=0.8
        )
        assert adapter.validate(valid_doc) is True
        
        # Invalid: low confidence
        low_conf = Document(
            id="2", source_type=SourceType.PDF, url="test.pdf",
            title="Test", content="Content", metadata={}, confidence=0.2
        )
        assert adapter.validate(low_conf) is False
        
        # Invalid: empty content
        empty = Document(
            id="3", source_type=SourceType.PDF, url="test.pdf",
            title="Test", content="", metadata={}, confidence=0.8
        )
        assert adapter.validate(empty) is False
    
    def test_cache_operations(self):
        """Test adapter caching."""
        adapter = Mock(spec=SourceAdapter)
        adapter._cache = {}
        adapter.get_from_cache = SourceAdapter.get_from_cache.__get__(adapter)
        adapter.add_to_cache = SourceAdapter.add_to_cache.__get__(adapter)
        adapter.clear_cache = SourceAdapter.clear_cache.__get__(adapter)
        
        doc = Document(
            id="1", source_type=SourceType.PDF, url="test.pdf",
            title="Test", content="Content", metadata={}, confidence=0.8
        )
        
        # Initially empty
        assert adapter.get_from_cache("key1") is None
        
        # Add to cache
        adapter.add_to_cache("key1", doc)
        assert adapter.get_from_cache("key1") == doc
        
        # Clear cache
        adapter.clear_cache()
        assert adapter.get_from_cache("key1") is None


class TestPDFAdapter:
    """Tests for PDF adapter."""
    
    @pytest.fixture
    def pdf_adapter(self):
        """Create PDF adapter instance."""
        mock_pypdf = Mock()
        with patch.object(PDFAdapter, '__init__', lambda self, config: (
            setattr(self, 'config', config or {}),
            setattr(self, 'max_file_size', config.get("max_file_size_mb", 50) * 1024 * 1024),
            setattr(self, 'timeout', config.get("timeout_seconds", 30)),
            setattr(self, 'extract_images', config.get("extract_images", False)),
            setattr(self, 'PyPDF2', mock_pypdf),
            setattr(self, '_cache', {})
        )[-1]):
            adapter = PDFAdapter({"max_file_size_mb": 10})
            # Restore the real methods
            adapter._generate_id = PDFAdapter._generate_id.__get__(adapter, PDFAdapter)
            adapter._assess_text_quality = PDFAdapter._assess_text_quality.__get__(adapter, PDFAdapter)
            adapter._extract_metadata = PDFAdapter._extract_metadata.__get__(adapter, PDFAdapter)
            adapter._download_pdf = PDFAdapter._download_pdf.__get__(adapter, PDFAdapter)
            return adapter
    
    def test_initialization(self, pdf_adapter):
        """Test PDF adapter initialization."""
        assert pdf_adapter.max_file_size == 10 * 1024 * 1024
        assert pdf_adapter.timeout == 30  # default
    
    def test_generate_id(self, pdf_adapter):
        """Test ID generation."""
        url1 = "http://example.com/doc.pdf"
        url2 = "http://example.com/doc.pdf"
        url3 = "http://example.com/other.pdf"
        
        id1 = pdf_adapter._generate_id(url1)
        id2 = pdf_adapter._generate_id(url2)
        id3 = pdf_adapter._generate_id(url3)
        
        assert id1 == id2  # Same URL = same ID
        assert id1 != id3  # Different URL = different ID
    
    def test_assess_text_quality(self, pdf_adapter):
        """Test text quality assessment."""
        # Good text (long enough)
        good_text = "This is a well-formatted document with proper text content. " * 5
        assert pdf_adapter._assess_text_quality(good_text) > 0.7
        
        # Poor text (too short)
        short_text = "abc"
        assert pdf_adapter._assess_text_quality(short_text) == 0.3
        
        # Noisy text (low letter ratio)
        noisy_text = "###@@@$$$%%%^^^" * 20
        assert pdf_adapter._assess_text_quality(noisy_text) < 0.7
    
    @patch('garuda_intel.sources.pdf_adapter.requests.get')
    def test_download_pdf_success(self, mock_get, pdf_adapter):
        """Test successful PDF download."""
        # Mock successful response
        mock_response = Mock()
        mock_response.content = b"PDF content"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = pdf_adapter._download_pdf("http://example.com/doc.pdf")
        
        assert isinstance(result, BytesIO)
        assert result.read() == b"PDF content"
    
    @patch('garuda_intel.sources.pdf_adapter.requests.get')
    def test_download_pdf_too_large(self, mock_get, pdf_adapter):
        """Test PDF download with file too large."""
        # Mock response with large content
        mock_response = Mock()
        mock_response.content = b"x" * (20 * 1024 * 1024)  # 20MB
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        from garuda_intel.sources.base_adapter import FetchError
        with pytest.raises(FetchError, match="too large"):
            pdf_adapter._download_pdf("http://example.com/large.pdf")
    
    def test_extract_metadata(self, pdf_adapter):
        """Test metadata extraction."""
        mock_reader = Mock()
        mock_reader.pages = [Mock(), Mock()]  # 2 pages
        mock_reader.is_encrypted = False
        mock_reader.metadata = {
            "/Title": "Test Document",
            "/Author": "Test Author"
        }
        
        metadata = pdf_adapter._extract_metadata(mock_reader)
        
        assert metadata["pages"] == 2
        assert metadata["encrypted"] is False
        assert metadata["title"] == "Test Document"
        assert metadata["author"] == "Test Author"


class TestAPIAdapter:
    """Tests for API adapter."""
    
    @pytest.fixture
    def rest_adapter(self):
        """Create REST API adapter."""
        return APIAdapter({
            "api_type": "rest",
            "base_url": "https://api.example.com",
            "timeout_seconds": 10
        })
    
    @pytest.fixture
    def graphql_adapter(self):
        """Create GraphQL API adapter."""
        return APIAdapter({
            "api_type": "graphql",
            "base_url": "https://api.example.com/graphql",
            "auth_token": "test-token"
        })
    
    def test_rest_initialization(self, rest_adapter):
        """Test REST adapter initialization."""
        assert rest_adapter.api_type == APIType.REST
        assert rest_adapter.base_url == "https://api.example.com"
        assert rest_adapter.timeout == 10
    
    def test_graphql_initialization(self, graphql_adapter):
        """Test GraphQL adapter initialization."""
        assert graphql_adapter.api_type == APIType.GRAPHQL
        assert "Authorization" in graphql_adapter.headers
        assert graphql_adapter.headers["Authorization"] == "Bearer test-token"
    
    def test_build_url(self, rest_adapter):
        """Test URL building."""
        # Relative endpoint
        url1 = rest_adapter._build_url("/users")
        assert url1 == "https://api.example.com/users"
        
        # Absolute URL
        url2 = rest_adapter._build_url("https://other.com/api")
        assert url2 == "https://other.com/api"
    
    def test_extract_title(self, rest_adapter):
        """Test title extraction from data."""
        # Dict with title field
        data1 = {"title": "My Title", "content": "..."}
        title1 = rest_adapter._extract_title(data1, "query")
        assert title1 == "My Title"
        
        # Dict with name field
        data2 = {"name": "Entity Name", "content": "..."}
        title2 = rest_adapter._extract_title(data2, "query")
        assert title2 == "Entity Name"
        
        # Single key dict
        data3 = {"users": [...]}
        title3 = rest_adapter._extract_title(data3, "query")
        assert title3 == "users"
    
    @patch('garuda_intel.sources.api_adapter.requests.get')
    def test_fetch_rest_success(self, mock_get, rest_adapter):
        """Test successful REST API fetch."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = rest_adapter._fetch_rest("/endpoint", params={"q": "test"})
        
        assert result == {"data": "test"}
        mock_get.assert_called_once()
    
    @patch('garuda_intel.sources.api_adapter.requests.post')
    def test_fetch_graphql_success(self, mock_post, graphql_adapter):
        """Test successful GraphQL fetch."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {"users": [{"name": "Test"}]}
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        query = "query { users { name } }"
        result = graphql_adapter._fetch_graphql(query)
        
        assert result == {"users": [{"name": "Test"}]}
        mock_post.assert_called_once()
    
    @patch('garuda_intel.sources.api_adapter.requests.post')
    def test_fetch_graphql_with_errors(self, mock_post, graphql_adapter):
        """Test GraphQL fetch with errors."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "errors": [{"message": "Field not found"}]
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        from garuda_intel.sources.base_adapter import FetchError
        with pytest.raises(FetchError, match="GraphQL errors"):
            graphql_adapter._fetch_graphql("query { invalid }")
    
    def test_normalize(self, rest_adapter):
        """Test response normalization."""
        raw_data = {
            "data": {"users": [{"name": "Alice"}, {"name": "Bob"}]},
            "query": "/users",
            "url": "https://api.example.com/users"
        }
        
        doc = rest_adapter.normalize(raw_data)
        
        assert doc.source_type == SourceType.API
        assert doc.url == "https://api.example.com/users"
        assert "Alice" in doc.content
        assert doc.confidence == 0.9
        assert "api_type" in doc.metadata
