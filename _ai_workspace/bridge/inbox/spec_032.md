# spec_032: Conversational RAG (履歴保持チャット UI)

- **Author**: Cowork (中島)
- **Created**: 2026-05-14
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: v0.7 コア 2/3。spec_031 (Parent Doc) と並行可能、依存なし。spec_033 (RAGAS) は本 spec 後に評価対象が増える

## 1. 目的

v0.6 までは「単発検索 + RAG」のみで、フォローアップ質問 (例: 「もっと詳しく」「それはなぜ?」) に対応できなかった。**Conversational RAG** を実装して、Slack/Discord bot や Claude Desktop からの対話的利用に耐える UX に引き上げる。

```
[現状 v0.6.0]
- /api/search, /api/answer は session 概念なし
- 1 クエリごとに完全独立、過去のやり取りはクライアントが文字列結合する必要あり
- Streamlit UI / Next.js UI ともに「履歴」コンポーネントなし

[変更後 v0.7 (spec_032)]
- /api/chat エンドポイント新設: {session_id?, question} → {answer, sources, session_id, history_summary?}
- session_id 省略時はサーバが UUID4 で発番
- 履歴 6 turn (=12 messages) までを Gemini Flash で「standalone question」に rewrite してから検索
- ConversationStore: in-memory dict + TTL (24h) + LRU (100 sessions)
- Streamlit UI に "Chat" タブ追加 (st.chat_input / st.chat_message)
- Next.js に /chat ページ追加 (履歴クライアント保持 + サーバ session_id 同期)
- Claude Desktop / MCP からも対話で使えるよう axis_chat tool 追加
```

## 2. 制約

### 触ってよいファイル

- `backend/src/conversation.py` — **新規** (ConversationStore + Message dataclass)
- `backend/src/question_rewriter.py` — **新規** (Gemini Flash で follow-up → standalone)
- `backend/src/rag.py` — `chat(session_id, question)` 関数追加
- `backend/src/api.py` — `POST /api/chat` 追加、`GET /api/chat/{session_id}` (履歴取得) 追加、`DELETE /api/chat/{session_id}` (リセット) 追加
- `backend/tests/test_conversation.py` — **新規**
- `backend/tests/test_question_rewriter.py` — **新規** (Gemini を mock)
- `backend/tests/test_api.py` — `/api/chat` の e2e
- `mcp_server/server.py` — `axis_chat` tool 追加 (`session_id`, `question`)
- `mcp_server/_session.py` — **新規** (MCP プロセス内の session keep)
- `streamlit_app.py` — Chat タブ追加 (`st.tabs(["Search", "Chat"])`)
- `frontend/src/app/chat/page.tsx` — **新規** (App Router 経由の chat ページ)
- `frontend/src/lib/chatClient.ts` — **新規** (fetch wrapper、session_id を localStorage に保持)
- `frontend/src/components/ChatMessage.tsx` — **新規**
- `frontend/src/components/ChatInput.tsx` — **新規**
- `docs/adr/ADR-018-conversational-rag.md` — **新規**
- `docs/api-reference.md` — `/api/chat` 仕様追加
- `docs/architecture.md` — Conversational フロー追加
- `README.md` — Features に 1 行、UI スクショ位置確保
- `CHANGELOG.md` — Day 32 追記
- `config.yml` — `chat.{enabled, max_history_turns, ttl_seconds, max_sessions}`
- `backend/src/config.py` — 上記キーを読み込み

### 触ってはいけないもの

- `backend/src/loader.py` / `embedder.py` / `vector_store.py` / `search.py` / `chunker.py` (spec_031 で別途) — ロジック変更なし、`rag.chat()` から既存 `search.search()` を呼ぶだけ
- `backend/src/ingester.py` / `normalizer.py` / `integrity.py` / `marker.py` / `bm25*.py`
- `_ai_workspace/`

### コーディングルール

- セッションストアは **in-memory のみ**。Redis / DB 連携は v0.8 候補 (spec_037)。v0.7 でも複数 worker (uvicorn --workers >1) では session が失われ得るので **single worker 前提** を docs/deployment.md に明記
- 既存パターン: Pydantic v2 + FastAPI v0.x + dataclass
- 新規依存追加なし (UUID は uuid、TTL は単純 dict の last_access タイムスタンプで実装)
- frontend は既存 Next.js 構成 (App Router + Tailwind + shadcn なし) に倣う

### デプロイ

- 本 spec は実装のみ。tag は v0.7.0 で一括

## 3. やってほしいこと

### 3-1. Conversation store (`backend/src/conversation.py`)

```python
"""In-memory chat session storage with TTL + LRU eviction."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Iterator
import uuid


@dataclass
class Message:
    role: str               # "user" | "assistant"
    content: str
    sources: list[dict] = field(default_factory=list)   # assistant のみ
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Session:
    session_id: str
    messages: list[Message] = field(default_factory=list)
    last_access: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationStore:
    """Thread-safe in-memory session store."""

    def __init__(self, *, max_sessions: int = 100, ttl_seconds: int = 86400):
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()
        self._max = max_sessions
        self._ttl = timedelta(seconds=ttl_seconds)

    def get_or_create(self, session_id: str | None = None) -> Session:
        with self._lock:
            self._evict_expired()
            if session_id and session_id in self._sessions:
                s = self._sessions[session_id]
                s.last_access = datetime.now(timezone.utc)
                return s
            new_id = session_id or str(uuid.uuid4())
            s = Session(session_id=new_id)
            self._sessions[new_id] = s
            self._evict_lru()
            return s

    def append(self, session_id: str, msg: Message) -> None: ...
    def get_history(self, session_id: str, *, last_n_turns: int = 6) -> list[Message]: ...
    def delete(self, session_id: str) -> bool: ...

    def _evict_expired(self) -> None: ...
    def _evict_lru(self) -> None: ...
```

**設計ポイント**:

- スレッドセーフ (uvicorn の async worker 内で問題が出ないように Lock 取得)
- TTL: 24 時間アクセスなし → eviction
- LRU: max_sessions 超過 → 最も古い last_access を捨てる
- last_n_turns: 履歴は最新 N ターンだけ取得 (ターン = user + assistant ペア)

### 3-2. Question rewriter (`backend/src/question_rewriter.py`)

```python
"""Rewrite follow-up questions into standalone queries using Gemini Flash."""

from __future__ import annotations
import google.generativeai as genai
from backend.src.conversation import Message


REWRITE_PROMPT = """\
あなたは検索クエリ書き換え専門のアシスタントです。
以下のチャット履歴を踏まえて、最後のユーザーの質問を「履歴を見なくても意味が通じる単独の検索クエリ」に書き換えてください。

- 履歴の文脈が必要なければ、元の質問をそのまま返してください
- 出力は書き換え後の質問テキスト 1 行のみ。前置きや説明は不要
- 固有名詞や技術用語は維持

[履歴]
{history}

[最後の質問]
{question}

[書き換え後の質問]"""


def rewrite_question(
    question: str,
    history: list[Message],
    *,
    model_name: str = "gemini-1.5-flash",
) -> str:
    """Return standalone query. Falls back to original on error."""
    if not history:
        return question
    history_text = "\n".join(
        f"{m.role}: {m.content[:200]}" for m in history[-6:]
    )
    try:
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content(
            REWRITE_PROMPT.format(history=history_text, question=question),
            generation_config={"temperature": 0.0, "max_output_tokens": 200},
        )
        rewritten = resp.text.strip()
        if not rewritten or len(rewritten) > 500:
            return question
        return rewritten
    except Exception:
        # Network / quota issues → fall back to original
        return question
```

**フォールバック方針**: API エラー時は元クエリで検索続行 (UX を止めない)。

### 3-3. RAG.chat() (`backend/src/rag.py`)

```python
def chat(
    question: str,
    *,
    session_id: str | None = None,
    axes: dict | None = None,
    store: ConversationStore | None = None,
) -> ChatResponse:
    store = store or get_default_store()
    session = store.get_or_create(session_id)

    history = session.messages[-12:]  # 6 turn = 12 messages
    rewritten = rewrite_question(question, history)
    hits = search(rewritten, axes=axes, k=5)
    answer, sources = answer_from_hits(question, hits, history_messages=history)

    store.append(session.session_id, Message(role="user", content=question))
    store.append(session.session_id, Message(
        role="assistant", content=answer, sources=sources,
    ))
    return ChatResponse(
        session_id=session.session_id,
        question=question,
        rewritten_question=rewritten if rewritten != question else None,
        answer=answer,
        sources=sources,
    )
```

`answer_from_hits` は既存 `answer()` を流用しつつ、Claude へのプロンプトに **直近 3 ターンの履歴** を添える:

```python
SYSTEM_PROMPT = """\
あなたは社内ナレッジ検索アシスタントです。
直近の会話履歴と、検索でヒットしたドキュメントを参考に、ユーザーの質問に答えてください。

- 答えはドキュメントに書かれた内容に忠実に
- 出典 (sources) を必ず明示
- 履歴と矛盾する内容は履歴を優先せず、ドキュメントに従う
"""
```

### 3-4. FastAPI endpoint (`backend/src/api.py`)

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None
    axes: dict | None = None


class ChatResponseModel(BaseModel):
    session_id: str
    question: str
    rewritten_question: str | None
    answer: str
    sources: list[dict]


@app.post("/api/chat", response_model=ChatResponseModel)
def post_chat(req: ChatRequest):
    resp = rag.chat(req.question, session_id=req.session_id, axes=req.axes)
    return ChatResponseModel(**asdict(resp))


@app.get("/api/chat/{session_id}")
def get_chat_history(session_id: str):
    session = store.get_or_create(session_id)
    return {
        "session_id": session.session_id,
        "messages": [asdict(m) for m in session.messages],
    }


@app.delete("/api/chat/{session_id}", status_code=204)
def delete_chat(session_id: str):
    if not store.delete(session_id):
        raise HTTPException(status_code=404, detail="session not found")
```

### 3-5. MCP tool (`mcp_server/server.py`)

```python
@mcp.tool()
def axis_chat(question: str, session_id: str | None = None) -> dict:
    """対話的検索 + 回答。session_id を保持すれば follow-up が効く。"""
    try:
        resp = rag.chat(question, session_id=session_id, store=_mcp_store)
        return {
            "session_id": resp.session_id,
            "answer": resp.answer,
            "sources": resp.sources,
            "rewritten_question": resp.rewritten_question,
        }
    except Exception as e:
        return make_error_response(e, tool="axis_chat")
```

MCP プロセスは長寿命なので、`_mcp_store = ConversationStore(max_sessions=20, ttl_seconds=3600)` をモジュール global で持つ。docs/mcp-server.md に「axis_chat の session は MCP プロセス再起動で消える」明記。

### 3-6. Streamlit "Chat" タブ (`streamlit_app.py`)

```python
import streamlit as st
import requests

API = "http://localhost:8000"

def main():
    st.title("axis-knowledge-rag")
    tab_search, tab_chat = st.tabs(["Search", "Chat"])
    with tab_search:
        _search_tab()
    with tab_chat:
        _chat_tab()


def _chat_tab():
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = None
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    for m in st.session_state.chat_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("sources"):
                with st.expander(f"出典 {len(m['sources'])} 件"):
                    for s in m["sources"]:
                        st.markdown(f"- **{s['title']}** ({s['doc_id']})")

    if q := st.chat_input("質問を入力"):
        st.session_state.chat_messages.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("考え中..."):
                r = requests.post(f"{API}/api/chat", json={
                    "question": q,
                    "session_id": st.session_state.chat_session_id,
                }, timeout=60).json()
            st.session_state.chat_session_id = r["session_id"]
            st.markdown(r["answer"])
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": r["answer"],
                "sources": r.get("sources", []),
            })
    if st.button("会話をリセット"):
        if sid := st.session_state.chat_session_id:
            requests.delete(f"{API}/api/chat/{sid}", timeout=10)
        st.session_state.chat_session_id = None
        st.session_state.chat_messages = []
        st.rerun()
```

### 3-7. Next.js `/chat` page

#### `frontend/src/app/chat/page.tsx`

```tsx
"use client";
import { useEffect, useState } from "react";
import { ChatMessage } from "@/components/ChatMessage";
import { ChatInput } from "@/components/ChatInput";
import { postChat, getStoredSessionId, setStoredSessionId, clearStoredSessionId } from "@/lib/chatClient";

type Msg = { role: "user" | "assistant"; content: string; sources?: any[] };

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => { setSessionId(getStoredSessionId()); }, []);

  async function send(q: string) {
    setMessages(m => [...m, { role: "user", content: q }]);
    setLoading(true);
    try {
      const res = await postChat({ question: q, session_id: sessionId });
      setSessionId(res.session_id);
      setStoredSessionId(res.session_id);
      setMessages(m => [...m, { role: "assistant", content: res.answer, sources: res.sources }]);
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    clearStoredSessionId();
    setSessionId(null);
    setMessages([]);
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">Chat</h1>
        <button onClick={reset} className="text-sm text-gray-500 hover:underline">リセット</button>
      </div>
      <div className="space-y-3 mb-4">
        {messages.map((m, i) => <ChatMessage key={i} msg={m} />)}
        {loading && <div className="text-sm text-gray-400">考え中...</div>}
      </div>
      <ChatInput onSend={send} disabled={loading} />
    </main>
  );
}
```

#### `frontend/src/lib/chatClient.ts`

```ts
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const KEY = "axis-chat-session-id";

export async function postChat(body: { question: string; session_id: string | null }) {
  const res = await fetch(`${API}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`chat failed: ${res.status}`);
  return res.json();
}

export const getStoredSessionId = () =>
  typeof window === "undefined" ? null : localStorage.getItem(KEY);
export const setStoredSessionId = (id: string) =>
  typeof window === "undefined" ? null : localStorage.setItem(KEY, id);
export const clearStoredSessionId = () =>
  typeof window === "undefined" ? null : localStorage.removeItem(KEY);
```

`ChatMessage.tsx` / `ChatInput.tsx` は既存 UI コンポーネント (SearchBar, ResultCard, AnswerPanel) のスタイルに揃える。

### 3-8. config.yml

```yaml
chat:
  enabled: true
  max_history_turns: 6        # 6 turn = 12 messages
  ttl_seconds: 86400          # 24h
  max_sessions: 100
  rewriter:
    model: "gemini-1.5-flash"
    enabled: true             # false なら rewrite skip (元クエリで検索)
```

### 3-9. テスト

#### `backend/tests/test_conversation.py`

- `test_get_or_create_new_session`: session_id=None → 新規 UUID
- `test_get_or_create_existing`: 同じ id を渡すと同じ session が返る
- `test_append_and_history`: append したものが get_history で取れる
- `test_history_truncation`: last_n_turns=3 で 6 messages
- `test_ttl_eviction`: 古い session が削除される (timestamp を手で操作)
- `test_lru_eviction`: max_sessions=2 で 3 つ作ると最古が消える
- `test_delete_session`: delete 後 get_or_create で別 UUID になる
- `test_thread_safety`: 100 並列 append でメッセージ全数残る

#### `backend/tests/test_question_rewriter.py`

- `test_empty_history_returns_original`: history=[] → 入力そのまま
- `test_rewrites_with_pronoun`: 「それの詳細は?」+ 前文「LangChain について」→ rewrite で「LangChain」が出現
- `test_api_error_falls_back`: Gemini 例外時、元クエリ返却
- `test_max_length_cap`: rewrite が 500 字超 → 元クエリにフォールバック

`google.generativeai.GenerativeModel` は `monkeypatch` でモック。

#### `backend/tests/test_api.py` 追加分

- `test_chat_creates_session`: 初回 POST → session_id 発番
- `test_chat_reuses_session`: 2 回目 POST に session_id 付きで送信 → 履歴が API 側に蓄積
- `test_chat_history_endpoint`: GET /api/chat/{sid} で履歴が返る
- `test_chat_delete_endpoint`: DELETE /api/chat/{sid} で 204 → 再 GET で 404

### 3-10. ADR-018

`docs/adr/ADR-018-conversational-rag.md`:

- Context: 単発 RAG では follow-up が無理
- Decision: in-memory ConversationStore + Gemini Flash rewriter
- Alternatives:
  - (a) LangChain ConversationBufferMemory → 却下 (依存重い)
  - (b) Redis session → 採用見送り (v0.8 候補)
  - (c) Full message history を Claude に毎回渡す → 部分採用 (rewrite + 直近 3 turn 添付の合わせ技)
- Consequences: single-worker 制約、24h TTL、再起動で消える

### 3-11. 動作確認

```bash
cd ~/projects/axis-knowledge-rag
git checkout -b feat/spec_032-conversational-rag

# Backend
ruff check .
python3 -m pytest -q backend/tests/test_conversation.py backend/tests/test_question_rewriter.py backend/tests/test_api.py -v
python3 -m pytest -q --cov=backend/src --cov-report=term-missing | tail -20

# Streamlit smoke
uvicorn backend.src.api:app --port 8000 &
sleep 3
streamlit run streamlit_app.py --server.port 8501 &
sleep 5
# (手動: ブラウザで Chat タブ確認)
curl -s -X POST http://localhost:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"question":"RAG とは何ですか"}' | jq .session_id
# 同じ session_id を再利用
SID=$(curl -s -X POST http://localhost:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"question":"RAG とは何ですか"}' | jq -r .session_id)
curl -s -X POST http://localhost:8000/api/chat -H 'Content-Type: application/json' \
  -d "{\"question\":\"それの利点は?\",\"session_id\":\"$SID\"}" | jq '{rewritten:.rewritten_question, ans:.answer}'
kill %1 %2

# Frontend
cd frontend
npm test 2>&1 | tail -20
npm run build 2>&1 | tail -10
```

### 3-12. コミット粒度

1. `feat(conversation): ConversationStore with TTL + LRU eviction`
2. `feat(question_rewriter): Gemini Flash follow-up rewriter with fallback`
3. `feat(rag): chat() with history-aware retrieval + generation`
4. `feat(api): POST/GET/DELETE /api/chat endpoints`
5. `feat(mcp): axis_chat tool with module-scoped session store`
6. `feat(streamlit): Chat tab with st.chat_input/message`
7. `feat(frontend): /chat page + ChatMessage/ChatInput components + chatClient`
8. `test: conversation / rewriter / api chat (>=15 new tests)`
9. `docs: ADR-018, api-reference, architecture, README features`
10. `chore: CHANGELOG Day 32`

`git push -u origin feat/spec_032-conversational-rag`

### 3-13. result_032.md に書くこと

- /api/chat 2 回連続呼び出しの実ログ (rewritten_question が効いている例)
- session TTL / LRU の挙動テスト結果
- Streamlit Chat タブと Next.js /chat のスクショ取得手順 (画像は手動)
- 全テスト数 (169 → 169+N)、ruff 緑、カバレッジ
- MCP axis_chat の呼び出しサンプル

## 4. 成功条件

- [ ] `POST /api/chat` で session_id 発番 + 再利用が動く
- [ ] follow-up 質問が rewriter で standalone に書き換えられる (テストで確認)
- [ ] Streamlit Chat タブで連続対話可能
- [ ] Next.js `/chat` ページで連続対話可能 + localStorage で session 復元
- [ ] MCP `axis_chat` tool が Claude Desktop から呼べる
- [ ] 既存 169 tests 緑、新規 chat 関連 >=15 件
- [ ] ruff 緑、CI 緑、Docker Build 緑
- [ ] ADR-018 / docs 全部更新
- [ ] git push 完了

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_032.md`

## 6. 質問があるとき

- **rewriter モデル**: gemini-1.5-flash で軽い (~1 円 / 100 回) 想定だが、quota が逼迫してたら `gemini-1.5-flash-8b` に降格 OK
- **uvicorn workers**: 本 spec は単一 worker 前提。Docker `CMD` で `--workers 1` 固定にする必要があるか確認 (現状 docker-compose.yml がどうなってるかは CC 側でチェック)
- **frontend 既存スタイル**: SearchBar 等がどんなクラス命名規則か、shadcn を使ってるかは CC が現物確認。既存に揃えてくれれば OK
- **history を Claude プロンプトに添付するか rewrite だけで良いか**: 本 spec では「rewrite + 直近 3 turn 添付」のハイブリッド。冗長なら直近 1 turn のみに削減してよい

迷ったら Open questions に書いて `status: blocked` で終了。

## 7. 補足

### 設計の意図

- LangChain を避けつつ、対話 UX で見劣りしない実装を最少コードで
- session storage は in-memory で **意図的に簡素化**: v0.7 の demo / 個人運用には十分。v0.8 で Redis 化を検討

### 将来の拡張余地

- spec_034 候補 (v0.7 サブ): In-Text Citation Highlighting — chat 回答内の出典番号と本文の対応表示
- spec_037 候補 (v0.8): Redis / sqlite で session 永続化、複数 worker 対応
- spec_038 候補 (v0.8): user 認証付きの multi-tenant session
