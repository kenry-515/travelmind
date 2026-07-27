# TravelMind Agent (智游伴)

多 Agent 协作 + RAG + 多模态的 AI 旅行规划系统：多轮对话收敛意图，一键生成经过真实数据校验的结构化行程卡片。

## 运行方式

**依赖**：Python 3.11+ / Node.js 18+

```bash
# 后端（端口 8000）
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填入 DEEPSEEK_API_KEY / MOONSHOT_API_KEY / AMAP_API_KEY(+AMAP_SIGN_KEY)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端（端口 5173，/api 已代理到 8000）
cd frontend
npm install
npm run dev
```

Windows 可双击根目录 `start-dev.bat` 一键启动。

## 架构三层

```
L1 交互层   React 19 + Vite（对话式规划 / 推荐 / 行程卡片 / 图片识别）
L2 意图层   FastAPI + 对话状态机（槽位收敛、修改分流、局部重生成）
L3 生成层   7 步异步管线（Profile→Trend→Weather→RAG→Recommend→Plan）
            + 契约校验（docs/itinerary.schema.json）+ 高德存续/顺路处理
            + validation_report（每个行程附带 POI 存续/顺路/天气校验报告，前端可视化）
```

## 部署约束

- **对话会话存储**：默认内存实现（TTL 2h，单 worker，重启丢会话）；设置
  `SESSION_STORE=redis` + `REDIS_URL` 后切换 Redis 外置，**解除单 worker
  限制并支持重启恢复**（`uvicorn --workers 2` 冒烟已验证）
- **API Keys 按量付费**：DeepSeek（主 LLM）/ Kimi 开放平台（视觉）/ 高德（POI·路线）；Open-Meteo 天气免费
- **知识库**：1,721 POI / 30 城市（含 450 美食 POI），来源高德 API + Wikidata + AI 标注
- **ChromaDB**：1,721 文档，1,075 维向量（TF-IDF + Tag One-Hot）
- 回归基准 fixture：`docs/itinerary.example.json`（上海）、`docs/itinerary.example.cq.json`（重庆）

## 质量评测

`backend/evals/` 提供约束通过率看板（三级指标，判定全部为确定性代码，不用 LLM 当评委）：

```bash
cd backend && python -X utf8 -m evals.run_evals   # 需后端在线，约 8-12 分钟
```

- **Micro**：所有 (query × 24 约束) 单元格的通过比例
- **Macro = Final Pass Rate**：单条 query 内全部约束通过才算通过的比例
- 评测集：`backend/evals/queries.json`（63 条，7 分类，可扩充，不许写死在脚本）
- 结果落盘：`backend/evals/results/YYYY-MM-DD.json`（含逐 query 逐项明细）
- 当前基线指标：见 `docs/BASELINE.md`

## 数据巡检

知识库 POI 数据可能随时间过时。`backend/scripts/poi_health_check.py` 通过高德 API
逐条验证全部 KB POI 的存续状态，失效 POI 自动从推荐管线排除：

```bash
cd backend && python scripts/poi_health_check.py
```

报告输出到 `backend/data/poi_health_YYYY-MM-DD.json`。定时运行说明见
[`docs/DEPLOY.md` §8](docs/DEPLOY.md#8-poi-存续巡检)。

## 测试

```bash
cd backend && python -m pytest          # 单元测试（无真实外部调用，约 2s）
```

- 覆盖 dialog_manager / itinerary_contract / recommendation_agent 纯逻辑
  （槽位与分流、契约校验、6 因子评分），外部调用全部 mock/fake
- CI：`.github/workflows/ci.yml`（pytest + 前端 tsc + oxlint，push/PR 触发）
- 另有脚本级测试（见上文运行方式与本节之外）：`scripts/smoke_test.py`
  全栈冒烟、`scripts/contract_regression.py` 契约回归、`evals/` 质量看板
