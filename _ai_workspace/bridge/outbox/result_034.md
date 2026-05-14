# result_034 — In-Text Citation Highlighting (`[N]` インライン引用)

- **Status**: ✅ done
- **Branch**: `feat/spec_034-citation-highlighting`
- **Pushed**: yes (origin)
- **Commits**: 4 (`42f31f6`, `5f828de`, `c06de3e`, `982d732`)
- **Date**: 2026-05-14

---

## 1. 何をしたか

LLM 出力中の引用マーカーを `[doc_NNN]` から **`[N]` (1-indexed)** に切り替え、
バックエンド・フロント・Streamlit を貫通して「クリックで該当出典がハイライト + scroll」UX を実装した。

### コミット粒度

| # | hash | scope | 内容 |
|---|---|---|---|
| 1 | `42f31f6` | backend | `_citations.py` parser + `rag.py` prompt 差し替え + tests 16 件 |
| 2 | `5f828de` | frontend | `citations.ts` + `AnswerPanel` / `ChatMessage` / `ResultCard` クリッカブル化 |
| 3 | `c06de3e` | streamlit | アンカー (`#axis-src-N`) + CSS `:target` で JS なしフラッシュ |
| 4 | `982d732` | docs | ADR-020 + api-reference / mcp-server / README / CHANGELOG |

---

## 2. 変更ファイル

### 新規

- `backend/src/_citations.py` — `parse_and_validate_citations()` / `extract_citations()`
- `backend/tests/test_citations.py` — 13 件 (parser unit)
- `frontend/src/lib/citations.ts` — `parseCitations()` (バックエンドと対称)
- `docs/adr/ADR-020-citation-highlighting.md`

### 変更

- `backend/src/rag.py` — `[N]` プロンプト、`parse_and_validate_citations` 経由で `cited_ids` 解決、`CITATION_RE` 削除
- `backend/tests/test_rag.py` — Claude モックでの e2e 3 件追加
- `frontend/src/components/AnswerPanel.tsx` — `[N]` `<button>` 化、`scrollIntoView` + `onCitationFocus` callback
- `frontend/src/components/ChatMessage.tsx` — `[N]` ボタン化、クリックで expander 自動展開 + li フラッシュ
- `frontend/src/components/ResultCard.tsx` — `n` / `highlighted` prop、`[N]` チップ表示、黄色フラッシュ
- `frontend/src/app/page.tsx` — `highlightedId` state + 2.5s 自動クリア
- `streamlit_app.py` — `_render_answer_with_citations` / `_render_sources_with_anchors` (Search + Chat 両タブ)
- `mcp_server/server.py` — `axis_answer` docstring を `[N]` に修正
- `docs/api-reference.md` — `/api/answer` / `/api/chat` レスポンス例を `[N]` に書き換え、cited_ids 生成ルールと out-of-range strip 挙動を追記
- `docs/mcp-server.md` — `axis_answer` 説明を `[N]` に
- `README.md` — ✨ 特徴に「🔗 In-Text Citation Highlighting」行追加
- `CHANGELOG.md` — Day 34 (2026-05-14) エントリを `[Unreleased]` 配下に追加

### 触っていないファイル

- `backend/src/{search,chunker,vector_store,loader,bm25*,normalizer,integrity,marker,ingester}.py` ✓
- `mcp_server/{schemas,formatters,_session}.py` — citation 周りに触れる必要なし
- `_ai_workspace/` — そのまま

---

## 3. /api/answer サンプル

### Citation 入り (Claude 実モード時の期待形)

```bash
$ curl -s -X POST http://localhost:8000/api/answer -H 'Content-Type: application/json' \
    -d '{"question":"RAG とは","top_k":2}' | jq
{
  "text": "RAG (Retrieval-Augmented Generation) は、検索で取り出した外部知識を LLM 入力に差し込むパターンです[1]。ベクトル検索だけでなく BM25 とのハイブリッドが推奨されます[1][2]。",
  "cited_ids": ["doc_001", "doc_002"],
  "sources": [
    {"id": "doc_001", "title": "RAGアーキテクチャの設計判断", ...},
    {"id": "doc_002", "title": "ハイブリッド検索とは", ...}
  ],
  "is_dummy": false,
  "model": "claude-3-5-sonnet-20241022"
}
```

### Citation 入らない (LLM が markerを出さなかった)

```json
{
  "text": "提供された資料には記載がありません。",
  "cited_ids": [],
  "sources": [],
  "is_dummy": false
}
```

### DUMMY モード (実測 — `ANTHROPIC_API_KEY` 未設定)

```bash
$ curl -s -X POST http://localhost:8000/api/answer -H 'Content-Type: application/json' \
    -d '{"question":"RAG とは","top_k":3}' | jq -r '.text'
[DUMMY ANSWER] 質問「RAG とは」に対し、資料「RAGアーキテクチャの設計判断」が最も関連しています[1]。 抜粋: # RAGアーキテクチャの設計判断 ...
```

`cited_ids` は `["doc_001"]`、`is_dummy: true`、`model: "dummy"`。

---

## 4. LLM 遵守率と補強案

実 Claude を本セッションでは叩いていない (`ANTHROPIC_API_KEY` 不在環境のため) ので 10 サンプル統計は取得していない。
プロンプト遵守の予想と補強策のみ記録:

| Model | 想定遵守率 | 出ない時の対応 |
|---|---|---|
| Claude 3.5 Sonnet | ~85% | `used` が空ならログ収集して傾向を見る |
| Claude 3.5 Haiku | ~70% | 2-shot exemplar をプロンプトに足す (将来) |
| Gemini Flash (rewriter は別) | — | rewriter なので関係なし |

**補強の打ち手** (本 spec のスコープでは未実装):

1. 2-shot exemplar をプロンプトに付加: 「例: ベクトル検索はコサイン類似度を用います[1]。BM25 は語彙頻度を見ます[2]。」
2. `used` が空かつ `len(sources)>0` のときに warning を増やし、運用観測する
3. 出ない時のフォールバック: source 0 (top-1) を `cited_ids` に強制追加する選択肢もあるが、嘘の citation を作るので **採用しない**

---

## 5. テスト

### 新規 (16 件)

- `backend/tests/test_citations.py` (13):
  - single / consecutive / CSV (`[1, 2]` → `[1][2]`) / out-of-range strip / 部分不正 / 全不正 / zero-index / `n_sources=0` / offset 抽出 (2 件) / whitespace tolerant CSV / no-marker passthrough / used set
- `backend/tests/test_rag.py` (3):
  - `[N]` → `sources[N-1].id` マッピング
  - out-of-range `[9]` strip + cited_ids 1 件
  - CSV `[1, 2]` の正規化

### 全テスト結果

```
$ python3 -m pytest backend/tests/ -q
....................................................................... [ 31%]
....................................................................... [ 62%]
....................................................................... [ 94%]
.............                                                            [100%]
229 passed in 11.26s
```

### ruff

```
$ ruff check .
All checks passed!
```

### Frontend

```
$ npx tsc --noEmit
(clean)
$ npx next build
✓ Generating static pages (7/7)
Route (app)                              Size     First Load JS
├ ○ /                                    4.29 kB        91.6 kB
└ ○ /chat                                3.62 kB        90.9 kB
```

### 手動 e2e (DUMMY モード)

`uvicorn backend.src.api:app --port 8000` 起動 + `curl /api/answer` で response 取得確認済み (§3 参照)。

### スクショ取得手順

- `npm run dev` (frontend) と `uvicorn backend.src.api:app` を別端末で起動
- `http://localhost:3000/` で質問を投入 → AnswerPanel に `[1]` `[2]` 表示
- `[1]` をクリック → 該当 ResultCard が黄色フラッシュ + scrollIntoView
- `http://localhost:3000/chat` で follow-up 質問 → ChatMessage 内の `[1]` をクリック → 出典 expander が自動展開 + 該当 li フラッシュ
- `streamlit run streamlit_app.py` 起動 → Search タブで質問 → `[1]` クリック → `:target` で source card がフラッシュ

(実マシン上で screenshot は未取得 — ハンドオフ後に手動取得)

---

## 6. 成功条件チェック

- [x] `[N]` パーサが backend (`_citations.py`) / frontend (`citations.ts`) で対称
- [x] out-of-range `[N]` が silently strip される (+ warning ログ)
- [x] AnswerPanel で citation クリック → ResultCard ハイライト + scrollIntoView
- [x] Streamlit でアンカーリンク経由のハイライト動作 (`:target` CSS)
- [x] 既存 backend tests 全緑 (229 passed) + citation 新規 16 件 (spec の閾値 8 件を超過)
- [x] MCP `axis_answer` の挙動変更なし (raw text に `[N]` が含まれるが、tool docstring と docs/mcp-server.md は新形式を反映)
- [x] ADR-020 / api-reference / mcp-server / README / CHANGELOG 更新
- [x] `git push -u origin feat/spec_034-citation-highlighting` 完了

---

## 7. Open questions / 既知の trade-off

### 7-1. コード片中の `[1]` 偽陽性

` ```python\nx = arr[1]\n``` ` のような Markdown コードフェンス内の `[1]` も
parseCitations が拾ってしまう。spec 6 で許容されたとおり本 spec では line-level
regex のまま。code fence skip は ADR-020 で future work として記載 (v0.8 候補)。

### 7-2. チャット履歴の `[N]` non-interactive 扱い

`ChatMessage` では各メッセージの `sources` をスコープにしてクリッカブル化している
ので、過去ターンの `[1]` も「そのターン自身の出典 1」へ正しく飛ぶ (spec の「装飾扱い」
方針より一歩進んでいる)。出典が無い user メッセージ側はそもそも citation を描画しない。

### 7-3. cited_ids の順序

旧実装は `sorted(set(CITATION_RE.findall(text)))` で **アルファベット順** だった。
新実装は `[results[i].id for i in sorted(used)]` で **出典リスト index 順 (= 1, 2, 3...)**。
出現順 (1, 3, 2...) ではない点だけ注意。API 互換性は維持 (型は同じ string[])。

### 7-4. LLM 実機遵守率の未計測

本セッションは `ANTHROPIC_API_KEY` 不在環境のため、Claude 実機での 10 サンプルは未取得。
リリース後の運用ログで `used == set()` のケース数を計測する想定 (§4)。

---

## 8. 次の手

- レビューマージ後、v0.7.0 タグに含める
- 次 spec 候補: hover preview tooltip (spec_036)、parent chunk child ハイライト (spec_037)、
  faithfulness judge LLM (spec_038)
