# spec_023: AI ingester (`backend/src/ingester.py`) — メモ → YAML 自動変換

- **Author**: Cowork (中島)
- **Created**: 2026-05-13
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: spec_001〜022 (rag.py / config.yml / normalizer.py / loader.py / mcp_server を再利用)

## 1. 目的

```
[現状]
- 既存メモ (Slack 抜粋 / 議事録 / Apple Notes / Markdown without frontmatter) を
  axis-knowledge-rag が読める形に変換するには **手動で YAML frontmatter を書く**必要がある
- 既存メモ資産を取り込むハードルが高い (1 ファイル 30 秒〜2 分かかる)
- 個人 OSS のユーザビリティ上の最後のボトルネック

[変更後]
- `backend/src/ingester.py` が Claude API で「raw text → YAML frontmatter 付き Markdown」変換を提供
- 単発 CLI: `python -m scripts.yamlize <input.txt>` → stdout に整形済み Markdown
- バッチ CLI: `python -m scripts.yamlize_dir <input_dir>/ --output <output_dir>/`
- MCP tool: `axis_ingest_memo(text)` を mcp_server に追加 (Claude Desktop からも呼べる)
- 軸推測の制約: `config.yml` の axes 定義を Claude に渡し、enum 軸は許可値しか出させない
- DUMMY モード対応 (ANTHROPIC_API_KEY 不要、決定論的に mock YAML を返す)
```

差別化機能 #4 を追加。"RAG ツールに **検索 + 生成 + ingestion** の AI 統合" を一つの OSS にまとめる、AI ネイティブなナレッジマネジメントツールを完成させる。

## 2. 制約

### 触ってよいファイル / 新規作成

- `backend/src/ingester.py` — 新規。core logic
- `backend/src/ingester_schemas.py` — 新規 (Pydantic: IngestRequest / IngestResult)
- `backend/tests/test_ingester.py` — 新規 (DUMMY mode + sample)
- `scripts/yamlize.py` — 新規。単発変換 CLI
- `scripts/yamlize_dir.py` — 新規。バッチ変換 CLI
- `examples/raw_memos/sample_memo_01.txt` 〜 `03.txt` — 新規。デモ用入力サンプル 3 本
- `docs/ingester.md` — 新規。設計と使用例
- `mcp_server/server.py` — `axis_ingest_memo` tool 追加
- `mcp_server/schemas.py` — `IngestInput` 追加
- `mcp_server/tests/test_server.py` — `axis_ingest_memo` の DUMMY test 追加
- `CHANGELOG.md` — Day 23

### 触ってはいけないもの

- 既存の loader / search / rag / normalizer / integrity の **API**
- `frontend/` — 関係なし
- `_ai_workspace/`、`docs/spec-v2.md`

### コーディングルール

- Python 3.11+、既存 codebase の規約踏襲
- Pydantic v2 で AI レスポンスをパース (`IngestResult` schema)
- Claude API は `rag.py` と同じ `Anthropic` クライアントを使用
- DUMMY モード: `ANTHROPIC_API_KEY` 未設定 → 決定論的 mock を返す
- 軸推測の制約 strict: enum 軸は許可値のみ、整数軸は範囲チェック
- LangChain / LlamaIndex 禁止
- ruff + pytest 規約準拠

### 依存追加: なし

`rag.py` で既に `anthropic` 入っているので追加不要。

## 3. やってほしいこと

### 3-1. `backend/src/ingester_schemas.py`

```python
"""Pydantic schemas for the ingester (memo → YAML)."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngestResult(BaseModel):
    """The structured response we ask Claude to produce."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(..., description="Unique doc id, e.g. 'doc_011'", pattern=r'^doc_\d{3,}$')
    title: str = Field(..., min_length=3, max_length=200)
    axes: dict[str, str | int] = Field(..., description="Filled axis values")
    tags: list[str] = Field(default_factory=list, max_length=10)
    refs: list[str] = Field(default_factory=list)
    body: str = Field(..., min_length=20)

    @field_validator("refs")
    @classmethod
    def _refs_format(cls, v: list[str]) -> list[str]:
        for r in v:
            if not r.startswith("doc_"):
                raise ValueError(f"Invalid ref id: {r}")
        return v


class IngestOptions(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    knowledge_dir: str = Field(
        default="./examples/knowledge",
        description="Existing knowledge dir to derive next id and validate refs against.",
    )
    suggested_category: Optional[str] = Field(
        default=None, description="Hint to bias Claude's category choice."
    )
    max_tokens: int = Field(default=1500, ge=512, le=4096)
```

### 3-2. `backend/src/ingester.py`

```python
"""AI-powered ingester: raw text → axis-knowledge-rag YAML frontmatter Markdown.

Reuses the Claude API client pattern from rag.py. DUMMY mode (no API key)
returns a deterministic mock for offline development and CI.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from backend.src.config import load_axes_config, settings
from backend.src.ingester_schemas import IngestOptions, IngestResult
from backend.src.loader import load_directory

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")


_SYSTEM_PROMPT = """\
あなたは axis-knowledge-rag のナレッジエディタです。
ユーザーが渡す raw text を、以下の YAML frontmatter 付き Markdown 構造に変換してください。

出力は必ず以下の JSON 形式 (説明文や ``` などのコードフェンス無しで):
{
  "id": "doc_NNN",
  "title": "...",
  "axes": {<axis_name>: <value>, ...},
  "tags": [...],
  "refs": [],
  "body": "..."
}

ルール:
1. id は 与えられた 'next_id' を使う
2. title は本文要約 3〜200 文字、絵文字なし
3. axes は与えられた axes_constraints に厳密従う:
   - type='enum' の軸は values のいずれか必須
   - type='string' は短く (50字以内)
   - type='integer' は 範囲内
   - required=true の軸は必ず埋める、required=false は推測できるなら埋め、無理なら省略
4. tags: 2〜5 個、snake_case、英小文字推奨だが日本語可
5. refs: 与えられた existing_doc_ids の範囲内でのみ参照。推測しない場合は []
6. body は raw text を整形した本文。情報を勝手に削らず、ただ markdown として整える。

軸が不明確な場合は最も近い enum 値を選び、メタフィールド notes (内部用) に短いコメントを残しても良い。
"""


def _next_doc_id(knowledge_dir: Path) -> str:
    """Read existing knowledge dir, return 'doc_NNN' where NNN = max+1."""
    if not knowledge_dir.exists():
        return "doc_001"
    docs = load_directory(knowledge_dir)
    numbers = []
    for d in docs:
        # extract NNN from id like doc_011
        if d.id.startswith("doc_"):
            try:
                numbers.append(int(d.id[4:]))
            except ValueError:
                pass
    nxt = (max(numbers) + 1) if numbers else 1
    return f"doc_{nxt:03d}"


def _existing_doc_ids(knowledge_dir: Path) -> list[str]:
    if not knowledge_dir.exists():
        return []
    return [d.id for d in load_directory(knowledge_dir)]


def _dummy_result(raw_text: str, next_id: str) -> IngestResult:
    """Deterministic mock for DUMMY mode tests."""
    h = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:8]
    return IngestResult(
        id=next_id,
        title=f"[DUMMY] Auto-generated from raw text ({h})",
        axes={"category": "メモ", "topic": "未分類"},
        tags=["dummy", "auto"],
        refs=[],
        body=f"<!-- DUMMY mode: ingested without Claude API -->\n\n{raw_text.strip()}",
    )


class Ingester:
    """Convert raw text into a structured IngestResult via Claude API."""

    def __init__(self, *, force_dummy: bool = False, model: str = DEFAULT_MODEL):
        self._model = model
        self._use_dummy = force_dummy or not settings.anthropic_api_key
        if self._use_dummy:
            logger.warning("Ingester running in DUMMY mode (no ANTHROPIC_API_KEY)")
            self._client = None
        else:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=settings.anthropic_api_key)

    @property
    def is_dummy(self) -> bool:
        return self._use_dummy

    def ingest(self, raw_text: str, options: Optional[IngestOptions] = None) -> IngestResult:
        opts = options or IngestOptions()
        knowledge_dir = Path(opts.knowledge_dir)
        next_id = _next_doc_id(knowledge_dir)

        if self._use_dummy:
            return _dummy_result(raw_text, next_id)

        existing_ids = _existing_doc_ids(knowledge_dir)
        axes_cfg = load_axes_config()
        constraints = axes_cfg.get("axes", [])

        user_msg = (
            f"# next_id\n{next_id}\n\n"
            f"# existing_doc_ids\n{existing_ids}\n\n"
            f"# axes_constraints\n{json.dumps(constraints, ensure_ascii=False, indent=2)}\n\n"
            + (f"# suggested_category\n{opts.suggested_category}\n\n" if opts.suggested_category else "")
            + f"# raw_text\n{raw_text}\n"
        )

        resp = self._client.messages.create(
            model=self._model,
            max_tokens=opts.max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw_json = "".join(b.text for b in resp.content if hasattr(b, "text"))
        # tolerate fences if Claude slips
        if raw_json.strip().startswith("```"):
            raw_json = raw_json.strip().strip("`")
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
            raw_json = raw_json.strip()

        try:
            data = json.loads(raw_json)
            return IngestResult(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            raise RuntimeError(f"Claude returned invalid JSON: {e}\nRaw: {raw_json[:500]}") from e


def render_markdown(result: IngestResult) -> str:
    """Render an IngestResult as a YAML-frontmatter Markdown document."""
    fm = {
        "id": result.id,
        "title": result.title,
        "axes": result.axes,
        "tags": result.tags,
        "refs": result.refs,
    }
    yaml_block = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
    return f"---\n{yaml_block}---\n\n{result.body}\n"
```

### 3-3. `scripts/yamlize.py`

```python
"""CLI: convert a single raw text file to YAML-frontmatter Markdown.

Usage:
    python -m scripts.yamlize input.txt
    python -m scripts.yamlize input.txt --output examples/knowledge/doc_011.md
    python -m scripts.yamlize input.txt --suggested-category 議事録
    cat memo.txt | python -m scripts.yamlize -
"""

import argparse
import sys
from pathlib import Path

from backend.src.config import configure_logging
from backend.src.ingester import Ingester, render_markdown
from backend.src.ingester_schemas import IngestOptions


def main(argv: list[str]) -> int:
    configure_logging()
    p = argparse.ArgumentParser()
    p.add_argument("input", help="Path to raw text file, or '-' for stdin")
    p.add_argument("--output", "-o", help="Output Markdown file path. Default: stdout")
    p.add_argument("--knowledge-dir", default="./examples/knowledge")
    p.add_argument("--suggested-category", default=None)
    p.add_argument("--max-tokens", type=int, default=1500)
    args = p.parse_args(argv[1:])

    if args.input == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(args.input).read_text(encoding="utf-8")

    opts = IngestOptions(
        knowledge_dir=args.knowledge_dir,
        suggested_category=args.suggested_category,
        max_tokens=args.max_tokens,
    )
    ingester = Ingester()
    result = ingester.ingest(raw, opts)
    md = render_markdown(result)

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"[ok] wrote {args.output} (id={result.id}, title={result.title!r})", file=sys.stderr)
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

### 3-4. `scripts/yamlize_dir.py`

`scripts/yamlize.py` のバッチ版。`input_dir/*.txt` を読んで `output_dir/<next_id>-<slug>.md` に書き出す。複数ファイル処理中の id 衝突を防ぐため、各ファイル処理後に knowledge_dir を再スキャンするか、in-memory counter で連番増やす。

### 3-5. `examples/raw_memos/sample_memo_0[1-3].txt`

3 種のサンプル:

- `sample_memo_01.txt` — Slack コピペ風 (LLM 評価指標について)
- `sample_memo_02.txt` — 議事録風 (MTG メモ)
- `sample_memo_03.txt` — 自己ノート風 (短いアイデアメモ)

### 3-6. `backend/tests/test_ingester.py`

pytest:

- `test_dummy_mode_produces_valid_result` — DUMMY 強制 → IngestResult が valid
- `test_render_markdown_round_trip` — DUMMY result を render → frontmatter.load() で再 parse
- `test_next_doc_id_increments` — 既存 doc_010 まである dir で next_id == "doc_011"
- `test_next_doc_id_empty_dir` — 空 dir で next_id == "doc_001"

### 3-7. MCP tool `axis_ingest_memo`

`mcp_server/schemas.py` に `IngestInput`:
```python
class IngestInput(_BaseInput):
    raw_text: str = Field(..., min_length=20, max_length=10000)
    knowledge_dir: str = Field(default="./examples/knowledge")
    suggested_category: Optional[str] = None
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)
```

`mcp_server/server.py` に tool 追加:
```python
@mcp.tool(
    name="axis_ingest_memo",
    annotations={
        "title": "Convert raw memo to YAML-frontmatter Markdown",
        "readOnlyHint": True,  # Does not modify files; just returns the converted content
        "destructiveHint": False,
        "idempotentHint": False,  # Claude API is nondeterministic
        "openWorldHint": True,  # Calls Anthropic API
    },
)
async def axis_ingest_memo(params: IngestInput) -> str:
    """Convert a raw memo text into axis-knowledge-rag YAML frontmatter Markdown."""
    from backend.src.ingester import Ingester, render_markdown
    from backend.src.ingester_schemas import IngestOptions

    ingester = Ingester()
    opts = IngestOptions(
        knowledge_dir=params.knowledge_dir,
        suggested_category=params.suggested_category,
    )
    result = ingester.ingest(params.raw_text, opts)
    md = render_markdown(result)

    if params.response_format == ResponseFormat.JSON:
        import json
        return json.dumps({
            "id": result.id, "title": result.title, "axes": result.axes,
            "tags": result.tags, "refs": result.refs, "rendered_md": md,
        }, ensure_ascii=False, indent=2)
    return md
```

### 3-8. `docs/ingester.md`

300 行:

- なぜ作ったか (ingestion ハードルの除去)
- アーキ (Claude API + 軸制約 + DUMMY fallback)
- 3 つの利用方法 (CLI 単発 / バッチ / MCP tool)
- 軸推測のプロンプト戦略
- 既知の制約 (long memo は max_tokens 超え可能性、refs 推測は保守的)
- v0.5+ 計画 (Slack/Notion 連携 → 自動 ingestion, batch + review UI in Next.js)

### 3-9. README に「Ingester」セクション追加

Quickstart 直下に:

```markdown
## 🤖 メモを自動 YAML 化

既存メモ (Slack 抜粋 / 議事録 etc.) を axis-knowledge-rag 用 Markdown に AI 変換:

```bash
# 単発
python -m scripts.yamlize memo.txt --output examples/knowledge/doc_011.md

# バッチ
python -m scripts.yamlize_dir ./raw_memos/ -o examples/knowledge/

# Claude Desktop / MCP から
axis_ingest_memo(raw_text="...")
```

詳細: [docs/ingester.md](docs/ingester.md)
```

### 3-10. 動作確認

```bash
cd ~/projects/axis-knowledge-rag
pip install -e ".[dev]" --break-system-packages

# DUMMY モード (キー無しでも動く)
python -m scripts.yamlize examples/raw_memos/sample_memo_01.txt

# バッチ DUMMY
python -m scripts.yamlize_dir examples/raw_memos/ -o /tmp/output/

# テスト
pytest backend/tests/test_ingester.py -v
pytest mcp_server/tests/ -v
```

### 3-11. コミット (8〜10 件)

1. `feat(ingester): add Pydantic schemas in ingester_schemas.py`
2. `feat(ingester): implement core Claude-API memo → YAML logic`
3. `feat(ingester): add render_markdown helper`
4. `feat: add scripts/yamlize.py CLI for single-file conversion`
5. `feat: add scripts/yamlize_dir.py CLI for batch conversion`
6. `test(ingester): add DUMMY-mode integration tests`
7. `feat(mcp): add axis_ingest_memo tool`
8. `test(mcp): add axis_ingest_memo DUMMY test`
9. `docs: add docs/ingester.md + README section + sample raw memos`
10. `docs: changelog Day 23`

`git push -u origin feat/spec_023-ingester`

### 3-12. result_023.md

- 3 サンプルメモを DUMMY モードで変換した出力サンプル (markdown 全文)
- ANTHROPIC_API_KEY あれば実 Claude モードでも 1 件変換した結果
- pytest 全 pass
- README + docs サイズ
- フォローアップ: Slack 連携 (v0.5)、Apple Notes インポート (v0.6)

## 4. 成功条件

- [ ] `python -m scripts.yamlize examples/raw_memos/sample_memo_01.txt` が valid な YAML frontmatter Markdown を出す
- [ ] `python -m scripts.yamlize_dir ./examples/raw_memos/ -o /tmp/out/` で 3 ファイル変換
- [ ] DUMMY モードで全テスト PASS
- [ ] MCP tool `axis_ingest_memo` が server に登録される (mcp_server/tests/test_server.py で確認)
- [ ] LangChain/LlamaIndex 不使用
- [ ] ruff check passes
- [ ] dev-b で push

## 5. 出力先

`_ai_workspace/bridge/outbox/result_023.md`

## 6. 質問

- **`yaml.safe_dump` の出力フォーマット**: Python 標準なので順序保持されない可能性、`sort_keys=False` で順序維持。`OrderedDict` 不要
- **Claude が JSON 以外を返した場合**: コードフェンス除去のロジックを入れたが、それでも失敗したら `RuntimeError`。retry 機構は v0.5 で
- **既存 doc id の最大値推定**: `load_directory` で全 doc 読み込む → 重いが軽量サンプル数ならOK。大規模時には ChromaDB から id 一覧取得に置換 (v0.5)
- **refs 推測の保守性**: Claude が推測しすぎないように prompt で「与えられた existing_doc_ids 内のみ」と明記
- **依存追加**: なし (anthropic + pyyaml は既に入っている)

## 7. 補足

### 設計の意図

- **`rag.py` の Claude API ラッパーを再利用**: Anthropic クライアント生成、DUMMY モード判定パターンをそのまま継承
- **Pydantic で AI レスポンスをパース**: validation で hallucination リスクを早期検出
- **`load_axes_config()` を呼んで動的制約**: config.yml 変更が即反映
- **`_next_doc_id` を毎回計算**: バッチ処理でも id 衝突しない設計

### Day 22 (MCP server) との関係

spec_022 で MCP server が「ナレッジを read する」5 tools を提供。spec_023 で **「ナレッジを ingest (write 前段)」する 1 tool** を追加。これにより Claude Desktop から:
- メモを書く → `axis_ingest_memo` で YAML 化 → ファイルに保存
- そのナレッジを `axis_search` / `axis_answer` で引き出す

という双方向のループが完成する。

### 中島さんへ (差別化ピッチ)

「**RAG 系 OSS 多々あれど、ingestion 段階で AI を組み込んでる物は少ない**。Notion AI や Mem.ai はクラウド側、LangChain 系は手動 schema 定義。本 OSS は **Local-first で ingestion から retrieval まで一貫して AI ファースト**」が ES 一文で書ける。
