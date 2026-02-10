from datetime import datetime, timezone

from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.database.helpers import uuid4
from garuda_intel.database.models import Entity


def test_save_entities_prefers_latest_duplicate_entity():
    """Ensure duplicate name/kind rows do not raise and pick the most recent."""
    store = SQLAlchemyStore("sqlite:///:memory:")
    newer_id = uuid4()
    older_id = uuid4()

    with store.Session() as session:
        session.add(
            Entity(
                id=older_id,
                name="Acme Corp",
                kind="company",
                data={"source": "old"},
                metadata_json={},
                last_seen=datetime(2023, 1, 1, tzinfo=timezone.utc),
            )
        )
        session.add(
            Entity(
                id=newer_id,
                name="Acme Corp",
                kind="company",
                data={"source": "new"},
                metadata_json={},
                last_seen=datetime(2025, 1, 1, tzinfo=timezone.utc),
            )
        )
        session.commit()

    mapping = store.save_entities(
        [{"name": "Acme Corp", "kind": "company", "data": {"updated": True}}]
    )

    assert str(mapping.get(("Acme Corp", "company"))) == str(newer_id)

    with store.Session() as session:
        entity = session.get(Entity, newer_id)
        assert entity is not None
        assert entity.data.get("source") == "new"
        assert entity.data.get("updated") is True
