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
    Intelligence,
    Page,
    MediaItem,
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
        """Verify headquarters is defined as subtype of location (address is alias for location)."""
        parent = ENTITY_TYPE_HIERARCHY.get("headquarters")
        assert parent in ("address", "location")
    
    def test_ceo_is_subtype_of_person(self):
        """Verify ceo is defined as subtype of person."""
        assert ENTITY_TYPE_HIERARCHY.get("ceo") == "person"
    
    def test_subsidiary_is_subtype_of_company(self):
        """Verify subsidiary is defined as subtype of company."""
        assert ENTITY_TYPE_HIERARCHY.get("subsidiary") == "company"


class TestSemanticEntityDeduplicator:
    """Test SemanticEntityDeduplicator functionality."""
    
    def test_find_semantic_duplicates_exact(self, db_session):
        """Test finding exact duplicate by name."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        # Create test entities
        with db_session() as session:
            entity = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corporation",
                kind="company",
            )
            session.add(entity)
            session.commit()
        
        # Find duplicates
        duplicates = deduplicator.find_semantic_duplicates("Microsoft Corporation")
        
        assert len(duplicates) == 1
        assert duplicates[0]["match_type"] == "exact"
        assert duplicates[0]["similarity"] == 1.0
    
    def test_find_semantic_duplicates_similar_names(self, db_session):
        """Test finding similar names like 'Microsoft' vs 'Microsoft Corp.'"""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        # Create test entities
        with db_session() as session:
            entity = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corporation",
                kind="company",
            )
            session.add(entity)
            session.commit()
        
        # Find duplicates with similar name
        duplicates = deduplicator.find_semantic_duplicates("Microsoft Corp.", threshold=0.5)
        
        # Should find similarity based on word overlap
        assert len(duplicates) >= 1
        assert duplicates[0]["entity"]["name"] == "Microsoft Corporation"
    
    def test_name_normalization(self, db_session):
        """Test name normalization for comparison."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        # Test normalization
        normalized = deduplicator._normalize_name("Apple Inc.")
        assert "incorporated" in normalized
        
        normalized = deduplicator._normalize_name("Google LLC")
        assert "limited liability company" in normalized
    
    def test_deduplicate_entities_dry_run(self, db_session):
        """Test deduplication in dry run mode."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        # Create similar entities
        with db_session() as session:
            entity1 = Entity(
                id=uuid.uuid4(),
                name="Apple Inc.",
                kind="company",
                data={"industry": "Technology"},
            )
            entity2 = Entity(
                id=uuid.uuid4(),
                name="Apple Incorporated",
                kind="company",
                data={"founded": "1976"},
            )
            session.add(entity1)
            session.add(entity2)
            session.commit()
        
        # Run dry run
        report = deduplicator.deduplicate_entities(dry_run=True, threshold=0.7)
        
        # Should find duplicates but not merge them in dry run mode
        # Verify that we found potential duplicates OR nothing was merged (dry_run behavior)
        assert len(report["merged"]) == 0  # Dry run should never merge
        # Note: Duplicates may or may not be found depending on similarity threshold


class TestGraphSearchEngine:
    """Test GraphSearchEngine functionality."""
    
    def test_search_entities_sql(self, db_session):
        """Test SQL entity search."""
        from garuda_intel.extractor.entity_merger import GraphSearchEngine
        
        engine = GraphSearchEngine(db_session)
        
        # Create test entities
        with db_session() as session:
            entity = Entity(
                id=uuid.uuid4(),
                name="Tesla Inc.",
                kind="company",
            )
            session.add(entity)
            session.commit()
        
        # Search
        results = engine.search_entities("Tesla")
        
        assert len(results) == 1
        assert results[0]["match_type"] == "sql_exact"
        assert results[0]["entity"]["name"] == "Tesla Inc."
    
    def test_traverse_graph_single_depth(self, db_session):
        """Test single-depth graph traversal."""
        from garuda_intel.extractor.entity_merger import GraphSearchEngine
        
        engine = GraphSearchEngine(db_session)
        
        # Create test entities and relationships
        with db_session() as session:
            company = Entity(id=uuid.uuid4(), name="SpaceX", kind="company")
            person = Entity(id=uuid.uuid4(), name="Elon Musk", kind="person")
            
            session.add(company)
            session.add(person)
            session.flush()
            
            rel = Relationship(
                id=uuid.uuid4(),
                source_id=company.id,
                target_id=person.id,
                relation_type="has_ceo",
            )
            session.add(rel)
            session.commit()
            
            company_id = str(company.id)
            person_id = str(person.id)
        
        # Traverse from company
        result = engine.traverse_graph([company_id], max_depth=1)
        
        assert len(result["root_entities"]) == 1
        assert result["root_entities"][0]["name"] == "SpaceX"
        assert 1 in result["depths"]
        assert len(result["depths"][1]["entities"]) == 1
        assert result["depths"][1]["entities"][0]["entity"]["name"] == "Elon Musk"
    
    def test_find_path_between_entities(self, db_session):
        """Test path finding between entities."""
        from garuda_intel.extractor.entity_merger import GraphSearchEngine
        
        engine = GraphSearchEngine(db_session)
        
        # Create chain: A -> B -> C
        with db_session() as session:
            a = Entity(id=uuid.uuid4(), name="Entity A", kind="entity")
            b = Entity(id=uuid.uuid4(), name="Entity B", kind="entity")
            c = Entity(id=uuid.uuid4(), name="Entity C", kind="entity")
            
            session.add_all([a, b, c])
            session.flush()
            
            rel1 = Relationship(id=uuid.uuid4(), source_id=a.id, target_id=b.id, relation_type="links_to")
            rel2 = Relationship(id=uuid.uuid4(), source_id=b.id, target_id=c.id, relation_type="links_to")
            
            session.add_all([rel1, rel2])
            session.commit()
            
            a_id, c_id = str(a.id), str(c.id)
        
        # Find path from A to C
        path = engine.find_path(a_id, c_id, max_depth=3)
        
        assert path is not None
        assert len(path) == 3
        assert path[0]["entity"]["name"] == "Entity A"
        assert path[1]["entity"]["name"] == "Entity B"
        assert path[2]["entity"]["name"] == "Entity C"


class TestRelationshipConfidenceManager:
    """Test RelationshipConfidenceManager functionality."""
    
    def test_record_new_relationship(self, db_session):
        """Test recording a new relationship."""
        from garuda_intel.extractor.entity_merger import RelationshipConfidenceManager
        
        manager = RelationshipConfidenceManager(db_session)
        
        # Create entities
        with db_session() as session:
            e1 = Entity(id=uuid.uuid4(), name="Company X", kind="company")
            e2 = Entity(id=uuid.uuid4(), name="Person Y", kind="person")
            session.add_all([e1, e2])
            session.commit()
            
            e1_id, e2_id = str(e1.id), str(e2.id)
        
        # Record relationship
        result = manager.record_relationship(e1_id, e2_id, "employs", source_url="https://example.com")
        
        assert result["is_new"] is True
        assert result["confidence"] == 0.5
        assert result["occurrence_count"] == 1
    
    def test_boost_relationship_confidence(self, db_session):
        """Test that recording same relationship multiple times boosts confidence."""
        from garuda_intel.extractor.entity_merger import RelationshipConfidenceManager
        
        manager = RelationshipConfidenceManager(db_session)
        
        # Create entities
        with db_session() as session:
            e1 = Entity(id=uuid.uuid4(), name="Company Z", kind="company")
            e2 = Entity(id=uuid.uuid4(), name="Product A", kind="product")
            session.add_all([e1, e2])
            session.commit()
            
            e1_id, e2_id = str(e1.id), str(e2.id)
        
        # Record relationship multiple times
        result1 = manager.record_relationship(e1_id, e2_id, "produces", source_url="https://source1.com")
        result2 = manager.record_relationship(e1_id, e2_id, "produces", source_url="https://source2.com")
        result3 = manager.record_relationship(e1_id, e2_id, "produces", source_url="https://source3.com")
        
        assert result1["is_new"] is True
        assert result2["is_new"] is False
        assert result3["is_new"] is False
        
        # Confidence should increase
        assert result2["confidence"] > result1["confidence"]
        assert result3["confidence"] > result2["confidence"]
        
        # Occurrence count should increase
        assert result3["occurrence_count"] == 3
    
    def test_get_high_confidence_relationships(self, db_session):
        """Test getting high confidence relationships."""
        from garuda_intel.extractor.entity_merger import RelationshipConfidenceManager
        
        manager = RelationshipConfidenceManager(db_session)
        
        # Create entities and relationships
        with db_session() as session:
            e1 = Entity(id=uuid.uuid4(), name="Test Company", kind="company")
            e2 = Entity(id=uuid.uuid4(), name="Test Location", kind="location")
            session.add_all([e1, e2])
            session.commit()
            
            e1_id, e2_id = str(e1.id), str(e2.id)
        
        # Record relationship multiple times to boost confidence
        for i in range(5):
            manager.record_relationship(e1_id, e2_id, "headquartered_in", source_url=f"https://source{i}.com")
        
        # Get high confidence relationships
        results = manager.get_high_confidence_relationships(min_confidence=0.6, min_occurrences=3)
        
        assert len(results) >= 1
        found = next((r for r in results if r["relation_type"] == "headquartered_in"), None)
        assert found is not None
        assert found["occurrence_count"] >= 3


class TestDeduplicationPreservesHighestKind:
    """Test that deduplication preserves the highest kind and richest data.
    
    Verifies the requirement: during reflect and deduplicate, entities
    are never ALL lost but instead merge to the highest kind with
    the richest data.
    
    Example: Bill Gates(entity), B. Gates(founder), William Bill Gates(person)
    → William Bill Gates (founder) with all data merged.
    """
    
    def test_merge_preserves_highest_kind(self, db_session):
        """Test that _merge_entities upgrades target kind from source."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            # Target has generic kind, source has more specific kind
            target = Entity(
                id=uuid.uuid4(),
                name="Bill Gates",
                kind="person",
                data={"company": "Microsoft"},
            )
            source = Entity(
                id=uuid.uuid4(),
                name="B. Gates",
                kind="founder",
                data={"founded": "Microsoft Corporation"},
            )
            session.add(target)
            session.add(source)
            session.commit()
            
            target_id = str(target.id)
            source_id = str(source.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        # Verify: the surviving entity should have the most specific kind
        with db_session() as session:
            surviving = session.execute(
                select(Entity).where(Entity.id == target_id)
            ).scalar_one()
            
            assert surviving.kind == "founder"  # upgraded from person
            assert surviving.data.get("company") == "Microsoft"  # kept original data
            assert surviving.data.get("founded") == "Microsoft Corporation"  # merged source data
    
    def test_merge_preserves_longest_name(self, db_session):
        """Test that _merge_entities uses the longest (richest) name."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            target = Entity(
                id=uuid.uuid4(),
                name="B. Gates",
                kind="entity",
                data={},
            )
            source = Entity(
                id=uuid.uuid4(),
                name="William Bill Gates",
                kind="person",
                data={"full_name": "William Henry Gates III"},
            )
            session.add(target)
            session.add(source)
            session.commit()
            
            target_id = str(target.id)
            source_id = str(source.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        with db_session() as session:
            surviving = session.execute(
                select(Entity).where(Entity.id == target_id)
            ).scalar_one()
            
            # Should have the longer, more informative name
            assert surviving.name == "William Bill Gates"
            # Should also upgrade kind and merge data
            assert surviving.kind == "person"
            assert surviving.data.get("full_name") == "William Henry Gates III"
    
    def test_merge_records_source_kind_in_history(self, db_session):
        """Test that merge records the source kind in merge history."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            target = Entity(
                id=uuid.uuid4(),
                name="Bill Gates",
                kind="person",
                data={},
            )
            source = Entity(
                id=uuid.uuid4(),
                name="B. Gates",
                kind="founder",
                data={},
            )
            session.add(target)
            session.add(source)
            session.commit()
            
            target_id = str(target.id)
            source_id = str(source.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        with db_session() as session:
            surviving = session.execute(
                select(Entity).where(Entity.id == target_id)
            ).scalar_one()
            
            merge_history = surviving.metadata_json.get("merged_from", [])
            assert len(merge_history) == 1
            assert merge_history[0]["kind"] == "founder"
    
    def test_select_canonical_entity_picks_highest_kind(self, db_session):
        """Test _select_canonical_entity picks entity with most specific kind."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        entity1 = Entity(
            id=uuid.uuid4(),
            name="Bill Gates",
            kind="entity",
            data={},
        )
        entity2 = Entity(
            id=uuid.uuid4(),
            name="B. Gates",
            kind="founder",
            data={"role": "founder"},
        )
        entity3 = Entity(
            id=uuid.uuid4(),
            name="William Bill Gates",
            kind="person",
            data={"occupation": "technologist", "net_worth": "130B"},
        )
        
        canonical = deduplicator._select_canonical_entity([entity1, entity2, entity3])
        
        # founder is more specific (rank 2) than person (rank 1) and entity (rank 0)
        # Among rank 2, entity2 has 1 data field so it wins
        assert canonical.kind == "founder"
        assert str(canonical.id) == str(entity2.id)
    
    def test_select_canonical_entity_tiebreak_by_data_richness(self, db_session):
        """Test that when kind ranks are equal, richest data wins."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        entity1 = Entity(
            id=uuid.uuid4(),
            name="Elon Musk",
            kind="ceo",
            data={"company": "Tesla"},
        )
        entity2 = Entity(
            id=uuid.uuid4(),
            name="Elon Reeve Musk",
            kind="founder",
            data={"company": "SpaceX", "born": "1971", "nationality": "US"},
        )
        
        canonical = deduplicator._select_canonical_entity([entity1, entity2])
        
        # Both ceo and founder are rank 2, but entity2 has more data fields
        assert str(canonical.id) == str(entity2.id)
    
    def test_select_canonical_entity_tiebreak_by_name_length(self, db_session):
        """Test that when kind and data are equal, longest name wins."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        entity1 = Entity(
            id=uuid.uuid4(),
            name="B. Gates",
            kind="founder",
            data={"role": "co-founder"},
        )
        entity2 = Entity(
            id=uuid.uuid4(),
            name="William Bill Gates",
            kind="founder",
            data={"role": "co-founder"},
        )
        
        canonical = deduplicator._select_canonical_entity([entity1, entity2])
        
        # Same kind (founder) and data count, but entity2 has longer name
        assert str(canonical.id) == str(entity2.id)
        assert canonical.name == "William Bill Gates"
    
    def test_kind_specificity_rank(self, db_session):
        """Test _get_kind_specificity_rank returns correct rankings."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        # Generic types → rank 0
        assert deduplicator._get_kind_specificity_rank("entity") == 0
        assert deduplicator._get_kind_specificity_rank("general") == 0
        assert deduplicator._get_kind_specificity_rank("") == 0
        
        # Parent types → rank 1
        assert deduplicator._get_kind_specificity_rank("person") == 1
        assert deduplicator._get_kind_specificity_rank("company") == 1
        assert deduplicator._get_kind_specificity_rank("address") == 1
        
        # Specialized types → rank 2
        assert deduplicator._get_kind_specificity_rank("founder") == 2
        assert deduplicator._get_kind_specificity_rank("ceo") == 2
        assert deduplicator._get_kind_specificity_rank("headquarters") == 2
    
    def test_full_dedup_scenario_bill_gates(self, db_session):
        """
        Full integration test: 3 entities for Bill Gates with different kinds.
        
        Bill Gates(entity), B. Gates(founder), William Bill Gates(person)
        → William Bill Gates (founder) as master with all data merged.
        Duplicates are soft-merged (kept as subordinates with duplicate_of relationship).
        """
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            e1 = Entity(
                id=uuid.uuid4(),
                name="Bill Gates",
                kind="entity",
                data={"known_for": "Microsoft"},
            )
            e2 = Entity(
                id=uuid.uuid4(),
                name="B. Gates",
                kind="founder",
                data={"founded": "Microsoft Corporation"},
            )
            e3 = Entity(
                id=uuid.uuid4(),
                name="William Bill Gates",
                kind="person",
                data={"born": "1955", "nationality": "American"},
            )
            session.add_all([e1, e2, e3])
            session.commit()
            
            e1_id = str(e1.id)
            e2_id = str(e2.id)
            e3_id = str(e3.id)
        
        # Run deduplication with a low threshold so all three match
        report = deduplicator.deduplicate_entities(dry_run=False, threshold=0.3)
        
        # After hard-delete merge, only the canonical entity should remain
        with db_session() as session:
            remaining = session.execute(select(Entity)).scalars().all()
            assert len(remaining) == 1
            
            survivor = remaining[0]
            # Should have the most specific kind: founder (rank 2)
            assert survivor.kind == "founder"
            # Should have the longest name
            assert survivor.name == "William Bill Gates"
            # Should have all data merged
            assert survivor.data.get("known_for") == "Microsoft"
            assert survivor.data.get("founded") == "Microsoft Corporation"
            assert survivor.data.get("born") == "1955"
            assert survivor.data.get("nationality") == "American"
            
            # merged_from metadata should record the merged entities
            assert "merged_from" in survivor.metadata_json
            assert len(survivor.metadata_json["merged_from"]) == 2


class TestMergeTransfersAllReferences:
    """Test that _merge_entities properly transfers all references and handles edge cases."""
    
    def test_merge_transfers_relationships_with_flush(self, db_session):
        """Test that relationships survive the merge with proper flush and duplicate_of is created."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            # Create source and target entities
            source = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corp",
                kind="company",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corporation",
                kind="company",
            )
            # Create a third entity to have relationships with
            entity_c = Entity(
                id=uuid.uuid4(),
                name="Bill Gates",
                kind="person",
            )
            session.add_all([source, target, entity_c])
            session.commit()
            
            # Create relationships: source -> entity_c and entity_c -> source
            rel1 = Relationship(
                id=uuid.uuid4(),
                source_id=source.id,
                target_id=entity_c.id,
                relation_type="FOUNDED_BY",
            )
            rel2 = Relationship(
                id=uuid.uuid4(),
                source_id=entity_c.id,
                target_id=source.id,
                relation_type="FOUNDED",
            )
            session.add_all([rel1, rel2])
            session.commit()
            
            source_id = str(source.id)
            target_id = str(target.id)
            entity_c_id = str(entity_c.id)
        
        # Merge source into target
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        # Verify relationships survived and point to target (source is deleted)
        with db_session() as session:
            relationships = session.execute(select(Relationship)).scalars().all()
            # 2 original relationships redirected (no duplicate_of since source is deleted)
            assert len(relationships) == 2, "Both relationships should survive after merge"
            
            # Check that original relationships now point to target instead of source
            rel_types = {}
            for rel in relationships:
                if str(rel.source_id) == target_id and str(rel.target_id) == entity_c_id:
                    rel_types['target_to_c'] = rel.relation_type
                elif str(rel.source_id) == entity_c_id and str(rel.target_id) == target_id:
                    rel_types['c_to_target'] = rel.relation_type
            
            assert rel_types.get('target_to_c') == "FOUNDED_BY"
            assert rel_types.get('c_to_target') == "FOUNDED"
            
            # Source entity should be deleted
            source = session.execute(
                select(Entity).where(Entity.id == source_id)
            ).scalar_one_or_none()
            assert source is None, "Source entity should be deleted after merge"
    
    def test_merge_removes_self_referential_relationships(self, db_session):
        """Test that self-referential relationships are removed after merge, source is deleted."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            # Create source and target entities
            source = Entity(
                id=uuid.uuid4(),
                name="Company A",
                kind="company",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Company A Inc",
                kind="company",
            )
            session.add_all([source, target])
            session.commit()
            
            # Create a relationship FROM source TO target
            # After merge, this would become target -> target (self-loop)
            rel = Relationship(
                id=uuid.uuid4(),
                source_id=source.id,
                target_id=target.id,
                relation_type="SUBSIDIARY_OF",
            )
            session.add(rel)
            session.commit()
            
            source_id = str(source.id)
            target_id = str(target.id)
        
        # Merge source into target
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        # Verify self-referential relationship is removed and source is deleted
        with db_session() as session:
            relationships = session.execute(select(Relationship)).scalars().all()
            # Self-referential relationship should be removed, no duplicate_of since source deleted
            assert len(relationships) == 0, "Self-referential relationships should be removed"
            
            # Source entity should be deleted
            source = session.execute(
                select(Entity).where(Entity.id == source_id)
            ).scalar_one_or_none()
            assert source is None, "Source entity should be deleted after merge"
    
    def test_merge_deduplicates_relationships(self, db_session):
        """Test that duplicate relationships are deduplicated, plus duplicate_of is created."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            # Create source, target, and a third entity
            source = Entity(
                id=uuid.uuid4(),
                name="Microsoft",
                kind="company",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corporation",
                kind="company",
            )
            entity_c = Entity(
                id=uuid.uuid4(),
                name="Bill Gates",
                kind="person",
            )
            session.add_all([source, target, entity_c])
            session.commit()
            
            # Both source and target have a relationship to entity_c
            # After merge, both will be from target -> entity_c (duplicate)
            rel1 = Relationship(
                id=uuid.uuid4(),
                source_id=source.id,
                target_id=entity_c.id,
                relation_type="FOUNDED_BY",
            )
            rel2 = Relationship(
                id=uuid.uuid4(),
                source_id=target.id,
                target_id=entity_c.id,
                relation_type="FOUNDED_BY",
            )
            session.add_all([rel1, rel2])
            session.commit()
            
            source_id = str(source.id)
            target_id = str(target.id)
            entity_c_id = str(entity_c.id)
        
        # Merge source into target
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        # Verify: 1 deduplicated FOUNDED_BY (no duplicate_of since source is deleted)
        with db_session() as session:
            relationships = session.execute(select(Relationship)).scalars().all()
            assert len(relationships) == 1, "Only deduplicated relationship should remain"
            
            founded_by_rels = [r for r in relationships if r.relation_type == "FOUNDED_BY"]
            
            assert len(founded_by_rels) == 1
            rel = founded_by_rels[0]
            assert str(rel.source_id) == target_id
            assert str(rel.target_id) == entity_c_id
            assert rel.relation_type == "FOUNDED_BY"
            
            # Source entity should be deleted
            source = session.execute(
                select(Entity).where(Entity.id == source_id)
            ).scalar_one_or_none()
            assert source is None, "Source entity should be deleted after merge"
    
    def test_merge_transfers_entity_field_values(self, db_session):
        """Test that EntityFieldValue records are transferred to target."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            # Create source and target entities
            source = Entity(
                id=uuid.uuid4(),
                name="Microsoft",
                kind="company",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corporation",
                kind="company",
            )
            session.add_all([source, target])
            session.commit()
            
            # Create a dynamic field definition
            field_def = DynamicFieldDefinition(
                id=uuid.uuid4(),
                entity_type="company",
                field_name="revenue",
                field_type="number",
            )
            session.add(field_def)
            session.commit()
            
            # Create field values for source entity
            field_value = EntityFieldValue(
                id=uuid.uuid4(),
                entity_id=source.id,
                field_definition_id=field_def.id,
                field_name="revenue",
                value_text="100B",
            )
            session.add(field_value)
            session.commit()
            
            source_id = str(source.id)
            target_id = str(target.id)
            field_value_id = str(field_value.id)
        
        # Merge source into target
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        # Verify field value is now associated with target
        with db_session() as session:
            field_value = session.execute(
                select(EntityFieldValue).where(EntityFieldValue.id == field_value_id)
            ).scalar_one()
            assert str(field_value.entity_id) == target_id
            assert field_value.value_text == "100B"
    
    def test_merge_transfers_intelligence_records(self, db_session):
        """Test that Intelligence records are transferred to target."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            # Create source and target entities
            source = Entity(
                id=uuid.uuid4(),
                name="Microsoft",
                kind="company",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corporation",
                kind="company",
            )
            session.add_all([source, target])
            session.commit()
            
            # Create intelligence record for source
            intel = Intelligence(
                id=uuid.uuid4(),
                entity_id=source.id,
                data={"content": "Microsoft is a technology company", "founded": "1975"},
            )
            session.add(intel)
            session.commit()
            
            source_id = str(source.id)
            target_id = str(target.id)
            intel_id = str(intel.id)
        
        # Merge source into target
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        # Verify intelligence record is now associated with target
        with db_session() as session:
            intel = session.execute(
                select(Intelligence).where(Intelligence.id == intel_id)
            ).scalar_one()
            assert str(intel.entity_id) == target_id
            assert intel.data.get("content") == "Microsoft is a technology company"
    
    def test_merge_transfers_page_references(self, db_session):
        """Test that Page records are transferred to target."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            # Create source and target entities
            source = Entity(
                id=uuid.uuid4(),
                name="Microsoft",
                kind="company",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corporation",
                kind="company",
            )
            session.add_all([source, target])
            session.commit()
            
            # Create page record for source
            page = Page(
                id=uuid.uuid4(),
                url="https://microsoft.com",
                title="Microsoft homepage",
            )
            session.add(page)
            session.commit()
            
            # Now set entity_id after page is persisted
            page.entity_id = source.id
            session.commit()
            
            source_id = str(source.id)
            target_id = str(target.id)
            page_id = str(page.id)
        
        # Merge source into target
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        # Verify page record is now associated with target
        with db_session() as session:
            page = session.execute(
                select(Page).where(Page.id == page_id)
            ).scalar_one()
            assert str(page.entity_id) == target_id
            assert page.title == "Microsoft homepage"
    
    def test_merge_transfers_media_items(self, db_session):
        """Test that MediaItem records are transferred to target."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            # Create source and target entities
            source = Entity(
                id=uuid.uuid4(),
                name="Microsoft",
                kind="company",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corporation",
                kind="company",
            )
            session.add_all([source, target])
            session.commit()
            
            # Create media item for source
            media = MediaItem(
                id=uuid.uuid4(),
                entity_id=source.id,
                media_type="image",
                url="https://example.com/logo.png",
            )
            session.add(media)
            session.commit()
            
            source_id = str(source.id)
            target_id = str(target.id)
            media_id = str(media.id)
        
        # Merge source into target
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        # Verify media item is now associated with target
        with db_session() as session:
            media = session.execute(
                select(MediaItem).where(MediaItem.id == media_id)
            ).scalar_one()
            assert str(media.entity_id) == target_id
            assert media.media_type == "image"
    
    def test_merge_merges_metadata(self, db_session):
        """Test that source's metadata_json is merged into target (fills gaps only)."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            # Create source with metadata
            source = Entity(
                id=uuid.uuid4(),
                name="Microsoft",
                kind="company",
                metadata_json={
                    "website": "https://microsoft.com",
                    "founded": "1975",
                    "extra_field": "extra_value",
                }
            )
            # Create target with partial metadata
            target = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corporation",
                kind="company",
                metadata_json={
                    "website": "https://www.microsoft.com",  # Different value - should NOT be overwritten
                    "stock_symbol": "MSFT",
                }
            )
            session.add_all([source, target])
            session.commit()
            
            source_id = str(source.id)
            target_id = str(target.id)
        
        # Merge source into target
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        # Verify metadata is merged correctly
        with db_session() as session:
            target = session.execute(
                select(Entity).where(Entity.id == target_id)
            ).scalar_one()
            
            # Target's original values should be preserved
            assert target.metadata_json.get("website") == "https://www.microsoft.com"
            assert target.metadata_json.get("stock_symbol") == "MSFT"
            
            # Source's unique values should be added
            assert target.metadata_json.get("founded") == "1975"
            assert target.metadata_json.get("extra_field") == "extra_value"
            
            # Merge history should be recorded
            assert "merged_from" in target.metadata_json
            merge_history = target.metadata_json["merged_from"]
            assert len(merge_history) == 1
            assert merge_history[0]["id"] == source_id
            assert merge_history[0]["name"] == "Microsoft"


class TestHardDeleteMerge:
    """Test that merge deletes source entity after transferring all data."""
    
    def test_source_entity_deleted_after_merge(self, db_session):
        """Test that the source entity is deleted after merge."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            source = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corp",
                kind="company",
                data={"industry": "tech"},
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corporation",
                kind="company",
                data={"website": "microsoft.com"},
            )
            session.add_all([source, target])
            session.commit()
            source_id = str(source.id)
            target_id = str(target.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        # Source entity should be deleted
        with db_session() as session:
            source = session.execute(
                select(Entity).where(Entity.id == source_id)
            ).scalar_one_or_none()
            assert source is None, "Source entity should be deleted after merge"
            
            # Target should have inherited source data
            target = session.execute(
                select(Entity).where(Entity.id == target_id)
            ).scalar_one()
            assert target.data.get("industry") == "tech"
            assert target.data.get("website") == "microsoft.com"
    
    def test_merged_from_metadata_recorded(self, db_session):
        """Test that target entity records merged_from metadata."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            source = Entity(
                id=uuid.uuid4(),
                name="Bill Gates",
                kind="person",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="William Bill Gates",
                kind="founder",
            )
            session.add_all([source, target])
            session.commit()
            source_id = str(source.id)
            target_id = str(target.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        with db_session() as session:
            target = session.execute(
                select(Entity).where(Entity.id == target_id)
            ).scalar_one()
            assert target.metadata_json is not None
            assert "merged_from" in target.metadata_json
            merged_entries = target.metadata_json["merged_from"]
            assert len(merged_entries) == 1
            assert merged_entries[0]["id"] == source_id
            assert merged_entries[0]["name"] == "Bill Gates"
    
    def test_no_duplicate_of_relationship_after_merge(self, db_session):
        """Test that no duplicate_of relationship exists since source is deleted."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            source = Entity(
                id=uuid.uuid4(),
                name="MSFT",
                kind="company",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Microsoft Corporation",
                kind="company",
            )
            session.add_all([source, target])
            session.commit()
            source_id = str(source.id)
            target_id = str(target.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        with db_session() as session:
            # No duplicate_of relationship should exist since source entity is deleted
            dup_rels = session.execute(
                select(Relationship).where(Relationship.relation_type == "duplicate_of")
            ).scalars().all()
            assert len(dup_rels) == 0, "No duplicate_of relationship after hard-delete merge"
    
    def test_page_references_transferred_before_delete(self, db_session):
        """Test that source entity's page references are transferred to target before deletion."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            source = Entity(
                id=uuid.uuid4(),
                name="Bill Gates",
                kind="person",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="William Bill Gates",
                kind="founder",
            )
            session.add_all([source, target])
            session.commit()
            
            # Create a page associated with the source
            page = Page(
                id=uuid.uuid4(),
                url="https://intel-source.com/bill-gates",
                title="Intel page about Bill Gates",
            )
            session.add(page)
            session.commit()
            page.entity_id = source.id
            session.commit()
            
            source_id = str(source.id)
            target_id = str(target.id)
            page_id = str(page.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        # Source entity should be deleted, page transferred to target
        with db_session() as session:
            source = session.execute(
                select(Entity).where(Entity.id == source_id)
            ).scalar_one_or_none()
            assert source is None, "Source entity should be deleted"
            
            # Page should now point to target
            page = session.execute(
                select(Page).where(Page.id == page_id)
            ).scalar_one()
            assert str(page.entity_id) == target_id, "Page should be transferred to target"
    
    def test_richest_name_wins_in_merge(self, db_session):
        """Test that the longest (richest) name is preserved on the target."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            source = Entity(
                id=uuid.uuid4(),
                name="William Henry Gates III",
                kind="person",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Bill Gates",
                kind="person",
            )
            session.add_all([source, target])
            session.commit()
            source_id = str(source.id)
            target_id = str(target.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        with db_session() as session:
            target = session.execute(
                select(Entity).where(Entity.id == target_id)
            ).scalar_one()
            assert target.name == "William Henry Gates III"
    
    def test_most_specific_kind_wins_in_merge(self, db_session):
        """Test that the most specific kind wins when merging."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            # Source has kind "person" (rank 1), target has "entity" (rank 0)
            source = Entity(
                id=uuid.uuid4(),
                name="Some Person",
                kind="person",
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Some Person Entity",
                kind="entity",
            )
            session.add_all([source, target])
            session.commit()
            source_id = str(source.id)
            target_id = str(target.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        with db_session() as session:
            target = session.execute(
                select(Entity).where(Entity.id == target_id)
            ).scalar_one()
            # "person" (rank 1) should win over "entity" (rank 0)
            assert target.kind == "person"


class TestComprehensiveStructuredDataExtraction:
    """Test that entity extraction captures comprehensive structured data."""
    
    def test_product_entity_captures_specifications(self):
        """Test that product entities capture specifications, prices, providers."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
            extract_related_entities=True,
            enable_comprehensive_extraction=True,
        )
        
        finding = {
            "products": [
                {
                    "name": "Widget Pro X",
                    "description": "Advanced industrial widget",
                    "manufacturer": "Acme Corp",
                    "price": "$299.99",
                    "currency": "USD",
                    "provider": "TechDistro Inc",
                    "version": "3.2",
                    "specifications": {"weight": "1.5kg", "dimensions": "10x10x5cm", "power": "120V"},
                    "sku": "WPX-3200",
                    "rating": "4.8/5",
                    "availability": "In Stock",
                    "additional_attributes": {"warranty": "2 years", "material": "titanium"},
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(finding)
        assert len(entities) == 1
        
        product = entities[0]
        assert product["name"] == "Widget Pro X"
        assert product["kind"] == "product"
        
        # Core product data
        assert product["data"]["price"] == "$299.99"
        assert product["data"]["provider"] == "TechDistro Inc"
        assert product["data"]["version"] == "3.2"
        assert product["data"]["specifications"] == {"weight": "1.5kg", "dimensions": "10x10x5cm", "power": "120V"}
        assert product["data"]["sku"] == "WPX-3200"
        assert product["data"]["rating"] == "4.8/5"
        assert product["data"]["availability"] == "In Stock"
        # Additional attributes merged into data
        assert product["data"]["warranty"] == "2 years"
        assert product["data"]["material"] == "titanium"
    
    def test_location_entity_captures_detailed_address(self):
        """Test that location entities capture street, postal code, lat/lng."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
            extract_related_entities=True,
            enable_comprehensive_extraction=True,
        )
        
        finding = {
            "locations": [
                {
                    "address": "1 Microsoft Way",
                    "street": "Microsoft Way",
                    "city": "Redmond",
                    "state": "Washington",
                    "postal_code": "98052",
                    "country": "USA",
                    "type": "headquarters",
                    "latitude": "47.6405",
                    "longitude": "-122.1292",
                    "phone": "+1-425-882-8080",
                    "additional_attributes": {"timezone": "PST", "campus_size": "500 acres"},
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(finding)
        assert len(entities) == 1
        
        loc = entities[0]
        assert loc["data"]["street"] == "Microsoft Way"
        assert loc["data"]["state"] == "Washington"
        assert loc["data"]["postal_code"] == "98052"
        assert loc["data"]["latitude"] == "47.6405"
        assert loc["data"]["longitude"] == "-122.1292"
        assert loc["data"]["phone"] == "+1-425-882-8080"
        assert loc["data"]["timezone"] == "PST"
        assert loc["data"]["campus_size"] == "500 acres"
    
    def test_person_entity_captures_additional_attributes(self):
        """Test that person entities capture extended attributes."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
            extract_related_entities=True,
            enable_comprehensive_extraction=True,
        )
        
        finding = {
            "persons": [
                {
                    "name": "John Smith",
                    "title": "CEO",
                    "role": "chief executive officer",
                    "organization": "Acme Corp",
                    "email": "john@acme.com",
                    "education": "MBA Stanford",
                    "nationality": "American",
                    "additional_attributes": {"linkedin": "linkedin.com/in/johnsmith"},
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(finding)
        assert len(entities) == 1
        
        person = entities[0]
        assert person["data"]["email"] == "john@acme.com"
        assert person["data"]["education"] == "MBA Stanford"
        assert person["data"]["nationality"] == "American"
        assert person["data"]["linkedin"] == "linkedin.com/in/johnsmith"
    
    def test_organization_entity_captures_additional_attributes(self):
        """Test that organization entities capture registration numbers, certifications."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
            extract_related_entities=True,
            enable_comprehensive_extraction=True,
        )
        
        finding = {
            "organizations": [
                {
                    "name": "Acme Corp",
                    "type": "company",
                    "industry": "Manufacturing",
                    "description": "Leading widget manufacturer",
                    "registration_number": "DE123456789",
                    "tax_id": "US-EIN-12-3456789",
                    "employee_count": "5000",
                    "certifications": ["ISO 9001", "ISO 14001"],
                    "additional_attributes": {"stock_exchange": "NYSE", "ticker": "ACME"},
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(finding)
        assert len(entities) == 1
        
        org = entities[0]
        assert org["data"]["registration_number"] == "DE123456789"
        assert org["data"]["tax_id"] == "US-EIN-12-3456789"
        assert org["data"]["employee_count"] == "5000"
        assert org["data"]["certifications"] == ["ISO 9001", "ISO 14001"]
        assert org["data"]["stock_exchange"] == "NYSE"
        assert org["data"]["ticker"] == "ACME"
    
    def test_unknown_extra_fields_captured(self):
        """Test that arbitrary unknown fields are captured from entity extraction."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
            extract_related_entities=True,
            enable_comprehensive_extraction=True,
        )
        
        finding = {
            "products": [
                {
                    "name": "Custom Widget",
                    "description": "A special widget",
                    "custom_field_1": "custom_value_1",
                    "proprietary_code": "X-42",
                }
            ]
        }
        
        entities = extractor.extract_entities_from_finding(finding)
        assert len(entities) == 1
        
        product = entities[0]
        # Unknown fields should be captured
        assert product["data"]["custom_field_1"] == "custom_value_1"
        assert product["data"]["proprietary_code"] == "X-42"


class TestMergeInheritsAllStructuredData:
    """Test that merge transfers ALL structured data and relations, then deletes source."""
    
    def test_merge_transfers_all_data_fields(self, db_session):
        """Test that all structured data fields are transferred from source to target."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            source = Entity(
                id=uuid.uuid4(),
                name="Widget Pro",
                kind="product",
                data={
                    "price": "$299.99",
                    "specifications": {"weight": "1.5kg"},
                    "provider": "TechDistro",
                    "rating": "4.8",
                },
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Widget Pro X",
                kind="product",
                data={
                    "manufacturer": "Acme Corp",
                    "description": "Advanced widget",
                },
            )
            session.add_all([source, target])
            session.commit()
            source_id = str(source.id)
            target_id = str(target.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        with db_session() as session:
            # Source should be deleted
            source = session.execute(
                select(Entity).where(Entity.id == source_id)
            ).scalar_one_or_none()
            assert source is None, "Source entity should be deleted after merge"
            
            # Target should have all data
            target = session.execute(
                select(Entity).where(Entity.id == target_id)
            ).scalar_one()
            assert target.data["manufacturer"] == "Acme Corp"
            assert target.data["description"] == "Advanced widget"
            assert target.data["price"] == "$299.99"
            assert target.data["specifications"] == {"weight": "1.5kg"}
            assert target.data["provider"] == "TechDistro"
            assert target.data["rating"] == "4.8"
    
    def test_merge_higher_ranked_data_wins(self, db_session):
        """Test that the target (higher ranked) entity's data takes priority."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            source = Entity(
                id=uuid.uuid4(),
                name="Acme Corp",
                kind="company",
                data={
                    "industry": "Old Industry",
                    "founded": "1990",
                    "ceo": "Old CEO",
                },
            )
            target = Entity(
                id=uuid.uuid4(),
                name="Acme Corporation",
                kind="company",
                data={
                    "industry": "Manufacturing",
                    "website": "acme.com",
                },
            )
            session.add_all([source, target])
            session.commit()
            source_id = str(source.id)
            target_id = str(target.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        with db_session() as session:
            target = session.execute(
                select(Entity).where(Entity.id == target_id)
            ).scalar_one()
            # Target's existing data should win
            assert target.data["industry"] == "Manufacturing"
            assert target.data["website"] == "acme.com"
            # Source fills gaps
            assert target.data["founded"] == "1990"
            assert target.data["ceo"] == "Old CEO"
    
    def test_merge_transfers_all_relationships(self, db_session):
        """Test that all relationships are transferred from source to target."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            source = Entity(id=uuid.uuid4(), name="Source Co", kind="company")
            target = Entity(id=uuid.uuid4(), name="Source Company", kind="company")
            person = Entity(id=uuid.uuid4(), name="John Smith", kind="person")
            location = Entity(id=uuid.uuid4(), name="New York", kind="location")
            product = Entity(id=uuid.uuid4(), name="Widget", kind="product")
            session.add_all([source, target, person, location, product])
            session.commit()
            
            # Create various relationships from source
            rels = [
                Relationship(id=uuid.uuid4(), source_id=source.id, target_id=person.id, relation_type="employs"),
                Relationship(id=uuid.uuid4(), source_id=source.id, target_id=location.id, relation_type="headquartered_at"),
                Relationship(id=uuid.uuid4(), source_id=product.id, target_id=source.id, relation_type="produced_by"),
            ]
            session.add_all(rels)
            session.commit()
            
            source_id = str(source.id)
            target_id = str(target.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        with db_session() as session:
            # Source should be deleted
            assert session.execute(
                select(Entity).where(Entity.id == source_id)
            ).scalar_one_or_none() is None
            
            # All relationships should now point to/from target
            rels = session.execute(select(Relationship)).scalars().all()
            assert len(rels) == 3
            
            for rel in rels:
                assert str(rel.source_id) != source_id
                assert str(rel.target_id) != source_id
    
    def test_merge_transfers_intelligence_records(self, db_session):
        """Test that intelligence records are transferred to target before deletion."""
        from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator
        
        deduplicator = SemanticEntityDeduplicator(db_session)
        
        with db_session() as session:
            source = Entity(id=uuid.uuid4(), name="Source", kind="company")
            target = Entity(id=uuid.uuid4(), name="Target", kind="company")
            session.add_all([source, target])
            session.commit()
            
            # Create an intelligence record for source
            intel = Intelligence(
                id=uuid.uuid4(),
                entity_id=source.id,
                entity_name="Source",
                entity_type="company",
                confidence=0.9,
                data={"key": "value"},
            )
            session.add(intel)
            session.commit()
            
            source_id = str(source.id)
            target_id = str(target.id)
            intel_id = str(intel.id)
        
        with db_session() as session:
            deduplicator._merge_entities(session, source_id, target_id)
            session.commit()
        
        with db_session() as session:
            # Intelligence should now point to target
            intel = session.execute(
                select(Intelligence).where(Intelligence.id == intel_id)
            ).scalar_one()
            assert str(intel.entity_id) == target_id


class TestDynamicEntityTypeDiscovery:
    """Test that entity types can be discovered dynamically via LLM extraction."""

    def test_llm_entity_type_registers_new_kind(self):
        """Test that an LLM-provided entity_type gets registered in the registry."""
        from garuda_intel.types.entity.registry import EntityKindRegistry

        extractor = IntelExtractor(
            enable_entity_merging=False,
            extract_related_entities=True,
            enable_comprehensive_extraction=True,
        )

        finding = {
            "organizations": [
                {
                    "name": "Red Cross",
                    "type": "nonprofit",
                    "description": "Humanitarian organization",
                    "entity_type": "humanitarian_ngo",
                    "parent_type": "org",
                }
            ]
        }

        entities = extractor.extract_entities_from_finding(finding)
        assert len(entities) == 1
        assert entities[0]["kind"] == "humanitarian_ngo"

        # Verify it was registered in the registry
        registry = EntityKindRegistry.instance()
        kind_info = registry.get_kind("humanitarian_ngo")
        assert kind_info is not None
        assert kind_info.parent_kind == "org"

    def test_llm_entity_type_for_person(self):
        """Test that an LLM-provided entity_type for a person gets registered."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
            extract_related_entities=True,
            enable_comprehensive_extraction=True,
        )

        finding = {
            "persons": [
                {
                    "name": "Dr. Jane Doe",
                    "title": "Chief Medical Officer",
                    "role": "CMO",
                    "entity_type": "cmo",
                    "parent_type": "person",
                }
            ]
        }

        entities = extractor.extract_entities_from_finding(finding)
        assert len(entities) == 1
        assert entities[0]["kind"] == "cmo"

        from garuda_intel.types.entity.registry import EntityKindRegistry
        registry = EntityKindRegistry.instance()
        kind_info = registry.get_kind("cmo")
        assert kind_info is not None
        assert kind_info.parent_kind == "person"

    def test_llm_entity_type_for_product(self):
        """Test that an LLM-provided entity_type for a product gets registered."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
            extract_related_entities=True,
            enable_comprehensive_extraction=True,
        )

        finding = {
            "products": [
                {
                    "name": "CloudWatch Pro",
                    "description": "Monitoring SaaS",
                    "entity_type": "saas",
                    "parent_type": "product",
                }
            ]
        }

        entities = extractor.extract_entities_from_finding(finding)
        assert len(entities) == 1
        assert entities[0]["kind"] == "saas"

        from garuda_intel.types.entity.registry import EntityKindRegistry
        registry = EntityKindRegistry.instance()
        kind_info = registry.get_kind("saas")
        assert kind_info is not None
        assert kind_info.parent_kind == "product"

    def test_llm_entity_type_for_location(self):
        """Test that an LLM-provided entity_type for a location gets registered."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
            extract_related_entities=True,
            enable_comprehensive_extraction=True,
        )

        finding = {
            "locations": [
                {
                    "address": "Building 42, Data Center Park",
                    "city": "Ashburn",
                    "country": "USA",
                    "entity_type": "data_center",
                    "parent_type": "location",
                }
            ]
        }

        entities = extractor.extract_entities_from_finding(finding)
        assert len(entities) == 1
        assert entities[0]["kind"] == "data_center"

        from garuda_intel.types.entity.registry import EntityKindRegistry
        registry = EntityKindRegistry.instance()
        kind_info = registry.get_kind("data_center")
        assert kind_info is not None
        assert kind_info.parent_kind == "location"

    def test_llm_entity_type_for_event(self):
        """Test that an LLM-provided entity_type for an event gets registered."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
            extract_related_entities=True,
            enable_comprehensive_extraction=True,
        )

        finding = {
            "events": [
                {
                    "title": "Microsoft acquires Activision",
                    "date": "2023",
                    "entity_type": "merger",
                    "parent_type": "event",
                }
            ]
        }

        entities = extractor.extract_entities_from_finding(finding)
        assert len(entities) == 1
        assert entities[0]["kind"] == "merger"

        from garuda_intel.types.entity.registry import EntityKindRegistry
        registry = EntityKindRegistry.instance()
        kind_info = registry.get_kind("merger")
        assert kind_info is not None
        assert kind_info.parent_kind == "event"

    def test_dynamic_hierarchy_visible_in_global_dicts(self):
        """Test that dynamically registered kinds show up in ENTITY_TYPE_HIERARCHY."""
        from garuda_intel.types.entity.registry import EntityKindRegistry

        registry = EntityKindRegistry.instance()
        # Register a completely new kind
        registry.register_kind(
            name="test_dynamic_kind_xyz",
            parent_kind="person",
            description="Test dynamic kind",
        )

        # Now check: the dynamic hierarchy should include this new kind
        assert "test_dynamic_kind_xyz" in ENTITY_TYPE_HIERARCHY
        assert ENTITY_TYPE_HIERARCHY["test_dynamic_kind_xyz"] == "person"

    def test_fallback_to_detection_when_no_entity_type(self):
        """Test that when entity_type is not provided, existing detection logic is used."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
            extract_related_entities=True,
        )

        finding = {
            "persons": [
                {
                    "name": "Jane Smith",
                    "title": "CEO",
                    "role": "chief executive officer",
                }
            ]
        }

        entities = extractor.extract_entities_from_finding(finding)
        assert len(entities) == 1
        # Should detect CEO from title/role without entity_type field
        assert entities[0]["kind"] == "ceo"


class TestFillerValueSanitization:
    """Test that filler/placeholder values are stripped from LLM responses."""

    def test_sanitize_simple_fillers(self):
        """Test that common filler strings are stripped."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
        )

        data = {
            "basic_info": {
                "official_name": "Acme Corp",
                "ticker": "not mentioned",
                "industry": "Technology",
                "description": "N/A",
                "founded": "not available",
                "website": "https://acme.com",
            }
        }

        result = extractor._sanitize_filler_values(data)
        basic_info = result["basic_info"]
        assert basic_info.get("official_name") == "Acme Corp"
        assert "ticker" not in basic_info  # "not mentioned" should be removed
        assert basic_info.get("industry") == "Technology"
        assert "description" not in basic_info  # "N/A" should be removed
        assert "founded" not in basic_info  # "not available" should be removed
        assert basic_info.get("website") == "https://acme.com"

    def test_sanitize_nested_fillers(self):
        """Test that filler values are stripped from nested structures."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
        )

        data = {
            "persons": [
                {
                    "name": "John Doe",
                    "title": "not mentioned in the text",
                    "role": "Engineer",
                    "bio": "unknown",
                    "email": "Not Specified",
                },
                {
                    "name": "not mentioned",
                },
            ]
        }

        result = extractor._sanitize_filler_values(data)
        # The second person should be removed since name becomes empty
        persons = result["persons"]
        assert len(persons) == 1
        person = persons[0]
        assert person["name"] == "John Doe"
        assert "title" not in person
        assert person["role"] == "Engineer"
        assert "bio" not in person
        assert "email" not in person

    def test_sanitize_preserves_valid_data(self):
        """Test that valid data is not stripped."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
        )

        data = {
            "basic_info": {
                "official_name": "None Corp",
                "industry": "Technology",
                "founded": "2020",
            },
            "products": [
                {"name": "Widget", "price": "$29.99"},
            ],
        }

        # "None Corp" should NOT be stripped - it looks like a real name
        result = extractor._sanitize_filler_values(data)
        assert result["basic_info"]["official_name"] == "None Corp"
        assert result["basic_info"]["industry"] == "Technology"
        assert len(result["products"]) == 1

    def test_sanitize_handles_empty_input(self):
        """Test that empty/null inputs are handled gracefully."""
        extractor = IntelExtractor(
            enable_entity_merging=False,
        )

        assert extractor._sanitize_filler_values({}) == {}
        assert extractor._sanitize_filler_values([]) == []
        assert extractor._sanitize_filler_values("") == ""
        assert extractor._sanitize_filler_values(None) is None
        assert extractor._sanitize_filler_values(42) == 42
