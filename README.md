# TravelMind Agent（智游伴）— AI 多 Agent 旅行规划系统

> AI-powered multi-agent travel planning system.
> React 19 + FastAPI + DeepSeek v4-flash + Chroma RAG + PostgreSQL

## 快速开始

```bash
# 1. 环境准备
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入 API Key（DeepSeek / Kimi 必填）

# 2. 启动全部服务（Docker）
docker compose up -d

# 3. 或本地开发
cd backend && python -m app.main          # API → :8000
cd frontend && npm run dev                 # Vite → :5173
```

## 架构

```
┌─ React 19 + Vite + Tailwind ──────────────────────┐
│  6 页面 / 13 组件 / SSE 流式 / PDF 导出            │
│  路由: /home /chat /recommend /itinerary /image    │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / SSE
┌─ FastAPI + uvicorn ──┴──────────────────────────────┐
│  23 条路由 / 对话状态机 / 令牌桶限流 60rpm          │
│  9 路由组: health/chat/agent/recommend/weather/     │
│           image/dialog/itineraries/favorites         │
└──────────────────────┬──────────────────────────────┘
                       │
┌─ 7 步 Agent 管线 ───┴──────────────────────────────┐
│  Profile → Trend → Weather → RAG → Recommend →      │
│  Plan → Aggregator                                   │
│  契约校验 + 路线优化 + POI 存续 + 价格注入          │
└──────────────────────┬──────────────────────────────┘
                       │
┌─ 外部服务 ──────────┴──────────────────────────────┐
│  DeepSeek v4-flash（推理） Kimi k2.6（视觉）        │
│  Chroma + TF-IDF 1075维 RAG / Open-Meteo 天气       │
│  PostgreSQL / Redis / Amap（可选）                   │
└─────────────────────────────────────────────────────┘
```

## API 文档

启动后端后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## 质量指标

| 项目 | 数值 |
|------|------|
| 单元测试 | 483+ |
| E2E 测试 | 27 tests |
| 评测 queries | 80 × 28 约束 |
| 知识库 POI | 2,410 / 30 城市 |
| 评测 Micro | 85.0% |
| 评测 Macro | 76.2% (61/80) |

## 开发命令

```bash
# 全量开发循环
cd backend && bash scripts/fixcycle.sh

# 环境预检
cd backend && python scripts/preflight_check.py

# E2E 测试
cd frontend && npm run test:e2e

# 全量评测
cd backend && python -X utf8 -m evals.run_evals

# pytest 单元测试
cd backend && python -m pytest -q

# 类型检查
cd frontend && npx tsc -b
```

## 文档

- [SOP 矩阵](docs/SOP_MATRIX.md) — 功能正逆向路径文档
- [评测基线](docs/BASELINE.md) — 约束通过率看板
- [部署指南](docs/DEPLOY.md) — Docker 部署说明
