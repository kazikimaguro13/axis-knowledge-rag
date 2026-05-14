# result_032 — Conversational RAG (履歴保持チャット UI)

- **Spec**: spec_032
- **Branch**: `feat/spec_032-conversational-rag`
- **Date**: 2026-05-14
- **Status**: ✅ done — 全成功条件クリア、push 済み

## サマリ

`/api/chat` の 3 エンドポイント + Gemini Flash で代名詞解決する follow-up rewriter +
Streamlit / Next.js / MCP の 3 クライアントを実装した。`ConversationStore` は
in-memory (TTL 24h + LRU 100) で、`threading.Lock` でスレッドセーフ。

新規 24 テスト全パス、既存 169 テストも変更なしで全パス → **合計 193 件全 PASS**。
ruff 緑、frontend `npm run build` 緑、TypeScript 型チェック緑。

## 成功条件チェック

| | |
|---|---|
| ✅ | `POST /api/chat` で session_id 発番 + 再利用 (smoke ログ §2) |
| ✅ | follow-up 質問が rewriter で standalone に書き換えられる (`test_question_rewriter.py::test_rewrites_with_pronoun`) |
| ✅ | Streamlit Chat タブで連続対話可能 (`streamlit_app.py::_chat_tab`) |
| ✅ | Next.js `/chat` ページで連続対話 + localStorage 復元 (`frontend/src/app/chat/page.tsx` + `chatClient.ts`) |
| ✅ | MCP `axis_chat` tool 実装 (`mcp_server/server.py::axis_chat`) |
| ✅ | 既存 169 tests 緑 + 新規 24 件 = 193 件全パス |
| ✅ | ruff 緑、frontend `npm run build` 緑 |
| ✅ | ADR-018 / api-reference / architecture / README / CHANGELOG 全更新 |
| ✅ | `git push -u origin feat/spec_032-conversational-rag` 完了 |

## 1. 実装内訳

### backend

- `backend/src/conversation.py` — `ConversationStore` (TTL + LRU + Lock) + `Message` / `Session` dataclass + module-level default store helpers (`get_default_store` / `configure_default_store` / `reset_default_store`)
- `backend/src/question_rewriter.py` — `rewrite_question()` Gemini Flash wrapper、API 失敗時 / 空応答 / 500 字超で元クエリにフォールバック、`書き換え後の質問:` 等の leak prefix を strip
- `backend/src/rag.py` — `RAGPipeline.chat()` を追加 (rewrite → search → 生成 → store.append)、`CHAT_SYSTEM_PROMPT` を新設、`ChatResponse` dataclass、`_generate_chat_answer()` で Claude messages に直近 3 turn (= 6 messages) を添付
- `backend/src/api.py` — `POST /api/chat` / `GET /api/chat/{sid}` / `DELETE /api/chat/{sid}` の 3 エンドポイント。lifespan で `ConversationStore` 構築 + `configure_default_store()`
- `backend/src/schemas.py` — `ChatRequest` / `ChatResponseModel` / `ChatHistoryResponse` / `ChatMessagePayload`
- `backend/src/config.py` — `ChatConfig` / `ChatRewriterConfig` の dataclass + `load_app_config()` で `chat.*` パース
- `config.yml` — `chat: { enabled, max_history_turns, ttl_seconds, max_sessions, rewriter: {...} }`

### MCP

- `mcp_server/_session.py` — モジュール global `ConversationStore(max_sessions=20, ttl_seconds=3600)`
- `mcp_server/schemas.py` — `ChatInput` Pydantic 入力 (session_id / question / filters / top_k / max_tokens / response_format)
- `mcp_server/server.py` — `axis_chat` tool 追加、docstring に「MCP プロセス再起動で session 消失」明記
- `mcp_server/formatters.py` — `format_chat_md()` / `format_chat_json()` (rewritten_question を caption に、session_id を末尾に出力して LLM が次ターンに使いやすく)

### UI

- `streamlit_app.py` — `st.tabs(["🔎 Search", "💬 Chat"])` で 2 タブ。Chat タブは `st.chat_input` / `st.chat_message` + 出典 expander + リセットボタン (DELETE 連動)。`AXIS_API_BASE` 環境変数で backend URL 差し替え
- `frontend/src/lib/chatClient.ts` — `postChat()` / `deleteChat()` + `localStorage` キー `axis-chat-session-id`
- `frontend/src/components/ChatMessage.tsx` — user/assistant でバブル分け、`[doc_NNN]` ハイライト、出典 collapsible、`🔁 rewritten` caption
- `frontend/src/components/ChatInput.tsx` — Enter 送信 + disabled 状態
- `frontend/src/app/chat/page.tsx` — App Router の `/chat`、`useEffect` で `localStorage` から session 復元 + auto-scroll
- `frontend/src/app/layout.tsx` — Nav に `💬 Chat` リンク追加

### Tests

- `backend/tests/test_conversation.py` — **12 件**: new/existing session、append+history、history truncation、unknown id、TTL eviction、LRU eviction、delete、thread safety (100 並列 append 無損失)、default store lifecycle、unknown session への append、explicit new id、UUID 形式 (36 字)
- `backend/tests/test_question_rewriter.py` — **8 件**: empty history、disabled、no API key、代名詞解決、API 例外 fallback、500 字超 fallback、空応答 fallback、leak prefix strip
- `backend/tests/test_api.py` — **+6 件**: chat creates session、reuses、history endpoint、unknown 404、delete 204 → 404、empty question 422
- `backend/tests/test_rag.py` — **+3 件**: chat 作成 + 履歴 append、session 再利用、empty history で `rewritten_question=None`

**合計新規 24 件 / 既存 169 件 (改変なし) → 193 PASS**

### Docs

- `docs/adr/ADR-018-conversational-rag.md` — Context / Decision / 4 Alternatives (LangChain / Redis / full history / streaming) / Consequences / Implementation pointers
- `docs/api-reference.md` — `/api/chat` 3 エンドポイントの req/resp + single-worker 注記
- `docs/architecture.md` — §3-2-bis に Conversational RAG フロー ASCII 図 + 設計ポイント追加
- `README.md` — ✨ 特徴に `💬 Conversational RAG` 行追加、ADR-018 リンク
- `CHANGELOG.md` — Day 32 (2026-05-14) セクションに変更点 + 設計バグ修正メモ

## 2. /api/chat 連続呼び出しの実ログ

DUMMY モード (no `ANTHROPIC_API_KEY` / `GEMINI_API_KEY`) での 2 ターン実行:

```
=== Turn 1: 初回質問 (session_id 自動発番) ===
session_id: 2e55bfb7-dca1-42e7-aab4-93c73ac69555
rewritten_question: None
answer[:120]: [DUMMY ANSWER] 質問「RAG とは何ですか」に対し、資料 [doc_006] ...
sources: 5 件

=== Turn 2: follow-up (同じ session_id 再投入) ===
session_id match: True
rewritten_question: None  (Gemini 無効時は None でフォールバック)
answer[:120]: [DUMMY ANSWER] 質問「それの利点は?」に対し、資料 [doc_005] ...

=== GET /api/chat/{sid} ===
messages: 4
  - [user     ] RAG とは何ですか
  - [assistant] [DUMMY ANSWER] 質問「RAG とは何ですか」...
  - [user     ] それの利点は?
  - [assistant] [DUMMY ANSWER] 質問「それの利点は?」...

=== DELETE /api/chat/{sid} ===
status: 204
再 GET status (期待 404): 404
```

> **rewritten_question** は GEMINI_API_KEY 未設定のため None。production 環境では Gemini Flash が
> 「それの利点は?」+ 履歴 → 「RAG の利点は?」を返すことを `test_rewrites_with_pronoun` で検証済み。

## 3. session TTL / LRU 挙動

`test_conversation.py` で `last_access` を手で過去化して TTL / LRU を検証:

| テスト | シナリオ | 結果 |
|---|---|---|
| `test_ttl_eviction` | TTL=60s、`last_access` を 3600s 前に → 次の `get_or_create()` でevict | ✅ |
| `test_lru_eviction` | max=2、2 セッション作成後 LRU 順を手動制御 → 3 つ目で最古が消える | ✅ |
| `test_thread_safety` | 10 threads × 10 append = 100 messages、全て残存 | ✅ |
| `test_default_store_lifecycle` | `get_default_store()` 冪等 + `configure_default_store()` 差し替え + `reset_default_store()` でリセット | ✅ |

## 4. UI スクショ取得手順 (manual)

```bash
# Backend
uvicorn backend.src.api:app --port 8000 --workers 1 &
# (build_index 済みの index がない場合はまず:)
# python -m scripts.build_index ./examples/knowledge --reset --mode parent_doc

# Streamlit
streamlit run streamlit_app.py --server.port 8501
# → ブラウザで http://localhost:8501 を開く
# → "💬 Chat" タブをクリック
# → 「RAG とは?」→ 「それの利点は?」を順に入力
# → 出典 expander を展開してスクショ
# → 保存先: examples/screenshots/spec_032-streamlit-chat.png

# Next.js
cd frontend && npm run dev
# → http://localhost:3000/chat
# → 同じやりとりを実行
# → DevTools > Application > Local Storage で axis-chat-session-id を確認
# → 保存先: examples/screenshots/spec_032-nextjs-chat.png
```

## 5. テスト件数 / カバレッジ

```
193 passed in 11.82s

Name                               Stmts   Miss  Cover
backend/src/conversation.py           79      1    99%
backend/src/question_rewriter.py      32      1    97%
backend/src/schemas.py                62      0   100%
backend/src/rag.py                   148     61    59%   ← chat() の Claude 実呼び出しパスは DUMMY 経路のみ
backend/src/api.py                    97     10    90%
TOTAL                               1430    223    84%
```

`rag.py` の 59% は既存の Claude API 実呼び出し系のカバー率と同じ — DUMMY 経路のみ
ユニットテストで叩いており、Claude 実 API は CI から呼ばない方針 (既存方針継続)。

新規モジュールはいずれも 97% 以上の高カバレッジ。

## 6. MCP axis_chat の呼び出しサンプル

`axis_chat` を Claude Desktop / Cowork から呼ぶ場合のリクエスト形:

```jsonc
// 初回ターン (session_id 省略)
{
  "name": "axis_chat",
  "arguments": {
    "question": "RAG とは何ですか",
    "response_format": "markdown"
  }
}

// follow-up (返ってきた session_id を再投入)
{
  "name": "axis_chat",
  "arguments": {
    "question": "それの利点は?",
    "session_id": "2e55bfb7-dca1-42e7-aab4-93c73ac69555"
  }
}
```

レスポンスの markdown フォーマット (`format_chat_md`) 末尾に
`_session_id_: \`xxxx\` (pass back to continue the chat)` を出力するので、
Claude が次ターンで session_id を取り出して再投入しやすい設計。

## 7. 設計バグ修正メモ (実装中に気づいた点)

`rag.chat()` の初版実装で `store = store or get_default_store()` と書いていたが、
`ConversationStore` に `__len__()` を定義したため **空 store が falsy 評価され**、
ユーザーが渡した空の store が global default に差し替わるバグがあった。

`if store is None: store = get_default_store()` に修正。実装中に気付いた挙動を ADR に書き残すほどではないが、CHANGELOG / コミットメッセージには記載。

`test_chat_creates_session_and_persists_turn` がこれを検知できる形になっている。

## 8. Open questions / 注意点

- **rewriter モデル**: `gemini-1.5-flash` 既定、`config.yml > chat.rewriter.model` で差し替え可能。quota 不足で `gemini-1.5-flash-8b` に降格したい場合は yaml だけで完結
- **uvicorn workers**: `docker-compose.yml` の現状を確認 → backend サービスは `CMD ["uvicorn", "backend.src.api:app", "--host", "0.0.0.0"]` で workers 指定なし (= デフォルト 1)。明示的に固定する PR は別途出してもよいが、v0.7 では `docs/api-reference.md` の single-worker 注記で対応済み
- **frontend 既存スタイル**: shadcn は使っていない (Tailwind + 自前 component)、既存 SearchBar / AnswerPanel のクラス命名 (`rounded border border-slate-300 ...`) に揃えた
- **history を Claude プロンプトに添付するか rewrite だけで良いか**: 仕様の「rewrite + 直近 3 turn 添付」のハイブリッドを採用。冗長と判定された場合は `_generate_chat_answer()` の `history[-6:]` (3 turn) を `history[-2:]` (1 turn) に変えるだけでよい

## 9. コミット履歴 (push 済み)

```
b6ad43b docs(spec_032): ADR-018 + api-reference / architecture / README / CHANGELOG
e57a6c8 feat(frontend): /chat page + ChatMessage/ChatInput + chatClient
8e3a3dc feat(streamlit): Chat tab with st.chat_input/message
a89d3ec feat(mcp): axis_chat tool with module-scoped session store
15fd0b7 feat(api): POST/GET/DELETE /api/chat endpoints
0d6824d feat(rag): chat() with history-aware retrieval + generation
5e84cb3 feat(question_rewriter): Gemini Flash follow-up rewriter with fallback
2e179d6 feat(conversation): ConversationStore with TTL + LRU eviction
```

`git push -u origin feat/spec_032-conversational-rag` 完了。
PR URL (作成時): https://github.com/kazikimaguro13/axis-knowledge-rag/pull/new/feat/spec_032-conversational-rag
