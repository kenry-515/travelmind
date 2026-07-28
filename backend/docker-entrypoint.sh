#!/usr/bin/env bash
# TravelMind Agent — 后端容器入口：等待 DB → 向量库自举 → 迁移 → 启动 API。
set -e

# Phase 14d: SIGTERM handler — graceful shutdown
_cleanup() {
    echo "[entrypoint] SIGTERM received — shutting down..."
    exec 2>/dev/null || true
    exit 0
}
trap _cleanup SIGTERM SIGINT

# Phase 12.29e: wait-for-DB 重试循环（pg_isready 最多 30 次 ≈ 60s）
if [ -n "${DATABASE_URL_SYNC:-}" ]; then
  DB_HOST=$(echo "$DATABASE_URL_SYNC" | sed -E 's|.*@([^:/]+).*|\1|')
  DB_PORT=$(echo "$DATABASE_URL_SYNC" | sed -E 's|.*:([0-9]+)/.*|\1|')
  if [ -z "$DB_PORT" ]; then DB_PORT=5432; fi
  if [ -n "$DB_HOST" ]; then
    echo "[entrypoint] Waiting for PostgreSQL at $DB_HOST:$DB_PORT ..."
    for i in $(seq 1 30); do
      if pg_isready -h "$DB_HOST" -p "$DB_PORT" -q 2>/dev/null; then
        echo "[entrypoint] PostgreSQL is ready (attempt $i)"
        break
      fi
      if [ "$i" -eq 30 ]; then
        echo "[entrypoint] ERROR: PostgreSQL not available after 30 attempts — exiting"
        exit 1
      fi
      echo "[entrypoint] Waiting for PostgreSQL... ($i/30)"
      sleep 2
    done
  fi
fi

if ! python -c "
import sys
sys.path.insert(0, '/app')
from app.rag.vector_store import ChromaStore
s = ChromaStore()
s.connect()
sys.exit(0 if s.count() > 0 else 1)
"; then
  echo "[entrypoint] Chroma 向量库为空，开始从 data/attractions.json 重建..."
  python scripts/build_knowledge_base.py
fi

echo "[entrypoint] Running database migrations..."
# Phase 12.29e: 迁移失败 fast-fail（不再静默吞掉）
python -m alembic upgrade head

exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
