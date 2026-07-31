# 羊城智游 · 广州 AI 旅游智能体

> AI+旅游休闲大赛 · 广州专属 AI 旅行规划助手
> React 19 + FastAPI + DeepSeek + RAG

[![CI](https://img.shields.io/github/actions/workflow/status/kenry-515/travelmind/ci.yml?branch=main&label=CI&logo=github)](https://github.com/kenry-515/travelmind/actions/workflows/ci.yml)
[![E2E](https://img.shields.io/github/actions/workflow/status/kenry-515/travelmind/e2e.yml?branch=main&label=E2E&logo=playwright)](https://github.com/kenry-515/travelmind/actions/workflows/e2e.yml)
[![Backend Tests](https://img.shields.io/badge/tests-672%20passing-brightgreen?logo=pytest)](backend/tests/)
[![E2E Tests](https://img.shields.io/badge/e2e-28%20passing-brightgreen?logo=playwright)](frontend/e2e/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg?logo=python)](https://www.python.org)
[![Node](https://img.shields.io/badge/node-22+-green.svg?logo=node.js)](https://nodejs.org)

## 快速开始

```bash
# 1. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入 DEEPSEEK_API_KEY

# 2. 启动后端
cd backend
pip install -r requirements.txt
python -m app.main
# → http://localhost:8000

# 3. 启动前端（新终端）
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

## 项目特色

### 🏙️ 广州专属
- 174 个广州景区 POI 数据
- 7 个行政区覆盖（越秀/海珠/荔湾/天河/白云/番禺/花都）
- 西关文化、珠江夜游、粤式美食等特色路线

### 🤖 核心功能
| 功能 | 页面 | 说明 |
|------|------|------|
| AI 行程规划 | `/chat` | 多轮对话式定制广州行程 |
| AI 虚拟导游 | `/guide` | 广州景点智能讲解伴游 |
| 景区资源调度 | `/resources` | 168+ 景区热度可视化与错峰建议 |
| 拍照识景 | `/image` | 上传照片智能识别广州景点 |

### 🎯 技术架构
```
React 19 + TypeScript + Tailwind
    ↓ HTTP / SSE
FastAPI + uvicorn
    ↓
7步 Agent 管线: Profile → Trend → Weather → RAG → Recommend → Plan → Aggregator
    ↓
DeepSeek v4-flash (LLM) + Chroma RAG + Open-Meteo 天气
```

## API 端点

启动后端后访问:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 核心 API
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/dialog/message` | POST | 对话消息 |
| `/api/v1/dialog/generate/stream` | POST | SSE 流式生成行程 |
| `/api/v1/guide/featured` | GET | 精选 POI |
| `/api/v1/guide/search` | GET | 景点搜索 |
| `/api/v1/guide/narration/{name}` | GET | AI 讲解词 |
| `/api/v1/resources/overview` | GET | 资源仪表盘 |
| `/api/v1/resources/list` | GET | 资源列表 |
| `/api/v1/weather` | GET | 天气查询 |

## 开发命令

```bash
# 后端测试
cd backend
python -m pytest -q

# 前端检查
cd frontend
npx tsc -b          # 类型检查
npm run lint        # 代码检查
```

## 项目结构

```
TravelMindAgent/
├── backend/              # 后端服务
│   ├── app/
│   │   ├── agents/       # 7 个 Agent 模块
│   │   ├── api/          # API 路由
│   │   ├── services/     # 业务服务
│   │   └── rag/          # RAG 检索
│   ├── data/             # 广州 POI 数据
│   └── tests/            # 单元测试
├── frontend/             # 前端应用
│   ├── src/
│   │   ├── pages/        # 6 个页面
│   │   ├── components/  # 共享组件
│   │   └── lib/          # API 封装
│   └── e2e/              # E2E 测试
└── docs/                 # 文档
    └── itinerary.schema.json
```

## 文档

- [接手文档 HANDOFF](HANDOFF.md) — 详细的项目交接文档
- [行程契约](docs/itinerary.schema.json) — 行程数据 Schema

---

**羊城智游** · 广州专属 AI 旅行规划智能体  
Powered by AI+旅游休闲大赛
