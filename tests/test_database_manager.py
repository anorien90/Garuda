"""Tests for the multi-database manager."""

import json
import os
import tempfile
import uuid

import pytest

from garuda_intel.services.database_manager import DatabaseManager
from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.database.models import Entity, Intelligence


@pytest.fixture()
def tmp_data_dir(tmp_path):
    """Provide a temporary data directory."""
    return str(tmp_path)


@pytest.fixture()
def manager(tmp_data_dir):
    """Create a DatabaseManager backed by a temp directory (no Qdrant)."""
    return DatabaseManager(data_dir=tmp_data_dir, qdrant_url=None)


# ------------------------------------------------------------------
# Registry & listing
# ------------------------------------------------------------------

class TestRegistry:
    def test_registry_created_on_init(self, manager, tmp_data_dir):
        reg_path = os.path.join(tmp_data_dir, "databases.json")
        assert os.path.exists(reg_path)
        with open(reg_path) as f:
            data = json.load(f)
        assert data["active"] == "default"
        assert "default" in data["databases"]

    def test_list_databases_default(self, manager):
        dbs = manager.list_databases()
        assert len(dbs) == 1
        assert dbs[0]["name"] == "default"
        assert dbs[0]["is_active"] is True

    def test_get_active_database(self, manager):
        active = manager.get_active_database()
        assert active["name"] == "default"
        assert active["is_active"] is True


# ------------------------------------------------------------------
# Create
# ------------------------------------------------------------------

class TestCreate:
    def test_create_database(self, manager, tmp_data_dir):
        info = manager.create_database("test_research", description="My research DB")
        assert info["name"] == "test_research"
        assert info["qdrant_collection"] == "garuda_test_research"
        assert info["description"] == "My research DB"
        # The SQLite file should exist
        assert os.path.exists(info["db_path"])

    def test_create_sanitizes_name(self, manager):
        info = manager.create_database("My Cool DB!")
        assert info["name"] == "my_cool_db"

    def test_create_duplicate_raises(self, manager):
        manager.create_database("uniq")
        with pytest.raises(ValueError, match="already exists"):
            manager.create_database("uniq")

    def test_create_and_activate(self, manager):
        manager.create_database("new_one", set_active=True)
        active = manager.get_active_database()
        assert active["name"] == "new_one"

    def test_list_after_create(self, manager):
        manager.create_database("alpha")
        manager.create_database("beta")
        dbs = manager.list_databases()
        names = {d["name"] for d in dbs}
        assert names == {"default", "alpha", "beta"}


# ------------------------------------------------------------------
# Switch
# ------------------------------------------------------------------

class TestSwitch:
    def test_switch_database(self, manager):
        manager.create_database("second")
        store, collection = manager.switch_database("second")
        assert isinstance(store, SQLAlchemyStore)
        assert collection == "garuda_second"
        assert manager.get_active_database()["name"] == "second"

    def test_switch_nonexistent_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.switch_database("does_not_exist")


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------

class TestDelete:
    def test_delete_database(self, manager):
        manager.create_database("to_delete")
        assert manager.delete_database("to_delete") is True
        dbs = manager.list_databases()
        names = {d["name"] for d in dbs}
        assert "to_delete" not in names

    def test_delete_default_raises(self, manager):
        with pytest.raises(ValueError, match="Cannot delete the default"):
            manager.delete_database("default")

    def test_delete_active_raises(self, manager):
        manager.create_database("active_one", set_active=True)
        with pytest.raises(ValueError, match="Cannot delete the active"):
            manager.delete_database("active_one")

    def test_delete_nonexistent_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.delete_database("ghost")

    def test_delete_with_files(self, manager):
        info = manager.create_database("deleteme")
        assert os.path.exists(info["db_path"])
        manager.delete_database("deleteme", delete_files=True)
        assert not os.path.exists(info["db_path"])


# ------------------------------------------------------------------
# Merge (SQL only, no Qdrant in tests)
# ------------------------------------------------------------------

class TestMerge:
    def test_merge_entities(self, manager, tmp_data_dir):
        # Create source db with an entity
        src_info = manager.create_database("src_db")
        src_store = SQLAlchemyStore(url=f"sqlite:///{src_info['db_path']}")
        with src_store.Session() as s:
            ent = Entity(
                id=uuid.uuid4(),
                entry_type="entity",
                name="Test Corp",
                kind="company",
                data={"industry": "tech"},
            )
            s.add(ent)
            s.commit()
            ent_id = ent.id

        # Merge into default
        stats = manager.merge_databases("src_db", "default")
        assert stats["entities"] == 1

        # Verify entity is in the target
        tgt_store = SQLAlchemyStore(
            url=f"sqlite:///{manager.get_active_database()['db_path']}"
        )
        with tgt_store.Session() as s:
            merged = s.get(Entity, ent_id)
            assert merged is not None
            assert merged.name == "Test Corp"

    def test_merge_same_raises(self, manager):
        with pytest.raises(ValueError, match="must differ"):
            manager.merge_databases("default", "default")

    def test_merge_nonexistent_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.merge_databases("nope", "default")


# ------------------------------------------------------------------
# Global search
# ------------------------------------------------------------------

class TestGlobalSearch:
    def test_global_search_finds_entities(self, manager, tmp_data_dir):
        # Add entity to default db
        default_info = manager.get_active_database()
        store = SQLAlchemyStore(url=f"sqlite:///{default_info['db_path']}")
        with store.Session() as s:
            s.add(Entity(
                id=uuid.uuid4(),
                entry_type="entity",
                name="Acme Inc",
                kind="company",
            ))
            s.commit()

        results = manager.global_search("Acme")
        assert "default" in results
        assert any(h["name"] == "Acme Inc" for h in results["default"])

    def test_global_search_across_multiple_dbs(self, manager, tmp_data_dir):
        # Entity in default
        def_info = manager.get_active_database()
        store1 = SQLAlchemyStore(url=f"sqlite:///{def_info['db_path']}")
        with store1.Session() as s:
            s.add(Entity(id=uuid.uuid4(), entry_type="entity", name="Alpha Corp", kind="company"))
            s.commit()

        # Entity in second db
        sec_info = manager.create_database("second")
        store2 = SQLAlchemyStore(url=f"sqlite:///{sec_info['db_path']}")
        with store2.Session() as s:
            s.add(Entity(id=uuid.uuid4(), entry_type="entity", name="Alpha Labs", kind="research"))
            s.commit()

        results = manager.global_search("Alpha")
        assert "default" in results
        assert "second" in results
        assert any(h["name"] == "Alpha Corp" for h in results["default"])
        assert any(h["name"] == "Alpha Labs" for h in results["second"])

    def test_global_search_no_results(self, manager):
        results = manager.global_search("zzz_nonexistent_xyz")
        assert results == {}


# ------------------------------------------------------------------
# Sanitization helper
# ------------------------------------------------------------------

class TestSanitize:
    def test_sanitize_basic(self):
        assert DatabaseManager._sanitize_name("hello world") == "hello_world"

    def test_sanitize_special_chars(self):
        assert DatabaseManager._sanitize_name("my-db!@#") == "my_db"

    def test_sanitize_empty(self):
        name = DatabaseManager._sanitize_name("!!!")
        assert name.startswith("db_")
