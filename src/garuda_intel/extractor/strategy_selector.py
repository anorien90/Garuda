"""
Entity-Specific Extraction Strategies.

This module provides specialized extraction strategies optimized for different
entity types and page types.
"""

import logging
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

from ..types.entity import EntityProfile, EntityType


class ExtractionStrategy(ABC):
    """Base class for extraction strategies."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @abstractmethod
    def get_extraction_prompt(self, profile: EntityProfile, text: str, page_type: str, url: str) -> str:
        """
        Generate extraction prompt optimized for this strategy.
        
        Args:
            profile: Entity profile being researched
            text: Page text to extract from
            page_type: Type of page (e.g., 'official', 'news', 'registry')
            url: Page URL
            
        Returns:
            Optimized extraction prompt
        """
        pass
    
    @abstractmethod
    def get_priority_fields(self) -> List[str]:
        """
        Get priority fields for this strategy.
        
        Returns:
            List of field paths in priority order
        """
        pass
    
    def get_validation_rules(self) -> Dict[str, Any]:
        """
        Get validation rules specific to this strategy.
        
        Returns:
            Dictionary of validation rules
        """
        return {}
    
    def post_process(self, extracted: Dict) -> Dict:
        """
        Post-process extracted intelligence.
        
        Args:
            extracted: Raw extracted intelligence
            
        Returns:
            Processed intelligence
        """
        return extracted


class CompanyExtractionStrategy(ExtractionStrategy):
    """Optimized for company/organization entities."""
    
    def get_extraction_prompt(self, profile: EntityProfile, text: str, page_type: str, url: str) -> str:
        """Generate company-optimized extraction prompt."""
        
        # Adjust focus based on page type
        if page_type == "official":
            focus = """
Focus particularly on:
- Official legal name and branding
- Leadership team and executives (names, titles, bios)
- Products and services offered
- Corporate structure and subsidiaries
- Contact information and locations
"""
        elif page_type == "news":
            focus = """
Focus particularly on:
- Company announcements and events
- Executive changes or appointments
- Product launches or updates
- Financial results or funding
- Partnerships or acquisitions
"""
        elif page_type == "registry":
            focus = """
Focus particularly on:
- Exact legal company name
- Registration numbers and identifiers
- Registered addresses
- Directors and officers
- Financial filings and reports
"""
        else:
            focus = """
Focus particularly on:
- Company name and description
- Key people and their roles
- Business activities and products
- Locations and contact info
"""
        
        caution = ""
        if "registry" in page_type or any(x in url.lower() for x in ["opencorporates", "northdata", "companies house"]):
            caution = """
CRITICAL: This appears to be a registry or directory listing multiple entities.
Extract ONLY data for "{company_name}". Ignore similar companies or search results.
Verify entity names match before extracting.
""".format(company_name=profile.name)
        
        prompt = f"""
You are an expert business intelligence analyst. Extract comprehensive information about the company "{profile.name}".

ENTITY DETAILS:
- Name: {profile.name}
- Type: Company/Organization
- Location hint: {profile.location_hint}

PAGE CONTEXT:
- Type: {page_type}
- URL: {url}

{caution}

{focus}

TEXT TO ANALYZE:
{text[:4000]}

Return ONLY a JSON object with this exact schema (omit empty fields):
{{
  "basic_info": {{
    "official_name": "",
    "ticker": "",
    "industry": "",
    "description": "",
    "founded": "",
    "website": "",
    "employee_count": ""
  }},
  "persons": [
    {{"name": "", "title": "", "role": "executive|founder|board", "bio": ""}}
  ],
  "locations": [
    {{"address": "", "city": "", "country": "", "type": "headquarters|office|facility"}}
  ],
  "financials": [
    {{"year": "", "revenue": "", "currency": "USD", "profit": "", "funding": ""}}
  ],
  "products": [
    {{"name": "", "description": "", "status": "active|discontinued"}}
  ],
  "events": [
    {{"title": "", "date": "", "description": "", "type": "launch|acquisition|funding"}}
  ],
  "metrics": [
    {{"type": "employees|customers|users", "value": "", "unit": "", "date": ""}}
  ],
  "relationships": [
    {{"source": "{profile.name}", "target": "", "relation_type": "subsidiary|partner|customer", "description": ""}}
  ]
}}

Be precise and factual. Extract only information explicitly stated in the text.
"""
        return prompt
    
    def get_priority_fields(self) -> List[str]:
        """Get priority fields for company extraction."""
        return [
            "basic_info.official_name",
            "basic_info.industry",
            "basic_info.website",
            "persons",
            "locations",
            "basic_info.founded",
            "financials",
            "products",
            "metrics",
            "events",
            "relationships"
        ]
    
    def get_validation_rules(self) -> Dict[str, Any]:
        """Get company-specific validation rules."""
        return {
            "required_fields": ["basic_info.official_name"],
            "numeric_fields": ["basic_info.employee_count", "metrics.value"],
            "date_fields": ["basic_info.founded", "events.date", "financials.year"],
            "url_fields": ["basic_info.website"],
        }


class PersonExtractionStrategy(ExtractionStrategy):
    """Optimized for person/individual entities."""
    
    def get_extraction_prompt(self, profile: EntityProfile, text: str, page_type: str, url: str) -> str:
        """Generate person-optimized extraction prompt."""
        
        if page_type == "official":
            focus = """
Focus particularly on:
- Full name and titles
- Current position and employer
- Professional background and biography
- Education and qualifications
- Contact information
"""
        elif page_type == "news":
            focus = """
Focus particularly on:
- Recent activities or announcements
- Career moves or appointments
- Achievements or recognitions
- Quotes or statements
- Affiliations and relationships
"""
        else:
            focus = """
Focus particularly on:
- Personal and professional details
- Career history and positions
- Affiliations and memberships
- Notable achievements
"""
        
        prompt = f"""
You are an expert researcher analyzing information about the person "{profile.name}".

ENTITY DETAILS:
- Name: {profile.name}
- Type: Person/Individual
- Location hint: {profile.location_hint}

PAGE CONTEXT:
- Type: {page_type}
- URL: {url}

{focus}

TEXT TO ANALYZE:
{text[:4000]}

Return ONLY a JSON object with this schema (omit empty fields):
{{
  "basic_info": {{
    "official_name": "",
    "title": "",
    "current_employer": "",
    "bio": "",
    "nationality": "",
    "education": ""
  }},
  "persons": [
    {{"name": "", "relationship": "colleague|mentor|partner", "description": ""}}
  ],
  "jobs": [
    {{"title": "", "company": "", "start_date": "", "end_date": "", "description": ""}}
  ],
  "events": [
    {{"title": "", "date": "", "description": "", "type": "award|appointment|publication"}}
  ],
  "locations": [
    {{"city": "", "country": "", "type": "residence|office"}}
  ],
  "relationships": [
    {{"source": "{profile.name}", "target": "", "relation_type": "works_for|founded|advises", "description": ""}}
  ]
}}

Extract only factual information explicitly stated in the text.
"""
        return prompt
    
    def get_priority_fields(self) -> List[str]:
        """Get priority fields for person extraction."""
        return [
            "basic_info.official_name",
            "basic_info.title",
            "basic_info.current_employer",
            "basic_info.bio",
            "jobs",
            "events",
            "relationships",
            "persons"
        ]


class NewsExtractionStrategy(ExtractionStrategy):
    """Optimized for news/event entities."""
    
    def get_extraction_prompt(self, profile: EntityProfile, text: str, page_type: str, url: str) -> str:
        """Generate news-optimized extraction prompt."""
        
        prompt = f"""
You are an expert news analyst extracting structured information from a news article about "{profile.name}".

ARTICLE CONTEXT:
- Topic: {profile.name}
- URL: {url}

Focus on:
- Main events or developments described
- Key people mentioned and their roles
- Organizations involved
- Dates and timeline
- Quotes and sources
- Impact and implications

TEXT TO ANALYZE:
{text[:4000]}

Return ONLY a JSON object with this schema (omit empty fields):
{{
  "basic_info": {{
    "description": "",
    "category": "business|technology|politics|general"
  }},
  "events": [
    {{"title": "", "date": "", "description": "", "impact": "", "type": "announcement|incident|achievement"}}
  ],
  "persons": [
    {{"name": "", "title": "", "role": "source|subject|analyst", "quote": ""}}
  ],
  "relationships": [
    {{"source": "", "target": "", "relation_type": "involves|affects|partners", "description": ""}}
  ],
  "metrics": [
    {{"type": "", "value": "", "unit": "", "context": ""}}
  ]
}}

Extract factual information and clearly attribute quotes to their sources.
"""
        return prompt
    
    def get_priority_fields(self) -> List[str]:
        """Get priority fields for news extraction."""
        return [
            "events",
            "persons",
            "relationships",
            "basic_info.description",
            "metrics"
        ]


class TopicExtractionStrategy(ExtractionStrategy):
    """Optimized for topic/concept entities."""
    
    def get_extraction_prompt(self, profile: EntityProfile, text: str, page_type: str, url: str) -> str:
        """Generate topic-optimized extraction prompt."""
        
        prompt = f"""
You are an expert knowledge analyst extracting structured information about the topic "{profile.name}".

TOPIC DETAILS:
- Subject: {profile.name}
- URL: {url}

Focus on:
- Definition and explanation
- Key concepts and principles
- Historical development
- Related topics and concepts
- Notable contributors or researchers
- Applications and examples

TEXT TO ANALYZE:
{text[:4000]}

Return ONLY a JSON object with this schema (omit empty fields):
{{
  "basic_info": {{
    "description": "",
    "category": "",
    "definition": ""
  }},
  "events": [
    {{"title": "", "date": "", "description": "", "significance": ""}}
  ],
  "persons": [
    {{"name": "", "contribution": "", "role": "researcher|inventor|contributor"}}
  ],
  "relationships": [
    {{"source": "{profile.name}", "target": "", "relation_type": "related_to|part_of|leads_to", "description": ""}}
  ],
  "products": [
    {{"name": "", "description": "", "application": ""}}
  ]
}}

Be comprehensive and focus on factual, verifiable information.
"""
        return prompt
    
    def get_priority_fields(self) -> List[str]:
        """Get priority fields for topic extraction."""
        return [
            "basic_info.description",
            "basic_info.definition",
            "events",
            "persons",
            "relationships",
            "products"
        ]


class StrategySelector:
    """Selects optimal extraction strategy based on entity and page type."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Strategy registry
        self._strategies = {
            EntityType.COMPANY: CompanyExtractionStrategy(),
            EntityType.PERSON: PersonExtractionStrategy(),
            EntityType.NEWS: NewsExtractionStrategy(),
            EntityType.TOPIC: TopicExtractionStrategy(),
        }
        
        # Page type modifiers (future enhancement)
        self._page_type_modifiers = {
            "official": {"boost_basic_info": 1.2},
            "news": {"boost_events": 1.3},
            "registry": {"boost_basic_info": 1.5, "strict_name_matching": True},
            "social": {"boost_persons": 1.2, "boost_relationships": 1.3},
        }
    
    def select_strategy(self, entity_type: EntityType, page_type: str = "") -> ExtractionStrategy:
        """
        Select optimal extraction strategy based on entity and page type.
        
        Args:
            entity_type: Type of entity being researched
            page_type: Type of page being analyzed
            
        Returns:
            ExtractionStrategy instance optimized for this context
        """
        # Get base strategy for entity type
        strategy = self._strategies.get(entity_type)
        
        if not strategy:
            # Default to company strategy
            self.logger.warning(f"No strategy for entity type {entity_type}, using company strategy")
            strategy = self._strategies[EntityType.COMPANY]
        
        # Apply page type modifiers (future enhancement)
        # Could create modified strategy instances based on page_type
        
        return strategy
    
    def get_all_strategies(self) -> Dict[EntityType, ExtractionStrategy]:
        """Get all registered strategies."""
        return self._strategies
    
    def register_strategy(self, entity_type: EntityType, strategy: ExtractionStrategy) -> None:
        """
        Register a custom extraction strategy.
        
        Args:
            entity_type: Entity type for this strategy
            strategy: ExtractionStrategy instance
        """
        self._strategies[entity_type] = strategy
        self.logger.info(f"Registered custom strategy for {entity_type}")
