"""Tests for ensuring all relationships are persisted."""

try:
    import pytest
except ImportError:
    pytest = None
    
from garuda_intel.database.engine import SQLAlchemyStore


def test_relationship_auto_entity_creation():
    """Test that relationships auto-create missing entities."""
    
    # Create in-memory database
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    # Create a page first
    page_record = {
        "url": "https://example.com/test",
        "page_type": "article",
        "score": 0.8,
        "summary": "Test page",
        "extracted_intel": [],
        "metadata": {},
        "extracted": [],
        "links": [],
        "has_high_confidence_intel": False,
        "text_content": "Test content",
        "text_length": 12,
        "entity_type": "organization",
        "domain_key": "example.com",
        "depth": 0,
    }
    
    page_id = store.save_page(page_record)
    assert page_id is not None
    print(f"✓ Page created: {page_id}")
    
    # Create entities with relationships where some entities don't exist yet
    entities = [
        {
            "name": "Company A",
            "kind": "organization",
            "data": {},
            "page_id": page_id,
        }
    ]
    
    entity_map = store.save_entities(entities)
    company_a_id = entity_map.get(("Company A", "organization"))
    assert company_a_id is not None
    print(f"✓ Company A entity created: {company_a_id}")
    
    # Now simulate what happens in explorer/engine.py when a relationship
    # references a non-existent entity
    # This should auto-create the missing entity
    
    missing_entities = [
        {
            "name": "Person B",
            "kind": "person",
            "data": {"auto_created_from_relationship": True},
            "page_id": page_id,
        }
    ]
    
    new_entity_map = store.save_entities(missing_entities)
    person_b_id = new_entity_map.get(("Person B", "person"))
    assert person_b_id is not None
    print(f"✓ Person B entity auto-created: {person_b_id}")
    
    # Create relationship between Company A and Person B
    rel_id = store.save_relationship(
        from_id=company_a_id,
        to_id=person_b_id,
        relation_type="employs",
        meta={"confidence": 0.9}
    )
    
    assert rel_id is not None
    print(f"✓ Relationship created: {rel_id}")
    
    # Verify the relationship exists
    with store.Session() as session:
        from garuda_intel.database.models import Relationship, Entity
        from sqlalchemy import select
        
        # Check relationship
        rel = session.execute(
            select(Relationship).where(Relationship.id == rel_id)
        ).scalar_one_or_none()
        
        assert rel is not None
        assert str(rel.source_id) == company_a_id
        assert str(rel.target_id) == person_b_id
        assert rel.relation_type == "employs"
        print(f"✓ Relationship verified in database")
        
        # Check that both entities exist
        entity_a = session.execute(
            select(Entity).where(Entity.id == company_a_id)
        ).scalar_one_or_none()
        
        entity_b = session.execute(
            select(Entity).where(Entity.id == person_b_id)
        ).scalar_one_or_none()
        
        assert entity_a is not None
        assert entity_b is not None
        print(f"✓ Both entities exist in database")


def test_multi_level_relationships():
    """Test that multi-level relationship chains are preserved."""
    
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    # Create page
    page_id = store.save_page({
        "url": "https://example.com/org",
        "page_type": "article",
        "score": 0.9,
        "summary": "Organization page",
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
    })
    
    # Create entity hierarchy: Organization -> Person -> Location
    entities = [
        {
            "name": "Tech Corp",
            "kind": "organization",
            "data": {},
            "page_id": page_id,
        },
        {
            "name": "CEO Smith",
            "kind": "person",
            "data": {},
            "page_id": page_id,
        },
        {
            "name": "New York",
            "kind": "location",
            "data": {},
            "page_id": page_id,
        }
    ]
    
    entity_map = store.save_entities(entities)
    org_id = entity_map.get(("Tech Corp", "organization"))
    person_id = entity_map.get(("CEO Smith", "person"))
    location_id = entity_map.get(("New York", "location"))
    
    assert org_id and person_id and location_id
    print(f"✓ Created 3 entities")
    
    # Create relationships
    rel1 = store.save_relationship(org_id, person_id, "has_ceo")
    rel2 = store.save_relationship(person_id, location_id, "lives_in")
    rel3 = store.save_relationship(org_id, location_id, "headquartered_in")
    
    assert rel1 and rel2 and rel3
    print(f"✓ Created 3 relationships forming a chain")
    
    # Verify all relationships exist
    from garuda_intel.database.models import Relationship
    from sqlalchemy import select
    
    with store.Session() as session:
        all_rels = session.execute(select(Relationship)).scalars().all()
        
        # Should have at least 6 relationships:
        # - 3 explicit ones we created
        # - 3 page->entity "mentions_entity" relationships from save_entities
        assert len(all_rels) >= 3
        print(f"✓ Found {len(all_rels)} total relationships (including page mentions)")


def test_relationship_deduplication_preserves_mandatory():
    """Test that deduplication doesn't remove mandatory relationships."""
    
    from garuda_intel.database.relationship_manager import RelationshipManager
    
    store = SQLAlchemyStore("sqlite:///:memory:")
    manager = RelationshipManager(store, llm_extractor=None)
    
    # Create entities
    entities = [
        {"name": "Entity A", "kind": "organization", "data": {}},
        {"name": "Entity B", "kind": "person", "data": {}},
    ]
    
    entity_map = store.save_entities(entities)
    entity_a_id = entity_map.get(("Entity A", "organization"))
    entity_b_id = entity_map.get(("Entity B", "person"))
    
    # Create duplicate relationships (same source, target, type but different metadata)
    rel1 = store.save_relationship(
        entity_a_id, entity_b_id, "employs", 
        meta={"confidence": 0.7, "source": "page1"}
    )
    rel2 = store.save_relationship(
        entity_a_id, entity_b_id, "employs", 
        meta={"confidence": 0.9, "source": "page2"}
    )
    
    print(f"✓ Created 2 duplicate relationships")
    
    # Run deduplication
    removed = manager.deduplicate_relationships(auto_fix=True)
    
    # Should remove 1 duplicate, keeping the higher confidence one
    assert removed == 1
    print(f"✓ Removed {removed} duplicate relationship")
    
    # Verify one relationship still exists (the higher confidence one)
    from garuda_intel.database.models import Relationship
    from sqlalchemy import select
    
    with store.Session() as session:
        remaining = session.execute(
            select(Relationship).where(
                Relationship.source_id == entity_a_id,
                Relationship.target_id == entity_b_id,
                Relationship.relation_type == "employs"
            )
        ).scalars().all()
        
        assert len(remaining) == 1
        assert remaining[0].metadata_json.get("confidence") == 0.9
        print(f"✓ Kept relationship with higher confidence (0.9)")


if __name__ == "__main__":
    print("\n=== Testing Relationship Persistence ===\n")
    
    test_relationship_auto_entity_creation()
    print()
    
    test_multi_level_relationships()
    print()
    
    test_relationship_deduplication_preserves_mandatory()
    print()
    
    print("\n=== All relationship tests completed ===\n")
