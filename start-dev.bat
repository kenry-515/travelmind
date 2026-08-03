@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
rem ============================================================
rem  TravelMind Agent — Windows dev launcher (backend + frontend)
rem  Double-click this file (or run from cmd/PowerShell)
rem  Open http://localhost:5173 in your browser after ~30s
rem ============================================================

rem Resolve script directory (handles spaces in paths)
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo ==========================================
echo  TravelMind Agent — Starting dev stack
echo  ROOT = %ROOT%
echo ==========================================
echo.

rem ── 0. Sanity checks ───────────────────────────────
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo         Install Python 3.11+ from https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js not found in PATH.
    echo         Install Node.js 22+ from https://nodejs.org/
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
for /f "tokens=1 delims=." %%i in ("%PYVER%") do set PYMAJOR=%%i
echo [OK] Python %PYVER%
echo [OK] Node.js: 
node --version
echo.

rem ── 1. Backend setup ──────────────────────────────
set "BACKEND_DIR=%ROOT%\backend"
if not exist "%BACKEND_DIR%\app\main.py" (
    echo [ERROR] Backend dir not found: %BACKEND_DIR%
    pause
    exit /b 1
)

rem Check .env exists; copy from example if missing
if not exist "%BACKEND_DIR%\.env" (
    if exist "%BACKEND_DIR%\.env.example" (
        echo [INFO] Copying .env.example to .env (please edit DEEPSEEK_API_KEY!)
        copy /Y "%BACKEND_DIR%\.env.example" "%BACKEND_DIR%\.env" >nul
    ) else (
        echo [ERROR] .env and .env.example both missing in backend\
        pause
        exit /b 1
    )
)

rem Warn if DEEPSEEK_API_KEY is still the placeholder
findstr /C:"DEEPSEEK_API_KEY=sk-xxx" "%BACKEND_DIR%\.env" >nul 2>nul
if not errorlevel 1 (
    echo.
    echo [WARNING] DEEPSEEK_API_KEY is still the placeholder "sk-xxx".
    echo           Edit backend\.env and set a real key before generating itineraries.
    echo.
)

rem Install backend deps if missing (check uvicorn module)
python -c "import uvicorn" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing backend dependencies ^(this can take 1-2 min^)...
    pushd "%BACKEND_DIR%"
    python -m pip install --upgrade pip
    python -m pip install -r requirements-prod.txt
    if errorlevel 1 (
        echo [ERROR] pip install failed. Check your network/proxy.
        popd
        pause
        exit /b 1
    )
    popd
    echo [OK] Backend deps installed.
) else (
    echo [OK] Backend deps already installed.
)
echo.

rem ── 2. Frontend setup ─────────────────────────────
set "FRONTEND_DIR=%ROOT%\frontend"
if not exist "%FRONTEND_DIR%\package.json" (
    echo [ERROR] Frontend dir not found: %FRONTEND_DIR%
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo [INFO] Installing frontend dependencies ^(this can take 2-3 min^)...
    pushd "%FRONTEND_DIR%"
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed. Check your network/proxy.
        popd
        pause
        exit /b 1
    )
    popd
    echo [OK] Frontend deps installed.
) else (
    echo [OK] Frontend deps already installed.
)
echo.

rem ── 3. Launch backend + frontend ───────────────────
echo [INFO] Starting backend ^(port 8000^) ...
start "TravelMind Backend  (:8000)" cmd /k "cd /d "%BACKEND_DIR%" && python -m app.main"

echo [INFO] Starting frontend ^(port 5173^) ...
start "TravelMind Frontend (:5173)" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

echo.
echo ==========================================
echo  Both servers starting in new windows.
echo.
echo   Backend  -^> http://localhost:8000/api/v1/health
echo   Frontend -^> http://localhost:5173
echo.
echo  Wait ~20-30s for backend RAG warmup, then open:
echo    http://localhost:5173/chat       (旅程规划)
echo    http://localhost:5173/resources  (资源调度)
echo    http://localhost:5173/guide      (虚拟导游)
echo    http://localhost:5173/image      (拍照识景)
echo.
echo  To stop: close both cmd windows, or:
echo    taskkill /FI "WINDOWTITLE:TravelMind*"
echo ==========================================
echo.
echo Press any key to close this launcher window...
pause >nul