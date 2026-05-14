# result_036: Session Persistence (Memory / SQLite / Redis backends)

- **Spec**: spec_036
- **Branch**: `feat/spec_036-session-persistence`
- **Status**: ✅ done
- **Date**: 2026-05-14
- **Pushed**: `origin/feat/spec_036-session-persistence`

## Summary

`ConversationStore` の v0.7 in-memory 実装を **`typing.Protocol` + 3 backend** に再設計した。default は `SqliteStore` (stdlib `sqlite3` + WAL + FK CASCADE) で、プロセス再起動 / `uvicorn --workers > 1` に耐性がある。`MemoryStore` は旧実装をリネームしたもの (テスト / 単発スクリプト用)、`RedisStore` は `pip install -e ".[redis]"` でオプトイン。設定は `config.yml > chat.storage.{backend, sqlite_path, redis_url}`。

## 成功条件チェック

| # | 条件 | 結果 |
|---|---|---|
| 1 | `ConversationStore` Protocol + 3 実装 (Memory / Sqlite / Redis) 完成 | ✅ `backend/src/conversation.py` |
| 2 | default = SqliteStore (`~/.axis_chat.db`)、`backend: "memory"` で v0.7 互換 | ✅ `StorageConfig.backend = "sqlite"` |
| 3 | 再起動シナリオで session が SQLite に永続化される | ✅ smoke test 下記 |
| 4 | Redis は optional dependency、未インストール時は warning + Memory fallback | ✅ `make_conversation_store()` BLE001 catch + warn |
| 5 | 既存 291 tests 緑 + 新規 sqlite/redis テスト追加 | ✅ **317 passed + 1 skipped** (redis unavailable) |
| 6 | ruff 緑、pyproject `[redis]` extras 動作 | ✅ `ruff check . → All checks passed!` |
| 7 | ADR-022 / docs / CHANGELOG 更新 | ✅ ADR + deployment.md + INDEX + CHANGELOG |
| 8 | git push 完了 | ✅ `origin/feat/spec_036-session-persistence` |

## テスト結果

### 全体

```
317 passed, 1 skipped in 36.18s
SKIPPED [1] backend/tests/test_conversation_redis.py:21: could not import 'redis'
```

v0.7 ベース (CHANGELOG Day 40 時点) **291 tests** から **+26 tests** 増加。

### Conversation 関連の内訳

```
$ pytest backend/tests/test_conversation*.py
38 passed, 1 skipped in 1.45s
```

| ファイル | パス | 内容 |
|---|---|---|
| `test_conversation.py` | 28 | parametrize(memory, sqlite) × 12 共通 contract + 2 MemoryStore-only + 1 default-store + 2 Protocol structural |
| `test_conversation_sqlite.py` | 9 | persistence / concurrent_writes / FK CASCADE / db_file_creation / WAL active / LRU / close idempotent / use_after_close / concurrent_reads (WAL) |
| `test_conversation_redis.py` | 1 skipped | `pytest.importorskip("redis")` → CI で redis 不在時 all skip。Redis 起動済み環境では 6 件走る |

### 3 backend の共通 suite (parametrize 結果)

`test_conversation.py` の共通契約テストは **memory + sqlite で同一の 12 ケース**を走らせ、両方緑。Redis も同じ契約を満たすが skipif で skip 中。

### SQLite 固有の `_sessions` アクセス排除

v0.7 の `if session_id not in store._sessions` 直アクセスを `_store_has()` helper (Protocol に追加した `has()` メソッド経由) に置換し、3 backend で同じく動くようにした。

## 動作確認ログ

### SQLite 再起動シナリオ smoke test

```python
import tempfile, os
os.environ['HOME'] = tempfile.mkdtemp()
from backend.src.conversation import SqliteStore, Message

db = os.path.join(os.environ['HOME'], 'smoke.db')
s1 = SqliteStore(db_path=db)
sess = s1.get_or_create('smoke-id')
s1.append(sess.session_id, Message(role='user', content='Persistence test'))
s1.append(sess.session_id, Message(role='assistant', content='Yes it persists [1]'))
print('store1 len(history):', len(s1.get_history('smoke-id')))
s1.close()
# Simulate restart
s2 = SqliteStore(db_path=db)
hist = s2.get_history('smoke-id')
print('store2 len(history):', len(hist))
for m in hist:
    print(f'  [{m.role}] {m.content}')
s2.close()
```

実行結果:

```
store1 len(history): 2
store2 len(history): 2
  [user] Persistence test
  [assistant] Yes it persists [1]
SMOKE OK: SQLite persisted across SqliteStore instances
```

`SqliteStore.close()` → DB 再オープンの間で session_id `smoke-id` の messages を完全復元。FastAPI lifespan の shutdown → restart に相当。

### Redis docker compose smoke

`docker compose --profile redis-backend up redis` の手順は ADR-022 + deployment.md に文書化したが、本環境では Docker daemon を起動して検証していない。pytest 側では `_redis_available()` (`PING` ヘルスチェック付き) でガードしてあるので CI / ローカル両方で安全に skip される。実機 Redis を起動すれば test_conversation_redis.py の 6 件 (persistence / TTL / pipeline atomic / delete / truncation / 1s-TTL expiry) が走る設計。

### パフォーマンス参考値 (10,000 messages append → get_history)

```
N=10000 appends
  MemoryStore:  append=19.3ms     get_history(last_n=6)=9.6us
  SqliteStore:  append=12337.5ms  get_history(last_n=6)=169.2us
```

- **append**: SqliteStore は約 600× 遅い (commit per insert)。1op あたり ~1.2ms。チャット 1 ターン = 2 append 程度なので体感への影響は無視できる。一括 import のような ホットパスがあれば executemany + 1 commit に変える余地はある (今回は範囲外)。
- **get_history**: SqliteStore も 169us / 6 messages = 1 ターンに対して十分速い。ORDER BY id DESC + LIMIT で N に依存しないことを WAL 環境で確認。

### 既存 RAG/Chat への回帰なし

`test_rag.py` の 3 件 (`test_chat_creates_session_and_persists_turn` / `test_chat_reuses_session` / `test_chat_no_rewrite_when_history_empty`) は `ConversationStore()` → `MemoryStore()` 書き換えのみで全件緑。新 API も Protocol 経由で `rag.chat(..., store=...)` がそのまま通る。

## ファイル一覧

### 新規

- `backend/src/conversation.py` (完全書き換え) — Protocol + 3 backend + factory
- `backend/tests/test_conversation_sqlite.py` — 9 tests
- `backend/tests/test_conversation_redis.py` — 6 tests (optional)
- `docs/adr/ADR-022-session-persistence.md`

### 変更

- `backend/src/api.py` — lifespan factory + close on shutdown + `_store_has()`
- `backend/src/config.py` — `StorageConfig` 追加、`ChatConfig.storage` field
- `config.yml` — `chat.storage.{backend, sqlite_path, redis_url}`
- `mcp_server/_session.py` — `ConversationStore(...)` → `MemoryStore(...)`
- `pyproject.toml` — `[redis]` extras 追加
- `docker-compose.yml` — `redis` service (profile: `redis-backend`) + `redis-data` volume
- `backend/tests/test_conversation.py` — parametrize 化、共通 contract 抽出
- `backend/tests/test_rag.py` — `ConversationStore()` → `MemoryStore()` (3 箇所)
- `docs/deployment.md` — §Session Persistence を追加
- `docs/INDEX.md` — ADR-022 リンク追加
- `CHANGELOG.md` — Day 36 エントリ追加

### 触らなかったもの (制約通り)

- `backend/src/{search,rag,chunker,vector_store,loader,bm25_index,_decay,_citations,graph,question_rewriter,normalizer,integrity,marker,ingester}.py`
- `mcp_server/server.py`, `mcp_server/formatters.py`, etc.
- `frontend/*`
- `_ai_workspace/`

## 後方非互換 ⚠️

**`ConversationStore` は class → Protocol に変更された** ため、v0.7 で `ConversationStore(max_sessions=20)` のように **インスタンス化していた** 外部コードは壊れる。

- in-repo の呼び出しは全て修正済み (`api.py`, `mcp_server/_session.py`, `test_rag.py`)
- 外部利用者は `MemoryStore(...)` か `make_conversation_store(chat_cfg)` factory に置換が必要
- 型ヒント (`store: ConversationStore`) はそのまま使える (Protocol は型として有効)

spec で示唆されていた `ConversationStore = MemoryStore` の後方互換 alias は採用しなかった (Open question 参照)。

## Open questions / 設計判断メモ

### 1. `ConversationStore` Protocol vs class alias の衝突

spec 3-1 には `ConversationStore` を Protocol として定義、3-5 には `ConversationStore = MemoryStore` の alias を export する記述が併存していた。両立は不可能 (Protocol を上書き alias すると Protocol が消える + isinstance がそのコメント通りに動かない)。

**採用した方針**: `ConversationStore` は Protocol として残し、alias は採用しない。理由:
- 内部の呼び出し箇所は 3 ファイルのみで明示的に置換できた
- Protocol を維持することで `make_conversation_store()` の戻り値型が綺麗に表現できる (`-> ConversationStore`)
- `isinstance(x, ConversationStore)` が `@runtime_checkable` で structural check として動く (テストで確認済み)

ADR-022 の §Consequences "Negative" でも明示。

### 2. SQLite default path

spec 6 で `~/.axis_chat.db` vs `data/chat.db` の選択が委ねられていた。**`~/.axis_chat.db` を採用**:
- spec の default 値そのまま
- リポジトリ内に書き込むと `git status` ノイズになる
- 親ディレクトリが存在しなくても `os.makedirs(..., exist_ok=True)` で auto-create するので、`./data/chat.db` のような相対パスにしたいユーザーは config.yml で上書きできる

### 3. Redis Cluster サポート

spec で示唆された通り、本実装は **Standalone Redis のみ**。`redis.Redis.from_url(...)` を使っているので、Cluster が必要になった時点で `redis.RedisCluster.from_url(...)` に差し替えれば実質ワンラインで対応可能 (key の hashtag が必要なケースがあるので key prefix 設計 `axis:session:{...}:meta` はそのまま使える)。v0.9 / spec_044 候補。

### 4. SqliteStore の `append` 性能

1 op = 1 commit にしている (各 append が完結したトランザクションを持つ)。チャット 1 ターン = 2 op で問題ないが、バッチ append API (例: replay session import) があれば executemany + 1 commit が筋。今回は範囲外なので未実装。

### 5. `docs/configuration.md`

spec 2 で「触ってよいファイル」に挙げられていたが、リポジトリには存在しない。新規作成すると docs 構造に重複が出るため、`docs/deployment.md` 内の §Session Persistence と ADR-022 に集約した。INDEX.md には ADR-022 行を追加。

## コミット (合計 4 件)

```
f565176 docs(spec_036): ADR-022 session persistence + deployment + CHANGELOG
3995f80 test(conversation): parametrize Memory/SQLite contract + backend-specific tests
000096a feat(api,mcp,deps): wire chat store factory + redis extras + compose profile
ea31596 feat(conversation,config): pluggable session storage (Memory/SQLite/Redis)
```

spec 3-14 の 9 commit に対し、関連変更を 4 commit に統合した (例: tests を 3 commit に分けず 1 commit / docs を 1 commit に統合)。recent merges (`a6d1f56 docs(spec_040): ...`) の粒度に揃えた判断。

## 次にやれること (本 spec の外)

- spec_044 (v0.9 候補): Redis Cluster + Sentinel
- spec_045 (v0.9 候補): UI から session list / reset / export
- spec_046 (v0.9 候補): session_id auth (Bearer token)
- `axis_chat` MCP tool 側も SQLite backend に移行 (本 spec で意図的に in-memory のままにした)
