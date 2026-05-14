# spec_037: Parent JSON → SQLite migration (parents.json の永続化方式変更)

- **Author**: Cowork (中島)
- **Created**: 2026-05-14
- **Target**: Claude Code (`dev-d`)
- **Project**: `~/projects/axis-knowledge-rag-d` (WSL Ubuntu, d-worktree)
- **Status**: pending
- **Bundles**: v0.8 spec 2/5。spec_031 (Parent Doc) の運用硬化

## 1. 目的

spec_031 で導入した `parents.json` (parent text の sidecar) は:

- 100-200 docs までは現実的
- 1000+ docs だと **起動時の全 JSON ロード遅延**
- 編集 (例: 1 parent の text update) で **JSON 全体を書き直す** → I/O ヘビー

これを **SQLite (parents.db)** に置換し、**lazy load + JSON fallback** を実装する。既存ユーザーは `python -m scripts.build_index --migrate-parents-json` で 1 発移行可能。

```
[現状 v0.7]
data/chroma/parents.json (全 parent text 1 ファイル)
↓
起動時に dict として全 load → メモリ常駐

[変更後 v0.8]
data/chroma/parents.db (sqlite)
  schema: parents(parent_id PK, doc_id, title, text, metadata_json)
  index: parents(doc_id)
↓
起動時は connection only、parent_id クエリ時に SELECT (lazy load)
↓
parents.json があるのに parents.db が無ければ自動で migrate (1 回だけ)
```

## 2. 制約

### 触ってよいファイル

- `backend/src/vector_store.py` — `_persist_parents()` / `load_parents()` / `has_parents()` を SQLite 対応に拡張。`_parent_db_path` / `_parents_json_path` を持ち、両方サポート (sqlite 優先)
- `backend/src/parent_storage.py` — **新規** (SQLite ラッパ + JSON fallback)。`ParentStorage` Protocol + `SqliteParentStorage` / `JsonParentStorage` の 2 実装
- `scripts/build_index.py` — `--migrate-parents-json` フラグ追加 (旧 JSON → 新 sqlite 一発移行)。`--rebuild` / `--mode parent_doc` でも新規 sqlite 生成
- `backend/src/config.py` — `ParentDocConfig.storage` (`"json"` | `"sqlite"`、default `"sqlite"`)
- `config.yml` — `retrieval.parent_doc.storage: "sqlite"` (default)
- `backend/tests/test_parent_storage.py` — **新規** (10+ tests)
- `backend/tests/test_vector_store.py` — `has_parents()` / `load_parents()` の sqlite 経路テスト追加 (3 件)
- `docs/adr/ADR-023-parent-storage-sqlite.md` — **新規**
- `docs/configuration.md` — `parent_doc.storage` 設定
- `CHANGELOG.md` — Day 37 追記

### 触ってはいけないもの

- `backend/src/{chunker,search,rag,loader,embedder,bm25_index,normalizer,integrity,marker,ingester,_decay,_citations,conversation,question_rewriter,graph}.py`
- ChromaDB の collection や embedding ロジック
- `mcp_server/*`、`frontend/*`、`streamlit_app.py`
- `_ai_workspace/`

### コーディングルール

- **stdlib `sqlite3` のみ** で実装 (新規依存追加なし)
- `parents.json` 互換は **lazy migrate**: 起動時に sqlite 不在 + JSON 存在 → 自動で sqlite 化 + warning ログ
- 移行コマンド `--migrate-parents-json` は **冪等** (既に sqlite ある場合は no-op + skip)
- 既存 v0.7 で `parents.json` を持つユーザーは **何もしなくても動く** (lazy migrate で透過的に変換)
- スレッドセーフ: `check_same_thread=False` + WAL mode

### デプロイ

- v0.8.0 リリース内。tag は spec_036〜039 揃ったあと

## 3. やってほしいこと

### 3-1. ParentStorage Protocol (`backend/src/parent_storage.py`)

```python
"""Pluggable storage for parent chunk text (spec_031 sidecar evolution).

Two implementations:
- SqliteParentStorage (v0.8 default): file-backed sqlite, lazy SELECT per parent_id
- JsonParentStorage (v0.7 fallback): full-JSON load at init, kept for backward compat
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable
import json
import logging
import sqlite3

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
        INDEX parents_doc_id ON parents(doc_id)
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

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.executescript(self.SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.commit()

    def get(self, parent_id):
        row = self._conn.execute(
            "SELECT parent_id, doc_id, title, text, metadata_json FROM parents WHERE parent_id = ?",
            (parent_id,),
        ).fetchone()
        return self._row_to_parent(row) if row else None

    def get_many(self, parent_ids):
        if not parent_ids:
            return []
        placeholders = ",".join("?" * len(parent_ids))
        rows = self._conn.execute(
            f"SELECT parent_id, doc_id, title, text, metadata_json FROM parents "
            f"WHERE parent_id IN ({placeholders})",
            parent_ids,
        ).fetchall()
        # Preserve input order
        by_id = {r[0]: r for r in rows}
        return [self._row_to_parent(by_id[pid]) for pid in parent_ids if pid in by_id]

    def upsert_many(self, parents):
        if not parents:
            return 0
        rows = [(
            p.parent_id, p.doc_id, p.title, p.text,
            json.dumps(p.metadata, ensure_ascii=False) if p.metadata else None,
        ) for p in parents]
        self._conn.executemany(
            "INSERT OR REPLACE INTO parents (parent_id, doc_id, title, text, metadata_json) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def has(self, parent_id):
        row = self._conn.execute(
            "SELECT 1 FROM parents WHERE parent_id = ?", (parent_id,)
        ).fetchone()
        return row is not None

    def count(self):
        return self._conn.execute("SELECT COUNT(*) FROM parents").fetchone()[0]

    def clear(self):
        self._conn.execute("DELETE FROM parents")
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def _row_to_parent(self, row):
        parent_id, doc_id, title, text, metadata_json = row
        metadata = json.loads(metadata_json) if metadata_json else {}
        return ParentChunk(
            parent_id=parent_id, doc_id=doc_id, title=title, text=text,
            metadata=metadata,
        )


class JsonParentStorage:
    """Legacy v0.7 JSON-file storage. Loads all parents at init (eager).

    Kept for backward compat / fallback when sqlite db is absent.
    """

    def __init__(self, json_path: str | Path):
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

    def get(self, parent_id): return self._parents.get(parent_id)
    def get_many(self, parent_ids):
        return [self._parents[pid] for pid in parent_ids if pid in self._parents]
    def upsert_many(self, parents):
        for p in parents:
            self._parents[p.parent_id] = p
        self._persist()
        return len(parents)
    def has(self, parent_id): return parent_id in self._parents
    def count(self): return len(self._parents)
    def clear(self):
        self._parents.clear()
        if self._json_path.exists():
            self._json_path.unlink()
    def close(self): pass

    def _persist(self):
        data = {"version": 1, "parents": {
            pid: {
                "doc_id": p.doc_id, "title": p.title, "text": p.text,
                "metadata": p.metadata,
            } for pid, p in self._parents.items()
        }}
        self._json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
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
        all_parents = [json_store.get(pid) for pid in list(json_store._parents.keys())]
        sqlite_store.upsert_many([p for p in all_parents if p])
        _log.info("migrated %d parents to %s", sqlite_store.count(), sqlite_path)
        json_store.close()
        return sqlite_store
    return SqliteParentStorage(sqlite_path)
```

### 3-2. vector_store.py の差し替え

既存 `VectorStore` で:
- `self._parents: dict[str, ParentChunk]` を保持していた → `self._parent_storage: ParentStorage` に切替
- `_persist_parents()` → `self._parent_storage.upsert_many(parents)`
- `load_parents()` → `self._parent_storage` を init で構築済み、何もしない (lazy fetch)
- `has_parents()` → `self._parent_storage.count() > 0`
- `query_with_parents()` の最後で `self._parent_storage.get_many(top_pids)`

差分は最小限。既存テストの大半は互換動作するはず。

### 3-3. scripts/build_index.py 拡張

```python
parser.add_argument(
    "--migrate-parents-json",
    action="store_true",
    help="One-shot: migrate parents.json to parents.db then exit (idempotent).",
)
parser.add_argument(
    "--parent-storage",
    choices=["sqlite", "json"],
    default=None,
    help="Override config.yml retrieval.parent_doc.storage",
)
```

`--migrate-parents-json` 単独実行:
- chroma_dir 配下に `parents.json` あれば → `parents.db` に移行
- 既に `parents.db` ある → "already migrated" メッセージ + exit 0
- どちらも無し → "no parents.json found" + exit 0

```bash
python -m scripts.build_index --migrate-parents-json
# → migrated 47 parents to data/chroma/parents.db
```

### 3-4. config 拡張

```python
@dataclass(frozen=True)
class ParentDocConfig:
    enabled: bool = True
    chunk_strategy: str = "h2"
    max_child_tokens: int = 256
    top_k_children: int = 20
    top_n_parents: int = 5
    storage: str = "sqlite"   # ← 新規 ("sqlite" | "json")
```

`config.yml` に:

```yaml
retrieval:
  parent_doc:
    enabled: true
    chunk_strategy: "h2"
    max_child_tokens: 256
    top_k_children: 20
    top_n_parents: 5
    storage: "sqlite"   # ← 新規 (default sqlite)
```

### 3-5. テスト (`backend/tests/test_parent_storage.py`)

```python
import pytest
from pathlib import Path
from backend.src.chunker import ParentChunk
from backend.src.parent_storage import (
    SqliteParentStorage, JsonParentStorage, make_parent_storage,
)


def make_parent(pid="p1", doc_id="d1", title="t1", text="body 1"):
    return ParentChunk(parent_id=pid, doc_id=doc_id, title=title, text=text, metadata={"k":"v"})


class TestCommon:
    """Run identical contract tests against sqlite & json."""

    @pytest.fixture(params=["sqlite", "json"])
    def store(self, request, tmp_path):
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

    def test_persists_across_instances(self, tmp_path):
        db = tmp_path / "p.db"
        s1 = SqliteParentStorage(db)
        s1.upsert_many([make_parent("p1", text="persist")])
        s1.close()
        s2 = SqliteParentStorage(db)
        assert s2.get("p1").text == "persist"
        s2.close()

    def test_wal_mode_enabled(self, tmp_path):
        s = SqliteParentStorage(tmp_path / "p.db")
        mode = s._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
        s.close()

    def test_index_on_doc_id(self, tmp_path):
        s = SqliteParentStorage(tmp_path / "p.db")
        cur = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='parents'"
        ).fetchall()
        assert any("doc_id" in row[0] for row in cur)
        s.close()


class TestMigration:
    """make_parent_storage の lazy migrate テスト。"""

    def test_auto_migrate_json_to_sqlite(self, tmp_path):
        # Prepare json
        json_store = JsonParentStorage(tmp_path / "parents.json")
        json_store.upsert_many([make_parent("p1"), make_parent("p2")])
        json_store.close()
        # Call factory
        store = make_parent_storage(tmp_path, storage="sqlite")
        assert isinstance(store, SqliteParentStorage)
        assert store.count() == 2
        assert (tmp_path / "parents.db").exists()
        store.close()

    def test_factory_no_files_returns_empty_sqlite(self, tmp_path):
        store = make_parent_storage(tmp_path, storage="sqlite")
        assert isinstance(store, SqliteParentStorage)
        assert store.count() == 0
        store.close()

    def test_factory_storage_json_returns_json(self, tmp_path):
        store = make_parent_storage(tmp_path, storage="json")
        assert isinstance(store, JsonParentStorage)
        store.close()
```

### 3-6. ADR-023

`docs/adr/ADR-023-parent-storage-sqlite.md`:

- **Context**: parents.json は < 200 docs では十分だが scale で問題、全 read/write が必要
- **Decision**: SQLite (`parents.db`) を default、`parents.json` を fallback として残す
- **Alternatives**:
  - (a) parquet → 却下 (依存追加 + 編集 API 弱い)
  - (b) LMDB → 却下 (依存追加 + 個人運用に過剰)
  - (c) SQLite (採用) — stdlib のみ、indexed lookup、WAL で並行 OK
  - (d) JSON 維持 → 却下 (scale 問題)
- **Consequences**:
  - 既存 parents.json を持つユーザーは初回起動で自動移行 (warning 1 行のみ)
  - `chroma/parents.db` が新たに生成される (~30KB / 50 parents 想定)
  - `--migrate-parents-json` で手動移行も可能
  - JSON モードは config で `storage: "json"` 指定すると有効

### 3-7. 動作確認

```bash
cd ~/projects/axis-knowledge-rag-d   # d-worktree
git checkout -b feat/spec_037-parent-sqlite

# Unit test
ruff check backend/src/parent_storage.py
python3 -m pytest -q backend/tests/test_parent_storage.py backend/tests/test_vector_store.py -v

# 既存 index で auto-migrate 確認 (parents.json 既存)
ls data/chroma/parents.json   # → 存在
python -m scripts.build_index --migrate-parents-json
ls data/chroma/parents.db     # → 新規生成
sqlite3 data/chroma/parents.db "SELECT COUNT(*) FROM parents;"  # → docs 数

# 起動時の lazy load 確認
uvicorn backend.src.api:app --port 8000 &
sleep 3
curl -s -X POST http://localhost:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"RAG","top_k":3}' | jq '.hits | length'
kill %1

# 全体テスト
python3 -m pytest -q
```

### 3-8. コミット粒度

1. `feat(parent_storage): Protocol + SqliteParentStorage + JsonParentStorage`
2. `feat(parent_storage): make_parent_storage factory with auto-migrate (json → sqlite)`
3. `refactor(vector_store): use ParentStorage instead of in-memory parents dict`
4. `feat(build_index): --migrate-parents-json + --parent-storage flags`
5. `feat(config): retrieval.parent_doc.storage = "sqlite" | "json"`
6. `test(parent_storage): parametrize common contract + sqlite-specific + migration`
7. `docs: ADR-023 + configuration + CHANGELOG Day 37`

`git push -u origin feat/spec_037-parent-sqlite`

### 3-9. result_037.md に書くこと

- parents.json (v0.7) と parents.db (v0.8) の **サイズ比較** (KB 単位)
- 起動時間: 1000 parents での JSON 全 load vs sqlite lazy 開始の比較 (ms)
- 既存テスト 291 件 → 何件に増えたか
- migrate コマンドの実行ログ
- backward compat: `storage: "json"` で旧挙動が完全再現できることを確認

## 4. 成功条件

- [ ] `ParentStorage` Protocol + 2 実装 (Sqlite / Json) 完成
- [ ] default = SQLite (`data/chroma/parents.db`)
- [ ] `parents.json` 既存ユーザーは初回起動で **自動 migrate** + warning ログ
- [ ] `python -m scripts.build_index --migrate-parents-json` が冪等
- [ ] `storage: "json"` で v0.7 挙動が完全再現
- [ ] 既存 291 tests 緑 + 新規 parent_storage ~13 件 = >=304 件 PASS
- [ ] ruff 緑
- [ ] ADR-023 / config / CHANGELOG 更新
- [ ] git push 完了 (main には push しない)

## 5. 出力先

`~/projects/axis-knowledge-rag-d/_ai_workspace/bridge/outbox/result_037.md`

## 6. 質問があるとき

- **migration の trigger タイミング**: 本 spec は **factory function 呼び出し時** に lazy migrate。代案として `scripts/build_index.py` 起動時に明示的に行う方が読みやすいかもしれない。CC 判断で OK
- **parents.json の自動削除**: migrate 完了後に旧 JSON を削除するか保持するか。保持する方が安全 (戻したい場合) なので **保持**。ADR-023 に記載
- **VACUUM タイミング**: clear() 後の sqlite が pages を再利用するか、VACUUM を呼ぶか。v0.8 では VACUUM 呼ばない (DB 小さい想定)、Open questions に記録のみ

迷ったら `result_037.md` の Open questions に書いて `status: blocked` で終了。

## 7. 補足

### 設計の意図

- 「内部最適化だけど **将来 scale するときの宿題を今潰す**」一手
- 既存 ユーザーが何もしなくても自動移行する gentle UX
- SQLite stdlib で依存 0、ポータブル

### 将来の拡張余地

- **spec_047 候補** (v0.9): parent text の versioning (history テーブル追加)
- **spec_048 候補** (v0.9): parent FTS5 全文検索 (sqlite の built-in)、BM25 を sqlite で完結
- **spec_049 候補** (v1.0): parent_storage を PostgreSQL backend へ拡張 (本格運用向け)
