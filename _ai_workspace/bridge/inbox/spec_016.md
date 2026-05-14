# spec_016: Day 16 — Next.js プロジェクト初期化 + Tailwind

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜015 (FastAPI 完成前提), `docs/spec-v2.md` Day 16 行

## 1. 目的

```
[現状]
- バックエンドは FastAPI で動作 (Day 15)
- フロントエンドは Streamlit のみ
- リポジトリに frontend/ 配下なし

[変更後]
- `frontend/` 配下に Next.js 14 (App Router) + TypeScript プロジェクトを初期化
- Tailwind CSS 設定済み
- ESLint 設定済み
- ルーティング: `/` (検索画面) と `/settings` (軸フィルタ管理) の 2 ページが空テンプレで表示される
- `lib/api.ts` で FastAPI の型を反映した fetcher を実装
- `npm run dev` で `localhost:3000` で起動
- `npm run build` で production build が通る
```

実コンポーネント実装は Day 17、本日は **「プロジェクト土台 + API クライアントが用意できた」** が完了条件。

## 2. 制約

### 触ってよいファイル

- `frontend/` 配下 (新規作成)
- `package.json` (frontend 用、リポジトリルートには置かない)
- `tsconfig.json`, `next.config.js`, `tailwind.config.ts`, `postcss.config.js`, `eslint.config.mjs`
- `.gitignore` — `node_modules/` `.next/` `frontend/.env*` 追記 (既存にあるなら確認のみ)
- `docs/architecture.md` — Frontend セクション追加
- `CHANGELOG.md`

### 触ってはいけないもの

- `backend/` 以下
- `streamlit_app.py` (Week 3 末まで保持)
- `_ai_workspace/`、`docs/spec-v2.md`

### コーディングルール

- Next.js 14 App Router (pages router 不使用)
- TypeScript strict mode
- Tailwind CSS 3.x
- パッケージマネージャは `npm` (yarn / pnpm は導入しない)
- 依存は最小限: react, next, tailwindcss, typescript, @types/node, @types/react, eslint, eslint-config-next
- 状態管理ライブラリ (Zustand, Redux 等) は **入れない** — `useState` / `Context` で十分
- API クライアントは `fetch` 直叩き、axios 不要

## 3. やってほしいこと

### 3-1. Next.js init

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"
npx create-next-app@14 frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src-dir \
  --import-alias "@/*" \
  --use-npm \
  --no-turbopack
```

create-next-app の対話を回避するためにフラグ全部指定。実行後 `frontend/` ディレクトリができている。

### 3-2. ディレクトリ構成 (Day 16 時点)

```
frontend/
├── src/
│   ├── app/
│   │   ├── page.tsx               # 検索画面 (空テンプレ)
│   │   ├── settings/
│   │   │   └── page.tsx           # 設定画面 (空テンプレ)
│   │   ├── layout.tsx             # 共通レイアウト + ナビ
│   │   └── globals.css
│   ├── components/
│   │   └── .gitkeep               # Day 17 で SearchBar/AxisFilter/ResultCard
│   └── lib/
│       └── api.ts                 # FastAPI fetcher
├── public/
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
├── package.json
└── eslint.config.mjs
```

### 3-3. `frontend/src/app/layout.tsx`

```tsx
import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "axis-knowledge-rag",
  description: "軸検索 + RAG over YAML frontmatter Markdown",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="min-h-screen bg-slate-50 text-slate-900">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="text-lg font-semibold">
              🔍 axis-knowledge-rag
            </Link>
            <nav className="flex gap-4 text-sm">
              <Link href="/" className="hover:underline">
                検索
              </Link>
              <Link href="/settings" className="hover:underline">
                設定
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
```

### 3-4. `frontend/src/app/page.tsx` (検索画面、空テンプレ)

```tsx
"use client";

export default function HomePage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">検索</h1>
      <p className="text-slate-500">
        Day 17 でここに SearchBar / AxisFilter / ResultCard を実装します。
      </p>
    </div>
  );
}
```

### 3-5. `frontend/src/app/settings/page.tsx`

```tsx
export default function SettingsPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">設定</h1>
      <p className="text-slate-500">
        将来的に軸定義 (config.yml) の編集 UI を提供します。
      </p>
    </div>
  );
}
```

### 3-6. `frontend/src/lib/api.ts`

```tsx
// API client for the FastAPI backend. Types mirror backend/src/schemas.py.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface AxisDef {
  name: string;
  type: string;
  values?: string[];
  required?: boolean;
}

export interface AxesResponse {
  axes: AxisDef[];
}

export interface SearchResultPayload {
  id: string;
  title: string;
  score: number;
  axes: Record<string, string | number>;
  body_snippet: string;
  path: string;
  refs: string[];
}

export interface SearchResponse {
  results: SearchResultPayload[];
}

export interface AnswerResponse {
  text: string;
  cited_ids: string[];
  sources: SearchResultPayload[];
  is_dummy: boolean;
  model: string | null;
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => jsonFetch<{ status: string; embedder_mode: string; rag_mode: string }>("/api/health"),
  axes: () => jsonFetch<AxesResponse>("/api/axes"),
  search: (body: {
    query?: string | null;
    filters?: Record<string, string | number>;
    top_k?: number;
  }) =>
    jsonFetch<SearchResponse>("/api/search", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  answer: (body: {
    question: string;
    filters?: Record<string, string | number>;
    top_k?: number;
    max_tokens?: number;
  }) =>
    jsonFetch<AnswerResponse>("/api/answer", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
```

### 3-7. `.env.local.example` (frontend 用)

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

### 3-8. `.gitignore` 確認 / 更新

リポジトリルートに以下があるか確認、無ければ追記:

```
# Next.js
frontend/node_modules
frontend/.next
frontend/out
frontend/.env.local
frontend/.env*.local
```

### 3-9. 動作確認

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag/frontend"
npm install
npm run dev &
sleep 5

# トップページが表示される
curl -I http://localhost:3000

# 設定ページが表示される
curl -I http://localhost:3000/settings

# build が通る
npm run build
npm run lint

kill %1
```

別ターミナルで `uvicorn backend.src.api:app --reload --port 8000` を立ち上げてから:

```bash
# 開発中のブラウザコンソールで:
# > await fetch("http://localhost:8000/api/health").then(r => r.json())
```

CORS が通り、`/api/health` のレスポンスが取れることをユーザーが確認する手順を result に書く。

### 3-10. コミット

1. `feat: bootstrap Next.js 14 app with Tailwind in frontend/`
2. `feat: add root layout with navigation`
3. `feat: add placeholder pages for / and /settings`
4. `feat: add lib/api.ts typed FastAPI client`
5. `chore: gitignore Next.js build artifacts`
6. `docs: add frontend section to architecture.md`
7. `docs: changelog Day 16`

`git push origin main` (dev-b)

### 3-11. result_016.md

特に:

- `npm install` の所要時間 (node_modules はサイズ大きい、後で `.dockerignore` 対象)
- `npm run dev` / `npm run build` / `npm run lint` の出力
- `curl http://localhost:3000` の HTTP status
- FastAPI と CORS が通るかの確認手順 (ユーザー手元で実施推奨)

## 4. 成功条件

- [ ] `frontend/` 配下に Next.js プロジェクトが存在
- [ ] `npm run dev` で `localhost:3000` が表示
- [ ] `/` と `/settings` が表示される
- [ ] `npm run build` が成功
- [ ] `lib/api.ts` で FastAPI の型を反映済み
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_016.md`

## 6. 質問

- **Node.js のバージョン**: Next.js 14 は Node 18+ を要求。中島さんの環境を確認したい (ない場合は手元 install 案内)
- **create-next-app の対話で出るオプション**: 上記フラグで全部押さえているが、もし対話モードに落ちたら spec のフラグ通りに回答する
- **shadcn/ui を入れるか**: Week 3 で UI を綺麗にしたい場合は導入候補だが、Day 16 ではミニマムにしておく。Day 17 で必要なら追加判断
- **`turbopack`**: `--no-turbopack` を指定 (安定優先)、`--turbopack` で高速化する選択肢もあり

## 7. 補足

### 設計の意図

- **状態管理ライブラリ不採用**: 採用担当者に「シンプルに保てる判断ができる」とアピール、useState / Context で十分
- **API client を `fetch` 直叩き**: axios の機能 (interceptor 等) は今のフェーズでは要らない、薄いラッパーで十分
- **`NEXT_PUBLIC_API_BASE` env**: 本番デプロイ時に URL を切り替えやすく
- **Streamlit 残存**: v0.3.0 リリース後の retreat 用、また採用担当者が「2 種類の UI が試せる」と気づくのも面白い

### Day 17 連携

`SearchBar.tsx`、`AxisFilter.tsx`、`ResultCard.tsx` を `src/components/` に実装、`/` ページから使う。`api.search()` を呼んで結果表示まで。
