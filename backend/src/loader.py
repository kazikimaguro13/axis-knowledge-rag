"""Markdown + YAML frontmatter loader.

仕様書 docs/spec-v2.md セクション 5.1 のフォーマットを読み込んで
Document オブジェクトに変換する。Day 1 の主成果物。
"""

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter

logger = logging.getLogger(__name__)


class LoaderError(Exception):
    """Raised when a Markdown document fails to load."""


@dataclass
class Document:
    """A loaded knowledge document.

    Attributes:
        id: Unique identifier from frontmatter `id` field.
        title: Human-readable title.
        axes: Structured axis values (category, topic, level, author, year, ...).
        tags: Free-form tags.
        refs: IDs of referenced documents.
        body: The Markdown body (without frontmatter).
        path: Source file path on disk.
        raw_meta: Full frontmatter dict for debugging / extension.
    """

    id: str
    title: str
    axes: dict[str, Any]
    tags: list[str]
    refs: list[str]
    body: str
    path: Path
    raw_meta: dict[str, Any] = field(default_factory=dict)


def load_document(path: Path) -> Document:
    """Load a single Markdown file with YAML frontmatter."""
    if not path.exists():
        raise LoaderError(f"File not found: {path}")
    if not path.is_file():
        raise LoaderError(f"Not a file: {path}")

    try:
        post = frontmatter.load(path)
    except Exception as e:
        raise LoaderError(f"Failed to parse frontmatter for {path}: {e}") from e

    meta = post.metadata
    if "id" not in meta:
        raise LoaderError(f"Missing required 'id' field in {path}")
    if "title" not in meta:
        raise LoaderError(f"Missing required 'title' field in {path}")

    return Document(
        id=str(meta["id"]),
        title=str(meta["title"]),
        axes=dict(meta.get("axes", {})),
        tags=list(meta.get("tags", [])),
        refs=list(meta.get("refs", [])),
        body=post.content,
        path=path,
        raw_meta=dict(meta),
    )


def load_directory(
    dir_path: Path, *, pattern: str = "*.md", strict: bool = False
) -> list[Document]:
    """Load all Markdown files under a directory (non-recursive by default).

    Args:
        dir_path: Directory containing Markdown knowledge files.
        pattern: Glob pattern; pass `**/*.md` for recursive.
        strict: If True, raise on first failure. If False (default), skip
                failed files with a WARN log so a single broken file doesn't
                break the batch.

    Returns:
        List of successfully loaded Documents.
    """
    if not dir_path.exists():
        raise LoaderError(f"Directory not found: {dir_path}")
    if not dir_path.is_dir():
        raise LoaderError(f"Not a directory: {dir_path}")

    docs: list[Document] = []
    files = sorted(dir_path.glob(pattern))
    if not files:
        logger.warning("No Markdown files matched %s in %s", pattern, dir_path)
        return docs

    for f in files:
        try:
            docs.append(load_document(f))
        except LoaderError as e:
            if strict:
                raise
            logger.warning("Skipping %s: %s", f, e)

    logger.info("Loaded %d/%d documents from %s", len(docs), len(files), dir_path)
    return docs


def _main(argv: list[str]) -> int:
    """CLI entrypoint: `python -m backend.src.loader <dir>`."""
    from backend.src.config import configure_logging

    configure_logging()

    if len(argv) < 2:
        print("Usage: python -m backend.src.loader <directory>", file=sys.stderr)
        return 1

    target = Path(argv[1])
    docs = load_directory(target, pattern="*.md")

    print(f"\n=== Loaded {len(docs)} documents from {target} ===\n")
    for d in docs:
        print(f"- [{d.id}] {d.title}")
        print(f"    axes: {d.axes}")
        print(f"    tags: {d.tags}  refs: {d.refs}")
        print(f"    body: {len(d.body)} chars\n")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
