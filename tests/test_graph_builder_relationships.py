"""Test graph builder relationship edge creation with multi-node types."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.database.models import Entity, Page, Intelligence, Seed, Relationship
from garuda_intel.webapp.services.graph_builder import _add_relationship_edges, _get_node_label
from sqlalchemy import select
import uuid


def test_relationship_edges_in_graph():
    """Test that relationship edges are created with proper kinds and labels."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    # Create test data
    with store.Session() as session:
        # Create entities
        entity1 = Entity(
            id=uuid.uuid4(),
            name="Company Alpha",
            kind="organization",
            data={}
        )
        entity2 = Entity(
            id=uuid.uuid4(),
            name="John Doe",
            kind="person",
            data={}
        )
        
        # Create a page
        page1 = Page(
            id=uuid.uuid4(),
            url="https://example.com/about",
            title="About Company Alpha",
            page_type="about_page",
            score=0.9
        )
        
        # Create a seed
        seed1 = Seed(
            id=uuid.uuid4(),
            query="Company Alpha",
            entity_type="organization",
            source="manual"
        )
        
        session.add_all([entity1, entity2, page1, seed1])
        session.commit()
        
        # Create relationships with different types
        rel1 = Relationship(
            id=uuid.uuid4(),
            source_id=entity2.id,
            target_id=entity1.id,
            relation_type="works_at",
            source_type="entity",
            target_type="entity",
            metadata_json={"confidence": 0.9, "source": "linkedin"}
        )
        
        rel2 = Relationship(
            id=uuid.uuid4(),
            source_id=page1.id,
            target_id=entity1.id,
            relation_type="mentions",
            source_type="page",
            target_type="entity",
            metadata_json={"confidence": 0.85}
        )
        
        rel3 = Relationship(
            id=uuid.uuid4(),
            source_id=seed1.id,
            target_id=page1.id,
            relation_type="discovered",
            source_type="seed",
            target_type="page",
            metadata_json={"search_rank": 1}
        )
        
        session.add_all([rel1, rel2, rel3])
        session.commit()
        
        print(f"✓ Created 2 entities, 1 page, 1 seed")
        print(f"✓ Created 3 relationships with types: works_at, mentions, discovered")
        
        # Test the graph builder
        nodes = {}
        links = {}
        entry_type_map = {
            str(entity1.id): "entity",
            str(entity2.id): "entity",
            str(page1.id): "page",
            str(seed1.id): "seed",
        }
        
        def ensure_node(node_id, label, node_type, score=None, count_inc=1, meta=None):
            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id,
                    "label": label,
                    "type": node_type,
                    "meta": meta or {}
                }
            return node_id
        
        def add_edge(a, b, kind, weight=1, meta=None):
            key = tuple(sorted((a, b)))
            links[key] = {
                "source": a,
                "target": b,
                "kind": kind,
                "weight": weight,
                "meta": meta or {}
            }
        
        _add_relationship_edges(session, ensure_node, add_edge, entry_type_map)
        
        print(f"✓ Graph builder created {len(nodes)} nodes and {len(links)} edges")
        
        # Verify nodes have proper labels
        assert len(nodes) >= 4, f"Expected at least 4 nodes, got {len(nodes)}"
        
        entity1_node = nodes.get(str(entity1.id))
        assert entity1_node is not None, "Entity1 node not found"
        assert entity1_node["label"] == "Company Alpha", f"Expected label 'Company Alpha', got '{entity1_node['label']}'"
        print(f"✓ Entity node has correct label: {entity1_node['label']}")
        
        entity2_node = nodes.get(str(entity2.id))
        assert entity2_node is not None, "Entity2 node not found"
        assert entity2_node["label"] == "John Doe", f"Expected label 'John Doe', got '{entity2_node['label']}'"
        print(f"✓ Entity node has correct label: {entity2_node['label']}")
        
        page1_node = nodes.get(str(page1.id))
        assert page1_node is not None, "Page node not found"
        assert page1_node["label"] == "About Company Alpha", f"Expected label 'About Company Alpha', got '{page1_node['label']}'"
        print(f"✓ Page node has correct label: {page1_node['label']}")
        
        seed1_node = nodes.get(str(seed1.id))
        assert seed1_node is not None, "Seed node not found"
        assert seed1_node["label"] == "Company Alpha", f"Expected label 'Company Alpha', got '{seed1_node['label']}'"
        print(f"✓ Seed node has correct label: {seed1_node['label']}")
        
        # Verify edges have kind="relationship"
        assert len(links) == 3, f"Expected 3 edges, got {len(links)}"
        
        for link_key, link_data in links.items():
            assert link_data["kind"] == "relationship", f"Expected kind 'relationship', got '{link_data['kind']}'"
            assert "relation_type" in link_data["meta"], "Edge metadata should contain relation_type"
            print(f"✓ Edge has kind='relationship' with relation_type='{link_data['meta']['relation_type']}'")
        
        # Verify specific relation types are preserved in metadata
        relation_types = [link["meta"]["relation_type"] for link in links.values()]
        assert "works_at" in relation_types, "works_at relation_type not found in metadata"
        assert "mentions" in relation_types, "mentions relation_type not found in metadata"
        assert "discovered" in relation_types, "discovered relation_type not found in metadata"
        print(f"✓ All relation types preserved in metadata: {relation_types}")


def test_get_node_label_function():
    """Test the _get_node_label helper function."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    
    with store.Session() as session:
        # Create test nodes
        entity = Entity(
            id=uuid.uuid4(),
            name="Test Entity",
            kind="person"
        )
        page = Page(
            id=uuid.uuid4(),
            url="https://test.com",
            title="Test Page"
        )
        session.add_all([entity, page])
        session.commit()
        
        # Test label fetching
        entity_label = _get_node_label(session, str(entity.id), "entity")
        assert entity_label == "Test Entity", f"Expected 'Test Entity', got '{entity_label}'"
        print(f"✓ _get_node_label correctly returns entity name: {entity_label}")
        
        page_label = _get_node_label(session, str(page.id), "page")
        assert page_label == "Test Page", f"Expected 'Test Page', got '{page_label}'"
        print(f"✓ _get_node_label correctly returns page title: {page_label}")
        
        # Test fallback for non-existent node
        fake_id = str(uuid.uuid4())
        fallback_label = _get_node_label(session, fake_id, "entity")
        assert fallback_label == fake_id, f"Expected fallback to ID, got '{fallback_label}'"
        print(f"✓ _get_node_label falls back to ID for non-existent nodes")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Testing Graph Builder Relationship Edge Creation")
    print("=" * 70 + "\n")
    
    print("Test 1: Relationship edges in graph")
    print("-" * 70)
    test_relationship_edges_in_graph()
    print()
    
    print("Test 2: _get_node_label function")
    print("-" * 70)
    test_get_node_label_function()
    print()
    
    print("=" * 70)
    print("✓ All graph builder tests passed!")
    print("=" * 70 + "\n")
