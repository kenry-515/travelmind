# TravelMind Agent (智游伴)

AI-powered multi-agent travel planning system — from a single user sentence **or a travel photo** to a complete travel itinerary.

## Overview

TravelMind Agent leverages LLM-based multi-agent collaboration, RAG knowledge enhancement, and multimodal understanding to deliver personalized travel recommendations. A LangGraph workflow orchestrates the pipeline: Profile → Trend → Weather → RAG → Recommendation → Planning.

**Status:** ✅ Phase 5 complete — multimodal image analysis live. Phase 6 (demo polish) in progress.

### Core Features

- **一句话生成行程** — natural language request → structured itinerary with timed attractions, meals, transport tips and weather
- **智能推荐** — 6-factor weighted scoring (preference / trend / budget / location / time / reliability) over an 896-attraction knowledge base (15 cities)
- **图片识别（多模态）** — upload a travel photo, Kimi `kimi-k2.6` recognizes location & style tags, then closes the loop by recommending similar attractions from the same tags
- **AI 对话** — streaming travel Q&A (SSE)
- **天气建议** — 7-day forecast with travel suitability scores (Open-Meteo, no key required)

## Architecture

```
L1: User Interaction  — React 19 + TS + Vite + Tailwind 4
L2: API Service       — FastAPI REST /api/v1/* (10 routes)
L3: Agent Intelligence — LangGraph StateGraph (Orchestrator + 6 Agents)
L4: AI Capability     — DeepSeek (LLM) / Kimi k2.6 (Vision) / TF-IDF+Tag Embedding
L5: Data Resource     — Chroma (1075-dim vectors) + JSON knowledge base (+ optional PostgreSQL)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript 6, Vite 8, Tailwind CSS 4, shadcn/ui, Lucide |
| Backend | Python 3.11, FastAPI, Pydantic v2 |
| AI/LLM | DeepSeek (chat), Kimi `kimi-k2.6` (vision), LangGraph (orchestration) |
| RAG | Chroma + sklearn TF-IDF (70%) & tag one-hot (30%) = 1075-dim composite |
| Maps | Amap/高德 (POI, routing, distance matrix; MD5-signed) |
| Weather | Open-Meteo (free, no key) |
| Database | PostgreSQL (optional — system runs fine offline without it) |

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env      # fill in your API keys (see below)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev               # http://localhost:5173 (proxies /api → :8000)
```

Windows 一键启动（开发）：双击根目录 `start-dev.bat`。

### Environment Variables (`backend/.env`)
- `DEEPSEEK_API_KEY` — DeepSeek API key（主 LLM，必需）
- `MOONSHOT_API_KEY` — Kimi 开放平台 key（图片识别，必需；platform.kimi.com 创建）
- `AMAP_API_KEY` + `AMAP_SIGN_KEY` — 高德 API key + 数字签名私钥（路线/距离矩阵）
- `DATABASE_URL` — PostgreSQL（可选，不配置则降级运行）
- 其余默认值见 `backend/.env.example`

## API Routes (`/api/v1`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| POST | `/chat` | Streaming travel Q&A (SSE) |
| POST | `/agent/plan` | Full pipeline: Profile→Trend→Weather→RAG→Recommend→Plan |
| POST | `/agent/profile` | Standalone NL profile extraction |
| POST | `/recommend` | NL query → ranked places (no itinerary) |
| POST | `/recommend/quick` | Pre-extracted {city, tags} → ranked places |
| GET | `/weather/cities` | Supported cities |
| GET | `/weather/{city}` | 7-day forecast + travel scores |
| POST | `/weather/travel-advice` | Simplified weather advice |
| POST | `/image/analyze` | Photo → {location, tags, description, confidence} (Kimi vision) |

## Project Structure

```
TravelMindAgent/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry (lifespan: RAG init)
│   │   ├── config/settings.py   # pydantic-settings
│   │   ├── api/                 # 6 routers: health/chat/agent/recommend/weather/image
│   │   ├── agents/              # orchestrator, profile, trend, recommendation,
│   │   │                        # planning, vision
│   │   ├── services/            # llm(DeepSeek), vision(Kimi), amap, weather
│   │   └── rag/                 # TF-IDF+tag embedding, Chroma store, retriever
│   ├── scripts/                 # data pipeline (wikidata/wikipedia/amap/AI-enrich/build)
│   └── data/                    # knowledge base: attractions(896)/trends(84)/tags(51)
├── frontend/src/
│   ├── pages/                   # Home / Chat / Recommend / Itinerary / Image
│   ├── components/              # SearchInput, ChatBox, PlaceCard, ScoreBar,
│   │                            # ImageUploader, Toast, ErrorBoundary, ...
│   └── lib/api.ts               # typed API client (axios)
├── docs/                        # incl. DEMO_GUIDE.md
└── start-dev.bat                # Windows one-click dev startup
```

## License

MIT
