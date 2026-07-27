# TravelMind Agent — 项目交接文档（Kimi Code / Claude Code 通用）

> **用途：** 任何 AI 编程助手（Kimi Code 或 Claude Code）都可凭本文档无缝接手开发。
> **维护约定（用户要求 2026-07-26）：** 每完成一轮开发，必须即时更新本文档的当前状态相关小节（头部快照、§1 状态表、§6 数据、§9 变更记录、§10 遗留与方向、§12 基线文件名），保证接手方拿到的是最新真相。
> **当前日期：** 2026-07-27
> **当前阶段：** 12.28
> **最新基线：** Micro 83.7% / Macro 61.3%（49/80）（12.28 v3，`2026-07-27-12.28-v3.json`）
> **最新评测存档：** `backend/evals/results/2026-07-27-phase12_28-v3.json`
>
> **⚠️ 交接状态：✅ Phase 12.28 已完成（2026-07-27）**——评测体系 v4.0（80 query × 28 约束）、5 个 skill、一站式 fixcycle 开发循环、暗色模式、骨架屏全站覆盖、后端健壮性加固。
>
> **上次完整交接：** 2026-07-27（Phase 12.27 收尾完成），本文档为最新状态

---

## 1. 项目概览

**TravelMind Agent（智游伴）** — 基于 LLM + 多 Agent 协作 + RAG + 多模态的 AI 旅游规划系统。

### 核心功能
1. **对话式规划**（主流程）：多轮对话收敛意图 → 槽位填充 → 确认 → 一键生成结构化行程
2. **智能推荐**：自然语言输入 → Profile 提取 → Trend 分析 → RAG 检索 → 7 因子打分排序
3. **行程管理**：SSE 流式生成 → 契约校验 → POI 存续验证 → 路线优化 → 价格注入 → 版本历史
4. **图片识别**：上传旅行照片 → Kimi k2.6 识别地标/风格标签 → 跨城推荐相似景点
5. **质量评测**：三级指标（Micro/Macro/Final）确定性打分，80 条查询 × 28 约束

### 当前完成状态（Phase 12.28 已完成，2026-07-27）

| 维度 | 数值 |
|------|------|
| 后端 Python 模块 | 50+ 个 |
| API 端点 | 24+ 条（9 个路由模块，+dialog/generate/stream） |
| Agent | 9 个 |
| Service | 15 个（+local_itinerary_store） |
| 单元测试 | **349 个全过**（0 失败，~13s） |
| 评测查询 | **80 条 × 28 约束**（7 分类） + **多轮剧本 28 断言**（dialog_scenarios.py） |
| 最新评测 | **Micro 83.7% / Macro 61.3%（49/80，12.28 v3）** |
| 知识库 | **2,321 POI / 30 城市** |
| 社交趋势 | social_trends_live.json 12 条实时热度（WebBridge 采集） |
| 前端页面 | 6 个（Home / Chat / Recommend / Itinerary / Image / History） |
| 前端组件 | 14 个 |
| TypeScript / oxlint | 0 错误 |
| 项目技能 | 5 个（travelmind-devcycle / eval / data / test / fixcycle，见 §14） |

---

## 2. 技术栈（与代码一致）

| 层 | 技术 |
|---|------|
| **前端** | React 19 + TypeScript + Vite + Tailwind CSS（无组件库，纯手工） |
| **状态管理** | React Context + useReducer（无 Redux） |
| **PDF 导出** | html2canvas + jsPDF |
| **Lint** | oxlint |
| **后端** | Python 3.11 + FastAPI + Uvicorn（支持多 worker） |
| **校验** | Pydantic v2 + pydantic-settings + jsonschema |
| **数据库** | SQLAlchemy 2.0 (async) + asyncpg (PostgreSQL) + Alembic（3 个迁移版本） |
| **缓存/会话** | Redis 5.2（可选，SESSION_STORE=redis 时启用） |
| **主 LLM** | DeepSeek `deepseek-v4-flash`（非思考模式，按量付费） |
| **视觉模型** | Kimi `kimi-k2.6`（`api.moonshot.cn`，按量付费） |
| **Embedding** | TF-IDF (scikit-learn, char n-gram 2-4, 1024 维) + Tag One-Hot (51 维) = 1075 维混合向量 |
| **向量库** | ChromaDB 0.5.20（PersistentClient, cosine HNSW） |
| **地图** | 高德 Amap（POI 搜索 + 步行/公交/驾车路线 + 距离矩阵 + MD5 签名） |
| **天气** | Open-Meteo（无限免费，无需 Key） |
| **HTTP 客户端** | httpx 0.28（异步，trust_env=False） |
| **数据管线** | Wikidata SPARQL (CC0) → Wikipedia API (CC BY-SA) → Amap POI → AI enrich → Price enrich → Chroma |
| **DevOps** | Docker Compose（4 服务）+ GitHub Actions CI（pytest + tsc + oxlint） |

---

## 3. 完整目录结构

```
D:\TravelMindAgent\
├── HANDOFF_TO_KIMICODE.md      ← 当前文件
├── README.md                    # 项目 README（运行/评测/测试说明）
├── start-dev.bat                # Windows 一键启动
├── docker-compose.yml
├── docs\
│   ├── BASELINE.md              # 所有 Phase 评测基线（含 Phase 12.16 完整数据）
│   ├── DEMO_GUIDE.md            # 比赛演示指南（5 分钟演示路径）
│   └── DEPLOY.md                # Docker 部署指南
├── memory\                      # Claude Code 持久记忆（C:\Users\Kenry\.claude\...）
│   ├── MEMORY.md                # 记忆索引
│   ├── project-overview.md      # 项目概览
│   ├── current-status.md        # 最新完整状态（Phase 12.16）
│   ├── architecture.md          # 三层架构 + 23 路由 + 7 步管线
│   ├── tech-stack.md            # 实际技术栈
│   ├── api-constraints.md       # 外部 API 限额 + 缓存策略
│   ├── data-strategy.md         # 6 步数据管线
│   ├── data-integrity.md        # 🔴 铁律：严禁 AI 编造数据
│   └── task-breakdown.md        # 完整开发历程
├── backend\
│   ├── .env                      # 实际 Key（不提交 Git）
│   ├── .env.example              # Key 模板
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── docker-entrypoint.sh      # 自动重建 Chroma（向量库为空时）
│   ├── alembic.ini
│   ├── pytest.ini
│   ├── alembic\                  # 数据库迁移（3 个版本）
│   │   └── versions\
│   │       ├── ef9334ed713a_initial.py
│   │       ├── 6e4bd4265e11_make_session_id_nullable.py
│   │       └── 9f9b046b899e_add_itinerary_versions_phase8_3.py
│   ├── app\
│   │   ├── main.py               # FastAPI 入口，lifespan 中初始化 RAG + DB
│   │   ├── config\
│   │   │   └── settings.py       # pydantic-settings（环境变量读取）
│   │   ├── core\
│   │   │   └── __init__.py       # 核心工具
│   │   ├── database\
│   │   │   ├── connection.py     # SQLAlchemy async engine + session
│   │   │   └── models.py         # 11 张表 ORM 模型
│   │   ├── middleware\
│   │   │   └── __init__.py       # RequestIDMiddleware（纯 ASGI，非 BaseHTTPMiddleware）
│   │   ├── api\
│   │   │   ├── __init__.py       # 路由聚合（include_router × 9）
│   │   │   ├── health.py         # GET /api/v1/health（+ DB 状态）
│   │   │   ├── chat.py           # POST /api/v1/chat（SSE 流式）
│   │   │   ├── agent.py          # POST /agent/plan, /plan/stream, /plan/regenerate-day, /profile
│   │   │   ├── dialog.py         # POST /dialog/message, /dialog/generate（对话状态机）
│   │   │   ├── recommend.py      # POST /recommend, /recommend/quick
│   │   │   ├── weather.py        # GET /weather/{city}, /weather/cities, POST /weather/travel-advice
│   │   │   ├── image.py          # POST /image/analyze（Kimi 视觉）
│   │   │   ├── itineraries.py    # GET/POST/DELETE /itineraries（行程 CRUD + 版本）
│   │   │   ├── favorites.py      # GET/POST/DELETE /favorites
│   │   │   └── deps.py           # 依赖注入（get_db, get_current_user）
│   │   ├── agents\
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py        # 7 步 async 管线（自研，无 LangGraph 依赖）
│   │   │   ├── profile_agent.py       # NL → 结构化画像（DeepSeek structured output）
│   │   │   ├── trend_agent.py         # 热度分析（118+ 条趋势，4 策略模糊匹配）
│   │   │   ├── recommendation_agent.py # 7 因子加权打分（含 weather boost）
│   │   │   ├── planning_agent.py      # LLM 生成行程（DeepSeek + JSON Schema，最多 3 次重试）
│   │   │   ├── route_optimizer.py     # POI 存续校验 + 闭店替换 + 区域归位 + 近邻重排
│   │   │   ├── itinerary_contract.py  # Schema 校验 + 月份检测 + 天气覆盖 + 室内/室外分类
│   │   │   ├── dialog_manager.py      # 对话状态机（COLLECTING→CONFIRMING→GENERATING→DELIVERED）
│   │   │   ├── chat_agent.py          # 自由对话（非填槽）
│   │   │   └── vision_agent.py        # 图片分析 → 标签 + 地标特征
│   │   ├── services\
│   │   │   ├── llm_service.py              # BaseLLMProvider + DeepSeekProvider
│   │   │   ├── vision_service.py           # BaseVisionProvider + KimiVisionProvider
│   │   │   ├── amap_service.py             # 高德 POI + 路线 + 距离矩阵 + MD5 签名
│   │   │   ├── weather_service.py          # Open-Meteo 7 天预报 + 旅行评分
│   │   │   ├── session_store.py            # 会话持久化（Memory/Redis 双模，TTL 2h）
│   │   │   ├── cache_service.py            # 缓存管理（Redis/NoOp）
│   │   │   ├── user_service.py             # 匿名用户（device_id）
│   │   │   ├── favorite_service.py         # 收藏管理
│   │   │   ├── itinerary_service.py        # 行程 CRUD
│   │   │   ├── itinerary_version_service.py # 版本快照 + 恢复
│   │   │   ├── poi_health_service.py       # POI 存续巡检
│   │   │   ├── price_enricher.py           # 真实价格注入（区间价 + 来源时间戳）
│   │   │   └── name_normalizer.py          # POI 名称标准化
│   │   └── rag\
│   │       ├── __init__.py          # init_rag_from_data() 启动入口
│   │       ├── embedding.py         # TFIDFEmbeddingProvider + CompositeEmbeddingProvider
│   │       ├── vector_store.py      # ChromaStore 封装（PersistentClient）
│   │       ├── retriever.py         # 6 因子 RAG 检索（含 weather boost，Phase 12.16 核心）
│   │       └── landmark_matcher.py  # 地标二次匹配（图片识别辅助）
│   ├── scripts\
│   │   ├── fetch_wikidata.py         # Wikidata SPARQL（30 城市）
│   │   ├── enrich_wikipedia.py       # Wikipedia 摘要（wikimedia.org 绕过 GFW）
│   │   ├── enrich_amap.py            # 高德 POI 补充 + MD5 签名
│   │   ├── ai_enrich.py              # DeepSeek 批量标注（批次 25，max 2 并发）
│   │   ├── enrich_prices.py          # 价格注入（确定性，无 LLM）
│   │   ├── build_knowledge_base.py   # 合并 → TF-IDF 拟合 → Chroma 入库
│   │   ├── enrich_food_amap.py       # 高德美食 POI 采集（454+ 美食 POI）
│   ├── enrich_indoor_amap.py     # 高德室内 POI 采集（Phase 12.17，需 AMAP_API_KEY）
│   ├── fetch_indoor_osm.py       # OSM Overpass 室内 POI 采集（Phase 12.17，无需 Key）
│   ├── merge_indoor_pois.py      # 室内 POI 合并入 attractions.json（去重）
│   ├── indoor_coverage_report.py # 各城市室内 POI 覆盖率统计（确定性）
│   │   ├── enrich_social_trends.py   # 社交媒体热点采集
│   │   ├── enrich_search_trends.py   # 搜索趋势采集
│   │   ├── expand_cities.py          # 新城市批量添加
│   │   ├── add_missing_landmarks.py  # 手动地标补充（67 个）
│   │   ├── geocode_landmarks.py      # 地标地理编码
│   │   ├── poi_health_check.py       # POI 存续巡检（高德 API，5 并发限速）
│   │   ├── contract_regression.py    # 行程契约回归测试（真实 LLM 调用）
│   │   ├── smoke_test.py             # 全栈冒烟（零 LLM 成本）
│   │   ├── e2e_pages.py              # 浏览器 E2E
│   │   ├── test_dialog_scripts.py    # 对话流回归
│   │   ├── test_intent_slots.py      # 意图槽位测试
│   │   ├── test_vision.py            # 视觉识别测试
│   │   ├── eval_smart.py             # 增量智能评测（Phase 12.28a）🔧
│   │   ├── update_docs.py            # 自动文档更新（Phase 12.28a）🔧
│   │   ├── fixcycle.sh               # 一站式开发循环（Phase 12.28a）🔧
│   │   └── wb.py                     # WebBridge 工具
│   ├── tests\
│   │   ├── conftest.py
│   │   ├── test_recommendation_agent.py   # 6→7 因子评分 + 匿名化 bug 回归
│   │   ├── test_dialog_manager.py         # 对话状态机
│   │   ├── test_itinerary_contract.py     # 契约校验
│   │   ├── test_route_optimizer.py        # 路线优化
│   │   ├── test_price_enricher.py         # 价格注入
│   │   ├── test_name_normalizer.py        # 名称标准化
│   │   ├── test_planning_agent.py         # 行程生成
│   │   ├── test_session_store.py          # 会话存储
│   │   ├── test_cache_service.py          # 缓存服务
│   │   ├── test_favorite_service.py       # 收藏服务
│   │   ├── test_itinerary_service.py      # 行程服务
│   │   ├── test_itinerary_versioning.py   # 版本管理
│   │   ├── test_poi_health.py             # POI 健康
│   │   ├── test_refusal.py                # 拒绝策略
│   │   └── test_disturbance_replan.py    # 扰动重规划
│   ├── data\
│   │   ├── attractions.json          # 主知识库（1,788 POI，30 城市）
│   │   ├── trends.json               # 118+ 条趋势数据
│   │   ├── social_trends.json        # 社交媒体热点
│   │   ├── food_pois.json            # 美食 POI（454 条）
│   │   ├── tags.json                 # 51 个标签（6 大类）
│   │   ├── known_closures.json       # 已验证闭店/搬迁 POI
│   │   ├── poi_aliases.json          # POI 别名
│   │   └── fallback_trends.json      # 回退趋势数据
│   ├── evals\
│   │   ├── queries.json              # 63 条评测查询（7 分类）
│   │   ├── run_evals.py              # 评测执行器（三级指标，24 约束，确定性打分）
│   │   ├── __init__.py
│   │   └── results\                  # 历史评测结果（30+ 个 JSON 文件）
│   │       └── 2026-07-26-phase12_26-v1.json  # 最新基线
│   └── chroma_data\                  # Chroma 持久化向量库（2,057 文档，不提交 Git）
└── frontend\
    ├── package.json
    ├── vite.config.ts                # /api 代理 → localhost:8000
    ├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
    ├── index.html
    ├── Dockerfile
    ├── nginx.conf
    ├── .oxlintrc.json
    ├── public\
    ├── fixtures\
    │   └── itinerary.example.json    # 前端开发用示例数据
    └── src\
        ├── main.tsx
        ├── App.tsx                   # 6 条路由（含 MobileNav）
        ├── index.css                 # Tailwind v4
        ├── lib\
        │   ├── api.ts                # 完整类型化 API Client
        │   ├── deviceId.ts           # 匿名用户标识
        │   └── exportPdf.ts          # PDF 导出
        ├── hooks\
        │   └── usePlanStream.ts      # SSE 流式 Hook
        ├── types\
        │   └── itinerary.ts          # 行程类型定义
        ├── components\
        │   ├── SearchInput.tsx        # 首页搜索框
        │   ├── ExampleQuestions.tsx   # 示例问题
        │   ├── ChatBox.tsx            # 对话气泡
        │   ├── ChatInput.tsx          # 对话输入
        │   ├── IntentBar.tsx          # 槽位编辑
        │   ├── PlaceCard.tsx          # 景点推荐卡片（含可展开评分明细）
        │   ├── ScoreBar.tsx           # 6→7 因子评分可视化
        │   ├── DayCard.tsx            # 日程卡片
        │   ├── PriceBadge.tsx         # 价格标签
        │   ├── ValidationReportCard.tsx # 校验报告卡片
        │   ├── ImageUploader.tsx      # 图片上传
        │   ├── ErrorBoundary.tsx      # 错误边界
        │   ├── Skeleton.tsx           # 骨架屏
        │   ├── MobileNav.tsx          # 移动端导航
        │   └── Toast.tsx              # 提示
        └── pages\
            ├── HomePage.tsx           # 首页（系统自检 + 5 入口）
            ├── ChatPage.tsx           # AI 对话（SSE 流式）
            ├── RecommendPage.tsx      # 智能推荐（搜索 → 结果网格）
            ├── ItineraryPage.tsx      # 行程展示（天气 + 时间线 + 价格 + 校验报告）
            ├── ImagePage.tsx          # 图片识别 + 相似景点推荐
            └── HistoryPage.tsx        # 行程历史列表
```

---

## 4. 全部 API 路由（23 条，9 模块）

| Router | 方法 | 端点 | 用途 |
|--------|------|------|------|
| health | GET | `/api/v1/health` | 健康检查 + DB 状态 |
| chat | POST | `/api/v1/chat` | LLM 对话（SSE 流式） |
| agent | POST | `/api/v1/agent/plan` | 全管线生成行程（阻塞） |
| agent | POST | `/api/v1/agent/plan/stream` | 全管线生成行程（SSE 进度） |
| agent | POST | `/api/v1/agent/plan/regenerate-day` | 局部单日重生成 |
| agent | POST | `/api/v1/agent/profile` | 独立 Profile 提取 |
| recommend | POST | `/api/v1/recommend` | 完整推荐管线（Profile→Trend→RAG→Score） |
| recommend | POST | `/api/v1/recommend/quick` | 快速推荐（跳过 Profile 提取） |
| weather | GET | `/api/v1/weather/cities` | 已支持城市列表 |
| weather | GET | `/api/v1/weather/{city}` | 7 天预报 + 旅行评分 |
| weather | POST | `/api/v1/weather/travel-advice` | 旅行天气建议 |
| image | POST | `/api/v1/image/analyze` | Kimi 视觉分析（multipart） |
| dialog | POST | `/api/v1/dialog/message` | 多轮对话（槽位状态机） |
| dialog | POST | `/api/v1/dialog/generate` | 确认后触发生成 |
| itineraries | GET | `/api/v1/itineraries` | 用户行程列表（分页） |
| itineraries | GET | `/api/v1/itineraries/{id}` | 行程详情（含版本链） |
| itineraries | GET | `/api/v1/itineraries/{id}/versions` | 版本列表 |
| itineraries | GET | `/api/v1/itineraries/{id}/versions/{vid}` | 特定版本快照 |
| itineraries | POST | `/api/v1/itineraries/{id}/restore/{vid}` | 恢复到历史版本 |
| itineraries | DELETE | `/api/v1/itineraries/{id}` | 删除行程 |
| favorites | GET | `/api/v1/favorites` | 收藏列表 |
| favorites | POST | `/api/v1/favorites` | 添加收藏 |
| favorites | DELETE | `/api/v1/favorites/{id}` | 取消收藏 |

---

## 5. 核心架构决策

### 5.1 7 步 Agent 管线（orchestrator.py，自研 async，无 LangGraph）

```
User Input → [1] Profile Agent      → 提取目的地/预算/天数/标签/同伴/风格
           → [2] Trend Agent        → 热门景点 + 标签加权（118+ 条趋势）
           → [3] Weather Fetch      → Open-Meteo 7 天预报 + 旅行评分
           → [4] RAG Retrieval      → Chroma 向量检索（1075 维）+ 6 因子精排（含 weather boost）
           → [5] Recommendation     → 7 因子加权打分排序 + 过滤无效 POI
           → [6] Planning Agent     → LLM 生成结构化行程（DeepSeek × 最多 3 次重试）
                 ├─ route_optimizer  → POI 存续校验 + 闭店替换 + 区域归位 + 近邻重排
                 ├─ price_enricher   → KB 价格匹配 + 区间注入 + 过期检测
                 └─ itinerary_contract → Schema 校验 + 月份检测 + 天气覆盖检测
           → [7] Response Aggregator → 人类可读摘要 + TravelState 完整返回
```

- 每个节点包裹在 try/except 中，单点失败不中断管线
- 错误累积在 `state["error"]` 中，用分号分隔
- 所有 Agent 通过模块级 lazy import 加载，ImportError → stub skipping
- **重要：** Weather Fetch（Step 3）在 RAG Retrieval（Step 4）之前执行，实现天气感知检索

### 5.2 7 因子推荐打分公式（Phase 12.16 新增 weather）

```
Score = 0.35 × Preference_Match     (用户标签 vs 景点标签 Jaccard + 重叠率)
      + 0.25 × Trend_Heat           (热门度 + 标签匹配加成，上限 1.0)
      + 0.15 × Budget_Match         (三档匹配：经济/适中/高端，±1 档衰减)
      + 0.10 × Location_Efficiency  (高德距离矩阵，距离城中心评分)
      + 0.10 × Time_Match           (最佳游玩月份 vs 出行月份，±1 月衰减)
      + 0.05 × Data_Reliability     (数据源置信度 0.5-0.9)
      + weather_boost                (NEW: indoor +0.20×rain_ratio / outdoor -0.10×rain_ratio)
```

### 5.3 RAG 6 因子精排（Phase 12.16 新增 weather boost）

```
Relevance = 0.45 × Semantic_Similarity  (Chroma cosine → TF-IDF char n-gram)
          + 0.25 × Tag_Overlap          (Jaccard-like)
          + 0.15 × Popularity_Score     (1-10 标准化)
          + 0.10 × Budget_Match         (三档匹配)
          + 0.05 × Season_Match         (月份 ∩ best_time)
          + weather_boost                (NEW: 同推荐层逻辑)
```

### 5.4 天气感知双 Boost 架构（Phase 12.16 核心）

**rain_ratio 计算：**
- 每天判定雨天：weather_desc 含（雨/雷/雪/阵雨/暴雨），或 precipitation > 0.5mm，或 WMO code ≥ 50
- rain_ratio = 雨天 / 总预报天数
- rain_ratio < 0.2 时不生效（雨少不干扰正常排序）

**boost 公式：**
- indoor/semi POI → `+0.20 × rain_ratio`
- outdoor POI → `-0.10 × rain_ratio`

**双 boost 链：**
1. RAG retriever: `retrieve(profile, query, top_k, weather)` → `_rerank(rain_ratio)` → `_get_weather_boost(meta, rain_ratio)`
2. Recommender: `recommend(profile, candidates, trends, weather)` → inline rain_ratio + `classify_poi_indoor()`
3. Cache key 包含 rain_ratio：`f"rag:{city}:{tags_hash}:{budget}:{travel_style}:{travel_month}:{top_k}:w{rain_ratio:.1f}"`

**室内/室外分类：** `classify_poi_indoor()` 在 `itinerary_contract.py`，基于 KB 标签（40+ indoor / 30+ outdoor 关键词）+ 名称安全覆盖（80+ 模式）+ 正则兜底

### 5.5 对话状态机（Dialog Manager，Phase 12.25 重构）

```
COLLECTING → 城市缺失？→ suggest 组合卡（仅一次）
          → 城市 KB 外？→ suggest 建议 / refuse（覆盖校验优先）
          → days 缺失？→ ask 天数（仅一次）
          → 偏好缺失？→ ask 偏好（仅一次，"意图明确前不推卡片"）
          → 放权语（随便/你看着办）→ 跳过剩余追问
          → 齐全？→ CONFIRMING → 确认摘要（默认值明示）
                        → 用户确认 → GENERATING → 调用 Orchestrator
                                     → DELIVERED → 行程展示
提取接地校验（ground_extraction）：
  LLM 提取的 days/tags/同行/预算/节奏必须在用户原文有字面/同义线索，
  否则丢弃——杜绝 LLM"默认猜测"造成槽位假满（对话链路专用）。
修改分流（DELIVERED 后）：
  "第二天改成动物园" → local (单日重生成)
  "预算改为经济"     → slot_change (槽位更新 → 全网重生成)
  "整体节奏慢一点"   → global (全网重生成)
```

### 5.6 嵌入方案（无 GPU，纯 Python）

- **TF-IDF**（sklearn TfidfVectorizer, char_wb, ngram 2-4, max_features=1024）
- **Tag One-Hot**（51 维）
- **Composite** = TF-IDF(70%) + Tag(30%) = **1075 维**
- 原因：PyTorch 在 Windows 上 fbgemm.dll 损坏，DeepSeek 无 embeddings API

### 5.7 高德 API 签名

```python
def _amap_sign(params: dict, sign_key: str) -> str:
    sorted_keys = sorted(params.keys())
    raw = "&".join(f"{k}={params[k]}" for k in sorted_keys)
    raw += sign_key
    return hashlib.md5(raw.encode("utf-8")).hexdigest()
```

### 5.8 Wikipedia GFW 绕过

- `zh.wikipedia.org` 被 TLS 干扰
- 解决：使用 `wikimedia.org/api/rest_v1/` 作为 base URL，设 `Host: zh.wikipedia.org` header
- 如果失效 → 跳过 Wikipedia，直接用 DeepSeek AI 标注

---

## 6. 数据现状

### 6.1 景点知识库（attractions.json）

- **2,321 POI / 30 城市**（含美食 POI + 手动补充地标 + OSM 室内/美食/住宿 POI + 社交验证 POI；Phase 12.27 上海美食 9 类、室内覆盖全部 ≥35%、住宿 169 条、深圳香港污染已清洗 -16）
- `name_normalized` 覆盖率 **100%**
- 全部 AI 标注（tags, suitable_for, best_time, price_level, popularity_score）；OSM 补充条目带 `osm_id` 可追溯、`rating: null`（OSM 无评分数据）
- 每条有 `_validate_enrichment()` 服务端校验
- Chroma 向量库：持久化在 `backend/chroma_data/`；**KB 变更后必须 `bash scripts/backend_restart.sh --rebuild` 重建才生效**
- 室内覆盖率：30 城市全部 ≥35%（拉萨 35.7%、香格里拉 49.0%，Phase 12.22 低覆盖清零）
- 社交候选 143+16 条已全部验证有去向（27 条真实已在库、114 条 OSM 未找到、2 条泛称），报告存 `data/social_poi_verify_report.json`；国家海洋博物馆等个别真实 POI 待高德渠道验证

**⚠️ 注意：`attractions.json` 是 dict 格式 `{"attractions": [...]}`，不是直接 list！访问时需 `json.load(f)['attractions']`**

### 6.2 天气覆盖

- 30 城市全部支持 Open-Meteo 7 天预报
- 城市别名：35 组（如"魔都"→"上海"，"山城"→"重庆"）
- 天气覆盖检测：`weather_coverage` 约束 100%

### 6.3 辅助数据文件

| 文件 | 内容 | 来源 |
|------|------|------|
| `data/tags.json` | 51 个标签 / 6 大类 | 人工整理 |
| `data/trends.json` | 118+ 条趋势数据（30 城市） | 人工整理（携程/马蜂窝/小红书/抖音热榜） |
| `data/social_trends.json` | 社交媒体热点（仅可验证数据） | 真实新闻引用 |
| `data/food_pois.json` | 美食 POI（454 条） | 高德 API |
| `data/known_closures.json` | 已验证关闭/搬迁 POI | 人工验证 |
| `data/poi_aliases.json` | POI 别名 | 人工整理 |
| `data/poi_health_*.json` | POI 健康巡检报告 | `scripts/poi_health_check.py` 定时生成 |
| `data/indoor_osm.json` | OSM 室内 POI（269 条，带 osm_id） | `scripts/fetch_indoor_osm.py`（Overpass API） |
| `data/indoor_coverage_report.json` | 各城市室内覆盖率报告 | `scripts/indoor_coverage_report.py` |

---

## 7. 环境变量（.env）

```bash
# ===== 必填 =====
DEEPSEEK_API_KEY=sk-xxx           # DeepSeek 主 LLM（对话/规划）
MOONSHOT_API_KEY=sk-xxx           # Kimi 开放平台（图片识别）
AMAP_API_KEY=xxx                  # 高德 POI + 路线
AMAP_SIGN_KEY=xxx                 # 高德数字签名（可选，控制台开启后必填）

# ===== 可选（按需） =====
LLM_PROVIDER=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
VISION_PROVIDER=kimi
MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
VISION_MODEL=kimi-k2.6
VISION_TIMEOUT=60
OPEN_METEO_BASE_URL=https://api.open-meteo.com
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/travelmind_db
DATABASE_URL_SYNC=postgresql://postgres:postgres@localhost:5432/travelmind_db
SESSION_STORE=memory              # memory | redis
REDIS_URL=redis://localhost:6379/0
CHROMA_PERSIST_DIR=./chroma_data
APP_ENV=development
APP_DEBUG=true
APP_HOST=0.0.0.0
APP_PORT=8000
```

**当前 backend/.env 中已配置的 Key：** DEEPSEEK_API_KEY ✅ / MOONSHOT_API_KEY ✅ / AMAP_API_KEY ❌（为空，2026-07-25 发现；路线/POI 相关高德调用当前不可用）/ AMAP_SIGN_KEY ✅

**Phase 12.17 新增数据源：** OpenStreetMap Overpass API（ODbL，无需 Key，`scripts/fetch_indoor_osm.py`）——Wikidata 被 GFW 阻断、高德 Key 缺失时的室内 POI 来源。

---

## 8. 关键坑位 & 经验（全部已验证）

### 已解决的坑
1. **Chroma 批量插入限制**：batch_size 不能超过 166，设为 150
2. **Chroma 遥测噪音**：`ANONYMIZED_TELEMETRY=False` 无法完全消除，SDK 版本 bug，不影响功能
3. **高德 API 签名**：必须在控制台开启数字签名，否则 INVALID_USER_SIGNATURE
4. **SSE 流式**：不能用 `BaseHTTPMiddleware`（会缓冲响应），必须用纯 ASGI middleware
5. **PyTorch Windows**：fbgemm.dll 损坏，放弃 PyTorch，用 sklearn TF-IDF 替代
6. **Wikipedia GFW**：TLS 干扰，用 wikimedia.org 作为代理
7. **Planning Agent 空响应**：加了 retry（最多 3 次）
8. **DB 启动超时**：从 5s 降到 2s，避免离线开发时卡住
9. **`attractions.json` 格式**：是 `{"attractions": [...]}` dict，不是直接 list
10. **Edit 工具中文匹配**：Unicode 字符可能导致编辑匹配失败，可用 Python 脚本替代
11. **评测被中断**：后端 kill 会导致 eval 中所有 query 返回 "Server disconnected"，需重启后端重跑
12. **uvicorn 无 --reload**：改了后端代码必须重启才生效（用 `bash scripts/backend_restart.sh`）
13. **评测参数**：是 `--category standard` 不是 `--tags`；结果文件绝不覆盖历史，每次新文件名
14. **provider 配额 403**：偶发中断（子代理/评测进程被杀），重跑即可恢复，不是代码问题
15. **eval_compare.py**：per_constraint 的键是 `pass/total/rate` 不是 `passed`
16. **Docker 旧容器抢端口**：`docker compose up` 启动的 backend（8000）/frontend（5173）容器是旧镜像/旧 dist，会与本地 uvicorn/vite 同时监听同一端口，请求被随机路由到旧代码——**跑评测或体验前必须 `netstat -ano | grep :8000` 确认只有一个监听者**，否则 `docker stop travelmindagent-backend-1 travelmindagent-frontend-1`（Phase 12.21 实测踩坑：chat 评测一度"全面恶化"实为旧容器答的）
16. **/dialog/message 请求字段**：是 `text` 不是 `message`；前端行程保存走 `X-Device-ID` header
17. **社交采集（WebBridge）**：需用户浏览器在线 + daemon 运行（`~/.kimi-webbridge/bin/kimi-webbridge.exe start`）；XHS 正文页被反爬只有搜索页可用；抖音选择器 `div[class*="search-result-card"]`；Windows 中文请求体用 `--data-binary @file`（文件须 UTF-8）

### 待注意的坑
- DeepSeek API 偶发超时（30-90s），planning agent 已有 retry
- LLM 非确定性：chat/multi-city 分类评测有 ±20pp 波动，多次运行取均值
- Windows GBK 终端编码问题，不影响功能
- 前端端口 5173，后端 8000，Vite 已配置 proxy
- 后端启动后需等 RAG 初始化完成（~10-30s），日志可见 `Chroma 向量库加载完成`

---

## 9. Phase 12.17 → 12.27 完整变更（最新，2026-07-26）

> Phase 12.16 及更早的完整记录见 `docs/BASELINE.md`。

### Phase 12.27（行程三缺口，✅ 已收尾——2026-07-27 Claude Code）

**用户需求（2026-07-26 原话）："行程规划只会推荐景点，吃住都没有推荐；行程很密集；想去掉不想去的行程无法直接更改"。**

#### 全部完成（pytest 349 全过、前端 build/oxlint 0 错误、全量评测 63/63）

1. **节奏分档（②缺口）**
   - `itinerary_contract.enforce_pace_density(data, pace)`：休闲/慢→每天≤4、适中→≤5、紧凑/特种兵→≤6，保序截断；在 planning_agent 路线优化前调用
   - planning prompt（planning_agent.py `_QUALITY_REQUIREMENTS` 第 3 条）同步改为分档表述
   - 测试：`TestPaceDensity` ×4（tests/test_itinerary_contract.py）

2. **单项删改（③缺口）**
   - 后端：`dialog_manager.try_remove_item(itinerary, text)`——触发词（去掉/删掉/不去/别去/取消…）+ 双变体匹配（_normalize + _core_name），最长匹配优先；空天保护（当天仅剩 1 项时拒删并提示重排）；删后 `inject_computed_fields` 重算 stats；已接入 dialog.py `_handle_modification` 最优先位置（零 LLM）
   - 前端：DayCard 行程项 hover 显示 × 删除按钮（`onRemoveItem` prop），ItineraryPage `handleRemoveItem` 本地删除 + 重算地点数 + 写回 sessionStorage + toast
   - 测试：`TestTryRemoveItem` ×5；dialog_scenarios 新增 S5.1b（28/28 全绿）

3. **吃住真实推荐（①缺口）**
   - `itinerary_contract.attach_daily_dining_and_stay(data, kb, city)`：按天挂载 KB 真实餐厅（午餐热度最高、晚餐与午餐品类错开、跨天不重复、排除行程已出现项）+ 住宿（tags 含「住宿」，每天 1 个）；KB 不足时保留 LLM 原 eat
   - **schema 演进**：`docs/itinerary.schema.json` day 新增可选 `stay` 字段；前端类型用 `npm run gen:types` 重新生成（注意：重新生成后 price_summary 字段变可选，ItineraryPage 已加 `as PriceSummary` 断言兼容）
   - **住宿数据**：新脚本 `scripts/fetch_hotels_osm.py`（OSM tourism=hotel/guest_house/hostel，30 城），采 174 条→清洗（去 SPA 等误标）169 条→合并→KB 2168→**2337**→Chroma 已重建
   - DayCard：「每日一味」改「今日餐饮」+ 新增「建议住宿」行（day.stay 存在时）
   - 测试：`TestAttachDiningStay` ×4；离线实测上海/厦门挂载正确（真实餐厅+真实酒店）

#### ✅ 已修缺陷（2026-07-27 Claude Code 收尾）

**q21（深圳2日科技都市游）Chroma HNSW 错误——已修复：**
- 根因：Chroma collection 重建后 HNSW 默认参数与较大 top_k 不匹配，`search()` 静默返回 `[]`
- 修复 1：`vector_store.connect()` 创建/更新 collection 时设置 `hnsw:search_ef=200`
- 修复 2：`vector_store.search()` 新增 HNSW 错误重试（逐步减小 n_results） + 三重试后 log error（不再静默）
- 验证：q21 返回 2 天 9 项行程 + 20 候选，正常

**深圳香港数据污染——已清洗：**
- `attractions.json` 移除 16 条香港越界 POI（2337→2321）
- `build_kb.py` normalize 阶段集成 `_CITY_COORD_BOUNDS` 坐标边界校验，防止未来污染
- 清洗后重建 KB（2321 POI），评测满分 63/63

#### 收尾清单（全部完成 ✅）
1. ✅ 修 q21 Chroma 错误 + 深圳香港污染清洗 → KB 重建（2321 POI）
2. ✅ 全量评测 63/63 Micro 100% / Macro 100%（存档 `2026-07-27-phase12_27-v1.json`）
3. ✅ 截图走查前端 6 页（`ui_walkthrough.py`，桌面版全部通过）
4. ✅ `docs/BASELINE.md` 已补 Phase 12.27 节

### Phase 12.26（测试体系升级：真实场景可信 + 重复工作脚本化）
- **`scripts/dialog_scenarios.py`**：9 剧本 27 项确定性断言（零 LLM 评判）——模糊收敛/KB 外恢复/中途改主意/放权流/生成后修改/一轮确认/重复幂等/生成中留言排队/9 类对抗输入（空/长文/emoji/英文/injection/SQL/乱码）。全绿；对抗测试证明系统鲁棒（LLM 自然化解注入与越界请求），零代码修复
- **`scripts/ui_walkthrough.py`**：WebBridge 一键 6 页桌面 + iframe 390px 移动截图（`docs/images/walkthrough/`），单页失败不阻断
- 两个脚本登记进 `skills/travelmind-test`（§5/§6），SKILL.md 过期描述同步修正
- 验收：e2e 5/5、冒烟 5/5、全量评测 Macro 100%（phase12_26-v1）

### Phase 12.25（对话收敛策略重构：意图明确前不推卡片）
- **用户场景根因（两层）**：①旧 `required_missing` 只查 city/days，tags/预算/同行静默默认；②`extract_profile` 对用户没说的信息返回"默认猜测"（"我想去惠州玩"→ days=3、tags=["休闲","自然"]），槽位假满直接 confirming
- **修复 1**：`dialog_manager.ground_extraction()` 提取接地校验——LLM 提取的 days/tags/同行/预算/节奏必须在用户原文有字面或同义线索，否则丢弃（对话链路专用；/agent/plan 单发规划不受影响）
- **修复 2**：`next_action(state, text)` 重构——city→days→偏好逐槽位自然追问，每槽位最多问一次（`state["asked"]` 标记）；放权语（"随便/你看着办/都可以"）跳过剩余追问用默认值+明示；城市覆盖校验提前
- **测试**：pytest 327→336（+9：next_action 新行为 3 + ground_extraction 6）；`test_dialog_scripts.py` S1 更新为"城市+天数→追问偏好→回答→确认"，10/10 通过
- **实测用户场景**：惠州（覆盖提示）→南宁（追问天数）→3天（追问偏好）→美食/古镇（确认）；放权语→默认值确认
- 验收：全量评测 **Macro 100%**（phase12_25-v1）、e2e 5/5、冒烟 5/5

### Phase 12.24（前端惊艳级升级 + 对话生成 SSE 真实进度）
- **视觉 2.0**（index.css）：动态极光背景 `.aurora`（3 块渐变色漂移，纯 transform GPU 动画）+ 弱化版 `.aurora-soft`（工作页）+ 颗粒纹理 `.grain` + display 字体层级 + `.stagger` 交错入场 + `.card-glow`/`.focus-glow` 微交互 + `prefers-reduced-motion` 可达性；已应用到全部 6 页
- **新端点 `POST /api/v1/dialog/generate/stream`**：与 /agent/plan/stream 同一事件源（orchestrator `run_travel_workflow_stream`）的真实阶段进度；会话状态机与自动保存逻辑与阻塞式一致（auto-save 抽取为 `_auto_save_itinerary` 共用）
- **ChatPage**：生成过程从 spinner 升级为 6 阶段进度卡（绿勾/转圈/实时 message），SSE 失败自动回退阻塞式接口
- **DayCard**：贯通式时间轴（脊柱线 + 节点 + 时刻列 + 内容卡）+ 日程渐变横幅
- **移动端**：iframe 390px 模拟视口走查法（WebBridge 无视口模拟时的替代方案），3 个关键页无溢出
- 验收：build/oxlint 0 错误、e2e 5/5、冒烟 5/5、全量评测 **Macro 100%**（后端改动后复测，存档 phase12_24-v1）
- **注意**：vite dev 后台任务不要用 `| head` 截断输出（SIGPIPE 会杀掉 vite）

### Phase 12.23（前端年轻化改版，纯 frontend/，后端零改动）
- **HomePage**：接入此前造好但未使用的 `ExampleQuestions` 示例问题卡片（一句话直接进入对话规划）；首屏间距紧凑化
- **ChatBox**：空状态改为"AI 先开口"的欢迎泡泡（"嗨，我是小旅 👋 你的旅行搭子～"）+ 4 张可点开场卡片（新增可选 prop `onStarterSelect`，ChatPage 传入 sendText）
- **RecommendPage**：空状态 emoji 卡片化，点击示例直接搜索（抽出 `runSearch`，少一步操作）
- **HistoryPage**：修复空状态 CTA 与底部固定操作栏重复（底部栏仅在列表非空时渲染）
- **e2e_pages.py**：行程页断言从已下线的 fixture 预览更新为空状态断言（产品代码此前已移除 fixture 路径，属测试维护非产品改动）；ItineraryPage 过期 docstring 同步
- 验收：`npm run build` 0 错误、oxlint 0 错误、e2e_pages 5/5、smoke_test 5/5；6 页 before/after 截图走查（`docs/images/before_*.jpeg` / `after_*.jpeg`）
- **环境注意**：本地开发前需 `docker stop travelmindagent-frontend-1`（旧 dist 容器占 5173）；vite dev 以后台任务运行

### Phase 12.22（知识库扩展 + 管线容错加固，评测满分保持）
- KB 2,114 → **2,168 POI**：上海 +40 OSM 美食（新脚本 `fetch_food_osm.py`，类型 3→9 类）、香格里拉 +14 OSM 美食/咖啡（室内覆盖 28.6%→49.0%，低覆盖城市清零）
- 143+16 条社交候选全部分块验证：27 条真实但已在库、114 条 OSM 未找到、2 条泛称；0 条新增（印证 OSM 扩充已覆盖真实 POI，社交价值在热度信号）
- `social_trends_live.json` 12 条实时热度（WebBridge 小红书采集）
- **verify_merge_social_pois.py 加固**：504 fail-fast（`OverpassUnavailable` 单城跳过+幂等补跑）、三镜像轮换、±0.8° 宽 bbox 二轮、`--cities` 分块、报告按城市增量合并
- `build_kb.py` 单入口新增 fetch-food-osm / merge-food 阶段
- 评测复测 Micro/Macro 100% 零劣化（`2026-07-26-phase12_22-v1.json`）

### Phase 12.21（8 条失败 query 根因修复，评测满分）
- **Micro 100% / Macro 100%（63/63）**，24 项约束全部满分，7 分类全部满分
- 修复明细与根因论证见 `docs/BASELINE.md` Phase 12.21 节：
  - weather_fit：守卫与评估器 KB 查找键口径统一（`_build_kb_tag_lookups`/`_lookup_kb_tags`，itinerary_contract.py）
  - route_ok：`_rebalance_days_geographically()` 跨天地理再平衡（route_optimizer.py）
  - min_score_filter：`_diversity_penalty` 嵌套结构取名修复 + 跨城 `_multi_city` location 中性化
  - food_diversity：`_refine_food_tags()` 运行时细分类型推导 + `_supplement_food_diversity()` 确定性候选保底（新增 `ChromaStore.get_by_metadata`）
  - chat：评测标记表语义修正（特征串替换泛化词）+ chat_agent prompt 补自然对话原则
- 单测 310 → **327**（+17 回归测试）
- **环境坑位：Docker 旧后端容器（travelmindagent-backend-1）与本地 uvicorn 同抢 8000 端口**，请求被随机路由到旧代码——跑评测前必须 `netstat -ano | grep :8000` 确认只有一个监听者；5173 的 Docker nginx 同理是旧 dist

### Phase 12.17–12.19（天气/数据/管线）
- **prompt 雨天分级 + 恶劣天气确定性替换**：`enforce_severe_weather_indoor()` 于 `backend/app/agents/itinerary_contract.py`
- **OSM 室内 POI 扩充**：KB 扩至 2,114 条 / 30 城
- **multi-city 修复**：trend 加载 + 相关过滤 + top20
- **数据全流程管线**（采集→验证→合并→重建→质检）：
  - `scripts/build_kb.py` — 单入口 7 阶段
  - `scripts/collect_social_webbridge.py` — 小红书/抖音采集（WebBridge）
  - `scripts/verify_merge_social_pois.py` — OSM 验证合并（匹配规则：标准化相等，或候选名≥4字符⊆OSM名 + 泛称黑名单——两次数据污染复盘后的最终版）
  - `scripts/data_quality_report.py` — 数据质检
- 结果：Macro 85.7%（`2026-07-25-phase12_19-v1.json`）

### Phase 12.20（对话/推荐/保存三链路）
- **对话自然化**：`backend/app/api/dialog.py` 新增 `_naturalize_reply()`——状态机定动作、LLM 定语气（temperature=0.9，失败回退模板），解决"AI 只会重复追问槽位"的体验问题
- **推荐修复**：洪崖洞补录进 KB；`recommendation_agent.py` 餐厅名不再抑制地标趋势；`recommend.py` per-tag 候选池补充 + `_ensure_intent_coverage()`，解决"夜景+美食只推荐美食"问题
- **行程保存**：`backend/app/services/local_itinerary_store.py`——PG 断连时文件型回退，存 `backend/data/user_itineraries/{device_id}/`（device_id 经消毒）；已接入 `agent.py`/`dialog.py` auto-save 和 `itineraries.py` list/detail/delete
- 结果：**Micro 98.4% / Macro 87.3%（55/63）/ weather_fit 92.5%（37/40）/ poi_verified 100%**（历史最高）
- 分类明细：standard 27/30 · food 9/10 · chat 3/5 · multi-city 3/5 · edge 5/5 · extreme 5/5 · image-tag 3/3

### 工程化（skill 化，2026-07-26）
- 脚本：`scripts/backend_restart.sh [--rebuild]`、`scripts/full_verify.sh`（pytest+build+oxlint+冒烟，零 LLM 成本）、`scripts/eval_compare.py <基线> <新跑>`
- 技能：`skills/travelmind-devcycle`、`travelmind-eval`、`travelmind-data` + 既有 `travelmind-test`
- 原则：脚本能跑的绝不调模型，冒烟/E2E 零 LLM 成本

---

## 10. 已知遗留 & 下一轮优化方向

### 已知遗留（非阻塞，均已记录）
- 天津国家海洋博物馆等个别真实 POI 因 OSM 名称/覆盖问题未过验证，留档 `data/social_poi_verify_report.json`，待高德渠道恢复后走高德验证
- `backend/.env` 的 `AMAP_API_KEY=` 为空——用户填入后可恢复 POI 存续巡检和高德采集（`enrich_indoor_amap.py` 已就绪）
- Docker 前端容器（5173 nginx）是旧 dist，用户若在浏览器体验需先重建或改用本地 vite
- Overpass 公共实例白天 504/429 高发：管线已做三镜像+退避，重跑验证类任务建议错峰或用 `--cities` 分块

### 下一轮方向（按优先级，均已初步根因摸底）

1. **行程"吃住+节奏+可删改"三缺口**（用户 2026-07-26 提出，下一个 goal，建议直接复制创建）
   - **吃住推荐缺失**：行程只有景点；`day.eat`（每日一味）是 LLM 文本而非 KB 真实餐厅；无住宿推荐。思路：确定性后处理——按天从 KB 美食 POI（454+54 条）就近挂载午/晚餐（复用 `_refine_food_tags` 品类多样性），住宿先从 OSM `tourism=hotel` 采集（新查询类型，参考 `fetch_indoor_osm.py` 模式）再挂载；评测新增 meal_coverage/hotel_present 约束（属增强，写理由）
   - **行程太密集**：planning prompt 现为"每天 3-6 个条目"（planning_agent.py:361），实测 17 项/3 天偏赶。思路：按 pace 分档上限（休闲≤4 / 适中≤5 / 紧凑≤6）改 prompt + `itinerary_contract` 校验兜底；注意 stats_place_count 是动态计算不受数量影响
   - **单项删改**：`dialog_manager.py:450` 已有 `不去|换成|删[掉除]|加[上一个]` 模式但走 LLM 重生成；用户要的是"直接去掉"。思路：delivered 态"去掉/不去 XX"→ 确定性删除该 item（匹配 KB 名后从 day.items 移除 + 重算 stats，零 LLM）+ 前端行程项加删除按钮（调修改接口或本地态+重存）
2. **社交采集扩品类**：抖音/大众点评适配（中期路线，见 DATA_PIPELINE.md）；XHS 正文页被反爬，只有搜索页可用
3. **高德渠道恢复**：用户填 `AMAP_API_KEY` 后跑 `enrich_indoor_amap.py` + `poi_health_check.py` + 国家海洋博物馆等待验证 POI
4. **定时巡检**：kimi 会话内已挂每天 09:23 跑 dialog_scenarios --skip-generate（id b770a48e，仅 kimi 会话存活时触发；Claude Code 接手后如需请自行重建等价定时任务）
5. **评测稳定性**：满分基线下每次改动后跑全量评测防回退（LLM/天气波动）

---

## 11. 启动命令

```bash
# ===== 开发模式 =====

# 后端（在 backend/ 目录下）
cd D:\TravelMindAgent\backend
pip install -r requirements.txt
cp .env.example .env   # 填入 DEEPSEEK_API_KEY / MOONSHOT_API_KEY / AMAP_API_KEY(+AMAP_SIGN_KEY)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# （不用 --reload；改代码后用 bash scripts/backend_restart.sh 重启）
# 等待日志显示 "Chroma 向量库加载完成"

# 前端（在 frontend/ 目录下，另一个终端）
cd D:\TravelMindAgent\frontend
npm install
npm run dev
# 访问 http://localhost:5173

# Windows 可双击根目录 start-dev.bat 一键启动

# ===== Docker 部署 =====
docker compose up --build -d
# 可选 PostgreSQL：docker compose --profile db up -d

# ===== 测试 =====
cd backend && python -m pytest                    # 327 测试，~12s（无外部调用）
cd backend && python -m pytest --cov=app --cov-report=term  # 含覆盖率

# ===== 评测 =====
cd backend && python -X utf8 -m evals.run_evals   # 全量 63 query，需后端在线，约 8-12 分钟
cd backend && python -X utf8 -m evals.run_evals --limit 5  # 快速冒烟（5 条）

# ===== 前端检查 =====
cd frontend && npm run build                      # TypeScript 严格模式，0 错误
cd frontend && npx oxlint                        # Lint 检查

# ===== 数据巡检 =====
cd backend && python scripts/poi_health_check.py  # POI 存续验证（高德 API，约 15-30 分钟）

# ===== 全栈冒烟 =====
cd backend && python scripts/smoke_test.py        # 零 LLM 成本
cd backend && python scripts/contract_regression.py  # 含真实 LLM 调用
```

---

## 12. 评测体系

### 指标定义
- **Micro**：所有 (63 query × 24 约束) 单元格的通过比例
- **Macro = Final Pass Rate**：单条 query 内全部约束通过才算通过的比例

### 7 个分类（63 条 query）
| 分类 | 数量 | 说明 |
|------|------|------|
| standard | 30 | 标准旅行规划（核心分类） |
| food | 10 | 纯美食推荐 |
| chat | 5 | 自由对话（非填槽） |
| multi-city | 5 | 跨城市模糊查询 |
| extreme | 5 | 极限预算/极长时间/多人团队 |
| edge | 5 | 边界场景 |
| image-tag | 3 | 图片标签推荐 |

### 24 项约束（确定性代码打分，不用 LLM 当评委）
- 契约层 9 项：schema_valid, days_correct, stats_place_count, budget_consistent, month_consistent 等
- 内容层 7 项：poi_verified, route_ok, weather_fit, weather_coverage, weather_tips, price_enriched, name_normalized
- 美食 3 项：food_coverage, food_diversity, food_local_ratio
- 对话 3 项：chat_reply_length, chat_topic_relevant, chat_not_slotfill
- 图片 3 项：image_tag_relevance, image_tag_cross_city, image_tag_threshold
- 多城 3 项：cross_city_covered, multi_city_diversity, min_score_filter

### 评测结果文件命名
- 格式：`backend/evals/results/YYYY-MM-DD-phaseXX_XX-vN.json`
- 最新基线：`2026-07-26-phase12_26-v1.json`
- 不要覆盖历史结果，每次用新的文件名

---

## 13. 🔴 数据完整性铁律

**绝对禁止 AI 编写或估算任何数据。** 每一条数据必须能追溯到真实来源。

1. 所有数值必须来自真实数据源（Amap API、Open-Meteo、WebSearch 引用），不得 AI 估算
2. 数据文件必须标注来源，无法获取真实数据时留空或标记 `null`
3. 评测/测试中的期望值必须基于真实数据或明确需求规格
4. 每次添加/修改数据时自问"这个值从哪里来？"

详见 `memory/data-integrity.md`

---

## 14. 给接手 AI（Kimi Code / Claude Code）的操作指南

### 第一天：跑通系统

```bash
# 1. 确认环境
python --version   # 需要 3.11+
node --version     # 需要 18+

# 2. 启动后端
cd D:\TravelMindAgent\backend
pip install -r requirements.txt
# 确认 .env 中 Key 可用
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# 等待 "Chroma 向量库加载完成"

# 3. 另一个终端，启动前端
cd D:\TravelMindAgent\frontend
npm install
npm run dev

# 4. 验证
curl http://localhost:8000/api/v1/health
# 浏览器打开 http://localhost:5173
# 点击「检测后端连接」确认联通
```

### 第二天：了解代码

1. **先读** `docs/BASELINE.md` — 了解所有 Phase 的评测演进
2. **再读** `memory/current-status.md` — 了解当前瓶颈和下一步方向
3. **跑一次测试**：`cd backend && python -m pytest`（应 327 passed, 0 failed）
4. **快速评测冒烟**：`cd backend && python -X utf8 -m evals.run_evals --limit 5`
5. **浏览核心代码路径**：
   - `orchestrator.py` → 理解 7 步管线
   - `retriever.py` → 理解 RAG + weather boost
   - `recommendation_agent.py` → 理解 7 因子打分
   - `planning_agent.py` → 理解 LLM 行程生成
   - `dialog_manager.py` → 理解对话状态机

### 第三天开始：继续优化

**立即可做的：** 按 §10「下一轮方向」优先级逐项推进；每完成一轮就回到本文档更新当前状态小节。

**提交检查清单：**
- [ ] `cd backend && python -m pytest` — 全量通过
- [ ] `cd frontend && npm run build` — TypeScript 0 错误
- [ ] 如果改了数据/评分逻辑 → `cd backend && python -X utf8 -m evals.run_evals` — 基线不劣化
- [ ] 更新 `docs/BASELINE.md` 和**本文档的当前状态小节**（头部快照/§1/§6/§9/§10/§12 —— 维护约定见头部，这是 Claude Code 等接手方的唯一真相来源）
- [ ] `git add` + `git commit`（遵循现有 commit 风格：`feat(phaseXX): 中文描述`）

### 常见操作速查

```bash
# 重启后端（改了后端代码必须重启；--rebuild 同时重建 Chroma）
cd backend && bash scripts/backend_restart.sh [--rebuild]

# 提交前全量验证（pytest + build + oxlint + 冒烟，零 LLM 成本）
cd backend && bash scripts/full_verify.sh

# 评测结果对比（基线 vs 新跑，零 LLM 成本）
cd backend && python -X utf8 scripts/eval_compare.py <基线.json> <新跑.json>

# 只跑 weather_fit 相关的评测（快速迭代）
cd backend && python -X utf8 -m evals.run_evals --category standard
```

**项目级技能（skills/ 目录）：**
- `travelmind-devcycle` — 后端重启/重建/全量验证循环
- `travelmind-eval` — 评测执行与基线对比（含判定参考与文件命名铁律）
- `travelmind-data` — 数据管线（覆盖率→采集→验证→合并→重建→质检 + 数据污染复盘教训）
- `travelmind-test` — 冒烟/契约回归/浏览器 E2E（既有）

---

**文档结束。祝接手开发顺利！🚀**
