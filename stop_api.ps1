# Stop processes on port 8000
$processIds = netstat -ano | Select-String ":8000" | Select-String "LISTENING" | ForEach-Object { ($_ -split '\s+')[-1] } | Sort-Object -Unique
foreach ($procId in $processIds) {
    if ($procId -match '^\d+$') {
        Write-Host "Stopping process $procId"
        Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
    }
}
Write-Host "Done stopping processes on port 8000"
