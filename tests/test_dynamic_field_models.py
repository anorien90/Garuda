"""
Unit tests for dynamic field discovery database models.

Tests the DynamicFieldDefinition, EntityFieldValue, and FieldDiscoveryLog models.
"""

import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from garuda_intel.database.models import (
    Base,
    Entity,
    DynamicFieldDefinition,
    EntityFieldValue,
    FieldDiscoveryLog,
)


@pytest.fixture
def db_session():
    """Create an in-memory database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


class TestDynamicFieldDefinition:
    """Test DynamicFieldDefinition model."""
    
    def test_create_field_definition(self, db_session):
        """Test creating a basic field definition."""
        field = DynamicFieldDefinition(
            id=uuid.uuid4(),
            field_name="industry",
            display_name="Industry Sector",
            description="Primary industry or sector of the company",
            entity_type="company",
            field_type="text",
            importance="critical",
            source="llm",
            is_active=True,
        )
        db_session.add(field)
        db_session.commit()
        
        # Verify retrieval
        retrieved = db_session.execute(
            select(DynamicFieldDefinition).where(
                DynamicFieldDefinition.field_name == "industry"
            )
        ).scalar_one()
        
        assert retrieved.field_name == "industry"
        assert retrieved.display_name == "Industry Sector"
        assert retrieved.entity_type == "company"
        assert retrieved.importance == "critical"
        assert retrieved.is_active is True
    
    def test_field_discovery_count_tracking(self, db_session):
        """Test that discovery count can be incremented."""
        field = DynamicFieldDefinition(
            id=uuid.uuid4(),
            field_name="founded_year",
            entity_type="company",
            discovery_count=1,
            success_rate=0.5,
        )
        db_session.add(field)
        db_session.commit()
        
        # Simulate re-discovery
        field.discovery_count += 1
        field.success_rate = 0.75  # Improved rate
        field.last_seen_at = datetime.now(timezone.utc)
        db_session.commit()
        
        retrieved = db_session.execute(
            select(DynamicFieldDefinition).where(
                DynamicFieldDefinition.field_name == "founded_year"
            )
        ).scalar_one()
        
        assert retrieved.discovery_count == 2
        assert retrieved.success_rate == 0.75
    
    def test_hierarchical_fields(self, db_session):
        """Test creating hierarchical field relationships."""
        # Parent field: address
        address_field = DynamicFieldDefinition(
            id=uuid.uuid4(),
            field_name="address",
            entity_type="company",
            field_type="object",
            importance="important",
        )
        db_session.add(address_field)
        db_session.flush()
        
        # Child fields
        city_field = DynamicFieldDefinition(
            id=uuid.uuid4(),
            field_name="city",
            entity_type="company",
            field_type="text",
            parent_field_id=address_field.id,
        )
        postal_code_field = DynamicFieldDefinition(
            id=uuid.uuid4(),
            field_name="postal_code",
            entity_type="company",
            field_type="text",
            parent_field_id=address_field.id,
        )
        db_session.add_all([city_field, postal_code_field])
        db_session.commit()
        
        # Verify parent-child relationship
        parent = db_session.execute(
            select(DynamicFieldDefinition).where(
                DynamicFieldDefinition.field_name == "address"
            )
        ).scalar_one()
        
        assert len(parent.sub_fields) == 2
        sub_field_names = {f.field_name for f in parent.sub_fields}
        assert "city" in sub_field_names
        assert "postal_code" in sub_field_names
    
    def test_field_to_dict(self, db_session):
        """Test to_dict method returns correct structure."""
        field = DynamicFieldDefinition(
            id=uuid.uuid4(),
            field_name="ceo",
            display_name="Chief Executive Officer",
            description="The CEO of the company",
            entity_type="company",
            field_type="text",
            importance="critical",
            discovery_count=5,
            success_rate=0.85,
            example_values={"examples": ["Satya Nadella", "Tim Cook"]},
            source="llm",
            is_active=True,
            last_seen_at=datetime.now(timezone.utc),
        )
        db_session.add(field)
        db_session.commit()
        
        field_dict = field.to_dict()
        
        assert "id" in field_dict
        assert field_dict["field_name"] == "ceo"
        assert field_dict["display_name"] == "Chief Executive Officer"
        assert field_dict["importance"] == "critical"
        assert field_dict["discovery_count"] == 5
        assert field_dict["success_rate"] == 0.85
        assert "examples" in field_dict.get("example_values", {})
    
    def test_unique_constraint_field_entity_type(self, db_session):
        """Test unique constraint on field_name + entity_type."""
        field1 = DynamicFieldDefinition(
            id=uuid.uuid4(),
            field_name="location",
            entity_type="company",
        )
        db_session.add(field1)
        db_session.commit()
        
        # Same field name, different entity type - should work
        field2 = DynamicFieldDefinition(
            id=uuid.uuid4(),
            field_name="location",
            entity_type="person",
        )
        db_session.add(field2)
        db_session.commit()
        
        # Same field name, same entity type - should fail
        field3 = DynamicFieldDefinition(
            id=uuid.uuid4(),
            field_name="location",
            entity_type="company",
        )
        db_session.add(field3)
        
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()


class TestEntityFieldValue:
    """Test EntityFieldValue model."""
    
    @pytest.fixture
    def entity(self, db_session):
        """Create a test entity."""
        entity = Entity(
            id=uuid.uuid4(),
            name="Test Company",
            kind="company",
        )
        db_session.add(entity)
        db_session.commit()
        return entity
    
    def test_create_text_field_value(self, db_session, entity):
        """Test creating a text field value."""
        field_value = EntityFieldValue(
            id=uuid.uuid4(),
            entity_id=entity.id,
            field_name="headquarters",
            value_text="San Francisco, CA",
            confidence=0.95,
            extraction_method="llm",
            is_current=True,
        )
        db_session.add(field_value)
        db_session.commit()
        
        retrieved = db_session.execute(
            select(EntityFieldValue).where(
                EntityFieldValue.entity_id == entity.id
            )
        ).scalar_one()
        
        assert retrieved.field_name == "headquarters"
        assert retrieved.get_value() == "San Francisco, CA"
        assert retrieved.confidence == 0.95
    
    def test_create_number_field_value(self, db_session, entity):
        """Test creating a numeric field value."""
        field_value = EntityFieldValue(
            id=uuid.uuid4(),
            entity_id=entity.id,
            field_name="employee_count",
            value_number=50000.0,
            confidence=0.8,
            extraction_method="heuristic",
            is_current=True,
        )
        db_session.add(field_value)
        db_session.commit()
        
        retrieved = db_session.execute(
            select(EntityFieldValue).where(
                EntityFieldValue.field_name == "employee_count"
            )
        ).scalar_one()
        
        assert retrieved.get_value() == 50000.0
    
    def test_create_json_field_value(self, db_session, entity):
        """Test creating a JSON field value."""
        address_data = {
            "street": "1 Microsoft Way",
            "city": "Redmond",
            "state": "WA",
            "postal_code": "98052",
        }
        field_value = EntityFieldValue(
            id=uuid.uuid4(),
            entity_id=entity.id,
            field_name="address",
            value_json=address_data,
            confidence=0.9,
            extraction_method="llm",
            is_current=True,
        )
        db_session.add(field_value)
        db_session.commit()
        
        retrieved = db_session.execute(
            select(EntityFieldValue).where(
                EntityFieldValue.field_name == "address"
            )
        ).scalar_one()
        
        value = retrieved.get_value()
        assert isinstance(value, dict)
        assert value["city"] == "Redmond"
        assert value["postal_code"] == "98052"
    
    def test_field_value_versioning(self, db_session, entity):
        """Test that field values support versioning."""
        # Create initial value
        old_value = EntityFieldValue(
            id=uuid.uuid4(),
            entity_id=entity.id,
            field_name="revenue",
            value_number=100000000.0,
            confidence=0.7,
            is_current=True,
        )
        db_session.add(old_value)
        db_session.commit()
        
        # Mark old as superseded
        old_value.is_current = False
        
        # Create new value
        new_value = EntityFieldValue(
            id=uuid.uuid4(),
            entity_id=entity.id,
            field_name="revenue",
            value_number=150000000.0,
            confidence=0.9,
            is_current=True,
        )
        old_value.superseded_by_id = new_value.id
        
        db_session.add(new_value)
        db_session.commit()
        
        # Query current values only
        current_values = db_session.execute(
            select(EntityFieldValue).where(
                EntityFieldValue.entity_id == entity.id,
                EntityFieldValue.field_name == "revenue",
                EntityFieldValue.is_current == True,  # noqa: E712
            )
        ).scalars().all()
        
        assert len(current_values) == 1
        assert current_values[0].get_value() == 150000000.0
        
        # Query all values (history)
        all_values = db_session.execute(
            select(EntityFieldValue).where(
                EntityFieldValue.entity_id == entity.id,
                EntityFieldValue.field_name == "revenue",
            )
        ).scalars().all()
        
        assert len(all_values) == 2
    
    def test_entity_dynamic_field_relationship(self, db_session, entity):
        """Test entity-to-field-values relationship."""
        # Add multiple field values
        fields = [
            EntityFieldValue(
                id=uuid.uuid4(),
                entity_id=entity.id,
                field_name="industry",
                value_text="Technology",
                is_current=True,
            ),
            EntityFieldValue(
                id=uuid.uuid4(),
                entity_id=entity.id,
                field_name="founded",
                value_number=1975.0,
                is_current=True,
            ),
        ]
        db_session.add_all(fields)
        db_session.commit()
        
        # Access through entity relationship
        db_session.refresh(entity)
        assert len(entity.dynamic_field_values) == 2
        
        field_names = {fv.field_name for fv in entity.dynamic_field_values}
        assert "industry" in field_names
        assert "founded" in field_names
    
    def test_field_value_to_dict(self, db_session, entity):
        """Test to_dict method returns correct structure."""
        field_value = EntityFieldValue(
            id=uuid.uuid4(),
            entity_id=entity.id,
            field_name="stock_symbol",
            value_text="MSFT",
            confidence=1.0,
            extraction_method="user",
            source_url="https://finance.yahoo.com/quote/MSFT",
            is_current=True,
        )
        db_session.add(field_value)
        db_session.commit()
        
        value_dict = field_value.to_dict()
        
        assert "id" in value_dict
        assert value_dict["field_name"] == "stock_symbol"
        assert value_dict["value"] == "MSFT"
        assert value_dict["confidence"] == 1.0
        assert value_dict["extraction_method"] == "user"
        assert value_dict["source_url"] == "https://finance.yahoo.com/quote/MSFT"


class TestFieldDiscoveryLog:
    """Test FieldDiscoveryLog model."""
    
    def test_create_successful_discovery_log(self, db_session):
        """Test logging a successful field discovery."""
        log = FieldDiscoveryLog(
            id=uuid.uuid4(),
            field_name="ceo",
            entity_type="company",
            was_successful=True,
            extraction_confidence=0.92,
            discovery_method="llm",
            extraction_method="llm",
            context_snippet="The CEO of Microsoft is Satya Nadella...",
        )
        db_session.add(log)
        db_session.commit()
        
        retrieved = db_session.execute(
            select(FieldDiscoveryLog).where(
                FieldDiscoveryLog.field_name == "ceo"
            )
        ).scalar_one()
        
        assert retrieved.was_successful is True
        assert retrieved.extraction_confidence == 0.92
        assert "Satya Nadella" in retrieved.context_snippet
    
    def test_create_failed_discovery_log(self, db_session):
        """Test logging a failed field discovery."""
        log = FieldDiscoveryLog(
            id=uuid.uuid4(),
            field_name="patent_count",
            entity_type="company",
            was_successful=False,
            discovery_method="heuristic",
            metadata_json={"error": "Field not found in document"},
        )
        db_session.add(log)
        db_session.commit()
        
        retrieved = db_session.execute(
            select(FieldDiscoveryLog).where(
                FieldDiscoveryLog.field_name == "patent_count"
            )
        ).scalar_one()
        
        assert retrieved.was_successful is False
        assert retrieved.metadata_json["error"] == "Field not found in document"
    
    def test_discovery_log_aggregation(self, db_session):
        """Test that discovery logs can be aggregated for learning."""
        # Create multiple discovery attempts
        logs = [
            FieldDiscoveryLog(
                id=uuid.uuid4(),
                field_name="revenue",
                entity_type="company",
                was_successful=True,
                extraction_confidence=0.85,
                discovery_method="llm",
            ),
            FieldDiscoveryLog(
                id=uuid.uuid4(),
                field_name="revenue",
                entity_type="company",
                was_successful=True,
                extraction_confidence=0.9,
                discovery_method="llm",
            ),
            FieldDiscoveryLog(
                id=uuid.uuid4(),
                field_name="revenue",
                entity_type="company",
                was_successful=False,
                discovery_method="heuristic",
            ),
        ]
        db_session.add_all(logs)
        db_session.commit()
        
        # Query success rate
        from sqlalchemy import func
        
        success_count = db_session.execute(
            select(func.count(FieldDiscoveryLog.id)).where(
                FieldDiscoveryLog.field_name == "revenue",
                FieldDiscoveryLog.was_successful == True,  # noqa: E712
            )
        ).scalar()
        
        total_count = db_session.execute(
            select(func.count(FieldDiscoveryLog.id)).where(
                FieldDiscoveryLog.field_name == "revenue",
            )
        ).scalar()
        
        assert success_count == 2
        assert total_count == 3
        assert success_count / total_count == pytest.approx(0.667, rel=0.01)


class TestIntegration:
    """Integration tests for dynamic field workflow."""
    
    def test_complete_field_discovery_workflow(self, db_session):
        """Test complete workflow: define field, create entity, set value, track discovery."""
        # 1. Create field definition (discovered by LLM)
        field_def = DynamicFieldDefinition(
            id=uuid.uuid4(),
            field_name="market_cap",
            display_name="Market Capitalization",
            description="Total market value of company shares",
            entity_type="company",
            field_type="number",
            importance="critical",
            source="llm",
            discovery_count=1,
        )
        db_session.add(field_def)
        
        # 2. Create entity
        entity = Entity(
            id=uuid.uuid4(),
            name="Apple Inc.",
            kind="company",
        )
        db_session.add(entity)
        db_session.flush()
        
        # 3. Set field value with link to definition
        field_value = EntityFieldValue(
            id=uuid.uuid4(),
            entity_id=entity.id,
            field_definition_id=field_def.id,
            field_name="market_cap",
            value_number=3000000000000.0,  # $3 trillion
            confidence=0.95,
            extraction_method="llm",
            source_url="https://finance.yahoo.com/quote/AAPL",
            is_current=True,
        )
        db_session.add(field_value)
        
        # 4. Log the discovery
        discovery_log = FieldDiscoveryLog(
            id=uuid.uuid4(),
            field_name="market_cap",
            entity_type="company",
            entity_id=entity.id,
            was_successful=True,
            extraction_confidence=0.95,
            discovery_method="llm",
            context_snippet="Apple's market cap reached $3 trillion...",
        )
        db_session.add(discovery_log)
        
        # 5. Update field definition stats
        field_def.discovery_count += 1
        field_def.success_rate = 1.0  # 100% success so far
        field_def.last_seen_at = datetime.now(timezone.utc)
        
        db_session.commit()
        
        # Verify everything is connected
        db_session.refresh(entity)
        
        assert len(entity.dynamic_field_values) == 1
        assert entity.dynamic_field_values[0].get_value() == 3000000000000.0
        assert entity.dynamic_field_values[0].field_definition.field_name == "market_cap"
