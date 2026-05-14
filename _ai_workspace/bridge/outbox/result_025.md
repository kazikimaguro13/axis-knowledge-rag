# result_025: Doc 整合性パス (v0.4 メタデータ統一)

- **Spec**: `inbox/spec_025.md`
- **Executor**: Claude Code (dev-b)
- **Started**: 2026-05-13 18:35
- **Finished**: 2026-05-13 19:05
- **Status**: done

## 1. 要約

result_024.md (CC 総合レビュー) の B 判定要因「メタデータ不整合」を一括解消。pyproject / api.py / README badge / `/api/health` の version 文字列を **0.4.0 一本** に揃え、`_pkg_version()` 経由の動的取得に切替。MCP tool 数表記を全 doc で **6 tools (5 read + 1 ingest)** に統一、`docs/mcp-server.md` に `axis_ingest_memo` の I/O 仕様セクションを追加。`docs/api-reference.md` と `docs/mcp-server.md` の `axes` サンプル値を `config.yml` と完全一致させ、壊れていた `demo.gif` 参照を削除。`docs/INDEX.md` の portfolio-notes 残骸 (空セクション) を削除、`docs/deployment.md` に `git fetch --tags` 手順を追記。ロジック変更ゼロ、ruff + pytest 緑 (136 tests pass)。

## 2. 変更ファイル

```
 CHANGELOG.md          | 14 +++++++++
 README.md             | 12 ++++----
 backend/src/api.py    | 16 +++++-----
 docs/INDEX.md         |  3 --
 docs/api-reference.md | 13 ++++++---
 docs/deployment.md    |  4 +++
 docs/mcp-server.md    | 81 ++++++++++++++++++++++++++++++++++++++++++++-------
 pyproject.toml        |  2 +-
 8 files changed, 111 insertions(+), 34 deletions(-)
```

## 3. 主要な変更点（ハイライト）

### `pyproject.toml`

```diff
-version = "0.1.0.dev0"
+version = "0.4.0"
```

v0.1.0.dev0 のままだった `version` を実体 v0.4.0 に追従。これによって `importlib.metadata.version("axis-knowledge-rag")` が `0.4.0` を返すようになり、後続の `_pkg_version()` 経由の動的取得が正しい値になる。

### `backend/src/api.py`

```diff
+def _pkg_version() -> str:
+    try:
+        return version("axis-knowledge-rag")
+    except PackageNotFoundError:
+        return "unknown"
+
+
 app = FastAPI(
     title="axis-knowledge-rag",
     description="軸検索 + RAG over YAML frontmatter Markdown",
-    version="0.3.0.dev0",
+    version=_pkg_version(),
     lifespan=lifespan,
     ...
 )
-
-
-def _pkg_version() -> str:
-    try:
-        return version("axis-knowledge-rag")
-    except PackageNotFoundError:
-        return "unknown"
```

`_pkg_version()` を `FastAPI(...)` 直前に移動 (旧コードでは下に定義されていたため `FastAPI(version=)` から呼べなかった)。`/api/health` の version レスポンスは元から `_pkg_version()` を返していたが、FastAPI 自体の `app.version` も同じ単一情報源 (pyproject.toml) を読むようになり、OpenAPI ドキュメント / Swagger UI の表示も自動的に `0.4.0` に揃う。

### `README.md`

```diff
-[![Version](https://img.shields.io/badge/Version-0.3.0-brightgreen.svg)](#ロードマップ)
+[![Version](https://img.shields.io/badge/Version-0.4.0-brightgreen.svg)](#ロードマップ)
-[![Status: v0.3](https://img.shields.io/badge/Status-v0.3-orange.svg)](#ロードマップ)
+[![Status: v0.4](https://img.shields.io/badge/Status-v0.4-orange.svg)](#ロードマップ)

-<!-- DEMO_GIF_HERE -->
-![demo](examples/screenshots/demo.gif)
-
-> _デモ GIF は Day 20 に中島さんが撮影予定。撮影後 `<!-- DEMO_GIF_HERE -->` 行を削除してください。_
+> 📹 **Demo**: 録画は未公開 (近日追加予定)。動作確認は [Quickstart](#-quickstart-docker) を参照。
+> 撮影手順は [📸 デモ GIF 取得チェックリスト](#-デモ-gif-取得チェックリスト) を参照。

-| ✅ **v0.4.0** | 2026-05-13 | MCP server (stdio) — 5 read-only tools、Claude Desktop / Cowork 対応 |
+| ✅ **v0.4.0** | 2026-05-13 | MCP server (stdio) — 6 tools (5 read + 1 ingest)、Claude Desktop / Cowork 対応 |
```

demo.gif の対応は **方針 A** (img 行削除) を採用。GitHub プレビューで 404 にならない + README 末尾の「📸 デモ GIF 取得チェックリスト」セクションは既に詳細手順があるためそこへリンク誘導。録画完了後はトップに img を再挿入するだけで済む。

### `docs/mcp-server.md`

```diff
-...コード重複ゼロで 5 tools を実装できた。
+...コード重複ゼロで 6 tools (5 read + 1 ingest) を実装できた。

-- **category** (enum, required) — values: ['技術記事', '日記', '読書メモ', 'ミーティングメモ', 'アイデア']
+- **category** (enum, required) — values: ['技術記事', 'メモ', '議事録', 'ToDo']
-- **level** (enum) — values: ['入門', '初級', '中級', '上級']
+- **level** (enum) — values: ['初級', '中級', '上級']

+### 3-6. `axis_ingest_memo`
+
+生メモ (Slack 抜粋 / 議事録 / Apple Notes / プレーン Markdown) を axis-knowledge-rag 形式の
+YAML-frontmatter Markdown に Claude API で変換する。**ファイル書き込みなし** ...
+ (Input schema 表、Markdown / JSON 出力サンプル、Annotations)
```

`axis_ingest_memo` の 3-6 詳細セクション (I/O 例 + annotations) を追加 + 軸サンプル値を config.yml と一致 (`日記/読書メモ/ミーティングメモ/アイデア` という存在しない値を `メモ/議事録/ToDo` に修正)。テストカバレッジ表に `axis_ingest_memo` 行追加 (18 → 21 tests)。

### `docs/api-reference.md`

```diff
-  "version": "0.3.0",
+  "version": "0.4.0",

-      "values": ["技術記事", "ノウハウ", "メモ"],
-      "required": false
+      "values": ["技術記事", "メモ", "議事録", "ToDo"],
+      "required": true
+    },
+    {
+      "name": "topic",
+      "type": "string",
+      "required": true
     },
     {
       "name": "level",
       "type": "enum",
-      "values": ["入門", "中級", "上級"],
+      "values": ["初級", "中級", "上級"],
```

`config.yml` と完全一致。`topic` (required string) も追加して `axis_list_axes` / `GET /api/axes` の実レスポンスと整合。

### `docs/INDEX.md`

```diff
-## Portfolio
-
-
 ---
```

portfolio-notes 削除 (`feat/spec_006-docker` 復旧時) の残骸である空セクションを削除。

### `docs/deployment.md`

```diff
 # 環境変数ファイルを作成 (API キーは optional)
+# (任意) リリースタグを手元に取り込む — clone 直後はタグが未取得の場合がある
+git fetch --tags origin
+git tag -l                       # v0.1.0 〜 v0.4.0 が表示されれば OK
 cp .env.example .env
```

GitHub Release は v0.1.0〜v0.4.0 の 4 つ origin にあるが、default の clone ではタグが手元に来ない場合があるため明示。

### `CHANGELOG.md`

Day 25 エントリを `[Unreleased]` 直下に追加 (本 spec の全変更点を一覧化)。

## 4. テスト・品質チェック結果

```
$ python3 -c "from importlib.metadata import version; print(version('axis-knowledge-rag'))"
0.4.0

$ grep -n "version" pyproject.toml
7:version = "0.4.0"
72:target-version = "py311"

$ curl http://localhost:8765/api/health    # uvicorn launched on port 8765
{"status":"ok","version":"0.4.0","embedder_mode":"DUMMY","rag_mode":"DUMMY"}

$ curl http://localhost:8765/api/openapi.json | jq .info.version
"0.4.0"

$ grep -c "@mcp.tool" mcp_server/server.py
6

$ grep -n "ノウハウ\|入門" docs/*.md
# (axes 値としての "ノウハウ" "入門" は 0 件。残るのは
#  docs/api-reference.md / docs/mcp-server.md にあるドキュメントタイトル
#  "RAG パターン入門" / "プロンプトエンジニアリング入門" — これは axis 値ではない)

$ grep -n "demo.gif" README.md
304:- [ ] GIF 化、`examples/screenshots/demo.gif` として保存 ...
# (壊れた img 参照は削除済み。残るのは末尾のキャプチャ checklist の保存先指定のみ)

$ python3 -m ruff check .
All checks passed!

$ python3 -m pytest
........................................................................ [ 52%]
................................................................         [100%]
136 passed in 8.07s

$ git tag -l
v0.1.0
v0.2.0
v0.3.0
v0.4.0

$ git ls-remote --tags origin | grep -c "\^{}"
4    # v0.1.0 〜 v0.4.0 全てリモートに存在

$ git log --oneline feat/spec_025-doc-consistency ^main
125acf2 docs: changelog Day 25 (spec_025 doc consistency)
aeaa064 docs: clean portfolio-notes residue + document git fetch --tags
32f11a9 docs(readme): remove broken demo.gif reference (will be re-added when recorded)
1485525 docs(api-reference): align /api/axes + /api/health samples with config.yml
bf90d7e docs: bump MCP tool count to 6 + document axis_ingest_memo
4c177e5 docs(readme): update version badge to 0.4.0
30744b8 feat(api): use _pkg_version() in FastAPI version field
83321da chore: bump version to 0.4.0 in pyproject.toml
```

### Version 文字列 before/after 一覧

| 場所 | Before | After |
|---|---|---|
| `pyproject.toml::version` | `"0.1.0.dev0"` | `"0.4.0"` |
| `backend/src/api.py::FastAPI(version=)` | `"0.3.0.dev0"` (hardcoded) | `_pkg_version()` (動的) |
| `/api/health` response | `"0.1.0.dev0"` (= pyproject 値) | `"0.4.0"` |
| `/api/openapi.json::info.version` | `"0.3.0.dev0"` | `"0.4.0"` |
| `README.md` Version badge | `0.3.0` | `0.4.0` |
| `README.md` Status badge | `v0.3` | `v0.4` |
| `docs/api-reference.md::/api/health sample` | `"0.3.0"` | `"0.4.0"` |

### MCP tool count before/after

| 場所 | Before | After |
|---|---|---|
| `README.md` roadmap row | `5 read-only tools` | `6 tools (5 read + 1 ingest)` |
| `docs/mcp-server.md` L40 (本文) | `5 tools` | `6 tools (5 read + 1 ingest)` |
| `docs/mcp-server.md` Inspector 手順 | `5 つの axis_* tools` | `6 つの axis_* tools` (+ axis_ingest_memo 例追加) |
| `docs/mcp-server.md` file-tree caption | `5 tools` | `6 tools` |
| `docs/mcp-server.md` test count | `18 tests` | `21 tests` (+ axis_ingest_memo 行追加) |
| `mcp_server/server.py` `@mcp.tool` count | 6 (実体は既に揃っていた) | 6 (no change, ground truth) |

### git tag 状態 (最終結論)

- **ローカル**: `v0.1.0` / `v0.2.0` / `v0.3.0` / `v0.4.0` 全 4 つ存在
- **リモート (origin)**: `git ls-remote --tags origin` で v0.1.0〜v0.4.0 全 4 つ存在
- **結論**: 状態は正常。dev-b 環境では clone 時に既に取り込まれていた (fetch 不要だった) が、新規 clone での再現性を担保するため `docs/deployment.md` の起動手順に `git fetch --tags origin` を追記
- spec_025 の前提では「dev-b clone から見えない」と書かれていたが、本実行時点では確認したところローカルにも揃っていた (中島さんの dev-a 操作で同期されたか、過去手動で取り込み済み)。**Open question 化は不要**

## 5. 想定外だったこと / 判断ポイント

- **`_pkg_version()` の配置**: 旧コードでは `app = FastAPI(...)` の **下** に定義されていたため、そのままでは `FastAPI(version=_pkg_version())` を呼べない。`@asynccontextmanager` lifespan の直後 (FastAPI 構築直前) に移動して、定義順を整理した。`/api/health` も同じ関数を参照しているので二重定義は無し
- **demo.gif の方針**: spec が「CC 判断で OK」だったので **方針 A (img 削除)** を採用。理由は (1) GitHub プレビューで 404 になる方が「未完成感」が強くマイナス、(2) README 末尾に既に存在する詳細な「📸 デモ GIF 取得チェックリスト」セクションがあるので、トップから誘導するテキストノートにリンクするだけで運用フローが回る、(3) 1x1 透明 PNG プレースホルダ案は GitHub プレビュー上で「画像読み込みエラー」と区別がつきにくい
- **`docs/mcp-server.md` の `axis_list_axes` サンプル軸値**: spec 本体 (3-4) は `api-reference.md` のみ言及していたが、grep 結果から `docs/mcp-server.md` L172 / L174 / L188 / L191 にも同じ不整合 (`日記`/`読書メモ`/`ミーティングメモ`/`アイデア` という config.yml に存在しない値) を発見。spec 3-5 の「他 docs も統一」に該当するため同時に修正
- **テスト件数の追従**: `docs/mcp-server.md` 9 章のテストカバレッジ表が `18 tests` のままだったが、実際は `axis_ingest_memo` の 3 件が追加済みで 21 件 (`pytest --collect-only` で確認)。表に新行 `axis_ingest_memo | 3` を追加し total 21 に追従
- **コミット粒度**: spec の 7 段階分割を尊重して 8 commit に分けた (CHANGELOG を末尾に分離 + INDEX/deployment.md cleanup を一括化)。README は一度 `git checkout` で revert してから 3 段階 (version badge → tool count → demo.gif) に再適用することで「1 ファイル 3 コミット」の分割を実現
- **`pip install -e .` 再実行**: `pyproject.toml::version` を変更しただけでは `importlib.metadata.version("axis-knowledge-rag")` が旧値 `0.1.0.dev0` を返すため、metadata 更新のために `pip install -e . --break-system-packages` を実行。これによって `/api/health` が `0.4.0` を返すことを確認。ユーザー側でも同様の手順が必要 (動作確認手順に明記)

## 6. Open questions

なし。

## 7. 動作確認手順（ユーザー）

```
1. cd ~/projects/axis-knowledge-rag
2. git fetch origin && git checkout feat/spec_025-doc-consistency
3. pip install -e .          # ← pyproject の新 version で metadata 更新
                             #   (システム Python なら --break-system-packages も検討)
4. python3 -c "from importlib.metadata import version; print(version('axis-knowledge-rag'))"
   # 期待: 0.4.0
5. uvicorn backend.src.api:app --port 8000 &
   sleep 3 && curl http://localhost:8000/api/health
   # 期待: {"status":"ok","version":"0.4.0","embedder_mode":"DUMMY","rag_mode":"DUMMY"}
   kill %1
6. python3 -m pytest --quiet
   # 期待: 136 passed
7. python3 -m ruff check .
   # 期待: All checks passed!
8. GitHub で README をプレビュー → demo.gif の 404 が出ないことを確認
   https://github.com/kazikimaguro13/axis-knowledge-rag/blob/feat/spec_025-doc-consistency/README.md
9. (任意) PR を作成: gh pr create --base main --head feat/spec_025-doc-consistency
```

期待結果:

- version 文字列が全箇所 `0.4.0` で揃う (pyproject / api.py / README badge / /api/health / OpenAPI)
- MCP tool 数表記が全箇所 `6 tools` で揃う (README ロードマップ / docs/mcp-server.md 各所)
- `docs/api-reference.md` と `docs/mcp-server.md` の axes サンプルが `config.yml` (技術記事/メモ/議事録/ToDo + 初級/中級/上級) と一致
- `README.md` プレビューに壊れた demo.gif の 404 が出ない
- ruff / pytest 緑 (ロジック未変更を担保)
- `feat/spec_025-doc-consistency` ブランチが origin に push 済み (`git push -u origin feat/spec_025-doc-consistency` 実行済み)

## 8. 次の提案

実装中に気づいた、別 spec として切り出すべき改善案。

- **spec_026 候補**: CHANGELOG の歴史エントリ (Day 22 / Day 23) で `5 read-only tools` / `5 tools` と書かれた箇所が残存。これは「過去ログとして正しい」ので spec_025 では触らなかったが、もし「現状にも適用される歴史記述」と解釈するなら追補注記を入れる選択肢あり (低優先度)
- **spec_026 候補**: `docs/architecture.md` / `docs/design-decisions.md` には axes サンプル値の直接列挙はないが、ADR の文面で `category: "技術記事"` 単体を使っている箇所がある。今回の修正で `["技術記事", "メモ", "議事録", "ToDo"]` の 4 値スキーマが正となるので、ADR 説明文でも 4 値であることを明示するとさらに整合性が高まる (低優先度)
- **spec_026 候補 (本命)**: spec_025 で残った `examples/screenshots/demo.gif` の実録画。Day 20 / Day 26 で中島さんが手動で撮影 → README トップに img 再挿入。撮影手順は README 末尾チェックリストにあるのでそれをなぞる
- **spec_027 候補**: spec 本体に「Next spec 候補」として `MCP error sanitization` / `ChromaDB cosine 距離明示` / `Ingester 重複スキャン削減` が列挙されていた。順序は (1) MCP error sanitization (リスク低 + dev 体験改善) → (2) Ingester 堅牢化 → (3) ChromaDB 距離明示 を推奨
