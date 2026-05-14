# spec_005: Day 5 — Streamlit UI (`streamlit_app.py`)

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜004 完成前提, `docs/spec-v2.md` Day 5 行

## 1. 目的

```
[現状]
- バックエンドが CLI で完成 (loader, embedder, vector_store, search, rag)
- まだ UI がない、Day 7 のリリース時に「README にデモが貼れない」状態

[変更後]
- `streamlit_app.py` (リポジトリ直下) が動作
- サイドバー: 軸フィルタ (category / topic / level / author / year を config.yml から動的生成)
- メイン上部: 質問入力欄
- メイン中央: RAG 回答 + 出典ハイライト
- メイン下部: 検索結果カード一覧 (score、axes、snippet、ファイルパス)
- `streamlit run streamlit_app.py` で起動、`localhost:8501` で利用可能
```

Week 1 のクライマックス。**操作感が分かるスクリーンショット** が README v0.1 に必要なので、ここで「動く絵」を作る。

## 2. 制約

### 触ってよいファイル / 新規作成

- `streamlit_app.py` — 新規、リポジトリ直下
- `backend/src/config.py` — 軸定義 (config.yml) を読み込むヘルパー `load_axes_config()` を追加 (既存 API は壊さない)
- `backend/requirements.txt` — `streamlit>=1.37.0` 追加
- `pyproject.toml` — dependencies に同上 (optional-dependencies `[ui]` でもよいが Day 5 では main に入れて OK)
- `examples/screenshots/` — 起動後のスクショ 2 枚を保存 (Day 7 で README に貼る)
- `CHANGELOG.md`

### 触ってはいけないもの

- `_ai_workspace/`、`docs/spec-v2.md`
- 既存の loader/embedder/vector_store/search/rag の API
- `_ai_workspace/bridge/outbox/result_*.md` (CC は自分のぶんのみ書く)

### コーディングルール

- Streamlit は `st.cache_resource` で SearchEngine / RAGPipeline を 1 回だけ初期化
- 軸フィルタは `st.sidebar.selectbox` (enum 軸) と `st.sidebar.text_input` (free 軸)
- 結果カードは `st.container` で枠を付け、`st.markdown` で title / axes / snippet
- 出典ハイライト: `Answer.cited_ids` に含まれる結果カードに `:green[★ cited]` バッジを付ける
- ファイル全体で 200 行以内目標、コメントで sections を区切る

## 3. やってほしいこと

### 3-1. `backend/src/config.py` に追加

```python
def load_axes_config(path: Path | None = None) -> dict:
    """Load axes definition from config.yml."""
    import yaml

    config_path = path or Path("./config.yml")
    if not config_path.exists():
        return {"axes": []}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"axes": []}
```

### 3-2. `streamlit_app.py`

```python
"""Streamlit UI for axis-knowledge-rag.

Usage:
    streamlit run streamlit_app.py

Requires the index to be built first:
    python -m scripts.build_index ./examples/knowledge --reset
"""

from pathlib import Path
from typing import Any

import streamlit as st

from backend.src.config import configure_logging, load_axes_config, settings
from backend.src.embedder import Embedder
from backend.src.rag import RAGPipeline
from backend.src.search import SearchEngine
from backend.src.vector_store import VectorStore

configure_logging()
st.set_page_config(
    page_title="axis-knowledge-rag",
    page_icon="🔍",
    layout="wide",
)


# ----- Resource bootstrap (cached) -----------------------------------------

@st.cache_resource
def get_pipeline() -> tuple[SearchEngine, RAGPipeline]:
    store = VectorStore(path=settings.chroma_db_path)
    embedder = Embedder()
    engine = SearchEngine(store, embedder)
    rag = RAGPipeline(engine)
    return engine, rag


@st.cache_data
def get_axes_config() -> dict:
    return load_axes_config()


engine, rag = get_pipeline()
axes_cfg = get_axes_config()


# ----- Header --------------------------------------------------------------

st.title("🔍 axis-knowledge-rag")
st.caption(
    "YAML frontmatter 付き Markdown ナレッジに対する、軸検索 + RAG 検索の Local-first OSS"
)
mode_badges: list[str] = []
mode_badges.append("🤖 Embedder: " + ("DUMMY" if Embedder().is_dummy else "Gemini"))
mode_badges.append("🤖 RAG: " + ("DUMMY" if rag.is_dummy else (rag._model or "Claude")))
st.caption(" | ".join(mode_badges))


# ----- Sidebar: axis filters -----------------------------------------------

st.sidebar.header("軸フィルタ")
filters: dict[str, Any] = {}
for axis in axes_cfg.get("axes", []):
    name = axis["name"]
    atype = axis.get("type", "string")
    if atype == "enum":
        choice = st.sidebar.selectbox(
            name,
            options=["(指定なし)"] + list(axis.get("values", [])),
            index=0,
            key=f"filter_{name}",
        )
        if choice != "(指定なし)":
            filters[name] = choice
    elif atype == "integer":
        v = st.sidebar.number_input(name, value=0, step=1, key=f"filter_{name}")
        if v != 0:
            filters[name] = int(v)
    else:
        v = st.sidebar.text_input(name, key=f"filter_{name}")
        if v.strip():
            filters[name] = v.strip()

top_k = st.sidebar.slider("Top K", min_value=1, max_value=10, value=5)

st.sidebar.divider()
if st.sidebar.button("ChromaDB の件数を表示"):
    st.sidebar.info(f"格納済み: {engine._store.count()} 件")


# ----- Main: question + answer ---------------------------------------------

question = st.text_input("質問を入力", placeholder="例: RAGアーキテクチャの設計判断は?")

if question:
    with st.spinner("検索 + 生成中..."):
        ans = rag.answer(question, filters=filters or None, top_k=top_k)

    st.subheader("💡 回答")
    if ans.is_dummy:
        st.info("DUMMY モード (ANTHROPIC_API_KEY 未設定)")
    st.markdown(ans.text)

    st.subheader(f"📚 関連資料 ({len(ans.sources)} 件)")
    for r in ans.sources:
        cited = r.id in ans.cited_ids
        with st.container(border=True):
            cols = st.columns([4, 1])
            with cols[0]:
                st.markdown(
                    f"**{r.title}**  "
                    f"`{r.id}`  "
                    + (":green[★ cited]" if cited else "")
                )
                st.caption(f"axes: {r.axes}")
                st.write(r.body_snippet)
            with cols[1]:
                st.metric("score", f"{r.score:.3f}")
                st.caption(r.path)
else:
    st.info("左サイドバーで軸を絞り込み、上の入力欄に質問を入れてください。")
    st.markdown(
        "**例:** 軸 `category=技術記事` でフィルタしてから「ベクトル検索の仕組みは?」と聞いてみる。"
    )
```

### 3-3. 動作確認 + スクショ取得

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"
pip install -e .

# index ビルド (まだなら)
python -m scripts.build_index ./examples/knowledge --reset

# UI 起動
streamlit run streamlit_app.py
```

期待動作:

- 起動後 `localhost:8501` で UI が表示される
- サイドバーに category / topic / level / author / year のフィルタが出る
- 質問を入れると 数秒で 「💡 回答」 と 「📚 関連資料」 が出る
- DUMMY モードでもエラーなく動く

スクショは:

- `examples/screenshots/main-view.png` (初期画面)
- `examples/screenshots/with-answer.png` (質問入力後の状態)

を **CC 側で取得できる手段がない** ので、CC は「ユーザーがスクショを撮るためのチェックリスト」を `result_005.md` に書くだけで OK。実際のスクショ取得は中島さんが手動で行う前提。

### 3-4. コミット

1. `chore: add streamlit to dependencies`
2. `feat: add load_axes_config helper in config.py`
3. `feat: implement Streamlit UI (streamlit_app.py)`
4. `docs: add screenshots checklist for README v0.1`
5. `docs: changelog Day 5`

`git push origin main` (dev-b)

### 3-5. result_005.md

特に書くこと:

- `streamlit run` の起動ログ (port、URL)
- 動作確認した質問パターン 3 件以上 (DUMMY モードでも OK)
- `engine._store` という private 属性に触っているのでリファクタ候補として記載 (Week 2 で `store_count()` public API を VectorStore に追加することを提案)
- スクショは取れない旨と、ユーザーが手動で撮るチェックリスト

## 4. 成功条件

- [ ] `streamlit run streamlit_app.py` がエラーなく起動
- [ ] 軸フィルタ・質問入力・回答表示・関連資料カードが動作
- [ ] cited 出典に `★ cited` バッジが付く
- [ ] DUMMY モードで動く
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_005.md`

## 6. 質問

- **Streamlit バージョン互換**: `st.container(border=True)` は 1.30+ で利用可。古いバージョンの場合は `st.container()` で fallback
- **cache_resource の挙動**: Embedder / VectorStore を cache すると Hot reload で stale になる。reset ボタンを追加するか判断 (Week 1 では追加しない方針、Open question に書くだけ)
- **streamlit_app.py の置き場**: リポジトリ直下に置くか `frontend_streamlit/` 下に置くか。Week 3 で Next.js に移行するので、Day 5 では **リポジトリ直下** で OK (移行時にディレクトリごと退避)

## 7. 補足

### 設計の意図

- **`st.cache_resource` を使う**: SearchEngine / RAGPipeline は重い init、Streamlit の再実行ループで毎回作り直すとパフォーマンスが死ぬ
- **`load_axes_config` を config.py に**: 軸定義は UI 以外 (Week 2 の integrity チェック) でも使うので一元化
- **`engine._store.count()` のアクセス**: private なので Week 2 で public 化する候補、ここでは toleration
- **絵文字バッジ**: ★ cited を緑、Streamlit 1.30+ の `:green[]` 構文。動かないバージョンなら `**cited**` で代替

### Day 6 連携

Day 6 で Docker 化。`streamlit_app.py` をそのまま `streamlit run` で起動する Dockerfile を書く。Day 6 spec で詳細。
