#!/usr/bin/env bash
# dispatch (Linux native claude, branch model, feature-branch push enabled)
# 使い方: bash dispatch.sh 006 docker
set -euo pipefail
NUM="${1:?spec 番号を指定 (例: 006)}"
SLUG="${2:-}"
BRANCH="feat/spec_${NUM}${SLUG:+-${SLUG}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
SPEC="_ai_workspace/bridge/inbox/spec_${NUM}.md"
RESULT="_ai_workspace/bridge/outbox/result_${NUM}.md"

if [ ! -f "$PROJECT_DIR/$SPEC" ]; then
  echo "ERROR: $PROJECT_DIR/$SPEC not found" >&2
  exit 1
fi

cd "$PROJECT_DIR"

CLAUDE_BIN="$HOME/.npm-global/bin/claude"
if [ ! -x "$CLAUDE_BIN" ]; then
  echo "ERROR: $CLAUDE_BIN not found or not executable" >&2
  exit 1
fi

export CLAUDE_CONFIG_DIR="$HOME/.claude-project-b"

echo "[dispatch] spec    = $SPEC"
echo "[dispatch] result  = $RESULT"
echo "[dispatch] account = dev-b (CLAUDE_CONFIG_DIR=$CLAUDE_CONFIG_DIR)"
echo "[dispatch] branch  = $BRANCH"
echo "[dispatch] claude  = $CLAUDE_BIN ($(\"$CLAUDE_BIN\" --version))"

git fetch origin
git checkout main 2>/dev/null || true
git pull origin main 2>&1 | tail -3 || true
git checkout -B "$BRANCH" origin/main
echo "[dispatch] checked out $BRANCH from origin/main"

echo "[dispatch] starting CC..."

"$CLAUDE_BIN" --dangerously-skip-permissions -p \
  "${SPEC} を読んで実行して。\
**重要: 現在のブランチは ${BRANCH} です。commit + push する時は \`git push -u origin ${BRANCH}\` でこのフィーチャーブランチに push してください。main に直接 push しないでください。**\
完了後は同階層 ${RESULT} に _ai_workspace/bridge/templates/result_template.md の構造で結果を書いて。\
GitHub アカウントは kazikimaguro13 (PAT 認証済み)。" \
  < /dev/null
