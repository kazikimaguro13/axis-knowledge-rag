# spec_034: In-Text Citation Highlighting (回答内出典ハイライト)

- **Author**: Cowork (中島)
- **Created**: 2026-05-14
- **Target**: Claude Code (`dev-b` or `dev-d` — UI 主体なので b 推奨)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: v0.7 サブ (リリース直前に滑り込み)。Gemini 案 ⑧
- **Depends on**: spec_031 (parent doc sources), spec_032 (chat UI で表示先が増える)
- **Recommended dispatch after**: spec_031 + spec_032 が main にマージされたあと

## 1. 目的

v0.6 までの RAG 回答は「文末に出典一覧」スタイル。質問者は **どの一文がどの出典に基づいているか** がパッと分からない。

これを **インライン引用** + **クリックハイライト** で改善する。回答テキスト中に `[1]` `[2]` のような上付きマーカーを埋め込み、UI 側でクリックすると対応する source カードがハイライト + スクロール表示される。

```
[現状]
回答: "RAG は検索 + 生成の組み合わせです。BM25 とベクトルのハイブリッドが推奨です。"
出典: [1] 01-rag-patterns.md, [2] 02-vector-search.md
→ どの文が [1] でどの文が [2] かユーザーは推測するしかない

[変更後]
回答: "RAG は検索 + 生成の組み合わせです[1]。BM25 とベクトルのハイブリッドが推奨です[2]。"
出典: [1] 01-rag-patterns.md, [2] 02-vector-search.md
→ [1] をクリック → 出典 1 のカードが黄色ハイライト + 視界に入る位置にスクロール
→ ホバー → 該当出典をプレビュー (tooltip)
```

## 2. 制約

### 触ってよいファイル

- `backend/src/rag.py` — Claude へのプロンプトに「文末に [N] を付けて」を追記、ポストプロセスで [N] を確実に source index にマップ
- `backend/src/_citations.py` — **新規** (回答テキスト中の [N] → source index バインダー、parse + 検証)
- `backend/tests/test_citations.py` — **新規**
- `backend/tests/test_rag.py` — citation 付き回答の e2e テスト追加
- `frontend/src/components/AnswerPanel.tsx` — [N] パーサ + クリッカブル span 化
- `frontend/src/components/SourceCard.tsx` — `highlighted` prop 追加 + ハイライト CSS
- `frontend/src/components/ChatMessage.tsx` (spec_032 で新設想定) — 同じパーサ適用
- `frontend/src/lib/citations.ts` — **新規** (renderWithCitations 共通関数)
- `frontend/src/styles/globals.css` (or Tailwind config) — `.citation-marker` / `.source-highlighted` クラス
- `streamlit_app.py` — st.markdown + JS injection で同等機能 (st.html or st.components.v1.html)
- `docs/api-reference.md` — `/api/answer` レスポンス例で [N] 付きを明記
- `docs/adr/ADR-020-citation-highlighting.md` — **新規** (UI 仕様、マーカー記法の根拠)
- `README.md` — Features に 1 行
- `CHANGELOG.md` — Day 34 追記

### 触ってはいけないもの

- `backend/src/{search,chunker,vector_store,loader,bm25*,normalizer,integrity,marker,ingester}.py` — 検索ロジックには手を入れない
- `mcp_server/` — MCP は text-only クライアント (Claude Desktop) で UI 概念がないため変更なし。citation marker [N] は raw text に残るので互換 OK
- `_ai_workspace/`

### コーディングルール

- マーカー記法は **`[N]` (半角括弧、N は 1 始まり整数)**。複数同時引用は `[1][2]` または `[1, 2]` の両方を許容
- 回答テキスト中に **存在しない N** が出た場合は **silently strip** (regression を出さない、ログにのみ warning)
- 新規依存 0 (パーサは正規表現で書ける)
- 既存テスト互換 (回答出力フォーマットは互換: marker が無い回答も valid)

### デプロイ

- 本 spec は v0.7.0 直前のリリーススライドイン。tag/Release は v0.7.0 で一括

## 3. やってほしいこと

### 3-1. RAG 出力に [N] を埋め込む (`backend/src/rag.py`)

#### プロンプト修正

既存 `answer()` (or `answer_from_hits()`) の system prompt 末尾に追加:

```python
SYSTEM_PROMPT_TAIL = """\

## 引用ルール
- 出典に基づく主張の文末に `[N]` を付けてください (N は 1 始まり、出典リストの index と一致)
- 複数の出典が同じ主張を裏付ける場合は `[1][2]` のように連続させてください
- 出典に書かれていない一般論や前置きには [N] を付けないでください
- 不明な場合は無理に [N] を付けず、本文だけ返してください
"""
```

#### ポストプロセス

```python
from backend.src._citations import parse_and_validate_citations

def answer_from_hits(question, hits, **kw) -> tuple[str, list[Source]]:
    raw_answer = _call_claude(question, hits)
    answer, used_indices = parse_and_validate_citations(raw_answer, n_sources=len(hits))
    sources = [hits[i].to_source() for i in range(len(hits))]
    return answer, sources
```

### 3-2. Citation parser (`backend/src/_citations.py`)

```python
"""Parse [N] markers in RAG output, validate against source count, strip invalid ones."""

from __future__ import annotations
import re
import logging

_log = logging.getLogger(__name__)

# matches [1], [12], also [1][2] (consecutive) and [1, 2]
_RE_MARKER = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def parse_and_validate_citations(text: str, *, n_sources: int) -> tuple[str, set[int]]:
    """Return (cleaned_text, set_of_used_source_indices_0based).

    - Strips markers referencing N > n_sources (logs warning).
    - Preserves 1-based [N] notation in output (UI is responsible for mapping).
    """
    used: set[int] = set()

    def _replace(m: re.Match) -> str:
        nums_str = m.group(1)
        nums = [int(x.strip()) for x in nums_str.split(",")]
        valid = [n for n in nums if 1 <= n <= n_sources]
        invalid = [n for n in nums if n not in valid]
        if invalid:
            _log.warning("citation out of range: %s (n_sources=%d)", invalid, n_sources)
        if not valid:
            return ""
        used.update(n - 1 for n in valid)
        # canonical form: separate brackets
        return "".join(f"[{n}]" for n in valid)

    cleaned = _RE_MARKER.sub(_replace, text)
    return cleaned, used


def extract_citations(text: str) -> list[tuple[int, int, int]]:
    """Return list of (start_offset, end_offset, n_1based) for UI rendering."""
    out: list[tuple[int, int, int]] = []
    for m in _RE_MARKER.finditer(text):
        nums_str = m.group(1)
        nums = [int(x.strip()) for x in nums_str.split(",")]
        # Each number in a comma-separated list gets the SAME span (UI can split if needed)
        for n in nums:
            out.append((m.start(), m.end(), n))
    return out
```

### 3-3. Frontend パーサ (`frontend/src/lib/citations.ts`)

```ts
export type Segment =
  | { kind: "text"; text: string }
  | { kind: "citation"; n: number };

const RE_MARKER = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

export function parseCitations(text: string): Segment[] {
  const segments: Segment[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = RE_MARKER.exec(text)) !== null) {
    if (m.index > lastIndex) {
      segments.push({ kind: "text", text: text.slice(lastIndex, m.index) });
    }
    for (const n of m[1].split(",").map(s => parseInt(s.trim(), 10))) {
      if (!Number.isNaN(n)) segments.push({ kind: "citation", n });
    }
    lastIndex = m.index + m[0].length;
  }
  if (lastIndex < text.length) {
    segments.push({ kind: "text", text: text.slice(lastIndex) });
  }
  return segments;
}
```

### 3-4. AnswerPanel.tsx 修正

```tsx
import { useState } from "react";
import { parseCitations } from "@/lib/citations";
import { SourceCard } from "./SourceCard";

type Props = { answer: string; sources: { doc_id: string; title: string; text: string }[] };

export function AnswerPanel({ answer, sources }: Props) {
  const [highlighted, setHighlighted] = useState<number | null>(null);
  const segments = parseCitations(answer);

  function focusSource(n: number) {
    setHighlighted(n - 1);
    document.getElementById(`source-${n}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    // auto-clear highlight after 3s
    setTimeout(() => setHighlighted(curr => (curr === n - 1 ? null : curr)), 3000);
  }

  return (
    <div>
      <div className="prose prose-sm max-w-none">
        {segments.map((s, i) =>
          s.kind === "text" ? (
            <span key={i}>{s.text}</span>
          ) : (
            <button
              key={i}
              type="button"
              onClick={() => focusSource(s.n)}
              className="citation-marker mx-0.5 inline-flex items-baseline align-super text-xs font-semibold text-blue-600 hover:bg-yellow-200 px-1 rounded transition"
              title={sources[s.n - 1]?.title ?? "Unknown source"}
            >
              [{s.n}]
            </button>
          )
        )}
      </div>
      <div className="mt-6 space-y-2">
        {sources.map((src, i) => (
          <SourceCard
            key={i}
            id={`source-${i + 1}`}
            n={i + 1}
            source={src}
            highlighted={highlighted === i}
          />
        ))}
      </div>
    </div>
  );
}
```

### 3-5. SourceCard.tsx 修正

`highlighted` prop が true のとき:
- 黄色背景に 1 秒間トランジション
- `data-highlighted` 属性付与でテスト可能に

```tsx
type Props = {
  id: string;
  n: number;
  source: { doc_id: string; title: string; text: string };
  highlighted?: boolean;
};

export function SourceCard({ id, n, source, highlighted }: Props) {
  return (
    <article
      id={id}
      data-highlighted={highlighted ? "true" : "false"}
      className={`rounded border p-3 transition-colors duration-500 ${
        highlighted ? "bg-yellow-100 border-yellow-400" : "bg-white border-gray-200"
      }`}
    >
      <header className="flex items-baseline justify-between">
        <span className="text-xs text-gray-500">[{n}]</span>
        <h3 className="text-sm font-semibold">{source.title}</h3>
        <span className="ml-auto text-xs text-gray-400">{source.doc_id}</span>
      </header>
      <p className="mt-1 text-sm text-gray-700 line-clamp-4">{source.text}</p>
    </article>
  );
}
```

### 3-6. Streamlit 側 (`streamlit_app.py`)

Streamlit はピュア HTML/JS の柔軟性が低いので、`st.components.v1.html` で小さな HTML island を出すか、シンプルに `st.markdown` で `<a href="#source-1">[1]</a>` を生成 (アンカーリンク方式) で OK:

```python
import re
import streamlit as st

def render_answer_with_citations(answer: str, sources: list[dict]):
    # Replace [N] with anchor links
    def _link(m):
        nums = [int(x.strip()) for x in m.group(1).split(",")]
        out = []
        for n in nums:
            if 1 <= n <= len(sources):
                out.append(f'<a href="#source-{n}" class="cite">[{n}]</a>')
        return "".join(out)

    html = re.sub(r"\[(\d+(?:\s*,\s*\d+)*)\]", _link, answer)
    st.markdown(f"""
    <style>
      .cite {{ color: #2563eb; text-decoration: none; font-weight: 600; }}
      .cite:hover {{ background: #fde68a; }}
      .src-card:target {{ background: #fef9c3; transition: background 1s; }}
    </style>
    <div class="answer">{html}</div>
    """, unsafe_allow_html=True)

    for i, s in enumerate(sources, 1):
        st.markdown(f"""
        <article id="source-{i}" class="src-card" style="padding:8px;border:1px solid #e5e7eb;border-radius:6px;margin:6px 0;">
          <strong>[{i}] {s['title']}</strong> <small>{s['doc_id']}</small>
          <p style="margin-top:4px;color:#374151;">{s['text'][:300]}...</p>
        </article>
        """, unsafe_allow_html=True)
```

CSS `:target` セレクタで anchor 移動時に自動ハイライト。Streamlit の `st.session_state` 制約を避けるためサーバラウンドトリップなし。

### 3-7. テスト (`backend/tests/test_citations.py`)

```python
from backend.src._citations import parse_and_validate_citations, extract_citations


def test_basic_citation():
    text = "RAG is great[1]. BM25 helps[2]."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "RAG is great[1]. BM25 helps[2]."
    assert used == {0, 1}


def test_multi_citation():
    text = "Both true[1, 2]."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "Both true[1][2]."
    assert used == {0, 1}


def test_consecutive():
    text = "Yes[1][2]."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "Yes[1][2]."
    assert used == {0, 1}


def test_out_of_range_stripped():
    text = "Bad[3] good[1]."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "Bad good[1]."
    assert used == {0}


def test_no_citations_passthrough():
    text = "No markers here."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "No markers here."
    assert used == set()


def test_extract_offsets():
    text = "A[1] B[2,3]."
    offsets = extract_citations(text)
    # [1] at offset 1, [2,3] at offset 6
    assert (1, 4, 1) in offsets
    assert any(end == 11 and n == 3 for _, end, n in offsets)
```

`backend/tests/test_rag.py` に追加 (Claude API mock):

```python
def test_answer_includes_citation_markers(mock_claude, mock_hits_2_sources):
    mock_claude.return_value = "First fact[1]. Second fact[2]."
    answer, sources = answer_from_hits("Q?", mock_hits_2_sources)
    assert "[1]" in answer and "[2]" in answer
    assert len(sources) == 2


def test_answer_strips_invalid_citation(mock_claude, mock_hits_1_source):
    mock_claude.return_value = "Real[1]. Fake[5]."
    answer, sources = answer_from_hits("Q?", mock_hits_1_source)
    assert "[5]" not in answer
    assert "[1]" in answer
```

Frontend (`frontend/__tests__/citations.test.ts`):

```ts
import { parseCitations } from "@/lib/citations";

test("single citation", () => {
  expect(parseCitations("A[1] B")).toEqual([
    { kind: "text", text: "A" },
    { kind: "citation", n: 1 },
    { kind: "text", text: " B" },
  ]);
});

test("multi citation [1, 2]", () => {
  expect(parseCitations("X[1, 2]")).toEqual([
    { kind: "text", text: "X" },
    { kind: "citation", n: 1 },
    { kind: "citation", n: 2 },
  ]);
});
```

### 3-8. ADR-020

`docs/adr/ADR-020-citation-highlighting.md`:

- Context: 回答内のどの文がどの出典かが不明 → ユーザー信頼度低下
- Decision: `[N]` インラインマーカー (1 始まり) + UI 側でクリッカブル化
- Alternatives:
  - (a) `<sup data-source-id="...">` のような構造化 HTML を生成 → 却下: MCP / pure-text クライアントで崩れる
  - (b) JSON で answer = `[{text, citations: []}, ...]` のセグメント配列 → 却下: 既存 API 互換崩壊
  - (c) `[N]` plain text マーカー → **採用**: pure text 互換、UI は parser で展開
- Consequences:
  - MCP クライアントは [N] がそのまま見える (許容)
  - LLM が指示を守らないと marker が出ないことがある (n_used=0 をログ収集して将来チューン)

### 3-9. 動作確認

```bash
cd ~/projects/axis-knowledge-rag
git checkout -b feat/spec_034-citation-highlighting

# Backend
ruff check .
python3 -m pytest -q backend/tests/test_citations.py backend/tests/test_rag.py -v

# Manual e2e
uvicorn backend.src.api:app --port 8000 &
sleep 3
curl -s -X POST http://localhost:8000/api/answer -H 'Content-Type: application/json' \
  -d '{"query":"RAG とは"}' | jq -r '.answer'
# → 期待: 文末に [1] [2] が含まれる
kill %1

# Frontend
cd frontend && npm test -- citations
npm run build

# Streamlit smoke (手動)
streamlit run streamlit_app.py
```

### 3-10. コミット粒度

1. `feat(rag): add citation markers [N] to LLM prompt + post-process`
2. `feat(citations): _citations.py parser/validator + tests`
3. `feat(frontend): citations.ts parser + AnswerPanel citation buttons`
4. `feat(frontend): SourceCard highlighted state + scroll-into-view`
5. `feat(streamlit): anchor-link based citation rendering with :target CSS`
6. `docs: ADR-020 + api-reference example + README feature line`
7. `chore: CHANGELOG Day 34`

`git push -u origin feat/spec_034-citation-highlighting`

### 3-11. result_034.md に書くこと

- /api/answer のサンプル response (citation 入り、入らないケース両方)
- 既存 LLM (Claude) が指示通り [N] を出してくれる率 (10 サンプル) — 出ない場合の補強案
- 新規テスト数、ruff / pytest
- スクショ取得手順 (手動)

## 4. 成功条件

- [ ] [N] パーサが backend / frontend で対称
- [ ] out-of-range [N] が silently strip される
- [ ] AnswerPanel で citation クリック → SourceCard ハイライト + scroll
- [ ] Streamlit でアンカーリンク経由のハイライト動作
- [ ] 既存 tests 全緑 + citation 新規 >=8 件
- [ ] MCP `axis_answer` 回答は変更なし (raw text に [N] が含まれる程度)
- [ ] ADR-020 / docs / CHANGELOG 更新
- [ ] git push 完了

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_034.md`

## 6. 質問があるとき

- **LLM が [N] を出してくれない率**: Claude 3.5 Haiku で system prompt 末尾に明示しても 1-2 割は出ないかも。回答品質より頻度を取るなら 2-shot exemplars をプロンプトに足す。CC 判断
- **chat 履歴での [N]**: 履歴ターンの answer にも [N] が残るが、別ターンの出典 index とは紐付かない。本 spec では「履歴の [N] は装飾扱いで非インタラクティブ」とする
- **Markdown 内コード片の [N]**: ```python\nx = arr[1]\n``` のような偽陽性は OK で良いか。シンプルに line-level regex なので **コード内 [1] もマーカー化されて見栄えが悪い** ことがある。許容して docs に注意書き、または code fence 内は skip するパーサ拡張のどちらか

迷ったら Open questions に書いて `status: blocked` で終了。

## 7. 補足

### 設計の意図

- ポートフォリオで「Perplexity 風 UX」を最小コストで実現
- API レスポンスフォーマット (answer: string, sources: list) は変えない → 既存 MCP / curl 利用者へ影響なし

### 将来の拡張余地

- spec_036 候補 (v0.8): hover preview tooltip (出典本文を浮動表示)
- spec_037 候補 (v0.8): citation span に対応する **parent chunk の該当 child だけハイライト** (spec_031 と組み合わせ)
- spec_038 候補 (v0.8): 「この [N] は本当に文を裏付けているか」を judge LLM で検証 → faithfulness を per-sentence 化
