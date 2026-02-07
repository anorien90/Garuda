"""Tests for the dynamic entity kind registry."""

import pytest
from garuda_intel.types.entity.registry import (
    EntityKindRegistry,
    EntityKindInfo,
    RelationTypeInfo,
    get_registry,
    normalize_kind,
    get_kind_priority,
)


class TestEntityKindInfo:
    """Tests for EntityKindInfo dataclass."""
    
    def test_creation(self):
        """Test creating an EntityKindInfo."""
        info = EntityKindInfo(
            name="test_kind",
            priority=50,
            color="#ffffff",
            description="Test kind",
            aliases=["test", "testing"],
            fields=["name", "description"],
        )
        
        assert info.name == "test_kind"
        assert info.priority == 50
        assert info.color == "#ffffff"
        assert "test" in info.aliases
        assert "name" in info.fields
    
    def test_to_dict(self):
        """Test converting EntityKindInfo to dict."""
        info = EntityKindInfo(
            name="test_kind",
            priority=25,
            description="A test kind",
        )
        
        d = info.to_dict()
        assert d["name"] == "test_kind"
        assert d["priority"] == 25
        assert d["description"] == "A test kind"


class TestRelationTypeInfo:
    """Tests for RelationTypeInfo dataclass."""
    
    def test_creation(self):
        """Test creating a RelationTypeInfo."""
        info = RelationTypeInfo(
            name="test-relation",
            source_kinds=["person"],
            target_kinds=["org"],
            description="Test relation",
        )
        
        assert info.name == "test-relation"
        assert "person" in info.source_kinds
        assert "org" in info.target_kinds
    
    def test_to_dict(self):
        """Test converting RelationTypeInfo to dict."""
        info = RelationTypeInfo(
            name="test-relation",
            inverse_relation="inverse-test",
        )
        
        d = info.to_dict()
        assert d["name"] == "test-relation"
        assert d["inverse_relation"] == "inverse-test"


class TestEntityKindRegistry:
    """Tests for EntityKindRegistry class."""
    
    @pytest.fixture
    def registry(self):
        """Create a fresh registry instance."""
        # Reset the singleton for testing
        EntityKindRegistry._instance = None
        reg = EntityKindRegistry()
        return reg
    
    def test_builtin_kinds_exist(self, registry):
        """Test that builtin kinds are registered."""
        kinds = registry.get_kind_names()
        
        assert "person" in kinds
        assert "org" in kinds
        assert "company" in kinds
        assert "product" in kinds
        assert "location" in kinds
        assert "event" in kinds
        assert "technology" in kinds
        assert "document" in kinds
        assert "concept" in kinds
        assert "infrastructure" in kinds
        assert "project" in kinds
        assert "entity" in kinds
    
    def test_builtin_relations_exist(self, registry):
        """Test that builtin relations are registered."""
        relations = registry.get_relation_names()
        
        assert "has-person" in relations
        assert "works-at" in relations
        assert "has-location" in relations
        assert "has-product" in relations
        assert "related-entity" in relations
    
    def test_register_new_kind(self, registry):
        """Test registering a new entity kind."""
        info = registry.register_kind(
            name="new_kind",
            priority=30,
            color="#abcdef",
            description="A new kind",
            aliases=["newkind"],
            fields=["field1"],
        )
        
        assert info.name == "new_kind"
        assert info.priority == 30
        assert info.color == "#abcdef"
        assert info.is_builtin is False
        
        # Should be findable
        assert registry.get_kind("new_kind") is not None
        assert "new_kind" in registry.get_kind_names()
    
    def test_register_kind_via_alias(self, registry):
        """Test that kinds can be found via aliases."""
        registry.register_kind(
            name="custom",
            aliases=["mycustom", "custom_kind"],
        )
        
        # Should be findable via alias
        info = registry.get_kind("mycustom")
        assert info is not None
        assert info.name == "custom"
    
    def test_normalize_kind(self, registry):
        """Test kind name normalization."""
        # Direct match
        assert registry.normalize_kind("person") == "person"
        
        # Alias match
        assert registry.normalize_kind("individual") == "person"  # alias of person
        assert registry.normalize_kind("corporation") == "company"  # alias of company
        
        # Unknown kind returns as-is
        assert registry.normalize_kind("unknown_kind") == "unknown_kind"
        
        # Empty returns entity
        assert registry.normalize_kind("") == "entity"
    
    def test_get_priority(self, registry):
        """Test getting kind priorities."""
        # Person should be highest priority (1)
        assert registry.get_priority("person") == 1
        
        # Entity should be lowest priority (99)
        assert registry.get_priority("entity") == 99
        
        # Unknown kinds get default priority (50)
        assert registry.get_priority("unknown_kind") == 50
    
    def test_get_kind_priority_map(self, registry):
        """Test getting the priority map."""
        priority_map = registry.get_kind_priority_map()
        
        assert priority_map["person"] == 1
        assert priority_map["org"] == 2
        assert priority_map["entity"] == 99
    
    def test_get_kind_colors(self, registry):
        """Test getting the color map."""
        colors = registry.get_kind_colors()
        
        assert "person" in colors
        assert colors["person"].startswith("#")
    
    def test_register_new_relation(self, registry):
        """Test registering a new relation type."""
        info = registry.register_relation(
            name="new-relation",
            source_kinds=["person"],
            target_kinds=["event"],
            description="A new relation",
        )
        
        assert info.name == "new-relation"
        assert info.is_builtin is False
        assert "new-relation" in registry.get_relation_names()
    
    def test_sync_from_database(self, registry):
        """Test syncing kinds from database."""
        # Simulate kinds discovered in database
        db_kinds = ["person", "org", "custom_db_kind", "another_kind"]
        
        registry.sync_from_database(db_kinds)
        
        # Person and org already exist
        # custom_db_kind and another_kind should be registered
        assert "custom_db_kind" in registry.get_kind_names()
        assert "another_kind" in registry.get_kind_names()
        
        # They should have default properties
        info = registry.get_kind("custom_db_kind")
        assert info is not None
        assert info.is_builtin is False
    
    def test_to_dict(self, registry):
        """Test exporting registry as dict."""
        d = registry.to_dict()
        
        assert "kinds" in d
        assert "relations" in d
        assert "person" in d["kinds"]
        assert "has-person" in d["relations"]


class TestConvenienceFunctions:
    """Test module-level convenience functions."""
    
    def test_get_registry(self):
        """Test getting the global registry."""
        reg = get_registry()
        assert isinstance(reg, EntityKindRegistry)
    
    def test_normalize_kind_function(self):
        """Test the normalize_kind convenience function."""
        # Should normalize known kinds
        assert normalize_kind("individual") == "person"
    
    def test_get_kind_priority_function(self):
        """Test the get_kind_priority convenience function."""
        assert get_kind_priority("person") == 1
        assert get_kind_priority("unknown") == 50
