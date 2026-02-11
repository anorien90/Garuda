"""Tests for StoreProxy database switching isolation and entity/relationship deletion."""

import json
import os
import tempfile
import uuid

import pytest
from sqlalchemy import select

from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.database.models import Entity, Relationship, Intelligence
from garuda_intel.services.database_manager import DatabaseManager


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture()
def tmp_data_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture()
def manager(tmp_data_dir):
    return DatabaseManager(data_dir=tmp_data_dir, qdrant_url=None)


# ------------------------------------------------------------------
# StoreProxy – transparent swapping
# ------------------------------------------------------------------


class _StoreProxy:
    """Same proxy class used in app.py – duplicated here for unit-testing."""

    def __init__(self, initial):
        object.__setattr__(self, '_target', initial)

    def _swap(self, new_store):
        object.__setattr__(self, '_target', new_store)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_target'), name)

    def __setattr__(self, name, value):
        if name == '_target':
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, '_target'), name, value)


class TestStoreProxy:
    def test_proxy_delegates_session(self, tmp_path):
        db_path = str(tmp_path / "a.db")
        real = SQLAlchemyStore(url=f"sqlite:///{db_path}")
        proxy = _StoreProxy(real)
        # Session attribute should be accessible via proxy
        assert proxy.Session is real.Session

    def test_proxy_swap_changes_session(self, tmp_path):
        db_a = str(tmp_path / "a.db")
        db_b = str(tmp_path / "b.db")
        store_a = SQLAlchemyStore(url=f"sqlite:///{db_a}")
        store_b = SQLAlchemyStore(url=f"sqlite:///{db_b}")
        proxy = _StoreProxy(store_a)
        assert proxy.Session is store_a.Session
        proxy._swap(store_b)
        assert proxy.Session is store_b.Session

    def test_closures_pick_up_swap(self, tmp_path):
        """A closure that captured the proxy sees the new store after swap."""
        db_a = str(tmp_path / "a.db")
        db_b = str(tmp_path / "b.db")
        store_a = SQLAlchemyStore(url=f"sqlite:///{db_a}")
        store_b = SQLAlchemyStore(url=f"sqlite:///{db_b}")
        proxy = _StoreProxy(store_a)

        # Simulate a closure capturing the proxy
        def get_entities():
            with proxy.Session() as s:
                return s.execute(select(Entity)).scalars().all()

        # Add entity to store_a
        with store_a.Session() as s:
            s.add(Entity(id=uuid.uuid4(), entry_type="entity", name="A-Corp", kind="company"))
            s.commit()

        assert len(get_entities()) == 1  # sees store_a

        # Swap to store_b (empty)
        proxy._swap(store_b)
        assert len(get_entities()) == 0  # sees store_b

        # Swap back
        proxy._swap(store_a)
        assert len(get_entities()) == 1  # sees store_a again


# ------------------------------------------------------------------
# Database switching isolation
# ------------------------------------------------------------------


class TestSwitchIsolation:
    def test_entities_isolated_per_db(self, manager, tmp_data_dir):
        """After switching, only entities from the active DB should be visible."""
        # Add entity to default
        default_info = manager.get_active_database()
        store_default = SQLAlchemyStore(url=f"sqlite:///{default_info['db_path']}")
        with store_default.Session() as s:
            s.add(Entity(id=uuid.uuid4(), entry_type="entity", name="Default Corp", kind="company"))
            s.commit()

        # Create and switch to second DB
        sec_info = manager.create_database("research")
        store_research, _ = manager.switch_database("research")
        with store_research.Session() as s:
            s.add(Entity(id=uuid.uuid4(), entry_type="entity", name="Research Lab", kind="research"))
            s.commit()

        # Research DB should only have Research Lab
        with store_research.Session() as s:
            ents = s.execute(select(Entity)).scalars().all()
            names = {e.name for e in ents}
            assert names == {"Research Lab"}

        # Switch back to default
        store_back, _ = manager.switch_database("default")
        with store_back.Session() as s:
            ents = s.execute(select(Entity)).scalars().all()
            names = {e.name for e in ents}
            assert names == {"Default Corp"}


# ------------------------------------------------------------------
# Entity + Relationship deletion
# ------------------------------------------------------------------


class TestEntityDeletion:
    def test_delete_entity_removes_relationships(self, tmp_path):
        db_path = str(tmp_path / "del.db")
        store = SQLAlchemyStore(url=f"sqlite:///{db_path}")

        ent_a = Entity(id=uuid.uuid4(), entry_type="entity", name="Alpha", kind="company")
        ent_b = Entity(id=uuid.uuid4(), entry_type="entity", name="Beta", kind="company")
        rel = Relationship(
            id=uuid.uuid4(),
            entry_type="relationship",
            source_id=ent_a.id,
            target_id=ent_b.id,
            relation_type="partner",
        )

        with store.Session() as s:
            s.add_all([ent_a, ent_b, rel])
            s.commit()

        # Delete Alpha and its relationships
        with store.Session() as s:
            entity = s.query(Entity).filter_by(id=ent_a.id).first()
            for r in list(entity.outgoing_relationships) + list(entity.incoming_relationships):
                s.delete(r)
            s.delete(entity)
            s.commit()

        # Verify Alpha is gone and relationship is gone
        with store.Session() as s:
            assert s.get(Entity, ent_a.id) is None
            assert s.get(Relationship, rel.id) is None
            # Beta still exists
            assert s.get(Entity, ent_b.id) is not None

    def test_delete_single_relationship(self, tmp_path):
        db_path = str(tmp_path / "reltest.db")
        store = SQLAlchemyStore(url=f"sqlite:///{db_path}")

        ent_a = Entity(id=uuid.uuid4(), entry_type="entity", name="X", kind="org")
        ent_b = Entity(id=uuid.uuid4(), entry_type="entity", name="Y", kind="org")
        rel = Relationship(
            id=uuid.uuid4(),
            entry_type="relationship",
            source_id=ent_a.id,
            target_id=ent_b.id,
            relation_type="funding",
        )

        with store.Session() as s:
            s.add_all([ent_a, ent_b, rel])
            s.commit()

        with store.Session() as s:
            r = s.get(Relationship, rel.id)
            assert r is not None
            s.delete(r)
            s.commit()

        with store.Session() as s:
            assert s.get(Relationship, rel.id) is None
            # Both entities still exist
            assert s.get(Entity, ent_a.id) is not None
            assert s.get(Entity, ent_b.id) is not None
