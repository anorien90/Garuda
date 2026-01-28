"""Multi-source intelligence aggregation framework."""

from .base_adapter import SourceAdapter, Document
from .pdf_adapter import PDFAdapter
from .api_adapter import APIAdapter

__all__ = [
    "SourceAdapter",
    "Document",
    "PDFAdapter",
    "APIAdapter",
]
