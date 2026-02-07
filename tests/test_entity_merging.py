"""
Tests for entity merging and type hierarchy functionality.

Tests:
- Entity lookup and merging
- Entity type hierarchy detection
- Specialized entity type creation
- Field value tracking
"""

import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from garuda_intel.database.models import (
    Base,
    Entity,
    Relationship,
    DynamicFieldDefinition,
    EntityFieldValue,
    FieldDiscoveryLog,
)
from garuda_intel.extractor.entity_merger import (
    EntityMerger,
    FieldDiscoveryTracker,
    ENTITY_TYPE_HIERARCHY,
)
from garuda_intel.extractor.intel_extractor import IntelExtractor


@pytest.fixture
def db_session():
    """Create an in-memory database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session_maker = Session
    yield session_maker
    engine.dispose()


class TestEntityMerger:
    """Test EntityMerger functionality."""
    
    def test_get_or_create_new_entity(self, db_session):
        """Test creating a new entity."""
        merger = EntityMerger(db_session)
        
        entity_id, was_created = merger.get_or_create_entity(
            name="Microsoft Corporation",
            kind="company",
            data={"industry": "Technology", "founded": "1975"},
        )
        
        assert was_created is True
        assert entity_id is not None
        
        # Verify entity was created
        with db_session() as session:
            entity = session.execute(
                select(Entity).where(Entity.id == entity_id)
            ).scalar_one()
            
            assert entity.name == "Microsoft Corporation"
            assert entity.kind == "company"
            assert entity.data.get("industry") == "Technology"
    
    def test_merge_existing_entity(self, db_session):
        """Test merging data into an existing entity."""
        merger = EntityMerger(db_session)
        
        # Create initial entity
        entity_id1, created1 = merger.get_or_create_entity(
            name="Apple Inc.",
            kind="company",
            data={"industry": "Technology"},
        )
        assert created1 is True
        
        # Merge new data into existing entity
        entity_id2, created2 = merger.get_or_create_entity(
            name="Apple Inc.",
            kind="company",
            data={"founded": "1976", "ceo": "Tim Cook"},
        )
        
        assert created2 is False
        assert entity_id2 == entity_id1
        
        # Verify data was merged
        with db_session() as session:
            entity = session.execute(
                select(Entity).where(Entity.id == entity_id1)
            ).scalar_one()
            
            assert entity.data.get("industry") == "Technology"
            assert entity.data.get("founded") == "1976"
            assert entity.data.get("ceo") == "Tim Cook"
    
    def test_upgrade_entity_type(self, db_session):
        """Test upgrading entity to a more specific type."""
        merger = EntityMerger(db_session)
        
        # Create generic entity
        entity_id, _ = merger.get_or_create_entity(
            name="1 Microsoft Way, Redmond",
            kind="location",
            data={"address": "1 Microsoft Way", "city": "Redmond"},
        )
        
        # Upgrade to more specific type
        success = merger.upgrade_entity_type(
            entity_id=entity_id,
            new_kind="headquarters",
            reason="Detected as company headquarters",
        )
        
        assert success is True
        
        # Verify upgrade
        with db_session() as session:
            entity = session.execute(
                select(Entity).where(Entity.id == entity_id)
            ).scalar_one()
            
            assert entity.kind == "headquarters"
            assert "type_history" in entity.metadata_json
            assert len(entity.metadata_json["type_history"]) == 1
            assert entity.metadata_json["type_history"][0]["from"] == "location"
            assert entity.metadata_json["type_history"][0]["to"] == "headquarters"
    
    def test_type_upgrade_on_merge(self, db_session):
        """Test type upgrade during merge."""
        merger = EntityMerger(db_session)
        
        # Create generic person
        entity_id1, _ = merger.get_or_create_entity(
            name="Satya Nadella",
            kind="person",
            data={"role": "CEO"},
        )
        
        # Merge with more specific type
        entity_id2, created = merger.get_or_create_entity(
            name="Satya Nadella",
            kind="ceo",
            data={"company": "Microsoft"},
        )
        
        assert created is False
        assert entity_id2 == entity_id1
        
        # Verify type was upgraded
        with db_session() as session:
            entity = session.execute(
                select(Entity).where(Entity.id == entity_id1)
            ).scalar_one()
            
            # Note: The merger should upgrade person to ceo since ceo is more specific
            assert entity.kind == "ceo"
    
    def test_create_specialized_entity(self, db_session):
        """Test creating a specialized entity linked to parent."""
        merger = EntityMerger(db_session)
        
        # Create parent entity
        parent_id, _ = merger.get_or_create_entity(
            name="Google LLC",
            kind="company",
            data={"industry": "Technology"},
        )
        
        # Create specialized entity
        specialized_id = merger.create_specialized_entity(
            parent_entity_id=parent_id,
            specialized_name="1600 Amphitheatre Parkway",
            specialized_kind="headquarters",
            relationship_type="has_headquarters",
            data={"city": "Mountain View", "country": "USA"},
        )
        
        assert specialized_id is not None
        
        # Verify relationship was created
        with db_session() as session:
            relationships = session.execute(
                select(Relationship).where(
                    Relationship.source_id == parent_id,
                    Relationship.target_id == specialized_id,
                )
            ).scalars().all()
            
            assert len(relationships) == 1
            assert relationships[0].relation_type == "has_headquarters"
    
    def test_detect_specialized_type_headquarters(self, db_session):
        """Test detecting headquarters type from context."""
        merger = EntityMerger(db_session)
        
        result = merger.detect_specialized_type(
            name="One Microsoft Way",
            context="The headquarters of Microsoft is located at One Microsoft Way in Redmond",
            parent_kind="location",
        )
        
        assert result == "headquarters"
    
    def test_detect_specialized_type_ceo(self, db_session):
        """Test detecting CEO type from context."""
        merger = EntityMerger(db_session)
        
        result = merger.detect_specialized_type(
            name="Tim Cook",
            context="Tim Cook is the CEO of Apple Inc.",
            parent_kind="person",
        )
        
        assert result == "ceo"
    
    def test_find_existing_entity_exact_match(self, db_session):
        """Test finding entity by exact name match."""
        merger = EntityMerger(db_session)
        
        # Create entity
        merger.get_or_create_entity(
            name="Amazon.com Inc.",
            kind="company",
            data={"industry": "E-commerce"},
        )
        
        # Find by exact name
        found = merger.find_existing_entity("Amazon.com Inc.")
        
        assert found is not None
        assert found["name"] == "Amazon.com Inc."
        assert found["kind"] == "company"
    
    def test_find_existing_entity_case_insensitive(self, db_session):
        """Test finding entity with case-insensitive match."""
        merger = EntityMerger(db_session)
        
        # Create entity
        merger.get_or_create_entity(
            name="Tesla Inc.",
            kind="company",
        )
        
        # Find with different case
        found = merger.find_existing_entity("TESLA INC.")
        
        assert found is not None
        assert found["name"] == "Tesla Inc."


class TestFieldDiscoveryTracker:
    """Test FieldDiscoveryTracker functionality."""
    
    def test_log_discovery_success(self, db_session):
        """Test logging a successful field discovery."""
        tracker = FieldDiscoveryTracker(db_session)
        
        log_id = tracker.log_discovery(
            field_name="revenue",
            entity_type="company",
            was_successful=True,
            extraction_confidence=0.95,
            discovery_method="llm",
            context_snippet="The company reported $100B in annual revenue",
        )
        
        assert log_id is not None
        
        # Verify log was created
        with db_session() as session:
            log = session.execute(
                select(FieldDiscoveryLog).where(FieldDiscoveryLog.id == log_id)
            ).scalar_one()
            
            assert log.field_name == "revenue"
            assert log.was_successful is True
            assert log.extraction_confidence == 0.95
    
    def test_get_field_success_rate(self, db_session):
        """Test calculating field success rate."""
        tracker = FieldDiscoveryTracker(db_session)
        
        # Log multiple attempts
        tracker.log_discovery("ceo", "company", True, 0.9)
        tracker.log_discovery("ceo", "company", True, 0.85)
        tracker.log_discovery("ceo", "company", False)
        tracker.log_discovery("ceo", "company", True, 0.95)
        
        success_rate = tracker.get_field_success_rate("ceo", "company")
        
        assert success_rate == pytest.approx(0.75, rel=0.01)  # 3/4 = 0.75


class TestIntelExtractorEntityTypes:
    """Test IntelExtractor entity type detection."""
    
    def test_extract_ceo_type(self):
        """Test that CEO is detected from person data."""
        extractor = IntelExtractor()
        
        finding = {
            "persons": [
                {"name": "Tim Cook", "title": "CEO", "role": "chief executive"}
            ]
        }
        
        entities = extractor.extract_entities_from_finding(finding)
        
        assert len(entities) == 1
        assert entities[0]["name"] == "Tim Cook"
        assert entities[0]["kind"] == "ceo"
    
    def test_extract_founder_type(self):
        """Test that founder is detected from person data."""
        extractor = IntelExtractor()
        
        finding = {
            "persons": [
                {"name": "Bill Gates", "title": "Co-founder", "role": "founder"}
            ]
        }
        
        entities = extractor.extract_entities_from_finding(finding)
        
        assert len(entities) == 1
        assert entities[0]["name"] == "Bill Gates"
        assert entities[0]["kind"] == "founder"
    
    def test_extract_headquarters_type(self):
        """Test that headquarters is detected from location data."""
        extractor = IntelExtractor()
        
        finding = {
            "locations": [
                {
                    "address": "1 Infinite Loop",
                    "city": "Cupertino",
                    "type": "headquarters"
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(finding)
        
        assert len(entities) == 1
        assert entities[0]["kind"] == "headquarters"
    
    def test_extract_headquarters_from_context(self):
        """Test that headquarters is detected from context text."""
        extractor = IntelExtractor()
        
        finding = {
            "locations": [
                {
                    "address": "1 Microsoft Way",
                    "city": "Redmond",
                    "type": "office"
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(
            finding,
            context_text="The corporate headquarters is located at 1 Microsoft Way"
        )
        
        assert len(entities) == 1
        # Should detect headquarters from context
        assert entities[0]["kind"] == "headquarters"
    
    def test_suggested_relationship_for_ceo(self):
        """Test that CEO entities have suggested relationship to company."""
        extractor = IntelExtractor()
        
        finding = {
            "persons": [
                {"name": "Sundar Pichai", "title": "CEO", "role": "chief executive"}
            ]
        }
        
        entities = extractor.extract_entities_from_finding(
            finding,
            primary_entity_name="Google LLC"
        )
        
        assert len(entities) == 1
        assert "suggested_relationship" in entities[0]
        assert entities[0]["suggested_relationship"]["target"] == "Google LLC"
        assert entities[0]["suggested_relationship"]["relation_type"] == "ceo_of"
    
    def test_suggested_relationship_for_headquarters(self):
        """Test that headquarters entities have suggested relationship to company."""
        extractor = IntelExtractor()
        
        finding = {
            "locations": [
                {
                    "address": "One Apple Park Way",
                    "city": "Cupertino",
                    "type": "headquarters"
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(
            finding,
            primary_entity_name="Apple Inc."
        )
        
        assert len(entities) == 1
        assert "suggested_relationship" in entities[0]
        assert entities[0]["suggested_relationship"]["target"] == "Apple Inc."
        assert entities[0]["suggested_relationship"]["relation_type"] == "headquarters_of"


class TestEntityTypeHierarchy:
    """Test entity type hierarchy definitions."""
    
    def test_headquarters_is_subtype_of_address(self):
        """Verify headquarters is defined as subtype of address."""
        assert ENTITY_TYPE_HIERARCHY.get("headquarters") == "address"
    
    def test_ceo_is_subtype_of_person(self):
        """Verify ceo is defined as subtype of person."""
        assert ENTITY_TYPE_HIERARCHY.get("ceo") == "person"
    
    def test_subsidiary_is_subtype_of_company(self):
        """Verify subsidiary is defined as subtype of company."""
        assert ENTITY_TYPE_HIERARCHY.get("subsidiary") == "company"
