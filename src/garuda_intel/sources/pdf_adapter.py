"""PDF source adapter for research papers and reports.

This adapter fetches and processes PDF documents, extracting text content
and metadata for intelligence gathering.
"""

import hashlib
import os
import tempfile
from typing import List, Dict, Any, Optional
from io import BytesIO
import requests

from .base_adapter import (
    SourceAdapter,
    Document,
    SourceType,
    FetchError,
    NormalizationError,
)


class PDFAdapter(SourceAdapter):
    """Adapter for fetching and processing PDF documents.
    
    Features:
    - Download PDFs from URLs
    - Extract text content using PyPDF2
    - Extract metadata (title, author, creation date)
    - Support for local PDF files
    - Automatic text quality assessment
    
    Configuration:
        max_file_size_mb: Maximum PDF file size to process (default: 50)
        timeout_seconds: Download timeout (default: 30)
        extract_images: Whether to attempt image extraction (default: False)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize PDF adapter.
        
        Args:
            config: Configuration dict with optional keys:
                - max_file_size_mb (int): Max file size
                - timeout_seconds (int): Download timeout
                - extract_images (bool): Extract images from PDF
        """
        super().__init__(config)
        self.max_file_size = self.config.get("max_file_size_mb", 50) * 1024 * 1024
        self.timeout = self.config.get("timeout_seconds", 30)
        self.extract_images = self.config.get("extract_images", False)
        
        # Try to import PDF library
        try:
            import PyPDF2
            self.PyPDF2 = PyPDF2
        except ImportError:
            raise ImportError(
                "PyPDF2 is required for PDF processing. "
                "Install it with: pip install PyPDF2"
            )
    
    def fetch(self, query: str, **kwargs) -> List[Document]:
        """Fetch PDF document(s) from URL or local path.
        
        Args:
            query: PDF URL or local file path
            **kwargs: Additional parameters (currently unused)
            
        Returns:
            List containing single normalized Document
            
        Raises:
            FetchError: If download or file access fails
        """
        # Check cache first
        cached = self.get_from_cache(query)
        if cached:
            return [cached]
        
        try:
            if query.startswith(("http://", "https://")):
                pdf_data = self._download_pdf(query)
                source_id = self._generate_id(query)
            else:
                # Local file path
                pdf_data = self._read_local_pdf(query)
                source_id = self._generate_id(query)
            
            # Normalize the PDF data
            document = self.normalize({
                "data": pdf_data,
                "url": query,
                "id": source_id
            })
            
            # Cache the result
            self.add_to_cache(query, document)
            
            return [document]
            
        except Exception as e:
            raise FetchError(f"Failed to fetch PDF from {query}: {str(e)}")
    
    def normalize(self, raw_data: Any) -> Document:
        """Extract text and metadata from PDF data.
        
        Args:
            raw_data: Dict with keys:
                - data: PDF binary data (BytesIO or bytes)
                - url: Source URL or path
                - id: Document ID
                
        Returns:
            Normalized Document object
            
        Raises:
            NormalizationError: If PDF parsing fails
        """
        try:
            pdf_data = raw_data["data"]
            url = raw_data["url"]
            doc_id = raw_data["id"]
            
            if isinstance(pdf_data, bytes):
                pdf_data = BytesIO(pdf_data)
            
            # Parse PDF
            reader = self.PyPDF2.PdfReader(pdf_data)
            
            # Extract metadata
            metadata = self._extract_metadata(reader)
            
            # Extract text from all pages
            text_content = self._extract_text(reader)
            
            # Calculate confidence based on text quality
            confidence = self._assess_text_quality(text_content)
            
            # Get title from metadata or filename
            title = metadata.get("title")
            if not title:
                title = os.path.basename(url) if "/" in url else url
            
            return Document(
                id=doc_id,
                source_type=SourceType.PDF,
                url=url,
                title=title,
                content=text_content,
                metadata=metadata,
                confidence=confidence
            )
            
        except Exception as e:
            raise NormalizationError(f"Failed to normalize PDF: {str(e)}")
    
    def _download_pdf(self, url: str) -> BytesIO:
        """Download PDF from URL.
        
        Args:
            url: PDF URL
            
        Returns:
            BytesIO with PDF data
            
        Raises:
            FetchError: If download fails
        """
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": "Garuda-Intel/1.0"}
            )
            response.raise_for_status()
            
            # Check file size
            content_length = len(response.content)
            if content_length > self.max_file_size:
                raise FetchError(
                    f"PDF too large: {content_length / 1024 / 1024:.1f}MB "
                    f"(max: {self.max_file_size / 1024 / 1024:.1f}MB)"
                )
            
            return BytesIO(response.content)
            
        except requests.RequestException as e:
            raise FetchError(f"Failed to download PDF: {str(e)}")
    
    def _read_local_pdf(self, path: str) -> BytesIO:
        """Read PDF from local file.
        
        Args:
            path: Local file path
            
        Returns:
            BytesIO with PDF data
            
        Raises:
            FetchError: If file read fails
        """
        try:
            # Check file size
            file_size = os.path.getsize(path)
            if file_size > self.max_file_size:
                raise FetchError(
                    f"PDF too large: {file_size / 1024 / 1024:.1f}MB "
                    f"(max: {self.max_file_size / 1024 / 1024:.1f}MB)"
                )
            
            with open(path, "rb") as f:
                return BytesIO(f.read())
                
        except Exception as e:
            raise FetchError(f"Failed to read local PDF: {str(e)}")
    
    def _extract_metadata(self, reader) -> Dict[str, Any]:
        """Extract metadata from PDF.
        
        Args:
            reader: PyPDF2 PdfReader object
            
        Returns:
            Dict with metadata fields
        """
        metadata = {
            "pages": len(reader.pages),
            "encrypted": reader.is_encrypted
        }
        
        # Extract document info if available
        if reader.metadata:
            info = reader.metadata
            if "/Title" in info:
                metadata["title"] = str(info["/Title"])
            if "/Author" in info:
                metadata["author"] = str(info["/Author"])
            if "/Subject" in info:
                metadata["subject"] = str(info["/Subject"])
            if "/Creator" in info:
                metadata["creator"] = str(info["/Creator"])
            if "/CreationDate" in info:
                metadata["creation_date"] = str(info["/CreationDate"])
        
        return metadata
    
    def _extract_text(self, reader) -> str:
        """Extract text from all PDF pages.
        
        Args:
            reader: PyPDF2 PdfReader object
            
        Returns:
            Concatenated text from all pages
        """
        text_parts = []
        
        for page_num, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
                if text:
                    text_parts.append(f"[Page {page_num + 1}]\n{text}\n")
            except Exception:
                # Skip pages that fail to extract
                continue
        
        return "\n".join(text_parts)
    
    def _assess_text_quality(self, text: str) -> float:
        """Assess quality of extracted text.
        
        Args:
            text: Extracted text
            
        Returns:
            Confidence score (0.0-1.0)
        """
        if not text or len(text.strip()) < 100:
            return 0.3
        
        # Calculate metrics
        total_chars = len(text)
        alpha_chars = sum(c.isalpha() for c in text)
        space_chars = sum(c.isspace() for c in text)
        
        # Good text should have reasonable ratio of letters to total chars
        alpha_ratio = alpha_chars / total_chars if total_chars > 0 else 0
        space_ratio = space_chars / total_chars if total_chars > 0 else 0
        
        # Score based on ratios
        if alpha_ratio < 0.4:  # Too few letters (likely OCR noise)
            return 0.5
        elif alpha_ratio > 0.7 and space_ratio > 0.1:  # Good text
            return 0.95
        else:  # Acceptable text
            return 0.75
    
    def _generate_id(self, url: str) -> str:
        """Generate unique ID for document.
        
        Args:
            url: Document URL or path
            
        Returns:
            Hash-based unique ID
        """
        return hashlib.md5(url.encode()).hexdigest()
