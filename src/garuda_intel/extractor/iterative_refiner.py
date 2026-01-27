"""
Iterative Extraction Refinement System.

This module refines intelligence extraction by detecting gaps, contradictions,
and requesting additional context when needed.
"""

import logging
import requests
from typing import Dict, Any, List, Tuple, Optional, Set
from collections import defaultdict
import json

from ..types.entity import EntityProfile
from ..database.store import PersistenceStore


class IterativeRefiner:
    """
    Refines extraction by analyzing initial findings and requesting more detail.
    
    Features:
    - Detects contradictions in intelligence from multiple sources
    - Identifies gaps in extracted data
    - Generates targeted prompts for missing information
    - Validates consistency across sources
    """
    
    def __init__(
        self, 
        llm_extractor: Any,
        store: PersistenceStore,
        ollama_url: str = "http://localhost:11434/api/generate",
        model: str = "granite3.1-dense:8b",
        refinement_timeout: int = 60,
    ):
        """
        Initialize the iterative refiner.
        
        Args:
            llm_extractor: LLMIntelExtractor instance for extraction
            store: Persistence store for loading existing intelligence
            ollama_url: Ollama API URL
            model: LLM model name
            refinement_timeout: Timeout for refinement requests
        """
        self.llm_extractor = llm_extractor
        self.store = store
        self.ollama_url = ollama_url
        self.model = model
        self.refinement_timeout = refinement_timeout
        self.logger = logging.getLogger(__name__)
        
        # Priority fields for each entity type
        self.priority_fields = {
            "company": [
                "basic_info.official_name",
                "basic_info.industry", 
                "basic_info.founded",
                "basic_info.website",
                "persons",
                "locations",
                "financials"
            ],
            "person": [
                "basic_info.official_name",
                "basic_info.title",
                "basic_info.bio",
                "persons",
                "events",
                "relationships"
            ],
            "news": [
                "events",
                "persons",
                "relationships",
                "basic_info.description"
            ],
            "topic": [
                "basic_info.description",
                "events",
                "relationships"
            ]
        }
    
    def refine_extraction(
        self, 
        entity_id: str, 
        initial_intel: Dict, 
        page_text: str,
        page_url: str = "",
        page_type: str = "",
    ) -> Dict:
        """
        Refine extraction by analyzing initial findings and requesting more detail.
        
        Args:
            entity_id: Entity ID being researched
            initial_intel: Initial intelligence extracted
            page_text: Full page text for re-extraction
            page_url: URL of the page
            page_type: Type of page
            
        Returns:
            Refined intelligence dictionary
        """
        if not initial_intel or not page_text:
            return initial_intel
        
        # Identify gaps in the initial extraction
        gaps = self._identify_gaps(initial_intel, page_type)
        
        if not gaps:
            # No gaps found, return original
            self.logger.debug("No gaps identified in extraction")
            return initial_intel
        
        # Generate targeted extraction for gaps
        refined_intel = dict(initial_intel)
        
        for gap_field in gaps[:3]:  # Refine top 3 gaps
            self.logger.info(f"Refining gap: {gap_field}")
            
            # Generate targeted prompt
            targeted_prompt = self.request_additional_context(entity_id, gap_field, page_text, page_url)
            
            if not targeted_prompt:
                continue
            
            # Extract with targeted prompt
            gap_result = self._extract_with_prompt(targeted_prompt)
            
            # Merge gap result into refined intel
            if gap_result:
                refined_intel = self._merge_gap_data(refined_intel, gap_result, gap_field)
        
        return refined_intel
    
    def detect_contradictions(self, intel_records: List[Dict]) -> List[Dict]:
        """
        Detect contradictions in intelligence from multiple sources.
        
        Args:
            intel_records: List of intelligence dictionaries from different sources
            
        Returns:
            List of contradiction records with details
        """
        if len(intel_records) < 2:
            return []
        
        contradictions = []
        
        # Check basic_info fields for contradictions
        basic_fields = ["official_name", "founded", "industry", "ticker", "website"]
        for field in basic_fields:
            values = []
            sources = []
            
            for i, record in enumerate(intel_records):
                basic_info = record.get("basic_info", {})
                if basic_info.get(field):
                    values.append(basic_info[field])
                    sources.append(i)
            
            # Detect contradictions (different non-empty values)
            unique_values = set(values)
            if len(unique_values) > 1:
                contradictions.append({
                    "field": f"basic_info.{field}",
                    "values": list(unique_values),
                    "sources": sources,
                    "severity": "high" if field in ["official_name", "ticker"] else "medium",
                })
        
        # Check for contradictory person roles
        person_contradictions = self._detect_person_contradictions(intel_records)
        contradictions.extend(person_contradictions)
        
        # Check for contradictory financial data
        financial_contradictions = self._detect_financial_contradictions(intel_records)
        contradictions.extend(financial_contradictions)
        
        return contradictions
    
    def request_additional_context(
        self, 
        entity_id: str, 
        gap_field: str,
        page_text: str = "",
        page_url: str = "",
    ) -> str:
        """
        Generate targeted prompt to extract specific missing information.
        
        Args:
            entity_id: Entity ID being researched
            gap_field: Field that has a gap (e.g., 'basic_info.founded')
            page_text: Page text to extract from
            page_url: URL of the page
            
        Returns:
            Targeted extraction prompt
        """
        # Map gap field to extraction focus
        field_prompts = {
            "basic_info.official_name": "the exact official legal name",
            "basic_info.founded": "the founding date or year of establishment",
            "basic_info.industry": "the primary industry or sector",
            "basic_info.website": "the official website URL",
            "basic_info.ticker": "the stock ticker symbol",
            "persons": "key people, executives, founders, or notable team members",
            "locations": "office locations, headquarters, or addresses",
            "financials": "financial data such as revenue, funding, or market cap",
            "products": "products, services, or offerings",
            "events": "significant events, milestones, or news",
            "relationships": "business relationships, partnerships, or acquisitions",
        }
        
        focus = field_prompts.get(gap_field, gap_field)
        
        if not page_text:
            return ""
        
        # Create targeted prompt
        prompt = f"""
You are an expert intelligence analyst. Analyze the following text and extract ONLY information about {focus}.

Focus specifically on finding {focus}. Ignore other information.

TEXT:
{page_text[:3000]}

Return a JSON object with the relevant extracted data. Be precise and factual.
"""
        
        return prompt
    
    def validate_consistency(
        self, 
        new_intel: Dict, 
        existing_intel: List[Dict]
    ) -> Tuple[bool, List[str]]:
        """
        Validate new intelligence against existing data.
        
        Args:
            new_intel: New intelligence to validate
            existing_intel: List of existing intelligence records
            
        Returns:
            Tuple of (is_consistent, list of issues)
        """
        if not existing_intel:
            return True, []
        
        issues = []
        
        # Check basic_info consistency
        new_basic = new_intel.get("basic_info", {})
        
        for field in ["official_name", "ticker", "founded", "industry"]:
            new_value = new_basic.get(field)
            if not new_value:
                continue
            
            # Check against all existing records
            for existing in existing_intel:
                existing_basic = existing.get("basic_info", {})
                existing_value = existing_basic.get(field)
                
                if existing_value and existing_value != new_value:
                    # Potential inconsistency
                    # Allow some flexibility for dates and similar values
                    if not self._values_compatible(field, new_value, existing_value):
                        issues.append(
                            f"Inconsistent {field}: new='{new_value}' vs existing='{existing_value}'"
                        )
        
        # Check person consistency
        new_persons = new_intel.get("persons", [])
        if new_persons:
            person_issues = self._validate_person_consistency(new_persons, existing_intel)
            issues.extend(person_issues)
        
        is_consistent = len(issues) == 0
        return is_consistent, issues
    
    def _identify_gaps(self, intel: Dict, page_type: str) -> List[str]:
        """Identify missing or incomplete fields in intelligence."""
        gaps = []
        
        if not intel:
            return gaps
        
        # Determine entity type from intel structure
        entity_type = "company"  # default
        basic_info = intel.get("basic_info", {})
        if basic_info.get("ticker") or basic_info.get("industry"):
            entity_type = "company"
        
        # Get priority fields for this entity type
        priority = self.priority_fields.get(entity_type, [])
        
        for field_path in priority:
            if "." in field_path:
                section, field = field_path.split(".", 1)
                section_data = intel.get(section, {})
                
                if isinstance(section_data, dict) and not section_data.get(field):
                    gaps.append(field_path)
            else:
                # List field
                if not intel.get(field_path) or len(intel.get(field_path, [])) == 0:
                    gaps.append(field_path)
        
        return gaps
    
    def _extract_with_prompt(self, prompt: str) -> Dict:
        """Execute extraction with a custom prompt."""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            }
            
            response = requests.post(
                self.ollama_url, 
                json=payload, 
                timeout=self.refinement_timeout
            )
            
            result = response.json().get("response", "{}")
            return json.loads(result)
            
        except Exception as e:
            self.logger.warning(f"Failed to extract with custom prompt: {e}")
            return {}
    
    def _merge_gap_data(self, base: Dict, gap_data: Dict, gap_field: str) -> Dict:
        """Merge gap-specific extraction into base intelligence."""
        if not gap_data:
            return base
        
        merged = dict(base)
        
        # Identify what kind of gap we're filling
        if gap_field.startswith("basic_info."):
            field = gap_field.split(".", 1)[1]
            if "basic_info" not in merged:
                merged["basic_info"] = {}
            
            # Fill the specific field if gap_data has it
            if isinstance(gap_data, dict):
                if field in gap_data:
                    merged["basic_info"][field] = gap_data[field]
                elif "basic_info" in gap_data and field in gap_data["basic_info"]:
                    merged["basic_info"][field] = gap_data["basic_info"][field]
        
        elif gap_field in ["persons", "locations", "financials", "products", "events", "relationships"]:
            # List field - append new items
            if gap_field in gap_data and isinstance(gap_data[gap_field], list):
                if gap_field not in merged:
                    merged[gap_field] = []
                
                # Deduplicate before merging
                existing_items = {json.dumps(item, sort_keys=True) for item in merged[gap_field]}
                for item in gap_data[gap_field]:
                    item_str = json.dumps(item, sort_keys=True)
                    if item_str not in existing_items:
                        merged[gap_field].append(item)
        
        return merged
    
    def _detect_person_contradictions(self, records: List[Dict]) -> List[Dict]:
        """Detect contradictions in person/role data."""
        contradictions = []
        
        # Build person -> roles mapping
        person_roles: Dict[str, Set[str]] = defaultdict(set)
        
        for record in records:
            for person in record.get("persons", []):
                if not isinstance(person, dict):
                    continue
                
                name = person.get("name", "").lower()
                title = person.get("title", "")
                
                if name and title:
                    person_roles[name].add(title)
        
        # Check for contradictory roles (e.g., CEO vs CTO)
        executive_roles = {"ceo", "cto", "cfo", "coo", "president"}
        
        for name, titles in person_roles.items():
            title_set = {t.lower() for t in titles}
            exec_titles = title_set & executive_roles
            
            if len(exec_titles) > 1:
                contradictions.append({
                    "field": "persons",
                    "person": name,
                    "values": list(titles),
                    "severity": "medium",
                    "type": "conflicting_roles"
                })
        
        return contradictions
    
    def _detect_financial_contradictions(self, records: List[Dict]) -> List[Dict]:
        """Detect contradictions in financial data."""
        contradictions = []
        
        # Group financials by year
        year_data: Dict[str, List[Dict]] = defaultdict(list)
        
        for record in records:
            for financial in record.get("financials", []):
                if not isinstance(financial, dict):
                    continue
                
                year = financial.get("year", "")
                if year:
                    year_data[year].append(financial)
        
        # Check for contradictory revenue in same year
        for year, financials in year_data.items():
            if len(financials) < 2:
                continue
            
            revenues = [f.get("revenue") for f in financials if f.get("revenue")]
            unique_revenues = set(revenues)
            
            if len(unique_revenues) > 1:
                contradictions.append({
                    "field": "financials",
                    "year": year,
                    "values": list(unique_revenues),
                    "severity": "high",
                    "type": "conflicting_revenue"
                })
        
        return contradictions
    
    def _values_compatible(self, field: str, value1: str, value2: str) -> bool:
        """Check if two values are compatible (not contradictory)."""
        if value1 == value2:
            return True
        
        # For dates, allow flexible matching
        if field == "founded":
            # Extract years
            import re
            year1 = re.search(r'\d{4}', str(value1))
            year2 = re.search(r'\d{4}', str(value2))
            
            if year1 and year2:
                return year1.group() == year2.group()
        
        # For names, allow case-insensitive and minor variations
        if field == "official_name":
            v1_clean = value1.lower().replace(",", "").replace(".", "").replace("inc", "").strip()
            v2_clean = value2.lower().replace(",", "").replace(".", "").replace("inc", "").strip()
            
            # Check if one is substring of other
            if v1_clean in v2_clean or v2_clean in v1_clean:
                return True
        
        return False
    
    def _validate_person_consistency(self, new_persons: List[Dict], existing_intel: List[Dict]) -> List[str]:
        """Validate person data consistency."""
        issues = []
        
        # Build map of existing person -> title
        existing_map = {}
        for intel in existing_intel:
            for person in intel.get("persons", []):
                if not isinstance(person, dict):
                    continue
                name = person.get("name", "").lower()
                title = person.get("title", "")
                if name and title:
                    existing_map[name] = title
        
        # Check new persons against existing
        for person in new_persons:
            if not isinstance(person, dict):
                continue
            
            name = person.get("name", "").lower()
            title = person.get("title", "")
            
            if name in existing_map and title:
                existing_title = existing_map[name]
                if existing_title != title:
                    # Check if contradiction or just more detail
                    if not self._titles_compatible(title, existing_title):
                        issues.append(
                            f"Person '{name}' has conflicting titles: '{title}' vs '{existing_title}'"
                        )
        
        return issues
    
    def _titles_compatible(self, title1: str, title2: str) -> bool:
        """Check if two titles are compatible."""
        t1 = title1.lower()
        t2 = title2.lower()
        
        # Same title
        if t1 == t2:
            return True
        
        # One contains the other (e.g., "CEO" and "CEO and Founder")
        if t1 in t2 or t2 in t1:
            return True
        
        return False
