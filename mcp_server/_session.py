"""Module-scoped conversation store for the MCP server process.

The MCP stdio process is long-lived (kept alive by the client until the
client itself exits), so a process-global ``MemoryStore`` is the right
place for ``axis_chat`` to keep history. The cap is intentionally small
(20 sessions / 1h TTL) — Claude Desktop typically only juggles a handful
of concurrent dialogs. We deliberately stick with in-memory here even
after spec_036 — the MCP process owns its own session lifecycle and has
no requirement to share state with the FastAPI backend.
"""

from __future__ import annotations

from backend.src.conversation import MemoryStore

mcp_chat_store = MemoryStore(max_sessions=20, ttl_seconds=3600)
