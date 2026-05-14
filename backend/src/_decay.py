"""Time-weighted decay factor for search score adjustment."""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import Any

_log = logging.getLogger(__name__)


def decay_factor(
    updated_at: Any,
    *,
    now: datetime | None = None,
    half_life_days: float = 180.0,
) -> float:
    """Return decay coefficient in (0.0, 1.0].

    - decay = exp(-ln(2) * age_days / half_life_days)
    - At age=half_life_days: 0.5; at age=2*half_life_days: 0.25
    - updated_at = None / empty / unparseable → 1.0 (no penalty)
    """
    if not updated_at:
        return 1.0
    now = now or datetime.now(UTC)
    try:
        dt = _parse_datetime(updated_at)
    except Exception:  # noqa: BLE001
        _log.warning("time_decay: failed to parse updated_at=%r, using 1.0", updated_at)
        return 1.0
    age_seconds = (now - dt).total_seconds()
    if age_seconds < 0:
        return 1.0  # future-dated doc → no penalty
    age_days = age_seconds / 86400.0
    return math.exp(-math.log(2) * age_days / half_life_days)


def blend_score(base_score: float, decay: float, weight: float) -> float:
    """Blend base score with decay factor.

    final = base * (1 - w) + (base * decay) * w
          = base * (1 - w * (1 - decay))
    """
    w = max(0.0, min(1.0, weight))
    return base_score * (1.0 - w * (1.0 - decay))


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    raise TypeError(f"unsupported updated_at type: {type(value).__name__}")
