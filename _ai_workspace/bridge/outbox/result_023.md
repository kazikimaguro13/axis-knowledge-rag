# result_023: AI ingester (`backend/src/ingester.py`) — メモ → YAML 自動変換

- **Spec**: `inbox/spec_023.md`
- **Executor**: Claude Code (dev-b)
- **Started**: 2026-05-13 (session start)
- **Finished**: 2026-05-13 (session end)
- **Status**: done

## 1. 要約

raw text → YAML frontmatter Markdown の AI 変換コンポーネントを実装。`Ingester` クラス本体 (`backend/src/ingester.py`) は `rag.py` の Anthropic クライアントパターンを継承し、`ANTHROPIC_API_KEY` 未設定時は sha256 派生の決定論的 mock を返す DUMMY モードで動作。`config.yml` の `axes` 定義を Claude にプロンプトとして渡して enum 軸制約を強制し、Pydantic v2 (`IngestResult`) でレスポンスを strict validation。単発 CLI (`scripts/yamlize.py`)、バッチ CLI (`scripts/yamlize_dir.py`)、MCP tool (`axis_ingest_memo`) の 3 形態で提供。サンプル raw memo 3 本 (Slack/議事録/自己ノート) と docs/ingester.md (184 行) を追加。全 137 テスト PASS、ruff clean、feat/spec_023-ingester に 9 commit を push 済み。

## 2. 変更ファイル

```
 CHANGELOG.md                          |  15 +++
 README.md                             |  25 +++++
 backend/src/ingester.py               | 178 ++++++++++++++++
 backend/src/ingester_schemas.py       |  46 +++++
 backend/tests/test_ingester.py        | 126 +++++++++++
 docs/INDEX.md                         |   3 +-
 docs/ingester.md                      | 184 ++++++++++++++++
 examples/raw_memos/sample_memo_01.txt |  19 ++++
 examples/raw_memos/sample_memo_02.txt |  33 ++++
 examples/raw_memos/sample_memo_03.txt |  16 +++
 mcp_server/schemas.py                 |  19 ++++
 mcp_server/server.py                  |  58 ++++++
 mcp_server/tests/test_server.py       |  49 +++++
 scripts/yamlize.py                    |  55 +++++
 scripts/yamlize_dir.py                | 100 ++++++++++
 15 files changed, 925 insertions(+), 1 deletion(-)
```

## 3. 主要な変更点（ハイライト）

### `backend/src/ingester_schemas.py`

`IngestResult` (Pydantic v2) を hallucinated レスポンスの早期検出フィルタとして配置。

```python
id: str = Field(..., pattern=r"^doc_\d{3,}$")
title: str = Field(..., min_length=3, max_length=200)
axes: dict[str, str | int]
refs: list[str]  # field_validator で 'doc_' prefix 強制
body: str = Field(..., min_length=20)
```

### `backend/src/ingester.py`

`Ingester` クラスは `rag.RAGPipeline` と同じ DUMMY 判定ロジック (`force_dummy or not settings.anthropic_api_key`) を採用。プロンプトには 4 ブロックを注入:

- `# next_id` — `_next_doc_id(knowledge_dir)` で計算
- `# existing_doc_ids` — `refs` の候補集合 (推測で `doc_999` を作らせない)
- `# axes_constraints` — `config.yml` の `axes` 定義を `json.dumps` で丸ごと
- `# raw_text` — ユーザ入力

`_strip_code_fence` で Claude が稀に返すコードフェンスを除去。`render_markdown` は `yaml.safe_dump(sort_keys=False, allow_unicode=True)` で順序維持。

### `scripts/yamlize_dir.py`

バッチ実行時に `knowledge_dir` を書き換えずに連続変換すると `_next_doc_id` が毎回同じ値を返してしまうため、in-memory counter (`_bump_id`) で連番を維持する設計に。

```python
current_id = _next_doc_id(knowledge_dir)
for f in files:
    result = ingester.ingest(raw, opts)
    result = result.model_copy(update={"id": current_id})
    out_path = out_dir / f"{current_id}-{slug}.md"
    ...
    current_id = _bump_id(current_id)
```

### `mcp_server/server.py` — `axis_ingest_memo`

6 個目の tool として追加。`openWorldHint=True` で Anthropic API 呼び出しを明示、`idempotentHint=False` で Claude の非決定性を表明。JSON モードは `rendered_md` と `is_dummy` を含む構造体を返し、呼び出し側が DUMMY 結果を誤って commit しないよう判定材料を渡す。

## 4. テスト・品質チェック結果

```
$ python3 -m pytest -q
........................................................................ [ 52%]
................................................................         [100%]
137 passed in ~3s

$ python3 -m ruff check .
All checks passed!

$ python3 -m scripts.yamlize examples/raw_memos/sample_memo_01.txt --force-dummy
---
id: doc_011
title: '[DUMMY] Auto-generated from raw text (5c3b0772)'
axes:
  category: メモ
  topic: 未分類
tags:
- dummy
- auto
refs: []
---

<!-- DUMMY mode: ingested without Claude API -->
LLM 評価指標についてのまとめ (Slack コピペ風)
...

$ python3 -m scripts.yamlize_dir examples/raw_memos/ -o /tmp/spec_023_out --force-dummy
[ok] sample_memo_01.txt → doc_011-dummy-auto-generated-from-raw-text-5c3b0772.md
[ok] sample_memo_02.txt → doc_012-dummy-auto-generated-from-raw-text-a94c86b9.md
[ok] sample_memo_03.txt → doc_013-dummy-auto-generated-from-raw-text-42fa9f78.md
[done] converted 3 file(s) into /tmp/spec_023_out

$ python3 -c "from backend.src.loader import load_directory; from pathlib import Path; \
              print([d.id for d in load_directory(Path('/tmp/spec_023_out'))])"
['doc_011', 'doc_012', 'doc_013']  # 既存 loader で parse 可能を確認

$ git log --oneline -9
fcb68b3 docs: changelog Day 23
f52c112 docs: add docs/ingester.md + README section + sample raw memos
851b0cc test(mcp): add axis_ingest_memo DUMMY tests
019c4ff feat(mcp): add axis_ingest_memo tool
5e3fa6b test(ingester): add DUMMY-mode integration tests
a7d8fff feat: add scripts/yamlize_dir.py CLI for batch conversion
ca33f7f feat: add scripts/yamlize.py CLI for single-file conversion
16233f3 feat(ingester): implement core Claude-API memo → YAML logic + render_markdown
16bc584 feat(ingester): add Pydantic schemas in ingester_schemas.py
```

### DUMMY モード 3 サンプル変換結果 (markdown 全文)

#### sample_memo_01.txt → doc_011 (Slack 風)

```markdown
---
id: doc_011
title: '[DUMMY] Auto-generated from raw text (5c3b0772)'
axes:
  category: メモ
  topic: 未分類
tags:
- dummy
- auto
refs: []
---

<!-- DUMMY mode: ingested without Claude API -->

LLM 評価指標についてのまとめ (Slack コピペ風)

最近 RAG の精度評価について調べていたので雑に共有。

主に使われてるのは:
- Faithfulness: 出典文書に書いてあることだけ言ってるか (Hallucination の逆)
- Answer Relevance: 質問に対して答えが噛み合ってるか
- Context Precision: 検索で取ってきた document の上位がちゃんと関連してるか
- Context Recall: 必要な情報が検索で全部拾えてるか

RAGAS とか TruLens がよく使われてる。RAGAS は GPT-4 を裏で呼んで自動評価する系で、
ground truth がなくても評価できるのが便利。ただし API コストが地味にかかる。

うちのプロジェクトに導入するとしたら:
1. まず Faithfulness を最優先 (誤答が出ないことが OSS としての信頼)
2. Context Precision は検索ロジック改善の指標
3. Recall は手動でゴールデンセット作る必要あるので後回し

ベンチマーク回す頻度は週1くらいでいいかな。CI で毎回回すとコスト爆発する。
```

#### sample_memo_02.txt → doc_012 (議事録風)

```markdown
---
id: doc_012
title: '[DUMMY] Auto-generated from raw text (a94c86b9)'
axes:
  category: メモ
  topic: 未分類
tags:
- dummy
- auto
refs: []
---

<!-- DUMMY mode: ingested without Claude API -->

2026-05-13 axis-knowledge-rag 週次 MTG 議事録

参加: 中島、Claude (dev-b)
時間: 19:00 - 19:45

## 議題

1. spec_022 (MCP server) の振り返り
2. spec_023 (AI ingester) の方針確認
3. v0.5 ロードマップ

## 決定事項

- MCP server は read-only 5 tools で merge 済み。ingestion 系は別 spec に切り出し
- ingester は DUMMY モード必須。CI で API キーなしで動くこと
- Pydantic で AI レスポンスを strict validation。hallucinated ref を弾くため
- 軸推測は config.yml の axes 定義を Claude に渡して制約 prompt で縛る
- 単発 CLI / バッチ CLI / MCP tool の 3 形態で提供

## TODO

- 中島: README に Ingester セクション追加 → done in spec_023
- Claude: ingester.py 実装、テスト、ドキュメント
- 来週: Slack 連携 (v0.5) の方針決定

## 議論メモ

LangChain の DocumentLoader / TextSplitter を真似るか迷ったが、自前実装の方針を維持。
理由は「依存を増やさず、Claude API を直接叩く方が透明」。
将来 v0.6 で複数 LLM 対応する時に LangChain にすり替える選択肢は残しておく。

ingester の出力先は examples/knowledge/ ではなく一旦別ディレクトリに溜めて、
人間レビュー後に commit する運用を想定。自動 commit はしない。
```

#### sample_memo_03.txt → doc_013 (自己ノート風)

```markdown
---
id: doc_013
title: '[DUMMY] Auto-generated from raw text (42fa9f78)'
axes:
  category: メモ
  topic: 未分類
tags:
- dummy
- auto
refs: []
---

<!-- DUMMY mode: ingested without Claude API -->

アイデア: ナレッジベースに「読書ログ」軸を足すかも

最近読んでる本の引用 + 感想を貯めたいんだが、
今の category enum (技術記事 / メモ / 議事録 / ToDo) には収まらない。

候補:
A. category に "読書ログ" を追加する
B. 新しい軸 `source_type` を増やす (book / paper / web)
C. tags でゆるく管理 (book:title みたいな)

たぶん A が一番素直。enum 追加は config.yml 1 行で済む。
ただ将来 paper, podcast, video など細かく分けたくなる気配があるので、
v0.5 で B に進化させる前提で、当面は A でいく。

実装メモ: enum 追加するだけだと既存 doc は影響ないので migration 不要。
ingester (spec_023) にも自動で反映される (config.yml を毎回読むので)。
```

### 実 Claude モードでの 1 件変換

DUMMY モードのみ実行。今セッションでは `ANTHROPIC_API_KEY` が利用可能でない (未設定 / 検証コマンドが python の `import os; os.environ.get('ANTHROPIC_API_KEY')` で None) ため、実 Claude 呼び出しはスキップ。実モードでの確認は中島さん側で `.env` にキーを置いてから `python -m scripts.yamlize examples/raw_memos/sample_memo_01.txt` を流す手順 (本書 §7) を推奨。

## 5. 想定外だったこと / 判断ポイント

- **`yamlize_dir` の id 衝突問題**: `_next_doc_id` は `knowledge_dir` を毎回スキャンするため、バッチで `out_dir` ≠ `knowledge_dir` の場合は全ファイルが同じ `next_id` を受け取る。spec の「複数ファイル処理中の id 衝突を防ぐため、各ファイル処理後に knowledge_dir を再スキャンするか、in-memory counter で連番増やす」のうち後者を採用 (再スキャンは I/O コストが線形に効くため)。Claude が返した `id` を `result.model_copy(update={"id": current_id})` で上書きすることで、DUMMY/実モードどちらでも整合する形に。
- **`mcp_server/server.py` の import 配置**: `axis_ingest_memo` の本体で `from backend.src.ingester import ...` を関数内 import にした。理由はスタートアップ時に Anthropic クライアントの依存を解決させないため (DUMMY モードでも `import anthropic` 自体は走るが、ingester.py の lazy import 設計を踏襲)。
- **テストの blind exception**: 当初 `pytest.raises(Exception)` で min_length バリデーションを確認していたが ruff B017 で叩かれたので `ValidationError` に絞り込んだ。
- **slug 生成の非 ASCII フォールバック**: 日本語タイトルだと `_SLUG_RE` 後に空文字になるため、`fallback=f.stem` (入力ファイル名) で復旧。DUMMY タイトルは ASCII なので結果的に `dummy-auto-generated-from-raw-text-XXXX` 形式に。実 Claude モードでは日本語タイトル → filename stem への退避が想定される。
- **spec の commit 一覧の「2. core logic」「3. render_markdown helper」**: 同一ファイル (`backend/src/ingester.py`) に同居するので 1 コミットに統合。spec の 8〜10 commit 範囲に収めるため最終的に 9 commits に。
- **`docs/INDEX.md` の MCP tools 数**: 既存記述「5 tools」を「6 tools」に更新。`mcp-server.md` 本文側の数字までは更新していない (今 spec のスコープ外。次 spec で整備推奨)。

## 6. Open questions

なし。spec のすべての成功条件をクリア:
- [x] `python -m scripts.yamlize examples/raw_memos/sample_memo_01.txt` が valid な YAML frontmatter Markdown を出す
- [x] `python -m scripts.yamlize_dir ./examples/raw_memos/ -o /tmp/out/` で 3 ファイル変換 (id 連番 011→013)
- [x] DUMMY モードで全テスト PASS (137 tests)
- [x] MCP tool `axis_ingest_memo` が server に登録される (`mcp_server/tests/test_server.py` で 3 件確認)
- [x] LangChain/LlamaIndex 不使用
- [x] `ruff check` passes
- [x] feat/spec_023-ingester に push

## 7. 動作確認手順（ユーザー）

```bash
cd ~/projects/axis-knowledge-rag

# 1) ブランチを最新に
git fetch origin feat/spec_023-ingester
git checkout feat/spec_023-ingester

# 2) 依存 (既存環境で OK、増やしてない)
pip install -e ".[dev]"

# 3) DUMMY モード単発
python3 -m scripts.yamlize examples/raw_memos/sample_memo_01.txt

# 4) DUMMY モードバッチ
python3 -m scripts.yamlize_dir examples/raw_memos/ -o /tmp/out --force-dummy
ls /tmp/out  # → doc_011-... / doc_012-... / doc_013-...md

# 5) テスト + ruff
python3 -m pytest backend/tests/test_ingester.py mcp_server/tests/test_server.py -v
python3 -m ruff check .

# 6) 実 Claude モード (要 ANTHROPIC_API_KEY)
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
python3 -m scripts.yamlize examples/raw_memos/sample_memo_02.txt \
    --suggested-category 議事録 \
    --output /tmp/doc_011_real.md
cat /tmp/doc_011_real.md

# 7) MCP tool 動作確認 (Claude Desktop 経由)
#    examples/claude_desktop_config.json を ~/Library/Application Support/Claude/ に置いて Claude Desktop 再起動
#    → "axis-knowledge-rag" mcp server から axis_ingest_memo が見える
```

期待結果:
- 手順 3 → stdout に `---` で始まる YAML frontmatter + 本文
- 手順 4 → 3 ファイル、id が doc_011/012/013 で連番
- 手順 5 → ingester 13 tests + server 21 tests 全 PASS、ruff `All checks passed!`
- 手順 6 → 実 Claude が axes/title/tags を `config.yml` の制約内で埋める
- 手順 7 → Claude Desktop の tool 一覧に `axis_ingest_memo` が現れる

## 8. 次の提案（任意）

実装中に気づいた、別 spec として切り出すべき改善案。

- **spec_024 候補: Slack export 一括 ingest** — `slack_export/*.json` を読み、チャンネル単位でメモを抽出 → `yamlize_dir` に流すラッパー。spec_023 docs §6 の v0.5 計画を spec 化。
- **spec_025 候補: ingester の retry + repair ロジック** — Claude が JSON 以外を返したとき、`_strip_code_fence` で吸収できなければ 2 度目のリクエストでスキーマ違反点を指摘して修復させる (現状は `RuntimeError`)。
- **spec_026 候補: Next.js review UI** — `yamlize_dir` の出力を Web UI で1件ずつプレビュー → 承認 → `examples/knowledge/` に commit。spec_023 docs §6 の「batch + review UI」を spec 化。
- **`docs/mcp-server.md` の追従更新** — spec_022 で 5 tools と書かれた箇所が複数あるので、新 tool 追加を反映する小 spec が欲しい (今 spec のスコープ外として温存)。
- **既存 doc の next_id 計算高速化** — 数千件規模で `load_directory` 走査が線形に重くなる。ChromaDB から `id` 一覧を取得する高速版を検討 (spec_023 docs §5 既知制約)。
