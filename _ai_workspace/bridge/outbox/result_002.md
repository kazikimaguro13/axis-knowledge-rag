# result_002: Day 2 — embedder.py + vector_store.py + build_index

- **Spec**: `inbox/spec_002.md`
- **Executor**: Claude Code (dev-b / kazikimaguro13)
- **Started**: 2026-05-12 (Day 2)
- **Finished**: 2026-05-12
- **Status**: partial

> 完成度: コードは spec どおり実装・コミット・push 済み。ただしローカル実行環境 (Windows 11 + Python 3.12) で **chromadb の Rust コアが access violation で落ちる** ため、`build_index` と vector_store テストはこの PC では走らせきれていない。embedder 側は DUMMY モードで全 PASS。CI (Linux) では問題なく走る想定。

## 1. 要約

- `backend/src/embedder.py` を新規実装。`GEMINI_API_KEY` 未設定時は SHA-256 ベースの deterministic 768-dim ベクトルを返す DUMMY モードで動作 (CI / オフライン dev 対応)。
- `backend/src/vector_store.py` を新規実装。ChromaDB の PersistentClient / EphemeralClient を切替可能にし、`Document.axes` を `axis_*` プレフィックスで平坦化して metadata に保存。
- `scripts/build_index.py` を新規追加。`python -m scripts.build_index ./examples/knowledge --reset` の I/F で動くようにした。
- 依存ライブラリ (`google-generativeai>=0.7.0`, `chromadb>=0.5.0`) を `pyproject.toml` / `backend/requirements.txt` に追加。
- `config.py` に `COLLECTION_NAME = "axis_knowledge"` 定数を追加 (search.py が同じ名前を引けるように)。
- assert ベースの smoke test を 2 本追加。embedder は全 PASS、vector_store は **chromadb 1.5.9 が Windows で segfault するため未確認**。
- dev-b (kazikimaguro13) で `git push origin main` 済み。6 commit。

## 2. 変更ファイル

```
 CHANGELOG.md                       |   8 +++
 backend/requirements.txt           |   2 +
 backend/src/config.py              |   2 +
 backend/src/embedder.py            |  57 +++++++++++++++++++
 backend/src/vector_store.py        |  96 ++++++++++++++++++++++++++++++++
 backend/tests/test_embedder.py     |  58 ++++++++++++++++++++
 backend/tests/test_vector_store.py | 109 +++++++++++++++++++++++++++++++++++++
 pyproject.toml                     |   2 +
 scripts/__init__.py                |   0
 scripts/build_index.py             |  46 ++++++++++++++++
 10 files changed, 380 insertions(+)
```

`.gitignore` / `.env.example` は Day 1 で既に `.chromadb/` / `GEMINI_API_KEY` が入っていたため変更なし。

## 3. 主要な変更点（ハイライト）

### `backend/src/embedder.py`

```python
class Embedder:
    def __init__(self, *, force_dummy: bool = False) -> None:
        self._use_dummy = force_dummy or not settings.gemini_api_key
        if self._use_dummy:
            logger.warning("Embedder running in DUMMY mode (no GEMINI_API_KEY)")
        else:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            self._genai = genai
```

- spec のコード例どおりに実装。`force_dummy=True` でテストから明示的に DUMMY を選べる。
- `_dummy_embedding` は `SHA-256(text)` を 768 次元に詰めて `[-1, 1)` 正規化。意味的な意味は無いが、deterministic なので往復テストに使える。

### `backend/src/vector_store.py`

```python
COLLECTION_NAME を config.py から import。
_flatten_axes が dict[str|int|float|bool|...] → axis_<key> に平坦化。
EphemeralClient(in_memory=True) と PersistentClient(path=...) を切替。
```

- `axes` がスカラ以外 (list, dict など) の場合は `str(v)` にフォールバック。search.py 側で文字列マッチで引ける。
- `reset()` は `delete_collection` → `get_or_create_collection` の組合せ。collection が存在しないときに raise されるパスを try/except で握りつぶし。

### `backend/src/config.py`

```diff
+ COLLECTION_NAME = "axis_knowledge"
```

vector_store.py から `from backend.src.config import COLLECTION_NAME` で参照。search.py (Day 3) も同じ定数を引ける。

### `scripts/build_index.py`

```python
docs = load_directory(args.knowledge_dir)
store = VectorStore(path=args.db_path)
if args.reset:
    store.reset()
embedder = Embedder()
embeddings = embedder.embed_batch([d.body for d in docs])
store.upsert_many(docs, embeddings)
```

spec の通り。`--reset` と `--db-path` を引数化。

### tests

- `test_embedder.py`: dim=768 / determinism / 異テキスト→異ベクトル / batch shape の 4 ケース。
- `test_vector_store.py`: upsert→count / upsert_many+query / reset→0 / 長さ不一致 raise / `axis_category` フィルタの 5 ケース。

## 4. テスト・品質チェック結果

```
$ python -m backend.tests.test_loader
PASS: test_load_minimal_document
PASS: test_missing_id_raises
PASS: test_load_directory_skips_bad_files
PASS: test_strict_mode_raises_on_bad_file

$ python -m backend.tests.test_embedder
Embedder running in DUMMY mode (no GEMINI_API_KEY)
... (4回)
PASS: test_dummy_returns_correct_dim
PASS: test_dummy_is_deterministic
PASS: test_dummy_differs_across_texts
PASS: test_embed_batch_shape

$ python -m backend.tests.test_vector_store
Embedder running in DUMMY mode (no GEMINI_API_KEY)
Windows fatal exception: access violation
  File "C:\...\chromadb\api\rust.py", line 509 in _upsert
  File "C:\...\chromadb\api\models\Collection.py", line 489 in upsert
  File "...\backend\src\vector_store.py", line 57 in upsert
  ...
[exit code 5 — segfault on first upsert]

$ python -m scripts.build_index ./examples/knowledge --reset
(同じ Rust 拡張で segfault するため未実行)

$ git log --oneline -6
af0f846 docs: add Day 2 entry to CHANGELOG
d92488f test: add smoke tests for embedder and vector_store
5794eb9 feat: add scripts/build_index.py to index knowledge directory
90440a1 feat: implement ChromaDB vector store wrapper
2d93aac feat: implement Gemini embedder with dummy fallback for CI
9b5922a chore: add chromadb and google-generativeai to dependencies

$ git push origin main
   a9039a9..af0f846  main -> main
```

### LangChain / LlamaIndex のチェック

```
$ grep -RIn "langchain\|llama_index" backend scripts
(no match)
```

OK、import していない。

## 5. 想定外だったこと / 判断ポイント

### 5-1. ChromaDB 1.5.9 が Windows 11 + Python 3.12 で segfault する（最大の事件）

`spec >=0.5.0` 指定で `pip install` すると最新の `chromadb==1.5.9` が入る。これが **`collection.upsert(...)` 内部の Rust binding (`chromadb/api/rust.py` の `self.bindings.upsert`) で Windows fatal exception: access violation を起こす**。`.add()` でも同じ場所で落ちる。

調査履歴:
- chromadb 1.5.9 → segfault
- chromadb 1.4.1 → segfault (同じ場所)
- chromadb 1.0.21 → segfault (同じ場所)
- chromadb 1.0.0 → 拒否 (chroma-hnswlib のビルドに MSVC++ 14 が必要)
- chromadb 0.6.3 → 同上、ビルド不可
- chromadb 0.5.x → 同上、ビルド不可
- `anonymized_telemetry=False` / `posthog` uninstall / `add` への置き換え → 全て同じ場所で segfault

つまり「Windows で wheel が落ちてくる chromadb 1.x 系統」と「自前ビルドが必要な 0.x 系統」しか選択肢がなく、前者が壊れていて、後者は MSVC が無いと入らない。Linux/macOS/CI 上では問題なく動くはず（Chroma の Rust 拡張は manylinux で広く動作報告あり）。

**判断**: spec 通りの実装をそのまま push する。これは Chroma 側の Windows wheel のバグで、自分の実装ミスではない。**vector_store コードと build_index は Linux/CI 上でユーザーが走らせて初めて検証完了**となる。requirements.txt のバージョン制約は spec の `>=0.5.0` のままにしてあるが、Windows ユーザー向けに将来 `chromadb>=0.5.0,!=1.5.9,...` のような除外指定が要るかもしれない（Open question にも書いた）。

### 5-2. GEMINI_API_KEY が未設定だった

実機 (`.env` 無し) では DUMMY モードでしか確認できなかった。`Embedder()` の通常コンストラクタ → `is_dummy == True` → `_dummy_embedding` 経路は通っている。Gemini 本番 API 呼び出しパス (`self._genai.embed_content(...)`) は **コードレビューレベルでしか確認していない**。`google.generativeai>=0.7.0` の `embed_content` シグネチャ自体は変わっていない想定だが、API キーを入れて手動確認するのはユーザー側で必要。

### 5-3. ChromaDB のディスク使用量 (`du -sh .chromadb`)

build_index が走らないため `.chromadb/` ディレクトリは未生成。**測定不能**。参考までに Chroma の PersistentClient は SQLite + HNSW で、5 docs / 768-dim ベクトルなら 1〜5MB 程度に収まる見込み。

### 5-4. Gemini API の rate limit 実機検証

API キーが手元に無いので **未実施**。`google.generativeai.embed_content` は `ResourceExhausted` 例外を投げる想定（gRPC ステータス 429）。今は `try/except` を入れていないので、本番でレート制限に当たった場合は build_index がクラッシュする。spec_003 以降 or 別 spec で `tenacity` での retry + backoff 入れた方がよさそう（Section 8 に提案を書いた）。

### 5-5. ChromaDB 1.5.x の `upsert` API は存在する

spec section 6 で「`upsert` が無ければ `add` で代替」とあったが、1.5.x には両方ある。`upsert` をそのまま使った。

### 5-6. commit 数

spec 3-6 は「3〜6 個」と幅があり、example が 5 commits だったが、CHANGELOG を独立コミットにしたかったので 6 commits にした。prefix 規約 (`chore:` / `feat:` / `test:` / `docs:`) は spec_001 と同じ。

## 6. Open questions

- **Q1: Windows サポート方針**
  chromadb の Rust 拡張が Windows 11 + Python 3.12 で segfault する件、ローカル開発を Windows でする場合の workaround をどう用意するか？
  選択肢:
   1. README に「Windows は WSL2 推奨」と書く
   2. Python 3.11 にダウングレード推奨 (未検証だが、wheel ビルドが違う可能性)
   3. chromadb の Windows-only wheel をどこかから持ってくる (要調査)
   4. 開発時のローカル vector store を pluggable にして、Windows では sqlite-vss / lancedb 等にフォールバック (v0.4 の範囲かも)

  **判断不能だった**ので Open question として残す。とりあえず spec_003 (Day 3) は CI (Linux) 前提で進めるのが現実的。
- **Q2: requirements の chromadb バージョンピン**
  上記が解決するまで Windows 開発者が壁にぶつかる。`chromadb>=0.5.0,<1.5.10` のような明示的な不良バージョン除外を入れるべきか、それとも一律に「Linux/macOS 推奨」と諦めるか？

## 7. 動作確認手順（ユーザー）

### 7-1. Linux / macOS / WSL2 / CI で実行する場合（推奨）

```
1. git pull origin main
2. python -m pip install -e .
3. (任意) export GEMINI_API_KEY=AIzaSyxxxxx   # 設定すれば GEMINI mode
4. python -m backend.tests.test_embedder
5. python -m backend.tests.test_vector_store
6. python -m scripts.build_index ./examples/knowledge --reset
7. du -sh .chromadb
```

期待結果:
- 4: 4 件すべて PASS
- 5: 5 件すべて PASS
- 6:
   ```
   Indexed 5 documents into .chromadb
   Total in collection: 5
   Embedder mode: DUMMY  (or GEMINI)
   ```
- 7: 数MB 程度

### 7-2. Windows ネイティブで実行する場合

embedder までは PASS する。vector_store + build_index は **現状 segfault する**ので、WSL2 か Linux 環境で動かすこと。

```
1. python -m backend.tests.test_embedder
   → 期待: 4 件 PASS

2. python -m backend.tests.test_vector_store
   → 現状: Windows fatal exception: access violation (chromadb 側 Rust 拡張の Windows wheel のバグ)
```

## 8. 次の提案（任意）

- **spec_003 候補 (元々の予定)**: `search.py` — `VectorStore.query(where={"axis_*": ...})` を呼んでハイブリッド検索。Day 3 のメイン。
- **spec_003.5 候補 (今回見つけた追加事項)**:
   - Gemini API の retry + backoff (`tenacity` か手書き) を `Embedder.embed_batch` に入れる。rate limit (429) と 5xx を再試行。
   - chromadb の Windows 互換問題を README + docs にまとめる。WSL2 セットアップ手順 or 「動かない時のエラーメッセージ集」を docs/troubleshooting.md として独立させる。
- **v0.4 候補**: VectorStore をプラガブル化 (`AbstractVectorStore` インターフェース)。ChromaDB だけでなく sqlite-vss / lancedb / Qdrant 等に差し替えられるようにすると、上記 Windows 問題も含めて取り回しが楽になる。
