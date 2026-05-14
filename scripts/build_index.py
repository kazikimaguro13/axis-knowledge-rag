"""Build the ChromaDB index from a knowledge directory.

Two modes (spec_031):
    * ``--mode legacy``: file-level embedding (v0.6 behavior).
    * ``--mode parent_doc``: chunk each .md into H2-section parents +
      paragraph-level children, embed the children, and write parents to
      ``parents.json`` next to the Chroma directory.
    * ``--mode auto`` (default): pick based on ``config.yml`` →
      ``retrieval.parent_doc.enabled``.

Usage:
    python -m scripts.build_index ./examples/knowledge
    python -m scripts.build_index ./examples/knowledge --reset
    python -m scripts.build_index ./examples/knowledge --rebuild --mode parent_doc
"""

import argparse
import sys
from pathlib import Path

from backend.src.chunker import chunk_markdown
from backend.src.config import (
    configure_logging,
    load_app_config,
    load_axes_config,
    settings,
)
from backend.src.embedder import Embedder
from backend.src.loader import load_directory
from backend.src.normalizer import Normalizer
from backend.src.vector_store import VectorStore


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Build ChromaDB index from Markdown.")
    parser.add_argument("knowledge_dir", type=Path)
    parser.add_argument("--reset", action="store_true", help="Drop existing collection first")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Alias for --reset (matches spec_031 wording).",
    )
    parser.add_argument("--db-path", type=Path, default=settings.chroma_db_path)
    parser.add_argument(
        "--strict-integrity",
        action="store_true",
        help="Abort index build if broken refs are detected",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "legacy", "parent_doc"],
        default="auto",
        help="Indexing mode. 'auto' follows config.yml retrieval.parent_doc.enabled.",
    )
    args = parser.parse_args(argv[1:])

    import yaml

    try:
        with open("config.yml", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        config = {}

    app_cfg = load_app_config()
    if args.mode == "auto":
        mode = "parent_doc" if app_cfg.retrieval.parent_doc.enabled else "legacy"
    else:
        mode = args.mode

    normalizer = Normalizer.from_config(load_axes_config())
    docs = load_directory(args.knowledge_dir, normalizer=normalizer)

    if args.strict_integrity or config.get("integrity", {}).get("fail_on_broken", False):
        from backend.src.integrity import IntegrityChecker, format_report

        report = IntegrityChecker().check(docs)
        if report.has_errors:
            print(format_report(report), file=sys.stderr)
            print("Integrity check failed. Aborting.", file=sys.stderr)
            return 1

    if not docs:
        print("No documents found.", file=sys.stderr)
        return 1

    store = VectorStore(path=args.db_path)
    if args.reset or args.rebuild:
        store.reset()

    embedder = Embedder()

    if mode == "parent_doc":
        pd = app_cfg.retrieval.parent_doc
        parents_all = []
        children_all = []
        for d in docs:
            fm = {
                "title": d.title,
                "axes": d.axes,
                "normalized_axes": d.normalized_axes,
                "tags": d.tags,
                "refs": d.refs,
                "path": str(d.path),
            }
            ps, cs = chunk_markdown(
                d.id, d.normalized_body or d.body, fm,
                max_child_tokens=pd.max_child_tokens,
            )
            parents_all.extend(ps)
            children_all.extend(cs)

        if not children_all:
            print("No child chunks produced from corpus.", file=sys.stderr)
            return 1

        embeddings = embedder.embed_batch([c.text for c in children_all])
        store.add_chunks(parents_all, children_all, embeddings)

        print(
            f"Indexed (parent_doc) {len(docs)} docs → "
            f"{len(parents_all)} parents / {len(children_all)} children"
        )
        print(f"  → ChromaDB:   {args.db_path}")
        sidecar = args.db_path / "parents.json"
        if sidecar.exists():
            print(f"  → parents.json: {sidecar} ({sidecar.stat().st_size} bytes)")
    else:
        # body そのものではなく normalize 済みテキストを embed する。
        # 同じ semantic で書き方が異なる文書を近い位置に配置するため。
        embeddings = embedder.embed_batch([d.normalized_body for d in docs])
        store.upsert_many(docs, embeddings)
        print(f"Indexed (legacy) {len(docs)} documents into {args.db_path}")

    print(f"Total in collection: {store.count()}")
    print(f"Embedder mode: {'DUMMY' if embedder.is_dummy else 'GEMINI'}")
    print(f"Index mode:    {mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
