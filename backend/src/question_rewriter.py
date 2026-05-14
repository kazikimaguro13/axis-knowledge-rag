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


DEFAULT_MODEL = "gemini-1.5-flash"
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


def rewrite_question(
    question: str,
    history: list[Message],
    *,
    model_name: str = DEFAULT_MODEL,
    enabled: bool = True,
) -> str:
    """Rewrite ``question`` into a standalone query using chat history.

    Returns the original ``question`` unchanged when:
    - ``enabled=False``
    - ``history`` is empty
    - ``GEMINI_API_KEY`` is not configured
    - Gemini call raises any exception
    - the model returns an empty / oversized (>500 chars) response
    """
    if not enabled or not history or not question.strip():
        return question
    if not settings.gemini_api_key:
        return question
    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content(
            REWRITE_PROMPT.format(
                history=_format_history(history),
                question=question,
            ),
            generation_config={"temperature": 0.0, "max_output_tokens": 200},
        )
        rewritten = (getattr(resp, "text", "") or "").strip()
        if not rewritten or len(rewritten) > MAX_REWRITE_LEN:
            return question
        # Strip a leading "書き換え後の質問:" prefix if the model leaks it
        for prefix in ("書き換え後の質問:", "Rewritten question:", "Q:"):
            if rewritten.startswith(prefix):
                rewritten = rewritten[len(prefix):].strip()
        return rewritten or question
    except Exception as e:  # noqa: BLE001 — fall back on any failure
        logger.warning("question rewriter failed, using original query: %s", e)
        return question
