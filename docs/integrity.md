# Knowledge Base Integrity Checker

## 概要

`backend/src/integrity.py` はナレッジベースの **参照整合性** を検証するモジュールだ。
ドキュメントの `refs: [...]` フィールドが指す ID が実際に存在するかを確認し、
壊れリンク・孤立ドキュメント・循環参照を一括検出してレポートする。

---

## なぜ参照整合性が重要か

ナレッジベースが 10 件を超えると、ドキュメント間の参照は手作業では追いきれなくなる。
典型的な問題は次の 3 種類だ。

### 1. 壊れリンク (Broken Refs)

```yaml
# 05-prompt-engineering.md
refs: ["doc_999"]   # doc_999 は存在しない
```

RAG 検索でこのドキュメントがヒットしても、参照先をたどれない。
ユーザーが「詳細は doc_999 を参照」と期待しても 404 的な体験になる。

### 2. 孤立ドキュメント (Orphan Docs)

誰からも参照されないドキュメントは、ナレッジグラフ上で孤立している。
これ自体は致命的ではないが、

- 別のドキュメントから参照すべきだったのに漏れている
- 不要になったが削除されていない

のどちらかを示す可能性があるため、警告として浮かび上げる。

### 3. 循環参照 (Cycles)

```
RAG とは → ベクトル検索とは → RAG とは → ...
```

RAG システムでは相互参照は自然に発生する（例: 「RAG」と「ベクトル検索」が互いを参照する）。
エラーではなく **警告** として扱い、意図しないループは人間が判断する設計にしている。

---

## アーキテクチャ

```
IntegrityChecker.check(docs: list[Document]) -> IntegrityReport
         |
         |-- ID セット構築 (O(n))
         |-- refs ループ: 壊れリンク検出 (O(n * avg_refs))
         |-- 孤立ドキュメント検出 (O(n))
         +-- _find_cycles(graph) -> DFS WHITE/GRAY/BLACK
```

### IntegrityReport (dataclass)

| フィールド     | 型                   | 説明                          |
|------------|----------------------|-------------------------------|
| total_docs | int                  | 検査したドキュメント総数        |
| total_refs | int                  | 参照エントリの総数              |
| broken_refs | list[BrokenRef]     | 存在しない ID を指す参照一覧    |
| orphan_docs | list[str]           | 誰からも参照されない doc ID 一覧 |
| cycles      | list[list[str]]     | 検出された循環参照パス一覧       |
| docs_by_id  | dict[str, str]      | id -> ファイルパス の逆引き辞書  |
| has_errors  | bool (property)     | broken_refs が 1 件以上あれば True |

### BrokenRef (dataclass)

| フィールド     | 型    | 説明                          |
|------------|-------|-------------------------------|
| source_id  | str   | 参照元のドキュメント ID        |
| source_path | str  | 参照元のファイルパス           |
| target_id  | str   | 参照先の (存在しない) ID       |

---

## サイクル検出アルゴリズム

DFS (深さ優先探索) の WHITE / GRAY / BLACK 3 色法を採用している。

```
WHITE  = 未訪問
GRAY   = 訪問中 (スタックに積まれている)
BLACK  = 訪問完了
```

ノードを訪問しようとしたとき、その色が GRAY なら「既にスタックにある = サイクル」と判定し、
スタックを巻き戻してサイクルパスを記録する。

この実装の特徴:
- 有向グラフの多重エッジに対応
- 自己参照 (`A -> A`) もサイクルとして検出する
- 標準ライブラリのみで実装 (外部依存ゼロ)

---

## CLI の使い方

### テキスト出力 (デフォルト)

```bash
python -m backend.src.integrity ./examples/knowledge
```

出力例:

```
=== Integrity Report ===
Total documents: 5
Total refs:      1

[BROKEN] Broken refs: 1
  - doc_005 (examples/knowledge/05-prompt-engineering.md) -> doc_999 (missing)

[WARN] Orphan docs (not referenced): 4
  - doc_001
  - doc_002
  - doc_003
  - doc_004

[OK] No cycles
```

### JSON 出力

```bash
python -m backend.src.integrity ./examples/knowledge --json
```

```json
{
  "total_docs": 5,
  "total_refs": 1,
  "broken_refs": [
    {
      "source_id": "doc_005",
      "source_path": "examples/knowledge/05-prompt-engineering.md",
      "target_id": "doc_999"
    }
  ],
  "orphan_docs": ["doc_001", "doc_002", "doc_003", "doc_004"],
  "cycles": []
}
```

### strict モード

```bash
python -m backend.src.integrity ./examples/knowledge --strict
echo $?   # 1 (壊れリンクがあるため)
```

`--strict` フラグを付けると、壊れリンクが 1 件以上あった場合に **終了コード 1** を返す。
CI パイプラインに組み込む場合に使用する。

---

## build_index.py との統合

`scripts/build_index.py` に `--strict-integrity` フラグを追加した。

```bash
# 壊れリンクがある場合はインデックス構築を中止
python -m scripts.build_index ./examples/knowledge --strict-integrity
```

`config.yml` の `integrity.fail_on_broken: true` でもフラグと同等の動作になる:

```yaml
integrity:
  check_refs: true
  fail_on_broken: true   # これが true だと --strict-integrity 相当
```

フロー:

```
build_index.py
  -> load_directory()
  -> IntegrityChecker().check(docs)   # --strict-integrity or fail_on_broken=true の場合
       -> has_errors? -> YES: format_report() を stderr に出力して exit 1
       -> NO: 続行
  -> Embedder.embed_batch()
  -> VectorStore.upsert_many()
```

---

## 壊れリンクの典型パターン

| パターン             | 原因                           | 対処                          |
|-------------------|-------------------------------|-------------------------------|
| `doc_999` 参照      | テスト用ダミー ID を消し忘れた   | refs から削除するか実ドキュメントを作成 |
| 削除したドキュメントへの参照 | ドキュメントを削除したが refs を更新しなかった | 参照元の refs を更新           |
| タイポ (`doc_01` vs `doc_001`) | ID の書き間違い         | 正しい ID に修正               |
| 別ナレッジベースへの参照 | 設計ミス                      | refs は同一ナレッジベース内のみ対象とする |

---

## 開発者向け: プログラムから使う

```python
from pathlib import Path
from backend.src.loader import load_directory
from backend.src.integrity import IntegrityChecker, format_report

docs = load_directory(Path("./examples/knowledge"))
report = IntegrityChecker().check(docs)

if report.has_errors:
    print(format_report(report))
    raise SystemExit(1)

# JSON 化して Day 13 の自動ドキュメント生成に流す
import json
data = report.as_dict()
json.dumps(data, indent=2, ensure_ascii=False)
```

---

## strict モードの使い分け

| シナリオ                     | 推奨設定                      |
|----------------------------|-------------------------------|
| 開発中 (壊れリンクがあっても作業したい) | デフォルト (strict なし)       |
| CI / CD パイプライン          | `--strict` または `fail_on_broken: true` |
| デモ・プレゼン前の最終確認     | `python -m backend.src.integrity --strict` |
| インデックス構築を安全に行いたい | `build_index --strict-integrity` |

---

## 将来計画

### v0.3 予定: `--fix` フラグ

壊れリンクを自動で refs から除去するオプション。
`--dry-run` と組み合わせて安全に動作させる設計を検討中。

### v0.4 予定: `notes:` への自動 backlink 注入

Day 11 で実装する `marker.py` の `<!-- AUTO_GENERATED_*** -->` ブロックが
refs を自動生成する場合、整合性チェックはその自動生成 refs も検証対象に含める。
人間が書いた refs と自動生成 refs が共存しても、integrity は透過的に扱える設計になっている。

### v0.4 予定: `--strict-cycles` フラグ

循環参照を warning ではなく error として扱うフラグ。
RAG では相互参照が自然に発生するため、デフォルトは warning のままとし、
オプトインで strict にできる設計にする。

### v0.5 予定: グラフ可視化

`report.as_dict()` の出力を Mermaid 形式の有向グラフ図に変換し、
`docs/knowledge-graph.md` に自動生成する機能。ナレッジベースの全体像を俯瞰できる。

---

## FAQ

**Q: 自己参照 (`refs: ["doc_001"]` in `doc_001`) は許容されるか?**

A: 技術的には問題ないが、integrity はサイクルとして検出し警告する。
自己参照が意味を持つユースケースは少ないため、通常は設計ミスと見なしてよい。

**Q: `refs` に同じ ID を複数回書いたらどうなるか?**

A: それぞれ個別の参照としてカウントされる。重複チェックは現在の scope 外だが、
v0.3 で `duplicate_refs` を IntegrityReport に追加することを検討中。

**Q: サブディレクトリのドキュメントも対象になるか?**

A: `load_directory()` のデフォルトは非再帰 (`*.md`)。再帰的に読み込む場合は
`load_directory(path, pattern="**/*.md")` を使い、同じ docs リストを渡せばよい。

**Q: `doc_999` のサンプル壊れリンクはいつ修正するか?**

A: `05-prompt-engineering.md` の `refs: ["doc_999"]` は Day 1 で意図的に仕込んだ
デモ用の壊れリンクだ。integrity 機能のデモとして v0.2.0 リリースまで残す方針だが、
v0.2.0 リリース直前に削除するか実ドキュメントを作成するかの判断は Open question として残している。
詳細は `result_010.md` の Open questions セクションを参照。

---

## See also

- [architecture.md](architecture.md) — IntegrityChecker のビルドフローでの位置づけ
- [api-reference.md](api-reference.md#backendsrcintegrity) — `IntegrityChecker` / `IntegrityReport` API
- [INDEX.md](INDEX.md) — ドキュメント目次
