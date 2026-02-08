"""
Entity Gap Analyzer Service.

Analyzes existing entity data to identify missing information and generate
targeted crawling strategies to fill those gaps.
"""

import logging
from typing import Dict, Any, List, Set, Optional
from datetime import datetime
from collections import defaultdict
import json

from ..database.store import PersistenceStore


logger = logging.getLogger(__name__)


class EntityGapAnalyzer:
    """
    Analyzes entities to identify missing data fields and generate
    intelligent queries to fill those gaps.
    """
    
    # Define expected fields per entity type
    # Using string keys for consistency since not all types are in EntityType enum
    EXPECTED_FIELDS = {
        'company': {
            'critical': ['official_name', 'industry', 'website'],
            'important': ['ticker', 'founded', 'description', 'headquarters'],
            'supplementary': ['revenue', 'employees', 'ceo', 'products']
        },
        'person': {
            'critical': ['full_name'],
            'important': ['title', 'organization', 'location'],
            'supplementary': ['bio', 'education', 'email', 'social_media']
        },
        'product': {
            'critical': ['name', 'manufacturer'],
            'important': ['description', 'category', 'launch_date'],
            'supplementary': ['price', 'specifications', 'reviews']
        },
        'organization': {
            'critical': ['name', 'type'],
            'important': ['description', 'location', 'founded'],
            'supplementary': ['mission', 'leadership', 'size']
        },
        'location': {
            'critical': ['name', 'country'],
            'important': ['coordinates', 'type'],
            'supplementary': ['population', 'area', 'timezone']
        },
        'topic': {
            'critical': ['name', 'description'],
            'important': ['category', 'keywords'],
            'supplementary': ['related_topics', 'references']
        },
        'news': {
            'critical': ['title', 'date'],
            'important': ['source', 'summary'],
            'supplementary': ['authors', 'categories', 'entities_mentioned']
        }
    }
    
    def __init__(self, store: PersistenceStore):
        """
        Initialize the gap analyzer.
        
        Args:
            store: Database store for querying entities
        """
        self.store = store
        self.logger = logging.getLogger(__name__)
    
    def analyze_entity_gaps(self, entity_id: str) -> Dict[str, Any]:
        """
        Analyze a specific entity to identify data gaps.
        
        Args:
            entity_id: UUID of the entity to analyze
            
        Returns:
            Dictionary with gap analysis including missing fields, suggestions, queries
        """
        # Validate entity_id format
        import uuid as uuid_module
        try:
            # Ensure entity_id is a valid UUID string
            if not entity_id or not isinstance(entity_id, str):
                return {"error": "Invalid entity_id: must be a non-empty string"}
            # Try to parse as UUID to validate format
            uuid_module.UUID(entity_id)
        except (ValueError, AttributeError, TypeError) as e:
            return {"error": f"Invalid entity_id format: {entity_id}"}
        
        with self.store.Session() as session:
            from ..database.models import Entity, Intelligence
            
            # Get entity
            entity = session.query(Entity).filter(Entity.id == entity_id).first()
            if not entity:
                return {"error": "Entity not found"}
            
            # Determine entity type
            entity_type = self._normalize_entity_type(entity.kind)
            
            # Get all intelligence for this entity
            intel_records = session.query(Intelligence).filter(
                Intelligence.entity_id == entity_id
            ).all()
            
            # Aggregate all data
            all_data = self._aggregate_entity_data(entity, intel_records)
            
            # Identify gaps
            gaps = self._identify_gaps(all_data, entity_type)
            
            # Generate targeted queries for gaps
            queries = self._generate_gap_queries(entity.name, entity_type, gaps)
            
            # Score gaps by priority
            prioritized_gaps = self._prioritize_gaps(gaps, entity_type)
            
            # Suggest data sources
            sources = self._suggest_sources(entity.name, entity_type, gaps)
            
            return {
                "entity_id": str(entity_id),
                "entity_name": entity.name,
                "entity_type": entity.kind,
                "completeness_score": self._calculate_completeness(all_data, entity_type),
                "missing_fields": gaps,
                "prioritized_gaps": prioritized_gaps,
                "suggested_queries": queries,
                "suggested_sources": sources,
                "last_updated": entity.updated_at.isoformat() if entity.updated_at else None,
                "intelligence_count": len(intel_records)
            }
    
    def analyze_all_entities(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Analyze multiple entities to identify those with the most critical gaps.
        
        Args:
            limit: Maximum number of entities to analyze
            
        Returns:
            List of entities with gap analysis, sorted by gap priority
        """
        with self.store.Session() as session:
            from ..database.models import Entity
            
            # Get recent or high-priority entities
            entities = session.query(Entity).order_by(
                Entity.updated_at.desc()
            ).limit(limit).all()
            
            results = []
            for entity in entities:
                analysis = self.analyze_entity_gaps(str(entity.id))
                if "error" not in analysis:
                    results.append(analysis)
            
            # Sort by gap criticality (lowest completeness first)
            results.sort(key=lambda x: x.get("completeness_score", 100))
            
            return results
    
    def generate_crawl_plan(
        self, 
        entity_name: Optional[str] = None, 
        entity_type: Optional[str] = None,
        entity: Optional[Any] = None,
        task_type: Optional[str] = None,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate an intelligent crawl plan for a given entity.
        
        This is the entry point for "lookup known entity and crawl missing data".
        Supports two modes of operation:
        1. Legacy: Pass entity_name (and optionally entity_type) - will lookup entity in DB
        2. New: Pass entity object directly - skips lookup and uses provided entity
        
        Args:
            entity_name: Name of entity to research (e.g., "Bill Gates") - used if entity not provided
            entity_type: Optional entity type hint - used if entity not provided
            entity: Optional Entity model instance - if provided, uses this directly
            task_type: Optional task type (e.g., "fill_gap", "investigate") for context
            context: Optional context/reason for the crawl
            
        Returns:
            Crawl plan with queries, sources, and strategy
        """
        # Validate parameters - need either entity or entity_name
        if entity is None and entity_name is None:
            raise ValueError("Must provide either 'entity' or 'entity_name' parameter")
        
        # If entity object provided directly, use it
        if entity is not None:
            # Entity exists - analyze gaps
            self.logger.info(f"Using provided entity '{entity.name}' - analyzing gaps")
            analysis = self.analyze_entity_gaps(str(entity.id))
            
            plan = {
                "mode": "gap_filling",
                "entity_id": str(entity.id),
                "entity_name": entity.name,
                "analysis": analysis,
                "strategy": "targeted",
                "queries": analysis.get("suggested_queries", []),
                "sources": analysis.get("suggested_sources", []),
                "priority": "fill_critical_gaps"
            }
            
            # Add task context if provided
            if task_type:
                plan["task_type"] = task_type
            if context:
                plan["context"] = context
            
            return plan
        
        # Legacy path: lookup entity by name
        with self.store.Session() as session:
            from ..database.models import Entity
            
            found_entity = session.query(Entity).filter(
                Entity.name.ilike(f"%{entity_name}%")
            ).first()
            
            if found_entity:
                # Entity exists - analyze gaps
                self.logger.info(f"Found existing entity '{found_entity.name}' - analyzing gaps")
                analysis = self.analyze_entity_gaps(str(found_entity.id))
                
                plan = {
                    "mode": "gap_filling",
                    "entity_id": str(found_entity.id),
                    "entity_name": found_entity.name,
                    "analysis": analysis,
                    "strategy": "targeted",
                    "queries": analysis.get("suggested_queries", []),
                    "sources": analysis.get("suggested_sources", []),
                    "priority": "fill_critical_gaps"
                }
                
                # Add task context if provided
                if task_type:
                    plan["task_type"] = task_type
                if context:
                    plan["context"] = context
                
                return plan
            else:
                # Entity doesn't exist - discovery mode
                self.logger.info(f"New entity '{entity_name}' - starting discovery")
                
                # Infer entity type if not provided
                if not entity_type:
                    entity_type = self._infer_entity_type(entity_name)
                
                # Generate discovery queries
                queries = self._generate_discovery_queries(entity_name, entity_type)
                sources = self._suggest_sources(entity_name, entity_type, [])
                
                plan = {
                    "mode": "discovery",
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "strategy": "comprehensive",
                    "queries": queries,
                    "sources": sources,
                    "priority": "establish_baseline"
                }
                
                # Add task context if provided
                if task_type:
                    plan["task_type"] = task_type
                if context:
                    plan["context"] = context
                
                return plan
    
    def _aggregate_entity_data(self, entity, intel_records) -> Dict[str, Any]:
        """Aggregate all data about an entity from entity record and intelligence."""
        aggregated = {
            "name": entity.name,
            "kind": entity.kind,
        }
        
        # Add data from entity.data
        if entity.data:
            aggregated.update(entity.data)
        
        # Add metadata
        if entity.metadata_json:
            aggregated.update(entity.metadata_json)
        
        # Aggregate intelligence records
        for intel in intel_records:
            if intel.data:
                # Merge basic_info
                if "basic_info" in intel.data:
                    for k, v in intel.data["basic_info"].items():
                        if v and k not in aggregated:
                            aggregated[k] = v
                
                # Collect list fields
                for list_field in ["persons", "locations", "financials", "products", "events"]:
                    if list_field in intel.data and intel.data[list_field]:
                        if list_field not in aggregated:
                            aggregated[list_field] = []
                        aggregated[list_field].extend(intel.data[list_field])
        
        return aggregated
    
    def _identify_gaps(self, data: Dict[str, Any], entity_type: str) -> List[Dict[str, str]]:
        """Identify missing fields based on entity type."""
        gaps = []
        
        expected = self.EXPECTED_FIELDS.get(entity_type, {})
        
        for priority in ['critical', 'important', 'supplementary']:
            fields = expected.get(priority, [])
            for field in fields:
                # Check various possible field names
                if not self._has_field(data, field):
                    gaps.append({
                        "field": field,
                        "priority": priority,
                        "category": self._categorize_field(field)
                    })
        
        return gaps
    
    def _has_field(self, data: Dict, field: str) -> bool:
        """Check if a field exists and has meaningful value."""
        # Direct check
        if field in data and data[field]:
            return True
        
        # Check common variations
        variations = [
            field.replace("_", ""),
            field.replace("_", " "),
            field.lower(),
            field.upper()
        ]
        
        for var in variations:
            if var in data and data[var]:
                return True
        
        return False
    
    def _categorize_field(self, field: str) -> str:
        """Categorize field type for query generation."""
        categories = {
            "identity": ["name", "official_name", "full_name"],
            "business": ["industry", "ticker", "revenue", "employees"],
            "location": ["headquarters", "location", "address", "country"],
            "temporal": ["founded", "launch_date", "established"],
            "contact": ["website", "email", "phone", "social_media"],
            "descriptive": ["description", "bio", "mission"],
            "hierarchical": ["ceo", "leadership", "organization", "manufacturer"]
        }
        
        for category, fields in categories.items():
            if any(f in field.lower() for f in fields):
                return category
        
        return "other"
    
    def _generate_gap_queries(self, entity_name: str, entity_type: str, gaps: List[Dict]) -> List[str]:
        """Generate targeted search queries to fill specific gaps."""
        queries = []
        
        # Group gaps by category
        gap_categories = defaultdict(list)
        for gap in gaps:
            gap_categories[gap["category"]].append(gap["field"])
        
        # Generate queries per category
        for category, fields in gap_categories.items():
            if category == "business":
                queries.append(f'"{entity_name}" revenue employees industry')
                queries.append(f'"{entity_name}" company information')
            elif category == "location":
                queries.append(f'"{entity_name}" headquarters location address')
            elif category == "temporal":
                queries.append(f'"{entity_name}" founded history')
            elif category == "contact":
                queries.append(f'"{entity_name}" official website contact')
            elif category == "descriptive":
                queries.append(f'"{entity_name}" about description overview')
            elif category == "hierarchical":
                queries.append(f'"{entity_name}" leadership team management')
        
        # Add entity-type specific queries
        if entity_type == 'company':
            queries.append(f'"{entity_name}" investor relations')
            queries.append(f'"{entity_name}" annual report')
        elif entity_type == 'person':
            queries.append(f'"{entity_name}" biography')
            queries.append(f'"{entity_name}" linkedin profile')
        
        return list(set(queries))  # Remove duplicates
    
    def _generate_discovery_queries(self, entity_name: str, entity_type: str) -> List[str]:
        """Generate comprehensive discovery queries for a new entity."""
        queries = [
            f'"{entity_name}"',
            f'"{entity_name}" official',
            f'"{entity_name}" information',
        ]
        
        if entity_type == 'company':
            queries.extend([
                f'"{entity_name}" company',
                f'"{entity_name}" investor relations',
                f'"{entity_name}" about us',
                f'"{entity_name}" corporate information'
            ])
        elif entity_type == 'person':
            queries.extend([
                f'"{entity_name}" biography',
                f'"{entity_name}" profile',
                f'"{entity_name}" linkedin',
                f'"{entity_name}" about'
            ])
        elif entity_type == 'product':
            queries.extend([
                f'"{entity_name}" product',
                f'"{entity_name}" specifications',
                f'"{entity_name}" details'
            ])
        
        return queries
    
    def _prioritize_gaps(self, gaps: List[Dict], entity_type: str) -> List[Dict]:
        """Score and prioritize gaps by importance and findability."""
        scored_gaps = []
        
        for gap in gaps:
            priority_score = {
                'critical': 10,
                'important': 5,
                'supplementary': 1
            }.get(gap['priority'], 0)
            
            # Estimate findability based on field type
            findability_score = self._estimate_findability(gap['field'], entity_type)
            
            combined_score = priority_score * findability_score
            
            scored_gaps.append({
                **gap,
                'score': combined_score,
                'findability': findability_score
            })
        
        # Sort by score descending
        scored_gaps.sort(key=lambda x: x['score'], reverse=True)
        
        return scored_gaps
    
    def _estimate_findability(self, field: str, entity_type: str) -> float:
        """
        Estimate how likely we are to find this field online.
        
        Returns: 0.0 to 1.0
        """
        # High findability fields
        high = ['website', 'official_name', 'industry', 'description', 'location']
        # Medium findability fields
        medium = ['ticker', 'founded', 'ceo', 'headquarters', 'title']
        # Low findability fields
        low = ['revenue', 'employees', 'email', 'phone']
        
        if any(h in field.lower() for h in high):
            return 0.9
        elif any(m in field.lower() for m in medium):
            return 0.6
        elif any(l in field.lower() for l in low):
            return 0.3
        else:
            return 0.5
    
    def _suggest_sources(self, entity_name: str, entity_type: str, gaps: List[Dict]) -> List[Dict[str, str]]:
        """Suggest specific sources to find missing data."""
        sources = []
        
        if entity_type == 'company':
            sources.append({
                "name": "Official Website",
                "url_pattern": f"site:{{company_domain}} about",
                "fields": ["description", "headquarters", "products"]
            })
            sources.append({
                "name": "LinkedIn Company Page",
                "url_pattern": f"site:linkedin.com/company {entity_name}",
                "fields": ["industry", "employees", "description"]
            })
            sources.append({
                "name": "Crunchbase",
                "url_pattern": f"site:crunchbase.com {entity_name}",
                "fields": ["founded", "funding", "employees", "headquarters"]
            })
            sources.append({
                "name": "Wikipedia",
                "url_pattern": f"site:wikipedia.org {entity_name}",
                "fields": ["description", "founded", "history"]
            })
        
        elif entity_type == 'person':
            sources.append({
                "name": "LinkedIn Profile",
                "url_pattern": f"site:linkedin.com/in {entity_name}",
                "fields": ["title", "organization", "bio", "education"]
            })
            sources.append({
                "name": "Wikipedia",
                "url_pattern": f"site:wikipedia.org {entity_name}",
                "fields": ["bio", "achievements", "background"]
            })
            sources.append({
                "name": "Official Bio Pages",
                "url_pattern": f'"{entity_name}" biography',
                "fields": ["bio", "background", "achievements"]
            })
        
        return sources
    
    def _calculate_completeness(self, data: Dict, entity_type: str) -> float:
        """
        Calculate completeness score (0-100) based on available fields.
        """
        expected = self.EXPECTED_FIELDS.get(entity_type, {})
        
        total_fields = 0
        filled_fields = 0
        
        # Weight by priority
        weights = {'critical': 3, 'important': 2, 'supplementary': 1}
        
        for priority, fields in expected.items():
            weight = weights.get(priority, 1)
            for field in fields:
                total_fields += weight
                if self._has_field(data, field):
                    filled_fields += weight
        
        if total_fields == 0:
            return 0.0
        
        return (filled_fields / total_fields) * 100
    
    def _normalize_entity_type(self, kind: Optional[str]) -> str:
        """Normalize entity type to standard string values."""
        if not kind:
            return 'entity'
        
        kind_lower = kind.lower()
        
        # Map to standard string values
        if any(x in kind_lower for x in ['company', 'corporation', 'business']):
            return 'company'
        elif any(x in kind_lower for x in ['person', 'individual', 'people']):
            return 'person'
        elif any(x in kind_lower for x in ['product', 'service']):
            return 'product'
        elif any(x in kind_lower for x in ['organization', 'org', 'ngo']):
            return 'organization'
        elif any(x in kind_lower for x in ['location', 'place', 'city', 'country']):
            return 'location'
        elif any(x in kind_lower for x in ['news', 'event', 'article']):
            return 'news'
        elif any(x in kind_lower for x in ['topic', 'subject', 'theme']):
            return 'topic'
        else:
            return 'entity'
    
    def _infer_entity_type(self, entity_name: str) -> str:
        """Infer entity type from name patterns, returns standard string value."""
        name_lower = entity_name.lower()
        
        # Company indicators
        company_suffixes = ['inc', 'corp', 'ltd', 'llc', 'gmbh', 'ag', 'sa', 'plc']
        if any(suffix in name_lower for suffix in company_suffixes):
            return 'company'
        
        # Person indicators (has spaces, title case)
        words = entity_name.split()
        if len(words) >= 2 and all(w[0].isupper() for w in words if w):
            return 'person'
        
        # Default
        return 'entity'
