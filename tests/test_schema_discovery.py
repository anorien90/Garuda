"""
Unit tests for dynamic schema discovery.

Tests the DynamicSchemaDiscoverer class and field discovery functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from garuda_intel.extractor.schema_discovery import (
    DynamicSchemaDiscoverer,
    DiscoveredField,
    FieldImportance
)
from garuda_intel.types.entity import EntityProfile


class TestDiscoveredField:
    """Test DiscoveredField dataclass."""
    
    def test_field_creation(self):
        """Test creating a discovered field."""
        field = DiscoveredField(
            field_name="industry",
            description="Primary industry sector",
            importance=FieldImportance.CRITICAL,
            example="Technology"
        )
        
        assert field.field_name == "industry"
        assert field.description == "Primary industry sector"
        assert field.importance == FieldImportance.CRITICAL
        assert field.example == "Technology"
    
    def test_field_to_dict(self):
        """Test converting field to dictionary."""
        field = DiscoveredField(
            field_name="founded",
            description="Year founded",
            importance=FieldImportance.IMPORTANT,
            example="2020"
        )
        
        field_dict = field.to_dict()
        assert field_dict["field_name"] == "founded"
        assert field_dict["importance"] == "important"


class TestDynamicSchemaDiscoverer:
    """Test DynamicSchemaDiscoverer class."""
    
    @pytest.fixture
    def discoverer(self):
        """Create a schema discoverer instance."""
        return DynamicSchemaDiscoverer(
            ollama_url="http://localhost:11434/api/generate",
            model="test-model",
            cache_schemas=True
        )
    
    @pytest.fixture
    def entity_profile(self):
        """Create a test entity profile."""
        from garuda_intel.types.entity import EntityType
        return EntityProfile(
            name="Acme Corp",
            entity_type=EntityType.COMPANY,
            aliases=[]
        )
    
    def test_initialization(self, discoverer):
        """Test discoverer initialization."""
        assert discoverer.ollama_url == "http://localhost:11434/api/generate"
        assert discoverer.model == "test-model"
        assert discoverer.cache_schemas is True
        assert len(discoverer._schema_cache) == 0
    
    def test_build_discovery_prompt(self, discoverer, entity_profile):
        """Test building discovery prompt."""
        sample_text = "Acme Corp is a leading technology company..."
        
        entity_type = str(entity_profile.entity_type.value) if hasattr(entity_profile.entity_type, 'value') else str(entity_profile.entity_type)
        
        prompt = discoverer._build_discovery_prompt(
            entity_name=entity_profile.name,
            entity_type=entity_type,
            sample_text=sample_text,
            max_fields=10
        )
        
        assert "Acme Corp" in prompt
        assert sample_text in prompt
        assert "JSON" in prompt
    
    def test_parse_llm_response_valid_json(self, discoverer):
        """Test parsing valid JSON response."""
        llm_output = json.dumps([
            {
                "field_name": "industry",
                "description": "Primary industry",
                "importance": "critical",
                "example": "Technology"
            },
            {
                "field_name": "founded",
                "description": "Year founded",
                "importance": "important",
                "example": "2020"
            }
        ])
        
        fields_data = discoverer._parse_llm_response(llm_output)
        
        assert len(fields_data) == 2
        assert fields_data[0]["field_name"] == "industry"
        assert fields_data[1]["field_name"] == "founded"
    
    def test_parse_llm_response_with_markdown(self, discoverer):
        """Test parsing JSON wrapped in markdown code fences."""
        llm_output = """```json
[
    {
        "field_name": "industry",
        "description": "Primary industry",
        "importance": "critical"
    }
]
```"""
        
        fields_data = discoverer._parse_llm_response(llm_output)
        
        assert len(fields_data) == 1
        assert fields_data[0]["field_name"] == "industry"
    
    def test_parse_llm_response_invalid_json(self, discoverer):
        """Test parsing invalid JSON returns empty list."""
        llm_output = "This is not valid JSON"
        
        fields_data = discoverer._parse_llm_response(llm_output)
        
        assert fields_data == []
    
    def test_get_fallback_schema(self, discoverer):
        """Test getting fallback schema."""
        fallback = discoverer._get_fallback_schema()
        
        assert len(fallback) > 0
        assert any(f.field_name == "description" for f in fallback)
        assert any(f.field_name == "industry" for f in fallback)
        assert all(isinstance(f, DiscoveredField) for f in fallback)
    
    @patch('requests.post')
    def test_discover_fields_success(self, mock_post, discoverer, entity_profile):
        """Test successful field discovery."""
        # Mock LLM response
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": json.dumps([
                {
                    "field_name": "industry",
                    "description": "Primary industry sector",
                    "importance": "critical",
                    "example": "Technology"
                },
                {
                    "field_name": "employee_count",
                    "description": "Number of employees",
                    "importance": "important",
                    "example": "500"
                }
            ])
        }
        mock_post.return_value = mock_response
        
        sample_text = "Acme Corp is a technology company with 500 employees..."
        
        fields = discoverer.discover_fields(entity_profile, sample_text)
        
        assert len(fields) == 2
        assert fields[0].field_name == "industry"
        assert fields[0].importance == FieldImportance.CRITICAL
        assert fields[1].field_name == "employee_count"
        assert fields[1].importance == FieldImportance.IMPORTANT
    
    @patch('requests.post')
    def test_discover_fields_uses_cache(self, mock_post, discoverer, entity_profile):
        """Test that discovery uses cache for same entity type."""
        # Mock LLM response
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": json.dumps([
                {"field_name": "industry", "description": "Industry", "importance": "critical"}
            ])
        }
        mock_post.return_value = mock_response
        
        sample_text = "Sample text"
        
        # First call - should hit LLM
        fields1 = discoverer.discover_fields(entity_profile, sample_text)
        assert mock_post.call_count == 1
        
        # Second call with same entity type - should use cache
        fields2 = discoverer.discover_fields(entity_profile, sample_text)
        assert mock_post.call_count == 1  # No additional calls
        
        assert fields1 == fields2
    
    @patch('requests.post')
    def test_discover_fields_timeout(self, mock_post, discoverer, entity_profile):
        """Test discovery handles timeout gracefully."""
        import requests
        mock_post.side_effect = requests.Timeout()
        
        sample_text = "Sample text"
        
        fields = discoverer.discover_fields(entity_profile, sample_text)
        
        # Should return fallback schema
        assert len(fields) > 0
        assert any(f.field_name == "description" for f in fields)
    
    def test_build_extraction_prompt(self, discoverer):
        """Test building extraction prompt from discovered schema."""
        fields = [
            DiscoveredField(
                field_name="industry",
                description="Primary industry",
                importance=FieldImportance.CRITICAL,
                example="Technology"
            ),
            DiscoveredField(
                field_name="location",
                description="Headquarters location",
                importance=FieldImportance.IMPORTANT,
                example="San Francisco"
            )
        ]
        
        prompt = discoverer.build_extraction_prompt(
            discovered_fields=fields,
            entity_name="Acme Corp",
            text_chunk="Acme Corp is based in San Francisco..."
        )
        
        assert "Acme Corp" in prompt
        assert "industry" in prompt
        assert "location" in prompt
        assert "[CRITICAL]" in prompt
        assert "[IMPORTANT]" in prompt
        assert "JSON" in prompt
    
    def test_get_cached_schema(self, discoverer):
        """Test getting cached schema."""
        # Add to cache
        fields = [
            DiscoveredField(
                field_name="test_field",
                description="Test",
                importance=FieldImportance.CRITICAL
            )
        ]
        discoverer._schema_cache["Company"] = fields
        
        # Retrieve from cache
        cached = discoverer.get_cached_schema("Company")
        assert cached == fields
        
        # Non-existent type
        assert discoverer.get_cached_schema("NonExistent") is None
    
    def test_clear_cache(self, discoverer):
        """Test clearing cache."""
        # Add to cache
        discoverer._schema_cache["Company"] = []
        discoverer._schema_cache["Person"] = []
        
        # Clear specific type
        discoverer.clear_cache("Company")
        assert "Company" not in discoverer._schema_cache
        assert "Person" in discoverer._schema_cache
        
        # Clear all
        discoverer.clear_cache()
        assert len(discoverer._schema_cache) == 0
    
    def test_get_cache_stats(self, discoverer):
        """Test getting cache statistics."""
        # Add to cache
        discoverer._schema_cache["Company"] = [
            DiscoveredField("field1", "desc1", FieldImportance.CRITICAL),
            DiscoveredField("field2", "desc2", FieldImportance.IMPORTANT)
        ]
        discoverer._schema_cache["Person"] = [
            DiscoveredField("field3", "desc3", FieldImportance.SUPPLEMENTARY)
        ]
        
        stats = discoverer.get_cache_stats()
        
        assert stats["cache_size"] == 2
        assert stats["total_fields"] == 3
        assert "Company" in stats["cached_types"]
        assert "Person" in stats["cached_types"]
    
    def test_no_caching_when_disabled(self):
        """Test that caching can be disabled."""
        discoverer = DynamicSchemaDiscoverer(cache_schemas=False)
        
        # Manually add to cache
        discoverer._schema_cache["Company"] = []
        
        # Should not use cache even if present
        assert discoverer.cache_schemas is False
