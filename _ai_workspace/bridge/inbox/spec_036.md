# spec_036: Session Persistence (Memory / SQLite / Redis backends)

- **Author**: Cowork (中島)
- **Created**: 2026-05-14
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: v0.8 spec 1/5。spec_032 (Conversational RAG) の運用硬化

## 1. 目的

spec_032 で導入した `ConversationStore` は **in-memory + Lock** で実装した。v0.7 demo / 個人運用には十分だが、以下 2 つの致命傷がある:

1. **`uvicorn --workers > 1`** で session が worker 間で共有されず、再リクエストで別 worker に当たると session 喪失
2. **プロセス再起動 / クラッシュで全 session 消滅** — 24h TTL の意味を成さない

これを **抽象化 + 3 実装 (Memory / SQLite / Redis)** で解決し、default を **SqliteStore** (個人運用に最適) に切り替える。docker-compose で Redis を立てたい人は `STORAGE_BACKEND=redis` で切り替え可能。

```
[現状 v0.7]
ConversationStore (具象クラス) = in-memory dict + threading.Lock + TTL/LRU

[変更後 v0.8]
ConversationStore (Protocol) ←─ MemoryStore (現状の実装、後方互換)
                            ←─ SqliteStore (新規、default、~/.axis_chat.db)
                            ←─ RedisStore (新規、optional、docker-compose 連携)

設定: config.yml > chat.storage.backend = "sqlite" (default) | "memory" | "redis"
```

## 2. 制約

### 触ってよいファイル

- `backend/src/conversation.py` — `ConversationStore` を Protocol に変更、`MemoryStore` (既存ロジック移行)、`SqliteStore` (新規)、`RedisStore` (新規) を追加。factory function `make_conversation_store(config)` を export
- `backend/src/config.py` — `ChatConfig.storage` に `StorageConfig` (`backend: "memory"|"sqlite"|"redis"`, `sqlite_path: str`, `redis_url: str | None`) を追加
- `config.yml` — `chat.storage.*` セクション追加 (default `backend: "sqlite"`)
- `backend/src/api.py` — lifespan で `make_conversation_store(cfg.chat)` で初期化
- `backend/tests/test_conversation.py` — Memory/Sqlite/Redis 各実装の同じテストを `parametrize` で走らせる。Redis は `pytest.mark.skipif(no redis)` で optional skip
- `backend/tests/test_conversation_sqlite.py` — **新規** (SQLite 固有: ファイル永続化、再起動後の取得、concurrent write)
- `backend/tests/test_conversation_redis.py` — **新規** (Redis 固有: skipif で Redis 不在時 skip)
- `docs/adr/ADR-022-session-persistence.md` — **新規**
- `docs/configuration.md` — `chat.storage.*` 設定説明
- `docs/deployment.md` — single-worker 制約の解除手順、Redis docker-compose 追記
- `docker-compose.yml` — optional `redis` service (profile: `redis-backend`)
- `CHANGELOG.md` — Day 36 追記
- `pyproject.toml` — `[project.optional-dependencies]` の `redis` extras に `redis>=5.0` 追加 (default インストールには含めない)

### 触ってはいけないもの

- `backend/src/{search,rag,chunker,vector_store,loader,bm25_index,_decay,_citations,graph,question_rewriter,normalizer,integrity,marker,ingester}.py`
- `mcp_server/*` — MCP は `_session.py` でモジュール global store を持っているが、本 spec では触らない (in-memory のまま、別 process なので問題なし)
- `frontend/*` — UI 側は session_id を持つだけなので変更不要
- `_ai_workspace/`

### コーディングルール

- **Protocol を使う** (Python 3.10+ の `typing.Protocol`) で `ConversationStore` を契約化
- 既存 `ConversationStore` クラスは **`MemoryStore` にリネーム** + 後方互換 alias で `ConversationStore = MemoryStore` を `__init__.py` か `conversation.py` 末尾に export (既存呼び出しを壊さない)
- Sqlite は **stdlib の `sqlite3`** で実装 (新規依存追加なし)
- Redis は **optional dependency** (`pip install -e ".[redis]"` でのみインストール)
- SqliteStore は `~/.axis_chat.db` (default、`os.path.expanduser` で展開)。設定で上書き可
- すべての store は `threading.Lock` (Memory)、`sqlite3` の同期、`redis` SDK の atomic op で **スレッドセーフ**
- 既存テスト互換: `MemoryStore` を直接使うテストは無修正で通る

### デプロイ

- v0.8.0 リリースの硬化機能。tag は spec_036〜039 揃ったあと

## 3. やってほしいこと

### 3-1. Protocol 化 (`backend/src/conversation.py`)

#### 設計スケッチ

```python
"""Persistence-pluggable chat session storage.

Three implementations:
- MemoryStore: thread-safe in-memory dict (v0.7 default, kept for tests / fast path)
- SqliteStore: file-backed sqlite, default for v0.8+
- RedisStore: optional, requires `pip install -e ".[redis]"`
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Protocol, runtime_checkable
import json
import sqlite3
import uuid


@dataclass
class Message:
    role: str
    content: str
    sources: list[dict] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Session:
    session_id: str
    messages: list[Message] = field(default_factory=list)
    last_access: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class ConversationStore(Protocol):
    """Contract for all session storage backends."""

    def get_or_create(self, session_id: str | None = None) -> Session: ...
    def append(self, session_id: str, msg: Message) -> None: ...
    def get_history(self, session_id: str, *, last_n_turns: int = 6) -> list[Message]: ...
    def delete(self, session_id: str) -> bool: ...
    def __len__(self) -> int: ...
    def close(self) -> None: ...  # idempotent
```

### 3-2. MemoryStore (既存ロジック移行)

```python
class MemoryStore:
    """In-memory session storage with TTL + LRU.

    Equivalent to v0.7's ConversationStore. Kept for tests, fast local runs,
    and as a fallback when sqlite/redis are not available.
    """

    def __init__(self, *, max_sessions: int = 100, ttl_seconds: int = 86400):
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()
        self._max = max_sessions
        self._ttl = timedelta(seconds=ttl_seconds)

    def get_or_create(self, session_id=None): ...
    def append(self, session_id, msg): ...
    def get_history(self, session_id, *, last_n_turns=6): ...
    def delete(self, session_id): ...
    def __len__(self): return len(self._sessions)
    def close(self): pass  # no-op
```

(v0.7 の実装をそのまま `MemoryStore` にリネーム)

### 3-3. SqliteStore

```python
class SqliteStore:
    """File-backed session storage using stdlib sqlite3.

    Schema:
        sessions(session_id TEXT PK, last_access REAL)
        messages(id INTEGER PK AUTOINCREMENT, session_id TEXT FK, role TEXT,
                 content TEXT, sources_json TEXT, timestamp REAL)
        INDEX: messages(session_id, id)
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        last_access REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        sources_json TEXT,
        timestamp REAL NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
    """

    def __init__(
        self, db_path: str = "~/.axis_chat.db",
        *, max_sessions: int = 1000, ttl_seconds: int = 86400,
    ):
        import os
        self._db_path = os.path.expanduser(db_path)
        self._max = max_sessions
        self._ttl = ttl_seconds
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.executescript(self.SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")  # concurrent reads
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = Lock()
        self._evict_expired()

    def get_or_create(self, session_id=None):
        with self._lock:
            self._evict_expired()
            now = datetime.now(timezone.utc)
            if session_id:
                row = self._conn.execute(
                    "SELECT session_id FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row:
                    self._conn.execute(
                        "UPDATE sessions SET last_access = ? WHERE session_id = ?",
                        (now.timestamp(), session_id),
                    )
                    self._conn.commit()
                    return self._load_session(session_id, now)
            new_id = session_id or str(uuid.uuid4())
            self._conn.execute(
                "INSERT INTO sessions (session_id, last_access) VALUES (?, ?)",
                (new_id, now.timestamp()),
            )
            self._conn.commit()
            self._evict_lru()
            return Session(session_id=new_id, last_access=now)

    def append(self, session_id, msg):
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages (session_id, role, content, sources_json, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, msg.role, msg.content,
                 json.dumps(msg.sources, ensure_ascii=False), msg.timestamp.timestamp()),
            )
            self._conn.execute(
                "UPDATE sessions SET last_access = ? WHERE session_id = ?",
                (datetime.now(timezone.utc).timestamp(), session_id),
            )
            self._conn.commit()

    def get_history(self, session_id, *, last_n_turns=6):
        rows = self._conn.execute(
            "SELECT role, content, sources_json, timestamp FROM messages "
            "WHERE session_id = ? ORDER BY id ASC", (session_id,),
        ).fetchall()
        msgs = [self._row_to_msg(r) for r in rows]
        n_msgs = last_n_turns * 2
        return msgs[-n_msgs:] if n_msgs > 0 else msgs

    def delete(self, session_id):
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def __len__(self):
        return self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def _load_session(self, session_id, last_access): ...
    def _row_to_msg(self, row): ...
    def _evict_expired(self): ...
    def _evict_lru(self): ...
```

### 3-4. RedisStore

```python
class RedisStore:
    """Redis-backed session storage. Requires `pip install -e ".[redis]"`.

    Keys:
        axis:session:{session_id}:meta  → JSON {"last_access": float}
        axis:session:{session_id}:msgs  → LIST of JSON-serialized Message
    TTL applied per-key (auto-expire).
    """

    def __init__(self, url: str = "redis://localhost:6379/0", *, ttl_seconds: int = 86400):
        try:
            import redis
        except ImportError as e:
            raise RuntimeError(
                "RedisStore requires `pip install -e \".[redis]\"`"
            ) from e
        self._r = redis.Redis.from_url(url, decode_responses=True)
        self._ttl = ttl_seconds
        # Verify connection
        self._r.ping()

    def get_or_create(self, session_id=None):
        new_id = session_id or str(uuid.uuid4())
        meta_key = f"axis:session:{new_id}:meta"
        now = datetime.now(timezone.utc)
        existing = self._r.get(meta_key)
        if existing:
            self._r.set(meta_key, json.dumps({"last_access": now.timestamp()}), ex=self._ttl)
            self._r.expire(f"axis:session:{new_id}:msgs", self._ttl)
            return self._load_session(new_id)
        self._r.set(meta_key, json.dumps({"last_access": now.timestamp()}), ex=self._ttl)
        return Session(session_id=new_id, last_access=now)

    def append(self, session_id, msg):
        msgs_key = f"axis:session:{session_id}:msgs"
        meta_key = f"axis:session:{session_id}:meta"
        msg_json = json.dumps({
            "role": msg.role, "content": msg.content,
            "sources": msg.sources, "timestamp": msg.timestamp.timestamp(),
        }, ensure_ascii=False)
        pipe = self._r.pipeline()
        pipe.rpush(msgs_key, msg_json)
        pipe.expire(msgs_key, self._ttl)
        pipe.set(meta_key, json.dumps({"last_access": datetime.now(timezone.utc).timestamp()}),
                 ex=self._ttl)
        pipe.execute()

    def get_history(self, session_id, *, last_n_turns=6):
        msgs_key = f"axis:session:{session_id}:msgs"
        rows = self._r.lrange(msgs_key, 0, -1)
        msgs = [self._json_to_msg(r) for r in rows]
        n_msgs = last_n_turns * 2
        return msgs[-n_msgs:] if n_msgs > 0 else msgs

    def delete(self, session_id):
        meta_key = f"axis:session:{session_id}:meta"
        msgs_key = f"axis:session:{session_id}:msgs"
        deleted = self._r.delete(meta_key, msgs_key)
        return deleted > 0

    def __len__(self):
        return sum(1 for _ in self._r.scan_iter("axis:session:*:meta"))

    def close(self):
        if self._r:
            self._r.close()
            self._r = None

    def _load_session(self, session_id): ...
    def _json_to_msg(self, row): ...
```

### 3-5. Factory function

```python
def make_conversation_store(cfg) -> ConversationStore:
    """Construct the configured conversation store backend.

    Falls back to MemoryStore (with warning log) on misconfiguration.
    """
    backend = cfg.storage.backend.lower()
    if backend == "memory":
        return MemoryStore(max_sessions=cfg.max_sessions, ttl_seconds=cfg.ttl_seconds)
    if backend == "sqlite":
        return SqliteStore(
            db_path=cfg.storage.sqlite_path,
            max_sessions=cfg.max_sessions,
            ttl_seconds=cfg.ttl_seconds,
        )
    if backend == "redis":
        try:
            return RedisStore(url=cfg.storage.redis_url, ttl_seconds=cfg.ttl_seconds)
        except RuntimeError as e:
            _log.warning("RedisStore unavailable: %s; falling back to MemoryStore", e)
            return MemoryStore(max_sessions=cfg.max_sessions, ttl_seconds=cfg.ttl_seconds)
    _log.warning("unknown chat.storage.backend=%r; falling back to MemoryStore", backend)
    return MemoryStore(max_sessions=cfg.max_sessions, ttl_seconds=cfg.ttl_seconds)


# Backward compat alias for v0.7 imports
ConversationStore = MemoryStore  # type: ignore[misc, assignment]
```

(Protocol と alias の併存に注意: `isinstance(x, ConversationStore)` は Protocol だけ評価し、`runtime_checkable` で structural check)

### 3-6. config.py 拡張

```python
@dataclass(frozen=True)
class StorageConfig:
    backend: str = "sqlite"           # "memory" | "sqlite" | "redis"
    sqlite_path: str = "~/.axis_chat.db"
    redis_url: str = "redis://localhost:6379/0"


@dataclass(frozen=True)
class ChatConfig:
    enabled: bool = True
    max_history_turns: int = 6
    ttl_seconds: int = 86400
    max_sessions: int = 100
    rewriter: ChatRewriterConfig = field(default_factory=ChatRewriterConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)  # ← 新規
```

`load_app_config()` で `chat.storage.{backend, sqlite_path, redis_url}` を読み取り。

### 3-7. config.yml

```yaml
chat:
  enabled: true
  max_history_turns: 6
  ttl_seconds: 86400
  max_sessions: 100
  rewriter:
    enabled: true
    model: "gemini-1.5-flash"
  storage:
    backend: "sqlite"                       # memory | sqlite | redis
    sqlite_path: "~/.axis_chat.db"          # backend=sqlite 時のみ参照
    redis_url: "redis://localhost:6379/0"   # backend=redis 時のみ参照
```

### 3-8. api.py lifespan

```python
from backend.src.conversation import make_conversation_store, configure_default_store

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_app_config()
    store = make_conversation_store(cfg.chat)
    state["chat_store"] = store
    configure_default_store(store)
    _log.info("chat store: %s (backend=%s)", type(store).__name__, cfg.chat.storage.backend)
    yield
    store.close()
```

`configure_default_store()` は v0.7 で既存。`get_default_store()` は Protocol 経由で同じく動く。

### 3-9. pyproject.toml

```toml
[project.optional-dependencies]
eval = [
    # ... 既存 ...
]
redis = [
    "redis>=5.0,<6",
]
```

(default install には Redis 含めない、`pip install -e ".[redis]"` で追加)

### 3-10. docker-compose.yml

`profiles` で optional 起動:

```yaml
services:
  redis:
    image: redis:7-alpine
    profiles: ["redis-backend"]
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes

volumes:
  redis-data:
```

ユーザーは `docker compose --profile redis-backend up` で Redis 立てられる。

### 3-11. テスト

#### `backend/tests/test_conversation.py` (parametrize で 3 backend を並行 test)

```python
import pytest
from backend.src.conversation import MemoryStore, SqliteStore, RedisStore, Message

def memory_store(): return MemoryStore(max_sessions=100, ttl_seconds=86400)

@pytest.fixture
def store(request, tmp_path):
    backend = request.param
    if backend == "memory":
        s = MemoryStore(max_sessions=100, ttl_seconds=86400)
    elif backend == "sqlite":
        s = SqliteStore(db_path=str(tmp_path / "test.db"))
    elif backend == "redis":
        pytest.importorskip("redis")
        try:
            s = RedisStore(url="redis://localhost:6379/15", ttl_seconds=86400)
            s._r.flushdb()
        except Exception:
            pytest.skip("redis not available")
    yield s
    s.close()


@pytest.mark.parametrize("store", ["memory", "sqlite"], indirect=True)
class TestStoreCommon:
    def test_get_or_create_new(self, store): ...
    def test_get_or_create_existing(self, store): ...
    def test_append_and_history(self, store): ...
    def test_history_truncation(self, store): ...
    def test_delete(self, store): ...
    def test_len(self, store): ...
    # ... 既存 12 件を共通テストに昇格
```

#### `backend/tests/test_conversation_sqlite.py` (SqliteStore 固有、5 件)

1. `test_persists_across_instances` — store1 で append → store1.close() → store2 で同じ db_path → 履歴取得
2. `test_concurrent_writes` — 10 threads × 10 append、すべて保存 (sqlite3 + WAL)
3. `test_eviction_cleans_messages` — TTL evict 後 messages も削除 (CASCADE)
4. `test_db_file_creation` — db_path 不在から自動作成
5. `test_wal_mode_active` — `PRAGMA journal_mode` が `wal` を返す

#### `backend/tests/test_conversation_redis.py` (Redis、optional)

```python
import pytest

redis = pytest.importorskip("redis")

def _redis_available():
    try:
        r = redis.Redis(host="localhost", port=6379, db=15)
        r.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="Redis not running")


def test_redis_persists_across_instances(): ...
def test_redis_ttl_applied(): ...
def test_redis_pipeline_atomic(): ...
```

(CI で Redis 動かさない場合は all skip)

### 3-12. ADR-022

`docs/adr/ADR-022-session-persistence.md`:

- **Context**: v0.7 の in-memory store は worker 多重化 / 再起動で session 喪失
- **Decision**: Protocol + 3 backend (Memory / SQLite / Redis)、default SQLite
- **Alternatives**:
  - (a) ファイルベースの pickle dump → 却下 (concurrent write が破綻)
  - (b) JSON file with file lock → 却下 (read/write 全文、スケールしない)
  - (c) SQLite (採用、default) — stdlib のみ、WAL で concurrent OK
  - (d) Redis (optional) — Redis Standalone 想定、Cluster 対応は v0.9
  - (e) PostgreSQL → 却下 (個人運用に過剰)
- **Consequences**:
  - SQLite default で **再起動後も session 維持**
  - `pip install -e ".[redis]"` で Redis backend 利用可能
  - 既存 `MemoryStore` は維持 (テスト + 開発用 fast path)
  - `~/.axis_chat.db` は手動削除可、UI からのリセットは現状未対応 (v0.9 候補)

### 3-13. 動作確認

```bash
cd ~/projects/axis-knowledge-rag
git checkout -b feat/spec_036-session-persistence

# Unit + integration
ruff check .
python3 -m pytest -q backend/tests/test_conversation*.py -v

# 再起動シナリオ (SQLite)
echo '{"question": "Persistence test"}' | curl -s -X POST \
  http://localhost:8000/api/chat -H 'Content-Type: application/json' \
  -d @- | jq -r .session_id  # → e.g. "abc-123"
# uvicorn を再起動
pkill -f uvicorn; sleep 2
uvicorn backend.src.api:app --port 8000 &
sleep 3
curl -s http://localhost:8000/api/chat/abc-123 | jq '.messages | length'  # → 2 (永続化されている)

# Redis スモーク (optional)
docker compose --profile redis-backend up -d redis
pip install -e ".[redis]"
# config.yml で backend: "redis" に変更
uvicorn backend.src.api:app --port 8000 &
# 同じ手順で session 持続を確認
```

### 3-14. コミット粒度

1. `feat(conversation): Protocol-based ConversationStore + MemoryStore (rename of v0.7 impl)`
2. `feat(conversation): SqliteStore with WAL + foreign keys + auto-evict`
3. `feat(conversation): optional RedisStore with pipeline atomic ops`
4. `feat(config): chat.storage.{backend,sqlite_path,redis_url}`
5. `feat(api): lifespan uses make_conversation_store() factory`
6. `test: parametrize Memory/Sqlite for common store API + sqlite-specific 5 tests`
7. `test(redis): optional skipif redis-not-available`
8. `feat(deps): redis as optional [redis] extras + docker-compose redis profile`
9. `docs: ADR-022 + configuration / deployment + CHANGELOG Day 36`

`git push -u origin feat/spec_036-session-persistence`

### 3-15. result_036.md に書くこと

- 3 backend での同じテスト suite 結果
- SQLite: 再起動シナリオでの session 持続実測ログ
- Redis: docker compose 起動 + smoke 実測 (環境あれば、なければ pytest skip 数を報告)
- 後方互換: MemoryStore alias (`ConversationStore = MemoryStore`) が v0.7 のテストを破壊していないか
- パフォーマンス参考値: 10,000 messages append → get_history の SQLite vs Memory 時間比較

## 4. 成功条件

- [ ] `ConversationStore` Protocol + 3 実装 (Memory / Sqlite / Redis) 完成
- [ ] default = SqliteStore (`~/.axis_chat.db`)、`backend: "memory"` で v0.7 互換
- [ ] 再起動シナリオで session が SQLite に永続化される
- [ ] Redis は optional dependency、未インストール時は warning + Memory fallback
- [ ] 既存 291 tests 緑 + 新規 sqlite 5 + 共通 parametrize で追加カバレッジ
- [ ] ruff 緑、pyproject [redis] extras 動作
- [ ] ADR-022 / docs / CHANGELOG 更新
- [ ] git push 完了

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_036.md`

## 6. 質問があるとき

- **SQLite path のデフォルト**: `~/.axis_chat.db` を採用したが、project root の `data/chat.db` の方が「リポジトリで完結」する。CC 判断で OK (default 揃え)、ADR-022 に根拠
- **MemoryStore のリネーム影響**: `from backend.src.conversation import ConversationStore` で v0.7 を import している箇所が壊れる可能性。alias で `ConversationStore = MemoryStore` を export しているが、isinstance チェックがある場合は Protocol 経由に書き換える必要あり。grep で確認
- **Redis Cluster**: 本 spec は Standalone のみ。Cluster サポートは v0.9 (spec_044 候補) で `redis.RedisCluster` に切り替え可能なように設計しておく

迷ったら `result_036.md` の Open questions に書いて `status: blocked` で終了。

## 7. 補足

### 設計の意図

- ポートフォリオ的に「**production-ready にした**」を 1 行で説明できる材料
- SQLite stdlib は依存 0 で永続化を実現、デプロイの面倒さを最小化
- Redis は本気で多重 worker / マルチホストを使う時の選択肢として残す

### 将来の拡張余地

- **spec_044 候補** (v0.9): Redis Cluster + Sentinel 対応
- **spec_045 候補** (v0.9): UI から session list / reset / export 機能
- **spec_046 候補** (v0.9): session_id auth (Bearer token で session 所有者検証)
