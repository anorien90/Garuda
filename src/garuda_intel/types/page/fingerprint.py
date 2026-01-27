from dataclasses import dataclass
from typing import Optional


@dataclass
class PageFingerprint:
    page_id: Optional[str]          # UUID of the page (preferred)
    selector: str                   # CSS selector used to extract repeating blocks
    purpose: str                    # e.g., "headline_list", "bio_section", "leadership_table"
    sample_text: Optional[str] = None
    page_url: Optional[str] = None  # legacy/backfill; used to derive page_id if needed
