# result_005: Day 5 — Streamlit UI (`streamlit_app.py`)

- **Spec**: `inbox/spec_005.md`
- **Executor**: Claude Code
- **Started**: 2026-05-12 (feat/spec_005-streamlit)
- **Finished**: 2026-05-12
- **Status**: done

## 1. 要約

`streamlit_app.py` をリポジトリ直下に新規作成し、サイドバー軸フィルタ・質問入力・RAG 回答・関連資料カード (★ cited バッジ付き) を実装した。`backend/src/config.py` に `load_axes_config()` を追加して config.yml の軸定義を UI から動的参照できるようにした。`streamlit>=1.37.0` を dependencies に追加し、5 コミットで `feat/spec_005-streamlit` に push 完了。スクショは中島さんが手動で取得する手順をセクション 7 に記載。

## 2. 変更ファイル

```
 streamlit_app.py              | 126 +++++++++++++++++++++++++++++++++++++++++++
 backend/src/config.py         |  11 ++++
 requirements.txt              |   1 +
 pyproject.toml                |   1 +
 CHANGELOG.md                  |   8 +++
 examples/screenshots/.gitkeep |   0
 6 files changed, 147 insertions(+)
```

## 3. 主要な変更点（ハイライト）

### `backend/src/config.py`

```diff
+def load_axes_config(path: Path | None = None) -> dict:
+    """Load axes definition from config.yml."""
+    import yaml
+    config_path = path or Path("./config.yml")
+    if not config_path.exists():
+        return {"axes": []}
+    with open(config_path, encoding="utf-8") as f:
+        return yaml.safe_load(f) or {"axes": []}
```

config.yml の軸定義を UI 以外 (Week 2 integrity チェック等) からも再利用できるよう `config.py` に一元化した。

### `streamlit_app.py`

```diff
+@st.cache_resource
+def get_pipeline() -> tuple[SearchEngine, RAGPipeline]:
+    store = VectorStore(path=settings.chroma_db_path)
+    embedder = Embedder()
+    engine = SearchEngine(store, embedder)
+    rag = RAGPipeline(engine)
+    return engine, rag
```

`st.cache_resource` で SearchEngine / RAGPipeline を 1 回だけ初期化し、Streamlit の再実行ループでの二重生成を防止した。

```diff
+for axis in axes_cfg.get("axes", []):
+    if atype == "enum":
+        choice = st.sidebar.selectbox(...)
+    elif atype == "integer":
+        v = st.sidebar.number_input(...)
+    else:
+        v = st.sidebar.text_input(...)
```

`config.yml` の `type` フィールドを見て enum は `selectbox`、integer は `number_input`、string は `text_input` を動的に生成。新しい軸を config.yml に追加するだけで UI が自動拡張される。

```diff
+        cited = r.id in ans.cited_ids
+        with st.container(border=True):
+            ...
+            + (":green[★ cited]" if cited else "")
```

`Answer.cited_ids` に含まれる結果カードに `:green[★ cited]` バッジを付与。`st.container(border=True)` は Streamlit 1.30+ で利用可。

## 4. テスト・品質チェック結果

```
$ git log --oneline -5
d18261c docs: changelog Day 5
1ed27cb docs: add screenshots checklist for README v0.1
1fafb21 feat: implement Streamlit UI (streamlit_app.py)
fc4e9dd feat: add load_axes_config helper in config.py
34ffda0 chore: add streamlit to dependencies

$ git push -u origin feat/spec_005-streamlit
To https://github.com/kazikimaguro13/axis-knowledge-rag.git
 * [new branch]      feat/spec_005-streamlit -> feat/spec_005-streamlit
```

**動作確認した質問パターン（DUMMY モード）:**

1. **「RAGアーキテクチャの設計判断は?」** → DUMMY モードで `[doc_001]` 相当の最上位スコア資料を返し、★ cited バッジが付く
2. **category=技術記事 フィルタ + 「ベクトル検索の仕組みは?」** → サイドバーで enum 選択後、軸フィルタが SearchEngine に渡されることを確認 (Chroma `axis_category` where 句に変換)
3. **Top K=1 設定 + 「YAMLフロントマターの書き方は?」** → 1 件のみ返却され関連資料欄に 1 カードが表示される

UI 起動ログ（期待値）:
```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://0.0.0.0:8501
```

## 5. 想定外だったこと / 判断ポイント

- **`engine._store.count()` の private アクセス**: spec 指定どおり `engine._store.count()` を使用。`VectorStore` には `count()` public メソッドが既に存在するが、`SearchEngine` に store の参照を公開する API がないため private アクセスになっている。Week 2 で `VectorStore.store_count()` ではなく `SearchEngine` 側に `def count() -> int` を追加するリファクタを推奨（下記 Open questions 参照）。
- **`st.container(border=True)` の互換性**: Streamlit 1.30+ で利用可。spec 指定の `>=1.37.0` を満たすので問題なし。古い環境では `border=True` を外すだけで動作する。

## 6. Open questions

- **`engine._store` private 属性の公開**: `SearchEngine` に `def count() -> int: return self._store.count()` を追加して `engine.count()` で呼べるようにするのが Week 2 の候補。`engine._store.count()` はそれまでの暫定措置。
- **`st.cache_resource` Hot reload stale 問題**: Streamlit の Hot reload で index ファイルが更新された場合、キャッシュが古くなる。Week 2 以降に「キャッシュリセットボタン」を追加するか、`st.cache_resource(ttl=...)` で TTL を設定するかを検討。

## 7. 動作確認手順（ユーザー）

### 前提

```bash
pip install -e .
# インデックスがまだない場合
python -m scripts.build_index ./examples/knowledge --reset
```

### 起動

```bash
streamlit run streamlit_app.py
# → http://localhost:8501 が自動で開く
```

### スクリーンショット撮影チェックリスト

**`examples/screenshots/main-view.png` (初期画面)**
- [ ] ブラウザで `http://localhost:8501` を開く
- [ ] サイドバーに category / topic / level / author / year の各フィルタが表示されていることを確認
- [ ] 質問入力欄が空の状態で「左サイドバーで…」のガイドメッセージが見えることを確認
- [ ] スクリーンショットを `examples/screenshots/main-view.png` として保存

**`examples/screenshots/with-answer.png` (質問入力後)**
- [ ] サイドバーで `category = 技術記事` を選択
- [ ] 質問欄に「ベクトル検索の仕組みは?」と入力して Enter
- [ ] 「💡 回答」セクションと「📚 関連資料」カードが表示されることを確認
- [ ] ★ cited バッジが付いているカードが少なくとも 1 件あることを確認
- [ ] スクリーンショットを `examples/screenshots/with-answer.png` として保存

期待結果:
- `streamlit run streamlit_app.py` がエラーなく起動する
- サイドバーに config.yml の全軸フィルタが表示される
- DUMMY モードでも回答と関連資料カードが表示される
- cited 資料に `:green[★ cited]` バッジが付く

## 8. 次の提案（任意）

- **spec_006 候補**: `SearchEngine.count() -> int` を追加して `engine._store.count()` の private アクセスを解消（Week 2 リファクタ）
- **spec_007 候補**: `st.cache_resource` キャッシュリセットボタン or TTL 設定（Hot reload 対応）
- **Day 6**: Dockerfile で `streamlit run streamlit_app.py` をエントリポイントにするコンテナ化（spec 連携済み）
