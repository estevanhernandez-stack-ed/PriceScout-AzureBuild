# PriceScout Full Stack Development Startup Script
# Run with: .\start_dev.ps1

Write-Host "========================================"  -ForegroundColor Cyan
Write-Host "  PriceScout Full Stack Development"     -ForegroundColor Cyan
Write-Host "========================================"  -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Start FastAPI backend in a new window
Write-Host "Starting FastAPI backend on port 8000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir'; .\.venv\Scripts\Activate.ps1; uvicorn api.main:app --reload --port 8000"

# Wait for backend to start
Start-Sleep -Seconds 3

# Start React frontend in a new window
Write-Host "Starting React frontend on port 3000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\frontend'; npm run dev"

Write-Host ""
Write-Host "========================================"  -ForegroundColor Cyan
Write-Host "  Both servers starting..."              -ForegroundColor Cyan
Write-Host "  API:      http://localhost:8000"       -ForegroundColor Yellow
Write-Host "  Frontend: http://localhost:3000"       -ForegroundColor Yellow
Write-Host "  API Docs: http://localhost:8000/docs"  -ForegroundColor Yellow
Write-Host "========================================"  -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to exit this window..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
