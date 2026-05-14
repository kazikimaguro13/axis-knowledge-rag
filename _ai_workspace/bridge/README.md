# bridge — Cowork × Claude Code 連携運用

このフォルダは **Cowork (戦略・レビュー) と Claude Code (実装・重作業) のあいだの仕様書・結果のやりとり場所** です。

## レイアウト

```
bridge/
├── README.md          ← この文書
├── dispatch.sh        ← Claude Code に spec を投げる helper (任意)
├── templates/
│   ├── spec_template.md
│   └── result_template.md
├── inbox/             ← Cowork が書く spec_NNN.md（Claude Code が読む）
│   └── INDEX.md       ← 進捗一覧
├── outbox/            ← Claude Code が書く result_NNN.md（Cowork が読む）
└── archive/           ← 完了したペアを移動
```

## 命名規則

- `spec_001.md`, `spec_002.md`, … 連番3桁
- 結果は同じ番号: `result_001.md`
- アーカイブ後は `archive/2026-04-29/spec_001.md` のように日付フォルダにまとめる

## 運用ルーチン

### 1. 仕様作成（Cowork → inbox）

Cowork はユーザーから依頼を受けたら、`templates/spec_template.md` を雛形に **触ってよいファイル・成功条件・出力先** を明示した spec を `inbox/spec_NNN.md` として書き出す。書いたら `inbox/INDEX.md` に1行追記する。

### 2. ディスパッチ（人手 or 自動）

**手動 (terminal)**:
```bash
bash _ai_workspace/bridge/dispatch.sh 001
```

**Cowork 内から自動**:
```bash
& 'C:\Program Files\Git\bin\bash.exe' -lc "
cd '<project>' \
  && export CLAUDE_CONFIG_DIR=~/.claude-project-a \
  && claude --dangerously-skip-permissions -p \
    'bridge/inbox/spec_001.md を読んで実行して。完了後は outbox/result_001.md に結果を書いて。' \
  < /dev/null 2>&1
"
```

### 3. 実行（Claude Code）

Claude Code は spec を読み、コードを編集・テスト実行し、結果を `outbox/result_NNN.md` に書く。

### 4. レビュー（Cowork）

Cowork が `outbox/result_NNN.md` を読んで内容確認。OK なら `archive/` へ移動を提案。NG なら spec_NNN+1.md で次の指示を出す。

### 5. アーカイブ

完了ペアは `archive/YYYY-MM-DD/` 配下に移動する：

```
archive/
└── 2026-04-29/
    ├── spec_001.md
    └── result_001.md
```

## 判断基準: いつ Cowork 直接、いつ Claude Code に dispatch？

**Cowork で直接やる**:
- 1〜2 ファイル、〜30 行の小さい修正
- 動作確認、デバッグ、ログ調査
- ユーザーとの対話的な議論・設計検討
- spec 起草、result レビュー
- フロントエンド (Next.js / React 等) のローカル開発
- 設定値の確認、ドキュメント整備

**Claude Code に dispatch**:
- 5+ ファイル、100+ 行の大きな変更
- git push、clasp push、deploy 系
- 既存バックエンドへの機能追加
- スキーマ変更を伴う改修
- 環境構築 (npm install + 初期設定 + 起動確認)

迷ったら **Cowork で直接**。dispatch のオーバーヘッドの方が大きくなりがち。

## 守るべき原則

1. **Spec は具体的に**: 触ってよい/ダメなファイルを必ず書く
2. **Claude Code は spec の範囲を超えない**: 迷ったら止めて Open questions に書く
3. **結果は再現可能に**: result には diff、テスト出力、判断ポイントを必ず含める
4. **小さく区切る**: 1 spec = 30 分以内で完了する単位に分割
5. **秘密情報を spec/result に書かない**: API キー、パスワード等

## INDEX.md（進行管理）

`inbox/INDEX.md` に進行状況を一覧する。新しい spec を書くたびに行を追加。
