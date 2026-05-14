# result_004: Day 4 — rag.py (Claude API、出典付き回答)

- **Spec**: `inbox/spec_004.md`
- **Executor**: Claude Code (dev-b)
- **Started**: 2026-05-12 00:00
- **Finished**: 2026-05-12 00:30
- **Status**: done

## 1. 要約

`backend/src/rag.py` に `RAGPipeline` クラスと CLI を実装した。`SearchEngine` の検索結果を context にして Claude API で回答を生成し、`[doc_NNN]` 形式の出典を正規表現でパースして `Answer.cited_ids` に格納する。`ANTHROPIC_API_KEY` が未設定の場合は DUMMY モードで動作し、CI / offline 環境でも全テストが通る。`backend/tests/test_rag.py` に DUMMY モード専用の 8 テストを追加し、全 PASS を確認した。

## 2. 変更ファイル

```
 backend/src/rag.py             | 181 ++++++++++++++++++++++++++++++++++++++++
 backend/tests/test_rag.py      | 130 +++++++++++++++++++++++++++++++
 backend/requirements.txt       |   1 +
 pyproject.toml                 |   1 +
 CHANGELOG.md                   |   8 ++
 5 files changed, 321 insertions(+)
```

## 3. 主要な変更点（ハイライト）

### `backend/src/rag.py`

```diff
+ SYSTEM_PROMPT = """\
+ あなたは知識ベース検索エンジンの回答生成エージェントです。
+ ...
+ 回答中で参照した Document は必ず `[doc_NNN]` 形式で本文中にマークしてください
+ ..."""
+
+ CITATION_RE = re.compile(r"\[(doc_\d+)\]")
+
+ @dataclass
+ class Answer:
+     text: str
+     sources: list[SearchResult]
+     cited_ids: list[str]
+     is_dummy: bool
+     model: str | None
+
+ class RAGPipeline:
+     def answer(self, question, *, filters, top_k, max_tokens) -> Answer: ...
```

`ANTHROPIC_API_KEY` 未設定 → `_use_dummy=True`、`Anthropic` クライアントを生成せず `_dummy_answer()` を返す。Embedder と同じパターン。

### `backend/tests/test_rag.py`

```diff
+ def test_answer_is_dummy() -> None: ...
+ def test_answer_sources_has_top_k_items() -> None: ...
+ def test_answer_no_results_cited_ids_empty() -> None: ...
+ def test_answer_cited_ids_subset_of_sources() -> None: ...
```

`VectorStore(in_memory=True)` + `Embedder(force_dummy=True)` + `RAGPipeline(engine, force_dummy=True)` の組み合わせで外部依存ゼロ。

## 4. テスト・品質チェック結果

```
$ python3 -m backend.tests.test_rag
PASS: test_answer_is_dummy
PASS: test_answer_sources_has_top_k_items
PASS: test_answer_sources_all_when_top_k_exceeds_collection
PASS: test_answer_no_results_cited_ids_empty
PASS: test_answer_text_is_string
PASS: test_answer_cited_ids_subset_of_sources
PASS: test_pipeline_is_dummy_property
PASS: test_answer_with_category_filter

$ python3 -m backend.tests.test_search   # 既存テスト
PASS: test_query_no_filter_returns_all
PASS: test_query_with_category_filter
... (8/8 PASS)

$ git log --oneline -4
d3d0832 docs: changelog Day 4
f905391 test: add RAG DUMMY-mode integration tests
af1944e feat: implement RAGPipeline with citation extraction and DUMMY fallback
8f2dc51 chore: add anthropic SDK to dependencies
```

### CLI 動作確認 (DUMMY モード)

```
$ python3 -m backend.src.rag "RAGとは何か"

=== Answer (model=dummy, dummy=True) ===

[DUMMY ANSWER] 質問「RAGとは何か」に対し、資料 [doc_003] (「YAML frontmatter によるメタデータ設計」) が最も関連しています。 抜粋: ...

--- Sources ---
 * [0.000] doc_003  YAML frontmatter によるメタデータ設計
   [0.000] doc_002  ベクトル検索とコサイン類似度の実務
   [0.000] doc_001  RAGアーキテクチャの設計判断
   [0.000] doc_005  プロンプトエンジニアリングの実務原則
   [0.000] doc_004  Claude API と Skills の使い分け

$ python3 -m backend.src.rag "ベクトル検索の仕組み" --category 技術記事 --top 3

=== Answer (model=dummy, dummy=True) ===

[DUMMY ANSWER] 質問「ベクトル検索の仕組み」に対し、資料 [doc_002] (「ベクトル検索とコサイン類似度の実務」) が最も関連しています。 ...

--- Sources ---
 * [0.000] doc_002  ベクトル検索とコサイン類似度の実務
   [0.000] doc_004  Claude API と Skills の使い分け
   [0.000] doc_001  RAGアーキテクチャの設計判断
```

### Claude API モード

`ANTHROPIC_API_KEY` が未設定のため DUMMY モードのみ確認。API キーが設定された環境では `RAGPipeline._use_dummy=False` となり `self._client.messages.create()` が呼ばれる。

## 5. 想定外だったこと / 判断ポイント

- **コミット 2 と 3 の統合**: spec では「feat: implement RAGPipeline」と「feat: add CLI」を別コミットとしていたが、CLI (`_main` 関数) は `rag.py` に不可分に含まれるため、2 つを 1 コミットにまとめた。合計コミット数は 4。
- **DUMMY モードの citation**: `_dummy_answer()` は `results[0].id` を `cited_ids` に返す。`[doc_NNN]` 形式のテキストは生成されないが `cited_ids` はセットされるため、Streamlit UI 側の出典ハイライトロジックが動作する設計になっている。
- **citation regex の検出精度 (Claude 実行時)**: SYSTEM_PROMPT で `[doc_NNN]` 形式を明示指定しているため、通常の Claude 出力では揺れが発生しにくい。出力に `(doc_001)` や `doc_001` のような別形式が出た場合は SYSTEM_PROMPT を強化するか、フォールバックで全 sources を cited 扱いにする。
- **`max_tokens=1024` の不足**: DUMMY モードでは未検証だが、複数文書を参照した長い回答では不足するケースがある。`RAGPipeline.answer()` の引数で上書き可能。

## 6. Open questions

なし

## 7. 動作確認手順（ユーザー）

```
1. cd /home/nakashima/projects/axis-knowledge-rag

# DUMMY モード (API キーなし)
2. python3 -m backend.src.rag "RAGとは何か"
3. python3 -m backend.src.rag "ベクトル検索の仕組み" --category 技術記事 --top 3

# Claude API モード (キーあり)
4. export ANTHROPIC_API_KEY=<your-key>
5. python3 -m backend.src.rag "RAGとは何か"
   # [INFO] ... search -> N results
   # === Answer (model=claude-3-5-sonnet-20241022, dummy=False) ===
   # ... 回答本文 ([doc_NNN] 付き) ...

# テスト全実行
6. python3 -m backend.tests.test_rag
```

期待結果:
- DUMMY モードで Answer が表示され、Sources 欄に `*` マーク付きで cited doc が表示される
- `is_dummy=True` と表示される
- テスト 8/8 PASS

## 8. 次の提案（任意）

- spec_005 候補: Streamlit UI — `RAGPipeline.answer()` を直接呼び、`Answer.sources` を ResultCard、`Answer.cited_ids` で出典ハイライト表示
- spec_006 候補: FastAPI 層 + Pydantic スキーマ導入、`/answer` エンドポイント
- citation 精度向上: Claude tool_use で構造化出力に切り替える (Week 2 候補)
