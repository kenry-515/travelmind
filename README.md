# TravelMind Agent (智游伴)

AI-powered multi-agent travel planning system — from a single user sentence to a complete travel itinerary.

## Overview

TravelMind Agent leverages LLM-based multi-agent collaboration, RAG knowledge enhancement, and multi-modal understanding to deliver personalized travel recommendations. The system orchestrates 6 specialized agents (Profile, Trend, RAG Retriever, Recommendation, Planning, Vision) through a LangGraph workflow.

**Status:** 🚧 Phase 1 — Foundation (MVP in 14 days)

## Architecture

```
L1: User Interaction  — React + TS + Vite + Tailwind + shadcn/ui
L2: API Service       — FastAPI REST /api/v1/*
L3: Agent Intelligence — LangGraph StateGraph (Orchestrator + 6 Agents)
L4: AI Capability     — LLM / Vision / Embedding Services
L5: Data Resource     — PostgreSQL + Chroma + File Storage
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| AI/LLM | DeepSeek (chat), Qwen-VL (vision), LangGraph (agent orchestration) |
| RAG | LangChain + Chroma |
| Maps | Amap (POI), Baidu (routing) |
| Weather | Open-Meteo (free, no key) |
| Database | PostgreSQL + Chroma |

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+

### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
cp .env.example .env      # fill in your API keys
uvicorn app.main:app --reload
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Environment Variables
Copy `.env.example` to `backend/.env` and fill in:
- `DEEPSEEK_API_KEY` — DeepSeek API key (required for LLM)
- `QWEN_API_KEY` — Qwen-VL API key (required for vision)
- `AMAP_API_KEY` — Amap/高德 API key (required for POI data)
- `BAIDU_MAP_AK` — Baidu Maps API key (required for routing)

## Project Structure

```
TravelMindAgent/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config/settings.py    # pydantic-settings
│   │   ├── database/            # SQLAlchemy async + models
│   │   ├── api/                 # REST endpoints
│   │   ├── agents/              # LangGraph agents
│   │   ├── services/            # External service integrations
│   │   └── rag/                 # RAG: embedding, vector store, retriever
│   ├── scripts/                 # Data pipeline scripts
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/          # Reusable UI components
│       ├── pages/               # Route pages
│       └── lib/                 # Utilities
├── data/                        # Generated knowledge base (gitignored)
└── docs/                        # Documentation
```

## License

MIT
