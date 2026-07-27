#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# TravelMind Agent — 一站式开发循环（fixcycle）
# Phase 12.28a — 将每轮开发固定步骤压缩为一条命令
#
# 编排：pytest → build → oxlint → 重启后端 → eval_smart → update_docs
#
# 用法：
#   bash scripts/fixcycle.sh              # 完整循环
#   bash scripts/fixcycle.sh --skip-eval  # 跳过评测（快速迭代）
#   bash scripts/fixcycle.sh --quick      # 仅 pytest+build+lint（最快）
#   bash scripts/fixcycle.sh --no-restart # 不重启后端
# ──────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
ROOT_DIR="$(dirname "$BACKEND_DIR")"
FRONTEND_DIR="$ROOT_DIR/frontend"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
SKIP_EVAL=false
SKIP_RESTART=false
QUICK=false

# Parse args
for arg in "$@"; do
    case "$arg" in
        --skip-eval) SKIP_EVAL=true ;;
        --no-restart) SKIP_RESTART=true ;;
        --quick) QUICK=true; SKIP_EVAL=true ;;
    esac
done

log_section() {
    echo ""
    echo -e "${CYAN}═══ $1 ═══${NC}"
}

log_pass() {
    echo -e "  ${GREEN}✅ $1${NC}"
    PASS=$((PASS + 1))
}

log_fail() {
    echo -e "  ${RED}❌ $1${NC}"
    FAIL=$((FAIL + 1))
}

log_warn() {
    echo -e "  ${YELLOW}⚠️  $1${NC}"
}

# ── Step 1: pytest ──────────────────────────────────────
log_section "1/6 pytest"
cd "$BACKEND_DIR"
if python -m pytest -q 2>&1; then
    log_pass "pytest 全部通过"
else
    log_fail "pytest 失败"
    exit 1
fi

# ── Step 2: Frontend build ──────────────────────────────
log_section "2/6 npm run build"
cd "$FRONTEND_DIR"
if npm run build 2>&1; then
    log_pass "TypeScript build 0 错误"
else
    log_fail "TypeScript build 失败"
    exit 1
fi

# ── Step 3: oxlint ──────────────────────────────────────
log_section "3/6 oxlint"
if npx oxlint 2>&1; then
    log_pass "oxlint 0 错误"
else
    log_fail "oxlint 失败"
    exit 1
fi

cd "$BACKEND_DIR"

# ── Step 4: 重启后端 ────────────────────────────────────
if $SKIP_RESTART; then
    log_warn "4/6 跳过重启后端（--no-restart）"
elif $QUICK; then
    log_warn "4/6 跳过重启后端（--quick）"
else
    log_section "4/6 重启后端"
    if bash scripts/backend_restart.sh 2>&1; then
        log_pass "后端已重启并就绪"
    else
        log_fail "后端重启失败"
        exit 1
    fi
fi

# ── Step 5: Smart Eval ──────────────────────────────────
if $SKIP_EVAL || $QUICK; then
    if $QUICK; then
        log_warn "5/6 跳过评测（--quick）"
    else
        log_warn "5/6 跳过评测（--skip-eval）"
    fi
else
    log_section "5/6 eval_smart（增量评测）"
    if python -X utf8 scripts/eval_smart.py 2>&1; then
        log_pass "eval_smart 通过（零劣化）"
    else
        log_fail "eval_smart 检测到劣化"
        # Don't exit — allow doc update to proceed but flag failure
    fi
fi

# ── Step 6: Update Docs ─────────────────────────────────
log_section "6/6 update_docs"
DOC_UPDATED=false
# Try to auto-update with latest eval result
LATEST_RESULT=$(ls -t "$BACKEND_DIR/evals/results/"*.json 2>/dev/null | head -1 || echo "")
if [ -n "$LATEST_RESULT" ] && [ -f "$LATEST_RESULT" ]; then
    # Extract metrics from latest result for doc update
    MICRO=$(python -c "import json; d=json.load(open('$LATEST_RESULT','r',encoding='utf-8')); print(d.get('micro',0))" 2>/dev/null || echo "1.0")
    MACRO=$(python -c "import json; d=json.load(open('$LATEST_RESULT','r',encoding='utf-8')); print(d.get('macro',0))" 2>/dev/null || echo "1.0")
    TEST_COUNT=$(python -m pytest --co -q 2>/dev/null | tail -1 | grep -oP '\d+(?= tests)' || echo "349")

    if python -X utf8 scripts/update_docs.py "$LATEST_RESULT" \
        --phase "12.28a" \
        --test-count "$TEST_COUNT" 2>&1; then
        log_pass "文档已更新"
        DOC_UPDATED=true
    else
        log_warn "文档自动更新失败（可手动执行）"
    fi
else
    log_warn "无评测结果，跳过文档更新"
fi

# ── Summary ──────────────────────────────────────────────
echo ""
echo -e "${CYAN}══════════════════════════════════════${NC}"
echo -e "${CYAN}  fixcycle 完成${NC}"
echo -e "${CYAN}══════════════════════════════════════${NC}"
echo -e "  通过: ${GREEN}${PASS}${NC}"
if [ $FAIL -gt 0 ]; then
    echo -e "  失败: ${RED}${FAIL}${NC}"
fi
echo ""

if [ "$DOC_UPDATED" = false ] && ! $SKIP_EVAL && ! $QUICK; then
    echo -e "${YELLOW}💡 提示：运行以下命令手动更新文档：${NC}"
    echo "   cd backend && python -X utf8 scripts/update_docs.py <evals/results/最新.json> --phase 12.28a"
fi

exit $FAIL
