# spec_018: Day 18 — AnswerPanel + ストリーミング風 UI + 出典リンク

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: spec_001〜017, `docs/spec-v2.md` Day 18 行

## 1. 目的

```
[現状]
- Day 17 で /api/search 経由の検索 UI 完成
- RAG 回答 (/api/answer) は未統合

[変更後]
- `AnswerPanel.tsx` コンポーネント追加: 質問入力 + 回答表示
- 「検索のみ」と「RAG 回答も生成」の切替トグル
- ローディング中のスケルトン UI (ストリーミング風アニメーション)
- 回答中の [doc_NNN] を ResultCard へのリンクに変換 (アンカー)
- cited な ResultCard には `★ cited` バッジハイライト (spec_005 と同じデザイン)
- エラーハンドリング: API timeout / DUMMY モード警告 / no-result
```

## 2. 制約

### 触ってよいファイル

- `frontend/src/components/AnswerPanel.tsx` — 新規
- `frontend/src/components/SkeletonLoader.tsx` — 新規
- `frontend/src/components/ResultCard.tsx` — `cited` prop の活用、`#doc_NNN` への anchor id
- `frontend/src/app/page.tsx` — AnswerPanel 統合
- `CHANGELOG.md`

### 触ってはいけないもの

- backend (Day 4 で確定済み)
- `frontend/src/lib/api.ts` (Day 16 で確定)
- 既存 layout / SearchBar / AxisFilter
- `_ai_workspace/`、`docs/spec-v2.md`

### コーディングルール

- TypeScript strict、useState のみ
- streaming はサーバー側に SSE/WS を入れず、**疑似ストリーミング** (回答テキストを文字ずつ表示する CSS アニメ + 一定間隔で `setInterval` で typewriter 風)
- 出典の正規表現: `\[(doc_\d+)\]`
- アクセシビリティ: `role="alert"` for errors, `aria-live="polite"` for answer panel

## 3. やってほしいこと

### 3-1. `SkeletonLoader.tsx`

```tsx
"use client";

export default function SkeletonLoader() {
  return (
    <div className="animate-pulse space-y-2 rounded border border-slate-200 bg-white p-4">
      <div className="h-3 w-1/4 rounded bg-slate-200" />
      <div className="h-3 w-full rounded bg-slate-200" />
      <div className="h-3 w-5/6 rounded bg-slate-200" />
      <div className="h-3 w-3/4 rounded bg-slate-200" />
    </div>
  );
}
```

### 3-2. `AnswerPanel.tsx`

```tsx
"use client";

import { useEffect, useState } from "react";

interface Props {
  text: string;
  citedIds: string[];
  isLoading: boolean;
  isDummy: boolean;
  model: string | null;
  error: string | null;
}

const CITATION_RE = /\[(doc_\d+)\]/g;

function renderWithCitations(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = CITATION_RE.exec(text)) !== null) {
    if (m.index > lastIndex) {
      parts.push(text.slice(lastIndex, m.index));
    }
    parts.push(
      <a
        key={`cite-${i++}`}
        href={`#${m[1]}`}
        className="mx-0.5 rounded bg-emerald-100 px-1 text-xs font-medium text-emerald-700 no-underline hover:bg-emerald-200"
      >
        [{m[1]}]
      </a>
    );
    lastIndex = m.index + m[0].length;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}

export default function AnswerPanel({
  text,
  citedIds,
  isLoading,
  isDummy,
  model,
  error,
}: Props) {
  // typewriter effect for pseudo-streaming
  const [displayed, setDisplayed] = useState("");
  useEffect(() => {
    if (!text) {
      setDisplayed("");
      return;
    }
    setDisplayed("");
    let i = 0;
    const id = setInterval(() => {
      i += Math.max(1, Math.floor(text.length / 80));
      if (i >= text.length) {
        setDisplayed(text);
        clearInterval(id);
      } else {
        setDisplayed(text.slice(0, i));
      }
    }, 25);
    return () => clearInterval(id);
  }, [text]);

  if (isLoading) {
    return (
      <section className="space-y-2" aria-live="polite" aria-busy>
        <h2 className="text-lg font-semibold">💡 回答</h2>
        <div className="space-y-2">
          <div className="h-4 w-1/3 animate-pulse rounded bg-slate-200" />
          <div className="h-4 w-full animate-pulse rounded bg-slate-200" />
          <div className="h-4 w-2/3 animate-pulse rounded bg-slate-200" />
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">
        ⚠ 回答生成エラー: {error}
      </section>
    );
  }

  if (!text) {
    return null;
  }

  return (
    <section aria-live="polite" className="space-y-2 rounded border border-emerald-200 bg-emerald-50 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">💡 回答</h2>
        <span className="text-xs text-slate-500">
          {isDummy ? "DUMMY mode" : `model: ${model ?? "?"}`}
          {citedIds.length > 0 && `  ·  cited: ${citedIds.join(", ")}`}
        </span>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
        {renderWithCitations(displayed)}
      </p>
    </section>
  );
}
```

### 3-3. `ResultCard.tsx` に anchor id を追加

```tsx
<article
  id={result.id}  // ← 追加。AnswerPanel の <a href="#doc_NNN"> から飛ぶ
  className={...}
>
```

### 3-4. `page.tsx` 統合

```tsx
"use client";

import { useState } from "react";
import AnswerPanel from "@/components/AnswerPanel";
import AxisFilter from "@/components/AxisFilter";
import ResultCard from "@/components/ResultCard";
import SearchBar from "@/components/SearchBar";
import { api, AnswerResponse, SearchResultPayload } from "@/lib/api";

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Record<string, string | number>>({});
  const [results, setResults] = useState<SearchResultPayload[]>([]);
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [withRag, setWithRag] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    if (!query && Object.keys(filters).length === 0) return;
    setIsLoading(true);
    setError(null);
    setAnswer(null);
    try {
      if (withRag && query) {
        const ans = await api.answer({ question: query, filters, top_k: 5 });
        setAnswer(ans);
        setResults(ans.sources);
      } else {
        const r = await api.search({ query: query || null, filters, top_k: 10 });
        setResults(r.results);
      }
    } catch (e) {
      setError(String(e));
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-[240px_1fr]">
      <AxisFilter filters={filters} onChange={setFilters} />
      <section className="space-y-4">
        <h1 className="text-2xl font-bold">検索</h1>
        <SearchBar value={query} onChange={setQuery} onSubmit={handleSearch} isLoading={isLoading} />

        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={withRag}
            onChange={(e) => setWithRag(e.target.checked)}
          />
          RAG 回答も生成する (`/api/answer`)
        </label>

        <AnswerPanel
          text={answer?.text ?? ""}
          citedIds={answer?.cited_ids ?? []}
          isLoading={isLoading && withRag}
          isDummy={answer?.is_dummy ?? false}
          model={answer?.model ?? null}
          error={error}
        />

        {results.length > 0 && (
          <p className="text-sm text-slate-500">📚 関連資料 {results.length} 件</p>
        )}
        <div className="space-y-3">
          {results.map((r) => (
            <ResultCard
              key={r.id}
              result={r}
              cited={answer?.cited_ids?.includes(r.id) ?? false}
            />
          ))}
        </div>
        {!isLoading && results.length === 0 && !error && (
          <p className="text-sm text-slate-400">
            左のフィルタを設定して検索バーから問い合わせてください。
          </p>
        )}
      </section>
    </div>
  );
}
```

### 3-5. 動作確認

```bash
# Terminal 1: backend
cd ~/projects/axis-knowledge-rag
uvicorn backend.src.api:app --reload --port 8000

# Terminal 2: frontend
cd ~/projects/axis-knowledge-rag/frontend
npm run dev
# http://localhost:3000
```

ブラウザで:

1. デフォルトで「RAG 回答も生成する」がチェック
2. 質問入力 → 回答 (typewriter で表示) + 関連資料カード
3. 回答中の [doc_001] をクリック → 該当カードへスクロール
4. cited なカードは緑枠 + ★ cited バッジ
5. チェックを外すと search のみ (高速)

### 3-6. コミット

1. `feat: add SkeletonLoader component`
2. `feat: add AnswerPanel with typewriter effect and citation links`
3. `feat: add #anchor to ResultCard for jump-to-source`
4. `feat: integrate AnswerPanel into / with RAG toggle`
5. `docs: changelog Day 18`

`git push origin main` (dev-b)

### 3-7. result_018.md

- typewriter 速度の調整値 (25ms 間隔、80 等分が妥当か)
- DUMMY モードでの動作確認
- citation リンクが anchor jump できるか

## 4. 成功条件

- [ ] `/api/answer` から取得した text が typewriter 風に表示
- [ ] `[doc_NNN]` がアンカーリンクになり、ResultCard へジャンプ
- [ ] cited な ResultCard に ★ cited バッジ
- [ ] RAG トグルで search-only / RAG 切替動作
- [ ] DUMMY モードでエラーなし
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_018.md`

## 6. 質問

- **typewriter のパフォーマンス**: 長い回答 (2000 chars) で setInterval が重くなる可能性、その場合は `requestAnimationFrame` ベースに切替
- **citation 抽出を frontend vs backend**: 今は frontend regex、`Answer.cited_ids` (backend で抽出済み) を信頼するなら frontend regex は冗長。両方持つことの可読性 vs 単一情報源
- **モバイル対応**: Day 18 では未対応、Day 20 でスクショ撮るまでにはレスポンシブ崩れがないことだけ確認

## 7. 補足

### 設計の意図

- **疑似ストリーミング**: 本物の SSE/WS は backend を作り直す必要、Week 3 の中盤ではコストが高い。typewriter で「動いてる感」を出すのは UI 設計テクニックの 1 つ
- **anchor jump**: 単純な `<a href="#id">` で行ける、SPA navigation 不要
- **`★ cited` の連動**: AnswerPanel の citedIds と ResultCard.cited prop が同じ source、UI の整合性を確保

### Day 19 連携

Day 19 で Docker 構成を backend / frontend に分割、`docker compose up` で localhost:3000 と :8000 が同時起動するように。
