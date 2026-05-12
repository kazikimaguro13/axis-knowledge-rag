"""Build the ChromaDB index from a knowledge directory.

Usage:
    python -m scripts.build_index ./examples/knowledge
    python -m scripts.build_index ./examples/knowledge --reset
"""

import argparse
import sys
from pathlib import Path

from backend.src.config import configure_logging, settings
from backend.src.embedder import Embedder
from backend.src.loader import load_directory
from backend.src.vector_store import VectorStore


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Build ChromaDB index from Markdown.")
    parser.add_argument("knowledge_dir", type=Path)
    parser.add_argument("--reset", action="store_true", help="Drop existing collection first")
    parser.add_argument("--db-path", type=Path, default=settings.chroma_db_path)
    parser.add_argument(
        "--strict-integrity",
        action="store_true",
        help="Abort index build if broken refs are detected",
    )
    args = parser.parse_args(argv[1:])

    import yaml

    try:
        with open("config.yml", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        config = {}

    docs = load_directory(args.knowledge_dir)

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
    if args.reset:
        store.reset()

    embedder = Embedder()
    embeddings = embedder.embed_batch([d.body for d in docs])
    store.upsert_many(docs, embeddings)

    print(f"Indexed {len(docs)} documents into {args.db_path}")
    print(f"Total in collection: {store.count()}")
    print(f"Embedder mode: {'DUMMY' if embedder.is_dummy else 'GEMINI'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
