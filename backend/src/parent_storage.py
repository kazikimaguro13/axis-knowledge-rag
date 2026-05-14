"""Pluggable storage for parent chunk text (spec_031 sidecar evolution).

Two implementations:
- SqliteParentStorage (v0.8 default): file-backed sqlite, lazy SELECT per parent_id
- JsonParentStorage (v0.7 fallback): full-JSON load at init, kept for backward compat
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Protocol, runtime_checkable

from backend.src.chunker import ParentChunk

_log = logging.getLogger(__name__)


@runtime_checkable
class ParentStorage(Protocol):
    """Contract for parent-text persistence backends."""

    def get(self, parent_id: str) -> ParentChunk | None: ...
    def get_many(self, parent_ids: list[str]) -> list[ParentChunk]: ...
    def upsert_many(self, parents: list[ParentChunk]) -> int: ...
    def has(self, parent_id: str) -> bool: ...
    def count(self) -> int: ...
    def clear(self) -> None: ...
    def close(self) -> None: ...


class SqliteParentStorage:
    """SQLite-backed parent storage with lazy SELECT per parent_id.

    Schema:
        parents(parent_id TEXT PK, doc_id TEXT, title TEXT, text TEXT, metadata_json TEXT)
        INDEX idx_parents_doc_id ON parents(doc_id)
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS parents (
        parent_id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        title TEXT NOT NULL,
        text TEXT NOT NULL,
        metadata_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_parents_doc_id ON parents(doc_id);
    """

    # SQLite's default SQLITE_LIMIT_VARIABLE_NUMBER is 999 on builds <3.32 and
    # 32766 on newer builds — but we target the conservative limit so 1000+ doc
    # corpora work everywhere (spec_042 MID #2).
    SQLITE_VARIABLE_LIMIT = 999

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path) if str(db_path) != ":memory:" else Path(":memory:")
        if str(db_path) != ":memory:":
            self._db_path = Path(db_path)
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(self.SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.commit()

    def get(self, parent_id: str) -> ParentChunk | None:
        row = self._conn.execute(
            "SELECT parent_id, doc_id, title, text, metadata_json FROM parents WHERE parent_id = ?",
            (parent_id,),
        ).fetchone()
        return self._row_to_parent(row) if row else None

    def get_many(self, parent_ids: list[str]) -> list[ParentChunk]:
        """Fetch multiple parents in one or more queries.

        Chunked at ``SQLITE_VARIABLE_LIMIT`` (999) so 1000+ docs don't trip
        SQLite's bind-variable cap (spec_042 MID #2). Input order is preserved
        and missing ids are silently dropped — same contract as the original
        single-query implementation.
        """
        if not parent_ids:
            return []
        by_id: dict[str, tuple] = {}
        for i in range(0, len(parent_ids), self.SQLITE_VARIABLE_LIMIT):
            chunk = parent_ids[i : i + self.SQLITE_VARIABLE_LIMIT]
            placeholders = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                f"SELECT parent_id, doc_id, title, text, metadata_json FROM parents "
                f"WHERE parent_id IN ({placeholders})",
                chunk,
            ).fetchall()
            for r in rows:
                by_id[r[0]] = r
        return [self._row_to_parent(by_id[pid]) for pid in parent_ids if pid in by_id]

    def upsert_many(self, parents: list[ParentChunk]) -> int:
        if not parents:
            return 0
        rows = [
            (
                p.parent_id,
                p.doc_id,
                p.title,
                p.text,
                json.dumps(p.metadata, ensure_ascii=False) if p.metadata else None,
            )
            for p in parents
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO parents (parent_id, doc_id, title, text, metadata_json) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def has(self, parent_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM parents WHERE parent_id = ?", (parent_id,)
        ).fetchone()
        return row is not None

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM parents").fetchone()[0]

    def clear(self) -> None:
        self._conn.execute("DELETE FROM parents")
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    def list_all(self) -> list[ParentChunk]:
        """Return all stored parents. Not part of the Protocol; used by VectorStore.load_parents()."""
        rows = self._conn.execute(
            "SELECT parent_id, doc_id, title, text, metadata_json FROM parents"
        ).fetchall()
        return [self._row_to_parent(r) for r in rows]

    def _row_to_parent(self, row: tuple) -> ParentChunk:
        parent_id, doc_id, title, text, metadata_json = row
        metadata = json.loads(metadata_json) if metadata_json else {}
        return ParentChunk(
            parent_id=parent_id,
            doc_id=doc_id,
            title=title,
            text=text,
            metadata=metadata,
        )


class JsonParentStorage:
    """Legacy v0.7 JSON-file storage. Loads all parents at init (eager).

    Kept for backward compat / fallback when sqlite db is absent.
    """

    def __init__(self, json_path: str | Path) -> None:
        self._json_path = Path(json_path)
        self._parents: dict[str, ParentChunk] = {}
        if self._json_path.exists():
            raw = json.loads(self._json_path.read_text(encoding="utf-8"))
            for pid, pdata in (raw.get("parents") or {}).items():
                self._parents[pid] = ParentChunk(
                    parent_id=pid,
                    doc_id=pdata["doc_id"],
                    title=pdata["title"],
                    text=pdata["text"],
                    metadata=pdata.get("metadata") or {},
                )

    def get(self, parent_id: str) -> ParentChunk | None:
        return self._parents.get(parent_id)

    def get_many(self, parent_ids: list[str]) -> list[ParentChunk]:
        return [self._parents[pid] for pid in parent_ids if pid in self._parents]

    def upsert_many(self, parents: list[ParentChunk]) -> int:
        for p in parents:
            self._parents[p.parent_id] = p
        self._persist()
        return len(parents)

    def has(self, parent_id: str) -> bool:
        return parent_id in self._parents

    def count(self) -> int:
        return len(self._parents)

    def clear(self) -> None:
        self._parents.clear()
        if self._json_path.exists():
            self._json_path.unlink()

    def close(self) -> None:
        pass

    def list_all(self) -> list[ParentChunk]:
        """Return all stored parents. Not part of the Protocol; used by VectorStore.load_parents()."""
        return list(self._parents.values())

    def _persist(self) -> None:
        data: dict = {
            "version": 1,
            "parents": {
                pid: {
                    "doc_id": p.doc_id,
                    "title": p.title,
                    "text": p.text,
                    "metadata": p.metadata,
                }
                for pid, p in self._parents.items()
            },
        }
        self._json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def make_parent_storage(
    chroma_dir: str | Path,
    *,
    storage: str = "sqlite",
) -> ParentStorage:
    """Construct ParentStorage with lazy JSON → SQLite migration.

    Behavior:
        storage == "sqlite":
            - parents.db exists → SqliteParentStorage
            - parents.db absent + parents.json exists → auto-migrate to sqlite + return Sqlite
            - both absent → empty SqliteParentStorage
        storage == "json": always JsonParentStorage (legacy mode)
    """
    chroma_dir = Path(chroma_dir)
    sqlite_path = chroma_dir / "parents.db"
    json_path = chroma_dir / "parents.json"

    if storage == "json":
        return JsonParentStorage(json_path)

    # storage == "sqlite" (default)
    if not sqlite_path.exists() and json_path.exists():
        _log.warning("parents.json found, auto-migrating to parents.db (one-time)")
        sqlite_store = SqliteParentStorage(sqlite_path)
        json_store = JsonParentStorage(json_path)
        all_parents = list(json_store._parents.values())
        sqlite_store.upsert_many(all_parents)
        _log.info("migrated %d parents to %s", sqlite_store.count(), sqlite_path)
        json_store.close()
        return sqlite_store

    return SqliteParentStorage(sqlite_path)
