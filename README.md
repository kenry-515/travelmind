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
```

## 部署约束

- **对话会话为内存实现**（TTL 2h）：必须**单 worker** 运行，进程重启即丢会话；生产环境请替换为 Redis 等外部存储（`backend/app/agents/dialog_manager.py`）
- **API Keys 按量付费**：DeepSeek（主 LLM）/ Kimi 开放平台（视觉）/ 高德（POI·路线）；Open-Meteo 天气免费
- 回归基准 fixture：`docs/itinerary.example.json`（上海）、`docs/itinerary.example.cq.json`（重庆）
