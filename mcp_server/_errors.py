"""Centralized error handling for MCP tools.

Goal: never leak internal details (file paths, API error bodies, Pydantic
input values) to MCP clients. Errors are logged server-side with a
correlation id, and clients get a generic message referencing the id.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def new_correlation_id() -> str:
    """Generate a short correlation id for log<->client tracing."""
    return uuid.uuid4().hex[:5]


def make_error_response(tool_name: str, exc: BaseException, *, corr_id: str | None = None) -> str:
    """Log full exception and return a sanitized message for the client.

    Args:
        tool_name: For log context (e.g., 'axis_search').
        exc: The exception caught. Logged with traceback, NOT included in return.
        corr_id: Optional pre-generated correlation id. Auto-generated if None.

    Returns:
        A short, client-facing string that does not contain exception details.
    """
    cid = corr_id or new_correlation_id()
    logger.exception(
        "[corr=%s] %s failed", cid, tool_name,
        extra={"corr_id": cid, "tool_name": tool_name},
    )
    return f"Error [{cid}]: {tool_name} failed. Check server logs (correlation id: {cid})."
