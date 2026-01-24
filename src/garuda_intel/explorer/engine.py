import logging
import requests
import json

from collections import defaultdict
from typing import List, Dict, Optional, Set, Tuple, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

from ..browser.selenium import SeleniumBrowser
from ..extractor.engine import ContentExtractor
from .scorer import URLScorer
from ..discover.frontier import Frontier
from ..types.entity import EntityType, EntityProfile
from ..database.store import PersistenceStore
from ..vector.engine import VectorStore
from ..extractor.llm import LLMIntelExtractor


class IntelligentExplorer:
    """
    Advanced Entity-Aware Explorer.
    Orchestrates: Semantic Ranking -> Extraction -> Semantic Redundancy ->
    Reflection/Verification -> Dynamic Pattern Evolution -> Storing.
    """
    def __init__(
        self,
        profile: EntityProfile,
        use_selenium: bool = True,
        max_pages_per_domain: int = 5,
        max_total_pages: int = 25,
        max_depth: int = 3,
        score_threshold: float = 20.0,
        persistence: Optional[PersistenceStore] = None,
        vector_store: Optional[VectorStore] = None,
        llm_extractor: Optional[LLMIntelExtractor] = None,
        scorer_patterns: List[Dict] = None,
        scorer_domains: List[Dict] = None,
        enable_llm_link_rank: bool = True,
    ):
        self.profile = profile
        self.use_selenium = use_selenium
        self.max_pages_per_domain = max_pages_per_domain
        self.max_total_pages = max_total_pages
        self.max_depth = max_depth
        self.score_threshold = score_threshold

        # Core Components
        self.content_extractor = ContentExtractor()
        self.llm_extractor = llm_extractor
        self.store = persistence
        self.vector_store = vector_store

        # URL Scoring Logic
        self.url_scorer = URLScorer(profile.name, profile.entity_type, patterns=scorer_patterns, domains=scorer_domains)
        if profile.official_domains:
            self.url_scorer.set_official_domains(profile.official_domains)

        # State Management
        self.visited_urls: Set[str] = set()
        self.explored_data: Dict[str, dict] = {}
        self.domain_counts = defaultdict(int)
        self.logger = logging.getLogger(__name__)
        self.enable_llm_link_rank = enable_llm_link_rank

    def explore(self, start_urls: List[str], browser: Optional[SeleniumBrowser] = None) -> Dict[str, dict]:
        """Main loop orchestrating the full intelligence pipeline."""
        frontier = Frontier()
        for url in start_urls:
            score, _ = self.url_scorer.score_url(url, "", 0)
            frontier.push(score, 0, url, "Seed URL")

        pages_explored = 0
        own_browser = False

        if self.use_selenium and browser is None:
            try:
                browser = SeleniumBrowser(headless=True)
                browser._init_driver()
                own_browser = True
            except Exception as e:
                self.logger.warning(f"Selenium fallback to requests: {e}")
                self.use_selenium = False

        try:
            while len(frontier) and pages_explored < self.max_total_pages:
                current = frontier.pop()
                if not current:
                    break

                score, depth, url, link_text = current
                url_norm = self._normalize_url(url)

                # Guard Clauses
                if (
                    url_norm in self.visited_urls
                    or depth > self.max_depth
                    or self.domain_counts[self._get_domain_key(url)] >= self.max_pages_per_domain
                ):
                    continue

                self.visited_urls.add(url_norm)
                self.domain_counts[self._get_domain_key(url)] += 1

                # 1. FETCH & EXTRACT LINKS
                html, links = self._fetch_page_and_links(url, depth, browser)
                if not html:
                    continue

                # 2. THE INTELLIGENCE WORKSTATION (Extraction, Reflection, Summarization)
                page_record = self._run_intelligence_pipeline(url, html, depth, score)
                if not page_record:
                    continue  # Likely skipped due to semantic redundancy

                self.explored_data[url] = page_record
                pages_explored += 1

                # 3. DYNAMIC EVOLUTION
                if page_record.get("has_high_confidence_intel"):
                    self._boost_domain_priority(url)

                # 4. SEMANTIC LINK PRIORITIZATION
                self._enqueue_new_links(frontier, url, html, links, depth, page_record.get("text_content", ""))

        finally:
            if own_browser and browser:
                browser.close()

        return self.explored_data

    def _run_intelligence_pipeline(self, url: str, html: str, depth: int, score: float) -> Optional[Dict]:
        """The full extraction and reflection process."""
        # A. Physical Extraction
        self.logger.info(f"Processing: {url} at depth {depth} with score {score:.2f}")
        text_content = self.content_extractor.html_to_text(html)
        text_length = len(text_content) if text_content else 0
        metadata = self.content_extractor.extract_metadata(html)
        page_type = self.content_extractor.detect_page_type(url, html, metadata, self.profile.entity_type)

        # 0. Bring in prior intel context via semantic search so downstream extraction knows what we already found.
        prior_intel = []
        if self.vector_store and self.llm_extractor:
            prior_intel = self._collect_prior_intel_context(text_content)

        # B. Semantic Redundancy Check
        if self.vector_store and self.llm_extractor:
            embedding = self.llm_extractor.embed_text(text_content)
            if embedding:
                similar = self.vector_store.search(embedding, top_k=1)
                if similar and similar[0].score > 0.96:
                    self.logger.info(f"Redundancy Filter: Skipping {url} (Similarity: {similar[0].score:.2f})")
                    return None
                self.vector_store.upsert(
                    url,
                    embedding,
                    {
                        "kind": "page_raw",
                        "title": metadata.get("title"),
                        "type": page_type,
                        "entity": self.profile.name,
                        "entity_type": getattr(self.profile.entity_type, "value", str(self.profile.entity_type)),
                    },
                )

        # C. Intelligence Extraction & Verification
        verified_findings = []
        has_high_confidence = False
        extracted_entities: List[Dict] = []
        finding_ids: List[Tuple[Dict, Optional[int]]] = []

        if self.llm_extractor:
            raw_intel = self.llm_extractor.extract_intelligence(
                self.profile,
                text_content,
                page_type,
                url,
                prior_intel or None,
            )

            findings = raw_intel if isinstance(raw_intel, list) else [raw_intel]
            for finding in findings:
                if not finding:
                    continue
                is_verified, conf_score = self.llm_extractor.reflect_and_verify(self.profile, finding)
                self.logger.debug(f"Reflection Result - Verified: {is_verified}, Confidence: {conf_score}")
                if is_verified and conf_score >= 70:
                    has_high_confidence = True
                    if not finding.get("basic_info", {}).get("official_name"):
                        finding.setdefault("basic_info", {})["official_name"] = self.profile.name
                    verified_findings.append(finding)
                    intel_id = None
                    if self.store:
                        intel_id = self.store.save_intelligence(finding, conf_score)
                    finding_ids.append((finding, intel_id))
                    extracted_entities.extend(self.llm_extractor.extract_entities_from_finding(finding))

            if not verified_findings and raw_intel:
                extracted_entities.extend(self.llm_extractor.extract_entities_from_finding(raw_intel))

        summary = self.llm_extractor.summarize_page(text_content) if self.llm_extractor else ""

        page_record = {
            "url": url,
            "page_type": page_type,
            "score": score,
            "summary": summary,
            "extracted_intel": verified_findings,
            "has_high_confidence_intel": has_high_confidence,
            "text_content": text_content,
            "metadata": metadata,
            "text_length": text_length,
            "entity_type": getattr(self.profile.entity_type, "value", str(self.profile.entity_type)),
            "domain_key": self._get_domain_key(url),
            "depth": depth,
        }

        entity_id_map: Dict[tuple, int] = {}
        if self.store:
            self.store.save_page(page_record)
            if extracted_entities:
                entity_id_map = self.store.save_entities(extracted_entities)

        if self.vector_store and self.llm_extractor:
            self._persist_embeddings(
                url,
                metadata,
                summary,
                text_content,
                finding_ids,
                extracted_entities,
                entity_id_map,
                page_type,
            )

        return page_record

    def _enqueue_new_links(self, frontier, base_url, html, links, depth, page_text):
        if depth >= self.max_depth:
            return

        if self.enable_llm_link_rank and self.llm_extractor and links:
            links = self.llm_extractor.rank_links(self.profile, base_url, page_text[:3000], links)

        for link in links:
            href = link.get("href")
            text = link.get("text", "")
            if not href or self._normalize_url(href) in self.visited_urls:
                continue

            h_score, reason = self.url_scorer.score_url(href, text, depth + 1)
            llm_score = link.get("llm_score", 0)

            final_score = max(h_score, llm_score)
            if final_score >= self.score_threshold:
                frontier.push(final_score, depth + 1, href, text)

    def _fetch_page_and_links(self, url: str, depth: int, browser: Optional[SeleniumBrowser]) -> Tuple[str, List[Dict]]:
        if self.use_selenium and browser:
            html = browser.get_page(url)
            links = browser.find_links(url) if depth < self.max_depth else []
            return html, links
        else:
            html = self._fetch_with_requests(url)
            links = self._extract_links(html, url) if depth < self.max_depth else []
            return html, links

    def _boost_domain_priority(self, url: str):
        domain = urlparse(url).netloc.lower()
        self.url_scorer.boost_domain(domain, amount=25)
        self.logger.info(f"Learning: Domain {domain} identified as high-value.")

    def _normalize_url(self, url: str) -> str:
        try:
            p = urlparse(url)
            return f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
        except Exception:
            return url

    def _get_domain_key(self, url: str) -> str:
        return urlparse(url).netloc.lower().replace("www.", "")

    def _fetch_with_requests(self, url: str) -> str:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            return r.text if r.status_code == 200 else ""
        except Exception:
            return ""

    def _extract_links(self, html: str, base_url: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        found = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            if href.startswith("http"):
                found.append({"href": href, "text": a.get_text(strip=True)})
        return found

    def _collect_prior_intel_context(self, text_content: str) -> List[Dict]:
        context = []
        try:
            query_vec = self.llm_extractor.embed_text(text_content[:4000])
            if not query_vec:
                return context
            hits = self.vector_store.search(query_vec, top_k=5)
            for h in hits or []:
                payload = getattr(h, "payload", {}) or {}
                if payload.get("kind") == "finding" and payload.get("data"):
                    context.append(payload["data"])
        except Exception as e:
            self.logger.warning(f"Context recall failed: {e}")
        return context

    def _persist_embeddings(
        self,
        url: str,
        metadata: Dict,
        summary: str,
        text_content: str,
        finding_ids: List[Tuple[Dict, Optional[int]]],
        entities: List[Dict],
        entity_id_map: Dict[tuple, int],
        page_type: str,
    ):
        try:
            entries = self.llm_extractor.build_embeddings_for_page(
                url=url,
                metadata=metadata,
                summary=summary,
                text_content=text_content,
                findings_with_ids=finding_ids,
                page_type=page_type,
                entity_name=self.profile.name,
                entity_type=self.profile.entity_type,
            )
            if entities:
                entries.extend(
                    self.llm_extractor.build_embeddings_for_entities(
                        entities=entities,
                        source_url=url,
                        entity_type=self.profile.entity_type,
                        entity_id_map=entity_id_map,
                    )
                )
            for entry in entries:
                self.vector_store.upsert(
                    point_id=entry["id"],
                    vector=entry["vector"],
                    payload=entry["payload"],
                )
        except Exception as e:
            self.logger.warning(f"Embedding persistence failed for {url}: {e}")
