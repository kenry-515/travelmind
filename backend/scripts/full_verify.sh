#!/usr/bin/env bash
# TravelMind — 提交前全量验证（零 LLM 成本）
# 用法: bash scripts/full_verify.sh   （在 backend/ 目录下执行）
# 行为: pytest → 前端 build → oxlint → 冒烟（需后端在线），逐项输出 PASS/FAIL，任一失败即非零退出
set -u
FAIL=0

step() { echo; echo "===== $1 ====="; }

cd "$(dirname "$0")/.."   # → backend/

step "1/4 后端单测（backend）"
(python -m pytest 2>&1 | grep -E "passed|failed" | tail -1) || FAIL=1

step "2/4 前端构建（TypeScript）"
(cd ../frontend && npm run build 2>&1 | grep -E "error|✓ built" | tail -3) || FAIL=1

step "3/4 前端 Lint（oxlint）"
(cd ../frontend && npx oxlint 2>&1 | tail -2) || FAIL=1

step "4/4 全栈冒烟（需后端在线）"
if curl -s -m 3 http://localhost:8000/api/v1/health >/dev/null 2>&1; then
  (python -X utf8 scripts/smoke_test.py 2>&1 | tail -3) || FAIL=1
else
  echo "SKIP: 后端不在线（可用 bash scripts/backend_restart.sh 启动后重跑）"
fi

echo
if [ "$FAIL" = "0" ]; then echo "===== 全量验证: ALL PASS ====="; else echo "===== 全量验证: 有失败项 ====="; fi
exit $FAIL
