"""CLI: convert a single raw text file to YAML-frontmatter Markdown.

Usage:
    python -m scripts.yamlize input.txt
    python -m scripts.yamlize input.txt --output examples/knowledge/doc_011.md
    python -m scripts.yamlize input.txt --suggested-category 議事録
    cat memo.txt | python -m scripts.yamlize -
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.src.config import configure_logging
from backend.src.ingester import Ingester, render_markdown
from backend.src.ingester_schemas import IngestOptions


def main(argv: list[str]) -> int:
    configure_logging()
    p = argparse.ArgumentParser(description="raw text → YAML-frontmatter Markdown (axis-knowledge-rag)")
    p.add_argument("input", help="Path to raw text file, or '-' for stdin")
    p.add_argument("--output", "-o", help="Output Markdown file path. Default: stdout")
    p.add_argument("--knowledge-dir", default="./examples/knowledge")
    p.add_argument("--suggested-category", default=None)
    p.add_argument("--max-tokens", type=int, default=1500)
    p.add_argument("--force-dummy", action="store_true", help="Force DUMMY mode even if ANTHROPIC_API_KEY is set")
    args = p.parse_args(argv[1:])

    raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")

    opts = IngestOptions(
        knowledge_dir=args.knowledge_dir,
        suggested_category=args.suggested_category,
        max_tokens=args.max_tokens,
    )
    ingester = Ingester(force_dummy=args.force_dummy)
    result = ingester.ingest(raw, opts)
    md = render_markdown(result)

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(
            f"[ok] wrote {args.output} (id={result.id}, title={result.title!r})",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
