#!/usr/bin/env bash
# dispatch v3 - explicit tool-use prompt, max-turns 100
set -uo pipefail
NUM="${1:?spec番号}"
SLUG="${2:-}"
BRANCH="feat/spec_${NUM}${SLUG:+-${SLUG}}"

PROJECT_DIR="/home/nakashima/projects/axis-knowledge-rag"
SPEC="_ai_workspace/bridge/inbox/spec_${NUM}.md"
RESULT="_ai_workspace/bridge/outbox/result_${NUM}.md"
LOG="${PROJECT_DIR}/_ai_workspace/logs/dispatch_${NUM}_v3.log"
CLAUDE_BIN="/home/nakashima/.npm-global/bin/claude"

cd "$PROJECT_DIR" || exit 1
mkdir -p _ai_workspace/logs _ai_workspace/bridge/outbox

export CLAUDE_CONFIG_DIR="/home/nakashima/.claude-project-b"

PROMPT="あなたは Claude Code として ${PROJECT_DIR} で作業します。
以下の手順を **必ず実行** してください (会話で説明するだけではなく、Read/Edit/Write/Bash ツールを使って実際にファイルを変更・コミット・push してください):

1. Read ツールで ${PROJECT_DIR}/${SPEC} を読む
2. spec の指示に従って Read/Edit/Write ツールでファイルを作成・編集 (bm25_index.py 新規作成、search.py 更新、tests 追加、ADR-016 追加、CHANGELOG 更新など)
3. Bash ツールで pip install -e . --break-system-packages を実行 (新規依存 rank-bm25 を有効化)
4. Bash ツールで ruff check . と pytest を実行、すべて緑になるまで修正
5. Bash ツールで git add . && git commit -m '...' && git push -u origin ${BRANCH} を実行
6. Write ツールで ${PROJECT_DIR}/${RESULT} に result_template.md 構造の結果レポートを作成

**重要事項:**
- 現在のブランチは ${BRANCH} です (すでに checkout 済)
- main に直接 push しないこと
- 必ず ${BRANCH} に push すること
- GitHub auth: kazikimaguro13 (PAT は ~/.git-credentials)
- 全 pytest 緑にしてから push

時間がかかってもいいので、最後まで完遂してから停止してください。"

{
  echo "[$(date -Is)] v3 start, branch=$(git branch --show-current)"
  echo "[$(date -Is)] launching claude..."
} > "$LOG"

# Run claude with explicit max-turns and verbose output
$CLAUDE_BIN --dangerously-skip-permissions -p "$PROMPT" \
  >> "$LOG" 2>&1 < /dev/null

echo "[$(date -Is)] claude exited code=$?" >> "$LOG"
