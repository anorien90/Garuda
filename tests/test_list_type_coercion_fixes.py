"""
Tests for list-type coercion fixes in entity extraction and relationship processing.

These tests validate that list values returned by LLMs (instead of strings) are
handled gracefully without raising TypeError or AttributeError.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from garuda_intel.extractor.intel_extractor import IntelExtractor


def _make_extractor():
    """Create a minimal IntelExtractor for testing entity extraction."""
    return IntelExtractor(
        ollama_url="http://localhost:11434/api/generate",
        model="test-model",
    )


# --- Bug fix: org.get("type") returns a list instead of string ---


def test_org_type_as_list():
    """extract_entities_from_finding should not crash when org type is a list."""
    extractor = _make_extractor()
    finding = {
        "organizations": [
            {"name": "Acme Corp", "type": ["company", "tech"]}
        ]
    }
    entities = extractor.extract_entities_from_finding(finding)
    assert len(entities) >= 1
    org_entity = [e for e in entities if e["name"] == "Acme Corp"][0]
    assert org_entity["kind"] == "company"
    print("PASS: org type as list handled correctly")


def test_org_type_as_string():
    """Baseline: org type as string still works correctly."""
    extractor = _make_extractor()
    finding = {
        "organizations": [
            {"name": "Acme Corp", "type": "company"}
        ]
    }
    entities = extractor.extract_entities_from_finding(finding)
    assert len(entities) >= 1
    org_entity = [e for e in entities if e["name"] == "Acme Corp"][0]
    assert org_entity["kind"] == "company"
    print("PASS: org type as string works correctly")


def test_org_type_as_none():
    """org type as None should default to 'organization'."""
    extractor = _make_extractor()
    finding = {
        "organizations": [
            {"name": "Unknown Org", "type": None}
        ]
    }
    entities = extractor.extract_entities_from_finding(finding)
    assert len(entities) >= 1
    org_entity = [e for e in entities if e["name"] == "Unknown Org"][0]
    assert org_entity["kind"] in ("organization", "org")
    print("PASS: org type as None handled correctly")


def test_org_type_as_empty_list():
    """org type as empty list should default to 'organization'."""
    extractor = _make_extractor()
    finding = {
        "organizations": [
            {"name": "Empty Type Org", "type": []}
        ]
    }
    entities = extractor.extract_entities_from_finding(finding)
    assert len(entities) >= 1
    org_entity = [e for e in entities if e["name"] == "Empty Type Org"][0]
    assert org_entity["kind"] in ("organization", "org")
    print("PASS: org type as empty list handled correctly")


if __name__ == "__main__":
    test_org_type_as_list()
    test_org_type_as_string()
    test_org_type_as_none()
    test_org_type_as_empty_list()
    print("\nAll tests passed!")
