# TravelMind Agent — 完整项目交接文档

> **目标：** 让 KimiCode 无缝接管开发，从 Phase 5（Day 10）继续。
> **当前日期：** 2026-07-18
> **完成进度：** Phase 1-4 / 6（共 14 天，已完成 Day 1-9）

---

## 1. 项目概览

**TravelMind Agent（智游伴）** — 基于 LLM + 多 Agent 协作 + RAG + 多模态的 AI 旅游规划系统。

- **14 天 MVP**，目标是 AI 智能体创新大赛
- **核心流程：** 用户输入一句话 → Profile Agent → Trend Agent → Weather → RAG 检索 → Recommendation Agent（6 因子打分）→ Planning Agent（LLM 生成行程）→ 前端展示

### 当前完成状态

| Phase | 天数 | 内容 | 状态 |
|-------|------|------|------|
| Phase 1 | Day 1-2 | 项目脚手架 + 前后端连接 | ✅ |
| Phase 2 | Day 3 | LLM Service + Chat API + ChatPage | ✅ |
| Phase 3 | Day 4-7 | 多 Agent + 真实数据 + RAG | ✅ |
| Phase 4 | Day 8-9 | 天气服务 + 推荐/行程 API + 前端页面 | ✅ |
| **Phase 5** | **Day 10-11** | **多模态（Qwen-VL 图片识别）** | **← 下一步** |
| Phase 6 | Day 12-14 | 数据扩充 + UI 打磨 + Demo 准备 | 待开始 |

---

## 2. 技术栈

| 层 | 技术 |
|---|------|
| **前端** | React 19 + TypeScript 6 + Vite 8 + Tailwind CSS 4 + shadcn/ui + Lucide React |
| **后端** | Python 3.11 + FastAPI + Uvicorn + Pydantic v2 |
| **LLM** | DeepSeek（deepseek-chat），用户付费 API Key |
| **视觉** | Qwen-VL-Max（主力）/ Tencent Hunyuan-Vision（备选）|
| **地图** | 高德 Amap（POI 搜索 + 步行/公交/驾车路线 + 距离矩阵）— 已替代百度 |
| **天气** | Open-Meteo（免费，无限调用，无需 Key）|
| **数据** | Wikidata SPARQL → Wikipedia API → Amap POI → DeepSeek AI 标注 |
| **向量库** | Chroma（持久化到 `chroma_data/`），TF-IDF + Tag One-Hot = 1075 维 |
| **Agent 框架** | LangGraph StateGraph（TravelState TypedDict）|
| **数据库** | PostgreSQL + asyncpg（开发环境可选，离线也能跑）|

---

## 3. 目录结构

```
D:\TravelMindAgent\
├── HANDOFF_TO_KIMICODE.md     ← 当前文件
├── backend\
│   ├── .env                    # 实际 Key（不提交）
│   ├── .env.example            # Key 模板
│   ├── requirements.txt
│   ├── app\
│   │   ├── main.py             # FastAPI 入口，lifespan 中初始化 RAG
│   │   ├── config\settings.py  # pydantic-settings
│   │   ├── database\           # SQLAlchemy async + models
│   │   ├── middleware\         # RequestIDMiddleware（纯 ASGI）
│   │   ├── api\
│   │   │   ├── __init__.py     # 路由聚合（9 条路由）
│   │   │   ├── health.py       # GET /api/v1/health
│   │   │   ├── chat.py         # POST /api/v1/chat (SSE 流式)
│   │   │   ├── agent.py        # POST /api/v1/agent/plan + /agent/profile
│   │   │   ├── recommend.py    # POST /api/v1/recommend + /recommend/quick
│   │   │   └── weather.py      # GET /weather/{city} + /weather/cities + POST /weather/travel-advice
│   │   ├── agents\
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py      # LangGraph 主控（7 节点线性管线）
│   │   │   ├── profile_agent.py     # NL→结构化画像（DeepSeek chat_structured）
│   │   │   ├── trend_agent.py       # 热度分析（4 策略模糊匹配）
│   │   │   ├── recommendation_agent.py  # 6 因子加权打分
│   │   │   └── planning_agent.py    # LLM 生成日程（DeepSeek + JSON Schema）
│   │   ├── services\
│   │   │   ├── llm_service.py       # BaseLLMProvider + DeepSeekProvider
│   │   │   ├── amap_service.py      # 高德路线 API（步行/公交/距离矩阵 + MD5 签名）
│   │   │   └── weather_service.py   # Open-Meteo 7 天预报
│   │   └── rag\
│   │       ├── __init__.py          # init_rag_from_data() 启动入口
│   │       ├── embedding.py         # TFIDFEmbeddingProvider + CompositeEmbeddingProvider
│   │       ├── vector_store.py      # ChromaStore 封装
│   │       └── retriever.py         # 5 因子 RAG 检索器
│   ├── scripts\
│   │   ├── fetch_wikidata.py        # Wikidata SPARQL（10 城市）
│   │   ├── enrich_wikipedia.py      # Wikipedia 摘要（wikimedia.org 绕过 GFW）
│   │   ├── enrich_amap.py           # 高德 POI 补充 + MD5 签名
│   │   ├── ai_enrich.py             # DeepSeek 批量标注
│   │   └── build_knowledge_base.py  # 合并 → Chroma 入库
│   ├── data\
│   │   ├── attractions.json         # 最终知识库（445 景点，10 城市）
│   │   ├── trends.json              # 56 条趋势数据
│   │   └── tags.json                # 51 个标签（6 大类）
│   └── chroma_data\                 # Chroma 持久化向量库
├── frontend\
│   ├── package.json
│   ├── vite.config.ts               # 已配置 /api 代理到 localhost:8000
│   ├── src\
│   │   ├── main.tsx
│   │   ├── App.tsx                  # 4 条路由
│   │   ├── index.css                # Tailwind v4
│   │   ├── lib\api.ts               # 完整类型化 API Client
│   │   ├── components\
│   │   │   ├── SearchInput.tsx
│   │   │   ├── ExampleQuestions.tsx
│   │   │   ├── ChatBox.tsx
│   │   │   ├── ChatInput.tsx
│   │   │   ├── Toast.tsx
│   │   │   ├── ErrorBoundary.tsx
│   │   │   ├── ScoreBar.tsx         # 6 因子评分可视化（新增）
│   │   │   └── PlaceCard.tsx        # 景点推荐卡片（新增）
│   │   └── pages\
│   │       ├── HomePage.tsx
│   │       ├── ChatPage.tsx
│   │       ├── RecommendPage.tsx    # 推荐搜索 + 结果页（新增）
│   │       └── ItineraryPage.tsx    # 日程时间线展示页（新增）
└── memory\                          # 项目记忆（完整上下文）
    ├── MEMORY.md
    ├── project-overview.md
    ├── tech-stack.md
    ├── architecture.md
    ├── data-strategy.md
    ├── api-constraints.md（需更新，还有百度残留）
    ├── task-breakdown.md
    ├── day5-status.md
    ├── day6-status.md
    ├── day7-status.md
    └── day8-9-status.md
```

---

## 4. 当前全部 API 路由（9 条）

```
GET    /api/v1/health
POST   /api/v1/chat
POST   /api/v1/agent/plan          ← 完整 Agent 管线（Profile→Trend→Weather→RAG→Recommend→Plan）
POST   /api/v1/agent/profile       ← 独立画像提取
POST   /api/v1/recommend           ← 仅推荐（停在评分，不生成行程）
POST   /api/v1/recommend/quick     ← 快速推荐（需预提取参数）
GET    /api/v1/weather/cities      ← 支持的城市列表
GET    /api/v1/weather/{city}      ← 7 天天气预报 + 旅行评分
POST   /api/v1/weather/travel-advice ← 简化天气建议
```

---

## 5. 核心架构决策

### 5.1 LangGraph 管线（orchestrator.py）

```
START → profile_extraction → trend_analysis → weather_fetch
      → rag_retrieval → recommendation → planning → response_aggregator → END
```

- 每个节点包裹在 try/except 中，单点失败不中断管线
- 错误累积在 `state["error"]` 中，用分号分隔
- 所有 Agent 通过模块级 lazy import 加载，ImportError → stub skipping

### 5.2 6 因子推荐打分公式

```
Score = 0.35 × Preference_Match     (Jaccard: 用户标签 vs 景点标签)
      + 0.25 × Trend_Heat           (trends.json + 4 策略模糊匹配)
      + 0.15 × Budget_Match         (经济/适中/高端三档)
      + 0.10 × Location_Efficiency  (高德距离矩阵: ≤5km=1.0, >30km=0.1)
      + 0.10 × Time_Match           (best_time vs 出行月份)
      + 0.05 × Data_Reliability     (wikidata+amap=0.9, amap=0.8, wikidata=0.7)
```

### 5.3 RAG 检索（5 因子重排序）

```
Relevance = 0.45 × similarity + 0.25 × tag_match + 0.15 × popularity
          + 0.10 × budget + 0.05 × season
```

### 5.4 嵌入方案

- **TF-IDF**（sklearn TfidfVectorizer, char_wb, ngram 2-4, max_features=1024）
- **Tag One-Hot**（51 维）
- **Composite** = TF-IDF(70%) + Tag(30%) = **1075 维**
- 原因：PyTorch 在 Windows 上 fbgemm.dll 损坏，DeepSeek 无 embeddings API

### 5.5 高德 API 签名

```python
def _amap_sign(params: dict, sign_key: str) -> str:
    sorted_keys = sorted(params.keys())
    raw = "&".join(f"{k}={params[k]}" for k in sorted_keys)
    raw += sign_key
    return hashlib.md5(raw.encode("utf-8")).hexdigest()
# 参数中需要加上 sig 字段
```

### 5.6 Wikipedia GFW 绕过

- `zh.wikipedia.org` 被 TLS 干扰
- 解决：使用 `wikimedia.org/api/rest_v1/` 作为 base URL，设 `Host: zh.wikipedia.org` header
- 如果失效 → 跳过 Wikipedia，直接用 DeepSeek AI 标注

---

## 6. 数据现状

### 景点知识库（attractions.json）

| 城市 | 数量 | 来源 |
|------|------|------|
| 重庆 | 80 | Wikidata + Amap |
| 北京 | 78 | Wikidata |
| 成都 | 50 | Wikidata + Amap 补充 |
| 上海 | 50 | Wikidata |
| 西安 | 44 | Wikidata |
| 杭州 | 40 | Wikidata |
| 广州 | 30 | Wikidata + Amap 补充 |
| 长沙 | 28 | Wikidata |
| 厦门 | 25 | Wikidata + Amap 补充 |
| 大理 | 20 | Wikidata + Amap 补充 |
| **总计** | **445** | |

- 全部 445 个景点已 AI 标注（tags, suitable_for, best_time, price_level, popularity_score）
- Chroma 向量库：445 文档，1075 维，持久化在 `backend/chroma_data/`
- 趋势数据：56 条（10 城市）

---

## 7. 环境变量（.env）

当前 backend/.env 中已配置的 Key：
- `DEEPSEEK_API_KEY` — ✅ 已配置
- `AMAP_API_KEY` — ✅ 已配置
- `AMAP_SIGN_KEY` — ✅ 已配置（数字签名私钥，见 backend/.env）
- `DATABASE_URL` — PostgreSQL（开发环境可选，不存在也能跑）
- Qwen-VL Key — ⚠️ **Phase 5 需要配置**

---

## 8. 关键坑位 & 经验

### 已解决的坑
1. **Chroma 批量插入限制**：batch_size 不能超过 166，设为 150
2. **Chroma 遥测噪音**：`ANONYMIZED_TELEMETRY=False` 无法完全消除，SDK 版本 bug，不影响功能
3. **高德 API 签名**：必须在控制台开启数字签名，否则 INVALID_USER_SIGNATURE
4. **SSE 流式**：不能用 `BaseHTTPMiddleware`（会缓冲响应），必须用纯 ASGI middleware
5. **趋势数据匹配**：Wikidata 景点偏历史/博物馆，缺少网红景点（洪崖洞、李子坝等），需要趋势补充机制
6. **Planning Agent 偶发空响应**：加了 retry（2 次）
7. **PyTorch Windows**：fbgemm.dll 损坏，放弃 PyTorch，用 sklearn TF-IDF 替代
8. **Wikipedia GFW**：TLS 干扰，用 wikimedia.org 作为代理
9. **DB 启动超时**：从 5s 降到 2s，避免离线开发时卡住

### 待注意的坑
- DeepSeek API 偶发超时（30-90s），planning agent 已有 retry
- Windows GBK 终端编码问题，不影响功能
- 前端端口 5173，后端 8000，Vite 已配置 proxy

---

## 9. 下一步：Phase 5 多模态（Day 10-11）

### Day 10: 视觉服务 + Vision Agent
**需要创建的文件：**

1. **`backend/app/services/vision_service.py`**
   - `BaseVisionProvider` 抽象类
   - `QwenVLProvider` — 阿里云 DashScope API（`https://dashscope.aliyuncs.com/compatible-mode/v1`）
   - `TencentHunyuanProvider` — 备选
   - `analyze_image(image_base64) → {location, tags, description}`
   - Qwen-VL-Max 免费额度：100 万 tokens/月

2. **`backend/app/agents/vision_agent.py`**
   - `analyze_travel_image(image_data) → dict`
   - 从图片识别：地点名称、地标特征、风格标签（古镇/自然/城市等）、氛围
   - 将识别结果转为用户标签，供推荐管线使用

3. **`backend/app/api/image.py`**
   - `POST /api/v1/image/analyze` — multipart/form-data 上传图片
   - 返回 `{location, tags, description, confidence}`

### Day 11: 前端图片页
4. **`frontend/src/components/ImageUploader.tsx`** — 拖拽上传组件
5. **`frontend/src/pages/ImagePage.tsx`** — 上传 + 分析结果展示
6. 更新 `App.tsx` 添加 `/image` 路由

### 验证命令
```bash
# 后端
curl -X POST http://localhost:8000/api/v1/image/analyze \
  -F "image=@test_photo.jpg"

# 前端
cd frontend && npm run build  # 必须通过
```

---

## 10. 启动命令

```bash
# 后端（在 backend/ 目录下）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端（在 frontend/ 目录下）
npm run dev

# 前端构建检查
npm run build
```

---

## 11. Memory 文件完整内容

以下是从 `memory/` 目录导出的全部项目记忆，供 KimiCode 全面了解上下文。

### 11.1 Project Overview

**TravelMind Agent（智游伴）** — 基于大语言模型、多 Agent 协作、RAG 知识增强、多模态理解能力的 AI 旅游决策智能体。

目标：14 天 MVP，完成从"用户一句话输入"到"AI 生成完整旅行方案 + 图片识别"的闭环 Web Demo。

核心用户流程：用户输入需求 → User Profile Agent → Orchestrator 任务分配 → RAG 知识检索 → Recommendation Agent → Planning Agent → LLM 生成方案 → 前端展示

### 11.2 架构（5 层）

```
L1: User Interaction  — React + TS + Vite + Tailwind + shadcn/ui
L2: Application Service — FastAPI REST /api/v1/*
L3: Agent Intelligence — LangGraph StateGraph (Orchestrator + 6 Agents)
L4: AI Capability      — LLM Service / Vision Service / Embedding Service
L5: Data Resource      — PostgreSQL + Chroma + File Storage
```

**前端路由：**
| 路由 | 页面 | 关键组件 |
|------|------|---------|
| `/` | HomePage | SearchInput, ExampleQuestions |
| `/chat` | ChatPage | ChatBox, MessageBubble, ChatInput |
| `/recommend` | RecommendPage | PlaceCard[], ScoreBar, TagList |
| `/itinerary` | ItineraryPage | DayTimeline, DayCard, TransportTip |
| `/image` | ImagePage | ImageUploader, AnalyzeResult（待开发）|

### 11.3 数据管线

```
Wikidata SPARQL (CC0)
  └─► Query tourist attractions per city
      └─► {name, lat, lon, wikiArticle}

Wikipedia API (via wikimedia.org 绕过 GFW)
  └─► Fetch Chinese page extract

Amap POI Search（高德补充 + MD5 签名）
  └─► Supplement niche cities（成都/广州/厦门/大理）
      └─► Verify coordinates, add address

DeepSeek AI Enrichment（批量 25 个）
  └─► tags, suitable_for, best_time, price_level, popularity_score

Merge → data/attractions.json (445 places) → Chroma (1075 维)
```

### 11.4 Phase 3 完整状态（Day 4-7）

已实现的 5 个 Agent：

1. **Profile Agent** — DeepSeek chat_structured() NL → {destination, tags, budget, days, companions, travel_style, constraints}
2. **Trend Agent** — 56 条趋势数据，4 策略模糊名称匹配（exact → substring → core name strip → shared 3-char chunks），未匹配的热门景点会作为合成推荐补充
3. **RAG Retriever** — 5 因子检索（similarity 0.45 + tag_match 0.25 + popularity 0.15 + budget 0.10 + season 0.05）
4. **Recommendation Agent** — 6 因子加权打分，高德距离矩阵计算 Location Efficiency（≤5km=1.0, >30km=0.1），趋势补充机制
5. **Planning Agent** — DeepSeek JSON Schema 输出结构化日程（overview, days, plan[{day, theme, attractions, meals, transport_tips}], general_tips），支持 retry

### 11.5 Phase 4 完整状态（Day 8-9）

**后端新增：**
- Weather Service：Open-Meteo 7 天预报 + 旅行适宜度评分（雷暴 -0.8, 大雨 -0.6, 高温 >38°C -0.3, 低温 <0°C -0.3, 大风 >50km/h -0.2）
- Weather API：3 个端点
- Recommend API：2 个端点（完整推荐 + 快速推荐）
- Orchestrator 新增 weather_fetch 节点

**前端新增：**
- ScoreBar 组件（6 因子彩色条形图）
- PlaceCard 组件（排名卡片 + 可展开评分明细）
- RecommendPage（搜索 → 加载 → 结果网格）
- ItineraryPage（天气卡片 + 日程时间线 + 餐饮/交通）
- 完整 TypeScript 类型化 API Client

### 11.6 API 约束（需更新：还有百度残留）

| API | 每日免费额度 | 状态 |
|-----|------------|------|
| DeepSeek chat | Pay-as-you-go | ✅ 主力 LLM |
| Qwen-VL-Max | 1M tokens/月 | ⚠️ 待 Phase 5 配置 |
| Tencent Hunyuan | 1000 图片/天 | 备选 |
| Amap POI/Search | 5000/天 | ✅ 已配置 + 签名 |
| Open-Meteo Weather | 无限（无需 Key）| ✅ 已集成 |
| Wikidata SPARQL | 无限（无需 Key）| ✅ 已获取 |
| Wikipedia API | 无限（无需 Key）| ✅ 已获取 |

### 11.7 数据质量

- 445 个景点，10 城市全覆盖
- 全部 AI 标注（tags, suitable_for, best_time, price_level, popularity_score）
- 每条有 `_validate_enrichment()` 服务端校验
- 56 条趋势数据（手动整理，结构化方便未来替换为 API）
- 51 个标签（6 大类：旅行主题/活动类型/自然风光/人文历史/美食购物/出行特征）

---

## 12. 给 KimiCode 的操作指南

1. **先跑通现有系统：**
   ```bash
   # 终端 1
   cd D:\TravelMindAgent\backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   
   # 终端 2
   cd D:\TravelMindAgent\frontend
   npm run dev
   # 访问 http://localhost:5173
   ```

2. **测试 API：**
   ```bash
   curl http://localhost:8000/api/v1/health
   curl http://localhost:8000/api/v1/weather/cities
   ```

3. **开始 Phase 5：**
   - 需要配置 `QWEN_API_KEY` 到 `backend/.env`
   - 创建 `backend/app/services/vision_service.py`
   - 创建 `backend/app/agents/vision_agent.py`
   - 创建 `backend/app/api/image.py`
   - 创建前端图片上传组件和页面

4. **提交检查：** `cd frontend && npm run build` 必须通过（TypeScript 严格模式）

---

**文档结束。祝 KimiCode 开发顺利！🚀**
