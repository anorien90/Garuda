"""
Tests for structure persistence: StructureKind, StructureRelation, UserSetting
models, derive_child_color utility, and registry save/load round-trips.
"""

import pytest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from garuda_intel.database.models import (
    Base,
    StructureKind,
    StructureRelation,
    UserSetting,
)
from garuda_intel.types.entity.registry import (
    EntityKindRegistry,
    derive_child_color,
    get_registry,
)


@pytest.fixture
def db_session():
    """Create a fresh in-memory database for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    yield Session
    engine.dispose()


@pytest.fixture
def fresh_registry():
    """Return a freshly-initialised EntityKindRegistry singleton."""
    EntityKindRegistry._instance = None
    reg = EntityKindRegistry.instance()
    yield reg
    # Reset so other tests are not affected
    EntityKindRegistry._instance = None


# -----------------------------------------------------------------------
# derive_child_color
# -----------------------------------------------------------------------


class TestDeriveChildColor:
    """Tests for the derive_child_color helper."""

    def test_returns_valid_hex(self):
        c = derive_child_color("#0ea5e9", 0)
        assert c.startswith("#")
        assert len(c) == 7

    def test_different_children_get_different_colors(self):
        parent = "#22c55e"
        colors = {derive_child_color(parent, i) for i in range(5)}
        # All five should be unique
        assert len(colors) == 5

    def test_child_color_differs_from_parent(self):
        parent = "#ff0000"
        child = derive_child_color(parent, 0)
        assert child != parent

    def test_invalid_hex_returns_fallback(self):
        assert derive_child_color("invalid", 0) == "#94a3b8"
        assert derive_child_color("#short", 0) == "#94a3b8"


# -----------------------------------------------------------------------
# StructureKind / StructureRelation / UserSetting ORM models
# -----------------------------------------------------------------------


class TestStructureKindModel:
    """Tests for the StructureKind ORM model."""

    def test_create_and_read(self, db_session):
        with db_session() as s:
            sk = StructureKind(
                id=uuid.uuid4(),
                name="test_kind",
                color="#abcdef",
                priority=55,
                parent_kind="org",
                aliases_json=["alias1"],
                description="A test kind",
                is_builtin=False,
            )
            s.add(sk)
            s.commit()

            loaded = s.query(StructureKind).filter_by(name="test_kind").one()
            assert loaded.color == "#abcdef"
            assert loaded.priority == 55
            assert loaded.parent_kind == "org"
            assert loaded.aliases_json == ["alias1"]
            assert loaded.is_builtin is False

    def test_to_dict(self, db_session):
        with db_session() as s:
            sk = StructureKind(
                id=uuid.uuid4(), name="d_kind", color="#111111", priority=10
            )
            s.add(sk)
            s.commit()
            d = sk.to_dict()
            assert d["name"] == "d_kind"
            assert d["color"] == "#111111"

    def test_unique_name_constraint(self, db_session):
        """Duplicate names should raise an IntegrityError."""
        from sqlalchemy.exc import IntegrityError

        with db_session() as s:
            s.add(StructureKind(id=uuid.uuid4(), name="dup_kind", color="#000"))
            s.commit()

        with pytest.raises(IntegrityError):
            with db_session() as s:
                s.add(StructureKind(id=uuid.uuid4(), name="dup_kind", color="#111"))
                s.commit()


class TestStructureRelationModel:
    """Tests for the StructureRelation ORM model."""

    def test_create_and_read(self, db_session):
        with db_session() as s:
            sr = StructureRelation(
                id=uuid.uuid4(),
                name="test_rel",
                color="rgba(0,0,0,0.5)",
                directed=False,
                description="A test relation",
                is_builtin=True,
            )
            s.add(sr)
            s.commit()

            loaded = s.query(StructureRelation).filter_by(name="test_rel").one()
            assert loaded.directed is False
            assert loaded.is_builtin is True

    def test_to_dict(self, db_session):
        with db_session() as s:
            sr = StructureRelation(
                id=uuid.uuid4(), name="d_rel", color="rgba(1,2,3,0.1)"
            )
            s.add(sr)
            s.commit()
            d = sr.to_dict()
            assert d["name"] == "d_rel"


class TestUserSettingModel:
    """Tests for the UserSetting ORM model."""

    def test_create_and_read(self, db_session):
        with db_session() as s:
            us = UserSetting(
                id=uuid.uuid4(),
                key="theme",
                value_json={"mode": "dark"},
                description="Theme preference",
            )
            s.add(us)
            s.commit()

            loaded = s.query(UserSetting).filter_by(key="theme").one()
            assert loaded.value_json == {"mode": "dark"}
            assert loaded.description == "Theme preference"

    def test_to_dict(self, db_session):
        with db_session() as s:
            us = UserSetting(id=uuid.uuid4(), key="lang", value_json={"lang": "en"})
            s.add(us)
            s.commit()
            d = us.to_dict()
            assert d["key"] == "lang"
            assert d["value"] == {"lang": "en"}

    def test_unique_key_constraint(self, db_session):
        from sqlalchemy.exc import IntegrityError

        with db_session() as s:
            s.add(UserSetting(id=uuid.uuid4(), key="dup_key", value_json={}))
            s.commit()

        with pytest.raises(IntegrityError):
            with db_session() as s:
                s.add(UserSetting(id=uuid.uuid4(), key="dup_key", value_json={}))
                s.commit()


# -----------------------------------------------------------------------
# Registry save / load round-trip
# -----------------------------------------------------------------------


class TestRegistrySaveLoad:
    """Tests for save_to_database / load_from_database on EntityKindRegistry."""

    def test_save_populates_database(self, db_session, fresh_registry):
        with db_session() as s:
            stats = fresh_registry.save_to_database(s)
            s.commit()
            assert stats["kinds_saved"] > 0
            assert stats["relations_saved"] > 0

            count = s.query(StructureKind).count()
            assert count == stats["kinds_saved"]

    def test_round_trip_preserves_custom_kind(self, db_session, fresh_registry):
        fresh_registry.register_kind(
            "hospital_xyz",
            parent_kind="org",
            description="Hospital kind",
            priority=60,
        )
        original_color = fresh_registry.get_kind("hospital_xyz").color

        # Save
        with db_session() as s:
            fresh_registry.save_to_database(s)
            s.commit()

        # Reset registry and reload
        EntityKindRegistry._instance = None
        reg2 = EntityKindRegistry.instance()
        assert "hospital_xyz" not in reg2._kinds

        with db_session() as s:
            reg2.load_from_database(s)

        loaded = reg2.get_kind("hospital_xyz")
        assert loaded is not None
        assert loaded.color == original_color
        assert loaded.parent_kind == "org"
        assert loaded.priority == 60

    def test_round_trip_preserves_custom_relation(self, db_session, fresh_registry):
        fresh_registry.register_relation(
            "advises",
            color="rgba(10,20,30,0.5)",
            directed=True,
            description="Advisory relationship",
        )

        with db_session() as s:
            fresh_registry.save_to_database(s)
            s.commit()

        EntityKindRegistry._instance = None
        reg2 = EntityKindRegistry.instance()

        with db_session() as s:
            reg2.load_from_database(s)

        loaded = reg2.get_relation("advises")
        assert loaded is not None
        assert loaded.color == "rgba(10,20,30,0.5)"
        assert loaded.directed is True

    def test_save_upserts_existing_rows(self, db_session, fresh_registry):
        """Second save should update existing rows, not duplicate them."""
        with db_session() as s:
            fresh_registry.save_to_database(s)
            s.commit()
            first_count = s.query(StructureKind).count()

        # Register a new kind and save again
        fresh_registry.register_kind("extra_kind", description="Extra")
        with db_session() as s:
            fresh_registry.save_to_database(s)
            s.commit()
            second_count = s.query(StructureKind).count()

        # Should only have one more row, not duplicates
        assert second_count == first_count + 1

    def test_child_color_derivation_on_register(self, fresh_registry):
        """When registering a kind with parent but no color, color is derived from parent."""
        parent_color = fresh_registry.get_kind("person").color

        fresh_registry.register_kind(
            "data_analyst_xyz",
            parent_kind="person",
        )
        child = fresh_registry.get_kind("data_analyst_xyz")

        assert child.color != parent_color
        assert child.color != "#94a3b8"  # Not the default gray
        assert child.color.startswith("#")
        assert len(child.color) == 7

    def test_builtin_flag_set_correctly(self, db_session, fresh_registry):
        """Builtin kinds should have is_builtin=True in the DB."""
        fresh_registry.register_kind("non_builtin_xyz", description="Not builtin")

        with db_session() as s:
            fresh_registry.save_to_database(s)
            s.commit()

            builtin = s.query(StructureKind).filter_by(name="person").one()
            assert builtin.is_builtin is True

            custom = s.query(StructureKind).filter_by(name="non_builtin_xyz").one()
            assert custom.is_builtin is False
