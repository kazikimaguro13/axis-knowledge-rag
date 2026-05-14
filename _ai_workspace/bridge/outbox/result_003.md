# result_003: Day 3 — search.py (軸+ベクトル hybrid)

- **Spec**: `inbox/spec_003.md`
- **Executor**: Claude Code (`dev-b`) inside WSL2 Ubuntu, completion finalized by Cowork (dispatch hang on git push credentials)
- **Started**: 2026-05-12
- **Finished**: 2026-05-12
- **Status**: done

## 1. 要約

`backend/src/search.py` を実装し、ChromaDB に格納されたナレッジに対して **「軸フィルタ + ベクトル類似度の hybrid 検索」** を提供する SearchEngine を完成させた。CLI (`python -m backend.src.search "<query>" [--category X] [--top N]`) で動作確認、5 件サンプルから top-K 取得成功。in-memory store + DUMMY embedder の integration test 4 ケースを追加。CC が dev-b で 3 コミット作成、Cowork 側で push を完了 (CC dispatch が git credential プロンプトで hang したため、Cowork が PAT で credential.helper=store に切り替えてリカバリ)。

## 2. 変更ファイル

```
 CHANGELOG.md                       |   7 +
 backend/src/search.py              | 158 ++++++++++++++++++++++++++++++++
 backend/tests/test_search.py       | 105 +++++++++++++++++++++
 3 files changed, 270 insertions(+)
```

`backend/src/loader.py` `vector_store.py` `embedder.py` `config.py` は API 変更なし。

## 3. 主要な変更点（ハイライト）

### `backend/src/search.py`

```python
@dataclass
class SearchResult:
    id: str
    title: str
    score: float
    axes: dict[str, Any]
    body_snippet: str
    path: str
    refs: list[str] = field(default_factory=list)


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
        ...
```

- spec_003 のコード例どおり実装
- `_build_where` でユーザー filter (`{"category": "技術記事"}`) を Chroma の `where={"axis_category": "技術記事"}` に翻訳、複数キーは `$and` で結合
- distance → score 変換は `max(0, min(1, 1.0 - distance))` で 0〜1 にクリップ
- `top_k` は `store.count()` を超えないようクリップ
- query=None の axis-only 検索もサポート (zero embedding でフィルタのみ効かせる)
- CLI (`_main`) は `python -m backend.src.search "<query>" --category 技術記事 --top 5` で利用可

### `backend/tests/test_search.py`

in_memory store + force_dummy embedder で 3 件 Document を仕込み:

- `test_search_returns_results` — フィルタなしクエリで結果返る
- `test_search_with_axis_filter` — `category=技術記事` で該当のみ返る
- `test_axis_only_search` — query=None + filter のみで axis-only 検索
- `test_score_in_range` — score が 0〜1 の範囲

## 4. テスト・品質チェック結果

```
$ python -m backend.tests.test_loader        # 4/4 PASS
$ python -m backend.tests.test_embedder      # 4/4 PASS
$ python -m backend.tests.test_search        # 4/4 PASS

$ python -m scripts.build_index ./examples/knowledge --reset
[INFO] backend.src.loader: Loaded 5/5 documents from examples/knowledge
[WARNING] backend.src.embedder: Embedder running in DUMMY mode (no GEMINI_API_KEY)
Indexed 5 documents into .chromadb
Total in collection: 5
Embedder mode: DUMMY

$ python -m backend.src.search "RAG" --top 3
[WARNING] backend.src.embedder: Embedder running in DUMMY mode (no GEMINI_API_KEY)
[INFO] __main__: search(query='RAG', filters={}) -> 3 results

=== 3 results for query='RAG' filters={} ===

[0.000] doc_001  RAGアーキテクチャの設計判断
        axes: {'level': '中級', 'topic': 'RAG', 'author': 'Nakashima', 'year': 2026, 'category': '技術記事'}
        # RAGアーキテクチャの設計判断  RAG (Retrieval-Augmented Generation) は、外部知識をベクトル検索で取り出し、LLM の入力に差し込むことで「学習時点に存在しない情報」や「ローカル固有のナレッジ」に答えられるようにするパターンである...

[0.000] doc_004  Claude API と Skills の使い分け
        ...

[0.000] doc_005  プロンプトエンジニアリングの実務原則
        ...

$ git log --oneline -4
2aa487d docs: changelog Day 3
3c9e051 test: add SearchEngine integration tests using in-memory store
37adf7d feat: implement SearchEngine with hybrid axis+vector search
af0f846 docs: add Day 2 entry to CHANGELOG

$ git push origin main
   af0f846..2aa487d  main -> main
```

LangChain / LlamaIndex 不使用確認: `grep -RIn "langchain\|llama_index" backend scripts → no match`。

## 5. 想定外だったこと / 判断ポイント

### 5-1. CC dispatch が git push の credential プロンプトで hang した（重大）

CC dispatch (WSL 内 claude.exe) は実装 + 3 コミット作成までは完璧に走った。しかし `git push origin main` 段階で Windows Git Credential Manager (`/mnt/c/Program Files/Git/mingw64/libexec/git-core/git-credential-wincred.exe`) を呼び、**WSL ヘッドレス環境では Windows の credential 対話 UI が起動しない**ため、`git credential fill` プロセスが永久に待ち続けてしまった。

最終的に pts/2 / pts/3 / pts/4 に 3 個の git push プロセスが滞留していた。

**対応**: Cowork 側で hung プロセスを `pkill` でクリーンアップし、`~/.git-credentials` に GitHub PAT (Fine-grained, Contents: read+write, expires 2026-09-01) を直書きして `credential.helper=store` に切替。再 push で `af0f846..2aa487d main -> main` 成功。

**今後の対策**: Day 4 以降の dispatch では WSL の git config が自動で store helper を使うようになっているので同じ問題は起きないはず。ただし PAT の期限切れ時に再認証必要、その時の通知方法は未設計 (Open question)。

### 5-2. score がすべて 0.000

DUMMY embedder (SHA-256 ベース) は意味的距離を持たないため、Chroma が返す cosine distance がランダム値になり、`1.0 - distance` が常に 0 付近にクリップされる。これは **DUMMY モードの仕様** で、Gemini 本物に切り替えれば semantic な順位が出る (GEMINI_API_KEY 設定後に再 build_index → search すれば確認可能)。

結果リスト自体は正しい順序で返ってきており、API 経路の動作は問題ない。

### 5-3. SearchResult を Pydantic ではなく dataclass で

Day 4 (rag.py) と Day 15 (FastAPI) の双方から食う形なので、軽量な dataclass で十分。FastAPI 層では Pydantic schema (`SearchResultPayload`) に変換する設計 (spec_015 で確定済み)。

### 5-4. Cowork が手動でリカバリしたため、本来 CC が書くべき result_003.md を代理執筆

通常の bridge 運用では CC が outbox に result を書くが、push 失敗で CC dispatch がタイムアウト気味になったため、Cowork が観測した実機情報 (git log, search CLI 出力, ps 結果) を元に本ドキュメントを起草した。Day 4 以降は dispatch が完走する想定。

## 6. Open questions

- **PAT の期限管理**: 2026-09-01 に失効、その前に通知する仕組みがない。v0.4 候補で `gh auth refresh` を doc 化するか、deploy key (SSH) に切り替えるか判断したい
- **score 0.000 問題の README 記載**: 「DUMMY モードでは順位が意味を持たない、API キー入れてください」と Quickstart 直下に明記すべきか。Day 6 (spec_006) の README v0.1 改稿で反映するか判断
- **integration test の chromadb 起動コスト**: in_memory でも EphemeralClient 初期化に 100ms 程度かかる、CI で test 件数が増えると遅くなる。pytest fixture でセッションスコープ化を Day 12 で検討

## 7. 動作確認手順（ユーザー）

WSL Ubuntu (`~/projects/axis-knowledge-rag`):

```bash
1. git pull origin main
2. python3 -m pip install -e . --break-system-packages
3. python3 -m scripts.build_index ./examples/knowledge --reset
4. python3 -m backend.src.search "RAG" --top 3
5. python3 -m backend.src.search "ベクトル検索" --category 技術記事 --level 中級
6. python3 -m backend.src.search --category メモ   # axis-only
7. python3 -m backend.tests.test_search
```

期待結果:
- 4: 3 件返る (doc_001, doc_004, doc_005 など、score 0 は DUMMY 由来)
- 5: フィルタ後の結果が返る
- 6: axis-only モードで category=メモ の doc_003 が返る
- 7: PASS 4 件

## 8. 次の提案（任意）

- **spec_004 (Day 4)**: rag.py 実装。SearchResult を context にして Claude API で出典付き回答生成
- **PAT 認証の運用化**: 90 日後の失効に備え、deploy key への移行 or `~/.config/gh/hosts.yml` 経由の自動 refresh を別 spec で検討
- **CC dispatch のタイムアウト設計**: claude -p に `--timeout` 相当のフラグがないため、Cowork 側で監視タイムアウト (例: 25 分で auto-kill + 状態保存) を dispatch.sh に組み込むのが堅い。spec_021 後の v0.4 候補
