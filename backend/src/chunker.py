"""Parent-child chunking for Markdown documents (spec_031).

This module implements the "Small-to-Big" / Parent Document Retrieval
chunking strategy: a Markdown body is split into

    * **parents**: H2-level sections (or the whole document when no H2 is
      present). Parent text is what we ultimately hand to the LLM.
    * **children**: smaller sub-blocks within each parent (split at H3+
      headings, paragraph boundaries, and a hard token cap). Children are
      the units we embed and run vector / BM25 search against.

Search hits a child, but we deduplicate by parent_id and surface the parent
as the retrieval result so the LLM gets a coherent block of context instead
of a chopped-up fragment.

The implementation deliberately avoids LangChain / llama-index — keeping the
project's "no framework" posture (see ADR-001). All splitting is regex +
standard library.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# JP-aware rough token estimate: 2 chars ≈ 1 token (Gemini / Claude tokenizers
# don't expose a JP-friendly counter cheaply, so we stay conservative).
_CHARS_PER_TOKEN = 2

# Default cap. 256 tokens ≈ 512 chars; safe for Gemini text-embedding-004
# (max 2048 tokens) and small enough that BM25 / vector fits the relevant
# region of a long parent.
DEFAULT_MAX_CHILD_TOKENS = 256

_H2_RE = re.compile(r"(?m)^(##\s+.+)$")
_H3_PLUS_RE = re.compile(r"(?m)^(#{3,}\s+.+)$")
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
_ASCII_ALPHA_RE = re.compile(r"[a-z]")


@dataclass(frozen=True)
class ParentChunk:
    """An H2-level (or whole-doc) chunk used as LLM context.

    Attributes:
        parent_id: Deterministic id, ``{doc_id}#{slug-or-hash}`` or
            ``{doc_id}#root`` when the document has no H2.
        doc_id: Source document identifier (path or frontmatter id).
        title: H2 heading text (or the document title for the root parent).
        text: Full parent text including its child sub-blocks.
        metadata: A copy of the document-level frontmatter / axes dict.
    """

    parent_id: str
    doc_id: str
    title: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ChildChunk:
    """A small chunk used as the embedding / search unit.

    Attributes:
        child_id: Deterministic id ``{parent_id}#c{index:03d}``.
        parent_id: Backreference to the owning parent.
        doc_id: Source document identifier (mirrors parent.doc_id).
        text: The child text (already stripped, never empty).
        token_estimate: ``len(text) // 2`` — rough JP token count.
        metadata: Inherited from the parent (axes, etc.).
    """

    child_id: str
    parent_id: str
    doc_id: str
    text: str
    token_estimate: int
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chunk_markdown(
    doc_id: str,
    body: str,
    frontmatter: dict[str, Any] | None = None,
    *,
    max_child_tokens: int = DEFAULT_MAX_CHILD_TOKENS,
) -> tuple[list[ParentChunk], list[ChildChunk]]:
    """Split a Markdown body into parent (H2) chunks and child sub-chunks.

    Args:
        doc_id: Identifier of the source document (e.g., relative path).
        body: Raw Markdown body (frontmatter already stripped).
        frontmatter: Document-level metadata dict; copied into every parent
            and inherited by every child. ``None`` is treated as ``{}``.
        max_child_tokens: Soft cap on child size. Default 256 tokens
            (~ 512 chars JP). Children are split at sentence boundaries
            (``。`` or ``.``) when the cap is exceeded so meaning stays
            intact.

    Returns:
        ``(parents, children)`` — both ordered as encountered in the body.
        Every child's ``parent_id`` references some entry in ``parents``;
        no orphan children are produced.

    Edge cases:
        * Empty body → ``([], [])``.
        * No H2 → exactly one parent covering the whole body, with title
          taken from ``frontmatter["title"]`` (or ``doc_id`` as fallback).
        * Sections containing only a heading (no content) are still emitted
          as a parent but produce **zero** children.
    """
    fm = dict(frontmatter or {})
    body = body or ""

    sections = _split_into_h2_sections(body, fm)
    if not sections:
        return [], []

    parents: list[ParentChunk] = []
    children: list[ChildChunk] = []
    seen_parent_ids: dict[str, int] = {}

    for sec_title, sec_body in sections:
        base_parent_id = _make_parent_id(doc_id, sec_title)
        # Final dedup safety net: if two H2s in the same doc still collide
        # (same title text → identical slug or identical md5), suffix the
        # 2nd, 3rd, ... occurrence with -2, -3, ... so parent_id stays unique
        # and the dependent child_ids never duplicate downstream in Chroma.
        count = seen_parent_ids.get(base_parent_id, 0)
        seen_parent_ids[base_parent_id] = count + 1
        parent_id = base_parent_id if count == 0 else f"{base_parent_id}-{count + 1}"
        parent_text = sec_body.strip()
        parents.append(
            ParentChunk(
                parent_id=parent_id,
                doc_id=doc_id,
                title=sec_title,
                text=parent_text,
                metadata=dict(fm),
            )
        )
        for i, ch_text in enumerate(_split_children(parent_text, max_child_tokens)):
            children.append(
                ChildChunk(
                    child_id=f"{parent_id}#c{i:03d}",
                    parent_id=parent_id,
                    doc_id=doc_id,
                    text=ch_text,
                    token_estimate=max(1, len(ch_text) // _CHARS_PER_TOKEN),
                    metadata=dict(fm),
                )
            )

    return parents, children


# ---------------------------------------------------------------------------
# H2 splitting
# ---------------------------------------------------------------------------


def _split_into_h2_sections(
    body: str, frontmatter: dict[str, Any]
) -> list[tuple[str, str]]:
    """Return ``[(section_title, section_body), ...]`` in document order.

    A document with no H2 yields a single ``("<doc title>", body)`` tuple —
    so callers always get at least one parent for non-empty input.
    """
    if not body.strip():
        return []

    parts = _H2_RE.split(body)
    # parts[0] is the prelude (anything before the first H2); parts[1::2]
    # are H2 lines; parts[2::2] are the bodies that follow each H2.
    prelude = parts[0]

    sections: list[tuple[str, str]] = []
    if len(parts) == 1:
        # No H2 at all → whole doc is a single root section.
        title = _doc_title(frontmatter)
        sections.append((title, prelude))
        return sections

    # If there is meaningful content before the first H2, keep it as a
    # synthetic root parent so we don't lose preamble text.
    if prelude.strip():
        sections.append((_doc_title(frontmatter), prelude))

    for h2_line, h2_body in zip(parts[1::2], parts[2::2], strict=True):
        title = h2_line.lstrip("# ").strip()
        sections.append((title, h2_body))

    return sections


def _doc_title(frontmatter: dict[str, Any]) -> str:
    val = frontmatter.get("title") if frontmatter else None
    if isinstance(val, str) and val.strip():
        return val.strip()
    return "root"


# ---------------------------------------------------------------------------
# Child splitting
# ---------------------------------------------------------------------------


def _split_children(text: str, max_child_tokens: int) -> list[str]:
    """Split a parent body into child texts respecting structure + size cap.

    Strategy:
        1. Split at H3+ headings — each subsection becomes a candidate.
        2. Within each candidate, split at blank lines (paragraph boundary).
        3. If a paragraph still exceeds ``max_child_tokens``, break it at
           sentence ends (``。`` or ``.``) so we never cut mid-sentence
           unless a single sentence is itself too long.

    Empty / whitespace-only / heading-only blocks are skipped — every
    returned chunk has actual content.
    """
    if not text.strip():
        return []

    max_chars = max(1, max_child_tokens * _CHARS_PER_TOKEN)
    children: list[str] = []

    for sub in _split_at_h3(text):
        for para in _split_paragraphs(sub):
            if not para.strip() or _is_heading_only(para):
                continue
            if len(para) <= max_chars:
                children.append(para.strip())
            else:
                children.extend(_split_by_sentence(para, max_chars))

    return [c for c in children if c]


def _split_at_h3(text: str) -> list[str]:
    """Split on H3+ headings, keeping the heading attached to its body."""
    if not _H3_PLUS_RE.search(text):
        return [text]

    parts = _H3_PLUS_RE.split(text)
    chunks: list[str] = []
    if parts[0].strip():
        chunks.append(parts[0])
    for h_line, h_body in zip(parts[1::2], parts[2::2], strict=True):
        chunks.append(f"{h_line}\n{h_body}")
    return chunks


def _split_paragraphs(text: str) -> list[str]:
    """Split on one-or-more blank lines."""
    return re.split(r"\n\s*\n", text)


def _is_heading_only(block: str) -> bool:
    """True if the block contains only Markdown heading lines + whitespace."""
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("#"):
            return False
    return True


def _split_by_sentence(text: str, max_chars: int) -> list[str]:
    """Greedy sentence-boundary splitter under a hard char cap."""
    text = text.strip()
    if not text:
        return []

    pieces = re.split(r"(?<=[。\.!?！？])\s*", text)
    pieces = [p for p in pieces if p.strip()]
    if not pieces:
        return [text[:max_chars]]

    out: list[str] = []
    buf = ""
    for piece in pieces:
        # If a single sentence is itself bigger than the cap, hard-cut it
        # — better truncated text than dropping content entirely.
        if len(piece) > max_chars:
            if buf:
                out.append(buf.strip())
                buf = ""
            for i in range(0, len(piece), max_chars):
                out.append(piece[i : i + max_chars].strip())
            continue
        if buf and len(buf) + len(piece) > max_chars:
            out.append(buf.strip())
            buf = piece
        else:
            buf = (buf + piece) if buf else piece
    if buf.strip():
        out.append(buf.strip())
    return [o for o in out if o]


# ---------------------------------------------------------------------------
# Parent ID generation
# ---------------------------------------------------------------------------


def _make_parent_id(doc_id: str, title: str) -> str:
    """Deterministic ``{doc_id}#{slug}`` parent identifier.

    The slug is ASCII-folded from the title; titles that fold to a "weak"
    slug (empty, or numeric/symbol-only with no ASCII letters — e.g.
    JP "## 1. 目的" → "1") fall back to an md5-hex prefix of the
    NFKC-normalized title. This keeps the id stable across runs and
    avoids parent_id collisions when two JP H2s share the same numeric
    prefix (spec_055). ASCII-strong slugs like "rag-patterns" are kept
    verbatim for backwards compatibility.
    """
    slug = _slugify(title)
    if not _is_strong_slug(slug):
        normalized = unicodedata.normalize("NFKC", title or "")
        slug = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{doc_id}#{slug}"


def _is_strong_slug(slug: str) -> bool:
    """A slug is "strong" iff it contains at least one ASCII [a-z] letter.

    Empty slugs and numeric/symbol-only slugs ("1", "3-1", "2-") are weak
    and must be replaced with a hash to avoid collisions across JP titles
    that ASCII-fold to the same residue.
    """
    if not slug:
        return False
    return bool(_ASCII_ALPHA_RE.search(slug))


def _slugify(title: str) -> str:
    if not title:
        return ""
    if title == "root":
        return "root"
    folded = unicodedata.normalize("NFKD", title)
    folded = folded.encode("ascii", "ignore").decode("ascii")
    folded = folded.lower()
    folded = _SLUG_STRIP_RE.sub("-", folded).strip("-")
    return folded
