"""Rewrite follow-up questions into standalone search queries.

Uses Gemini Flash (1.5 by default) to rewrite a user's latest question into
a query that no longer depends on the chat history. The standalone form is
used as the retrieval query; the *original* question is still used for
answer generation, so the LLM still hears the natural phrasing from the
user.

All failures (no API key, network error, quota exhaustion, oversized
output) fall back to the original question so chat UX never blocks.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.src.config import settings

if TYPE_CHECKING:
    from backend.src.conversation import Message

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "gemini-2.5-flash"
MAX_REWRITE_LEN = 500


REWRITE_PROMPT = """\
あなたは検索クエリ書き換え専門のアシスタントです。
以下のチャット履歴を踏まえて、最後のユーザーの質問を「履歴を見なくても意味が通じる単独の検索クエリ」に書き換えてください。

- 履歴の文脈が必要なければ、元の質問をそのまま返してください
- 出力は書き換え後の質問テキスト 1 行のみ。前置きや説明は不要
- 固有名詞や技術用語は維持

[履歴]
{history}

[最後の質問]
{question}

[書き換え後の質問]"""


def _format_history(history: list[Message]) -> str:
    return "\n".join(f"{m.role}: {m.content[:200]}" for m in history[-6:])


def _clean_rewritten(rewritten: str) -> str:
    """Strip a leading prefix the model may have leaked back."""
    for prefix in ("書き換え後の質問:", "Rewritten question:", "Q:"):
        if rewritten.startswith(prefix):
            rewritten = rewritten[len(prefix):].strip()
    return rewritten


def _rewrite_with_ollama(prompt: str, model_name: str, url: str) -> str:
    """spec_045: call an Ollama chat model for the rewrite."""
    import ollama

    client = ollama.Client(host=url)
    resp = client.chat(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.0, "num_predict": 200},
    )
    return (resp["message"]["content"] or "").strip()


def _rewrite_with_gemini(prompt: str, model_name: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content(
        prompt,
        generation_config={"temperature": 0.0, "max_output_tokens": 200},
    )
    return (getattr(resp, "text", "") or "").strip()


def rewrite_question(
    question: str,
    history: list[Message],
    *,
    model_name: str = DEFAULT_MODEL,
    enabled: bool = True,
    backend: str = "gemini",
    ollama_url: str = "http://localhost:11434",
) -> str:
    """Rewrite ``question`` into a standalone query using chat history.

    spec_045 added ``backend`` so the rewriter can run fully on-prem via
    Ollama. ``backend="gemini"`` (default) keeps v0.8.1 behaviour exactly.

    Returns the original ``question`` unchanged when:
    - ``enabled=False`` / ``history`` is empty / ``question`` is blank
    - the chosen backend isn't configured (no GEMINI_API_KEY for gemini,
      no ``ollama`` package / unreachable server for ollama)
    - the model call raises
    - the response is empty or >500 chars (likely a hallucination)
    """
    if not enabled or not history or not question.strip():
        return question
    prompt = REWRITE_PROMPT.format(
        history=_format_history(history),
        question=question,
    )
    backend_l = (backend or "gemini").lower()
    try:
        if backend_l == "ollama":
            rewritten = _rewrite_with_ollama(prompt, model_name, ollama_url)
        else:
            if not settings.gemini_api_key:
                return question
            rewritten = _rewrite_with_gemini(prompt, model_name)
    except Exception as e:  # noqa: BLE001 — fall back on any failure
        logger.warning("question rewriter failed, using original query: %s", e)
        return question

    if not rewritten or len(rewritten) > MAX_REWRITE_LEN:
        return question
    rewritten = _clean_rewritten(rewritten)
    return rewritten or question
