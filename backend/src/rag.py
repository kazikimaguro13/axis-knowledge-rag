"""RAG pipeline: retrieve via SearchEngine, generate with Claude.

Returns an Answer that contains the generated text + citation list,
preserving source document IDs for downstream UI rendering.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from backend.src.config import load_app_config, settings
from backend.src.conversation import (
    ConversationStore,
    Message,
    get_default_store,
)
from backend.src.embedder import Embedder
from backend.src.question_rewriter import rewrite_question
from backend.src.search import SearchEngine, SearchResult
from backend.src.vector_store import VectorStore

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

SYSTEM_PROMPT = """\
あなたは知識ベース検索エンジンの回答生成エージェントです。
ユーザーの質問に対して、提供された Document の内容**のみ**から回答してください。
提供された文書に書かれていないことは「資料には記載がない」と答えてください。

回答ルール:
1. 回答中で参照した Document は必ず `[doc_NNN]` 形式で本文中にマークしてください
2. 複数 Document を参照した場合は `[doc_001][doc_004]` のように並べる
3. 推測や一般論を加えず、Document の内容を要約・引用する形にする
4. 出典が無い質問への回答は「提供された資料には記載がありません」と短く答える

簡潔で読みやすい日本語で答えてください。
"""

CHAT_SYSTEM_PROMPT = """\
あなたは社内ナレッジ検索アシスタントです。
直近の会話履歴と、検索でヒットしたドキュメントを参考に、ユーザーの質問に答えてください。

回答ルール:
1. 答えは検索でヒットしたドキュメントに書かれた内容に忠実に
2. 回答中で参照した Document は必ず `[doc_NNN]` 形式で本文中にマークしてください
3. 履歴と矛盾する内容があった場合、履歴ではなくドキュメントに従う
4. 履歴は文脈把握 (代名詞解決・話題継続) のためだけに使う
5. 出典が無い場合は「提供された資料には記載がありません」と短く答える

簡潔で読みやすい日本語で答えてください。
"""

CITATION_RE = re.compile(r"\[(doc_\d+)\]")


@dataclass
class Answer:
    text: str
    sources: list[SearchResult] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)
    is_dummy: bool = False
    model: str | None = None


@dataclass
class ChatResponse:
    """Return type for ``RAGPipeline.chat()``.

    ``rewritten_question`` is ``None`` when no rewrite happened (either the
    rewriter was skipped, fell back on error, or the rewrite matched the
    original verbatim) — that lets the UI display the rewrite badge only
    when it carries information.
    """

    session_id: str
    question: str
    rewritten_question: str | None
    answer: str
    sources: list[SearchResult] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)
    is_dummy: bool = False
    model: str | None = None


def _format_context(results: list[SearchResult]) -> str:
    """Concise context — the legacy v0.6 format kept for short snippet hits."""
    lines: list[str] = []
    for r in results:
        lines.append(f"### [{r.id}] {r.title}")
        lines.append(f"axes: {r.axes}")
        lines.append(r.body_snippet)
        lines.append("")
    return "\n".join(lines)


def build_context(
    results: list[SearchResult],
    *,
    max_chars: int = 8000,
) -> str:
    """Concatenate parent (or doc) bodies with citation headers, capped by chars.

    Uses ``body_full`` when populated (parent-doc mode) — that's the entire
    H2 section text. Falls back to ``body_snippet`` otherwise, so the legacy
    file-level path keeps working without changes. The hard ``max_chars``
    budget protects the LLM context window — blocks beyond the budget are
    dropped silently rather than truncated mid-sentence.
    """
    out: list[str] = []
    used = 0
    for i, r in enumerate(results, 1):
        body = r.body_full or r.body_snippet or ""
        block = (
            f"## 出典 {i}: [{r.id}] {r.title}\n"
            f"(file: {r.path})\n"
            f"axes: {r.axes}\n\n"
            f"{body}\n\n"
        )
        if used + len(block) > max_chars:
            break
        out.append(block)
        used += len(block)
    return "".join(out)


def _dummy_answer(question: str, results: list[SearchResult]) -> Answer:
    """Generate a deterministic offline answer for dev / CI."""
    if not results:
        return Answer(
            text="提供された資料には記載がありません。",
            sources=[],
            cited_ids=[],
            is_dummy=True,
        )
    cited = [results[0].id]
    text = (
        f"[DUMMY ANSWER] 質問「{question}」に対し、"
        f"資料 [{results[0].id}] (「{results[0].title}」) が最も関連しています。"
        f" 抜粋: {results[0].body_snippet[:120]}..."
    )
    return Answer(
        text=text, sources=results, cited_ids=cited, is_dummy=True, model="dummy"
    )


class RAGPipeline:
    def __init__(
        self,
        engine: SearchEngine,
        *,
        force_dummy: bool = False,
        model: str = DEFAULT_MODEL,
        context_max_chars: int | None = None,
    ) -> None:
        self._engine = engine
        self._model = model
        self._use_dummy = force_dummy or not settings.anthropic_api_key
        if context_max_chars is None:
            try:
                context_max_chars = load_app_config().rag.context_max_chars
            except Exception:  # noqa: BLE001
                context_max_chars = 8000
        self._context_max_chars = context_max_chars
        if self._use_dummy:
            logger.warning("RAGPipeline running in DUMMY mode (no ANTHROPIC_API_KEY)")
            self._client = None
        else:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=settings.anthropic_api_key)

    @property
    def is_dummy(self) -> bool:
        return self._use_dummy

    def answer(
        self,
        question: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int = 5,
        max_tokens: int = 1024,
    ) -> Answer:
        results = self._engine.search(question, filters=filters, top_k=top_k)
        if self._use_dummy:
            return _dummy_answer(question, results)

        # Prefer build_context() — uses full parent text in parent-doc mode,
        # falls back to snippets in legacy mode. Same prompt either way.
        if any(r.body_full for r in results):
            context = build_context(results, max_chars=self._context_max_chars)
        else:
            context = _format_context(results)
        user_msg = (
            f"# 質問\n{question}\n\n"
            f"# 提供された資料 (上位 {len(results)} 件)\n\n{context}\n\n"
            "上記の資料のみを根拠に、出典マーク [doc_NNN] を付けて回答してください。"
        )
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        cited_ids = sorted(set(CITATION_RE.findall(text)))
        return Answer(
            text=text,
            sources=results,
            cited_ids=cited_ids,
            is_dummy=False,
            model=self._model,
        )

    # ------------------------------------------------------------------
    # spec_032: conversational RAG
    # ------------------------------------------------------------------

    def chat(
        self,
        question: str,
        *,
        session_id: str | None = None,
        filters: dict[str, Any] | None = None,
        top_k: int = 5,
        max_tokens: int = 1024,
        store: ConversationStore | None = None,
        rewriter_enabled: bool = True,
        rewriter_model: str = "gemini-1.5-flash",
        history_turns: int = 6,
    ) -> ChatResponse:
        """Single-turn chat that keeps history under ``session_id``.

        Steps:
        1. Look up (or create) the session in ``store``.
        2. Rewrite the question into a standalone query using up to
           ``history_turns`` turns of prior context.
        3. Retrieve with the rewritten query, generate with Claude (or the
           dummy fallback) — the generation prompt sees the *original*
           question plus the last 3 turns of history.
        4. Append user + assistant messages back into the session.
        """
        # Use ``is None`` rather than ``store or ...`` — ConversationStore
        # defines __len__, so an empty store is falsy and would silently
        # fall through to the module default.
        if store is None:
            store = get_default_store()
        session = store.get_or_create(session_id)

        history = store.get_history(
            session.session_id, last_n_turns=history_turns
        )
        rewritten = rewrite_question(
            question,
            history,
            model_name=rewriter_model,
            enabled=rewriter_enabled,
        )
        retrieval_query = rewritten or question

        results = self._engine.search(retrieval_query, filters=filters, top_k=top_k)

        if self._use_dummy:
            ans = _dummy_answer(question, results)
        else:
            ans = self._generate_chat_answer(
                question=question,
                results=results,
                history=history,
                max_tokens=max_tokens,
            )

        # Persist turn — sources as plain dicts so the store stays
        # JSON-friendly (the API returns them via asdict()).
        sources_payload = [_source_to_dict(s) for s in ans.sources]
        store.append(session.session_id, Message(role="user", content=question))
        store.append(
            session.session_id,
            Message(role="assistant", content=ans.text, sources=sources_payload),
        )

        return ChatResponse(
            session_id=session.session_id,
            question=question,
            rewritten_question=rewritten if rewritten != question else None,
            answer=ans.text,
            sources=ans.sources,
            cited_ids=ans.cited_ids,
            is_dummy=ans.is_dummy,
            model=ans.model,
        )

    def _generate_chat_answer(
        self,
        *,
        question: str,
        results: list[SearchResult],
        history: list[Message],
        max_tokens: int,
    ) -> Answer:
        """Call Claude with chat-style prompt (history + retrieved context)."""
        if any(r.body_full for r in results):
            context = build_context(results, max_chars=self._context_max_chars)
        else:
            context = _format_context(results)

        # Replay the last ~3 turns (= 6 messages) so Claude sees the dialog
        # but the bulk of the budget still goes to the retrieved docs.
        recent = history[-6:]
        messages: list[dict[str, str]] = []
        for m in recent:
            if m.role not in ("user", "assistant"):
                continue
            messages.append({"role": m.role, "content": m.content})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"# 質問\n{question}\n\n"
                    f"# 提供された資料 (上位 {len(results)} 件)\n\n{context}\n\n"
                    "上記の資料のみを根拠に、出典マーク [doc_NNN] を付けて回答してください。"
                ),
            }
        )
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=CHAT_SYSTEM_PROMPT,
            messages=messages,
        )
        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        cited_ids = sorted(set(CITATION_RE.findall(text)))
        return Answer(
            text=text,
            sources=results,
            cited_ids=cited_ids,
            is_dummy=False,
            model=self._model,
        )


def _source_to_dict(s: SearchResult) -> dict[str, Any]:
    """Plain-dict view of a SearchResult for storage / JSON serialization."""
    return {
        "id": s.id,
        "title": s.title,
        "score": s.score,
        "axes": dict(s.axes),
        "body_snippet": s.body_snippet,
        "path": s.path,
        "refs": list(s.refs),
    }


def _main(argv: list[str]) -> int:
    import argparse
    from pathlib import Path

    from backend.src.config import configure_logging

    configure_logging()
    p = argparse.ArgumentParser()
    p.add_argument("question")
    p.add_argument("--category")
    p.add_argument("--topic")
    p.add_argument("--level")
    p.add_argument("--author")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--db-path", default=str(settings.chroma_db_path))
    args = p.parse_args(argv[1:])

    filters = {
        k: v
        for k, v in {
            "category": args.category,
            "topic": args.topic,
            "level": args.level,
            "author": args.author,
        }.items()
        if v is not None
    }
    store = VectorStore(path=Path(args.db_path))
    embedder = Embedder()
    engine = SearchEngine(store, embedder)
    rag = RAGPipeline(engine)
    ans = rag.answer(args.question, filters=filters or None, top_k=args.top)

    print(f"\n=== Answer (model={ans.model}, dummy={ans.is_dummy}) ===\n")
    print(ans.text)
    print("\n--- Sources ---")
    for s in ans.sources:
        marker = "*" if s.id in ans.cited_ids else " "
        print(f" {marker} [{s.score:.3f}] {s.id}  {s.title}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv))
