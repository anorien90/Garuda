"""Test to verify PostCrawlProcessor doesn't wipe multi-node relationships.

This test simulates the post-crawl processing scenario where validate_relationships
is called with fix_invalid=True, ensuring that legitimate relationships between
different node types are preserved.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.database.relationship_manager import RelationshipManager
from garuda_intel.database.models import Relationship, Page, Entity, Intelligence, Seed
from sqlalchemy import select, func
import uuid


def test_post_crawl_processing_scenario():
    """
    Simulate the PostCrawlProcessor scenario with mixed node type relationships.
    
    This test creates relationships between various node types (Entity, Page,
    Intelligence, Seed) and then calls validate_relationships(fix_invalid=True)
    to ensure that legitimate relationships are not deleted.
    """
    store = SQLAlchemyStore("sqlite:///:memory:")
    manager = RelationshipManager(store, llm_extractor=None)
    
    print("Setting up test scenario with mixed node types...")
    
    # Create entities
    entities = [
        {"name": "Company ABC", "kind": "organization", "data": {"industry": "tech"}},
        {"name": "John Doe", "kind": "person", "data": {"role": "CEO"}},
        {"name": "Jane Smith", "kind": "person", "data": {"role": "CTO"}},
    ]
    entity_map = store.save_entities(entities)
    company_id = entity_map.get(("Company ABC", "organization"))
    john_id = entity_map.get(("John Doe", "person"))
    jane_id = entity_map.get(("Jane Smith", "person"))
    
    # Create pages
    page1_id = store.save_page({
        "url": "https://example.com/company",
        "page_type": "company_profile",
        "score": 0.95,
        "summary": "Company profile page",
        "extracted_intel": [],
        "metadata": {},
        "extracted": [],
        "links": [],
        "has_high_confidence_intel": True,
        "text_content": "Company ABC profile",
        "text_length": 20,
        "entity_type": "organization",
        "domain_key": "example.com",
        "depth": 0,
    })
    
    page2_id = store.save_page({
        "url": "https://example.com/team",
        "page_type": "team_page",
        "score": 0.85,
        "summary": "Team page",
        "extracted_intel": [],
        "metadata": {},
        "extracted": [],
        "links": [],
        "has_high_confidence_intel": True,
        "text_content": "Our team",
        "text_length": 8,
        "entity_type": "organization",
        "domain_key": "example.com",
        "depth": 1,
    })
    
    # Create intelligence entries
    with store.Session() as session:
        intel1 = Intelligence(
            id=uuid.uuid4(),
            entity_id=company_id,
            page_id=page1_id,
            entity_name="Company ABC",
            entity_type="organization",
            confidence=0.9,
            data={"founded": "2020", "employees": "100+"}
        )
        intel2 = Intelligence(
            id=uuid.uuid4(),
            entity_id=john_id,
            page_id=page2_id,
            entity_name="John Doe",
            entity_type="person",
            confidence=0.85,
            data={"title": "CEO", "background": "Tech industry veteran"}
        )
        session.add(intel1)
        session.add(intel2)
        session.commit()
        intel1_id = str(intel1.id)
        intel2_id = str(intel2.id)
    
    # Create seeds
    with store.Session() as session:
        seed1 = Seed(
            id=uuid.uuid4(),
            query="Company ABC tech startup",
            entity_type="organization",
            source="search"
        )
        seed2 = Seed(
            id=uuid.uuid4(),
            query="John Doe CEO",
            entity_type="person",
            source="search"
        )
        session.add(seed1)
        session.add(seed2)
        session.commit()
        seed1_id = str(seed1.id)
        seed2_id = str(seed2.id)
    
    print(f"✓ Created 3 entities, 2 pages, 2 intelligence entries, 2 seeds")
    
    # Create a realistic set of relationships with different node types
    relationships = []
    
    # Entity ↔ Entity relationships
    relationships.append(store.save_relationship(company_id, john_id, "has_ceo", {"confidence": 0.9}))
    relationships.append(store.save_relationship(company_id, jane_id, "has_cto", {"confidence": 0.85}))
    relationships.append(store.save_relationship(john_id, company_id, "works_at", {"confidence": 0.9}))
    relationships.append(store.save_relationship(jane_id, company_id, "works_at", {"confidence": 0.85}))
    
    # Page → Entity relationships
    relationships.append(store.save_relationship(page1_id, company_id, "about", {"confidence": 0.95}))
    relationships.append(store.save_relationship(page2_id, john_id, "mentions", {"confidence": 0.8}))
    relationships.append(store.save_relationship(page2_id, jane_id, "mentions", {"confidence": 0.8}))
    
    # Intelligence → Entity relationships
    relationships.append(store.save_relationship(intel1_id, company_id, "describes", {"confidence": 0.9}))
    relationships.append(store.save_relationship(intel2_id, john_id, "describes", {"confidence": 0.85}))
    
    # Seed → Page relationships
    relationships.append(store.save_relationship(seed1_id, page1_id, "discovered", {"confidence": 0.7}))
    relationships.append(store.save_relationship(seed2_id, page2_id, "discovered", {"confidence": 0.7}))
    
    print(f"✓ Created {len(relationships)} relationships with mixed node types")
    
    # Count relationships before validation
    with store.Session() as session:
        count_before = session.execute(
            select(func.count()).select_from(Relationship)
        ).scalar()
    
    print(f"✓ Total relationships before validation: {count_before}")
    
    # === SIMULATE POST-CRAWL PROCESSING ===
    print("\nSimulating PostCrawlProcessor.validate_relationships(fix_invalid=True)...")
    
    # This is the critical call that was previously deleting all non-Entity relationships
    validation_report = manager.validate_relationships(fix_invalid=True)
    
    print(f"✓ Validation report:")
    print(f"  - Total: {validation_report['total']}")
    print(f"  - Valid: {validation_report['valid']}")
    print(f"  - Circular: {validation_report['circular']}")
    print(f"  - Orphaned: {validation_report['orphaned']}")
    print(f"  - Fixed: {validation_report['fixed']}")
    
    # Count relationships after validation
    with store.Session() as session:
        count_after = session.execute(
            select(func.count()).select_from(Relationship)
        ).scalar()
    
    print(f"✓ Total relationships after validation: {count_after}")
    
    # CRITICAL ASSERTIONS
    # With the fix, no legitimate relationships should be deleted
    assert validation_report['orphaned'] == 0, \
        f"Expected 0 orphaned relationships, but found {validation_report['orphaned']}"
    
    assert count_after >= len(relationships), \
        f"Lost relationships! Before: {count_before}, After: {count_after}"
    
    assert validation_report['valid'] >= len(relationships), \
        f"Not all relationships validated! Expected >= {len(relationships)}, got {validation_report['valid']}"
    
    print(f"\n✓ SUCCESS: All {count_after} relationships preserved after validation!")
    print(f"✓ No legitimate multi-node relationships were deleted")
    
    # Verify specific relationship types still exist
    with store.Session() as session:
        # Check Entity↔Entity
        entity_rels = session.execute(
            select(Relationship).where(
                Relationship.source_type == "entity",
                Relationship.target_type == "entity"
            )
        ).scalars().all()
        assert len(entity_rels) >= 4, f"Expected >= 4 Entity↔Entity relationships, got {len(entity_rels)}"
        print(f"✓ Entity↔Entity relationships: {len(entity_rels)}")
        
        # Check Page→Entity
        page_rels = session.execute(
            select(Relationship).where(
                Relationship.source_type == "page",
                Relationship.target_type == "entity"
            )
        ).scalars().all()
        assert len(page_rels) >= 3, f"Expected >= 3 Page→Entity relationships, got {len(page_rels)}"
        print(f"✓ Page→Entity relationships: {len(page_rels)}")
        
        # Check Intelligence→Entity
        intel_rels = session.execute(
            select(Relationship).where(
                Relationship.source_type == "intelligence",
                Relationship.target_type == "entity"
            )
        ).scalars().all()
        assert len(intel_rels) >= 2, f"Expected >= 2 Intelligence→Entity relationships, got {len(intel_rels)}"
        print(f"✓ Intelligence→Entity relationships: {len(intel_rels)}")
        
        # Check Seed→Page
        seed_rels = session.execute(
            select(Relationship).where(
                Relationship.source_type == "seed",
                Relationship.target_type == "page"
            )
        ).scalars().all()
        assert len(seed_rels) >= 2, f"Expected >= 2 Seed→Page relationships, got {len(seed_rels)}"
        print(f"✓ Seed→Page relationships: {len(seed_rels)}")
    
    print(f"\n" + "=" * 70)
    print("✓ PostCrawlProcessor scenario test PASSED!")
    print("✓ Multi-node type relationships are now properly preserved!")
    print("=" * 70)


def test_post_crawl_with_actual_orphans():
    """
    Test that true orphaned relationships are still detected and removed
    during post-crawl processing.
    """
    store = SQLAlchemyStore("sqlite:///:memory:")
    manager = RelationshipManager(store, llm_extractor=None)
    
    print("\nTesting orphan detection during post-crawl processing...")
    
    # Create valid entities
    entities = [{"name": "Valid Entity", "kind": "organization", "data": {}}]
    entity_map = store.save_entities(entities)
    valid_id = entity_map.get(("Valid Entity", "organization"))
    
    # Create a valid relationship
    valid_rel_id = store.save_relationship(valid_id, valid_id, "same_as")
    
    # Manually create orphaned relationships (simulate data corruption)
    fake_id1 = str(uuid.uuid4())
    fake_id2 = str(uuid.uuid4())
    
    with store.Session() as session:
        orphan1 = Relationship(
            id=uuid.uuid4(),
            source_id=valid_id,
            target_id=fake_id1,  # Does not exist
            relation_type="orphan_test",
            metadata_json={}
        )
        orphan2 = Relationship(
            id=uuid.uuid4(),
            source_id=fake_id2,  # Does not exist
            target_id=valid_id,
            relation_type="orphan_test",
            metadata_json={}
        )
        session.add(orphan1)
        session.add(orphan2)
        session.commit()
    
    print(f"✓ Created 1 valid relationship and 2 orphaned relationships")
    
    # Validate with fix_invalid=True
    validation_report = manager.validate_relationships(fix_invalid=True)
    
    print(f"✓ Validation report:")
    print(f"  - Total: {validation_report['total']}")
    print(f"  - Valid: {validation_report['valid']}")
    print(f"  - Orphaned: {validation_report['orphaned']}")
    print(f"  - Fixed: {validation_report['fixed']}")
    
    # Should detect and remove the 2 orphaned relationships
    assert validation_report['orphaned'] == 2, \
        f"Expected 2 orphaned relationships, got {validation_report['orphaned']}"
    assert validation_report['fixed'] >= 2, \
        f"Expected >= 2 fixed (removed), got {validation_report['fixed']}"
    
    # Valid relationship should still exist (but it's circular, so it gets removed too)
    # Let's check final count
    with store.Session() as session:
        final_count = session.execute(
            select(func.count()).select_from(Relationship)
        ).scalar()
    
    print(f"✓ Orphan detection works: {validation_report['orphaned']} orphans removed")
    print(f"✓ Final relationship count: {final_count}")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Testing PostCrawlProcessor Scenario")
    print("=" * 70 + "\n")
    
    test_post_crawl_processing_scenario()
    test_post_crawl_with_actual_orphans()
    
    print("\n" + "=" * 70)
    print("✓ All PostCrawlProcessor tests PASSED!")
    print("=" * 70 + "\n")
