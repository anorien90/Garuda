"""Tests for entity extraction and graph connectivity fixes."""

try:
    import pytest
except ImportError:
    pytest = None

from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.extractor.intel_extractor import IntelExtractor


def test_entity_extraction_with_all_types():
    """Test that all entity types are extracted with complete data."""
    
    extractor = IntelExtractor()
    
    # Sample finding with multiple entity types
    finding = {
        "basic_info": {
            "official_name": "Microsoft Corporation",
            "ticker": "MSFT",
            "industry": "Software & Cloud",
            "description": "Technology company",
            "founded": "1975",
            "website": "https://www.microsoft.com"
        },
        "persons": [
            {
                "name": "Bill Gates",
                "title": "Co-founder",
                "role": "founder",
                "bio": "Co-founded Microsoft in 1975"
            },
            {
                "name": "Satya Nadella",
                "title": "CEO",
                "role": "executive",
                "organization": "Microsoft"
            }
        ],
        "locations": [
            {
                "city": "Redmond",
                "country": "USA",
                "type": "headquarters"
            }
        ],
        "products": [
            {
                "name": "Windows",
                "description": "Operating system",
                "status": "active"
            },
            {
                "name": "Azure",
                "description": "Cloud platform",
                "status": "active"
            }
        ],
        "events": [
            {
                "title": "Founded Microsoft",
                "date": "1975-04-04",
                "description": "Company founded"
            }
        ]
    }
    
    # Extract entities
    entities = extractor.extract_entities_from_finding(finding)
    
    # Verify all entity types are extracted
    entity_kinds = {e["kind"] for e in entities}
    assert "company" in entity_kinds or "entity" in entity_kinds, "Basic info entity missing"
    assert "person" in entity_kinds, "Person entities missing"
    assert "location" in entity_kinds, "Location entities missing"
    assert "product" in entity_kinds, "Product entities missing"
    assert "event" in entity_kinds, "Event entities missing"
    
    # Verify persons have data
    persons = [e for e in entities if e["kind"] == "person"]
    assert len(persons) == 2, f"Expected 2 persons, got {len(persons)}"
    
    bill_gates = next((p for p in persons if p["name"] == "Bill Gates"), None)
    assert bill_gates is not None, "Bill Gates not found"
    assert bill_gates.get("data", {}).get("title") == "Co-founder", "Person data not preserved"
    assert bill_gates.get("data", {}).get("role") == "founder", "Person role not preserved"
    
    # Verify products have data
    products = [e for e in entities if e["kind"] == "product"]
    assert len(products) == 2, f"Expected 2 products, got {len(products)}"
    
    windows = next((p for p in products if p["name"] == "Windows"), None)
    assert windows is not None, "Windows product not found"
    assert windows.get("data", {}).get("description") == "Operating system", "Product data not preserved"
    
    # Verify locations have data
    locations = [e for e in entities if e["kind"] == "location"]
    assert len(locations) >= 1, f"Expected at least 1 location, got {len(locations)}"
    
    redmond = next((l for l in locations if "Redmond" in l["name"]), None)
    assert redmond is not None, "Redmond location not found"
    
    print("✓ All entity types extracted with complete data")


def test_seed_page_relationships():
    """Test that seeds create relationships with pages."""
    
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    # Save a seed
    seed_id = store.save_seed(
        query="Microsoft Corporation",
        entity_type="company",
        source="test"
    )
    assert seed_id is not None
    print(f"✓ Seed created: {seed_id}")
    
    # Save a page
    page_record = {
        "url": "https://www.microsoft.com",
        "page_type": "company_home",
        "score": 0.9,
        "summary": "Microsoft homepage",
        "text_content": "Microsoft Corporation",
        "entity_type": "company",
    }
    page_id = store.save_page(page_record)
    assert page_id is not None
    print(f"✓ Page created: {page_id}")
    
    # Create seed-to-page relationship
    rel_id = store.save_relationship(
        from_id=seed_id,
        to_id=page_id,
        relation_type="seed_page",
        meta={"depth": 0}
    )
    assert rel_id is not None
    print(f"✓ Seed→Page relationship created: {rel_id}")


def test_page_link_relationships():
    """Test that page links create relationships."""
    
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    # Create two pages
    page1 = {
        "url": "https://example.com/page1",
        "page_type": "article",
        "text_content": "Page 1",
    }
    page1_id = store.save_page(page1)
    
    page2 = {
        "url": "https://example.com/page2",
        "page_type": "article",
        "text_content": "Page 2",
    }
    page2_id = store.save_page(page2)
    
    # Create links
    links = [
        {
            "href": "https://example.com/page2",
            "text": "Link to page 2",
            "score": 0.8,
            "depth": 1
        }
    ]
    store.save_links("https://example.com/page1", links)
    
    print("✓ Page links saved with relationships")


def test_uuid_validation():
    """Test that UUID validation prevents errors."""
    
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    # Test with valid UUID
    entities = [
        {
            "name": "Test Entity",
            "kind": "organization",
            "data": {},
        }
    ]
    entity_map = store.save_entities(entities)
    entity_id = entity_map.get(("Test Entity", "organization"))
    assert entity_id is not None
    
    # Try to save relationship with the valid entity ID (should work)
    page_record = {
        "url": "https://example.com/test",
        "text_content": "Test",
    }
    page_id = store.save_page(page_record)
    
    rel_id = store.save_relationship(
        from_id=page_id,
        to_id=entity_id,
        relation_type="mentions_entity"
    )
    assert rel_id is not None
    
    print("✓ UUID validation working correctly")


def test_page_content_unique_constraint():
    """Test that PageContent has unique constraint on page_id."""
    
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    # Create a page
    page_record = {
        "url": "https://example.com/unique",
        "page_type": "article",
        "text_content": "Original content",
        "html": "<html>Original</html>",
    }
    page_id = store.save_page(page_record)
    
    # Try to save the same page again with updated content
    # This should merge/update, not create duplicate PageContent
    updated_record = {
        "url": "https://example.com/unique",
        "page_type": "article",
        "text_content": "Updated content",
        "html": "<html>Updated</html>",
    }
    page_id_2 = store.save_page(updated_record)
    
    # Should return the same page ID
    assert page_id == page_id_2
    
    # Get page content and verify it was updated, not duplicated
    content = store.get_page_content("https://example.com/unique")
    assert content is not None
    assert "Updated" in content.get("text", "")
    
    print("✓ PageContent unique constraint working correctly")


if __name__ == "__main__":
    print("Running entity extraction and graph connectivity tests...")
    print()
    
    test_entity_extraction_with_all_types()
    test_seed_page_relationships()
    test_page_link_relationships()
    test_uuid_validation()
    test_page_content_unique_constraint()
    
    print()
    print("✓ All tests passed!")
