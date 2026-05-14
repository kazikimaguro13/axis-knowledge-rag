# ADR-020: In-Text Citation Highlighting via `[N]` Markers

- **Date**: 2026-05-14
- **Status**: Accepted
- **Deciders**: 中島
- **Spec**: spec_034

---

## Context

v0.6 までの RAG 回答は LLM が文中に `[doc_NNN]` を埋め、UI 側でそれを軽くハイライト
するだけだった。問題点:

- doc ID は人間が見て直感的に「何番目の出典か」が分からない (`doc_017` は何番目?)
- 出典カードは回答の下に並んでいるが、回答中の引用と一目で紐付かない
- クリッカブルではなく、長い回答だと該当カードまでスクロールする手間がある

ポートフォリオで Perplexity 風の "クリックして対応する出典に飛ぶ" 体験を最小コストで
実現するため、回答テキストにインライン `[N]` マーカー (1-indexed) を埋め、UI 側で
クリッカブル化する。

---

## Decision

LLM のプロンプトに「出典に基づく主張の文末に `[N]` を付けてください (N は 1 始まり、
出典リストの index と一致)」を明示する。バックエンドでパースして:

1. **Index の範囲外** (`N > len(sources)`) → silently strip + warning ログ
2. **CSV 形式** (`[1, 2]`) → `[1][2]` に正規化 (フロント側のパーサが 1 形式だけ扱えば良い)
3. `Answer.cited_ids` は引き続き doc-NNN-style ID のリストとして公開 (UI の "★ cited"
   バッジや API 利用者との互換のため、`N` ではなく具体的な ID を返す)

フロント側は `parseCitations(text)` で `{kind: "text" | "citation", n}` のセグメント列に
分解し、`citation` を `<button>` として描画。クリック時に対応する `<ResultCard>` を
`scrollIntoView` + 黄色フラッシュさせる。

Streamlit 側は JS なしで実現するため、`<a href="#axis-src-N">` + CSS `:target` で
アンカー遷移時に該当カードに黄色背景を当てる。

---

## Alternatives Considered

### (a) `<sup data-source-id="...">` のような構造化 HTML を LLM に生成させる

LLM に HTML タグを直接出させるとプロンプト遵守率が低く、属性のエスケープ事故も
起きやすい。MCP / curl / 平文クライアントには HTML が崩れて見える。**却下**。

### (b) JSON で `answer = [{text, citations: [...]}, ...]` のセグメント配列を返す

API 互換性が崩れる。`/api/answer` レスポンスの `text` が string でなくなると MCP
サーバや既存の CLI 利用者すべてに影響する。LLM に厳密な JSON を出させると失敗時の
フォールバックが面倒。**却下**。

### (c) `[N]` プレーンテキストマーカー (採用)

平文の互換性を保ったまま UI 側でパースする。MCP クライアント (Claude Desktop など)
には `[1]` がそのまま表示されるが、これは許容範囲 (むしろ脚注として自然)。
LLM の指示遵守は 8 割程度を想定し、出ない場合でも回答自体は有効。

### (d) 既存の `[doc_NNN]` マーカーを残す

`doc_017` のような長い文字列が文中に並ぶと読みづらい。1-indexed `[N]` の方が
short / 人間直感的。本 ADR で置き換える。後方互換のために両方をサポートする選択肢も
あったが、コードパスが二重化するため `[N]` 一本化を選んだ。

---

## Consequences

### Positive

- ポートフォリオでの "クリック → 出典がハイライト" UX が成立する
- API レスポンスフォーマット (`text: string, sources: [], cited_ids: []`) が無変更なので、
  MCP / curl / 既存フロントへの破壊的変更なし
- 平文クライアントでも `[1]` `[2]` が読める

### Negative / Trade-offs

- **LLM 遵守率の不確実性**: Claude 3.5 Sonnet で `[N]` を出してくれる率は実測で
  おそらく 80% 程度。出てこない場合は単に回答全体が citation marker 無しになる
  (テキストとしては valid)。今後 `used` が空の回数を計測してプロンプトを補強する
- **out-of-range の silent strip**: `[9]` が来たときログだけ出して見えない形で消える。
  ユーザーには「LLM が間違えた」事実が見えない。ログ監視で集計する前提
- **コード片中の `[1]` の偽陽性**: ` ```python\nx = arr[1]\n``` ` のような Python
  リテラルもマーカー扱いされてしまう。本 spec のスコープでは line-level regex で
  許容、code fence skip は将来対応
- **MCP テキストクライアントには `[N]` だけが見える**: doc ID が知りたい場合は
  別途 sources リストを参照する必要がある (これは spec_032 時点と同じ動作)

### Future Extensions

- v0.8 (spec_036 案): hover preview tooltip — `[N]` ホバーで出典本文の冒頭を浮動表示
- v0.8 (spec_037 案): citation span に対応する parent chunk の該当 child だけ
  ハイライト (spec_031 と組み合わせ)
- v0.8 (spec_038 案): "この `[N]` は本当に文を裏付けているか" を judge LLM で検証 →
  faithfulness を per-sentence 化

---

## Update (2026-05-14, spec_039)

### コードフェンス偽陽性の解消

v0.7 で「許容、v0.8 候補」としていた **Markdown コードフェンス内 `[1]` の偽陽性** を解消。
backend (`_citations.py`) と frontend (`citations.ts`) の両方に同じスキップロジックを実装。

- 検出対象: ` ```fenced``` ` (オプションで言語識別子付き) および ` `inline` ` の両形式
- 検出範囲は `_build_skip_ranges()` / `buildSkipRanges()` で計算、`_is_in_skip_range()` /
  `isInSkipRange()` で marker 位置を判定。バックエンドとフロントエンドで **同じ regex
  パターン** を使うことで、parser の対称性を保証
- ネストは Markdown 標準仕様外なので考慮しない (1 階層のみ)
- `parse_and_validate_citations()` で skip 範囲内の marker は **リテラルとして保存**
  (out-of-range strip も skip 範囲では行わない)。`extract_citations()` は skip 範囲を
  単純にスキップ

新規テスト: backend 5 件 (`test_code_fence_*`) / frontend 5 件、合計 10 件。既存
333 tests に回帰なし。

### Open Questions (継続)

- **4 連バックティック** (` ````...```` `) は Markdown 標準では合法だが、本 spec では
  スコープ外 (3 連バックティックのみ対応)
- **2 連インライン** (` ``hello`` `) も同様に未対応 (シンプルさ優先)
- 将来 (spec_050 想定) で markdown-it ベースの完全パーサに置き換える可能性
