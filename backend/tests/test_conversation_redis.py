"""RedisStore tests (spec_036).

Optional — the whole module is skipped when either:

- The ``redis`` Python client isn't installed (i.e. the user didn't run
  ``pip install -e ".[redis]"``), or
- No Redis server is reachable at ``localhost:6379``.

This lets CI skip cleanly without a Redis service while still exercising
the path locally / in a docker-compose env. Tests use logical DB 15 and
flush it on setup to avoid clobbering anything real.
"""

from __future__ import annotations

import contextlib
import time

import pytest

redis = pytest.importorskip("redis")  # noqa: E402

from backend.src.conversation import Message  # noqa: E402


def _redis_available() -> bool:
    try:
        r = redis.Redis(host="localhost", port=6379, db=15, socket_connect_timeout=1)
        r.ping()
        r.close()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(), reason="Redis server not reachable on localhost:6379"
)


@pytest.fixture
def store():
    from backend.src.conversation import RedisStore

    s = RedisStore(url="redis://localhost:6379/15", ttl_seconds=86400)
    s._r.flushdb()  # noqa: SLF001
    try:
        yield s
    finally:
        with contextlib.suppress(Exception):
            s._r.flushdb()  # noqa: SLF001
        s.close()


def test_redis_persists_across_instances() -> None:
    """A second RedisStore instance pointing at the same URL sees prior writes."""
    from backend.src.conversation import RedisStore

    s1 = RedisStore(url="redis://localhost:6379/15", ttl_seconds=86400)
    s1._r.flushdb()  # noqa: SLF001
    sid = s1.get_or_create("rkey").session_id
    s1.append(sid, Message(role="user", content="hi"))
    s1.append(sid, Message(role="assistant", content="hello"))
    s1.close()

    s2 = RedisStore(url="redis://localhost:6379/15", ttl_seconds=86400)
    try:
        hist = s2.get_history("rkey", last_n_turns=6)
        assert len(hist) == 2
        assert hist[0].content == "hi"
        assert hist[1].role == "assistant"
    finally:
        s2._r.flushdb()  # noqa: SLF001
        s2.close()


def test_redis_ttl_applied(store) -> None:
    """Both meta and msgs keys have a positive TTL set on append."""
    sid = store.get_or_create("ttlcheck").session_id
    store.append(sid, Message(role="user", content="hi"))
    meta_ttl = store._r.ttl(store._meta_key(sid))  # noqa: SLF001
    msgs_ttl = store._r.ttl(store._msgs_key(sid))  # noqa: SLF001
    assert 0 < meta_ttl <= 86400
    assert 0 < msgs_ttl <= 86400


def test_redis_pipeline_atomic(store) -> None:
    """Append uses a pipeline so msg + meta updates land together."""
    sid = store.get_or_create("atomic").session_id
    store.append(sid, Message(role="user", content="one"))
    store.append(sid, Message(role="assistant", content="two"))
    # Verify both list length and meta JSON are consistent post-append.
    assert store._r.llen(store._msgs_key(sid)) == 2  # noqa: SLF001
    assert store._r.get(store._meta_key(sid)) is not None  # noqa: SLF001
    hist = store.get_history(sid)
    assert [m.content for m in hist] == ["one", "two"]


def test_redis_delete(store) -> None:
    sid = store.get_or_create("d").session_id
    store.append(sid, Message(role="user", content="x"))
    assert store.delete(sid) is True
    assert store.delete(sid) is False
    assert store.get_history(sid) == []


def test_redis_history_truncation(store) -> None:
    sid = store.get_or_create("trunc").session_id
    for i in range(6):
        role = "user" if i % 2 == 0 else "assistant"
        store.append(sid, Message(role=role, content=f"msg{i}"))
    hist = store.get_history(sid, last_n_turns=2)
    assert len(hist) == 4
    assert hist[0].content == "msg2"
    assert hist[-1].content == "msg5"


def test_redis_short_ttl_actually_expires() -> None:
    """A 1-second TTL means an unrefreshed session is gone after ~1s."""
    from backend.src.conversation import RedisStore

    s = RedisStore(url="redis://localhost:6379/15", ttl_seconds=1)
    try:
        s._r.flushdb()  # noqa: SLF001
        sid = s.get_or_create("short").session_id
        s.append(sid, Message(role="user", content="ephemeral"))
        time.sleep(1.5)
        assert s.has(sid) is False
        assert s.get_history(sid) == []
    finally:
        s._r.flushdb()  # noqa: SLF001
        s.close()
