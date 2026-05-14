#!/usr/bin/env bash
# dispatch v2 - simplified, no escape issues, log everything
# usage: bash dispatch_v2.sh 029 bm25-hybrid
set -uo pipefail   # NOT -e (let claude failures be captured in log)

NUM="${1:?spec番号}"
SLUG="${2:-}"
BRANCH="feat/spec_${NUM}${SLUG:+-${SLUG}}"

PROJECT_DIR="/home/nakashima/projects/axis-knowledge-rag"
SPEC="_ai_workspace/bridge/inbox/spec_${NUM}.md"
RESULT="_ai_workspace/bridge/outbox/result_${NUM}.md"
LOG="${PROJECT_DIR}/_ai_workspace/logs/dispatch_${NUM}_v2.log"
CLAUDE_BIN="/home/nakashima/.npm-global/bin/claude"

cd "$PROJECT_DIR" || exit 1
mkdir -p _ai_workspace/logs

{
  echo "[$(date -Is)] dispatch v2 start"
  echo "  spec = $SPEC"
  echo "  result = $RESULT"
  echo "  branch = $BRANCH (already checked out by parent)"
  echo "  claude = $CLAUDE_BIN"
  $CLAUDE_BIN --version
  echo "  current branch = $(git branch --show-current)"
} > "$LOG" 2>&1

export CLAUDE_CONFIG_DIR="/home/nakashima/.claude-project-b"

PROMPT="${SPEC} を読んで実行して。重要: 現在のブランチは ${BRANCH} です。commit + push する時は \`git push -u origin ${BRANCH}\` でこのフィーチャーブランチに push してください。main に直接 push しないでください。完了後は同階層 ${RESULT} に _ai_workspace/bridge/templates/result_template.md の構造で結果を書いて。GitHub アカウントは kazikimaguro13 (PAT 認証済み)。"

echo "[$(date -Is)] launching claude..." >> "$LOG"
$CLAUDE_BIN --dangerously-skip-permissions -p "$PROMPT" >> "$LOG" 2>&1 < /dev/null
echo "[$(date -Is)] claude exited with code $?" >> "$LOG"
