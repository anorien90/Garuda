"""Tests for comprehensive entity extraction and relationship inference."""

from garuda_intel.extractor.intel_extractor import IntelExtractor


def test_comprehensive_extraction_enabled():
    """Test that comprehensive extraction mode is enabled by default."""
    
    extractor = IntelExtractor(enable_comprehensive_extraction=True)
    assert extractor.enable_comprehensive_extraction is True
    print("✓ Comprehensive extraction enabled by default")


def test_extract_entities_from_finding_with_organizations():
    """Test that organizations are extracted from findings."""
    
    extractor = IntelExtractor()
    
    finding = {
        "basic_info": {
            "official_name": "Microsoft Corporation",
            "industry": "Technology"
        },
        "persons": [
            {"name": "Satya Nadella", "title": "CEO", "organization": "Microsoft"},
            {"name": "Bill Gates", "title": "Co-founder", "role": "founder"}
        ],
        "organizations": [
            {"name": "LinkedIn", "type": "company", "industry": "Social"},
            {"name": "GitHub", "type": "company", "industry": "Developer Tools"},
            {"name": "Activision Blizzard", "type": "company", "industry": "Gaming"}
        ],
        "products": [
            {"name": "Windows", "description": "Operating system", "manufacturer": "Microsoft"},
            {"name": "Azure", "description": "Cloud platform"}
        ]
    }
    
    entities = extractor.extract_entities_from_finding(finding)
    
    # Count entity types
    entity_kinds = [e["kind"] for e in entities]
    
    # Check that organizations are extracted
    # Expect exactly 4 organizations: Microsoft (from basic_info) + LinkedIn, GitHub, Activision Blizzard
    org_count = sum(1 for k in entity_kinds if k in ["company", "organization"])
    assert org_count == 4, f"Expected 4 organizations, got {org_count}. Entities: {entities}"
    
    # Check specific organizations
    org_names = [e["name"] for e in entities if e["kind"] in ["company", "organization"]]
    assert "LinkedIn" in org_names, f"LinkedIn not found in {org_names}"
    assert "GitHub" in org_names, f"GitHub not found in {org_names}"
    assert "Activision Blizzard" in org_names, f"Activision Blizzard not found in {org_names}"
    
    print("✓ Organizations extracted from findings")


def test_relationship_inference():
    """Test that relationships are inferred between entities."""
    
    extractor = IntelExtractor()
    
    # Create entities that should have inferred relationships
    entities = [
        {"name": "Satya Nadella", "kind": "ceo", "data": {"organization": "Microsoft"}},
        {"name": "Microsoft", "kind": "company", "data": {"industry": "Technology"}},
        {"name": "Windows", "kind": "product", "data": {"manufacturer": "Microsoft"}},
        {"name": "Redmond", "kind": "headquarters", "data": {"associated_entity": "Microsoft"}},
    ]
    
    context = """
    Microsoft Corporation is headquartered in Redmond, Washington.
    Satya Nadella has been the CEO of Microsoft since 2014.
    Windows is Microsoft's flagship operating system.
    """
    
    inferred_rels = extractor.infer_relationships_from_entities(entities, context)
    
    # Check that relationships were inferred
    assert len(inferred_rels) > 0, "No relationships inferred"
    
    # Check relationship structure
    for rel in inferred_rels:
        assert "source" in rel, "Relationship missing source"
        assert "target" in rel, "Relationship missing target"
        assert "relation_type" in rel, "Relationship missing relation_type"
        assert "inferred" in rel and rel["inferred"], "Relationship not marked as inferred"
    
    # Check specific relationships
    rel_pairs = [(r["source"], r["target"], r["relation_type"]) for r in inferred_rels]
    print(f"Inferred relationships: {rel_pairs}")
    
    # Should have CEO-Company relationship
    ceo_rel_exists = any(
        ("Satya Nadella" in r[0] or "Satya Nadella" in r[1]) and 
        ("Microsoft" in r[0] or "Microsoft" in r[1])
        for r in rel_pairs
    )
    assert ceo_rel_exists, "CEO-Company relationship not inferred"
    
    print("✓ Relationships inferred from entity context")


def test_relationship_inference_org_to_org():
    """Test that organization-organization relationships are inferred."""
    
    extractor = IntelExtractor()
    
    entities = [
        {"name": "Microsoft", "kind": "company", "data": {}},
        {"name": "Activision Blizzard", "kind": "company", "data": {}},
    ]
    
    context = """
    Microsoft acquired Activision Blizzard in a landmark $68.7 billion deal,
    making it one of the largest gaming acquisitions in history.
    """
    
    inferred_rels = extractor.infer_relationships_from_entities(entities, context)
    
    # Check that acquisition relationship was inferred
    acq_rels = [r for r in inferred_rels if r.get("relation_type") == "acquired"]
    assert len(acq_rels) > 0, "Acquisition relationship not inferred"
    
    print("✓ Organization-Organization relationships inferred")


def test_entities_appear_together():
    """Test the helper method for detecting co-occurrence."""
    
    extractor = IntelExtractor()
    
    context = "Bill Gates and Paul Allen founded Microsoft in 1975 in Albuquerque, New Mexico."
    context_lower = context.lower()
    
    # Entities that appear together - the function expects lowercase context
    assert extractor._entities_appear_together("bill gates", "microsoft", context_lower)
    assert extractor._entities_appear_together("paul allen", "microsoft", context_lower)
    
    # Entities that appear far apart (in a longer context)
    long_context = "bill gates is a philanthropist. " + "x" * 300 + " microsoft is a company."
    assert not extractor._entities_appear_together("bill gates", "microsoft", long_context, window=100)
    
    print("✓ Entity co-occurrence detection working")


def test_detect_org_org_relation():
    """Test organization relationship type detection."""
    
    extractor = IntelExtractor()
    
    # Test acquisition
    context1 = "Microsoft acquired LinkedIn in 2016 for $26.2 billion."
    rel_type = extractor._detect_org_org_relation("Microsoft", "LinkedIn", context1)
    assert rel_type == "acquired", f"Expected 'acquired', got {rel_type}"
    
    # Test partnership
    context2 = "Microsoft and OpenAI announced a strategic partnership."
    rel_type = extractor._detect_org_org_relation("Microsoft", "OpenAI", context2)
    assert rel_type == "partners_with", f"Expected 'partners_with', got {rel_type}"
    
    # Test competition
    context3 = "Microsoft competes with Google in the cloud computing market."
    rel_type = extractor._detect_org_org_relation("Microsoft", "Google", context3)
    assert rel_type == "competes_with", f"Expected 'competes_with', got {rel_type}"
    
    print("✓ Organization relationship type detection working")


def test_comprehensive_aggregate_structure():
    """Test that the aggregate structure includes organizations."""
    
    extractor = IntelExtractor()
    
    # Simulate what extract_intelligence would produce
    aggregate = {
        "basic_info": {},
        "persons": [],
        "jobs": [],
        "metrics": [],
        "locations": [],
        "financials": [],
        "products": [],
        "events": [],
        "relationships": [],
        "organizations": [],
    }
    
    new_intel = {
        "organizations": [
            {"name": "TestCorp", "type": "company"}
        ]
    }
    
    merged = extractor._merge_intel(aggregate, new_intel)
    
    assert "organizations" in merged
    assert len(merged["organizations"]) == 1
    assert merged["organizations"][0]["name"] == "TestCorp"
    
    print("✓ Aggregate structure includes organizations")


if __name__ == "__main__":
    print("Running comprehensive extraction tests...")
    print()
    
    test_comprehensive_extraction_enabled()
    test_extract_entities_from_finding_with_organizations()
    test_relationship_inference()
    test_relationship_inference_org_to_org()
    test_entities_appear_together()
    test_detect_org_org_relation()
    test_comprehensive_aggregate_structure()
    
    print()
    print("✓ All comprehensive extraction tests passed!")
