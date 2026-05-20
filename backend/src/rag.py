"""RAG pipeline: retrieve via SearchEngine, generate with Claude or Ollama.

Returns an Answer that contains the generated text + citation list,
preserving source document IDs for downstream UI rendering.

spec_045: ``GenerationBackend`` Protocol abstracts the LLM call so a fully
on-prem Ollama backend can replace the default Anthropic Claude path without
touching the retrieval / citation logic.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from backend.src._citations import parse_and_validate_citations
from backend.src.config import load_app_config, settings
from backend.src.conversation import (
    ConversationStore,
    Message,
    get_default_store,
)
from backend.src.embedder import make_embedder
from backend.src.gap_detection import GapStore, detect_no_info
from backend.src.question_rewriter import rewrite_question
from backend.src.search import SearchEngine, SearchResult
from backend.src.vector_store import VectorStore

if TYPE_CHECKING:
    from backend.src.config import GenerationConfig

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

# Index-based citation marker `[N]` (1-indexed, matches the position of a
# source in the prompt's `## 出典 N` blocks). See ADR-020.
SYSTEM_PROMPT = """\
あなたは知識ベース検索エンジンの回答生成エージェントです。
ユーザーの質問に対して、提供された Document の内容**のみ**から回答してください。
提供された文書に書かれていないことは「資料には記載がない」と答えてください。

回答ルール:
1. 出典に基づく主張の文末に `[N]` を付けてください (N は 1 始まり、出典リストの index と一致)
2. 複数の出典が同じ主張を裏付ける場合は `[1][2]` のように連続させてください
3. 出典に書かれていない一般論や前置きには `[N]` を付けないでください
4. 推測や一般論を加えず、Document の内容を要約・引用する形にする
5. 出典が無い質問への回答は「提供された資料には記載がありません」と短く答える

簡潔で読みやすい日本語で答えてください。
"""

CHAT_SYSTEM_PROMPT = """\
あなたは社内ナレッジ検索アシスタントです。
直近の会話履歴と、検索でヒットしたドキュメントを参考に、ユーザーの質問に答えてください。

回答ルール:
1. 答えは検索でヒットしたドキュメントに書かれた内容に忠実に
2. 出典に基づく主張の文末に `[N]` を付けてください (N は 1 始まり、出典リストの index と一致)
3. 複数の出典が同じ主張を裏付ける場合は `[1][2]` のように連続させてください
4. 履歴と矛盾する内容があった場合、履歴ではなくドキュメントに従う
5. 履歴は文脈把握 (代名詞解決・話題継続) のためだけに使う
6. 出典が無い場合は「提供された資料には記載がありません」と短く答える

簡潔で読みやすい日本語で答えてください。
"""


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


def _smart_truncate(text: str, max_chars: int = 200) -> str:
    """Truncate at the nearest sentence boundary at or before ``max_chars``.

    Looks for 。 / . / ! / ? / blank-line in the last 30% of the window and
    cuts there; falls back to a hard slice + "…" when no boundary is found.
    Returns text unchanged when it fits within ``max_chars``.
    """
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    window_start = int(max_chars * 0.7)
    candidate = text[window_start:max_chars]
    for marker in ("。\n", "。", ".\n", ". ", "!\n", "! ", "?\n", "? ", "\n\n"):
        idx = candidate.rfind(marker)
        if idx >= 0:
            cut = window_start + idx + len(marker.rstrip())
            return text[:cut] + "…"
    return text[:max_chars] + "…"


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
    snippet = _smart_truncate(results[0].body_snippet, max_chars=200)
    text = (
        f"[DUMMY ANSWER] 質問「{question}」に対し、"
        f"資料「{results[0].title}」が最も関連しています[1]。"
        f" 抜粋: {snippet}"
    )
    return Answer(
        text=text, sources=results, cited_ids=cited, is_dummy=True, model="dummy"
    )


# ---------------------------------------------------------------------------
# spec_045: GenerationBackend Protocol + Claude/Ollama implementations
# ---------------------------------------------------------------------------


@runtime_checkable
class GenerationBackend(Protocol):
    """Protocol for the LLM call inside :class:`RAGPipeline`.

    Backends only see the system prompt and a Claude-compatible
    ``messages: [{"role": "...", "content": "..."}]`` list. They are not
    responsible for prompt construction or citation parsing.
    """

    def generate(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
    ) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def is_dummy(self) -> bool: ...


class ClaudeBackend:
    """Anthropic Claude backend (v0.8.1 default)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key or settings.anthropic_api_key)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def is_dummy(self) -> bool:
        return False

    def generate(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
    ) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return "".join(b.text for b in resp.content if hasattr(b, "text"))


class OllamaBackend:
    """Ollama ``/api/chat`` backend (spec_045 fully on-prem path)."""

    DEFAULT_MODEL = "llama3"
    DEFAULT_URL = "http://localhost:11434"

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        url: str = DEFAULT_URL,
    ) -> None:
        import ollama

        self._client = ollama.Client(host=url)
        self._model = model
        self._url = url

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def is_dummy(self) -> bool:
        return False

    def generate(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
    ) -> str:
        ollama_messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        ollama_messages.extend(messages)
        resp = self._client.chat(
            model=self._model,
            messages=ollama_messages,
            options={"num_predict": max_tokens},
        )
        return resp["message"]["content"]


class DummyGenerationBackend:
    """Sentinel — never actually called; :class:`RAGPipeline` short-circuits to
    :func:`_dummy_answer` when ``is_dummy`` is True. Kept so the factory always
    returns a ``GenerationBackend`` and call sites avoid ``Optional``."""

    @property
    def model_name(self) -> str:
        return "dummy"

    @property
    def is_dummy(self) -> bool:
        return True

    def generate(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
    ) -> str:
        return "提供された資料には記載がありません。"


def make_generation_backend(cfg: GenerationConfig | None = None) -> GenerationBackend:
    """Build a :class:`GenerationBackend` from :class:`GenerationConfig`.

    - ``cfg is None`` → defaults (``backend="claude"``).
    - ``backend="claude"``: Anthropic client; auto-falls back to dummy when
      ``ANTHROPIC_API_KEY`` is missing (v0.8.1 behaviour).
    - ``backend="ollama"``: spec_045 on-prem chat path. Falls back to dummy
      on ImportError / connection failure so callers never crash at startup.
    - ``backend="dummy"``: explicit dummy.
    """
    if cfg is None:
        from backend.src.config import GenerationConfig as _GC

        cfg = _GC()
    backend = (cfg.backend or "claude").lower()
    if backend == "ollama":
        try:
            return OllamaBackend(model=cfg.ollama.model, url=cfg.ollama.url)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Ollama generation backend failed (%s), falling back to DUMMY", e
            )
            return DummyGenerationBackend()
    if backend == "dummy":
        return DummyGenerationBackend()
    if not settings.anthropic_api_key:
        logger.warning("RAGPipeline running in DUMMY mode (no ANTHROPIC_API_KEY)")
        return DummyGenerationBackend()
    if backend != "claude":
        logger.warning("Unknown generation backend %r, falling back to claude", backend)
    return ClaudeBackend(model=DEFAULT_MODEL)


class RAGPipeline:
    def __init__(
        self,
        engine: SearchEngine,
        *,
        force_dummy: bool = False,
        model: str = DEFAULT_MODEL,
        context_max_chars: int | None = None,
        backend: GenerationBackend | None = None,
        gap_store: GapStore | None = None,
    ) -> None:
        self._engine = engine
        self._model = model
        # spec_048: optional gap-detection hook. When ``None`` every
        # ``answer`` / ``chat`` call skips the regex check + record (zero
        # cost), matching ``gap.enabled=false`` semantics.
        self._gap_store = gap_store
        if context_max_chars is None:
            try:
                context_max_chars = load_app_config().rag.context_max_chars
            except Exception:  # noqa: BLE001
                context_max_chars = 8000
        self._context_max_chars = context_max_chars
        # ``backend`` overrides everything. Else: ``force_dummy`` short-circuits
        # to DummyGenerationBackend, otherwise the factory inspects config /
        # ANTHROPIC_API_KEY to decide Claude vs dummy. This preserves v0.8.1
        # behaviour exactly when no caller specifies a backend.
        if backend is not None:
            self._backend: GenerationBackend = backend
        elif force_dummy:
            self._backend = DummyGenerationBackend()
        elif not settings.anthropic_api_key:
            logger.warning("RAGPipeline running in DUMMY mode (no ANTHROPIC_API_KEY)")
            self._backend = DummyGenerationBackend()
        else:
            self._backend = ClaudeBackend(model=model)
        # Keep this attribute readable by older tests that mock ``_client``
        # directly. The chat path reads from ``self._backend.generate(...)`` —
        # the legacy ``answer()`` path also delegates there.
        self._client = getattr(self._backend, "_client", None)
        self._use_dummy = self._backend.is_dummy

    @property
    def is_dummy(self) -> bool:
        return bool(self._use_dummy)

    @property
    def backend_name(self) -> str:
        """Short label for telemetry: ``CLAUDE`` / ``OLLAMA`` / ``DUMMY``."""
        if self._backend.is_dummy:
            return "DUMMY"
        if isinstance(self._backend, OllamaBackend):
            return "OLLAMA"
        if isinstance(self._backend, ClaudeBackend):
            return "CLAUDE"
        return type(self._backend).__name__.upper()

    def _call_generation(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> str:
        """Delegate to the active backend's ``generate`` call.

        Test shim: if a ``_client`` attribute has been injected (legacy
        v0.8.1 test path that monkey-patched the Anthropic SDK directly),
        prefer it so existing tests keep working without reworking the
        fake-Anthropic helpers.
        """
        client = getattr(self, "_client", None)
        if client is not None and not self._use_dummy:
            # Legacy path: tests mock the Anthropic Messages API on _client.
            create = getattr(getattr(client, "messages", None), "create", None)
            if callable(create):
                resp = create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                )
                return "".join(
                    block.text for block in resp.content if hasattr(block, "text")
                )
        return self._backend.generate(system, messages, max_tokens=max_tokens)

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
            ans = _dummy_answer(question, results)
            self._record_llm_gap(question, ans.text, results)
            return ans

        # Prefer build_context() — uses full parent text in parent-doc mode,
        # falls back to snippets in legacy mode. Same prompt either way.
        if any(r.body_full for r in results):
            context = build_context(results, max_chars=self._context_max_chars)
        else:
            context = _format_context(results)
        user_msg = (
            f"# 質問\n{question}\n\n"
            f"# 提供された資料 (上位 {len(results)} 件)\n\n{context}\n\n"
            "上記の資料のみを根拠に、出典マーク [N] (N は 1 始まり、上の 出典 i の i と一致) を付けて回答してください。"
        )
        raw = self._call_generation(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=max_tokens,
        )
        text, used = parse_and_validate_citations(raw, n_sources=len(results))
        cited_ids = [results[i].id for i in sorted(used)]
        self._record_llm_gap(question, text, results)
        return Answer(
            text=text,
            sources=results,
            cited_ids=cited_ids,
            is_dummy=False,
            model=self._backend.model_name,
        )

    # ------------------------------------------------------------------
    # spec_048: knowledge-gap detection hook
    # ------------------------------------------------------------------

    def _record_llm_gap(
        self,
        question: str,
        answer_text: str,
        results: list[SearchResult],
    ) -> None:
        """Log when the LLM answered "資料に記載がない" (regex detection).

        Skipped when ``gap_store`` wasn't wired in (the default outside
        ``api.py``). Search-side gaps are logged separately by
        ``SearchEngine._record_gap``; this hook only fires for the
        ``llm_no_info`` reason so the report can distinguish "we didn't
        find anything" from "we found something but the LLM still
        couldn't answer".
        """
        if self._gap_store is None or not question:
            return
        try:
            if not detect_no_info(answer_text):
                return
            self._gap_store.record(
                query=question,
                reason="llm_no_info",
                top_score=float(results[0].score) if results else None,
                n_results=len(results),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("gap store record failed: %s", e)

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
        # spec_048: chat path goes through the same gap detection — the
        # rewritten question is what hit the index, but we want the
        # user-facing string in the report so it's actionable.
        self._record_llm_gap(question, ans.text, results)

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
                    "上記の資料のみを根拠に、出典マーク [N] (N は 1 始まり、上の 出典 i の i と一致) を付けて回答してください。"
                ),
            }
        )
        raw = self._call_generation(
            system=CHAT_SYSTEM_PROMPT,
            messages=messages,
            max_tokens=max_tokens,
        )
        text, used = parse_and_validate_citations(raw, n_sources=len(results))
        cited_ids = [results[i].id for i in sorted(used)]
        return Answer(
            text=text,
            sources=results,
            cited_ids=cited_ids,
            is_dummy=False,
            model=self._backend.model_name,
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
    app_cfg = load_app_config()
    embedder = make_embedder(app_cfg.embedder)
    engine = SearchEngine(store, embedder)
    rag = RAGPipeline(engine, backend=make_generation_backend(app_cfg.generation))
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
