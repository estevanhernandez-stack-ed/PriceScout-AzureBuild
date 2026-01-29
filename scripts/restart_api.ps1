# Restart the API server
Set-Location "c:\Users\estev\Desktop\theatre-operations-platform\apps\pricescout-react"

# Kill any existing uvicorn on port 8001
$proc = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | Get-Process -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "Stopping existing process on port 8001..."
    Stop-Process $proc -Force
    Start-Sleep 2
}

# Start new uvicorn process
Write-Host "Starting API server on port 8001..."
Start-Process cmd -ArgumentList '/k cd /d c:\Users\estev\Desktop\theatre-operations-platform\apps\pricescout-react && .venv\Scripts\activate && uvicorn api.main:app --reload --port 8001' -WindowStyle Normal
