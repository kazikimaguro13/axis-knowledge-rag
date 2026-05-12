# Changelog

## [Unreleased]

### Day 2 (2026-05-12)
- backend/src/embedder.py: Gemini text-embedding-004 wrapper with deterministic dummy fallback (CI / offline dev)
- backend/src/vector_store.py: ChromaDB PersistentClient wrapper (axis-aware metadata flattening)
- scripts/build_index.py: index a knowledge directory into `.chromadb/`
- backend/src/config.py: add `COLLECTION_NAME = "axis_knowledge"` constant
- Dependencies: google-generativeai>=0.7.0, chromadb>=0.5.0
- Smoke tests for embedder and vector_store (assert-based, in-memory Chroma)

### Day 1 (2026-05-12)
- Initial project structure
- backend/src/loader.py: Markdown + YAML frontmatter loader
- 5 sample knowledge documents under examples/knowledge/
