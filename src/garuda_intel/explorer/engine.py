import logging
import requests

from collections import defaultdict
from typing import List, Dict, Optional, Set, Tuple, Any
from urllib.parse import urlparse, urljoin
from uuid import uuid5, NAMESPACE_URL
from bs4 import BeautifulSoup

from ..browser.selenium import SeleniumBrowser
from ..extractor.engine import ContentExtractor
from .scorer import URLScorer
from ..discover.frontier import Frontier
from ..discover.crawl_learner import CrawlLearner
from ..discover.post_crawl_processor import PostCrawlProcessor
from ..types.entity import EntityProfile
from ..database.store import PersistenceStore
from ..database.relationship_manager import RelationshipManager
from ..vector.engine import VectorStore
from ..extractor.llm import LLMIntelExtractor
from ..extractor.iterative_refiner import IterativeRefiner
from ..extractor.strategy_selector import StrategySelector


# Configuration constants for relationship inference
# Maximum characters of context to use for relationship inference (balance between coverage and performance)
MAX_RELATIONSHIP_INFERENCE_CONTEXT = 8000
# Confidence score assigned to inferred relationships (lower than LLM-extracted relationships)
INFERRED_RELATIONSHIP_CONFIDENCE = 60.0


def _uuid5_url(url: str) -> str:
    return str(uuid5(NAMESPACE_URL, url))

def _as_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]

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
        media_extractor = None,
        max_fetch_workers: int = 5,
    ):
        self.profile = profile
        self.use_selenium = use_selenium
        self.max_pages_per_domain = max_pages_per_domain
        self.max_total_pages = max_total_pages
        self.max_depth = max_depth
        self.score_threshold = score_threshold
        self.max_fetch_workers = max_fetch_workers

        # Core Components
        self.content_extractor = ContentExtractor()
        self.llm_extractor = llm_extractor
        self.store = persistence
        self.vector_store = vector_store
        self.media_extractor = media_extractor
        
        # Relationship Management (Phase 3)
        self.relationship_manager = None
        if persistence and llm_extractor:
            self.relationship_manager = RelationshipManager(persistence, llm_extractor)
        
        # Crawl Learning (Phase 4)
        self.crawl_learner = None
        if persistence:
            self.crawl_learner = CrawlLearner(persistence)
        
        # Iterative Refinement (Phase 4)
        self.iterative_refiner = None
        if llm_extractor and persistence:
            self.iterative_refiner = IterativeRefiner(llm_extractor, persistence)
        
        # Strategy Selection (Phase 4)
        self.strategy_selector = StrategySelector()
        
        # Post-crawl Processor (Comprehensive deduplication and aggregation)
        self.post_crawl_processor = None
        if persistence:
            self.post_crawl_processor = PostCrawlProcessor(
                store=persistence,
                relationship_manager=self.relationship_manager,
                llm=llm_extractor,
                vector_store=vector_store
            )

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

    def explore(self, start_urls: List[str], 
                browser: Optional[SeleniumBrowser] = None) -> Dict[str, dict]:
        """Main loop with parallel HTTP fetching and sequential LLM."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        frontier = Frontier()
        seed_ids = []  # Track seed IDs to create relationships later
        
        if self.store:
            for url in start_urls:
                try:
                    seed_id = self.store.save_seed(
                        query=self.profile.name, 
                        entity_type=self.profile.entity_type.value, 
                        source="explorer"
                    )
                    seed_ids.append((seed_id, url))
                except Exception as e:
                    self.logger.debug(f"Failed to save seed: {e}")

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
            # Track seed-to-url mapping for relationship creation
            seed_url_map = {url: seed_id for seed_id, url in seed_ids}
            
            # Parallel fetch pool (only when not using Selenium)
            fetch_workers = min(
                self.max_fetch_workers, self.max_total_pages
            )
            
            while len(frontier) and pages_explored < self.max_total_pages:
                # Phase 1: Collect batch of URLs to fetch
                batch = []
                # Selenium uses sequential fetching (batch of 1)
                # Requests library uses parallel fetching
                batch_size = (1 if self.use_selenium else fetch_workers)
                
                while (len(frontier) and len(batch) < batch_size 
                       and pages_explored + len(batch) < self.max_total_pages):
                    current = frontier.pop()
                    if not current:
                        break

                    score, depth, url, link_text = current
                    url_norm = self._normalize_url(url)

                    # Guard Clauses
                    if (url_norm in self.visited_urls
                        or depth > self.max_depth
                        or self.domain_counts[self._get_domain_key(url)] 
                           >= self.max_pages_per_domain):
                        continue

                    self.visited_urls.add(url_norm)
                    self.domain_counts[self._get_domain_key(url)] += 1
                    batch.append((score, depth, url, link_text))
                
                if not batch:
                    break
                
                # Phase 2: Parallel HTTP fetch (if not using Selenium)
                fetch_results = {}
                
                if self.use_selenium:
                    # Sequential fetch with Selenium (shared browser)
                    for score, depth, url, link_text in batch:
                        try:
                            html, links = self._fetch_page_and_links(
                                url, depth, browser
                            )
                            if html:
                                fetch_results[url] = (html, links, score, depth)
                        except Exception as e:
                            self.logger.warning(
                                f"Fetch failed for {url}: {e}"
                            )
                else:
                    # Parallel fetch with requests
                    with ThreadPoolExecutor(
                        max_workers=min(len(batch), fetch_workers)
                    ) as fetch_pool:
                        future_to_url = {}
                        for score, depth, url, link_text in batch:
                            future = fetch_pool.submit(
                                self._fetch_page_and_links, 
                                url, depth, None
                            )
                            future_to_url[future] = (
                                score, depth, url, link_text
                            )
                        
                        for future in as_completed(future_to_url):
                            score, depth, url, link_text = (
                                future_to_url[future]
                            )
                            try:
                                html, links = future.result()
                                if html:
                                    fetch_results[url] = (
                                        html, links, score, depth
                                    )
                            except Exception as e:
                                self.logger.warning(
                                    f"Parallel fetch failed for {url}: {e}"
                                )
                
                # Phase 3: Sequential LLM processing
                for url, (html, links, score, depth) in fetch_results.items():
                    # THE INTELLIGENCE WORKSTATION 
                    # (Extraction, Reflection, Summarization)
                    page_record = self._run_intelligence_pipeline(
                        url, html, depth, score
                    )
                    if not page_record:
                        continue  # Skipped due to semantic redundancy

                    # Create Seed→Page relationship if URL came from seed
                    if (url in seed_url_map and self.store 
                        and page_record.get("id")):
                        try:
                            self.store.save_relationship(
                                from_id=seed_url_map[url],
                                to_id=page_record["id"],
                                relation_type="seed_page",
                                meta={"depth": depth}
                            )
                        except Exception as e:
                            self.logger.debug(
                                f"Failed to create seed→page relationship: {e}"
                            )

                    self.explored_data[url] = page_record
                    pages_explored += 1

                    # DYNAMIC EVOLUTION
                    if page_record.get("has_high_confidence_intel"):
                        self._boost_domain_priority(url)

                    # SEMANTIC LINK PRIORITIZATION
                    self._enqueue_new_links(
                        frontier, url, html, links, depth, 
                        page_record.get("text_content", "")
                    )

        finally:
            if own_browser and browser:
                browser.close()
            
            # Comprehensive post-crawl processing
            if self.post_crawl_processor and pages_explored > 0:
                try:
                    self.logger.info(
                        "Running comprehensive post-crawl processing..."
                    )
                    session_id = f"crawl_{self.profile.name}_{pages_explored}"
                    self.post_crawl_processor.process(
                        session_id=session_id
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Post-crawl processing failed: {e}"
                    )
            
            # Crawl learning (improving future crawls)
            if self.crawl_learner and pages_explored > 0:
                try:
                    self.logger.info(
                        "Recording crawl results for learning..."
                    )
                    for url, page_data in self.explored_data.items():
                        intel_quality = page_data.get("avg_confidence", 0.5)
                        page_type = page_data.get("page_type", "general")
                        extraction_success = page_data.get(
                            "has_high_confidence_intel", False
                        )
                        
                        self.crawl_learner.record_crawl_result(
                            url=url,
                            page_type=page_type,
                            intel_quality=intel_quality,
                            extraction_success=extraction_success
                        )
                    
                    # Update URL scorer with learned patterns
                    if self.url_scorer and self.explored_data:
                        domain_key = self._get_domain_key(
                            list(self.explored_data.keys())[0]
                        )
                        reliability = (
                            self.crawl_learner.get_domain_reliability(
                                domain_key
                            )
                        )
                        if reliability > 0:
                            self.logger.info(
                                f"Domain {domain_key} reliability: "
                                f"{reliability:.2f}"
                            )
                except Exception as e:
                    self.logger.warning(
                        f"Crawl learning recording failed: {e}"
                    )

        return self.explored_data

    def _run_intelligence_pipeline(self, url: str, html: str, depth: int, score: float) -> Optional[Dict]:
        """
        The full extraction and reflection process:
        - Extract text, metadata, links
        - Run LLM extraction + reflection
        - Persist page, links, entities, intel
        - Persist embeddings
        """
        # 1) Extract content and links
        text_content = self.content_extractor.html_to_text(html)
        metadata = self.content_extractor.extract_metadata(html)
        page_type = self.content_extractor.detect_page_type(
            url, html, metadata, self.profile.entity_type
        )
        links = self._extract_links(url, html, metadata, depth)
        extracted_entities: List[Dict] = []
        verified_findings: List[Dict] = []
        verified_findings_with_scores: List[Tuple[Dict, float]] = []
        finding_ids: List[Tuple[Dict, Optional[str], Optional[str]]] = []

        # 2) LLM extraction + reflection
        finding_to_entities = {}  # Map findings to their extracted entities
        if self.llm_extractor:
            raw_intel = self.llm_extractor.extract_intelligence(
                profile=self.profile,
                text=text_content,
                page_type=page_type,
                url=url,
                existing_intel=None,
            )
            if raw_intel:
                for finding in _as_list(raw_intel):
                    is_verified, conf_score = self.llm_extractor.reflect_and_verify(
                        self.profile, finding
                    )
                    if is_verified:
                        finding.setdefault("basic_info", {})["official_name"] = self.profile.name
                        verified_findings.append(finding)
                        verified_findings_with_scores.append((finding, conf_score))
                        # Extract and track entities for this finding
                        finding_entities = self.llm_extractor.extract_entities_from_finding(finding)
                        finding_to_entities[id(finding)] = finding_entities  # Use id() to create unique key
                        extracted_entities.extend(finding_entities)

            if not verified_findings and raw_intel:
                extracted_entities.extend(
                    self.llm_extractor.extract_entities_from_finding(raw_intel)
                )
            
            # Infer additional relationships between extracted entities using context
            if extracted_entities and hasattr(self.llm_extractor, 'infer_relationships_from_entities'):
                inferred_rels = self.llm_extractor.infer_relationships_from_entities(
                    entities=extracted_entities,
                    context_text=text_content[:MAX_RELATIONSHIP_INFERENCE_CONTEXT] if text_content else ""
                )
                # Add inferred relationships to the findings for persistence
                if inferred_rels:
                    self.logger.info(f"Inferred {len(inferred_rels)} additional relationships from entity context")
                    # Create a synthetic finding for inferred relationships
                    if verified_findings:
                        # Add to last finding
                        if "relationships" not in verified_findings[-1]:
                            verified_findings[-1]["relationships"] = []
                        verified_findings[-1]["relationships"].extend(inferred_rels)
                    else:
                        # Create new finding for inferred relationships
                        inferred_finding = {
                            "basic_info": {},
                            "relationships": inferred_rels,
                        }
                        verified_findings.append(inferred_finding)
                        verified_findings_with_scores.append((inferred_finding, INFERRED_RELATIONSHIP_CONFIDENCE))

        summary = (
            self.llm_extractor.summarize_page(text_content)
            if self.llm_extractor
            else ""
        )
        text_length = len(text_content or "")

        page_record = {
            "url": url,
            "page_type": page_type,
            "score": score,
            "summary": summary,
            "extracted_intel": verified_findings,
            "metadata": metadata,
            "extracted": extracted_entities,
            "links": links,
            "has_high_confidence_intel": any(
                cs >= 70 for _, cs in verified_findings_with_scores
            ),
            "text_content": text_content,
            "text_length": text_length,
            "entity_type": getattr(self.profile.entity_type, "value", str(self.profile.entity_type)),
            "domain_key": self._get_domain_key(url),
            "depth": depth,
        }

        # Initialize to avoid UnboundLocalError when store is absent or fails
        entity_id_map: Dict[tuple, str] = {}
        primary_entity_id: Optional[str] = None
        page_uuid: Optional[str] = None

        # 3) Persist page, entities, links, intel
        if self.store:
            page_uuid = self.store.save_page(page_record)
            page_record["id"] = page_uuid
            
            # Extract media from page if media extractor is available
            if self.media_extractor and html:
                try:
                    import uuid
                    # Convert page_uuid string to UUID if needed
                    if isinstance(page_uuid, str):
                        page_uuid_obj = uuid.UUID(page_uuid)
                    else:
                        page_uuid_obj = page_uuid
                    self.media_extractor.extract_media_from_page(page_uuid_obj, url, html)
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Media extraction failed for {url}: {e}")

            if extracted_entities:
                # Add page_id context to all entities to create Page→Entity relationships
                for entity in extracted_entities:
                    if "page_id" not in entity:
                        entity["page_id"] = page_uuid
                
                entity_id_map = self.store.save_entities(extracted_entities) or {}

            # Save relationships from findings
            # Build lowercase name lookup for efficient entity matching
            entity_name_to_id = {}
            for (ent_name, ent_kind), ent_id in entity_id_map.items():
                entity_name_to_id[ent_name.lower()] = ent_id
            
            # Track entities that need to be created for relationships
            # Use dict to avoid duplicates: key=(name, kind), value=entity_dict
            missing_entities_dict = {}
            
            for finding, conf_score in verified_findings_with_scores:
                relationships = finding.get("relationships", [])
                if relationships and isinstance(relationships, list):
                    for rel in relationships:
                        if not isinstance(rel, dict):
                            continue
                        source_name = rel.get("source")
                        target_name = rel.get("target")
                        relation_type = rel.get("relation_type") or "related"
                        description = rel.get("description", "")
                        source_type = rel.get("source_type", "entity")
                        target_type = rel.get("target_type", "entity")
                        
                        # Coerce list values to strings (LLM may return lists)
                        if isinstance(source_name, list):
                            source_name = source_name[0] if source_name else None
                        if isinstance(target_name, list):
                            target_name = target_name[0] if target_name else None
                        if isinstance(source_type, list):
                            source_type = source_type[0] if source_type else "entity"
                        if isinstance(target_type, list):
                            target_type = target_type[0] if target_type else "entity"
                        
                        if source_name and target_name:
                            # Look up entity IDs using lowercase name lookup
                            source_id = entity_name_to_id.get(source_name.lower())
                            target_id = entity_name_to_id.get(target_name.lower())
                            
                            # Auto-create missing entities to ensure relationships are always persisted
                            if not source_id:
                                # Create entity for source if it doesn't exist
                                # Use (name, kind) as key to avoid duplicates
                                key = (source_name, source_type)
                                if key not in missing_entities_dict:
                                    missing_entities_dict[key] = {
                                        "name": source_name,
                                        "kind": source_type,
                                        "data": {"auto_created_from_relationship": True},
                                        "page_id": page_uuid,
                                    }
                            
                            if not target_id:
                                # Create entity for target if it doesn't exist
                                key = (target_name, target_type)
                                if key not in missing_entities_dict:
                                    missing_entities_dict[key] = {
                                        "name": target_name,
                                        "kind": target_type,
                                        "data": {"auto_created_from_relationship": True},
                                        "page_id": page_uuid,
                                    }
            
            # Create any missing entities
            if missing_entities_dict:
                try:
                    missing_entities_to_create = list(missing_entities_dict.values())
                    new_entity_map = self.store.save_entities(missing_entities_to_create) or {}
                    # Update entity_id_map and entity_name_to_id with newly created entities
                    entity_id_map.update(new_entity_map)
                    for (ent_name, ent_kind), ent_id in new_entity_map.items():
                        entity_name_to_id[ent_name.lower()] = ent_id
                except Exception as e:
                    self.logger.warning(f"Failed to create missing entities for relationships: {e}")
            
            # Now save all relationships (all entities should exist)
            for finding, conf_score in verified_findings_with_scores:
                relationships = finding.get("relationships", [])
                if relationships and isinstance(relationships, list):
                    for rel in relationships:
                        if not isinstance(rel, dict):
                            continue
                        source_name = rel.get("source")
                        target_name = rel.get("target")
                        relation_type = rel.get("relation_type") or "related"
                        description = rel.get("description", "")
                        
                        if source_name and target_name:
                            # Look up entity IDs (should now all exist)
                            source_id = entity_name_to_id.get(source_name.lower())
                            target_id = entity_name_to_id.get(target_name.lower())
                            
                            # Save relationship
                            if source_id and target_id:
                                try:
                                    # Build metadata, excluding None values
                                    rel_meta = {
                                        "description": description,
                                        "confidence": conf_score,
                                    }
                                    if page_uuid:
                                        rel_meta["page_id"] = page_uuid
                                    
                                    self.store.save_relationship(
                                        from_id=source_id,
                                        to_id=target_id,
                                        relation_type=relation_type,
                                        meta=rel_meta
                                    )
                                except Exception as e:
                                    self.logger.debug(f"save_relationship failed: {e}")
                            else:
                                # Log if we still couldn't find entities (shouldn't happen)
                                self.logger.warning(
                                    f"Unable to persist relationship {source_name} -> {target_name} "
                                    f"({relation_type}): entities not found"
                                )

            if links:
                try:
                    self.store.save_links(url, links)
                except Exception as e:
                    self.logger.debug(f"save_links failed: {e}")

            primary_entity_id = entity_id_map.get(
                (
                    self.profile.name,
                    getattr(self.profile.entity_type, "value", str(self.profile.entity_type)),
                )
            )
            
            # Create relationships between primary entity and other entities found on the page
            if primary_entity_id and entity_id_map:
                primary_kind = getattr(self.profile.entity_type, "value", str(self.profile.entity_type))
                for (ent_name, ent_kind), ent_id in entity_id_map.items():
                    # Don't create self-relationship
                    if ent_id != primary_entity_id:
                        try:
                            # Determine relationship type based on entity kinds
                            relation_type = "related-entity"
                            rel_meta = {"page_id": page_uuid, "discovered_together": True}
                            
                            # Company/Organization relationships
                            if primary_kind in ["company", "organization"]:
                                if ent_kind == "person":
                                    relation_type = "has-person"
                                    rel_meta["relationship_context"] = "employment_or_leadership"
                                elif ent_kind == "product":
                                    relation_type = "has-product"
                                    rel_meta["relationship_context"] = "product_ownership"
                                elif ent_kind == "location":
                                    relation_type = "has-location"
                                    rel_meta["relationship_context"] = "office_or_headquarters"
                                elif ent_kind == "event":
                                    relation_type = "participated-in-event"
                                    rel_meta["relationship_context"] = "organizational_event"
                            
                            # Person relationships
                            elif primary_kind == "person":
                                if ent_kind in ["company", "organization"]:
                                    relation_type = "works-at"
                                    rel_meta["relationship_context"] = "employment"
                                elif ent_kind == "location":
                                    relation_type = "located-at"
                                    rel_meta["relationship_context"] = "residence_or_office"
                                elif ent_kind == "event":
                                    relation_type = "participated-in-event"
                                    rel_meta["relationship_context"] = "personal_participation"
                            
                            # Product relationships
                            elif primary_kind == "product":
                                if ent_kind in ["company", "organization"]:
                                    relation_type = "produced-by"
                                    rel_meta["relationship_context"] = "manufacturer"
                                elif ent_kind == "person":
                                    relation_type = "associated-with-person"
                                    rel_meta["relationship_context"] = "creator_or_contributor"
                            
                            # Primary entity is related to other entities on the same page
                            self.store.save_relationship(
                                from_id=primary_entity_id,
                                to_id=ent_id,
                                relation_type=relation_type,
                                meta=rel_meta
                            )
                        except Exception as e:
                            self.logger.debug(f"Failed to create entity-entity relationship: {e}")

        for finding, conf_score in verified_findings_with_scores:
            intel_id = None
            if self.store:
                intel_id = self.store.save_intelligence(
                    finding=finding,
                    confidence=conf_score,
                    page_id=page_uuid,
                    entity_id=primary_entity_id,
                    entity_name=self.profile.name,
                    entity_type=getattr(self.profile.entity_type, "value", str(self.profile.entity_type)),
                )
                
                # Link Intelligence to all extracted sub-entities (persons, products, locations, events)
                # This ensures that each sub-entity maintains provenance to the intel that mentioned it
                if intel_id:
                    # Use already-extracted entities from this finding (avoid re-extraction)
                    finding_entities = finding_to_entities.get(id(finding), [])
                    for sub_entity in finding_entities:
                        sub_entity_name = sub_entity.get("name")
                        sub_entity_kind = sub_entity.get("kind")
                        if sub_entity_name and sub_entity_kind:
                            # Look up the entity ID from the entity_id_map
                            sub_entity_id = entity_id_map.get((sub_entity_name, sub_entity_kind))
                            if sub_entity_id:
                                try:
                                    # Create Intel→Entity relationship to track which entities are mentioned in this intel
                                    self.store.save_relationship(
                                        from_id=intel_id,
                                        to_id=sub_entity_id,
                                        relation_type="mentions_entity",
                                        meta={
                                            "confidence": conf_score,
                                            "page_id": page_uuid,
                                            "entity_type": sub_entity_kind,
                                        }
                                    )
                                except Exception as e:
                                    self.logger.debug(f"Failed to create Intel→Entity relationship: {e}")
            
            finding_ids.append((finding, intel_id, primary_entity_id))

        # 4) Persist embeddings (page + entities + findings + semantic snippets)
        if self.vector_store and self.llm_extractor:
            try:
                self.logger.info(f"Generating embeddings for page: {url}")
                entries = self.llm_extractor.build_embeddings_for_page(
                    url=url,
                    metadata=metadata,
                    summary=summary,
                    text_content=text_content,
                    findings_with_ids=finding_ids,
                    page_type=page_type,
                    entity_name=self.profile.name,
                    entity_type=self.profile.entity_type,
                    page_uuid=page_uuid,
                )
                if extracted_entities:
                    entries.extend(
                        self.llm_extractor.build_embeddings_for_entities(
                            entities=extracted_entities,
                            source_url=url,
                            entity_type=self.profile.entity_type,
                            entity_id_map=entity_id_map,
                            page_uuid=page_uuid,
                        )
                    )

                # 4b) Generate fine-grained semantic snippets (1-3 sentences)
                snippet_entries = self._generate_and_store_snippets(
                    text_content=text_content,
                    url=url,
                    page_type=page_type,
                    page_uuid=page_uuid,
                    primary_entity_id=primary_entity_id,
                    extracted_entities=extracted_entities,
                )
                entries.extend(snippet_entries)
                
                self.logger.info(f"Upserting {len(entries)} embeddings to Qdrant for page: {url}")
                for entry in entries:
                    self.vector_store.upsert(
                        point_id=entry["id"],
                        vector=entry["vector"],
                        payload=entry["payload"],
                    )
                self.logger.info(f"Successfully stored {len(entries)} embeddings in Qdrant")
            except Exception as e:
                self.logger.error(f"Failed to persist embeddings for {url}: {e}", exc_info=True)
        elif not self.vector_store:
            self.logger.warning(f"Vector store not available - skipping embedding generation for {url}")
        elif not self.llm_extractor:
            self.logger.warning(f"LLM extractor not available - skipping embedding generation for {url}")

        return page_record

    # ------------------------------------------------------------------
    # Semantic snippet helpers
    # ------------------------------------------------------------------

    def _generate_and_store_snippets(
        self,
        text_content: str,
        url: str,
        page_type: str,
        page_uuid: Optional[str],
        primary_entity_id: Optional[str],
        extracted_entities: List[Dict],
    ) -> List[Dict[str, Any]]:
        """Create 1-3 sentence semantic snippets, persist to DB, return
        embedding entries for the vector store."""
        from ..extractor.semantic_chunker import SemanticChunker

        chunker = SemanticChunker()
        snippets = chunker.chunk_into_snippets(
            text_content or "",
            source_url=url,
            max_sentences=3,
        )
        if not snippets:
            return []

        # Collect entity names for cross-referencing
        entity_names = [e.get("name", "").lower() for e in extracted_entities if e.get("name")]

        # Annotate snippets with entity refs found in their text
        for snippet in snippets:
            refs = [n for n in entity_names if n and n in snippet.text.lower()]
            snippet.entity_refs = refs if refs else None

        # Persist snippets to SQL (best-effort)
        if self.store:
            try:
                self._persist_snippets_to_db(
                    snippets, page_uuid, primary_entity_id,
                )
            except Exception as e:
                self.logger.warning(f"Failed to persist semantic snippets to DB: {e}")

        # Build Qdrant embedding entries
        snippet_entries = self.llm_extractor.build_snippet_embeddings(
            snippets=snippets,
            source_url=url,
            page_type=page_type,
            entity_name=self.profile.name,
            entity_type=self.profile.entity_type,
            page_uuid=page_uuid,
        )
        self.logger.info(
            f"Generated {len(snippet_entries)} semantic-snippet embeddings for {url}"
        )
        return snippet_entries

    def _persist_snippets_to_db(
        self,
        snippets,
        page_uuid: Optional[str],
        entity_id: Optional[str],
    ):
        """Store semantic snippets in the SQL database."""
        import uuid as _uuid
        from ..database.models import SemanticSnippet

        session_maker = getattr(self.store, "Session", None)
        if not session_maker:
            return

        with session_maker() as session:
            for snippet in snippets:
                row = SemanticSnippet(
                    id=_uuid.uuid4(),
                    text=snippet.text,
                    chunk_index=snippet.chunk_index or 0,
                    prev_context=snippet.prev_context,
                    next_context=snippet.next_context,
                    topic_context=snippet.topic_context,
                    source_url=snippet.source_url,
                    page_id=_uuid.UUID(page_uuid) if page_uuid else None,
                    entity_id=_uuid.UUID(entity_id) if entity_id else None,
                    entity_refs_json=snippet.entity_refs,
                )
                session.add(row)
            session.commit()

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
            llm_score = float(link.get("llm_score", 0) or 0)

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
            links = self._extract_links(url, html, {}, depth) if depth < self.max_depth else []
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

    def _extract_links(
        self,
        url: str,
        html: str,
        metadata: Optional[dict] = None,
        depth: int = 0,
    ) -> List[Dict]:
        """
        Parse outgoing links from the page. Metadata/depth are accepted for compatibility.
        """
        links: List[Dict] = []
        if not html:
            return links
        try:
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a.get("href")
                text = a.get_text(strip=True)[:500] if a.get_text() else ""
                links.append(
                    {
                        "href": urljoin(url, href),
                        "text": text,
                        "depth": depth + 1,
                        "reason": "page_link",
                        "score": 0,
                    }
                )
        except Exception as e:
            self.logger.debug(f"_extract_links failed: {e}")
        return links

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
        finding_ids: List[Tuple[Dict, Optional[int], Optional[str]]],
        entities: List[Dict],
        entity_id_map: Dict[tuple, Any],
        page_type: str,
        page_uuid: Optional[str],
    ):
        try:
            entries = self.llm_extractor.build_embeddings_for_page(
                url=url,
                metadata=metadata,
                summary=summary,
                text_content=text_content,
                findings_with_ids=[(f, iid, ent_id) for (f, iid, ent_id) in finding_ids],
                page_type=page_type,
                entity_name=self.profile.name,
                entity_type=self.profile.entity_type,
                page_uuid=page_uuid,
            )
            if entities:
                entries.extend(
                    self.llm_extractor.build_embeddings_for_entities(
                        entities=entities,
                        source_url=url,
                        entity_type=self.profile.entity_type,
                        entity_id_map=entity_id_map,
                        page_uuid=page_uuid,
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
