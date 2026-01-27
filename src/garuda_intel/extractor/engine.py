# Entity-aware and fingerprint-capable extractor
import re
import json
import logging
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

from .filter import SemanticFilter
from ..types.entity.type import EntityType
from ..types.page.fingerprint import PageFingerprint


class ContentExtractor:
    """Extracts structured content from HTML pages with entity-aware heuristics."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _strip_prompty_lines(self, text: str) -> str:
        """
        Remove lines that look like injected prompts, crawler boilerplate, or scoring metadata.
        """
        if not text:
            return ""
        drop_patterns = re.compile(
            r"(?i)(^|\b)(instruction|prompt|assistant:|user:|###|score\s*\d+|uuid\s+[0-9a-f-]{8,}|No extracted intel|depth\s+\d+)\b"
        )
        kept = []
        for line in text.splitlines():
            if drop_patterns.search(line):
                continue
            kept.append(line)
        cleaned = "\n".join(kept).strip()
        # Truncate at first instruction-like marker
        cut_mark = re.search(r"(?i)(instruction:|###\s|assistant:|user:)", cleaned)
        if cut_mark:
            cleaned = cleaned[: cut_mark.start()].strip()
        return cleaned

    def html_to_text(self, html: str, max_length: int = 15000) -> str:
        if not html:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        for element in soup(
            ["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "noscript"]
        ):
            element.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        text = self._strip_prompty_lines(text)
        return text[:max_length]

    def extract_images(self, html: str, base_url: str) -> List[Dict]:
        """
        Specific extraction for better visual data selection.
        """
        soup = BeautifulSoup(html, "html.parser")
        images = []
        for img in soup.find_all("img"):
            src = img.get("src")
            if src and not src.startswith("data:"):
                images.append(
                    {
                        "url": src,
                        "alt": img.get("alt", ""),
                        "title": img.get("title", ""),
                        "parent_text": img.parent.get_text()[:100] if img.parent else "",
                    }
                )
        return images

    def extract_metadata(self, html: str) -> dict:
        metadata = {}
        if not html:
            return metadata
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text(strip=True)
        for meta in soup.find_all("meta"):
            name = meta.get("name", "").lower() or meta.get("property", "").lower()
            content = meta.get("content", "")
            if name in ["description", "og:description"]:
                metadata["description"] = content
            elif name in ["og:title"]:
                metadata["og_title"] = content
            elif name == "author":
                metadata["author"] = content
            elif name == "keywords":
                metadata["keywords"] = content
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                metadata.setdefault("structured_data", []).append(json.loads(script.string))
            except Exception:
                pass
        return metadata

    def detect_page_type(self, url: str, html: str, metadata: dict, entity_type: EntityType) -> str:
        url_lower = url.lower()
        if entity_type == EntityType.NEWS and any(x in url_lower for x in ["/news", "/article", "/story", "/press"]):
            return "news"
        if entity_type == EntityType.PERSON and any(x in url_lower for x in ["/bio", "/about", "/person", "/people"]):
            return "person_profile"
        if entity_type == EntityType.COMPANY:
            if any(x in url_lower for x in ["opencorporates", "companies-house", "company-information", "northdata"]):
                return "registry"
            if "sec.gov" in url_lower:
                return "sec_filing"
            if any(x in url_lower for x in ["/investor", "/annual-report", "/financials", "/earnings"]):
                return "investor"
            if any(x in url_lower for x in ["/leadership", "/management", "/board", "/executive", "/about"]):
                return "leadership"
        if "wikipedia.org" in url_lower:
            return "wikipedia"
        return "general"

    def capture_fingerprints(self, page_type: str, soup: BeautifulSoup, page_url: str, page_id: Optional[str] = None) -> List[PageFingerprint]:
        fps: List[PageFingerprint] = []
        pid = page_id

        def add_fp(selector: str, purpose: str, sample: str):
            fps.append(
                PageFingerprint(
                    page_id=pid,
                    page_url=page_url,
                    selector=selector,
                    purpose=purpose,
                    sample_text=sample,
                )
            )

        if page_type == "news":
            for selector in [".article", ".story", "article", ".post", ".card"]:
                nodes = soup.select(selector)
                if len(nodes) >= 2:
                    sample = nodes[0].get_text(strip=True)[:200] if nodes else ""
                    add_fp(selector, "headline_list", sample)
                    break

        if page_type in ("leadership", "person_profile"):
            for selector in [".team-member", ".bio", ".profile", "table", "dl"]:
                nodes = soup.select(selector)
                if len(nodes) >= 1:
                    sample = nodes[0].get_text(strip=True)[:200] if nodes else ""
                    add_fp(selector, "people_section", sample)
                    break

        if page_type == "registry":
            for selector in [".company-info", ".entity-details", "#company-data", "table"]:
                nodes = soup.select(selector)
                if len(nodes) >= 1:
                    sample = nodes[0].get_text(strip=True)[:200] if nodes else ""
                    add_fp(selector, "company_info", sample)
                    break

        if page_type == "investor":
            for selector in [".financials", ".investor-data", "#financial-table", "table"]:
                nodes = soup.select(selector)
                if len(nodes) >= 1:
                    sample = nodes[0].get_text(strip=True)[:200] if nodes else ""
                    add_fp(selector, "financial_data", sample)
                    break

        if page_type == "wikipedia":
            for selector in [".infobox", "#mw-content-text table", ".vcard"]:
                nodes = soup.select(selector)
                if len(nodes) >= 1:
                    sample = nodes[0].get_text(strip=True)[:200] if nodes else ""
                    add_fp(selector, "infobox", sample)
                    break

        if page_type == "general":
            for selector in ["h1", "h2", "h3", "p", "table"]:
                nodes = soup.select(selector)
                if len(nodes) >= 5:
                    sample = nodes[0].get_text(strip=True)[:200] if nodes else ""
                    add_fp(selector, "general_content", sample)
                    break

        if page_type == "sec_filing":
            for selector in [".sec-document", "#form-data", "pre"]:
                nodes = soup.select(selector)
                if len(nodes) >= 1:
                    sample = nodes[0].get_text(strip=True)[:200] if nodes else ""
                    add_fp(selector, "sec_filing_data", sample)
                    break

        if page_type == "person_profile":
            for selector in [".contact-info", ".personal-details", "table", "dl", ".vcard"]:
                nodes = soup.select(selector)
                if len(nodes) >= 1:
                    sample = nodes[0].get_text(strip=True)[:200] if nodes else ""
                    add_fp(selector, "contact_info", sample)
                    break

        return fps
