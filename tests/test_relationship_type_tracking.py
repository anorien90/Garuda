"""Tests for relationship type tracking.

This test suite validates that the new source_type and target_type fields
are properly populated when creating relationships.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.database.relationship_manager import RelationshipManager
from garuda_intel.database.models import Relationship, Page, Entity, Seed
from sqlalchemy import select
import uuid


def test_type_tracking_on_new_relationships():
    """Test that new relationships automatically get type information."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    # Create entities
    entities = [
        {"name": "Company A", "kind": "organization", "data": {}},
        {"name": "Person B", "kind": "person", "data": {}},
    ]
    entity_map = store.save_entities(entities)
    company_id = entity_map.get(("Company A", "organization"))
    person_id = entity_map.get(("Person B", "person"))
    
    print(f"✓ Created entities: {company_id[:8]}..., {person_id[:8]}...")
    
    # Create relationship
    rel_id = store.save_relationship(
        company_id, person_id, "employs",
        meta={"confidence": 0.9}
    )
    
    print(f"✓ Created relationship: {rel_id[:8]}...")
    
    # Verify type fields are populated
    with store.Session() as session:
        rel = session.execute(
            select(Relationship).where(Relationship.id == rel_id)
        ).scalar_one_or_none()
        
        assert rel is not None
        assert rel.source_type == "entity", f"Expected source_type='entity', got '{rel.source_type}'"
        assert rel.target_type == "entity", f"Expected target_type='entity', got '{rel.target_type}'"
        
        print(f"✓ Relationship has correct types: source_type={rel.source_type}, target_type={rel.target_type}")


def test_type_tracking_mixed_nodes():
    """Test type tracking with mixed node types."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    # Create a page
    page_record = {
        "url": "https://example.com/test",
        "page_type": "article",
        "score": 0.8,
        "summary": "Test",
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
    
    # Create an entity
    entities = [{"name": "Company X", "kind": "organization", "data": {}}]
    entity_map = store.save_entities(entities)
    entity_id = entity_map.get(("Company X", "organization"))
    
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
    
    print(f"✓ Created page, entity, and seed")
    
    # Create relationships between different node types
    rel1_id = store.save_relationship(page_id, entity_id, "mentions")
    rel2_id = store.save_relationship(seed_id, page_id, "discovered")
    rel3_id = store.save_relationship(entity_id, entity_id, "same_as")  # Self-reference (should be circular)
    
    print(f"✓ Created 3 relationships with mixed types")
    
    # Verify all types are correctly tracked
    with store.Session() as session:
        # Page -> Entity
        rel1 = session.execute(
            select(Relationship).where(Relationship.id == rel1_id)
        ).scalar_one_or_none()
        assert rel1.source_type == "page", f"Expected 'page', got '{rel1.source_type}'"
        assert rel1.target_type == "entity", f"Expected 'entity', got '{rel1.target_type}'"
        print(f"✓ Page→Entity: source_type={rel1.source_type}, target_type={rel1.target_type}")
        
        # Seed -> Page
        rel2 = session.execute(
            select(Relationship).where(Relationship.id == rel2_id)
        ).scalar_one_or_none()
        assert rel2.source_type == "seed", f"Expected 'seed', got '{rel2.source_type}'"
        assert rel2.target_type == "page", f"Expected 'page', got '{rel2.target_type}'"
        print(f"✓ Seed→Page: source_type={rel2.source_type}, target_type={rel2.target_type}")
        
        # Entity -> Entity (circular)
        rel3 = session.execute(
            select(Relationship).where(Relationship.id == rel3_id)
        ).scalar_one_or_none()
        assert rel3.source_type == "entity", f"Expected 'entity', got '{rel3.source_type}'"
        assert rel3.target_type == "entity", f"Expected 'entity', got '{rel3.target_type}'"
        print(f"✓ Entity→Entity: source_type={rel3.source_type}, target_type={rel3.target_type}")


def test_backfill_types_for_existing_relationships():
    """Test that backfill correctly adds types to existing relationships."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    manager = RelationshipManager(store, llm_extractor=None)
    
    # Create entities
    entities = [
        {"name": "Company Y", "kind": "organization", "data": {}},
        {"name": "Person Z", "kind": "person", "data": {}},
    ]
    entity_map = store.save_entities(entities)
    company_id = entity_map.get(("Company Y", "organization"))
    person_id = entity_map.get(("Person Z", "person"))
    
    print(f"✓ Created entities")
    
    # Manually create a relationship WITHOUT types (simulating old data)
    with store.Session() as session:
        old_rel = Relationship(
            id=uuid.uuid4(),
            source_id=company_id,
            target_id=person_id,
            relation_type="employs",
            source_type=None,  # Explicitly no type
            target_type=None,  # Explicitly no type
            metadata_json={"confidence": 0.8}
        )
        session.add(old_rel)
        session.commit()
        old_rel_id = str(old_rel.id)
    
    print(f"✓ Created old-style relationship without types")
    
    # Verify it has no types
    with store.Session() as session:
        rel_before = session.execute(
            select(Relationship).where(Relationship.id == old_rel_id)
        ).scalar_one_or_none()
        assert rel_before.source_type is None
        assert rel_before.target_type is None
        print(f"✓ Confirmed relationship has no types initially")
    
    # Backfill types
    updated_count = manager.backfill_relationship_types()
    
    assert updated_count >= 1, f"Expected to update at least 1 relationship, got {updated_count}"
    print(f"✓ Backfilled types for {updated_count} relationship(s)")
    
    # Verify types are now populated
    with store.Session() as session:
        rel_after = session.execute(
            select(Relationship).where(Relationship.id == old_rel_id)
        ).scalar_one_or_none()
        assert rel_after.source_type == "entity", f"Expected 'entity', got '{rel_after.source_type}'"
        assert rel_after.target_type == "entity", f"Expected 'entity', got '{rel_after.target_type}'"
        print(f"✓ Types backfilled correctly: source_type={rel_after.source_type}, target_type={rel_after.target_type}")


def test_backfill_partial_types():
    """Test backfill only updates missing type fields."""
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
    
    # Create relationship with only source_type set
    with store.Session() as session:
        partial_rel = Relationship(
            id=uuid.uuid4(),
            source_id=company_id,
            target_id=person_id,
            relation_type="employs",
            source_type="entity",  # Already set
            target_type=None,  # Missing
            metadata_json={}
        )
        session.add(partial_rel)
        session.commit()
        partial_rel_id = str(partial_rel.id)
    
    print(f"✓ Created relationship with partial type info (source_type only)")
    
    # Backfill
    updated_count = manager.backfill_relationship_types()
    
    print(f"✓ Backfill updated {updated_count} relationship(s)")
    
    # Verify both types are now set
    with store.Session() as session:
        rel = session.execute(
            select(Relationship).where(Relationship.id == partial_rel_id)
        ).scalar_one_or_none()
        assert rel.source_type == "entity"
        assert rel.target_type == "entity"
        print(f"✓ Partial backfill successful: both types now set")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Testing Relationship Type Tracking")
    print("=" * 70 + "\n")
    
    print("Test 1: Type tracking on new relationships")
    print("-" * 70)
    test_type_tracking_on_new_relationships()
    print()
    
    print("Test 2: Type tracking with mixed node types")
    print("-" * 70)
    test_type_tracking_mixed_nodes()
    print()
    
    print("Test 3: Backfill types for existing relationships")
    print("-" * 70)
    test_backfill_types_for_existing_relationships()
    print()
    
    print("Test 4: Backfill partial types")
    print("-" * 70)
    test_backfill_partial_types()
    print()
    
    print("=" * 70)
    print("✓ All type tracking tests passed!")
    print("=" * 70 + "\n")
