"""
Dynamic schema discovery for intelligence extraction.

Automatically identifies relevant fields to extract based on entity type
and content analysis using LLM-driven field discovery.
"""

import json
import logging
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from ..types.entity import EntityProfile


class FieldImportance(str, Enum):
    """Importance level for discovered fields."""
    CRITICAL = "critical"
    IMPORTANT = "important"
    SUPPLEMENTARY = "supplementary"


@dataclass
class DiscoveredField:
    """Represents a dynamically discovered field."""
    field_name: str
    description: str
    importance: FieldImportance
    example: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'field_name': self.field_name,
            'description': self.description,
            'importance': self.importance.value,
            'example': self.example
        }


class DynamicSchemaDiscoverer:
    """
    Discovers relevant data fields for entities using LLM analysis.
    
    Automatically identifies what information should be extracted for
    different entity types and industries, reducing need for hardcoded schemas.
    """
    
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434/api/generate",
        model: str = "granite3.1-dense:8b",
        cache_schemas: bool = True,
        discovery_timeout: int = 60,
    ):
        """
        Initialize schema discoverer.
        
        Args:
            ollama_url: URL of Ollama API endpoint
            model: LLM model to use for schema discovery
            cache_schemas: Whether to cache discovered schemas by entity type
            discovery_timeout: Timeout for LLM requests in seconds
        """
        self.ollama_url = ollama_url
        self.model = model
        self.cache_schemas = cache_schemas
        self.discovery_timeout = discovery_timeout
        self.logger = logging.getLogger(__name__)
        
        # Schema cache: {entity_type: [DiscoveredField]}
        self._schema_cache: Dict[str, List[DiscoveredField]] = {}
    
    def discover_fields(
        self,
        entity_profile: EntityProfile,
        sample_text: str,
        max_fields: int = 15
    ) -> List[DiscoveredField]:
        """
        Discover relevant fields for the entity using LLM analysis.
        
        Args:
            entity_profile: The entity to analyze
            sample_text: Sample content about the entity
            max_fields: Maximum number of fields to discover
            
        Returns:
            List of discovered fields with importance and descriptions
        """
        entity_type = entity_profile.kind or "Unknown"
        
        # Check cache first
        if self.cache_schemas and entity_type in self._schema_cache:
            self.logger.debug(f"Using cached schema for entity type: {entity_type}")
            return self._schema_cache[entity_type]
        
        # Prepare sample text (limit to avoid token limits)
        sample = sample_text[:2000] if len(sample_text) > 2000 else sample_text
        
        # Build LLM prompt for field discovery
        prompt = self._build_discovery_prompt(
            entity_name=entity_profile.name,
            entity_type=entity_type,
            sample_text=sample,
            max_fields=max_fields
        )
        
        # Call LLM
        discovered_fields = self._call_llm_for_discovery(prompt, max_fields)
        
        # Cache the schema
        if self.cache_schemas and discovered_fields:
            self._schema_cache[entity_type] = discovered_fields
            self.logger.info(f"Cached schema for entity type '{entity_type}' with {len(discovered_fields)} fields")
        
        return discovered_fields
    
    def _build_discovery_prompt(
        self,
        entity_name: str,
        entity_type: str,
        sample_text: str,
        max_fields: int
    ) -> str:
        """Build prompt for LLM-based field discovery."""
        return f"""Analyze this entity and identify the most relevant data fields to extract.

Entity Name: {entity_name}
Entity Type: {entity_type}
Sample Content:
{sample_text}

Task: Identify the {max_fields} most relevant data fields to extract for this type of entity.
For each field, provide:
1. field_name: A short, descriptive name (snake_case)
2. description: What this field represents
3. importance: One of "critical", "important", or "supplementary"
4. example: An example value (if clear from the sample)

Return ONLY a valid JSON array with this exact structure:
[
  {{
    "field_name": "industry",
    "description": "Primary industry or sector",
    "importance": "critical",
    "example": "Technology"
  }},
  ...
]

Focus on fields that are:
- Specific to this entity type
- Present or inferable from the sample
- Useful for understanding the entity's nature and activities

Return JSON only, no additional text."""
    
    def _call_llm_for_discovery(self, prompt: str, max_fields: int) -> List[DiscoveredField]:
        """
        Call LLM to discover fields.
        
        Args:
            prompt: The discovery prompt
            max_fields: Maximum fields to return
            
        Returns:
            List of discovered fields
        """
        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=self.discovery_timeout,
            )
            response.raise_for_status()
            
            result = response.json()
            llm_output = result.get("response", "")
            
            # Parse the JSON response
            fields_data = self._parse_llm_response(llm_output)
            
            # Convert to DiscoveredField objects
            discovered_fields = []
            for field_data in fields_data[:max_fields]:
                try:
                    field = DiscoveredField(
                        field_name=field_data.get("field_name", "").lower().replace(" ", "_"),
                        description=field_data.get("description", ""),
                        importance=FieldImportance(field_data.get("importance", "supplementary")),
                        example=field_data.get("example")
                    )
                    discovered_fields.append(field)
                except (ValueError, KeyError) as e:
                    self.logger.warning(f"Skipping invalid field: {e}")
                    continue
            
            self.logger.info(f"Discovered {len(discovered_fields)} fields")
            return discovered_fields
            
        except requests.Timeout:
            self.logger.error("Schema discovery timed out")
            return self._get_fallback_schema()
        except Exception as e:
            self.logger.error(f"Schema discovery failed: {e}")
            return self._get_fallback_schema()
    
    def _parse_llm_response(self, llm_output: str) -> List[Dict[str, Any]]:
        """
        Parse LLM response into field definitions.
        
        Args:
            llm_output: Raw LLM response
            
        Returns:
            List of field dictionaries
        """
        if not llm_output:
            return []
        
        # Clean up the response
        cleaned = llm_output.strip()
        
        # Remove markdown code fences if present
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        
        # Try to parse JSON
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "fields" in data:
                return data["fields"]
            else:
                self.logger.warning("Unexpected JSON structure in LLM response")
                return []
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse LLM response as JSON: {e}")
            return []
    
    def _get_fallback_schema(self) -> List[DiscoveredField]:
        """
        Return a basic fallback schema when discovery fails.
        
        Returns:
            List of basic fields applicable to most entities
        """
        return [
            DiscoveredField(
                field_name="description",
                description="General description of the entity",
                importance=FieldImportance.CRITICAL,
                example=None
            ),
            DiscoveredField(
                field_name="industry",
                description="Primary industry or sector",
                importance=FieldImportance.IMPORTANT,
                example=None
            ),
            DiscoveredField(
                field_name="location",
                description="Physical location or headquarters",
                importance=FieldImportance.IMPORTANT,
                example=None
            ),
            DiscoveredField(
                field_name="key_people",
                description="Important people associated with entity",
                importance=FieldImportance.IMPORTANT,
                example=None
            ),
            DiscoveredField(
                field_name="founded",
                description="Founding date or establishment year",
                importance=FieldImportance.SUPPLEMENTARY,
                example=None
            ),
        ]
    
    def build_extraction_prompt(
        self,
        discovered_fields: List[DiscoveredField],
        entity_name: str,
        text_chunk: str
    ) -> str:
        """
        Build an extraction prompt using discovered schema.
        
        Args:
            discovered_fields: Fields to extract
            entity_name: Name of entity
            text_chunk: Text to extract from
            
        Returns:
            Formatted extraction prompt
        """
        # Build field descriptions
        field_descriptions = []
        for field in discovered_fields:
            importance_marker = {
                FieldImportance.CRITICAL: "[CRITICAL]",
                FieldImportance.IMPORTANT: "[IMPORTANT]",
                FieldImportance.SUPPLEMENTARY: "[OPTIONAL]"
            }[field.importance]
            
            desc = f"- {field.field_name} {importance_marker}: {field.description}"
            if field.example:
                desc += f" (e.g., {field.example})"
            field_descriptions.append(desc)
        
        field_list = "\n".join(field_descriptions)
        
        return f"""Extract information about {entity_name} from the following text.

Fields to extract:
{field_list}

Text:
{text_chunk}

Return a JSON object with the field names as keys. Only include fields where you found information.
If a field value is not found, omit it from the result.

Return ONLY valid JSON, no additional text."""
    
    def get_cached_schema(self, entity_type: str) -> Optional[List[DiscoveredField]]:
        """
        Get cached schema for an entity type.
        
        Args:
            entity_type: The type of entity
            
        Returns:
            Cached schema if available, None otherwise
        """
        return self._schema_cache.get(entity_type)
    
    def clear_cache(self, entity_type: Optional[str] = None):
        """
        Clear schema cache.
        
        Args:
            entity_type: If provided, clear only this type. Otherwise clear all.
        """
        if entity_type:
            self._schema_cache.pop(entity_type, None)
            self.logger.info(f"Cleared schema cache for entity type: {entity_type}")
        else:
            self._schema_cache.clear()
            self.logger.info("Cleared all schema cache")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about schema cache.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            "cached_types": list(self._schema_cache.keys()),
            "cache_size": len(self._schema_cache),
            "total_fields": sum(len(fields) for fields in self._schema_cache.values())
        }
