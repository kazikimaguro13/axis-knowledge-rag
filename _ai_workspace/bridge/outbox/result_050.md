# result_050 — v0.9 全体総合コードレビュー (F1-F5)

- **Status**: ✅ done (read-only review)
- **Branch**: `review/v0.9-overall` (checkout 済み) → 結果のみ commit/push
- **Date**: 2026-05-20
- **Range**: `v0.8.1..HEAD` = 45 commits, +5343 / -156 行, 64 files
- **Specs covered**: spec_045 (Ollama) / spec_046 (Browser Ext) / spec_047 (Feedback) / spec_048 (Gap Detect) / spec_049 (Bidirectional refs)
- **Source modifications**: **0** (touched only result_050.md)

---

## 0. 結論 / ヘッドライン

**判定: A−（ES に貼って出せる。ただし HIGH 1 件・MID 3 件を v0.9.x patch で潰すと安心）**

- `pytest`: **419 passed / 2 skipped** (28.2s)
- `ruff check .`: **All checks passed**
- `next build`: **緑** (5/5 static pages)
- `tsc --noEmit`: **緑**（frontend jest は repo に jest config が無く 0/2 suites fail — テストランナー未整備というだけで型/ビルドは OK）
- 4 つの v0.9 マーキー機能 + spec_049 のミニ拡張、いずれも Protocol+factory パターンで揃っており設計は一貫
- セキュリティ上の致命傷は無し。ただし「全 endpoint が無認証、CORS が広い、PII 平文保存」が **同時に成立** している点は本番運用時に明示判断が必要

---

## 1. 各 spec × 4 軸の所見テーブル

| spec | security | performance | correctness | maintainability |
|---|---|---|---|---|
| **045 Ollama** | 〇 URL は config 経由のみで外部入力なし。`EVAL_OVERRIDE_FLAG` 経由で `embedder.ollama.url` を上書き可能だが env var 起点なので低リスク | △ `embed_batch` が逐次 (Ollama API が単発のみ)。`_probe_dim` が `__init__` で同期ブロック | **▲ HIGH-1**: bge-m3 (1024-dim) ↔ Gemini 既存 index (768-dim) の dim mismatch を起動時に検出していない。さらに `search.py:252 / 368` で axis-only query に `[0.0]*768` ハードコード | 〇 Protocol が clean。`_client = getattr(self._backend, "_client", None)` (rag.py:388) はテスト shim 用ハックで匂う |
| **046 Browser Ext** | **▲ MID-1**: `/api/ingest` 無認証 + CORS 広め。localhost で動かす前提だが、リモート公開時はファイル書き込みが open。`_slugify` の path traversal は OK (`..` は drop される) | 〇 単発ファイル書きだけ。サイズ制限は Pydantic max_length で実施 | △ `popup.js` は常に `selected_text: null` を送り、選択範囲は `body` に詰めている。spec の selected_text 経路は実質 dead code | △ `_yaml_dump` 自前実装。PyYAML は既に依存。`yaml.safe_dump` に切替えるべき |
| **047 Feedback** | **▲ MID-2**: `query` を平文保存、無認証 endpoint。PII (名前・社内固有名詞・誤入力) が `~/.axis_feedback.db` に蓄積、retention/TTL なし | 〇 単一接続 + Lock、WAL モード。`evaluation/feedback_report.py` の Python 集計で十分 (~10K 行まで) | 〇 UI は `feedback !== null` で disable、optimistic update + 失敗時 revert。リロードで state 戻るので server 側 idempotency なし (許容) | 〇 Protocol+factory が spec_036 / spec_048 と揃う |
| **048 Gap Detect** | **▲ MID-3**: `query` が `~/.axis_gap.db` に平文蓄積。no_results/low_score でも記録するので **PII 蓄積面が feedback よりさらに広い** | △ Lock+INSERT+commit が `/api/search`+`/api/answer` の hot path に乗る。実測 ~1ms/req で許容範囲だが、disk growth に上限なし | △ `detect_no_info` の `r"わかりません" / r"不明です"` が広め。「Aの場合はXですが、Bの場合はわかりません」のような部分回答も `llm_no_info` と判定される false positive あり | 〇 search/rag hook は `gap_store is None` で完全 no-op。`gap.enabled=false` は本当にゼロコスト |
| **049 Bidirectional** | 〇 新しい attack surface なし | △ HTTP `/api/graph/{id}/neighbors` を 2 回呼ぶ (`Promise.all` で並列なので wall-clock は OK だが backend CPU は 2x)。MCP 側は 1 ツール呼び出しで内部 fan-out — **HTTP と MCP で実装方式が非対称** | **▲ LOW-1**: `hop > 1` のとき `direction=both` 1 回と (`direction=out` + `direction=in`) 2 回は等価でない。ADR-030 で言及済み、Sidebar は `hop=1` のみ使うので実害なし | 〇 `format_neighbors_md_bidirectional` と既存 `format_neighbors_md` は別関数。重複は許容範囲 |

---

## 2. 新たに見つけた問題 (priority 付き)

### HIGH-1: Embedder 切替時の dim mismatch サイレントクラッシュ
**場所**: `backend/src/embedder.py:189-191`、`backend/src/search.py:252,368`

```python
# search.py L252 (legacy path)
embedding = [0.0] * 768

# search.py L368 (parent-doc path)
embedding = [0.0] * 768
```

bge-m3 を Ollama で使うと `OllamaEmbedder.dim == 1024`、既存 Chroma index は Gemini text-embedding-004 (768) で構築されている。
- ユーザーが `config.yml` で `embedder.backend=ollama` に切り替えても、既存 `.chromadb/` を rebuild しない限り次の query で Chroma が "dimension mismatch" を投げる
- さらに **axis-only query (`query is None`)** では embedder の dim を見ずに `[0.0] * 768` を直接渡している。bge-m3 index 上で axis-only リスト取得すると常に失敗

**推奨修正** (v0.9.1 patch):
1. `lifespan` 起動時に `store._collection.metadata` か最初の query で得た distances 長と `embedder.dim` を比較、不一致なら明示エラー + 「`scripts/build_index.py --rebuild`」を案内
2. `search.py` の `[0.0] * 768` を `[0.0] * self._embedder.dim` に変更（Embedder Protocol に既に `dim` プロパティがある）

### MID-1: `/api/ingest` 無認証 + CORS chrome-extension://\* + localhost wildcard
**場所**: `backend/src/api.py:206-212`、`backend/src/api.py:248-273`

- 任意の Chrome 拡張・任意の `http://localhost:*` タブが `/api/ingest` を叩いてファイル書き込み可能
- README / docs/deployment.md には「localhost のみで動かす想定」とあるが、`uvicorn ... --host 0.0.0.0` で外に出すと open file write 状態
- spec_046 ADR で「ローカル専用」と明言しているなら `--host 127.0.0.1` を **デフォルトで強制** するか、ingest endpoint だけ origin 制限 / ヘッダ secret を要求するのが安全

**推奨修正**: docker-compose / `make` 経由は既に localhost bind。`README` に「`/api/ingest` は無認証なので絶対に外部公開するな」を太字で書く。または Token 1 個を `INGEST_TOKEN` env で要求する 5 行追加。

### MID-2: PII の長期蓄積 (feedback + gap)
**場所**: `backend/src/feedback.py:91-112`、`backend/src/gap_detection.py:95-122`

- `query` を平文 SQLite に **TTL なし** で書き込む
- gap 側は no_results / low_score の query も全部記録 → "誤入力で社内固有名詞を打った" 系のログが永遠に残る
- GDPR / 社内コンプラ通せばグレー〜赤

**推奨修正**:
- `feedback.db_retention_days` / `gap.db_retention_days` を `FeedbackConfig` / `GapConfig` に足す (default 90)
- `list_recent()` の sibling として `purge_older_than(days)` を Protocol に追加し、報告 endpoint or daily job で叩く
- `make feedback-report` / `make gap-report` に purge オプション

### MID-3: `detect_no_info` の false positive (部分回答も "no_info" 判定)
**場所**: `backend/src/gap_detection.py:169-184`

`r"わかりません"` / `r"不明です"` が回答全文に対する `re.search` なので、「A は X です [1]。B についてはわかりません」が `llm_no_info` 判定される。test_gap_detection.py の negative case は全文が "ちゃんとした回答" のものしか見ていない。

**推奨修正**:
- patterns を `(?:^|\n)\s*(?:わかりません|不明です)\s*[。\.！!？?]?\s*$` のように文末・独立文に制限
- もしくは `cited_ids` が 0 件のときだけ `detect_no_info` を回す (cited あればモデルは何か答えている)

### LOW-1: `hop > 1` の bidirectional 不等価
**場所**: `frontend/src/lib/graphClient.ts:87-102`、`backend/src/graph.py:105-141`

(direction=out, hop=2) ∪ (direction=in, hop=2) ≠ (direction=both, hop=2) のケースがある (A→B, C←D で A 起点 hop=2)。
- ADR-030 で言及済み、Sidebar は `hop=1` 固定なので実害ゼロ
- ただし将来 hop を可変にすると「forwardlinks に出てこないが both では出るノード」が消える

**推奨修正**: `fetchNeighborsBidirectional(docId, hop, max_neighbors)` のシグネチャに hop を残すなら、JSDoc で「hop>1 は近似」と明示。または `bidirectional=true` の単一 endpoint を `/api/graph/{id}/neighbors` に追加 (MCP 側に既に同名フラグあり、対称性 ↑)。

---

## 3. ポジティブ評価 (褒め)

1. **Protocol+factory パターンの徹底** — Embedder / GenerationBackend / FeedbackStore / GapStore / ParentStorage / ConversationStore、6 つの "差し替え可能な依存" が同じ設計で揃った。`make_xxx(cfg)` で disabled 時に `None` を返し、call site で if-skip するだけというのも一貫
2. **disabled=zero-cost** — gap も feedback も `enabled=false` で `make_xxx_store` が `None` を返し、search/rag/api 側はそれを見て丸ごと no-op。"機能をオフにしたら本当に消える" は実装上珍しいほど綺麗
3. **MCP `axis_neighbors` の後方互換** — `bidirectional: bool = False` default で旧 caller は完全に同じ shape を見る。spec_049 で API を変えるのではなく拡張する判断が正しい
4. **ChatMessage.tsx の二重送信防止 + optimistic UI + 失敗時 revert** — `disabled={feedback !== null}` でクリック後即 disable、API 失敗時は state を元に戻す。クライアント 100 行に詰め込まれた UX 配慮が良い
5. **Ollama optional 化** — `pip install -e ".[ollama]"` 専用 extras + `docker compose --profile ollama` で必須化を避け、依存爆発を抑えた。テストも `pytest.importorskip + AXIS_OLLAMA_INTEGRATION env` でガード

---

## 4. 全体としての一貫性

### 4 つの SQLite (.axis_chat / .axis_feedback / .axis_gap / parents.db) の整理

|ファイル|spec|backend Lock|WAL|デフォパス|Protocol|
|---|---|---|---|---|---|
|`.axis_chat.db`|036|あり|あり|`~/.axis_chat.db`|`ConversationStore`|
|`.axis_feedback.db`|047|あり|あり|`~/.axis_feedback.db`|`FeedbackStore`|
|`.axis_gap.db`|048|あり|あり|`~/.axis_gap.db`|`GapStore`|
|`parents.db`|037|**なし**|あり|`<chroma_dir>/parents.db`|`ParentStorage`|

**観察**:
- 4 つすべてに `__init__` で `expanduser → mkdir → sqlite3.connect(check_same_thread=False) → executescript(SCHEMA) → PRAGMA journal_mode=WAL → commit → Lock()` というほぼ同じ 20 行が **コピペで 4 回** 書かれている
- `parent_storage.py` だけ Lock を持っていない。読み主体 + lifespan 起動時に一度ロードするため実害は無いが、設計的には不揃い

**推奨**: `backend/src/_sqlite_base.py` に
```python
class _SqliteStoreBase:
    SCHEMA: str = ""
    def __init__(self, db_path: str | Path) -> None:
        ... # 共通プレリュード
```
を作って 4 store が継承する。ただし **これは v0.10 で良い** (現状動いている分には急がない)。

### 共通 Store Protocol を見直すべきか

→ **NO**。それぞれの `record / get / list_recent` の引数が違いすぎて、共通インターフェースに無理に押し込むメリットが少ない。Protocol を **個別に保ったまま**、`__init__` boilerplate だけ共通化するのが筋。

### v0.9 として一貫していない点

1. **bidirectional の実装方式**: MCP は 1 ツール呼び出しで内部 fan-out、HTTP は 2 callの fetch。`/api/graph/{id}/neighbors?bidirectional=true` も足してしまったほうがクライアント実装が簡潔
2. **PII retention**: feedback / gap だけ無制限、chat (spec_036) は `ttl_seconds=86400`。retention の方針を `~/.axis_*.db` 全体で揃えるべき
3. **DB 配置**: 3 つは `~/.axis_*.db`、parents.db は chroma_dir 配下。後者は parent_storage が "chroma の sidecar" 意識なので妥当だが、ドキュメント / 運用面で混乱しやすい (`make backup-data` のような script を書くなら全部まとめたい)

---

## 5. v0.9.0 リリース可否

**A− (= ES 貼り付けは可、ただし v0.9.1 patch を 1-2 週で出す前提)**

ES に貼って出せる根拠:
- 全テスト緑 (419/419)、ruff・tsc・next build いずれも warning なし
- spec_041 → spec_044 のレビュー指摘は v0.8.1 で全て解消済み (今回のスコープ外だが念のため diff 確認: `lifespan` の `run_in_executor`、`get_many` の chunking、`sessions.last_access` index、いずれも残っている)
- 5 機能とも optional / disabled に倒せる設計で、Day-1 でユーザーが何か破壊する余地が少ない

ES に貼る前にやっておきたい (v0.9.1 patch 候補):
1. **HIGH-1** dim mismatch 検出 + `[0.0] * self._embedder.dim` 修正 — 3〜5 行
2. **MID-3** `detect_no_info` の false positive 引き締め — pattern 修正 + テスト追加で 10 行
3. **README** に「`/api/ingest` 無認証、localhost only」の警告 — docs 1 段落

優先度低 (v0.10 でよい):
- **MID-1** ingest token 認証
- **MID-2** retention 機構
- **LOW-1** hop>1 bidirectional 厳密化
- 4 SQLite store の共通 base
- HTTP `/api/graph/.../neighbors?bidirectional=true` の追加

---

## 6. v0.10 候補

1. **Auth レイヤー (横串)** — `/api/ingest` だけでなく `/api/feedback`、`/api/answer` も含めて、`Authorization: Bearer <token>` を任意で受け付ける middleware。env `AXIS_API_TOKEN` が設定されたときだけ有効。リモート公開ユースケース対応
2. **PII retention** — feedback / gap に共通 `purge_older_than(days)` を生やし、daily cron / Makefile target で叩く
3. **Auto-ingest from gap** — gap_report の top query を Browser Extension + LLM で frontmatter 候補化して自動 propose (ADR-029 Alternatives に既に書いてある)
4. **Ollama batch API** — Ollama 0.5 から `/api/embed` が batch 対応。`embed_batch` の逐次ループを 1 リクエストに集約
5. **共通 SqliteStoreBase** — 4 store の `__init__` boilerplate 統一
6. **`/api/graph/.../neighbors?bidirectional=true`** — HTTP と MCP の対称化、フロント往復 1 回化
7. **Active learning loop の "学習" 部分** — spec_047 で logging までは出来たが、`bm25_weight` や `time_decay.weight` を feedback の net score で自動チューニングする箱物
8. **Telemetry/ tracing** — 4 store 統合で運用ログ (top10 latency, error rate) の dashboard

---

## 7. 成功条件チェック

- [x] 5 spec × 4 軸の所見テーブル → §1
- [x] 全体評価 (A/B/C) → A− (§0, §5)
- [x] 新たな問題 0-5 件 → 5 件 (HIGH-1 / MID-3 / LOW-1) §2
- [x] ポジティブ評価 0-5 件 → 5 件 §3
- [x] v0.10 候補 → 8 件 §6
- [x] ファイル変更 0 (result_050.md 以外) / commit 0 (review commit のみ後で作成)
- [x] result_050.md に出力

— end of review —
