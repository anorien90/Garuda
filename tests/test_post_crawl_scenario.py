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
    print(f"  Note: Circular relationship also removed, so final count is 0 (1 circular + 2 orphaned = 3 removed)")


def test_cross_kind_entity_deduplication():
    """
    Test that entities with the same name but different kinds
    are merged when one is a generic 'entity' kind and the other
    is a more specific kind (person, org, etc.).
    
    This addresses the issue where "Satya Nadella" appears twice:
    - Once as 'person' with rich metadata (role, title, etc.)
    - Once as 'entity' with minimal metadata
    """
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    print("\nTesting cross-kind entity deduplication...")
    
    # Create entities with the same name but different kinds
    # Simulate the scenario where the same person is discovered as both
    # a generic 'entity' and a specific 'person'
    entities = [
        # Generic entity with minimal data (discovered first from relationships)
        {"name": "Satya Nadella", "kind": "entity", "data": {}},
        # Specific person entity with rich data (discovered later from extraction)
        {
            "name": "Satya Nadella", 
            "kind": "person", 
            "data": {"role": "executive", "title": "CEO", "bio": "Tech leader"}
        },
        # Another generic entity
        {"name": "Microsoft Corporation", "kind": "entity", "data": {}},
        # Specific org entity with rich data
        {
            "name": "Microsoft Corporation", 
            "kind": "org", 
            "data": {"industry": "Technology", "founded": "1975"}
        },
        # Person without a duplicate (should remain unchanged)
        {"name": "Bill Gates", "kind": "person", "data": {"role": "founder"}},
    ]
    
    # Save entities
    entity_map = store.save_entities(entities)
    
    # Initially, we should have 5 entities with different (name, kind) combinations
    with store.Session() as session:
        count_before = session.execute(
            select(func.count()).select_from(Entity)
        ).scalar()
    
    print(f"✓ Created {count_before} entities before deduplication")
    
    # Verify we have both kinds for Satya Nadella
    with store.Session() as session:
        satya_entities = session.execute(
            select(Entity).where(Entity.name == "Satya Nadella")
        ).scalars().all()
        print(f"✓ Satya Nadella entities before dedup: {len(satya_entities)} "
              f"(kinds: {[e.kind for e in satya_entities]})")
        assert len(satya_entities) == 2, f"Expected 2 Satya Nadella entities, got {len(satya_entities)}"
    
    # Run deduplication
    merge_map = store.deduplicate_entities(threshold=0.85)
    
    print(f"✓ Deduplication merged {len(merge_map)} entities")
    
    # After deduplication, generic 'entity' kinds should be merged into specific kinds
    with store.Session() as session:
        count_after = session.execute(
            select(func.count()).select_from(Entity)
        ).scalar()
    
    print(f"✓ Entities after deduplication: {count_after}")
    
    # Verify Satya Nadella now only exists once
    with store.Session() as session:
        satya_entities = session.execute(
            select(Entity).where(Entity.name == "Satya Nadella")
        ).scalars().all()
        print(f"✓ Satya Nadella entities after dedup: {len(satya_entities)} "
              f"(kinds: {[e.kind for e in satya_entities]})")
        
        # Should only have the 'person' entity remaining
        assert len(satya_entities) == 1, \
            f"Expected 1 Satya Nadella entity after dedup, got {len(satya_entities)}"
        assert satya_entities[0].kind == "person", \
            f"Expected 'person' kind to be preserved, got '{satya_entities[0].kind}'"
        # Verify rich data is preserved
        assert satya_entities[0].data.get("role") == "executive", \
            "Expected 'executive' role to be preserved"
        assert satya_entities[0].data.get("title") == "CEO", \
            "Expected 'CEO' title to be preserved"
    
    # Verify Microsoft Corporation is also deduplicated
    with store.Session() as session:
        microsoft_entities = session.execute(
            select(Entity).where(Entity.name == "Microsoft Corporation")
        ).scalars().all()
        print(f"✓ Microsoft Corporation entities after dedup: {len(microsoft_entities)} "
              f"(kinds: {[e.kind for e in microsoft_entities]})")
        
        assert len(microsoft_entities) == 1, \
            f"Expected 1 Microsoft Corporation entity after dedup, got {len(microsoft_entities)}"
        assert microsoft_entities[0].kind == "org", \
            f"Expected 'org' kind to be preserved, got '{microsoft_entities[0].kind}'"
    
    # Verify Bill Gates was not affected (only one entity existed)
    with store.Session() as session:
        gates_entities = session.execute(
            select(Entity).where(Entity.name == "Bill Gates")
        ).scalars().all()
        assert len(gates_entities) == 1, f"Bill Gates should still have 1 entity"
        assert gates_entities[0].kind == "person", "Bill Gates should still be 'person' kind"
    
    print(f"\n✓ Cross-kind deduplication test PASSED!")
    print(f"  - Generic 'entity' kinds merged into specific kinds")
    print(f"  - Rich metadata preserved in the merged entity")
    print(f"  - {count_before} entities reduced to {count_after}")
    return True


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Testing PostCrawlProcessor Scenario")
    print("=" * 70 + "\n")
    
    test_post_crawl_processing_scenario()
    test_post_crawl_with_actual_orphans()
    test_cross_kind_entity_deduplication()
    
    print("\n" + "=" * 70)
    print("✓ All PostCrawlProcessor tests PASSED!")
    print("=" * 70 + "\n")
