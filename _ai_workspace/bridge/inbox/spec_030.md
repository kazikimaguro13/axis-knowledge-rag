# spec_030: README 整備 & リポジトリメタデータ設定 (公開印象の磨き込み)

- **Author**: Cowork (中島) — 外部 Claude レビュー (`spec_001_readme_cleanup.md` ダウンロード版) を本プロジェクトの bridge 形式に書き換え
- **Created**: 2026-05-14
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Type**: chore (docs + GitHub metadata)
- **Bundles**: なし

## 1. 目的

外部 Claude レビュー (`/mnt/c/Users/cocor/Downloads/spec_001_readme_cleanup.md`) で指摘された **公開印象を毀損する内部メモ** を削除し、リポジトリの GitHub メタデータ (About / Topics) を設定する。「AI に丸投げで中身を確認していない人」という印象を回避し、採用担当が 30 秒で価値を理解できる状態にする。

```
[現状の問題]
- README L296: "中島さんが Day 20 中に手動で撮る:" という内部 TODO + 個人名
- README L16: 上記セクションへの参照リンク
- README L294-307: 「デモ GIF 取得チェックリスト」セクション全体が公開状態
- GitHub About description: 未設定 (null)
- GitHub Topics: 0 件
- examples/screenshots/: ディレクトリは存在するが README 等のガイドなし

[変更後]
- README から「デモ GIF 取得チェックリスト」セクション完全削除
- 冒頭 Demo 引用ブロックの文言を簡潔化
- README Author 表記 (Author: 中島) は標準的な attribution なので維持
- docs/design-decisions.md の ADR Deciders 表記は設計史なので維持 (spec_001 の例外規定準拠)
- GitHub About description セット
- GitHub Topics 14 件セット (rag / claude-api / gemini-api / mcp-server / nextjs 等)
- examples/screenshots/README.md でスクリーンショット運用ガイド整備
- 将来のデモ GIF 配置を見越したコメントアウト行を README 先頭に追加
```

## 2. 制約

### 触ってよいファイル

- `README.md` — 内部 TODO 削除、デモ引用ブロック簡略化、コメントアウト img 行追加
- `examples/screenshots/README.md` — **新規**。撮影ガイドライン
- `CHANGELOG.md` — Day 30 追記
- GitHub API 経由: About description / Topics

### 触ってはいけないもの

- `backend/` / `frontend/` / `mcp_server/` のコード
- `docs/design-decisions.md` の **ADR 本体** (Deciders 表記の `中島` はそのまま、設計史として正当)
- README の `Author: 中島` 行 (標準的な attribution)
- `_ai_workspace/`

### コーディングルール

- `gh` CLI は環境にない。GitHub API 操作は **curl + PAT** で行う:
  ```bash
  PAT=$(grep -oP 'kazikimaguro13:\K[^@]+' ~/.git-credentials)
  curl -X PATCH -H "Authorization: Bearer $PAT" -H "Accept: application/vnd.github+json" \
    https://api.github.com/repos/kazikimaguro13/axis-knowledge-rag \
    -d '{"description": "..."}'
  ```
- ruff + pytest は本 spec ではコード変更ないので走らせなくてよい (docs のみ)

## 3. やってほしいこと

### Task 1: README から「デモ GIF 取得チェックリスト」セクション削除

`README.md` の以下を削除:

1. **L294-307 (`## 📸 デモ GIF 取得チェックリスト` 見出しから次の見出しの直前まで)** をセクションごと全削除
2. **L16 の参照行**: `> 撮影手順は [📸 デモ GIF 取得チェックリスト](#-デモ-gif-取得チェックリスト) を参照。` を削除
3. デモ案内引用を以下に簡略化:
   - 変更前: `> 📹 **Demo**: 録画は未公開 (近日追加予定)。動作確認は [Quickstart](#-quickstart-docker) を参照。`
   - 変更後: `> 📹 **Demo GIF**: coming soon. 動作確認は [Quickstart](#-quickstart-docker) を参照。`

**検証コマンド**:

```bash
grep -i "Day [0-9]\+ 中" README.md       # → 0 件
grep "デモ GIF 取得チェックリスト" README.md  # → 0 件
grep "中島さんが" README.md                # → 0 件
```

### Task 2: 取りこぼし内部表記の洗い出し

```bash
grep -nrE "(中島さん|TODO.*(手動|あとで|要修正)|Day [0-9]+ (中に|まで))" README.md docs/
```

ヒットした行をルールで処理:
- 個人名 (`中島さん` 等) → 削除 or `the maintainer` / `the author` に置換
- 作業日付表記 (`Day NN 中に` 等) → 削除
- 内部 TODO (`要修正` `あとで` 等) → 削除

**例外**:
- `docs/design-decisions.md` の `Deciders: 中島` は ADR 設計史なので残す
- README L316 `Author: 中島 (GitHub: @kazikimaguro13)` は標準 attribution なので残す

### Task 3: GitHub About description 設定

```bash
PAT=$(grep -oP 'kazikimaguro13:\K[^@]+' ~/.git-credentials)
curl -X PATCH -H "Authorization: Bearer $PAT" -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/kazikimaguro13/axis-knowledge-rag \
  -d '{"description": "軸メタデータ × ベクトル検索 × BM25 の 3-way hybrid RAG OSS。日本語ナレッジ特化、MCP server 対応、LangChain 不使用の自前実装。"}'
```

検証:
```bash
curl -s -H "Authorization: Bearer $PAT" https://api.github.com/repos/kazikimaguro13/axis-knowledge-rag \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["description"])'
```

### Task 4: GitHub Topics 設定 (14 件)

```bash
PAT=$(grep -oP 'kazikimaguro13:\K[^@]+' ~/.git-credentials)
curl -X PUT -H "Authorization: Bearer $PAT" -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/kazikimaguro13/axis-knowledge-rag/topics \
  -d '{"names":["rag","claude-api","gemini-api","mcp-server","nextjs","fastapi","vector-search","chromadb","bm25","japanese-nlp","knowledge-management","local-first","llm","python"]}'
```

検証:
```bash
curl -s -H "Authorization: Bearer $PAT" https://api.github.com/repos/kazikimaguro13/axis-knowledge-rag \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["topics"]),"topics:", d["topics"])'
```

期待値: 14 件 / `["rag", "claude-api", "gemini-api", "mcp-server", "nextjs", "fastapi", "vector-search", "chromadb", "bm25", "japanese-nlp", "knowledge-management", "local-first", "llm", "python"]`

### Task 5: スクリーンショットディレクトリ整備

既存 `examples/screenshots/` (`.gitkeep` のみ) に **`README.md` を追加**:

```markdown
# Screenshots

This directory contains demo screenshots and GIFs of axis-knowledge-rag.

## Files

- `demo.gif` — Main demo (search → answer flow) [coming soon]
- `main-view.png` — Main search screen [coming soon]
- `with-answer.png` — Answer panel with citations [coming soon]

## Recording guidelines

- Resolution: 1280×720 minimum
- GIF: 854×480 if file size exceeds 5 MB
- Duration: 8–15 seconds for main demo
```

`README.md` 冒頭 `# axis-knowledge-rag` 見出しのすぐ下に、コメントアウト img 行を追加:

```markdown
# axis-knowledge-rag

<!-- ![demo](./examples/screenshots/demo.gif) -->

YAML frontmatter 付き Markdown ナレッジに対する、**軸メタデータ検索 + ベクトル検索 + RAG** のローカル Web アプリ OSS。
```

(将来 demo.gif を配置したら `<!-- -->` を外すだけで反映)

### Task 6: CHANGELOG.md Day 30 追記

```markdown
### Day 30 (2026-05-14) — Public README cleanup + GitHub metadata

- README: 「デモ GIF 取得チェックリスト」セクション削除 (内部 TODO 表記、外部公開不適切)
- README: 冒頭引用ブロックの撮影手順リンクを削除、Demo 文言を簡潔化
- README: 冒頭にコメントアウト img タグを配置 (将来の demo.gif 配置時に外すだけ)
- examples/screenshots/README.md: 新規、撮影ガイドライン
- GitHub About description セット: "軸メタデータ × ベクトル検索 × BM25 の 3-way hybrid RAG OSS..."
- GitHub Topics セット: 14 件 (rag / claude-api / gemini-api / mcp-server / nextjs / fastapi / vector-search / chromadb / bm25 / japanese-nlp / knowledge-management / local-first / llm / python)
- ADR 表記 (Deciders: 中島) は設計史なので残置 (spec_030 §2 制約準拠)
```

### Task 7: コミット & プッシュ

```bash
cd ~/projects/axis-knowledge-rag

# Task 1, 2, 5, 6
git add README.md docs/ examples/screenshots/ CHANGELOG.md
git -c user.email='kazikimaguro13@users.noreply.github.com' -c user.name='kazikimaguro13' \
  commit -m "docs: remove internal TODO from README + add screenshots guide

- Remove 'デモ GIF 取得チェックリスト' section (internal work checklist with
  personal name and Day NN reference, not suitable for public exposure)
- Simplify demo placeholder caption to 'coming soon'
- Add commented-out img tag for future demo.gif placement
- Add examples/screenshots/README.md with recording guidelines
- ADR 'Deciders: 中島' lines kept as legitimate design history"

git push origin main
```

Task 3, 4 (GitHub API) は commit を伴わないので独立実行。

## 4. 成功条件

- [ ] README に「デモ GIF 取得チェックリスト」セクションが存在しない
- [ ] README L16 の撮影手順リンクが削除されている
- [ ] `grep "中島さんが" README.md` → 0 件
- [ ] `grep "Day [0-9]+ 中" README.md` → 0 件
- [ ] README に `<!-- ![demo](./examples/screenshots/demo.gif) -->` が存在
- [ ] `examples/screenshots/README.md` が新規作成され、ガイドライン記載済み
- [ ] GitHub About description が非 null
- [ ] GitHub Topics が 14 件
- [ ] main に push 済み、コミット 1 件
- [ ] CHANGELOG に Day 30 セクション追加

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_030.md`

result_template.md 構造で、各 Task の完了判定と検証コマンド出力を記載。

## 6. 補足

### main HEAD

`387c61c chore(release): bump to 0.6.0 — BM25 hybrid search`

### 元レビューファイル

`/mnt/c/Users/cocor/Downloads/spec_001_readme_cleanup.md` (外部 Claude セッションでの v0.5 時点レビュー)

本 spec はそれを v0.6 時点に合わせて再構成。差分:
- `gh` CLI → `curl + PAT` (環境に合わせる)
- 個人名表記の例外明示 (Author / ADR Deciders)
- v0.6 で追加した BM25 を description に含める
- Topics に `bm25` を追加 (元 spec の 14 件中の `typescript` を差し替え、frontend は付随なので bm25 を優先)

### 本 spec のスコープ外

- ブログ記事の投稿 / レビュー
- demo GIF / スクリーンショットの実撮影 (Cowork からは録画不可、本人手作業)
- backend / frontend のコード品質レビュー
- 旧 dispatch.sh / dispatch_v2.sh / dispatch_v3.sh の整理
