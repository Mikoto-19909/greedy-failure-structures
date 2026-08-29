#!/bin/bash
# 并行多分支 Agent 演示（简化版）
# 3 个 agent 分别给 3 个 contracts 模块补 docstring
# 每个 agent 在独立 worktree 中工作，不需要 Bash 权限

set -e
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
WORKTREE_ROOT="$(cd -- "$REPO_ROOT/.." && pwd)"
BRANCH_PREFIX="agent-docstring"

# ---- 清理 ----
for i in 1 2 3; do
  git -C "$REPO_ROOT" worktree remove --force "$WORKTREE_ROOT/wt-$i" 2>/dev/null || true
done
git -C "$REPO_ROOT" branch -D "$BRANCH_PREFIX/benchmark-result" "$BRANCH_PREFIX/contract-csv" "$BRANCH_PREFIX/registry-contracts" 2>/dev/null || true

# ---- 创建 worktrees ----
echo "=== Creating 3 worktrees ==="
git -C "$REPO_ROOT" worktree add "$WORKTREE_ROOT/wt-1" -b "${BRANCH_PREFIX}/benchmark-result" HEAD
git -C "$REPO_ROOT" worktree add "$WORKTREE_ROOT/wt-2" -b "${BRANCH_PREFIX}/contract-csv" HEAD
git -C "$REPO_ROOT" worktree add "$WORKTREE_ROOT/wt-3" -b "${BRANCH_PREFIX}/registry-contracts" HEAD

# ---- 启动 3 个 agent（只用 Read + Write，不需要 Bash）----
echo "=== Launching 3 agents ==="

(cd "$WORKTREE_ROOT/wt-1" && claude -p \
  "Read src/maxcover/_benchmark_result.py. Add a clear module-level docstring at the top explaining what this module does. Write the file back." \
  --allowedTools "Read,Write") &
PID1=$!

(cd "$WORKTREE_ROOT/wt-2" && claude -p \
  "Read src/maxcover/_contract_csv.py. Add a clear module-level docstring at the top explaining what this module does. Write the file back." \
  --allowedTools "Read,Write") &
PID2=$!

(cd "$WORKTREE_ROOT/wt-3" && claude -p \
  "Read src/maxcover/_registry_contracts.py. Add a clear module-level docstring at the top explaining what this module does. Write the file back." \
  --allowedTools "Read,Write") &
PID3=$!

echo "Agent 1 (benchmark-result): PID $PID1"
echo "Agent 2 (contract-csv):     PID $PID2"
echo "Agent 3 (registry):         PID $PID3"

# ---- 等待 ----
echo "=== Waiting ==="
AGENT_FAILURE=0
if wait "$PID1"; then echo "Agent 1: DONE"; else AGENT_EXIT_CODE=$?; echo "Agent 1: FAILED (exit $AGENT_EXIT_CODE)"; AGENT_FAILURE=1; fi
if wait "$PID2"; then echo "Agent 2: DONE"; else AGENT_EXIT_CODE=$?; echo "Agent 2: FAILED (exit $AGENT_EXIT_CODE)"; AGENT_FAILURE=1; fi
if wait "$PID3"; then echo "Agent 3: DONE"; else AGENT_EXIT_CODE=$?; echo "Agent 3: FAILED (exit $AGENT_EXIT_CODE)"; AGENT_FAILURE=1; fi

if [ "$AGENT_FAILURE" -ne 0 ]; then
  echo "At least one agent failed; stopping before reporting success." >&2
  exit 1
fi

# ---- 结果 ----
echo "=== Results ==="
for i in 1 2 3; do
  WT="$WORKTREE_ROOT/wt-$i"
  if [ -d "$WT" ]; then
    CHANGES=$(git -C "$WT" diff --stat)
    if [ -n "$CHANGES" ]; then
      echo "wt-$i: changed"
      echo "$CHANGES"
    else
      echo "wt-$i: no changes"
    fi
  fi
done

# ---- 清理 ----
echo "=== Cleaning up ==="
for i in 1 2 3; do
  git -C "$REPO_ROOT" worktree remove "$WORKTREE_ROOT/wt-$i" --force 2>/dev/null || true
done

echo "=== Done ==="
git -C "$REPO_ROOT" branch | grep "$BRANCH_PREFIX" || echo "(no branches created)"
