# spec_028: 再総合コードレビュー (B→A 判定確認、spec_025/026/027 後)

- **Author**: Cowork (中島)
- **Created**: 2026-05-13
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Type**: code-review (no source modifications)
- **Bundles**: spec_024 (前回レビュー、B 判定) + spec_025 / 026 / 027 (B→A 改善)

## 1. 目的

前回 spec_024 で **B 判定** をもらった指摘を spec_025/026/027 で順に解消した。改善が反映されているか、A 判定に上がるかを確認する。

```
[前回 spec_024 で指摘された 10 件]
1.  README badge/tools 数 inconsistency → spec_025 で修正
2.  api.py version / pyproject.toml version drift → spec_025 で修正
3.  demo.gif placeholder 404 → spec_025 で削除
4.  git tag が見えない問題 → spec_025 で「git fetch --tags」案内追記
5.  docs/api-reference.md axes サンプル不整合 → spec_025 で修正
6.  ingester.py 二重スキャン → spec_026 で _scan_knowledge_dir 統合
7.  ingester.py invalid JSON 即終了 → spec_026 で retry 実装
8.  MCP error が internal details 漏らす → spec_027 で make_error_response 導入
9.  axis_search の zero embedding (axis-only) → 未対応 (spec_028 で議論)
10. axis_list_documents 200 件上限 → spec_026 で list_with_filter 解除

[このレビューでやること]
- 10 件指摘がすべて解消されているか確認
- 新たな問題が混入していないか確認
- security / performance / correctness / maintainability の 4 軸再評価
- A 判定 (引き渡し可能) に届くか判定
```

**重要: 修正禁止。** すべて result_028.md に書き出す。

## 2. 制約

### 触ってよいファイル

- なし。**完全 read-only**
- `_ai_workspace/bridge/outbox/result_028.md` のみ書き込み可

### 触ってはいけないもの

- 全ソースコード、ドキュメント、設定
- git 操作 (commit / push / branch / tag)

## 3. やってほしいこと

### 3-1. 前回指摘 10 件の解消確認

各項目について「解消 / 一部解消 / 未対応 / 新規問題」の判定:

1. **README badge / tools 数** — `grep "version-0.4" README.md` / `grep "6 tools" docs/mcp-server.md` で確認
2. **api.py version / pyproject** — `grep "_pkg_version()" backend/src/api.py` / `grep "0.4.0" pyproject.toml`
3. **demo.gif** — `grep "demo.gif" README.md` (期待: 0 件)
4. **git tag 案内** — `git tag -l` 確認 + `grep "fetch --tags" docs/` で案内文確認
5. **axes サンプル** — `grep "ノウハウ\|入門" docs/` (期待: 0 件)
6. **ingester 二重スキャン** — `grep "_scan_knowledge_dir" backend/src/ingester.py`、`load_directory` 呼び出し回数を grep
7. **ingester retry** — `grep "retry_count" backend/src/ingester*.py`
8. **MCP error sanitize** — `grep "make_error_response" mcp_server/server.py` (期待: 6 件) + `mcp_server/_errors.py` 存在確認
9. **axis-only zero embedding** — `axis_list_documents` が list_with_filter ベースになったか確認 (zero embedding は完全には消えてないかも)
10. **axis_list_documents 200 上限** — `grep "top_k=200" mcp_server/server.py` (期待: 0 件) + `grep "list_with_filter\|count_with_filter" mcp_server/server.py`

### 3-2. 4 軸再評価

軽めに見る:
- Security: 新たな漏洩経路追加されていないか、特に MCP error sanitize の例外網羅性
- Performance: 二重スキャン解消の妥当性、retry 実装が無限ループしないか
- Correctness: テストカバレッジ (前回 76% → 上がってるか)、新規追加された tests の網羅性
- Maintainability: spec_025/026/027 で documents が更新されているか、changelog が日次

### 3-3. 全体評価

- **A: 引き渡し可能** — もう何も直すべきものがない、ES に貼って自信を持って出せる
- **B: 軽微な改善あり** — 残り少し
- **C: 重大な問題** — リリース推奨しない

判定理由を 3-5 文で明確に。

### 3-4. 新たに見つけた問題

10 件指摘以外で、spec_025/026/027 で新規に混入した、または以前見落としていた問題を最大 5 件。

### 3-5. 結果を result_028.md に書く

`templates/result_template.md` 構造で:

- 1. 要約 (1 行 + 主要観察)
- 2. 全体評価 (A/B/C と根拠)
- 3. 前回 10 件指摘の解消状況テーブル
- 4. 新たに見つけた問題 (0〜5 件)
- 5. 4 軸別の差分所見 (前回比)
- 6. ポジティブ評価
- 7. 推奨される次の spec (もしあれば)
- 8. Open questions

### 3-6. 修正禁止

read-only タスク。気になる点があっても commit / edit せず、すべて result_028.md に。

## 4. 成功条件

- [ ] 10 件指摘の解消判定がテーブルで記載
- [ ] 全体評価 (A/B/C) が 1 つ明示
- [ ] 新たな問題が 0〜5 件記載
- [ ] ファイル変更 0、commit 0

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_028.md`

## 6. 補足

### main HEAD

`1ae9ed6 fix(merge): restore spec_026 axis_list_documents body lost to spec_027 conflict resolution`

これは spec_026 + spec_027 を merge した後に手動 fix した commit。**merge 後のテスト 162 件全 PASS、ruff 緑** の状態を確認済み。

### 前回レビューとの差分対象

spec_024 が見たのは HEAD `6363bdd` (v0.4.0)。
今回見るのは HEAD `1ae9ed6` (v0.5.0 候補)。
diff は `git diff 6363bdd..1ae9ed6 --stat` で把握できる。
