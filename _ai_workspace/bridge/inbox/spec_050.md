# spec_050: v0.9 全体総合コードレビュー (F1-F5 完成後)

- **Author**: auto_dispatch_controller
- **Created**: auto
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Type**: **code-review (no source modifications)**

## 1. 目的

v0.8.1 から F1-F5 (spec_045〜049) を順次マージした v0.9 状態を **総合レビュー** する。spec_041 / 044 と同じ read-only パターン。

## 2. 対象

`git log v0.8.1..HEAD --oneline` の差分すべて。主に:
- spec_045 (Ollama integration)
- spec_046 (Browser Extension MVP)
- spec_047 (Active Learning Feedback)
- spec_048 (Knowledge Gap Detection)
- spec_049 (Bidirectional refs)

## 3. やってほしいこと

各 spec について **security / performance / correctness / maintainability** の 4 軸評価:

1. spec_045 (Ollama): Embedder/Generation の Protocol 化が綺麗か、URL injection 経路、bge-m3 次元 mismatch の検知、API 呼び出しの timeout / retry
2. spec_046 (Browser Ext): CORS 設定の妥当性 (`chrome-extension://*` は wild card OK か)、`/api/ingest` の XSS / path traversal、slug 生成のロバスト性
3. spec_047 (Feedback): SqliteStore のスレッドセーフ性、UI feedback button の二重送信防止、query の PII 蓄積リスク
4. spec_048 (Gap Detection): `detect_no_info` の偽陽性率、search/rag hook が既存 logic を破壊していないか、gap DB の disk growth 抑制
5. spec_049 (Bidirectional): API 2x call の cost、forwardlinks/backlinks の表示順、MCP 後方互換

加えて **全体としての一貫性**:
- 4 つの新規 SQLite (.axis_chat / .axis_feedback / .axis_gap / parents) の整理、共通の Store Protocol を見直すべきか
- v0.9.0 リリース可能か (A 判定 = ES に貼れる)
- 新たに見つけた問題 0-5 件、priority 付き
- ポジティブ評価 0-5 件
- v0.10 候補

結果を `_ai_workspace/bridge/outbox/result_050.md` に書く。**修正禁止**。

## 4. 成功条件

- [ ] 5 spec × 4 軸の所見テーブル
- [ ] 全体評価 (A/B/C)
- [ ] 新たな問題 0-5 件
- [ ] ファイル変更 0、commit 0
- [ ] result_050.md に出力済み

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_050.md`
