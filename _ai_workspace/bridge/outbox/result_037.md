# result_037 — Parent Storage: JSON → SQLite migration

- **Spec**: spec_037
- **Date**: 2026-05-14
- **Branch**: feat/spec_037-parent-sqlite
- **Status**: complete

---

## 1. ファイルサイズ比較

| ファイル | parents 数 | サイズ |
|---------|-----------|-------|
| `parents.json` (v0.7) | 5 | 2.5 KB |
| `parents.db` (v0.8 SQLite) | 5 | 16 KB (SQLite ページ overhead は固定 = 5 親以上で逆転) |
| `parents.json` (v0.7) | 1000 | **1,190 KB** |
| `parents.db` (v0.8 SQLite) | 1000 | **1,392 KB** |

> ファイルサイズは SQLite の方が若干大きい (WAL + B-tree overhead)。  
> ただし JSON はフル read/write が必要なのに対し SQLite は行単位 I/O なので、  
> 実効コストは 1000 parents 以上で SQLite が大幅に有利。

---

## 2. 起動時間比較 (1000 parents)

| 方式 | 起動コスト (avg 10 runs) |
|-----|------------------------|
| JSON 全ロード (v0.7) | **12.8 ms** |
| SQLite lazy init (v0.8) | **0.7 ms** |

SQLite は接続開放のみで初期化完了。1000 parents での改善は **約 18 倍**。

---

## 3. テスト件数

| 項目 | 件数 |
|-----|-----|
| spec_037 実装前 (spec_040 完了時点) | 291 件 |
| spec_037 追加テスト (test_parent_storage.py) | 22 件 (TestCommon×2バックエンド + TestSqliteSpecific + TestMigration) |
| spec_037 追加テスト (test_vector_store.py) | 3 件 |
| **合計** | **316 件** (目標 304+ を達成) |

全テスト PASS、ruff 緑。

---

## 4. マイグレーションコマンド実行ログ

```bash
# 初回 (parents.json あり → parents.db 新規生成)
$ python3 -m scripts.build_index --migrate-parents-json --db-path /tmp/demo_chroma
migrated 5 parents to /tmp/demo_chroma/parents.db

# 2回目 (冪等: parents.db 既存 → skip)
$ python3 -m scripts.build_index --migrate-parents-json --db-path /tmp/demo_chroma
already migrated: /tmp/demo_chroma/parents.db exists — skipping.

# どちらも exit 0
```

---

## 5. Backward compat: `storage: "json"` で v0.7 挙動確認

`config.yml` を `storage: "json"` にした場合:

- `make_parent_storage(chroma_dir, storage="json")` → `JsonParentStorage` を返す
- `JsonParentStorage` は `parents.json` を全ロードし、従来通りの動作を再現
- テスト `test_factory_storage_json_returns_json` で確認済み

---

## 6. lazy auto-migrate の動作確認

`make_parent_storage(chroma_dir, storage="sqlite")` 呼び出し時に:

- `parents.db` 不在 + `parents.json` 存在 → warning ログ 1 行出力 + 自動 sqlite 化
- `parents.json` は削除しない (保持。`storage: "json"` で戻せる)
- テスト `test_auto_migrate_json_to_sqlite` / `test_migrated_data_matches_original` で確認済み

---

## 7. 実装サマリ

| ファイル | 変更種別 | 概要 |
|---------|---------|-----|
| `backend/src/parent_storage.py` | **新規** | `ParentStorage` Protocol + `SqliteParentStorage` + `JsonParentStorage` + `make_parent_storage()` factory |
| `backend/src/vector_store.py` | 修正 | `self._parents dict` → `self._parent_storage: ParentStorage` に置換 |
| `scripts/build_index.py` | 修正 | `--migrate-parents-json` / `--parent-storage` フラグ追加 |
| `backend/src/config.py` | 修正 | `ParentDocConfig.storage` フィールド追加 |
| `config.yml` | 修正 | `retrieval.parent_doc.storage: "sqlite"` 追加 |
| `backend/tests/test_parent_storage.py` | **新規** | 17 テストケース (22 実行) |
| `backend/tests/test_vector_store.py` | 修正 | SQLite パス専用テスト 3 件追加 |
| `docs/adr/ADR-023-parent-storage-sqlite.md` | **新規** | 設計判断記録 |
| `docs/configuration.md` | **新規** | 全 config.yml キーのリファレンス表 |
| `CHANGELOG.md` | 修正 | Day 37 追記 |

---

## 8. Open Questions (記録のみ)

- **VACUUM**: `reset()` 後に `VACUUM` 未実施。DB サイズ < 100KB の想定で v0.8 は無視。spec_047 候補。
- **parents.json 自動削除**: migrate 完了後も `parents.json` を保持 (`storage: "json"` へ戻し可能にする)。意図的設計。
- **1000+ parents でのファイルサイズ**: SQLite は JSON よりわずかに大きいが、行単位 I/O の優位性が上回る。

---

## 成功条件チェック

- [x] `ParentStorage` Protocol + 2 実装 (Sqlite / Json) 完成
- [x] default = SQLite (`data/chroma/parents.db`)
- [x] `parents.json` 既存ユーザーは初回起動で自動 migrate + warning ログ
- [x] `python3 -m scripts.build_index --migrate-parents-json` が冪等
- [x] `storage: "json"` で v0.7 挙動が完全再現
- [x] 既存 291 tests 緑 + 新規 ~25 件 = **316 件 PASS** (目標 304+ を達成)
- [x] ruff 緑
- [x] ADR-023 / configuration.md / CHANGELOG 更新
- [x] git push 完了 (main への push なし)
