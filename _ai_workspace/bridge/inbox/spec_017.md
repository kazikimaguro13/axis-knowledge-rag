# spec_017: Day 17 — SearchBar / AxisFilter / ResultCard 実装

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜016, `docs/spec-v2.md` Day 17 行

## 1. 目的

```
[現状]
- Next.js のページは空テンプレ
- API クライアント (lib/api.ts) は完成

[変更後]
- `SearchBar.tsx`: クエリ入力 + 検索ボタン
- `AxisFilter.tsx`: `/api/axes` を fetch して動的に sidebar フィルタ生成 (enum→select, string→input, integer→number input)
- `ResultCard.tsx`: 1 件の検索結果カード
- `/` ページで上記 3 つを組み合わせ、`/api/search` を叩いて結果表示
- ローディング状態 / エラーハンドリング基本実装
- Tailwind で見栄え整える (Streamlit を超える完成度)
```

Day 18 で AnswerPanel を追加するので、今日は **検索結果一覧まで動く** が完了条件。

## 2. 制約

### 触ってよいファイル

- `frontend/src/components/SearchBar.tsx` — 新規
- `frontend/src/components/AxisFilter.tsx` — 新規
- `frontend/src/components/ResultCard.tsx` — 新規
- `frontend/src/app/page.tsx` — 上記 3 つを組み合わせ
- `frontend/src/app/globals.css` — 必要なら微調整
- `CHANGELOG.md`

### 触ってはいけないもの

- backend 全般
- `frontend/src/app/layout.tsx` (Day 16 で確定)
- `frontend/src/lib/api.ts` (Day 16 で確定)
- `_ai_workspace/`、`docs/spec-v2.md`

### コーディングルール

- "use client" 必要なコンポーネントのみ (page.tsx は use client、layout は server)
- 状態は `useState` のみ、Context 不要
- ローディングは `isLoading` boolean、エラーは `error: string | null`
- アクセシビリティ: input に label、ボタンに `aria-busy`
- アニメーションは Tailwind `transition` クラスで最小限
- API レスポンスのバリデーションは Pydantic 側に任せる (frontend は型を信じる、エラー時は catch)

## 3. やってほしいこと

### 3-1. `frontend/src/components/SearchBar.tsx`

```tsx
"use client";

import { FormEvent } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  isLoading: boolean;
}

export default function SearchBar({ value, onChange, onSubmit, isLoading }: Props) {
  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit();
  }
  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="例: RAG アーキテクチャの設計判断は?"
        aria-label="検索クエリ"
        className="flex-1 rounded border border-slate-300 bg-white px-3 py-2 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
      />
      <button
        type="submit"
        disabled={isLoading}
        aria-busy={isLoading}
        className="rounded bg-blue-600 px-4 py-2 font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
      >
        {isLoading ? "検索中..." : "検索"}
      </button>
    </form>
  );
}
```

### 3-2. `frontend/src/components/AxisFilter.tsx`

```tsx
"use client";

import { useEffect, useState } from "react";
import { api, AxisDef } from "@/lib/api";

interface Props {
  filters: Record<string, string | number>;
  onChange: (filters: Record<string, string | number>) => void;
}

export default function AxisFilter({ filters, onChange }: Props) {
  const [axes, setAxes] = useState<AxisDef[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .axes()
      .then((r) => setAxes(r.axes))
      .catch((e) => setError(String(e)));
  }, []);

  function set(key: string, value: string | number | undefined) {
    const next = { ...filters };
    if (value === undefined || value === "" || value === 0) {
      delete next[key];
    } else {
      next[key] = value;
    }
    onChange(next);
  }

  if (error) {
    return <div className="text-sm text-red-600">軸の取得に失敗: {error}</div>;
  }

  return (
    <aside className="space-y-3">
      <h2 className="text-sm font-semibold text-slate-700">軸フィルタ</h2>
      {axes.map((a) => {
        if (a.type === "enum" && a.values) {
          return (
            <label key={a.name} className="block text-sm">
              <span className="mb-1 block text-slate-600">{a.name}</span>
              <select
                value={(filters[a.name] as string) ?? ""}
                onChange={(e) => set(a.name, e.target.value)}
                className="w-full rounded border border-slate-300 bg-white px-2 py-1"
              >
                <option value="">(指定なし)</option>
                {a.values.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          );
        }
        if (a.type === "integer") {
          return (
            <label key={a.name} className="block text-sm">
              <span className="mb-1 block text-slate-600">{a.name}</span>
              <input
                type="number"
                value={(filters[a.name] as number) ?? ""}
                onChange={(e) => set(a.name, parseInt(e.target.value, 10) || 0)}
                className="w-full rounded border border-slate-300 bg-white px-2 py-1"
              />
            </label>
          );
        }
        return (
          <label key={a.name} className="block text-sm">
            <span className="mb-1 block text-slate-600">{a.name}</span>
            <input
              type="text"
              value={(filters[a.name] as string) ?? ""}
              onChange={(e) => set(a.name, e.target.value)}
              className="w-full rounded border border-slate-300 bg-white px-2 py-1"
            />
          </label>
        );
      })}
    </aside>
  );
}
```

### 3-3. `frontend/src/components/ResultCard.tsx`

```tsx
"use client";

import { SearchResultPayload } from "@/lib/api";

interface Props {
  result: SearchResultPayload;
  cited?: boolean;
}

export default function ResultCard({ result, cited = false }: Props) {
  return (
    <article
      className={
        "rounded border bg-white p-4 shadow-sm transition " +
        (cited ? "border-emerald-400" : "border-slate-200")
      }
    >
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="text-base font-semibold">
          {result.title}
          {cited && (
            <span className="ml-2 rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">
              ★ cited
            </span>
          )}
        </h3>
        <span className="text-xs text-slate-500">score {result.score.toFixed(3)}</span>
      </div>
      <p className="mb-2 text-xs text-slate-500">
        {Object.entries(result.axes)
          .map(([k, v]) => `${k}: ${v}`)
          .join("  ·  ")}
      </p>
      <p className="text-sm text-slate-800">{result.body_snippet}</p>
      <p className="mt-2 truncate text-xs text-slate-400" title={result.path}>
        {result.id}  ·  {result.path}
      </p>
    </article>
  );
}
```

### 3-4. `frontend/src/app/page.tsx`

```tsx
"use client";

import { useState } from "react";
import AxisFilter from "@/components/AxisFilter";
import ResultCard from "@/components/ResultCard";
import SearchBar from "@/components/SearchBar";
import { api, SearchResultPayload } from "@/lib/api";

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Record<string, string | number>>({});
  const [results, setResults] = useState<SearchResultPayload[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    if (!query && Object.keys(filters).length === 0) {
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const r = await api.search({ query: query || null, filters, top_k: 10 });
      setResults(r.results);
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
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={handleSearch}
          isLoading={isLoading}
        />
        {error && <div className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</div>}
        {results.length > 0 && (
          <p className="text-sm text-slate-500">{results.length} 件の結果</p>
        )}
        <div className="space-y-3">
          {results.map((r) => (
            <ResultCard key={r.id} result={r} />
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
# 別ターミナル 1
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"
uvicorn backend.src.api:app --reload --port 8000

# 別ターミナル 2
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag/frontend"
npm run dev
# → http://localhost:3000
```

ブラウザで:

1. サイドバーに category / topic / level / author / year のフィルタが出る
2. "RAGとは" と入力 → 検索 → 結果カードが出る
3. category=技術記事 を選択 → 検索 → フィルタ後の結果

### 3-6. コミット

1. `feat: add SearchBar component`
2. `feat: add AxisFilter component fetching /api/axes`
3. `feat: add ResultCard component`
4. `feat: wire up search flow in /`
5. `docs: changelog Day 17`

`git push origin main` (dev-b)

### 3-7. result_017.md

- `npm run dev` 起動ログ
- 動作確認のブラウザコンソールエラー (あれば)
- スクショは取れない (中島さん手動)

## 4. 成功条件

- [ ] `/` ページで検索フロー動作 (API → 結果カード)
- [ ] AxisFilter が `/api/axes` から動的生成
- [ ] DUMMY モードでもエラーなく結果表示
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_017.md`

## 6. 質問

- **`year` フィルタの初期値**: 0 を「未指定」扱いにしているが、軸定義上は `required: false`。UX 上の判断
- **filter リセットボタン**: 入れるかどうか、Day 17 では入れない方針 (Day 18 で AnswerPanel と一緒に再検討)
- **エラー表示の改善**: Day 17 では文字列をそのまま出す、Day 18 で改善

## 7. 補足

### 設計の意図

- **`SearchBar` / `ResultCard` は presentational**: state を持たない、再利用しやすい
- **`AxisFilter` は data-fetching を持つ**: `/api/axes` を自分で叩く、page.tsx を薄く保つ
- **`page.tsx` を 1 ファイルに**: Day 17 ではここに集約、Day 18 で AnswerPanel が増えたら分割検討

### Day 18 連携

AnswerPanel を追加して `/api/answer` を呼ぶ。cited_ids でカードに `★ cited` バッジを付ける (ResultCard の `cited` prop を渡す)。
