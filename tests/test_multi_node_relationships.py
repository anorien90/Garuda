"""Tests for multi-node type relationship validation.

This test suite validates that relationships can be created and validated
between different node types (Entity, Page, Intelligence, Seed), not just
Entity↔Entity relationships.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.database.relationship_manager import RelationshipManager
from garuda_intel.database.models import (
    Entity, Page, Intelligence, Seed, Relationship, BasicDataEntry
)
from sqlalchemy import select
import uuid


def test_entity_to_entity_relationships():
    """Test that Entity↔Entity relationships still work (baseline)."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    manager = RelationshipManager(store, llm_extractor=None)
    
    # Create entities
    entities = [
        {"name": "Company A", "kind": "organization", "data": {}},
        {"name": "Person B", "kind": "person", "data": {}},
    ]
    
    entity_map = store.save_entities(entities)
    company_id = entity_map.get(("Company A", "organization"))
    person_id = entity_map.get(("Person B", "person"))
    
    assert company_id and person_id
    print(f"✓ Created 2 entities: {company_id[:8]}..., {person_id[:8]}...")
    
    # Create relationship
    rel_id = store.save_relationship(
        company_id, person_id, "employs",
        meta={"confidence": 0.9}
    )
    assert rel_id
    print(f"✓ Created Entity↔Entity relationship: {rel_id[:8]}...")
    
    # Validate relationships
    report = manager.validate_relationships(fix_invalid=True)
    
    assert report["total"] >= 1
    assert report["orphaned"] == 0, "Entity↔Entity relationship should not be orphaned"
    assert report["valid"] >= 1
    print(f"✓ Validation passed: {report['valid']}/{report['total']} valid, {report['orphaned']} orphaned")
    
    # Ensure relationship still exists
    with store.Session() as session:
        rel = session.execute(
            select(Relationship).where(Relationship.id == rel_id)
        ).scalar_one_or_none()
        assert rel is not None, "Relationship should not be deleted"
        print(f"✓ Relationship persisted after validation")


def test_page_to_entity_relationships():
    """Test that Page↔Entity relationships are validated correctly."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    manager = RelationshipManager(store, llm_extractor=None)
    
    # Create a page
    page_record = {
        "url": "https://example.com/page1",
        "page_type": "article",
        "score": 0.8,
        "summary": "Test page",
        "extracted_intel": [],
        "metadata": {},
        "extracted": [],
        "links": [],
        "has_high_confidence_intel": False,
        "text_content": "Test",
        "text_length": 4,
        "entity_type": "organization",
        "domain_key": "example.com",
        "depth": 0,
    }
    page_id = store.save_page(page_record)
    assert page_id
    print(f"✓ Created Page: {page_id[:8]}...")
    
    # Create an entity
    entities = [{"name": "Company X", "kind": "organization", "data": {}}]
    entity_map = store.save_entities(entities)
    entity_id = entity_map.get(("Company X", "organization"))
    assert entity_id
    print(f"✓ Created Entity: {entity_id[:8]}...")
    
    # Create Page→Entity relationship
    rel_id = store.save_relationship(
        page_id, entity_id, "mentions",
        meta={"confidence": 0.85}
    )
    assert rel_id
    print(f"✓ Created Page→Entity relationship: {rel_id[:8]}...")
    
    # Validate relationships
    report = manager.validate_relationships(fix_invalid=True)
    
    assert report["orphaned"] == 0, "Page↔Entity relationship should not be orphaned"
    print(f"✓ Validation passed: {report['valid']}/{report['total']} valid, {report['orphaned']} orphaned")
    
    # Ensure relationship still exists
    with store.Session() as session:
        rel = session.execute(
            select(Relationship).where(Relationship.id == rel_id)
        ).scalar_one_or_none()
        assert rel is not None, "Page→Entity relationship should not be deleted"
        print(f"✓ Page→Entity relationship persisted after validation")


def test_intelligence_to_entity_relationships():
    """Test that Intelligence↔Entity relationships are validated correctly."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    manager = RelationshipManager(store, llm_extractor=None)
    
    # Create entity and page
    entities = [{"name": "Person Y", "kind": "person", "data": {}}]
    entity_map = store.save_entities(entities)
    entity_id = entity_map.get(("Person Y", "person"))
    
    page_record = {
        "url": "https://example.com/page2",
        "page_type": "profile",
        "score": 0.9,
        "summary": "Profile page",
        "extracted_intel": [],
        "metadata": {},
        "extracted": [],
        "links": [],
        "has_high_confidence_intel": False,
        "text_content": "Profile",
        "text_length": 7,
        "entity_type": "person",
        "domain_key": "example.com",
        "depth": 0,
    }
    page_id = store.save_page(page_record)
    
    assert entity_id and page_id
    print(f"✓ Created Entity: {entity_id[:8]}... and Page: {page_id[:8]}...")
    
    # Create Intelligence entry
    with store.Session() as session:
        intel = Intelligence(
            id=uuid.uuid4(),
            entity_id=entity_id,
            page_id=page_id,
            entity_name="Person Y",
            entity_type="person",
            confidence=0.9,
            data={"bio": "Test bio"}
        )
        session.add(intel)
        session.commit()
        intel_id = str(intel.id)
    
    print(f"✓ Created Intelligence: {intel_id[:8]}...")
    
    # Create Intelligence→Entity relationship
    rel_id = store.save_relationship(
        intel_id, entity_id, "describes",
        meta={"confidence": 0.95}
    )
    assert rel_id
    print(f"✓ Created Intelligence→Entity relationship: {rel_id[:8]}...")
    
    # Validate relationships
    report = manager.validate_relationships(fix_invalid=True)
    
    assert report["orphaned"] == 0, "Intelligence↔Entity relationship should not be orphaned"
    print(f"✓ Validation passed: {report['valid']}/{report['total']} valid, {report['orphaned']} orphaned")
    
    # Ensure relationship still exists
    with store.Session() as session:
        rel = session.execute(
            select(Relationship).where(Relationship.id == rel_id)
        ).scalar_one_or_none()
        assert rel is not None, "Intelligence→Entity relationship should not be deleted"
        print(f"✓ Intelligence→Entity relationship persisted after validation")


def test_seed_to_page_relationships():
    """Test that Seed↔Page relationships are validated correctly."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    manager = RelationshipManager(store, llm_extractor=None)
    
    # Create a seed
    with store.Session() as session:
        seed = Seed(
            id=uuid.uuid4(),
            query="test query",
            entity_type="organization",
            source="manual"
        )
        session.add(seed)
        session.commit()
        seed_id = str(seed.id)
    
    print(f"✓ Created Seed: {seed_id[:8]}...")
    
    # Create a page
    page_record = {
        "url": "https://example.com/page3",
        "page_type": "result",
        "score": 0.75,
        "summary": "Search result",
        "extracted_intel": [],
        "metadata": {},
        "extracted": [],
        "links": [],
        "has_high_confidence_intel": False,
        "text_content": "Result",
        "text_length": 6,
        "entity_type": "organization",
        "domain_key": "example.com",
        "depth": 1,
    }
    page_id = store.save_page(page_record)
    assert page_id
    print(f"✓ Created Page: {page_id[:8]}...")
    
    # Create Seed→Page relationship
    rel_id = store.save_relationship(
        seed_id, page_id, "discovered",
        meta={"confidence": 0.8}
    )
    assert rel_id
    print(f"✓ Created Seed→Page relationship: {rel_id[:8]}...")
    
    # Validate relationships
    report = manager.validate_relationships(fix_invalid=True)
    
    assert report["orphaned"] == 0, "Seed↔Page relationship should not be orphaned"
    print(f"✓ Validation passed: {report['valid']}/{report['total']} valid, {report['orphaned']} orphaned")
    
    # Ensure relationship still exists
    with store.Session() as session:
        rel = session.execute(
            select(Relationship).where(Relationship.id == rel_id)
        ).scalar_one_or_none()
        assert rel is not None, "Seed→Page relationship should not be deleted"
        print(f"✓ Seed→Page relationship persisted after validation")


def test_orphan_detection_still_works():
    """Test that true orphaned relationships are still detected and removed."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    manager = RelationshipManager(store, llm_extractor=None)
    
    # Create an entity
    entities = [{"name": "Valid Entity", "kind": "organization", "data": {}}]
    entity_map = store.save_entities(entities)
    valid_id = entity_map.get(("Valid Entity", "organization"))
    assert valid_id
    print(f"✓ Created valid Entity: {valid_id[:8]}...")
    
    # Create a relationship with a non-existent target
    fake_id = str(uuid.uuid4())
    
    with store.Session() as session:
        orphaned_rel = Relationship(
            id=uuid.uuid4(),
            source_id=valid_id,
            target_id=fake_id,
            relation_type="test_orphan",
            metadata_json={"confidence": 0.5}
        )
        session.add(orphaned_rel)
        session.commit()
        orphan_rel_id = str(orphaned_rel.id)
    
    print(f"✓ Created orphaned relationship: {orphan_rel_id[:8]}... (target does not exist)")
    
    # Validate relationships with fix_invalid=True
    report = manager.validate_relationships(fix_invalid=True)
    
    assert report["orphaned"] >= 1, "Should detect at least one orphaned relationship"
    assert report["fixed"] >= 1, "Should fix/remove orphaned relationship"
    print(f"✓ Detected {report['orphaned']} orphaned relationship(s)")
    print(f"✓ Fixed/removed {report['fixed']} relationship(s)")
    
    # Ensure orphaned relationship was deleted
    with store.Session() as session:
        rel = session.execute(
            select(Relationship).where(Relationship.id == orphan_rel_id)
        ).scalar_one_or_none()
        assert rel is None, "Orphaned relationship should be deleted"
        print(f"✓ Orphaned relationship correctly deleted")


def test_mixed_node_type_relationships():
    """Test a complex scenario with multiple node types in relationships."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    manager = RelationshipManager(store, llm_extractor=None)
    
    # Create various nodes
    entities = [
        {"name": "Company Z", "kind": "organization", "data": {}},
        {"name": "CEO Smith", "kind": "person", "data": {}},
    ]
    entity_map = store.save_entities(entities)
    company_id = entity_map.get(("Company Z", "organization"))
    ceo_id = entity_map.get(("CEO Smith", "person"))
    
    page_record = {
        "url": "https://example.com/company-z",
        "page_type": "company_profile",
        "score": 0.95,
        "summary": "Company profile",
        "extracted_intel": [],
        "metadata": {},
        "extracted": [],
        "links": [],
        "has_high_confidence_intel": True,
        "text_content": "Company profile",
        "text_length": 15,
        "entity_type": "organization",
        "domain_key": "example.com",
        "depth": 0,
    }
    page_id = store.save_page(page_record)
    
    with store.Session() as session:
        seed = Seed(
            id=uuid.uuid4(),
            query="Company Z",
            entity_type="organization",
            source="search"
        )
        session.add(seed)
        session.commit()
        seed_id = str(seed.id)
    
    print(f"✓ Created 2 entities, 1 page, 1 seed")
    
    # Create multiple relationships between different node types
    rel_ids = []
    rel_ids.append(store.save_relationship(company_id, ceo_id, "has_ceo"))
    rel_ids.append(store.save_relationship(page_id, company_id, "about"))
    rel_ids.append(store.save_relationship(seed_id, page_id, "discovered"))
    rel_ids.append(store.save_relationship(ceo_id, company_id, "works_at"))
    
    print(f"✓ Created {len(rel_ids)} mixed-type relationships")
    
    # Validate relationships
    report = manager.validate_relationships(fix_invalid=True)
    
    assert report["orphaned"] == 0, "No legitimate relationships should be orphaned"
    assert report["valid"] >= len(rel_ids), f"All {len(rel_ids)} relationships should be valid"
    print(f"✓ Validation passed: {report['valid']}/{report['total']} valid, {report['orphaned']} orphaned")
    
    # Ensure all relationships still exist
    with store.Session() as session:
        for rel_id in rel_ids:
            rel = session.execute(
                select(Relationship).where(Relationship.id == rel_id)
            ).scalar_one_or_none()
            assert rel is not None, f"Relationship {rel_id} should not be deleted"
    
    print(f"✓ All {len(rel_ids)} mixed-type relationships persisted after validation")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Testing Multi-Node Type Relationship Validation")
    print("=" * 70 + "\n")
    
    print("Test 1: Entity↔Entity relationships (baseline)")
    print("-" * 70)
    test_entity_to_entity_relationships()
    print()
    
    print("Test 2: Page↔Entity relationships")
    print("-" * 70)
    test_page_to_entity_relationships()
    print()
    
    print("Test 3: Intelligence↔Entity relationships")
    print("-" * 70)
    test_intelligence_to_entity_relationships()
    print()
    
    print("Test 4: Seed↔Page relationships")
    print("-" * 70)
    test_seed_to_page_relationships()
    print()
    
    print("Test 5: Orphan detection still works")
    print("-" * 70)
    test_orphan_detection_still_works()
    print()
    
    print("Test 6: Mixed node type relationships")
    print("-" * 70)
    test_mixed_node_type_relationships()
    print()
    
    print("=" * 70)
    print("✓ All multi-node type relationship tests passed!")
    print("=" * 70 + "\n")
