# Bridge spec INDEX

| #   | Created     | Project           | Title                                              | Status   | Result        |
| --- | ----------- | ----------------- | -------------------------------------------------- | -------- | ------------- |
| 001 | 2026-05-12  | axis-knowledge-rag | Day 1: プロジェクト初期化 + loader.py 実装         | done     | result_001.md |
| 002 | 2026-05-12  | axis-knowledge-rag | Day 2: embedder + vector_store + build_index       | partial  | result_002.md |
| 003 | 2026-05-12  | axis-knowledge-rag | Day 3: search.py (軸+ベクトル hybrid)              | done     | result_003.md |
| 004 | 2026-05-12  | axis-knowledge-rag | Day 4: rag.py (Claude API + 出典)                  | done     | result_004.md (main) |
| 005 | 2026-05-12  | axis-knowledge-rag | Day 5: Streamlit UI                                | done     | result_005.md (feat/spec_005-streamlit) |
| 006 | 2026-05-12  | axis-knowledge-rag | Day 6: Docker + サンプル 10本 + README v0.1        | done     | result_006.md (feat/spec_006-docker, force-pushed) |
| 007 | 2026-05-12  | axis-knowledge-rag | Day 7: v0.1.0 リリース (tag + GitHub Release)      | pending  | (未生成)      |
| 008 | 2026-05-12  | axis-knowledge-rag | Day 8: normalizer.py (NFKC + カナ + lowercase)     | done     | result_008.md (feat/spec_008-normalizer) |
| 009 | 2026-05-12  | axis-knowledge-rag | Day 9: normalizer を検索パイプライン統合           | done     | (dev-b, feat/spec_009-normalizer-integration) |
| 010 | 2026-05-12  | axis-knowledge-rag | Day 10: integrity.py (参照整合性)                  | done     | result_010.md (feat/spec_010-integrity) |
| 011 | 2026-05-12  | axis-knowledge-rag | Day 11: marker.py (AUTO_GENERATED ブロック)        | done     | result_011.md (feat/spec_011-marker) |
| 012 | 2026-05-12  | axis-knowledge-rag | Day 12: pytest 化 + GitHub Actions CI              | done     | (dev-d, feat/spec_012-pytest-ci) |
| 013 | 2026-05-12  | axis-knowledge-rag | Day 13: docs/ 整備 (architecture / ADR / API ref)  | done     | (dev-b, feat/spec_013-docs) |
| 014 | 2026-05-12  | axis-knowledge-rag | Day 14: v0.2.0 リリース                            | pending  | (未生成)      |
| 015 | 2026-05-12  | axis-knowledge-rag | Day 15: FastAPI (backend/api.py)                   | done     | (dev-d, feat/spec_015-fastapi) |
| 016 | 2026-05-12  | axis-knowledge-rag | Day 16: Next.js init + Tailwind                    | done     | (dev-b, feat/spec_016-nextjs-init) |
| 017 | 2026-05-12  | axis-knowledge-rag | Day 17: SearchBar / AxisFilter / ResultCard        | done     | (dev-b, feat/spec_017-components) |
| 018 | 2026-05-12  | axis-knowledge-rag | Day 18: AnswerPanel + streaming UI                 | done     | (dev-b, feat/spec_018-answer-panel) |
| 019 | 2026-05-12  | axis-knowledge-rag | Day 19: Docker 分割 (backend + frontend) + E2E     | done     | (dev-b, feat/spec_019-docker-split) |
| 020 | 2026-05-12  | axis-knowledge-rag | Day 20: README full + デモ GIF + docs 最終整理     | done     | (dev-d, feat/spec_020-readme-full) |
| 021 | 2026-05-12  | axis-knowledge-rag | Day 21: v0.3.0 リリース (フィナーレ)               | pending  | (未生成)      |
| 022 | 2026-05-13  | axis-knowledge-rag | Day 22 (bonus): MCP server 化 (axis_knowledge_rag_mcp) | done     | (dev-d, feat/spec_022-mcp-server) ⭐ |
| 023 | 2026-05-13  | axis-knowledge-rag | Day 23 (bonus #2): AI ingester (raw memo → YAML)    | done     | (dev-b, feat/spec_023-ingester) ⭐ |
| 024 | 2026-05-13  | axis-knowledge-rag | 総合コードレビュー (read-only, v0.1〜v0.4 全体)     | done     | result_024.md (B 判定、10 件指摘) |
| 025 | 2026-05-13  | axis-knowledge-rag | Doc 整合性パス (B→A 昇格、CC レビュー後)            | done     | result_025.md (8 commits) |
| 026 | 2026-05-13  | axis-knowledge-rag | Ingester 堅牢化 (二重スキャン+リトライ+pagination上限) | done     | result_026.md (dev-b, 5 commits) |
| 027 | 2026-05-13  | axis-knowledge-rag | MCP error sanitization (correlation id)             | done     | result_027.md (dev-d, 5 commits) |
| 028 | 2026-05-13  | axis-knowledge-rag | 再総合コードレビュー (B→A 判定確認、read-only)      | done     | result_028.md (A 判定 🏆) |
| 029 | 2026-05-14  | axis-knowledge-rag | BM25 ハイブリッド (3-way fusion + ADR-016)          | done     | (CC 実装、v0.6.0 リリース、169 tests PASS) |
| 030 | 2026-05-14  | axis-knowledge-rag | README 内部 TODO 除去 + Topics/About 設定           | done     | (Task 1/2 完了、3/4 は PAT スコープ不足で保留) |
| 031 | 2026-05-14  | axis-knowledge-rag | Parent Document Retrieval (Small-to-Big)            | pending  | (未生成、v0.7 コア 1/3) |
| 032 | 2026-05-14  | axis-knowledge-rag | Conversational RAG (履歴保持チャット UI)            | pending  | (未生成、v0.7 コア 2/3) |
| 033 | 2026-05-14  | axis-knowledge-rag | RAGAS CI/CD (LLM-as-a-Judge 自動評価)               | pending  | (未生成、v0.7 コア 3/3) |
| 034 | 2026-05-14  | axis-knowledge-rag | In-Text Citation Highlighting (Gemini ⑧)            | pending  | (未生成、v0.7 サブ、spec_031/032 後) |
| 035 | 2026-05-14  | axis-knowledge-rag | Time-Weighted Decay (Gemini ⑭、opt-in)              | pending  | (未生成、v0.7 サブ、spec_031 後) |

<!--
記入例:
| 001 | 2026-05-05  | myproj  | 認証基盤導入                    | done     | result_001.md |
| 002 | 2026-05-05  | myproj  | login UI 実装                   | pending  | (未生成)      |

Status:
  pending     - 着手前
  in_progress - 実行中
  done        - 完了、レビュー済
  blocked     - Open questions あり、ユーザー判断待ち
  superseded  - 別 spec で代替されたため廃案
-->
