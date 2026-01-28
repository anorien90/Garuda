"""Test to verify metadata_json field works correctly with Entity model."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.database.models import Entity
from sqlalchemy.orm.attributes import flag_modified
import uuid


def test_metadata_json_assignment():
    """Test that metadata_json can be assigned and modified on Entity objects."""
    print("\n=== Test: metadata_json Assignment ===")
    
    # Create in-memory database
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    with store.get_session() as session:
        # Test 1: Create entity with metadata_json
        entity1 = Entity(
            id=uuid.uuid4(),
            name="Test Entity",
            kind="company",
            metadata_json={"industry": "tech", "founded": "2020"}
        )
        session.add(entity1)
        session.flush()
        
        print(f"✓ Created entity with metadata_json: {entity1.metadata_json}")
        assert entity1.metadata_json == {"industry": "tech", "founded": "2020"}
        
        # Test 2: Update existing metadata_json
        entity1.metadata_json["employees"] = 100
        flag_modified(entity1, 'metadata_json')
        session.flush()
        
        print(f"✓ Updated metadata_json: {entity1.metadata_json}")
        assert "employees" in entity1.metadata_json
        
        # Test 3: Initialize empty metadata_json and add data
        entity2 = Entity(
            id=uuid.uuid4(),
            name="Another Entity",
            kind="person"
        )
        session.add(entity2)
        session.flush()
        
        if not entity2.metadata_json:
            entity2.metadata_json = {}
        
        entity2.metadata_json["role"] = "CEO"
        entity2.metadata_json["title"] = "Chief Executive"
        flag_modified(entity2, 'metadata_json')
        session.flush()
        
        print(f"✓ Initialized and updated metadata_json: {entity2.metadata_json}")
        assert entity2.metadata_json == {"role": "CEO", "title": "Chief Executive"}
        
        # Test 4: Verify metadata doesn't interfere with metadata_json
        # entity.metadata should be the SQLAlchemy MetaData object
        # entity.metadata_json should be the JSON column
        print(f"✓ Entity has both metadata (class attr) and metadata_json (column)")
        assert hasattr(entity1, 'metadata')  # SQLAlchemy MetaData
        assert hasattr(entity1, 'metadata_json')  # Our JSON column
        
        session.commit()
    
    print("✓ All metadata_json tests passed!")


def test_post_crawl_processor_pattern():
    """Test the exact pattern used in post_crawl_processor.py."""
    print("\n=== Test: PostCrawlProcessor Pattern ===")
    
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    with store.get_session() as session:
        # Simulate the pattern from post_crawl_processor.py lines 371-384
        existing_entity = Entity(
            id=uuid.uuid4(),
            name="Microsoft",
            kind="company",
            metadata_json={"industry": "tech"}
        )
        session.add(existing_entity)
        session.flush()
        
        # New data to merge
        entity_data = {
            "founded": "1975",
            "founder": "Bill Gates",
            "location": "Redmond"
        }
        
        # This is the pattern from the fixed code
        merged_data = False
        if not existing_entity.metadata_json:
            existing_entity.metadata_json = {}
        
        for key, value in entity_data.items():
            if value and key not in existing_entity.metadata_json:
                existing_entity.metadata_json[key] = value
                merged_data = True
        
        if merged_data:
            flag_modified(existing_entity, 'metadata_json')
        
        session.flush()
        
        print(f"✓ Merged metadata_json: {existing_entity.metadata_json}")
        assert existing_entity.metadata_json["industry"] == "tech"  # Original
        assert existing_entity.metadata_json["founded"] == "1975"  # Merged
        assert existing_entity.metadata_json["founder"] == "Bill Gates"  # Merged
        
        session.commit()
    
    print("✓ PostCrawlProcessor pattern works correctly!")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Metadata JSON Fix Tests")
    print("=" * 60)
    
    test_metadata_json_assignment()
    test_post_crawl_processor_pattern()
    
    print("\n" + "=" * 60)
    print("✓ All metadata_json fix tests passed!")
    print("=" * 60)
    print("\nThese tests validate:")
    print("  - Entity.metadata_json can be assigned and modified")
    print("  - flag_modified works with 'metadata_json'")
    print("  - PostCrawlProcessor merge pattern works correctly")
    print("  - No confusion between .metadata and .metadata_json")
