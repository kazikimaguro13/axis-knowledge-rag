# Changelog

## [Unreleased]

### Day 22 (2026-05-13) — MCP server 化 (spec_022)
- mcp_server/__init__.py: 新規 (package marker)
- mcp_server/__main__.py: 新規。`python -m mcp_server` エントリポイント
- mcp_server/schemas.py: Pydantic v2 入力モデル (SearchInput / AnswerInput / ListAxesInput / CheckIntegrityInput / ListDocumentsInput) + ResponseFormat enum
- mcp_server/formatters.py: Markdown / JSON 整形ヘルパー (search / answer / axes / integrity / documents)
- mcp_server/server.py: FastMCP ベース MCP サーバー本体 — 5 read-only tools (axis_search / axis_answer / axis_list_axes / axis_check_integrity / axis_list_documents), lazy singleton (_get_engine / _get_rag), stdio transport 対応 (logging → stderr)
- mcp_server/tests/test_server.py: pytest smoke tests 18 件 — 全 5 tools の markdown/json 両モード、pagination、lazy init、DUMMY モードのみ使用 (CI は API キーなし)
- pyproject.toml: `mcp>=1.2.0` を dependencies に追加、`[project.scripts]` に `axis-knowledge-rag-mcp` 登録、`setuptools.packages.find` に `mcp_server*` 追加、pytest testpaths に `mcp_server/tests` 追加
- README.md: MCP server セクション追加 (Quickstart 直下) — Claude Desktop 設定例、tool 一覧表、docs/mcp-server.md リンク; ロードマップに v0.4.0 ✅ 追加
- docs/mcp-server.md: 新規 — 動機・アーキテクチャ・5 tools 詳細仕様 (I/O サンプル) / Claude Desktop / Cowork / mcp-cli 組み込み手順 / DUMMY モード試験手順 / 既知制約 / 将来計画
- docs/INDEX.md: mcp-server.md エントリ追加
- examples/claude_desktop_config.json: 新規。Claude Desktop 組み込み設定例
- mcp>=1.2.0 (実インストール: 1.27.1)

### Day 20 (2026-05-13)
- README.md: v0.3 全面改稿 — shields.io バッジ (Version 0.3.0 / Next.js 14 追加)、デモ GIF placeholder、Next.js + FastAPI アーキ図 (ASCII)、デモ GIF 取得チェックリスト、ロードマップ v0.1〜v0.3 全 ✅
- docs/architecture.md: v0.3 構成に更新 — Next.js 14 + FastAPI の ASCII コンポーネント図、Mermaid フロー図、コンポーネント責務一覧 (backend/frontend 両方)、v0.3 Docker Compose 構成
- docs/design-decisions.md: ADR-013 (疑似ストリーミング typewriter)、ADR-014 (Streamlit を deprecated せず残す)、ADR-015 (Docker multi-stage frontend slim 化) を追加
- docs/api-reference.md: 全 4 endpoint を最終版に整備 — エラーレスポンス仕様、全フィールド説明、起動方法追記
- docs/deployment.md: 新規 — Local Docker / ChromaDB バックアップ / Fly.io / Cloud Run / TLS プロキシ / CI/CD 構成
- docs/portfolio-notes.md: 新規 — ES / 履歴書記述用素材集 (使用技術 / 成果物概要 / 工夫した点 / 数字まとめ / 面接 Q&A)

### Day 15 (2026-05-13)
- backend/src/schemas.py: Pydantic v2 schemas — HealthResponse, AxisDef, AxesResponse, SearchRequest, SearchResultPayload, SearchResponse, AnswerRequest, AnswerResponse
- backend/src/api.py: FastAPI app with lifespan init (SearchEngine + RAGPipeline 1回のみ), 4 endpoints: GET /api/health, GET /api/axes, POST /api/search, POST /api/answer
- backend/src/api.py: CORS middleware (localhost:3000, localhost:8501), Swagger UI at /api/docs
- backend/tests/test_api.py: 4 TestClient tests (health, search_empty, answer_dummy, axes) — all PASS
- backend/requirements.txt + pyproject.toml: fastapi>=0.115.0, uvicorn[standard]>=0.30.0 追加
- docs/api-reference.md: 4 endpoint の仕様、起動方法、CORS 設定を記載

### Day 12 (2026-05-13)
- pyproject.toml: add `[project.optional-dependencies].dev` with pytest>=8, pytest-cov>=5, ruff>=0.5
- pyproject.toml: add `[tool.pytest.ini_options]`, `[tool.coverage.run/report]`, `[tool.ruff.lint]` sections
- backend/tests/conftest.py: shared fixtures — dummy_embedder, in_memory_store (tmp_path-isolated), search_engine, sample_documents
- backend/tests/test_*.py: convert all 8 test files to pytest style; remove __main__ runners
- backend/tests/test_normalizer.py: 15-case parametrize table + 4-case query_matches_index parametrize
- backend/tests/test_marker.py: parametrize for invalid-name and append-newline variants
- backend/src/*.py + streamlit_app.py: ruff auto-fix (UP035, F401, B905, SIM105)
- .github/workflows/ci.yml: push/PR → ruff check + pytest --cov-fail-under=70, matrix py311/py312
- .github/workflows/docker.yml: push/PR → Docker build-only with GHA layer cache
- Coverage: 72.49% (70% threshold met), 90 tests all PASS

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
