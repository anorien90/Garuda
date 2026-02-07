"""
Tests for dynamic entity kind registry integration with intel extractor.

Tests the enhanced extraction capabilities:
- Entity kind lookup from registry
- Inheritance support (CEO from Person, Address from Location)
- Related entity extraction from pages
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from garuda_intel.types.entity.registry import EntityKindRegistry, get_registry
from garuda_intel.extractor.intel_extractor import IntelExtractor


class TestEntityKindRegistryIntegration:
    """Test EntityKindRegistry integration with IntelExtractor."""
    
    @pytest.fixture
    def registry(self):
        """Get the singleton registry instance."""
        return get_registry()
    
    @pytest.fixture
    def extractor(self):
        """Create an IntelExtractor instance."""
        return IntelExtractor(
            enable_entity_merging=False,  # Disable merging for unit tests
            enable_schema_discovery=False,
            enable_quality_validation=False,
        )
    
    def test_registry_has_builtin_person_hierarchy(self, registry):
        """Test that registry has person type hierarchy."""
        # Check that specialized person types have person as parent
        ceo_info = registry.get_kind("ceo")
        assert ceo_info is not None
        assert ceo_info.parent_kind == "person"
        
        founder_info = registry.get_kind("founder")
        assert founder_info is not None
        assert founder_info.parent_kind == "person"
        
        executive_info = registry.get_kind("executive")
        assert executive_info is not None
        assert executive_info.parent_kind == "person"
    
    def test_registry_has_builtin_location_hierarchy(self, registry):
        """Test that registry has location type hierarchy."""
        # Check that specialized location types have location as parent
        hq_info = registry.get_kind("headquarters")
        assert hq_info is not None
        assert hq_info.parent_kind == "location"
        
        office_info = registry.get_kind("office")
        assert office_info is not None
        assert office_info.parent_kind == "location"
    
    def test_registry_is_subtype_of(self, registry):
        """Test is_subtype_of method for hierarchical relationships."""
        # CEO is a subtype of person
        assert registry.is_subtype_of("ceo", "person") is True
        
        # Headquarters is a subtype of location
        assert registry.is_subtype_of("headquarters", "location") is True
        
        # Person is not a subtype of CEO (reverse)
        assert registry.is_subtype_of("person", "ceo") is False
        
        # Same type is considered a subtype of itself
        assert registry.is_subtype_of("person", "person") is True
    
    def test_extractor_detects_ceo_from_title(self, extractor):
        """Test that extractor correctly detects CEO from title."""
        finding = {
            "persons": [
                {
                    "name": "Satya Nadella",
                    "title": "Chief Executive Officer",
                    "role": "executive"
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(finding)
        
        # Should have extracted the person
        assert len(entities) == 1
        person = entities[0]
        assert person["name"] == "Satya Nadella"
        assert person["kind"] == "ceo"
        assert person["parent_kind"] == "person"
    
    def test_extractor_detects_founder_from_role(self, extractor):
        """Test that extractor correctly detects founder from role."""
        finding = {
            "persons": [
                {
                    "name": "Bill Gates",
                    "title": "Co-founder",
                    "role": "founder"
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(finding)
        
        # Should detect as founder
        assert len(entities) == 1
        person = entities[0]
        assert person["name"] == "Bill Gates"
        assert person["kind"] == "founder"
        assert person["parent_kind"] == "person"
    
    def test_extractor_detects_headquarters_from_type(self, extractor):
        """Test that extractor correctly detects headquarters from location type."""
        finding = {
            "locations": [
                {
                    "city": "Redmond",
                    "country": "USA",
                    "type": "headquarters"
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(finding)
        
        # Should detect as headquarters
        assert len(entities) == 1
        location = entities[0]
        assert location["name"] == "Redmond"
        assert location["kind"] == "headquarters"
        assert location["parent_kind"] == "location"
    
    def test_extractor_detects_headquarters_from_context(self, extractor):
        """Test that extractor detects headquarters from context text."""
        finding = {
            "locations": [
                {
                    "city": "Cupertino",
                    "country": "USA",
                    "type": ""  # No explicit type
                }
            ]
        }
        
        # Context mentions headquarters
        entities = extractor.extract_entities_from_finding(
            finding, 
            context_text="Apple Park is the corporate headquarters located in Cupertino"
        )
        
        # Should detect as headquarters from context
        assert len(entities) == 1
        location = entities[0]
        assert location["name"] == "Cupertino"
        assert location["kind"] == "headquarters"
    
    def test_extractor_creates_relationships_for_executives(self, extractor):
        """Test that extractor creates suggested relationships for executives."""
        finding = {
            "persons": [
                {
                    "name": "Tim Cook",
                    "title": "CEO",
                    "role": "executive"
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(
            finding,
            primary_entity_name="Apple Inc."
        )
        
        # Should have suggested relationship
        assert len(entities) == 1
        person = entities[0]
        assert "suggested_relationship" in person
        assert person["suggested_relationship"]["target"] == "Apple Inc."
        assert person["suggested_relationship"]["relation_type"] == "ceo_of"
    
    def test_extractor_extracts_all_entity_types(self, extractor):
        """Test that extractor extracts all entity types from a finding."""
        finding = {
            "basic_info": {
                "official_name": "Microsoft Corporation",
                "ticker": "MSFT",
                "industry": "Technology"
            },
            "persons": [
                {"name": "Bill Gates", "title": "Co-founder", "role": "founder"},
                {"name": "Satya Nadella", "title": "CEO", "role": "executive"}
            ],
            "locations": [
                {"city": "Redmond", "country": "USA", "type": "headquarters"}
            ],
            "products": [
                {"name": "Windows", "description": "Operating system"}
            ],
            "events": [
                {"title": "Founded", "date": "1975"}
            ]
        }
        
        entities = extractor.extract_entities_from_finding(
            finding,
            primary_entity_name="Microsoft Corporation"
        )
        
        # Should have extracted all entities
        kinds = {e["kind"] for e in entities}
        
        assert "company" in kinds
        assert "founder" in kinds
        assert "ceo" in kinds
        assert "headquarters" in kinds
        assert "product" in kinds
        assert "event" in kinds
        
        # Check total count
        assert len(entities) == 6
    
    def test_resolve_entity_kind_registers_unknown(self, extractor):
        """Test that unknown kinds are automatically registered."""
        # Get a completely new kind
        kind = extractor._resolve_entity_kind("custom_specialist")
        
        assert kind == "custom_specialist"
        
        # Should now be in registry
        registry = get_registry()
        kind_info = registry.get_kind("custom_specialist")
        assert kind_info is not None
    
    def test_detect_person_kind_detects_executives(self, extractor):
        """Test _detect_person_kind detects various executive types."""
        test_cases = [
            ({"title": "Chief Executive Officer"}, "ceo"),
            ({"title": "CEO"}, "ceo"),
            ({"role": "founder"}, "founder"),
            ({"title": "Co-founder"}, "founder"),
            ({"title": "Chief Financial Officer"}, "executive"),
            ({"title": "CFO"}, "executive"),
            ({"title": "President"}, "executive"),
            ({"title": "Vice President of Sales"}, "executive"),
            ({"title": "Director of Engineering"}, "executive"),
            ({"title": "Board Member", "role": "board"}, "board_member"),
            ({"title": "Chairman"}, "board_member"),
            ({"title": "Software Engineer"}, "person"),  # Regular employee
        ]
        
        for person_data, expected_kind in test_cases:
            kind = extractor._detect_person_kind(person_data)
            assert kind == expected_kind, f"Expected {expected_kind} for {person_data}, got {kind}"
    
    def test_detect_location_kind_detects_types(self, extractor):
        """Test _detect_location_kind detects various location types."""
        test_cases = [
            ({"type": "headquarters"}, "Redmond", "", "headquarters"),
            ({"type": "HQ"}, "San Jose", "", "headquarters"),
            ({"type": ""}, "Main Office", "", "headquarters"),  # Label contains keyword
            ({"type": "branch"}, "Seattle", "", "branch_office"),
            ({"type": "regional office"}, "Austin", "", "branch_office"),
            ({"type": "registered address"}, "Wilmington", "", "registered_address"),
            ({"type": "office"}, "Chicago", "", "office"),
            ({"type": ""}, "London", "", "location"),  # Generic location
        ]
        
        for loc_data, label, context, expected_kind in test_cases:
            kind = extractor._detect_location_kind(loc_data, label, context)
            assert kind == expected_kind, f"Expected {expected_kind} for {loc_data}/{label}, got {kind}"


class TestEntityKindRegistryDynamicRegistration:
    """Test dynamic registration of new entity kinds."""
    
    @pytest.fixture
    def registry(self):
        """Get the singleton registry instance."""
        return get_registry()
    
    def test_register_custom_person_subtype(self, registry):
        """Test registering a custom person subtype."""
        # Register a new specialized person type
        registry.register_kind(
            name="data_scientist",
            parent_kind="person",
            description="Data scientist role",
            priority=60,
        )
        
        kind_info = registry.get_kind("data_scientist")
        assert kind_info is not None
        assert kind_info.parent_kind == "person"
        assert registry.is_subtype_of("data_scientist", "person") is True
    
    def test_register_custom_location_subtype(self, registry):
        """Test registering a custom location subtype."""
        # Register a new specialized location type
        registry.register_kind(
            name="data_center",
            parent_kind="location",
            description="Data center facility",
            priority=55,
        )
        
        kind_info = registry.get_kind("data_center")
        assert kind_info is not None
        assert kind_info.parent_kind == "location"
        assert registry.is_subtype_of("data_center", "location") is True
    
    def test_normalize_kind_with_alias(self, registry):
        """Test that aliases are properly normalized."""
        # 'organisation' should normalize to 'org'
        normalized = registry.normalize_kind("organisation")
        assert normalized == "org"
        
        # 'organization' should also normalize to 'org'
        normalized = registry.normalize_kind("organization")
        assert normalized == "org"
    
    def test_should_merge_kinds_with_hierarchy(self, registry):
        """Test should_merge_kinds with hierarchical types."""
        # CEO (child) and person (parent) should merge to CEO
        should_merge, winning_kind = registry.should_merge_kinds("ceo", "person")
        assert should_merge is True
        assert winning_kind == "ceo"
        
        # person (parent) and CEO (child) should merge to CEO
        should_merge, winning_kind = registry.should_merge_kinds("person", "ceo")
        assert should_merge is True
        assert winning_kind == "ceo"
        
        # Two different specific types should not merge
        should_merge, winning_kind = registry.should_merge_kinds("ceo", "founder")
        assert should_merge is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
