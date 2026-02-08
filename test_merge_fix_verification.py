#!/usr/bin/env python3
"""
Verification script for the entity merger fix.
This script creates a scenario that would have failed before the fix
and verifies that relationships survive after merging.

Run from the repository root:
    python test_merge_fix_verification.py

Or with explicit PYTHONPATH:
    PYTHONPATH=. python test_merge_fix_verification.py
"""

import sys
import os
import uuid

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from garuda_intel.database.models import Base, Entity, Relationship
from garuda_intel.extractor.entity_merger import SemanticEntityDeduplicator


def test_merge_fix():
    """Test that the merge fix works correctly."""
    # Create in-memory database
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    
    deduplicator = SemanticEntityDeduplicator(Session)
    
    print("Creating test entities and relationships...")
    with Session() as session:
        # Create three entities
        microsoft = Entity(
            id=uuid.uuid4(),
            name="Microsoft",
            kind="company",
            data={"industry": "Technology"},
        )
        microsoft_corp = Entity(
            id=uuid.uuid4(),
            name="Microsoft Corporation",
            kind="company",
            data={"founded": "1975"},
        )
        bill_gates = Entity(
            id=uuid.uuid4(),
            name="Bill Gates",
            kind="person",
        )
        session.add_all([microsoft, microsoft_corp, bill_gates])
        session.commit()
        
        # Create relationships
        rel1 = Relationship(
            id=uuid.uuid4(),
            source_id=microsoft.id,
            target_id=bill_gates.id,
            relation_type="FOUNDED_BY",
        )
        rel2 = Relationship(
            id=uuid.uuid4(),
            source_id=bill_gates.id,
            target_id=microsoft.id,
            relation_type="FOUNDED",
        )
        session.add_all([rel1, rel2])
        session.commit()
        
        microsoft_id = str(microsoft.id)
        microsoft_corp_id = str(microsoft_corp.id)
        bill_gates_id = str(bill_gates.id)
        
        print(f"✓ Created entities:")
        print(f"  - Microsoft (ID: {microsoft_id})")
        print(f"  - Microsoft Corporation (ID: {microsoft_corp_id})")
        print(f"  - Bill Gates (ID: {bill_gates_id})")
        print(f"✓ Created 2 relationships between Microsoft and Bill Gates")
    
    # Merge microsoft into microsoft_corp
    print(f"\nMerging 'Microsoft' into 'Microsoft Corporation'...")
    with Session() as session:
        success = deduplicator._merge_entities(session, microsoft_id, microsoft_corp_id)
        session.commit()
        
        if not success:
            print("✗ FAILED: Merge operation returned False")
            return False
        print("✓ Merge completed successfully")
    
    # Verify results
    print("\nVerifying results...")
    with Session() as session:
        # Check entities
        entities = session.execute(select(Entity)).scalars().all()
        print(f"✓ Entities remaining: {len(entities)} (expected: 2)")
        if len(entities) != 2:
            print(f"✗ FAILED: Expected 2 entities, got {len(entities)}")
            return False
        
        # Check that the survivor has merged data
        survivor = session.execute(
            select(Entity).where(Entity.id == microsoft_corp_id)
        ).scalar_one_or_none()
        
        if not survivor:
            print("✗ FAILED: Survivor entity not found")
            return False
        
        print(f"✓ Survivor entity: '{survivor.name}'")
        print(f"  - Kind: {survivor.kind}")
        print(f"  - Data: {survivor.data}")
        
        if survivor.data.get("industry") != "Technology":
            print("✗ FAILED: Data not merged (missing 'industry')")
            return False
        if survivor.data.get("founded") != "1975":
            print("✗ FAILED: Data not merged (missing 'founded')")
            return False
        print("✓ Data merged correctly")
        
        # Check relationships - THIS IS THE CRITICAL TEST
        relationships = session.execute(select(Relationship)).scalars().all()
        print(f"✓ Relationships remaining: {len(relationships)} (expected: 2)")
        
        if len(relationships) != 2:
            print(f"✗ FAILED: Expected 2 relationships to survive, got {len(relationships)}")
            print("   This is the bug we're fixing - relationships were CASCADE deleted!")
            return False
        
        # Verify relationships point to the correct entities
        rel_types = {}
        for rel in relationships:
            if str(rel.source_id) == microsoft_corp_id and str(rel.target_id) == bill_gates_id:
                rel_types['corp_to_gates'] = rel.relation_type
            elif str(rel.source_id) == bill_gates_id and str(rel.target_id) == microsoft_corp_id:
                rel_types['gates_to_corp'] = rel.relation_type
        
        if rel_types.get('corp_to_gates') != "FOUNDED_BY":
            print(f"✗ FAILED: Expected FOUNDED_BY relationship from corp to gates")
            return False
        if rel_types.get('gates_to_corp') != "FOUNDED":
            print(f"✗ FAILED: Expected FOUNDED relationship from gates to corp")
            return False
        
        print("✓ Relationships correctly redirected to survivor entity")
        print(f"  - Microsoft Corporation -> Bill Gates: FOUNDED_BY")
        print(f"  - Bill Gates -> Microsoft Corporation: FOUNDED")
    
    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED!")
    print("="*60)
    print("\nThe fix successfully:")
    print("1. Preserves relationships during merge (no CASCADE delete)")
    print("2. Redirects relationships to the survivor entity")
    print("3. Merges data from both entities")
    print("4. Handles the flush() timing correctly")
    return True


if __name__ == "__main__":
    success = test_merge_fix()
    exit(0 if success else 1)
