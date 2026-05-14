# spec_014: Day 14 — v0.2.0 リリース (差別化機能リリース)

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜013, `docs/spec-v2.md` Day 14 行

## 1. 目的

```
[現状]
- v0.1.0 リリース済み (Day 7)
- Week 2 で normalizer / integrity / marker / pytest+CI / docs 拡充が完了
- まだリリースされていない、CHANGELOG は `[Unreleased]` のまま

[変更後]
- 全 CLI / Streamlit / Docker / CI のフルパス動作確認
- `CHANGELOG.md` の Unreleased を `[0.2.0] - 2026-05-25` に確定
- README に「v0.2 の新機能」セクション追加 (表記ゆれデモ、integrity 例)
- annotated tag `v0.2.0` を打って push
- GitHub Release v0.2.0 を作成
- 残課題 / 既知バグを Week 3 (v0.3.0) の inbox の起案メモとして outbox に書く
```

## 2. 制約

### 触ってよいファイル

- `CHANGELOG.md`
- `README.md` (v0.2 新機能セクション追加、ロードマップ更新)
- バグ修正があれば該当ファイル
- `_ai_workspace/bridge/outbox/result_014.md`
- `_ai_workspace/bridge/outbox/release-notes-v0.2.0.md` (Release 用)

### 触ってはいけないもの

- `_ai_workspace/bridge/inbox/`
- `docs/spec-v2.md`
- 既存 commit 履歴
- リポジトリ削除等の重大操作 (削除しない)

## 3. やってほしいこと

### 3-1. 事前バグスイープ

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"

# 全テスト
pytest -v
# 期待: 全 PASS、coverage 70%+

# ruff
ruff check .
# 期待: 0 violation

# CLI 動作確認 (全モジュール)
python -m backend.src.loader ./examples/knowledge
python -m backend.src.normalizer 2>/dev/null || true  # CLI なしの場合スキップ
python -m backend.src.integrity ./examples/knowledge
python -m backend.src.integrity ./examples/knowledge --strict || true  # broken refs 残ってれば exit 1
python -m backend.src.marker examples/knowledge/01-rag-patterns.md --list
python -m scripts.build_index ./examples/knowledge --reset
python -m backend.src.search "RAGとは" --category 技術記事
python -m backend.src.search "らぐ"  # 表記ゆれ吸収
python -m backend.src.rag "Claude API の活用方法は?"

# Streamlit (5 秒で kill)
timeout 8 streamlit run streamlit_app.py --server.headless=true || true

# Docker
docker compose build
docker compose up -d
sleep 5
curl -I http://localhost:8501
docker compose down

# LangChain / LlamaIndex 不使用確認
grep -RIn -E "langchain|llama_index|llama-index" backend/ streamlit_app.py scripts/ \
  && echo "FORBIDDEN IMPORT FOUND" || echo "OK"
```

バグ発見したら `fix:` コミットで修正、1 つにつき 1 コミット。

### 3-2. CHANGELOG.md 確定

```markdown
## [0.2.0] - 2026-05-25

### Added
- `normalizer.py` — NFKC + カタカナ→ひらがな + lowercase の正規化パイプライン
- `integrity.py` — 参照整合性チェック (broken refs / orphans / cycles)
- `marker.py` — `<!-- AUTO_GENERATED_*** -->` ブロックによる人間記述 / AI 生成の共存
- Normalizer を loader / vector_store / search パイプラインに統合
- `--strict-integrity` フラグを `scripts/build_index.py` に追加
- pytest 化、coverage 計測 (70%+)
- ruff lint 設定
- GitHub Actions CI (test + lint, Python 3.11/3.12 matrix)
- GitHub Actions Docker build workflow
- `docs/architecture.md`, `docs/design-decisions.md` (12 ADR), `docs/api-reference.md`

### Changed
- `Document` dataclass に `normalized_*` フィールド追加 (後方互換)
- ChromaDB metadata に `axis_*_norm` を追加 (生 axis は保持)

### Roadmap
- v0.3.0 (2026-06-01): Next.js + FastAPI 移行、UI/UX 最終形
```

### 3-3. README v0.2 セクション追加

```markdown
## v0.2 新機能 (2026-05-25)

### 表記ゆれ吸収

```bash
python -m backend.src.search "ＲＡＧ"  # 全角
python -m backend.src.search "RAG"    # 半角
python -m backend.src.search "らぐ"   # ひらがな
python -m backend.src.search "ラグ"   # カタカナ
# 全て同じ Document にヒット
```

### 参照整合性チェック

```bash
python -m backend.src.integrity ./examples/knowledge

# === Integrity Report ===
# Total documents: 10
# Total refs:      5
# ❌ Broken refs: 1
#   - doc_005 -> doc_999 (missing)
```

### AUTO_GENERATED ブロック

Markdown 内で `<!-- AUTO_GENERATED_START: <name> -->` 〜 `<!-- AUTO_GENERATED_END: <name> -->`
で囲まれた区画は自動生成として保護され、再生成で他の本文を上書きしません。

詳細: [docs/marker.md](docs/marker.md)
```

ロードマップ表で v0.2.0 を `✅ released` に。

### 3-4. リリースコミット + タグ + push

```bash
git add CHANGELOG.md README.md
git commit -m "chore(release): v0.2.0"

git tag -a v0.2.0 -m "v0.2.0 — Differentiation features

- 表記ゆれ吸収 (NFKC + katakana→hiragana)
- 参照整合性チェック
- AUTO_GENERATED マーカー方式
- pytest + ruff + CI
- ADR / API reference / architecture docs
"

git push origin main
git push origin v0.2.0
```

### 3-5. GitHub Release

`gh` CLI が dev-b 環境にあれば:

```bash
gh release create v0.2.0 \
  --title "v0.2.0 — Differentiation features" \
  --notes-file _ai_workspace/bridge/outbox/release-notes-v0.2.0.md
```

Release Notes は CHANGELOG の `[0.2.0]` をそのままコピー + 末尾に「次回 (v0.3.0) は Next.js + FastAPI 移行」。

### 3-6. Week 3 への引き継ぎメモ (任意、CC 側で書く)

`outbox/handoff-to-week3.md`:

- Week 2 で見つかった既知バグの一覧
- v0.3.0 (Next.js + FastAPI 移行) で気をつけるべき API の互換性
- DUMMY モードの維持が壊れやすい箇所
- Streamlit から Next.js 移行で「これは捨ててもいい」既存コード一覧

### 3-7. result_014.md

- 全 PASS の最終ログ抜粋
- CHANGELOG diff
- `git tag` 出力
- Release URL (https://github.com/kazikimaguro13/axis-knowledge-rag/releases/tag/v0.2.0)
- Week 3 引き継ぎメモのリンク

## 4. 成功条件

- [ ] 全テスト / lint / CLI / Streamlit / Docker / CI で動作
- [ ] CHANGELOG が `[0.2.0] - 2026-05-25` で確定
- [ ] `v0.2.0` annotated tag が GitHub に存在
- [ ] GitHub Release v0.2.0 が作成 (CLI 不可なら手動手順を result に)
- [ ] dev-b で push 完了
- [ ] LangChain / LlamaIndex 不使用維持

## 5. 出力先

`_ai_workspace/bridge/outbox/result_014.md`

## 6. 質問

- **doc_999 壊れリンクの扱い**: spec_010 で議論。v0.2.0 で残すなら README/integrity demo にとって最高の素材、修正するなら integrity の strict モードを Day 14 で初めて使う形になる。判断未定なら Open question で残す
- **public 化のタイミング**: spec_007 で public 化しているはず。万一未公開なら Day 14 で公開、判断つかなければ停止
- **email プレースホルダ**: spec_001 で削除した `pyproject.toml authors` の email、Day 14 で最終決定 (実 email or GitHub `noreply`)

## 7. 補足

### 設計の意図

- **v0.2.0 はあくまで「差別化機能の集大成」**: 機能追加は最小限、品質と docs を整えるリリース
- **Week 3 引き継ぎメモ**: bridge 運用の良さ、後続 spec 作成時の素材になる

### Week 3 連携 (spec_015 以降)

Week 3 は仕様書セクション 8 の Day 15〜21:
- spec_015 (Day 15): FastAPI 化 (`backend/src/api.py`)
- spec_016 (Day 16): Next.js プロジェクト初期化
- spec_017 (Day 17): SearchBar / AxisFilter / ResultCard
- spec_018 (Day 18): AnswerPanel + ストリーミング風 UI
- spec_019 (Day 19): Docker 分割 + E2E
- spec_020 (Day 20): デモ GIF + README 完全版
- spec_021 (Day 21): v0.3.0 リリース + フューチャー ES 提出
