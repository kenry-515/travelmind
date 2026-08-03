# 羊城智游 · 广州 AI 旅游智能体

> AI+旅游休闲大赛 · 广州专属 AI 旅行规划助手
> React 19 + FastAPI + DeepSeek + RAG

[![CI](https://img.shields.io/github/actions/workflow/status/kenry-515/travelmind/ci.yml?branch=main&label=CI&logo=github)](https://github.com/kenry-515/travelmind/actions/workflows/ci.yml)
[![E2E](https://img.shields.io/github/actions/workflow/status/kenry-515/travelmind/e2e.yml?branch=main&label=E2E&logo=playwright)](https://github.com/kenry-515/travelmind/actions/workflows/e2e.yml)
[![Backend Tests](https://img.shields.io/github/actions/workflow/status/kenry-515/travelmind/backend-tests.yml?branch=main&label=backend%20tests&logo=pytest)](https://github.com/kenry-515/travelmind/actions)
[![Backend Tests](https://img.shields.io/badge/tests-718%20passing-brightgreen?logo=pytest)](backend/tests/)
[![E2E Tests](https://img.shields.io/badge/e2e-28%20passing-brightgreen?logo=playwright)](frontend/e2e/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg?logo=python&logoColor=white)](https://www.python.org)
[![Node](https://img.shields.io/badge/node-22+-green.svg?logo=node.js&logoColor=white)](https://nodejs.org)

---

## 🚀 快速开始（3 种方式，按需选择）

### 方式 A：本地 Python（最快，推荐开发用）

**前置**: Python 3.11+ 已装

```powershell
# Windows PowerShell / macOS / Linux 通用

# 1. 克隆 & 配置
git clone https://github.com/kenry-515/travelmind.git
cd travelmind
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入 DEEPSEEK_API_KEY（其他 key 默认即可）

# 2. 启动后端
cd backend
pip install -r requirements-prod.txt
python -m app.main
# ✅ 看到 "Uvicorn running on http://0.0.0.0:8000" 即启动成功
# → http://localhost:8000
# → 健康检查: http://localhost:8000/api/v1/health

# 3. 启动前端（新终端窗口）
cd ..\frontend    # Windows
# cd ../frontend  # macOS / Linux
npm install
npm run dev
# → http://localhost:5173
```

### 方式 B：WSL 2 + uv venv（推荐生产用）

WSL 2 + uv 是当前生产部署方案，参考 [docs/DEPLOY.md](docs/DEPLOY.md)

```bash
# WSL Ubuntu
wsl --install -d Ubuntu
sudo apt update && sudo apt install -y build-essential

# 安装 uv（Python 包管理）
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# 启动后端
cd /mnt/d/travelmind/backend   # 或你 clone 的路径
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements-prod.txt
cp .env.example .env  # 编辑填 DEEPSEEK_API_KEY
python -m app.main
# → http://localhost:8000
```

### 方式 C：Docker Compose（一键全套）

```bash
# 前置: Docker Desktop 已运行

# 1. 启动 Redis + Postgres + Backend + Frontend
docker compose up -d
# 等 30s 让 backend 启动（RAG 预热需要时间）

# 2. 验证
curl http://localhost:8000/api/v1/health
# → {"status":"ok",...}

# 前端: http://localhost:8080
# 后端 API: http://localhost:8000
```

---

## ⚠️ Windows 启动常见问题

### Q1: `python -m app.main` 没反应 / 窗口一闪就关

**原因**: Python 找不到包，或依赖未装。

**解决**:
```powershell
# 在 backend 目录里
python --version                              # 确认 Python 3.11+
pip install -r requirements-prod.txt          # 必须用 prod 不是 dev
python -c "import fastapi; print('OK')"      # 测试 import
python -m app.main                            # 应看到 "Uvicorn running on..."
```

### Q2: 端口 8000 被占用

**解决**:
```powershell
# 查看占用
netstat -ano | findstr :8000
# 杀掉进程
taskkill /PID <进程ID> /F

# 或换端口启动
$env:APP_PORT=8001
python -m app.main
```

### Q3: `.env` 文件找不到 / API Key 未生效

**解决**:
```powershell
# .env 必须在 backend/ 目录，跟 app/ 同级
backend/
├── .env          ← 在这里
├── app/
├── data/
└── requirements-prod.txt
```

### Q4: 启动报 `ModuleNotFoundError`

**原因**: 没在 backend 目录启动。

**解决**: `cd backend` 后再 `python -m app.main`。

### Q5: 中文 POI 显示乱码

**Windows 终端**: 设置 `PYTHONIOENCODING=utf-8`
```powershell
$env:PYTHONIOENCODING="utf-8"
python -m app.main
```

---

## 🏙️ 项目特色

### 广州专属
- **184 个**广州景区 POI 数据（11 个行政区全覆盖：越秀/荔湾/海珠/天河/白云/黄埔/番禺/花都/南沙/从化/增城）
- 西关文化、珠江夜游、粤式美食、长隆亲子等特色路线
- 76 个真实图片（Wikipedia Commons）+ 31 天价格日历 + 8 时段调度

### 🤖 核心功能

| 功能 | 页面 | 说明 |
|------|------|------|
| AI 行程规划 | `/chat` | 多轮对话式定制广州行程 + 收藏栏联动 |
| AI 虚拟导游 | `/guide` | 广州景点智能讲解 + AI 伴游对话 |
| 景区资源调度 | `/resources` | 184 景区热度可视化、错峰建议、价格日历 |
| 拍照识景 | `/image` | 上传照片 → Kimi Vision 识别 → AI 讲解 |
| 收藏栏 | `/favorites` | 用户加 POI 进收藏，二次规划时优先 |

### 🎯 技术架构

```
React 19 + TypeScript + Tailwind
    ↓ HTTP / SSE
FastAPI + uvicorn (本项目 Python 3.11+)
    ↓
7步 Agent 管线: Profile → Trend → Weather → RAG → Recommend → Plan → Aggregator
    ↓
DeepSeek v4-flash (LLM) + Chroma RAG + Open-Meteo 天气
    ↓
attractions.json (184 POI, 11 区) + session store (Redis/内存)
```

---

## 📡 API 端点（部分）

启动后访问 http://localhost:8000/docs 看完整 OpenAPI 文档。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/health` | GET | 健康检查（包含所有依赖） |
| `/api/v1/health/live` | GET | 进程存活 |
| `/api/v1/health/ready` | GET | 依赖就绪 |
| `/api/v1/dialog/message` | POST | 多轮对话（槽位填充） |
| `/api/v1/dialog/generate` | POST | 生成行程卡 |
| `/api/v1/guide/narration/{poi_name}` | GET | 虚拟导游讲解 |
| `/api/v1/guide/chat` | POST | 虚拟导游对话 |
| `/api/v1/image/analyze-with-guide` | POST | 拍照识景 + 整合讲解 |
| `/api/v1/resources/overview` | GET | 资源总览（184 POI 11 区） |
| `/api/v1/resources/calendar/{poi_name}` | GET | 31 天价格日历 |
| `/api/v1/resources/schedule/{poi_name}` | GET | 8 时段调度建议 |
| `/api/v1/favorites` | GET/POST/DELETE | 收藏栏 |
| `/api/v1/favorites/pois` | GET | 一键拉所有收藏 POI |

---

## 🧪 测试

```bash
cd backend

# 单元 + 集成测试
pytest --no-cov
# 当前: 718 passed, 0 failed

# 端到端: 启动 backend + frontend 后
cd ../frontend
npm run test:e2e
# 当前: 28 passed
```

---

## 📁 项目结构

```
travelmind/
├── backend/              # Python FastAPI 后端
│   ├── app/
│   │   ├── agents/       # 7 步 Agent 管线
│   │   ├── api/          # REST 路由
│   │   ├── services/     # LLM / Vision / Cache / Session
│   │   └── main.py
│   ├── data/             # POI 数据 (184 广州景点)
│   ├── tests/            # pytest 718 passed
│   ├── .env.example
│   └── requirements-prod.txt
├── frontend/             # React 19 + Vite
│   ├── src/
│   └── e2e/              # Playwright 28 passed
├── docs/                 # 设计文档 + 部署指南
├── docker-compose.yml
└── README.md
```

---

## 🚢 部署

参考 [docs/DEPLOY.md](docs/DEPLOY.md)：

- WSL 2 + Docker Desktop (Mirrored networking)
- 阿里云 / 腾讯云 ECS
- 国内访问：DeepSeek + 高德 AMAP 配额注意

---

## 📄 License

MIT