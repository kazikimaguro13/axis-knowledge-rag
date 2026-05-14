# spec_010: Day 10 — integrity.py (参照整合性チェック)

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜009 完成前提, `docs/spec-v2.md` Day 10 行

## 1. 目的

```
[現状]
- ナレッジ Markdown に `refs: ["doc_002", "doc_999"]` のような参照が書ける
- 例: `examples/knowledge/05-prompt-engineering.md` は `doc_999` という存在しない doc を指している (Day 1 で意図的に仕込み)
- この壊れリンクを検出する手段がない

[変更後]
- `backend/src/integrity.py` が `IntegrityChecker` を提供:
  - `check(docs: list[Document]) -> IntegrityReport` で全 doc を一括検証
  - レポートには broken_refs / orphan_docs / cycle_warnings を含む
- CLI `python -m backend.src.integrity ./examples/knowledge` で human-readable レポート出力
- `config.yml` の `integrity.check_refs / fail_on_broken` を尊重
- `scripts/build_index.py` に `--strict-integrity` フラグ追加で、壊れリンクある場合 index 構築を止める
```

差別化機能 2 つ目。ナレッジが大きくなるほど価値が出る機能 (履歴書アピール強い)。

## 2. 制約

### 触ってよいファイル

- `backend/src/integrity.py` — 新規
- `backend/tests/test_integrity.py` — 新規
- `scripts/build_index.py` — `--strict-integrity` フラグ追加
- `docs/integrity.md` — 仕組み解説
- `CHANGELOG.md`

### 触ってはいけないもの

- 既存 source の他ファイル (loader/embedder/vector_store/search/rag/normalizer)
- 既存テスト (回帰禁止)
- `_ai_workspace/`、`docs/spec-v2.md`

### コーディングルール

- 標準ライブラリのみ (`dataclasses` / `collections` / `typing`)
- レポートは dataclass で構造化 (JSON 化可能、Day 13 の docs 自動生成に流せる)
- CLI 出力は色付き不要、シンプルなテキスト

## 3. やってほしいこと

### 3-1. `backend/src/integrity.py`

```python
"""Reference integrity checker for the knowledge base.

Validates that every `refs: [...]` entry in a document points to an existing
document id, and surfaces orphans / cycles for awareness.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from backend.src.loader import Document

logger = logging.getLogger(__name__)


@dataclass
class BrokenRef:
    source_id: str
    source_path: str
    target_id: str  # the missing one


@dataclass
class IntegrityReport:
    total_docs: int = 0
    total_refs: int = 0
    broken_refs: list[BrokenRef] = field(default_factory=list)
    orphan_docs: list[str] = field(default_factory=list)  # docs not referenced by anyone
    cycles: list[list[str]] = field(default_factory=list)  # simple cycle detection
    docs_by_id: dict[str, str] = field(default_factory=dict)  # id -> path

    @property
    def has_errors(self) -> bool:
        return bool(self.broken_refs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_docs": self.total_docs,
            "total_refs": self.total_refs,
            "broken_refs": [
                {"source_id": b.source_id, "source_path": b.source_path, "target_id": b.target_id}
                for b in self.broken_refs
            ],
            "orphan_docs": self.orphan_docs,
            "cycles": self.cycles,
        }


def _find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Simple DFS cycle detection. Returns a list of cycle paths."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = defaultdict(int)
    cycles: list[list[str]] = []
    stack: list[str] = []

    def visit(node: str) -> None:
        if color[node] == GRAY:
            # Found cycle: rewind stack until we find node again
            idx = stack.index(node)
            cycles.append(stack[idx:] + [node])
            return
        if color[node] == BLACK:
            return
        color[node] = GRAY
        stack.append(node)
        for nxt in graph.get(node, []):
            visit(nxt)
        stack.pop()
        color[node] = BLACK

    for n in list(graph.keys()):
        if color[n] == WHITE:
            visit(n)
    return cycles


class IntegrityChecker:
    def check(self, docs: list[Document]) -> IntegrityReport:
        report = IntegrityReport(total_docs=len(docs))
        ids = {d.id for d in docs}
        report.docs_by_id = {d.id: str(d.path) for d in docs}

        referenced: set[str] = set()
        graph: dict[str, list[str]] = defaultdict(list)

        for d in docs:
            for r in d.refs:
                report.total_refs += 1
                referenced.add(r)
                graph[d.id].append(r)
                if r not in ids:
                    report.broken_refs.append(
                        BrokenRef(source_id=d.id, source_path=str(d.path), target_id=r)
                    )

        # orphan = doc not referenced by anyone (including itself)
        report.orphan_docs = sorted(d.id for d in docs if d.id not in referenced)

        # cycles
        report.cycles = _find_cycles(graph)

        return report


def format_report(report: IntegrityReport) -> str:
    lines: list[str] = []
    lines.append(f"=== Integrity Report ===")
    lines.append(f"Total documents: {report.total_docs}")
    lines.append(f"Total refs:      {report.total_refs}")
    lines.append("")
    if report.broken_refs:
        lines.append(f"❌ Broken refs: {len(report.broken_refs)}")
        for b in report.broken_refs:
            lines.append(f"  - {b.source_id} ({b.source_path}) -> {b.target_id} (missing)")
    else:
        lines.append("✅ No broken refs")
    lines.append("")
    if report.orphan_docs:
        lines.append(f"⚠️  Orphan docs (not referenced): {len(report.orphan_docs)}")
        for o in report.orphan_docs:
            lines.append(f"  - {o}")
    else:
        lines.append("✅ No orphan docs")
    lines.append("")
    if report.cycles:
        lines.append(f"⚠️  Cycles: {len(report.cycles)}")
        for c in report.cycles:
            lines.append("  - " + " -> ".join(c))
    else:
        lines.append("✅ No cycles")
    return "\n".join(lines)


def _main(argv: list[str]) -> int:
    import argparse
    import json
    import sys
    from pathlib import Path

    from backend.src.config import configure_logging
    from backend.src.loader import load_directory

    configure_logging()
    p = argparse.ArgumentParser()
    p.add_argument("knowledge_dir", type=Path)
    p.add_argument("--json", action="store_true", help="Output JSON instead of text")
    p.add_argument("--strict", action="store_true", help="Exit 1 if broken refs found")
    args = p.parse_args(argv[1:])

    docs = load_directory(args.knowledge_dir)
    report = IntegrityChecker().check(docs)

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_report(report))

    if args.strict and report.has_errors:
        return 1
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv))
```

### 3-2. `scripts/build_index.py` 更新

```python
def main(argv):
    ...
    parser.add_argument("--strict-integrity", action="store_true",
                        help="Abort index build if broken refs are detected")
    args = parser.parse_args(argv[1:])

    docs = load_directory(args.knowledge_dir, normalizer=norm)

    if args.strict_integrity or config.get("integrity", {}).get("fail_on_broken", False):
        from backend.src.integrity import IntegrityChecker, format_report
        report = IntegrityChecker().check(docs)
        if report.has_errors:
            print(format_report(report), file=sys.stderr)
            print("Integrity check failed. Aborting.", file=sys.stderr)
            return 1

    ...  # continue with embedding + upsert
```

### 3-3. `backend/tests/test_integrity.py`

- 5 件 doc、broken refs 0 のケース → `has_errors == False`
- broken refs 1 のケース → `broken_refs` に 1 件
- orphan doc 検出 (`doc_001` が誰からも参照されない場合)
- 単純な cycle (`A -> B -> A`) 検出
- self-loop (`A -> A`) は cycle として検出される

### 3-4. `docs/integrity.md`

200 行程度。「なぜ参照整合性が重要か」「壊れリンクの典型パターン」「strict モード」「将来計画 (v0.4 で `notes:` への自動 backlink 注入)」。

### 3-5. 動作確認

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"
python -m backend.src.integrity ./examples/knowledge

# 期待出力:
# ❌ Broken refs: 1
#   - doc_005 (examples/knowledge/05-prompt-engineering.md) -> doc_999 (missing)
# ⚠️ Orphan docs: ... (doc_002 / doc_005 等)

python -m backend.src.integrity ./examples/knowledge --strict
# 期待: 終了コード 1

python -m backend.src.integrity ./examples/knowledge --json | head -20
# 期待: JSON 形式

python -m scripts.build_index ./examples/knowledge --strict-integrity
# 期待: 失敗 (doc_999 を指す壊れリンクがあるため)
```

### 3-6. コミット

1. `feat: implement integrity.py with broken refs, orphans, cycles`
2. `feat: add --strict-integrity to build_index.py`
3. `test: add integrity checker tests`
4. `docs: add docs/integrity.md`
5. `docs: changelog Day 10`

`git push origin main` (dev-b)

### 3-7. result_010.md

特に書くこと:

- 既存 5 件サンプルでの integrity 出力 (text + JSON)
- cycle 検出のテストケースを実例で
- `--strict-integrity` で build_index が aborts することを確認
- Open question で「サンプルの壊れリンク doc_999 をいつ修正するか」を提案 (v0.2.0 リリース直前か、それともデモのため残すか)

## 4. 成功条件

- [ ] CLI が text / JSON 両モード動作
- [ ] `--strict` で終了コード 1
- [ ] build_index `--strict-integrity` で abort
- [ ] 全テスト PASS
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_010.md`

## 6. 質問

- **doc_999 をどうするか**: Day 1 で意図的に仕込んだ壊れリンク。v0.2.0 リリース時に integrity 機能のデモとして残すなら現状維持、修正するなら refs 削除。判断分かれそうなので質問
- **cycle の扱い**: 厳密には RAG では cycle は「相互参照する記事」で発生し得る (例: 「RAG とは → ベクトル検索 → RAG」)。エラーではなく warning にしているが、`--strict-cycles` フラグを足すか質問
- **orphan の扱い**: 単独で完結した記事は orphan になりやすい。エラーではなく info レベル

## 7. 補足

### 設計の意図

- **cycle 検出は DFS の WHITE/GRAY/BLACK スタイル**: 標準的、可読性高い
- **report を dataclass + as_dict**: Day 13 で `docs/integrity-report.md` を自動生成する候補に使える
- **build_index への統合**: ユーザーが「壊れリンクのまま index 化する」と「直してから index する」を選べる

### Day 11 連携

`marker.py` で `<!-- AUTO_GENERATED_*** -->` ブロックを扱う際、自動生成セクションに refs を入れる場合の整合性は integrity で検出できる (人間が書いた refs と自動生成が共存しても OK)。Day 11 spec で詳細。
