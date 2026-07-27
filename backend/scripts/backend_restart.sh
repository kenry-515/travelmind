#!/usr/bin/env bash
# TravelMind — 后端重启（Windows Git Bash 专用）
# 用法: bash scripts/backend_restart.sh [--rebuild]
#   --rebuild  重启前先用 build_kb.py --only normalize,rebuild 重建 Chroma
# 行为: 杀掉 :8000 上的 uvicorn → （可选）重建 → 后台启动 → 轮询健康检查 → 打印 READY
set -u
cd "$(dirname "$0")/.."

REBUILD=0
[ "${1:-}" = "--rebuild" ] && REBUILD=1

echo "[1/4] 停止旧后端..."
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { \$_.CommandLine -match 'uvicorn' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null
sleep 2

if [ "$REBUILD" = "1" ]; then
  echo "[2/4] 重建 Chroma..."
  python -X utf8 scripts/build_kb.py --only normalize,rebuild 2>&1 | grep -E "补齐|count=|管线完成" | tail -4
else
  echo "[2/4] 跳过 Chroma 重建"
fi

echo "[3/4] 启动后端..."
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/travelmind-backend.log 2>&1 &
echo "  pid=$!"

echo "[4/4] 等待健康检查..."
for i in $(seq 1 24); do
  sleep 5
  if curl -s -m 3 http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    echo "READY: 后端已就绪（$((i*5))s）"
    curl -s -m 3 http://localhost:8000/api/v1/health
    exit 0
  fi
done
echo "FAIL: 120s 内后端未就绪，请查看 /tmp/travelmind-backend.log"
exit 1
