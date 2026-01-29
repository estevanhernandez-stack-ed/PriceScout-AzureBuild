@echo off
echo ========================================
echo   PriceScout Full Stack Development
echo ========================================
echo.

REM Start FastAPI backend in a new window
echo Starting FastAPI backend on port 8000...
start "PriceScout API" cmd /k "cd /d %~dp0 && .venv\Scripts\activate && uvicorn api.main:app --reload --port 8000"

REM Wait a moment for backend to start
timeout /t 3 /nobreak > nul

REM Start React frontend in a new window
echo Starting React frontend on port 3000...
start "PriceScout Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================
echo   Both servers starting...
echo   API:      http://localhost:8000
echo   Frontend: http://localhost:3000
echo   API Docs: http://localhost:8000/api/v1/docs
echo ========================================
echo.
echo Press any key to exit this window...
pause > nul
