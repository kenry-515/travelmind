@echo off
rem TravelMind Agent - one-click dev startup (backend + frontend)
rem Double-click this file, then open http://localhost:5173

start "TravelMind Backend  (:8000)" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
start "TravelMind Frontend (:5173)" cmd /k "cd /d %~dp0frontend && npm run dev"

echo Backend  -^> http://localhost:8000/api/v1/health
echo Frontend -^> http://localhost:5173
