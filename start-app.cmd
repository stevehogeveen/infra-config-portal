@echo off
setlocal

set "REPO_ROOT=%~dp0"
set "BACKEND_PORT=8002"
set "FRONTEND_PORT=5175"

echo Starting Infra Config Portal backend on port %BACKEND_PORT% ...
start "Infra Portal Backend" /D "%REPO_ROOT%app\backend" cmd /c "set PROVIDER_MODE=local-lab-readwrite&& .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port %BACKEND_PORT%"

echo Starting Infra Config Portal frontend on port %FRONTEND_PORT% ...
start "Infra Portal Frontend" /D "%REPO_ROOT%app\frontend" cmd /c "set FRONTEND_PORT=%FRONTEND_PORT%&& set FRONTEND_HOST=127.0.0.1&& set APP_PROXY_TARGET=http://127.0.0.1:%BACKEND_PORT%&& npm run dev"

echo.
echo Waiting for the frontend to come up...
set /a tries=0
:waitloop
set /a tries+=1
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:%FRONTEND_PORT%/' -UseBasicParsing -TimeoutSec 2) | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    if %tries% GEQ 45 (
        echo Frontend did not come up in time. Check the "Infra Portal Backend" / "Infra Portal Frontend" windows for errors.
        pause
        exit /b 1
    )
    timeout /t 1 >nul
    goto waitloop
)

echo Frontend is up. Opening browser...
start "" "http://127.0.0.1:%FRONTEND_PORT%/overview"

echo.
echo Infra Config Portal is running.
echo Backend and frontend are running in their own windows - close those windows to stop them.
echo This window can be closed safely.
timeout /t 5 >nul
