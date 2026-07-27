# TravelMind Agent (智游伴) — Claude Code 项目上下文

AI 多 Agent 旅行规划系统。MCP 大赛项目，已超出 MVP 进入持续优化。

## 快速命令

```bash
# 开发循环（一站式）
cd backend && bash scripts/fixcycle.sh              # 完整: pytest→build→lint→重启→eval→doc
cd backend && bash scripts/fixcycle.sh --quick      # 仅 pytest+build+lint

# 单独步骤
cd backend && python -m pytest -q                          # 349 测试 ~13s
cd frontend && npm run build                               # TypeScript 编译
cd backend && python -X utf8 -m evals.run_evals --out evals/results/$(date +%Y-%m-%d)-v1.json  # 全量评测

# 前后端启动
cd backend && python -m app.main          # API → :8000
cd frontend && npm run dev                # Vite → :5173

# Docker
docker compose up -d                      # 全栈一键启动
```

## 架构 (三层)

```
L1 React 19 + Vite + Tailwind → 6 页面 / 13 组件 / SSE 流式 / PDF 导出
L2 FastAPI (23 路由) + 对话状态机 + 令牌桶限流 60rpm
L3 7 步管线: Profile→Trend→Weather→RAG→Recommend→Plan→Aggregator
   + 契约校验 + 路线优化 + POI 存续 + 价格注入 + 天气缓存
```

## 关键技术决策

- **LLM**: DeepSeek v4-flash (主推理), Kimi k2.6 (视觉)
- **RAG**: Chroma + TF-IDF char n-gram (1075维, 轻量无需 GPU)
- **评分**: 6 因子公式 (Preference_Match×0.35 + Trend_Heat×0.25 + ...)
- **评测**: 80 queries × 28 约束确定性打分 (禁止 LLM 当评委)
- **地图**: Amap (可选, 当前优雅降级为 KB-only)
- **天气**: Open-Meteo (免费, 无 API Key) + TTL 30min 两级缓存
- **数据库**: PostgreSQL + Redis (外置 session) + Chroma (向量)
- **数据铁律**: 严禁 AI 编造数据，所有数值必须来自真实来源

## 项目技能 (5 个)

- `travelmind-devcycle` — 开发循环 (pytest → smoke → walkthrough → contract → eval)
- `travelmind-fixcycle` — 快速迭代 (pytest → build → lint → eval_smart → update_docs)
- `travelmind-eval` — 评测分析 (run_evals → 结果解读 → 建议)
- `travelmind-test` — 测试维护 (新增/修改单测 + evals queries)
- `travelmind-data` — 数据管线 (build_kb → health_check → social 采集)

## 目录速查

| 目录 | 内容 |
|------|------|
| `backend/app/agents/` | 9 Agent (orchestrator, planning, recommendation, profile, trend, route_optimizer, vision, price_enricher, dialog_manager) |
| `backend/app/api/` | 路由 (agent, dialog, recommend, itineraries, favorites, image, weather, health) |
| `backend/app/services/` | 外部服务 (amap, weather, weather_cache, vision, price_enricher, itinerary) |
| `backend/app/rag/` | RAG (retriever, vector_store) |
| `backend/app/middleware/` | 限流 + 请求 ID |
| `backend/evals/` | 评测框架 (run_evals.py, queries.json) |
| `backend/scripts/` | 工具脚本 (fixcycle, eval_smart, update_docs, build_kb) |
| `backend/data/` | KB 数据 (attractions.json) |
| `frontend/src/pages/` | 6 页面 (Home, Chat, Recommend, Itinerary, Image, History) |
| `frontend/src/components/` | 13 组件 |
| `docs/` | 文档 (BASELINE, DEMO_GUIDE, DEPLOY) |
| `skills/` | Claude Code 技能定义 |
| `memory/` | 持久化记忆 |

## 更多细节

- 完整交接文档: [HANDOFF_TO_KIMICODE.md](HANDOFF_TO_KIMICODE.md) (53KB 详尽版)
- 评测基线: [docs/BASELINE.md](docs/BASELINE.md)
- 部署指南: [docs/DEPLOY.md](docs/DEPLOY.md)
