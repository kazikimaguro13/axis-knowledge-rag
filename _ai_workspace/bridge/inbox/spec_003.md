# spec_003: Day 3 — search.py (軸フィルタ + ベクトル類似度 ハイブリッド)

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001 (loader), spec_002 (embedder, vector_store) 完成前提, `docs/spec-v2.md` Day 3 行

## 1. 目的

```
[現状]
- Day 2 で ChromaDB に Document が格納され、軸メタデータが `axis_*` プレフィックスで保存されている
- まだ「検索」インターフェイスがない

[変更後]
- `backend/src/search.py` が SearchEngine クラスとして以下を提供:
  - 軸フィルタのみ (vector 検索なし)
  - クエリ + 軸フィルタの hybrid (Chroma の where + query_embeddings)
  - 結果は SearchResult dataclass (score 付き) のリスト
- CLI で `python -m backend.src.search "RAGとは" --category 技術記事` 実行可能
- Day 4 (rag.py) が SearchResult を context として食える状態
```

差別化の核「**軸フィルタ + ベクトル検索の組み合わせ**」を実装する一番大事な日。Day 4 の RAG は「軸で絞ってから生成」する構造にするので、ここで API を確定させる。

## 2. 制約

### 触ってよいファイル / 新規作成

- `backend/src/search.py` — 新規
- `backend/tests/test_search.py` — 新規
- `backend/src/config.py` — 既存 API を壊さない範囲で定数を追加して OK
- `CHANGELOG.md` — Day 3 追記

### 触ってはいけないもの

- `_ai_workspace/`、`docs/spec-v2.md`、`backend/src/loader.py`、`backend/src/embedder.py`、`backend/src/vector_store.py`
- 既存のコレクション schema、`_flatten_axes` の axis_ プレフィックス規約

### コーディングルール

- spec_001/002 と同じ
- SearchEngine は依存注入で組み立てる: `SearchEngine(store: VectorStore, embedder: Embedder)`
- 結果は dataclass `SearchResult` で固める (id, title, score, axes, body_snippet, path, refs)
- score は ChromaDB の distance を **類似度に変換** (`1.0 - distance` を 0〜1 にクリップ、distance metric は cosine 前提)

## 3. やってほしいこと

### 3-1. `backend/src/search.py`

```python
"""Hybrid search over the knowledge index.

Combines axis filtering (exact match on metadata) with vector similarity
(cosine on embeddings). The unique selling point of axis-knowledge-rag.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.src.embedder import Embedder
from backend.src.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    id: str
    title: str
    score: float
    axes: dict[str, Any]
    body_snippet: str
    path: str
    refs: list[str] = field(default_factory=list)


def _build_where(filters: dict[str, Any]) -> dict[str, Any] | None:
    """Translate user-level filters to Chroma where-clause.

    User passes: {"category": "技術記事", "level": "中級"}
    Chroma needs: {"axis_category": "技術記事", "axis_level": "中級"}
    Multiple keys are AND-combined via the implicit dict form.
    """
    if not filters:
        return None
    out = {f"axis_{k}": v for k, v in filters.items()}
    if len(out) == 1:
        return out
    # Chroma 0.5 requires explicit $and for multi-key
    return {"$and": [{k: v} for k, v in out.items()]}


def _snippet(body: str, max_chars: int = 200) -> str:
    body = body.strip().replace("\n", " ")
    if len(body) <= max_chars:
        return body
    return body[:max_chars] + "..."


def _to_results(raw: dict[str, Any]) -> list[SearchResult]:
    """Convert Chroma query() output to SearchResult list."""
    ids = raw.get("ids", [[]])[0]
    distances = raw.get("distances", [[]])[0]
    metadatas = raw.get("metadatas", [[]])[0]
    documents = raw.get("documents", [[]])[0]

    out: list[SearchResult] = []
    for i, doc_id in enumerate(ids):
        md = metadatas[i] or {}
        dist = distances[i] if distances else 0.0
        score = max(0.0, min(1.0, 1.0 - dist))
        axes = {k.removeprefix("axis_"): v for k, v in md.items() if k.startswith("axis_")}
        refs = [r for r in (md.get("refs") or "").split(",") if r]
        out.append(
            SearchResult(
                id=doc_id,
                title=str(md.get("title", "")),
                score=score,
                axes=axes,
                body_snippet=_snippet(documents[i] if documents else ""),
                path=str(md.get("path", "")),
                refs=refs,
            )
        )
    return out


class SearchEngine:
    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    def search(
        self,
        query: str | None,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Hybrid search.

        Args:
            query: Natural-language query. If None, axis-only search (top_k arbitrary).
            filters: User-friendly axis filters (`{"category": "技術記事"}`).
            top_k: Maximum results to return.
        """
        where = _build_where(filters or {})

        if query is None:
            # Axis-only path: use a zero embedding (Chroma will then sort by
            # distance from zero, which is arbitrary — but we mostly care about
            # the filter). top_k is bounded by collection size.
            n = min(top_k, max(self._store.count(), 1))
            embedding = [0.0] * 768
        else:
            embedding = self._embedder.embed(query)
            n = top_k

        raw = self._store.query(embedding=embedding, n_results=n, where=where)
        results = _to_results(raw)
        logger.info(
            "search(query=%r, filters=%s) -> %d results", query, filters, len(results)
        )
        return results


def _main(argv: list[str]) -> int:
    """CLI:
        python -m backend.src.search "<query>" [--category X] [--level Y] [--top 5]
    """
    import argparse

    from backend.src.config import configure_logging, settings

    configure_logging()
    p = argparse.ArgumentParser()
    p.add_argument("query", nargs="?", default=None)
    p.add_argument("--category")
    p.add_argument("--topic")
    p.add_argument("--level")
    p.add_argument("--author")
    p.add_argument("--year", type=int)
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
            "year": args.year,
        }.items()
        if v is not None
    }

    from pathlib import Path

    store = VectorStore(path=Path(args.db_path))
    embedder = Embedder()
    engine = SearchEngine(store, embedder)
    results = engine.search(args.query, filters=filters, top_k=args.top)

    print(f"\n=== {len(results)} results for query={args.query!r} filters={filters} ===\n")
    for r in results:
        print(f"[{r.score:.3f}] {r.id}  {r.title}")
        print(f"        axes: {r.axes}")
        print(f"        {r.body_snippet}\n")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv))
```

### 3-2. `backend/tests/test_search.py`

- in_memory VectorStore + force_dummy Embedder で 3 件 Document を仕込む
- フィルタなし query — 3 件返る
- `filters={"category": "技術記事"}` — 該当のみ返る
- query=None + axis-only — フィルタ一致のみ返る
- スコアが 0〜1 の範囲

### 3-3. 動作確認

```bash
# 前提: spec_002 の build_index 済み
python -m backend.src.search "RAGとは" --top 3

python -m backend.src.search "ベクトル検索の原理" --category 技術記事 --level 中級

python -m backend.src.search --category メモ
```

### 3-4. コミット

1. `feat: implement SearchEngine with hybrid axis+vector search`
2. `feat: add CLI to backend/src/search.py`
3. `test: add SearchEngine integration tests using in-memory store`
4. `docs: changelog Day 3`

`git push origin main` (dev-b)

### 3-5. result_003.md

特に検証してほしいこと:

- Chroma 0.5 の `$and` 構文が手元バージョンで動くか
- distance → score 変換の妥当性 (DUMMY モードでは hash 由来なので絶対値は無意味、相対順位だけ意味があることを result に書く)
- 既存サンプル 5 本 + 各 CLI 例の実行結果を貼る

## 4. 成功条件

- [ ] CLI 3 パターンが結果を返す
- [ ] テスト全 PASS
- [ ] dev-b で push 成功
- [ ] SearchResult が Day 4 の rag.py で食える形 (id, title, body_snippet, score, refs を持つ)

## 5. 出力先

`_ai_workspace/bridge/outbox/result_003.md`

## 6. 質問

- **Chroma where 構文**: `$and` が動かない場合、複数フィルタは Python 側で post-filter する fallback を入れて result に書く
- **DUMMY モードでの query 順位**: 順位がでたらめでも CLI は動く、ただし result に「semantic な意味はない」と明記
- **`axis_year` の型**: int で入っているはずだが、Chroma が string に強制変換していないか確認、必要なら `where={"axis_year": {"$eq": 2026}}` 形式を試す

## 7. 補足

### 設計の意図

- **DI で組み立て**: SearchEngine が VectorStore / Embedder を所有しないので、テストで in_memory + DUMMY に差し替えやすい
- **filters を User-friendly な dict**: `{"category": "技術記事"}` で受け、内部で `axis_*` プレフィックスを付け直す。`vector_store._flatten_axes` を呼び出し側が意識しなくていい
- **CLI を search.py に同居**: 別ファイル `cli.py` にすると import 循環の温床、Day 5 (Streamlit) で UI 側からは `SearchEngine` を直接 import するのでこれで十分
- **`top_k` を `count()` でクリップ**: Chroma は collection より大きい n_results を渡すとエラーになるバージョンがある

### Day 4 連携

rag.py は SearchEngine から取得した `list[SearchResult]` を context にプロンプトを組む。`body_snippet` は短いので、rag.py 側で必要なら `path` を Open し直して全文を取り直す設計にする (この方針も result_003 に書く)。
