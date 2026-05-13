"""CLI: batch-convert a directory of raw text files to YAML-frontmatter Markdown.

Usage:
    python -m scripts.yamlize_dir ./raw_memos/ --output ./examples/knowledge/
    python -m scripts.yamlize_dir ./raw_memos/ -o /tmp/out/ --pattern "*.txt"

For each input file:
  1. compute `next_id` against `knowledge_dir` + the in-memory counter (so
     batch runs don't collide even when `knowledge_dir` is not written into),
  2. ask the Ingester to produce an `IngestResult`,
  3. write `<next_id>-<slug>.md` to `output_dir`.

The in-memory counter prevents id collisions when many files are processed
before any of them lands in `knowledge_dir`.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from backend.src.config import configure_logging
from backend.src.ingester import Ingester, _next_doc_id, render_markdown
from backend.src.ingester_schemas import IngestOptions, IngestResult

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str, fallback: str) -> str:
    s = _SLUG_RE.sub("-", title.lower()).strip("-")
    if not s or not any(c.isascii() and c.isalnum() for c in s):
        # Title was all non-ASCII (e.g. Japanese) → use the input filename stem
        s = _SLUG_RE.sub("-", fallback.lower()).strip("-") or "doc"
    return s[:60]


def _bump_id(doc_id: str) -> str:
    n = int(doc_id[4:])
    return f"doc_{n + 1:03d}"


def main(argv: list[str]) -> int:
    configure_logging()
    p = argparse.ArgumentParser(description="Batch raw text → YAML-frontmatter Markdown")
    p.add_argument("input_dir", help="Directory containing raw text files")
    p.add_argument("--output", "-o", required=True, help="Output directory for .md files")
    p.add_argument("--pattern", default="*.txt", help="Glob pattern for inputs (default: *.txt)")
    p.add_argument("--knowledge-dir", default="./examples/knowledge")
    p.add_argument("--suggested-category", default=None)
    p.add_argument("--max-tokens", type=int, default=1500)
    p.add_argument("--force-dummy", action="store_true")
    args = p.parse_args(argv[1:])

    in_dir = Path(args.input_dir)
    out_dir = Path(args.output)
    if not in_dir.is_dir():
        print(f"[error] not a directory: {in_dir}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(in_dir.glob(args.pattern))
    if not files:
        print(f"[warn] no files matched {args.pattern} in {in_dir}", file=sys.stderr)
        return 0

    ingester = Ingester(force_dummy=args.force_dummy)
    knowledge_dir = Path(args.knowledge_dir)
    current_id = _next_doc_id(knowledge_dir)
    written: list[tuple[Path, IngestResult]] = []

    for f in files:
        raw = f.read_text(encoding="utf-8")
        opts = IngestOptions(
            knowledge_dir=args.knowledge_dir,
            suggested_category=args.suggested_category,
            max_tokens=args.max_tokens,
        )
        result = ingester.ingest(raw, opts)
        # Override Claude's id with our in-memory counter to guarantee no collisions
        # within this batch. The Ingester already used `next_id`, but with a stale
        # knowledge_dir view across iterations, multiple files would share the same id.
        result = result.model_copy(update={"id": current_id})
        slug = _slugify(result.title, fallback=f.stem)
        out_path = out_dir / f"{current_id}-{slug}.md"
        out_path.write_text(render_markdown(result), encoding="utf-8")
        print(f"[ok] {f.name} → {out_path.name} (title={result.title!r})", file=sys.stderr)
        written.append((out_path, result))
        current_id = _bump_id(current_id)

    print(f"[done] converted {len(written)} file(s) into {out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
