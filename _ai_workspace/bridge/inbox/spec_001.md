# spec_001: Day 1 — プロジェクト初期化 + loader.py 実装

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: `docs/spec-v2.md` セクション 3, 4, 5, 6 (Day 1 行)

## 1. 目的

`axis-knowledge-rag` の Day 1 として、3週間プランの土台を構築する。

```
[現状]
- リポジトリ直下に README.md のみ
- バックエンドのコード、サンプル knowledge、Python パッケージ設定すべて未作成
- _ai_workspace/bridge/ と docs/spec-v2.md は既に配置済み

[変更後]
- バックエンドの最低限のディレクトリ構造が存在
- `pyproject.toml` / `requirements.txt` / `.env.example` が揃い、`pip install -e .` で開発インストール可能
- `backend/src/loader.py` が YAML frontmatter 付き Markdown を Document オブジェクトに読み込める
- `examples/knowledge/` に仕様書セクション 5.1 形式のサンプル Markdown 5本
- `python -m backend.src.loader ./examples/knowledge` で 5 件の Document が一覧表示される (Day 1 完了条件)
- v0.1.0 へ向けた Day 1 ぶんのコミットが dev-b アカウントで GitHub に push されている
```

Day 1 のゴールは「動くコアの最下層 = ナレッジ読み込み層」を確実に動かすこと。Day 2 (`embedder.py` + `vector_store.py`) がこの loader の出力に依存するので、ここで Document スキーマと例外処理を確定させる。

## 2. 制約

### 触ってよいファイル / 新規作成するもの

- `pyproject.toml` — 新規作成。プロジェクトメタデータ、依存、パッケージ宣言
- `requirements.txt` — 新規作成 (pyproject.toml と二重管理しない方針、requirements.txt は pip install しやすさのためのミラー)
- `.env.example` — 新規作成。`CLAUDE_API_KEY`、`GEMINI_API_KEY` のプレースホルダ
- `.gitignore` — 新規作成 (Python 標準 + `.env` + `.chromadb/` + Node 標準を先取り)
- `README.md` — Day 1 時点の概要に更新 (リポジトリ直下の既存ファイル、現状 1 行のみ)
- `LICENSE` — MIT で新規作成
- `backend/` 配下 — 仕様書セクション 3 の構成で **Day 1 時点のもののみ** 作成:
  - `backend/__init__.py` (空)
  - `backend/src/__init__.py` (空)
  - `backend/src/config.py` (env 読み込みの最小実装)
  - `backend/src/loader.py` ← 本 spec の主成果物
  - `backend/tests/__init__.py` (空)
  - `backend/tests/test_loader.py` (最低限の smoke test)
  - `backend/requirements.txt` (依存ライブラリ宣言)
- `examples/knowledge/01-rag-patterns.md` 〜 `05-prompt-engineering.md` — サンプル 5 本
- `config.yml` — 仕様書セクション 5.2 の軸定義ファイル (loader はまだ読み込まないが Day 3 で使うのでテンプレを置く)
- `CHANGELOG.md` — v0.1.0 の進捗を順次書く先頭ファイル

### 触ってはいけないもの

- `_ai_workspace/` 配下 — bridge 運用領域、CC は spec/result の読み書きのみ
- `docs/spec-v2.md` — 仕様書本体、変更不可 (Cowork 側でのみ更新する)
- `frontend/` — Week 3 の Next.js 移行で初めて触る
- `backend/src/embedder.py` / `vector_store.py` / `search.py` / `rag.py` / `api.py` — Day 2 以降の範囲
- `backend/src/normalizer.py` / `integrity.py` / `marker.py` — Week 2 の範囲

### コーディングルール

- Python 3.11 を前提 (`pyproject.toml` で `requires-python = ">=3.11"`)
- Type hints 必須 (Python の型注釈は `from __future__ import annotations` 不要、3.11 ネイティブで書く)
- docstring は Google style
- dataclass / Pydantic 不使用、シンプルに `@dataclass` で Document を定義 (Pydantic は API 層 = Day 4 以降で導入)
- 例外設計: ファイル読み込みエラーは握りつぶさず `loader.py` 専用の `LoaderError` を `raise`、ただしバッチ読み込み時は 1 ファイル失敗で全体停止しないよう **WARN ログ + skip** モードを提供
- ロガーは標準 `logging`、フォーマットは `[%(levelname)s] %(name)s: %(message)s`
- LangChain / LlamaIndex は **絶対に import しない** (差別化のキモなので)
- `pip install -e .` で開発インストール可能にする (`pyproject.toml` の `[project]` セクションで `name = "axis-knowledge-rag"`)
- ファイル末尾に空行 1 個、改行コード LF
- ruff 想定なので line-length 100、import 順は標準 → サードパーティ → ローカル

### 依存ライブラリ (今日入れるもののみ)

backend/requirements.txt:

```
python-frontmatter>=1.1.0
python-dotenv>=1.0.0
pyyaml>=6.0
```

pytest 系は **Week 1 では入れない**。Week 2 (Day 12) で CI と一緒に導入する。Day 1 の test_loader.py は `python -m backend.tests.test_loader` で動く形 (assert ベースの素の Python) で書く。

### デプロイ・コミット

- 全作業完了後、dev-b アカウントで `git push origin main`
- リモートは既に `https://github.com/kazikimaguro13/axis-knowledge-rag.git` を指している (clone 直後の状態)
- コミット粒度は仕様書セクション 10 に従い **1 コミット 30〜50 行を目安**、Day 1 で 3〜6 コミット
- コミットメッセージ prefix: `feat:` / `fix:` / `docs:` / `chore:` / `test:`
- Day 1 ではタグは打たない (v0.1.0 タグは Day 7 = 5/18)

## 3. やってほしいこと

### 3-1. プロジェクト基盤ファイル作成 (1 コミット目)

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "axis-knowledge-rag"
version = "0.1.0.dev0"
description = "Axis-based search + RAG over YAML frontmatter Markdown knowledge (Local-first OSS)"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
authors = [{ name = "Nakashima", email = "<your-email>" }]
keywords = ["rag", "vector-search", "markdown", "knowledge-base", "local-first"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Programming Language :: Python :: 3.11",
  "License :: OSI Approved :: MIT License",
  "Operating System :: OS Independent",
]
dependencies = [
  "python-frontmatter>=1.1.0",
  "python-dotenv>=1.0.0",
  "pyyaml>=6.0",
]

[project.urls]
Homepage = "https://github.com/kazikimaguro13/axis-knowledge-rag"
Repository = "https://github.com/kazikimaguro13/axis-knowledge-rag"

[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

`.env.example`:

```
# === LLM Providers ===
ANTHROPIC_API_KEY=sk-ant-xxxxx
GEMINI_API_KEY=AIzaSyxxxxx

# === Storage ===
CHROMA_DB_PATH=./.chromadb

# === Logging ===
LOG_LEVEL=INFO
```

`.gitignore` (Python + Node 標準を先取り、`.env`、`.chromadb/`、`__pycache__/`、`*.egg-info/`、`node_modules/`、`.next/` を含める)

`LICENSE`: 標準 MIT (Year: 2026, Author: Nakashima)

`config.yml`: 仕様書セクション 5.2 の通り

`CHANGELOG.md`:

```markdown
# Changelog

## [Unreleased]

### Day 1 (2026-05-12)
- Initial project structure
- backend/src/loader.py: Markdown + YAML frontmatter loader
- 5 sample knowledge documents under examples/knowledge/
```

`README.md` (Day 1 版、後の Day で順次拡充):

```markdown
# axis-knowledge-rag

YAML frontmatter 付き Markdown ナレッジに対する、軸検索 + RAG 検索のローカル Web アプリ OSS。

## ステータス

🚧 開発中 (v0.1.0 リリース予定: 2026-05-18)

## 特徴 (3 週間で実装予定)

- **軸メタデータでの構造化検索 + ベクトル検索のハイブリッド**
- 日本語ナレッジ特化 (表記ゆれ吸収予定)
- LangChain / LlamaIndex 不使用、自前実装
- Local-first 設計 (個人データを外部送信しない)

## ロードマップ

| バージョン | 目標日 | 内容 |
| --- | --- | --- |
| v0.1.0 | 2026-05-18 | コア MVP (Streamlit) |
| v0.2.0 | 2026-05-25 | 差別化機能 (表記ゆれ / 参照整合性 / マーカー方式) |
| v0.3.0 | 2026-06-01 | Next.js + FastAPI 移行、UI/UX 最終形 |

詳細仕様: `docs/spec-v2.md`
```

このコミットで `feat: initial project skeleton (pyproject, license, readme, gitignore)` 相当。

### 3-2. backend/src/config.py + ディレクトリ骨格 (1 コミット目に含める or 2 コミット目)

`backend/__init__.py` 空ファイル
`backend/src/__init__.py` 空ファイル
`backend/tests/__init__.py` 空ファイル
`backend/requirements.txt`:

```
python-frontmatter>=1.1.0
python-dotenv>=1.0.0
pyyaml>=6.0
```

`backend/src/config.py`:

```python
"""Project-wide configuration loaded from environment / .env."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime settings.

    Values are sourced from environment variables (or .env if present).
    """

    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    chroma_db_path: Path = Path(os.getenv("CHROMA_DB_PATH", "./.chromadb"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


def configure_logging(level: str | None = None) -> None:
    """Configure root logger with project-standard format."""
    logging.basicConfig(
        level=level or Settings().log_level,
        format="[%(levelname)s] %(name)s: %(message)s",
    )


settings = Settings()
```

### 3-3. backend/src/loader.py (本 spec の主成果物)

仕様書セクション 5.1 の Markdown フォーマットを読み込み、Document データクラスへ。

```python
"""Markdown + YAML frontmatter loader.

仕様書 docs/spec-v2.md セクション 5.1 のフォーマットを読み込んで
Document オブジェクトに変換する。Day 1 の主成果物。
"""

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter

logger = logging.getLogger(__name__)


class LoaderError(Exception):
    """Raised when a Markdown document fails to load."""


@dataclass
class Document:
    """A loaded knowledge document.

    Attributes:
        id: Unique identifier from frontmatter `id` field.
        title: Human-readable title.
        axes: Structured axis values (category, topic, level, author, year, ...).
        tags: Free-form tags.
        refs: IDs of referenced documents.
        body: The Markdown body (without frontmatter).
        path: Source file path on disk.
        raw_meta: Full frontmatter dict for debugging / extension.
    """

    id: str
    title: str
    axes: dict[str, Any]
    tags: list[str]
    refs: list[str]
    body: str
    path: Path
    raw_meta: dict[str, Any] = field(default_factory=dict)


def load_document(path: Path) -> Document:
    """Load a single Markdown file with YAML frontmatter."""
    if not path.exists():
        raise LoaderError(f"File not found: {path}")
    if not path.is_file():
        raise LoaderError(f"Not a file: {path}")

    try:
        post = frontmatter.load(path)
    except Exception as e:
        raise LoaderError(f"Failed to parse frontmatter for {path}: {e}") from e

    meta = post.metadata
    if "id" not in meta:
        raise LoaderError(f"Missing required 'id' field in {path}")
    if "title" not in meta:
        raise LoaderError(f"Missing required 'title' field in {path}")

    return Document(
        id=str(meta["id"]),
        title=str(meta["title"]),
        axes=dict(meta.get("axes", {})),
        tags=list(meta.get("tags", [])),
        refs=list(meta.get("refs", [])),
        body=post.content,
        path=path,
        raw_meta=dict(meta),
    )


def load_directory(
    dir_path: Path, *, pattern: str = "*.md", strict: bool = False
) -> list[Document]:
    """Load all Markdown files under a directory (non-recursive by default).

    Args:
        dir_path: Directory containing Markdown knowledge files.
        pattern: Glob pattern; pass `**/*.md` for recursive.
        strict: If True, raise on first failure. If False (default), skip
                failed files with a WARN log so a single broken file doesn't
                break the batch.

    Returns:
        List of successfully loaded Documents.
    """
    if not dir_path.exists():
        raise LoaderError(f"Directory not found: {dir_path}")
    if not dir_path.is_dir():
        raise LoaderError(f"Not a directory: {dir_path}")

    docs: list[Document] = []
    files = sorted(dir_path.glob(pattern))
    if not files:
        logger.warning("No Markdown files matched %s in %s", pattern, dir_path)
        return docs

    for f in files:
        try:
            docs.append(load_document(f))
        except LoaderError as e:
            if strict:
                raise
            logger.warning("Skipping %s: %s", f, e)

    logger.info("Loaded %d/%d documents from %s", len(docs), len(files), dir_path)
    return docs


def _main(argv: list[str]) -> int:
    """CLI entrypoint: `python -m backend.src.loader <dir>`."""
    from backend.src.config import configure_logging

    configure_logging()

    if len(argv) < 2:
        print("Usage: python -m backend.src.loader <directory>", file=sys.stderr)
        return 1

    target = Path(argv[1])
    docs = load_directory(target, pattern="*.md")

    print(f"\n=== Loaded {len(docs)} documents from {target} ===\n")
    for d in docs:
        print(f"- [{d.id}] {d.title}")
        print(f"    axes: {d.axes}")
        print(f"    tags: {d.tags}  refs: {d.refs}")
        print(f"    body: {len(d.body)} chars\n")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
```

### 3-4. backend/tests/test_loader.py (pytest 抜き、assert ベース)

```python
"""Smoke tests for loader. Run via: python -m backend.tests.test_loader"""

import sys
import tempfile
from pathlib import Path

from backend.src.loader import LoaderError, load_directory, load_document


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_load_minimal_document() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.md"
        _write(
            p,
            """---
id: t1
title: Test 1
axes:
  category: 技術記事
tags: [a, b]
refs: []
---

Body text.
""",
        )
        doc = load_document(p)
        assert doc.id == "t1"
        assert doc.title == "Test 1"
        assert doc.axes == {"category": "技術記事"}
        assert doc.tags == ["a", "b"]
        assert "Body text." in doc.body


def test_missing_id_raises() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "bad.md"
        _write(p, "---\ntitle: no id\n---\nbody\n")
        try:
            load_document(p)
        except LoaderError:
            return
        raise AssertionError("LoaderError not raised")


def test_load_directory_skips_bad_files() -> None:
    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "good.md"
        bad = Path(td) / "bad.md"
        _write(good, "---\nid: g\ntitle: Good\n---\nok\n")
        _write(bad, "---\ntitle: no id\n---\nbody\n")
        docs = load_directory(Path(td))
        assert len(docs) == 1
        assert docs[0].id == "g"


def test_strict_mode_raises_on_bad_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        _write(Path(td) / "bad.md", "---\ntitle: no id\n---\nbody\n")
        try:
            load_directory(Path(td), strict=True)
        except LoaderError:
            return
        raise AssertionError("LoaderError not raised in strict mode")


if __name__ == "__main__":
    tests = [
        test_load_minimal_document,
        test_missing_id_raises,
        test_load_directory_skips_bad_files,
        test_strict_mode_raises_on_bad_file,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    sys.exit(1 if failed else 0)
```

### 3-5. examples/knowledge/ サンプル 5 本

仕様書セクション 5.1 のフォーマットで、**互いに `refs` で軽くリンクされた** 5 本。Day 3 の参照整合性チェック (Week 2) を見据えて、`doc_001 → doc_002` のような有効リンクと、わざと `doc_999` への壊れリンクを 1 本だけ仕込む (Week 2 で検出されるネタとして)。

ファイル名と中身の方針:

- `01-rag-patterns.md` (id: doc_001, category: 技術記事, topic: RAG, level: 中級)
- `02-vector-search.md` (id: doc_002, category: 技術記事, topic: ベクトル検索, level: 中級, refs: [doc_001])
- `03-yaml-frontmatter.md` (id: doc_003, category: メモ, topic: メタデータ設計, level: 初級)
- `04-claude-skills.md` (id: doc_004, category: 技術記事, topic: Claude, level: 中級, refs: [doc_001, doc_003])
- `05-prompt-engineering.md` (id: doc_005, category: 技術記事, topic: プロンプト, level: 上級, refs: [doc_999])  ← わざと壊れリンク

各ファイル本文は 300〜500 字程度の、それっぽい技術メモ。著作権リスクのある引用はせず、一般論を平易に。

### 3-6. 動作確認

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"

# 依存インストール
python -m pip install -e .

# loader CLI 実行 (Day 1 完了条件)
python -m backend.src.loader ./examples/knowledge

# 期待: 5 件の Document が一覧表示される

# テスト実行
python -m backend.tests.test_loader

# 期待: PASS が 4 件、FAIL/ERROR 0 件
```

### 3-7. コミット + Push (dev-b アカウントで)

コミット粒度の目安 (3〜6 コミット):

1. `feat: initial project skeleton (pyproject, license, readme, gitignore, changelog)`
2. `feat: add backend package layout and config.py`
3. `feat: implement Markdown + YAML frontmatter loader (loader.py)`
4. `test: add smoke tests for loader (assert-based, no pytest yet)`
5. `docs: add 5 sample knowledge documents under examples/knowledge`
6. `chore: pin loader-stage dependencies in backend/requirements.txt`

最後に:

```bash
git push origin main
```

push 時の GitHub 認証が **`kazikimaguro13` で通る** ことを確認すること。違うアカウントで通るようなら、コミットせず `result_001.md` の Open questions に書いて停止 (重要、間違ったアカウントで push したくない)。

### 3-8. 結果を `outbox/result_001.md` に書く

`_ai_workspace/bridge/templates/result_template.md` の構造で:

- 作成したファイル一覧 (相対パス、行数)
- 実行したコマンドとその出力 (loader CLI、test) 全文
- 失敗 / skip した部分があれば理由
- 設計判断ポイント (例: dataclass vs Pydantic を分けた理由、strict 引数の意図)
- 次の spec (Day 2) で気をつけたほうがいいこと、loader の API で変えたほうがよさそうな点

## 4. 成功条件

- [ ] `python -m backend.src.loader ./examples/knowledge` が 5 件の Document を表示
- [ ] `python -m backend.tests.test_loader` が 4 件 PASS / 0 件 FAIL
- [ ] LangChain / LlamaIndex を import していない (grep で確認)
- [ ] `pip install -e .` が成功する
- [ ] dev-b アカウント (`kazikimaguro13`) で `git push origin main` 成功
- [ ] コミット履歴が 3〜6 コミット、prefix 規約に従っている
- [ ] `result_001.md` が outbox に書かれている

## 5. 出力先

`C:\Users\cocor\Desktop\就活\axis-knowledge-rag\_ai_workspace\bridge\outbox\result_001.md`

## 6. 質問があるとき

迷ったら作業を停止して `outbox/result_001.md` の Open questions に書き、status を `blocked` にして終了。

特に判断が割れそうなところ:

- **GitHub 認証アカウント**: push 時に dev-b 用の `kazikimaguro13` 以外で通ろうとした場合は **必ず停止** して質問する (誤アカウント push は致命的)
- **依存ライブラリのバージョン**: 上限指定なしで pip resolve 失敗するなら、安定バージョンに pin して理由を report に書く
- **サンプル本文の内容**: 5 本のサンプル本文は技術一般論で OK だが、もし「サムライ施策で得た知見をベースにしたい」など固有要素を入れるべきか迷ったら、汎用論で書いて outbox に提案だけ書く

## 7. 補足

### 設計の意図

- **dataclass を選んだ理由**: Pydantic を Day 1 で入れると依存が増え、Streamlit/FastAPI 移行までの間 over-engineering になる。標準ライブラリ縛りの方が「自前実装」アピールにもなる。API 層 (Day 4) で Pydantic を導入する
- **strict=False をデフォルトに**: ナレッジは数十〜数百本になり、1 ファイル壊れで全停止すると運用つらい。バッチでは WARN + skip、単一読み込みでは raise が直感的
- **`pattern="*.md"` のデフォルトを非再帰に**: ユーザーが意図せず `node_modules/**/*.md` を拾うリスクを排除。recursive にしたい人は明示的に `**/*.md` を渡す
- **`__main__` を `_main(argv)` に分離**: テストから呼びやすくする (Day 2 以降で必要になる可能性)

### 将来の拡張余地

- **spec_002 候補 (Day 2)**: `embedder.py` (Gemini text-embedding-004) + `vector_store.py` (ChromaDB)、`scripts/build_index.py` でサンプル 5 本をインデックス化
- **spec_003 候補 (Day 3)**: `search.py` (軸フィルタ + ベクトル類似度ハイブリッド)、CLI 検索
- loader の API は Day 2 以降で「`load_directory` の戻り値を pickle にキャッシュする」拡張が来るかもしれないので、Document を dataclass にしておけば自動で対応可能
