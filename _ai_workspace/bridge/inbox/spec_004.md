# spec_004: Day 4 — rag.py (Claude API、出典付き回答)

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜003 完成前提, `docs/spec-v2.md` Day 4 行

## 1. 目的

```
[現状]
- spec_003 で SearchEngine が動き、軸フィルタ + ベクトル検索で関連ナレッジを取れる
- まだ「生成 (回答)」のレイヤーがない

[変更後]
- `backend/src/rag.py` が以下を提供:
  - `RAGPipeline` クラス: SearchEngine の結果を context にして Claude API で回答生成
  - **出典必須**: 回答中で参照した Document id を `[doc_001]` 形式で本文に埋め、別途 `sources: list[SearchResult]` も返す
  - **anthropic-api 未設定時の DUMMY モード**: Embedder と同様に offline で動かせる
- CLI `python -m backend.src.rag "質問" --category 技術記事` で出典付き回答
- API 層 (Day 4 後半 or Day 5) は未着手で OK、まず CLI で完成させる
```

差別化ポイントの **「Local-first」「Claude + Gemini 役割分担」** をここで実装する。Pydantic はまだ入れない (API 化は spec_006 or spec_009 で導入)。

## 2. 制約

### 触ってよいファイル / 新規作成

- `backend/src/rag.py` — 新規
- `backend/tests/test_rag.py` — 新規 (DUMMY モードのみ)
- `backend/requirements.txt` — `anthropic>=0.34.0` 追加
- `pyproject.toml` — dependencies に同上
- `CHANGELOG.md`

### 触ってはいけないもの

- `_ai_workspace/`、`docs/spec-v2.md`、既存の loader/embedder/vector_store/search/config
- 既存の DUMMY 判定ロジック (Embedder と整合させる)

### コーディングルール

- spec_001〜003 と同じ
- Claude API は `anthropic.Anthropic` クライアントを直に使う (LangChain 禁止)
- model: `claude-3-5-sonnet-20241022` を **環境変数 `CLAUDE_MODEL` で上書き可能** に
- 出典マークは `[doc_NNN]` でプロンプトに指示、後処理でパース
- system prompt は文字列定数として rag.py の冒頭に定義 (prompts/ ディレクトリは作らない、Day 4 ではここで十分)

### 依存ライブラリ追加

```
anthropic>=0.34.0
```

## 3. やってほしいこと

### 3-1. `backend/src/rag.py`

```python
"""RAG pipeline: retrieve via SearchEngine, generate with Claude.

Returns an Answer that contains the generated text + citation list,
preserving source document IDs for downstream UI rendering.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from backend.src.config import settings
from backend.src.embedder import Embedder
from backend.src.search import SearchEngine, SearchResult
from backend.src.vector_store import VectorStore

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

SYSTEM_PROMPT = """\
あなたは知識ベース検索エンジンの回答生成エージェントです。
ユーザーの質問に対して、提供された Document の内容**のみ**から回答してください。
提供された文書に書かれていないことは「資料には記載がない」と答えてください。

回答ルール:
1. 回答中で参照した Document は必ず `[doc_NNN]` 形式で本文中にマークしてください
2. 複数 Document を参照した場合は `[doc_001][doc_004]` のように並べる
3. 推測や一般論を加えず、Document の内容を要約・引用する形にする
4. 出典が無い質問への回答は「提供された資料には記載がありません」と短く答える

簡潔で読みやすい日本語で答えてください。
"""

CITATION_RE = re.compile(r"\[(doc_\d+)\]")


@dataclass
class Answer:
    text: str
    sources: list[SearchResult] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)
    is_dummy: bool = False
    model: str | None = None


def _format_context(results: list[SearchResult]) -> str:
    lines: list[str] = []
    for r in results:
        lines.append(f"### [{r.id}] {r.title}")
        lines.append(f"axes: {r.axes}")
        lines.append(r.body_snippet)
        lines.append("")
    return "\n".join(lines)


def _dummy_answer(question: str, results: list[SearchResult]) -> Answer:
    """Generate a deterministic offline answer for dev / CI."""
    if not results:
        return Answer(
            text="提供された資料には記載がありません。",
            sources=[],
            cited_ids=[],
            is_dummy=True,
        )
    cited = [results[0].id]
    text = (
        f"[DUMMY ANSWER] 質問「{question}」に対し、"
        f"資料 [{results[0].id}] (「{results[0].title}」) が最も関連しています。"
        f" 抜粋: {results[0].body_snippet[:120]}..."
    )
    return Answer(
        text=text, sources=results, cited_ids=cited, is_dummy=True, model="dummy"
    )


class RAGPipeline:
    def __init__(
        self,
        engine: SearchEngine,
        *,
        force_dummy: bool = False,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._engine = engine
        self._model = model
        self._use_dummy = force_dummy or not settings.anthropic_api_key
        if self._use_dummy:
            logger.warning("RAGPipeline running in DUMMY mode (no ANTHROPIC_API_KEY)")
            self._client = None
        else:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=settings.anthropic_api_key)

    @property
    def is_dummy(self) -> bool:
        return self._use_dummy

    def answer(
        self,
        question: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int = 5,
        max_tokens: int = 1024,
    ) -> Answer:
        results = self._engine.search(question, filters=filters, top_k=top_k)
        if self._use_dummy:
            return _dummy_answer(question, results)

        context = _format_context(results)
        user_msg = (
            f"# 質問\n{question}\n\n"
            f"# 提供された資料 (上位 {len(results)} 件)\n\n{context}\n\n"
            "上記の資料のみを根拠に、出典マーク [doc_NNN] を付けて回答してください。"
        )
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        cited_ids = sorted(set(CITATION_RE.findall(text)))
        return Answer(
            text=text,
            sources=results,
            cited_ids=cited_ids,
            is_dummy=False,
            model=self._model,
        )


def _main(argv: list[str]) -> int:
    import argparse
    from pathlib import Path

    from backend.src.config import configure_logging

    configure_logging()
    p = argparse.ArgumentParser()
    p.add_argument("question")
    p.add_argument("--category")
    p.add_argument("--topic")
    p.add_argument("--level")
    p.add_argument("--author")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--db-path", default=str(settings.chroma_db_path))
    args = p.parse_args(argv[1:])

    filters = {
        k: v
        for k, v in {
            "category": args.category,
            "topic": args.topic,
            "level": args.level,
            "author": args.author,
        }.items()
        if v is not None
    }
    store = VectorStore(path=Path(args.db_path))
    embedder = Embedder()
    engine = SearchEngine(store, embedder)
    rag = RAGPipeline(engine)
    ans = rag.answer(args.question, filters=filters or None, top_k=args.top)

    print(f"\n=== Answer (model={ans.model}, dummy={ans.is_dummy}) ===\n")
    print(ans.text)
    print("\n--- Sources ---")
    for s in ans.sources:
        marker = "*" if s.id in ans.cited_ids else " "
        print(f" {marker} [{s.score:.3f}] {s.id}  {s.title}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv))
```

### 3-2. `backend/tests/test_rag.py`

- in_memory store + DUMMY embedder + DUMMY rag で構築
- 既存 spec_003 の test と同じサンプルを上書きしないように setup
- `answer("dummy question")` が `is_dummy=True` で返る
- `sources` に top_k 件入る
- `cited_ids` が結果 0 件の場合は空 list

### 3-3. 動作確認

```bash
# 前提: spec_002 build_index 済み (DUMMY でも OK)
python -m backend.src.rag "RAGとは何か"

python -m backend.src.rag "ベクトル検索の仕組み" --category 技術記事 --top 3

# ANTHROPIC_API_KEY 設定済みなら、実際の Claude 出力を確認
```

### 3-4. コミット

1. `chore: add anthropic SDK to dependencies`
2. `feat: implement RAGPipeline with citation extraction and DUMMY fallback`
3. `feat: add CLI for backend/src/rag.py`
4. `test: add RAG DUMMY-mode integration tests`
5. `docs: changelog Day 4`

`git push origin main` (dev-b)

### 3-5. result_004.md

特に書くべきこと:

- DUMMY と Claude 実行 (キーあれば) 両方の出力例
- citation regex `\[(doc_\d+)\]` の検出精度 (Claude が指示通り `[doc_001]` を出すか、別形式に揺れていないか)
- `max_tokens=1024` で足りなかったケースの有無

## 4. 成功条件

- [ ] CLI 動作 (DUMMY モード)
- [ ] Claude API モード (キーあれば)
- [ ] `cited_ids` が抽出される
- [ ] テスト全 PASS
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_004.md`

## 6. 質問

- **Claude が citation を付けない場合**: SYSTEM_PROMPT を強化、もしくは後処理で「使われた sources を全部 cited 扱いにする」フォールバック。判断したい場合は質問
- **context が長すぎる場合の chunking**: 今は body_snippet 200 字を使うので問題なし。フル本文を使うなら token 数を測る必要、その場合は質問
- **モデル名**: `claude-3-5-sonnet-20241022` が deprecated になっている可能性。エラーが出たら最新の sonnet 系に切り替え、result に記載

## 7. 補足

### 設計の意図

- **Pydantic 不使用**: Day 4 では API 層を作らない、Streamlit (Day 5) から `RAGPipeline.answer` を直に呼ぶので dataclass で十分
- **citation regex でパース**: Claude の出力に頼った構造化、tool_use を使う方が堅いが OSS 公開時の理解しやすさ優先で簡素に。Week 2 で tool_use への切り替えも検討
- **system prompt を冒頭定数化**: prompts/ ディレクトリ作るのは早すぎ、Day 4 では 1 つのプロンプトだけなので

### Day 5 連携

Streamlit UI からは `RAGPipeline.answer()` を直接呼ぶ。`Answer.sources` を ResultCard、`Answer.cited_ids` で出典をハイライト、`Answer.text` を AnswerPanel に表示する設計を Day 5 spec で書く。
