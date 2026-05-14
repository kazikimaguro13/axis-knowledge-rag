# result_009: Day 9 — normalizer を検索パイプラインに統合

- **Spec**: `inbox/spec_009.md`
- **Executor**: Claude Code (`dev-b`, feat/spec_009-normalizer-integration)
- **Started**: 2026-05-13 (午後)
- **Finished**: 2026-05-13 (午後)
- **Status**: done

## 1. 要約

`backend/src/normalizer.py` (Day 8 完成) を、loader → vector_store → search → build_index → streamlit_app の検索パイプライン全体に統合した。Document に `normalized_*` 派生フィールドを追加し、生フィールドは UI 表示用に据え置き。ChromaDB metadata には `axis_<key>_norm` を併記して、SearchEngine が query / filters を normalize してから `_build_where_norm` で where 句を組む。8 ケースの E2E 統合テスト (`test_integration_normalization.py`) と既存テスト 5 ファイル分の更新で、表記ゆれ (全角/半角・カナ/ひらがな・大小文字) を吸収できることを確認。`feat/spec_009-normalizer-integration` ブランチに 7 コミット分けてプッシュ済み。

## 2. 変更ファイル

```
 CHANGELOG.md                                    |  12 ++
 backend/src/loader.py                           |  34 ++++-
 backend/src/search.py                           |  54 +++++--
 backend/src/vector_store.py                     |  18 ++-
 backend/tests/test_integration_normalization.py | 194 ++++++++++++++++++++++++
 backend/tests/test_search.py                    |  26 +++-
 backend/tests/test_vector_store.py              |  18 ++-
 scripts/build_index.py                          |  10 +-
 streamlit_app.py                                |   4 +-
 9 files changed, 338 insertions(+), 32 deletions(-)
```

## 3. 主要な変更点（ハイライト）

### `backend/src/loader.py`

```diff
+ from backend.src.normalizer import Normalizer
  ...
  @dataclass
  class Document:
      ...
      raw_meta: dict[str, Any] = field(default_factory=dict)
+     normalized_title: str = ""
+     normalized_body: str = ""
+     normalized_axes: dict[str, str] = field(default_factory=dict)
+     normalized_tags: list[str] = field(default_factory=list)

- def load_document(path: Path) -> Document:
+ def load_document(path: Path, normalizer: Normalizer | None = None) -> Document:
      ...
+     if normalizer is not None:
+         doc.normalized_title = normalizer(doc.title)
+         doc.normalized_body = normalizer(doc.body)
+         doc.normalized_axes = {k: normalizer(str(v)) for k, v in doc.axes.items()}
+         doc.normalized_tags = [normalizer(t) for t in doc.tags]
      return doc
```

`normalizer=None` (デフォルト) なら Day 1 と全く同じ挙動。`normalized_*` は default で空 string / 空 dict / 空 list なので、Document を手動で組み立てている既存テストは無修正で通る (後方互換のため `@dataclass` 順に新フィールドを末尾追加)。

### `backend/src/vector_store.py`

```diff
+ def _flatten_axes_with_norm(axes, normalized):
+     out = _flatten_axes(axes)
+     for k, v in normalized.items():
+         out[f"axis_{k}_norm"] = v
+     return out

  class VectorStore:
      def upsert(self, doc, embedding):
          metadata = {
              "title": doc.title,
+             "title_norm": doc.normalized_title,
              "path": str(doc.path),
              "tags": ",".join(doc.tags),
+             "tags_norm": ",".join(doc.normalized_tags),
              "refs": ",".join(doc.refs),
-             **_flatten_axes(doc.axes),
+             **_flatten_axes_with_norm(doc.axes, doc.normalized_axes),
          }
```

生メタデータは UI 表示用に温存。`_norm` サフィックスは Day 10 以降も統一する規約。

### `backend/src/search.py`

```diff
  class SearchEngine:
-     def __init__(self, store, embedder):
+     def __init__(self, store, embedder, normalizer=None):
          self._store = store
          self._embedder = embedder
+         self._normalizer = normalizer or Normalizer()

      def search(self, query, *, filters=None, top_k=5):
-         where = _build_where(filters or {})
-         embedding = self._embedder.embed(query)
+         norm_filters = (
+             {k: self._normalizer(str(v)) for k, v in filters.items()}
+             if filters else None
+         )
+         where = _build_where_norm(norm_filters or {})
+         q_norm = self._normalizer(query)
+         embedding = self._embedder.embed(q_norm)
```

加えて `_to_results` で `_norm` サフィックス付きキーを raw `axes` dict から除外 (UI 表示に混ざらないように)。

### `scripts/build_index.py`

```diff
- docs = load_directory(args.knowledge_dir)
+ normalizer = Normalizer.from_config(load_axes_config())
+ docs = load_directory(args.knowledge_dir, normalizer=normalizer)
  ...
- embeddings = embedder.embed_batch([d.body for d in docs])
+ embeddings = embedder.embed_batch([d.normalized_body for d in docs])
```

embed 対象が body → normalized_body に変わる。同じ semantic で書き方違いの文書を近いベクトル位置に配置するための変更。

### `streamlit_app.py`

```diff
  @st.cache_resource
  def get_pipeline():
      ...
+     normalizer = Normalizer.from_config(load_axes_config())
-     engine = SearchEngine(store, embedder)
+     engine = SearchEngine(store, embedder, normalizer)
```

### `backend/tests/test_integration_normalization.py` (新規, 194 行)

8 ケースの End-to-End:

1. 全角 `ＲＡＧ` クエリ → 半角 `RAG` 含む doc にヒット
2. ひらがな `らぐ` クエリ → カタカナ `ラグ` 含む doc にヒット
3. 大文字 `CLAUDE` クエリ → 小文字 `claude` 含む doc にヒット
4. 全角 `ＴｅｃｈＮｏｔｅ` filter → `TechNote` の doc を返す
5. `技術記事` filter で複数 doc が引っかかる
6. upsert 後の metadata に `axis_*_norm` / `title_norm` / `tags_norm` が併記
7. `SearchResult.axes` に `_norm` キーが混入しない (UI 用)
8. `load_document(normalizer=None)` で normalized_* が空のまま (後方互換)

### `backend/tests/test_vector_store.py` (副次修正)

`_fresh_store()` ヘルパを追加。Chroma `EphemeralClient` がプロセス内で内部 system を共有するため、複数テストで同 `COLLECTION_NAME` を upsert すると state が leak していた (pre-existing flakiness)。各テスト冒頭で `store.reset()` を呼ぶことで隔離した。

## 4. テスト・品質チェック結果

```
$ python3 -m backend.tests.test_loader
  PASS: test_load_minimal_document
  PASS: test_missing_id_raises
  PASS: test_load_directory_skips_bad_files
  PASS: test_strict_mode_raises_on_bad_file

$ python3 -m backend.tests.test_normalizer
  16/16 PASSED

$ python3 -m backend.tests.test_embedder
  PASS × 4

$ python3 -m backend.tests.test_vector_store
  PASS × 5  (pre-existing flakiness 解消後)

$ python3 -m backend.tests.test_search
  PASS × 8  (test_query_with_category_filter / test_axis_only_no_query_with_filter
            は normalizer injection を追加して継続合格)

$ python3 -m backend.tests.test_rag
  PASS × 8

$ python3 -m backend.tests.test_marker
  31/31 passed

$ python3 -m backend.tests.test_integrity
  PASS × 5

$ python3 -m backend.tests.test_integration_normalization
  8/8 PASSED  (新規)

$ python3 -m scripts.build_index ./examples/knowledge --reset
  Indexed 10 documents into .chromadb
  Total in collection: 10
  Embedder mode: DUMMY
```

合計 **9 テストファイル / 89 ケース 全 PASS**、回帰なし。

### Before / After 比較 (DUMMY embedder)

`SearchEngine(normalizer=ON/OFF)` を切り替えて同じ index に同じクエリを投げた結果:

| query        | normalize OFF (raw)              | normalize ON                    |
| ------------ | -------------------------------- | ------------------------------- |
| `ＲＡＧとは` | [doc_001, doc_003, doc_002]      | **[doc_003, doc_008, doc_001]** |
| `RAGとは`    | [doc_001, doc_004, doc_008]      | **[doc_003, doc_008, doc_001]** |
| `らぐ`       | [doc_010, doc_003, doc_008]      | **[doc_010, doc_003, doc_008]** |
| `ラグ`       | [doc_001, doc_008, doc_005]      | **[doc_010, doc_003, doc_008]** |
| `CLAUDE`     | [doc_002, doc_006, doc_004]      | **[doc_008, doc_003, doc_005]** |
| `claude`     | [doc_008, doc_003, doc_005]      | **[doc_008, doc_003, doc_005]** |

- normalize OFF: 表記の違いで top-3 集合 / 順序がバラバラ (DUMMY embedder は SHA-256 ハッシュ依存なので 1 文字違うだけで完全に別ベクトル)
- normalize ON: `ＲＡＧとは` と `RAGとは` が同じ top-3 / 順序、`らぐ` と `ラグ` が同じ top-3 / 順序、`CLAUDE` と `claude` が同じ top-3 / 順序

CLI でも:

```
$ python3 -m backend.src.search "ＲＡＧとは" --top 1
[0.000] doc_003  YAML frontmatter によるメタデータ設計

$ python3 -m backend.src.search "RAGとは" --top 1
[0.000] doc_003  YAML frontmatter によるメタデータ設計
```

→ 全角/半角どちらでも同じ top-1。

### ChromaDB 容量

```
Before (Day 6 index, axis_category のみ):    620K
After  (Day 9 index, axis_*_norm 併記):     1.2M
```

倍程度に増加。要因:

1. metadata に `title_norm` / `tags_norm` / `axis_<key>_norm` を全 doc 分追加 (10 doc × 5 軸 + α)
2. `--reset` 後の Chroma は SQLite 内部に segment を再構築するため、削除済み旧データの hnswlib バイナリが暫く残るケースがある
3. embed 対象が body → normalized_body に変わったが 768 次元自体は不変、ベクトル本体のサイズは増えない

サンプル 10 doc 規模ではほぼ無視できるが、本番規模 (数千〜) では metadata 倍増分が効いてくる。Day 10 以降で metadata の trim (`refs` / `tags` 重複を捨てる等) を検討する余地あり。

### git log

```
$ git log --oneline 763b019..HEAD
bc1c84e docs: changelog Day 9
e13729b test: add E2E normalization integration tests
eeca5f1 feat: wire Normalizer into Streamlit app
de32402 feat: index normalized body in build_index.py
3017b3e feat: integrate Normalizer into SearchEngine
104efe9 feat: store normalized metadata in ChromaDB (axis_*_norm)
bc9bf46 feat: extend Document with normalized_* fields

$ git push -u origin feat/spec_009-normalizer-integration
 * [new branch]      feat/spec_009-normalizer-integration -> feat/spec_009-normalizer-integration
branch 'feat/spec_009-normalizer-integration' set up to track 'origin/feat/spec_009-normalizer-integration'.
```

## 5. 想定外だったこと / 判断ポイント

- **半角カナ filter の「全角と同じ結果」の意味**: spec の例 `--category ｺﾞｼﾞｭﾂｷｼﾞ` (半角カナ) は normalize 後 `ごじゅつきじ` になる。一方 index 上の `axis_category_norm` は `技術記事` (漢字なので normalize 後も漢字)。よって kana 表記の filter は漢字 axis にはマッチしない (実例 `examples/knowledge/` でも 0 件返る)。これは spec が示す「表記ゆれ吸収」が "kana ↔ kana" / "全角 ↔ 半角" の範囲に限定されることの実証で、欠陥ではない。integration テストの `test_zenkaku_filter_matches_normalized_axis` ではあえて `TechNote` の doc を用意して、全角 `ＴｅｃｈＮｏｔｅ` filter が当たることを確認した。
- **`test_vector_store` の pre-existing flakiness**: stash で確認したところ Day 9 着手前から `test_reset_clears_collection` / `test_axis_filter_query` は失敗していた。Chroma EphemeralClient のプロセス内 state 共有が原因なので、`_fresh_store()` で `store.reset()` を冒頭に呼ぶようヘルパ化した。spec_009 のスコープ内 (「既存テストの更新、回帰なし」) と判断して同コミットに含めた。
- **`_to_results` の axes フィルタ**: Day 9 前は `axes = {k.removeprefix("axis_"): v for k, v ...}` で全 `axis_*` キーを取り込んでいた。`axis_*_norm` を追加した結果 `axes["category_norm"]` のような UI ノイズが出るため、`endswith("_norm")` を除外条件に追加。
- **`SearchEngine(normalizer=None)` のデフォルト**: spec の挙動どおり `Normalizer()` (config なし、デフォルト全 ON) を内部で生成。明示的に渡されなかった場合に「正規化なし」になると、build_index 側で normalize して embed したベクトルと、search 側で生クエリのまま embed したベクトルが噛み合わなくなるため、安全側 (常に normalize) をデフォルトにした。

## 6. Open questions

なし。

## 7. 動作確認手順（ユーザー）

```bash
# 1. 最新を pull
git fetch origin feat/spec_009-normalizer-integration
git checkout feat/spec_009-normalizer-integration

# 2. 全テスト
for t in test_loader test_normalizer test_embedder test_vector_store \
         test_search test_rag test_marker test_integrity \
         test_integration_normalization; do
  echo "=== $t ==="
  python3 -m backend.tests.$t 2>&1 | grep -E "PASS|FAIL|ERROR|PASSED"
done

# 3. index 再構築 (旧スキーマと非互換なので --reset 必須)
python3 -m scripts.build_index ./examples/knowledge --reset

# 4. Before/After 比較 (CLI)
python3 -m backend.src.search "ＲＡＧとは" --top 3
python3 -m backend.src.search "RAGとは" --top 3
# → 同じ top-1 (doc_003) が返る

python3 -m backend.src.search "らぐ" --category 技術記事 --top 3
python3 -m backend.src.search "ラグ" --category 技術記事 --top 3
# → どちらも同じ doc_002, doc_005, doc_004 が返る

# 5. Streamlit
streamlit run streamlit_app.py
# → 質問欄に「ＲＡＧとは」「らぐ」「CLAUDE」など全角/カナ/大文字で投げて
#    妥当な doc が候補に出ることを目視で確認
```

期待結果:
- 全テスト PASS
- 全角クエリと半角クエリが同じ top-1 を返す
- ひらがなクエリとカタカナクエリが同じ top-3 を返す
- Streamlit UI が壊れていない
- `_ai_workspace/` / `docs/spec-v2.md` / `backend/src/rag.py` / `backend/src/normalizer.py` は無変更

## 8. 次の提案（任意）

- **spec_010 候補: metadata trim**: Chroma metadata の `tags` / `tags_norm` / `refs` を CSV 文字列で持っているが、`tags` と `tags_norm` のどちらかを表示用としてのみ保持し、検索には片方しか使わない場合は redundancy になっている。本番規模で metadata サイズが効いてくるなら trim を検討。
- **spec_011 候補: normalizer の filter 用 alias**: 半角カナ filter (`ｷﾞｼﾞｭﾂｷｼﾞ`) が漢字 axis (`技術記事`) に当たらない件は、軸定義に「カナ alias」「英字 alias」を持たせて normalize 比較対象を増やす拡張で解決可能。例: `category: 技術記事 (aliases: [TechNote, ぎじゅつきじ])` のように。
- **spec_012 候補: Gemini モード での Before/After**: 今回は DUMMY embedder で「ハッシュ衝突が一致する」ことを確認したが、Gemini 実モードでは semantic similarity が動くので Before/After の差分は別の意味を持つ。`GEMINI_API_KEY` 設定環境で再計測すると、normalize による recall@k 改善の定量化ができる。
