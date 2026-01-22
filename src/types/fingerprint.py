from dataclasses import dataclass
from typing import Optional


@dataclass
class PageFingerprint:
    page_url: str
    selector: str         # CSS selector used to extract repeating blocks
    purpose: str          # e.g., "headline_list", "bio_section", "leadership_table"
    sample_text: Optional[str] = None
