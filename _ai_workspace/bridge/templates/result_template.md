# result_NNN: <spec_NNN と同じタイトル>

- **Spec**: `inbox/spec_NNN.md`
- **Executor**: Claude Code
- **Started**: YYYY-MM-DD HH:MM
- **Finished**: YYYY-MM-DD HH:MM
- **Status**: done | partial | blocked

## 1. 要約

何をしたかを 3〜5 行で要約。

## 2. 変更ファイル

```
 path/to/file1.py | XX +++++++++
 path/to/file2.gs | YY +++
 2 files changed, ZZ insertions(+)
```

## 3. 主要な変更点（ハイライト）

### `path/to/file1.py`

```diff
+ def new_function():
+     pass
```

その変更の意図を 1〜2 行で。

### `path/to/file2.gs`

...

## 4. テスト・品質チェック結果

```
$ npm test  (or 等価のコマンド)
✓ all passed

$ git log --oneline -1
abcdef0 spec_NNN: <タイトル>
```

## 5. 想定外だったこと / 判断ポイント

- spec で曖昧だった部分を <こう判断した>
- <ライブラリ X> が <Y バージョン> でしか動かなかったので調整した
- (該当なしならセクションごと削除)

## 6. Open questions

完全に判断不能だった事項のみ、ここに書く（status: blocked のとき）。

- Q1: <質問>
- Q2: <質問>

(該当なしなら「なし」と書く or セクション削除)

## 7. 動作確認手順（ユーザー）

```
1. <ユーザーがやるべき手順 1>
2. <ユーザーがやるべき手順 2>
3. 確認: <期待される結果>
```

期待結果:
- <成功条件 1>
- <成功条件 2>

## 8. 次の提案（任意）

実装中に気づいた、別 spec として切り出すべき改善案。

- spec_NNN+1 候補: <内容>
