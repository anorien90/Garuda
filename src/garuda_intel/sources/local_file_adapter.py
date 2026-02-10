"""Local file source adapter for PDF, text, and media files.

This adapter processes local files of various types, extracting text content
from PDFs, text files, images (via OCR), and audio/video (via transcription).
"""

import hashlib
import logging
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

logger = logging.getLogger(__name__)


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
        ".log", ".rst", ".yaml", ".yml", ".py", ".ini", ".cfg", ".toml",
        ".sh", ".bat", ".ps1", ".sql", ".r", ".rb", ".js", ".ts", ".css"
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
        """Extract text and images from PDF file.
        
        Extracts text from all pages and attempts to extract embedded images.
        Extracted images are saved to a subdirectory alongside the PDF for
        further processing by the pipeline.
        
        Args:
            path: PDF file path
            
        Returns:
            Extracted text including image references
            
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
                extracted_images = []
                
                for page_num, page in enumerate(reader.pages):
                    # Extract text from every page - never skip
                    try:
                        text = page.extract_text()
                        if text:
                            text_parts.append(f"[Page {page_num + 1}]\n{text}\n")
                    except Exception as e:
                        logger.debug(f"Text extraction failed for page {page_num + 1}: {e}")
                        text_parts.append(f"[Page {page_num + 1}]\n[Text extraction failed: {type(e).__name__}]\n")
                    
                    # Extract embedded images from this page
                    try:
                        images = self._extract_images_from_pdf_page(
                            page, page_num, path
                        )
                        if images:
                            extracted_images.extend(images)
                            for img_info in images:
                                text_parts.append(
                                    f"[Embedded Image: {img_info['filename']} "
                                    f"from Page {page_num + 1} - "
                                    f"{img_info.get('width', '?')}x{img_info.get('height', '?')}]"
                                )
                                if img_info.get("ocr_text"):
                                    text_parts.append(f"Image OCR: {img_info['ocr_text']}")
                    except Exception as e:
                        # Don't fail the whole PDF if image extraction fails
                        logger.debug(f"Failed to extract images from page {page_num + 1}: {e}")
                
                # Extract table data from pages
                try:
                    table_content = self._extract_tables_from_text(
                        "\n".join(text_parts)
                    )
                    if table_content:
                        text_parts.append(f"\n[Extracted Table Data]\n{table_content}")
                except Exception as e:
                    logger.debug(f"Failed to extract tables from PDF: {e}")
                
                # Store extracted image paths in metadata for pipeline processing
                if extracted_images:
                    text_parts.append(
                        f"\n[PDF contains {len(extracted_images)} embedded image(s)]"
                    )
                
                return "\n".join(text_parts)
                
        except Exception as e:
            raise FetchError(f"Failed to extract PDF content: {str(e)}")
    
    def _extract_images_from_pdf_page(
        self, page, page_num: int, pdf_path: str
    ) -> list:
        """Extract embedded images from a PDF page.
        
        Saves extracted images to a subdirectory next to the PDF file.
        Optionally performs OCR on extracted images.
        
        Args:
            page: PyPDF2 page object
            page_num: Page number (0-indexed)
            pdf_path: Path to the source PDF file
            
        Returns:
            List of dicts with image info (filename, path, dimensions, ocr_text)
        """
        extracted = []
        
        if not hasattr(page, 'images'):
            return extracted
        
        # Create output directory for extracted images
        pdf_dir = os.path.dirname(os.path.abspath(pdf_path))
        pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]
        img_dir = os.path.join(pdf_dir, f"{pdf_basename}_images")
        
        try:
            for img_idx, image in enumerate(page.images):
                try:
                    img_filename = f"page{page_num + 1}_img{img_idx + 1}"
                    # Determine extension from image name or default to png
                    if hasattr(image, 'name') and '.' in image.name:
                        ext = os.path.splitext(image.name)[1]
                        img_filename += ext
                    else:
                        img_filename += ".png"
                    
                    os.makedirs(img_dir, exist_ok=True)
                    img_path = os.path.join(img_dir, img_filename)
                    
                    # Save the image data
                    with open(img_path, "wb") as img_file:
                        img_file.write(image.data)
                    
                    img_info = {
                        "filename": img_filename,
                        "path": img_path,
                        "page_num": page_num + 1,
                        "source_pdf": pdf_path,
                    }
                    
                    # Get image dimensions and OCR if PIL is available
                    if self.PIL_Image:
                        try:
                            pil_img = self.PIL_Image.open(img_path)
                            w, h = pil_img.size
                            img_info["width"] = w
                            img_info["height"] = h
                            
                            # OCR the image if available
                            if self.has_ocr_support:
                                try:
                                    ocr_text = self.pytesseract.image_to_string(pil_img)
                                    if ocr_text and ocr_text.strip():
                                        img_info["ocr_text"] = ocr_text.strip()
                                except Exception as e:
                                    logger.debug(f"OCR failed for image {img_filename}: {e}")
                        except Exception as e:
                            logger.debug(f"Failed to get image dimensions for {img_filename}: {e}")
                    
                    extracted.append(img_info)
                except Exception as e:
                    logger.debug(f"Failed to extract image {img_idx + 1} from page {page_num + 1}: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Failed to process images for page {page_num + 1}: {e}")
        
        return extracted
    
    def _extract_tables_from_text(self, text: str) -> str:
        """Extract and normalize table-like data from text content.
        
        Detects common table patterns in text (CSV-like rows, aligned columns,
        pipe-delimited tables) and extracts them in a structured format.
        
        Args:
            text: Text content that may contain table data
            
        Returns:
            Extracted table data as structured text, or empty string
        """
        import re
        
        tables_found = []
        lines = text.split('\n')
        
        # Pattern 1: Pipe-delimited tables (Markdown style)
        pipe_rows = []
        for line in lines:
            stripped = line.strip()
            if '|' in stripped and stripped.count('|') >= 2:
                # Skip Markdown table separator lines like |---|---| or | :--- | ---: |
                # Must have pipes and primarily dashes/colons/spaces between them
                if not re.match(r'^\|?[\s:-]+\|[\s|:-]+\|?$', stripped):
                    cells = [c.strip() for c in stripped.split('|') if c.strip()]
                    if cells:
                        pipe_rows.append(cells)
            elif pipe_rows and len(pipe_rows) >= 2:
                # End of table
                tables_found.append(self._format_table_rows(pipe_rows))
                pipe_rows = []
        if pipe_rows and len(pipe_rows) >= 2:
            tables_found.append(self._format_table_rows(pipe_rows))
        
        # Pattern 2: Tab-delimited data
        tab_rows = []
        for line in lines:
            if '\t' in line:
                cells = [c.strip() for c in line.split('\t') if c.strip()]
                if len(cells) >= 2:
                    tab_rows.append(cells)
            elif tab_rows and len(tab_rows) >= 2:
                tables_found.append(self._format_table_rows(tab_rows))
                tab_rows = []
        if tab_rows and len(tab_rows) >= 2:
            tables_found.append(self._format_table_rows(tab_rows))
        
        return "\n\n".join(tables_found)
    
    def _format_table_rows(self, rows: list) -> str:
        """Format table rows into a readable text representation.
        
        Args:
            rows: List of row data, each row being a list of cell values
            
        Returns:
            Formatted table string
        """
        if not rows:
            return ""
        
        # Use first row as header if available
        header = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else []
        
        parts = [f"Table ({len(rows)} rows, {len(header)} columns):"]
        parts.append(f"Headers: {' | '.join(str(h) for h in header)}")
        
        for i, row in enumerate(data_rows):
            row_data = []
            for j, cell in enumerate(row):
                col_name = header[j] if j < len(header) else f"Col{j+1}"
                row_data.append(f"{col_name}: {cell}")
            parts.append(f"Row {i+1}: {' | '.join(row_data)}")
        
        return "\n".join(parts)
    
    def _extract_text_content(self, path: str) -> str:
        """Extract content from text file with table data detection.
        
        For CSV files, additionally extracts structured table data.
        For other text files, reads as plain text.
        
        Args:
            path: Text file path
            
        Returns:
            File content as string, with table data extraction for CSV files
            
        Raises:
            FetchError: If reading fails
        """
        try:
            _, ext = os.path.splitext(path)
            ext = ext.lower()
            
            # Try different encodings
            raw_content = None
            encodings = ['utf-8', 'utf-16', 'latin-1', 'ascii']
            
            for encoding in encodings:
                try:
                    with open(path, 'r', encoding=encoding) as f:
                        raw_content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            # If all encodings fail, read as binary
            if raw_content is None:
                with open(path, 'rb') as f:
                    raw_content = f.read().decode('utf-8', errors='ignore')
            
            # For CSV files, also extract structured table data
            if ext == '.csv' and raw_content:
                try:
                    table_data = self._extract_csv_structured(path, raw_content)
                    if table_data:
                        return f"{raw_content}\n\n[Structured Table Data]\n{table_data}"
                except Exception as e:
                    logger.debug(f"Failed to extract structured data from CSV {path}: {e}")
            
            return raw_content
                
        except Exception as e:
            raise FetchError(f"Failed to read text file: {str(e)}")
    
    def _extract_csv_structured(self, path: str, raw_content: str) -> str:
        """Extract structured data from CSV files.
        
        Parses CSV content into structured key-value format for better
        intelligence extraction by the LLM pipeline.
        
        Args:
            path: CSV file path
            raw_content: Raw CSV text content
            
        Returns:
            Structured text representation of CSV data
        """
        import csv
        from io import StringIO
        
        try:
            reader = csv.reader(StringIO(raw_content))
            rows = list(reader)
            
            if len(rows) < 2:
                return ""
            
            headers = rows[0]
            parts = [f"CSV Table ({len(rows) - 1} data rows, {len(headers)} columns):"]
            parts.append(f"Columns: {' | '.join(headers)}")
            
            for i, row in enumerate(rows[1:]):
                row_data = []
                for j, cell in enumerate(row):
                    if cell.strip():
                        col_name = headers[j] if j < len(headers) else f"Col{j+1}"
                        row_data.append(f"{col_name}: {cell.strip()}")
                if row_data:
                    parts.append(f"Row {i+1}: {' | '.join(row_data)}")
            
            return "\n".join(parts)
        except Exception:
            return ""
    
    def _extract_image_content(self, path: str) -> str:
        """Extract text and metadata from image using OCR and image analysis.
        
        Extracts OCR text and basic image metadata. When processed through
        the full pipeline, descriptions and keywords will be added via
        Image2Text models.
        
        Args:
            path: Image file path
            
        Returns:
            Extracted text and metadata via OCR
            
        Raises:
            FetchError: If OCR not available or fails
        """
        parts = []
        filename = os.path.basename(path)
        parts.append(f"[Image file: {filename}]")
        
        image = None
        
        # Extract image metadata
        try:
            if self.PIL_Image:
                image = self.PIL_Image.open(path)
                width, height = image.size
                fmt = image.format or "unknown"
                mode = image.mode
                parts.append(f"Format: {fmt} | Dimensions: {width}x{height} | Mode: {mode}")
        except Exception as e:
            parts.append(f"Image metadata extraction failed: {str(e)}")
        
        # OCR text extraction
        if self.has_ocr_support:
            try:
                # Reuse image if already opened, otherwise open it
                if image is None:
                    image = self.PIL_Image.open(path)
                text = self.pytesseract.image_to_string(image)
                if text and text.strip():
                    parts.append(f"OCR extracted text:\n{text.strip()}")
                else:
                    parts.append("OCR: No text detected")
            except Exception as e:
                parts.append(f"OCR failed: {str(e)}")
        else:
            parts.append("OCR not available. Install pytesseract and Pillow: pip install pytesseract Pillow")
        
        return "\n".join(parts)
    
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
        
        # For PDFs, check if extracted images exist
        if file_type in self.PDF_EXTENSIONS:
            pdf_basename = os.path.splitext(os.path.basename(path))[0]
            img_dir = os.path.join(os.path.dirname(os.path.abspath(path)), f"{pdf_basename}_images")
            if os.path.isdir(img_dir):
                image_files = [f for f in os.listdir(img_dir) 
                              if os.path.isfile(os.path.join(img_dir, f))]
                metadata["extracted_images_dir"] = img_dir
                metadata["extracted_images_count"] = len(image_files)
                metadata["extracted_image_paths"] = [
                    os.path.join(img_dir, f) for f in image_files
                ]
        
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
