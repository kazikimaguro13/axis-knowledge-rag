# ADR-022: Pluggable Session Persistence (Memory / SQLite / Redis)

- **Status**: Accepted
- **Date**: 2026-05-14
- **Spec**: spec_036
- **Related**: ADR-018 (Conversational RAG), spec_032 (in-memory store)

## Context

spec_032 introduced `ConversationStore` as an in-memory `dict` guarded
by `threading.Lock`. That was deliberately the cheapest thing that could
possibly work — single uvicorn worker, no persistence — and shipped in
v0.7 with a clear note that durability was a v0.8 concern.

The shortcuts are now visible in production:

1. **Worker affinity**. With `uvicorn --workers > 1` a session is bound
   to whichever Python process happened to handle the first request.
   Subsequent requests for the same `session_id` land on a different
   worker about 50 % of the time and see an empty history.
2. **No durability**. A process restart (deploy, crash, OOM kill) drops
   every conversation. The 24-hour TTL was therefore a lie: the actual
   upper bound on session lifetime was *uptime*.
3. **Single-host ceiling**. Even fixing (1) with sticky cookies leaves
   us unable to scale horizontally across nodes — every machine has its
   own private dict.

We want session continuity to keep working as a polished feature even
when the deployment story grows beyond "one uvicorn worker on a laptop".

## Decision

Introduce a `ConversationStore` `typing.Protocol` and three concrete
backends:

| Backend       | When to use                                  | Survives restart | Multi-worker safe | Extra deps |
|---------------|----------------------------------------------|------------------|-------------------|------------|
| `MemoryStore` | Tests, single-shot scripts, fallback         | No               | No                | None       |
| `SqliteStore` | Default. Personal / single-host deployments  | Yes              | Yes (WAL)         | None (stdlib `sqlite3`) |
| `RedisStore`  | Multi-host / multi-worker production         | Yes              | Yes (atomic ops)  | `redis>=5,<6` (extras) |

A factory `make_conversation_store(chat_cfg)` reads
`chat.storage.backend` (default `"sqlite"`) and constructs the right one.
Misconfiguration (unknown backend, redis not installed, redis unreachable
on boot) logs a warning and falls back to `MemoryStore` so the API still
starts.

### Default = SQLite (file-backed)

- Zero new runtime dependencies — `sqlite3` is in the stdlib.
- WAL journal mode (`PRAGMA journal_mode=WAL`) gives us concurrent
  readers while writers hold the lock, which matches FastAPI's
  threadpool dispatch model.
- `FOREIGN KEY (...) ON DELETE CASCADE` ensures evicting a session row
  takes its messages with it — no orphaned rows on TTL eviction.
- `~/.axis_chat.db` is the default path so the file lives outside the
  repo by default (no risk of accidental commit). Override via
  `chat.storage.sqlite_path`.

### Redis is optional

- `pip install -e ".[redis]"` adds `redis>=5.0,<6`.
- Backed by one `meta` key + one `msgs` LIST per session, with `EX`
  TTL applied on every write so an active conversation never expires.
- LRU/eviction is delegated to Redis' own `maxmemory-policy allkeys-lru`
  — clients that care about a hard cap configure it there.
- The docker-compose `redis` service lives behind a profile
  (`docker compose --profile redis-backend up redis`) so it doesn't
  start by default.

## Alternatives considered

### (a) File-based pickle dump

Snapshot the in-memory dict to disk every N seconds. Rejected: any
concurrent write loses data; recovery on crash returns to the last
snapshot, not the last accepted request.

### (b) Single JSON file with file lock

Same idea, plaintext. Rejected: every read/write rewrites the whole
file, scales O(total sessions × messages). Locking is platform-specific
and notoriously fragile on Windows / WSL bind mounts.

### (c) SQLite (**adopted as default**)

Stdlib, file-backed, ACID, has a 30-year track record of "the obvious
embedded DB". WAL handles our concurrency requirements. The only real
downside is single-host: WAL doesn't work across NFS, and a writer must
live on the same machine as the file. For personal-RAG use cases that's
fine; multi-host workloads use Redis.

### (d) Redis (**adopted as optional**)

The standard answer for production session storage. Adds a runtime
dependency and a service to operate, which is why it's opt-in. Standalone
Redis only for now; Cluster / Sentinel support is tracked as a v0.9
candidate (spec_044) — `redis.RedisCluster` is mostly drop-in if we ever
need to swap.

### (e) PostgreSQL / MySQL

Overkill for a tool whose primary persona is "developer with a laptop".
We'd be the first OSS RAG to require an RDBMS just for chat history. If
a deployer wants Postgres, RedisStore + a Redis-to-Postgres archival
job is more flexible than baking it in.

## Consequences

### Positive

- **Default behaviour is now durable**: sessions survive `pkill -HUP`,
  systemd restarts, crashes. The 24-hour TTL means what it says.
- **uvicorn worker count is no longer a footgun**: the SQLite default
  is workers-safe (each worker opens its own connection to the shared
  file in WAL mode).
- **Deployments that want true horizontal scale have a documented
  path** (Redis backend) instead of being stuck.
- **`MemoryStore` is still there** for tests / fast local runs — they
  shouldn't touch the filesystem.

### Negative / accepted trade-offs

- **Existing v0.7 callers that did `ConversationStore(max_sessions=...)`
  break** at runtime: `ConversationStore` is now a Protocol, not a
  class. We chose the breaking-rename path over a confusing alias
  because the only in-repo callers were two internal files
  (`api.py`, `mcp_server/_session.py`); external consumers should
  switch to `MemoryStore` or the factory. Documented in CHANGELOG.
- **`~/.axis_chat.db` accumulates over time** if `TTL` isn't reached.
  Acceptable: the file is small (~few KB per session) and the user can
  `rm` it freely. A UI "reset all sessions" affordance is tracked as a
  v0.9 candidate (spec_045).
- **Redis is single-node** in this spec. A Sentinel/Cluster client is
  not a code-shape change, just a swap in `RedisStore.__init__`.

### Operational notes

- **Single-worker users**: behaviour is unchanged from v0.7 except
  sessions now survive restarts. Nothing else to do.
- **Multi-worker users**: bump `uvicorn --workers 4` freely; SQLite
  WAL handles it. Use Redis if you need cross-host scale.
- **Privacy-conscious users**: `chat.storage.backend: "memory"`
  restores the v0.7 zero-disk behaviour.
