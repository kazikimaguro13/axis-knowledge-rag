"""Tests for the Gemini Flash question rewriter (spec_032).

We don't hit the real Gemini API — instead we patch
``google.generativeai.GenerativeModel`` so the test suite runs offline.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.src import question_rewriter
from backend.src.conversation import Message
from backend.src.question_rewriter import rewrite_question


def _hist(*pairs: tuple[str, str]) -> list[Message]:
    return [Message(role=role, content=content) for role, content in pairs]


def test_empty_history_returns_original() -> None:
    assert rewrite_question("RAG とは?", []) == "RAG とは?"


def test_disabled_returns_original() -> None:
    hist = _hist(("user", "LangChain とは?"), ("assistant", "..."))
    assert rewrite_question("それの利点は?", hist, enabled=False) == "それの利点は?"


def test_no_api_key_returns_original(monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings is frozen — replace the module-level singleton.
    monkeypatch.setattr(
        question_rewriter, "settings", SimpleNamespace(gemini_api_key=None)
    )
    hist = _hist(("user", "LangChain"), ("assistant", "a"))
    assert rewrite_question("それの利点は?", hist) == "それの利点は?"


class _FakeModel:
    def __init__(self, *, text: str = "", raise_exc: BaseException | None = None) -> None:
        self.text = text
        self.raise_exc = raise_exc
        self.last_prompt: str | None = None

    def generate_content(self, prompt: str, **_: Any) -> Any:
        self.last_prompt = prompt
        if self.raise_exc is not None:
            raise self.raise_exc
        return SimpleNamespace(text=self.text)


def _install_fake(
    monkeypatch: pytest.MonkeyPatch, fake: _FakeModel
) -> None:
    monkeypatch.setattr(
        question_rewriter, "settings", SimpleNamespace(gemini_api_key="fake-key")
    )
    fake_genai = SimpleNamespace(
        configure=lambda **_: None,
        GenerativeModel=lambda _model: fake,
    )
    import sys

    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)


def test_rewrites_with_pronoun(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeModel(text="LangChain の利点は?")
    _install_fake(monkeypatch, fake)
    hist = _hist(
        ("user", "LangChain について教えて"),
        ("assistant", "LangChain は LLM アプリ用のフレームワークです。"),
    )
    out = rewrite_question("それの利点は?", hist)
    assert "LangChain" in out
    assert fake.last_prompt is not None
    # The history block must include both turns
    assert "LangChain について教えて" in fake.last_prompt


def test_api_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeModel(raise_exc=RuntimeError("quota exhausted"))
    _install_fake(monkeypatch, fake)
    hist = _hist(("user", "x"), ("assistant", "y"))
    assert rewrite_question("それは?", hist) == "それは?"


def test_max_length_cap_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeModel(text="x" * 600)
    _install_fake(monkeypatch, fake)
    hist = _hist(("user", "a"), ("assistant", "b"))
    assert rewrite_question("orig", hist) == "orig"


def test_empty_response_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeModel(text="   ")
    _install_fake(monkeypatch, fake)
    hist = _hist(("user", "a"), ("assistant", "b"))
    assert rewrite_question("orig", hist) == "orig"


def test_strips_leak_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeModel(text="書き換え後の質問: RAG とは何ですか")
    _install_fake(monkeypatch, fake)
    hist = _hist(("user", "a"), ("assistant", "b"))
    out = rewrite_question("RAG とは?", hist)
    assert out == "RAG とは何ですか"
