# Changelog

## [Unreleased]

### Day 9 (2026-05-13)
- backend/src/loader.py: Document に `normalized_title` / `normalized_body` / `normalized_axes` / `normalized_tags` を追加。生フィールドは据え置きで後方互換 (normalizer=None で空のまま)
- backend/src/loader.py: `load_document` / `load_directory` が optional の `Normalizer` を受け取る
- backend/src/vector_store.py: `_flatten_axes_with_norm` 追加、metadata に `title_norm` / `tags_norm` / `axis_<key>_norm` を併記
- backend/src/search.py: `SearchEngine` が `Normalizer` を保持。query と filters を normalize したうえで `axis_*_norm` を where 句に使う `_build_where_norm` を新設
- backend/src/search.py: `_to_results` が `_norm` サフィックス付きキーを除外して raw axes のみ返す
- scripts/build_index.py: `Normalizer.from_config(load_axes_config())` を作成、`normalized_body` を embed 対象に
- streamlit_app.py: `get_pipeline()` で Normalizer を SearchEngine に注入
- backend/tests/test_integration_normalization.py: 8 ケースの End-to-End normalization 統合テスト (全角/ひらがな/大文字クエリ → 半角/カタカナ/小文字 index のヒット、axis_*_norm 併記検証、後方互換)
- backend/tests/test_vector_store.py: `_fresh_store()` ヘルパで Chroma EphemeralClient のプロセス内 state 共有による flakiness を解消
- backend/tests/test_search.py: docs を Normalizer 経由で構築、新しい `axis_*_norm` where 句に追従

### Day 11 (2026-05-13)
- backend/src/marker.py: AUTO_GENERATED block handling — extract_blocks, update_block, strip_blocks, validate_balance
- backend/src/marker.py: CLI entrypoint (`python -m backend.src.marker`) with --list / --update / --strip / --validate modes
- backend/tests/test_marker.py: 31 tests covering extract, update, strip, validate, nested DOTALL, CRLF, CLI modes
- examples/knowledge/01-rag-patterns.md: demo AUTO_GENERATED summary block (placeholder for Day 13 build script)
- docs/marker.md: design rationale, ASCII diagram, API reference, CLI usage, recommended block names

### Day 10 (2026-05-12)
- backend/src/integrity.py: IntegrityChecker with broken_refs, orphan_docs, cycle detection
- backend/src/integrity.py: CLI entrypoint (`python -m backend.src.integrity`) with --json and --strict flags
- backend/tests/test_integrity.py: 5 tests covering no-error, broken refs, orphans, cycles, self-loops
- scripts/build_index.py: --strict-integrity flag aborts index build on broken refs
- docs/integrity.md: architecture explanation, CLI usage, FAQ, future roadmap

### Day 8 (2026-05-12)
- backend/src/normalizer.py: Japanese text normalizer (NFKC + katakana→hiragana + lowercase), standard library only (unicodedata)
- backend/src/normalizer.py: `normalize_text` pure function + `Normalizer` class (config.yml-driven)
- backend/tests/test_normalizer.py: 16 cases covering NFKC, kana, lowercase, idempotency, options toggle
- docs/normalizer.md: pipeline explanation, edge cases, future extensions
- config.yml: added `lowercase: true` to normalization section

### Day 6 (2026-05-13)
- Dockerfile: python:3.11-slim base, `pip install -e .`, build_index + streamlit run on CMD
- docker-compose.yml: app service (ports 8501:8501, env_file .env, chroma-data volume, examples/knowledge ro mount)
- .dockerignore: exclude .git / _ai_workspace / docs / __pycache__ / .chromadb / .env / node_modules
- examples/knowledge/06-10: 5 new sample knowledge docs (prompt-injection / evaluation-metrics / tooling-comparison / cost-estimation / future-roadmap)
- README.md: v0.1 rewrite — shields.io badges, demo placeholder, features/quickstart/manual setup/roadmap/architecture
- Note: doc_005 → doc_999 broken ref intentionally retained for Week 2 integrity demo

### Day 5 (2026-05-12)
- streamlit_app.py: Streamlit UI with sidebar axis filter, search bar, answer panel, result cards
- streamlit_app.py: @st.cache_resource for SearchEngine and RAGPipeline initialization
- backend/src/config.py: `load_axes_config()` helper to read config.yml
- examples/screenshots/: checklist for README v0.1 demo capture
- Dependencies: streamlit>=1.37.0 added

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
