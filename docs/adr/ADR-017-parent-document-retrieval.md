# ADR-017: Parent Document Retrieval (Small-to-Big)

- **Date**: 2026-05-14
- **Status**: Accepted
- **Deciders**: 中島
- **Spec**: spec_031

## Context

v0.6 までは「`.md` ファイル 1 つ = 1 ドキュメント」として丸ごと埋め込んでいた。
これは実装はシンプルだが、長文ファイルでは局所的な質問にもファイル全体が hit するため、
検索の **再現率は高いが精度が低い** という問題があった。

特に `examples/knowledge/` の内、本文が 2,000 字を超えるファイルでは、
冒頭の H2 セクションに hit したのに別の H2 セクションの内容まで LLM プロンプトに混ざり、
出典リンク `[doc_NNN]` も粒度が粗くなって、ユーザーが「どの段落を見ればよいか」分かりづらくなる。

## Decision

検索粒度を「ファイル」から「H2 セクション」に下げる **Parent Document Retrieval (Small-to-Big)** を採用する。
具体的には:

1. **Chunker (`backend/src/chunker.py`)** を新設し、Markdown 本文を:
   - **parents**: H2 (`## ...`) 単位 (H2 がない場合は doc 全体を 1 parent)
   - **children**: parent 内部を H3+ / 段落 / 文末境界で分割した小ブロック (~256 token / 512 文字)
   に分割する。
2. **検索インデックス**: ChromaDB には **child だけ embedding** する。`parent_id` を child の metadata に持たせる。
3. **検索フロー**:
   - 上位 `top_k_children=20` の child を vector 検索で取得
   - `parent_id` でグルーピングし、最良スコアの child を持つ parent を上位 `top_n_parents=5` 件返す
4. **LLM コンテキスト**: 検索 hit の **parent 全文** を `build_context()` で連結 (`max_chars=8000` でトリム)
5. **parent の永続化**: ChromaDB ディレクトリ直下に `parents.json` として書き出し、起動時に lazy-load
6. **後方互換**: `config.yml > retrieval.parent_doc.enabled = false` にすれば v0.6 と同一挙動 (file-level)

## Alternatives

### (a) ファイル丸ごと (= 旧方式) — 却下

- 長文での精度低下が顕在化していた。
- 出典リンクの粒度がユーザー体験を損なう。

### (b) RecursiveCharacterTextSplitter (LangChain 流) — 却下

- 新規依存追加 (LangChain) になる → ADR-001 (LangChain 不採用) と整合しない。
- 文字数だけで切るので Markdown 構造 (H2/H3 の意味区切り) を捨ててしまう。
- 自前実装で 200 行未満で書けるため、依存を増やす理由がない。

### (c) Hierarchical Embeddings (parent も child も両方 embed) — 却下

- ストレージコスト 2 倍 + 埋め込み API コスト 2 倍。
- 検索フローが複雑化し、運用ログ・デバッグが難しくなる。
- 本プロジェクトの規模 (1k〜10k doc 想定) ではメリットが薄い。

### (d) 採用案 = parent JSON sidecar + child embedding only

- 埋め込みコストは旧方式と同等 (parent text は埋めない)。
- parent text の更新は JSON 書き換えだけで完結 (再 embedding 不要)。
- ChromaDB の collection はそのまま使え、移行コストが小さい。

## Consequences

### Positive

- 出典 `[parent_id]` が H2 セクション粒度になり、「どこを見ればよいか」が明確に。
- LLM に渡すコンテキストが構造的に閉じた塊 (H2 セクション本文) になり、文脈の途切れが減る。
- 既存 BM25 ハイブリッド (ADR-016) と併存可。BM25 は file-level スコア、parent への伝播は `max(parent_score)` で行う。

### Negative / Trade-off

- `data/parents.json` という追加成果物が生まれる。`scripts/build_index.py --rebuild --mode parent_doc` を一度実行する必要がある。
- `parent_doc.enabled=true` で `parents.json` が無いと **fallback 警告**を出して legacy モードで動作する (fail-fast にしないのは初回起動で UI が真っ白になるのを避けるため)。
- BM25 を child 化していないため、BM25 のスコアと vector スコアの粒度が異なる。
  → 重み調整が必要かは v0.7 リリース後に bench で検証 (現状 `bm25_weight=0.5` で回帰なし)。
- MCP の `sources` 配列で同じ `doc_id` (= file path) が複数回現れ得る (異なる H2 から hit した場合)。
  → `docs/mcp-server.md` に明記。

### 実装上のメモ

- parent_id 形式: `{doc_id}#{ascii-slug}`、CJK のみのタイトルは `{doc_id}#{md5[:8]}` フォールバック (Chroma metadata key は ASCII 安全である必要がある)。
- 文字数の token 換算は **2 文字 ≈ 1 token** (JP 平均) とラフに近似。Gemini text-embedding-004 上限 (2,048 tokens) を踏まえて `max_child_tokens=256` を default。
- child boundary は 文末 (`。` / `.` / `!` / `?`) に揃える。長文を途中で切らない。

## Status / Future work

- spec_034 候補: parent 単位での **再ランキング** (Cohere Rerank or LLM-as-Reranker)
- spec_036 候補: BM25 も child 化 (まずは A/B テスト)
- spec_039 候補: chunker を CST ベース (mistletoe 等) に置き換えて nested markdown 対応
