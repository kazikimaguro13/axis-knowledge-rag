# API Reference

`backend/src/` 以下の public モジュールの API リファレンス。
全モジュールは Python 標準ライブラリ + 必要最小限の SDK で構成され、外部フレームワーク (LangChain 等) には依存しない。

このファイルは `モジュール → クラス/関数 → シグネチャ → 使用例` の階層で読めるように整理している。
内部実装の詳細は省略し、呼び出し側が知るべき型・例外・副作用に絞って記述する。

> 自動生成 (pdoc 等) ではなく **手書き** で維持している。理由は [ADR-009](design-decisions.md#adr-009) と
> [`design-decisions.md`](design-decisions.md) を参照。

---

## 目次

- [`backend.src.config`](#backendsrcconfig)
- [`backend.src.loader`](#backendsrcloader)
- [`backend.src.normalizer`](#backendsrcnormalizer)
- [`backend.src.embedder`](#backendsrcembedder)
- [`backend.src.vector_store`](#backendsrcvector_store)
- [`backend.src.search`](#backendsrcsearch)
- [`backend.src.rag`](#backendsrcrag)
- [`backend.src.integrity`](#backendsrcintegrity)
- [`backend.src.marker`](#backendsrcmarker)

---

## `backend.src.config`

プロジェクト全体の設定。環境変数 / `.env` / `config.yml` を解決する。

### `Settings` (frozen dataclass)

| Field | Type | Default | Description |
|---|---|---|---|
| `anthropic_api_key` | `str \| None` | `os.getenv("ANTHROPIC_API_KEY")` | Claude API キー (未設定なら RAG が DUMMY) |
| `gemini_api_key` | `str \| None` | `os.getenv("GEMINI_API_KEY")` | Gemini Embedding API キー (未設定なら Embedder が DUMMY) |
| `chroma_db_path` | `Path` | `Path("./.chromadb")` | ChromaDB の永続ディレクトリ |
| `log_level` | `str` | `"INFO"` | ログレベル |

モジュールロード時に `settings = Settings()` がインスタンス化されるので、通常はそのまま使う。

### `COLLECTION_NAME: str = "axis_knowledge"`

ChromaDB のコレクション名 (プロジェクト全体で 1 本)。

### `configure_logging(level: str | None = None) -> None`

ルートロガーをプロジェクト標準フォーマットで初期化する。CLI エントリポイントから呼ぶ。

### `load_axes_config(path: Path | None = None) -> dict`

`config.yml` を読み込む。存在しない場合は `{"axes": []}` を返す。

**Example**:

```python
from backend.src.config import settings, load_axes_config

print(settings.chroma_db_path)
config = load_axes_config()
for axis in config.get("axes", []):
    print(axis["name"], axis["type"])
```

---

## `backend.src.loader`

Markdown + YAML frontmatter を `Document` データクラスに変換する。

### `Document` (dataclass)

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | `str` | required | frontmatter `id` (グローバル一意) |
| `title` | `str` | required | frontmatter `title` |
| `axes` | `dict[str, Any]` | required | 軸メタデータ (`category` / `topic` / `level` / ...) |
| `tags` | `list[str]` | required | 自由タグ |
| `refs` | `list[str]` | required | 参照先 ID のリスト |
| `body` | `str` | required | Markdown 本文 (frontmatter を除く) |
| `path` | `Path` | required | ソースファイルパス |
| `raw_meta` | `dict[str, Any]` | `{}` | frontmatter 全体 (拡張用) |
| `normalized_title` | `str` | `""` | normalize 後の title (normalizer 渡した場合のみ) |
| `normalized_body` | `str` | `""` | normalize 後の body |
| `normalized_axes` | `dict[str, str]` | `{}` | normalize 後の axes 値 |
| `normalized_tags` | `list[str]` | `[]` | normalize 後の tags |

### `LoaderError(Exception)`

ファイル不在 / 必須フィールド欠落 / frontmatter パース失敗時に送出。

### `load_document(path: Path, normalizer: Normalizer | None = None) -> Document`

Markdown ファイルを 1 件読み込む。`normalizer` を渡すと `normalized_*` フィールドが populate される。

**Raises**: `LoaderError` — ファイル不在 / `id` または `title` 欠落 / frontmatter パース失敗。

**Example**:

```python
from pathlib import Path
from backend.src.loader import load_document
from backend.src.normalizer import Normalizer

doc = load_document(Path("examples/knowledge/01-rag-patterns.md"), normalizer=Normalizer())
print(doc.id, doc.title, doc.axes)
print(doc.normalized_title)  # NFKC + lowercase 済み
```

### `load_directory(dir_path: Path, *, pattern: str = "*.md", strict: bool = False, normalizer: Normalizer | None = None) -> list[Document]`

ディレクトリ配下を一括ロード。

- `pattern`: glob パターン (`**/*.md` で再帰)
- `strict`: True で最初の `LoaderError` で raise、False (デフォルト) で WARN ログを出して該当ファイルをスキップ

**Raises**: `LoaderError` (ディレクトリ不在 / 非ディレクトリ / `strict=True` 時の個別エラー)。

**Example**:

```python
docs = load_directory(Path("examples/knowledge"), normalizer=Normalizer())
print(f"Loaded {len(docs)} documents")
```

### CLI

```bash
python -m backend.src.loader <directory>
```

各ドキュメントの id / title / axes / tags / refs / 本文長を表示する。

---

## `backend.src.normalizer`

日本語ナレッジの表記ゆれを吸収する正規化パイプライン (NFKC + カナ統一 + lowercase)。
詳細は [`normalizer.md`](normalizer.md) を参照。

### `NormalizerOptions` (frozen dataclass)

| Field | Type | Default | Description |
|---|---|---|---|
| `nfkc` | `bool` | `True` | `unicodedata.normalize("NFKC", ...)` を適用 |
| `katakana_to_hiragana` | `bool` | `True` | U+30A1–30F6 を U+3041–3096 にシフト |
| `lowercase` | `bool` | `True` | `str.lower()` を適用 |

### `normalize_text(text: str, options: NormalizerOptions | None = None) -> str`

純粋関数。1 ステップずつ適用順序通りに変換する。

### `Normalizer`

stateful なラッパ。`__call__(text) -> str` で関数オブジェクトとしても使える。

#### `Normalizer.__init__(options: NormalizerOptions | None = None)`

#### `Normalizer.from_config(config: dict) -> Normalizer`

`config["normalization"]` 部から `NormalizerOptions` を構築。
キーは `nfkc` / `katakana_to_hiragana` / `lowercase`。

#### `Normalizer.__call__(text: str) -> str`

#### `Normalizer.options -> NormalizerOptions` (property)

**Example**:

```python
from backend.src.normalizer import Normalizer, NormalizerOptions, normalize_text

# 関数として使う
assert normalize_text("ＲＡＧ パターン") == "ragパターン"  # NFKC で 半角化, lowercase

# クラスとして使う (config.yml 連携)
import yaml
config = yaml.safe_load(open("config.yml"))
normalizer = Normalizer.from_config(config)
assert normalizer("カタカナ") == "かたかな"

# オプション無効化
n2 = Normalizer(NormalizerOptions(katakana_to_hiragana=False))
assert n2("カタカナ") == "カタカナ"
```

---

## `backend.src.embedder`

Gemini `text-embedding-004` ラッパ + 決定的 DUMMY フォールバック。

### `EMBEDDING_DIM: int = 768`

出力ベクトルの次元。Gemini text-embedding-004 と一致。

### `Embedder`

#### `Embedder.__init__(*, force_dummy: bool = False)`

- `force_dummy=True` または `GEMINI_API_KEY` 未設定の場合 → DUMMY モード
- DUMMY モードでは SHA256 ハッシュから 768 次元ベクトルを決定的に生成する

#### `Embedder.is_dummy -> bool` (property)

#### `Embedder.embed(text: str) -> list[float]`

単一テキストを 768 次元ベクトル化。

#### `Embedder.embed_batch(texts: Sequence[str]) -> list[list[float]]`

バッチ版。内部では逐次的に `embed()` を呼ぶ (Gemini SDK の batch API 非利用)。

**Example**:

```python
from backend.src.embedder import Embedder

# CI / ローカル開発用
embedder = Embedder(force_dummy=True)
vec = embedder.embed("RAG とは")
assert len(vec) == 768
assert embedder.is_dummy

# 本番
embedder = Embedder()  # GEMINI_API_KEY が設定されていれば実 API
vecs = embedder.embed_batch(["RAG とは", "ベクトル検索とは"])
```

---

## `backend.src.vector_store`

ChromaDB `PersistentClient` ラッパ。axis メタデータを flatten 保存する。

### `VectorStore`

#### `VectorStore.__init__(path: Path | None = None, *, in_memory: bool = False)`

- `in_memory=True` で `EphemeralClient` (テスト用)
- それ以外は `path or Path("./.chromadb")` に `PersistentClient` を作成

コレクション名は `config.COLLECTION_NAME` (= `"axis_knowledge"`) で固定。

#### `VectorStore.upsert(doc: Document, embedding: list[float]) -> None`

Document + 768 次元ベクトルを 1 件 insert/update。metadata は以下のキーで保存:

- `title` / `title_norm` / `path` / `tags` (カンマ区切り) / `tags_norm` / `refs` (カンマ区切り)
- 各軸につき `axis_<key>` (生の値) と `axis_<key>_norm` (正規化値)

#### `VectorStore.upsert_many(docs: list[Document], embeddings: list[list[float]]) -> None`

バッチ版。`len(docs) != len(embeddings)` で `ValueError`。

#### `VectorStore.count() -> int`

#### `VectorStore.query(embedding: list[float], *, n_results: int = 5, where: dict[str, Any] | None = None) -> dict[str, Any]`

Chroma の raw query 結果を返す (`ids` / `distances` / `metadatas` / `documents` を含む dict)。
SearchEngine が `_to_results()` で `SearchResult` に変換する想定。

#### `VectorStore.reset() -> None`

コレクションを drop して作り直す。`scripts/build_index.py --reset` の実体。

**Example**:

```python
from pathlib import Path
from backend.src.vector_store import VectorStore
from backend.src.loader import load_directory
from backend.src.embedder import Embedder
from backend.src.normalizer import Normalizer

store = VectorStore(in_memory=True)
embedder = Embedder(force_dummy=True)
normalizer = Normalizer()

docs = load_directory(Path("examples/knowledge"), normalizer=normalizer)
embeddings = embedder.embed_batch([d.normalized_body for d in docs])
store.upsert_many(docs, embeddings)
print(store.count())  # ドキュメント数

# 検索
q_vec = embedder.embed("RAG")
raw = store.query(q_vec, n_results=3, where={"axis_category_norm": "技術記事"})
```

---

## `backend.src.search`

軸フィルタ + ベクトル検索の hybrid SearchEngine。

### `SearchResult` (dataclass)

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | `str` | required | ドキュメント ID |
| `title` | `str` | required | 生の title (UI 表示用) |
| `score` | `float` | required | cosine 類似度を 0.0〜1.0 にクリップしたスコア |
| `axes` | `dict[str, Any]` | required | 生の軸メタデータ (UI 表示用) |
| `body_snippet` | `str` | required | 本文の先頭抜粋 (改行除去、200 字制限) |
| `path` | `str` | required | ソースファイルパス |
| `refs` | `list[str]` | `[]` | refs フィールド (カンマ区切りから復元) |

### `SearchEngine`

#### `SearchEngine.__init__(store: VectorStore, embedder: Embedder, normalizer: Normalizer | None = None)`

`normalizer` 未指定時はデフォルト `Normalizer()` (全オプション on)。

#### `SearchEngine.search(query: str | None, *, filters: dict[str, Any] | None = None, top_k: int = 5) -> list[SearchResult]`

- `query=None`: 軸 filter のみで検索 (ベクトルはゼロベクトル、結果順序は arbitrary)
- `filters`: ユーザー用キー (`{"category": "技術記事"}`)。内部で normalize して `axis_*_norm` に変換
- `top_k`: 上限件数

クエリも filter も normalize 経由で渡るので、表記ゆれを吸収して検索できる。

**Example**:

```python
from backend.src.search import SearchEngine

# 引数の組み立ては VectorStore / Embedder の例を参照
engine = SearchEngine(store, embedder, normalizer)
results = engine.search("RAG とは", filters={"category": "技術記事"}, top_k=5)
for r in results:
    print(f"[{r.score:.3f}] {r.id} {r.title}")
    print(f"  axes={r.axes}")
    print(f"  snippet={r.body_snippet}")
```

### CLI

```bash
python -m backend.src.search "RAG とは" --category 技術記事 --top 5
```

---

## `backend.src.rag`

Claude API を使った RAG パイプライン (retrieve → generate)。

### `DEFAULT_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")`

### `SYSTEM_PROMPT: str`

回答生成用のシステムプロンプト (出典 `[doc_NNN]` の付与ルールを含む)。

### `CITATION_RE = re.compile(r"\[(doc_\d+)\]")`

生成テキストから出典 ID を抽出する正規表現。

### `Answer` (dataclass)

| Field | Type | Default | Description |
|---|---|---|---|
| `text` | `str` | required | 生成された回答テキスト |
| `sources` | `list[SearchResult]` | `[]` | retrieval した上位 K 件 |
| `cited_ids` | `list[str]` | `[]` | `[doc_NNN]` から抽出した出典 ID (sorted unique) |
| `is_dummy` | `bool` | `False` | DUMMY モードで生成された場合 True |
| `model` | `str \| None` | `None` | 実際に使ったモデル名 (`"dummy"` も含む) |

### `RAGPipeline`

#### `RAGPipeline.__init__(engine: SearchEngine, *, force_dummy: bool = False, model: str = DEFAULT_MODEL)`

- `force_dummy=True` または `ANTHROPIC_API_KEY` 未設定 → DUMMY モード
- DUMMY 応答は固定フォーマット (最上位 1 件の id + 抜粋)

#### `RAGPipeline.is_dummy -> bool` (property)

#### `RAGPipeline.answer(question: str, *, filters: dict[str, Any] | None = None, top_k: int = 5, max_tokens: int = 1024) -> Answer`

retrieve → context 整形 → Claude `messages.create` → 出典抽出。
DUMMY モードでは Claude を呼ばず固定文字列を返す。

**Example**:

```python
from backend.src.rag import RAGPipeline

rag = RAGPipeline(engine)  # ANTHROPIC_API_KEY が無ければ自動 DUMMY
answer = rag.answer("RAG の構成要素は?", filters={"category": "技術記事"})
print(answer.text)
print("Cited:", answer.cited_ids)
for s in answer.sources:
    mark = "*" if s.id in answer.cited_ids else " "
    print(f"  {mark} [{s.score:.3f}] {s.id} {s.title}")
```

### CLI

```bash
python -m backend.src.rag "RAG とは" --category 技術記事 --top 5
```

---

## `backend.src.integrity`

ナレッジベースの参照整合性を検証する。詳細は [`integrity.md`](integrity.md) を参照。

### `BrokenRef` (dataclass)

| Field | Type | Description |
|---|---|---|
| `source_id` | `str` | 参照元 ID |
| `source_path` | `str` | 参照元ファイルパス |
| `target_id` | `str` | 参照先 (= 存在しない ID) |

### `IntegrityReport` (dataclass)

| Field | Type | Default | Description |
|---|---|---|---|
| `total_docs` | `int` | `0` | 検査ドキュメント数 |
| `total_refs` | `int` | `0` | refs エントリ総数 |
| `broken_refs` | `list[BrokenRef]` | `[]` | 壊れリンク一覧 |
| `orphan_docs` | `list[str]` | `[]` | 誰からも参照されない doc ID 一覧 |
| `cycles` | `list[list[str]]` | `[]` | 循環参照パス一覧 |
| `docs_by_id` | `dict[str, str]` | `{}` | id → path 逆引き |

#### `IntegrityReport.has_errors -> bool` (property)

`broken_refs` が 1 件以上で True。`--strict` フラグの判定に使う。

#### `IntegrityReport.as_dict() -> dict[str, Any]`

JSON シリアライズ用。

### `IntegrityChecker`

#### `IntegrityChecker.check(docs: list[Document]) -> IntegrityReport`

- 壊れリンク検出 (O(n × avg_refs))
- 孤立ドキュメント検出 (O(n))
- 循環参照検出 (DFS WHITE/GRAY/BLACK 3 色法、自己参照も検出)

### `format_report(report: IntegrityReport) -> str`

テキスト表示用フォーマッタ。CLI と Python から両方使える。

**Example**:

```python
from pathlib import Path
from backend.src.loader import load_directory
from backend.src.integrity import IntegrityChecker, format_report

docs = load_directory(Path("examples/knowledge"))
report = IntegrityChecker().check(docs)
print(format_report(report))

if report.has_errors:
    raise SystemExit(1)
```

### CLI

```bash
python -m backend.src.integrity examples/knowledge          # テキスト出力
python -m backend.src.integrity examples/knowledge --json   # JSON 出力
python -m backend.src.integrity examples/knowledge --strict # 壊れリンクで exit 1
```

---

## `backend.src.marker`

`<!-- AUTO_GENERATED_START: <name> -->` ブロックの抽出・更新・削除・検証。
詳細は [`marker.md`](marker.md) を参照。

### `NAME_PATTERN: str = r"[a-zA-Z0-9_-]+"`

許容されるブロック名のパターン。スペース・記号は不可。

### `MarkerBlock` (dataclass)

| Field | Type | Description |
|---|---|---|
| `name` | `str` | ブロック名 (例: `"summary"`) |
| `content` | `str` | デリミタを除いた内側のテキスト |
| `raw_full` | `str` | デリミタ込みのマッチ文字列 |

### `MarkerError(Exception)`

`update_block()` に無効な名前 (`NAME_PATTERN` 不一致) を渡したときに送出。

### `extract_blocks(text: str) -> list[MarkerBlock]`

文書内の全 AUTO_GENERATED ブロックを **ドキュメント順** で返す。

### `validate_balance(text: str) -> list[str]`

START/END の対応を検証し、エラーメッセージのリストを返す。空リストで balanced。

### `update_block(text: str, name: str, new_content: str) -> str`

指定名のブロック内容を `new_content` で置換。存在しない場合は末尾に追加する。
**戻り値は新しい文字列**。元ファイルへの書き込みは呼び出し側の責務。

### `strip_blocks(text: str) -> str`

全 AUTO_GENERATED ブロック (デリミタ込み) を削除した文字列を返す。
"human-only 版" を作る用途。

**Example**:

```python
from pathlib import Path
from backend.src.marker import extract_blocks, update_block, strip_blocks, validate_balance

path = Path("examples/knowledge/01-rag-patterns.md")
text = path.read_text(encoding="utf-8")

# 一覧
for b in extract_blocks(text):
    print(f"{b.name}: {len(b.content)} chars")

# 検証
errs = validate_balance(text)
assert not errs, errs

# 更新 (存在しなければ末尾に追加)
new_text = update_block(text, "summary", "RAG = Retrieval-Augmented Generation。")
path.write_text(new_text, encoding="utf-8")

# 人間記述だけ抜き出す
human_only = strip_blocks(text)
```

### CLI

```bash
python -m backend.src.marker <file> --list
python -m backend.src.marker <file> --validate
python -m backend.src.marker <file> --update --name summary --content "..."
python -m backend.src.marker <file> --strip
```

---

## 例外階層 まとめ

```
Exception
├── LoaderError       (loader.py)         ファイル不在 / 必須フィールド欠落
└── MarkerError       (marker.py)         無効なブロック名
```

他のモジュールはドメイン例外を投げず、`ValueError` / `Chroma` 由来の例外を素通しする。

---

## 型の安全性

- 全 public API には PEP 604 (`X | None`) 型ヒントが付いている
- 型チェッカ (mypy / pyright) は現時点で CI に組み込んでいない (理由: [ADR-009](design-decisions.md#adr-009))
- v0.3 (Next.js 移行) のタイミングで `mypy --strict` 導入を再評価する
