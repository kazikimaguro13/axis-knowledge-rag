# Changelog

## [Unreleased]

### Day 4 (2026-05-12)
- backend/src/rag.py: RAGPipeline (Claude API + DUMMY fallback) with citation extraction via `[doc_NNN]` regex
- backend/src/rag.py: CLI entrypoint (`python -m backend.src.rag`) with axis filters
- backend/tests/test_rag.py: 8 DUMMY-mode integration tests (all pass)
- Dependencies: anthropic>=0.34.0 added to requirements.txt and pyproject.toml
- Model: claude-3-5-sonnet-20241022, overridable via CLAUDE_MODEL env var
- DUMMY mode: activated when ANTHROPIC_API_KEY is unset (consistent with Embedder pattern)

### Day 3 (2026-05-12)
- backend/src/search.py: SearchEngine (hybrid axis+vector search) with SearchResult dataclass
- backend/src/search.py: CLI entrypoint (`python -m backend.src.search`)
- backend/tests/test_search.py: 8 integration tests using in-memory VectorStore + force_dummy Embedder
- Verified: Chroma 0.5 `$and` multi-key filter works correctly
- Note: score=0.0 in DUMMY mode is expected (hash-derived embeddings have near-zero cosine similarity)

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
