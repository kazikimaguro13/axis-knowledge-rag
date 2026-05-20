"""Save a captured web page as YAML+Markdown to the knowledge directory.

Used by ``POST /api/ingest`` (spec_046) — the browser extension sends URL +
title + body (and optionally a user-selected snippet), and we persist a new
``examples/knowledge/web_YYYYMMDD_HHMMSS_<slug>.md`` file that the existing
indexer can pick up untouched.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SLUG_RE_DROP = re.compile(r"[^\w\s-]", flags=re.UNICODE)
_SLUG_RE_COLLAPSE = re.compile(r"[-\s]+", flags=re.UNICODE)


def _slugify(text: str, max_len: int = 40) -> str:
    """Convert title to a filesystem-safe slug.

    Japanese / wide characters are NFKC-normalised first so 「全角ABC」 → 「abc」.
    Empty input falls back to ``"web"`` so the filename remains valid.
    """

    text = unicodedata.normalize("NFKC", text or "")
    text = _SLUG_RE_DROP.sub("", text.lower())
    text = _SLUG_RE_COLLAPSE.sub("-", text).strip("-_")
    return text[:max_len] or "web"


def _yaml_scalar(value: Any) -> str:
    """Render a single YAML scalar, quoting only when strictly necessary.

    PyYAML accepts ``https://example.com`` as a bare scalar (the ``:`` is
    only a key/value delimiter when followed by whitespace), so we keep
    URLs unquoted. We quote only when the value starts with a YAML
    reserved indicator, contains ``: `` / ``\\n``, or has leading/trailing
    whitespace.
    """

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = "" if value is None else str(value)
    needs_quote = (
        s == ""
        or s[0] in "-?:,[]{}&*!|>'\"%@`"
        or ": " in s
        or " #" in s
        or "\n" in s
        or s.strip() != s
    )
    if needs_quote:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def _yaml_dump(data: Mapping[str, Any]) -> str:
    """Minimal YAML serializer for the small frontmatter we emit."""

    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, Mapping):
            lines.append(f"{key}:")
            for sub_key, sub_value in value.items():
                lines.append(f"  {sub_key}: {_yaml_scalar(sub_value)}")
        elif isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    return "\n".join(lines)


def save_web_page(
    *,
    url: str,
    title: str,
    body: str,
    selected_text: str | None = None,
    knowledge_dir: str | Path = "./examples/knowledge",
    now: datetime | None = None,
) -> Path:
    """Persist a captured web page as a YAML-frontmatter Markdown file.

    Filename: ``web_YYYYMMDD_HHMMSS_<slug>.md`` (UTC). ``selected_text``,
    when provided and non-empty, takes priority over ``body`` so the user's
    deliberate selection wins over the full-page dump.
    """

    knowledge_dir = Path(knowledge_dir)
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    captured_at = (now or datetime.now(UTC)).astimezone(UTC)
    slug = _slugify(title or "")
    fname = f"web_{captured_at:%Y%m%d_%H%M%S}_{slug}.md"
    path = knowledge_dir / fname

    selected = (selected_text or "").strip()
    main_content = selected if selected else (body or "").strip()

    frontmatter: dict[str, Any] = {
        "id": path.stem,
        "title": title,
        "source": "browser-extension",
        "url": url,
        "captured_at": captured_at.isoformat(),
        "axes": {
            "category": "Web",
            "topic": "未分類",
            "level": "中級",
        },
        "refs": [],
    }
    fm = _yaml_dump(frontmatter)
    md = f"---\n{fm}\n---\n\n# {title}\n\nsource: {url}\n\n{main_content}\n"
    path.write_text(md, encoding="utf-8")
    return path
