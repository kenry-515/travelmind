#!/usr/bin/env bash
# TravelMind Agent — 后端容器入口：向量库为空时先自举，再启动 API。
set -e

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

exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
