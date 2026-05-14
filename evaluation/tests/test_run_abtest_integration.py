"""spec_042: verify EVAL_OVERRIDE_FLAG actually reaches load_app_config().

These are pure-config integration tests — no RAGAS, no LLM, no I/O beyond
the YAML file. They lock in the wiring that spec_038 forgot to land and
spec_041 review flagged HIGH.
"""

from __future__ import annotations

import logging

from backend.src.config import load_app_config


def test_override_changes_time_decay_enabled(monkeypatch):
    monkeypatch.setenv("EVAL_OVERRIDE_FLAG", "retrieval.time_decay.enabled=true")
    cfg = load_app_config()
    assert cfg.retrieval.time_decay.enabled is True


def test_override_changes_chat_enabled(monkeypatch):
    monkeypatch.setenv("EVAL_OVERRIDE_FLAG", "chat.enabled=false")
    cfg = load_app_config()
    assert cfg.chat.enabled is False


def test_override_multiple_keys(monkeypatch):
    monkeypatch.setenv(
        "EVAL_OVERRIDE_FLAG",
        "retrieval.time_decay.enabled=true;chat.enabled=false",
    )
    cfg = load_app_config()
    assert cfg.retrieval.time_decay.enabled is True
    assert cfg.chat.enabled is False


def test_override_unknown_key_is_silent_warning(monkeypatch, caplog):
    monkeypatch.setenv("EVAL_OVERRIDE_FLAG", "nonexistent.path=true")
    with caplog.at_level(logging.WARNING, logger="backend.src.config"):
        load_app_config()
    assert any("unknown key" in r.getMessage() for r in caplog.records)


def test_override_no_env_no_change(monkeypatch):
    monkeypatch.delenv("EVAL_OVERRIDE_FLAG", raising=False)
    cfg = load_app_config()
    # spec_035 default
    assert cfg.retrieval.time_decay.enabled is False


def test_override_type_coercion(monkeypatch):
    monkeypatch.setenv(
        "EVAL_OVERRIDE_FLAG",
        "retrieval.time_decay.weight=0.5;graph.default_hop=2",
    )
    cfg = load_app_config()
    assert cfg.retrieval.time_decay.weight == 0.5
    assert cfg.graph.default_hop == 2
