# marker.py — AUTO_GENERATED ブロック保護

## 概要

`backend/src/marker.py` は、人間が書いた Markdown に AI が自動生成した区画を **共存** させるための仕組みを提供します。
詳細な設計判断は [design-decisions.md#adr-008](design-decisions.md#adr-008)、公開 API は [`api-reference.md`](api-reference.md#backendsrcmarker) を参照。

---

## 1. なぜマーカー方式か

RAG ナレッジファイルには、人間が書いたコアな知識と、AI が自動生成する要約・FAQ・メタデータの 2 種類のコンテンツが混在します。
素朴に上書きすると人間記述が消えてしまうため、**区画を HTML コメントで明示的に囲み、自動生成区画だけを選択的に更新** する方式を採用しています。

HTML コメント形式を選んだ理由：

- Markdown レンダラー（GitHub, Obsidian など）に無視される → **表示上クリーン**
- プレーンテキストなので diff が読みやすい
- `re` モジュールだけで実装でき、依存ゼロ

---

## 2. マーカー構文

```
<!-- AUTO_GENERATED_START: <name> -->
<content>
<!-- AUTO_GENERATED_END: <name> -->
```

- `<name>` は `[a-zA-Z0-9_-]+` のみ許可（スペース・記号は不可）
- 大文字小文字区別あり: `summary` ≠ `Summary`
- ネストは非対応（Phase 2 で検討）
- 改行コードは LF 前提（CRLF はアプリ側で normalize してから渡す）

---

## 3. 保護範囲の境界

```
┌───────────────────────────────────────────────────┐
│   Human-written section (絶対に変更しない)           │
│                                                   │
│   <!-- AUTO_GENERATED_START: summary -->  ◄─┐    │
│   AI が書く区画                              │    │
│   再生成時はここだけ書き換わる               │ ★  │
│   <!-- AUTO_GENERATED_END: summary -->    ◄─┘    │
│                                                   │
│   Human-written section (再び人間の記述)            │
└───────────────────────────────────────────────────┘
```

`update_block()` が書き換えるのは `START` / `END` の内側のみです。外側はいっさい触りません。

---

## 4. API リファレンス

### `MarkerBlock` dataclass

| フィールド | 型 | 説明 |
|---|---|---|
| `name` | `str` | ブロック名（例: `"summary"`） |
| `content` | `str` | 区画の内側テキスト（デリミタ除く） |
| `raw_full` | `str` | デリミタ込みの完全なマッチ文字列 |

---

### `extract_blocks(text: str) -> list[MarkerBlock]`

文書内の全 AUTO_GENERATED ブロックをドキュメント順で返します。

```python
from backend.src.marker import extract_blocks

text = open("examples/knowledge/01-rag-patterns.md").read()
for block in extract_blocks(text):
    print(f"{block.name}: {len(block.content)} chars")
```

---

### `update_block(text: str, name: str, new_content: str) -> str`

指定名のブロックを `new_content` で置換した新しい文字列を返します。
ブロックが存在しない場合は末尾に追加します（= 最初の自動生成と再生成を同じ呼び出しで扱える）。

```python
from backend.src.marker import update_block

text = open("doc.md").read()
new_text = update_block(text, "summary", "RAG は検索と生成を組み合わせた手法。")
open("doc.md", "w").write(new_text)
```

**注意**: 戻り値が更新済みテキスト。元ファイルへの書き込みは呼び出し側の責務です。

---

### `strip_blocks(text: str) -> str`

全 AUTO_GENERATED ブロック（デリミタ込み）を削除した文字列を返します。

用途：PR レビューや diff 確認時に AI 生成部分を除いた human-only 版を作る。

```python
from backend.src.marker import strip_blocks

human_only = strip_blocks(open("doc.md").read())
```

---

### `validate_balance(text: str) -> list[str]`

START / END の対応を検証し、エラーメッセージのリストを返します。空リストなら正常。

```python
from backend.src.marker import validate_balance

errs = validate_balance(open("doc.md").read())
if errs:
    for e in errs:
        print(f"ERROR: {e}")
```

---

### `MarkerError`

`update_block()` に無効な名前を渡したときに送出される例外。

---

## 5. CLI

```bash
# ブロック一覧
python -m backend.src.marker <file> --list

# ブロック更新（存在しなければ末尾に追加）
python -m backend.src.marker <file> --update --name <name> --content "<text>"

# 全ブロック削除
python -m backend.src.marker <file> --strip

# バランス検証
python -m backend.src.marker <file> --validate
```

### 使用例

```bash
# examples/knowledge/01-rag-patterns.md のブロック確認
python -m backend.src.marker examples/knowledge/01-rag-patterns.md --list
# => 1 block(s):
#      - summary: 39 chars

# summary ブロックを更新
python -m backend.src.marker examples/knowledge/01-rag-patterns.md \
  --update --name summary --content "RAG は検索と生成を組み合わせた手法。"

# 検証
python -m backend.src.marker examples/knowledge/01-rag-patterns.md --validate
# => ✅ Balanced

# AI 生成部を除いた版を確認（ファイルは変更される — 必要ならバックアップ先に）
cp examples/knowledge/01-rag-patterns.md /tmp/backup.md
python -m backend.src.marker examples/knowledge/01-rag-patterns.md --strip
```

---

## 6. 再生成フロー

```
                ┌──────────────────┐
                │  ナレッジ .md     │
                └────────┬─────────┘
                         │ read
                         ▼
              ┌─────────────────────┐
              │  extract_blocks()   │  ← 既存の自動生成内容を取得
              └─────────┬───────────┘
                        │
              ┌─────────▼───────────┐
              │  Claude API 呼び出し │  ← 新しい要約を生成
              └─────────┬───────────┘
                        │ new_content
              ┌─────────▼───────────┐
              │  update_block()     │  ← 人間記述を保護しつつ置換
              └─────────┬───────────┘
                        │ updated text
                        ▼
                ┌──────────────────┐
                │  ナレッジ .md     │  ← 上書き保存
                └──────────────────┘
```

---

## 7. ブロック名の推奨セット

| 名前 | 用途 |
|---|---|
| `summary` | 文書全体の要約（1〜3 段落） |
| `faq` | よくある質問と回答 |
| `metadata` | 自動抽出したキーワード・関連ドキュメント |
| `changelog` | 自動更新履歴 |
| `toc` | 目次 |

---

## 8. 既知の制限

| 制限 | 理由 | 将来対応 |
|---|---|---|
| ネスト非対応 | `_BLOCK_RE` が DOTALL で最初の END に貪欲マッチ | Phase 2: 再帰パーサー |
| 同名ブロック複数は `update_block` で 1 番目のみ更新 | 設計上の割り切り | `validate_balance` でエラーにしても良い |
| 改行は LF 前提 | CRLF は normalize してから渡す | CLI は `replace("\r\n", "\n")` 済み |

---

## 9. 設計判断メモ

### regex で実装、AST 不要

Markdown の自由度（任意の構文）を保つため、パーサーを持たない。HTML コメント形式なので Markdown レンダラーに無視される点が重要。

### `update_block` が存在しない場合は append

「最初に自動生成する」フローと「再生成する」フローを同じ呼び出しで扱える設計。呼び出し側で事前に `extract_blocks()` を使って存在確認する必要がない。

### `strip_blocks` の用途

AI 生成部分を取り除いた human-only 版を作るユースケース：

- PR レビュー時に diff をシンプルに見たい
- git blame で人間の変更箇所だけを追いたい
- AI 生成なしのバックアップを作る

---

## 10. Day 12 以降の予定

- **Day 12**: `pytest` 化（現在は assert ベースの自前ランナー）
- **Day 13 / v0.4**: ビルドスクリプトで Claude API を使い `summary` ブロックを自動生成
- **Phase 2**: ネストマーカーのサポート

---

## See also

- [architecture.md](architecture.md) — Marker 再生成フローのデータフロー位置づけ
- [design-decisions.md#adr-008](design-decisions.md) — マーカー方式採用の根拠 (ADR-008)
- [api-reference.md](api-reference.md#backendsrcmarker) — `extract_blocks` / `update_block` / `strip_blocks` API
- [INDEX.md](INDEX.md) — ドキュメント目次