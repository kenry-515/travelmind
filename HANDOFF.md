# 羊城智游 - 广州 AI 旅游智能体 接手文档

> 项目已专注广州地区 AI+旅游休闲大赛场景，所有全国通用功能已下线
> 最后更新: 2026-07-31（Phase 18 M5）

## 📌 项目概述

**羊城智游** 是一个面向 "AI+旅游休闲" 大赛的 **广州专属** AI 旅行规划智能体，支持：

- 多轮对话式行程规划（基于 DeepSeek v4-flash LLM）
- AI 虚拟导游讲解（基于 Kimi k2.6 视觉）
- 景区资源调度与错峰建议（168+ 广州景区）
- 拍照识景功能（Kimi 视觉反查广州 POI）
- 174 个广州 POI + 7 个行政区全覆盖

## 🏗️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19 + TypeScript + Vite 8 + Tailwind CSS v4 + Playwright E2E |
| 后端 | FastAPI + Python 3.11 + uvicorn |
| LLM | DeepSeek v4-flash（聊天 + 结构化输出） |
| 视觉 | Kimi k2.6（图片识景） |
| 数据 | Chroma RAG + 174 POI + 168 Chroma docs + TF-IDF 兜底 |
| 测试 | pytest 672 个（单元+集成+API+失败降级+边界+安全） |
| E2E | Playwright 28 个测试覆盖 8 个页面 + 错误展示 |
| 部署 | Docker Compose（postgres + redis + backend + frontend） |

## 📁 项目结构

```
TravelMindAgent/
├── backend/                       # 后端服务
│   ├── app/
│   │   ├── agents/                # 13 个 Agent 模块
│   │   │   ├── chat_agent.py           # 简单聊天
│   │   │   ├── dialog_manager.py       # 对话状态机（已加固：广州专属槽位/拒答/追问）
│   │   │   ├── guide_agent.py          # 虚拟导游（讲解 + 追问）
│   │   │   ├── orchestrator.py         # 7 步管线编排 + SSE 流
│   │   │   ├── planning_agent.py       # 行程生成（含 _call_llm fallback）
│   │   │   ├── profile_agent.py        # 用户画像提取
│   │   │   ├── resources_agent.py      # 资源调度启发式
│   │   │   ├── route_optimizer.py      # 路线优化 + closures 加载
│   │   │   ├── time_aware_planner.py   # 时间感知
│   │   │   ├── recommendation_agent.py  # 6 因子打分
│   │   │   ├── vision_agent.py         # 图片 → POI 反查
│   │   │   └── ...
│   │   ├── api/                   # 14 个路由模块（API 端点）
│   │   ├── services/              # 18 个业务服务
│   │   ├── rag/                   # Chroma + TF-IDF
│   │   ├── database/              # SQLAlchemy 模型 + Postgres
│   │   ├── middleware/            # 限流 + 日志脱敏 + RequestID
│   │   ├── config/                # Pydantic settings
│   │   └── main.py                # FastAPI app + lifespan
│   ├── data/                      # 广州 POI 数据（174 个）+ 闭店清单
│   ├── tests/                     # 672 个 pytest 测试
│   ├── alembic/                   # DB 迁移
│   ├── Dockerfile                 # 多阶段 + HEALTHCHECK + OCI LABEL
│   └── .dockerignore              # 12 类过滤（.git/node_modules/.venv/...）
│
├── frontend/                     # 前端应用
│   ├── src/
│   │   ├── pages/                # 7 个页面
│   │   │   ├── HomePage.tsx           # 首页（hero + 19 个广州标签 + 4 条精选路线）
│   │   │   ├── ChatPage.tsx           # 对话规划（已适配 M5.1 错误重试）
│   │   │   ├── GuidePage.tsx          # AI 虚拟导游
│   │   │   ├── ItineraryPage.tsx      # 行程展示
│   │   │   ├── ResourcesPage.tsx      # 广州景区资源调度
│   │   │   ├── ImagePage.tsx          # 拍照识景
│   │   │   ├── HistoryPage.tsx        # 历史行程
│   │   │   └── RecommendPage.tsx      # 快速推荐
│   │   ├── components/           # 18 个共享组件（含 Skeleton/Toast/PriceBadge 等）
│   │   ├── lib/                  # api.ts（含 APIError 统一解析）+ deviceId + exportPdf
│   │   ├── hooks/                # usePlanStream
│   │   ├── types/                # 自动生成的 itinerary types
│   │   └── App.tsx
│   ├── e2e/                       # Playwright E2E（28 个测试，8 个 spec 文件）
│   └── playwright.config.ts
│
└── docs/                         # 文档
    └── itinerary.schema.json     # 行程契约
```

## 🚀 快速启动

### 环境要求

- Python 3.10+ (开发用 3.11)
- Node.js 18+ (开发用 24)
- Docker Desktop（postgres + redis 容器）
- 必需 API Keys: `DEEPSEEK_API_KEY` + `MOONSHOT_API_KEY`（高德可选）

### 启动步骤

```bash
# 1. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入 DEEPSEEK_API_KEY 和 MOONSHOT_API_KEY
# 可选: AMAP_API_KEY (路线距离增强)，不填走 KB 坐标兜底

# 2. 启动 postgres + redis (Docker)
cd /mnt/d/TravelMindAgent
docker compose up -d postgres redis
# 也可以起 backend: docker compose up -d backend (用旧 image)

# 3. 启动后端（推荐本地 uvicorn 跑最新代码）
cd backend
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
SESSION_STORE=memory python -m uvicorn app.main:app --reload
# → http://localhost:8000

# 4. 启动前端
cd ../frontend
npm install
npm run dev
# → http://localhost:5173
```

### 一键 Docker 全栈

```bash
docker compose up --profile db -d backend frontend
# → http://localhost:5173 (前端)
# → http://localhost:8000 (后端)
```

## 🔗 核心 API 端点

### 对话流程
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/dialog/message` | POST | 发送对话消息 |
| `/api/v1/dialog/generate/stream` | POST | SSE 流式生成行程 |

### 导游功能
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/guide/featured` | GET | 获取精选 POI（默认广州） |
| `/api/v1/guide/search?q=...` | GET | 搜索景点 |
| `/api/v1/guide/narration/{name}` | GET | 获取讲解词 |
| `/api/v1/guide/chat` | POST | 导游模式追问 |

### 资源调度
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/resources/overview?city=广州` | GET | 资源总览仪表盘 |
| `/api/v1/resources/list` | GET | 资源列表（支持排序/筛选） |
| `/api/v1/resources/districts` | GET | 行政区列表（7 个区） |

### 行程
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/itineraries` | GET | 历史行程列表 |
| `/api/v1/itineraries/{id}` | GET | 单个行程详情 |
| `/api/v1/itineraries/{id}` | PATCH/DELETE | 更新/删除 |
| `/api/v1/agent/itinerary/share/{id}` | POST | 创建分享链接（HMAC 签名） |
| `/api/v1/agent/share/{id}?sig=...&exp=...` | GET | 验签后查看分享 |

### 收藏
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/favorites` | GET/POST | 列出/添加收藏 |
| `/api/v1/favorites/{id}` | DELETE | 删除收藏 |

### 其他
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/weather/{city}` | GET | 天气查询（Open-Meteo 免费） |
| `/api/v1/image/analyze` | POST | 拍照识景（multipart/form-data） |
| `/api/v1/recommend/quick` | POST | 快速推荐 |
| `/api/v1/health` | GET | 健康检查 |

## 🧪 开发命令

```bash
# 后端测试（672 个测试，~25s）
cd backend
.venv/bin/python -m pytest -q

# 前端类型检查
cd frontend
npx tsc -b

# 前端 lint
npm run lint

# 前端 build
npm run build

# 前端 E2E（需 docker backend 在 8000 端口 + vite 在 5173）
docker compose up -d backend      # 后端起
npx vite --port 5173 --host 127.0.0.1 &  # 前端起（手动）
npx playwright test                # 跑全部 28 个 E2E

# 全栈 E2E 验证脚本（pytest + docker compose + curl）
/tmp/hermes-verify-m5-full.py    # 见下方验证脚本章节
```

## 🎯 核心功能流程

### 1. 对话式行程规划
```
用户输入 → chat_agent → dialog_manager 提取槽位（已加固广州专属）
    → profile_agent 构建用户画像
    → 用户确认 → SSE 流式生成（orchestrator 7 步管线）
    → 行程卡片返回 → 跳转行程页
```

### 2. AI 虚拟导游
```
选择广州 POI → guide_agent 加载讲解词
    → 显示景点详情、周边推荐
    → 支持追问聊天（chatWithGuide）
```

### 3. 资源调度
```
加载广州景区数据 → KPI 仪表盘
    → 热度/价格/区域分布图
    → Top10 热度排行
    → 景区卡片列表（含调度建议）
```

## 📊 数据说明

### 广州 POI 数据
- **总数**: 174 个景区
- **分类**: 景点/美食/历史/建筑/文化/亲子/自然/夜景
- **区域**: 越秀/海珠/荔湾/天河/白云/番禺/花都/黄埔/南沙/增城/从化
- **数据字段**: 名称、标签、地址、热度、价格、坐标、更新时间

### 闭店清单
- 文件: `backend/data/known_closures.json`
- 当前为空（截至 2026-07-31 无人工核实停业项）
- **新停业**: 编辑此 JSON 即可，无需改代码

### 行程契约
- 文件: `docs/itinerary.schema.json`
- 类型: `TravelItinerary`
- 包含: 每日行程、天气、预算、清单、验证报告

## 🔧 错误处理 (Phase 18 M5.1)

所有 API 错误响应统一结构：
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "请求过于频繁,请稍后再试",
    "suggestion": "请等待 30 秒后重试,避免连续点击",
    "retryable": true,
    "details": { "retry_after_seconds": 30 }
  }
}
```

- `code`: 机器可读错误码
- `message`: 中文用户消息
- `suggestion`: 可执行的下一步建议
- `retryable`: 前端据此显示重试按钮
- `details`: 机器可读上下文

预设错误码见 `backend/app/api/errors.py:ErrorPresets`：
- `RATE_LIMITED` (限流)
- `SERVICE_UNAVAILABLE` (服务不可用)
- `LLM_TIMEOUT` (AI 超时)
- `CITY_NOT_SUPPORTED` (非广州)
- `INTERNAL_ERROR` (内部错误)
- `AUTH_REQUIRED` (缺设备标识)

前端 `api.ts` 自动解析为 `APIError` class，UI 组件可直接读 `.suggestion` / `.retryable` / `.onRetry`。

## 🔒 安全 (Phase 18 M5.3)

### 分享链接签名
- 算法: HMAC-SHA256(share_id + expires_at)
- Secret: 通过 `SHARE_SIGNING_SECRET` 环境变量配置（生产必填）
- URL 形式: `/share/{share_id}?sig={16hex}&exp={ISO}`
- 验证失败 → 404（防扫描/暴力枚举）
- 时序攻击防护: 用 `hmac.compare_digest`

### 日志脱敏
- `app.middleware.rate_limit._sanitize_log_value()`
- 自动 truncate 到 200 字符
- redact: API key / token / password / sk-xxx

### 限流
- 60 req/min/IP（可配置）
- 限流响应也用统一错误结构
- 自动清理 idle buckets（5min）

## ⚠️ 已知问题 & 注意事项

1. **API Key**: 必须配置 `DEEPSEEK_API_KEY` + `MOONSHOT_API_KEY` 才能用 AI 功能
2. **POI 数据**: 仅广州（174 个），不支持其他城市（这是大赛定位）
3. **SSE 流**: 行程生成最长 60 秒，前端已有 progress 提示 + 重试按钮
4. **价格数据**: 部分 POI 价格信息可能缺失，前端显示"暂无数据"
5. **天气**: 依赖 Open-Meteo 免费 API（无需 key）
6. **高德**: 可选。删除/留空 KEY 时，路径距离/POI 验证自动走 KB 坐标兜底
7. **跨平台开发**: 
   - 后端开发可用 WSL 或 Windows，`uv venv` 重建即可
   - 前端 Vite 8 需要重新 `npm install`（rolldown binding 平台相关）
   - Pytest fixture 用相对路径，不依赖具体磁盘

## 📝 最近更新记录

### 2026-07-31 完成 (Phase 18)

**P0 接手与稳定化**
- ✅ pytest 596 全绿（接手时 34 failed）
- ✅ Settings 加 `extra="ignore"` 防御未来 .env 字段
- ✅ .env.example 清理过时 QWEN/TENCENT，补高德可空说明
- ✅ 测试 fixture 跨平台修复（`D:/...` → 相对路径）
- ✅ 测试适配广州专属（dialog_manager / refusal / recommend / poi_health）

**M4 测试加固（+80 测试）**
- ✅ Favorites API（9 个）
- ✅ Guide API（10 个，含空查询降级）
- ✅ Resources API（11 个，含 limit 边界）
- ✅ Image API（4 个，含文件类型校验）
- ✅ 失败降级（12 个，含 LLM 超时 / RAG 失败 / Amap 空 key / 行程重试耗尽）

**M5 新功能 + 安全**
- ✅ M5.1 错误响应结构升级：`{code, message, suggestion, retryable, details}`
- ✅ M5.1 `ErrorPresets` 6 个常用错误预设（rate_limited/llm_timeout/city_not_supported 等）
- ✅ M5.1 前端 `api.ts` 解析 → `APIError` class；ChatPage 显示 suggestion + 重试按钮
- ✅ M5.3 分享链接 HMAC-SHA256 签名（含 11 个新测试）
- ✅ M5.3 限流响应统一错误格式
- ✅ M5.3 日志脱敏 `_sanitize_log_value`（含 5 个新测试）
- ✅ M5.4 Dockerfile 加 OCI LABEL + HEALTHCHECK + pg_isready
- ✅ M5.4 `.dockerignore` 12 类过滤

**前端 E2E（28 个测试）**
- ✅ Playwright 配置完整（chromium-headless-shell）
- ✅ 8 个 spec 文件：home/chat/guide/itinerary/history/recommend/theme/navigation
- ✅ 适配广州专属路径（/resources 取代 /recommend）
- ✅ ChatPage 错误测试覆盖 suggestion + retry 按钮

**最终战绩**
- 后端测试: **672 passed**（接手时 563 passed / 34 failed）
- 前端 E2E: **28 passed**
- Docker backend: **healthy**（compose up 后 12s 内通过 healthcheck）
- 大赛交付就绪

### 已下线功能
- ❌ 全国多城市推荐（UI/状态机仅广州）
- ❌ 模糊 KB 跨城市兜底（KB 锁死广州）
- ❌ `src/api/itineraries.py` 中的跨城 itinerary 关联

## 🔗 验收脚本

`/tmp/hermes-verify-m5-full.py`（临时验证，已清理但可重建）：
```python
# 1. pytest 全量
# 2. docker compose up -d backend
# 3. 等容器 healthy
# 4. curl /api/v1/health
# 5. docker compose down
```

---

**接手人**: Hermes (接手于 2026-07-31)
**交接人**: TRAE Agent
**项目状态**: ✅ 生产级，可发版/参赛
**目标**: 🎯 广州 AI+旅游休闲大赛专用智能体