# result_001: Day 1 — プロジェクト初期化 + loader.py 実装

- **Spec**: `inbox/spec_001.md`
- **Executor**: Claude Code (`dev-b`)
- **Started**: 2026-05-12
- **Finished**: 2026-05-12
- **Status**: done

## 1. 要約

Day 1 のスケルトン (pyproject, .env.example, .gitignore, LICENSE, config.yml, CHANGELOG, README) を作成し、`backend/` パッケージ配下に `config.py` と Day 1 主成果物の `loader.py` を実装。`examples/knowledge/` にサンプル Markdown 5本 (うち 1 本は Week 2 検証用に壊れ refs を仕込み済み) を配置。`pip install -e .` が成功、`python -m backend.src.loader ./examples/knowledge` で 5 件 Document を表示、`python -m backend.tests.test_loader` が 4/4 PASS。dev-b アカウント (`kazikimaguro13`) で `origin/main` に 6 コミットを push 済み。

## 2. 変更ファイル

```
 .env.example                                |   9 ++
 .gitignore                                  |  68 ++++++++++++++
 CHANGELOG.md                                |   8 ++
 LICENSE                                     |  21 +++++
 README.md                                   |  25 ++++-
 backend/__init__.py                         |   0
 backend/requirements.txt                    |   3 +
 backend/src/__init__.py                     |   0
 backend/src/config.py                       |  34 +++++++
 backend/src/loader.py                       | 138 ++++++++++++++++++++++++++++
 backend/tests/__init__.py                   |   0
 backend/tests/test_loader.py                |  89 ++++++++++++++++++
 config.yml                                  |  26 ++++++
 examples/knowledge/01-rag-patterns.md       |  22 +++++
 examples/knowledge/02-vector-search.md      |  22 +++++
 examples/knowledge/03-yaml-frontmatter.md   |  22 +++++
 examples/knowledge/04-claude-skills.md      |  22 +++++
 examples/knowledge/05-prompt-engineering.md |  24 +++++
 pyproject.toml                              |  36 ++++++++
 requirements.txt                            |   3 +
 20 files changed, 571 insertions(+), 1 deletion(-)
```

## 3. 主要な変更点（ハイライト）

### `backend/src/loader.py`

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


def load_document(path: Path) -> Document: ...
def load_directory(dir_path: Path, *, pattern: str = "*.md", strict: bool = False) -> list[Document]: ...
```

仕様書セクション 5.1 のフォーマットを 1 ファイル単位で読む `load_document`、ディレクトリを一括で読む `load_directory` の 2 段構成。`load_directory` は `strict=False` (デフォルト) で失敗ファイルを WARN ログ + skip、`strict=True` で `LoaderError` を再送出。CLI (`_main`) は `python -m backend.src.loader <dir>` で利用可能。

### `backend/src/config.py`

```python
@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    chroma_db_path: Path = Path(os.getenv("CHROMA_DB_PATH", "./.chromadb"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
```

`python-dotenv` で `.env` を読み込み、frozen dataclass で公開。`configure_logging()` で `[%(levelname)s] %(name)s: %(message)s` フォーマットを統一。

### `examples/knowledge/*.md`

5 本のサンプル。`doc_002 -> doc_001`、`doc_004 -> doc_001, doc_003` の有効リンクと、`doc_005 -> doc_999` の意図的な壊れリンク (Week 2 の `integrity.py` 検証用) を持つ。

### `pyproject.toml`

```toml
[project]
name = "axis-knowledge-rag"
version = "0.1.0.dev0"
requires-python = ">=3.11"
authors = [{ name = "Nakashima" }]
dependencies = ["python-frontmatter>=1.1.0", "python-dotenv>=1.0.0", "pyyaml>=6.0"]

[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]
```

`authors` の `email` は spec の `<your-email>` プレースホルダが setuptools の idn-email 検証で弾かれたため一旦削除 (詳細は 5 章)。

## 4. テスト・品質チェック結果

```
$ python -m pip install -e .
Successfully installed axis-knowledge-rag-0.1.0.dev0 python-frontmatter-1.1.0
(python-dotenv-1.2.2 / pyyaml-6.0.3 はすでに satisfied)

$ python -m backend.src.loader ./examples/knowledge
[INFO] __main__: Loaded 5/5 documents from examples\knowledge

=== Loaded 5 documents from examples\knowledge ===

- [doc_001] RAGアーキテクチャの設計判断
    axes: {'category': '技術記事', 'topic': 'RAG', 'level': '中級', 'author': 'Nakashima', 'year': 2026}
    tags: ['llm', 'vector-search', 'architecture']  refs: []
    body: 505 chars

- [doc_002] ベクトル検索とコサイン類似度の実務
    axes: {'category': '技術記事', 'topic': 'ベクトル検索', 'level': '中級', 'author': 'Nakashima', 'year': 2026}
    tags: ['embedding', 'similarity', 'chromadb']  refs: ['doc_001']
    body: 520 chars

- [doc_003] YAML frontmatter によるメタデータ設計
    axes: {'category': 'メモ', 'topic': 'メタデータ設計', 'level': '初級', 'author': 'Nakashima', 'year': 2026}
    tags: ['yaml', 'frontmatter', 'metadata']  refs: []
    body: 508 chars

- [doc_004] Claude API と Skills の使い分け
    axes: {'category': '技術記事', 'topic': 'Claude', 'level': '中級', 'author': 'Nakashima', 'year': 2026}
    tags: ['claude', 'llm', 'skills']  refs: ['doc_001', 'doc_003']
    body: 464 chars

- [doc_005] プロンプトエンジニアリングの実務原則
    axes: {'category': '技術記事', 'topic': 'プロンプト', 'level': '上級', 'author': 'Nakashima', 'year': 2026}
    tags: ['prompt', 'llm', 'design']  refs: ['doc_999']
    body: 616 chars

$ python -m backend.tests.test_loader
Skipping <tmp>/bad.md: Missing required 'id' field in <tmp>/bad.md
PASS: test_load_minimal_document
PASS: test_missing_id_raises
PASS: test_load_directory_skips_bad_files
PASS: test_strict_mode_raises_on_bad_file
EXIT=0

$ git log --oneline -7
a9039a9 chore: pin loader-stage dependencies in backend/requirements.txt
12f1999 docs: add 5 sample knowledge documents under examples/knowledge
75f87b6 test: add smoke tests for loader (assert-based, no pytest yet)
8a191ce feat: implement Markdown + YAML frontmatter loader (loader.py)
1e776da feat: add backend package layout and config.py
cb08564 feat: initial project skeleton (pyproject, license, readme, gitignore, changelog)
5bbb0c5 Initial commit

$ git push origin main
   5bbb0c5..a9039a9  main -> main
```

LangChain / LlamaIndex の grep: ヒットなし (`backend/` 配下、`pyproject.toml` ともに 0 件)。

## 5. 想定外だったこと / 判断ポイント

- **`pyproject.toml` の `authors[].email` プレースホルダで install 失敗**: spec の `email = "<your-email>"` をそのまま入れると、setuptools の pyproject 検証で `must be idn-email` エラー。`<your-email>` は spec 上「ここを後で埋める」マーカーと解釈し、Day 1 段階では email キーごと削除 (`authors = [{ name = "Nakashima" }]`) して install を通した。後で実メールを埋めるべき箇所として認識。
- **Python バージョン**: ローカル環境は 3.12.10。spec の `requires-python = ">=3.11"` を満たしているので変更せず。
- **CRLF 警告**: Windows で `core.autocrlf` が有効なため `git add` で大量の `LF will be replaced by CRLF` 警告。spec の「ファイル末尾に空行 1 個、改行コード LF」はワーキングディレクトリ上の宣言であり、git の autocrlf を上書きしないことに留めた (リポジトリ正規化を Day 1 で触ると影響範囲が大きいため、必要なら別 spec で `.gitattributes` 追加)。
- **`backend/requirements.txt` の位置**: spec のコミット計画では「2 コミット目に含める or 6 コミット目」とあったので、6 コミット目 `chore:` 単独に分離 (履歴の意図が読みやすい)。
- **GitHub 認証**: `git remote -v` が `https://github.com/kazikimaguro13/axis-knowledge-rag.git` を指し、`git config user.name` が `kazikimaguro13`。`git push origin main` は `5bbb0c5..a9039a9  main -> main` で成功。標準エラーに `git: 'credential-manager-core' is not a git command` という古い credential helper 設定の残骸メッセージが出たが、push 自体は完了している (ローカル Git Credential Manager が後段で正しく動いたため)。誤アカウント push のリスクなし。

## 6. Open questions

なし。

## 7. 動作確認手順（ユーザー）

```
1. cd C:\Users\cocor\Desktop\就活\axis-knowledge-rag
2. python -m pip install -e .         # 既に Day 1 で実行済み、再実行しても idempotent
3. python -m backend.src.loader ./examples/knowledge
4. python -m backend.tests.test_loader
5. GitHub 上で https://github.com/kazikimaguro13/axis-knowledge-rag のコミット履歴を確認
```

期待結果:
- 手順 3: `Loaded 5/5 documents from examples\knowledge` のログ + 5 件の Document リスト表示
- 手順 4: `PASS:` が 4 件、`FAIL` / `ERROR` 0 件、終了コード 0
- 手順 5: `cb08564` 〜 `a9039a9` の 6 コミット (`feat:` 3、`test:` 1、`docs:` 1、`chore:` 1) が `Initial commit` の上に積まれている

## 8. 次の提案（任意）

- **spec_002 候補 (Day 2)**: `embedder.py` (Gemini text-embedding-004) + `vector_store.py` (ChromaDB) + `scripts/build_index.py`。`load_directory` の戻り値 `list[Document]` をそのまま受け取ってインデックス化する想定なので、loader 側の API は据え置きで OK。ただし以下 2 点だけ Day 2 着手前に判断したい:
  - **`Document` を frozen/hashable にするか**: 現在は普通の `@dataclass`。ChromaDB へ突っ込む際に `id` を一意キーとして利用するため、複数読み込みでの重複検出を loader 側でやるなら `__hash__` 実装 or frozen 化が必要。Day 2 で重複ポリシー (上書き / エラー / skip) を決めるタイミングで合わせて検討。
  - **Markdown 本文の正規化タイミング**: 現状 `body` は frontmatter 除去後の生テキスト。NFKC や `<!-- AUTO_GENERATED_*** -->` ブロック処理は Week 2 (`normalizer.py` / `marker.py`) で別途行う前提を仕様書通り維持しているが、`load_document` に `preprocess: Callable[[str], str] | None = None` フックを足す案もあり (Day 2 でインデックス化前に挟みたい処理が出るかもしれないので、必要性が見えてから後付けで十分)。
- **`.gitattributes` 追加 spec**: 上記の CRLF 警告を恒久的に黙らせるなら、`* text=auto eol=lf` で line ending を強制したほうが Linux/Mac との混在で事故りにくい。優先度は低。
- **email プレースホルダの埋め直し**: `pyproject.toml` の `authors` に実 email を入れるかどうか (OSS 公開時に晒したくないなら GitHub の `noreply` アドレスに切替)。spec_007 (Day 7 = 5/18) の「v0.1.0 タグ付与とパブリック化」前までに決めれば良い。
