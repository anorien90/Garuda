"""Local file source adapter for PDF, text, and media files.

This adapter processes local files of various types, extracting text content
from PDFs, text files, images (via OCR), and audio/video (via transcription).
"""

import hashlib
import os
import mimetypes
from typing import List, Dict, Any, Optional
from io import BytesIO

from .base_adapter import (
    SourceAdapter,
    Document,
    SourceType,
    FetchError,
    NormalizationError,
)


class LocalFileAdapter(SourceAdapter):
    """Adapter for processing local files of various types.
    
    Features:
    - PDF files: Extract text using PyPDF2
    - Text files: Read plain text, markdown, CSV, JSON, XML, HTML, YAML, etc.
    - Image files: Extract text via OCR (pytesseract)
    - Audio/Video files: Transcribe using SpeechRecognition
    - Automatic file type detection
    - Path traversal protection
    - File size validation
    
    Configuration:
        max_file_size_mb: Maximum file size to process (default: 100)
        supported_extensions: Override list of supported extensions (optional)
    """
    
    # Default supported extensions by category
    PDF_EXTENSIONS = [".pdf"]
    TEXT_EXTENSIONS = [
        ".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm",
        ".log", ".rst", ".yaml", ".yml"
    ]
    IMAGE_EXTENSIONS = [
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif"
    ]
    MEDIA_EXTENSIONS = [
        ".mp3", ".wav", ".ogg", ".flac", ".m4a",
        ".mp4", ".avi", ".mov", ".webm", ".mkv"
    ]
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize local file adapter.
        
        Args:
            config: Configuration dict with optional keys:
                - max_file_size_mb (int): Max file size in MB
                - supported_extensions (list): Override supported extensions
        """
        super().__init__(config)
        self.max_file_size = self.config.get("max_file_size_mb", 100) * 1024 * 1024
        
        # Get supported extensions
        if "supported_extensions" in self.config:
            self.supported_extensions = self.config["supported_extensions"]
        else:
            self.supported_extensions = (
                self.PDF_EXTENSIONS + 
                self.TEXT_EXTENSIONS + 
                self.IMAGE_EXTENSIONS + 
                self.MEDIA_EXTENSIONS
            )
        
        # Try to import optional libraries
        self._setup_pdf_support()
        self._setup_ocr_support()
        self._setup_speech_support()
    
    def _setup_pdf_support(self):
        """Setup PDF processing support."""
        try:
            import PyPDF2
            self.PyPDF2 = PyPDF2
            self.has_pdf_support = True
        except ImportError:
            self.PyPDF2 = None
            self.has_pdf_support = False
    
    def _setup_ocr_support(self):
        """Setup OCR support for images."""
        try:
            import pytesseract
            from PIL import Image
            self.pytesseract = pytesseract
            self.PIL_Image = Image
            self.has_ocr_support = True
        except ImportError:
            self.pytesseract = None
            self.PIL_Image = None
            self.has_ocr_support = False
    
    def _setup_speech_support(self):
        """Setup speech recognition support."""
        try:
            import speech_recognition as sr
            self.sr = sr
            self.has_speech_support = True
        except ImportError:
            self.sr = None
            self.has_speech_support = False
    
    @classmethod
    def get_supported_extensions(cls) -> List[str]:
        """Get list of all supported file extensions.
        
        Returns:
            List of supported file extensions (with leading dots)
        """
        return (
            cls.PDF_EXTENSIONS + 
            cls.TEXT_EXTENSIONS + 
            cls.IMAGE_EXTENSIONS + 
            cls.MEDIA_EXTENSIONS
        )
    
    def fetch(self, query: str, **kwargs) -> List[Document]:
        """Fetch and process a local file.
        
        Args:
            query: Local file path
            **kwargs: Additional parameters (currently unused)
            
        Returns:
            List containing single normalized Document
            
        Raises:
            FetchError: If file access or processing fails
        """
        # Check cache first
        cached = self.get_from_cache(query)
        if cached:
            return [cached]
        
        try:
            document = self.process_file(query)
            if not document:
                raise FetchError(f"Failed to process file: {query}")
            
            # Cache the result
            self.add_to_cache(query, document)
            
            return [document]
            
        except Exception as e:
            raise FetchError(f"Failed to fetch file {query}: {str(e)}")
    
    def process_file(self, file_path: str) -> Optional[Document]:
        """Process a single local file.
        
        This is a convenience method that handles the complete pipeline:
        validation, reading, extraction, and normalization.
        
        Args:
            file_path: Path to local file
            
        Returns:
            Normalized Document or None if processing fails
            
        Raises:
            FetchError: If file access or validation fails
        """
        # Validate path
        real_path = self._validate_path(file_path)
        
        # Check file size
        self._validate_file_size(real_path)
        
        # Determine file type
        file_type = self._get_file_type(real_path)
        
        # Extract content based on file type
        content = self._extract_content(real_path, file_type)
        
        # Build metadata
        metadata = self._build_metadata(real_path, file_type)
        
        # Normalize to Document
        document = self.normalize({
            "path": file_path,
            "content": content,
            "file_type": file_type,
            "metadata": metadata
        })
        
        return document
    
    def normalize(self, raw_data: Any) -> Document:
        """Normalize file data into a Document.
        
        Args:
            raw_data: Dict with keys:
                - path: File path
                - content: Extracted text content
                - file_type: File type/extension
                - metadata: File metadata dict
                
        Returns:
            Normalized Document object
            
        Raises:
            NormalizationError: If normalization fails
        """
        try:
            path = raw_data["path"]
            content = raw_data["content"]
            file_type = raw_data["file_type"]
            metadata = raw_data["metadata"]
            
            # Generate document ID
            doc_id = self._generate_id(path)
            
            # Determine source type based on file type
            source_type = self._get_source_type(file_type)
            
            # Calculate confidence based on content quality
            confidence = self._assess_content_quality(content, file_type)
            
            # Use filename as title
            title = os.path.basename(path)
            
            return Document(
                id=doc_id,
                source_type=source_type,
                url=f"file://{os.path.abspath(path)}",
                title=title,
                content=content,
                metadata=metadata,
                confidence=confidence
            )
            
        except Exception as e:
            raise NormalizationError(f"Failed to normalize file data: {str(e)}")
    
    def _validate_path(self, path: str) -> str:
        """Validate file path and prevent path traversal attacks.
        
        Args:
            path: File path to validate
            
        Returns:
            Validated real path
            
        Raises:
            FetchError: If path is invalid or unsafe
        """
        try:
            real_path = os.path.realpath(path)
            
            # Ensure path doesn't contain traversal patterns
            if '..' in path or not os.path.isfile(real_path):
                raise FetchError(f"Invalid file path: {path}")
            
            # Check if file exists
            if not os.path.exists(real_path):
                raise FetchError(f"File not found: {path}")
            
            return real_path
            
        except Exception as e:
            if isinstance(e, FetchError):
                raise
            raise FetchError(f"Invalid file path: {str(e)}")
    
    def _validate_file_size(self, path: str):
        """Validate file size against maximum.
        
        Args:
            path: File path
            
        Raises:
            FetchError: If file is too large
        """
        file_size = os.path.getsize(path)
        if file_size > self.max_file_size:
            raise FetchError(
                f"File too large: {file_size / 1024 / 1024:.1f}MB "
                f"(max: {self.max_file_size / 1024 / 1024:.1f}MB)"
            )
    
    def _get_file_type(self, path: str) -> str:
        """Determine file type from extension.
        
        Args:
            path: File path
            
        Returns:
            File extension (lowercase, with dot)
            
        Raises:
            FetchError: If file type is not supported
        """
        _, ext = os.path.splitext(path)
        ext = ext.lower()
        
        if ext not in self.supported_extensions:
            raise FetchError(
                f"Unsupported file type: {ext}. "
                f"Supported: {', '.join(self.supported_extensions)}"
            )
        
        return ext
    
    def _extract_content(self, path: str, file_type: str) -> str:
        """Extract text content from file based on type.
        
        Args:
            path: File path
            file_type: File extension
            
        Returns:
            Extracted text content
            
        Raises:
            FetchError: If extraction fails
        """
        if file_type in self.PDF_EXTENSIONS:
            return self._extract_pdf_content(path)
        elif file_type in self.TEXT_EXTENSIONS:
            return self._extract_text_content(path)
        elif file_type in self.IMAGE_EXTENSIONS:
            return self._extract_image_content(path)
        elif file_type in self.MEDIA_EXTENSIONS:
            return self._extract_media_content(path)
        else:
            raise FetchError(f"No extraction handler for file type: {file_type}")
    
    def _extract_pdf_content(self, path: str) -> str:
        """Extract text from PDF file.
        
        Args:
            path: PDF file path
            
        Returns:
            Extracted text
            
        Raises:
            FetchError: If PDF processing not available or fails
        """
        if not self.has_pdf_support:
            raise FetchError(
                "PDF processing not available. Install PyPDF2: pip install PyPDF2"
            )
        
        try:
            with open(path, "rb") as f:
                reader = self.PyPDF2.PdfReader(f)
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
                
        except Exception as e:
            raise FetchError(f"Failed to extract PDF content: {str(e)}")
    
    def _extract_text_content(self, path: str) -> str:
        """Extract content from text file.
        
        Args:
            path: Text file path
            
        Returns:
            File content as string
            
        Raises:
            FetchError: If reading fails
        """
        try:
            # Try different encodings
            encodings = ['utf-8', 'utf-16', 'latin-1', 'ascii']
            
            for encoding in encodings:
                try:
                    with open(path, 'r', encoding=encoding) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue
            
            # If all encodings fail, read as binary and decode with errors='ignore'
            with open(path, 'rb') as f:
                return f.read().decode('utf-8', errors='ignore')
                
        except Exception as e:
            raise FetchError(f"Failed to read text file: {str(e)}")
    
    def _extract_image_content(self, path: str) -> str:
        """Extract text from image using OCR.
        
        Args:
            path: Image file path
            
        Returns:
            Extracted text via OCR
            
        Raises:
            FetchError: If OCR not available or fails
        """
        if not self.has_ocr_support:
            return f"[Image file: {os.path.basename(path)}]\nOCR not available. Install pytesseract and Pillow: pip install pytesseract Pillow"
        
        try:
            image = self.PIL_Image.open(path)
            text = self.pytesseract.image_to_string(image)
            
            if not text.strip():
                return f"[Image file: {os.path.basename(path)}]\nNo text detected via OCR"
            
            return f"[Image file: {os.path.basename(path)}]\nOCR extracted text:\n{text}"
            
        except Exception as e:
            return f"[Image file: {os.path.basename(path)}]\nOCR failed: {str(e)}"
    
    def _extract_media_content(self, path: str) -> str:
        """Extract text from audio/video using speech recognition.
        
        Args:
            path: Media file path
            
        Returns:
            Transcribed text
            
        Raises:
            FetchError: If speech recognition not available or fails
        """
        if not self.has_speech_support:
            return f"[Media file: {os.path.basename(path)}]\nSpeech recognition not available. Install SpeechRecognition: pip install SpeechRecognition"
        
        try:
            recognizer = self.sr.Recognizer()
            
            # For audio files, use AudioFile
            if any(path.lower().endswith(ext) for ext in ['.wav', '.mp3', '.ogg', '.flac']):
                with self.sr.AudioFile(path) as source:
                    audio = recognizer.record(source)
                    text = recognizer.recognize_google(audio)
                    return f"[Audio file: {os.path.basename(path)}]\nTranscription:\n{text}"
            else:
                # Video files need audio extraction first
                return f"[Video file: {os.path.basename(path)}]\nVideo transcription requires additional setup (ffmpeg + audio extraction)"
                
        except Exception as e:
            return f"[Media file: {os.path.basename(path)}]\nTranscription failed: {str(e)}"
    
    def _build_metadata(self, path: str, file_type: str) -> Dict[str, Any]:
        """Build metadata dict for file.
        
        Args:
            path: File path
            file_type: File extension
            
        Returns:
            Metadata dictionary
        """
        stat = os.stat(path)
        
        metadata = {
            "file_type": file_type,
            "file_size_bytes": stat.st_size,
            "file_size_mb": round(stat.st_size / 1024 / 1024, 2),
            "created_time": stat.st_ctime,
            "modified_time": stat.st_mtime,
            "absolute_path": os.path.abspath(path),
        }
        
        # Add MIME type
        mime_type, _ = mimetypes.guess_type(path)
        if mime_type:
            metadata["mime_type"] = mime_type
        
        return metadata
    
    def _get_source_type(self, file_type: str) -> SourceType:
        """Determine SourceType based on file extension.
        
        Args:
            file_type: File extension
            
        Returns:
            Appropriate SourceType
        """
        if file_type in self.PDF_EXTENSIONS:
            return SourceType.PDF
        elif file_type in self.TEXT_EXTENSIONS:
            return SourceType.STRUCTURED_DATA
        else:
            # Images and media use LOCAL_FILE
            return SourceType.LOCAL_FILE
    
    def _assess_content_quality(self, content: str, file_type: str) -> float:
        """Assess quality of extracted content.
        
        Args:
            content: Extracted text content
            file_type: File extension
            
        Returns:
            Confidence score (0.0-1.0)
        """
        if not content or len(content.strip()) < 10:
            return 0.3
        
        # Text files have high confidence
        if file_type in self.TEXT_EXTENSIONS:
            return 0.95
        
        # PDF confidence based on text quality
        if file_type in self.PDF_EXTENSIONS:
            total_chars = len(content)
            alpha_chars = sum(c.isalpha() for c in content)
            alpha_ratio = alpha_chars / total_chars if total_chars > 0 else 0
            
            if alpha_ratio < 0.4:
                return 0.5
            elif alpha_ratio > 0.7:
                return 0.9
            else:
                return 0.7
        
        # OCR and transcription have medium confidence
        if file_type in self.IMAGE_EXTENSIONS or file_type in self.MEDIA_EXTENSIONS:
            # Check if extraction was successful (not error message)
            if "not available" in content.lower() or "failed" in content.lower():
                return 0.2
            return 0.6
        
        return 0.5
    
    def _generate_id(self, path: str) -> str:
        """Generate unique ID for file.
        
        Args:
            path: File path
            
        Returns:
            Hash-based unique ID
        """
        # Use absolute path for consistent IDs
        abs_path = os.path.abspath(path)
        return hashlib.sha256(abs_path.encode()).hexdigest()
