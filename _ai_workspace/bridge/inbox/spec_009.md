# spec_009: Day 9 — normalizer を検索パイプラインに統合

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_008 (normalizer 単体実装完了前提), `docs/spec-v2.md` Day 9 行

## 1. 目的

```
[現状]
- normalizer.py が単体で動く (Day 8)
- 検索パイプライン (loader → embedder → vector_store → search → rag) はまだ生テキストのまま
- "ＲＡＧとは" で検索しても "RAGとは" のインデックスにヒットしない

[変更後]
- 検索クエリ・ナレッジ本文・軸の値・タグが全て normalize された状態で比較される
- 表記ゆれ吸収のテスト 5 ケース以上が全 PASS
- ヒット率向上が「Before/After 比較」として result に貼られる
```

## 2. 制約

### 触ってよいファイル

- `backend/src/loader.py` — Document に `normalized_body` フィールド追加 (既存 field は据え置き、後方互換)
- `backend/src/vector_store.py` — metadata に `normalized_title`, `normalized_tags`, `normalized_axes_*` を追加
- `backend/src/search.py` — クエリ normalize、where clause も normalize した値で比較
- `backend/src/embedder.py` — embed 対象テキストを normalize するオプション (デフォルト ON)
- `scripts/build_index.py` — normalize 適用後の embedding を作る
- `backend/tests/test_loader.py` `test_search.py` — 既存テスト更新、回帰なし
- `backend/tests/test_integration_normalization.py` — 新規、End-to-End で表記ゆれ吸収を確認
- `config.yml` — `normalization` セクションが反映されることを確認
- `CHANGELOG.md`

### 触ってはいけないもの

- `backend/src/normalizer.py` — Day 8 で確定、API 変更禁止
- `_ai_workspace/`、`docs/spec-v2.md`、`streamlit_app.py`、`rag.py` (RAG 側は context を normalize しない、人間が読むので生テキスト維持)

### コーディングルール

- Document の既存フィールド (id, title, body 等) は **生テキストのまま**。`normalized_*` を別フィールドとして追加 (後方互換)
- `Normalizer.from_config(load_axes_config())` で 1 インスタンス作って使い回す
- 軸の値 normalize: `_flatten_axes` 内で `axis_category_norm` のように `_norm` サフィックスで別キーに保存 (`axis_category` は生のまま、UI 表示用)
- 検索 where clause は normalize 後の値で組む (`axis_category_norm = normalize("技術記事")`)
- `embedder` は normalize 後テキストで embed する (DUMMY モードも同じ)

## 3. やってほしいこと

### 3-1. `loader.py` 拡張

```python
@dataclass
class Document:
    id: str
    title: str
    axes: dict[str, Any]
    tags: list[str]
    refs: list[str]
    body: str
    path: Path
    raw_meta: dict[str, Any] = field(default_factory=dict)
    # 新規 (normalize 後の派生フィールド)
    normalized_title: str = ""
    normalized_body: str = ""
    normalized_axes: dict[str, str] = field(default_factory=dict)
    normalized_tags: list[str] = field(default_factory=list)
```

`load_document` の末尾で normalize を実行 (引数で normalizer を受け取れるように):

```python
def load_document(
    path: Path, normalizer: Normalizer | None = None
) -> Document:
    ...  # 既存ロジック
    doc = Document(...)  # 既存フィールド埋め
    if normalizer is not None:
        doc.normalized_title = normalizer(doc.title)
        doc.normalized_body = normalizer(doc.body)
        doc.normalized_axes = {k: normalizer(str(v)) for k, v in doc.axes.items()}
        doc.normalized_tags = [normalizer(t) for t in doc.tags]
    return doc
```

`load_directory` も同様に normalizer を受け取って配る。デフォルトは `None` (Day 1 の挙動を維持、テスト互換)。

### 3-2. `vector_store.py` 拡張

```python
def _flatten_axes(axes: dict[str, Any]) -> dict[str, ...]:
    ...  # 既存

def _flatten_axes_with_norm(
    axes: dict[str, Any], normalized: dict[str, str]
) -> dict[str, ...]:
    out = _flatten_axes(axes)
    for k, v in normalized.items():
        out[f"axis_{k}_norm"] = v
    return out


class VectorStore:
    def upsert(self, doc: Document, embedding: list[float]) -> None:
        metadata = {
            "title": doc.title,
            "title_norm": doc.normalized_title,
            "path": str(doc.path),
            "tags": ",".join(doc.tags),
            "tags_norm": ",".join(doc.normalized_tags),
            "refs": ",".join(doc.refs),
            **_flatten_axes_with_norm(doc.axes, doc.normalized_axes),
        }
        ...
```

### 3-3. `search.py` 改修

- SearchEngine が Normalizer を持つ
- query は embed 前に normalize
- filters は where 構築時に key を `axis_*_norm`、value を normalize 後で
- SearchResult の表示はまだ生テキスト (UI で読みやすいまま)

```python
class SearchEngine:
    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        normalizer: Normalizer | None = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._normalizer = normalizer or Normalizer()

    def search(self, query, *, filters=None, top_k=5):
        q_norm = self._normalizer(query) if query else None
        norm_filters = (
            {k: self._normalizer(str(v)) for k, v in (filters or {}).items()}
            if filters else None
        )
        where = _build_where_norm(norm_filters or {})
        embedding = self._embedder.embed(q_norm) if q_norm else [0.0] * 768
        raw = self._store.query(embedding=embedding, n_results=top_k, where=where)
        return _to_results(raw)


def _build_where_norm(filters: dict[str, Any]) -> dict[str, Any] | None:
    if not filters:
        return None
    out = {f"axis_{k}_norm": v for k, v in filters.items()}
    if len(out) == 1:
        return out
    return {"$and": [{k: v} for k, v in out.items()]}
```

### 3-4. `embedder.py` の embed 対象 normalize

実装は **scripts/build_index.py 側**で normalize して `embedder.embed(normalized)` を渡す形が綺麗。Embedder クラス自体は変更不要 (Embedder は「与えられたテキストを embed する」責務に専念)。

### 3-5. `scripts/build_index.py` 更新

```python
def main(argv):
    ...
    norm = Normalizer.from_config(load_axes_config())
    docs = load_directory(args.knowledge_dir, normalizer=norm)
    ...
    embedder = Embedder()
    # body ではなく normalized_body を embed する
    embeddings = embedder.embed_batch([d.normalized_body for d in docs])
    store.upsert_many(docs, embeddings)
```

### 3-6. `streamlit_app.py` の `get_pipeline()` 更新

```python
@st.cache_resource
def get_pipeline() -> tuple[SearchEngine, RAGPipeline]:
    store = VectorStore(path=settings.chroma_db_path)
    embedder = Embedder()
    normalizer = Normalizer.from_config(load_axes_config())
    engine = SearchEngine(store, embedder, normalizer)
    rag = RAGPipeline(engine)
    return engine, rag
```

### 3-7. `backend/tests/test_integration_normalization.py` (新規)

End-to-End:

- in-memory VectorStore に 3 件投入 (`RAG`, `ラグ`, `claude`)
- query `"ＲＡＧ"` (全角) が `RAG` の Document を返す
- query `"らぐ"` (ひらがな) が `ラグ` の Document を返す
- query `"CLAUDE"` が `claude` の Document を返す
- filter `{"category": "技術記事"}` と `{"category": "ＴｅｃｈＮｏｔｅ"}` が同じ正規化結果になる場合の挙動

### 3-8. 既存テストの更新

- `test_loader.py`: normalizer なしの呼び出しが今まで通り動くこと (`normalized_*` フィールドは空文字 / 空 dict)
- `test_search.py`: 必要なら normalizer を inject、既存ケースは挙動が同じであることを確認

### 3-9. ビルド済みインデックスの再構築

```bash
python -m scripts.build_index ./examples/knowledge --reset
```

旧 metadata の `axis_category` のみだった collection を、新 `axis_category_norm` 入りに作り直す。

### 3-10. 動作確認

```bash
# Before / After 比較を CLI でやる
python -m backend.src.search "ＲＡＧとは"
python -m backend.src.search "RAGとは"

# 期待: 両方とも同じ top-1 を返す (DUMMY モードでもこれは確認可能、normalize 後テキストが同じなので)

python -m backend.src.search "らぐ" --category 技術記事
python -m backend.src.search "ラグ" --category 技術記事
python -m backend.src.search "ラグ" --category ｺﾞｼﾞｭﾂｷｼﾞ  # 半角カナ filter
```

### 3-11. コミット

1. `feat: extend Document with normalized_* fields`
2. `feat: store normalized metadata in ChromaDB (axis_*_norm)`
3. `feat: integrate Normalizer into SearchEngine`
4. `feat: index normalized body in build_index.py`
5. `feat: wire Normalizer into Streamlit app`
6. `test: add E2E normalization integration tests`
7. `docs: changelog Day 9`

`git push origin main` (dev-b)

### 3-12. result_009.md

特に書くこと:

- 既存テスト (`test_loader.py` 等) が回帰してないこと
- Before/After 比較: 同じクエリで normalize なし版と normalize あり版のヒット結果差分
- ChromaDB 容量がどれだけ増えたか (`du -sh .chromadb`)

## 4. 成功条件

- [ ] 全テスト PASS (loader, embedder, vector_store, search, rag, normalizer, integration_normalization)
- [ ] `python -m backend.src.search "ＲＡＧ"` と `"RAG"` が同じ top-1 を返す
- [ ] 半角カナ filter が全角と同じ結果を返す
- [ ] 既存 CLI / Streamlit が壊れていない
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_009.md`

## 6. 質問

- **既存インデックスとの互換**: spec_007 までで作った .chromadb は新スキーマと互換性がないので、`--reset` で作り直す前提。アナウンス不要 (private repo の dev データなので)。質問は不要
- **`Document` のフィールド追加で既存テストが壊れた場合**: デフォルト値で互換性を保つ実装を試み、それでも壊れたら test を更新して result に書く
- **`refs` の normalize**: doc id は normalize しない方針 (id は一意キーで `doc_001` 等)、混乱しないように normalizer の対象外

## 7. 補足

### 設計の意図

- **生テキストを保持、normalize 後を別フィールド**: UI は生テキストを表示、検索だけ normalize、というのが直感的
- **`_norm` サフィックス**: chroma metadata のキー命名規約として `_norm` を予約。Day 10 以降でも統一
- **embedder には normalized を渡す**: 同じ semantic でも書き方が違うベクトルが別位置に飛ぶのを防ぐ
- **RAG context は生テキスト**: Claude に提示する文書は人間が書いた通りの方が回答品質が良い

### Day 10 連携

`integrity.py` (参照整合性チェック) は normalize に依存しない (doc id は normalize しない)。両者を独立した spec にすることで失敗時の影響範囲を限定。
