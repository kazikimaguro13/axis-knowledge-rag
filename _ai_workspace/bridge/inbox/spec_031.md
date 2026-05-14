# spec_031: Parent Document Retrieval (Small-to-Big 検索)

- **Author**: Cowork (中島)
- **Created**: 2026-05-14
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: v0.6 (BM25 hybrid) の次に積む v0.7 コア 1/3。spec_032 (Conversational RAG) / spec_033 (RAGAS CI) と並行可能

## 1. 目的

v0.6 までは「.md ファイル 1 つ = 1 ドキュメント」を埋め込んでいた。長文ファイルでは局所的な質問にもファイル全体が hit してしまい、検索精度が落ちる (再現率は高いが精度が低い)。

これを **Parent Document Retrieval (Small-to-Big)** で改善する: 検索時は **小さなチャンク (= child)** をインデックス対象にして精密に hit させ、LLM に渡すコンテキストは **元の親 (= parent)** 単位に復元してから渡す。Hit した child の親をユニーク化して上位 N 件を返すことで、関連箇所がページのどこにあっても親ドキュメント丸ごとが LLM に供給される。

```
[現状 v0.6.0]
- loader.py: .md ファイル全文を 1 Document として返す
- vector_store: 1 ファイル = 1 embedding
- 長文ファイル (>2000 字) は粒度が粗く、特定段落の検索で hit しても余計な文脈が混ざる
- search の召喚効率が悪い

[変更後 v0.7 (spec_031)]
- chunker.py 新設: .md を H2 単位 (parent) + パラグラフ単位 (child) に分割
- ChromaDB には child だけ embedding (parent_id を metadata に持つ)
- 検索時: top_k_children=20 → group by parent_id → top_n_parents=5
- LLM への文脈: parent 本文 (= H2 セクション本文 or 短いファイルは全文)
- 後方互換: config.yml の retrieval.parent_doc.enabled で ON/OFF
```

## 2. 制約

### 触ってよいファイル

- `backend/src/chunker.py` — **新規** (markdown 分割ロジック)
- `backend/src/loader.py` — chunker と連携するための返却型拡張 (parent / child を分離して返す API 追加)
- `backend/src/vector_store.py` — `add_chunks()` / `query_with_parents()` の追加。既存 `add_documents()` は維持
- `backend/src/search.py` — `parent_doc.enabled` フラグ分岐、child→parent 復元
- `backend/src/rag.py` — context 組み立てを parent 単位に
- `scripts/build_index.py` — 新 chunking モード対応
- `backend/tests/test_chunker.py` — **新規**
- `backend/tests/test_loader.py` / `test_vector_store.py` / `test_search.py` / `test_rag.py` — 既存テストに parent retrieval ケース追加
- `config.yml` — `retrieval.parent_doc.{enabled, chunk_strategy, max_child_tokens, top_k_children, top_n_parents}`
- `backend/src/config.py` — 上記キーの読み込み
- `docs/adr/ADR-017-parent-document-retrieval.md` — **新規**
- `docs/architecture.md` — 検索フローの図/節を更新
- `README.md` — Features に 1 行追加、bench 結果を後段で記載できる枠を確保
- `CHANGELOG.md` — Day 31 追記
- `mcp_server/server.py` — `axis_search` / `axis_answer` で parent 単位の sources を返すように調整 (互換維持: sources の型は変えない)

### 触ってはいけないもの

- `backend/src/bm25.py` / `bm25_index.py` (v0.6 で追加されたもの) — BM25 は child レベルで動かす方針だが、本 spec の範囲外。後続 spec で BM25 も chunk 化検討
- `backend/src/ingester.py` — Ingester は記事生成側、検索とは独立
- `backend/src/normalizer.py` / `integrity.py` / `marker.py`
- `frontend/` — UI は次 spec (spec_032) で触る
- `_ai_workspace/`
- 既存の `add_documents()` シグネチャ (後方互換)

### コーディングルール

- chunker は **純粋関数** で副作用なし (テストしやすく)
- LangChain / llama-index は **使わない** (本リポの差別化点なので OSS 自前路線を維持)
- 既存パターンに倣う: dataclass / type hint / ruff 緑
- 新規依存追加なし (markdown 分割は標準ライブラリ + 既存の正規表現で実装可能)
- ChromaDB collection は既存と同じものを使う (再構築は許容、`scripts/build_index.py --rebuild`)

### デプロイ

- 本 spec は実装のみ。tag / Release は spec_031/032/033 揃ったあと v0.7.0 で一括

## 3. やってほしいこと

### 3-1. Chunker 実装 (`backend/src/chunker.py`)

#### 設計

```python
"""Parent-child chunking for Markdown documents.

Parents are H2 sections (or whole doc if no H2 present).
Children are sub-blocks within each parent, split at:
  1. H3+ headings
  2. paragraph boundaries (blank line)
  3. Hard cap of max_child_tokens (default 256 tokens ~ 1000 chars JP)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterator
import re
import uuid


@dataclass(frozen=True)
class ParentChunk:
    """An H2-level (or whole-doc) chunk used as LLM context."""
    parent_id: str          # deterministic: {doc_id}#{h2_slug or "root"}
    doc_id: str             # original .md path (relative to knowledge/)
    title: str              # H2 heading text (or doc title if root)
    text: str               # full parent text including children
    metadata: dict          # YAML frontmatter from parent doc


@dataclass(frozen=True)
class ChildChunk:
    """A small chunk used as the embedding/search unit."""
    child_id: str           # deterministic: {parent_id}#c{index}
    parent_id: str
    doc_id: str
    text: str
    token_estimate: int     # rough JP-aware estimate (len(text) // 2)
    metadata: dict          # inherited from parent (axes, etc.)


def chunk_markdown(
    doc_id: str,
    body: str,
    frontmatter: dict,
    *,
    max_child_tokens: int = 256,
) -> tuple[list[ParentChunk], list[ChildChunk]]:
    """Split a markdown body into parent (H2) chunks and child sub-chunks."""
    ...
```

#### 実装ポイント

- **H2 分割**: `re.split(r"^(##\s+.+)$", body, flags=re.MULTILINE)` で `(text_before, h2_line, ...)` のパターンに分解
- H2 が 0 個: parent = doc 全体 (title はフロントマターの title)
- H2 内部: H3 / `\n\n` / 文字数で child を作る
- child は **256 token (~1000 文字)** 上限。境界は文末 (`。` `.`) で切る
- parent_id は `f"{doc_id}#{slug(h2_title)}"`、ASCII 化は `unicodedata.normalize("NFKD", ...).encode("ascii","ignore")` → だめなら `hashlib.md5(title.encode()).hexdigest()[:8]`
- child は **空文字や見出しだけのもの** はスキップ
- 返り値の parents / children は 1:N で必ず整合 (orphan child を作らない)

#### スケッチ

```python
def chunk_markdown(doc_id, body, frontmatter, *, max_child_tokens=256):
    h2_sections = _split_h2(body, frontmatter)
    parents: list[ParentChunk] = []
    children: list[ChildChunk] = []
    for sec_title, sec_body in h2_sections:
        parent_id = _make_parent_id(doc_id, sec_title)
        parents.append(ParentChunk(
            parent_id=parent_id,
            doc_id=doc_id,
            title=sec_title,
            text=sec_body,
            metadata=dict(frontmatter),
        ))
        for i, chunk_text in enumerate(_split_children(sec_body, max_child_tokens)):
            children.append(ChildChunk(
                child_id=f"{parent_id}#c{i:03d}",
                parent_id=parent_id,
                doc_id=doc_id,
                text=chunk_text,
                token_estimate=len(chunk_text) // 2,
                metadata=dict(frontmatter),
            ))
    return parents, children
```

### 3-2. Vector store 拡張 (`backend/src/vector_store.py`)

既存の `add_documents()` は **維持**。新規メソッドを追加:

```python
def add_chunks(self, parents: list[ParentChunk], children: list[ChildChunk]) -> None:
    """Embed children only; persist parents as in-memory dict + JSON sidecar."""
    self._parents = {p.parent_id: p for p in parents}
    self._persist_parents()  # writes data/parents.json
    self._collection.add(
        ids=[c.child_id for c in children],
        embeddings=self._embedder.embed_batch([c.text for c in children]),
        metadatas=[{"parent_id": c.parent_id, "doc_id": c.doc_id, **c.metadata} for c in children],
        documents=[c.text for c in children],
    )

def query_with_parents(
    self,
    query: str,
    *,
    top_k_children: int = 20,
    top_n_parents: int = 5,
    where: dict | None = None,
) -> list[ParentChunk]:
    """Retrieve top children, group by parent_id, return top N unique parents."""
    res = self._collection.query(
        query_embeddings=[self._embedder.embed_query(query)],
        n_results=top_k_children,
        where=where,
    )
    seen: dict[str, float] = {}
    for child_meta, dist in zip(res["metadatas"][0], res["distances"][0], strict=True):
        pid = child_meta["parent_id"]
        score = 1.0 - dist  # cosine
        if pid not in seen or score > seen[pid]:
            seen[pid] = score
    top_parents = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:top_n_parents]
    return [self._parents[pid] for pid, _ in top_parents if pid in self._parents]
```

**parent 永続化**: `data/parents.json` (索引と同じディレクトリ)。フォーマット:

```json
{
  "version": 1,
  "parents": {
    "knowledge/01-rag-patterns.md#root": {
      "doc_id": "knowledge/01-rag-patterns.md",
      "title": "RAG Patterns",
      "text": "...",
      "metadata": {"category":"技術記事", ...}
    }
  }
}
```

build_index 時に書き出し、起動時に lazy-load。

### 3-3. Search 統合 (`backend/src/search.py`)

```python
def search(query: str, axes: dict | None = None, *, k: int = 5) -> list[SearchHit]:
    cfg = get_config()
    if cfg.retrieval.parent_doc.enabled:
        parents = vs.query_with_parents(
            query,
            top_k_children=cfg.retrieval.parent_doc.top_k_children,
            top_n_parents=k,
            where=_axes_to_where(axes),
        )
        return [SearchHit(
            doc_id=p.doc_id,
            title=p.title,
            text=p.text,
            score=1.0,  # parent-level score; spec_032+ で再ランキング検討
            metadata=p.metadata,
        ) for p in parents]
    # 既存 path (file-level)
    return _legacy_search(query, axes, k=k)
```

**BM25 ハイブリッドとの併存**: v0.6 で導入した 3-way fusion (vector + bm25 + axis) は **本 spec では vector path のみ** parent doc 化する。BM25 を child 化するのは v0.8 候補 (spec_036 で議論)。フラグ ON 時の挙動:

- vector スコア: parent 単位 (本 spec で実装)
- bm25 スコア: file 単位 (既存)
- axis スコア: file 単位 (既存)

→ 3-way fusion は `parent.doc_id` をキーに集約してから fuse。1 ファイル内に複数 parent が hit した場合は **max(parent_score)** を採用。実装は `search.py` の融合関数を修正。

### 3-4. RAG context 組み立て (`backend/src/rag.py`)

```python
def build_context(hits: list[SearchHit], *, max_chars: int = 8000) -> str:
    """Concatenate parent texts with title and source headers."""
    out = []
    used = 0
    for i, h in enumerate(hits, 1):
        block = f"## 出典 {i}: {h.title}\n(file: {h.doc_id})\n\n{h.text}\n\n"
        if used + len(block) > max_chars:
            break
        out.append(block)
        used += len(block)
    return "".join(out)
```

`max_chars` は Claude 3.5 Haiku で安全な 8000 字を default。設定化:
`config.yml > rag.context_max_chars`。

### 3-5. config.yml 拡張

```yaml
retrieval:
  parent_doc:
    enabled: true              # v0.7 default ON
    chunk_strategy: "h2"       # h2 | h2+paragraph (将来拡張)
    max_child_tokens: 256
    top_k_children: 20
    top_n_parents: 5
  bm25:
    # (v0.6 で既出のキーを維持)

rag:
  context_max_chars: 8000
```

`backend/src/config.py` の Pydantic モデル (or dataclass) に同上のフィールド追加。default を Python 側にも書いて、`config.yml` 無くても動くようにする (既存テスト互換)。

### 3-6. Index rebuild フロー

`scripts/build_index.py` に `--mode {legacy,parent_doc}` フラグ追加 (default は config.yml の `retrieval.parent_doc.enabled` に従う)。

```bash
# v0.7 標準フロー
python scripts/build_index.py --rebuild --mode parent_doc
# → data/chroma/ の collection 再構築 + data/parents.json 作成
```

`data/parents.json` が存在しないのに parent_doc.enabled=true で起動した場合は **fail-fast** (RuntimeError) で `--rebuild` を促す。

### 3-7. MCP server 経由 (`mcp_server/server.py`)

`axis_search` と `axis_answer` の戻り値型 (sources の構造) は **変えない**。

- 既存: `sources: [{doc_id, title, score}]` (file 単位)
- 新動作: 各 source は parent 単位 (`doc_id` + `title` が parent.title)。1 ファイル内に複数 parent が出ることがあるので **doc_id が重複し得る** ことに注意。MCP クライアント (例: Claude Desktop) は source list を表示するだけなので互換性 OK。

ドキュメント (`docs/mcp-server.md`) に「v0.7 以降、1 ファイルから複数の parent (H2 section) が返り得る」と明記。

### 3-8. テスト (`backend/tests/test_chunker.py` 新規)

- `test_chunk_no_h2_returns_single_parent`: H2 なしのドキュメント → parents=1, children>=1
- `test_chunk_with_h2_splits_correctly`: 3 つの H2 → parents=3
- `test_child_token_cap`: 長文 paragraph が max_child_tokens で分割される
- `test_child_boundary_respects_sentence_end`: 句点で切れる (途中で切れない)
- `test_parent_text_reconstruction`: parent.text = sum of children.text (空白除いた整合性)
- `test_parent_id_deterministic`: 同じ入力 → 同じ parent_id
- `test_orphan_child_never_generated`: すべての child.parent_id が parents に存在

`backend/tests/test_search.py` 既存テストに `parent_doc_enabled=True` 分岐を追加 (fixture で config を差し替え)。

カバレッジ目標: **chunker.py 95% / vector_store.py 全体 80% 維持**。

### 3-9. ADR-017

`docs/adr/ADR-017-parent-document-retrieval.md`:

- Context: v0.6 までの粒度問題
- Decision: H2 単位 parent + paragraph 単位 child、ChromaDB で child のみ embedding、parent は JSON sidecar
- Alternatives:
  - (a) ファイル丸ごと (= 旧方式) → 却下: 精度低下
  - (b) RecursiveCharacterTextSplitter (LangChain 流) → 却下: 依存追加 + markdown 構造を捨てる
  - (c) Hierarchical Embeddings (parent も埋め込む) → 却下: コストと管理複雑
  - (d) 採用案
- Consequences: parents.json の存在前提、build_index 再実行が必要、BM25 はまだ file 単位

### 3-10. 動作確認

```bash
cd ~/projects/axis-knowledge-rag
git checkout -b feat/spec_031-parent-doc-retrieval

# Lint / Type
ruff check .
mypy backend/src/chunker.py backend/src/vector_store.py

# テスト
python3 -m pytest -q
python3 -m pytest -q --cov=backend/src --cov-report=term-missing | tail -30

# Index rebuild
python scripts/build_index.py --rebuild --mode parent_doc
ls -la data/parents.json

# API smoke
uvicorn backend.src.api:app --port 8000 &
sleep 3
curl -s -X POST http://localhost:8000/api/search -H 'Content-Type: application/json' \
  -d '{"query": "RAG とは何か", "top_k": 5}' | jq '.hits[].title'
# → parent_doc.enabled=true なら H2 単位の title が複数返る想定
kill %1
```

### 3-11. コミット粒度

1. `feat(chunker): add Markdown H2-parent / paragraph-child chunking module`
2. `test(chunker): cover edge cases (no H2, long paragraphs, deterministic IDs)`
3. `feat(vector_store): add_chunks() and query_with_parents() with parents.json sidecar`
4. `feat(config): add retrieval.parent_doc.* keys + Pydantic schema`
5. `feat(search): branch on parent_doc.enabled, integrate with BM25 hybrid fusion`
6. `feat(rag): build_context() from parent texts with citation headers`
7. `feat(build_index): --mode parent_doc support and rebuild flow`
8. `feat(mcp): emit parent-level sources via existing schema (no breaking change)`
9. `docs: ADR-017 + architecture update + README feature line`
10. `chore: CHANGELOG Day 31`

`git push -u origin feat/spec_031-parent-doc-retrieval`

### 3-12. result_031.md に書くこと

- chunker の単体テストでの parent / child 分布 (sample 5 docs での平均値)
- index rebuild 後の collection 件数 (旧 vs 新)
- /api/search サンプル比較 (同じクエリで旧 file 単位 vs 新 parent 単位の title list)
- ruff / pytest / coverage
- 既存 169 tests が全部緑か (+新規 chunker tests 数)

## 4. 成功条件

- [ ] `chunker.py` 新規、parent / child を一貫生成
- [ ] `data/parents.json` が生成され、起動時にロード可能
- [ ] `parent_doc.enabled=true` でも `=false` でも検索が動く (後方互換)
- [ ] BM25 ハイブリッドと併用可 (3-way fusion が parent 単位で動作)
- [ ] 既存 169 tests 緑、新規 chunker tests >=7 件、合計 >=176 PASS
- [ ] カバレッジ 87% 維持 or 改善
- [ ] ADR-017 / architecture.md / README / CHANGELOG 更新
- [ ] MCP の sources 型は変えず、parent 単位で返る
- [ ] git push 完了

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_031.md`

## 6. 質問があるとき

- **chunk_strategy** を `h2` だけにしたが、H1 のみの doc が examples/ にあるか? あれば fallback ルール (H1 を parent に格上げ) を実装。なければ「H2 が無ければ doc 全体を parent に」のみで OK
- **parents.json のサイズ**: examples/knowledge/ 全部で何 KB になるか確認。10MB 超えたら sqlite 化検討 (本 spec では JSON のままで OK、警告だけ出す)
- **BM25 の挙動**: file 単位 BM25 と parent 単位 vector を fusion した時の重み再調整は必要か? config.yml の `retrieval.bm25.weight` はそのままで OK と想定 (回帰なければ)。回帰したら baseline 値を 0.05 下げる程度に留め、根拠を ADR-017 に追記

迷ったら `result_031.md` の Open questions に書いて `status: blocked` で終了。

## 7. 補足

### 設計の意図

- LangChain を使わない方針を維持。chunker は ~200 行で書ける
- parent を JSON sidecar にしたのは、ChromaDB に冗長な embedding を持たせない / parent text の更新が embedding 不要

### 将来の拡張余地

- spec_034 候補: parent 単位で再ランキング (Cohere Rerank or LLM-as-Reranker)
- spec_036 候補: BM25 も child 化 (まずは A/B テスト)
- spec_039 候補: chunker を CST ベース (mistletoe 等) に置き換えて network-deep markdown 対応
