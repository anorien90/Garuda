"""Multi-source intelligence aggregation framework."""

from .base_adapter import SourceAdapter, Document, SourceType
from .pdf_adapter import PDFAdapter
from .api_adapter import APIAdapter
from .local_file_adapter import LocalFileAdapter

__all__ = [
    "SourceAdapter",
    "Document",
    "SourceType",
    "PDFAdapter",
    "APIAdapter",
    "LocalFileAdapter",
]
