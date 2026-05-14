#!/usr/bin/env bash
# dispatch v4 — pass spec content via env var to avoid shell expansion of markdown
# usage: bash dispatch_v4.sh 030 readme-cleanup
set -uo pipefail

NUM="${1:?spec番号}"
SLUG="${2:-}"
BRANCH="feat/spec_${NUM}${SLUG:+-${SLUG}}"

PROJECT_DIR="/home/nakashima/projects/axis-knowledge-rag"
SPEC="${PROJECT_DIR}/_ai_workspace/bridge/inbox/spec_${NUM}.md"
RESULT_REL="_ai_workspace/bridge/outbox/result_${NUM}.md"
LOG="${PROJECT_DIR}/_ai_workspace/logs/dispatch_${NUM}.log"
CLAUDE_BIN="/home/nakashima/.npm-global/bin/claude"

cd "$PROJECT_DIR" || exit 1
mkdir -p _ai_workspace/logs _ai_workspace/bridge/outbox

export CLAUDE_CONFIG_DIR="/home/nakashima/.claude-project-b"

# Load spec content into a variable using cmd substitution but DON'T concatenate.
SPEC_BODY="$(cat "$SPEC")"

# Build the prompt as a single string variable so claude gets it as one argv.
PROMPT="${SPEC_BODY}

上記が spec の全文です。指示に従って実装してください。以下は守ってください:
- 現在のブランチは ${BRANCH} (checkout 済み)。
- 完了したら git commit + git push -u origin ${BRANCH}
- main には絶対に push しないでください
- GitHub API 操作が必要なタスクは curl + PAT (~/.git-credentials から抽出) で実行
- 完了後 ${RESULT_REL} に結果レポートを書く"

{
  echo "[$(date -Is)] dispatch v4 start"
  echo "  spec     = $SPEC ($(wc -l < "$SPEC") lines)"
  echo "  branch   = $(git branch --show-current)"
  echo "  claude   = $CLAUDE_BIN ($($CLAUDE_BIN --version))"
  echo "  prompt len = ${#PROMPT} chars"
  echo "[$(date -Is)] launching claude..."
} > "$LOG"

"$CLAUDE_BIN" --dangerously-skip-permissions -p "$PROMPT" \
  >> "$LOG" 2>&1 < /dev/null

echo "[$(date -Is)] claude exited code=$?" >> "$LOG"
