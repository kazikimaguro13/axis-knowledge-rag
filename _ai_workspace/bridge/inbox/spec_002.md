# spec_002: Day 2 — embedder.py + vector_store.py + build_index

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001 (loader.py 完成前提), `docs/spec-v2.md` Day 2 行

## 1. 目的

```
[現状]
- spec_001 で loader.py が完成し、5 本のサンプル knowledge を Document として読み込める
- ベクトル検索の基盤 (埋め込み生成 / ベクトルストア) はまだない

[変更後]
- Gemini text-embedding-004 で Document を 768 次元ベクトルへ変換できる (`embedder.py`)
- ChromaDB のラッパーが Document を保存・取得できる (`vector_store.py`)
- `scripts/build_index.py` でサンプル 5 本をインデックス化、`.chromadb/` に永続化
- 既存サンプルで `python -m scripts.build_index ./examples/knowledge` 実行成功
- Day 3 (search.py) が引ける状態に
```

Day 2 のゴールは **「読み込んだ Document をベクトル空間に乗せる」** こと。Gemini API キーが未設定でも fallback (ダミー埋め込み) で開発できるようにし、CI でもキー無しで test が通るようにする。

## 2. 制約

### 触ってよいファイル / 新規作成

- `backend/src/embedder.py` — 新規
- `backend/src/vector_store.py` — 新規
- `scripts/__init__.py` — 新規 (空)
- `scripts/build_index.py` — 新規
- `backend/tests/test_embedder.py` — 新規 (ダミー埋め込みモードで)
- `backend/tests/test_vector_store.py` — 新規 (in-memory ChromaDB で)
- `backend/requirements.txt` — `google-generativeai`, `chromadb` 追加
- `pyproject.toml` — `dependencies` に同上を追加
- `.env.example` — 既に `GEMINI_API_KEY` 入っているはず (spec_001 で)、ない場合のみ追記
- `.gitignore` — `.chromadb/` 追記 (spec_001 で入っていないなら)
- `CHANGELOG.md` — Day 2 セクション追記

### 触ってはいけないもの

- `_ai_workspace/` 配下
- `docs/spec-v2.md`
- `backend/src/loader.py` — Day 1 で確定。バグがあれば spec の Open questions に書く、勝手に変更しない
- `backend/src/config.py` — 微修正は OK だが、既存 API を壊さない
- `frontend/`、`backend/src/{normalizer,integrity,marker,search,rag,api}.py`

### コーディングルール

- spec_001 と同じ (Python 3.11, type hints, Google docstring, ruff line-length=100, LangChain/LlamaIndex 禁止)
- **dummy embedder モード**: `GEMINI_API_KEY` が未設定 / 空のとき、deterministic な擬似ベクトル (テキストハッシュベースの 768 次元) を返す。dev / CI 両対応
- ChromaDB は **PersistentClient** を使う (`.chromadb/` ディレクトリ)。テストでは `tempfile` でテンポラリパス
- collection 名は `axis_knowledge` (config.py に定数化)

### 依存ライブラリ追加

```
google-generativeai>=0.7.0
chromadb>=0.5.0
```

`chromadb` は依存が重いが、ローカル動作のメイン要件なので採用。今後 v0.4 でプラガブル化する余地は残す。

### デプロイ・コミット

- 完了後 dev-b で `git push origin main`
- コミット粒度 3〜6 個、prefix 規約は spec_001 と同じ

## 3. やってほしいこと

### 3-1. `backend/src/embedder.py`

```python
"""Gemini text-embedding-004 wrapper with a deterministic dummy fallback.

If GEMINI_API_KEY is not configured, returns hash-derived 768-dim vectors so
that downstream code paths can be exercised in CI / offline dev without
hitting the network.
"""

import hashlib
import logging
from typing import Sequence

from backend.src.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768
_GEMINI_MODEL = "text-embedding-004"


def _dummy_embedding(text: str) -> list[float]:
    """Deterministic 768-dim vector from text hash. NOT semantically meaningful."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    # Repeat hash bytes to fill 768 dims, normalize to [-1, 1]
    out: list[float] = []
    i = 0
    while len(out) < EMBEDDING_DIM:
        out.append((h[i % len(h)] / 127.5) - 1.0)
        i += 1
    return out[:EMBEDDING_DIM]


class Embedder:
    """Wraps Gemini embeddings with a graceful offline fallback."""

    def __init__(self, *, force_dummy: bool = False) -> None:
        self._use_dummy = force_dummy or not settings.gemini_api_key
        if self._use_dummy:
            logger.warning("Embedder running in DUMMY mode (no GEMINI_API_KEY)")
        else:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            self._genai = genai

    @property
    def is_dummy(self) -> bool:
        return self._use_dummy

    def embed(self, text: str) -> list[float]:
        if self._use_dummy:
            return _dummy_embedding(text)
        result = self._genai.embed_content(model=_GEMINI_MODEL, content=text)
        return list(result["embedding"])

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
```

### 3-2. `backend/src/vector_store.py`

```python
"""ChromaDB wrapper for storing Documents with axis metadata.

Stores body embedding as the primary vector and full axis dict in metadata
so that downstream search.py can filter on axes before / alongside vector
similarity.
"""

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.src.loader import Document

logger = logging.getLogger(__name__)

COLLECTION_NAME = "axis_knowledge"


def _flatten_axes(axes: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Chroma metadata must be flat scalar values."""
    out: dict[str, str | int | float | bool] = {}
    for k, v in axes.items():
        key = f"axis_{k}"
        if isinstance(v, (str, int, float, bool)):
            out[key] = v
        else:
            out[key] = str(v)
    return out


class VectorStore:
    def __init__(self, path: Path | None = None, *, in_memory: bool = False) -> None:
        if in_memory:
            self._client = chromadb.EphemeralClient()
        else:
            db_path = path or Path("./.chromadb")
            db_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(db_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)

    def upsert(self, doc: Document, embedding: list[float]) -> None:
        metadata = {
            "title": doc.title,
            "path": str(doc.path),
            "tags": ",".join(doc.tags),
            "refs": ",".join(doc.refs),
            **_flatten_axes(doc.axes),
        }
        self._collection.upsert(
            ids=[doc.id],
            embeddings=[embedding],
            documents=[doc.body],
            metadatas=[metadata],
        )

    def upsert_many(
        self, docs: list[Document], embeddings: list[list[float]]
    ) -> None:
        if len(docs) != len(embeddings):
            raise ValueError("docs and embeddings length mismatch")
        for d, e in zip(docs, embeddings):
            self.upsert(d, e)

    def count(self) -> int:
        return self._collection.count()

    def query(
        self,
        embedding: list[float],
        *,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
        )

    def reset(self) -> None:
        """Drop and recreate the collection. Useful for rebuilding."""
        try:
            self._client.delete_collection(name=COLLECTION_NAME)
        except Exception:  # noqa: BLE001 — Chroma raises specific error if not exists
            pass
        self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)
```

### 3-3. `scripts/build_index.py`

```python
"""Build the ChromaDB index from a knowledge directory.

Usage:
    python -m scripts.build_index ./examples/knowledge
    python -m scripts.build_index ./examples/knowledge --reset
"""

import argparse
import sys
from pathlib import Path

from backend.src.config import configure_logging, settings
from backend.src.embedder import Embedder
from backend.src.loader import load_directory
from backend.src.vector_store import VectorStore


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Build ChromaDB index from Markdown.")
    parser.add_argument("knowledge_dir", type=Path)
    parser.add_argument("--reset", action="store_true", help="Drop existing collection first")
    parser.add_argument("--db-path", type=Path, default=settings.chroma_db_path)
    args = parser.parse_args(argv[1:])

    docs = load_directory(args.knowledge_dir)
    if not docs:
        print("No documents found.", file=sys.stderr)
        return 1

    store = VectorStore(path=args.db_path)
    if args.reset:
        store.reset()

    embedder = Embedder()
    embeddings = embedder.embed_batch([d.body for d in docs])
    store.upsert_many(docs, embeddings)

    print(f"Indexed {len(docs)} documents into {args.db_path}")
    print(f"Total in collection: {store.count()}")
    print(f"Embedder mode: {'DUMMY' if embedder.is_dummy else 'GEMINI'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

### 3-4. Tests (assert ベース、pytest はまだ未導入)

`backend/tests/test_embedder.py`:

- `force_dummy=True` で 768 dim を返す
- 同じテキストは同じベクトル (deterministic)
- 異なるテキストは異なるベクトル

`backend/tests/test_vector_store.py`:

- `in_memory=True` で初期化、`upsert` → `count() == 1`
- ダミー Document + ダミー埋め込みで往復、`query` が結果を返す
- `reset()` で count が 0 に戻る

### 3-5. 動作確認

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"

pip install -e .

# DUMMY モードでもインデックス構築できることを確認
python -m scripts.build_index ./examples/knowledge --reset

# 期待: Indexed 5 documents into .chromadb, Total in collection: 5, Embedder mode: DUMMY

# テスト
python -m backend.tests.test_embedder
python -m backend.tests.test_vector_store
```

### 3-6. コミット + Push

1. `chore: add chromadb and google-generativeai to dependencies`
2. `feat: implement Gemini embedder with dummy fallback for CI`
3. `feat: implement ChromaDB vector store wrapper`
4. `feat: add scripts/build_index.py to index knowledge directory`
5. `test: add smoke tests for embedder and vector_store`

`git push origin main` (dev-b)

### 3-7. result_002.md を outbox に

`templates/result_template.md` の構造で、特に:

- DUMMY mode と GEMINI mode の挙動確認 (どちらでも index 構築できたか)
- ChromaDB のディスク使用量 (`du -sh .chromadb`)
- Gemini API の rate limit に当たった場合のエラーハンドリングを実機検証したか

## 4. 成功条件

- [ ] `python -m scripts.build_index ./examples/knowledge --reset` が 5 docs インデックス化成功
- [ ] DUMMY mode (API キー無し) で動作する
- [ ] GEMINI mode (API キーあり) でも動作する (キーが手元にある場合のみ任意)
- [ ] 全テスト PASS
- [ ] LangChain/LlamaIndex を import していない
- [ ] dev-b で git push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_002.md`

## 6. 質問があるとき

- **chromadb のバージョン互換**: 0.5.x で API 変わっているので、`upsert` メソッドが存在しない場合は `add` で代替、その旨 result に記載
- **Gemini embed_content の API シグネチャ**: google-generativeai のバージョンで微妙に違うので、エラーが出たら try-except で実装を切り替え、result に書く
- **chunking**: 今は body 全体を 1 ベクトルにしているが、長文だと精度が落ちる。Day 2 では chunking 不要、Week 2 / v0.4 で導入予定。質問されたらこの方針

## 7. 補足

### 設計の意図

- **DUMMY mode**: 開発時に Gemini key を毎回設定するのは面倒、CI で API call したくないので必須
- **collection 名定数化**: search.py が同じ collection 名を引くので、ハードコードしない
- **`_flatten_axes`**: Chroma の metadata はネスト不可、軸を `axis_*` プレフィックスで平坦化することで search.py の `where={"axis_category": "技術記事"}` がそのまま使える
- **in_memory モード**: テスト高速化、本番ではディスク永続化

### 将来の拡張余地

- spec_003 (Day 3): `search.py` でこのストアを引いて、axis フィルタ + vector 類似度 hybrid 検索
- v0.4 候補: embedder をプラガブル化 (OpenAI, Voyage 等への切り替え)、chunking 導入
