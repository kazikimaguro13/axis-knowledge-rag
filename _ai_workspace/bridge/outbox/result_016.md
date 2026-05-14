# result_016: Day 16 — Next.js プロジェクト初期化 + Tailwind

- **Spec**: `inbox/spec_016.md`
- **Executor**: Claude Code (Opus 4.7 / 1M)
- **Started**: 2026-05-13 14:07
- **Finished**: 2026-05-13 14:25
- **Status**: done

## 1. 要約

- `frontend/` 配下に Next.js 14.2.35 (App Router + TypeScript strict + Tailwind 3.4 + ESLint) を `create-next-app@14` で初期化。
- 共通レイアウト (検索 / 設定リンク付きヘッダー) と `/` `/settings` の placeholder ページ、`src/lib/api.ts` の FastAPI 用 typed fetcher を実装。
- `npm run lint` / `npm run build` / `npm run dev` の 3 種すべて成功、HTTP 200 を確認。
- ルート `.gitignore` の Python 用 `lib/` パターンが `frontend/src/lib` をマスクしていたので negate ルールで救済。
- `feat/spec_016-nextjs-init` に 7 commit、`git push -u origin feat/spec_016-nextjs-init` で remote 反映済み。

## 2. 変更ファイル

```
 .gitignore                              |    5 +
 CHANGELOG.md                            |   12 +
 docs/architecture.md                    |   63 +-
 frontend/.env.local.example             |    1 +
 frontend/.eslintrc.json                 |    3 +
 frontend/.gitignore                     |   36 +
 frontend/README.md                      |   36 +
 frontend/next.config.mjs                |    4 +
 frontend/package-lock.json              | 6026 +
 frontend/package.json                   |   26 +
 frontend/postcss.config.mjs             |    8 +
 frontend/src/app/favicon.ico            |  Bin
 frontend/src/app/fonts/GeistMonoVF.woff |  Bin
 frontend/src/app/fonts/GeistVF.woff     |  Bin
 frontend/src/app/globals.css            |   27 +
 frontend/src/app/layout.tsx             |   37 +
 frontend/src/app/page.tsx               |   12 +
 frontend/src/app/settings/page.tsx      |   10 +
 frontend/src/components/.gitkeep        |    0
 frontend/src/lib/api.ts                 |   77 +
 frontend/tailwind.config.ts             |   19 +
 frontend/tsconfig.json                  |   26 +
 22 files changed, 6426 insertions(+)
```

(`backend/src/api.py` の 2 行差分は spec_016 範囲外で、push 直前の `main` 上の `style(ruff)` 差分が混入したもの — Day 16 コミットには含まれていない。)

## 3. 主要な変更点（ハイライト）

### `frontend/src/app/layout.tsx`

```diff
- import type { Metadata } from "next";
- import localFont from "next/font/local";
+ import type { Metadata } from "next";
+ import Link from "next/link";
  import "./globals.css";
+
+ export const metadata: Metadata = {
+   title: "axis-knowledge-rag",
+   description: "軸検索 + RAG over YAML frontmatter Markdown",
+ };
...
+ <html lang="ja">
+   <body className="min-h-screen bg-slate-50 text-slate-900">
+     <header className="border-b border-slate-200 bg-white">
+       ...nav: 検索 / 設定...
```

Geist フォントの localFont 取り込みは廃し、Tailwind utility のみで slate 系のミニマルなナビバーを構築。`lang="ja"`。

### `frontend/src/lib/api.ts`

```diff
+ const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
+
+ export interface SearchResultPayload { id, title, score, axes, body_snippet, path, refs }
+ export interface AnswerResponse      { text, cited_ids, sources, is_dummy, model }
+
+ export const api = {
+   health: () => jsonFetch<...>("/api/health"),
+   axes:   () => jsonFetch<AxesResponse>("/api/axes"),
+   search: (body) => jsonFetch<SearchResponse>("/api/search", { method: "POST", body }),
+   answer: (body) => jsonFetch<AnswerResponse>("/api/answer", { method: "POST", body }),
+ };
```

`backend/src/schemas.py` (Day 15) の Pydantic モデルをそのまま TS interface にミラー。axios を入れず `fetch` の薄ラッパーで型だけを縛る、Day 17 のコンポーネント実装からはここを叩く。

### `.gitignore` (root)

```diff
+ frontend/.env.local
+ frontend/.env*.local
+ !frontend/.env.local.example
+ # Python の `lib/` ルール (line 13) が frontend/src/lib をマスクするので negate
+ !frontend/src/lib/
```

ルート `.gitignore` の Python distutils 由来 `lib/` パターンが `frontend/src/lib/` を巻き込んでいた → negate で救済 (詳細は §5 参照)。`.env.local.example` も同じく `.env.*` パターンに掛かるので negate。

### `docs/architecture.md`

```diff
+ ## 7. Frontend (Next.js, Day 16〜)
+ ### ディレクトリ / スタック / API 連携図 / 開発フロー
- ## 7. 拡張ポイント (Week 2 以降)
+ ## 8. 拡張ポイント (Week 2 以降)
```

§7 として Frontend を追加、拡張ポイント章を §8 に番号繰り下げ。

## 4. テスト・品質チェック結果

```
$ npm run lint
> next lint
✔ No ESLint warnings or errors

$ npm run build  (18.99s real)
> next build
  ▲ Next.js 14.2.35
   Creating an optimized production build ...
 ✓ Compiled successfully
   Linting and checking validity of types ...
   Collecting page data ...
 ✓ Generating static pages (6/6)
   Finalizing page optimization ...

Route (app)                              Size     First Load JS
┌ ○ /                                    401 B          87.6 kB
├ ○ /_not-found                          873 B          88.1 kB
└ ○ /settings                            138 B          87.4 kB
+ First Load JS shared by all            87.2 kB

$ npm run dev  (Ready in 1329ms)
$ curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3000/
HTTP 200
$ curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3000/settings
HTTP 200
$ curl -sI http://localhost:3000/
HTTP/1.1 200 OK
X-Powered-By: Next.js
Content-Type: text/html; charset=utf-8

$ git --no-pager log --oneline -7
83a88ce docs: changelog Day 16
4b373c0 docs: add frontend section to architecture.md
025a237 feat: add lib/api.ts typed FastAPI client
c4ce0d6 chore: gitignore Next.js build artifacts
d3c3e60 feat: add placeholder pages for / and /settings
1a1f898 feat: add root layout with navigation
b0a2d23 feat: bootstrap Next.js 14 app with Tailwind in frontend/
```

### コマンド所要時間まとめ

| Step                | 時間   | 備考 |
|---|---|---|
| `npx create-next-app@14` | 33.8s | `npm install` 含む。`added 380 packages, audited 381` |
| `npm install` (再実行は不要) | — | bootstrap 時に一括で完了 |
| `npm run build`      | 19.0s | 3 ルート全て static prerender |
| `npm run dev` (起動)  | 1.3s | "Ready in 1329ms" |
| `node_modules` サイズ | 349M  | `.dockerignore` 対象に追加検討 (Day 17 以降) |

## 5. 想定外だったこと / 判断ポイント

- **ルート `.gitignore` の `lib/` ルールが `frontend/src/lib` を巻き込んだ**: 既存の Python distutils 用 ignore (line 13 `lib/`) が再帰的にマッチするため、`!frontend/src/lib/` negate を追加。最初に気付かず lib/api.ts を含めず commit してしまい、`git reset --soft HEAD~1` で巻き戻してから gitignore commit → lib commit の順に並べ替えた。spec の commit 順とは入れ替えになるが、commit 数は 7 のまま。
- **`.env.local.example` も同様に `.env.*` パターンで ignore されていた**: `!frontend/.env.local.example` で救済。
- **生成された設定ファイルが `.mjs`**: spec では `next.config.js` / `eslint.config.mjs` と書かれていたが、`create-next-app@14` の既定では `next.config.mjs` + `.eslintrc.json` (classic ESLint config) になる。動作上問題ないのでそのまま採用。
- **`--no-turbopack` フラグは未指定**: `create-next-app@14` ではデフォルトで Webpack。`--turbopack` / `--no-turbopack` フラグ自体はあるが、未指定でも安定優先 (Webpack) になるため省略。`package.json` の dev script も `next dev` のみ。
- **`npm audit`**: 5 vulnerabilities (1 moderate / 4 high) が表示されたが、これは Next.js 14 系の依存に既知の脆弱性 (主に dev dep)。`audit fix --force` は breaking change を含むため未実施、Week 3 で対応予定。
- **`backend/src/api.py` の 2 行差分**: push 前の `main` 上に Day 15 の ruff fix commit (`d9338a6`) が乗っていたため、`feat/spec_016-nextjs-init` の比較対象 (`bb3d63f`) との diff stat に混入。Day 16 の 7 commits には含まれていない。

## 6. Open questions

なし。

## 7. 動作確認手順（ユーザー）

```
1. cd C:\Users\cocor\Desktop\就活\axis-knowledge-rag
2. git pull origin feat/spec_016-nextjs-init
3. cd frontend
4. npm install                  # 30〜60s、初回のみ
5. npm run dev                  # → "Ready in ~1s"

   別ターミナルで:
6. cd C:\Users\cocor\Desktop\就活\axis-knowledge-rag
7. uvicorn backend.src.api:app --reload --port 8000   # FastAPI 起動
8. ブラウザで http://localhost:3000 を開く
9. ナビの「設定」リンクをクリック → /settings へ遷移
10. ブラウザの DevTools コンソールで:
    > await fetch("http://localhost:8000/api/health").then(r => r.json())
    → {status: "ok", embedder_mode: "...", rag_mode: "..."} が返れば CORS 通過
```

期待結果:

- `/` で「検索 / Day 17 でここに SearchBar / AxisFilter / ResultCard を実装します。」が表示
- `/settings` で「設定 / 将来的に軸定義 (config.yml) の編集 UI を提供します。」が表示
- DevTools の `fetch("http://localhost:8000/api/health")` が 200 + JSON を返す (CORS 通過)
- `npm run build` でも 3 ルートとも static prerender できる

build/lint だけ確認したいときは:

```
cd frontend
npm run lint    # ✔ No ESLint warnings or errors
npm run build   # Route /, /settings, /_not-found
```

## 8. 次の提案（任意）

- **spec_017 候補**: `SearchBar` / `AxisFilter` / `ResultCard` を `src/components/` に実装し、`/` ページから `api.search()` を呼んで結果を表示。`api.answer()` で RAG 回答パネルも。
- **spec_017+ 候補**: `.dockerignore` に `frontend/node_modules` (349 MB) と `frontend/.next` を追加して Docker build を軽くする。
- **spec_017+ 候補**: `npm audit` の高脆弱性 5 件への対応 (Next.js 14 → 14.x 最新パッチ or eslint upgrade)。
- **spec_017+ 候補**: `frontend/` 用の CI ジョブ (`.github/workflows/ci.yml` に `npm ci && npm run lint && npm run build`) を追加。現状の CI は Python のみ。
