"""Streamlit UI for axis-knowledge-rag.

Usage:
    streamlit run streamlit_app.py

Requires the index to be built first:
    python -m scripts.build_index ./examples/knowledge --reset
"""

import contextlib
import os
from typing import Any

import requests
import streamlit as st

from backend.src.config import configure_logging, load_axes_config, settings
from backend.src.embedder import Embedder
from backend.src.normalizer import Normalizer
from backend.src.rag import RAGPipeline
from backend.src.search import SearchEngine
from backend.src.vector_store import VectorStore

configure_logging()
st.set_page_config(
    page_title="axis-knowledge-rag",
    page_icon="🔍",
    layout="wide",
)


# Backend URL for the Chat tab (the Search tab uses the in-process pipeline,
# but Chat goes through /api/chat so the session store lives server-side).
API_BASE = os.getenv("AXIS_API_BASE", "http://localhost:8000")


# ----- Resource bootstrap (cached) -----------------------------------------

@st.cache_resource
def get_pipeline() -> tuple[SearchEngine, RAGPipeline]:
    store = VectorStore(path=settings.chroma_db_path)
    embedder = Embedder()
    normalizer = Normalizer.from_config(load_axes_config())
    engine = SearchEngine(store, embedder, normalizer)
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


# ----- Tabs ---------------------------------------------------------------


def _search_tab() -> None:
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


def _chat_tab() -> None:
    st.caption(
        f"履歴を保持した連続対話モード。バックエンド `{API_BASE}/api/chat` を呼び出します。"
    )
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = None
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    cols = st.columns([3, 1])
    with cols[1]:
        if st.button("🗑 会話をリセット", use_container_width=True):
            sid = st.session_state.chat_session_id
            if sid:
                with contextlib.suppress(Exception):
                    requests.delete(f"{API_BASE}/api/chat/{sid}", timeout=10)
            st.session_state.chat_session_id = None
            st.session_state.chat_messages = []
            st.rerun()
    with cols[0]:
        if st.session_state.chat_session_id:
            st.caption(f"session: `{st.session_state.chat_session_id}`")

    for m in st.session_state.chat_messages:
        with st.chat_message(m["role"]):
            if m.get("rewritten_question"):
                st.caption(f"🔁 rewritten: `{m['rewritten_question']}`")
            st.markdown(m["content"])
            if m.get("sources"):
                with st.expander(f"📚 出典 {len(m['sources'])} 件"):
                    for s in m["sources"]:
                        st.markdown(
                            f"- **{s.get('title', '')}** `{s.get('id', '')}` "
                            f"(score {s.get('score', 0):.3f})"
                        )

    if q := st.chat_input("質問を入力 (例: RAGの利点は?)"):
        st.session_state.chat_messages.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("考え中..."):
                try:
                    r = requests.post(
                        f"{API_BASE}/api/chat",
                        json={
                            "question": q,
                            "session_id": st.session_state.chat_session_id,
                            "filters": filters or {},
                            "top_k": top_k,
                        },
                        timeout=120,
                    )
                    r.raise_for_status()
                    data = r.json()
                except Exception as e:
                    st.error(f"chat 失敗: {e}")
                    return
            st.session_state.chat_session_id = data["session_id"]
            if data.get("rewritten_question"):
                st.caption(f"🔁 rewritten: `{data['rewritten_question']}`")
            st.markdown(data["answer"])
            st.session_state.chat_messages.append(
                {
                    "role": "assistant",
                    "content": data["answer"],
                    "sources": data.get("sources", []),
                    "rewritten_question": data.get("rewritten_question"),
                }
            )


tab_search, tab_chat = st.tabs(["🔎 Search", "💬 Chat"])
with tab_search:
    _search_tab()
with tab_chat:
    _chat_tab()
