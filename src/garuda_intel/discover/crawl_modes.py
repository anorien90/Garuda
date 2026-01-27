"""
Crawl Modes and Entity-Aware Crawler.
Handles targeted crawling strategies based on entity data completeness.
"""

import logging
from enum import Enum
from typing import Dict, List, Any, Optional

from ..database.store import PersistenceStore
from ..extractor.llm import LLMIntelExtractor
from ..types.entity.profile import EntityProfile


class CrawlMode(str, Enum):
    """Crawling modes for different entity discovery scenarios."""
    DISCOVERY = "discovery"  # Find seed URLs for unknown entity
    TARGETING = "targeting"  # Crawl to fill gaps in known entity data
    EXPANSION = "expansion"  # Find related entities from known seed


class EntityAwareCrawler:
    """
    Entity-aware crawler that analyzes data gaps and generates targeted crawl strategies.
    """

    def __init__(self, store: PersistenceStore, llm_extractor: LLMIntelExtractor):
        """
        Initialize entity-aware crawler.
        
        Args:
            store: Database persistence store
            llm_extractor: LLM extractor for query generation
        """
        self.store = store
        self.llm_extractor = llm_extractor
        self.logger = logging.getLogger(__name__)

    def analyze_entity_gaps(self, entity_id: str) -> Dict[str, Any]:
        """
        Analyze an entity to identify missing data fields.
        
        Args:
            entity_id: Entity UUID to analyze
            
        Returns:
            Dictionary containing:
            - missing_fields: List of field names that are empty
            - completeness: Percentage of expected fields filled (0-1)
            - priority_gaps: Fields that should be filled first
        """
        # Get entity intelligence data (use min confidence to filter low-quality data)
        intel_records = self.store.get_intelligence(entity_id=entity_id, min_confidence=0.5)
        
        if not intel_records:
            return {
                "missing_fields": ["basic_info", "persons", "locations", "financials", "products"],
                "completeness": 0.0,
                "priority_gaps": ["basic_info", "locations"],
                "has_data": False,
            }

        # Aggregate all intelligence data
        aggregated = {
            "basic_info": {},
            "persons": [],
            "jobs": [],
            "metrics": [],
            "locations": [],
            "financials": [],
            "products": [],
            "events": [],
            "relationships": [],
        }

        for record in intel_records:
            data = record.get("data", {})
            # Merge basic_info
            if data.get("basic_info"):
                aggregated["basic_info"].update(data["basic_info"])
            
            # Extend lists
            for key in ["persons", "jobs", "metrics", "locations", "financials", "products", "events", "relationships"]:
                items = data.get(key, [])
                if isinstance(items, list):
                    aggregated[key].extend(items)

        # Define expected fields for each category
        expected_basic_fields = ["official_name", "ticker", "industry", "description", "founded", "website"]
        
        # Identify missing fields
        missing_fields = []
        priority_gaps = []
        
        # Check basic_info completeness
        basic_info = aggregated.get("basic_info", {})
        missing_basic = [f for f in expected_basic_fields if not basic_info.get(f)]
        if missing_basic:
            missing_fields.append("basic_info")
            if "official_name" in missing_basic or "description" in missing_basic:
                priority_gaps.append("basic_info")
        
        # Check list fields
        list_fields = ["persons", "locations", "financials", "products"]
        for field in list_fields:
            if not aggregated.get(field):
                missing_fields.append(field)
                if field in ["persons", "locations"]:
                    priority_gaps.append(field)
        
        # Calculate completeness
        list_categories = ["persons", "jobs", "metrics", "locations", "financials", "products", "events", "relationships"]
        total_categories = 1 + len(list_categories)  # basic_info + list categories
        filled_categories = 0
        
        if basic_info and any(basic_info.values()):
            filled_categories += 1
        for key in list_categories:
            if aggregated.get(key):
                filled_categories += 1
        
        completeness = filled_categories / total_categories
        
        return {
            "missing_fields": missing_fields,
            "completeness": completeness,
            "priority_gaps": priority_gaps,
            "has_data": bool(intel_records),
            "data_summary": aggregated,
        }

    def generate_targeted_queries(self, entity_profile: EntityProfile, gaps: Dict) -> List[str]:
        """
        Generate search queries to fill specific data gaps.
        
        Args:
            entity_profile: Entity profile with name and type
            gaps: Gap analysis from analyze_entity_gaps()
            
        Returns:
            List of search query strings
        """
        queries = []
        entity_name = entity_profile.name
        location = entity_profile.location_hint or ""
        
        priority_gaps = gaps.get("priority_gaps", [])
        missing_fields = gaps.get("missing_fields", [])
        
        # If we have no data, start with discovery queries
        if not gaps.get("has_data", True):
            queries.extend([
                f'"{entity_name}" official website',
                f'"{entity_name}" company information',
                f'"{entity_name}" about',
            ])
            if location:
                queries.append(f'"{entity_name}" {location}')
            return queries
        
        # Generate targeted queries for priority gaps
        if "basic_info" in priority_gaps:
            queries.extend([
                f'"{entity_name}" company profile',
                f'"{entity_name}" industry sector',
                f'"{entity_name}" official website about',
            ])
        
        if "persons" in priority_gaps or "persons" in missing_fields:
            queries.extend([
                f'"{entity_name}" leadership team',
                f'"{entity_name}" CEO founder',
                f'"{entity_name}" executives management',
            ])
        
        if "locations" in priority_gaps or "locations" in missing_fields:
            queries.extend([
                f'"{entity_name}" headquarters address',
                f'"{entity_name}" office locations',
                f'"{entity_name}" contact information',
            ])
        
        if "financials" in missing_fields:
            queries.extend([
                f'"{entity_name}" revenue earnings',
                f'"{entity_name}" financial results',
                f'"{entity_name}" annual report',
            ])
        
        if "products" in missing_fields:
            queries.extend([
                f'"{entity_name}" products services',
                f'"{entity_name}" solutions offerings',
            ])
        
        # Deduplicate while preserving order
        seen = set()
        unique_queries = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)
        
        return unique_queries[:10]  # Limit to top 10 queries

    def crawl_for_entity(
        self, 
        entity_profile: EntityProfile, 
        mode: CrawlMode = CrawlMode.TARGETING,
        entity_id: Optional[str] = None,
    ) -> Dict:
        """
        Execute entity-aware crawl based on mode.
        
        Args:
            entity_profile: Entity profile with name and type
            mode: Crawling mode (DISCOVERY, TARGETING, EXPANSION)
            entity_id: Optional entity ID for TARGETING mode
            
        Returns:
            Dictionary containing:
            - mode: The crawl mode used
            - queries: List of search queries generated
            - strategy: Description of crawl strategy
            - gaps: Gap analysis (for TARGETING mode)
        """
        strategy = ""
        queries = []
        gaps = None
        
        if mode == CrawlMode.DISCOVERY:
            # Generate broad discovery queries
            strategy = "Discovery mode: Finding seed URLs for unknown entity"
            queries = self.llm_extractor.generate_search_queries(
                entity_profile.name, 
                entity_profile.location_hint
            )
            
            # Add official domain queries if available
            if entity_profile.official_domains:
                for domain in entity_profile.official_domains:
                    queries.insert(0, f'site:{domain} about')
        
        elif mode == CrawlMode.TARGETING:
            # Analyze gaps and generate targeted queries
            if not entity_id:
                self.logger.warning("TARGETING mode requires entity_id, falling back to DISCOVERY")
                return self.crawl_for_entity(entity_profile, CrawlMode.DISCOVERY)
            
            strategy = "Targeting mode: Filling data gaps in known entity"
            gaps = self.analyze_entity_gaps(entity_id)
            queries = self.generate_targeted_queries(entity_profile, gaps)
            
        elif mode == CrawlMode.EXPANSION:
            # Find related entities
            strategy = "Expansion mode: Finding related entities from known seed"
            queries = [
                f'"{entity_profile.name}" partners collaborations',
                f'"{entity_profile.name}" acquisitions investments',
                f'"{entity_profile.name}" subsidiaries divisions',
                f'"{entity_profile.name}" competitors industry',
                f'"{entity_profile.name}" customers clients',
            ]
            
            # Add alias-based queries
            for alias in entity_profile.aliases:
                queries.append(f'"{alias}" related companies')
        
        result = {
            "mode": mode.value,
            "queries": queries,
            "strategy": strategy,
            "entity_name": entity_profile.name,
        }
        
        if gaps:
            result["gaps"] = gaps
        
        self.logger.info(f"Generated {len(queries)} queries for {mode.value} mode on {entity_profile.name}")
        
        return result
