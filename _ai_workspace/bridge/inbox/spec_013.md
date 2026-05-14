# spec_013: Day 13 — docs/ 整備 (architecture, design-decisions, ADR)

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜012, `docs/spec-v2.md` Day 13 行

## 1. 目的

```
[現状]
- README.md は v0.1.0 版で「何が動くか」は分かる
- 設計判断、アーキ全体像、API リファレンスがバラけている (normalizer.md / integrity.md / marker.md は単機能解説のみ)
- 採用担当者がリポジトリを開いた時に「設計の深さ」「業務級の意思決定プロセス」が一目で伝わらない

[変更後]
- `docs/architecture.md` — システム全体アーキ図 (ASCII or Mermaid) + データフロー + コンポーネント責務一覧
- `docs/design-decisions.md` — ADR (Architecture Decision Records) 形式で 8〜12 個の主要判断を集約
- `docs/api-reference.md` — 各モジュールの public API のリファレンス (sphinx 不要、手書き Markdown でしっかり書く)
- 各機能 docs (normalizer/integrity/marker) も Day 13 で目線揃え、必要なら章立て統一
- docs/INDEX.md — docs フォルダ全体の目次
```

採用担当者にとって「**設計判断を言語化できるエンジニア**」というアピールが直接できるのがこの Day。

## 2. 制約

### 触ってよいファイル

- `docs/architecture.md` — 新規
- `docs/design-decisions.md` — 新規
- `docs/api-reference.md` — 新規
- `docs/INDEX.md` — 新規
- `docs/normalizer.md` `docs/integrity.md` `docs/marker.md` — 既存、章立てを統一する微修正のみ
- `README.md` — `docs/` へのリンク追加
- `CHANGELOG.md`

### 触ってはいけないもの

- `docs/spec-v2.md` — Cowork 管轄
- ソース本体 (リファレンス書くために読むのは OK、変更禁止)
- `_ai_workspace/`

### コーディングルール

- 各 ADR は標準フォーマット (Context / Decision / Consequences / Alternatives / Status)
- ASCII 図優先、Mermaid 補助 (GitHub レンダリング前提)
- API リファレンスは `モジュール名 → クラス/関数 → シグネチャ → 使用例` の階層

## 3. やってほしいこと

### 3-1. `docs/architecture.md`

構成:

1. **概要** (3-4 文)
2. **コンポーネント図** (ASCII):
   ```
   ┌─────────────┐    ┌──────────────┐    ┌─────────────┐
   │  Markdown   │ -> │  loader.py   │ -> │  Document   │
   │  (frontmat) │    │              │    │  (dataclass)│
   └─────────────┘    └──────┬───────┘    └──────┬──────┘
                             │                    │
                       normalizer.py        embedder.py
                             │                    │
                             ▼                    ▼
                       (Document.normalized_*) (768-dim vec)
                             │                    │
                             └────────┬───────────┘
                                      ▼
                              ┌──────────────┐
                              │ vector_store │  ChromaDB
                              │  (.chromadb) │  PersistentClient
                              └──────┬───────┘
                                     ▲
                       ┌─────────────┼─────────────┐
                       │             │             │
                  ┌────┴────┐  ┌────┴─────┐  ┌────┴───┐
                  │ search  │  │  rag.py  │  │  CLI   │
                  │ Engine  │  │  Claude  │  │        │
                  └─────────┘  └──────────┘  └────────┘
                       │             │             │
                       └─────────────┼─────────────┘
                                     ▼
                            ┌──────────────┐
                            │ Streamlit UI │
                            └──────────────┘
   ```
3. **データフロー** (Index time / Query time / Update time の 3 シナリオ)
4. **コンポーネント責務一覧** (テーブル形式: モジュール / 責務 / 依存 / 不変条件)
5. **テストアーキテクチャ** (pytest + fixtures, DUMMY モードの位置づけ)
6. **デプロイメント** (Docker compose 構成、永続化される data)

### 3-2. `docs/design-decisions.md` (ADR 集約)

形式の例:

```markdown
# Architecture Decision Records

## ADR-001: LangChain / LlamaIndex を使わず RAG を自前実装する

- **Date**: 2026-05-12
- **Status**: Accepted
- **Deciders**: 中島

### Context
RAG 実装の選択肢として LangChain, LlamaIndex, Haystack 等のフレームワークが存在。
これらを使うと開発速度は上がるが、「フレームワークの抽象に乗っている」状態になりがち。

採用担当者に「RAG を自分で組める」と示すには、低レイヤを自前で書いた方が深い理解が伝わる。

### Decision
LangChain / LlamaIndex を一切使わず、embedder / vector_store / search / rag を全て自前実装する。

### Consequences
- ✅ コードベース全体を中島が読み切れる、ブラックボックスなし
- ✅ 履歴書で「RAG パイプライン自前実装」と書ける
- ✅ 依存追加で頻発するセキュリティ警告に巻き込まれない
- ❌ chunking / re-ranking / 高度な query rewriting は自作する必要、Week 1 では未対応
- ❌ tool ecosystem (LangSmith 等) と連携しない

### Alternatives Considered
- LangChain: 速いが abstraction が重い、設計理解アピールにならない
- LlamaIndex: data indexing は得意だが retrieval pipeline がカチっと固まり、軸検索を組み込みづらい
- Haystack: 機能が多すぎる、Local-first の趣旨と合わない

---

## ADR-002: ChromaDB をベクトルストアに採用する

...

## ADR-003: Pydantic ではなく dataclass を使う

...
```

最低 8 個、できれば 12 個書く。候補:

1. ADR-001: LangChain 不使用
2. ADR-002: ChromaDB 採用 (Pinecone, Weaviate, Qdrant 比較)
3. ADR-003: Pydantic ではなく dataclass
4. ADR-004: Streamlit を Week 1 に、Next.js を Week 3 に
5. ADR-005: DUMMY モード (offline 動作) 提供
6. ADR-006: 軸メタデータを `axis_*` プレフィックスで Chroma metadata 平坦化
7. ADR-007: normalize 後を別フィールド `normalized_*` に保存 (生テキスト保持)
8. ADR-008: AUTO_GENERATED マーカー方式 (人間記述と AI 生成の共存)
9. ADR-009: pytest + ruff のみ (mypy/black 不採用、Week 1 段階の判断)
10. ADR-010: Claude API + Gemini Embedding の役割分担
11. ADR-011: bridge 運用 (`_ai_workspace/`) の存在意義
12. ADR-012: chunking 不採用 (Week 1)、v0.4 で導入予定

### 3-3. `docs/api-reference.md`

各 public モジュールについて:

```markdown
## `backend.src.loader`

### `Document` (dataclass)

| Field | Type | Default | Description |
|---|---|---|---|
| id | str | required | Unique identifier from frontmatter |
| title | str | required | ... |
| ... |

### `load_document(path: Path, normalizer: Normalizer | None = None) -> Document`

Load a single Markdown file.

**Raises**: `LoaderError` if file missing / required field absent.

**Example**:

```python
from backend.src.loader import load_document
doc = load_document(Path("notes.md"))
print(doc.title, doc.axes)
```

### `load_directory(...)`

...

---

## `backend.src.embedder`

...
```

全モジュール (loader, embedder, vector_store, search, rag, normalizer, integrity, marker, config) を網羅。1 モジュール 50〜100 行程度。

### 3-4. `docs/INDEX.md`

```markdown
# Documentation Index

## Getting Started
- [README](../README.md) — Project overview, quickstart
- [spec-v2.md](spec-v2.md) — 3-week development plan (internal)

## Architecture
- [architecture.md](architecture.md) — System architecture, components, data flow
- [design-decisions.md](design-decisions.md) — ADR collection
- [api-reference.md](api-reference.md) — Module-by-module API

## Features
- [normalizer.md](normalizer.md) — Japanese text normalization
- [integrity.md](integrity.md) — Reference integrity checking
- [marker.md](marker.md) — AUTO_GENERATED block handling

## Operations
- (TBD: deployment.md in v0.3.0)
```

### 3-5. README からのリンク追加

```markdown
## Documentation

詳細な設計は [`docs/`](docs/) を参照:

- [Architecture](docs/architecture.md) — システム全体像
- [Design Decisions](docs/design-decisions.md) — 主要な設計判断 (ADR)
- [API Reference](docs/api-reference.md) — モジュール API
```

### 3-6. 動作確認

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"

# Markdown link check (簡易、外部ツール不要)
grep -rn "\](" docs/ README.md | head -30  # 怪しいパスがないかチェック

# 単に行数で量を確認
wc -l docs/*.md
```

### 3-7. コミット

1. `docs: add architecture.md (components, dataflow, ASCII diagram)`
2. `docs: add design-decisions.md with 12 ADRs`
3. `docs: add api-reference.md covering all backend modules`
4. `docs: add docs/INDEX.md and link from README`
5. `docs: align style of normalizer/integrity/marker docs`
6. `docs: changelog Day 13`

`git push origin main` (dev-b)

### 3-8. result_013.md

特に:

- 各 docs ファイルの行数 / 文字数
- ADR の項目一覧 (12 個全部)
- README からのリンク張りを確認
- スクショは取らない (Day 14 のリリースまでに中島さんが架けるなら良し)

## 4. 成功条件

- [ ] `docs/architecture.md` `design-decisions.md` `api-reference.md` `INDEX.md` 揃う
- [ ] ADR 8〜12 個記載
- [ ] README から docs へのリンクが追加されている
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_013.md`

## 6. 質問

- **ADR の内容を中島さんが事前にレビューしたい場合**: そのまま push せず、result に提案だけ書いて status=blocked で停止する選択肢あり。Day 13 の重要度を考えると「ADR-001〜005 だけ先に書いて、6〜12 はドラフト状態で push、後で追記」というステップ運用も可能。判断分かれそうな ADR (例: ADR-009 mypy/black 不採用) があれば質問
- **Mermaid を使うか ASCII のみか**: GitHub は Mermaid をレンダリングするが、`docs/architecture.md` を端末で見る人もいる。両併用 (ASCII を本文 + Mermaid を補助) でも良い
- **API リファレンスの生成自動化**: 本気で自動化するなら `pdoc` 等の導入だが、Week 2 のスコープを超える。Day 13 は手書きで質を上げる

## 7. 補足

### 設計の意図

- **ADR を独立した文書に集約**: 後から増やしやすい、PR で「ADR-N: ...」を追加する文化を作れる
- **API リファレンスを手書き**: 自動生成はあとから入れられる、手書きの方が「使い方」を含めて書ける (採用担当者に伝わりやすい)
- **docs/INDEX.md**: 文書が増えてきた時の目次、ナビゲーション性

### Day 14 連携

Day 14 (v0.2.0 リリース) で README v0.2 を作る。Day 13 の docs/ を引用して README を簡潔に保つ (READMEは入口、深い情報は docs/ に)。
