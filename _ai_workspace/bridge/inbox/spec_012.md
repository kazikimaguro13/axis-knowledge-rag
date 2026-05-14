# spec_012: Day 12 — pytest 化 + GitHub Actions CI

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜011, `docs/spec-v2.md` Day 12 行

## 1. 目的

```
[現状]
- テストはすべて assert ベース、`python -m backend.tests.test_<name>` 個別実行
- CI なし、push してもテストが自動実行されない
- coverage 計測なし
- 「業務級品質」を OSS でアピールするにはここを整える必要

[変更後]
- pytest 導入、全 test_*.py を pytest スタイルに統一
- `pyproject.toml` に `[tool.pytest.ini_options]` で testpaths と addopts を定義
- `ruff check .` を CI に組み込む (line-length=100、target=py311)
- `.github/workflows/ci.yml` で push / PR 時に pytest + ruff を自動実行
- coverage 70%+ を確認 (pytest-cov)
```

履歴書に書ける「CI / テストカバレッジ」のアピールを成立させる Day。

## 2. 制約

### 触ってよいファイル

- 全 `backend/tests/test_*.py` — pytest 形式に書き換え
- `pyproject.toml` — pytest, pytest-cov, ruff を `[project.optional-dependencies]` の `dev` に追加
- `.github/workflows/ci.yml` — 新規
- `.github/workflows/docker.yml` — 新規 (Docker build がパスすることを確認)
- `pytest.ini` — 不要 (pyproject に統合)
- `CHANGELOG.md`

### 触ってはいけないもの

- ソース本体 (`backend/src/*.py`) — テストの書き換えで挙動を変えない
- 既存依存 (`backend/requirements.txt`) は本番依存のみ、dev 依存は別管理
- `_ai_workspace/`、`docs/spec-v2.md`

### コーディングルール

- pytest fixture を活用 (in_memory store、DUMMY embedder を `conftest.py` で共有)
- パラメタライズテスト (`pytest.mark.parametrize`) で normalizer / marker のケースを集約
- coverage 計測対象は `backend.src` パッケージのみ (scripts, tests は除外)
- CI は ubuntu-latest + Python 3.11 / 3.12 のマトリックス

## 3. やってほしいこと

### 3-1. dev 依存追加 (`pyproject.toml`)

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.5.0",
]

[tool.pytest.ini_options]
testpaths = ["backend/tests"]
addopts = "-ra -q --strict-markers"
filterwarnings = [
    "ignore::DeprecationWarning",
]

[tool.coverage.run]
source = ["backend/src"]
omit = ["backend/src/__init__.py"]

[tool.coverage.report]
exclude_lines = [
    "if __name__ == .__main__.:",
    "raise NotImplementedError",
]
```

### 3-2. `backend/tests/conftest.py` 新規

```python
"""Shared fixtures for the test suite."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.src.embedder import Embedder
from backend.src.loader import Document
from backend.src.normalizer import Normalizer
from backend.src.search import SearchEngine
from backend.src.vector_store import VectorStore


@pytest.fixture
def dummy_embedder() -> Embedder:
    return Embedder(force_dummy=True)


@pytest.fixture
def in_memory_store() -> Iterator[VectorStore]:
    store = VectorStore(in_memory=True)
    yield store


@pytest.fixture
def normalizer() -> Normalizer:
    return Normalizer()


@pytest.fixture
def search_engine(
    in_memory_store: VectorStore, dummy_embedder: Embedder, normalizer: Normalizer
) -> SearchEngine:
    return SearchEngine(in_memory_store, dummy_embedder, normalizer)


@pytest.fixture
def sample_documents() -> list[Document]:
    return [
        Document(
            id=f"doc_{i:03d}",
            title=f"Title {i}",
            axes={"category": "技術記事", "level": "中級"},
            tags=["a"],
            refs=[],
            body=f"Body content for document {i}.",
            path=Path(f"/tmp/doc_{i}.md"),
            normalized_title=f"title {i}",
            normalized_body=f"body content for document {i}.",
            normalized_axes={"category": "技術記事", "level": "中級"},
            normalized_tags=["a"],
        )
        for i in range(1, 6)
    ]
```

### 3-3. 既存テストを pytest 形式へ

例 `test_normalizer.py`:

```python
import pytest

from backend.src.normalizer import (
    Normalizer,
    NormalizerOptions,
    normalize_text,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ＲＡＧ", "rag"),
        ("ＡＢＣ", "abc"),
        ("ラグ", "らぐ"),
        ("RAG", "rag"),
        ("Claude API", "claude api"),
        ("漢字", "漢字"),
        ("", ""),
        ("Hello　World", "hello world"),
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_idempotent() -> None:
    s = "ＲＡＧとカタカナ"
    assert normalize_text(normalize_text(s)) == normalize_text(s)


def test_options_disable_katakana() -> None:
    opts = NormalizerOptions(katakana_to_hiragana=False)
    assert normalize_text("ラグ", opts) == "ラグ"


def test_normalizer_class() -> None:
    n = Normalizer()
    assert n("ＲＡＧ") == "rag"
```

他 (`test_loader.py`, `test_embedder.py`, `test_vector_store.py`, `test_search.py`, `test_rag.py`, `test_integrity.py`, `test_marker.py`) も同様に書き換え。fixture を活用してボイラープレート削減。

### 3-4. `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: "pip"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Lint with ruff
        run: ruff check .

      - name: Run tests with coverage
        run: pytest --cov=backend/src --cov-report=term-missing --cov-fail-under=70

      - name: Upload coverage HTML
        if: matrix.python-version == '3.12'
        run: pytest --cov=backend/src --cov-report=html
        continue-on-error: true
```

### 3-5. `.github/workflows/docker.yml`

```yaml
name: Docker Build

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Build
        uses: docker/build-push-action@v6
        with:
          context: .
          push: false
          tags: axis-knowledge-rag:ci
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### 3-6. ruff 設定の最終化

既存 `pyproject.toml` の `[tool.ruff]` に lint rules 追加:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP", "B", "SIM"]
ignore = [
    "E501",  # line too long (covered by line-length, leaving as warning if exceeded)
]

[tool.ruff.lint.per-file-ignores]
"backend/tests/*" = ["E501"]
```

ローカルで `ruff check . --fix` を実行して既存 source の lint 違反を修正、別コミットで集約。

### 3-7. 動作確認

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"
pip install -e ".[dev]"

ruff check .
# 期待: All checks passed

pytest -v
# 期待: 全テスト PASS、coverage 70%+

pytest --cov=backend/src --cov-report=term-missing
# 期待: coverage report が表示、70%+
```

push 後に GitHub Actions が走ることを Actions タブで確認。

### 3-8. コミット

1. `chore: add pytest, pytest-cov, ruff to dev dependencies`
2. `refactor: convert test_loader to pytest style`
3. `refactor: convert test_normalizer to pytest with parametrize`
4. `refactor: convert remaining tests to pytest`
5. `chore: add conftest.py with shared fixtures`
6. `style: ruff auto-fix across backend/`
7. `ci: add GitHub Actions workflow (test + lint, matrix py311/py312)`
8. `ci: add Docker build workflow`
9. `docs: changelog Day 12`

`git push origin main` (dev-b)

### 3-9. result_012.md

特に書くこと:

- `pytest -v` の全テストパス一覧
- coverage report の数字 (% per module)
- ruff check で修正した違反の件数
- GitHub Actions のリンク (workflow 実行成功 / 失敗)

## 4. 成功条件

- [ ] `pip install -e ".[dev]"` 成功
- [ ] `pytest` で全テスト PASS
- [ ] coverage 70%+
- [ ] `ruff check .` で 0 violation
- [ ] `.github/workflows/ci.yml` がプッシュ後に成功 (CC は push してから 1〜2 分待って Actions 確認、できなければ result に書く)
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_012.md`

## 6. 質問

- **Python バージョンマトリックス**: 3.11 / 3.12 で OK か、3.13 も入れるか。最新の 3.13 は chromadb / google-generativeai が未対応の可能性、まず 3.11/3.12 でスタート
- **coverage 閾値**: 70% は仕様書通り。Week 1 のコード量だと 80%+ 行きそうだが、初期は緩めに設定
- **`cov-fail-under` の運用**: 数値以下で CI 落とすかは判断割れる。とりあえず `--cov-fail-under=70` 入れて、後で緩めるならコメントアウト
- **secret 管理**: API キーをテストで使わない (DUMMY モードのみ) ので、Actions に secret 設定不要

## 7. 補足

### 設計の意図

- **pytest と ruff のみ**: black, isort, mypy は Phase 2。Week 2 では「動く CI が GitHub バッジに出る」ことが目的
- **`[dev]` extras に分離**: 本番依存と開発依存を別管理 (Docker build には dev を入れない)
- **fixture 集約**: search / rag のテストで同じ setup を何度も書かないように

### Day 13 連携

Day 13 では `docs/architecture.md` で CI / テスト戦略について書く。Day 12 で確立した運用を文章化する。
