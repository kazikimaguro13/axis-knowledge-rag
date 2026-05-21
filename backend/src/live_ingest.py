"""Live ingest — embed a single Markdown file into a running index (spec_056).

Used by ``POST /api/ingest/memo`` and ``POST /api/ingest`` so a memo / web
page becomes searchable without ``build_index --rebuild`` + backend restart.
Reuses ``loader.load_document`` + ``chunker.chunk_markdown`` so the
parent/child structure stays identical to a full rebuild — the only
difference is scope (one file) and that we ``delete_doc`` first to make
re-ingest an upsert rather than a DuplicateIDError.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from backend.src.chunker import chunk_markdown
from backend.src.embedder import Embedder
from backend.src.loader import load_document
from backend.src.normalizer import Normalizer
from backend.src.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveIngestResult:
    doc_id: str
    parents: int
    children: int
    deleted_existing: int


def ingest_file(
    path: Path,
    *,
    store: VectorStore,
    embedder: Embedder,
    normalizer: Normalizer,
    max_child_tokens: int = 256,
) -> LiveIngestResult:
    """Load, chunk, embed one Markdown file and merge into the running store.

    Idempotent — calling twice with the same ``doc_id`` does not double the
    chunk count because ``VectorStore.delete_doc`` runs first.

    The frontmatter dict handed to ``chunk_markdown`` mirrors what
    ``scripts.build_index`` passes for parent_doc mode so child metadata
    (``axes`` / ``normalized_axes`` / ``title``) stays consistent.
    """
    doc = load_document(path, normalizer=normalizer)

    fm = {
        "title": doc.title,
        "axes": doc.axes,
        "normalized_axes": doc.normalized_axes,
        "tags": doc.tags,
        "refs": doc.refs,
        "path": str(doc.path),
    }
    parents, children = chunk_markdown(
        doc.id, doc.body, fm, max_child_tokens=max_child_tokens
    )
    deleted = store.delete_doc(doc.id)

    if not children:
        # Empty body — still surface the parent so re-ingest stays consistent.
        store.add_chunks(parents, [], [])
        return LiveIngestResult(
            doc_id=doc.id, parents=len(parents), children=0, deleted_existing=deleted
        )

    embeddings = embedder.embed_batch([normalizer(c.text) for c in children])
    store.add_chunks(parents, children, embeddings)
    logger.info(
        "live ingest: %s → %d parents / %d children (deleted_existing=%d)",
        doc.id, len(parents), len(children), deleted,
    )
    return LiveIngestResult(
        doc_id=doc.id,
        parents=len(parents),
        children=len(children),
        deleted_existing=deleted,
    )
