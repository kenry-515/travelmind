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
L3 生成层   LangGraph 管线（Profile→Trend→Weather→RAG→Recommend→Plan）
            + 契约校验（docs/itinerary.schema.json）+ 高德存续/顺路处理
            + validation_report（每个行程附带 POI 存续/顺路/天气校验报告，前端可视化）
```

## 部署约束

- **对话会话为内存实现**（TTL 2h）：必须**单 worker** 运行，进程重启即丢会话；生产环境请替换为 Redis 等外部存储（`backend/app/agents/dialog_manager.py`）
- **API Keys 按量付费**：DeepSeek（主 LLM）/ Kimi 开放平台（视觉）/ 高德（POI·路线）；Open-Meteo 天气免费
- 回归基准 fixture：`docs/itinerary.example.json`（上海）、`docs/itinerary.example.cq.json`（重庆）

## 质量评测

`backend/evals/` 提供约束通过率看板（三级指标，判定全部为确定性代码，不用 LLM 当评委）：

```bash
cd backend && python -X utf8 -m evals.run_evals   # 需后端在线，约 8-12 分钟
```

- **Micro**：所有 (query × 9 约束) 单元格的通过比例（schema/天数/地点数/预算/月份/POI 存续/顺路/天气匹配/天气覆盖）
- **Macro = Final Pass Rate**：单条 query 内全部约束通过才算通过的比例
- 评测集：`backend/evals/queries.json`（12 条，可扩充，不许写死在脚本）
- 结果落盘：`backend/evals/results/YYYY-MM-DD.json`（含逐 query 逐项明细）
- 当前基线指标：见 `docs/BASELINE.md`
