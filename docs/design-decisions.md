# Architecture Decision Records (ADR)

axis-knowledge-rag の設計上の主要判断を、ADR (Architecture Decision Record) 形式で集約する。
各 ADR は **Context / Decision / Consequences / Alternatives / Status** の 5 セクションで構成し、
判断の背景と代替案を保存することで、後から「なぜこう作ったか」を辿れるようにしている。

新しい ADR を追加する際は、末尾に `ADR-NNN` 形式で連番を振り、Status は `Proposed → Accepted → Deprecated → Superseded by ADR-XXX` の遷移で管理する。

---

## ADR-001: LangChain / LlamaIndex を使わず RAG を自前実装する

- **Date**: 2026-05-12
- **Status**: Accepted
- **Deciders**: 中島

### Context

RAG 実装の選択肢として LangChain, LlamaIndex, Haystack といったフレームワークが存在する。
これらを使うと開発速度は上がるが、**「フレームワークの抽象に乗っている」状態**になりがちで、
内部挙動の理解と説明可能性が損なわれる。

読み手に「RAG を自分で組める」と伝えるには、低レイヤを自前で書いた方が深い理解が伝わる。
また、これは個人ポートフォリオであり、依存を最小化することで長期メンテナンス性も担保したい。

### Decision

LangChain / LlamaIndex / Haystack を一切使わず、`embedder` / `vector_store` / `search` / `rag` を
全て自前実装する。Anthropic SDK と `google-generativeai` のような **公式 SDK は使う**
(API クライアントを再実装する意味はないため)。

### Consequences

- ✅ コードベース全体を作者が読み切れる、ブラックボックスなし
- ✅ 「RAG パイプライン自前実装」という設計理由が明示できる
- ✅ フレームワークの破壊的変更に巻き込まれない
- ✅ chunking / re-ranking / query rewriting といった発展機能を、必要になった時に自分で設計できる
- ❌ chunking 等の高度な retrieval パターンは自作する必要 (Week 1 では未対応)
- ❌ LangSmith のような周辺ツール ecosystem と連携しない

### Alternatives Considered

- **LangChain**: 速いが abstraction が重く、設計理解アピールにならない
- **LlamaIndex**: data indexing は得意だが retrieval pipeline がカチっと固まっており、軸検索を組み込みづらい
- **Haystack**: 機能が多すぎる、Local-first の趣旨と合わない

---

## ADR-002: ベクトルストアに ChromaDB を採用する

- **Date**: 2026-05-12
- **Status**: Accepted
- **Deciders**: 中島

### Context

ベクトルストアの選択肢は大きく分けて (a) クラウド SaaS (Pinecone, Weaviate Cloud)、
(b) セルフホスト OSS (Weaviate, Qdrant, Milvus)、(c) ライブラリ型 (Chroma, FAISS) の 3 系統。

本プロジェクトは Local-first / 個人ナレッジ運用を主用途とするため、
**外部サーバ不要・ファイル永続・Python から直接呼べる** ことが必須条件。

### Decision

ChromaDB の `PersistentClient` (`./.chromadb/` ディレクトリ永続) を採用する。
コレクション名 `axis_knowledge` を固定で 1 本だけ持ち、軸メタデータは
`axis_<key>` および `axis_<key>_norm` の 2 列で flatten 保存する。

### Consequences

- ✅ 外部プロセス・サーバ不要、`pip install chromadb` で完結
- ✅ ファイル永続なので `docker compose down` してもデータが残る
- ✅ Python API のみで完結、HTTP クライアントを書く必要なし
- ✅ axis メタデータの where 句が標準で使える (`$and` などで多軸 AND)
- ❌ 大規模 (>1M ベクトル) では性能不足、その時点で Qdrant / Weaviate へ移行が必要
- ❌ Chroma 0.5 で `$and` が必須になるなど、メタデータ filter の DSL が変化中

### Alternatives Considered

- **FAISS**: 速いが metadata filter が貧弱、軸検索の主要 USP と相性が悪い
- **Qdrant**: 機能は十分だが Docker 必須でセットアップが重い
- **Weaviate**: 同上、加えて GraphQL の学習コストがある
- **Pinecone**: SaaS、Local-first から外れる
- **pgvector**: PostgreSQL 前提、Local-first から外れる

---

## ADR-003: Pydantic ではなく dataclass を使う

- **Date**: 2026-05-12
- **Status**: Accepted
- **Deciders**: 中島

### Context

`Document` / `SearchResult` / `Answer` などのドメインオブジェクトを定義する際、
Pydantic を使うとバリデーション・JSON シリアライズが標準化される。
一方、本プロジェクトのドメインオブジェクトは内部用途で、**外部入力の validation はほぼ存在しない**
(frontmatter のパースは `python-frontmatter` 側で済んでいる)。

### Decision

標準ライブラリの `@dataclass` を使う。frozen が必要な場合は `frozen=True`、
デフォルト値が mutable な場合は `field(default_factory=...)` を使う。

### Consequences

- ✅ 依存ゼロ、Python 標準ライブラリのみ
- ✅ IDE 補完が同等に効く
- ✅ Pydantic v1/v2 移行のような破壊的変更に巻き込まれない
- ❌ JSON シリアライズは手書き (`as_dict()` メソッド) で書く必要がある
- ❌ 型バリデーションは実行時には行われない (型 hint は静的解析任せ)

### Alternatives Considered

- **Pydantic v2**: 高機能だが本プロジェクトの内部用途には過剰
- **attrs**: 機能は近いが標準ライブラリではない、選ぶ理由が薄い
- **TypedDict**: 軽量だがメソッドを持てない、`@property` が使えない

---

## ADR-004: Streamlit を Week 1 UI、Next.js を Week 3 に回す

- **Date**: 2026-05-12
- **Status**: Accepted
- **Deciders**: 中島

### Context

個人 OSS として React/Next.js 経験を示したい一方、
Week 1 で UI まで実装するには時間が足りない。
Streamlit は Python だけで UI が組めるため、`backend/` の薄いラッパとして即座に動作確認できる。

### Decision

- **Week 1 (v0.1.0)**: `streamlit_app.py` でサイドバー軸フィルタ + 質問入力 + 回答パネルを実装
- **Week 3 (v0.3.0)**: Next.js + FastAPI 構成に全面移行。Streamlit は削除

### Consequences

- ✅ Week 1 終了時点で「動く Web アプリ」がデモできる
- ✅ Streamlit 期間に backend API の境界を整理できるので、Next.js 移行がスムーズ
- ✅ 「UI フレームワーク選定の判断ができる」という判断軸を文書として残せる
- ❌ Week 1〜2 の UI コードは Week 3 で捨てる (sunk cost)
- ❌ Streamlit の `@st.cache_resource` 制約に縛られる期間がある

### Alternatives Considered

- **最初から Next.js**: 開発期間が伸びる、Week 1 デモが間に合わない
- **Gradio**: Streamlit より制約が強い、サイドバー設計の自由度が低い
- **CLI のみで Week 1 を終わらせる**: スクリーンショットが撮れずポートフォリオ訴求力が弱い

---

## ADR-005: DUMMY モード (オフライン動作) を一級市民で提供する

- **Date**: 2026-05-12
- **Status**: Accepted
- **Deciders**: 中島

### Context

RAG パイプラインは外部 API (Gemini Embedding + Claude) に依存するが、
**API キー無しでも CI / 開発者ローカル / デモ環境でパイプラインを動かしたい**。

特に GitHub Actions 上のテストは外部 API を叩けない (キー漏洩リスク + コスト)。

### Decision

`Embedder(force_dummy=True)` および `RAGPipeline(force_dummy=True)` を提供。
API キーが未設定の場合も自動で DUMMY モードにフォールバックする。

- Embedder DUMMY: SHA256 ハッシュ由来の決定的 768 次元ベクトル
- RAG DUMMY: 検索上位 1 件のタイトル + 抜粋を固定フォーマットで返す

### Consequences

- ✅ CI でパイプライン全体が走る (search → rag まで)
- ✅ コードを読みに来た人が clone してすぐ動かせる (API キーなしでも UI が立ち上がる)
- ✅ DUMMY/本物のフラグが `is_dummy` プロパティで可視化される
- ❌ DUMMY モードのテストは「意味的に正しい」ことを検証できない (cosine 類似度がゼロに近い)
- ❌ DUMMY モードの存在は本番コードを若干複雑にする (各クラスに `_use_dummy` 分岐)

### Alternatives Considered

- **API キー必須にする**: シンプルだが CI / お試し体験を犠牲にする
- **モックライブラリで都度差し替え**: テストごとに mock 設定が必要、運用負荷が高い
- **VCR (HTTP record/replay)**: 本物の API レスポンスを記録する必要、初回のキーが必須

---

## ADR-006: 軸メタデータを `axis_*` プレフィックスで Chroma metadata に flatten する

- **Date**: 2026-05-12
- **Status**: Accepted
- **Deciders**: 中島

### Context

ChromaDB の metadata は **flat な scalar dict** (str/int/float/bool) のみ受け付ける。
ネストした dict は保存できないため、`axes: {category: "技術記事", level: "中級"}` をそのまま渡せない。

また、検索時の where 句 (`{"axis_category": "技術記事"}`) と保存時のキーが対応する必要がある。

### Decision

- 保存時に `axes` を `{"axis_<key>": <value>}` に flatten する (`_flatten_axes()`)
- 正規化済みの値を `{"axis_<key>_norm": <normalized>}` として **併記** する (`_flatten_axes_with_norm()`)
- 検索時の where 句は `axis_<key>_norm` を使い、normalize 経由で照合する

### Consequences

- ✅ ChromaDB 制約に適合
- ✅ where 句が直感的 (`{"axis_category_norm": "技術記事"}`)
- ✅ 生の値と normalize 後の値を両方残せる (UI 表示は生、検索は norm)
- ❌ metadata 列が `axis_*` と `axis_*_norm` で 2 倍になる (現実的にはストレージ問題なし)
- ❌ 軸名のキー衝突 (例: `axis_title`) を避けるため、`axes:` の名前空間を予約する必要がある

### Alternatives Considered

- **生の値だけ保存**: 検索時に normalize の不一致でヒットしないケースが頻発
- **normalize 後の値だけ保存**: UI 表示用に逆引きできない (decode 不可)
- **ネストを JSON 文字列に**: where 句で部分一致が使えない、軸 filter の意味が消える

---

## ADR-007: normalize 後を別フィールド `normalized_*` に保存し、生テキストを保持する

- **Date**: 2026-05-12
- **Status**: Accepted
- **Deciders**: 中島

### Context

日本語ナレッジの表記ゆれ (全角/半角・カタカナ/ひらがな・大小文字) を吸収するため、
NFKC + カナ統一 + lowercase の normalize パイプラインを通す必要がある。

しかし **UI 表示や引用は生のテキスト** を使いたい (`ChromaDB` を `chromadb` で表示するのは違和感)。
両方を保持する設計が必要。

### Decision

`Document` データクラスに `normalized_title` / `normalized_body` / `normalized_axes` /
`normalized_tags` フィールドを追加し、`load_document(path, normalizer=...)` で populate する。

- Embedder には `normalized_body` を渡す (検索クエリも normalize するため整合)
- UI 表示には生の `title` / `body` を使う
- where 句には `axis_*_norm` (= `normalized_axes` から flatten したもの) を使う

### Consequences

- ✅ 検索のリコールが上がる (表記ゆれを吸収)
- ✅ UI 表示は元の見た目を保つ
- ✅ Normalizer を後から差し替えても再 index で対応できる
- ❌ Document サイズが約 2 倍になる (メモリ上、永続化先は metadata のみ)
- ❌ Normalizer の有無で `Document` の状態が変わる (test fixture が複雑になりがち)

### Alternatives Considered

- **生テキストだけ保存し検索時に normalize**: index 側が normalize されていないと cosine が安定しない
- **normalize 後だけ保存**: UI 表示を逆変換できず、見た目が損なわれる

---

## ADR-008: AUTO_GENERATED マーカー方式で人間記述と AI 生成を共存させる

- **Date**: 2026-05-13
- **Status**: Accepted
- **Deciders**: 中島

### Context

ナレッジ Markdown には、人間が書いたコアな知識と、AI が自動生成する要約・FAQ・メタデータの
2 種類のコンテンツを共存させたい。
ただし AI 生成を素朴に上書きすると人間記述が消えるため、**区画を明示する** 必要がある。

### Decision

HTML コメント形式のマーカーで AI 区画を囲み、`marker.py` の `update_block()` で
区画内部だけを書き換える方式を採用する:

```
<!-- AUTO_GENERATED_START: summary -->
<AI が書く区画>
<!-- AUTO_GENERATED_END: summary -->
```

### Consequences

- ✅ Markdown レンダラー (GitHub / Obsidian) では HTML コメントが非表示、見た目クリーン
- ✅ 標準ライブラリの `re` だけで実装可能、依存ゼロ
- ✅ diff が読みやすく、PR レビューで AI 生成部分を識別できる
- ✅ `strip_blocks()` で「人間記述のみ版」を作れる
- ❌ ネストマーカー非対応 (Phase 2 で再帰パーサーに移行予定)
- ❌ 同名ブロックが複数あると `update_block` は最初の 1 個しか書き換えない

### Alternatives Considered

- **別ファイルに分離**: `doc.md` と `doc.summary.md` のような構成。検索/表示で 2 ファイル扱いが煩雑
- **YAML frontmatter に格納**: 要約が長文の場合に YAML としての可読性が落ちる
- **専用 DSL / AST**: 学習コストが高く、Markdown の自由度を損なう

---

## ADR-009: テストツールは pytest のみ、mypy / black は採用しない (Week 1)

- **Date**: 2026-05-13
- **Status**: Accepted
- **Deciders**: 中島

### Context

Python プロジェクトの品質ツール選択肢は多い: pytest, mypy, black, ruff, pyright, isort, ...
全部入れるとセットアップが重く、Week 1 のスコープを圧迫する。
一方で「テストもリンタもない」状態は個人 OSS として弱い。

### Decision

Week 1 では以下のみ採用:

- **pytest >= 8** — テスト (90 ケース、coverage 72.49%)
- **ruff >= 0.5** — リンタ + import sort (black の代替フォーマットも内蔵)

採用しないもの:

- **black** — ruff format で代替できるため重複
- **mypy / pyright** — 型 hint は書いているが、Week 1 で型エラーゼロを目指すコストが見合わない
- **isort** — ruff の `I` ルールで代替

### Consequences

- ✅ pyproject.toml がシンプルに保たれる
- ✅ ruff は高速 (Rust 製)、CI 時間にほぼ影響しない
- ✅ 「ツール選定の判断ができる」という判断軸を文書として残せる
- ❌ 型エラーが実行時まで発覚しない
- ❌ Week 3 で Next.js 移行する際、API 契約の型整合性が手動チェックになる

### Alternatives Considered

- **mypy --strict から始める**: 既存コードへの annotation 投入コストが大きすぎる
- **pyright**: VSCode との統合は良いが CI 連携が mypy より弱い
- **採用なし**: ポートフォリオ訴求力が弱まる

Status: v0.3 で Next.js 移行時に mypy 導入を再検討する。

---

## ADR-010: Claude API と Gemini Embedding API で役割を分担する

- **Date**: 2026-05-12
- **Status**: Accepted
- **Deciders**: 中島

### Context

RAG パイプラインには (a) embedding 生成、(b) 回答生成 の 2 種類の LLM 呼び出しがある。
両者で同じプロバイダを使う必要はない。コストと品質のバランスで分離する余地がある。

| | Embedding | Generation |
|---|---|---|
| 求める性能 | 多言語対応 + 速さ + 安価 | 日本語の自然さ + 長文構成力 |
| Claude | 提供なし | ◎ |
| Gemini | text-embedding-004 (768d, 無料枠あり) | ○ |
| OpenAI | text-embedding-3 | ○ |

### Decision

- **Embedding**: Gemini `text-embedding-004` (768 次元)
- **Generation**: Anthropic Claude (`claude-3-5-sonnet-20241022` をデフォルト、`CLAUDE_MODEL` で上書き可)

両 API キーは個別の環境変数で管理し、片方だけ設定/未設定でも動作する。

### Consequences

- ✅ Gemini 無料枠で開発・デモ時のコストを抑えられる
- ✅ 回答品質は Claude が日本語で強く、ユーザー体験が良い
- ✅ 一方の API が落ちても、もう一方は影響なし
- ❌ プロバイダ 2 社の API キーを管理する運用負荷
- ❌ embedding と generation で言語モデルが違うため、completion の bias 補正は別途必要

### Alternatives Considered

- **OpenAI 単独**: シンプルだがコストが Gemini より高い
- **Claude 単独**: Embedding API が無い (2026 年 5 月時点)
- **ローカルモデル (sentence-transformers + Llama)**: 性能不足、Week 1 で動かすには重い

---

## ADR-011: `_ai_workspace/bridge/` 経由で人 ⇔ AI コラボを spec/result 文書化する

- **Date**: 2026-05-12
- **Status**: Accepted
- **Deciders**: 中島

### Context

本プロジェクトは Codex (spec 作成側) と Claude Code (実装側) の 2 AI 役割を分けて運用している。
ただ自然言語で会話を流すと「何を依頼したか」「どう実装したか」が消えるため、
**書面化された依頼書 (spec) と報告書 (result) を残す** プロセスが必要だった。

### Decision

`_ai_workspace/bridge/` 配下に固定構造を置く:

```
_ai_workspace/bridge/
├── inbox/      # Codex → Claude Code 依頼 (spec_NNN.md)
├── outbox/     # Claude Code → Codex 報告 (result_NNN.md)
└── templates/  # spec / result のテンプレ
```

spec/result は git 管理対象外 (`.gitignore` で除外)。

### Consequences

- ✅ AI ↔ AI の引き継ぎが完全に文書化される
- ✅ 後から「Day N で何を決めたか」を辿れる
- ✅ spec が「制約 / やってほしいこと / 成功条件」のフォーマットを強制するので、依頼の質が上がる
- ✅ 「AI 協業ワークフローを設計した」という判断軸を文書として残せる
- ❌ spec/result の手書きコストがある (テンプレで吸収しているが完全には消えない)
- ❌ `_ai_workspace/` は git 外なので、リポジトリ単体からはプロセスが見えない

### Alternatives Considered

- **GitHub Issues で代替**: 自然だが Codex/Claude が直接アクセスできず、コピペ運用になる
- **CHANGELOG だけで十分**: 結果は残るが依頼内容と背景判断が残らない
- **完全に会話ベース**: 履歴が流れる、再現性が低い

---

## ADR-012: Week 1 では chunking を導入しない、v0.4 で導入予定

- **Date**: 2026-05-12
- **Status**: Accepted (Week 1) / Pending (v0.4 で再検討)
- **Deciders**: 中島

### Context

一般的な RAG では、長文ドキュメントを 200〜500 トークン程度に分割 (chunking) して
個別に埋め込む。これによって retrieval の粒度が上がり、関連性スコアが安定する。

本プロジェクトのナレッジは Markdown 1 ファイル = 1 トピック (おおむね 1k〜3k 字) を想定しているため、
**Week 1 段階では 1 ドキュメント = 1 ベクトル** で十分機能する。

### Decision

Week 1 (v0.1.0) では chunking を実装しない。`Document.normalized_body` 全体を 1 ベクトル化する。
v0.4 で `Chunk` データクラスを導入し、`Document` から複数の `Chunk` を生成する設計に拡張する予定。

### Consequences

- ✅ 実装がシンプル、Week 1 のスコープに収まる
- ✅ 1 ドキュメント = 1 ID なので refs / integrity のロジックが直感的
- ✅ 短いナレッジに対しては chunking なしの方が context loss が少ない
- ❌ 長文ドキュメント (>5k 字) ではトピックが薄まり、retrieval 精度が落ちる
- ❌ Gemini Embedding は 2048 トークン上限、超える場合は事実上 truncate される
- ❌ v0.4 で chunking を導入する際、`vector_store` の ID 設計を変える必要 (Chunk ID = `<doc_id>::<chunk_idx>`)

### Alternatives Considered

- **最初から chunking**: Week 1 が間に合わない、refs/integrity の設計が複雑になる
- **章単位 (`##` 見出し) で分割**: Markdown 構造に依存しすぎ、frontmatter ID との対応が崩れる
- **固定文字数 (500 chars) で分割**: 日本語は文字単位 vs トークン単位で差が大きく、雑になる

---

## ADR-013: 疑似ストリーミング (typewriter) を採用、SSE/WebSocket は v0.4 へ

- **Date**: 2026-05-13
- **Status**: Accepted
- **Deciders**: 中島

### Context

RAG 回答生成は Claude API の呼び出しで数秒かかる。ユーザー体験として「回答が少しずつ表示される」
ストリーミング感が欲しい。選択肢は (a) SSE (Server-Sent Events)、(b) WebSocket、
(c) 一括受信後のクライアント側疑似ストリーミング (typewriter) の 3 つ。

SSE/WS は FastAPI 側の `StreamingResponse` と Next.js 側の `EventSource` / `WebSocket` クライアントを
両方実装する必要があり、Week 3 のスコープに対して工数が大きい。

### Decision

v0.3 では**クライアント側 typewriter アニメーション**を採用する。
FastAPI から一括で回答テキストを返し、`AnswerPanel` がレスポンス受信後に 1 文字ずつ描画する。

SSE / WS による真のストリーミングは v0.4 の拡張ポイントとして ADR に記録するにとどめる。

### Consequences

- ✅ バックエンド変更不要、フロントエンドのみで「ストリーミング感」を実現
- ✅ Week 3 のスコープに収まる
- ✅ DUMMY モードと本番モードで挙動が変わらない
- ❌ 実際には全文受信後に表示するため、長い回答ではユーザーが待つ時間がある
- ❌ 真のストリーミングより Context Window の効率が若干落ちる

### Alternatives Considered

- **SSE**: `StreamingResponse` + `EventSource` — バックエンドも変更必要、v0.4 で対応
- **WebSocket**: さらに工数が大きく、双方向通信が必要なユースケースでもない

---

## ADR-014: Streamlit を deprecated せず残す (後退路用)

- **Date**: 2026-05-13
- **Status**: Accepted
- **Deciders**: 中島

### Context

ADR-004 では「Week 3 で Streamlit を削除し Next.js に全面移行」と決定していた。
しかし実際には、Next.js 移行後も Streamlit を削除せずに残す判断をした。

理由は (a) Next.js frontend が壊れた場合の後退路として機能すること、
(b) README で「2 種類の UI が試せる」という独自性を示せること、
(c) 削除のコストに対してリターンが薄いこと。

### Decision

`streamlit_app.py` を v0.3 でも削除せず残す。
README と architecture.md に「レガシー UI / 後退路用」と明記し、
メイン UI は Next.js であることを明示する。

### Consequences

- ✅ Next.js frontend に問題が起きたときの保険として機能
- ✅ ポートフォリオ上「2 UI 構成」という差別化要素になる
- ✅ Streamlit 削除による破壊テストをスキップできる
- ❌ 2 つの UI を維持するコストが残る (バックエンド変更時に両方確認が必要)
- ❌ v0.4 で機能追加する際に Streamlit 側が陳腐化していく

### Alternatives Considered

- **削除**: シンプルだが ADR-004 の想定通り。後退路が消え、ポートフォリオ訴求力も一点集中になる
- **別ブランチで保持**: git 管理が複雑になり、CI での維持が手間

---

## ADR-015: Docker multi-stage で frontend image を slim 化

- **Date**: 2026-05-13
- **Status**: Accepted
- **Deciders**: 中島

### Context

Next.js の Docker image は単純にビルドすると `node_modules` を丸ごと含み 1GB 超になる。
本番デプロイ・GitHub Actions でのビルド時間・イメージ pull コストを考えると、
slim 化が必要。

### Decision

`frontend/Dockerfile` に multi-stage build を採用する:

```dockerfile
# Stage 1: builder
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: runner (本番イメージ)
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

`next.config.js` に `output: "standalone"` を設定し、Next.js が `server.js` を含む
standalone ディレクトリを生成するようにする。

### Consequences

- ✅ イメージサイズを ~1GB → ~200MB 程度に削減 (目安)
- ✅ CI/CD でのビルド・push・pull が高速化
- ✅ 本番環境でのデプロイコストが下がる
- ❌ `standalone` モードでは `public/` と `static/` の手動 COPY が必要
- ❌ Next.js のバージョンアップ時に `output: standalone` の動作確認が必要

### Alternatives Considered

- **single-stage**: シンプルだがイメージが大きすぎる
- **distroless**: セキュリティ強化だが Node.js 向けの distroless は設定が複雑

---

## ADR-016: BM25 を加えて 3-way hybrid 検索にする

- **Date**: 2026-05-14
- **Status**: Accepted
- **Deciders**: 中島

### Context

v0.5 までの hybrid 検索は **(a) 軸フィルタ + (b) ベクトル類似度** の 2-way 構成だった。
ベクトル検索は意味的近接に強い一方、**固有名詞 / 厳密な単語マッチ** に弱い。例えば
"ChromaDB" を検索するとベクトル空間上で「データベース」「ベクトルストア」と近接し、
本命のドキュメントが top_k に入らないことがある。

採用面接などで「BM25 と組み合わせていますか?」と聞かれた時に「ベクトルだけです」と
答えるのは v0.6 でカバーしたい、というモチベーションもある。

### Decision

- `rank_bm25.BM25Okapi` を採用し、in-memory に BM25 index を保持
- トークナイザは **正規化済みテキストの文字 n-gram (n=1, 2)** で済ます (MeCab / Sudachi の
  辞書配布を避ける)
- 軸フィルタで候補を絞った後の vector top_k と BM25 score を **weighted sum** で fusion:
  `final = (1 - bm25_weight) * cosine + bm25_weight * bm25_norm`
- BM25 score は **min-max 正規化** で `[0, 1]` に揃え、cosine と直接合算できるようにする
- `bm25_weight=0.5` をデフォルト、`SearchInput` / CLI から上書き可
- `bm25_weight=0.0` は **完全に v0.5 互換** (vector only)、後方互換を保つ
- vector 側は fusion 時に over-fetch (`max(top_k*2, 20)`) して BM25 が再ランクできる
  候補を確保する

### Consequences

- ✅ 固有名詞 / 厳密語彙マッチが強くなる
- ✅ ベクトルだけだと埋もれる希少語が浮上する
- ✅ `bm25_weight` で「ベクトル寄り / BM25 寄り」を 1 スカラーで説明できる
  (RRF より直感的)
- ❌ BM25 index がメモリに乗る (1000 docs で MB オーダー、無視できる)
- ❌ ingester で文書追加時に index 再構築が必要 (永続化は v0.7 で検討)
- ❌ 文字 n-gram は形態素ベース BM25 より精度が劣る (依存最小化とのトレードオフ、許容)

### Alternatives Considered

- **SPLADE / ColBERT**: sparse-dense 学習モデル。実装重く v1.0 候補
- **Elasticsearch / OpenSearch**: 外部依存、Local-first の方針に反する
- **形態素解析 (MeCab / Sudachi)**: 辞書配布で初期セットアップが重くなる
- **RRF (Reciprocal Rank Fusion)**: score 値が直感的でなく、UI/API での説明が
  難しい。重み付き和の方が「半々で混ぜる」「7:3 で固有名詞重視」と直接表現できる
  ので採用

---

## ADR の追加・改訂ルール

1. **追加**: 末尾に `ADR-NNN` で連番。Date / Status / Deciders を書き、5 セクション (Context / Decision / Consequences / Alternatives / Status) を埋める
2. **改訂**: 既存 ADR を直接書き換えず、新しい ADR で `Supersedes ADR-XXX` と記載
3. **Deprecate**: 元の ADR の Status を `Deprecated (see ADR-YYY)` に変更し、新 ADR にリンク
4. **PR 時の参照**: コミットメッセージや PR 説明に `(ADR-NNN)` を含めると後で辿りやすい
