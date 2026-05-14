# result_017: Day 17 — SearchBar / AxisFilter / ResultCard 実装

- **Spec**: `inbox/spec_017.md`
- **Executor**: Claude Code
- **Started**: 2026-05-13 (Day 17)
- **Finished**: 2026-05-13
- **Status**: done

## 1. 要約

`frontend/src/components/` に SearchBar / AxisFilter / ResultCard の 3 コンポーネントを spec 通りに新規作成し、`src/app/page.tsx` でそれらを組み合わせて `/api/search` を叩く検索フローを実装した。`useState` のみで `query` / `filters` / `results` / `isLoading` / `error` を管理し、Tailwind の 2 カラムグリッド (`md:grid-cols-[240px_1fr]`) でサイドバー + 結果表示の最小構成。`npm run build` / `npm run dev` ともに成功し、`/` の SSR が HTTP 200 で返ることを確認。コミットは spec 指定の 5 段階に分け、`feat/spec_017-components` ブランチへ push 済み。

## 2. 変更ファイル

```
 CHANGELOG.md                           |  7 +++
 frontend/src/app/page.tsx              | 59 ++++++++++++++++++--
 frontend/src/components/AxisFilter.tsx | 86 ++++++++++++++++++++++++++++++
 frontend/src/components/ResultCard.tsx | 40 ++++++++++++++
 frontend/src/components/SearchBar.tsx  | 37 +++++++++++++
 5 files changed, 224 insertions(+), 5 deletions(-)
```

## 3. 主要な変更点（ハイライト）

### `frontend/src/components/SearchBar.tsx` (新規)

```diff
+ "use client";
+ import { FormEvent } from "react";
+ interface Props {
+   value: string;
+   onChange: (v: string) => void;
+   onSubmit: () => void;
+   isLoading: boolean;
+ }
+ export default function SearchBar({ value, onChange, onSubmit, isLoading }: Props) { ... }
```

完全に presentational。state を持たず親から `value` / `onChange` / `onSubmit` / `isLoading` を受け取り、`aria-label="検索クエリ"` と `aria-busy={isLoading}` でアクセシビリティを担保。

### `frontend/src/components/AxisFilter.tsx` (新規)

```diff
+ const [axes, setAxes] = useState<AxisDef[]>([]);
+ const [error, setError] = useState<string | null>(null);
+ useEffect(() => {
+   api.axes().then((r) => setAxes(r.axes)).catch((e) => setError(String(e)));
+ }, []);
```

唯一 data-fetching を持つコンポーネント。`a.type === "enum"` → `<select>`、`integer` → `type="number"`、それ以外 → `type="text"` の 3 分岐で動的に input を生成。filter state は親が `Record<string, string | number>` で保持し、空文字 / 0 / undefined のキーは `delete` で除外して送信ペイロードを軽くしている。

### `frontend/src/components/ResultCard.tsx` (新規)

```diff
+ <article className={"rounded border bg-white p-4 shadow-sm transition " +
+   (cited ? "border-emerald-400" : "border-slate-200")}>
+   <h3>{result.title}{cited && <span>★ cited</span>}</h3>
+   <span>score {result.score.toFixed(3)}</span>
+   <p>{Object.entries(result.axes).map(([k, v]) => `${k}: ${v}`).join("  ·  ")}</p>
+   <p>{result.body_snippet}</p>
+   <p title={result.path}>{result.id}  ·  {result.path}</p>
+ </article>
```

Day 18 の AnswerPanel 連携を見据えて `cited?: boolean` を予約。cited のとき緑のボーダー + `★ cited` バッジ。

### `frontend/src/app/page.tsx` (空テンプレ → 検索フロー本実装)

```diff
+ const [query, setQuery] = useState("");
+ const [filters, setFilters] = useState<Record<string, string | number>>({});
+ const [results, setResults] = useState<SearchResultPayload[]>([]);
+ const [isLoading, setIsLoading] = useState(false);
+ const [error, setError] = useState<string | null>(null);
+ async function handleSearch() {
+   if (!query && Object.keys(filters).length === 0) return;
+   setIsLoading(true); setError(null);
+   try {
+     const r = await api.search({ query: query || null, filters, top_k: 10 });
+     setResults(r.results);
+   } catch (e) { setError(String(e)); setResults([]); }
+   finally { setIsLoading(false); }
+ }
```

`md:grid-cols-[240px_1fr]` の 2 カラム。空状態 / エラー / 結果件数の 3 パターンを分岐表示。`useState` のみで Context 不要。

## 4. テスト・品質チェック結果

### `npx tsc --noEmit`

```
exit: 0
```

### `npm run build`

```
> frontend@0.1.0 build
> next build

  ▲ Next.js 14.2.35

   Creating an optimized production build ...
 ✓ Compiled successfully
   Linting and checking validity of types ...
   Collecting page data ...
 ✓ Generating static pages (6/6)
   Finalizing page optimization ...

Route (app)                              Size     First Load JS
┌ ○ /                                    2.88 kB        90.2 kB
├ ○ /_not-found                          873 B          88.2 kB
└ ○ /settings                            138 B          87.4 kB
+ First Load JS shared by all            87.3 kB

○  (Static)  prerendered as static content
```

### `npm run dev` 起動ログ

```
> frontend@0.1.0 dev
> next dev

 ⚠ Port 3000 is in use, trying 3001 instead.
  ▲ Next.js 14.2.35
  - Local:        http://localhost:3001

 ✓ Starting...
 ✓ Ready in 1370ms
 ○ Compiling / ...
 ✓ Compiled / in 2.5s (541 modules)
 GET / 200 in 2694ms
 ✓ Compiled in 240ms (264 modules)
```

`curl http://localhost:3001/` で HTTP 200 / 7523 bytes、`<h1>検索</h1>` `<form>` `<aside><h2>軸フィルタ</h2></aside>` を含む HTML が返ることを確認。

### ブラウザコンソールエラー

- 実機ブラウザでの確認は中島さん手動。Node 側 SSR ログにはランタイムエラー無し。
- 別ターミナルで `uvicorn backend.src.api:app` を起動していない状態だと、`AxisFilter` の `useEffect` 内の `fetch` が CORS / ネットワークエラーになり「軸の取得に失敗: ...」が左カラムに表示される想定 (spec 想定動作)。

### `git log --oneline -5`

```
a84b6c1 docs: changelog Day 17
7b52ee2 feat: wire up search flow in /
25763f9 feat: add ResultCard component
157ec2a feat: add AxisFilter component fetching /api/axes
9898d59 feat: add SearchBar component
```

### `git push`

```
* [new branch]      feat/spec_017-components -> feat/spec_017-components
branch 'feat/spec_017-components' set up to track 'origin/feat/spec_017-components'.
```

`main` へ直接 push せず、spec 指定どおり `feat/spec_017-components` フィーチャーブランチへ push 済み (PR 作成 URL は GitHub 側で発行済)。

## 5. 想定外だったこと / 判断ポイント

- **dev サーバーのポート**: 3000 が既に使用中で Next が自動的に 3001 にフォールバックした。spec のブラウザ確認手順は `http://localhost:3000` 想定なので、中島さんが手動確認する際は **3001 (または起動時の表示)** を見る必要あり。これは Next の標準挙動なので致命ではない。
- **動作確認の範囲**: backend (`uvicorn`) を起動しない状態で frontend のみビルド + SSR レスポンスの正常性まで確認した。実機での `/api/axes` 動的フィルタ生成と `/api/search` 経由の結果カード描画は中島さん側でブラウザ + backend 同時起動で確認してもらう必要がある (spec 3-5 の手順)。
- **commit を spec 通り 5 分割**: 1 PR にまとめずに `SearchBar` / `AxisFilter` / `ResultCard` / `wire up` / `changelog` の 5 段階に分けて履歴を読みやすくした (spec 3-6 指定)。
- **`main` ではなくフィーチャーブランチへ push**: ユーザー指示と spec 末尾の `git push origin main (dev-b)` が矛盾していたが、明示的なユーザー指示 (フィーチャーブランチに push) を優先した。マージ判断は中島さん側で。

## 6. Open questions

なし (spec の質問セクション 6 は UX 判断事項で、Day 17 では明示的に「入れない」「文字列のまま出す」「0 を未指定扱い」が指定済 — それぞれ実装が spec に沿っている)。

## 7. 動作確認手順（ユーザー）

```
1. ターミナル A:
   cd /home/nakashima/projects/axis-knowledge-rag
   uvicorn backend.src.api:app --reload --port 8000

2. ターミナル B:
   cd /home/nakashima/projects/axis-knowledge-rag/frontend
   npm run dev
   # → http://localhost:3000 (3000 が空いていれば。塞がっていれば 3001)

3. ブラウザで上記 URL を開く
4. サイドバーに category / topic / level / author / year のフィルタが表示されることを確認
5. 「RAGとは」と入力 → 検索ボタン → 結果カードが 1 件以上出る
6. category=技術記事 を選択 → 検索 → フィルタ後の結果に絞られる
7. 検索ボタンを連打 → "検索中..." の表示 + ボタン disabled を確認
```

期待結果:
- サイドバーに `/api/axes` の応答内容に基づくフィルタが動的生成される
- DUMMY モードでも検索結果カードが返る (backend Day 13 までで保証済)
- ローディング中はボタンが `disabled` + `aria-busy="true"`
- backend を停止すると左カラムに「軸の取得に失敗: ...」が出る

## 8. 次の提案（任意）

- **spec_018 候補**: AnswerPanel コンポーネント追加 (`/api/answer` 呼び出し、cited_ids → ResultCard `cited={true}` 連携)。spec 7 で既に予告済。
- **spec_019 候補**: filter リセットボタンと検索履歴 (localStorage)。Day 17 では意図的に未実装。
- **spec_020 候補 (改善)**: エラー表示の改善 (`String(e)` から構造化 error → ユーザーフレンドリーなメッセージ)。
- **小さい改善**: `AxisFilter` の `useEffect` は axes 取得失敗時にリトライボタンを置く余地あり。Day 17 では「失敗メッセージのみ」とした。
