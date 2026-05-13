# Ingester — メモを自動 YAML 化

`backend/src/ingester.py` は **raw text → axis-knowledge-rag 用 YAML frontmatter Markdown** の
AI 変換コンポーネントです。3 形態 (単発 CLI / バッチ CLI / MCP tool) で提供します。

---

## 1. なぜ作ったか

axis-knowledge-rag は YAML frontmatter 付き Markdown を入力フォーマットに採用しており、
[`docs/spec-v2.md`](spec-v2.md) のとおり以下のような形式が必須です:

```markdown
---
id: doc_011
title: ベクトル検索の選定メモ
axes:
  category: 技術記事
  topic: RAG
  level: 中級
tags: [vector-search, embedding]
refs: []
---

ベクトル検索エンジンを選ぶ際の観点...
```

しかし既存メモ資産 (Slack 抜粋 / 議事録 / Apple Notes / プレーンな Markdown) を
取り込むには、毎回手で frontmatter を埋める必要があり、1 ファイルあたり 30 秒〜2 分かかります。
これは個人 OSS のユーザビリティ上、最後のボトルネックでした。

Ingester は Claude API を使ってこの変換を自動化します。

---

## 2. アーキテクチャ

```
┌────────────────────┐    ┌──────────────────────┐
│  raw text (.txt)   │ →  │  Ingester.ingest()   │
└────────────────────┘    │                      │
                          │  1. read knowledge   │
                          │     dir → next_id    │
                          │  2. load axes from   │
                          │     config.yml       │
                          │  3. build prompt     │
                          │     w/ constraints   │
                          │  4. Claude API call  │
                          │  5. parse JSON via   │
                          │     Pydantic         │
                          └──────────┬───────────┘
                                     ↓
                          ┌──────────────────────┐
                          │   IngestResult       │
                          │ (id/title/axes/...)  │
                          └──────────┬───────────┘
                                     ↓
                          ┌──────────────────────┐
                          │  render_markdown()   │ → frontmatter付き .md
                          └──────────────────────┘
```

**設計の要点:**

- **Pydantic v2 で AI レスポンスを strict validation** — `IngestResult` schema で
  `id` のパターン (`doc_\d{3,}`)、`refs` の prefix、`body` の最低長などを検証し、
  hallucination 由来の壊れた YAML を早期に弾きます。
- **`load_axes_config()` を毎回呼ぶ** — `config.yml` の `axes` 定義を Claude に渡して
  prompt 内で制約することで、enum 軸は許可値しか出さないようにします。
  config 変更が即反映され、Ingester 側はノータッチ。
- **`rag.py` のクライアント生成パターンを再利用** — `ANTHROPIC_API_KEY` 未設定 →
  DUMMY モード (`force_dummy=True` でも強制可) で決定論的な mock を返すので、
  CI / オフライン開発・テストで API キー不要。
- **`_next_doc_id` を毎回計算** — `examples/knowledge/` を走査して最大番号 + 1 を返す。
  バッチ処理 (`yamlize_dir`) では in-memory counter で衝突回避。
- **コードフェンス除去フォールバック** — Claude が稀に `\`\`\`json ... \`\`\`` で
  ラップして返した場合に備え、`_strip_code_fence` で吸収。

---

## 3. 使い方

### 3-1. 単発 CLI (`scripts/yamlize.py`)

```bash
# stdout に出力
python -m scripts.yamlize examples/raw_memos/sample_memo_01.txt

# ファイルに保存
python -m scripts.yamlize examples/raw_memos/sample_memo_01.txt \
    --output examples/knowledge/doc_011.md

# カテゴリのヒントを与える
python -m scripts.yamlize meeting_notes.txt --suggested-category 議事録

# stdin から読み込む
cat memo.txt | python -m scripts.yamlize -

# API キーがあっても DUMMY モード強制 (テスト用)
python -m scripts.yamlize memo.txt --force-dummy
```

### 3-2. バッチ CLI (`scripts/yamlize_dir.py`)

```bash
python -m scripts.yamlize_dir ./examples/raw_memos/ \
    --output /tmp/converted/ \
    --pattern "*.txt"
```

- 各ファイルは `<next_id>-<slug>.md` で出力 (slug は title 由来、非 ASCII は filename stem にフォールバック)。
- in-memory counter で id を連番に進めるため、`knowledge_dir` を更新せずに連続変換しても衝突しません。
- 人間レビューを通してから `examples/knowledge/` に commit する運用を想定。**自動 commit はしません。**

### 3-3. MCP tool (`axis_ingest_memo`)

Claude Desktop / Cowork / 任意の MCP クライアントから:

```jsonc
{
  "tool": "axis_ingest_memo",
  "params": {
    "raw_text": "<生メモテキスト>",
    "knowledge_dir": "./examples/knowledge",
    "suggested_category": "メモ",
    "response_format": "markdown"   // or "json"
  }
}
```

返り値:
- `response_format: markdown` (default) → 整形済み Markdown 文字列
- `response_format: json` → `{id, title, axes, tags, refs, rendered_md, is_dummy}` 構造体

[`docs/mcp-server.md`](mcp-server.md) も参照。

---

## 4. 軸推測のプロンプト戦略

Claude に投げるシステムプロンプト ([`backend/src/ingester.py`](../backend/src/ingester.py) の `_SYSTEM_PROMPT`)
には次の制約を明記しています:

1. **JSON のみ出力** — 説明文や コードフェンス無し
2. **id は `next_id` を必ずそのまま使う** — 上流で計算した連番を強制
3. **enum 軸は許可値のみ** — `axes_constraints` を `json.dumps` でそのまま埋め込む
4. **required=true は必ず埋める / required=false は推測できる時だけ**
5. **tags は 2〜5 個、snake_case 推奨だが日本語可**
6. **refs は与えられた `existing_doc_ids` の範囲内でのみ** — 推測で `doc_999` を作らない
7. **body は情報を削らずに markdown 整形**

Pydantic の `IngestResult` がさらにスキーマレベルで validate するので、prompt をすり抜けた
hallucinated ref ID は `ValidationError` で弾かれます。

---

## 5. 既知の制約

- **長文メモ** (max_tokens 1500 を超えるサイズ) は途中で切れる可能性あり。`--max-tokens 4096` で拡張可能。
- **refs 推測は保守的** — 確信が無いものは `[]` で返ってきます。手動補足してください。
- **大規模 KB での next_id 計算が重い** — `load_directory` で全 doc を読むため、数千件規模では
  数秒かかります。v0.5 で ChromaDB から id 一覧を取得する高速版に置換予定。
- **retry 機構なし** — Claude が JSON 以外を返した場合は `RuntimeError`。`_strip_code_fence`
  でフェンス付きには耐性がありますが、それ以上の修復は v0.5 で。
- **DUMMY モードは形式上の動作確認のみ** — 実 ingestion には `ANTHROPIC_API_KEY` が必須です。

---

## 6. v0.5+ 計画

- **Slack 連携** — Slack export JSON / 特定チャンネルを一括 ingest
- **Apple Notes インポート** — `osascript` 経由でメモを抜き出して一括変換
- **batch + review UI** — Next.js 側に「raw メモを貼り付け → 変換プレビュー → 一括 commit」フロー
- **複数 LLM 対応** — Anthropic / OpenAI / ローカル LLM をスイッチ可能に
- **retry & repair** — 不正 JSON が返った時に自動再投入

---

## 7. 関連ドキュメント

- [README](../README.md) の「メモを自動 YAML 化」セクション
- [`docs/mcp-server.md`](mcp-server.md) — MCP tool としての利用
- [`docs/spec-v2.md`](spec-v2.md) — 入力フォーマット仕様
- [`config.yml`](../config.yml) — 軸定義
