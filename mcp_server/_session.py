"""Module-scoped conversation store for the MCP server process.

The MCP stdio process is long-lived (kept alive by the client until the
client itself exits), so a process-global ``ConversationStore`` is the
right place for ``axis_chat`` to keep history. The cap is intentionally
small (20 sessions / 1h TTL) — Claude Desktop typically only juggles a
handful of concurrent dialogs.
"""

from __future__ import annotations

from backend.src.conversation import ConversationStore

# Tunable from the MCP module entry-point if needed, but the defaults are
# small on purpose: an MCP process should not act as a multi-tenant chat
# server. v0.7 reuses the FastAPI store class as-is.
mcp_chat_store = ConversationStore(max_sessions=20, ttl_seconds=3600)
