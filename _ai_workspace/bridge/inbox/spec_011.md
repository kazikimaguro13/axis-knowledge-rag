# spec_011: Day 11 — marker.py (AUTO_GENERATED ブロック保護)

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜010, `docs/spec-v2.md` Day 11 行

## 1. 目的

```
[現状]
- 人間が書いたナレッジ Markdown に AI で自動生成した要約 / FAQ / メタデータを追記する仕組みがない
- 仕様書 5.1 で `<!-- AUTO_GENERATED_START: summary --> ... <!-- AUTO_GENERATED_END: summary -->` というマーカー方式を予告済み

[変更後]
- `backend/src/marker.py` が以下を提供:
  - `MarkerBlock` dataclass — name, content, raw_full
  - `extract_blocks(text: str) -> list[MarkerBlock]` — マーカーで囲まれた区画を抽出
  - `update_block(text: str, name: str, new_content: str) -> str` — 既存ブロックを置換、無ければ末尾に追加
  - `strip_blocks(text: str) -> str` — マーカー区画を全削除
- CLI `python -m backend.src.marker --list <file>` でブロック一覧
- CLI `python -m backend.src.marker --update <file> --name summary --content "..."` でブロック更新
- 人間記述と自動生成が **物理的に共存** できる構造
```

差別化機能 3 つ目。OSS としての設計レベルの高さをアピールする要。

## 2. 制約

### 触ってよいファイル

- `backend/src/marker.py` — 新規
- `backend/tests/test_marker.py` — 新規
- `examples/knowledge/01-rag-patterns.md` などサンプルに **デモ用にマーカー区画を 1 つだけ追加**
- `docs/marker.md` — 解説
- `CHANGELOG.md`

### 触ってはいけないもの

- 既存 source の他ファイル
- 既存テスト (regression 禁止)
- `_ai_workspace/`、`docs/spec-v2.md`

### コーディングルール

- 標準ライブラリのみ (`re`, `dataclasses`)
- マーカー regex: `<!-- AUTO_GENERATED_START: <name> -->\n...\n<!-- AUTO_GENERATED_END: <name> -->`
- name は `[a-zA-Z0-9_-]+` のみ許可
- ネストは非対応 (Phase 2 で検討)
- 改行コード LF 前提、CRLF が来たら normalize

## 3. やってほしいこと

### 3-1. `backend/src/marker.py`

```python
"""AUTO_GENERATED marker block handling.

Allows human-written Markdown and AI-generated sections to coexist in the
same document. Blocks are delimited by:

    <!-- AUTO_GENERATED_START: <name> -->
    ...
    <!-- AUTO_GENERATED_END: <name> -->

Regenerating a block overwrites only the content between its delimiters,
preserving everything else (= the human-written part).
"""

import re
from dataclasses import dataclass

NAME_PATTERN = r"[a-zA-Z0-9_-]+"
_START_RE = re.compile(r"<!--\s*AUTO_GENERATED_START:\s*(" + NAME_PATTERN + r")\s*-->")
_END_RE = re.compile(r"<!--\s*AUTO_GENERATED_END:\s*(" + NAME_PATTERN + r")\s*-->")
_BLOCK_RE = re.compile(
    r"<!--\s*AUTO_GENERATED_START:\s*(?P<name>" + NAME_PATTERN + r")\s*-->\n"
    r"(?P<content>.*?)"
    r"\n<!--\s*AUTO_GENERATED_END:\s*(?P=name)\s*-->",
    re.DOTALL,
)


class MarkerError(Exception):
    pass


@dataclass
class MarkerBlock:
    name: str
    content: str
    raw_full: str  # full match including delimiters


def extract_blocks(text: str) -> list[MarkerBlock]:
    """Return all AUTO_GENERATED blocks in document order."""
    blocks: list[MarkerBlock] = []
    for m in _BLOCK_RE.finditer(text):
        blocks.append(
            MarkerBlock(
                name=m.group("name"),
                content=m.group("content"),
                raw_full=m.group(0),
            )
        )
    return blocks


def validate_balance(text: str) -> list[str]:
    """Return a list of validation errors (empty list if balanced)."""
    starts = [(m.group(1), m.start()) for m in _START_RE.finditer(text)]
    ends = [(m.group(1), m.start()) for m in _END_RE.finditer(text)]
    errors: list[str] = []
    if len(starts) != len(ends):
        errors.append(
            f"Marker count mismatch: {len(starts)} starts, {len(ends)} ends"
        )
    s_names = [n for n, _ in starts]
    e_names = [n for n, _ in ends]
    if sorted(s_names) != sorted(e_names):
        errors.append(
            f"Marker name mismatch: starts={s_names} ends={e_names}"
        )
    return errors


def update_block(text: str, name: str, new_content: str) -> str:
    """Replace an existing block's content. If absent, append at the end."""
    if not re.match(rf"^{NAME_PATTERN}$", name):
        raise MarkerError(f"Invalid marker name: {name!r}")

    new_content = new_content.rstrip("\n")
    replacement = (
        f"<!-- AUTO_GENERATED_START: {name} -->\n"
        f"{new_content}\n"
        f"<!-- AUTO_GENERATED_END: {name} -->"
    )

    block_re = re.compile(
        r"<!--\s*AUTO_GENERATED_START:\s*" + re.escape(name) + r"\s*-->\n"
        r".*?"
        r"\n<!--\s*AUTO_GENERATED_END:\s*" + re.escape(name) + r"\s*-->",
        re.DOTALL,
    )
    if block_re.search(text):
        return block_re.sub(replacement, text, count=1)

    # Append at end (with leading newline if needed)
    sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + replacement + "\n"


def strip_blocks(text: str) -> str:
    """Remove all AUTO_GENERATED blocks (delimiters included)."""
    return _BLOCK_RE.sub("", text)


def _main(argv: list[str]) -> int:
    import argparse
    import sys
    from pathlib import Path

    p = argparse.ArgumentParser()
    p.add_argument("file", type=Path)
    p.add_argument("--list", action="store_true")
    p.add_argument("--update", action="store_true")
    p.add_argument("--strip", action="store_true")
    p.add_argument("--validate", action="store_true")
    p.add_argument("--name")
    p.add_argument("--content")
    args = p.parse_args(argv[1:])

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 1
    text = args.file.read_text(encoding="utf-8").replace("\r\n", "\n")

    if args.list:
        blocks = extract_blocks(text)
        print(f"{len(blocks)} block(s):")
        for b in blocks:
            print(f"  - {b.name}: {len(b.content)} chars")
        return 0

    if args.validate:
        errs = validate_balance(text)
        if errs:
            for e in errs:
                print(f"❌ {e}")
            return 1
        print("✅ Balanced")
        return 0

    if args.update:
        if not args.name or args.content is None:
            print("Usage: --update --name <name> --content <text>", file=sys.stderr)
            return 1
        new_text = update_block(text, args.name, args.content)
        args.file.write_text(new_text, encoding="utf-8")
        print(f"Updated block '{args.name}' in {args.file}")
        return 0

    if args.strip:
        new_text = strip_blocks(text)
        args.file.write_text(new_text, encoding="utf-8")
        print(f"Stripped all blocks from {args.file}")
        return 0

    print("Specify one of: --list / --update / --strip / --validate", file=sys.stderr)
    return 1


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv))
```

### 3-2. `backend/tests/test_marker.py`

20+ パターン:

- extract: 0 ブロック / 1 ブロック / 複数ブロック
- update: 既存ブロック置換、存在しないブロック追加
- strip: 全削除、人間記述が保護される
- validate: balanced / 開始のみ / 終了のみ / 名前 mismatch
- nested を渡したら DOTALL で外側だけマッチすることを確認
- name に許可されない文字 (`@`, スペース) でエラー
- CRLF を渡した時の挙動

### 3-3. サンプルにマーカー区画を 1 つ追加

`examples/knowledge/01-rag-patterns.md` の本文末尾に:

```markdown
<!-- AUTO_GENERATED_START: summary -->
TBD: このセクションは自動生成プレースホルダ。実装後の build スクリプトで埋まる。
<!-- AUTO_GENERATED_END: summary -->
```

Day 11 段階では中身はプレースホルダ (Day 13 / v0.4 でビルド時 Claude 自動要約を生成、未来の自分への伏線)。

### 3-4. `docs/marker.md`

200 行程度。仕組み、再生成フロー、保護される範囲の境界を図解 (ASCII art)。

### 3-5. 動作確認

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"

# List
python -m backend.src.marker examples/knowledge/01-rag-patterns.md --list

# Update
python -m backend.src.marker examples/knowledge/01-rag-patterns.md \
  --update --name summary --content "RAG は検索と生成を組み合わせた手法。"

# Validate
python -m backend.src.marker examples/knowledge/01-rag-patterns.md --validate

# Strip (元に戻す前にバックアップ取ってから)
cp examples/knowledge/01-rag-patterns.md /tmp/backup.md
python -m backend.src.marker examples/knowledge/01-rag-patterns.md --strip
cp /tmp/backup.md examples/knowledge/01-rag-patterns.md  # 元に戻す

# Tests
python -m backend.tests.test_marker
```

### 3-6. コミット

1. `feat: implement marker.py for AUTO_GENERATED block handling`
2. `test: add marker tests (20+ cases)`
3. `docs: add demo AUTO_GENERATED block to sample knowledge`
4. `docs: add docs/marker.md`
5. `docs: changelog Day 11`

`git push origin main` (dev-b)

### 3-7. result_011.md

特に書くこと:

- 全 20+ テスト PASS ログ
- 実ファイルに対する `--list` / `--update` / `--validate` の出力
- nested マーカーを渡した時の挙動 (DOTALL で意図通り動くか)

## 4. 成功条件

- [ ] CLI 4 モード全て動作
- [ ] テスト全 PASS
- [ ] サンプル 01 にマーカー区画が入って integrity / search に影響していない
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_011.md`

## 6. 質問

- **マーカー区画は loader でどう扱うべきか**: 現状 `loader.py` は本文をそのまま `body` に入れる。マーカー区画も embedding 対象になる。これは「自動生成区画も検索ヒット対象にする」設計で OK か、それとも `strip_blocks` してから embed するか質問
- **ブロック名の命名規約**: `summary` `faq` `metadata` 等、推奨セットを `docs/marker.md` に書くか質問
- **複数の同名ブロック**: 1 ファイルに `summary` が 2 つあったらどう扱うか。今の実装は最初の 1 個だけ update、validate でエラーにしてもよいか質問

## 7. 補足

### 設計の意図

- **regex で実装、AST 不要**: Markdown の自由度を保つ。HTML コメント形式なので Markdown レンダラに無視される (GitHub 上で見ても綺麗)
- **`update_block` が存在しない場合は append**: 「最初に自動生成する」フローと「再生成する」フローを同じ呼び出しで扱える
- **`strip_blocks`**: AI 生成部分を取り除いて human-only 版を作るユースケース (PR レビューや diff 確認)

### Day 12 連携

Day 12 で pytest 化する際、`test_marker.py` も `assert` ベースから `pytest` に書き換える。マーカー機能自体は十分こなれている想定。
