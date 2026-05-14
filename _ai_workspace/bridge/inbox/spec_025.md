# spec_025: Doc 整合性パス (v0.4 メタデータ統一)

- **Author**: Cowork (中島)
- **Created**: 2026-05-13
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: spec_024 (CC 総合レビュー、B → A 昇格を狙う)

## 1. 目的

CC レビュー (result_024.md) で指摘された **メタデータ不整合** を一括修正し、ポートフォリオとしての完成度を A レベルに引き上げる。

```
[現状 = B 判定]
- README badge: Version 0.3.0 / Status alpha-v0.1 のまま (実体 v0.4.0)
- pyproject.toml version = "0.1.0.dev0" (実体 v0.4.0)
- backend/src/api.py:54 FastAPI(version="0.3.0.dev0") (実体 v0.4.0)
- /api/health の version response が「0.1.0.dev0」を返す
- README L222 + docs/mcp-server.md L40 / L465: 「5 read-only tools」と記載 (実体 6 tools, axis_ingest_memo 追加済み)
- README L14: ![demo](examples/screenshots/demo.gif) を貼っているがファイル無し → GitHub プレビューで 404
- docs/api-reference.md L51,57: axes サンプル値が ["ノウハウ","入門"] 等、config.yml と不一致
- git tag が dev-b clone から見えない (リモートにはある可能性、確認要)

[変更後 = A 判定狙い]
- 全 version 文字列が "0.4.0" で揃う
- /api/health が 0.4.0 を返す (pyproject 経由の動的取得)
- MCP tool 数表記が 6 に統一
- demo.gif placeholder を「録画予定」明示の TODO コメントに置換、もしくは README の img 行を削除
- docs/api-reference.md の axes 例が config.yml と一致
- git tag 状態が確実に説明できる (リモート確認 + 必要なら fetch --tags の手順を docs に書く)
```

## 2. 制約

### 触ってよいファイル

- `README.md` — badge 更新、tool count、demo placeholder
- `pyproject.toml` — version
- `backend/src/api.py` — FastAPI(version=...) を動的取得に
- `docs/mcp-server.md` — tool count
- `docs/api-reference.md` — axes サンプル
- `docs/INDEX.md` — リンク見直し (portfolio-notes 残骸など)
- `CHANGELOG.md` — Day 25 追記
- `examples/screenshots/` — placeholder ファイル追加 or 削除

### 触ってはいけないもの

- ソース実装 (backend/src/*.py, mcp_server/*.py, frontend/src/, scripts/*) のロジック変更は **禁止**
- 既存テスト
- `.github/workflows/*.yml`
- `_ai_workspace/`

### コーディングルール

- Docs のみの修正なので軽量
- `__version__ = "0.4.0"` を `backend/src/__init__.py` か `mcp_server/__init__.py` に置いて単一情報源にしても OK (任意改善)
- ruff / pytest はそのまま通る (Docs 主変更のため通過するはず)

## 3. やってほしいこと

### 3-1. version 文字列を全部 0.4.0 に統一

#### `pyproject.toml`

```diff
-version = "0.1.0.dev0"
+version = "0.4.0"
```

#### `backend/src/api.py` (L54 付近)

```diff
 app = FastAPI(
     title="axis-knowledge-rag",
     description="軸検索 + RAG over YAML frontmatter Markdown",
-    version="0.3.0.dev0",
+    version=_pkg_version(),  # 動的に pyproject.toml の値を返す (既に _pkg_version() ヘルパーがある)
     lifespan=lifespan,
 )
```

`_pkg_version()` は既に api.py 内に存在するので、その関数を `FastAPI(version=)` で呼ぶだけ。

#### `README.md` の badges (L5-7 付近)

```diff
-[![Version](https://img.shields.io/badge/version-0.3.0-blue.svg)](https://github.com/kazikimaguro13/axis-knowledge-rag/releases)
+[![Version](https://img.shields.io/badge/version-0.4.0-blue.svg)](https://github.com/kazikimaguro13/axis-knowledge-rag/releases)
```

`Status: alpha-v0.1` のバッジがあれば `released-v0.4` 等に変更。

### 3-2. MCP tool 数 5 → 6 に統一

#### `README.md`

```diff
-| `axis_search` | 軸フィルタ + ベクトル hybrid 検索 |
-| `axis_answer` | RAG (Claude API + 出典) |
-| `axis_list_axes` | 軸定義の取得 |
-| `axis_check_integrity` | 参照整合性チェック |
-| `axis_list_documents` | ドキュメント一覧 (pagination) |
+| `axis_search` | 軸フィルタ + ベクトル hybrid 検索 |
+| `axis_answer` | RAG (Claude API + 出典) |
+| `axis_list_axes` | 軸定義の取得 |
+| `axis_check_integrity` | 参照整合性チェック |
+| `axis_list_documents` | ドキュメント一覧 (pagination) |
+| `axis_ingest_memo` | raw memo → YAML frontmatter Markdown 変換 (Claude API) |
```

「5 read-only tools」の文言を「6 tools (5 read + 1 ingest)」または「6 read-only tools (ingest は memo を変換するだけでファイル書き込みなし)」に統一。

#### `docs/mcp-server.md`

同じく「5 tools」を「6 tools」に。tool 一覧表に `axis_ingest_memo` を追記、I/O example も。

### 3-3. demo.gif placeholder 問題

README L14 付近 (`![demo](examples/screenshots/demo.gif)`) の対応方針 2 通り:

**方針 A (推奨)**: img 行を削除、代わりに「Demo」セクションを下に追加し、Streamlit / Next.js UI のテキスト説明 + 実行手順だけ書く。GitHub で 404 にならない。

**方針 B**: `examples/screenshots/` に 1x1 透明 PNG プレースホルダ + `README_DEMO.md` で「TODO: GIF 録画予定」明記。

CC 判断で OK 方を採用。両方の意図を CHANGELOG に書く。

### 3-4. axes サンプル値を config.yml と一致させる

#### `docs/api-reference.md`

```diff
 ## GET /api/axes
 
 サンプルレスポンス:
 
 ```json
 {
   "axes": [
-    {"name": "category", "type": "enum", "values": ["技術記事", "ノウハウ", "メモ"], "required": true},
+    {"name": "category", "type": "enum", "values": ["技術記事", "メモ", "議事録", "ToDo"], "required": true},
     {"name": "topic", "type": "string", "required": true},
-    {"name": "level", "type": "enum", "values": ["入門", "中級", "上級"], "required": false}
+    {"name": "level", "type": "enum", "values": ["初級", "中級", "上級"], "required": false}
   ]
 }
 ```

実体 (`config.yml`) と完全一致させる。other docs (architecture / ADR) も同じ axes 例が出てる箇所を統一。

### 3-5. portfolio-notes 残骸 / その他

`docs/INDEX.md` で `portfolio-notes.md` への壊れリンクが残っていないか再確認。CHANGELOG にも残骸があれば消す。

`docs/architecture.md` / `docs/design-decisions.md` の axes 例も chr `config.yml` 一致を確認。

### 3-6. git tag 状態の確認 + 修復

```bash
cd ~/projects/axis-knowledge-rag
git tag -l                       # ローカル空のはず
git ls-remote --tags origin      # リモートには v0.1.0〜v0.4.0 がある想定
git fetch --tags origin          # ローカルに取り込む
git tag -l                       # 再確認 (4 つ表示されるはず)
```

リモートにもタグが無かった場合: 「リリースは GitHub UI で作成されているがタグが push されていない」状態。その場合は **本タスクの範囲外** とし、result_025.md の Open questions に記録のみ。

リモートにあった場合: `docs/deployment.md` か README の「インストール」セクションに「初回 clone 後は `git fetch --tags` を実行してください」を追記。

### 3-7. CHANGELOG に Day 25 追記

```markdown
### Day 25 (2026-05-13)

- Version metadata unification: pyproject.toml / api.py / README badge / api version response 全て 0.4.0 に統一
- /api/health の version レスポンスを `_pkg_version()` 経由の動的取得に変更
- MCP tool count 表記を 5→6 に統一 (axis_ingest_memo 追加反映)
- docs/api-reference.md の axes サンプル値を config.yml と一致 ("技術記事/メモ/議事録/ToDo" + "初級/中級/上級")
- README demo.gif 欠落問題の対応 (img 行を削除 or placeholder 配置)
- portfolio-notes.md への壊れリンク残骸を削除
- git tag 状態の確認、必要に応じて fetch --tags 手順を docs に記載
```

### 3-8. 動作確認

```bash
cd ~/projects/axis-knowledge-rag

# Version 確認
grep -n "version" pyproject.toml
python3 -c "from importlib.metadata import version; print(version('axis-knowledge-rag'))"

# /api/health 動作確認
uvicorn backend.src.api:app --port 8000 &
sleep 3
curl http://localhost:8000/api/health
kill %1

# MCP tool 数確認
grep -c "@mcp.tool" mcp_server/server.py    # 6 が期待値

# axes サンプル grep
grep -n "ノウハウ\|入門" docs/    # 0 件期待

# ruff + pytest
ruff check .
python3 -m pytest --quiet

# demo.gif 参照削除確認
grep -n "demo.gif" README.md
```

### 3-9. コミット粒度

1. `chore: bump version to 0.4.0 in pyproject.toml`
2. `feat(api): use _pkg_version() in FastAPI version field`
3. `docs(readme): update version badge to 0.4.0`
4. `docs: add axis_ingest_memo to MCP tools table + bump count to 6`
5. `docs(api-reference): fix axes sample values to match config.yml`
6. `docs(readme): remove broken demo.gif reference (will be re-added when recorded)`
7. `docs: changelog Day 25`

`git push -u origin feat/spec_025-doc-consistency`

### 3-10. result_025.md

特に:

- 修正前後の各 version 文字列 (diff)
- `/api/health` レスポンスの before/after
- `grep` 結果の before/after (5 tools → 6 tools)
- git tag 状態の最終結論 (リモートにあった/なかった、fetch 必要か)

## 4. 成功条件

- [ ] pyproject / api.py / README で全 version 文字列が 0.4.0 一貫
- [ ] /api/health が `{"version": "0.4.0", ...}` を返す
- [ ] MCP tool 表記が全箇所 6 tools に統一
- [ ] axes サンプルが config.yml と一致
- [ ] demo.gif 参照が解消 (img 行削除 or placeholder)
- [ ] git tag 状態の説明が docs にある
- [ ] ruff + pytest 緑
- [ ] dev-b で push

## 5. 出力先

`_ai_workspace/bridge/outbox/result_025.md`

## 6. 質問

- demo.gif: 方針 A (img 削除) か B (placeholder) か。CC 判断で OK
- `__version__` の単一情報源化: pyproject.toml だけで完結するなら `backend/src/__init__.py` への `__version__` 追加は不要 (importlib.metadata で OK)
- git tag リモート確認結果が想定外 (タグなし) の場合は spec_025 範囲外、Open questions のみ

## 7. 補足

### 設計の意図

- B → A 判定を狙う最も低コストな修正集
- ロジック変更ゼロ、docs と const のみ
- CC レビュー時にもう一度走らせると差が明確に出る

### Next spec 候補

- spec_026: Ingester 堅牢化 (重複スキャン削減 + retry)
- spec_027: MCP error sanitization
- spec_028: ChromaDB cosine 距離明示
