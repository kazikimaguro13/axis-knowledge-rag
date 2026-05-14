# result_018: Day 18 — AnswerPanel + ストリーミング風 UI + 出典リンク

- **Spec**: `inbox/spec_018.md`
- **Executor**: Claude Code (Opus 4.7, 1M context)
- **Started**: 2026-05-13 (午後)
- **Finished**: 2026-05-13 (午後)
- **Status**: done

## 1. 要約

`/api/answer` を `/` ページに統合する UI を追加。`AnswerPanel.tsx` (typewriter pseudo-streaming + `[doc_NNN]` 出典のアンカーリンク化 + DUMMY mode / model badge) と `SkeletonLoader.tsx` を新規作成。`ResultCard.tsx` に `id={result.id}` と `scroll-mt-4` を付与し、回答中のリンクから該当カードへスムーズにジャンプできるようにした。`page.tsx` に「RAG 回答も生成する」チェックボックスを追加し、トグルで `/api/answer` ↔ `/api/search` を切替。`answer.cited_ids` を `ResultCard.cited` prop に連動させて ★ cited バッジが点く。`npx tsc --noEmit` と `next build` ともに成功。

## 2. 変更ファイル

```
 CHANGELOG.md                               |   6 ++
 frontend/src/app/page.tsx                  |  44 +++++++++--
 frontend/src/components/AnswerPanel.tsx    | 114 +++++++++++++++++++++++++++++
 frontend/src/components/ResultCard.tsx     |   3 +-
 frontend/src/components/SkeletonLoader.tsx |  12 +++
 5 files changed, 172 insertions(+), 7 deletions(-)
```

## 3. 主要な変更点（ハイライト）

### `frontend/src/components/SkeletonLoader.tsx`

```tsx
+ export default function SkeletonLoader() {
+   return (
+     <div className="animate-pulse space-y-2 rounded border border-slate-200 bg-white p-4">
+       <div className="h-3 w-1/4 rounded bg-slate-200" />
+       <div className="h-3 w-full rounded bg-slate-200" />
+       <div className="h-3 w-5/6 rounded bg-slate-200" />
+       <div className="h-3 w-3/4 rounded bg-slate-200" />
+     </div>
+   );
+ }
```

Tailwind `animate-pulse` ベースの汎用スケルトン。Day 18 の `AnswerPanel` 内では同等のインライン skeleton を直接書いているが、将来 ResultCard ロード中の placeholder などに再利用可能な独立コンポーネントとして用意。

### `frontend/src/components/AnswerPanel.tsx`

```tsx
+ const CITATION_RE = /\[(doc_\d+)\]/g;
+
+ function renderWithCitations(text: string): React.ReactNode[] {
+   // [doc_NNN] を <a href="#doc_NNN"> に置換しつつ前後テキストを保持
+   ...
+ }
+
+ // pseudo-streaming: setInterval 25ms × (length / 80) chars/tick
+ useEffect(() => {
+   if (!text) { setDisplayed(""); return; }
+   setDisplayed("");
+   let i = 0;
+   const step = Math.max(1, Math.floor(text.length / 80));
+   const id = setInterval(() => {
+     i += step;
+     if (i >= text.length) { setDisplayed(text); clearInterval(id); }
+     else { setDisplayed(text.slice(0, i)); }
+   }, 25);
+   return () => clearInterval(id);
+ }, [text]);
```

- `CITATION_RE.lastIndex = 0` を毎回明示リセット (グローバル正規表現の state リーク対策)。
- `step = max(1, length / 80)` は短文・長文どちらでも 80 ticks 程度で完走する正規化 — 100 文字でも 2000 文字でも体感 2 秒で読了。
- 4 つの state (loading / error / empty / answered) を early return で分岐。answered 状態のみ `aria-live="polite"` + emerald 系の枠線/背景 + 右上に `DUMMY mode` または `model: <name>  ·  cited: doc_001, ...` を表示。

### `frontend/src/components/ResultCard.tsx`

```diff
- <article
-   className={
-     "rounded border bg-white p-4 shadow-sm transition " +
-     (cited ? "border-emerald-400" : "border-slate-200")
-   }
- >
+ <article
+   id={result.id}
+   className={
+     "scroll-mt-4 rounded border bg-white p-4 shadow-sm transition " +
+     (cited ? "border-emerald-400" : "border-slate-200")
+   }
+ >
```

`AnswerPanel` の `<a href="#doc_NNN">` がここに飛んでくる。`scroll-mt-4` で将来固定ヘッダーが入っても上端が隠れないように余白を確保。

### `frontend/src/app/page.tsx`

```diff
+ const [answer, setAnswer] = useState<AnswerResponse | null>(null);
+ const [withRag, setWithRag] = useState(true);
...
+ if (withRag && query) {
+   const ans = await api.answer({ question: query, filters, top_k: 5 });
+   setAnswer(ans);
+   setResults(ans.sources);
+ } else {
+   const r = await api.search({ query: query || null, filters, top_k: 10 });
+   setResults(r.results);
+ }
...
+ <AnswerPanel
+   text={answer?.text ?? ""}
+   citedIds={answer?.cited_ids ?? []}
+   isLoading={isLoading && withRag && !!query}
+   ...
+ />
...
+ <ResultCard
+   key={r.id}
+   result={r}
+   cited={answer?.cited_ids?.includes(r.id) ?? false}
+ />
```

- `isLoading && withRag && !!query` で「RAG モードで質問あり」のときだけ AnswerPanel の loading skeleton を出す。検索のみモードでは AnswerPanel は null。
- spec 通り `setAnswer(null)` を search 開始時に呼んで前回の回答を即座に消す (typewriter effect の依存配列 `[text]` がリセットされて UX 上ちらつかない)。

## 4. テスト・品質チェック結果

```
$ cd frontend && npx tsc --noEmit
(no errors)

$ npm run build
 ✓ Compiled successfully
 ✓ Generating static pages (6/6)
Route (app)                              Size     First Load JS
┌ ○ /                                    3.76 kB        91.1 kB
└ ○ /settings                            138 B          87.4 kB

$ git log --oneline -5
80af763 docs: changelog Day 18
2c221f4 feat: integrate AnswerPanel into / with RAG toggle
2eef7f0 feat: add #anchor to ResultCard for jump-to-source
2608ed5 feat: add AnswerPanel with typewriter effect and citation links
8017f61 feat: add SkeletonLoader component

$ git push -u origin feat/spec_018-answer-panel
 * [new branch]      feat/spec_018-answer-panel -> feat/spec_018-answer-panel
```

## 5. 想定外だったこと / 判断ポイント

- **ブランチ**: 指示通り `feat/spec_018-answer-panel` で作業し push。`main` 直 push はしていない。マージは Cowork 側で PR/merge してください。
- **typewriter 速度**: spec の質問 (3-7) に対応して `setInterval` を `requestAnimationFrame` 化はしなかった。25ms × 80 ticks ≒ 2 秒で完走、現状の典型回答長 (200〜800 chars) では `setInterval` でも体感問題なし。2000+ chars の超長文回答が日常化したら rAF + 経過時間ベースに切替推奨。
- **`CITATION_RE.lastIndex = 0` の明示リセット**: グローバルフラグ付き正規表現は state を保持するため、`renderWithCitations` が複数回呼ばれるとずれる可能性がある。spec のコードそのままだとリスクが残るので、関数先頭で明示リセットを追加 (1 行のみの差分)。
- **citation 抽出の二重ソース**: spec 質問 (3-7) で挙がっていた「frontend regex vs backend `cited_ids`」については、UI 側のリンク描画用に regex を残しつつ、★ cited バッジ判定 (`ResultCard.cited`) は `answer.cited_ids` を単一情報源として使う、という棲み分けにした。`cited_ids` の表示文字列も右上の badge に出すことで「backend が認識した cited」が見える。
- **`page.tsx` の `isLoading` 渡し方**: spec では `isLoading && withRag` だったが、`query` が空でも RAG トグルが ON だと skeleton が出てしまうので `isLoading && withRag && !!query` に絞った (search のみ呼ばれるパスでは AnswerPanel の loading を出さない)。
- **`SkeletonLoader.tsx` の利用箇所**: spec 3-1 で作るよう指定があったが `AnswerPanel` の中では同等のインライン skeleton を直接埋め込んだ (高さ/数を AnswerPanel 専用にチューニングしたかったため)。`SkeletonLoader` 自体は将来の汎用利用のために単体コンポーネントとして残してある。

## 6. Open questions

なし。

## 7. 動作確認手順（ユーザー）

```
# Terminal 1: backend (ANTHROPIC_API_KEY 未設定 → DUMMY mode)
cd ~/projects/axis-knowledge-rag
uvicorn backend.src.api:app --reload --port 8000

# Terminal 2: frontend
cd ~/projects/axis-knowledge-rag/frontend
npm run dev
# → http://localhost:3000
```

1. デフォルトで「RAG 回答も生成する」がチェック ON になっていることを確認。
2. 検索バーに「RAG アーキテクチャ」など入力 → Enter or 検索ボタン。
3. AnswerPanel に skeleton が一瞬出る → typewriter 風に文字が増えていく。右上に `DUMMY mode  ·  cited: doc_001, doc_002` のような badge。
4. 回答中の `[doc_001]` (緑バッジ) をクリック → 下の該当 ResultCard までスクロール。
5. cited な ResultCard には緑枠 + `★ cited` バッジが点いている。
6. 「RAG 回答も生成する」のチェックを外して同じ質問を送る → AnswerPanel が消え、`/api/search` 経由で高速に結果のみ返る。
7. backend を停止して検索 → 赤い `⚠ 回答生成エラー: ...` (role=alert) が表示される。

期待結果:

- typewriter で回答が滑らかに表示される (約 2 秒で完走)
- `[doc_NNN]` リンクが anchor jump として機能
- cited / non-cited で ResultCard の枠色 + バッジが切り替わる
- DUMMY モードでもエラーなく回答が出る
- `/api/answer` ↔ `/api/search` がトグルで切替可能
- `npx tsc --noEmit` と `npm run build` がエラーなし

## 8. 次の提案（任意）

- **spec_019 / Day 19**: spec_018 の補足にもある通り、Docker Compose で backend (`:8000`) + frontend (`:3000`) を `docker compose up` 一発で立ち上がるように。frontend は multi-stage build (`node:20-alpine` ベース) で slim 化。
- **spec 候補**: typewriter を `requestAnimationFrame` ベースに置き換え、`prefers-reduced-motion` で typewriter を無効化 → アクセシビリティ強化 (回答が即座に全文表示)。
- **spec 候補**: モバイル対応 — `md:grid-cols-[240px_1fr]` の左側 (AxisFilter) を `< md` ではドロワー化、`SearchBar` を sticky top に。Day 20 のスクショ撮影前に。
- **spec 候補**: AnswerPanel に「コピー」「再生成」ボタン (clipboard / 再 POST) を追加して UX 強化。
