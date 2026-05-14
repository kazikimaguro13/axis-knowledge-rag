"""Tests for parent_storage.py: Protocol contract + SQLite-specific + migration."""

import pytest
from pathlib import Path
from backend.src.chunker import ParentChunk
from backend.src.parent_storage import (
    JsonParentStorage,
    SqliteParentStorage,
    make_parent_storage,
)


def make_parent(pid: str = "p1", doc_id: str = "d1", title: str = "t1", text: str = "body 1") -> ParentChunk:
    return ParentChunk(parent_id=pid, doc_id=doc_id, title=title, text=text, metadata={"k": "v"})


class TestCommon:
    """Run identical contract tests against sqlite & json."""

    @pytest.fixture(params=["sqlite", "json"])
    def store(self, request: pytest.FixtureRequest, tmp_path: Path):
        if request.param == "sqlite":
            s = SqliteParentStorage(tmp_path / "p.db")
        else:
            s = JsonParentStorage(tmp_path / "p.json")
        yield s
        s.close()

    def test_empty_get_returns_none(self, store):
        assert store.get("nonexistent") is None

    def test_upsert_get(self, store):
        store.upsert_many([make_parent()])
        p = store.get("p1")
        assert p is not None and p.text == "body 1"

    def test_get_many_preserves_order(self, store):
        store.upsert_many([make_parent("p1"), make_parent("p2"), make_parent("p3")])
        result = store.get_many(["p3", "p1"])
        assert [p.parent_id for p in result] == ["p3", "p1"]

    def test_upsert_replaces(self, store):
        store.upsert_many([make_parent("p1", text="old")])
        store.upsert_many([make_parent("p1", text="new")])
        assert store.get("p1").text == "new"
        assert store.count() == 1

    def test_clear(self, store):
        store.upsert_many([make_parent("p1"), make_parent("p2")])
        store.clear()
        assert store.count() == 0

    def test_has(self, store):
        store.upsert_many([make_parent("p1")])
        assert store.has("p1") and not store.has("p2")

    def test_metadata_preserved(self, store):
        store.upsert_many([make_parent()])
        assert store.get("p1").metadata == {"k": "v"}


class TestSqliteSpecific:
    """SQLite 固有のテスト (3 件)。"""

    def test_persists_across_instances(self, tmp_path: Path):
        db = tmp_path / "p.db"
        s1 = SqliteParentStorage(db)
        s1.upsert_many([make_parent("p1", text="persist")])
        s1.close()
        s2 = SqliteParentStorage(db)
        assert s2.get("p1").text == "persist"
        s2.close()

    def test_wal_mode_enabled(self, tmp_path: Path):
        s = SqliteParentStorage(tmp_path / "p.db")
        mode = s._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
        s.close()

    def test_index_on_doc_id(self, tmp_path: Path):
        s = SqliteParentStorage(tmp_path / "p.db")
        cur = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='parents'"
        ).fetchall()
        assert any("doc_id" in row[0] for row in cur)
        s.close()


class TestMigration:
    """make_parent_storage の lazy migrate テスト。"""

    def test_auto_migrate_json_to_sqlite(self, tmp_path: Path):
        json_store = JsonParentStorage(tmp_path / "parents.json")
        json_store.upsert_many([make_parent("p1"), make_parent("p2")])
        json_store.close()

        store = make_parent_storage(tmp_path, storage="sqlite")
        assert isinstance(store, SqliteParentStorage)
        assert store.count() == 2
        assert (tmp_path / "parents.db").exists()
        store.close()

    def test_factory_no_files_returns_empty_sqlite(self, tmp_path: Path):
        store = make_parent_storage(tmp_path, storage="sqlite")
        assert isinstance(store, SqliteParentStorage)
        assert store.count() == 0
        store.close()

    def test_factory_storage_json_returns_json(self, tmp_path: Path):
        store = make_parent_storage(tmp_path, storage="json")
        assert isinstance(store, JsonParentStorage)
        store.close()

    def test_existing_sqlite_skips_migration(self, tmp_path: Path):
        """If parents.db already exists, JSON is not re-migrated."""
        # Create a parents.db first
        db = SqliteParentStorage(tmp_path / "parents.db")
        db.upsert_many([make_parent("p_existing")])
        db.close()
        # Also put a parents.json (with different data)
        json_store = JsonParentStorage(tmp_path / "parents.json")
        json_store.upsert_many([make_parent("p_json")])
        json_store.close()

        store = make_parent_storage(tmp_path, storage="sqlite")
        assert isinstance(store, SqliteParentStorage)
        # Should load from existing DB, not re-migrate from JSON
        assert store.has("p_existing")
        assert not store.has("p_json")
        store.close()

    def test_migrated_data_matches_original(self, tmp_path: Path):
        """Migrated SQLite store contains same data as source JSON."""
        json_store = JsonParentStorage(tmp_path / "parents.json")
        json_store.upsert_many([make_parent("p1", title="hello", text="world", doc_id="doc42")])
        json_store.close()

        store = make_parent_storage(tmp_path, storage="sqlite")
        p = store.get("p1")
        assert p is not None
        assert p.title == "hello"
        assert p.text == "world"
        assert p.doc_id == "doc42"
        assert p.metadata == {"k": "v"}
        store.close()
