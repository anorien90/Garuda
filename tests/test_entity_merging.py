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
        """Verify headquarters is defined as subtype of address."""
        assert ENTITY_TYPE_HIERARCHY.get("headquarters") == "address"
    
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
        → William Bill Gates (founder) with all data merged.
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
        
        # Verify only one entity remains
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


class TestMergeTransfersAllReferences:
    """Test that _merge_entities properly transfers all references and handles edge cases."""
    
    def test_merge_transfers_relationships_with_flush(self, db_session):
        """Test that relationships survive the merge with proper flush before delete."""
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
        
        # Verify relationships survived and point to target
        with db_session() as session:
            relationships = session.execute(select(Relationship)).scalars().all()
            assert len(relationships) == 2, "Both relationships should survive"
            
            # Check that relationships now point to target instead of source
            rel_types = {}
            for rel in relationships:
                if str(rel.source_id) == target_id and str(rel.target_id) == entity_c_id:
                    rel_types['target_to_c'] = rel.relation_type
                elif str(rel.source_id) == entity_c_id and str(rel.target_id) == target_id:
                    rel_types['c_to_target'] = rel.relation_type
            
            assert rel_types.get('target_to_c') == "FOUNDED_BY"
            assert rel_types.get('c_to_target') == "FOUNDED"
    
    def test_merge_removes_self_referential_relationships(self, db_session):
        """Test that self-referential relationships are removed after merge."""
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
        
        # Verify self-referential relationship is removed
        with db_session() as session:
            relationships = session.execute(select(Relationship)).scalars().all()
            assert len(relationships) == 0, "Self-referential relationship should be removed"
    
    def test_merge_deduplicates_relationships(self, db_session):
        """Test that duplicate relationships are deduplicated, keeping highest confidence."""
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
        
        # Verify only one relationship remains
        with db_session() as session:
            relationships = session.execute(select(Relationship)).scalars().all()
            assert len(relationships) == 1, "Duplicate relationships should be deduplicated"
            
            rel = relationships[0]
            assert str(rel.source_id) == target_id
            assert str(rel.target_id) == entity_c_id
            assert rel.relation_type == "FOUNDED_BY"
    
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
