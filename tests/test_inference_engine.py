"""Tests for knowledge inference engine."""

import pytest
from unittest.mock import Mock, MagicMock
import uuid

from garuda_intel.services.inference_engine import (
    KnowledgeInferenceEngine,
    InferredFact,
    InferenceConfidence,
    TransitiveLocationRule,
    IndustryFromCompanyRule,
)


class TestInferredFact:
    """Tests for InferredFact dataclass."""
    
    def test_fact_creation(self):
        """Test creating an inferred fact."""
        fact = InferredFact(
            entity_id="entity-123",
            field_name="location",
            value="San Francisco",
            confidence=0.85,
            inference_type="transitive_location",
            provenance=["company-456"],
            reasoning="Person works at company in SF"
        )
        
        assert fact.entity_id == "entity-123"
        assert fact.field_name == "location"
        assert fact.value == "San Francisco"
        assert fact.confidence == 0.85
        assert fact.timestamp is not None


class TestTransitiveLocationRule:
    """Tests for transitive location inference rule."""
    
    def test_rule_matches_person_with_employer_location(self):
        """Test rule matches when person has employer with location."""
        rule = TransitiveLocationRule()
        
        entity = {
            "id": "person-1",
            "kind": "person",
            "name": "John Doe"
        }
        
        graph_data = {
            "entities": {
                "company-1": {
                    "id": "company-1",
                    "name": "Tech Corp",
                    "data": {"location": "San Francisco"}
                }
            },
            "relationships": {
                "person-1": [
                    {
                        "type": "works_at",
                        "target_id": "company-1"
                    }
                ]
            }
        }
        
        assert rule.matches(entity, graph_data) is True
    
    def test_rule_no_match_wrong_entity_type(self):
        """Test rule doesn't match non-person entities."""
        rule = TransitiveLocationRule()
        
        entity = {
            "id": "company-1",
            "kind": "company",
            "name": "Tech Corp"
        }
        
        graph_data = {"entities": {}, "relationships": {}}
        
        assert rule.matches(entity, graph_data) is False
    
    def test_rule_no_match_no_employer(self):
        """Test rule doesn't match when person has no employer."""
        rule = TransitiveLocationRule()
        
        entity = {
            "id": "person-1",
            "kind": "person",
            "name": "John Doe"
        }
        
        graph_data = {
            "entities": {},
            "relationships": {}
        }
        
        assert rule.matches(entity, graph_data) is False
    
    def test_infer_location_from_employer(self):
        """Test inferring person location from employer."""
        rule = TransitiveLocationRule()
        
        entity = {
            "id": "person-1",
            "kind": "person",
            "name": "John Doe"
        }
        
        graph_data = {
            "entities": {
                "company-1": {
                    "id": "company-1",
                    "name": "Tech Corp",
                    "data": {"location": "San Francisco, CA"}
                }
            },
            "relationships": {
                "person-1": [
                    {
                        "type": "works_at",
                        "target_id": "company-1"
                    }
                ]
            }
        }
        
        facts = rule.infer(entity, graph_data)
        
        assert len(facts) == 1
        assert facts[0].field_name == "probable_location"
        assert facts[0].value == "San Francisco, CA"
        assert facts[0].confidence == rule.base_confidence
        assert "company-1" in facts[0].provenance


class TestIndustryFromCompanyRule:
    """Tests for industry inference rule."""
    
    def test_rule_matches_person_with_company_industry(self):
        """Test rule matches when person's company has industry."""
        rule = IndustryFromCompanyRule()
        
        entity = {
            "id": "person-1",
            "kind": "person",
            "name": "Jane Smith"
        }
        
        graph_data = {
            "entities": {
                "company-1": {
                    "id": "company-1",
                    "name": "Tech Corp",
                    "data": {"industry": "Software"}
                }
            },
            "relationships": {
                "person-1": [
                    {
                        "type": "works_at",
                        "target_id": "company-1"
                    }
                ]
            }
        }
        
        assert rule.matches(entity, graph_data) is True
    
    def test_infer_industry_from_employer(self):
        """Test inferring person's industry from employer."""
        rule = IndustryFromCompanyRule()
        
        entity = {
            "id": "person-1",
            "kind": "person",
            "name": "Jane Smith"
        }
        
        graph_data = {
            "entities": {
                "company-1": {
                    "id": "company-1",
                    "name": "Tech Corp",
                    "data": {"industry": "Software Development"}
                }
            },
            "relationships": {
                "person-1": [
                    {
                        "type": "works_at",
                        "target_id": "company-1"
                    }
                ]
            }
        }
        
        facts = rule.infer(entity, graph_data)
        
        assert len(facts) == 1
        assert facts[0].field_name == "industry"
        assert facts[0].value == "Software Development"
        assert facts[0].confidence == rule.base_confidence


class TestKnowledgeInferenceEngine:
    """Tests for the main inference engine."""
    
    def test_engine_initialization(self):
        """Test engine initializes with default rules."""
        engine = KnowledgeInferenceEngine(min_confidence=0.6)
        
        assert engine.min_confidence == 0.6
        assert len(engine.rules) >= 2  # At least the 2 default rules
    
    def test_register_custom_rule(self):
        """Test registering a custom rule."""
        engine = KnowledgeInferenceEngine()
        initial_count = len(engine.rules)
        
        custom_rule = Mock()
        engine.register_rule(custom_rule)
        
        assert len(engine.rules) == initial_count + 1
    
    def test_infer_missing_data(self):
        """Test inferring missing data for an entity."""
        engine = KnowledgeInferenceEngine(min_confidence=0.5)
        
        entity = {
            "id": "person-1",
            "kind": "person",
            "name": "Alice Johnson",
            "data": {}
        }
        
        graph_data = {
            "entities": {
                "person-1": entity,
                "company-1": {
                    "id": "company-1",
                    "name": "Acme Corp",
                    "data": {
                        "location": "New York",
                        "industry": "Manufacturing"
                    }
                }
            },
            "relationships": {
                "person-1": [
                    {
                        "type": "works_at",
                        "target_id": "company-1"
                    }
                ]
            }
        }
        
        facts = engine.infer_missing_data(entity, graph_data)
        
        # Should infer both location and industry
        assert len(facts) >= 2
        field_names = [f.field_name for f in facts]
        assert "probable_location" in field_names or "industry" in field_names
    
    def test_infer_with_field_filter(self):
        """Test inferring only specific fields."""
        engine = KnowledgeInferenceEngine(min_confidence=0.5)
        
        entity = {
            "id": "person-1",
            "kind": "person",
            "name": "Bob Williams",
            "data": {}
        }
        
        graph_data = {
            "entities": {
                "person-1": entity,
                "company-1": {
                    "id": "company-1",
                    "name": "Tech Inc",
                    "data": {
                        "location": "Seattle",
                        "industry": "Technology"
                    }
                }
            },
            "relationships": {
                "person-1": [
                    {
                        "type": "works_at",
                        "target_id": "company-1"
                    }
                ]
            }
        }
        
        # Only request location
        facts = engine.infer_missing_data(entity, graph_data, fields=["probable_location"])
        
        assert all(f.field_name == "probable_location" for f in facts)
    
    def test_confidence_threshold_filtering(self):
        """Test that low-confidence facts are filtered out."""
        engine = KnowledgeInferenceEngine(min_confidence=0.9)
        
        entity = {
            "id": "person-1",
            "kind": "person",
            "name": "Charlie Brown"
        }
        
        graph_data = {
            "entities": {
                "person-1": entity,
                "company-1": {
                    "id": "company-1",
                    "name": "Some Corp",
                    "data": {"location": "Boston"}
                }
            },
            "relationships": {
                "person-1": [
                    {
                        "type": "works_at",
                        "target_id": "company-1"
                    }
                ]
            }
        }
        
        facts = engine.infer_missing_data(entity, graph_data)
        
        # Transitive location has confidence 0.75 < 0.9, should be filtered
        location_facts = [f for f in facts if f.field_name == "probable_location"]
        assert len(location_facts) == 0
    
    def test_infer_for_all_entities(self):
        """Test running inference for all entities."""
        engine = KnowledgeInferenceEngine(min_confidence=0.5)
        
        graph_data = {
            "entities": {
                "person-1": {
                    "id": "person-1",
                    "kind": "person",
                    "name": "Alice"
                },
                "person-2": {
                    "id": "person-2",
                    "kind": "person",
                    "name": "Bob"
                },
                "company-1": {
                    "id": "company-1",
                    "name": "Tech Corp",
                    "data": {
                        "location": "SF",
                        "industry": "Tech"
                    }
                }
            },
            "relationships": {
                "person-1": [
                    {"type": "works_at", "target_id": "company-1"}
                ],
                "person-2": [
                    {"type": "works_at", "target_id": "company-1"}
                ]
            }
        }
        
        results = engine.infer_for_all_entities(graph_data)
        
        # Both persons should have inferences
        assert "person-1" in results
        assert "person-2" in results
        assert len(results["person-1"]) > 0
        assert len(results["person-2"]) > 0
    
    def test_build_graph_data(self):
        """Test building graph data from database."""
        # Mock database session
        mock_session = Mock()
        
        # Mock entities
        mock_entity1 = Mock()
        mock_entity1.id = uuid.uuid4()
        mock_entity1.name = "Test Entity"
        mock_entity1.kind = "person"
        mock_entity1.data = {"field": "value"}
        
        # Mock relationships
        mock_rel = Mock()
        mock_rel.source_id = mock_entity1.id
        mock_rel.target_id = uuid.uuid4()
        mock_rel.relation_type = "knows"
        mock_rel.metadata_json = {}
        
        mock_session.query.return_value.all.side_effect = [
            [mock_entity1],  # entities query
            [mock_rel]  # relationships query
        ]
        
        engine = KnowledgeInferenceEngine()
        graph_data = engine.build_graph_data(mock_session)
        
        assert "entities" in graph_data
        assert "relationships" in graph_data
        assert len(graph_data["entities"]) == 1
