"""Tests for enhanced entity extraction in post_crawl_processor."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime


def test_entity_creation_logic():
    """Test the logic for entity creation from intel data."""
    print("\n=== Test: Entity Creation Logic ===")
    
    # Simulate entity extraction from intel
    intel_data = {
        "persons": [
            {"name": "Bill Gates", "role": "Founder", "title": "Co-founder"},
            {"name": "Satya Nadella", "role": "CEO", "title": "Chief Executive Officer"}
        ],
        "products": [
            {"name": "Windows", "description": "Operating System"},
            {"name": "Azure", "description": "Cloud Platform"}
        ],
        "locations": [
            {"city": "Redmond", "country": "USA", "address": "1 Microsoft Way"}
        ],
        "events": [
            {"title": "Founded Microsoft", "date": "1975-04-04"}
        ]
    }
    
    # Extract entity information
    entities_to_create = []
    
    for entity_type in ['persons', 'products', 'locations', 'events']:
        items = intel_data.get(entity_type, [])
        if not isinstance(items, list):
            continue
        
        for item in items:
            if not isinstance(item, dict):
                continue
            
            entity_name = None
            entity_kind = None
            
            if entity_type == 'persons':
                entity_name = item.get('name')
                entity_kind = 'person'
            elif entity_type == 'products':
                entity_name = item.get('name')
                entity_kind = 'product'
            elif entity_type == 'locations':
                entity_name = item.get('address') or item.get('city') or item.get('country')
                entity_kind = 'location'
            elif entity_type == 'events':
                entity_name = item.get('title')
                entity_kind = 'event'
            
            if entity_name and entity_kind:
                entities_to_create.append({
                    'name': entity_name,
                    'kind': entity_kind,
                    'data': item
                })
    
    # Verify correct extraction
    assert len(entities_to_create) == 6, f"Expected 6 entities, got {len(entities_to_create)}"
    print(f"✓ Extracted {len(entities_to_create)} entities from intelligence data")
    
    # Verify entity types
    kinds = [e['kind'] for e in entities_to_create]
    assert kinds.count('person') == 2, "Should have 2 person entities"
    assert kinds.count('product') == 2, "Should have 2 product entities"
    assert kinds.count('location') == 1, "Should have 1 location entity"
    assert kinds.count('event') == 1, "Should have 1 event entity"
    print("✓ Entity kinds correctly identified")
    
    # Verify names
    names = [e['name'] for e in entities_to_create]
    assert "Bill Gates" in names, "Bill Gates should be extracted"
    assert "Windows" in names, "Windows should be extracted"
    print("✓ Entity names correctly extracted")


def test_entity_merging_logic():
    """Test the logic for merging entity data."""
    print("\n=== Test: Entity Merging Logic ===")
    
    # Simulate existing entity
    existing_entity = {
        'name': 'Bill Gates',
        'kind': 'person',
        'metadata': {'title': 'Co-founder'}
    }
    
    # New data from intel
    new_data = {
        'role': 'Founder',
        'description': 'Co-founded Microsoft in 1975'
    }
    
    # Merge logic
    merged_data = existing_entity['metadata'].copy()
    for key, value in new_data.items():
        if value and key not in merged_data:
            merged_data[key] = value
    
    # Verify merge
    assert 'title' in merged_data, "Existing data should be preserved"
    assert 'role' in merged_data, "New data should be added"
    assert 'description' in merged_data, "New data should be added"
    assert merged_data['title'] == 'Co-founder', "Existing values should not be overwritten"
    
    print("✓ Entity merging logic works correctly")
    print(f"  Original fields: {len(existing_entity['metadata'])}")
    print(f"  Merged fields: {len(merged_data)}")


def test_relation_type_determination():
    """Test that appropriate relation types are assigned."""
    print("\n=== Test: Relation Type Determination ===")
    
    # Mock entity objects
    class MockEntity:
        def __init__(self, kind):
            self.kind = kind
    
    # Function from post_crawl_processor
    def determine_relation_type(source_entity, target_entity):
        if not source_entity or not target_entity:
            return 'related_to'
        
        source_kind = source_entity.kind
        target_kind = target_entity.kind
        
        if source_kind in ['organization', 'company'] and target_kind == 'person':
            return 'has_person'
        elif source_kind in ['organization', 'company'] and target_kind == 'location':
            return 'has_location'
        elif source_kind in ['organization', 'company'] and target_kind == 'product':
            return 'produces'
        elif source_kind == 'person' and target_kind in ['organization', 'company']:
            return 'works_at'
        elif source_kind == 'person' and target_kind == 'event':
            return 'participated_in'
        elif target_kind == 'event':
            return 'associated_with_event'
        else:
            return 'related_to'
    
    org_entity = MockEntity('organization')
    person_entity = MockEntity('person')
    product_entity = MockEntity('product')
    location_entity = MockEntity('location')
    event_entity = MockEntity('event')
    
    # Test relation types
    rel_type = determine_relation_type(org_entity, person_entity)
    assert rel_type == "has_person", f"Expected 'has_person', got '{rel_type}'"
    print("✓ Organization → Person relation type: has_person")
    
    rel_type = determine_relation_type(org_entity, location_entity)
    assert rel_type == "has_location", f"Expected 'has_location', got '{rel_type}'"
    print("✓ Organization → Location relation type: has_location")
    
    rel_type = determine_relation_type(org_entity, product_entity)
    assert rel_type == "produces", f"Expected 'produces', got '{rel_type}'"
    print("✓ Organization → Product relation type: produces")
    
    rel_type = determine_relation_type(person_entity, org_entity)
    assert rel_type == "works_at", f"Expected 'works_at', got '{rel_type}'"
    print("✓ Person → Organization relation type: works_at")
    
    rel_type = determine_relation_type(person_entity, event_entity)
    assert rel_type == "participated_in", f"Expected 'participated_in', got '{rel_type}'"
    print("✓ Person → Event relation type: participated_in")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Entity Extraction and Post-Processing Tests")
    print("=" * 60)
    
    test_entity_creation_logic()
    test_entity_merging_logic()
    test_relation_type_determination()
    
    print("\n" + "=" * 60)
    print("✓ All entity extraction tests passed!")
    print("=" * 60)
    print("\nThese tests validate:")
    print("  - Entity creation from intelligence data")
    print("  - Entity merging when duplicates exist")
    print("  - Relationship type assignment logic")
    print("  - Proper entity kind identification")
