# システム概要書 v2: axis-knowledge-rag（3週間完璧版）

**作成日**: 2026-05-12
**作成者**: 中島
**ステータス**: 仕様確定済み、Day 1 着手予定

---

## 1. プロジェクトサマリー

**何**: YAML frontmatter付きMarkdownナレッジに対する、軸検索＋RAG検索のローカルWebアプリOSS

**誰のため**: 個人ブロガー、研究者、学生団体、小規模チーム

**他のRAGツールとの差別化**:
- 軸メタデータでの構造化検索＋ベクトル検索のハイブリッド
- 日本語ナレッジ特化（表記ゆれ吸収）
- LangChain/LlamaIndex不使用（自前実装）
- Local-first（個人データを外部送信しない）
- マーカー方式で人間記述と自動生成を共存

**期間**: 3週間（2026/5/12 〜 2026/6/1）

**最終ゴール**: v0.3.0を6/1までにパブリック化、フューチャーES応募時に「3バージョン分のコミット履歴」を持つ完成度の高いOSSをポートフォリオに

---

## 2. 全体ロードマップ

| 週 | リリース | 主要成果物 |
|---|---|---|
| **Week 1**<br>5/12〜5/18 | **v0.1.0**（コアMVP） | 軸検索＋ベクトル検索＋RAG生成がStreamlit UIで動作 |
| **Week 2**<br>5/19〜5/25 | **v0.2.0**（差別化機能） | 表記ゆれ吸収・参照整合性チェック・マーカー方式・テスト・CI |
| **Week 3**<br>5/26〜6/1 | **v0.3.0**（UI/UX最終形） | Next.js + FastAPIへ移行、README完全版、デモGIF |

---

## 3. ディレクトリ構成（最終形・v0.3.0時点）

```
axis-knowledge-rag/
├── README.md                       # 顔。デモGIF入り
├── LICENSE                         # MIT
├── CHANGELOG.md                    # v0.1〜v0.3の履歴
├── docker-compose.yml              # 一発起動
├── Dockerfile.backend
├── Dockerfile.frontend
├── pyproject.toml
├── .env.example
│
├── backend/                        # FastAPI (Python)
│   ├── src/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── loader.py               # Markdown + YAML読み込み
│   │   ├── normalizer.py           # 表記ゆれ吸収（v0.2追加）
│   │   ├── integrity.py            # 参照整合性チェック（v0.2追加）
│   │   ├── marker.py               # マーカー方式（v0.2追加）
│   │   ├── embedder.py             # Gemini埋め込み
│   │   ├── vector_store.py         # ChromaDBラッパー
│   │   ├── search.py               # 軸検索+ベクトル検索
│   │   ├── rag.py                  # RAGパイプライン
│   │   └── api.py                  # FastAPI エンドポイント
│   ├── tests/
│   │   ├── test_loader.py
│   │   ├── test_normalizer.py
│   │   ├── test_integrity.py
│   │   ├── test_marker.py
│   │   └── test_search.py
│   └── requirements.txt
│
├── frontend/                       # Next.js (TypeScript)
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx            # 検索画面
│   │   │   ├── settings/page.tsx   # 設定画面
│   │   │   └── layout.tsx
│   │   ├── components/
│   │   │   ├── SearchBar.tsx
│   │   │   ├── AxisFilter.tsx
│   │   │   ├── ResultCard.tsx
│   │   │   └── AnswerPanel.tsx
│   │   └── lib/
│   │       └── api.ts              # backend API クライアント
│   ├── package.json
│   └── next.config.js
│
├── examples/
│   └── knowledge/                  # サンプルMarkdown 15本程度
│       ├── 01-rag-patterns.md
│       ├── 02-claude-skills.md
│       └── ...
│
├── docs/
│   ├── architecture.md             # アーキ図 + データフロー
│   ├── design-decisions.md         # ADR形式の設計判断集
│   ├── normalizer.md               # 表記ゆれ吸収の仕組み
│   ├── integrity.md                # 参照整合性チェック
│   ├── marker.md                   # マーカー方式
│   └── api-reference.md            # FastAPI エンドポイント仕様
│
└── .github/
    └── workflows/
        ├── ci.yml                  # pytest + lint
        └── docker.yml              # Docker build test
```

---

## 4. 技術スタック

| 層 | 技術 | 採用判断 |
|---|---|---|
| **Frontend** | Next.js 14 (App Router) + TypeScript + Tailwind CSS | モダンフロントエンド経験のアピール |
| **Backend** | FastAPI (Python 3.11) | 業務でPython習熟済み、OpenAPI自動生成 |
| **Vector Store** | ChromaDB（埋め込み型） | サーバー不要、`pip install`即動作 |
| **Embedding** | Gemini text-embedding-004（768次元） | 業務実績あり |
| **LLM** | Claude API (claude-3-5-sonnet) | 業務実績あり、Tool use対応 |
| **Markdown解析** | python-frontmatter | YAML frontmatter標準 |
| **正規化** | unicodedata + 自前カナ変換 | 表記ゆれ吸収を自前実装 |
| **テスト** | pytest, pytest-asyncio | 標準的 |
| **Lint** | ruff (Python), eslint (TS) | 高速 |
| **CI/CD** | GitHub Actions | 標準的 |
| **コンテナ** | Docker + docker-compose | `up`一発起動 |

**意図的に使わないもの**:
- LangChain / LlamaIndex（「フレームワーク使った」と読まれないため）
- 認証ライブラリ（local-first設計なので不要）
- クラウドDB（local-firstなので不要）

---

## 5. データモデル

### 5.1 ナレッジMarkdownの形式

```markdown
---
id: "doc_001"                       # 一意ID
title: "RAGアーキテクチャの設計判断"
axes:
  category: "技術記事"
  topic: "RAG"
  level: "中級"
  author: "Nakashima"
  year: 2026
tags: ["llm", "vector-search"]
refs: ["doc_002", "doc_005"]        # 他ドキュメントへの参照
created: 2026-05-12
updated: 2026-05-12
---

# 本文

通常のMarkdown。

<!-- AUTO_GENERATED_START: summary -->
このセクションは自動生成。再生成で上書きされる。
<!-- AUTO_GENERATED_END: summary -->

人間が書いた本文は AUTO_GENERATED ブロック外なので保護される。
```

### 5.2 軸定義（`config.yml`）

```yaml
axes:
  - name: category
    type: enum
    values: ["技術記事", "メモ", "議事録", "ToDo"]
    required: true
  - name: topic
    type: string
    required: true
  - name: level
    type: enum
    values: ["初級", "中級", "上級"]
    required: false
  - name: author
    type: string
    required: false
  - name: year
    type: integer
    required: false

normalization:
  nfkc: true
  katakana_to_hiragana: true

integrity:
  check_refs: true
  fail_on_broken: false
```

---

## 6. Week 1 詳細: v0.1.0（コアMVP）

**目標**: 軸検索＋ベクトル検索＋RAG生成がStreamlitで動作

| 日 | やること | 完了条件 |
|---|---|---|
| **Day 1**<br>5/12 (月) | プロジェクト初期化、ディレクトリ構成、`pyproject.toml`、`.env.example`、`loader.py`実装、サンプルMarkdown 5本作成 | `python -m backend.src.loader ./examples/knowledge` でDocument一覧出力 |
| **Day 2**<br>5/13 (火) | `embedder.py`（Gemini埋め込み）、`vector_store.py`（ChromaDB）、インデックス構築スクリプト | サンプル5本がChromaDBに格納される |
| **Day 3**<br>5/14 (水) | `search.py`（軸フィルタ＋ベクトル類似度のハイブリッド検索） | CLIで「`category=技術記事`+クエリ」で関連doc top-5取得 |
| **Day 4**<br>5/15 (木) | `rag.py`（Claude APIでRAG生成）、出典付き回答 | CLIで質問→出典付き回答が返る |
| **Day 5**<br>5/16 (金) | Streamlit UI（`app.py`）、サイドバーに軸フィルタ、メインに検索結果 | ブラウザ操作で全フロー動作 |
| **Day 6**<br>5/17 (土) | Dockerfile、docker-compose、サンプル拡充（10本）、README v0.1版 | `docker-compose up`で起動 |
| **Day 7**<br>5/18 (日) | バグ修正、コミット履歴整理、**v0.1.0 タグ付与とパブリック化** | GitHubで公開、READMEで価値が伝わる |

---

## 7. Week 2 詳細: v0.2.0（差別化機能）

**目標**: サムライ施策で実装した「業務級の品質」をOSSに移植

| 日 | やること | 完了条件 |
|---|---|---|
| **Day 8**<br>5/19 (月) | `normalizer.py`（NFKC正規化、カタカナ→ひらがな） | `"RAG"`と`"ＲＡＧ"`、`"らぐ"`と`"ラグ"`が同一視される |
| **Day 9**<br>5/20 (火) | normalizerを検索パイプラインに統合、表記ゆれ吸収テスト | `test_normalizer.py`で全パターン pass |
| **Day 10**<br>5/21 (水) | `integrity.py`（参照整合性チェック、`refs:`の有効性検証） | 壊れた参照を検出してログ出力 |
| **Day 11**<br>5/22 (木) | `marker.py`（マーカー方式、`<!-- AUTO_GENERATED_*** -->`ブロック処理） | 自動生成部分の更新で人間記述が保護される |
| **Day 12**<br>5/23 (金) | `tests/` 全充実、pytest設定、`GitHub Actions / ci.yml` | CI通過、テストカバレッジ70%以上 |
| **Day 13**<br>5/24 (土) | `docs/`整備: architecture.md、design-decisions.md、各機能docs | 採用担当者が docs/ 読んで設計判断を理解できる |
| **Day 14**<br>5/25 (日) | README v0.2版（差別化機能の説明追加）、**v0.2.0 タグ付与** | リリースノートと併せて公開 |

---

## 8. Week 3 詳細: v0.3.0（UI/UX最終形）

**目標**: Streamlit → Next.js + FastAPIへ移行、ポートフォリオ完成

| 日 | やること | 完了条件 |
|---|---|---|
| **Day 15**<br>5/26 (月) | `backend/api.py`（FastAPI、Streamlitから検索ロジックを分離）、OpenAPI仕様書自動生成 | `/api/search`、`/api/answer` エンドポイント動作 |
| **Day 16**<br>5/27 (火) | Next.js プロジェクト初期化、Tailwind CSS設定、ルーティング | `/` と `/settings` ページが表示される |
| **Day 17**<br>5/28 (水) | `SearchBar.tsx`、`AxisFilter.tsx`、`ResultCard.tsx` 実装 | フロントから backend を叩いて検索結果表示 |
| **Day 18**<br>5/29 (木) | `AnswerPanel.tsx`（RAG回答表示、出典リンク、ローディング状態） | ストリーミング風のUI、エラーハンドリング |
| **Day 19**<br>5/30 (金) | Docker構成更新（backend + frontend 別コンテナ）、E2E動作確認 | `docker-compose up` で両方起動、`localhost:3000`で利用可能 |
| **Day 20**<br>5/31 (土) | README完全版、デモGIF作成（OBS or ScreenToGif で録画）、設計ドキュメント最終整理 | READMEで30秒以内に価値が伝わる |
| **Day 21**<br>6/1 (日) | 最終バグ修正、**v0.3.0 タグ付与とリリースノート**、フューチャーES に GitHubリンク貼付 | フューチャーES提出と同時にリポジトリ公開 |

---

## 9. v1.0以降のロードマップ（READMEに記載）

これは作らないが、READMEに書いておく項目。「設計を見据えている」と読まれる:

- **v0.4**: プラグインシステム（embedder/LLMの差し替え可能）
- **v0.5**: マルチユーザー対応
- **v0.6**: クラウドデプロイガイド
- **v1.0**: ドキュメントサイト（mkdocs）、ロゴ、ブランディング

---

## 10. 日々の進め方（Cowork指示テンプレ）

毎日、Cowork に投げるときの基本パターン:

```
本日は Day [N] です。

【今日の目標】
[該当日のやることを上のスケジュールから貼る]

【完了条件】
[該当日の完了条件を貼る]

【今日のコミット粒度】
- 1コミット30〜50行を目安に
- コミットメッセージは [feat/fix/docs/refactor]: の prefix で
- 1日あたり3〜6コミット目安

【作業開始】
specに従って Day [N] の作業を進めてください。
完了したら commit を作成し、`git log --oneline` の出力を見せてください。
```

---

## 11. 健康とペース管理

**3週間プランの前提**:

- 1日のOSS作業時間: **2〜4時間が目安**（VEXUM業務、ES、修士研究と並行のため）
- 平日: 2〜3時間、週末: 4〜6時間で十分達成可能
- **睡眠は最低6時間確保**（24時前就寝推奨）
- 各週末は1日「予備日」として残す（遅れた分のキャッチアップ用）
- Day 7、Day 14、Day 21の**リリース日は早めに切り上げ**、ストレスなくタグ付与

**進捗チェックポイント**:
- 5/18: v0.1.0 リリース済みか
- 5/25: v0.2.0 リリース済みか
- 5/31: Next.js移行 90% 完了か

**遅延した場合の優先順位**:
1. **Week 1の v0.1.0 は絶対死守**（動くものがないとリポジトリの意味がない）
2. Week 2の差別化機能は**最低 表記ゆれ吸収**だけは入れる（他はv0.4へ繰り越し可）
3. Week 3のNext.js移行が間に合わなければ、**Streamlit版のままv0.3.0としてリリース**（最悪これでもOK）

---

## 12. 未確定事項（着手前に決める）

1. **リポジトリ名**: `axis-knowledge-rag` で確定？別案あれば
2. **GitHubユーザー名**: READMEと履歴書に使うので、確定形を要確認
3. **軸の初期構成**: 上記の `category / topic / level / author / year` で良いか
4. **Day 1 着手日**: 今日（5/12）から開始？それとも明日（5/13）から？
5. **作業時間帯**: 朝型 or 夜型？（健康管理上、何時までに切るかを決めておくと続きやすい）

---

## 13. 履歴書記述用テンプレ（参考）

**GitHub**: `github.com/[username]/axis-knowledge-rag`

**◯使用技術**:
Python / FastAPI / Next.js (TypeScript) / ChromaDB / Claude API / Gemini Embedding / YAML frontmatter / Docker / Git / GitHub Actions

**◯個人開発orチーム開発**: 個人開発（OSS公開）

**◯成果物概要**:
個人や小チーム向けのMarkdownナレッジに対するRAG検索Web Appフレームワーク（OSS）。ユーザーがYAML frontmatter付きMarkdownファイルをローカルに配置し、Docker一発で起動するWeb UIから自然言語問い合わせ・軸検索ができる。バックエンドはFastAPI、フロントはNext.js、ベクトル検索はChromaDB、埋め込みはGemini text-embedding-004（768次元）。Local-first設計で個人データを外部送信しない。

**◯背景**:
業務で営業の暗黙知を5軸ナレッジ化し、新人エージェントの初提案完成時間を1.5日→27分（98%短縮）に短縮した経験から、その設計思想を汎用OSSとして再構築。個人ブロガー、研究者、学生団体など、構造化ナレッジを必要とする誰もが使える形に汎用化する。

**◯工夫した点**:
- メタデータ駆動設計: YAML frontmatter で軸タグ付け、後方互換性を担保した段階導入を可能に
- 表記ゆれ吸収: NFKC正規化＋カタカナ→ひらがな変換で、日本語検索精度を実用レベルに引き上げ
- 参照整合性チェック: ナレッジ間の参照を自動検証し、構造の劣化を防ぐ
- マーカー方式の自動生成保護: `<!-- AUTO_GENERATED -->` で人間記述部分と自動生成部分を共存させ、再生成時の上書き事故を防止
- マルチLLMオーケストレーション: Claude API（生成）+ Gemini Embedding（埋め込み）を役割分担
- LangChain / LlamaIndex を意図的に不使用: RAGアーキテクチャを自前実装、設計理解の深さを担保

---

**このドキュメントは3週間ずっと参照するマスタードキュメント。Cowork に Day N の指示を投げるときに該当セクションを抜粋して使う。**
