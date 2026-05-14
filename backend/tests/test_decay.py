"""Tests for backend.src._decay — pure time-decay functions."""

import logging
from datetime import UTC, datetime, timedelta

from backend.src._decay import blend_score, decay_factor


def test_no_updated_at_returns_one():
    assert decay_factor(None) == 1.0
    assert decay_factor("") == 1.0


def test_today_returns_one():
    now = datetime(2026, 5, 14, tzinfo=UTC)
    assert decay_factor(now, now=now) == 1.0


def test_half_life():
    now = datetime(2026, 5, 14, tzinfo=UTC)
    past = now - timedelta(days=180)
    d = decay_factor(past, now=now, half_life_days=180)
    assert abs(d - 0.5) < 1e-6


def test_double_half_life():
    now = datetime(2026, 5, 14, tzinfo=UTC)
    past = now - timedelta(days=360)
    d = decay_factor(past, now=now, half_life_days=180)
    assert abs(d - 0.25) < 1e-6


def test_future_dated_no_penalty():
    now = datetime(2026, 5, 14, tzinfo=UTC)
    future = now + timedelta(days=30)
    assert decay_factor(future, now=now) == 1.0


def test_iso_string_with_z():
    now = datetime(2026, 5, 14, tzinfo=UTC)
    d = decay_factor("2025-11-15T00:00:00Z", now=now, half_life_days=180)
    assert 0.4 < d < 0.6


def test_iso_string_date_only():
    now = datetime(2026, 5, 14, tzinfo=UTC)
    # 2026-05-14 minus 180 days = 2025-11-15
    d = decay_factor("2025-11-15", now=now, half_life_days=180)
    assert 0.4 < d < 0.6


def test_invalid_string_logs_and_returns_one(caplog):
    with caplog.at_level(logging.WARNING, logger="backend.src._decay"):
        result = decay_factor("not-a-date")
    assert result == 1.0
    assert any("failed to parse" in r.message for r in caplog.records)


def test_blend_weight_zero_is_passthrough():
    assert blend_score(1.0, 0.5, weight=0.0) == 1.0


def test_blend_weight_one_full_decay():
    assert blend_score(1.0, 0.5, weight=1.0) == 0.5


def test_blend_weight_half():
    # base=1.0, decay=0.5, w=0.5 → 1.0 * (1 - 0.5*0.5) = 0.75
    assert abs(blend_score(1.0, 0.5, weight=0.5) - 0.75) < 1e-6


def test_blend_clamps_weight_high():
    assert blend_score(1.0, 0.5, weight=2.0) == blend_score(1.0, 0.5, weight=1.0)


def test_blend_clamps_weight_negative():
    assert blend_score(1.0, 0.5, weight=-1.0) == 1.0


def test_decay_factor_preserves_recent_over_old():
    now = datetime(2026, 5, 14, tzinfo=UTC)
    recent = now - timedelta(days=10)
    old = now - timedelta(days=350)
    d_recent = decay_factor(recent, now=now, half_life_days=180)
    d_old = decay_factor(old, now=now, half_life_days=180)
    assert d_recent > d_old


def test_decay_factor_never_exceeds_one():
    now = datetime(2026, 5, 14, tzinfo=UTC)
    for days in [0, 1, 10, 100, 500, 1000]:
        past = now - timedelta(days=days)
        assert decay_factor(past, now=now) <= 1.0
