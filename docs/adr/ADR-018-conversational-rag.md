# ADR-018: Conversational RAG (履歴保持チャット)

- **Date**: 2026-05-14
- **Status**: Accepted
- **Deciders**: 中島
- **Spec**: spec_032

## Context

v0.6 までの `/api/search` / `/api/answer` はすべて単発クエリだった。
クライアント (Slack bot / Claude Desktop / Streamlit / Next.js UI) が
follow-up 質問 — 「もっと詳しく」「それはなぜ?」 — を投げると、
代名詞 (「それ」「あれ」) の参照先が失われて検索精度が劣化する。

LLM チャット UX を期待される現在、これは v0.7 の本流欠陥だった。
chat 形式に対応しないと Slack/Discord bot や対話的 UI に乗らない。

## Decision

**履歴を持つ `chat()` パスを追加する**。最小設計:

1. **In-memory ConversationStore** (`backend/src/conversation.py`)
   - TTL (default 24h) + LRU (default 100 sessions)
   - スレッドセーフ (`threading.Lock`)
   - **Redis / DB は不採用**。v0.8 で検討 (spec_037 候補)
2. **Question rewriter** (`backend/src/question_rewriter.py`)
   - Gemini Flash (`gemini-1.5-flash`) で「履歴 + 最終質問 → standalone クエリ」を生成
   - 失敗時 (no API key / 例外 / 出力空 / 500 字超) は **元クエリにフォールバック** — UX を絶対に止めない
3. **`rag.chat()`** — rewrite → 検索 → 生成 → 履歴 append
   - 生成プロンプト (`CHAT_SYSTEM_PROMPT`) には直近 3 ターンも添付して代名詞/話題継続を解決
   - 履歴と検索結果が矛盾した場合は **検索結果を優先** (= 履歴を真実の源にしない)
4. **3 つの新エンドポイント**:
   - `POST /api/chat` — session_id 省略時は UUID4 発番
   - `GET /api/chat/{session_id}` — 履歴取得
   - `DELETE /api/chat/{session_id}` — リセット (204)
5. **クライアント**: Streamlit に Chat タブ、Next.js に `/chat` ページ、MCP に `axis_chat` ツール
6. **Single-worker 前提**: 複数 uvicorn worker では session が見えなくなる旨を docs で明記

## Alternatives

### (a) LangChain `ConversationBufferMemory` を導入 — 却下

- ADR-001 で LangChain 不採用としている設計方針と矛盾
- 依存が重い (langchain + langchain-core + 推移依存)
- 自前実装で 150 行未満で書けるため、追加価値が薄い

### (b) Redis セッションストア — 採用見送り (v0.8 候補)

- Redis 依存は OSS の "local-first" 方針 (README §特徴) と相性が悪い
- v0.7 のターゲットは demo / 個人運用 → in-memory で十分
- 複数 worker + 永続化が欲しくなったら spec_037 で導入する余地は残す

### (c) Full message history を毎回 Claude に渡す (no rewrite) — 部分採用

- 履歴が長くなるとコンテキスト圧迫 + 検索クエリの精度低下
- 採用方針は **「rewrite で検索クエリは standalone 化、生成プロンプトにも直近 3 turn 添付」のハイブリッド**
- 検索精度が rewrite で確保され、自然な会話感は短い履歴添付で確保される

### (d) Server-Sent Events / WebSocket でストリーミング — 却下 (v0.7 範囲外)

- chat 1 turn は通常 < 10 秒なので JSON で十分
- ストリーミングは v0.8 以降の UX 強化候補

## Consequences

### Positive

- Slack/Discord bot や Claude Desktop で対話的に使える UX に到達
- LangChain 依存ゼロを維持 (ADR-001 整合)
- rewrite 失敗時のフォールバックで Gemini 不在 / quota 切れでも止まらない

### Negative / 制約

- **single uvicorn worker 前提**: `--workers >1` だと worker ごとに別 store になる
- **再起動で session が消える**: Docker / systemd で再起動すると履歴ロスト
- **Gemini quota コスト**: rewrite 1 回 ≒ 1k input + 200 output token = ~$0.0001 / call。月 10k call で ~$1
- **MCP プロセスの session は独立**: MCP の `axis_chat` は MCP プロセス内 store を使うので、FastAPI 側と共有しない (意図的)

### v0.8 拡張余地

- spec_034 候補: In-text citation highlighting (chat 回答内 `[doc_NNN]` → 出典展開)
- spec_037 候補: Redis / SQLite session 永続化、複数 worker 対応
- spec_038 候補: 認証付き multi-tenant session

## Implementation pointers

- `backend/src/conversation.py` — ConversationStore + Message dataclass
- `backend/src/question_rewriter.py` — rewrite_question() + Gemini Flash wrapper
- `backend/src/rag.py` — `RAGPipeline.chat()`、`ChatResponse`、`CHAT_SYSTEM_PROMPT`
- `backend/src/api.py` — `/api/chat` 3 endpoints + lifespan で `ConversationStore` 初期化
- `mcp_server/server.py` — `axis_chat` tool + `mcp_server/_session.py` モジュール global store
- `streamlit_app.py` — `st.tabs(["🔎 Search", "💬 Chat"])` で旧 UI と並列表示
- `frontend/src/app/chat/page.tsx` — App Router、localStorage で session 復元
- `config.yml > chat.*` — 全パラメータを設定ファイルから差し替え可能

## Acceptance

- 既存 169 tests + 新規 24 tests = 193 全パス
- ruff 緑
- `POST /api/chat` 2 回で `rewritten_question` フィールドが代名詞解決を反映
