"""
Refresh runner: re-fetch known pages using stored fingerprints to detect deltas.
"""
import logging
import requests
from bs4 import BeautifulSoup
from typing import List
from .persistence.store import PersistenceStore
from .models.page_fingerprint import PageFingerprint
from .extractor import ContentExtractor


class RefreshRunner:
    def __init__(self, store: PersistenceStore, use_selenium: bool = False, vector_store=None, llm_extractor=None):
        self.store = store
        self.use_selenium = use_selenium
        self.extractor = ContentExtractor()
        self.logger = logging.getLogger(__name__)
        self.vector_store = vector_store
        self.llm_extractor = llm_extractor

    def run(self, batch: int = 50):
        """Run  a refresh cycle on pending pages.
        Fetches pending pages, extracts content using stored fingerprints, updates the store,
        and updates vector store if applicable.
        ToDo: Add delta detection and change logging and re-fingerprinting.
        """
        pending = self.store.get_pending_refresh(limit=batch)
        for item in pending:
            url = item["url"]
            html = self._fetch(url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            fingerprints = self.store.get_fingerprints(url)
            if fingerprints:
                # Focused extraction per stored selectors
                snippets = []
                for fp in fingerprints:
                    for node in soup.select(fp.selector):
                        snippets.append(node.get_text(" ", strip=True))
                focused_text = " ".join(snippets) or self.extractor.html_to_text(html)
            else:
                focused_text = self.extractor.html_to_text(html)

            metadata = self.extractor.extract_metadata(html)
            page_record = {
                "url": url,
                "entity_type": item.get("entity_type"),
                "page_type": item.get("page_type"),
                "depth": 0,
                "score": 0,
                "domain_key": "",
                "metadata": metadata,
                "text_content": focused_text,
                "text_length": len(focused_text),
                "html": html,
                "extracted": {},
            }
            self.store.save_page(page_record)
            self.store.mark_visited(url)

            if self.vector_store and self.llm_extractor:
                try:
                    vector = self.llm_extractor.embed_text(focused_text)
                    self.vector_store.upsert(
                        point_id=url,
                        vector=vector,
                        payload={
                            "url": url,
                            "page_type": item.get("page_type"),
                            "entity_type": item.get("entity_type"),
                            "title": metadata.get("title", ""),
                        },
                    )
                except Exception as e:
                    self.logger.warning(f"Vector upsert failed during refresh for {url}: {e}")

    def _fetch(self, url: str) -> str:
        try:
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                return resp.text
        except Exception:
            self.logger.debug(f"Refresh fetch failed for {url}")
        return ""
