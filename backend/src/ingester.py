"""AI-powered ingester: raw text → axis-knowledge-rag YAML frontmatter Markdown.

Reuses the Claude API client pattern from `rag.py`. When `ANTHROPIC_API_KEY`
is not set (or `force_dummy=True`), falls back to a deterministic mock so the
CLI and tests run offline.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from backend.src.config import load_axes_config, settings
from backend.src.ingester_schemas import IngestOptions, IngestResult
from backend.src.loader import load_directory

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")


_SYSTEM_PROMPT = """\
あなたは axis-knowledge-rag のナレッジエディタです。
ユーザーが渡す raw text を、以下の YAML frontmatter 付き Markdown 構造に変換してください。

出力は必ず以下の JSON 形式 (説明文や ``` などのコードフェンス無しで):
{
  "id": "doc_NNN",
  "title": "...",
  "axes": {<axis_name>: <value>, ...},
  "tags": [...],
  "refs": [],
  "body": "..."
}

ルール:
1. id は 与えられた 'next_id' を必ずそのまま使う
2. title は本文要約 3〜200 文字、絵文字なし
3. axes は与えられた axes_constraints に厳密従う:
   - type='enum' の軸は values のいずれか必須
   - type='string' は短く (50字以内)
   - type='integer' は 範囲内
   - required=true の軸は必ず埋める、required=false は推測できるなら埋め、無理なら省略
4. tags: 2〜5 個、snake_case、英小文字推奨だが日本語可
5. refs: 与えられた existing_doc_ids の範囲内でのみ参照。推測しない場合は []
6. body は raw text を整形した本文。情報を勝手に削らず、ただ markdown として整える。
"""


def _scan_knowledge_dir(knowledge_dir: Path) -> tuple[str, list[str]]:
    """Single-scan helper: returns (next_doc_id, existing_doc_ids).

    Replaces the previous pair of `_next_doc_id` + `_existing_doc_ids`, which
    each called `load_directory()` independently and therefore parsed every
    frontmatter twice per ingest. Consolidating to one scan halves the I/O
    on batch ingestion (`yamlize_dir.py`).
    """
    if not knowledge_dir.exists():
        return "doc_001", []
    docs = load_directory(knowledge_dir)
    numbers: list[int] = []
    ids: list[str] = []
    for d in docs:
        ids.append(d.id)
        if d.id.startswith("doc_"):
            with contextlib.suppress(ValueError):
                numbers.append(int(d.id[4:]))
    nxt = (max(numbers) + 1) if numbers else 1
    return f"doc_{nxt:03d}", ids


def _next_doc_id(knowledge_dir: Path) -> str:
    """Back-compat wrapper that returns only the next id from `_scan_knowledge_dir`."""
    return _scan_knowledge_dir(knowledge_dir)[0]


def _existing_doc_ids(knowledge_dir: Path) -> list[str]:
    """Back-compat wrapper that returns only existing ids from `_scan_knowledge_dir`."""
    return _scan_knowledge_dir(knowledge_dir)[1]


def _dummy_result(raw_text: str, next_id: str) -> IngestResult:
    """Deterministic mock used when no API key is available (CI / offline dev)."""
    h = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:8]
    return IngestResult(
        id=next_id,
        title=f"[DUMMY] Auto-generated from raw text ({h})",
        axes={"category": "メモ", "topic": "未分類"},
        tags=["dummy", "auto"],
        refs=[],
        body=f"<!-- DUMMY mode: ingested without Claude API -->\n\n{raw_text.strip()}",
    )


def _strip_code_fence(s: str) -> str:
    """Best-effort: tolerate Claude wrapping JSON in ```json ... ``` fences."""
    t = s.strip()
    if not t.startswith("```"):
        return t
    t = t.strip("`").strip()
    if t.startswith("json"):
        t = t[4:].lstrip()
    if t.endswith("```"):
        t = t[:-3]
    return t.strip()


class Ingester:
    """Convert raw text into a structured `IngestResult` via Claude API."""

    def __init__(self, *, force_dummy: bool = False, model: str = DEFAULT_MODEL) -> None:
        self._model = model
        self._use_dummy = force_dummy or not settings.anthropic_api_key
        if self._use_dummy:
            logger.warning("Ingester running in DUMMY mode (no ANTHROPIC_API_KEY)")
            self._client = None
        else:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=settings.anthropic_api_key)

    @property
    def is_dummy(self) -> bool:
        return self._use_dummy

    def ingest(
        self,
        raw_text: str,
        options: IngestOptions | None = None,
    ) -> IngestResult:
        opts = options or IngestOptions()
        knowledge_dir = Path(opts.knowledge_dir)
        next_id, existing_ids = _scan_knowledge_dir(knowledge_dir)

        if self._use_dummy:
            return _dummy_result(raw_text, next_id)

        axes_cfg = load_axes_config()
        constraints = axes_cfg.get("axes", [])

        suggested_block = (
            f"# suggested_category\n{opts.suggested_category}\n\n"
            if opts.suggested_category
            else ""
        )
        base_user_msg = (
            f"# next_id\n{next_id}\n\n"
            f"# existing_doc_ids\n{existing_ids}\n\n"
            f"# axes_constraints\n{json.dumps(constraints, ensure_ascii=False, indent=2)}\n\n"
            f"{suggested_block}"
            f"# raw_text\n{raw_text}\n"
        )

        user_msg = base_user_msg
        last_error: Exception | None = None
        attempts = opts.retry_count + 1
        for attempt in range(attempts):
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=opts.max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw_json = "".join(b.text for b in resp.content if hasattr(b, "text"))
            raw_json = _strip_code_fence(raw_json)

            try:
                data = json.loads(raw_json)
                return IngestResult(**data)
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e
                logger.warning(
                    "Ingest attempt %d/%d failed: %s", attempt + 1, attempts, e
                )
                if attempt < attempts - 1:
                    # Feed the previous error back to Claude so the next attempt
                    # can self-correct. Keep the body short to avoid token bloat.
                    user_msg = (
                        f"{base_user_msg}\n"
                        f"# previous_attempt_failed\n"
                        f"Previous response was invalid JSON ({type(e).__name__}: {e}).\n"
                        f"Return ONLY valid JSON matching the schema — no code fences, no commentary.\n"
                    )

        raise RuntimeError(
            f"Claude returned invalid JSON after {attempts} attempts: {last_error}"
        )


def render_markdown(result: IngestResult) -> str:
    """Render an `IngestResult` as a YAML-frontmatter Markdown document."""
    fm = {
        "id": result.id,
        "title": result.title,
        "axes": result.axes,
        "tags": result.tags,
        "refs": result.refs,
    }
    yaml_block = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
    return f"---\n{yaml_block}---\n\n{result.body}\n"
